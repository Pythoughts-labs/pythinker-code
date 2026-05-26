from __future__ import annotations

import asyncio
import json
from pathlib import Path

from pythinker_review.llm.fake import FakeReviewLLM
from pythinker_review.security_scan.matchers import create_default_registry
from pythinker_review.security_scan.processor import (
    parse_investigate_results,
    process_project,
    triage_project,
)
from pythinker_review.security_scan.prompt import assemble_prompt, batch_languages
from pythinker_review.security_scan.scanner import scan_project
from pythinker_review.security_scan.store import (
    list_runs,
    load_all_file_records,
    read_file_record,
    read_run_meta,
    write_file_record,
)
from pythinker_review.security_scan.tech import detect_tech, read_tech_json


def test_security_scan_registry_ports_all_source_matchers() -> None:
    registry = create_default_registry()
    assert len(registry.get_all()) == 198
    assert registry.get_by_slug("auth-bypass") is not None
    assert registry.get_by_slug("github-workflow-security") is not None
    assert registry.get_by_slug("py-fastapi-route") is not None
    assert all(matcher.patterns for matcher in registry.get_all())


def test_security_scan_curated_matchers_cover_remaining_high_value_sources() -> None:
    registry = create_default_registry()
    cases = {
        "drizzle-raw-sql": "db.execute(sql.raw(req.query.orderBy))",
        "drizzle-mass-assignment": "await db.insert(users).values(req.body)",
        "tf-module-unpinned": 'source = "git::https://github.com/acme/module.git"',
        "trpc-public-procedure": "export const x = publicProcedure.input(schema).mutation(fn)",
        "security-behind-flag": "if (flags.isEnabled('new-auth')) { authorize(user) }",
        "url-regex-validation": "const ok = /^https?:\\/\\/.*$/.test(req.query.next)",
        "all-route-handlers": "export async function POST(req: Request) { return Response.json({}) }",
        "server-action": "'use server'\nexport async function saveUser() { return true }",
    }
    for slug, source in cases.items():
        matcher = registry.get_by_slug(slug)
        assert matcher is not None, slug
        assert matcher.match(source, "src/example.ts"), slug


def test_security_scan_line_anchored_matchers_use_multiline_default() -> None:
    matcher = create_default_registry().get_by_slug("dockerfile-curl-pipe-unverified")
    assert matcher is not None

    matches = matcher.match(
        "FROM alpine:3.20\nRUN curl https://example.test/install.sh | sh\n", "Dockerfile"
    )

    assert matches
    assert matches[0].line_numbers == [2]


def test_security_scan_multiline_patterns_match_across_lines() -> None:
    matcher = create_default_registry().get_by_slug("non-atomic-operation")
    assert matcher is not None

    matches = matcher.match(
        "const row = await findUser(id)\nawait updateUser(id, patch)", "src/db.ts"
    )

    assert matches
    assert matches[0].line_numbers == [1, 2]


