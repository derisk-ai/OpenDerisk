"""PlaybookResource — RFC-005 资源协议实现。

剧本作为组合资源，包含：
1. 独立文本部分（workflow, role_definition, behavior_constraints 等）
2. 子资源引用（skills, datasources, mcp, knowledge 等）
3. 剧本内置工具（get_playbook_info, get_playbook_skills 等）

设计要点：
- 继承 ResourceProtocol，实现 declare() 返回 Contribution 列表
- SYSTEM 槽：剧本文本（role_definition, workflow, constraints 等）
- TOOLS 槽：剧本内置工具 + 子资源引用
- 缓存策略：USER scope（用户级资源，跨会话共享）
- 生命周期：CONFIG_STATIC（配置态即定）

用法：
    config = PlaybookConfig(playbook_id=123)
    contribs = PlaybookResource.declare(config)
    # contribs -> [Contribution(slot=SYSTEM, ...), Contribution(slot=TOOLS, ...), ...]
"""
from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from derisk.agent.resource.tool.base import FunctionTool
from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.protocol import ResourceProtocol

if TYPE_CHECKING:
    from derisk.component import SystemApp

logger = logging.getLogger(__name__)

# 剧本文本的默认缓存策略：用户级资源，跨会话共享
_PLAYBOOK_CACHE_SCOPE = CacheScope.USER
_PLAYBOOK_LIFETIME = Lifetime.CONFIG_STATIC


@dataclass
class PlaybookTextContent:
    """剧本独立文本部分（declaration.text_content）。

    存储在 declaration DSL 的 text_content 字段中。
    """
    workflow: str = ""
    role_definition: str = ""
    goal: str = ""
    behavior_constraints: str = ""
    background: str = ""

    def to_dict(self) -> Dict[str, str]:
        """转换为字典，过滤空值。"""
        result = {}
        if self.workflow:
            result["workflow"] = self.workflow
        if self.role_definition:
            result["role_definition"] = self.role_definition
        if self.goal:
            result["goal"] = self.goal
        if self.behavior_constraints:
            result["behavior_constraints"] = self.behavior_constraints
        if self.background:
            result["background"] = self.background
        return result

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "PlaybookTextContent":
        """从 declaration.text_content 字典创建。"""
        if not data:
            return cls()
        return cls(
            workflow=data.get("workflow", ""),
            role_definition=data.get("role_definition", ""),
            goal=data.get("goal", ""),
            behavior_constraints=data.get("behavior_constraints", ""),
            background=data.get("background", ""),
        )


@dataclass
class PlaybookConfig:
    """PlaybookResource 的配置参数。

    配置态传入 playbook_id，declare 时使用预加载的数据。
    """
    playbook_id: int
    playbook_name: str = ""
    text_content: PlaybookTextContent = field(default_factory=PlaybookTextContent)
    skills: List[str] = field(default_factory=list)
    resources: List[Dict[str, Any]] = field(default_factory=list)
    deliverables: List[Dict[str, Any]] = field(default_factory=list)
    distill: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_playbook_response(cls, playbook: Any) -> "PlaybookConfig":
        """从 PlaybookResponse 创建配置（配置态预加载时使用）。"""
        declaration = getattr(playbook, "declaration", {}) or {}
        text_content = PlaybookTextContent.from_dict(
            declaration.get("text_content", {})
        )
        ctx = declaration.get("context", {})

        return cls(
            playbook_id=playbook.id,
            playbook_name=getattr(playbook, "name", ""),
            text_content=text_content,
            skills=declaration.get("skills", []),
            resources=ctx.get("resources", []),
            deliverables=declaration.get("deliverables", []),
            distill=declaration.get("distill", {}),
        )


# --------------------------------------------------------------------------- #
# 剧本内置工具
# --------------------------------------------------------------------------- #

def build_playbook_tools(config: PlaybookConfig) -> List[FunctionTool]:
    """构建剧本内置工具(委托 tools/ 自管目录)。"""
    from .tools.playbook_tools import build_playbook_tools as _build
    return _build(config)


