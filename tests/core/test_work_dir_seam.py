"""Runtime.work_dir seam (worktree-isolation P1).

Operational cwd/path-resolution reads go through runtime.work_dir so a
child runtime can be pointed at an isolation worktree without touching
the shared session, which keeps owning persistence paths.
"""

from __future__ import annotations

from pythinker_host.path import HostPath


class TestWorkDirSeam:
    def test_defaults_to_session_work_dir(self, runtime) -> None:
        assert runtime.work_dir == runtime.session.work_dir

    def test_subagent_clone_inherits_by_default(self, runtime) -> None:
        child = runtime.copy_for_subagent(agent_id="a1", subagent_type="coder")

        assert child.work_dir == runtime.session.work_dir
        assert child.builtin_args is runtime.builtin_args

    def test_override_redirects_child_only(self, runtime, tmp_path) -> None:
        worktree = HostPath.unsafe_from_local_path(tmp_path / "wt")

        child = runtime.copy_for_subagent(
            agent_id="a1",
            subagent_type="coder",
            work_dir_override=worktree,
            work_dir_ls="wt-listing",
        )

        assert child.work_dir == worktree
        assert worktree == child.builtin_args.PYTHINKER_WORK_DIR
        assert child.builtin_args.PYTHINKER_WORK_DIR_LS == "wt-listing"
        # Parent surfaces untouched; session stays shared for persistence.
        assert runtime.work_dir == runtime.session.work_dir
        assert runtime.session.work_dir == runtime.builtin_args.PYTHINKER_WORK_DIR
        assert child.session is runtime.session

    def test_grandchild_inherits_override(self, runtime, tmp_path) -> None:
        worktree = HostPath.unsafe_from_local_path(tmp_path / "wt")
        child = runtime.copy_for_subagent(
            agent_id="a1", subagent_type="coder", work_dir_override=worktree
        )

        grandchild = child.copy_for_subagent(agent_id="a2", subagent_type="explore")

        assert grandchild.work_dir == worktree
