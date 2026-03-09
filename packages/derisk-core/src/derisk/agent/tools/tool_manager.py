"""
ToolManager - 统一工具分组管理服务

提供工具的分组管理功能：
- 内置默认工具（builtin_required）
- 可选内置工具（builtin_optional）
- 自定义工具（custom）
- 外部工具（external - MCP/API）

支持 Agent 级别的工具绑定配置，包括反向解绑功能。
"""

from typing import Dict, Any, Optional, List, Set, Callable
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from .base import ToolBase, ToolCategory, ToolSource, ToolRiskLevel
from .metadata import ToolMetadata
from .registry import tool_registry

logger = logging.getLogger(__name__)


class ToolBindingType(str, Enum):
    """工具绑定类型"""

    BUILTIN_REQUIRED = "builtin_required"  # 内置默认绑定（必须）
    BUILTIN_OPTIONAL = "builtin_optional"  # 内置可选绑定
    CUSTOM = "custom"  # 自定义工具
    EXTERNAL = "external"  # 外部工具（MCP/API）


class ToolBindingConfig(BaseModel):
    """
    工具绑定配置

    用于存储 Agent 对工具的绑定关系
    """

    tool_id: str = Field(..., description="工具唯一标识")
    binding_type: ToolBindingType = Field(..., description="绑定类型")
    is_bound: bool = Field(True, description="是否已绑定")
    is_default: bool = Field(False, description="是否为默认绑定")
    can_unbind: bool = Field(True, description="是否可解除绑定")
    disabled_at_runtime: bool = Field(False, description="运行时是否禁用")
    bound_at: Optional[datetime] = Field(None, description="绑定时间")
    unbound_at: Optional[datetime] = Field(None, description="解除绑定时间")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")


class ToolGroup(BaseModel):
    """
    工具分组

    用于前端展示的分组结构
    """

    group_id: str = Field(..., description="分组ID")
    group_name: str = Field(..., description="分组显示名称")
    group_type: ToolBindingType = Field(..., description="分组类型")
    description: str = Field("", description="分组描述")
    icon: Optional[str] = Field(None, description="分组图标")
    tools: List[Dict[str, Any]] = Field(default_factory=list, description="工具列表")
    count: int = Field(0, description="工具数量")
    is_collapsible: bool = Field(True, description="是否可折叠")
    default_expanded: bool = Field(True, description="默认是否展开")
    display_order: int = Field(0, description="显示顺序")


class AgentToolConfiguration(BaseModel):
    """
    Agent 工具配置

    存储某个 Agent 的完整工具绑定配置
    """

    app_id: str = Field(..., description="应用ID")
    agent_name: str = Field(..., description="Agent名称")
    bindings: Dict[str, ToolBindingConfig] = Field(
        default_factory=dict, description="工具绑定配置映射 (tool_id -> config)"
    )
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    def get_binding(self, tool_id: str) -> Optional[ToolBindingConfig]:
        """获取指定工具的绑定配置"""
        return self.bindings.get(tool_id)

    def is_tool_enabled(self, tool_id: str) -> bool:
        """
        检查工具是否在运行时启用

        规则：
        1. 如果没有绑定配置，默认启用内置工具
        2. 如果有绑定配置，按配置判断
        3. 如果工具被标记为 disabled_at_runtime，禁用
        """
        binding = self.bindings.get(tool_id)
        if not binding:
            # 默认启用内置工具，禁用外部工具
            tool = tool_registry.get(tool_id)
            if tool and tool.metadata.source in [ToolSource.CORE, ToolSource.SYSTEM]:
                return True
            return False

        return binding.is_bound and not binding.disabled_at_runtime

    def get_enabled_tools(self) -> List[str]:
        """获取所有启用的工具ID列表"""
        enabled = []
        for tool_id, binding in self.bindings.items():
            if binding.is_bound and not binding.disabled_at_runtime:
                enabled.append(tool_id)
        return enabled


