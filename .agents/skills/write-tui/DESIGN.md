# TUI Design Spec

> This file is the **single source of truth** for all dialogs, selectors, and input fields in this directory. Read it before adding or changing an interactive component. Use the checklist at the end before committing.
> Reference component: `components/dialogs/model-selector.ts` (`/model`). Match its header, hints, search, selection, and current-item states in every list dialog.

---

## 1. Visual states

| Meaning | Standard | Constant / token |
|---|---|---|
| Selection pointer | `❯` (`primary`) | `constant/symbols.ts` → `SELECT_POINTER` |
| Selected item text | `primary` + bold | `chalk.hex(colors.primary).bold` |
| Current / active item | Trailing `← current` in `success` | `constant/symbols.ts` → `CURRENT_MARK` |
| Dangerous item / action | `error` (also bold when selected) | `chalk.hex(colors.error)` |
| Dangerous confirmation `[y/N]` | `warning` + bold | `chalk.hex(colors.warning)` |
| Toggle state: on | `enabled` after the name, two spaces in (`success`) | `chalk.hex(colors.success)` |
| Toggle state: off | `disabled` after the name, two spaces in (`textDim`) | `chalk.hex(colors.textDim)` |
| List / selector border | Straight `─` (`primary`), one rule each at the top and bottom | — |
| Input border | Rounded `╭ ╮ ╰ ╯` (`primary`) | — |

- **Do not** invent selection pointers (`>` / `▶` / `→`, etc.); use `SELECT_POINTER`.
- **Do not** use `●` / `(current)` for the current item; use `CURRENT_MARK` (at the end of the row, in `success`, with one leading space).
- Current and selected items are **independent**: current means the value in effect (trailing marker); selected means the cursor row (pointer + highlight). Both can appear on the same row.

## 2. Colors

- Always use **semantic tokens**: `chalk.hex(colors.<token>)`. The repository's `chalk-named-color-guard` enforces this; named colors such as `chalk.red` / `chalk.gray` are **prohibited**.
- `ThemeStyles` (`state.theme.styles.*()`) is an optional convenience wrapper. Colors must come from `ColorPalette` tokens with or without it.
- Available semantic tokens are in `theme/colors.ts`: `primary` `accent` `text` `textStrong` `textDim` `textMuted` `border` `borderFocus` `success` `warning` `error` `status`, etc.
- **Do not highlight individual keys in hints**: use `textMuted` for the whole line, without separate colors for `Enter` / `Esc` / `D`, etc.

## 3. Standard list-dialog layout

Follow `model-selector`, with this fixed order from top to bottom:

```text
─────────────────────────────────────────  ① Top border (primary, full-width rule)
 Select a model  (type to search)            ② Title (primary + bold), with a textMuted suffix when searchable and the query is empty
 ↑↓ navigate · Enter select · Esc cancel    ③ Hint (textMuted, directly below the title, no key highlighting)
                                            ④ Blank line
 Search: gpt                                ⑤ Search row, only with a query (` Search: ` in primary + query in text)
  ❯ GPT-5            openai                  ⑥ Item: pointer + name on the left, secondary column on the right (textMuted)
    GPT-4.1          openai ← current        Current item has a trailing ` ← current` (success)
                                            ⑦ Blank line
 ▼ 3 more                                   ⑧ Scroll / match indicator: `▼ N more` without a query, `x / y` with one
─────────────────────────────────────────  ⑨ Bottom border (primary, full-width rule)
```

Required conventions:

- **The header has only one top rule**. The hint follows the title directly; **do not** insert another rule below the title. The whole dialog has exactly two full-width rules (top + bottom).
- **`(type to search)` appears only as a title suffix** when the list is searchable and the query is empty. Do not repeat it in the hint.
- Render the **`Search:` row below the blank line and above the list**, only when there is a query.
- Place the hint directly below the title, with no blank line between them. Put one blank line between the hint and body.
- Pass every final line through `truncateToWidth(line, width)` to fit wide characters and narrow terminals.

## 4. Hint vocabulary (English UI)

Each hint segment has **key + description**. Separate segments with ` · ` (a middle dot with one space on each side).

