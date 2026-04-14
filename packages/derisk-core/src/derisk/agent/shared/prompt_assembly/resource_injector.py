"""
ResourceInjector - 资源注入器

提供统一的资源注入接口，支持 core_v1 和 core_v2 两种架构。

资源类型：
1. Sandbox - 沙箱环境
2. Agents - 子 Agent
3. Knowledge - 知识库
4. Skills - 技能
5. Tools - 工具
6. Database - 数据库
7. Custom - 自定义资源

设计原则：
- 架构无关：通过 ResourceContext 抽象不同架构的差异
- 可扩展：支持自定义资源类型和注入逻辑
- 异步优先：所有注入操作都是异步的
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING, runtime_checkable

from .prompt_registry import get_registry, PromptTemplate

if TYPE_CHECKING:
    from derisk.agent.resource import (
        AppResource,
        RetrieverResource,
        AgentSkillResource,
    )

logger = logging.getLogger(__name__)


class ResourceType(str, Enum):
    """资源类型

    对应 derisk.agent.resource.base.ResourceType:
    - SANDBOX: 沙箱环境（特殊资源，不在 base.ResourceType 中）
    - AGENTS: 子 Agent (App)
    - KNOWLEDGE: 知识库 (Knowledge)
    - SKILLS: 技能 (AgentSkill)
    - TOOLS: 工具 (Tool, Plugin)
    - DATABASE: 数据库 (DB)
    - INTERNET: 互联网搜索
    - WORKFLOW: 工作流
    - REASONING_ENGINE: 推理引擎
    - MEMORY: 记忆
    - DOCUMENT: 文档
    - CUSTOM: 自定义资源
    """

    SANDBOX = "sandbox"
    AGENTS = "agents"
    KNOWLEDGE = "knowledge"
    SKILLS = "skills"
    TOOLS = "tools"
    DATABASE = "database"
    INTERNET = "internet"
    WORKFLOW = "workflow"
    REASONING_ENGINE = "reasoning_engine"
    MEMORY = "memory"
    DOCUMENT = "document"
    CUSTOM = "custom"


@dataclass
class ResourceInfo:
    """资源信息"""

    resource_type: ResourceType
    code: str  # 唯一标识
    name: str
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.resource_type.value,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            **self.metadata,
        }


@dataclass
class ResourceContext:
    """
    资源上下文 - 抽象不同架构的资源获取方式

    支持两种架构：
    1. core_v1 (expand/react_master_agent): 使用 resource_map, sandbox_manager 等
    2. core_v2: 使用 resource, resource_map, sandbox_manager 等

    使用方式：
        # core_v1 架构
        ctx = ResourceContext.from_v1_agent(agent)

        # core_v2 架构
        ctx = ResourceContext.from_v2_agent(agent)
    """

    # 资源映射
    resource_map: Dict[str, List[Any]] = field(default_factory=dict)

    # 沙箱管理器
    sandbox_manager: Optional[Any] = None

    # Agent 引用（用于注入工具等）
    agent: Optional[Any] = None

    # 架构版本
    architecture: str = "v1"  # "v1" or "v2"

    # 缓存的资源信息
    _cached_resources: Dict[ResourceType, List[ResourceInfo]] = field(
        default_factory=dict
    )

    @classmethod
    def from_v1_agent(cls, agent: Any) -> "ResourceContext":
        """从 core_v1 Agent 创建上下文"""
        resource_map = getattr(agent, "resource_map", {}) or {}
        sandbox_manager = getattr(agent, "sandbox_manager", None)
        logger.info(
            f"ResourceContext.from_v1_agent: sandbox_manager={sandbox_manager is not None}, "
            f"resource_map_keys={list(resource_map.keys()) if resource_map else []}"
        )
        return cls(
            resource_map=resource_map,
            sandbox_manager=sandbox_manager,
            agent=agent,
            architecture="v1",
        )

    @classmethod
    def from_v2_agent(cls, agent: Any) -> "ResourceContext":
        """从 core_v2 Agent 创建上下文"""
        resource_map = getattr(agent, "resource_map", {}) or {}
        sandbox_manager = getattr(agent, "sandbox_manager", None)

        # core_v2 可能还有 resource 属性
        if not resource_map and hasattr(agent, "resource"):
            resource = getattr(agent, "resource", None)
            if resource:
                resource_map = {"default": [resource]}

        return cls(
            resource_map=resource_map,
            sandbox_manager=sandbox_manager,
            agent=agent,
            architecture="v2",
        )

    def get_resources(self, resource_type: ResourceType) -> List[ResourceInfo]:
        """获取指定类型的资源信息"""
        if resource_type in self._cached_resources:
            return self._cached_resources[resource_type]

        resources = self._extract_resources(resource_type)
        self._cached_resources[resource_type] = resources
        return resources

    def _extract_resources(self, resource_type: ResourceType) -> List[ResourceInfo]:
        """提取资源信息"""
        if resource_type == ResourceType.SANDBOX:
            return self._extract_sandbox()
        elif resource_type == ResourceType.AGENTS:
            return self._extract_agents()
        elif resource_type == ResourceType.KNOWLEDGE:
            return self._extract_knowledge()
        elif resource_type == ResourceType.SKILLS:
            return self._extract_skills()
        elif resource_type == ResourceType.DATABASE:
            return self._extract_database()
        elif resource_type == ResourceType.CUSTOM:
            return self._extract_custom()
        else:
            return []

    def _extract_sandbox(self) -> List[ResourceInfo]:
        """提取沙箱资源"""
        logger.info(
            f"_extract_sandbox: sandbox_manager={self.sandbox_manager is not None}"
        )
        if not self.sandbox_manager:
            return []

        sandbox_prompt = ""
        if hasattr(self.sandbox_manager, "prompt"):
            sandbox_prompt = getattr(self.sandbox_manager, "prompt", "") or ""

        work_dir = "/workspace"
        if hasattr(self.sandbox_manager, "work_dir"):
            work_dir = getattr(self.sandbox_manager, "work_dir", work_dir)
        elif hasattr(self.sandbox_manager, "client") and self.sandbox_manager.client:
            client = self.sandbox_manager.client
            if hasattr(client, "work_dir"):
                work_dir = getattr(client, "work_dir", work_dir)

        skill_dir = ""
        if hasattr(self.sandbox_manager, "client") and self.sandbox_manager.client:
            client = self.sandbox_manager.client
            if hasattr(client, "skill_dir"):
                skill_dir = getattr(client, "skill_dir", "")

        agent_skill_dir = "/home/ubuntu/.derisk/skills"
        if hasattr(self.sandbox_manager, "agent_skill_dir"):
            agent_skill_dir = getattr(
                self.sandbox_manager, "agent_skill_dir", agent_skill_dir
            )

        logger.info(
            f"_extract_sandbox: extracted work_dir={work_dir}, "
            f"skill_dir={skill_dir}, agent_skill_dir={agent_skill_dir}, "
            f"prompt_length={len(sandbox_prompt)}"
        )

        return [
            ResourceInfo(
                resource_type=ResourceType.SANDBOX,
                code="default_sandbox",
                name="Sandbox Environment",
                description=sandbox_prompt[:200]
                if sandbox_prompt
                else "Sandbox execution environment",
                metadata={
                    "prompt": sandbox_prompt,
                    "work_dir": work_dir,
                    "skill_dir": skill_dir,
                    "agent_skill_dir": agent_skill_dir,
                },
            )
        ]

    def _extract_agents(self) -> List[ResourceInfo]:
        """提取子 Agent 资源"""
        resources = []

        for key, value_list in self.resource_map.items():
            for item in value_list or []:
                # 检查是否是 AppResource
                if self._is_app_resource(item):
                    info = self._extract_agent_info(item)
                    if info:
                        resources.append(info)

        return resources

    def _extract_knowledge(self) -> List[ResourceInfo]:
        """提取知识库资源"""
        resources = []

        for key, value_list in self.resource_map.items():
            for item in value_list or []:
                if self._is_retriever_resource(item):
                    infos = self._extract_knowledge_infos(item)
                    resources.extend(infos)

        return resources

    def _extract_skills(self) -> List[ResourceInfo]:
        """提取技能资源"""
        resources = []

        for key, value_list in self.resource_map.items():
            for item in value_list or []:
                if self._is_skill_resource(item):
                    info = self._extract_skill_info(item)
                    if info:
                        resources.append(info)

        return resources

    def _extract_database(self) -> List[ResourceInfo]:
        """提取数据库资源"""
        resources = []

        logger.info(
            f"_extract_database: resource_map_keys={list(self.resource_map.keys()) if self.resource_map else []}"
        )

        for key, value_list in self.resource_map.items():
            for item in value_list or []:
                class_name = item.__class__.__name__ if item else "None"
                logger.debug(f"_extract_database: checking key={key}, class={class_name}")

                if self._is_database_resource(item):
                    logger.info(f"_extract_database: found database resource, key={key}, class={class_name}")
                    info = self._extract_database_info(item, key)
                    if info:
                        resources.append(info)
                        logger.info(
                            f"_extract_database: extracted db_name={info.metadata.get('db_name')}, "
                            f"db_type={info.metadata.get('db_type')}"
                        )
                else:
                    logger.debug(f"_extract_database: not a database resource, key={key}, class={class_name}")

        logger.info(f"_extract_database: total database resources found={len(resources)}")
        return resources

    def _extract_custom(self) -> List[ResourceInfo]:
        """提取自定义资源（如 open_rca_scene 等用户选择的场景资源）

        自定义资源是指通过 chat_in_params 传入的、不属于 SANDBOX/AGENTS/KNOWLEDGE/SKILLS/DATABASE
        的资源类型。这些资源会被注入到 system prompt 的 other_resources 部分。
        """
        resources = []

        # 排除已处理的资源类型
        excluded_types = (
            "AppResource",
            "AgentSkillResource",
            "RetrieverResource",
            "KnowledgeResource",
            "SkillResource",
            "BaseTool",
            "MCPToolPack",
            "ToolResource",
            "DBResource",
            "DatabaseResource",
            "RDBMSConnectorResource",
            "SQLiteDBResource",
        )

        for key, value_list in self.resource_map.items():
            for item in value_list or []:
                # 检查是否是已排除的资源类型
                class_name = item.__class__.__name__ if item else ""
                is_excluded = any(excluded in class_name for excluded in excluded_types)

                # 检查是否是已知的特殊资源类型
                is_app = self._is_app_resource(item)
                is_skill = self._is_skill_resource(item)
                is_knowledge = self._is_retriever_resource(item)
                is_database = self._is_database_resource(item)

                # 如果不是已排除或已知类型，则作为自定义资源处理
                if not is_excluded and not is_app and not is_skill and not is_knowledge and not is_database:
                    info = self._extract_custom_info(item, key)
                    if info:
                        resources.append(info)

        return resources

    # ==================== 资源类型检测 ====================

    def _is_app_resource(self, item: Any) -> bool:
        """检查是否是 AppResource"""
        # 尝试多种方式检测
        if hasattr(item, "app_code") and hasattr(item, "app_name"):
            return True
        # 检查类名
        class_name = item.__class__.__name__ if item else ""
        return "AppResource" in class_name or "AgentResource" in class_name

    def _is_retriever_resource(self, item: Any) -> bool:
        """检查是否是 RetrieverResource"""
        if hasattr(item, "knowledge_spaces"):
            return True
        class_name = item.__class__.__name__ if item else ""
        return "RetrieverResource" in class_name or "KnowledgeResource" in class_name

    def _is_skill_resource(self, item: Any) -> bool:
        """检查是否是 SkillResource"""
        if hasattr(item, "skill_meta"):
            return True
        class_name = item.__class__.__name__ if item else ""
        return "SkillResource" in class_name or "AgentSkillResource" in class_name

    def _is_database_resource(self, item: Any) -> bool:
        """检查是否是 DatabaseResource (DBResource)"""
        if item is None:
            return False

        # 检查是否有数据库特有的属性
        if hasattr(item, "db_name") or hasattr(item, "db_type"):
            logger.debug(f"_is_database_resource: detected by db_name/db_type attr, class={item.__class__.__name__}")
            return True

        # 检查 type() 方法返回值
        try:
            r_type = item.type()
            if isinstance(r_type, str):
                if r_type == "database" or r_type == "DB":
                    logger.debug(f"_is_database_resource: detected by type()='{r_type}', class={item.__class__.__name__}")
                    return True
            elif hasattr(r_type, "value"):
                if r_type.value == "database":
                    logger.debug(f"_is_database_resource: detected by type().value='database', class={item.__class__.__name__}")
                    return True
        except Exception:
            pass

        # 检查类名
        class_name = item.__class__.__name__ if item else ""
        is_db = (
            "DBResource" in class_name
            or "DatabaseResource" in class_name
            or "RDBMSConnectorResource" in class_name
            or "SQLiteDBResource" in class_name
        )
        if is_db:
            logger.debug(f"_is_database_resource: detected by class name '{class_name}'")
        return is_db

    # ==================== 资源信息提取 ====================

    def _extract_agent_info(self, item: Any) -> Optional[ResourceInfo]:
        """提取 Agent 信息"""
        try:
            return ResourceInfo(
                resource_type=ResourceType.AGENTS,
                code=getattr(item, "app_code", "") or "",
                name=getattr(item, "app_name", "") or "",
                description=getattr(item, "app_desc", "") or "",
            )
        except Exception as e:
            logger.warning(f"Failed to extract agent info: {e}")
            return None

    def _extract_knowledge_infos(self, item: Any) -> List[ResourceInfo]:
        """提取知识库信息列表"""
        infos = []
        try:
            knowledge_spaces = getattr(item, "knowledge_spaces", []) or []
            for space in knowledge_spaces:
                infos.append(
                    ResourceInfo(
                        resource_type=ResourceType.KNOWLEDGE,
                        code=getattr(space, "knowledge_id", "") or "",
                        name=getattr(space, "name", "") or "",
                        description=getattr(space, "desc", "") or "",
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to extract knowledge info: {e}")
        return infos

    def _extract_skill_info(self, item: Any) -> Optional[ResourceInfo]:
        """提取技能信息"""
        try:
            # 获取模式和分支
            mode, branch = "release", "master"
            debug_info = getattr(item, "debug_info", None)
            if debug_info and isinstance(debug_info, dict):
                if debug_info.get("is_debug"):
                    mode, branch = "debug", debug_info.get("branch", "master")

            # 获取元数据
            meta = item.skill_meta(mode) if hasattr(item, "skill_meta") else None
            if not meta:
                return None

            # Get skill_code (UUID or directory name)
            skill_code = (
                getattr(item, "_skill_code", None)
                or getattr(item, "skill_code", None)
                or ""
            )
            if not skill_code and hasattr(meta, "path") and meta.path:
                import os

                skill_code = os.path.basename(meta.path)

            # Determine skill path based on sandbox status
            skill_path = ""
            sandbox_enabled = False
            sandbox_skill_dir = ""

            if self.sandbox_manager:
                sb_client = getattr(self.sandbox_manager, "client", None)
                if sb_client:
                    sandbox_enabled = True
                    sandbox_skill_dir = getattr(sb_client, "skill_dir", "") or ""

            import os
            from derisk.agent.expand.react_master_agent.react_master_agent import (
                DATA_DIR,
            )

            if sandbox_enabled and sandbox_skill_dir and skill_code:
                # Sandbox mode: use absolute path in sandbox
                skill_path = os.path.join(sandbox_skill_dir, skill_code)
            elif skill_code:
                # Local mode: use absolute path locally
                local_skill_dir = os.path.join(DATA_DIR, "skill")
                skill_path = os.path.join(local_skill_dir, skill_code)
            else:
                # Fallback to meta path
                skill_path = getattr(meta, "path", "") or ""

            return ResourceInfo(
                resource_type=ResourceType.SKILLS,
                code=getattr(meta, "name", "") or "",
                name=getattr(meta, "name", "") or "",
                description=getattr(meta, "description", "") or "",
                metadata={
                    "path": skill_path,
                    "branch": branch,
                    "mode": mode,
                    "sandbox_enabled": sandbox_enabled,
                    "sandbox_skill_dir": sandbox_skill_dir if sandbox_enabled else "",
                },
            )
        except Exception as e:
            logger.warning(f"Failed to extract skill info: {e}")
            return None

    def _extract_database_info(self, item: Any, key: str) -> Optional[ResourceInfo]:
        """提取数据库资源信息"""
        try:
            # 获取数据库基本信息
            db_name = getattr(item, "_db_name", None) or getattr(item, "db_name", "") or ""
            db_type = getattr(item, "_db_type", None) or getattr(item, "db_type", "") or ""
            dialect = getattr(item, "_dialect", None) or getattr(item, "dialect", "") or db_type
            name = getattr(item, "name", "") or db_name or key

            # 获取 datasource_id (用于分级注入策略)
            datasource_id = getattr(item, "_datasource_id", None)

            logger.info(
                f"_extract_database_info: extracting from item, key={key}, "
                f"db_name={db_name}, db_type={db_type}, dialect={dialect}, name={name}, "
                f"datasource_id={datasource_id}"
            )

            # 获取 connector 信息（如果有）
            connector = getattr(item, "_connector", None) or getattr(item, "connector", None)
            connector_type = ""
            db_version = None
            if connector:
                connector_type = getattr(connector, "db_type", "") or ""
                # 获取数据库版本
                if hasattr(connector, "get_db_version"):
                    try:
                        db_version = connector.get_db_version()
                    except Exception as e:
                        logger.debug(f"Failed to get db version: {e}")
                logger.debug(f"_extract_database_info: found connector, connector_type={connector_type}, version={db_version}")

            # 组合描述信息
            description = f"{db_type} database: {db_name}"
            if dialect and dialect != db_type:
                description += f" (dialect: {dialect})"
            if db_version:
                description += f" [version: {db_version}]"

            return ResourceInfo(
                resource_type=ResourceType.DATABASE,
                code=db_name or key,
                name=name,
                description=description,
                metadata={
                    "db_name": db_name,
                    "db_type": db_type or connector_type,
                    "dialect": dialect or db_type or connector_type,
                    "connector_type": connector_type,
                    "db_version": db_version,  # 添加版本信息
                    "datasource_id": datasource_id,  # 用于分级注入策略
                    # 保存原始资源引用，用于获取表列表
                    "_resource": item,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to extract database info for {key}: {e}")
            return None

    def _extract_custom_info(self, item: Any, key: str) -> Optional[ResourceInfo]:
        """提取自定义资源信息"""
        try:
            resource_type_str = key
            if hasattr(item, "type"):
                r_type = item.type()
                if isinstance(r_type, str):
                    resource_type_str = r_type
                elif hasattr(r_type, "value"):
                    resource_type_str = r_type.value

            name = getattr(item, "name", "") or key
            description = (
                getattr(item, "scene_description", "")
                or getattr(item, "description", "")
                or ""
            )

            metadata = {"resource_type": resource_type_str}
            for attr in ["scene", "scene_name", "data_path", "scene_schema"]:
                if hasattr(item, attr):
                    val = getattr(item, attr, None)
                    if val:
                        metadata[attr] = val

            return ResourceInfo(
                resource_type=ResourceType.CUSTOM,
                code=key,
                name=name,
                description=description,
                metadata=metadata,
            )
        except Exception as e:
            logger.warning(f"Failed to extract custom resource info for {key}: {e}")
            return None


@runtime_checkable
class ResourceInjectorProtocol(Protocol):
    """资源注入器协议"""

    async def inject_sandbox(self, ctx: ResourceContext) -> Optional[str]:
        """注入沙箱资源"""
        ...

    async def inject_agents(self, ctx: ResourceContext) -> Optional[str]:
        """注入 Agent 资源"""
        ...

    async def inject_knowledge(self, ctx: ResourceContext) -> Optional[str]:
        """注入知识库资源"""
        ...

    async def inject_skills(self, ctx: ResourceContext) -> Optional[str]:
        """注入技能资源"""
        ...

    async def inject_database(self, ctx: ResourceContext) -> Optional[str]:
        """注入数据库资源"""
        ...

    async def inject_all(self, ctx: ResourceContext) -> str:
        """注入所有资源"""
        ...


class ResourceInjector:
    """
    资源注入器

    负责从 ResourceContext 提取资源信息并生成对应的 Prompt 内容。

    用法：
        injector = ResourceInjector()
        ctx = ResourceContext.from_v1_agent(agent)

        # 注入单个资源
        sandbox_prompt = await injector.inject_sandbox(ctx)

        # 注入所有资源
        all_resources = await injector.inject_all(ctx)
    """

    def __init__(
        self,
        use_templates: bool = True,
        custom_templates: Optional[Dict[ResourceType, str]] = None,
    ):
        """
        初始化

        Args:
            use_templates: 是否使用模板注册表中的模板
            custom_templates: 自定义模板映射 {资源类型: 模板内容}
        """
        self.use_templates = use_templates
        self.custom_templates = custom_templates or {}
        self.registry = get_registry()

    async def inject_sandbox(self, ctx: ResourceContext) -> Optional[str]:
        """注入沙箱资源"""
        resources = ctx.get_resources(ResourceType.SANDBOX)
        logger.info(f"inject_sandbox: resources_count={len(resources)}")
        if not resources:
            return None

        resource = resources[0]
        sandbox_prompt = resource.metadata.get("prompt", "")
        work_dir = resource.metadata.get("work_dir", "/workspace")
        skill_dir = resource.metadata.get("skill_dir", "")
        agent_skill_dir = resource.metadata.get(
            "agent_skill_dir", "/home/ubuntu/.derisk/skills"
        )
        use_agent_skill = len(ctx.get_resources(ResourceType.SKILLS)) > 0

        system_info = self._get_system_info(work_dir)

        logger.info(
            f"inject_sandbox: rendering template with "
            f"sandbox_enable=True, work_dir={work_dir}, "
            f"skill_dir={skill_dir}, system_info={system_info}, "
            f"use_agent_skill={use_agent_skill}, agent_skill_dir={agent_skill_dir}"
        )

        template = self._get_template(ResourceType.SANDBOX)
        if template:
            result = template.render(
                sandbox_enable=True,
                work_dir=work_dir,
                skill_dir=skill_dir,
                system_info=system_info,
                agent_skill_dir=agent_skill_dir,
                use_agent_skill=use_agent_skill,
                sandbox_prompt=sandbox_prompt,
                sandbox=resource.to_dict(),
            )
            logger.info(
                f"inject_sandbox: template rendered, result_length={len(result) if result else 0}"
            )
            return result

        return self._format_sandbox_default(resource)

    def _get_system_info(self, work_dir: str) -> str:
        """Get system info based on work_dir pattern to detect sandbox type."""
        import platform

        if not work_dir:
            return (
                "Ubuntu 24.04 linux/amd64（已联网），用户：ubuntu（拥有免密 sudo 权限）"
            )

        work_dir_lower = work_dir.lower()
        if "/pilot/data/" in work_dir_lower or "derisk" in work_dir_lower:
            system = platform.system()
            if system == "Darwin":
                return (
                    f"macOS ({platform.processor()}), 本地沙箱环境，路径映射到项目目录"
                )
            elif system == "Linux":
                return (
                    f"Linux ({platform.processor()}), 本地沙箱环境，路径映射到项目目录"
                )
            elif system == "Windows":
                return f"Windows, 本地沙箱环境，路径映射到项目目录"
            else:
                return f"{system}, 本地沙箱环境，路径映射到项目目录"

        return "Ubuntu 24.04 linux/amd64（已联网），用户：ubuntu（拥有免密 sudo 权限）"

    async def inject_agents(self, ctx: ResourceContext) -> Optional[str]:
        """注入 Agent 资源"""
        resources = ctx.get_resources(ResourceType.AGENTS)
        if not resources:
            return None

        template = self._get_template(ResourceType.AGENTS)
        if template:
            agents = [r.to_dict() for r in resources]
            return template.render(agents=agents)

        return self._format_agents_default(resources)

    async def inject_knowledge(self, ctx: ResourceContext) -> Optional[str]:
        """注入知识库资源"""
        resources = ctx.get_resources(ResourceType.KNOWLEDGE)
        if not resources:
            return None

        template = self._get_template(ResourceType.KNOWLEDGE)
        if template:
            knowledges = [r.to_dict() for r in resources]
            return template.render(knowledges=knowledges)

        return self._format_knowledge_default(resources)

    async def inject_skills(self, ctx: ResourceContext) -> Optional[str]:
        """注入技能资源"""
        resources = ctx.get_resources(ResourceType.SKILLS)
        if not resources:
            return None

        template = self._get_template(ResourceType.SKILLS)
        if template:
            skills = [r.to_dict() for r in resources]
            return template.render(skills=skills)

        return self._format_skills_default(resources)

    async def inject_database(self, ctx: ResourceContext) -> Optional[str]:
        """注入数据库资源

        注入内容包括：
        1. 数据库基本信息（名称、类型、方言）
        2. 表列表（从 DBResource.get_prompt 或 spec_service 获取）
        3. 使用说明
        """
        resources = ctx.get_resources(ResourceType.DATABASE)
        logger.info(f"inject_database: resources_count={len(resources)}")
        if not resources:
            return None

        # 获取每个数据库的详细信息（包含表列表）
        databases_with_tables = []
        for r in resources:
            db_dict = r.to_dict()
            # 移除内部引用，不传给模板
            db_dict.pop("_resource", None)

            # 获取表列表
            table_list = await self._get_database_table_list(r)
            db_dict["table_list"] = table_list
            databases_with_tables.append(db_dict)

        template = self._get_template(ResourceType.DATABASE)
        if template:
            return template.render(databases=databases_with_tables)

        return self._format_database_default(resources, databases_with_tables)

    async def _get_database_table_list(self, resource_info: ResourceInfo) -> str:
        """获取数据库的表列表 - 应用分级策略

        策略：
        - <100 tables: 完整列表（含摘要）
        - 100-500 tables: 紧凑列表（仅名称）
        - >500 tables: 统计信息 + 工具指引
        """
        db_name = resource_info.metadata.get("db_name", "")
        original_resource = resource_info.metadata.get("_resource")
        datasource_id = resource_info.metadata.get("datasource_id")

        # Try to import config for tiered strategy
        try:
            from derisk_serve.datasource.service.injection_config import (
                get_injection_mode,
                INJECTION_MODE_SMALL,
                INJECTION_MODE_MEDIUM,
                INJECTION_MODE_LARGE,
                MAX_MEDIUM_TABLE_DISPLAY,
                LARGE_DB_GUIDANCE_TEMPLATE,
                format_group_stats,
            )
            use_tiered = True
        except ImportError:
            use_tiered = False
            logger.debug("injection_config not available, using legacy mode")

        # Resolve datasource_id if not in metadata
        if not datasource_id:
            try:
                from derisk_serve.datasource.manages.connect_config_db import ConnectConfigDao
                dao = ConnectConfigDao()
                entity = dao.get_by_names(db_name)
                if entity:
                    datasource_id = entity.id
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"Failed to resolve datasource_id for {db_name}: {e}")

        # Apply tiered strategy if config available and datasource_id resolved
        if use_tiered and datasource_id:
            try:
                from derisk_serve.datasource.service.spec_service import DbSpecService
                spec_service = DbSpecService()

                # Get table stats
                stats = spec_service.get_db_stats(datasource_id)
                table_count = stats.get("total_tables", 0)
                injection_mode = get_injection_mode(table_count)

                logger.info(
                    f"_get_database_table_list: db={db_name}, "
                    f"tables={table_count}, mode={injection_mode}"
                )

                # Large DB: stats + guidance
                if injection_mode == INJECTION_MODE_LARGE:
                    table_list = spec_service.format_db_spec_for_prompt(
                        datasource_id, mode="large"
                    )
                    guidance = LARGE_DB_GUIDANCE_TEMPLATE.format(
                        total_tables=table_count,
                        group_stats=format_group_stats(stats.get("groups", {})),
                        db_name=db_name,
                    )
                    return table_list + "\n\n" + guidance

                # Medium DB: compact list
                elif injection_mode == INJECTION_MODE_MEDIUM:
                    if spec_service.has_spec(datasource_id):
                        return spec_service.format_db_spec_for_prompt(
                            datasource_id, mode="medium",
                            max_tables=MAX_MEDIUM_TABLE_DISPLAY
                        )

                # Small DB: full list (continue to legacy flow)
            except Exception as e:
                logger.warning(f"Tiered strategy failed for {db_name}: {e}")

        # Legacy flow: full table list
        return await self._get_database_table_list_legacy(resource_info)

    async def _get_database_table_list_legacy(self, resource_info: ResourceInfo) -> str:
        """获取数据库的表列表 - 传统方式（完整列表）

        优先级：
        1. 从 DBResource.get_prompt() 获取（包含表结构定义）
        2. 从 spec_service 获取表概览
        3. 从 connector 实时获取
        """
        db_name = resource_info.metadata.get("db_name", "")
        original_resource = resource_info.metadata.get("_resource")

        # 方法1：从 DBResource.get_prompt 获取
        if original_resource and hasattr(original_resource, "get_prompt"):
            try:
                prompt, _ = await original_resource.get_prompt(lang="zh")
                if prompt:
                    logger.info(f"Got table list from DBResource.get_prompt for {db_name}")
                    return prompt
            except Exception as e:
                logger.warning(f"Failed to get table list from DBResource: {e}")

        # 方法2：从 spec_service 获取
        try:
            from derisk_serve.datasource.manages.connect_config_db import ConnectConfigDao
            from derisk_serve.datasource.service.spec_service import DbSpecService

            dao = ConnectConfigDao()
            entity = dao.get_by_names(db_name)
            if entity:
                spec_service = DbSpecService()
                if spec_service.has_spec(entity.id):
                    table_list = spec_service.format_db_spec_for_prompt(
                        entity.id, mode="small"
                    )
                    if table_list:
                        logger.info(f"Got table list from spec_service for {db_name}")
                        return table_list
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to get table list from spec_service: {e}")

        # 方法3：从 connector 实时获取
        if original_resource:
            connector = getattr(original_resource, "_connector", None) or getattr(original_resource, "connector", None)
            if connector:
                try:
                    # 获取所有表名
                    table_names = connector.get_table_names()
                    if table_names:
                        table_list = "\n".join([f"- {t}" for t in table_names])
                        logger.info(f"Got table list from connector for {db_name}")
                        return table_list
                except Exception as e:
                    logger.warning(f"Failed to get table list from connector: {e}")

        # 返回空列表提示
        logger.warning(f"Could not get table list for {db_name}")
        return "（无法获取表列表，请使用 get_table_spec 工具查询）"

    async def inject_custom(self, ctx: ResourceContext) -> Optional[str]:
        """注入自定义资源"""
        resources = ctx.get_resources(ResourceType.CUSTOM)
        logger.info(f"inject_custom: resources_count={len(resources)}")
        if not resources:
            return None

        template = self._get_template(ResourceType.CUSTOM)
        if template:
            custom_resources = []
            for r in resources:
                actual_type = r.metadata.get("resource_type", r.code)
                resource_dict = {
                    "type": actual_type,
                    "code": r.code,
                    "name": r.name,
                    "description": r.description,
                    "metadata": {
                        k: v for k, v in r.metadata.items() if k != "resource_type"
                    }
                    if r.metadata
                    else {},
                }
                custom_resources.append(resource_dict)
            return template.render(resources=custom_resources)

        return self._format_custom_default(resources)

    async def inject_all(self, ctx: ResourceContext) -> str:
        """注入所有资源"""
        sections = []
        logger.info("inject_all: starting resource injection")

        sandbox = await self.inject_sandbox(ctx)
        if sandbox:
            sections.append(sandbox)
            logger.info(f"inject_all: sandbox injected, length={len(sandbox)}")
        else:
            logger.info("inject_all: no sandbox injected")

        agents = await self.inject_agents(ctx)
        if agents:
            sections.append(agents)

        knowledge = await self.inject_knowledge(ctx)
        if knowledge:
            sections.append(knowledge)

        skills = await self.inject_skills(ctx)
        if skills:
            sections.append(skills)

        database = await self.inject_database(ctx)
        if database:
            sections.append(database)
            logger.info(f"inject_all: database injected, length={len(database)}")

        custom = await self.inject_custom(ctx)
        if custom:
            sections.append(custom)
            logger.info(f"inject_all: custom resources injected, length={len(custom)}")

        result = "\n\n".join(sections)
        logger.info(
            f"inject_all: total sections={len(sections)}, result_length={len(result)}"
        )
        return result

    def _get_template(self, resource_type: ResourceType) -> Optional[PromptTemplate]:
        """获取资源类型的模板"""
        if resource_type in self.custom_templates:
            return PromptTemplate(
                category="resources",
                name=resource_type.value,
                content=self.custom_templates[resource_type],
                is_jinja2=True,
            )

        if self.use_templates:
            template_name = resource_type.value
            if resource_type == ResourceType.CUSTOM:
                template_name = "other"
            return self.registry.get("resources", template_name)

        return None

    # ==================== 默认格式化方法 ====================

    def _format_sandbox_default(self, resource: ResourceInfo) -> str:
        """默认沙箱格式"""
        prompt = resource.metadata.get("prompt", "")
        return f"""### 环境信息

