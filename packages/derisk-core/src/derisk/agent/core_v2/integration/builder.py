"""
V2ApplicationBuilder - Agent 构建工厂

基于原有的 AgentResource 体系构建 Core_v2 可运行的 Agent
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type, Union

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class AgentBuildResult:
    agent: Any
    agent_info: Any
    tools: Dict[str, Any]
    resources: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


class V2ApplicationBuilder:
    """
    V2 Agent 构建器

    核心功能:
    1. 从 AppResource 构建可运行的 Agent
    2. 转换 AgentResource 到 V2 Tool 系统
    3. 配置权限系统
    4. 集成 LLM 模型
    """

    def __init__(self):
        self._resource_builders: Dict[str, Callable] = {}
        self._tool_builders: Dict[str, Callable] = {}
        self._model_provider: Optional[Any] = None
        self._default_llm: Optional[str] = None

    def register_resource_builder(self, resource_type: str, builder: Callable):
        self._resource_builders[resource_type] = builder
        logger.info(f"[V2Builder] 注册资源构建器: {resource_type}")

    def register_tool_builder(self, tool_name: str, builder: Callable):
        self._tool_builders[tool_name] = builder
        logger.info(f"[V2Builder] 注册工具构建器: {tool_name}")

    def set_model_provider(self, provider: Any, default_llm: str = None):
        self._model_provider = provider
        self._default_llm = default_llm

    async def build_from_app(self, app: Any) -> AgentBuildResult:
        from derisk.agent.resource.app import AppResource

        if isinstance(app, AppResource):
            return await self._build_from_app_resource(app)

        if hasattr(app, "resources"):
            return await self._build_from_app_dict(app)

        raise ValueError(f"不支持的 App 类型: {type(app)}")

    async def build_from_config(self, config: Dict[str, Any]) -> AgentBuildResult:
        agent_name = config.get("name", "primary")
        agent_mode = config.get("mode", "primary")
        max_steps = config.get("max_steps", 20)

        permission_config = config.get("permission", {})
        resources_config = config.get("resources", [])
        tools_config = config.get("tools", [])
        model_config = config.get("model", {})

        agent_info = self._create_agent_info(
            name=agent_name,
            mode=agent_mode,
            max_steps=max_steps,
            permission=permission_config,
        )

        tools = await self._build_tools(tools_config)
        resources = await self._build_resources(resources_config)

        agent = await self._create_agent(
            agent_info=agent_info,
            tools=tools,
            resources=resources,
            model_config=model_config,
        )

        return AgentBuildResult(
            agent=agent,
            agent_info=agent_info,
            tools=tools,
            resources=resources,
            metadata={"config": config},
        )

    async def _build_from_app_resource(self, app: Any) -> AgentBuildResult:
        from ..agent_info import AgentInfo, AgentMode, PermissionRuleset

        agent_name = getattr(app, "name", "primary")
        agent_desc = getattr(app, "description", "")

        permission = PermissionRuleset.default()
        if hasattr(app, "permission"):
            permission = self._build_permission(app.permission)

        agent_info = AgentInfo(
            name=agent_name,
            mode=AgentMode.PRIMARY,
            max_steps=getattr(app, "max_steps", 20),
            permission=permission,
            description=agent_desc,
        )

        tools = {}
        resources = {}

        if hasattr(app, "resources") and app.resources:
            for resource in app.resources:
                built = await self._build_single_resource(resource)
                if built:
                    name = getattr(resource, "name", str(type(resource)))
                    if self._is_tool_resource(resource):
                        tools[name] = built
                    else:
                        resources[name] = built

        agent = await self._create_agent(
            agent_info=agent_info,
            tools=tools,
            resources=resources,
        )

        return AgentBuildResult(
            agent=agent,
            agent_info=agent_info,
            tools=tools,
            resources=resources,
        )

    async def _build_from_app_dict(self, app: Any) -> AgentBuildResult:
        return await self.build_from_config(
            {
                "name": getattr(app, "name", "primary"),
                "resources": getattr(app, "resources", []),
            }
        )

    def _create_agent_info(
        self,
        name: str,
        mode: str,
        max_steps: int,
        permission: Dict[str, Any],
    ) -> Any:
        from ..agent_info import AgentInfo, AgentMode, PermissionRuleset

        mode_map = {
            "primary": AgentMode.PRIMARY,
            "planner": AgentMode.PLANNER,
            "worker": AgentMode.WORKER,
        }

        ruleset = (
            PermissionRuleset.from_dict(permission)
            if permission
            else PermissionRuleset.default()
        )

        return AgentInfo(
            name=name,
            mode=mode_map.get(mode, AgentMode.PRIMARY),
            max_steps=max_steps,
            permission=ruleset,
        )

    async def _build_tools(self, tools_config: List[Any]) -> Dict[str, Any]:
        from derisk.agent.tools import tool_registry, BashTool

        tools = {}

        for tool_config in tools_config:
            if isinstance(tool_config, str):
                tool = tool_registry.get(tool_config)
                if tool:
                    tools[tool_config] = tool
            elif isinstance(tool_config, dict):
                tool_name = tool_config.get("name")
                if tool_name in self._tool_builders:
                    tool = self._tool_builders[tool_name](tool_config)
                    tools[tool_name] = tool
                elif tool_name in tool_registry._tools:
                    tools[tool_name] = tool_registry.get(tool_name)

        if "bash" not in tools:
            tools["bash"] = BashTool()

        return tools

    async def _build_resources(self, resources_config: List[Any]) -> Dict[str, Any]:
        resources = {}

        for resource_config in resources_config:
            resource = await self._build_single_resource(resource_config)
            if resource:
                name = getattr(resource_config, "name", str(uuid.uuid4().hex[:8]))
                resources[name] = resource

        return resources

    async def _build_single_resource(self, resource_config: Any) -> Optional[Any]:
        if hasattr(resource_config, "type"):
            resource_type = resource_config.type
            if isinstance(resource_type, str):
                pass
            else:
                resource_type = (
                    resource_type.value
                    if hasattr(resource_type, "value")
                    else str(resource_type)
                )

            if resource_type in self._resource_builders:
                return self._resource_builders[resource_type](resource_config)

        if hasattr(resource_config, "execute"):
            return resource_config

        return None

    def _is_tool_resource(self, resource: Any) -> bool:
        from derisk.agent.resource import BaseTool

        return isinstance(resource, BaseTool)

    def _build_permission(self, permission_config: Any) -> Any:
        from ..permission import PermissionRuleset

        if isinstance(permission_config, PermissionRuleset):
            return permission_config

        if isinstance(permission_config, dict):
            return PermissionRuleset.from_dict(permission_config)

        return PermissionRuleset.default()

    async def _create_agent(
        self,
        agent_info: Any,
        tools: Dict[str, Any],
        resources: Dict[str, Any],
        model_config: Optional[Dict] = None,
    ) -> Any:
        from derisk.agent.core_v2_integration.agent_impl import V2PDCAAgent

        agent = V2PDCAAgent(
            info=agent_info,
            tools=tools,
            resources=resources,
            model_provider=self._model_provider,
            model_config=model_config or {},
        )

        return agent


import uuid
