from __future__ import annotations

from pythinker_code.agentspec import DEFAULT_AGENT_FILE, load_agent_spec


def test_reviewer_debugger_prompts_share_recovery_and_policy_review_guidance() -> None:
    spec = load_agent_spec(DEFAULT_AGENT_FILE)

    for name in ("code-reviewer", "security-reviewer", "debugger", "review"):
        subagent = load_agent_spec(spec.subagents[name].path)
        prompt = subagent.system_prompt_args["ROLE_ADDITIONAL"]
        assert ".pythinker/review-guidelines.md" in prompt
        assert "graceful degradation" in prompt
        assert "observability/logging" in prompt
        assert "recovery behavior" in prompt
        assert "structured result/status correctness" in prompt
        assert "approval/policy mismatches" in prompt
