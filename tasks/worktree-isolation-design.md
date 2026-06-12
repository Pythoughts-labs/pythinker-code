# Worktree isolation for write-capable children — design note

**Status:** approved design, not yet implemented. Plan item:
`multi-agent/enforced-workspace-isolation` (Tier 1). Sized here as L: the
audit found ~94 `session.work_dir` / `PYTHINKER_WORK_DIR` consumer sites
across tools, soul, and permission layers, and child runtimes share the
parent's `session` and `builtin_args` objects — so honoring
`isolation="worktree"` requires a single work-dir seam first. A partial
redirect would produce *false* isolation (child believes it is isolated
while some tools still write the parent tree), which is worse than the
current honest intent-only metadata.

## Phases

1. **P1 — work-dir seam (mechanical, behavior-preserving).**
   `Runtime` gains `work_dir_override: HostPath | None = None` and a
   `work_dir` property returning `work_dir_override or session.work_dir`.
   Migrate consumers from `runtime.session.work_dir` to `runtime.work_dir`
   (sed-able; session object itself stays shared for persistence paths —
   ONLY operational cwd/path-resolution sites migrate; session-file paths
   like context/wire stores intentionally keep `session.*`).
   `copy_for_subagent(work_dir_override=...)` re-renders `builtin_args`
   (`PYTHINKER_WORK_DIR`, `PYTHINKER_WORK_DIR_LS`) for the child.
   Verify: full suite green, zero behavior change without an override.

2. **P2 — worktree lifecycle in the background runner.**
   When `isolation="worktree"` and the child type has a write profile:
   - Reject with an actionable error when the work dir is not a git repo.
   - `git worktree add <session_dir>/worktrees/<agent_id> HEAD` before
     launch; build the child runtime with `work_dir_override` pointing at
     it.
   - On completion, append to the final report: the worktree path and
     `git -C <wt> diff --stat` so the orchestrator merges deliberately.
   - Cleanup: remove the worktree when the child finished clean with no
     changes; retain it (and say so in the report) when it has changes or
     failed, matching existing recovery rules.

3. **P3 — RunAgents batch support** reusing P2 per child.

## Verification

- Unit: override property; builtin_args re-render; non-git rejection.
- Integration: two parallel background coders editing the same file land
  in distinct worktrees with no cross-clobber; reports name both paths.
