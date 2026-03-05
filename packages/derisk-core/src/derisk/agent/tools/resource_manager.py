"""
ToolResourceManager - 工具资源管理器

用于前端应用编辑模块选择关联，提供：
- 工具列表查询（分类展示）
- 工具详情获取
- 工具与应用关联
- 工具配置管理
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
import logging

from .base import ToolBase, ToolCategory, ToolSource, ToolRiskLevel
from .metadata import ToolMetadata
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolVisibility(str, Enum):
    """工具可见性"""
    PUBLIC = "public"      # 公开，所有人可见
    PRIVATE = "private"    # 私有，仅所有者可见
    SYSTEM = "system"      # 系统，系统预置


class ToolStatus(str, Enum):
    """工具状态"""
    ACTIVE = "active"      # 激活
    DISABLED = "disabled"  # 禁用
    DEPRECATED = "deprecated"  # 废弃


class ToolResource(BaseModel):
    """
    工具资源 - 用于前端展示和关联
    
    包含工具的完整信息，供前端编辑模块使用
    """
    
    # === 基本信息 ===
    tool_id: str = Field(..., description="工具唯一ID")
    name: str = Field(..., description="工具名称")
    display_name: str = Field("", description="展示名称")
    description: str = Field("", description="详细描述")
    version: str = "1.0.0"
    
    # === 分类信息 ===
    category: str = Field(..., description="工具类别")
    subcategory: Optional[str] = Field(None, description="子类别")
    source: str = Field(..., description="来源")
    tags: List[str] = Field(default_factory=list, description="标签")
    
    # === 风险与权限 ===
    risk_level: str = Field("low", description="风险等级")
    requires_permission: bool = Field(True, description="是否需要权限")
    
    # === 可见性与状态 ===
    visibility: ToolVisibility = Field(ToolVisibility.PUBLIC, description="可见性")
    status: ToolStatus = Field(ToolStatus.ACTIVE, description="状态")
    owner: Optional[str] = Field(None, description="所有者")
    
    # === 输入输出定义 ===
    input_schema: Dict[str, Any] = Field(default_factory=dict, description="输入Schema")
    output_schema: Dict[str, Any] = Field(default_factory=dict, description="输出Schema")
    examples: List[Dict[str, Any]] = Field(default_factory=list, description="使用示例")
    
    # === 执行配置 ===
    timeout: int = Field(120, description="默认超时(秒)")
    execution_mode: str = Field("local", description="执行模式")
    
    # === 关联信息 ===
    app_ids: List[str] = Field(default_factory=list, description="关联的应用ID列表")
    
    # === 元信息 ===
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # === 统计信息 ===
    call_count: int = Field(0, description="调用次数")
    success_count: int = Field(0, description="成功次数")
    
    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
    
    @classmethod
    def from_tool_base(cls, tool: ToolBase, tool_id: str = None) -> "ToolResource":
        """从ToolBase创建ToolResource"""
        metadata = tool.metadata
        return cls(
            tool_id=tool_id or metadata.name,
            name=metadata.name,
            display_name=metadata.display_name,
            description=metadata.description,
            version=metadata.version,
            category=metadata.category.value if hasattr(metadata.category, 'value') else str(metadata.category),
            subcategory=metadata.subcategory,
            source=metadata.source.value if hasattr(metadata.source, 'value') else str(metadata.source),
            tags=metadata.tags,
            risk_level=metadata.risk_level.value if hasattr(metadata.risk_level, 'value') else str(metadata.risk_level),
            requires_permission=metadata.requires_permission,
            input_schema=tool.parameters,
            output_schema=metadata.output_schema,
            examples=[e.model_dump() if hasattr(e, 'model_dump') else e for e in metadata.examples],
            timeout=metadata.timeout,
            execution_mode=metadata.environment.value if hasattr(metadata.environment, 'value') else str(metadata.environment),
        )


class ToolCategoryGroup(BaseModel):
    """工具分类组 - 用于前端分类展示"""
    
    category: str = Field(..., description="分类名称")
    display_name: str = Field(..., description="分类展示名")
    description: str = Field("", description="分类描述")
    icon: Optional[str] = Field(None, description="分类图标")
    tools: List[ToolResource] = Field(default_factory=list, description="该分类下的工具")
    count: int = Field(0, description="工具数量")


class ToolResourceManager:
    """
    工具资源管理器
    
    提供工具的资源管理功能，包括：
    1. 工具注册与发现
    2. 工具分类展示
    3. 工具与应用关联
    4. 工具配置管理
    
    使用方式：
        from derisk.agent.tools import tool_resource_manager
        
        # 获取分类工具列表
        groups = tool_resource_manager.get_tools_by_category()
        
        # 搜索工具
        tools = tool_resource_manager.search_tools("文件")
        
        # 关联工具到应用
        tool_resource_manager.associate_tool_to_app("tool_id", "app_id")
    """
    
    # 分类展示名称映射
    CATEGORY_DISPLAY_NAMES = {
        ToolCategory.BUILTIN: ("内置工具", "系统内置的基础工具"),
        ToolCategory.FILE_SYSTEM: ("文件系统", "文件读写、搜索等操作"),
        ToolCategory.CODE: ("代码工具", "代码编辑、格式化等"),
        ToolCategory.SHELL: ("Shell工具", "命令执行、脚本运行"),
        ToolCategory.SANDBOX: ("沙箱执行", "安全隔离环境执行"),
        ToolCategory.USER_INTERACTION: ("用户交互", "与用户进行交互"),
        ToolCategory.VISUALIZATION: ("可视化", "图表、表格等展示"),
        ToolCategory.NETWORK: ("网络工具", "HTTP请求、API调用"),
        ToolCategory.DATABASE: ("数据库", "数据库查询和操作"),
        ToolCategory.API: ("API工具", "外部API集成"),
        ToolCategory.MCP: ("MCP工具", "MCP协议工具"),
        ToolCategory.SEARCH: ("搜索工具", "内容搜索和检索"),
        ToolCategory.ANALYSIS: ("分析工具", "数据分析和处理"),
        ToolCategory.REASONING: ("推理工具", "逻辑推理和规划"),
        ToolCategory.UTILITY: ("工具函数", "常用工具函数"),
        ToolCategory.PLUGIN: ("插件工具", "扩展插件工具"),
        ToolCategory.CUSTOM: ("自定义工具", "用户自定义工具"),
    }
    
    def __init__(self, registry: ToolRegistry = None):
        self._registry = registry or ToolRegistry()
        self._tool_resources: Dict[str, ToolResource] = {}
        self._app_tool_associations: Dict[str, List[str]] = {}  # app_id -> [tool_ids]
        self._tool_app_associations: Dict[str, List[str]] = {}  # tool_id -> [app_ids]
    
    # === 工具注册 ===
    
    def register_tool_resource(self, resource: ToolResource) -> None:
        """注册工具资源"""
        self._tool_resources[resource.tool_id] = resource
        logger.debug(f"[ToolResourceManager] 注册工具资源: {resource.tool_id}")
    
    def unregister_tool_resource(self, tool_id: str) -> bool:
        """注销工具资源"""
        if tool_id in self._tool_resources:
            del self._tool_resources[tool_id]
            # 清理关联
            if tool_id in self._tool_app_associations:
                for app_id in self._tool_app_associations[tool_id]:
                    if app_id in self._app_tool_associations:
                        self._app_tool_associations[app_id] = [
                            tid for tid in self._app_tool_associations[app_id] if tid != tool_id
                        ]
                del self._tool_app_associations[tool_id]
            return True
        return False
    
    def sync_from_registry(self) -> int:
        """从注册表同步工具"""
        count = 0
        for tool in self._registry.list_all():
            tool_id = f"{tool.metadata.source.value}_{tool.metadata.name}"
            if tool_id not in self._tool_resources:
                resource = ToolResource.from_tool_base(tool, tool_id=tool_id)
                self.register_tool_resource(resource)
                count += 1
        return count
    
    # === 工具查询 ===
    
    def get_tool(self, tool_id: str) -> Optional[ToolResource]:
        """获取单个工具"""
        return self._tool_resources.get(tool_id)
    
    def get_tools_by_category(
        self,
        include_empty: bool = False,
        visibility_filter: Optional[List[ToolVisibility]] = None,
        status_filter: Optional[List[ToolStatus]] = None
    ) -> List[ToolCategoryGroup]:
        """
        按分类获取工具列表
        
        Args:
            include_empty: 是否包含空分类
            visibility_filter: 可见性过滤
            status_filter: 状态过滤
        
        Returns:
            List[ToolCategoryGroup]: 分类工具组列表
        """
        # 按分类组织工具
        category_tools: Dict[str, List[ToolResource]] = {}
        
        for resource in self._tool_resources.values():
            # 应用过滤条件
            if visibility_filter and resource.visibility not in visibility_filter:
                continue
            if status_filter and resource.status not in status_filter:
                continue
            
            cat = resource.category
            if cat not in category_tools:
                category_tools[cat] = []
            category_tools[cat].append(resource)
        
        # 构建分类组
        groups = []
        
        # 按预定义顺序输出
        for category in ToolCategory:
            cat_name = category.value if hasattr(category, 'value') else str(category)
            display_info = self.CATEGORY_DISPLAY_NAMES.get(category, (cat_name, ""))
            
            tools = category_tools.get(cat_name, [])
            
            if tools or include_empty:
                groups.append(ToolCategoryGroup(
                    category=cat_name,
                    display_name=display_info[0],
                    description=display_info[1],
                    tools=tools,
                    count=len(tools)
                ))
        
        return groups
    
    def get_tools_by_source(self, source: ToolSource) -> List[ToolResource]:
        """按来源获取工具"""
        source_value = source.value if hasattr(source, 'value') else str(source)
        return [
            r for r in self._tool_resources.values()
            if r.source == source_value
        ]
    
    def get_tools_by_risk_level(self, level: ToolRiskLevel) -> List[ToolResource]:
        """按风险等级获取工具"""
        level_value = level.value if hasattr(level, 'value') else str(level)
        return [
            r for r in self._tool_resources.values()
            if r.risk_level == level_value
        ]
    
    def search_tools(
        self,
        query: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[ToolResource]:
        """
        搜索工具
        
        Args:
            query: 搜索关键词
            category: 分类过滤
            tags: 标签过滤
        
        Returns:
            List[ToolResource]: 匹配的工具列表
        """
        query_lower = query.lower()
        results = []
        
        for resource in self._tool_resources.values():
            # 关键词匹配
            if (query_lower in resource.name.lower() or
                query_lower in resource.display_name.lower() or
                query_lower in resource.description.lower()):
                
                # 分类过滤
                if category and resource.category != category:
                    continue
                
                # 标签过滤
                if tags and not any(tag in resource.tags for tag in tags):
                    continue
                
                results.append(resource)
        
        return results
    
    def list_all_tools(self) -> List[ToolResource]:
        """列出所有工具"""
        return list(self._tool_resources.values())
    
    # === 应用关联 ===
    
    def associate_tool_to_app(self, tool_id: str, app_id: str) -> bool:
        """关联工具到应用"""
        if tool_id not in self._tool_resources:
            logger.warning(f"工具不存在: {tool_id}")
            return False
        
        # 添加到tool -> apps映射
        if tool_id not in self._tool_app_associations:
            self._tool_app_associations[tool_id] = []
        if app_id not in self._tool_app_associations[tool_id]:
            self._tool_app_associations[tool_id].append(app_id)
        
        # 添加到app -> tools映射
        if app_id not in self._app_tool_associations:
            self._app_tool_associations[app_id] = []
        if tool_id not in self._app_tool_associations[app_id]:
            self._app_tool_associations[app_id].append(tool_id)
        
        # 更新工具资源的关联信息
        self._tool_resources[tool_id].app_ids = self._tool_app_associations[tool_id].copy()
        
        logger.debug(f"[ToolResourceManager] 关联工具 {tool_id} 到应用 {app_id}")
        return True
    
    def dissociate_tool_from_app(self, tool_id: str, app_id: str) -> bool:
        """解除工具与应用的关联"""
        # 从tool -> apps映射中移除
        if tool_id in self._tool_app_associations:
            self._tool_app_associations[tool_id] = [
                aid for aid in self._tool_app_associations[tool_id] if aid != app_id
            ]
        
        # 从app -> tools映射中移除
        if app_id in self._app_tool_associations:
            self._app_tool_associations[app_id] = [
                tid for tid in self._app_tool_associations[app_id] if tid != tool_id
            ]
        
        # 更新工具资源
        if tool_id in self._tool_resources:
            self._tool_resources[tool_id].app_ids = self._tool_app_associations.get(tool_id, [])
        
        return True
    
    def get_app_tools(self, app_id: str) -> List[ToolResource]:
        """获取应用关联的工具列表"""
        tool_ids = self._app_tool_associations.get(app_id, [])
        return [
            self._tool_resources[tid] 
            for tid in tool_ids 
            if tid in self._tool_resources
        ]
    
    def get_tool_apps(self, tool_id: str) -> List[str]:
        """获取工具关联的应用列表"""
        return self._tool_app_associations.get(tool_id, [])
    
    # === 工具配置 ===
    
    def update_tool_status(self, tool_id: str, status: ToolStatus) -> bool:
        """更新工具状态"""
        if tool_id in self._tool_resources:
            self._tool_resources[tool_id].status = status
            self._tool_resources[tool_id].updated_at = datetime.now()
            return True
        return False
    
    def update_tool_visibility(self, tool_id: str, visibility: ToolVisibility) -> bool:
        """更新工具可见性"""
        if tool_id in self._tool_resources:
            self._tool_resources[tool_id].visibility = visibility
            self._tool_resources[tool_id].updated_at = datetime.now()
            return True
        return False
    
    def set_tool_owner(self, tool_id: str, owner: str) -> bool:
        """设置工具所有者"""
        if tool_id in self._tool_resources:
            self._tool_resources[tool_id].owner = owner
            self._tool_resources[tool_id].updated_at = datetime.now()
            return True
        return False
    
    # === 统计更新 ===
    
    def increment_call_count(self, tool_id: str, success: bool = True) -> None:
        """更新工具调用统计"""
        if tool_id in self._tool_resources:
            self._tool_resources[tool_id].call_count += 1
            if success:
                self._tool_resources[tool_id].success_count += 1


# 全局工具资源管理器
tool_resource_manager = ToolResourceManager()


def get_tool_resource_manager() -> ToolResourceManager:
    """获取工具资源管理器"""
    return tool_resource_manager