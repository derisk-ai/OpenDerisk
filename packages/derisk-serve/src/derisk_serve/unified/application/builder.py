"""
统一应用构建器实现
"""

import logging
from typing import Any, Dict, List, Optional

from .models import UnifiedResource, UnifiedAppInstance

logger = logging.getLogger(__name__)


class UnifiedAppBuilder:
    """
    统一应用构建器

    核心职责：
    1. 统一应用配置加载
    2. 统一资源解析和转换
    3. 自动适配V1/V2 Agent构建
    """

    def __init__(self, system_app: Any = None):
        self._system_app = system_app
        self._app_cache: Dict[str, UnifiedAppInstance] = {}

    async def build_app(
        self,
        app_code: str,
        agent_version: str = "auto",
        use_cache: bool = True,
        **kwargs,
    ) -> UnifiedAppInstance:
        """
        统一的应用构建入口

        Args:
            app_code: 应用代码
            agent_version: v1/v2/auto
            use_cache: 是否使用缓存

        Returns:
            UnifiedAppInstance: 统一应用实例
        """
        if use_cache and app_code in self._app_cache:
            logger.info(f"[UnifiedAppBuilder] 使用缓存应用实例: {app_code}")
            return self._app_cache[app_code]

        logger.info(
            f"[UnifiedAppBuilder] 开始构建应用: {app_code}, version={agent_version}"
        )

        gpts_app = await self._load_app_config(app_code)

        if agent_version == "auto":
            agent_version = self._detect_agent_version(gpts_app)
            logger.info(f"[UnifiedAppBuilder] 自动检测到Agent版本: {agent_version}")

        if agent_version == "v2":
            instance = await self._build_v2_app(gpts_app, **kwargs)
        else:
            instance = await self._build_v1_app(gpts_app, **kwargs)

        if use_cache:
            self._app_cache[app_code] = instance

        logger.info(
            f"[UnifiedAppBuilder] 应用构建完成: {app_code}, type={type(instance.agent).__name__}"
        )
        return instance

    async def _load_app_config(self, app_code: str) -> Any:
        """加载应用配置"""
        try:
            from derisk_serve.building.app.config import SERVE_SERVICE_COMPONENT_NAME
            from derisk_serve.building.app.service.service import Service
            from derisk._private.config import Config

            CFG = Config()
            app_service = CFG.SYSTEM_APP.get_component(
                SERVE_SERVICE_COMPONENT_NAME, Service
            )
            gpts_app = await app_service.app_detail(
                app_code, specify_config_code=None, building_mode=False
            )
            return gpts_app
        except Exception as e:
            logger.error(f"[UnifiedAppBuilder] 加载应用配置失败: {app_code}, error={e}")
            raise

    def _detect_agent_version(self, gpts_app: Any) -> str:
        """检测Agent版本"""
        if hasattr(gpts_app, "agent_version"):
            return gpts_app.agent_version or "v2"

        if hasattr(gpts_app, "team_context"):
            team_context = gpts_app.team_context
            if team_context:
                if hasattr(team_context, "agent_version"):
                    return team_context.agent_version
                if isinstance(team_context, dict):
                    return team_context.get("agent_version", "v2")

        return "v2"

    async def _build_v2_app(self, gpts_app: Any, **kwargs) -> UnifiedAppInstance:
        """
        构建V2应用实例

        关键改造点：
        1. 统一资源解析
        2. 统一工具绑定
        3. 创建V2 Agent
        """
        app_code = gpts_app.app_code
        app_name = gpts_app.app_name

        resources = await self._parse_resources(getattr(gpts_app, "resources", []))

        tools = await self._build_v2_tools(resources)

        agent = await self._create_v2_agent(
            app_code=app_code,
            gpts_app=gpts_app,
            tools=tools,
            resources=resources,
            **kwargs,
        )

        return UnifiedAppInstance(
            app_code=app_code,
            app_name=app_name,
            agent=agent,
            version="v2",
            resources=resources,
            config=self._extract_app_config(gpts_app),
            metadata={
                "team_mode": getattr(gpts_app, "team_mode", "single_agent"),
                "llm_strategy": getattr(gpts_app, "llm_strategy", None),
            },
        )

    async def _build_v1_app(self, gpts_app: Any, **kwargs) -> UnifiedAppInstance:
        """
        构建V1应用实例

        保持原有构建逻辑，但统一接口
        """
        try:
            from derisk_serve.agent.agents.chat.agent_chat import AgentChat

            app_code = gpts_app.app_code
            app_name = gpts_app.app_name

            resources = await self._parse_resources(getattr(gpts_app, "resources", []))

            agent = AgentChat(app_code=app_code, gpts_app=gpts_app, **kwargs)

            return UnifiedAppInstance(
                app_code=app_code,
                app_name=app_name,
                agent=agent,
                version="v1",
                resources=resources,
                config=self._extract_app_config(gpts_app),
            )
        except Exception as e:
            logger.error(f"[UnifiedAppBuilder] 构建V1应用失败: {e}")
            raise

    async def _parse_resources(self, raw_resources: List[Any]) -> List[UnifiedResource]:
        """
        统一资源解析

        将各种格式的资源统一转换为UnifiedResource
        """
        resources = []

        for res in raw_resources or []:
            try:
                unified_res = self._normalize_resource(res)
                if unified_res:
                    resources.append(unified_res)
            except Exception as e:
                logger.warning(f"[UnifiedAppBuilder] 资源解析失败: {e}")
                continue

        return resources

    def _normalize_resource(self, res: Any) -> Optional[UnifiedResource]:
        """
        标准化单个资源

        支持多种资源格式：
        1. Resource对象（有type、name属性）
        2. 字典格式
        3. V1/V2工具对象
        """
        if hasattr(res, "type") and hasattr(res, "name"):
            return UnifiedResource(
                type=res.type,
                name=res.name,
                config=getattr(res, "value", {}) or {},
                version=getattr(res, "version", "v2"),
                metadata={
                    "resource_id": getattr(res, "id", None),
                    "description": getattr(res, "description", ""),
                },
            )

        if isinstance(res, dict):
            return UnifiedResource(
                type=res.get("type", "unknown"),
                name=res.get("name", "unnamed"),
                config=res.get("config", res.get("value", {})),
                version=res.get("version", "v2"),
            )

        if hasattr(res, "info"):
            from derisk.agent.tools.base import ToolBase

            if isinstance(res, ToolBase):
                return UnifiedResource(
                    type="tool",
                    name=res.info.name,
                    config={"tool_instance": res},
                    version="v2",
                )

        return None

    async def _build_v2_tools(self, resources: List[UnifiedResource]) -> Dict[str, Any]:
        """
        构建V2工具集

        从资源列表中提取并构建工具
        """
        tools = {}

        for res in resources:
            if res.type == "tool":
                tool = await self._create_tool_from_resource(res)
                if tool:
                    tools[res.name] = tool

        return tools

    async def _create_tool_from_resource(
        self, resource: UnifiedResource
    ) -> Optional[Any]:
        """从资源创建工具实例"""
        try:
            if "tool_instance" in resource.config:
                return resource.config["tool_instance"]

            tool_name = resource.name
            tool_config = resource.config

            if tool_name in ["bash", "python", "read", "write", "edit"]:
                from derisk.agent.tools import tool_registry

                return tool_registry.get(tool_name)

            if tool_name.startswith("mcp_"):
                from derisk.agent.tools.builtin.mcp import MCPToolAdapter

                return MCPToolAdapter(mcp_tool=tool_config)

            return None
        except Exception as e:
            logger.error(
                f"[UnifiedAppBuilder] 创建工具失败: {resource.name}, error={e}"
            )
            return None

    async def _create_v2_agent(
        self,
        app_code: str,
        gpts_app: Any,
        tools: Dict[str, Any],
        resources: List[UnifiedResource],
        **kwargs,
    ) -> Any:
        """
        创建V2 Agent实例

        关键改造点：
        1. 使用统一的create_v2_agent接口
        2. 传递标准化的工具和资源
        """
        from derisk.agent.core_v2.integration import create_v2_agent

        team_context = getattr(gpts_app, "team_context", None)
        agent_name = "default"
        mode = "primary"

        if team_context:
            if hasattr(team_context, "agent_name"):
                agent_name = team_context.agent_name
            elif isinstance(team_context, dict):
                agent_name = team_context.get("agent_name", "default")

            if hasattr(team_context, "team_mode"):
                mode = (
                    "planner" if team_context.team_mode == "multi_agent" else "primary"
                )

        agent = create_v2_agent(
            name=agent_name,
            mode=mode,
            tools=tools,
            resources={
                "knowledge": [r for r in resources if r.type == "knowledge"],
                "skills": [r for r in resources if r.type == "skill"],
                "tools": [r for r in resources if r.type == "tool"],
            },
        )

        return agent

    def _extract_app_config(self, gpts_app: Any) -> Dict[str, Any]:
        """提取应用配置"""
        return {
            "app_code": gpts_app.app_code,
            "app_name": gpts_app.app_name,
            "app_desc": getattr(gpts_app, "app_desc", ""),
            "team_mode": getattr(gpts_app, "team_mode", "single_agent"),
            "language": getattr(gpts_app, "language", "en"),
            "llm_strategy": getattr(gpts_app, "llm_strategy", None),
        }

    def clear_cache(self, app_code: Optional[str] = None):
        """清理缓存"""
        if app_code:
            self._app_cache.pop(app_code, None)
        else:
            self._app_cache.clear()