| Action | Key token | Description | Complete segment |
|---|---|---|---|
| Move | `↑↓` | navigate | `↑↓ navigate` |
| Page | `←→` or `PgUp/PgDn` | page | `←→ page` |
| Confirm / select | `Enter` | select | `Enter select` |
| Cancel / close | `Esc` | cancel | `Esc cancel` |
| Delete | `D` | delete | `D delete` |
| Clear search | `Backspace` | clear | `Backspace clear` |
| Switch provider | `Tab` | toggle provider | `Tab toggle provider` |
| Search (title suffix) | Typing | — | `(type to search)` |

- **Capitalize key tokens** (`Enter` / `Esc` / `Tab` / `Backspace` / `D`); use **lowercase descriptions** (navigate / select / cancel / page / delete / clear). Keep `↑↓` / `←→` unchanged.
- Use `↑↓` for navigation, not `▲/▼`.
- Use only `cancel` to mean leaving the dialog, without mixing close / back / exit / dismiss. Domain-specific actions such as approval rejection are exceptions.
- Keep hints relevant to the state. With no query, the title already shows `(type to search)`; do not repeat it. With a query, append `Backspace clear` to the hint.

## 5. Tab bar (provider switching in `/model`)

`tabbed-model-selector` wraps the flat `model-selector` in provider tabs. Match the **AskUserQuestion** tabs:

```text
 Select a model  (type to search)
 Tab toggle provider · ↑↓ navigate · Enter select · Esc cancel   ← Provider switching is the first hint
                                            ← Blank line
 All   Pythinker Code   openai               ← Active: selectionBg + inverseText + bold; inactive: textMuted
                                            ← Blank line
  ❯ ...
```

- Put the tab bar **below the hint**, with **one blank line above and below** it.
- Active tab: ``chalk.bgHex(colors.selectionBg).hex(colors.inverseText).bold(` ${label} `)``; inactive tab: `chalk.hex(colors.textMuted)`. Both have the same visible width.
- The first tab is always `All` (all providers), and **`All` is the default**. Select a provider tab only when `initialTabId` is passed explicitly, such as after adding a provider through `/provider`.
- `Tab` / `Shift+Tab` cycle through tabs. `Tab toggle provider` is the first hint segment.
- The current model still uses `❯` + `← current` in its tab; switching tabs must preserve its location.

## 6. Keys

| Action | Key | Detection |
|---|---|---|
| Move | `↑` / `↓` | `matchesKey(data, Key.up/down)` |
| Page | `PgUp` / `PgDn` | `matchesKey(data, Key.pageUp/pageDown)` |
| Confirm / select | `Enter` | `matchesKey(data, Key.enter)` |
| Cancel / close | `Esc` | `matchesKey(data, Key.escape)` |
| Delete | `D` | `printableChar(data) === 'D'` (also accept `'d'`) |
| Search | Typing | `printableChar(data)` |

- **Character comparisons must use `printableChar()`** for the Kitty protocol. `printable-key-guard` enforces this. Use `matchesKey(data, Key.*)` for function keys.
- **`Esc` has two stages**: clear an existing query first (`list.clearQuery()`); call `onCancel()` only when the query is empty.
- `←` / `→` depend on the component: switch values where there is no paging structure (such as thinking on/off in `/model`); page in lists without horizontal values, such as `choice-picker`. **Do not** assign paging to `←→` in a component that uses them for thinking.
- **Use `D` for deletion**, consistently across `/provider` and `/plugins`. A letter key requires the list to have **no type-to-search**, or it would enter the search field. All current lists with delete actions are non-searchable. If a list needs both search and deletion, use a non-printable key for deletion.

## 7. Toggle lists and multi-select

Use this pattern when each row can be enabled or disabled independently, such as installed plugins in `/plugins` or MCP servers. A single-select list submits and closes with `Enter`; a toggle list uses `Space` to change the row in place and stays open.

```text
 Plugins
 ↑↓ navigate · Space toggle · Enter details · Esc cancel
                                            ← Blank line
 Installed plugins (2)                      ← Section title (textStrong / bold)
  ❯ Example plugin  enabled                 ← Selected name (❯ + primary + bold), status label (success)
    id example-plugin · 1 skill · MCP 1/1 · via plugins.example.com · official   ← Secondary information (textMuted, separated by ` · `)
    Sample tools  disabled                  ← Unselected name (text), status label (textDim)
    id sample-tools · 14 skills · via plugins.example.com · curated
```

