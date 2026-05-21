from pythinker_review.diagnostics.parser import parse_diagnostic


def test_parse_python_traceback_frame_and_exception() -> None:
    diagnostic = parse_diagnostic(
        '  File "x.py", line 12, in test_x\nAssertionError: nope\n', command="pytest"
    )
    assert diagnostic.command == "pytest"
    assert diagnostic.frames[0].file == "x.py"
    assert diagnostic.frames[0].line == 12
    assert diagnostic.exception == "AssertionError"


def test_parse_bounds_long_log() -> None:
    diagnostic = parse_diagnostic("a" * 100, max_chars=10)
    assert diagnostic.raw == "a" * 10
