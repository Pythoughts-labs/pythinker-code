---
name: agent-creator
description: Author a new project-specific Pythinker subagent (a specialist like "migration-reviewer" or "api-contract-checker") with a correct spec, a persona-rich system prompt, and a structured output contract. Use when the user wants to create, scaffold, or design a custom agent / subagent, or asks how Pythinker agent YAML / markdown agent files, tool scoping, or the extend-inheritance schema work.
---

# Agent Creator

Guide the user to a correct, immediately-loadable Pythinker agent definition. The hard part is not
the file format — it is a sharp `when_to_use`, a scoped tool set, a persona that earns its keep, and
a structured output contract. The builtin agents under `src/pythinker_code/agents/default/`
(`plan.yaml`, `explore.yaml`) are the quality bar; match them.

Do NOT invent a new loader or code path. Two existing, additive mechanisms already load custom
agents — pick the one that fits and write a file. No changes to `agentspec.py`, the CLI, or the
runtime are needed.

## Two ways to define an agent

### A. Markdown agent file (quick, auto-discovered) — preferred default

A single `<name>.md` placed in a discovery directory is auto-discovered on the next launch.
Frontmatter fields recognized by `parse_markdown_agent`:

- `name` — the agent name (falls back to the filename stem).
- `description` — what it is (falls back to the first body line).
- `when_to_use` — when the orchestrator should delegate to it (falls back to `description`).
- `tools` — a YAML list of **friendly tool names**, mapped to import paths automatically — do NOT
  use the `module:ClassName` form here. The supported names are: `Agent`, `Bash`, `Edit`, `Fetch`,
  `Glob`, `Grep`, `Read`, `TodoWrite`, `WebFetch`, `WebSearch`, `Write`.
- `model` — optional model alias.

The markdown **body** is the agent's system prompt (its persona + rules + output contract).

```markdown
---
name: migration-reviewer
description: Reviews database/schema migrations for safety and reversibility.
when_to_use: Use when a change touches migration files, schema DDL, or data backfills.
tools: [Read, Grep, Glob, Bash]
---

You are a database-migration safety reviewer. You do NOT edit files.
... persona, rules, and a structured output contract ...
```

### B. YAML agent spec (richer: inheritance, subagents, separate prompt file)

A `agent.yaml` + a separate `system.md`, loaded via `--agent-file path/to/agent.yaml` (or referenced
as a subagent). Use this when you need `extend` inheritance, a `subagents:` block, or fine-grained
`allowed_tools` / `exclude_tools`. Full `AgentSpec` fields (see `agentspec.py`):

- `extend` — agent file to inherit from; set to `"default"` to inherit the builtin agent. Child
  fields override the parent; `system_prompt_args` are merged by key; `subagents` entries are merged
  with child entries winning on key conflicts.
- `name` (required), `system_prompt_path` (required, relative to the yaml file).
- `tools` — list in **`module:ClassName`** form (e.g. `pythinker_code.tools.file:ReadFile`).
- `allowed_tools` / `exclude_tools` — narrow the inherited/declared tool set.
- `system_prompt_args` — dict; conventionally carries `ROLE_ADDITIONAL` (persona text injected into
  the shared prompt).
- `model`, `mode` (`primary` | `subagent` | `all` | `hidden`), `steps` (≥1), `temperature` (0–2),
  `top_p` (0–1), `when_to_use`, `subagents` (`{name: {path, description}}`).

## Discovery directories (project scope, first-match-wins)

Write the file into one of these (scanned in this precedence order):

1. `.pythinker/agents/`  2. `.claude/agents/`  3. `.agents/agents/`  4. `.codex/agents/`

Prefer `.pythinker/agents/`. A markdown agent whose name matches a builtin subagent type is
**skipped** (the builtin wins) — give a project agent a distinct name.

## Workflow

1. **Interview** — ask only what you cannot infer. The four load-bearing questions:
   - Role: what specialist is this, in one sentence?
   - `when_to_use`: what concrete trigger should make the orchestrator pick it? (be specific —
     vague triggers cause both over- and under-delegation.)
   - Tool scope: read-only (review/explore) or mutating (implement)? Grant the **fewest** tools the
     role needs.
   - Output contract: what structured sections must every response end with?
   Ask the most important first; avoid overwhelming the user with one giant question.

2. **Choose the form** — default to a markdown agent file (A). Use YAML (B) only when the user needs
   inheritance, a subagents block, or allowed/exclude tool narrowing.

3. **Write the persona** — model it on `plan.yaml` / `explore.yaml`:
   - State the role and any hard prohibition up front (e.g. "You do NOT have access to file-editing
     tools" for a read-only reviewer).
   - Require evidence over guesses ("build a context packet from repository evidence before
     concluding").
   - End with a **structured output contract** — a fixed set of headed sections the agent must
     always emit. The builtins use sections like `### SUMMARY`, `### EVIDENCE`, `### RISKS`,
     `### BLOCKERS`; pick the ones your specialist needs (e.g. add a `### FINDINGS` for a reviewer).
     A specialist without an output contract is just the default agent with a costume.

4. **Write the file** into the chosen discovery directory (default `.pythinker/agents/<name>.md`).
   Name the file after the agent; use lowercase-hyphen names.

5. **Validate** — round-trip it: confirm a markdown agent parses (it appears in the agent list / is
   selectable) or load a YAML agent with `--agent-file`. Fix frontmatter/field errors before
   finishing. Pythinker hard-fails on a malformed spec, so a clean load is the acceptance test.

## Rules

- Grant the minimum tool set. A reviewer that can `Write` is a footgun.
- Mark read-only specialists as such in the prompt AND by omitting mutating tools.
- Every agent needs a sharp `when_to_use` and a structured output contract — these are the
  difference between a useful specialist and noise.
- Do not duplicate a builtin agent's job; if one already fits, recommend it instead of cloning.
- Markdown agents use friendly tool names; YAML agents use `module:ClassName`. Do not mix them.

## Output

After creating the agent, report:

```text
AGENT: <name> (<markdown|yaml> form)
PATH: <file written>
WHEN TO USE: <one line>
TOOLS: <granted tools>
VALIDATION: <how you confirmed it loads>
```
