# Update the status of the active thread goal set via `/goal`.

Call this only when one of the following is true:

- **complete** — the completion audit passed: current evidence proves every requirement derived from the objective, with nothing missing, incomplete, or unverified. Provide the per-requirement evidence in `summary`. Do not mark complete because progress was made or because you are stopping work.
- **blocked** — you are truly at an impasse that cannot be resolved without user input or an external-state change, and the same blocking condition has repeated for at least three consecutive goal turns (counting the original turn and any automatic goal continuations). Never use blocked merely because the work is hard, slow, uncertain, or incomplete.

Marking the goal stops goal reminders and automatic continuations. The user can dismiss the goal with `/goal clear` or reactivate it with `/goal resume`.
