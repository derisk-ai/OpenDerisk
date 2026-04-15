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
        1. 无绑定配置 → 默认禁用（只有显式绑定的工具才启用）
        2. 有绑定配置 → 按配置判断 is_bound 且未 disabled_at_runtime
        3. 用户解绑的默认工具 → is_bound=False，不注入
        """
        binding = self.bindings.get(tool_id)
        if not binding:
            # 无绑定配置，默认禁用
            # 这样确保只有显式绑定（默认绑定或用户手动绑定）的工具才会被注入
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

    # 核心必选工具（无论是否沙箱都注入）
    BUILTIN_CORE_TOOLS: List[str] = [
        "ask_user",  # 用户交互（HIL）
    ]

    # 基础文件和Shell工具（沙箱和本地共享，默认绑定）
    # 这些工具根据沙箱状态自动切换执行环境
    BASIC_TOOLS: List[str] = [
        "bash",  # Shell执行（沙箱时委托给 shell_exec）
        "read",  # 文件读取（沙箱时委托给 view）
        "write",  # 文件写入（沙箱时委托给 create_file）
        "edit",  # 文件编辑（沙箱时委托给 edit_file）
        "deliver_file",  # 文件交付（标记为交付物并上传到 OSS）
        "skill_read",  # 读取 Skill 内容（默认注入）
        "skill_exec",  # 执行 Skill 脚本（默认注入）
        "skill_list",  # 列出可用 Skill（默认注入）
    ]

    # 沙箱专属工具（仅沙箱环境可用，需手动绑定）
    SANDBOX_ONLY_TOOLS: List[str] = [
        "download_file",  # 从沙箱下载文件
    ]

    # 向后兼容
    LOCAL_TOOLS: List[str] = ["bash", "read"]
    SANDBOX_TOOLS: List[str] = BASIC_TOOLS + SANDBOX_ONLY_TOOLS
    UNIFIED_TOOLS: List[str] = BASIC_TOOLS

    # 兼容旧代码的别名
    BUILTIN_REQUIRED_TOOLS = BUILTIN_CORE_TOOLS

    # 可选内置工具列表（Agent 可以选择绑定的工具）
    BUILTIN_OPTIONAL_TOOLS: List[str] = [
        "glob",  # 文件搜索
        "grep",  # 文本搜索
        "list_files",  # 列出文件
        "webfetch",  # 网页获取
        "websearch",  # 网络搜索
        "python",  # Python执行
        "knowledge_search",  # 知识库搜索
        "download_file",  # 沙箱下载文件（手动绑定）
        "get_table_spec",  # 数据库表结构查询
        "execute_sql",  # SQL执行
        "list_tables",  # 数据库表列表
    ]

    # 浏览器工具列表（暂不注册，后续按需启用）
    BROWSER_TOOLS: List[str] = []

    # 系统内置动态注入工具（运行时根据条件动态注入的系统工具）
    # 这类工具属于系统核心功能，但只在特定条件下才会被注入（如首次压缩后）
    SYSTEM_DYNAMIC_TOOLS: List[str] = [
        # Layer4 历史回顾工具（首次 compaction 完成后注入）
        "read_history_chapter",  # 读取历史章节
        "search_history",  # 搜索历史
        "get_tool_call_history",  # 获取工具调用历史
        "get_history_overview",  # 获取历史概览
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
        self._load_callback: Optional[Callable[[str, str], Optional[List[str]]]] = None

    def set_persist_callback(self, callback: Callable[[AgentToolConfiguration], bool]):
        """设置配置持久化回调函数"""
        self._persist_callback = callback

    def set_load_callback(self, callback: Callable[[str, str], Optional[List[str]]]):
        """
        设置配置加载回调函数

        回调签名: (app_id, agent_name) -> Optional[List[str]]
        返回持久化的已绑定工具ID列表，或 None 表示无持久化数据
        """
        self._load_callback = callback

    def _get_cache_key(self, app_id: str, agent_name: str) -> str:
        """生成缓存键"""
        return f"{app_id}:{agent_name}"

    def get_tool_groups(
        self,
        app_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        lang: str = "zh",
        sandbox_enabled: bool = False,
    ) -> List[ToolGroup]:
        """
        获取工具分组列表

        Args:
            app_id: 应用ID（用于获取绑定状态）
            agent_name: Agent名称（用于获取绑定状态）
            lang: 语言（zh/en）
            sandbox_enabled: 是否启用沙箱环境（影响 LOCAL_TOOLS 和 SANDBOX_TOOLS 的绑定状态）

        Returns:
            工具分组列表
        """
        # 获取所有工具
        all_tools = tool_registry.list_all()

        # 获取 Agent 的绑定配置（如果提供了 app_id 和 agent_name）
        agent_config = None
        if app_id and agent_name:
            agent_config = self.get_agent_config(
                app_id, agent_name, sandbox_enabled=sandbox_enabled
            )

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
                    tool_info["binding"] = binding.model_dump(mode="json")
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

        # 添加系统动态注入工具（这些工具在运行时动态注入，不在 tool_registry 中）
        for tool_id in self.SYSTEM_DYNAMIC_TOOLS:
            # 检查是否已经在列表中（可能已被注册）
            if any(t.get("tool_id") == tool_id for g in groups.values() for t in g):
                continue

            tool_info = self._create_dynamic_tool_info(tool_id, lang)

            # 系统动态工具归为可选内置工具
            group_type = ToolBindingType.BUILTIN_OPTIONAL

            # 添加绑定状态信息
            if agent_config:
                binding = agent_config.get_binding(tool_id)
                if binding:
                    tool_info["binding"] = binding.model_dump(mode="json")
                    tool_info["is_bound"] = binding.is_bound
                    tool_info["is_default"] = binding.is_default
                    tool_info["can_unbind"] = binding.can_unbind
                else:
                    # 动态工具默认不绑定，需要时再启用
                    tool_info["is_bound"] = False
                    tool_info["is_default"] = False
                    tool_info["can_unbind"] = True
            else:
                # 动态工具默认不绑定
                tool_info["is_bound"] = False
                tool_info["is_default"] = False
                tool_info["can_unbind"] = True

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
        """确定工具属于哪个分组

        基础工具（bash, read, write, edit）归为 BUILTIN_REQUIRED
        沙箱额外功能（download_file, deliver_file）归为 BUILTIN_OPTIONAL
        """
        metadata = tool.metadata

        # 检查是否是核心必选工具
        if tool_id in self.BUILTIN_CORE_TOOLS:
            return ToolBindingType.BUILTIN_REQUIRED

        # 检查是否是基础文件和Shell工具（默认绑定）
        if tool_id in self.BASIC_TOOLS:
            return ToolBindingType.BUILTIN_REQUIRED

        # 检查是否是浏览器工具
        if tool_id in self.BROWSER_TOOLS:
            return ToolBindingType.BUILTIN_OPTIONAL

        # 检查是否是可选内置工具
        if tool_id in self.BUILTIN_OPTIONAL_TOOLS:
            return ToolBindingType.BUILTIN_OPTIONAL

        # 检查是否是系统动态注入工具
        if tool_id in self.SYSTEM_DYNAMIC_TOOLS:
            return ToolBindingType.BUILTIN_OPTIONAL

        # 根据来源判断
        if metadata.source in [ToolSource.CORE, ToolSource.SYSTEM]:
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

        # Handle enum or string values (Pydantic's use_enum_values may convert to string)
        category_val = metadata.category
        if hasattr(category_val, "value"):
            category_val = category_val.value
        elif category_val is None:
            category_val = ""

        source_val = metadata.source
        if hasattr(source_val, "value"):
            source_val = source_val.value
        elif source_val is None:
            source_val = ""

        risk_level_val = metadata.risk_level
        if hasattr(risk_level_val, "value"):
            risk_level_val = risk_level_val.value
        elif risk_level_val is None:
            risk_level_val = "low"

        return {
            "tool_id": metadata.name,
            "name": metadata.name,
            "display_name": metadata.display_name or metadata.name,
            "description": metadata.description,
            "version": metadata.version,
            "category": category_val,
            "subcategory": metadata.subcategory,
            "source": source_val,
            "tags": metadata.tags,
            "risk_level": risk_level_val,
            "requires_permission": metadata.requires_permission,
            "input_schema": tool.parameters,
            "output_schema": metadata.output_schema,
            "examples": [ex.model_dump() for ex in metadata.examples]
            if metadata.examples
            else [],
            "timeout": metadata.timeout,
            "author": metadata.author,
            "doc_url": metadata.doc_url,
        }

    def _create_dynamic_tool_info(
        self, tool_id: str, lang: str = "zh"
    ) -> Dict[str, Any]:
        """
        为动态注入的系统工具创建工具信息

        这些工具不在 tool_registry 中注册，而是运行时动态注入到 agent 中。
        需要手动创建它们的元数据信息。

        Args:
            tool_id: 工具ID
            lang: 语言

        Returns:
            工具信息字典
        """
        # 动态工具的元数据映射
        DYNAMIC_TOOLS_METADATA: Dict[str, Dict[str, Any]] = {
            "read_history_chapter": {
                "display_name": "读取历史章节"
                if lang == "zh"
                else "Read History Chapter",
                "description": (
                    "读取指定历史章节的完整归档内容。"
                    "当你需要回顾之前的操作细节或找回之前的发现时使用此工具。"
                    "章节索引从 0 开始，可通过 get_history_overview 获取所有章节列表。"
                    if lang == "zh"
                    else "Read the full archived content of a specific history chapter. "
                    "Use this when you need to review previous operation details or retrieve past findings. "
                    "Chapter indices start from 0, use get_history_overview to see all chapters."
                ),
                "category": "memory",
                "subcategory": "history",
            },
            "search_history": {
                "display_name": "搜索历史" if lang == "zh" else "Search History",
                "description": (
                    "在所有已归档的历史章节中搜索信息。"
                    "搜索范围包括章节总结、关键决策和工具调用记录。"
                    "当你需要查找之前讨论过的特定主题或做出的决定时使用此工具。"
                    if lang == "zh"
                    else "Search for information across all archived history chapters. "
                    "Search scope includes chapter summaries, key decisions, and tool call records. "
                    "Use this when you need to find specific topics previously discussed or decisions made."
                ),
                "category": "memory",
                "subcategory": "history",
            },
            "get_tool_call_history": {
                "display_name": "获取工具调用历史"
                if lang == "zh"
                else "Get Tool Call History",
                "description": (
                    "获取工具调用历史记录。"
                    "从 WorkLog 中检索工具调用记录，可按工具名称过滤。"
                    if lang == "zh"
                    else "Get tool call history records. "
                    "Retrieve tool call records from WorkLog, can be filtered by tool name."
                ),
                "category": "memory",
                "subcategory": "history",
            },
            "get_history_overview": {
                "display_name": "获取历史概览"
                if lang == "zh"
                else "Get History Overview",
                "description": (
                    "获取历史章节目录概览。"
                    "返回所有已归档章节的列表，包括时间范围、消息数、工具调用数和摘要。"
                    if lang == "zh"
                    else "Get an overview of the history chapter catalog. "
                    "Returns a list of all archived chapters, including time range, message count, "
                    "tool call count, and summary."
                ),
                "category": "memory",
                "subcategory": "history",
            },
        }

        metadata = DYNAMIC_TOOLS_METADATA.get(
            tool_id,
            {
                "display_name": tool_id,
                "description": f"System dynamic tool: {tool_id}",
                "category": "system",
                "subcategory": "dynamic",
            },
        )

        return {
            "tool_id": tool_id,
            "name": tool_id,
            "display_name": metadata["display_name"],
            "description": metadata["description"],
            "version": "1.0.0",
            "category": metadata["category"],
            "subcategory": metadata.get("subcategory", ""),
            "source": "system",  # 系统内置动态工具
            "tags": ["dynamic", "system", "memory"],
            "risk_level": "low",
            "requires_permission": False,
            "input_schema": None,
            "output_schema": None,
            "examples": [],
            "timeout": 30000,
            "author": "system",
            "doc_url": None,
            "is_dynamic": True,  # 标记为动态工具
        }

    def get_agent_config(
        self,
        app_id: str,
        agent_name: str,
        create_if_missing: bool = True,
        sandbox_enabled: bool = False,
    ) -> Optional[AgentToolConfiguration]:
        """
        获取 Agent 的工具配置

        Args:
            app_id: 应用ID
            agent_name: Agent名称
            create_if_missing: 如果不存在是否创建默认配置
            sandbox_enabled: 是否启用沙箱环境（决定注入本地工具还是沙箱工具）

        Returns:
            Agent 工具配置
        """
        cache_key = self._get_cache_key(app_id, agent_name)

        # 先查缓存
        if cache_key in self._config_cache:
            return self._config_cache[cache_key]

        # 从数据库加载配置（通过回调）
        if self._load_callback:
            try:
                persisted_tool_ids = self._load_callback(app_id, agent_name)
                if persisted_tool_ids is not None:
                    config = self._create_config_from_persisted(
                        app_id, agent_name, persisted_tool_ids, sandbox_enabled
                    )
                    self._config_cache[cache_key] = config
                    logger.info(
                        f"[ToolManager] Loaded persisted config for {app_id}:{agent_name}, "
                        f"tools={persisted_tool_ids}"
                    )
                    return config
            except Exception as e:
                logger.warning(f"[ToolManager] Failed to load persisted config: {e}")

        # 创建默认配置
        if create_if_missing:
            config = self._create_default_config(app_id, agent_name, sandbox_enabled)
            self._config_cache[cache_key] = config
            return config

        return None

    def _create_default_config(
        self, app_id: str, agent_name: str, sandbox_enabled: bool = False
    ) -> AgentToolConfiguration:
        """
        创建默认的 Agent 工具配置

        Args:
            app_id: 应用ID
            agent_name: Agent名称
            sandbox_enabled: 是否启用沙箱环境
                基础工具（bash, read, write, edit）无论是否沙箱都默认绑定
                沙箱额外功能（download_file, deliver_file）需要手动绑定
        """
        bindings: Dict[str, ToolBindingConfig] = {}

        # 1. 核心必选工具（无论是否沙箱都注入）
        for tool_id in self.BUILTIN_CORE_TOOLS:
            tool = tool_registry.get(tool_id)
            if tool:
                bindings[tool_id] = ToolBindingConfig(
                    tool_id=tool_id,
                    binding_type=ToolBindingType.BUILTIN_REQUIRED,
                    is_bound=True,
                    is_default=True,
                    can_unbind=True,
                    disabled_at_runtime=False,
                    bound_at=datetime.now(),
                )

        # 2. 基础文件和Shell工具（沙箱和本地共享，默认绑定）
        for tool_id in self.BASIC_TOOLS:
            tool = tool_registry.get(tool_id)
            if tool:
                bindings[tool_id] = ToolBindingConfig(
                    tool_id=tool_id,
                    binding_type=ToolBindingType.BUILTIN_REQUIRED,
                    is_bound=True,
                    is_default=True,
                    can_unbind=True,
                    disabled_at_runtime=False,
                    bound_at=datetime.now(),
                )

        return AgentToolConfiguration(
            app_id=app_id,
            agent_name=agent_name,
            bindings=bindings,
        )

    def _create_config_from_persisted(
        self,
        app_id: str,
        agent_name: str,
        persisted_tool_ids: List[str],
        sandbox_enabled: bool = False,
    ) -> AgentToolConfiguration:
        """
        从持久化的工具ID列表创建配置

        resource_tool 是工具绑定的完整清单（全量数据源）：
        - 在 resource_tool 中的工具 → 已绑定 (is_bound=True)
        - 不在 resource_tool 中的工具 → 未绑定 (is_bound=False，包括默认工具)

        resource_tool 有数据时完全以它为准，不再叠加默认工具。
        这样默认工具的反向解绑才能被持久化。

        Args:
            app_id: 应用ID
            agent_name: Agent名称
            persisted_tool_ids: 持久化的已绑定工具ID列表（完整清单）
            sandbox_enabled: 是否启用沙箱环境
        """
        bindings: Dict[str, ToolBindingConfig] = {}
        persisted_set = set(persisted_tool_ids)

        # 默认工具集合（用于标记 is_default）
        default_tool_ids = set(self.BUILTIN_CORE_TOOLS) | set(self.BASIC_TOOLS)

        # 1. 处理所有已注册的工具
        all_tools = tool_registry.list_all()
        for tool in all_tools:
            tool_id = tool.metadata.name
            group_type = self._determine_tool_group(tool, tool_id)

            is_default_required = group_type == ToolBindingType.BUILTIN_REQUIRED

            # 完全按 persisted_set 判断是否绑定
            # resource_tool 是完整绑定清单，用户解绑的默认工具不在列表中 → is_bound=False
            is_bound = tool_id in persisted_set

            bindings[tool_id] = ToolBindingConfig(
                tool_id=tool_id,
                binding_type=group_type,
                is_bound=is_bound,
                is_default=is_default_required,
                can_unbind=True,
                disabled_at_runtime=False,
                bound_at=datetime.now() if is_bound else None,
            )

        # 2. 处理动态工具（可能不在 registry 中）
        for tool_id in self.SYSTEM_DYNAMIC_TOOLS:
            if tool_id not in bindings:
                is_bound = tool_id in persisted_set
                bindings[tool_id] = ToolBindingConfig(
                    tool_id=tool_id,
                    binding_type=ToolBindingType.BUILTIN_OPTIONAL,
                    is_bound=is_bound,
                    is_default=False,
                    can_unbind=True,
                    disabled_at_runtime=False,
                    bound_at=datetime.now() if is_bound else None,
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

            # 确定分组类型
            if tool:
                group_type = self._determine_tool_group(tool, tool_id)
            elif tool_id in self.SYSTEM_DYNAMIC_TOOLS:
                # 动态工具归为可选内置工具
                group_type = ToolBindingType.BUILTIN_OPTIONAL
            else:
                return False

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
            # 没有配置，只返回默认工具（BUILTIN_CORE + BASIC_TOOLS）
            default_tool_ids = set(self.BUILTIN_CORE_TOOLS) | set(self.BASIC_TOOLS)
            enabled_tools = []
            for tool_id in default_tool_ids:
                tool = tool_registry.get(tool_id)
                if tool:
                    enabled_tools.append(tool)
            return enabled_tools

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
