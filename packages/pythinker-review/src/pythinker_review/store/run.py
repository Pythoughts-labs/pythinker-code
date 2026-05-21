"""RunMeta lifecycle helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from pythinker_review.store.models import ChunkFailure, RunMeta, RunStatus


def transition(
    meta: RunMeta, *, status: RunStatus, chunk_failures: list[ChunkFailure] | None = None
) -> RunMeta:
    payload = meta.model_dump(by_alias=True, mode="json")
    payload["status"] = status
    payload["finished_at"] = datetime.now(tz=UTC).isoformat()
    if chunk_failures is not None:
        payload["chunk_failures"] = [
            cf.model_dump(by_alias=True, mode="json") for cf in chunk_failures
        ]
    return RunMeta.model_validate(payload)
