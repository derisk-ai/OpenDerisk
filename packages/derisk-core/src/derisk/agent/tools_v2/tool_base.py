"""
ToolBase - 工具基类

参考OpenCode的Tool定义模式
使用Pydantic Schema实现类型安全的工具定义
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class ToolRiskLevel(str, Enum):
    """工具风险等级"""

    LOW = "low"  # 低风险 - 如读取文件
    MEDIUM = "medium"  # 中风险 - 如编辑文件
    HIGH = "high"  # 高风险 - 如执行Shell命令


class ToolCategory(str, Enum):
    """工具类别"""

    FILE_SYSTEM = "file_system"  # 文件系统操作
    SHELL = "shell"  # Shell执行
    NETWORK = "network"  # 网络操作
    CODE = "code"  # 代码操作
    SEARCH = "search"  # 搜索操作
    ANALYSIS = "analysis"  # 分析操作
    UTILITY = "utility"  # 工具函数


class ToolMetadata(BaseModel):
    """工具元数据"""

    name: str  # 工具名称
    description: str  # 工具描述
    category: ToolCategory  # 工具类别
    risk_level: ToolRiskLevel = ToolRiskLevel.MEDIUM  # 风险等级
    requires_permission: bool = True  # 是否需要权限检查
    version: str = "1.0.0"  # 版本号
    tags: List[str] = Field(default_factory=list)  # 标签

    class Config:
        use_enum_values = True


class ToolResult(BaseModel):
    """工具执行结果"""

    success: bool  # 是否成功
    output: Any  # 输出结果
    error: Optional[str] = None  # 错误信息
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 元数据

    class Config:
        arbitrary_types_allowed = True


class ToolBase(ABC):
    """
    工具基类 - 参考OpenCode的Tool设计

    设计原则:
    1. Pydantic Schema - 类型安全的参数定义
    2. 权限集成 - 通过metadata.requires_permission
    3. 结果标准化 - 统一的ToolResult格式
    4. 风险分级 - 通过risk_level标识

    示例:
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

            async def execute(self, args: Dict[str, Any]) -> ToolResult:
                return ToolResult(success=True, output="结果")
    """

    def __init__(self):
        self.metadata = self._define_metadata()
        self.parameters = self._define_parameters()

    @abstractmethod
    def _define_metadata(self) -> ToolMetadata:
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

        示例:
            {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的命令"
                    },
                    "timeout": {
                        "type": "integer",
                        "default": 120
                    }
                },
                "required": ["command"]
            }
        """
        pass

    @abstractmethod
    async def execute(
        self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        执行工具

        Args:
            args: 工具参数
            context: 执行上下文

        Returns:
            ToolResult: 执行结果
        """
        pass

    def validate_args(self, args: Dict[str, Any]) -> bool:
        """
        验证参数

        Args:
            args: 待验证的参数

        Returns:
            bool: 是否有效
        """
        # 简单验证: 检查必需参数
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


class ToolRegistry:
    """
    工具注册表

    示例:
        registry = ToolRegistry()

        # 注册工具
        registry.register(BashTool())

        # 获取工具
        tool = registry.get("bash")

        # 列出工具
        tools = registry.list_by_category(ToolCategory.SHELL)
    """

    def __init__(self):
        self._tools: Dict[str, ToolBase] = {}

    def register(self, tool: ToolBase):
        """
        注册工具

        Args:
            tool: 工具实例
        """
        if tool.metadata.name in self._tools:
            raise ValueError(f"工具 '{tool.metadata.name}' 已注册")
        self._tools[tool.metadata.name] = tool

    def unregister(self, tool_name: str):
        """
        注销工具

        Args:
            tool_name: 工具名称
        """
        self._tools.pop(tool_name, None)

    def get(self, tool_name: str) -> Optional[ToolBase]:
        """
        获取工具

        Args:
            tool_name: 工具名称

        Returns:
            Optional[ToolBase]: 工具实例,不存在则返回None
        """
        return self._tools.get(tool_name)

    def list_all(self) -> List[ToolBase]:
        """
        列出所有工具

        Returns:
            List[ToolBase]: 工具列表
        """
        return list(self._tools.values())

    def list_by_category(self, category: ToolCategory) -> List[ToolBase]:
        """
        按类别列出工具

        Args:
            category: 工具类别

        Returns:
            List[ToolBase]: 工具列表
        """
        return [
            tool for tool in self._tools.values() if tool.metadata.category == category
        ]

    def list_by_risk_level(self, risk_level: ToolRiskLevel) -> List[ToolBase]:
        """
        按风险等级列出工具

        Args:
            risk_level: 风险等级

        Returns:
            List[ToolBase]: 工具列表
        """
        return [
            tool
            for tool in self._tools.values()
            if tool.metadata.risk_level == risk_level
        ]

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """
        获取OpenAI格式的工具列表

        Returns:
            List[Dict]: OpenAI工具列表
        """
        return [tool.to_openai_tool() for tool in self._tools.values()]


# 全局工具注册表
tool_registry = ToolRegistry()
