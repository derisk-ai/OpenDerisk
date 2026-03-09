"""
Tool Decorators Compatibility Layer - 工具装饰器兼容层

将旧的装饰器系统适配到统一工具框架:
- @tool / @derisk_tool -> 适配到统一 ToolBase
- @system_tool -> 系统工具
- @sandbox_tool -> 沙箱工具

这个兼容层允许旧代码继续工作，同时内部使用统一框架。
"""

from typing import Callable, Optional, Dict, Any, List, Union, Type
from functools import wraps
import asyncio
import inspect
import logging

from .base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from .metadata import ToolMetadata
from .result import ToolResult
from .context import ToolContext
from .registry import tool_registry

logger = logging.getLogger(__name__)


def tool(
    *decorator_args: Union[str, Callable],
    description: Optional[str] = None,
    args: Optional[Dict[str, Any]] = None,
    args_schema: Optional[Type] = None,
    ask_user: Optional[bool] = False,
    category: Optional[ToolCategory] = None,
    risk_level: Optional[ToolRiskLevel] = None,
    source: Optional[ToolSource] = None,
    tags: Optional[List[str]] = None,
    timeout: int = 60,
    auto_register: bool = True,
) -> Callable[..., Any]:
    """
    Unified tool decorator - 统一工具装饰器

    Creates a tool from a function and registers it with the unified framework.

    Usage:
        @tool
        def my_func(): ...

        @tool("tool_name")
        def my_func(): ...

        @tool("tool_name", description="My tool")
        def my_func(): ...

        @tool(description="My tool", category=ToolCategory.FILE_SYSTEM)
        def my_func(): ...
    """

    def _create_tool(name: str, func: Callable):
        # Parse description from docstring if not provided
        tool_description = description
        if not tool_description and func.__doc__:
            tool_description = func.__doc__.strip().split("\n")[0]
        if not tool_description:
            tool_description = f"Tool: {name}"

        # Parse parameters
        parameters = args or {}
        if args_schema:
            parameters = _parse_args_from_schema(args_schema)

        # Determine category
        tool_category = category or ToolCategory.UTILITY
        tool_risk = risk_level or ToolRiskLevel.LOW
        tool_source = source or ToolSource.USER

        # Create a unified tool class
        class UnifiedFunctionTool(ToolBase):
            def __init__(self):
                self._func = func
                self._is_async = asyncio.iscoroutinefunction(func)
                self._ask_user = ask_user
                super().__init__()

            def _define_metadata(self) -> ToolMetadata:
                return ToolMetadata(
                    name=name,
                    display_name=name.replace("_", " ").title(),
                    description=tool_description,
                    category=tool_category,
                    risk_level=tool_risk,
                    source=tool_source,
                    requires_permission=ask_user,
                    tags=tags or [],
                    timeout=timeout,
                )

            def _define_parameters(self) -> Dict[str, Any]:
                if parameters:
                    return _build_parameter_schema(parameters)
                return _infer_parameters(func)

            async def execute(
                self, args: Dict[str, Any], context: Optional[ToolContext] = None
            ) -> ToolResult:
                try:
                    # Prepare kwargs
                    kwargs = dict(args)

                    # Add context if function accepts it
                    sig = inspect.signature(self._func)
                    if "context" in sig.parameters:
                        kwargs["context"] = context

                    # Execute
                    if self._is_async:
                        result = await self._func(**kwargs)
                    else:
                        result = self._func(**kwargs)

                    # Wrap result
                    if isinstance(result, ToolResult):
                        return result

                    return ToolResult(
                        success=True,
                        output=str(result) if result is not None else "",
                        tool_name=self.name,
                    )

                except Exception as e:
                    logger.error(f"[{name}] Tool execution failed: {e}")
                    return ToolResult(
                        success=False, output="", error=str(e), tool_name=self.name
                    )

        # Create instance
        tool_instance = UnifiedFunctionTool()

        # Auto register
        if auto_register:
            tool_registry.register(tool_instance)
            logger.debug(f"[ToolDecorator] Registered tool: {name}")

        # Store reference
        tool_instance._original_func = func

        return tool_instance

    def _create_decorator(name: str):
        def decorator(func: Callable):
            tool_instance = _create_tool(name, func)

            @wraps(func)
            def sync_wrapper(*f_args, **kwargs):
                return func(*f_args, **kwargs)

            @wraps(func)
            async def async_wrapper(*f_args, **kwargs):
                return await func(*f_args, **kwargs)

            wrapper = (
                async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
            )
            wrapper._tool = tool_instance
            wrapper._is_derisk_tool = True
            # Set DERISK_TOOL_IDENTIFIER for backward compatibility with _is_function_tool
            setattr(wrapper, "derisk_tool", True)

            return wrapper

        return decorator

    # Handle different decorator usage patterns
    if len(decorator_args) == 1 and callable(decorator_args[0]):
        # @tool (no arguments)
        func = decorator_args[0]
        return _create_decorator(func.__name__)(func)

    elif len(decorator_args) == 1 and isinstance(decorator_args[0], str):
        # @tool("name")
        return _create_decorator(decorator_args[0])

    elif (
        len(decorator_args) == 2
        and isinstance(decorator_args[0], str)
        and callable(decorator_args[1])
    ):
        # @tool("name", description="...")
        name, func = decorator_args
        return _create_decorator(name)(func)

    elif len(decorator_args) == 0:
        # @tool(description="...", ...)
        def partial_decorator(func: Callable):
            return _create_decorator(func.__name__)(func)

        return partial_decorator

    else:
        raise ValueError("Invalid @tool usage")


