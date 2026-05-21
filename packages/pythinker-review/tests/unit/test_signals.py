from pythinker_review.signals.scanner import scan_signals


def test_detects_aws_access_key() -> None:
    findings = scan_signals(
        file_path="config.py", added_lines=[(10, 'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"')]
    )
    assert any(s.rule_id == "sec.signal.secret.aws_access_key" for s in findings)


def test_detects_shell_with_user_input() -> None:
    findings = scan_signals(
        file_path="x.py", added_lines=[(5, "subprocess.run(f'rm {user_path}', shell=True)")]
    )
    assert any(s.rule_id == "sec.signal.shell.user_var" for s in findings)


def test_detects_sql_concatenation() -> None:
    findings = scan_signals(
        file_path="db.py",
        added_lines=[(3, 'cursor.execute("SELECT * FROM t WHERE id=" + user_id)')],
    )
    assert any(s.rule_id == "sec.signal.sql.concat" for s in findings)


def test_no_false_positive_on_plain_text() -> None:
    assert scan_signals(file_path="x.py", added_lines=[(1, "x = 1 + 2  # arithmetic")]) == []
