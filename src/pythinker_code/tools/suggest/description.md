Post a soft, optional suggestion for the user's next action — without blocking the turn.

Unlike AskUserQuestion (a hard, turn-blocking modal), Suggest returns immediately and
posts an optional steer the user can act on or ignore. Use it after completing work to
offer an obvious next step, most often a review handoff.

When to use:
- After non-trivial changes, to offer a review: label "Review my changes", prefill "/review".
- To propose an obvious optional follow-up the user may want.

When NOT to use:
- When you genuinely need an answer to proceed — use AskUserQuestion instead.
- For routine progress updates — use Progress.
- Do not spam: at most one suggestion per turn, and only when it is genuinely useful.

This does not pause the turn; finish your final summary, and the suggestion stays for the
user to act on.
