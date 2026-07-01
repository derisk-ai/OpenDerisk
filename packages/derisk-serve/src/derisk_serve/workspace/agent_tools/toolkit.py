"""WorkspaceControlAgent wraps FunctionTools; injected into chat via extra_agents."""
from typing import List, Optional

from derisk.agent import ConversableAgent, LLMConfig
from derisk.agent.core.profile import ProfileConfig

from derisk_serve.workspace.agent_tools.playbook_tools import build_playbook_tools
from derisk_serve.workspace.agent_tools.read_tools import build_read_tools
from derisk_serve.workspace.agent_tools.write_tools import build_write_tools


# Layer 1 read tool names (shared by both modes) — 5 tools
LAYER1_READ = {
    "list_tasks",
    "get_task_info",
    "list_artifacts",
    "list_deliveries",
    "list_assets",
}
# Layer 2 read tool names (Lobby only) — 2 tools
LAYER2_READ = {"get_workspace_memory", "list_workspace_members"}
# Layer 3 read tool names (Workbench only) — 3 tools
LAYER3_READ = {"list_playbooks", "get_playbook_detail", "list_interventions"}


class WorkspaceControlAgent(ConversableAgent):
    """A ConversableAgent that exposes workspace read/write tools.

    Tools are registered in ``available_system_tools`` keyed by tool name so the
    agent can invoke them; the original list is also preserved in ``_tools``.
    Write tools create interventions rather than executing directly
    (non-blocking confirmation flow).
    """

    def __init__(
        self,
        system_app,
        tools: List,
        name: str = "workspace_control",
        llm_config: Optional[LLMConfig] = None,
    ):
        profile = ProfileConfig(name=name, role=name)
        super().__init__(profile=profile, llm_config=llm_config)
        self._tools = tools
        for tool in tools:
            self.available_system_tools[tool.name] = tool


def build_workspace_toolkit(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    conv_uid: Optional[str],
    task_id: Optional[int] = None,
    mode: str = "lobby",
    llm_config: Optional[LLMConfig] = None,
) -> Optional[WorkspaceControlAgent]:
    """Build the workspace control Agent for the given mode.

    Lobby (mode="lobby"): Layer 1 (5 read) + Layer 2 (2 read + 5 write) = 12 tools.
    Workbench (mode="workbench"): Layer 1 (5 read) + Layer 3 (3 read + 3 write) = 11 tools.
    Layer 2 and Layer 3 do not overlap.

    Returns ``None`` when ``conv_uid`` is missing, because write/playbook tools
    require a conversation context to create interventions.
    """
    if not conv_uid:
        return None

    all_read = build_read_tools(system_app, workspace_id)
    if mode == "lobby":
        layer1 = [t for t in all_read if t.name in LAYER1_READ]
        layer2_read = [t for t in all_read if t.name in LAYER2_READ]
        write = build_write_tools(
            system_app, workspace_id, user_id, conv_uid, task_id=task_id
        )
        tools = layer1 + layer2_read + write
    elif mode == "workbench":
        layer1 = [t for t in all_read if t.name in LAYER1_READ]
        layer3_read = [t for t in all_read if t.name in LAYER3_READ]
        playbook_write = build_playbook_tools(
            system_app, workspace_id, user_id, conv_uid, task_id=task_id
        )
        tools = layer1 + layer3_read + playbook_write
    else:
        raise ValueError(f"Unknown mode: {mode}")

    llm_config = llm_config or LLMConfig()
    return WorkspaceControlAgent(
        system_app=system_app, tools=tools, llm_config=llm_config
    )
