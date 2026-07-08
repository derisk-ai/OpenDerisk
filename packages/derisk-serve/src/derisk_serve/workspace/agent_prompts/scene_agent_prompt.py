from typing import Any, List

SCENE_AGENT_STATIC_PROMPT = """\
你是 OpenDerisk 场景空间助手（Scene Workspace Agent），当前工作空间的协作者。
你不是通用聊天助手；你的目标是理解用户在该场景空间中的工作目标，调用合适的工具推进任务，并把结果沉淀为可复用的资产或报告。
"""


def render_scene_dynamic_context(ctx: Any, mode: str = "lobby") -> str:
    """Render the dynamic workspace/playbook/task/tools block for the scene agent.

    Args:
        ctx: WorkspaceContextSnapshot (or a duck-typed test double).
        mode: "lobby" or "workbench".

    Returns:
        A Chinese prompt block describing the current scene context.
    """
    lines = ["## 当前场景上下文", ""]
    # TODO: implement in Task 4
    lines.append(f"模式：{mode}")
    return "\n".join(lines)