Conventions:

- **`Space` toggles the current row** immediately (on ↔ off), while keeping the dialog open. Include `Space toggle` in the hint.
- Put the **status label** immediately after the name, separated by two spaces: `enabled` in `success`, `disabled` in `textDim`. Handle other meanings through the same `statusStyle` source, such as `installed` in `success` and `install…` in `primary`.
- `Enter` has another role in toggle lists, such as `Enter details`; it does not toggle.
- List each independent action (toggle / details / delete / submenu) in the hint, with capitalized key tokens: `Space toggle · Enter details · D remove`. Follow section 4 for capitalization.
- A row can have one secondary information line for its id / count / source / trust level. Use `textMuted` and ` · ` separators.

## 8. Thinking control (`/model` only)

Show the selected model's three thinking states below the list, with a fixed segmented `[ On ] Off` appearance:

- Heading: `Thinking  (←→ to switch)` only in the `toggle` state; otherwise just `Thinking`.
- `toggle`: `[ On ]  Off` / `On  [ Off ]`, with the active segment in `primary` + bold.
- `always-on`: `[ Always on ]`.
- `unsupported`: `[ Off ]` + `unsupported` in `textMuted`.
- `←` / `→` change the draft. Normalize it with `effectiveThinking()` on submit (`always-on` → true, `unsupported` → false).

## 9. Input fields (multiple fields)

- Use a rounded box `╭ ╮ ╰ ╯` in `primary`.
- Switch fields with `Tab` / `Shift+Tab` / `↑` / `↓`.
- `Enter` advances to the next field, or submits from the last field.
- Cancel with `Esc` / `Ctrl+C` / `Ctrl+D`.
- Match the footer to the focused field: `Enter next` before the last field, `Enter submit` on the last field.
- Validate required fields in field order and focus the first invalid field. For example, in custom-registry, focus URL when it is empty, then token when it is empty. Show errors through the corresponding field's sub-hint state.

## 10. Shared components (reuse first)

| Purpose | Component |
|---|---|
| List cursor / search / paging state machine | `utils/searchable-list.ts` → `SearchableList` |
| Paged view | `utils/paging.ts` → `pageView` |
| Kitty printable characters | `utils/printable-key.ts` → `printableChar` / `isPrintableChar` (with guard) |
| Selection pointer / current-item marker | `constant/symbols.ts` → `SELECT_POINTER` / `CURRENT_MARK` |

New list components **must reuse `SearchableList`** for cursor / search / paging, and match the layout, keys, and copy in sections 3–8.

## 11. Checklist for new or changed dialogs

- [ ] Follow section 3: top rule, title (with optional `(type to search)` suffix), hint, blank line, `Search:` row, list, bottom rule. No inner rule below the title.
- [ ] The entire hint uses `textMuted`, without key highlighting. Key tokens are capitalized, descriptions are lowercase, and segments use ` · `.
- [ ] Use `SELECT_POINTER` and `CURRENT_MARK`, without custom `>` / `▶` / `→` / `●` / `(current)` markers.
- [ ] All colors come from `colors.<token>`, without named colors.
- [ ] Keys: `↑↓` move, `PgUp/PgDn` page, `Enter` confirms, `Esc` cancels (clear the query first in searchable lists), `D` deletes. Character comparisons use `printableChar()`.
- [ ] Use only `cancel` for leaving the dialog, without mixing close / back / exit / dismiss.
- [ ] Toggle lists use `Space toggle` in place and stay open. Put the `enabled` (`success`) / `disabled` (`textDim`) label two spaces after the name (section 7).
- [ ] Long lists show scroll / paging indicators (`▼ N more` or `x / y`); empty states have clear text such as `No matches`.
- [ ] Every line passes through `truncateToWidth(line, width)` to fit wide characters and narrow terminals.
- [ ] Reuse `SearchableList`. Input fields have rounded boxes; multiple fields support `Tab/↑↓` navigation and Enter to advance / submit at the last field.
- [ ] Component tests cover render snapshots and `handleInput` key behavior.
