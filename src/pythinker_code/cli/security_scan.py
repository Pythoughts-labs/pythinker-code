"""`pythinker security-scan` — active-model wrapper for Python-native Pythinker Security Scan."""

from __future__ import annotations

import os

import typer
from pythinker_review.cli import security_scan as upstream_security_scan
from pythinker_review.llm.fake import FakeReviewLLM
from pythinker_review.llm.protocol import ReviewLLM

# Importing review installs the active-model resolver shared by review/secscan.
from pythinker_code.cli import review as review_wrapper

_REVIEW_CLI = review_wrapper.cli
cli = upstream_security_scan.app


def _resolve_security_scan_llm() -> ReviewLLM:
    adapter = review_wrapper.build_active_llm()
    if adapter is not None:
        return adapter
    fake = os.environ.get("PYTHINKER_REVIEW_FAKE_LLM_RESPONSES")
    if fake is not None:
        return FakeReviewLLM(scripted=fake.split("\0") if fake else ["[]"])
    typer.secho(
        "No active model configured. Set PYTHINKER_REVIEW_FAKE_LLM_RESPONSES for tests, "
        "or configure a Pythinker model before running `pythinker security-scan`.",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=3)


upstream_security_scan.__dict__["_resolve_llm"] = _resolve_security_scan_llm
