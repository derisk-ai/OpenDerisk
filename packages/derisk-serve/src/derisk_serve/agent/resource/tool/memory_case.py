"""MemoryCaseToolPack - 将案例记忆 MCP 工具注册为 Agent 可调用的 ToolPack.

让任何 Agent（BAIZE 等）通过资源配置接入案例记忆。
自动从 Agent 上下文注入 scope（app_code, environment），
LLM 无需关心 scope 参数，每个 Agent 只能看到自己 scope 的案例。
"""

import json
import logging
from typing import Any, Dict, List, Optional, Type

from derisk.agent.resource import PackResourceParameters, ToolPack
from derisk.util import ParameterDescription
from derisk.util.i18n_utils import _

from derisk_serve.mcp.memory_case import BUILTIN_MEMORY_MCP, MemoryCasePluginService

logger = logging.getLogger(__name__)

# 线程局部变量，用于在工具调用时传递 app_code
import threading

_scope_context = threading.local()


def set_memory_case_scope(app_code: str, conv_id: Optional[str] = None):
    """在 Agent 构建时设置当前 scope 上下文。

    由 agent_chat / core_v2_adapter 在构建 agent 后调用，
    确保 MemoryCaseToolPack 能自动获取 app_code。
    """
    _scope_context.app_code = app_code
    _scope_context.conv_id = conv_id


def get_memory_case_scope() -> Dict[str, str]:
    """获取当前 scope 上下文。"""
    return {
        "app_code": getattr(_scope_context, "app_code", "default"),
        "conv_id": getattr(_scope_context, "conv_id", None),
    }


class MemoryCaseResourceParameters(PackResourceParameters):
    """案例记忆 MCP 资源参数."""

    @classmethod
    def _resource_version(cls) -> str:
        return "v1"


class MemoryCaseToolPack(ToolPack):
    """案例记忆 MCP 工具包.

    直接包装 MemoryCasePluginService 的 4 个工具为 Agent 可调用的工具，
    不依赖 SSE 通道，适合内置 MCP 插件。

    使用方式:
        1. 在 Agent 资源配置中添加 type="tool(memory_case)" 的资源
        2. 或通过 core_v2_adapter 在 Agent 创建时自动注入

    scope 自动注入:
        - app_code: 从 thread-local scope context 获取（由 agent_chat 设置）
        - environment: 默认 "default"
        - conv_id: 从 thread-local scope context 获取
        LLM 调用工具时无需手动传递 scope

    工具列表:
        - memory_case_search: 按范围和查询搜索相似案例
        - memory_case_upsert: 创建或更新案例
        - memory_case_feedback: 对案例进行反馈（调整置信度/生命周期）
        - memory_case_render: 将案例渲染为 Markdown
    """

    def __init__(self, system_app=None, **kwargs):
        self._system_app = system_app
        self._plugin: Optional[MemoryCasePluginService] = None
        self._initialized = False
        # ResourceManager may pass 'name' in kwargs via from_dict; avoid duplicate
        kwargs.setdefault("name", BUILTIN_MEMORY_MCP)
        super().__init__([], **kwargs)

    def _ensure_plugin(self) -> MemoryCasePluginService:
        if self._plugin is not None:
            return self._plugin

        if self._system_app is None:
            from derisk._private.config import Config
            self._system_app = Config().SYSTEM_APP

        from derisk_serve.mcp.service.service import Service as McpService
        mcp_service = McpService.get_instance(self._system_app)
        if mcp_service and hasattr(mcp_service, "_memory_plugin"):
            self._plugin = mcp_service._memory_plugin
        else:
            self._plugin = MemoryCasePluginService(self._system_app)

        return self._plugin

    def _resolve_scope(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """从工具调用参数或线程上下文自动解析 scope.

        优先级：
        1. LLM 显式传入的 scope 中的字段
        2. thread-local scope context（由 agent_chat 设置的 app_code/conv_id）
        3. 兜底默认值 "default"
        """
        scope = kwargs.get("scope") or {}
        ctx = get_memory_case_scope()

        # 自动填充 scope 字段（不覆盖 LLM 已传的值）
        scope.setdefault("app_code", ctx["app_code"])
        scope.setdefault("environment", "default")
        conv_id = scope.get("conv_id") or ctx.get("conv_id")
        if conv_id:
            scope.setdefault("conv_id", conv_id)

        return scope

    async def preload_resource(self):
        if self._initialized:
            return

        plugin = self._ensure_plugin()
        if not plugin.enabled:
            logger.warning("[MemoryCaseToolPack] memory_case plugin is disabled")
            self._initialized = True
            return

        for tool_spec in plugin.list_tools():
            self.add_command(
                command_label=tool_spec.description,
                command_name=tool_spec.name,
                args=self._convert_schema(tool_spec.inputSchema),
                function=self._make_caller(tool_spec.name),
            )

        self._initialized = True
        logger.info(
            "[MemoryCaseToolPack] loaded %d tools from memory_case",
            len(self._resources),
        )

    @staticmethod
    def _convert_schema(input_schema: Dict[str, Any]) -> Dict[str, Any]:
        args = {}
        props = input_schema.get("properties", {})
        required = set(input_schema.get("required", []))
        for name, schema in props.items():
            args[name] = {
                "name": name,
                "type": schema.get("type", "string"),
                "description": schema.get("description", ""),
                "required": name in required,
            }
        return args

    def _make_caller(self, tool_name: str):
        pack = self

        async def _call(**kwargs):
            plugin = pack._ensure_plugin()

            # 自动注入 scope（search 和 upsert 需要）
            if tool_name in ("memory_case_search", "memory_case_upsert"):
                scope = pack._resolve_scope(kwargs)
                kwargs["scope"] = scope

                # upsert: 确保案例中也包含 scope 信息
                if tool_name == "memory_case_upsert" and "case" in kwargs:
                    case_data = kwargs["case"]
                    if isinstance(case_data, dict):
                        case_data.setdefault("app_code", scope.get("app_code", "default"))
                        case_data.setdefault("environment", scope.get("environment", "default"))
                        if scope.get("conv_id"):
                            case_data.setdefault("source_conv_id", scope["conv_id"])

            result = await plugin.call_tool(tool_name, kwargs)
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False)
            return str(result)

        _call.__name__ = tool_name
        _call.__qualname__ = f"MemoryCaseToolPack.{tool_name}"
        return _call

    @classmethod
    def type(cls):
        return "tool(memory_case)"

    @classmethod
    def type_alias(cls) -> str:
        return "tool(memory_case)"

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[MemoryCaseResourceParameters]:
        return MemoryCaseResourceParameters