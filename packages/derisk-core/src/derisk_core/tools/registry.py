from typing import Dict, List, Optional, Type
from .base import ToolBase, ToolCategory, ToolMetadata

class ToolRegistry:
    """工具注册表"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: Dict[str, ToolBase] = {}
            cls._instance._categories: Dict[ToolCategory, List[str]] = {
                cat: [] for cat in ToolCategory
            }
        return cls._instance
    
    def register(self, tool: ToolBase) -> None:
        """注册工具"""
        self._tools[tool.metadata.name] = tool
        self._categories[tool.metadata.category].append(tool.metadata.name)
    
    def get(self, name: str) -> Optional[ToolBase]:
        """获取工具"""
        return self._tools.get(name)
    
    def list_all(self) -> List[ToolMetadata]:
        """列出所有工具"""
        return [t.metadata for t in self._tools.values()]
    
    def list_by_category(self, category: ToolCategory) -> List[ToolMetadata]:
        """按类别列出工具"""
        return [
            self._tools[name].metadata 
            for name in self._categories.get(category, [])
        ]
    
    def get_schemas(self) -> Dict[str, Dict]:
        """获取所有工具的Schema（用于LLM工具调用）"""
        schemas = {}
        for name, tool in self._tools.items():
            schemas[name] = {
                "name": name,
                "description": tool.metadata.description,
                "parameters": tool.parameters_schema
            }
        return schemas

tool_registry = ToolRegistry()

def register_builtin_tools():
    """注册内置工具"""
    from .code_tools import ReadTool, WriteTool, EditTool, GlobTool, GrepTool
    from .bash_tool import BashTool
    from .network_tools import WebFetchTool, WebSearchTool
    
    tool_registry.register(ReadTool())
    tool_registry.register(WriteTool())
    tool_registry.register(EditTool())
    tool_registry.register(GlobTool())
    tool_registry.register(GrepTool())
    tool_registry.register(BashTool())
    tool_registry.register(WebFetchTool())
    tool_registry.register(WebSearchTool())