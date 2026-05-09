"""MemoryCaseToolPack — register builtin memory_case tools as Agent ToolPack."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any, Dict, Optional, Type

from derisk.agent.resource import PackResourceParameters, ToolPack

from .case_context import (
    KEY_APP_CODE,
    KEY_ENVIRONMENT,
    merge_case_context,
)
from .plugin_resolver import resolve_memory_case_plugin
from .service import BUILTIN_MEMORY_MCP, MemoryCasePluginService

logger = logging.getLogger(__name__)

_scope_app_code: ContextVar[Optional[str]] = ContextVar(
    "memory_case_app_code", default=None
)
_scope_conv_id: ContextVar[Optional[str]] = ContextVar(
    "memory_case_conv_id", default=None
)


def set_memory_case_scope(app_code: str, conv_id: Optional[str] = None) -> None:
    """Set async context scope for memory_case tools (app_code / conv_id).

    Prefer calling ``bind_memory_case_scope_for_agent`` from ``scope_binding`` at
    Agent build time; this function is the low-level setter.
    """
    _scope_app_code.set(app_code)
    _scope_conv_id.set(conv_id)


def get_memory_case_scope() -> Dict[str, Optional[str]]:
    """Return current context scope."""
    app_code = _scope_app_code.get()
    return {
        "app_code": app_code if app_code is not None else "default",
        "conv_id": _scope_conv_id.get(),
    }


def inject_memory_scope(
    tool_name: str, arguments: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Resolve scope from ContextVar and inject into tool arguments.

    Called by both MemoryCaseToolPack._make_caller (Agent ToolPack path) and
    McpService.call_tool (MCP service path) so that scope injection is defined
    once inside the plugin.
    """
    if tool_name not in ("memory_case_search", "memory_case_upsert"):
        return arguments
    args = dict(arguments or {})
    ctx = get_memory_case_scope()
    scope = dict(args.get("scope") or {})
    scope.setdefault("app_code", ctx["app_code"])
    scope.setdefault("environment", "default")
    conv_id = scope.get("conv_id") or ctx.get("conv_id")
    if conv_id:
        scope.setdefault("conv_id", conv_id)
    args["scope"] = scope

    if tool_name == "memory_case_upsert" and "case" in args:
        case_data = dict(args["case"])
        patch: Dict[str, Any] = {
            KEY_APP_CODE: scope.get(KEY_APP_CODE, "default"),
            KEY_ENVIRONMENT: scope.get(KEY_ENVIRONMENT, "default"),
        }
        case_data["metadata"] = merge_case_context(
            case_data.get("metadata"), patch
        )
        if scope.get("conv_id"):
            case_data.setdefault("source_conv_id", scope["conv_id"])
        args["case"] = case_data
    return args


class MemoryCaseResourceParameters(PackResourceParameters):
    """Case-memory MCP resource parameters."""

    @classmethod
    def _resource_version(cls) -> str:
        return "v1"


class MemoryCaseToolPack(ToolPack):
    """ToolPack wrapping ``MemoryCasePluginService`` tools (no SSE)."""

    def __init__(self, system_app=None, **kwargs):
        self._system_app = system_app
        self._plugin: Optional[MemoryCasePluginService] = None
        self._initialized = False
        kwargs.setdefault("name", BUILTIN_MEMORY_MCP)
        super().__init__([], **kwargs)

    def _ensure_plugin(self) -> MemoryCasePluginService:
        if self._plugin is not None:
            return self._plugin

        if self._system_app is None:
            from derisk._private.config import Config

            self._system_app = Config().SYSTEM_APP

        self._plugin = resolve_memory_case_plugin(self._system_app)
        if self._plugin is None:
            logger.error(
                "memory_case plugin is unavailable: "
                "register_memory_case_plugin_resolver was not called "
                "(expected from McpService.init_app)"
            )
            raise RuntimeError(
                "MemoryCasePluginService is not available: "
                "register_memory_case_plugin_resolver was not called"
            )
        return self._plugin

    async def preload_resource(self) -> None:
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
        args: Dict[str, Any] = {}
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
            kwargs = inject_memory_scope(tool_name, kwargs) or kwargs
            result = await plugin.call_tool(tool_name, kwargs)
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False)
            return str(result)

        _call.__name__ = tool_name
        _call.__qualname__ = f"MemoryCaseToolPack.{tool_name}"
        return _call

    @classmethod
    def type(cls) -> str:
        return "tool(memory_case)"

    @classmethod
    def type_alias(cls) -> str:
        return "tool(memory_case)"

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[MemoryCaseResourceParameters]:
        return MemoryCaseResourceParameters
