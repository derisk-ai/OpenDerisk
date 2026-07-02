"""P4 Task 2: verify needs_tool_approval is removed from BaseAgent."""


def test_needs_tool_approval_removed():
    from derisk.agent.core.base_agent import ConversableAgent

    assert not hasattr(ConversableAgent, "needs_tool_approval"), (
        "ConversableAgent.needs_tool_approval should be removed in P4 "
        "(0 production callers; PermissionGate supersedes it)"
    )