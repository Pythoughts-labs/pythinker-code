"""Structured outputs for code-reviewr-derived PR assistant workflows."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PRFileSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    changes_summary: str
    changes_title: str
    label: str


class PRDescriptionOutput(BaseModel):
    """Read-only replacement for code-reviewr's /describe payload."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    types: list[str] = Field(default_factory=list, alias="type")
    labels: list[str] = Field(default_factory=list)
    description: str
    title: str
    pr_files: list[PRFileSummary] = Field(default_factory=list)
    changes_diagram: str | None = None

    @model_validator(mode="after")
    def ensure_title(self) -> PRDescriptionOutput:
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.description.strip():
            raise ValueError("description must not be empty")
        return self


class CodeSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevant_file: str
    language: str
    existing_code: str
    suggestion_content: str
    improved_code: str
    one_sentence_summary: str
    label: str
    score: int | None = Field(default=None, ge=0, le=10)
    score_why: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> CodeSuggestion:
        if (
            self.start_line is not None
            and self.end_line is not None
            and self.end_line < self.start_line
        ):
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class CodeSuggestionsOutput(BaseModel):
    """Read-only replacement for code-reviewr's /improve payload."""

    model_config = ConfigDict(extra="forbid")

    code_suggestions: list[CodeSuggestion] = Field(default_factory=list)


class PRQuestionAnswerOutput(BaseModel):
    """Answer to a user question about the reviewed diff."""

    model_config = ConfigDict(extra="forbid")

    question: str
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    referenced_files: list[str] = Field(default_factory=list)
    limitations: str | None = None


class LineQuestionAnswerOutput(BaseModel):
    """Answer to a user question about selected changed lines."""

    model_config = ConfigDict(extra="forbid")

    question: str
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    side: Literal["RIGHT", "LEFT"] = "RIGHT"
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> LineQuestionAnswerOutput:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class PRLabelsOutput(BaseModel):
    """Read-only replacement for code-reviewr's /generate_labels payload."""

    model_config = ConfigDict(extra="forbid")

    labels: list[str] = Field(default_factory=list, max_length=10)
    rationale: str | None = None


class ChangelogOutput(BaseModel):
    """Read-only replacement for code-reviewr's /update_changelog draft payload."""

    model_config = ConfigDict(extra="forbid")

    title: str
    entry: str
    bullets: list[str] = Field(default_factory=list)
    migration_notes: str | None = None


class DocsSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevant_file: str
    target_symbol: str | None = None
    relevant_line: int | None = Field(default=None, ge=1)
    doc_placement: Literal["before", "after"] | None = None
    docs_gap: str
    suggested_doc: str


class DocsOutput(BaseModel):
    """Read-only replacement for code-reviewr's /add_docs planning payload."""

    model_config = ConfigDict(extra="forbid")

    docs_suggestions: list[DocsSuggestion] = Field(default_factory=list)


ComplianceStatus = Literal["pass", "fail", "needs_human", "not_applicable"]
OverallComplianceStatus = Literal["pass", "fail", "needs_human"]


class ComplianceCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    status: ComplianceStatus
    rationale: str
    evidence_files: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)


class ComplianceOutput(BaseModel):
    """Read-only replacement for code-reviewr ticket/compliance checks."""

    model_config = ConfigDict(extra="forbid")

    overall_status: OverallComplianceStatus
    ticket_summary: str | None = None
    checks: list[ComplianceCheck] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class SimilarIssueMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    title: str
    path: str
    score: float = Field(ge=0.0)
    snippet: str = ""


class SimilarIssuesOutput(BaseModel):
    """Read-only local replacement for code-reviewr's /similar_issue workflow."""

    model_config = ConfigDict(extra="forbid")

    query: str
    matches: list[SimilarIssueMatch] = Field(default_factory=list)


class HelpDocsReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_name: str
    relevant_section_header_string: str = ""


class HelpDocsOutput(BaseModel):
    """Read-only answer to a question over local repository documentation."""

    model_config = ConfigDict(extra="forbid")

    user_question: str
    response: str
    relevant_sections: list[HelpDocsReference] = Field(default_factory=list)
    question_is_relevant: bool = True


__all__ = [
    "ChangelogOutput",
    "CodeSuggestion",
    "CodeSuggestionsOutput",
    "ComplianceCheck",
    "ComplianceOutput",
    "DocsOutput",
    "DocsSuggestion",
    "HelpDocsOutput",
    "HelpDocsReference",
    "LineQuestionAnswerOutput",
    "PRDescriptionOutput",
    "PRFileSummary",
    "PRLabelsOutput",
    "PRQuestionAnswerOutput",
    "SimilarIssueMatch",
    "SimilarIssuesOutput",
]
