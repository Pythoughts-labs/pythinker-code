"""EventSink: opt-out check, context enrichment, buffer management, timed flush.

Forwards every accepted event to OpenTelemetry as a structured log record.
The earlier custom-HTTP transport that posted to ``telemetry-logs.pythinker.com``
was retired in the SigNoz migration — the OTel exporter inside ``otel.py`` now
handles batching, retries, and disk-spool semantics on its own.
"""

from __future__ import annotations

import asyncio
import locale
import os
import platform
import threading
from typing import Any, cast

from pythinker_code.utils.logging import logger


def _assert_primitive(scope: str, key: str, value: Any) -> None:
    """Telemetry attribute values must be primitives. Catches accidental
    nested dicts/lists before they reach the OTel SDK serializer."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    raise TypeError(f"telemetry {scope}.{key} must be primitive, got {type(value).__name__}")


def _flatten_event(event: dict[str, Any]) -> dict[str, Any]:
    """Expand ``properties``/``context`` sub-dicts into flat ``property.*`` /
    ``context.*`` keys for OTel attributes. Top-level fields pass through.

    Raises ``TypeError`` on nested values inside properties/context.
    """
    out: dict[str, Any] = {}
    for key, value in event.items():
        if key == "properties":
            properties = cast(dict[str, Any], value) if isinstance(value, dict) else {}
            for pk, pv in properties.items():
                _assert_primitive("property", pk, pv)
                out[f"property.{pk}"] = pv
        elif key == "context":
            context = cast(dict[str, Any], value) if isinstance(value, dict) else {}
            for ck, cv in context.items():
                _assert_primitive("context", ck, cv)
                out[f"context.{ck}"] = cv
        else:
            out[key] = value
    return out


# Event names whose telemetry must be recorded at ERROR severity, so SigNoz
# severity filters and error dashboards can find them. Without this, track()
# forwards everything at the emit_log() default of INFO, leaving crashes and
# handled errors indistinguishable from product-analytics events.
_ERROR_EVENTS = frozenset({"error", "crash", "api_error"})

# Telemetry event name -> OTel severity. Names not listed stay INFO.
_EVENT_SEVERITY: dict[str, str] = {
    **dict.fromkeys(_ERROR_EVENTS, "error"),
    # A session that failed to load but fell back to a fresh state is degraded,
    # not broken — surface it above INFO without crying ERROR.
    "session_load_failed": "warning",
}


def _event_severity(event_name: str) -> str:
    """Map a telemetry event name to an OTel severity (defaults to ``info``)."""
    return _EVENT_SEVERITY.get(event_name, "info")


def _apply_canonical_error_attrs(event_name: str, attrs: dict[str, Any]) -> None:
    """Add stable, queryable ``error.*`` attributes for error-like events.

    Call sites are inconsistent: crashes and API errors carry ``error_type``
    while handled errors carry ``exc_class`` — which, after flattening, become
    ``property.error_type`` / ``property.exc_class``. Dashboards shouldn't have
    to know which. Mirror the discriminator into canonical top-level keys while
    leaving the original ``property.*`` values untouched. Mutates ``attrs``.
    """
    if event_name not in _ERROR_EVENTS:
        return
    error_type = attrs.get("property.error_type") or attrs.get("property.exc_class")
    if error_type is not None:
        attrs.setdefault("error.type", error_type)
    site = attrs.get("property.site")
    if site is not None:
        attrs.setdefault("error.site", site)
    if "property.expected" in attrs:
        attrs.setdefault("error.expected", attrs["property.expected"])
    # 'error' (handled) vs 'crash' (uncaught) vs 'api_error' (provider call).
    attrs.setdefault("error.kind", event_name)


def emit_events_to_otel(events: list[dict[str, Any]]) -> None:
    """Forward telemetry events to the OTel logs pipeline.

    Shared by :meth:`EventSink._emit_to_otel` and the crash-safe queue drain in
    :func:`pythinker_code.telemetry.flush_sync`, so a startup crash that occurs
    before any sink is attached still reaches SigNoz. ``otel.emit_log`` is a
    no-op when the SDK was never initialized, so this is always safe to call.
    """
    if not events:
        return
    try:
        from pythinker_code.telemetry import otel as _otel
    except Exception as exc:
        logger.debug(
            "Telemetry OTel import failed; dropping {n} events: {err}",
            n=len(events),
            err=exc,
        )
        return

    for event in events:
        event_name = str(event.get("event") or "event")
        ts = event.get("timestamp")
        ts_ns = int(ts * 1_000_000_000) if isinstance(ts, (int, float)) else None
        try:
            attrs = _flatten_event(event)
        except TypeError as exc:
            # Schema violation — drop, never retry.
            logger.debug("Telemetry event dropped (non-primitive attr): {err}", err=exc)
            continue
        attrs.pop("event", None)
        attrs.pop("timestamp", None)
        _apply_canonical_error_attrs(event_name, attrs)
        try:
            _otel.emit_log(
                name=event_name,
                attributes=attrs,
                severity=_event_severity(event_name),
                timestamp_ns=ts_ns,
            )
        except Exception:
            logger.debug("OTel emit failed; event dropped")


class EventSink:
    """Buffers telemetry events and flushes them in batches to OTel logs."""

    FLUSH_INTERVAL_S = 30.0
    FLUSH_THRESHOLD = 50

    def __init__(
        self,
        *,
        version: str = "",
        model: str = "",
        ui_mode: str = "shell",
    ) -> None:
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        # Static context enrichment
        self._context: dict[str, Any] = {
            "version": version,
            "runtime": "python",
            "platform": platform.system().lower(),
            "arch": platform.machine(),
            "python_version": platform.python_version(),
            "os_version": platform.release(),
            "ci": bool(os.environ.get("CI")),
            "locale": locale.getlocale()[0] or "",
            "terminal": os.environ.get("TERM_PROGRAM", ""),
        }
        self._model = model
        self._ui_mode = ui_mode

    def accept(self, event: dict[str, Any]) -> None:
        """Accept an event into the buffer. Non-blocking, thread-safe."""
        # Enrich with static context (copy to avoid mutating the caller's dict)
        ctx = {**self._context, "ui_mode": self._ui_mode}
        if self._model:
            ctx["model"] = self._model
        enriched = {**event, "context": ctx}

        with self._lock:
            self._buffer.append(enriched)
            should_flush = len(self._buffer) >= self.FLUSH_THRESHOLD

        if should_flush:
            self._schedule_async_flush()

    def start_periodic_flush(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Start a background task that flushes every FLUSH_INTERVAL_S seconds."""
        if self._flush_task is not None:
            return

        async def _periodic() -> None:
            try:
                while True:
                    await asyncio.sleep(self.FLUSH_INTERVAL_S)
                    await self._flush_async()
            except asyncio.CancelledError:
                pass

        if loop is None:
            loop = asyncio.get_running_loop()
        self._flush_task = loop.create_task(_periodic())

    async def retry_disk_events(self) -> None:
        """Compatibility shim — disk retries now happen inside the OTel
        exporter. No-op kept so existing callers don't break."""

    def clear_buffer(self) -> None:
        """Discard all buffered events without sending them."""
        with self._lock:
            self._buffer.clear()

    def stop_periodic_flush(self) -> None:
        """Cancel the periodic flush task."""
        if self._flush_task is not None:
            self._flush_task.cancel()
            self._flush_task = None

    async def flush(self) -> None:
        """Async flush: send all buffered events."""
        await self._flush_async()

    def flush_sync(self) -> None:
        """Synchronous flush for atexit / signal handlers.

        Drops the in-process buffer into the OTel pipeline. Network I/O is
        scheduled by the BatchLogRecordProcessor; the OTel SDK's own shutdown
        (called from ``otel.shutdown``) waits for that batch to drain.
        """
        with self._lock:
            if not self._buffer:
                return
            events = list(self._buffer)
            self._buffer.clear()
        self._emit_to_otel(events)

    async def _flush_async(self) -> None:
        """Take all buffered events and forward them to OTel logs."""
        with self._lock:
            if not self._buffer:
                return
            events = list(self._buffer)
            self._buffer.clear()
        self._emit_to_otel(events)

    def _emit_to_otel(self, events: list[dict[str, Any]]) -> None:
        emit_events_to_otel(events)

    def _schedule_async_flush(self) -> None:
        """Schedule an async flush from any thread."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._flush_async())
        except RuntimeError:
            # No running event loop — will be flushed by periodic task or on exit
            pass
