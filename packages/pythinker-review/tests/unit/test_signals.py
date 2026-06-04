from pythinker_review.signals.advisor import build_advisor_context
from pythinker_review.signals.scanner import scan_signals


def test_detects_aws_access_key() -> None:
    findings = scan_signals(
        file_path="config.py", added_lines=[(10, 'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"')]
    )
    assert any(s.rule_id == "sec.signal.secrets_exposure.aws_access_key" for s in findings)


def test_detects_shell_with_user_input() -> None:
    findings = scan_signals(
        file_path="x.py", added_lines=[(5, "subprocess.run(f'rm {user_path}', shell=True)")]
    )
    assert any(s.rule_id == "sec.signal.rce.shell_true" for s in findings)


def test_detects_sql_concatenation() -> None:
    findings = scan_signals(
        file_path="db.py",
        added_lines=[(3, 'cursor.execute("SELECT * FROM t WHERE id=" + user_id)')],
    )
    assert any(s.rule_id == "sec.signal.sql_injection.python_concat" for s in findings)


def test_detects_xss_open_redirect_and_jwt() -> None:
    findings = scan_signals(
        file_path="app.ts",
        added_lines=[
            (1, "el.innerHTML = req.query.html"),
            (2, "res.redirect(req.query.next)"),
            (3, "jwt.decode(token, options={verify: False})"),
        ],
    )
    ids = {signal.rule_id for signal in findings}
    assert "sec.signal.xss.unsafe_html" in ids
    assert "sec.signal.open_redirect.user_controlled_redirect" in ids
    assert "sec.signal.jwt_handling.algorithm_confusion" in ids


def test_no_false_positive_on_plain_text() -> None:
    assert scan_signals(file_path="x.py", added_lines=[(1, "x = 1 + 2  # arithmetic")]) == []


def test_advisor_context_detects_python_stack(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text('dependencies = ["fastapi"]')
    signals = {
        "app.py": scan_signals(
            file_path="app.py",
            added_lines=[(1, "@app.get('/debug')"), (2, "requests.get(url)")],
        )
    }
    context = build_advisor_context(repo=tmp_path, signals_by_file=signals)
    assert "fastapi" in context
    assert "Threat highlights" in context


def test_detects_cve_and_dependency_manifest_leads() -> None:
    findings = scan_signals(
        file_path="package.json",
        added_lines=[(2, '"lodash": "^4.17.20", // CVE-2020-8203')],
    )
    ids = {signal.rule_id for signal in findings}

    assert "sec.signal.vulnerability_intel.cve_reference" in ids
    assert "sec.signal.vulnerability_intel.dependency_change" in ids
    assert any(signal.metadata.get("cve") == "CVE-2020-8203" for signal in findings)


def test_advisor_context_includes_vulnerability_intel_leads(tmp_path) -> None:
    signals = {
        "requirements.txt": scan_signals(
            file_path="requirements.txt",
            added_lines=[(1, "django==1.2  # CVE-2019-19844")],
        )
    }

    context = build_advisor_context(repo=tmp_path, signals_by_file=signals)

    assert "Vulnerability intelligence leads" in context
    assert "CVE-2019-19844" in context
    assert "requirements.txt" in context


def test_advisor_context_uses_ported_framework_highlights(tmp_path) -> None:
    (tmp_path / "package.json").write_text('{"dependencies":{"koa":"^2.15.0"}}')
    signals = {
        "server.ts": scan_signals(
            file_path="server.ts",
            added_lines=[(1, "el.innerHTML = req.query.html")],
        )
    }

    context = build_advisor_context(repo=tmp_path, signals_by_file=signals)

    assert "### Koa" in context
    assert "middleware order matters" in context
