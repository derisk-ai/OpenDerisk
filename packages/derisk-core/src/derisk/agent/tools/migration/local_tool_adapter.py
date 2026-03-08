"""
LocalTool迁移适配器

将现有的LocalTool迁移到新工具框架：
- LocalToolPack转ToolBase
- GptsTool转ToolResource
- 数据库工具同步
"""

from typing import Dict, Any, Optional, List, Callable
import json
import logging
import asyncio

from ..base import ToolBase, ToolCategory, ToolSource, ToolRiskLevel, ToolEnvironment
from ..metadata import ToolMetadata
from ..context import ToolContext
from ..result import ToolResult
from ..registry import ToolRegistry, tool_registry
from ..resource_manager import (
    ToolResource, ToolResourceManager, ToolVisibility, ToolStatus,
    tool_resource_manager
)

logger = logging.getLogger(__name__)


class LocalToolWrapper(ToolBase):
    """
    LocalTool包装器
    
    将旧的LocalTool配置包装为新框架的ToolBase
    """
    
    def __init__(
        self,
        tool_id: str,
        tool_name: str,
        config: Dict[str, Any],
        handler: Callable = None
    ):
        """
        初始化包装器
        
        Args:
            tool_id: 工具ID
            tool_name: 工具名称
            config: 工具配置（包含class_name, method_name, description, input_schema等）
            handler: 执行处理器
        """
        self._tool_id = tool_id
        self._tool_name = tool_name
        self._config = config
        self._handler = handler
        
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=self._tool_name,
            display_name=self._config.get("name", self._tool_name),
            description=self._config.get("description", ""),
            category=self._map_category(self._config.get("category")),
            source=ToolSource.USER,
            risk_level=self._map_risk_level(self._config.get("risk_level")),
            requires_permission=self._config.get("ask_user", True),
            timeout=self._config.get("timeout", 120),
            tags=self._config.get("tags", []),
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        input_schema = self._config.get("input_schema", {})
        if isinstance(input_schema, str):
            try:
                input_schema = json.loads(input_schema)
            except Exception:
                input_schema = {"type": "object", "properties": {}}
        
        return input_schema
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        if self._handler:
            try:
                if asyncio.iscoroutinefunction(self._handler):
                    result = await self._handler(**args)
                else:
                    result = self._handler(**args)
                
                return ToolResult.ok(
                    output=result,
                    tool_name=self.name,
                    metadata={"tool_id": self._tool_id}
                )
            except Exception as e:
                logger.error(f"[LocalToolWrapper] 执行失败: {e}")
                return ToolResult.fail(
                    error=str(e),
                    tool_name=self.name
                )
        
        return ToolResult.fail(
            error="No handler configured",
            tool_name=self.name
        )
    
    def _map_category(self, category: str) -> ToolCategory:
        category_map = {
            "file": ToolCategory.FILE_SYSTEM,
            "file_system": ToolCategory.FILE_SYSTEM,
            "shell": ToolCategory.SHELL,
            "code": ToolCategory.CODE,
            "network": ToolCategory.NETWORK,
            "api": ToolCategory.API,
            "database": ToolCategory.DATABASE,
            "search": ToolCategory.SEARCH,
            "analysis": ToolCategory.ANALYSIS,
            "utility": ToolCategory.UTILITY,
            "custom": ToolCategory.CUSTOM,
        }
        return category_map.get(category, ToolCategory.CUSTOM)
    
    def _map_risk_level(self, level: str) -> ToolRiskLevel:
        level_map = {
            "safe": ToolRiskLevel.SAFE,
            "low": ToolRiskLevel.LOW,
            "medium": ToolRiskLevel.MEDIUM,
            "high": ToolRiskLevel.HIGH,
            "critical": ToolRiskLevel.CRITICAL,
        }
        return level_map.get(level, ToolRiskLevel.MEDIUM)