# Alias for backward compatibility
derisk_tool = tool


def system_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[ToolCategory] = None,
    **kwargs,
):
    """
    System tool decorator - 系统工具装饰器

    Creates a system-level tool with elevated permissions.
    """

    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or (
            func.__doc__.strip().split("\n")[0]
            if func.__doc__
            else f"System tool: {tool_name}"
        )

        return tool(
            tool_name,
            description=tool_desc,
            category=category or ToolCategory.SYSTEM,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            **kwargs,
        )(func)

    return decorator


def sandbox_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[ToolCategory] = None,
    **kwargs,
):
    """
    Sandbox tool decorator - 沙箱工具装饰器

    Creates a sandbox tool for isolated execution.
    """

    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or (
            func.__doc__.strip().split("\n")[0]
            if func.__doc__
            else f"Sandbox tool: {tool_name}"
        )

        return tool(
            tool_name,
            description=tool_desc,
            category=category or ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            **kwargs,
        )(func)

    return decorator


def shell_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    dangerous: bool = False,
    **kwargs,
):
    """
    Shell tool decorator - Shell工具装饰器

    Creates a shell command tool.
    """

    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or (
            func.__doc__.strip().split("\n")[0]
            if func.__doc__
            else f"Shell tool: {tool_name}"
        )

        return tool(
            tool_name,
            description=tool_desc,
            category=ToolCategory.SHELL,
            risk_level=ToolRiskLevel.HIGH if dangerous else ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=True,
            **kwargs,
        )(func)

    return decorator


def file_read_tool(
    name: Optional[str] = None, description: Optional[str] = None, **kwargs
):
    """
    File read tool decorator - 文件读取工具装饰器
    """

    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or (
            func.__doc__.strip().split("\n")[0]
            if func.__doc__
            else f"File read tool: {tool_name}"
        )

        return tool(
            tool_name,
            description=tool_desc,
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            **kwargs,
        )(func)

    return decorator


def file_write_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    dangerous: bool = False,
    **kwargs,
):
    """
    File write tool decorator - 文件写入工具装饰器
    """

    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or (
            func.__doc__.strip().split("\n")[0]
            if func.__doc__
            else f"File write tool: {tool_name}"
        )

        return tool(
            tool_name,
            description=tool_desc,
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.HIGH if dangerous else ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=True,
            **kwargs,
        )(func)

    return decorator


def network_tool(
    name: Optional[str] = None, description: Optional[str] = None, **kwargs
):
    """
    Network tool decorator - 网络工具装饰器
    """

    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or (
            func.__doc__.strip().split("\n")[0]
            if func.__doc__
            else f"Network tool: {tool_name}"
        )

        return tool(
            tool_name,
            description=tool_desc,
            category=ToolCategory.NETWORK,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=True,
            **kwargs,
        )(func)

    return decorator


def agent_tool(name: Optional[str] = None, description: Optional[str] = None, **kwargs):
    """
    Agent tool decorator - Agent工具装饰器
    """

    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or (
            func.__doc__.strip().split("\n")[0]
            if func.__doc__
            else f"Agent tool: {tool_name}"
        )

        return tool(
            tool_name,
            description=tool_desc,
            category=ToolCategory.API,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            **kwargs,
        )(func)

    return decorator


def interaction_tool(
    name: Optional[str] = None, description: Optional[str] = None, **kwargs
):
    """
    Interaction tool decorator - 交互工具装饰器
    """

    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or (
            func.__doc__.strip().split("\n")[0]
            if func.__doc__
            else f"Interaction tool: {tool_name}"
        )

        return tool(
            tool_name,
            description=tool_desc,
            category=ToolCategory.USER_INTERACTION,
            risk_level=ToolRiskLevel.SAFE,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            **kwargs,
        )(func)

    return decorator


# Helper functions


def _parse_args_from_schema(schema: Type) -> Dict[str, Any]:
    """Parse arguments from Pydantic schema"""
    if hasattr(schema, "model_json_schema"):
        json_schema = schema.model_json_schema()
    elif hasattr(schema, "schema"):
        json_schema = schema.schema()
    else:
        return {}

    return json_schema.get("properties", {})


def _build_parameter_schema(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Build JSON Schema from parameter dict"""
    properties = {}
    required = []

    for name, param in parameters.items():
        if isinstance(param, dict):
            properties[name] = {
                "type": param.get("type", "string"),
                "description": param.get("description", name),
            }
            if param.get("required", True):
                required.append(name)
        else:
            properties[name] = {
                "type": "string",
                "description": str(param) if param else name,
            }
            required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _infer_parameters(func: Callable) -> Dict[str, Any]:
    """Infer parameters from function signature"""
    sig = inspect.signature(func)
    properties = {}
    required = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls", "context"):
            continue

        # Get type
        if param.annotation != inspect.Parameter.empty:
            type_str = _type_to_string(param.annotation)
        else:
            type_str = "string"

        properties[name] = {
            "type": type_str,
            "description": name,
        }

        if param.default == inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _type_to_string(type_hint: Any) -> str:
    """Convert Python type hint to JSON Schema type"""
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    if type_hint in type_map:
        return type_map[type_hint]

    # Handle typing generics
    origin = getattr(type_hint, "__origin__", None)
    if origin:
        if origin in (list, List):
            return "array"
        if origin in (dict, Dict):
            return "object"

    return "string"


# Export all decorators
__all__ = [
    "tool",
    "derisk_tool",
    "system_tool",
    "sandbox_tool",
    "shell_tool",
    "file_read_tool",
    "file_write_tool",
    "network_tool",
    "agent_tool",
    "interaction_tool",
]