def test_security_scan_writes_file_records(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('dependencies = ["fastapi"]\n', encoding="utf-8")
    (repo / "app.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.post('/admin')\n"
        "def admin(user_id: str):\n"
        "    return {'ok': user_id}\n",
        encoding="utf-8",
    )
    data_root = tmp_path / "state" / "data"

    result = scan_project(project_id="repo", root=repo, data_root=data_root)

    assert result.candidate_count > 0
    record = read_file_record("repo", "app.py", data_root=data_root)
    assert record is not None
    assert any(candidate.vuln_slug == "py-fastapi-route" for candidate in record.candidates)


def test_security_scan_ignores_virtualenv_and_agent_worktrees(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.post('/admin')\n"
        "def admin(user_id: str):\n"
        "    return {'ok': user_id}\n"
    )
    (repo / "pyproject.toml").write_text('dependencies = ["fastapi"]\n', encoding="utf-8")
    (repo / "app.py").write_text(source, encoding="utf-8")
    # Heavy directories that must never be walked: dependency trees, build output,
    # local virtualenvs, and full repo copies under .claude/worktrees/.
    for ignored in (
        "node_modules/pkg/app.py",
        "build/app.py",
        ".venv/lib/python3.14/site-packages/pkg/app.py",
        ".claude/worktrees/agent-x/app.py",
        ".claude/worktrees/agent-x/.venv/lib/site-packages/pkg/app.py",
    ):
        path = repo / ignored
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    data_root = tmp_path / "state" / "data"
    result = scan_project(project_id="repo", root=repo, data_root=data_root)

    assert read_file_record("repo", "app.py", data_root=data_root) is not None
    for ignored in (
        "node_modules/pkg/app.py",
        "build/app.py",
        ".venv/lib/python3.14/site-packages/pkg/app.py",
        ".claude/worktrees/agent-x/app.py",
        ".claude/worktrees/agent-x/.venv/lib/site-packages/pkg/app.py",
    ):
        assert read_file_record("repo", ignored, data_root=data_root) is None
    # Only the real source file is scanned, not the ignored copies.
    assert result.candidate_count == 1


def test_security_scan_tech_detection_ignores_unscannable_trees(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('dependencies = ["fastapi"]\n', encoding="utf-8")
    (repo / "app.py").write_text("@app.post('/x')\ndef x(): return {}\n", encoding="utf-8")
    generated_rust = repo / "target" / "debug" / "build" / "generated.rs"
    generated_rust.parent.mkdir(parents=True)
    generated_rust.write_text("fn generated() {}\n", encoding="utf-8")
    data_root = tmp_path / "state" / "data"

    scan_project(project_id="repo", root=repo, data_root=data_root)

    tech = read_tech_json("repo", data_root=data_root)
    assert tech is not None
    assert "python" in tech.languages
    assert "rust" not in tech.languages


def test_security_scan_respects_gitignore(tmp_path: Path) -> None:
    import shutil
    import subprocess

    import pytest

    if shutil.which("git") is None:
        pytest.skip("git not available")

    repo = tmp_path / "repo"
    repo.mkdir()
    source = (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.post('/admin')\n"
        "def admin(user_id: str):\n"
        "    return {'ok': user_id}\n"
    )
    (repo / "pyproject.toml").write_text('dependencies = ["fastapi"]\n', encoding="utf-8")
    (repo / "app.py").write_text(source, encoding="utf-8")
    # A gitignored directory that IGNORE_DIRS knows nothing about must still be
    # skipped, because the scan honors git's ignore rules.
    (repo / ".gitignore").write_text("generated/\n", encoding="utf-8")
    generated = repo / "generated" / "app.py"
    generated.parent.mkdir(parents=True)
    generated.write_text(source, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)

    data_root = tmp_path / "state" / "data"
    result = scan_project(project_id="repo", root=repo, data_root=data_root)

    assert read_file_record("repo", "app.py", data_root=data_root) is not None
    assert read_file_record("repo", "generated/app.py", data_root=data_root) is None
    assert result.candidate_count == 1


def test_security_scan_matches_direct_children_for_globstar_file_patterns(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    workflow = repo / ".github" / "workflows" / "security.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: ci\npermissions: write-all\n", encoding="utf-8")
    data_root = tmp_path / "state" / "data"

    result = scan_project(
        project_id="repo",
        root=repo,
        data_root=data_root,
        matcher_slugs=["github-workflow-security"],
    )

    assert result.files_scanned == 1
    record = read_file_record("repo", ".github/workflows/security.yml", data_root=data_root)
    assert record is not None
    assert any(candidate.vuln_slug == "github-workflow-security" for candidate in record.candidates)


def test_security_scan_stats_count_scanned_files_and_removes_stale_candidates(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('dependencies = ["fastapi"]\n', encoding="utf-8")
    app = repo / "app.py"
    app.write_text("@app.post('/x')\ndef x(): return {}\n", encoding="utf-8")
    (repo / "safe.py").write_text("def safe(): return 1\n", encoding="utf-8")
    data_root = tmp_path / "state" / "data"

    first = scan_project(
        project_id="repo", root=repo, data_root=data_root, matcher_slugs=["py-fastapi-route"]
    )

    assert first.files_scanned == 2
    assert first.files_with_candidates == 1
    assert first.language_stats[0].scanned_files == 2
    assert first.language_stats[0].candidates == first.candidate_count
    run = list_runs("repo", data_root=data_root)[-1]
    assert run.stats.files_scanned == 2
    assert run.stats.candidates_found == first.candidate_count

    app.write_text("def safe_now(): return 1\n", encoding="utf-8")
    second = scan_project(
        project_id="repo", root=repo, data_root=data_root, matcher_slugs=["py-fastapi-route"]
    )

    assert second.files_scanned == 2
    assert second.candidate_count == 0
    record = read_file_record("repo", "app.py", data_root=data_root)
    assert record is not None
    assert record.candidates == []


def test_security_scan_resets_analyzed_record_when_candidates_change(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('dependencies = ["fastapi"]\n', encoding="utf-8")
    app = repo / "app.py"
    app.write_text("@app.post('/x')\ndef x(): return {}\n", encoding="utf-8")
    data_root = tmp_path / "state" / "data"
    scan_project(
        project_id="repo", root=repo, data_root=data_root, matcher_slugs=["py-fastapi-route"]
    )
    asyncio.run(
        process_project(
            project_id="repo",
            data_root=data_root,
            llm=FakeReviewLLM(scripted=[json.dumps([{"filePath": "app.py", "findings": []}])]),
            batch_size=1,
            jobs=1,
        )
    )
    record = read_file_record("repo", "app.py", data_root=data_root)
    assert record is not None
    assert record.status == "analyzed"
    record.status = "processing"
    record.locked_by_run_id = "old-run"
    record.locked_at = "2026-05-20T00:00:00Z"
    write_file_record(record, data_root=data_root)

    app.write_text("# moved\n@app.post('/x')\ndef x(): return {}\n", encoding="utf-8")
    scan_project(
        project_id="repo", root=repo, data_root=data_root, matcher_slugs=["py-fastapi-route"]
    )

    rescanned = read_file_record("repo", "app.py", data_root=data_root)
    assert rescanned is not None
    assert rescanned.status == "pending"
    assert rescanned.locked_by_run_id is None
    assert rescanned.locked_at is None
    assert rescanned.candidates[0].line_numbers == [2]


def test_security_scan_clears_stale_findings_when_candidates_disappear(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('dependencies = ["fastapi"]\n', encoding="utf-8")
    app = repo / "app.py"
    app.write_text("@app.post('/x')\ndef x(): return {}\n", encoding="utf-8")
    data_root = tmp_path / "state" / "data"
    scan_project(
        project_id="repo", root=repo, data_root=data_root, matcher_slugs=["py-fastapi-route"]
    )
    finding_response = json.dumps(
        [
            {
                "filePath": "app.py",
                "findings": [
                    {
                        "severity": "MEDIUM",
                        "vulnSlug": "py-fastapi-route",
                        "title": "Missing auth",
                        "description": "Route has no auth guard.",
                        "lineNumbers": [1],
                        "recommendation": "Add auth.",
                        "confidence": "medium",
                    }
                ],
            }
        ]
    )
    asyncio.run(
        process_project(
            project_id="repo",
            data_root=data_root,
            llm=FakeReviewLLM(scripted=[finding_response]),
            batch_size=1,
            jobs=1,
        )
    )
    analyzed = read_file_record("repo", "app.py", data_root=data_root)
    assert analyzed is not None
    assert analyzed.status == "analyzed"
    assert len(analyzed.findings) == 1

    app.write_text("def safe(): return {}\n", encoding="utf-8")
    scan_project(
        project_id="repo", root=repo, data_root=data_root, matcher_slugs=["py-fastapi-route"]
    )

    rescanned = read_file_record("repo", "app.py", data_root=data_root)
    assert rescanned is not None
    assert rescanned.status == "pending"
    assert rescanned.candidates == []
    assert rescanned.findings == []


def test_security_scan_prompt_includes_system_policy_and_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('dependencies = ["fastapi"]\n', encoding="utf-8")
    (repo / "app.py").write_text("@app.post('/x')\ndef x(): return {}\n", encoding="utf-8")
    data_root = tmp_path / "state" / "data"
    scan_project(
        project_id="repo", root=repo, data_root=data_root, matcher_slugs=["py-fastapi-route"]
    )
    records = load_all_file_records("repo", data_root=data_root)
    tech = detect_tech(repo)

    assembled = assemble_prompt(
        detected_tags=tech.tags,
        batch_slugs=[c.vuln_slug for r in records for c in r.candidates],
        batch_languages=batch_languages(records),
        project_info="Auth uses Depends(current_user).",
        records=records,
        project_root=repo,
    )

    assert "Pythinker Security Scan" in assembled.system
    assert "FastAPI" in assembled.system
    assert "app.py" in assembled.user


def test_security_scan_parse_adds_empty_results_for_missing_files() -> None:
    payload = '[{"filePath":"a.py","findings":[]}]'

    class R:
        file_path: str

        def __init__(self, file_path: str) -> None:
            self.file_path = file_path

    results = parse_investigate_results(payload, [R("a.py"), R("b.py")])  # type: ignore[arg-type]
    assert {item["filePath"] for item in results} == {"a.py", "b.py"}


def test_security_scan_process_uses_review_llm(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('dependencies = ["fastapi"]\n', encoding="utf-8")
    (repo / "app.py").write_text("@app.post('/x')\ndef x(): return {}\n", encoding="utf-8")
    data_root = tmp_path / "state" / "data"
    scan_project(
        project_id="repo", root=repo, data_root=data_root, matcher_slugs=["py-fastapi-route"]
    )
    response = json.dumps([{"filePath": "app.py", "findings": []}])
    llm = FakeReviewLLM(scripted=[response])

    result = asyncio.run(
        process_project(project_id="repo", data_root=data_root, llm=llm, batch_size=1, jobs=1)
    )

    assert result.analysis_count == 1
    assert result.error_batch_count == 0
    record = read_file_record("repo", "app.py", data_root=data_root)
    assert record is not None
    assert record.status == "analyzed"


def test_security_scan_process_partial_errors_still_complete_and_redact_messages(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('dependencies = ["fastapi"]\n', encoding="utf-8")
    (repo / "a.py").write_text("@app.post('/a')\ndef a(): return {}\n", encoding="utf-8")
    (repo / "b.py").write_text("@app.post('/b')\ndef b(): return {}\n", encoding="utf-8")
    data_root = tmp_path / "state" / "data"
    scan_project(
        project_id="repo", root=repo, data_root=data_root, matcher_slugs=["py-fastapi-route"]
    )

    def responder(_system: str, user: str) -> str:
        if "b.py" in user:
            raise RuntimeError("api_key=sk_test_123456789 failed while processing b.py")
        return json.dumps([{"filePath": "a.py", "findings": []}])

    result = asyncio.run(
        process_project(
            project_id="repo",
            data_root=data_root,
            llm=FakeReviewLLM(responder=responder),
            batch_size=1,
            jobs=1,
        )
    )

    run = read_run_meta("repo", result.run_id, data_root=data_root)
    assert result.analysis_count == 1
    assert result.error_batch_count == 1
    assert run.phase == "done"
    assert run.stats.error_messages
    assert "sk_test_123456789" not in run.stats.error_messages[0]
    assert "[REDACTED_SECRET]" in run.stats.error_messages[0]


def test_security_scan_triage_uses_file_path_and_writes_run_meta(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('dependencies = ["fastapi"]\n', encoding="utf-8")
    (repo / "a.py").write_text("@app.post('/a')\ndef a(): return {}\n", encoding="utf-8")
    (repo / "b.py").write_text("@app.post('/b')\ndef b(): return {}\n", encoding="utf-8")
    data_root = tmp_path / "state" / "data"
    scan_project(
        project_id="repo", root=repo, data_root=data_root, matcher_slugs=["py-fastapi-route"]
    )
    process_response = json.dumps(
        [
            {
                "filePath": "a.py",
                "findings": [
                    {
                        "severity": "MEDIUM",
                        "vulnSlug": "missing-auth",
                        "title": "Shared title",
                        "description": "a",
                        "lineNumbers": [1],
                        "recommendation": "fix a",
                        "confidence": "medium",
                    }
                ],
            },
            {
                "filePath": "b.py",
                "findings": [
                    {
                        "severity": "MEDIUM",
                        "vulnSlug": "missing-auth",
                        "title": "Shared title",
                        "description": "b",
                        "lineNumbers": [1],
                        "recommendation": "fix b",
                        "confidence": "medium",
                    }
                ],
            },
        ]
    )
    asyncio.run(
        process_project(
            project_id="repo",
            data_root=data_root,
            llm=FakeReviewLLM(scripted=[process_response]),
            batch_size=2,
            jobs=1,
        )
    )
    triage_response = json.dumps(
        [
            {
                "filePath": "b.py",
                "title": "Shared title",
                "priority": "P1",
                "exploitability": "moderate",
                "impact": "medium",
                "reasoning": "reachable sensitive route",
            }
        ]
    )

    result = asyncio.run(
        triage_project(
            project_id="repo", data_root=data_root, llm=FakeReviewLLM(scripted=[triage_response])
        )
    )

    assert result.triaged == 1
    a_record = read_file_record("repo", "a.py", data_root=data_root)
    b_record = read_file_record("repo", "b.py", data_root=data_root)
    assert a_record is not None
    assert b_record is not None
    assert a_record.findings[0].triage is None
    assert b_record.findings[0].triage is not None
    assert b_record.findings[0].triage.priority == "P1"
    triage_runs = [run for run in list_runs("repo", data_root=data_root) if run.type == "triage"]
    assert len(triage_runs) == 1
    assert triage_runs[0].phase == "done"
    assert triage_runs[0].stats.findings_count == 1
