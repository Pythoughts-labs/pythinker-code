import importlib.util
import json
from pathlib import Path

import pytest

from pythinker_review.engine.chunker import Chunk
from pythinker_review.engine.structured_diff import StructuredHunk
from pythinker_review.llm.fake import FakeReviewLLM
from pythinker_review.output.artifacts import render_artifact_pretty
from pythinker_review.reviewers.artifacts import (
    ChangelogOutput,
    CodeSuggestionsOutput,
    ComplianceOutput,
    DocsOutput,
    DocsSuggestion,
    HelpDocsOutput,
    LineQuestionAnswerOutput,
    PRDescriptionOutput,
    PRLabelsOutput,
    SimilarIssuesOutput,
)
from pythinker_review.reviewers.compliance import load_compliance_context
from pythinker_review.reviewers.help_docs import HelpDocsError, load_help_docs_context
from pythinker_review.reviewers.pr_artifacts import (
    build_artifact_user,
    run_changelog_artifact,
    run_code_suggestions_artifact,
    run_compliance_artifact,
    run_docs_artifact,
    run_help_docs_artifact,
    run_labels_artifact,
    run_line_question_artifact,
    run_pr_description_artifact,
)
from pythinker_review.reviewers.similar_issues import SimilarIssuesError, find_similar_issues


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


def test_pretty_artifact_renderer_escapes_model_markup() -> None:
    output = PRLabelsOutput(labels=["[red]spoof[/red]"], rationale="[/bold]literal")
    rendered = render_artifact_pretty(
        "labels", output, metadata={"source_label": "[blue]src[/blue]"}
    )
    assert "[red]spoof[/red]" in rendered
    assert "[/bold]literal" in rendered


def test_pretty_docs_renderer_includes_line_and_placement() -> None:
    output = DocsOutput(
        docs_suggestions=[
            DocsSuggestion(
                relevant_file="app.py",
                target_symbol="greet",
                relevant_line=7,
                doc_placement="before",
                docs_gap="Missing public helper docs.",
                suggested_doc="Document `greet(name)`.",
            )
        ]
    )

    rendered = render_artifact_pretty("docs", output, metadata={"source_label": "test"})

    assert "app.py:7" in rendered
    assert "(greet)" in rendered
    assert "before" in rendered


def test_line_question_prompt_uses_valid_side_example() -> None:
    prompt = (
        Path(__file__).parents[2]
        / "src/pythinker_review/reviewers/prompts/line_questions.system.md"
    ).read_text(encoding="utf-8")

    assert '"side": "RIGHT",' in prompt
    assert "RIGHT|LEFT" not in prompt


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


@pytest.mark.asyncio
async def test_changelog_and_docs_artifacts_parse_optional_fields() -> None:
    changelog = await run_changelog_artifact(
        diff=_diff(),
        metadata=_meta(),
        artifact_context="Pull request URL:\n======\nhttps://example.test/pr/1\n======",
        llm=FakeReviewLLM(
            scripted=[
                json.dumps(
                    {
                        "title": "Print value",
                        "entry": "Adds a print output helper.",
                        "bullets": ["Added print output."],
                        "migration_notes": None,
                    }
                )
            ]
        ),
        timeout_s=10.0,
    )
    assert changelog.ok
    assert isinstance(changelog.output, ChangelogOutput)

    docs = await run_docs_artifact(
        diff=_diff(),
        metadata=_meta(),
        artifact_context="Documentation style:\n======\nGoogle-style docstring\n======",
        llm=FakeReviewLLM(
            scripted=[
                json.dumps(
                    {
                        "docs_suggestions": [
                            {
                                "relevant_file": "app.py",
                                "target_symbol": "main",
                                "relevant_line": 1,
                                "doc_placement": "before",
                                "docs_gap": "New behavior lacks docs.",
                                "suggested_doc": "Document the new output behavior.",
                            }
                        ]
                    }
                )
            ]
        ),
        timeout_s=10.0,
    )
    assert docs.ok
    assert isinstance(docs.output, DocsOutput)
    assert docs.output.docs_suggestions[0].relevant_line == 1


def test_find_similar_issues_ranks_local_documents(tmp_path) -> None:
    issues = tmp_path / "issues"
    issues.mkdir()
    (issues / "bug.md").write_text(
        "# Empty greeting bug\n\nGreeting fails when the name is empty.", encoding="utf-8"
    )
    (issues / "docs.md").write_text("# Docs typo\n\nFix spelling.", encoding="utf-8")
    output, metadata = find_similar_issues(
        repo=tmp_path,
        issues_dir=Path("issues"),
        issue_text="empty greeting failure",
        issue_file=None,
        top_k=2,
        budget_chars=2_000,
        backend="lexical",
    )
    assert isinstance(output, SimilarIssuesOutput)
    assert output.matches[0].path == "issues/bug.md"
    assert metadata["issues_scanned"] == "2"
    assert metadata["similarity_backend"] == "lexical"


