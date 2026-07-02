"""ToolContext 工厂。

根据 tool_call + resource_map + sandbox_manager 构造 ToolContext，
按 tool 类型注入活资源句柄（DBResource / RetrieverResource / AppResource / sandbox_client）。

等价 BAIZE tool_action.py:993-1059 + agent_adapter.py:240-320 的组装逻辑。
"""
from typing import Any, Dict, List, Optional

from derisk.agent.tools.context import ToolContext
from derisk.agent.core.v2.tool_call_types import V2ToolCall


# tool_name → resource_map key 的映射
_TOOL_RESOURCE_MAP = {
    "execute_sql": "db_resource",
    "list_tables": "db_resource",
    "get_table_spec": "db_resource",
    "KnowledgeSearch": "knowledge_retriever",
    "AgentStart": "app_resource",
}

# tool_name → resource_map 类型 key（用于查找）
_TOOL_RESOURCE_TYPE = {
    "execute_sql": "DBResource",
    "list_tables": "DBResource",
    "get_table_spec": "DBResource",
    "KnowledgeSearch": "RetrieverResource",
    "AgentStart": "AppResource",
}


class ToolContextFactory:
    def __init__(
        self,
        *,
        agent_id: str,
        conv_id: str,
        user_id: Optional[str] = None,
        scene: Optional[str] = None,
        scenario_id: Optional[str] = None,
        language: str = "zh",
        resource_map: Optional[Dict[str, List[Any]]] = None,
        sandbox_manager: Optional[Any] = None,
        skill_dir: Optional[str] = None,
        available_skills: Optional[Dict[str, str]] = None,
        agent_file_system: Optional[Any] = None,
        agent: Optional[Any] = None,
    ):
        self._agent_id = agent_id
        self._conv_id = conv_id
        self._user_id = user_id
        self._scene = scene
        self._scenario_id = scenario_id
        self._language = language
        self._resource_map = resource_map or {}
        self._sandbox_manager = sandbox_manager
        self._skill_dir = skill_dir
        self._available_skills = available_skills or {}
        self._agent_file_system = agent_file_system
        self._agent = agent

    def build(self, tool_call: V2ToolCall, tool: Optional[Any] = None) -> ToolContext:
        ctx = ToolContext(
            agent_id=self._agent_id,
            conversation_id=self._conv_id,
            user_id=self._user_id,
            scene=self._scene,
            scenario_id=self._scenario_id,
            language=self._language,
            skill_dir=self._skill_dir,
            available_skills=self._available_skills,
        )

        # 注入沙箱活句柄（G7）
        if self._sandbox_manager is not None:
            ctx.set_resource("sandbox_client", self._sandbox_manager.client)

        # 注入 agent_file_system（G4）
        if self._agent_file_system is not None:
            ctx.set_resource("agent_file_system", self._agent_file_system)

        # 注入 agent 引用（G4）
        if self._agent is not None:
            ctx.set_resource("agent", self._agent)

        # 按 tool 类型派发对应资源（G4）
        tool_name = tool_call.name
        resource_type = _TOOL_RESOURCE_TYPE.get(tool_name)
        resource_key = _TOOL_RESOURCE_MAP.get(tool_name)
        if resource_type and resource_key:
            resources = self._resource_map.get(resource_type, [])
            if resources:
                ctx.set_resource(resource_key, resources[0])

        return ctx