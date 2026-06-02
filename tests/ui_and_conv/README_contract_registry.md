# Markdown + Report contract test registry (lead phase)

Maps spec bug classes to the test that guards them. Tier 1 = deterministic
capture. See
`docs/superpowers/specs/2026-05-29-tui-renderer-contract-hardening-design.md` §8.

| Spec area | Bug class | Test | Tier |
|---|---|---|---|
| 3 Markdown | table breaks on piped inline code | `test_md_table_contract::test_table_with_piped_inline_code_keeps_columns` | T1 |
| 3 Markdown | escaped pipe splits cell | `test_md_table_contract::test_table_with_escaped_pipes_keeps_literal_pipe` | T1 |
| 3 Markdown | code-span pipe escaper (unit) | `test_md_table_contract::test_escape_code_span_pipes_*` | T1 |
| 3 Markdown | escaper scoped to tables (prose inline-code safe) | `test_md_table_contract::test_prose_inline_code_pipe_is_not_corrupted_with_backslash` | T1 |
| 3 Markdown | empty header mislabeled | `test_md_table_contract::test_table_empty_header_cell_does_not_mislabel` | T1 |
| 3 Markdown | long cell data integrity (no truncation) | `test_md_table_contract::test_table_long_cell_wraps_without_dropping_content` | T1 |
| 3 Markdown | stale streamed table | `test_md_stream_idempotency::test_streaming_table_is_not_committed_mid_row` | T1 |
| 3 Markdown | nested report-fence promoted | `test_report_fence_nesting::*` | T1 |
| 4 ANSI | border inherits code-span color | `test_md_color_contract::test_code_block_border_does_not_use_inline_code_color` | T1 |
| 3 Markdown | report render on real data | `test_report_realdata::*` | T1 |
| 1 Stability | render idempotency | `test_md_stream_idempotency::test_h3_report_and_table_render_is_idempotent` | T1 |
| 1 Stability | offset divergence (H2) | `test_md_stream_idempotency::test_h2_stream_slices_reassemble_without_duplicate_rows` | T1 |
| 1 Stability | screen-authority | `test_md_render_authority::test_no_direct_terminal_writes_in_renderer` | T1 |
| repair | regex pipeline pinned | `test_md_repair_characterization::*` | T1 |

## Execution notes (deviations from the as-written plan)

Two contract tests exposed real gaps; both were resolved with explicit approval
(see the design spec §12):

- **Code-span pipes in tables (source fix).** `pythinker_markdown` followed
  strict GFM, so an unescaped `|` inside an inline code span dropped a table
  cell — exactly the malformed markdown LLMs emit. Fixed by escaping code-span
  pipes inside confirmed table rows (`_escape_code_span_pipes` in
  `components/markdown.py`, applied at the two `_split_pipe_cells` sites in
  `_normalize_table_block`). The escaper is proven *monotonic on cell count*, so
  it can never corrupt a well-formed table; residual corruption only on
  already-malformed input is intrinsic to a regex approach.
- **Long-cell test reframed to data integrity.** The bordered-grid table renderer
  folds long cell text across grid rows, drawing a vertical separator (│) between
  the fold lines, and may fold mid-word at widths < ~40 (cosmetic, *no data loss*).
  The long-cell guard therefore pins the stated contract ("wrap, not truncate"):
  every character survives — insensitive to whitespace *and* box-drawing glyphs —
  regardless of wrap.

## Known-weak guard (intentional, tracked)

- `test_md_stream_idempotency::test_streaming_table_is_not_committed_mid_row`
  contains a near-tautological branch (`... or "After" in "".join(committed)`),
  so its main protection is the reassembly-equality assertion. Kept as written
  (no source defect found); strengthen if the streaming committer is revisited.

## Hypotheses outcome

- **H1** (nested report-fence promotion) — reproduced, then fixed via AST fence
  extraction in `components/report.py` (`test_report_fence_nesting`).
- **H2** (stream offset divergence) — did **not** reproduce; kept as a guard.
- **H3** (render idempotency) — held; kept as a guard.