{prompt}

<important>
沙箱环境是临时的，会话结束后会被销毁。如需持久化文件，请使用 write_file 工具。
</important>"""

    def _format_agents_default(self, resources: List[ResourceInfo]) -> str:
        """默认 Agent 格式"""
        lines = ["<available_agents>", "以下是你可以调用的子代理：", ""]

        for r in resources:
            lines.append(f"- <agent>")
            lines.append(f"  <code>{r.code}</code>")
            lines.append(f"  <name>{r.name}</name>")
            lines.append(f"  <description>{r.description}</description>")
            lines.append(f"</agent>")

        lines.append("</available_agents>")
        lines.append("")
        lines.append("**调用方式：** 使用 `agent_start` 工具启动子代理。")

        return "\n".join(lines)

    def _format_knowledge_default(self, resources: List[ResourceInfo]) -> str:
        """默认知识库格式"""
        lines = ["<available_knowledges>", "以下是你可以使用的知识库：", ""]

        for r in resources:
            lines.append(f"- <knowledge>")
            lines.append(f"  <id>{r.code}</id>")
            lines.append(f"  <name>{r.name}</name>")
            lines.append(f"  <description>{r.description}</description>")
            lines.append(f"</knowledge>")

        lines.append("</available_knowledges>")
        lines.append("")
        lines.append("**使用方式：** 使用 `knowledge_search` 工具检索知识。")

        return "\n".join(lines)

    def _format_skills_default(self, resources: List[ResourceInfo]) -> str:
        """默认技能格式"""
        lines = []

        # Check if sandbox is enabled for any resource
        sandbox_enabled = False
        sandbox_skill_dir = ""
        for r in resources:
            if r.metadata.get("sandbox_enabled", False):
                sandbox_enabled = True
                sandbox_skill_dir = r.metadata.get("sandbox_skill_dir", "")
                break

        # Add sandbox environment info if sandbox is enabled
        if sandbox_enabled and sandbox_skill_dir:
            lines.append("以下技能存储在沙箱环境中，路径为沙箱内的绝对路径。")
            lines.append(f"技能目录：{sandbox_skill_dir}")
            lines.append(
                "使用方式：使用 `skill_load` 工具加载技能，或使用 `view` 工具读取技能目录中的 SKILL.md 文件。"
            )
            lines.append("")

        lines.append("<available_skills>")
        lines.append("以下是你可以加载的技能：")
        lines.append("")

        for r in resources:
            path = r.metadata.get("path", "")
            branch = r.metadata.get("branch", "master")
            lines.append(f"- <skill>")
            lines.append(f"  <name>{r.name}</name>")
            lines.append(f"  <description>{r.description}</description>")
            if path:
                lines.append(f"  <path>{path}</path>")
            lines.append(f"  <branch>{branch}</branch>")
            lines.append(f"</skill>")

        lines.append("</available_skills>")
        lines.append("")
        lines.append("**使用方式：** 使用 `skill_load` 工具加载技能。")

        return "\n".join(lines)

    def _format_database_default(
        self,
        resources: List[ResourceInfo],
        databases_with_tables: Optional[List[Dict]] = None,
    ) -> str:
        """默认数据库格式，包含表列表"""
        lines = ["<available_databases>", "以下是你可以使用的数据库：", ""]

        # 收集数据库类型信息，用于生成语法提示
        db_types_with_versions = set()

        # 使用包含表列表的数据
        if databases_with_tables:
            for db in databases_with_tables:
                lines.append(f"- <database>")
                lines.append(f"  <name>{db.get('name', '')}</name>")
                lines.append(f"  <db_name>{db.get('db_name', '')}</db_name>")
                db_type = db.get('db_type', '')
                dialect = db.get('dialect', db_type)
                db_version = db.get('db_version')

                if db_type:
                    lines.append(f"  <db_type>{db_type}</db_type>")
                if dialect:
                    lines.append(f"  <dialect>{dialect}</dialect>")
                if db_version:
                    lines.append(f"  <version>{db_version}</version>")
                    db_types_with_versions.add((db_type or dialect, db_version))
                elif db_type or dialect:
                    db_types_with_versions.add((db_type or dialect, None))

                if db.get('description'):
                    lines.append(f"  <description>{db.get('description')}</description>")

                # 添加表列表
                table_list = db.get('table_list', '')
                if table_list:
                    lines.append(f"  <tables>")
                    lines.append(f"{table_list}")
                    lines.append(f"  </tables>")
                lines.append(f"</database>")
        else:
            # 回退到原始格式
            for r in resources:
                db_name = r.metadata.get("db_name", r.code)
                db_type = r.metadata.get("db_type", "")
                dialect = r.metadata.get("dialect", db_type)
                db_version = r.metadata.get("db_version")

                lines.append(f"- <database>")
                lines.append(f"  <name>{r.name}</name>")
                lines.append(f"  <db_name>{db_name}</db_name>")
                if db_type:
                    lines.append(f"  <db_type>{db_type}</db_type>")
                if dialect:
                    lines.append(f"  <dialect>{dialect}</dialect>")
                if db_version:
                    lines.append(f"  <version>{db_version}</version>")
                    db_types_with_versions.add((db_type or dialect, db_version))
                elif db_type or dialect:
                    db_types_with_versions.add((db_type or dialect, None))
                lines.append(f"  <description>{r.description}</description>")
                lines.append(f"</database>")

        lines.append("</available_databases>")
        lines.append("")
        lines.append("**可用工具：**")
        lines.append("")
        lines.append("1. `get_table_spec` - 获取一张或多张表的详细 schema 信息")
        lines.append("   - 参数: db_name (必填), table_names (可选，多表用逗号分隔) 或 question (可选)")
        lines.append("   - 返回: 列定义、类型、注释、索引、样本数据等")
        lines.append("")
        lines.append("2. `execute_sql` - 执行 SQL 查询")
        lines.append("   - 参数: db_name (必填), sql (必填)")
        lines.append("   - **重要**: SQL 语法必须严格匹配数据库类型和版本！")
        lines.append("")

        # 根据数据库类型和版本生成针对性语法提示
        sql_syntax_hints = self._generate_sql_syntax_hints(db_types_with_versions)
        lines.extend(sql_syntax_hints)

        lines.append("")
        lines.append("3. `list_tables` - 列出数据库所有表名")
        lines.append("   - 使用场景: 表列表未注入或需要完整列表时")
        lines.append("")
        lines.append("**使用流程：**")
        lines.append("1. 查看上方的表列表和数据库版本信息")
        lines.append("2. 使用 `get_table_spec` 获取表的详细结构（支持多张表）")
        lines.append("3. 根据数据库类型和版本编写符合语法的 SQL")
        lines.append("4. 使用 `execute_sql` 执行查询")

        return "\n".join(lines)

    def _generate_sql_syntax_hints(self, db_types_with_versions: set) -> List[str]:
        """根据数据库类型和版本生成 SQL 语法提示"""
        hints = ["**SQL 语法要求（必须严格遵守）：**", ""]

        for db_type, version in db_types_with_versions:
            db_type_lower = (db_type or "").lower()

            if db_type_lower == "oracle":
                # Oracle 版本相关的语法提示
                if version:
                    try:
                        major, minor = map(int, version.split('.')[:2])
                        if (major, minor) >= (12, 1):
                            hints.append(f"Oracle {version}: 使用 FETCH FIRST n ROWS ONLY（12c+ 新语法）")
                            hints.append("   示例: SELECT * FROM table FETCH FIRST 10 ROWS ONLY")
                        else:
                            hints.append(f"Oracle {version}: 使用 ROWNUM（11g 及更早版本）")
                            hints.append("   示例: SELECT * FROM (SELECT * FROM table) WHERE ROWNUM <= 10")
                    except (ValueError, AttributeError):
                        hints.append(f"Oracle {version}: 优先使用 ROWNUM，兼容所有版本")
                        hints.append("   示例: SELECT * FROM (SELECT * FROM table) WHERE ROWNUM <= 10")
                else:
                    hints.append("Oracle: 使用 ROWNUM（兼容所有版本）")
                    hints.append("   示例: SELECT * FROM (SELECT * FROM table) WHERE ROWNUM <= 10")

                # Oracle 特定语法规范（重要！）
                hints.append("")
                hints.append("   **Oracle SQL 特殊语法规范**:")
                hints.append("   - 表名格式: 'OWNER.TABLE_NAME'，使用双引号: \"OWNER\".\"TABLE_NAME\"")
                hints.append("   - 无 LIMIT 关键字，日期函数使用 TO_DATE('YYYY-MM-DD', 'YYYY-MM-DD')")
                hints.append("   - **ORDER BY 聚合函数**:")
                hints.append("     ❌ ORDER BY COUNT DESC（错误！COUNT 是保留字，不能直接使用）")
                hints.append("     ✅ ORDER BY COUNT(*) DESC（正确！使用完整函数名）")
                hints.append("     ✅ ORDER BY 人数 DESC（正确！使用定义的别名）")
                hints.append("   - **列别名避免使用保留字**:")
                hints.append("     ❌ COUNT(*) AS COUNT（错误！COUNT 是保留字）")
                hints.append("     ✅ COUNT(*) AS cnt 或 人数（正确！使用非保留字）")
                hints.append("")

            elif db_type_lower == "mysql":
                hints.append("MySQL: 使用 LIMIT，标识符用反引号 ``")
                hints.append("   示例: SELECT * FROM `table` LIMIT 10")
                hints.append("")

            elif db_type_lower in ("postgresql", "postgres"):
                hints.append("PostgreSQL: 使用 LIMIT/OFFSET，标识符用双引号 \"\"")
                hints.append("   示例: SELECT * FROM \"table\" LIMIT 10 OFFSET 5")
                hints.append("")

            elif db_type_lower in ("mssql", "sqlserver", "sql server"):
                hints.append("SQL Server: 使用 TOP 或 OFFSET FETCH，标识符用方括号 []")
                hints.append("   示例: SELECT TOP 10 * FROM [table]")
                hints.append("   或: SELECT * FROM [table] ORDER BY col OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY")
                hints.append("")

            elif db_type_lower == "sqlite":
                hints.append("SQLite: 标准 SQL，使用 LIMIT/OFFSET")
                hints.append("   示例: SELECT * FROM table LIMIT 10")
                hints.append("")

            else:
                hints.append(f"{db_type}: 请查询该数据库的特定语法要求")
                hints.append("")

        if not db_types_with_versions:
            # 默认提示所有常见数据库
            hints.extend([
                "- SQLite: 标准 SQL，LIMIT 语法",
                "- MySQL: LIMIT，反引号 ``",
                "- PostgreSQL: LIMIT/OFFSET，双引号 \"\"",
                "- SQL Server: TOP 或 OFFSET FETCH，方括号 []",
                "- Oracle: ROWNUM（11g）或 FETCH FIRST（12c+），双引号 \"\"，无 LIMIT",
                "- Oracle: ORDER BY 聚合函数必须写完整（如 ORDER BY COUNT(*) DESC）",
            ])

        return hints

    def _format_custom_default(self, resources: List[ResourceInfo]) -> str:
        lines = ["<other_resources>", "以下是其他可用资源：", ""]

        for r in resources:
            actual_type = r.metadata.get("resource_type", r.code)
            lines.append(f"- <{actual_type}>")
            lines.append(f"  <name>{r.name}</name>")
            lines.append(f"  <description>{r.description}</description>")
            for key, value in r.metadata.items():
                if key not in ("resource_type", "scene") and value:
                    lines.append(f"  <{key}>{value}</{key}>")
            lines.append(f"</{actual_type}>")

        lines.append("</other_resources>")

        return "\n".join(lines)


def create_resource_injector(
    use_templates: bool = True,
    custom_templates: Optional[Dict[ResourceType, str]] = None,
) -> ResourceInjector:
    """创建资源注入器的便捷函数"""
    return ResourceInjector(
        use_templates=use_templates, custom_templates=custom_templates
    )
