# Documentation Agent Guide

This repository uses VitePress for the documentation site. User-facing pages live under `docs/`.

## Structure

- English docs live under `docs/`.
- Main sections (nav + sidebar) are:
  - Guides: getting-started, desktop, use-cases, interaction, sessions
  - Customization: mcp, skills, plugins, agents, hooks
  - Configuration: config-files, providers, overrides, env-vars, data-locations
  - Reference: pythinker-command, tools, slash-commands, keyboard
  - Release notes: changelog
- Navigation and sidebar are defined in `docs/.vitepress/config.ts`. Any new or renamed page must be wired there.

## Source of truth

- **Changelog page**: `docs/release-notes/changelog.md` is generated from the CLI package changelog after each release via the `sync-changelog` skill.

## Authoring workflow

- Each page should keep the section ordering established by surrounding pages. Changelog is the exception because it is generated from release history.

Before rewriting a page, always: (1) understand why the original is structured the way it is, (2) identify what the reader genuinely needs to know, (3) sketch the section structure, then (4) fill in the content. Skip step 1–3 and you will lose content while rearranging format.

## Readers

Pythinker Code documentation serves two overlapping audiences. Write for both simultaneously.

**Technical users** — familiar with the terminal, config files, API keys, and environment variables. Give them commands and paths directly; do not explain basics.

**Non-technical AI users** — product managers, designers, operators — who use AI tools but are unfamiliar with terms like "stdin", "exit code", or "regex". They primarily interact through VS Code or config files rather than writing scripts.

Both groups share the same behavior: they arrive with a specific goal, scan headings and first sentences before reading further, execute steps in order, and copy-paste code blocks directly. They abandon pages when they hit unexplained jargon.

**Writing targets:**
- Technical users: complete a task in under 5 minutes, no filler.
- Non-technical users: copy-paste their way to a working setup and roughly understand what it does, without needing to understand the underlying mechanics.

**Jargon rule:** On first use, add a plain-English gloss in parentheses. Use the term normally afterwards.

> Example: `stdin` (the channel a program reads input from), `exit code` (the status number a program returns when it finishes; 0 means success).

## Naming conventions

- Filenames are kebab-case.
- Use consistent section labels that match the sidebar titles.
- Use backticks for flags, commands, subcommands, command arguments, file paths, code identifiers, type names, field names, field values, and keyboard shortcuts.

## Wording conventions

- Do not change H1 titles or nav/sidebar labels.
- English H2+ headings use sentence case (only the first word capitalized unless it is a proper noun). Treat "Wire", "Plan mode", "Always Ask", "Ask When Needed", "Never Ask", "Thinking mode", and "Dynamic Workflow" as proper nouns; do not treat "agent" as a proper noun.
- Use `API key` in English; keep `JSON`, `JSONL`, `OAuth`, `macOS`, `Node.js`, `npm`, `pnpm`, and `TypeScript` as-is.
- Use straight double quotes with spaces for quoted content.
- Use inline code for tool names (e.g., `Read`, `Grep`, `Bash`).

Term mapping (proper noun handling):

| English | Proper noun (en) |
| --- | --- |
| Agent | no |
| main agent | no |
| subagent | no |
| shell | no |
| Plan mode | yes (Plan mode) |
| Always Ask | yes |
| Ask When Needed | yes |
| Never Ask | yes |
| Thinking mode | yes (Thinking mode) |
| MCP | yes |
| Pythinker Code CLI | yes |
| Agent Skills | yes |
| skill | no |
| system prompt | no |
| prompt | no |
| session | no |
| context | no |
| API key | no |
| JSON | yes |
| JSONL | yes |
| OAuth | yes |
| macOS | yes |
| TypeScript | yes |
| Node.js | yes |
| npm | yes |
| pnpm | yes |
| pythinker | yes |
| approval request | no |
| slash command | no |
| tool call | no |
| frontmatter | no |
| user message | no |
| assistant message | no |
| tool message | no |
| turn | no |
| provider | no |
| Prompt Flow | yes |
| Dynamic Workflow | yes (Dynamic Workflow) |
| Dynamic Workflow mode | yes (Dynamic Workflow mode) |
| diff | no |

### Pythinker platform rules

Two distinct platforms exist and must never be mixed:

