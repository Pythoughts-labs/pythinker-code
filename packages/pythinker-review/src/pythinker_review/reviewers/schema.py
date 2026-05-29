"""Strict pydantic models the LLM is asked to produce."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pythinker_review.store.models import Category, Severity, Suggestion

_MAX_TITLE_LEN = 80


class RawFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    title: str
    rationale: str
    category: Category
    severity: Severity
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_snippet: str | None = None
    suggestion: Suggestion | None = None
    confidence_reason: str | None = None
    exploitability: str | None = None
    reproduction: str | None = None
    test_analysis: str | None = None
    suggested_regression_test: str | None = None
    minimum_fix_scope: str | None = None

    @field_validator("title", mode="before")
    @classmethod
    def _truncate_title(cls, value: object) -> object:
        # Models (especially smaller ones) routinely exceed the title budget.
        # Truncate rather than hard-fail: a length violation used to fail the
        # whole ReviewerOutput parse, discarding *every* finding in the chunk.
        if isinstance(value, str) and len(value) > _MAX_TITLE_LEN:
            return value[: _MAX_TITLE_LEN - 1].rstrip() + "…"
        return value

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class ReviewerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[RawFinding] = Field(default_factory=list)
