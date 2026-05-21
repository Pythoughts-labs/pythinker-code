import json

import pytest

from pythinker_review.engine.chunker import Chunk
from pythinker_review.engine.structured_diff import StructuredHunk
from pythinker_review.llm.fake import FakeReviewLLM
from pythinker_review.reviewers.artifacts import (
    CodeSuggestionsOutput,
    ComplianceOutput,
    PRDescriptionOutput,
    PRLabelsOutput,
)
from pythinker_review.reviewers.compliance import load_compliance_context
from pythinker_review.reviewers.pr_artifacts import (
    build_artifact_user,
    run_code_suggestions_artifact,
    run_compliance_artifact,
    run_labels_artifact,
    run_pr_description_artifact,
)


def _diff() -> str:
    h = StructuredHunk(header="@@ -1 +1 @@", new_block="1 +print('x')", old_block="-pass")
    return Chunk(
        file="app.py", hunks=(h,), rendered="## File: 'app.py'\n__new hunk__\n1 +print('x')"
    ).rendered


def _meta() -> dict[str, str]:
    return {
        "branch": "feature",
        "base_ref": "main",
        "source_label": "git-diff:main",
        "changed_files": "app.py",
    }


def test_artifact_user_prompt_includes_metadata_question_context_and_diff() -> None:
    prompt = build_artifact_user(
        diff=_diff(), metadata=_meta(), question="what changed?", artifact_context="Checklist: yes"
    )
    assert "Branch: feature" in prompt
    assert "User question:" in prompt
    assert "Artifact context:" in prompt
    assert "## File: 'app.py'" in prompt


@pytest.mark.asyncio
async def test_pr_description_artifact_parses_strict_json() -> None:
    payload = json.dumps(
        {
            "type": ["Enhancement"],
            "title": "Print value",
            "description": "- Adds printing",
            "pr_files": [
                {
                    "filename": "app.py",
                    "changes_summary": "- Adds printing",
                    "changes_title": "Print output",
                    "label": "enhancement",
                }
            ],
            "changes_diagram": None,
        }
    )
    result = await run_pr_description_artifact(
        diff=_diff(), metadata=_meta(), llm=FakeReviewLLM(scripted=[payload]), timeout_s=10.0
    )
    assert result.ok
    assert isinstance(result.output, PRDescriptionOutput)
    assert result.output.title == "Print value"


@pytest.mark.asyncio
async def test_code_suggestions_artifact_accepts_empty_list() -> None:
    result = await run_code_suggestions_artifact(
        diff=_diff(),
        metadata=_meta(),
        llm=FakeReviewLLM(scripted=['{"code_suggestions": []}']),
        timeout_s=10.0,
    )
    assert result.ok
    assert isinstance(result.output, CodeSuggestionsOutput)
    assert result.output.code_suggestions == []


@pytest.mark.asyncio
async def test_labels_artifact_retries_malformed_once() -> None:
    llm = FakeReviewLLM(
        scripted=["not json", '{"labels": ["enhancement"], "rationale": "Adds output."}']
    )
    result = await run_labels_artifact(diff=_diff(), metadata=_meta(), llm=llm, timeout_s=10.0)
    assert result.ok
    assert isinstance(result.output, PRLabelsOutput)
    assert result.output.labels == ["enhancement"]
    assert len(llm.calls) == 2


def test_load_compliance_context_uses_bundled_checklist() -> None:
    context = load_compliance_context(ticket_text="Must add a greeting helper.")
    assert "Consistent Naming Conventions" in context
    assert "Ticket / acceptance criteria context" in context
    assert "Must add a greeting helper" in context


@pytest.mark.asyncio
async def test_compliance_artifact_parses_checks() -> None:
    payload = json.dumps(
        {
            "overall_status": "needs_human",
            "ticket_summary": "Adds a print statement.",
            "checks": [
                {
                    "title": "Robust Error Handling",
                    "status": "needs_human",
                    "rationale": "No error path is visible in this tiny diff.",
                    "evidence_files": ["app.py"],
                    "missing_requirements": [],
                }
            ],
            "risks": ["Only a bounded diff was reviewed."],
        }
    )
    result = await run_compliance_artifact(
        diff=_diff(),
        metadata=_meta(),
        compliance_context=load_compliance_context(),
        llm=FakeReviewLLM(scripted=[payload]),
        timeout_s=10.0,
    )
    assert result.ok
    assert isinstance(result.output, ComplianceOutput)
    assert result.output.overall_status == "needs_human"