class LocalToolMigrator:
    """
    LocalTool迁移器
    
    提供从旧LocalTool到新框架的迁移功能：
    1. 从数据库加载LocalTool配置
    2. 转换为ToolBase和ToolResource
    3. 注册到新框架
    4. 数据同步
    
    使用方式：
        migrator = LocalToolMigrator()
        
        # 迁移所有LocalTool
        count = migrator.migrate_all()
        
        # 迁移指定工具
        migrator.migrate_tool("tool_name")
    """
    
    def __init__(
        self,
        registry: ToolRegistry = None,
        resource_manager: ToolResourceManager = None
    ):
        self._registry = registry or tool_registry
        self._resource_manager = resource_manager or tool_resource_manager
    
    def migrate_from_database(self, gpts_tool_dao=None) -> int:
        """
        从数据库迁移LocalTool
        
        Args:
            gpts_tool_dao: GptsToolDao实例
        
        Returns:
            int: 迁移成功的工具数量
        """
        if gpts_tool_dao is None:
            try:
                from derisk_serve.agent.db.gpts_tool import GptsToolDao
                gpts_tool_dao = GptsToolDao()
            except ImportError:
                logger.warning("GptsToolDao未找到，跳过数据库迁移")
                return 0
        
        tools = gpts_tool_dao.get_tool_by_type('LOCAL')
        count = 0
        
        for tool in tools:
            try:
                config = json.loads(tool.config)
                self._register_local_tool(
                    tool_id=tool.tool_id,
                    tool_name=tool.tool_name,
                    config=config,
                    owner=tool.owner
                )
                count += 1
            except Exception as e:
                logger.error(f"迁移工具失败 {tool.tool_name}: {e}")
        
        logger.info(f"[LocalToolMigrator] 成功迁移 {count} 个LocalTool")
        return count
    
    def migrate_from_func_registry(self) -> int:
        """
        从函数注册表迁移
        """
        try:
            from derisk_serve.agent.resource.func_registry import central_registry
        except ImportError:
            logger.warning("central_registry未找到，跳过函数注册表迁移")
            return 0
        
        count = 0
        for name, func_info in central_registry._registry.items():
            try:
                if isinstance(name, tuple):
                    class_name, method_name = name
                else:
                    class_name, method_name = None, name
                
                tool_name = f"{class_name}_{method_name}" if class_name else method_name
                
                config = {
                    "class_name": class_name,
                    "method_name": method_name,
                    "description": func_info.get("description", ""),
                    "input_schema": func_info.get("input_schema", {}),
                }
                
                self._register_local_tool(
                    tool_id=f"func_{tool_name}",
                    tool_name=tool_name,
                    config=config
                )
                count += 1
            except Exception as e:
                logger.error(f"迁移函数工具失败 {name}: {e}")
        
        return count
    
    def _register_local_tool(
        self,
        tool_id: str,
        tool_name: str,
        config: Dict[str, Any],
        owner: str = None
    ) -> None:
        class_name = config.get("class_name")
        method_name = config.get("method_name")
        
        def create_handler(cls_name, method_name):
            async def handler(**kwargs):
                try:
                    from derisk_serve.agent.resource.func_registry import central_registry
                    func = central_registry.get_function(cls_name, method_name)
                    if asyncio.iscoroutinefunction(func):
                        return await func(**kwargs)
                    else:
                        return func(**kwargs)
                except Exception as e:
                    logger.error(f"执行LocalTool失败: {e}")
                    raise e
            return handler
        
        handler = None
        if method_name:
            handler = create_handler(class_name, method_name)
        
        wrapper = LocalToolWrapper(
            tool_id=tool_id,
            tool_name=tool_name,
            config=config,
            handler=handler
        )
        
        self._registry.register(wrapper, source=ToolSource.USER)
        
        resource = ToolResource(
            tool_id=tool_id,
            name=tool_name,
            display_name=config.get("name", tool_name),
            description=config.get("description", ""),
            category=config.get("category", "custom"),
            source="user",
            tags=config.get("tags", []),
            risk_level=config.get("risk_level", "medium"),
            requires_permission=config.get("ask_user", True),
            input_schema=config.get("input_schema", {}),
            owner=owner,
            visibility=ToolVisibility.PRIVATE if owner else ToolVisibility.PUBLIC,
            status=ToolStatus.ACTIVE
        )
        
        if isinstance(resource.input_schema, str):
            try:
                resource.input_schema = json.loads(resource.input_schema)
            except Exception:
                resource.input_schema = {}
        
        self._resource_manager.register_tool_resource(resource)
    
    def create_tool_resource_from_gpts_tool(self, gpts_tool: Any) -> ToolResource:
        config = json.loads(gpts_tool.config)
        input_schema = config.get("input_schema", {})
        if isinstance(input_schema, str):
            input_schema = json.loads(input_schema)
        
        return ToolResource(
            tool_id=gpts_tool.tool_id,
            name=gpts_tool.tool_name,
            display_name=config.get("name", gpts_tool.tool_name),
            description=config.get("description", ""),
            category=config.get("category", "custom"),
            source="user",
            tags=config.get("tags", []),
            risk_level=config.get("risk_level", "medium"),
            requires_permission=config.get("ask_user", True),
            input_schema=input_schema,
            owner=gpts_tool.owner,
            visibility=ToolVisibility.PRIVATE if gpts_tool.owner else ToolVisibility.PUBLIC,
            status=ToolStatus.ACTIVE
        )


def migrate_local_tools(gpts_tool_dao=None) -> int:
    migrator = LocalToolMigrator()
    return migrator.migrate_from_database(gpts_tool_dao)


local_tool_migrator = LocalToolMigrator()