"""JSON output: {"run": RunMeta, "findings": [Finding, ...]}."""

from __future__ import annotations

import json as _json

from pythinker_review.store.models import Finding, RunMeta


def render_json(meta: RunMeta, findings: list[Finding]) -> str:
    return _json.dumps(
        {
            "run": meta.model_dump(by_alias=True, mode="json"),
            "findings": [finding.model_dump(by_alias=True, mode="json") for finding in findings],
        },
        indent=2,
    )
