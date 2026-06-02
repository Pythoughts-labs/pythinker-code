# Shimmer traveling-waves redesign

**Date:** 2026-06-01
**Status:** Approved design, pending implementation
**Scope:** `src/pythinker_code/ui/shell/motion.py` (plus tests)

## Problem

The active-work shimmer (`_shimmer_segments`) sweeps a single bright highlight
right-to-left across a label, then jumps back and repeats in the same direction.
It loops in one direction only — there is no sense of the light bouncing or
reaching the end of the word.

We want the shimmer to read like **traveling waves**: a wave crosses the word,
splashes outward from the middle when it reaches the end, then a wave travels
back the other way, splashes again, and repeats.

## Goal

Restructure the per-character shimmer into a four-phase loop while keeping:

- the existing 3-color palette (`#D49E5A` muted orange-yellow base / `#E2C18A`
  warm sheen-trail mid / `#D8DCE2` silver highlight) and
  `_SHIMMER_INTERVAL_S = 0.22` tick;
- the **purely time-derived** model — every frame is a function of `elapsed_s`
  alone, so the prompt, activity tree, and pinned-todo renderers stay in sync
  with no shared animation state;
- the public surface: `shimmer_text`, `shimmer_prompt_fragments`, and the
  per-char path inside `activity_status_line` call the same engine with no
  signature changes;
- the `colors_disabled()` (plain text) and reduced-motion (static base amber)
  short-circuits exactly as today.

## Animation cycle

`L = len(label)`. One loop is four phases, indexed by
`frame = int(max(0.0, elapsed_s) / 0.22)`, `phase_index = frame % CYCLE_LEN`.

| Phase | Name            | Behavior                                                     | Frames           |
|-------|-----------------|-------------------------------------------------------------|------------------|
| A     | Wave → (R→L)    | Current sweep, unchanged: violet head + asymmetric coral trail | `L + 6`        |
| B     | Splash          | Wave blooms from center char outward to both edges, settles | `ceil(L/2) + 3`  |
| C     | Wave ← (L→R)    | Mirror of A: head travels the other way, trail flips side   | `L + 6`          |
| D     | Splash          | Same center-out bloom as B                                  | `ceil(L/2) + 3`  |

`CYCLE_LEN = 2*(L + 6) + 2*(ceil(L/2) + 3)`. After phase D the loop returns to A.

### Phase A — wave right-to-left (preserve current look)

Unchanged from today: `head = L + 2 - local_phase`; for each non-space char at
index `i`, `offset = i - head`:

- `offset == 0` → highlight
- `offset in (-1, 1, 2, 3)` → mid (asymmetric trailing edge)
- else → base

### Phase C — wave left-to-right (mirror)

`head` travels from the left edge to past the right edge as `local_phase`
increases. The trail is mirrored to the opposite side so the sheen still trails
*behind* the direction of travel:

- `offset == 0` → highlight
- `offset in (1, -1, -2, -3)` → mid
- else → base

### Phase B / D — splash (center-out traveling wave)

`center = (L - 1) / 2` (fractional for even `L`). On local splash frame `f`
(0-based), wavefront radius `r = f`. For each non-space char at index `i`,
`d = abs(i - center)`. The wavefront is a half-cell band so odd and even
lengths behave identically:

- `r - 0.5 <= d <= r + 0.5` → highlight — the expanding wavefront
- `d < r - 0.5` → mid — already-filled interior
- `d > r + 0.5` → base — not yet reached

For even `L` the two center chars (`d == 0.5`) light up together on `f == 0`;
for odd `L` the single center char (`d == 0`) lights up on `f == 0`.

The final settle frames (after the wavefront passes both edges) paint the whole
word base amber, giving a brief calm beat before the next wave launches.

Spaces remain uncolored (`None`) in every phase, exactly as today.

## Implementation shape

Refactor `_shimmer_segments(label, elapsed_s, *, reduced_motion)` into a small
dispatcher:

- keep the early returns (`not label`, `colors_disabled`, reduced-motion);
- compute `L`, the four phase lengths, `CYCLE_LEN`, and `phase_index`;
- delegate to one of two helpers that return a `list[str | None]` of per-char
  colors:
  - `_wave_colors(chars, local_phase, direction)` — phases A and C;
  - `_splash_colors(chars, local_phase)` — phases B and D;
- coalesce equal-color runs into `(color, text)` segments (existing logic).

No changes to `shimmer_text`, `shimmer_prompt_fragments`,
`shimmer_spinner_style`, or any call site.

## Edge cases

- `L == 0` → `[]` (existing guard).
- `L == 1` → `center == 0`, splash highlights the single char on `f == 0` then
  settles; waves degenerate gracefully (single char cycles base/mid/highlight).
- Labels with spaces / multi-word ("Reticulating splines") → positional math is
  unaffected; spaces stay `None`.

## Verification (TDD)

New tests in `tests/ui_and_conv/test_shell_motion_shimmer.py`:

1. **Splash originates at center and widens** — at a splash-phase frame, the
   highlighted indices are centered and the highlighted/filled span grows over
   consecutive frames.
2. **Phase C trail is mirrored vs phase A** — for a head at the same offset, the
   mid-colored trail sits on the opposite side.
3. **Cycle returns to start** — colors at `frame` and `frame + CYCLE_LEN`
   (for a fixed label) are identical.
4. **Palette + plain-text invariants preserved** — existing three-color and
   reduced-motion assertions still pass.

Plus: `make check-pythinker-code` (ruff check + ruff format) green.

## Out of scope

- `shimmer_spinner_style` (single-color whole-word path) keeps its current
  simple 4-step palette cycle.
- No new config flags, no palette changes, no timing knobs exposed.
