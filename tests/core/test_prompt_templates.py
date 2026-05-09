from __future__ import annotations

import pytest
from pythinker_host.path import HostPath

from pythinker_code.prompt_templates import (
    discover_prompt_templates,
    expand_prompt_template,
    parse_command_args,
    parse_prompt_template_text,
    substitute_args,
)


def test_parse_command_args_supports_quotes():
    assert parse_command_args("one \"two words\" 'three words'") == [
        "one",
        "two words",
        "three words",
    ]


def test_substitute_args_supports_placeholders():
    content = "$1 | $2 | $@ | $ARGUMENTS | ${@:2} | ${@:2:1}"
    assert substitute_args(content, ["alpha", "beta", "gamma"]) == (
        "alpha | beta | alpha beta gamma | alpha beta gamma | beta gamma | beta"
    )


def test_substitute_args_is_not_recursive():
    assert substitute_args("$1 $@", ["$2", "value"]) == "$2 $2 value"


def test_parse_prompt_template_frontmatter_and_body():
    template = parse_prompt_template_text(
        "---\ndescription: Review PR\nargument-hint: '<url>'\n---\nReview $1\n",
        file_path=HostPath("/tmp/pr.md"),
        scope="project",
    )

    assert template.name == "pr"
    assert template.description == "Review PR"
    assert template.argument_hint == "<url>"
    assert template.content == "Review $1"


def test_expand_prompt_template():
    template = parse_prompt_template_text(
        "Implement $ARGUMENTS",
        file_path=HostPath("/tmp/impl.md"),
        scope="user",
    )

    assert expand_prompt_template(template, 'fast "and safe"') == "Implement fast and safe"


@pytest.mark.asyncio
async def test_discover_prompt_templates_project_wins_over_user(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".pythinker" / "prompts").mkdir(parents=True)
    (project / ".pythinker" / "prompts" / "wr.md").write_text(
        "---\ndescription: Project wrap\n---\nproject $@\n",
        encoding="utf-8",
    )

    home = tmp_path / "home"
    (home / ".pythinker" / "prompts").mkdir(parents=True)
    (home / ".pythinker" / "prompts" / "wr.md").write_text(
        "---\ndescription: User wrap\n---\nuser $@\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home))
    templates = await discover_prompt_templates(HostPath.unsafe_from_local_path(project))

    assert templates["wr"].description == "Project wrap"
    assert templates["wr"].content == "project $@"


def test_prompt_templates_examples_expand():
    # Representative templates use both $@ and $ARGUMENTS; keep those
    # syntaxes compatible.
    assert substitute_args("Analyze GitHub issue(s): $ARGUMENTS", ["#1", "#2"]) == (
        "Analyze GitHub issue(s): #1 #2"
    )
    assert substitute_args("You are given one or more GitHub PR URLs: $@", ["url"]) == (
        "You are given one or more GitHub PR URLs: url"
    )