def test_find_similar_issues_rejects_issue_file_outside_repo(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    issues = repo / "issues"
    issues.mkdir()
    (issues / "bug.md").write_text("# Bug\n", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("# External issue\n", encoding="utf-8")

    with pytest.raises(SimilarIssuesError, match="escapes repository"):
        find_similar_issues(
            repo=repo,
            issues_dir=Path("issues"),
            issue_text="bug",
            issue_file=outside,
            top_k=1,
            budget_chars=2_000,
            backend="lexical",
        )


def test_find_similar_issues_skips_symlinked_issue_docs(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    issues = repo / "issues"
    issues.mkdir()
    (issues / "bug.md").write_text("# Empty greeting bug\n\nGreeting fails.", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("# External secret\n\nShould not be indexed.", encoding="utf-8")
    (issues / "outside.md").symlink_to(outside)

    output, metadata = find_similar_issues(
        repo=repo,
        issues_dir=Path("issues"),
        issue_text="empty greeting",
        issue_file=None,
        top_k=2,
        budget_chars=2_000,
        backend="lexical",
    )

    assert [match.path for match in output.matches] == ["issues/bug.md"]
    assert metadata["issues_scanned"] == "1"


def test_find_similar_issues_supports_optional_chromadb(tmp_path) -> None:
    if importlib.util.find_spec("chromadb") is None:
        pytest.skip("optional ChromaDB backend is not installed")

    issues = tmp_path / "issues"
    issues.mkdir()
    (issues / "bug.md").write_text(
        "# Empty greeting bug\n\nGreeting fails when the name is empty.", encoding="utf-8"
    )
    (issues / "docs.md").write_text("# Docs typo\n\nFix spelling.", encoding="utf-8")
    output, metadata = find_similar_issues(
        repo=tmp_path,
        issues_dir=Path("issues"),
        issue_text="empty greeting failure",
        issue_file=None,
        top_k=2,
        budget_chars=2_000,
        backend="chroma",
        chroma_path=Path(".pythinker-review/chroma"),
    )
    assert isinstance(output, SimilarIssuesOutput)
    assert output.matches
    assert {match.path for match in output.matches} >= {"issues/bug.md"}
    assert metadata["similarity_backend"] == "chroma"
    assert (tmp_path / ".pythinker-review" / "chroma").exists()


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


@pytest.mark.asyncio
async def test_line_question_artifact_parses_selected_line_answer() -> None:
    payload = json.dumps(
        {
            "question": "why this line?",
            "file": "app.py",
            "start_line": 1,
            "end_line": 1,
            "side": "RIGHT",
            "answer": "It adds output for debugging.",
            "confidence": 0.8,
            "limitations": None,
        }
    )
    result = await run_line_question_artifact(
        question="why this line?",
        diff=_diff(),
        metadata=_meta(),
        line_context="Selected lines:\n1 +print('x')",
        llm=FakeReviewLLM(scripted=[payload]),
        timeout_s=10.0,
    )
    assert result.ok
    assert isinstance(result.output, LineQuestionAnswerOutput)
    assert result.output.file == "app.py"


def test_load_help_docs_context_rejects_symlinked_docs_path(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside_docs = tmp_path / "docs"
    outside_docs.mkdir()
    (outside_docs / "usage.md").write_text("# Secret docs\n", encoding="utf-8")
    (repo / "docs").symlink_to(outside_docs, target_is_directory=True)

    with pytest.raises(HelpDocsError, match="contains symlink"):
        load_help_docs_context(
            repo=repo,
            docs_path=Path("docs"),
            include_root_readme=False,
            extensions=["md"],
            budget_chars=10_000,
        )


@pytest.mark.asyncio
async def test_help_docs_artifact_parses_references(tmp_path) -> None:
    repo = tmp_path
    docs = repo / "docs"
    docs.mkdir()
    (docs / "usage.md").write_text("# Usage\n\nRun `pythinker review diff`.", encoding="utf-8")
    docs_context, metadata = load_help_docs_context(
        repo=repo,
        docs_path=Path("docs"),
        include_root_readme=False,
        extensions=["md"],
        budget_chars=10_000,
    )
    assert "usage.md" in docs_context
    payload = json.dumps(
        {
            "user_question": "how do I review?",
            "response": "Run `pythinker review diff`.",
            "relevant_sections": [
                {"file_name": "docs/usage.md", "relevant_section_header_string": "# Usage"}
            ],
            "question_is_relevant": True,
        }
    )
    result = await run_help_docs_artifact(
        question="how do I review?",
        docs_context=docs_context,
        metadata=metadata,
        llm=FakeReviewLLM(scripted=[payload]),
        timeout_s=10.0,
    )
    assert result.ok
    assert isinstance(result.output, HelpDocsOutput)
    assert result.output.relevant_sections[0].file_name == "docs/usage.md"
