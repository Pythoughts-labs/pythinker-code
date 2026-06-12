"""Graduated fuzzy-matching ladder for edit-location recovery.

Whitespace drift or smart-punctuation mismatch used to hard-fail with
'old string not found', burning a re-read + retry turn. When the exact
match (and CRLF fallback) misses, a line-window seek retries with
graduated relaxations — trailing-whitespace, indentation, then
unicode-punctuation — replacing the ACTUAL matched file slice and naming
the fired relaxation in the tool message. Ambiguity semantics keep:
multiple fuzzy hits without replace_all still error.
"""

from __future__ import annotations

from pythinker_host.path import HostPath

from pythinker_code.tools.file.replace import Edit, Params, StrReplaceFile


async def _edit(tool: StrReplaceFile, path: HostPath, old: str, new: str, **kw):
    return await tool(Params(path=str(path), edit=Edit(old=old, new=new, **kw)))


async def test_trailing_whitespace_drift_recovers(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    file_path = temp_work_dir / "t.py"
    await file_path.write_text("def f():   \n    return 1   \n")

    result = await _edit(
        str_replace_file_tool, file_path, "def f():\n    return 1", "def f():\n    return 2"
    )

    assert not result.is_error
    assert "trailing-whitespace" in result.message
    assert "return 2" in await file_path.read_text()


async def test_indentation_drift_recovers(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    file_path = temp_work_dir / "t.py"
    await file_path.write_text("class A:\n\tdef f(self):\n\t\treturn 1\n")

    result = await _edit(
        str_replace_file_tool,
        file_path,
        "def f(self):\n    return 1",
        "    def f(self) -> int:\n        return 2",
    )

    assert not result.is_error
    assert "indentation" in result.message
    content = await file_path.read_text()
    assert "def f(self) -> int:" in content
    assert "return 1" not in content


async def test_smart_punctuation_recovers(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    file_path = temp_work_dir / "t.md"
    await file_path.write_text("It’s a “smart” test — really\n")

    result = await _edit(
        str_replace_file_tool,
        file_path,
        'It\'s a "smart" test - really',
        "plain text now",
    )

    assert not result.is_error
    assert "unicode-punctuation" in result.message
    assert await file_path.read_text() == "plain text now\n"


async def test_ambiguous_fuzzy_hits_still_error(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    original = "if x:   \n    pass\nif x:\t\n    pass\n"
    file_path = temp_work_dir / "t.py"
    await file_path.write_text(original)

    result = await _edit(str_replace_file_tool, file_path, "if x:\n    pass", "if y:\n    pass")

    assert result.is_error
    assert "occurs 2 times" in result.message
    assert "relaxed" in result.message
    assert await file_path.read_text() == original


async def test_replace_all_applies_to_every_fuzzy_hit(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    file_path = temp_work_dir / "t.py"
    await file_path.write_text("if x:   \n    pass\nif x:\t\n    pass\n")

    result = await _edit(
        str_replace_file_tool,
        file_path,
        "if x:\n    pass",
        "if y:\n    pass",
        replace_all=True,
    )

    assert not result.is_error
    assert await file_path.read_text() == "if y:\n    pass\nif y:\n    pass\n"


async def test_no_match_at_any_tier_keeps_not_found_error(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    file_path = temp_work_dir / "t.py"
    await file_path.write_text("alpha\nbeta\n")

    result = await _edit(str_replace_file_tool, file_path, "gamma", "delta")

    assert result.is_error
    assert "not found" in result.message


async def test_exact_match_carries_no_relaxation_note(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    file_path = temp_work_dir / "t.py"
    await file_path.write_text("value = 1\n")

    result = await _edit(str_replace_file_tool, file_path, "value = 1", "value = 2")

    assert not result.is_error
    assert "relaxed" not in result.message


async def test_crlf_file_fuzzy_splice_preserves_line_endings(
    str_replace_file_tool: StrReplaceFile, temp_work_dir: HostPath
):
    file_path = temp_work_dir / "t.txt"
    await file_path.write_text("first   \r\nsecond\r\nthird\r\n")

    result = await _edit(str_replace_file_tool, file_path, "first\nsecond", "primary\nextra")

    assert not result.is_error
    assert await file_path.read_text() == "primary\r\nextra\r\nthird\r\n"