| | Pythinker Code platform | Pythinker Open Platform |
|---|---|---|
| Audience | Individual developers, subscription-based | Enterprise / product integration, pay-per-token |
| OpenAI-compatible base URL | `https://api.pythinker.com/coding/v1` | `https://api.pythoughts.com/v1` |
| Anthropic-compatible base URL | `https://api.pythinker.com/coding/` | Not supported |
| API key entry | [Pythinker Code console](https://pythinker.com/code/console) | [pythinker.com/platform](https://pythinker.com/platform) |

Rules:
- When documenting Pythinker Code CLI or VS Code: always use `api.pythinker.com/coding/…`. Never write `api.pythoughts.com` in this context.
- When documenting Open Platform integration: use `api.pythoughts.com/v1`.
- Distinguish context explicitly: "in Pythinker Code CLI / VS Code" vs "in third-party tools / your own product".
- Product full names: **Pythinker Code CLI** and **Pythinker Code for VS Code**. Do not abbreviate to "Pythinker CLI".

## Typography

- **Keyboard shortcuts**: Use hyphen between modifier and key (`Ctrl-C`, `Ctrl-D`, `Shift-Tab`, `Alt-V`), not plus sign. Exception: literal application output (e.g., the `Press Ctrl+C again to exit` hint produced by the product itself) keeps its exact rendering.
- **Code block language**: Always specify language for fenced code blocks (e.g., ` ```sh `, ` ```toml `, ` ```json `, ` ```ts `). Exception: natural language examples (user prompts) may omit the language.
- **Callout titles**: Use short category titles for callout blocks (`::: tip`, `::: warning`, `::: info`, `::: danger`). Put the detailed description in the block content, not the title.
  - English: use no title or short words like `Note` for warning.
- **Version info blocks**: For version change callouts, use `::: info` with a category title (Added/Changed/Removed). The content should be a complete sentence.
- **Callout syntax**: Use `:::` for standalone callouts. `::::` is valid only as the outer fence of a nested container and must be correctly closed; an unclosed or mismatched `::::` breaks page rendering. When nesting is not needed, use a `>` blockquote inside a callout for secondary notes instead.

## Writing style

- **Natural narrative**: Organize content like writing an article, guiding readers smoothly through the material.
- **Avoid fragmentation**: Don't turn every point into a subheading; use paragraph transitions instead.
- **Global perspective**: "Getting Started" introduces core concepts only; detailed usage belongs in later pages.
- **Progressive depth**: Guides → Customization → Configuration → Reference, information deepens gradually.
- **No nav tip blocks**: VitePress provides automatic prev/next navigation; don't add redundant next-step tip blocks at page end. A `## Next steps` section is appropriate when there are closely related follow-on pages.
- **One idea per paragraph**: Each paragraph makes one point. 3–4 sentences is the target; split when a paragraph exceeds 5 sentences.
- **Map before detail**: Every page and every major section should open with one "map" sentence before expanding into details.

- **Parallel content needs formatting**: Multiple items of the same kind written as separate paragraphs force readers to parse shape instead of meaning. Fix:
  - Each item is "name + one sentence": use an unordered list: `- **Name**: description`
  - Multiple dimensions: use a table
  - Each item is longer than two sentences: use a `###` subheading

## Format decisions

Choose the format that matches the content's structure, not the one that looks most thorough.

**Ordered list** — steps that must happen in sequence.

**Unordered list** — parallel items with no ordering dependency.

**Table** — reference content with multiple dimensions to compare or look up.

**Prose** — explanations, motivations, caveats.

## Cross-references

Readers never read just one page. Add links wherever they help.

**Always link when:**
1. A concept mentioned on this page has a full explanation on another page — link on first mention.
2. This page gives a brief summary while another page has the full reference — link the summary to the detail.
3. A later section depends on a concept defined earlier on this page — back-link with `[term](#anchor)`.

## Page structure

```
# Title (noun phrase, no period)

Opening sentence or two + plain-English summary (only when the concept has a learning curve)

> blockquote (optional: Beta notice, prerequisites)

Diagram (optional)

::: warning Banner (deprecation, breaking change, security notice — after opening content, before first ##)

## First section

Body…

## Next steps (optional, only when related pages exist)
- [Page name](/path) — one sentence describing what the reader can do there
```

## Content completeness

**Default position: keep everything.** When editing a page, every block of original content needs an explicit destination.

## Checklist

### Format

| Problem | Fix |
|---|---|
| `::::` unclosed or mismatched | Close the fence or replace with `:::` if nesting is not needed |
| Banner before first `##` but also before opening content | Move to after opening sentences / blockquote / diagram |
| Steps written as unordered list | Change to ordered list |
| Multi-dimension comparison written as prose | Convert to table |
| Technical term used without explanation on first occurrence | Add plain-English gloss in parentheses |
| Cross-reference written as "see …" with no link | Add inline link; prefer anchor to section |
| Code block has no language tag | Add language (e.g., `sh`, `toml`, `json`) |

### Pythinker-specific consistency

- **Base URL**: matches the [Pythinker platform rules](#pythinker-platform-rules) table above
- **Upgrade command**: matches `guides/getting-started.md`
- **Model ID**: use `pythinker-for-coding`, not a versioned model name
- **Login command**: `/login`, not `/setup`
- **Product full name**: **Pythinker Code CLI** or **Pythinker Code for VS Code** — never "Pythinker CLI"
- **Platform URLs**: `api.pythinker.com/coding/…` for Pythinker Code platform; `api.pythoughts.com/v1` for Open Platform — never mix the two

## Build and preview

- Docs are built with VitePress from `docs/`.
- Common commands (run inside `docs/`):
  - `npm install`
  - `npm run dev`
  - `npm run build`
  - `npm run preview`
- The build output is `docs/.vitepress/dist`.

## Changelog syncing

See `sync-changelog` skill for the changelog generation workflow.
