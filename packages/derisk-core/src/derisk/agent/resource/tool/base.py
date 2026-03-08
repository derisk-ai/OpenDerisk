"""
Tool Resources - 兼容层重定向

此模块已迁移到统一工具框架。
所有工具类和装饰器现在从 derisk.agent.tools 导入。

旧的导入路径:
    from derisk.agent.resource.tool.base import tool, BaseTool, FunctionTool, ...

新的导入路径 (推荐):
    from derisk.agent.tools import tool, ToolBase, ToolRegistry, ...

此文件仅作为向后兼容层存在，新代码请使用统一框架。
"""

from typing import Any, Awaitable, Callable, Dict, Optional, Union
import asyncio

from derisk._private.pydantic import BaseModel, Field, model_validator
from derisk.util.configure.base import _MISSING

# 导入 Resource 基类
from ..base import (
    Resource,
    ResourceParameters,
    ResourceType,
    EXECUTE_ARGS_TYPE,
    PARSE_EXECUTE_ARGS_FUNCTION,
)

# 从统一框架重新导出
from derisk.agent.tools import (
    ToolBase,
    ToolCategory,
    ToolRiskLevel,
    ToolSource,
    ToolMetadata,
    ToolResult,
    ToolContext,
    ToolRegistry,
    tool_registry,
)

# 装饰器
from derisk.agent.tools.decorators import (
    tool,
    derisk_tool,
    system_tool,
    sandbox_tool,
)


# ToolFunc 类型定义 - 用于表示工具函数类型
ToolFunc = Union[Callable[..., Any], Callable[..., Awaitable[Any]]]


class ToolParameter(BaseModel):
    """Parameter for a tool."""

    name: str = Field(..., description="Parameter name")
    title: str = Field(
        ...,
        description="Parameter title, default to the name with the first letter "
        "capitalized",
    )
    type: str = Field(..., description="Parameter type", examples=["string", "integer"])
    description: str = Field(..., description="Parameter description")
    required: bool = Field(True, description="Whether the parameter is required")
    default: Optional[Any] = Field(
        _MISSING, description="Default value for the parameter"
    )

    @model_validator(mode="before")
    @classmethod
    def pre_fill(cls, values):
        """Pre-fill the model."""
        if not isinstance(values, dict):
            return values
        if "title" not in values:
            values["title"] = values["name"].replace("_", " ").title()
        if "description" not in values:
            values["description"] = values["title"]
        return values


class ToolResourceParameters(ResourceParameters):
    """Tool resource parameters class."""

    pass


# BaseTool - 必须继承自 Resource
class BaseTool(Resource[ToolResourceParameters]):
    """
    Base class for a tool.

    这是向后兼容的实现，继承自 Resource 以满足 isinstance 检查。
    """

    @classmethod
    def type(cls) -> ResourceType:
        """Return the resource type."""
        return ResourceType.Tool

    @property
    def description(self) -> str:
        """Return the description of the tool."""
        raise NotImplementedError

    @property
    def args(self) -> Dict[str, ToolParameter]:
        """Return the arguments of the tool."""
        raise NotImplementedError

    async def get_prompt(
        self,
        *,
        lang: str = "en",
        prompt_type: str = "default",
        question: Optional[str] = None,
        resource_name: Optional[str] = None,
        **kwargs,
    ):
        """Get the prompt."""
        import json

        prompt_template = (
            "{name}: Call this tool to interact with the {name} API. "
            "What is the {name} API useful for? {description} "
            "Parameters: {parameters}"
        )
        prompt_template_zh = (
            "{name}：调用此工具与 {name} API进行交互。{name} API 有什么用？"
            "{description} 参数：{parameters}"
        )
        template = prompt_template if lang == "en" else prompt_template_zh
        if prompt_type == "openai":
            properties = {}
            required_list = []
            for key, value in self.args.items():
                properties[key] = {
                    "type": value.type,
                    "description": value.description,
                }
                if value.required:
                    required_list.append(key)
            parameters_dict = {
                "type": "object",
                "properties": properties,
                "required": required_list,
            }
            parameters_string = json.dumps(parameters_dict, ensure_ascii=False)
        else:
            parameters = []
            for key, value in self.args.items():
                parameters.append(
                    {
                        "name": key,
                        "type": value.type,
                        "description": value.description,
                        "required": value.required,
                    }
                )
            parameters_string = json.dumps(parameters, ensure_ascii=False)
        return (
            template.format(
                name=self.name,
                description=self.description,
                parameters=parameters_string,
            ),
            None,
        )