class PlaybookResource(ResourceProtocol):
    """剧本资源协议实现。

    剧本是组合资源：
    1. SYSTEM 槽：独立文本部分（workflow, role, constraints 等）
    2. TOOLS 槽：剧本内置工具 + 子资源工具

    缓存策略：
    - SYSTEM 内容：USER scope（用户级，跨会话共享）
    - TOOLS 内容：NONE scope（每轮动态解析）
    """

    capability_id: str = "playbook"
    protocol_version: int = 1

    def __init__(
        self,
        config: PlaybookConfig,
        system_app: Optional["SystemApp"] = None,
    ):
        """初始化剧本资源。

        Args:
            config: 剧本配置（包含预加载的 declaration 数据）
            system_app: 系统应用实例（用于解析子资源）
        """
        self._config = config
        self._system_app = system_app

    @classmethod
    def declare(cls, config: PlaybookConfig) -> List[Contribution]:
        """声明面：返回 Contribution 列表（纯函数）。

        产出：
        - SYSTEM 槽：剧本文本（role_definition, workflow, constraints 等）
        - TOOLS 槽：剧本内置工具 + 子资源引用

        注意：declare 是纯函数，不能做 I/O。子资源解析需要
        通过 DataRequirement 或运行时注入完成。
        """
        contributions: List[Contribution] = []

        # 1. SYSTEM 槽：剧本文本
        system_text = cls._render_system_text(config)
        if system_text:
            contributions.append(
                Contribution(
                    capability_id=f"playbook:{config.playbook_id}:text",
                    slot=Slot.SYSTEM,
                    content=system_text,
                    lifetime=_PLAYBOOK_LIFETIME,
                    cache_scope=_PLAYBOOK_CACHE_SCOPE,
                    order=0,
                )
            )

        # 2. TOOLS 槽：剧本内置工具
        playbook_tools = build_playbook_tools(config)
        for tool in playbook_tools:
            contributions.append(
                Contribution(
                    capability_id=f"playbook:{config.playbook_id}:tool:{tool.name}",
                    slot=Slot.TOOLS,
                    content=tool,  # FunctionTool 实例
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.NONE,
                    order=0,
                )
            )

        # 3. TOOLS 槽：子资源引用（声明需要解析的工具）
        # 注意：这里的 content 是元数据，实际工具解析由执行投影完成
        if config.skills or config.resources:
            tool_refs = cls._build_tool_refs(config)
            contributions.append(
                Contribution(
                    capability_id=f"playbook:{config.playbook_id}:sub_resources",
                    slot=Slot.TOOLS,
                    content=tool_refs,  # 工具引用元数据
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.NONE,
                    order=1,
                )
            )

        return contributions

    @staticmethod
    def _render_system_text(config: PlaybookConfig) -> str:
        """渲染剧本的 SYSTEM 槽文本。

        组合：剧本标识 + 独立文本部分 + 产出物预期
        """
        parts: List[str] = []

        # 1. 剧本标识头
        parts.append(f"# Playbook: {config.playbook_name}")
        parts.append(f"Playbook ID: {config.playbook_id}")

        # 2. 独立文本部分
        tc = config.text_content
        if tc.role_definition:
            parts.append(f"\n## Role\n{tc.role_definition}")
        if tc.goal:
            parts.append(f"\n## Goal\n{tc.goal}")
        if tc.workflow:
            parts.append(f"\n## Workflow\n{tc.workflow}")
        if tc.behavior_constraints:
            parts.append(f"\n## Constraints\n{tc.behavior_constraints}")
        if tc.background:
            parts.append(f"\n## Background\n{tc.background}")

        # 3. 产出物预期（来自 deliverables）
        if config.deliverables:
            parts.append("\n## Expected Deliverables")
            for d in config.deliverables:
                dtype = d.get("type", "output")
                title = d.get("title", "")
                parts.append(f"- [{dtype}] {title}")

        # 4. 蒸馏规则（来自 distill）
        if config.distill.get("forced"):
            parts.append("\n## Note")
            parts.append("This task requires distilling outcomes into a workspace asset before closing.")

        return "\n".join(parts)

    @staticmethod
    def _build_tool_refs(config: PlaybookConfig) -> Dict[str, Any]:
        """构建工具引用元数据。

        返回包含 skills 和 resources 引用的字典，
        供执行投影层解析为实际工具。
        """
        return {
            "playbook_id": config.playbook_id,
            "playbook_name": config.playbook_name,
            "skills": config.skills,
            "resources": config.resources,
            # 执行投影层据此分派到对应的 ResourceManager/ToolRegistry
            "_resolve_hint": {
                "skills": "agent_skill",
                "datasource": "datasource",
                "data_source": "datasource",
                "mcp": "mcp(derisk)",
                "knowledge": "knowledge",
                "knowledge_space": "knowledge",
            },
        }

    async def consume(self, call_result: Any) -> List[Contribution]:
        """消费面：工具执行后反改输入（可选）。

        剧本资源通常不需要消费面，返回空列表。
        """
        return []


# --------------------------------------------------------------------------- #
# 工厂函数：从 playbook_id 创建 PlaybookResource
# --------------------------------------------------------------------------- #

async def create_playbook_resource(
    system_app: "SystemApp",
    playbook_id: int,
) -> Optional[PlaybookResource]:
    """从 playbook_id 创建 PlaybookResource 实例。

    此函数负责从数据库加载 playbook 数据，创建配置，
    然后返回 PlaybookResource 实例。

    Args:
        system_app: 系统应用实例
        playbook_id: 剧本 ID

    Returns:
        PlaybookResource 实例，如果剧本不存在则返回 None
    """
    from derisk_serve.playbook.service.service import (
        PLAYBOOK_SERVICE_COMPONENT_NAME,
        PlaybookService,
    )

    try:
        service = system_app.get_component(
            PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService
        )
        playbook = service.get_by_id(playbook_id)
        if not playbook:
            logger.warning(f"Playbook {playbook_id} not found")
            return None

        config = PlaybookConfig.from_playbook_response(playbook)
        return PlaybookResource(config, system_app)

    except Exception as e:
        logger.warning(f"Failed to create PlaybookResource for {playbook_id}: {e}")
        return None