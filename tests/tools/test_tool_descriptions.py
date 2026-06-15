from pathlib import Path


def test_agent_tool_description_includes_prompt_hygiene_note() -> None:
    text = (Path(__file__).parents[2] / "src/pythinker_code/tools/agent/description.md").read_text(
        encoding="utf-8"
    )
    assert "brief it like a smart colleague who just walked in" in text
    assert "pass the question, not prescribed steps" in text
