---
name: customize-pythinker
description: Edit Pythinker's own configuration — agent YAML specs and extend-inheritance, the permission profiles that gate tools, plugin.json, and hook lifecycle events. Use ONLY when the user wants to configure, customize, or extend Pythinker itself (its agents, permissions, plugins, or hooks). For authoring a new agent use agent-creator; for authoring a skill use skill-creator; for general usage Q&A use pythinker-code-help.
---

# Customize Pythinker

Authoritative, offline schema for editing Pythinker's own configuration surface. Pythinker
**hard-fails on a malformed config**, so get the schema right the first time. This skill covers the
config surfaces no other builtin skill owns. Out of scope: authoring agents (use `agent-creator`),
authoring skills (use `skill-creator`).

Always verify a value against the real schema before writing it. After any edit, confirm Pythinker
still starts (a malformed file aborts startup).

## Agent YAML (`agentspec.py`)

An agent spec is a YAML file with a separate system-prompt markdown file. Inheritance lets a project
agent extend the builtin one.

| Field | Type | Notes |
|---|---|---|
| `extend` | str | Agent file to inherit from. `"default"` inherits the builtin agent. Child fields override parent; `system_prompt_args` merge by key; `subagents` merge with child entries winning. |
| `name` | str | Required (or inherited via `extend`). |
| `system_prompt_path` | path | Required; resolved relative to the YAML file. |
| `system_prompt_args` | dict[str,str] | Conventionally carries `ROLE_ADDITIONAL` (persona text). Merged when extending. |
| `tools` | list[str] | `module:ClassName` form, e.g. `pythinker_code.tools.file:ReadFile`. |
| `allowed_tools` / `exclude_tools` | list[str] | Narrow the inherited/declared tool set. |
| `model` | str | Optional model alias. |
| `mode` | `primary` \| `subagent` \| `all` \| `hidden` | Defaults to `primary`. |
| `hidden` | bool | Optional; hides the agent from default selection. Distinct from `mode: hidden`. |
| `steps` | int ≥ 1 | Max steps per turn. |
| `temperature` | float 0–2 | Optional. |
| `top_p` | float 0–1 | Optional. |
| `when_to_use` | str | Delegation guidance for the orchestrator. |
| `subagents` | dict[name → {path, description}] | Child subagent map. |

Project agents are auto-discovered as `*.md` files (Claude-style frontmatter) in, by precedence:
`.pythinker/agents/` > `.claude/agents/` > `.agents/agents/` > `.codex/agents/`. A markdown agent
whose name matches a builtin subagent type is skipped (the builtin wins); use a distinct name.

## Permission profiles (`soul/permission.py`)

Profiles gate what a tool call may do. There are exactly six. Each sets three flags:

| Profile | allow_file_mutation | allow_shell_mutation | allow_plan_file_mutation |
|---|---|---|---|
| `read_only` | false | false | false |
| `plan` | false | false | **true** |
| `ask` | false | false | false |
| `implement` | **true** | **true** | false |
| `review` | false | false | false |
| `verify` | false | false | false |

Only `implement` permits file and shell mutation. `plan` is read-only except the plan file. Subagent
types map to profiles (e.g. `explore`→`read_only`, `plan`→`plan`, `coder`/`implementer`→`implement`,
`review`/`code-reviewer`/`security-reviewer`→`review`, `verifier`/`debugger`/`judge`→`verify`).

## Plugins (`plugin/__init__.py` — `plugin.json`)

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "optional",
  "config_file": "optional path; REQUIRED if `inject` is set",
  "inject": { "PROMPT_KEY": "text or file ref" },
  "tools": [
    { "name": "do_thing", "description": "...", "command": ["bin", "arg"], "parameters": {} }
  ]
}
```

`name` and `version` are required. If `inject` is present, `config_file` must also be present.
A `PluginToolSpec` has `name`, `description`, `command` (list[str]), and optional `parameters` (dict).
Unknown top-level keys are ignored.

## Hooks (`hooks/config.py`)

A `HookDef` (in `config.toml`) has:

- `event` — one of the 13 lifecycle events (below).
- `command` — shell command; receives JSON on stdin.
- `matcher` — regex to filter; empty matches everything.
- `timeout` — seconds, 1–600, default 30 (fail-open on timeout).

The 13 `HookEventType` values:
`PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `UserPromptSubmit`, `Stop`, `StopFailure`,
`SessionStart`, `SessionEnd`, `SubagentStart`, `SubagentStop`, `PreCompact`, `PostCompact`,
`Notification`.

## Workflow

1. Identify which surface the request touches (agent / permission / plugin / hook).
2. Read the user's current config first; never blind-overwrite.
3. Apply the smallest correct change, validated against the tables above.
4. Confirm Pythinker still starts cleanly; a malformed config aborts startup.

## Rules

- Verify every enum value and required field against this skill before writing — Pythinker
  hard-fails on bad config.
- Prefer the least-privileged permission profile that satisfies the need.
- Do not author new agents or skills here — defer to `agent-creator` / `skill-creator`.

## Output

```text
SURFACE: <agent|permission|plugin|hook>
CHANGE: <what was edited>
FILE: <path>
VALIDATION: <how you confirmed Pythinker still loads>
```
