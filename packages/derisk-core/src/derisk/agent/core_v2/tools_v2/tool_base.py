"""
工具基础类和注册系统

提供Agent可调用的工具框架
"""

from typing import Any, Callable, Dict, List, Optional, Type
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import asyncio
import logging
import inspect

logger = logging.getLogger(__name__)


@dataclass
class ToolMetadata:
    """工具元数据"""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    requires_permission: bool = False
    dangerous: bool = False
    category: str = "general"
    version: str = "1.0.0"
    examples: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolBase(ABC):
    """工具基类"""
    
    def __init__(self):
        self._metadata: Optional[ToolMetadata] = None
        self._define_metadata()
    
    @property
    def metadata(self) -> ToolMetadata:
        if self._metadata is None:
            self._metadata = self._define_metadata()
        return self._metadata
    
    @abstractmethod
    def _define_metadata(self) -> ToolMetadata:
        """定义工具元数据"""
        pass
    
    def _define_parameters(self) -> Dict[str, Any]:
        """定义工具参数（OpenAI function calling格式）"""
        return {}
    
    def get_openai_spec(self) -> Dict[str, Any]:
        """获取OpenAI工具定义"""
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": self._define_parameters() or self.metadata.parameters
            }
        }
    
    @abstractmethod
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        """执行工具"""
        pass
    
    def validate_args(self, args: Dict[str, Any]) -> Optional[str]:
        """验证参数，返回错误信息或None"""
        return None


def tool(
    name: str,
    description: str,
    parameters: Optional[Dict[str, Any]] = None,
    requires_permission: bool = False,
    dangerous: bool = False
):
    """工具装饰器"""
    def decorator(func: Callable):
        class FunctionTool(ToolBase):
            def _define_metadata(self) -> ToolMetadata:
                return ToolMetadata(
                    name=name,
                    description=description,
                    parameters=parameters or {},
                    requires_permission=requires_permission,
                    dangerous=dangerous
                )
            
            async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
                try:
                    if asyncio.iscoroutinefunction(func):
                        result = await func(**args)
                    else:
                        result = func(**args)
                    
                    if isinstance(result, ToolResult):
                        return result
                    
                    return ToolResult(
                        success=True,
                        output=str(result) if result is not None else ""
                    )
                except Exception as e:
                    logger.error(f"[{name}] 执行失败: {e}")
                    return ToolResult(
                        success=False,
                        output="",
                        error=str(e)
                    )
        
        return FunctionTool()
    return decorator


class ToolRegistry:
    """
    工具注册中心
    
    示例:
        registry = ToolRegistry()
        registry.register(bash_tool)
        
        # 获取OpenAI格式工具定义
        tools = registry.get_openai_tools()
        
        # 执行工具
        result = await registry.execute("bash", {"command": "ls"})
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolBase] = {}
    
    def register(self, tool: ToolBase) -> "ToolRegistry":
        """注册工具"""
        name = tool.metadata.name
        if name in self._tools:
            logger.warning(f"[ToolRegistry] 工具 {name} 已存在，将被覆盖")
        self._tools[name] = tool
        logger.debug(f"[ToolRegistry] 注册工具: {name}")
        return self
    
    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[ToolBase]:
        """获取工具"""
        return self._tools.get(name)
    
    def list_all(self) -> List[ToolBase]:
        """列出所有工具"""
        return list(self._tools.values())
    
    def list_names(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())
    
    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """获取OpenAI格式工具定义列表"""
        return [tool.get_openai_spec() for tool in self._tools.values()]
    
    async def execute(
        self,
        name: str,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """执行工具"""
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"工具不存在: {name}"
            )
        
        error = tool.validate_args(args)
        if error:
            return ToolResult(
                success=False,
                output="",
                error=f"参数验证失败: {error}"
            )
        
        try:
            return await tool.execute(args, context)
        except Exception as e:
            logger.exception(f"[ToolRegistry] 工具 {name} 执行异常: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
    
    def register_function(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: Optional[Dict[str, Any]] = None,
        requires_permission: bool = False
    ) -> "ToolRegistry":
        """通过函数注册工具"""
        class FunctionTool(ToolBase):
            def _define_metadata(self) -> ToolMetadata:
                return ToolMetadata(
                    name=name,
                    description=description,
                    parameters=parameters or {},
                    requires_permission=requires_permission
                )
            
            async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
                try:
                    sig = inspect.signature(func)
                    valid_args = {k: v for k, v in args.items() if k in sig.parameters}
                    
                    if asyncio.iscoroutinefunction(func):
                        result = await func(**valid_args)
                    else:
                        result = func(**valid_args)
                    
                    if isinstance(result, ToolResult):
                        return result
                    
                    return ToolResult(
                        success=True,
                        output=str(result) if result is not None else ""
                    )
                except Exception as e:
                    return ToolResult(
                        success=False,
                        output="",
                        error=str(e)
                    )
        
        self.register(FunctionTool())
        return self