class ToolManager:
    """
    统一工具管理器

    职责：
    1. 工具分组管理
    2. Agent 工具绑定配置
    3. 运行时工具加载
    4. 内置工具默认绑定策略
    """

    # 内置默认工具列表（Agent 默认就有的工具）
    BUILTIN_REQUIRED_TOOLS: List[str] = [
        "read",  # 文件读取
        "bash",  # Shell执行
        "question",  # 询问用户
        "terminate",  # 终止会话
    ]

    # 可选内置工具列表（Agent 可以选择绑定的工具）
    BUILTIN_OPTIONAL_TOOLS: List[str] = [
        "write",  # 文件写入
        "edit",  # 文件编辑
        "glob",  # 文件搜索
        "grep",  # 文本搜索
        "webfetch",  # 网页获取
        "websearch",  # 网络搜索
        "python",  # Python执行
        "browser",  # 浏览器工具
        "skill",  # 技能调用
    ]

    # 分组显示配置
    GROUP_CONFIG: Dict[ToolBindingType, Dict[str, Any]] = {
        ToolBindingType.BUILTIN_REQUIRED: {
            "name": "内置默认工具",
            "name_en": "Built-in Default Tools",
            "description": "Agent 默认绑定的核心工具，可反向解除绑定",
            "description_en": "Core tools bound by default, can be unbound",
            "icon": "SafetyOutlined",
            "default_expanded": True,
            "display_order": 1,
        },
        ToolBindingType.BUILTIN_OPTIONAL: {
            "name": "可选内置工具",
            "name_en": "Optional Built-in Tools",
            "description": "可根据需要手动绑定的内置工具",
            "description_en": "Built-in tools that can be manually bound",
            "icon": "ToolOutlined",
            "default_expanded": False,
            "display_order": 2,
        },
        ToolBindingType.CUSTOM: {
            "name": "自定义工具",
            "name_en": "Custom Tools",
            "description": "用户自定义创建的工具",
            "description_en": "Tools created by users",
            "icon": "AppstoreOutlined",
            "default_expanded": True,
            "display_order": 3,
        },
        ToolBindingType.EXTERNAL: {
            "name": "外部工具",
            "name_en": "External Tools",
            "description": "MCP、API 等外部服务工具",
            "description_en": "External service tools (MCP, API)",
            "icon": "CloudServerOutlined",
            "default_expanded": True,
            "display_order": 4,
        },
    }

    def __init__(self):
        self._config_cache: Dict[str, AgentToolConfiguration] = {}
        self._persist_callback: Optional[Callable[[AgentToolConfiguration], bool]] = (
            None
        )

    def set_persist_callback(self, callback: Callable[[AgentToolConfiguration], bool]):
        """设置配置持久化回调函数"""
        self._persist_callback = callback

    def _get_cache_key(self, app_id: str, agent_name: str) -> str:
        """生成缓存键"""
        return f"{app_id}:{agent_name}"

    def get_tool_groups(
        self,
        app_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        lang: str = "zh",
    ) -> List[ToolGroup]:
        """
        获取工具分组列表

        Args:
            app_id: 应用ID（用于获取绑定状态）
            agent_name: Agent名称（用于获取绑定状态）
            lang: 语言（zh/en）

        Returns:
            工具分组列表
        """
        # 获取所有工具
        all_tools = tool_registry.list_all()

        # 获取 Agent 的绑定配置（如果提供了 app_id 和 agent_name）
        agent_config = None
        if app_id and agent_name:
            agent_config = self.get_agent_config(app_id, agent_name)

        # 按分组类型组织工具
        groups: Dict[ToolBindingType, List[Dict[str, Any]]] = {
            ToolBindingType.BUILTIN_REQUIRED: [],
            ToolBindingType.BUILTIN_OPTIONAL: [],
            ToolBindingType.CUSTOM: [],
            ToolBindingType.EXTERNAL: [],
        }

        for tool in all_tools:
            tool_id = tool.metadata.name
            tool_info = self._tool_to_dict(tool, lang)

            # 确定工具的分组类型
            group_type = self._determine_tool_group(tool, tool_id)

            # 添加绑定状态信息
            if agent_config:
                binding = agent_config.get_binding(tool_id)
                if binding:
                    tool_info["binding"] = binding.model_dump()
                    tool_info["is_bound"] = binding.is_bound
                    tool_info["is_default"] = binding.is_default
                    tool_info["can_unbind"] = binding.can_unbind
                else:
                    # 没有绑定配置，使用默认逻辑
                    is_bound = group_type == ToolBindingType.BUILTIN_REQUIRED
                    tool_info["is_bound"] = is_bound
                    tool_info["is_default"] = is_bound
                    tool_info["can_unbind"] = (
                        group_type == ToolBindingType.BUILTIN_REQUIRED
                    )
            else:
                # 没有 Agent 配置，按默认规则
                is_bound = group_type == ToolBindingType.BUILTIN_REQUIRED
                tool_info["is_bound"] = is_bound
                tool_info["is_default"] = is_bound
                tool_info["can_unbind"] = group_type == ToolBindingType.BUILTIN_REQUIRED

            groups[group_type].append(tool_info)

        # 构建 ToolGroup 列表
        result = []
        for group_type in ToolBindingType:
            config = self.GROUP_CONFIG[group_type]
            tools = groups[group_type]

            group = ToolGroup(
                group_id=group_type.value,
                group_name=config["name"] if lang == "zh" else config["name_en"],
                group_type=group_type,
                description=config["description"]
                if lang == "zh"
                else config["description_en"],
                icon=config["icon"],
                tools=tools,
                count=len(tools),
                is_collapsible=True,
                default_expanded=config["default_expanded"],
                display_order=config["display_order"],
            )
            result.append(group)

        # 按显示顺序排序
        result.sort(key=lambda g: g.display_order)

        return result

    def _determine_tool_group(self, tool: ToolBase, tool_id: str) -> ToolBindingType:
        """确定工具属于哪个分组"""
        metadata = tool.metadata

        # 检查是否是内置默认工具
        if tool_id in self.BUILTIN_REQUIRED_TOOLS:
            return ToolBindingType.BUILTIN_REQUIRED

        # 检查是否是可选内置工具
        if tool_id in self.BUILTIN_OPTIONAL_TOOLS:
            return ToolBindingType.BUILTIN_OPTIONAL

        # 根据来源判断
        if metadata.source in [ToolSource.CORE, ToolSource.SYSTEM]:
            # 核心/系统来源但不是默认或可选的，归为可选
            return ToolBindingType.BUILTIN_OPTIONAL

        if metadata.source in [ToolSource.MCP, ToolSource.API]:
            return ToolBindingType.EXTERNAL

        # 用户创建的归为自定义
        if metadata.source == ToolSource.USER:
            return ToolBindingType.CUSTOM

        # 扩展的根据类别判断
        if metadata.source == ToolSource.EXTENSION:
            if metadata.category in [ToolCategory.MCP, ToolCategory.API]:
                return ToolBindingType.EXTERNAL
            return ToolBindingType.CUSTOM

        # 默认归为可选
        return ToolBindingType.BUILTIN_OPTIONAL

    def _tool_to_dict(self, tool: ToolBase, lang: str = "zh") -> Dict[str, Any]:
        """将工具转换为字典格式"""
        metadata = tool.metadata
        return {
            "tool_id": metadata.name,
            "name": metadata.name,
            "display_name": metadata.display_name or metadata.name,
            "description": metadata.description,
            "version": metadata.version,
            "category": metadata.category.value if metadata.category else "",
            "subcategory": metadata.subcategory,
            "source": metadata.source.value if metadata.source else "",
            "tags": metadata.tags,
            "risk_level": metadata.risk_level.value if metadata.risk_level else "low",
            "requires_permission": metadata.requires_permission,
            "input_schema": metadata.input_schema,
            "output_schema": metadata.output_schema,
            "examples": [ex.model_dump() for ex in metadata.examples]
            if metadata.examples
            else [],
            "timeout": metadata.timeout,
            "author": metadata.author,
            "doc_url": metadata.doc_url,
        }

    def get_agent_config(
        self, app_id: str, agent_name: str, create_if_missing: bool = True
    ) -> Optional[AgentToolConfiguration]:
        """
        获取 Agent 的工具配置

        Args:
            app_id: 应用ID
            agent_name: Agent名称
            create_if_missing: 如果不存在是否创建默认配置

        Returns:
            Agent 工具配置
        """
        cache_key = self._get_cache_key(app_id, agent_name)

        # 先查缓存
        if cache_key in self._config_cache:
            return self._config_cache[cache_key]

        # TODO: 从数据库加载配置
        # 这里先创建默认配置
        if create_if_missing:
            config = self._create_default_config(app_id, agent_name)
            self._config_cache[cache_key] = config
            return config

        return None

    def _create_default_config(
        self, app_id: str, agent_name: str
    ) -> AgentToolConfiguration:
        """创建默认的 Agent 工具配置"""
        bindings: Dict[str, ToolBindingConfig] = {}

        # 为内置默认工具创建绑定配置
        for tool_id in self.BUILTIN_REQUIRED_TOOLS:
            tool = tool_registry.get(tool_id)
            if tool:
                bindings[tool_id] = ToolBindingConfig(
                    tool_id=tool_id,
                    binding_type=ToolBindingType.BUILTIN_REQUIRED,
                    is_bound=True,
                    is_default=True,
                    can_unbind=True,  # 允许反向解绑
                    disabled_at_runtime=False,
                    bound_at=datetime.now(),
                )

        return AgentToolConfiguration(
            app_id=app_id,
            agent_name=agent_name,
            bindings=bindings,
        )

    def update_tool_binding(
        self,
        app_id: str,
        agent_name: str,
        tool_id: str,
        is_bound: bool,
        disabled_at_runtime: Optional[bool] = None,
    ) -> bool:
        """
        更新工具绑定状态

        Args:
            app_id: 应用ID
            agent_name: Agent名称
            tool_id: 工具ID
            is_bound: 是否绑定
            disabled_at_runtime: 运行时是否禁用

        Returns:
            是否成功
        """
        config = self.get_agent_config(app_id, agent_name)
        if not config:
            return False

        existing = config.bindings.get(tool_id)
        if existing:
            # 更新现有配置
            existing.is_bound = is_bound
            if disabled_at_runtime is not None:
                existing.disabled_at_runtime = disabled_at_runtime
            if not is_bound:
                existing.unbound_at = datetime.now()
        else:
            # 创建新配置
            tool = tool_registry.get(tool_id)
            if not tool:
                return False

            group_type = self._determine_tool_group(tool, tool_id)
            config.bindings[tool_id] = ToolBindingConfig(
                tool_id=tool_id,
                binding_type=group_type,
                is_bound=is_bound,
                is_default=False,
                can_unbind=True,
                disabled_at_runtime=disabled_at_runtime or False,
                bound_at=datetime.now() if is_bound else None,
            )

        config.updated_at = datetime.now()

        # 持久化配置
        if self._persist_callback:
            self._persist_callback(config)

        return True

    def get_runtime_tools(self, app_id: str, agent_name: str) -> List[ToolBase]:
        """
        获取运行时工具列表

        根据 Agent 的配置，返回实际可用的工具列表

        Args:
            app_id: 应用ID
            agent_name: Agent名称

        Returns:
            可用的工具列表
        """
        config = self.get_agent_config(app_id, agent_name)
        if not config:
            # 没有配置，返回所有内置工具
            return [
                tool
                for tool in tool_registry.list_all()
                if tool.metadata.source in [ToolSource.CORE, ToolSource.SYSTEM]
            ]

        enabled_tools = []
        all_tools = tool_registry.list_all()

        for tool in all_tools:
            tool_id = tool.metadata.name
            if config.is_tool_enabled(tool_id):
                enabled_tools.append(tool)

        return enabled_tools

    def get_runtime_tool_schemas(
        self, app_id: str, agent_name: str, format_type: str = "openai"
    ) -> List[Dict[str, Any]]:
        """
        获取运行时工具 Schema 列表

        Args:
            app_id: 应用ID
            agent_name: Agent名称
            format_type: 格式类型（openai/anthropic）

        Returns:
            工具 Schema 列表
        """
        tools = self.get_runtime_tools(app_id, agent_name)

        if format_type == "openai":
            return [tool.to_openai_tool() for tool in tools]
        elif format_type == "anthropic":
            return [tool.to_anthropic_tool() for tool in tools]
        else:
            return [tool.metadata.model_dump() for tool in tools]

    def clear_cache(
        self, app_id: Optional[str] = None, agent_name: Optional[str] = None
    ):
        """清除配置缓存"""
        if app_id and agent_name:
            cache_key = self._get_cache_key(app_id, agent_name)
            self._config_cache.pop(cache_key, None)
        elif app_id:
            # 清除该应用下所有 Agent 的配置
            keys_to_remove = [
                k for k in self._config_cache.keys() if k.startswith(f"{app_id}:")
            ]
            for k in keys_to_remove:
                self._config_cache.pop(k, None)
        else:
            self._config_cache.clear()


# 全局工具管理器实例
tool_manager = ToolManager()


def get_tool_manager() -> ToolManager:
    """获取全局工具管理器实例"""
    return tool_manager
