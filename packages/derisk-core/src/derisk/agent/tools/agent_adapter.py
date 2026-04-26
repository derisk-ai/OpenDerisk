"""
AgentToolAdapter - Agent工具适配器

提供Core和CoreV2 Agent与新工具框架的集成适配：
- Core Agent适配
- CoreV2 Agent适配
- 工具执行统一接口
"""

from typing import Dict, Any, Optional, List, Union
import logging
import asyncio

from .base import ToolBase, ToolCategory, ToolSource, ToolRiskLevel
from .metadata import ToolMetadata
from .context import ToolContext
from .result import ToolResult
from .registry import ToolRegistry, tool_registry
from .resource_manager import ToolResource, tool_resource_manager
from .authorization_middleware import (
    ToolAuthorizationMiddleware,
    AuthorizationContext,
    AuthorizationCheckResult,
)

logger = logging.getLogger(__name__)


class AgentToolAdapter:
    """
    Agent工具适配器

    提供Agent与新工具框架的集成接口：
    1. 工具发现和加载
    2. 工具执行（带授权检查）
    3. 权限检查
    4. 结果处理

    使用方式：
        adapter = AgentToolAdapter(agent)

        # 获取可用工具
        tools = adapter.get_available_tools()

        # 执行工具
        result = await adapter.execute_tool("read", {"path": "/tmp/file.txt"})
    """

    def __init__(
        self,
        agent: Any = None,
        registry: ToolRegistry = None,
        tool_ids: List[str] = None,
        interaction_gateway: Optional[Any] = None,
    ):
        """
        初始化适配器

        Args:
            agent: Agent实例（Core或CoreV2）
            registry: 工具注册表
            tool_ids: 可用工具ID列表（用于过滤）
            interaction_gateway: InteractionGateway 实例（用于用户授权交互）
        """
        self._agent = agent
        self._registry = registry or tool_registry
        self._tool_ids = tool_ids
        self._resource_manager = tool_resource_manager

        # 初始化授权中间件
        self._auth_middleware = ToolAuthorizationMiddleware(
            interaction_gateway=interaction_gateway,
        )

        # 同步工具资源
        self._resource_manager.sync_from_registry()

    # === 工具发现 ===

    def get_available_tools(self) -> List[ToolBase]:
        """
        获取Agent可用的工具列表

        Returns:
            List[ToolBase]: 可用工具列表
        """
        all_tools = self._registry.list_all()

        if self._tool_ids:
            return [t for t in all_tools if t.name in self._tool_ids]

        return all_tools

    def get_tool(self, tool_name: str) -> Optional[ToolBase]:
        """获取指定工具"""
        return self._registry.get(tool_name)

    def get_tool_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        """获取工具元数据"""
        tool = self.get_tool(tool_name)
        return tool.metadata if tool else None

    def get_tools_for_llm(self) -> List[Dict[str, Any]]:
        """
        获取给LLM使用的工具列表

        Returns:
            List[Dict]: OpenAI格式的工具列表
        """
        tools = self.get_available_tools()
        return [t.to_openai_tool() for t in tools]

    # === 工具执行 ===

    async def execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: Optional[Union[ToolContext, Dict[str, Any]]] = None,
        skip_authorization: bool = False,
    ) -> ToolResult:
        """
        执行工具（带授权检查）

        Args:
            tool_name: 工具名称
            args: 工具参数
            context: 执行上下文
            skip_authorization: 是否跳过授权检查（用于内部调用）

        Returns:
            ToolResult: 执行结果
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult.fail(
                error=f"Tool not found: {tool_name}", tool_name=tool_name
            )

        # 构建上下文
        tool_context = self._build_context(context)

        # 验证参数
        if not tool.validate_args(args):
            return ToolResult.fail(
                error="Invalid arguments",
                tool_name=tool_name,
                error_code="INVALID_ARGS",
            )

        # 预处理
        try:
            args = await tool.pre_execute(args)
        except Exception as e:
            logger.error(
                f"[AgentToolAdapter] Pre-execute failed: {tool_name}, error: {e}"
            )
            return ToolResult.fail(
                error=f"Pre-execute failed: {str(e)}", tool_name=tool_name
            )

        # 执行（带授权检查）
        if skip_authorization:
            # 跳过授权，直接执行
            return await self._do_execute(tool, args, tool_context)

        # 使用授权中间件执行
        try:
            result = await self._auth_middleware.execute_with_auth(
                tool=tool,
                args=args,
                context=tool_context,
                execute_fn=self._do_execute,
            )
            return result

        except Exception as e:
            logger.error(
                f"[AgentToolAdapter] Authorization/execution failed: {tool_name}, error: {e}"
            )
            return ToolResult.fail(error=str(e), tool_name=tool_name)

    async def _do_execute(
        self,
        tool: ToolBase,
        args: Dict[str, Any],
        context: Optional[ToolContext],
    ) -> ToolResult:
        """
        实际执行工具（内部方法）

        Args:
            tool: 工具实例
            args: 工具参数
            context: 工具上下文

        Returns:
            ToolResult: 执行结果
        """
        try:
            # 执行
            result = await tool.execute(args, context)

            # 后处理
            result = await tool.post_execute(result)

            # 更新统计
            tool_id = f"{tool.metadata.source.value}_{tool.metadata.name}"
            self._resource_manager.increment_call_count(tool_id, result.success)

            return result

        except asyncio.TimeoutError:
            return ToolResult.timeout(tool.name, tool.metadata.timeout)
        except Exception as e:
            logger.error(
                f"[AgentToolAdapter] Tool execution failed: {tool.name}, error: {e}"
            )
            return ToolResult.fail(error=str(e), tool_name=tool.name)

    def set_interaction_gateway(self, gateway: Any):
        """
        设置 InteractionGateway（用于用户授权交互）

        Args:
            gateway: InteractionGateway 实例
        """
        self._auth_middleware._interaction_gateway = gateway
        logger.info("[AgentToolAdapter] InteractionGateway set for authorization")

    def clear_authorization_cache(self, session_id: Optional[str] = None):
        """清除授权缓存"""
        self._auth_middleware.clear_session_cache(session_id)

    # === 上下文构建 ===

    def _build_context(
        self, context: Optional[Union[ToolContext, Dict[str, Any]]] = None
    ) -> ToolContext:
        """构建工具上下文"""
        if isinstance(context, ToolContext):
            return context

        if context is None:
            context = {}

        # 从Agent提取上下文信息
        if self._agent:
            context.setdefault("agent_id", getattr(self._agent, "agent_id", None))
            context.setdefault("agent_name", getattr(self._agent, "name", None))

            # Core Agent特有字段
            if hasattr(self._agent, "agent_context"):
                agent_ctx = self._agent.agent_context
                context.setdefault(
                    "conversation_id", getattr(agent_ctx, "conv_id", None)
                )
                context.setdefault("user_id", getattr(agent_ctx, "user_id", None))

                # 提取用户上下文信息（身份、角色、权限等）
                extra = getattr(agent_ctx, "extra", None)
                if extra and isinstance(extra, dict) and "user_context" in extra:
                    context.setdefault("user_context", extra["user_context"])

            # CoreV2 Agent特有字段
            if hasattr(self._agent, "context"):
                agent_ctx = self._agent.context
                context.setdefault(
                    "conversation_id", getattr(agent_ctx, "conversation_id", None)
                )

            # 注入沙箱管理器（用于沙箱工具）
            if hasattr(self._agent, "sandbox_manager"):
                sandbox_manager = self._agent.sandbox_manager
                if sandbox_manager is not None:
                    # 将 sandbox_manager 注入到 config 中，供 SandboxToolBase 使用
                    config = context.setdefault("config", {})
                    if isinstance(config, dict):
                        config["sandbox_manager"] = sandbox_manager

        return ToolContext(**context)

    # === Agent特定适配 ===

    def adapt_for_core(self) -> "CoreToolAdapter":
        """适配Core Agent"""
        return CoreToolAdapter(self)

    def adapt_for_core_v2(self) -> "CoreV2ToolAdapter":
        """适配CoreV2 Agent"""
        return CoreV2ToolAdapter(self)


class CoreToolAdapter:
    """
    Core Agent工具适配器

    提供Core Agent与工具框架的桥接
    """

    def __init__(self, adapter: AgentToolAdapter):
        self._adapter = adapter

    def to_resource(self) -> Dict[str, Any]:
        """
        转换为Core资源格式

        Returns:
            Dict: Core Agent的资源格式
        """
        tools = self._adapter.get_available_tools()

        resources = []
        for tool in tools:
            resources.append(
                {
                    "name": tool.metadata.name,
                    "description": tool.metadata.description,
                    "parameters": tool.parameters,
                    "type": "function",
                }
            )

        return {"tools": resources}

    def to_action_format(self) -> List[Dict[str, Any]]:
        """
        转换为Core Action格式

        Returns:
            List[Dict]: Core Agent的Action格式
        """
        tools = self._adapter.get_available_tools()

        actions = []
        for tool in tools:
            actions.append(
                {
                    "action": tool.metadata.name,
                    "description": tool.metadata.description,
                    "args": tool.parameters,
                }
            )

        return actions

    async def execute_for_core(
        self, action_input: Dict[str, Any], agent_context: Any = None
    ) -> Dict[str, Any]:
        """
        为Core Agent执行工具

        Args:
            action_input: Core Agent的Action输入
            agent_context: Core Agent的上下文

        Returns:
            Dict: Core Agent的执行结果格式
        """
        tool_name = action_input.get("tool_name") or action_input.get("action")
        args = action_input.get("args", {})

        context = {}
        if agent_context:
            context["conversation_id"] = getattr(agent_context, "conv_id", None)
            context["user_id"] = getattr(agent_context, "user_id", None)

            # 注入 sandbox_client（用于 cwd 授权检查）
            sandbox_manager = getattr(agent_context, "sandbox_manager", None)
            if sandbox_manager:
                context["sandbox_client"] = getattr(sandbox_manager, "client", None)
                if not context["sandbox_client"]:
                    context["sandbox_client"] = getattr(
                        sandbox_manager, "get_client", lambda: None
                    )()

        result = await self._adapter.execute_tool(tool_name, args, context)

        return {
            "is_exe_success": result.success,
            "content": result.output,
            "error": result.error,
            "metadata": result.metadata,
        }


class CoreV2ToolAdapter:
    """
    CoreV2 Agent工具适配器

    提供CoreV2 Agent与工具框架的桥接
    """

    def __init__(self, adapter: AgentToolAdapter):
        self._adapter = adapter

    def to_harness_format(self) -> Dict[str, Any]:
        """
        转换为CoreV2 Harness格式

        Returns:
            Dict: CoreV2 Harness的工具配置
        """
        tools = self._adapter.get_available_tools()

        return {
            "tools": [t.to_openai_tool() for t in tools],
            "tool_configs": {
                t.metadata.name: {
                    "timeout": t.metadata.timeout,
                    "risk_level": t.metadata.risk_level.value,
                    "requires_permission": t.metadata.requires_permission,
                }
                for t in tools
            },
        }

    async def execute_for_core_v2(
        self, tool_call: Dict[str, Any], execution_context: Any = None
    ) -> Dict[str, Any]:
        """
        为CoreV2 Agent执行工具

        Args:
            tool_call: 工具调用信息
            execution_context: CoreV2执行上下文

        Returns:
            Dict: CoreV2工具执行结果
        """
        tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name")
        args = tool_call.get("args") or tool_call.get("function", {}).get(
            "arguments", {}
        )

        if isinstance(args, str):
            import json

            args = json.loads(args)

        context = {}
        if execution_context:
            context["agent_id"] = getattr(execution_context, "agent_id", None)
            context["conversation_id"] = getattr(
                execution_context, "conversation_id", None
            )
            context["trace_id"] = getattr(execution_context, "trace_id", None)

            # 注入 sandbox_client（用于 cwd 授权检查）
            sandbox_manager = getattr(execution_context, "sandbox_manager", None)
            if sandbox_manager:
                context["sandbox_client"] = getattr(sandbox_manager, "client", None)
                if not context["sandbox_client"]:
                    context["sandbox_client"] = getattr(
                        sandbox_manager, "get_client", lambda: None
                    )()

        result = await self._adapter.execute_tool(tool_name, args, context)

        return {
            "tool_call_id": tool_call.get("id"),
            "role": "tool",
            "name": tool_name,
            "content": str(result.output)
            if result.success
            else f"Error: {result.error}",
            "success": result.success,
            "metadata": result.metadata,
        }


# === 便捷函数 ===


def create_tool_adapter_for_agent(
    agent: Any,
    tool_ids: List[str] = None,
    interaction_gateway: Optional[Any] = None,
) -> AgentToolAdapter:
    """
    为Agent创建工具适配器

    Args:
        agent: Agent实例
        tool_ids: 可用工具ID列表
        interaction_gateway: InteractionGateway 实例（用于用户授权交互）

    Returns:
        AgentToolAdapter: 工具适配器
    """
    return AgentToolAdapter(
        agent=agent,
        tool_ids=tool_ids,
        interaction_gateway=interaction_gateway,
    )


def get_tools_for_agent(agent_type: str = "core") -> List[Dict[str, Any]]:
    """
    获取Agent可用的工具列表

    Args:
        agent_type: Agent类型 (core/core_v2)

    Returns:
        List[Dict]: 工具列表
    """
    adapter = AgentToolAdapter()
    return adapter.get_tools_for_llm()
