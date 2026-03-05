"""
ToolRegistry - 工具注册表

提供全局工具管理：
- 工具注册/注销
- 工具查找与获取
- 工具分类管理
- 工具生命周期管理
"""

from typing import Dict, Any, Optional, List, Set
from pydantic import BaseModel, Field
from collections import defaultdict
import logging
import importlib
import inspect

from .base import ToolBase, ToolCategory, ToolSource, ToolRiskLevel
from .metadata import ToolMetadata

logger = logging.getLogger(__name__)


class ToolFilter(BaseModel):
    """工具过滤器"""
    
    categories: List[ToolCategory] = Field(default_factory=list, description="类别过滤")
    sources: List[ToolSource] = Field(default_factory=list, description="来源过滤")
    risk_levels: List[ToolRiskLevel] = Field(default_factory=list, description="风险等级过滤")
    tags: List[str] = Field(default_factory=list, description="标签过滤")
    search_query: Optional[str] = Field(None, description="搜索关键词")
    
    def matches(self, tool: ToolBase) -> bool:
        """检查工具是否匹配过滤条件"""
        metadata = tool.metadata
        
        if self.categories and metadata.category not in self.categories:
            return False
        
        if self.sources and metadata.source not in self.sources:
            return False
        
        if self.risk_levels and metadata.risk_level not in self.risk_levels:
            return False
        
        if self.tags:
            if not any(tag in metadata.tags for tag in self.tags):
                return False
        
        if self.search_query:
            query = self.search_query.lower()
            if (query not in metadata.name.lower() and
                query not in metadata.description.lower()):
                return False
        
        return True


class ToolRegistry:
    """
    全局工具注册表
    
    职责：
    1. 工具注册/注销
    2. 工具查找与获取
    3. 工具分类管理
    4. 工具生命周期管理
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolBase] = {}
        self._categories: Dict[ToolCategory, Set[str]] = defaultdict(set)
        self._sources: Dict[ToolSource, Set[str]] = defaultdict(set)
        self._metadata_index: Dict[str, ToolMetadata] = {}
        self._initialized = False
    
    def register(self, tool: ToolBase, source: ToolSource = ToolSource.SYSTEM) -> None:
        """注册工具"""
        tool_name = tool.metadata.name
        
        if tool_name in self._tools:
            logger.warning(f"工具 '{tool_name}' 已存在，将被覆盖")
        
        tool.metadata.source = source
        
        self._tools[tool_name] = tool
        self._categories[tool.metadata.category].add(tool_name)
        self._sources[source].add(tool_name)
        self._metadata_index[tool_name] = tool.metadata
        
        if hasattr(tool, 'on_register'):
            import asyncio
            try:
                if inspect.iscoroutinefunction(tool.on_register):
                    asyncio.create_task(tool.on_register())
                else:
                    tool.on_register()
            except Exception as e:
                logger.warning(f"工具 {tool_name} on_register 失败: {e}")
        
        logger.debug(f"[ToolRegistry] 已注册工具: {tool_name} (source={source.value})")
    
    def unregister(self, tool_name: str) -> bool:
        """注销工具"""
        if tool_name not in self._tools:
            return False
        
        tool = self._tools[tool_name]
        
        if hasattr(tool, 'on_unregister'):
            import asyncio
            try:
                if inspect.iscoroutinefunction(tool.on_unregister):
                    asyncio.create_task(tool.on_unregister())
                else:
                    tool.on_unregister()
            except Exception as e:
                logger.warning(f"工具 {tool_name} on_unregister 失败: {e}")
        
        self._categories[tool.metadata.category].discard(tool_name)
        self._sources[tool.metadata.source].discard(tool_name)
        del self._tools[tool_name]
        del self._metadata_index[tool_name]
        
        logger.debug(f"[ToolRegistry] 已注销工具: {tool_name}")
        return True
    
    def register_batch(self, tools: List[ToolBase], source: ToolSource = ToolSource.SYSTEM) -> int:
        """批量注册工具"""
        count = 0
        for tool in tools:
            try:
                self.register(tool, source=source)
                count += 1
            except Exception as e:
                logger.error(f"注册工具失败: {e}")
        return count
    
    def get(self, tool_name: str) -> Optional[ToolBase]:
        """获取工具"""
        return self._tools.get(tool_name)
    
    def get_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        """获取工具元数据"""
        return self._metadata_index.get(tool_name)
    
    def get_by_category(self, category: ToolCategory) -> List[ToolBase]:
        """获取指定类别的工具"""
        tool_names = self._categories.get(category, set())
        return [self._tools[name] for name in tool_names if name in self._tools]
    
    def get_by_source(self, source: ToolSource) -> List[ToolBase]:
        """获取指定来源的工具"""
        tool_names = self._sources.get(source, set())
        return [self._tools[name] for name in tool_names if name in self._tools]
    
    def get_by_risk_level(self, level: ToolRiskLevel) -> List[ToolBase]:
        """获取指定风险等级的工具"""
        return [tool for tool in self._tools.values() if tool.metadata.risk_level == level]
    
    def list_all(self) -> List[ToolBase]:
        """列出所有工具"""
        return list(self._tools.values())
    
    def list_all_metadata(self) -> List[ToolMetadata]:
        """列出所有工具元数据"""
        return list(self._metadata_index.values())
    
    def search(self, query: str) -> List[ToolBase]:
        """搜索工具"""
        query = query.lower()
        results = []
        for tool in self._tools.values():
            if (query in tool.metadata.name.lower() or
                query in tool.metadata.description.lower()):
                results.append(tool)
        return results
    
    def filter(self, tool_filter: ToolFilter) -> List[ToolBase]:
        """过滤工具"""
        return [tool for tool in self._tools.values() if tool_filter.matches(tool)]
    
    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """获取OpenAI格式的工具列表"""
        return [tool.to_openai_tool() for tool in self._tools.values()]
    
    def to_anthropic_tools(self) -> List[Dict[str, Any]]:
        """获取Anthropic格式的工具列表"""
        return [tool.to_anthropic_tool() for tool in self._tools.values()]
    
    def __len__(self) -> int:
        return len(self._tools)
    
    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self._tools
    
    def __getitem__(self, tool_name: str) -> ToolBase:
        return self._tools[tool_name]
    
    def discover_and_register(
        self, 
        module_path: str, 
        source: ToolSource = ToolSource.EXTENSION
    ) -> int:
        """从模块发现并注册工具"""
        count = 0
        try:
            module = importlib.import_module(module_path)
            for name in dir(module):
                obj = getattr(module, name)
                if (isinstance(obj, type) and 
                    issubclass(obj, ToolBase) and 
                    obj is not ToolBase):
                    try:
                        instance = obj()
                        self.register(instance, source=source)
                        count += 1
                    except Exception as e:
                        logger.warning(f"实例化工具 {name} 失败: {e}")
        except Exception as e:
            logger.error(f"发现工具失败: {e}")
        
        return count


tool_registry = ToolRegistry()


def get_tool(tool_name: str) -> Optional[ToolBase]:
    """获取工具的快捷方法"""
    return tool_registry.get(tool_name)


def register_builtin_tools() -> None:
    """注册内置工具"""
    from .builtin import register_all as register_builtin
    register_builtin(tool_registry)
    tool_registry._initialized = True
    logger.info(f"[ToolRegistry] 已注册 {len(tool_registry)} 个内置工具")