"""
ToolBase - 统一工具基类

设计原则：
1. 类型安全 - Pydantic Schema
2. 元数据丰富 - 分类、风险、权限
3. 执行统一 - 异步执行、超时控制
4. 结果标准 - ToolResult格式
5. 可观测性 - 日志、指标、追踪
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable, TypeVar, Union
from enum import Enum
from functools import wraps
import asyncio
import logging
import inspect

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolCategory(str, Enum):
    """工具主分类"""

    BUILTIN = "builtin"
    FILE_SYSTEM = "file_system"
    CODE = "code"
    SHELL = "shell"
    SANDBOX = "sandbox"
    USER_INTERACTION = "user_interaction"
    VISUALIZATION = "visualization"
    NETWORK = "network"
    DATABASE = "database"
    API = "api"
    MCP = "mcp"
    SEARCH = "search"
    ANALYSIS = "analysis"
    REASONING = "reasoning"
    UTILITY = "utility"
    MEDIA_GEN = "media_gen"
    PLUGIN = "plugin"
    SKILL = "skill"
    CUSTOM = "custom"


class ToolSource(str, Enum):
    """工具来源"""

    CORE = "core"
    SYSTEM = "system"
    EXTENSION = "extension"
    USER = "user"
    MCP = "mcp"
    API = "api"
    AGENT = "agent"


class ToolRiskLevel(str, Enum):
    """工具风险等级"""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolEnvironment(str, Enum):
    """工具执行环境"""

    LOCAL = "local"
    DOCKER = "docker"
    WASM = "wasm"
    REMOTE = "remote"
    SANDBOX = "sandbox"


class ToolBase(ABC):
    """
    统一工具基类

    设计原则：
    1. Pydantic Schema - 类型安全的参数定义
    2. 权限集成 - 通过metadata.requires_permission
    3. 结果标准化 - 统一的ToolResult格式
    4. 风险分级 - 通过risk_level标识

    示例：
        class MyTool(ToolBase):
            def _define_metadata(self) -> ToolMetadata:
                return ToolMetadata(
                    name="my_tool",
                    description="我的工具",
                    category=ToolCategory.UTILITY
                )

            def _define_parameters(self) -> Dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {
                        "input": {"type": "string"}
                    },
                    "required": ["input"]
                }

            async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult:
                return ToolResult(success=True, output="结果")
    """

    def __init__(self):
        from .metadata import ToolMetadata
        from .result import ToolResult
        from .context import ToolContext

        self._metadata = self._define_metadata()
        self._parameters = self._define_parameters()
        self._initialized = False

    @property
    def metadata(self):
        from .metadata import ToolMetadata

        return self._metadata

    @property
    def parameters(self):
        return self._parameters

    @property
    def name(self) -> str:
        return self._metadata.name

    @property
    def is_stream(self) -> bool:
        """是否流式输出工具，默认为 False"""
        return False

    @property
    def is_async(self) -> bool:
        """是否异步执行工具，默认为 True（execute 方法是 async）"""
        return True

    @property
    def stream_queue(self) -> Optional[asyncio.Queue]:
        """流式输出队列，仅当 is_stream=True 时使用"""
        return None

    @abstractmethod
    def _define_metadata(self):
        """
        定义工具元数据

        Returns:
            ToolMetadata: 工具元数据
        """
        pass

    @abstractmethod
    def _define_parameters(self) -> Dict[str, Any]:
        """
        定义工具参数(Schema格式)

        Returns:
            Dict: JSON Schema格式的参数定义
        """
        pass

    @abstractmethod
    async def execute(self, args: Dict[str, Any], context: Optional[Any] = None):
        """
        执行工具

        Args:
            args: 工具参数
            context: 执行上下文

        Returns:
            ToolResult: 执行结果
        """
        pass

    async def on_register(self) -> None:
        """注册时调用"""
        self._initialized = True
        logger.info(f"[Tool] {self.name} registered")

    async def on_unregister(self) -> None:
        """注销时调用"""
        logger.info(f"[Tool] {self.name} unregistered")

    async def pre_execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行前钩子"""
        return args

    async def post_execute(self, result) -> Any:
        """执行后钩子"""
        return result

    async def async_execute(self, *args, **kwargs):
        """
        异步执行工具的统一入口

        这是执行工具的推荐方法，内部会调用 execute 方法。
        提供此方法是为了保持与旧版 FunctionTool 接口的兼容性。

        Args:
            *args: 位置参数
            **kwargs: 关键字参数，可包含 'context' 用于传递执行上下文

        Returns:
            ToolResult: 执行结果
        """
        context = kwargs.pop("context", None)
        if args and len(args) >= 1:
            if isinstance(args[0], dict):
                merged_args = dict(args[0])
                merged_args.update(kwargs)
                return await self.execute(merged_args, context)
            return await self.execute(*args, **kwargs, context=context)
        else:
            return await self.execute(kwargs, context)

    def validate_args(self, args: Dict[str, Any]) -> bool:
        """
        验证参数

        Args:
            args: 待验证的参数

        Returns:
            bool: 是否有效
        """
        required = self.parameters.get("required", [])
        return all(param in args for param in required)

    def get_description_for_llm(self) -> str:
        """
        获取给LLM的工具描述

        Returns:
            str: 工具描述
        """
        return f"{self.metadata.name}: {self.metadata.description}"

    def to_openai_tool(self) -> Dict[str, Any]:
        """
        转换为OpenAI工具格式

        Returns:
            Dict: OpenAI工具定义
        """
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_tool(self) -> Dict[str, Any]:
        """
        转换为Anthropic工具格式

        Returns:
            Dict: Anthropic工具定义
        """
        return {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "input_schema": self.parameters,
        }

    def get_prompt(self, lang: str = "en") -> str:
        """
        获取工具提示词

        Args:
            lang: 语言(en/zh)

        Returns:
            str: 工具提示词
        """
        import json

        if lang == "zh":
            return (
                f"工具名称: {self.metadata.name}\n"
                f"描述: {self.metadata.description}\n"
                f"参数: {json.dumps(self.parameters, ensure_ascii=False)}"
            )
        return (
            f"Tool: {self.metadata.name}\n"
            f"Description: {self.metadata.description}\n"
            f"Parameters: {json.dumps(self.parameters)}"
        )


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: ToolCategory = ToolCategory.UTILITY,
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW,
    **metadata_kwargs,
) -> Callable:
    """
    工具装饰器 - 将函数转换为工具

    示例:
        @tool(name="my_tool", description="我的工具")
        async def my_tool(input: str) -> str:
            return f"processed: {input}"
    """
    from .metadata import ToolMetadata

    def decorator(func: Callable) -> "ToolBase":
        from .result import ToolResult

        tool_name = name or func.__name__
        tool_description = description or (func.__doc__ or "").strip()

        class FunctionTool(ToolBase):
            def __init__(self):
                self._func = func
                self._is_async = asyncio.iscoroutinefunction(func)
                super().__init__()

            def _define_metadata(self) -> ToolMetadata:
                return ToolMetadata(
                    name=tool_name,
                    description=tool_description,
                    category=category,
                    risk_level=risk_level,
                    **metadata_kwargs,
                )

            def _define_parameters(self) -> Dict[str, Any]:
                sig = inspect.signature(func)
                properties = {}
                required = []

                for param_name, param in sig.parameters.items():
                    if param_name in ("self", "cls", "context"):
                        continue

                    param_type = "string"
                    if param.annotation != inspect.Parameter.empty:
                        type_map = {
                            str: "string",
                            int: "integer",
                            float: "number",
                            bool: "boolean",
                            list: "array",
                            dict: "object",
                        }
                        param_type = type_map.get(param.annotation, "string")

                    properties[param_name] = {
                        "type": param_type,
                        "description": f"参数 {param_name}",
                    }

                    if param.default == inspect.Parameter.empty:
                        required.append(param_name)

                return {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }

            async def execute(
                self, args: Dict[str, Any], context: Optional[Any] = None
            ):
                try:
                    if self._is_async:
                        result = await self._func(**args)
                    else:
                        result = self._func(**args)

                    return ToolResult(success=True, output=result, tool_name=self.name)
                except Exception as e:
                    return ToolResult(
                        success=False, output=None, error=str(e), tool_name=self.name
                    )

        tool_instance = FunctionTool()

        if not asyncio.iscoroutinefunction(func):

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                return func(*args, **kwargs)

            sync_wrapper._tool = tool_instance
            return sync_wrapper
        else:

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            async_wrapper._tool = tool_instance
            return async_wrapper

    return decorator


def register_tool(registry: "ToolRegistry", source: ToolSource = ToolSource.SYSTEM):
    """
    注册工具装饰器

    示例:
        @register_tool(tool_registry, source=ToolSource.USER)
        class MyTool(ToolBase):
            ...
    """

    def decorator(tool_class: type) -> type:
        instance = tool_class()
        registry.register(instance, source=source)
        return tool_class

    return decorator