# FunctionTool 兼容类 - 包装函数为工具
class FunctionTool(BaseTool):
    """
    FunctionTool 兼容层 - 将函数包装为工具

    这是一个向后兼容的实现，继承自 BaseTool (Resource)。
    """

    def __init__(
        self,
        name: str,
        func: ToolFunc,
        description: Optional[str] = None,
        args: Optional[Dict[str, Union[ToolParameter, Dict[str, Any]]]] = None,
        args_schema=None,
        parse_execute_args_func: Optional[PARSE_EXECUTE_ARGS_FUNCTION] = None,
        **kwargs,
    ):
        self._name = name
        self._func = func
        self._description = description or func.__doc__ or ""
        self._args: Dict[str, ToolParameter] = self._parse_args(args)
        self._args_schema = args_schema
        self._parse_execute_args_func = parse_execute_args_func
        self._kwargs = kwargs
        self._is_async = asyncio.iscoroutinefunction(func)

    def _parse_args(
        self, args: Optional[Dict[str, Union[ToolParameter, Dict[str, Any]]]]
    ) -> Dict[str, ToolParameter]:
        """Parse args to ToolParameter dict."""
        if not args:
            return {}
        result = {}
        for key, value in args.items():
            if isinstance(value, ToolParameter):
                result[key] = value
            elif isinstance(value, dict):
                # If dict already has 'name', use it; otherwise use key as name
                if "name" not in value:
                    result[key] = ToolParameter(name=key, **value)
                else:
                    # Use the name from the dict, but still add to result with key
                    result[key] = ToolParameter(**value)
        return result

    @property
    def name(self) -> str:
        """Return the name of the tool."""
        return self._name

    @property
    def description(self) -> str:
        """Return the description of the tool."""
        return self._description

    @property
    def args(self) -> Dict[str, ToolParameter]:
        """Return the arguments of the tool."""
        return self._args

    @property
    def is_async(self) -> bool:
        """Return whether the tool is asynchronous."""
        return self._is_async

    def parse_execute_args(
        self, resource_name: Optional[str] = None, input_str: Optional[str] = None
    ) -> Optional[EXECUTE_ARGS_TYPE]:
        """Parse the execute arguments."""
        if self._parse_execute_args_func is not None:
            return self._parse_execute_args_func(input_str)
        return None

    def execute(self, *args, **kwargs) -> Any:
        """Execute the tool."""
        if self._is_async:
            raise ValueError("The function is asynchronous, use async_execute instead")
        return self._func(*args, **kwargs)

    async def async_execute(self, *args, **kwargs) -> Any:
        """Execute the tool asynchronously."""
        if not self._is_async:
            raise ValueError("The function is synchronous, use execute instead")
        return await self._func(*args, **kwargs)


# 保留旧的常量
DERISK_TOOL_IDENTIFIER = "derisk_tool"

__all__ = [
    "tool",
    "derisk_tool",
    "system_tool",
    "sandbox_tool",
    "ToolBase",
    "BaseTool",
    "FunctionTool",
    "ToolFunc",
    "ToolParameter",
    "ToolCategory",
    "ToolRiskLevel",
    "ToolSource",
    "ToolMetadata",
    "ToolResult",
    "ToolContext",
    "ToolRegistry",
    "tool_registry",
    "DERISK_TOOL_IDENTIFIER",
]
