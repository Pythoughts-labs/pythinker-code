Post a one-line progress checkpoint to the user during a long, multi-step turn.

The note appears as an append-only breadcrumb in the transcript, so the user can
scan what you've accomplished and decide whether to steer — without interrupting
your work.

## When to use

- On long multi-step work (migrations, multi-file refactors, multi-phase tasks),
  post a brief checkpoint after completing a meaningful milestone — e.g. after a
  phase, a risky step, or before starting a distinct new sub-task.

## When NOT to use

- NOT for the final answer or summary — write that as your normal response.
- NOT after every edit or tool call — that is noise. Prefer the fewest notes
  that let the user follow the arc of the work.
- NOT for questions — use AskUserQuestion when you need an answer to proceed.
- NOT on short or single-step turns.

Keep `title` short and scannable; use `body` only for a one-line detail or the
next step. This tool does not advance the task — it only reports progress.
