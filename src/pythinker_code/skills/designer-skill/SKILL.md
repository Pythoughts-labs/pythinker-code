---
name: designer-skill
description: Prescriptive frontend design guidance via the designer-skill MCP server. Use when the user asks to use designer-skill, improve UI/UX, run the anti-slop ship gate, apply a design system, or enhance pages/components with MCP-backed design references — especially for Pythinker docs and marketing surfaces with DESIGN.md/PRODUCT.md.
---

# designer-skill (MCP)

`designer-skill` is **not** a filesystem workflow skill. It is delivered by the connected **designer-skill MCP server**. After reading this stub, call the MCP tools below — do **not** call `ReadSkill` again for the same name.

## Required MCP tools

Call these by their registered tool keys (`mcp__designer-skill__<tool>`):

| Step | Tool | Purpose |
| --- | --- | --- |
| 1 | `get_design_system` | Session preflight, precedence rules, routing map, ship-gate overview |
| 2 | `get_reference` | Load the specific reference file the task needs |
| 3 | `dispatch_intent` | Route ambiguous design requests to the right reference/workflow |
| 4 | `apply_designer` | Apply prescriptive design moves to the scoped surface |
| 5 | `anti_slop_checklist` | Mandatory ship gate before declaring frontend work done |

If a tool is missing, check `/mcp` — the server may still be connecting.

## Session preflight

Before editing UI:

1. Read project design sources when present (`DESIGN.md`, `PRODUCT.md`, or equivalent).
2. Call `get_design_system` first.
3. Pull only the references the scoped surface needs via `get_reference`.
4. Implement changes; run `anti_slop_checklist` before finishing.

## Common aliases

These names refer to the same MCP integration — always use MCP tools, not `ReadSkill`:

- `designer-skill`
- `designer-skill:designer-skill` (plugin-style slash autocomplete)
- "use designer-skill mcp" / "designer mcp"

## When MCP is unavailable

If `/mcp` shows designer-skill disconnected, run `pythinker mcp` to configure/auth it. Do not substitute ad-hoc design advice for the MCP workflow when the user explicitly requested designer-skill.
