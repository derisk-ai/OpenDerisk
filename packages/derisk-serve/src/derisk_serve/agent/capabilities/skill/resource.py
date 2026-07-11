"""SkillResource —— 技能 capability 输入投影(RFC-005 全量迁移 Step B)。

技能是纯声明类:declare 渲染 skill 列表(<agent-skills> XML)进 SYSTEM 槽。
无 I/O(数据都是配置态 SkillMeta),无 executor。

双轨迁移:SkillResource 包装旧 AgentSkillResource 实例(由 build_resource
构建进 ResourcePack),declare 时调旧实例的 skill_meta + 模板渲染,使技能
脱离 LegacyResourceAdapter 桥接、走原生 declare。facade 遇 AgentSkillResource
实例经 _to_resource_protocol 包装成本类走 declare。
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.protocol import ResourceProtocol

logger = logging.getLogger(__name__)

# 模板对齐 agent_skills.py:19-36(技能列表 XML)
_SKILL_PROMPT_TEMPLATE = """<agent-skills>
这里是你可使用的agent-skill的元数据信息，skill的完整文件存在沙箱环境计算机的技能仓库目录中。下面是skill的基础信息包含skill名称'name'，能力介绍'description', 相对路径:'path', 仓库分支:'branch'.
{% for item in skills %}\
<{{loop.index }}>\
<name>{{item.name }}</name>
<description>{{item.description}}</description>
{% if item.path %}\
<path>{{item.path}}</path>
{% endif %}\
{% if item.owner %}\
<owner>{{item.owner}}</owner>
{% endif %}\
{% if item.branch %}\
<branch>{{item.branch}}</branch>
{% endif %}\
</{{loop.index }}>
{% endfor %}\
</agent-skills>"""


def _render_skills(skills: List[dict]) -> str:
    """渲染技能列表为 <agent-skills> 文本(对齐旧模板)。"""
    from derisk.util.template_utils import render

    return render(_SKILL_PROMPT_TEMPLATE, {"skills": skills})


class SkillResource(ResourceProtocol):
    """技能 capability:declare skill 列表进 SYSTEM。

    双轨:由旧 AgentSkillResource 实例包装构造,declare 委托旧实例的 skill_meta。
    """

    capability_id = "skill"
    protocol_version = 1

    def __init__(self, legacy_instance: Any = None, skills: Optional[List[dict]] = None):
        """两种构造方式:
        - legacy_instance: 旧 AgentSkillResource 实例(双轨 migrate),declare 委托其 skill_meta。
        - skills: 直接给已解析的技能列表(原生路径,不经旧实例)。
        """
        self._legacy = legacy_instance
        self._skills = skills

    def declare(self, config: Any = None) -> List[Contribution]:
        """实例 declare:委托 declare_skills 渲染 <agent-skills> SYSTEM Contribution。

        facade._declare_one 在实例上调 declare;此处分发到 declare_skills(从
        legacy_instance.skill_meta 或显式 skills 取数据渲染,无数据返回空)。
        """
        return self.declare_skills()

    def declare_skills(self) -> List[Contribution]:
        """实例方法:渲染技能列表 SYSTEM Contribution。"""
        skills = self._resolve_skills()
        if not skills:
            return []
        try:
            text = _render_skills(skills)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[skill] render skills failed: {e}")
            return []
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.SYSTEM,
                content=text,
                lifetime=Lifetime.CONFIG_STATIC,
                cache_scope=CacheScope.USER,
                order=20,
            )
        ]

    def _resolve_skills(self) -> List[dict]:
        """从 legacy_instance 或显式 skills 取技能列表(对齐旧 get_prompt 的 params)。"""
        if self._skills is not None:
            return self._skills
        if self._legacy is None:
            return []
        mode, branch = "release", "master"
        debug_info = getattr(self._legacy, "debug_info", None)
        if debug_info and isinstance(debug_info, dict) and debug_info.get("is_debug"):
            mode, branch = "debug", debug_info.get("branch", "master")
        meta = None
        try:
            meta = self._legacy.skill_meta(mode)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[skill] skill_meta failed: {e}")
            return []
        if not meta:
            return []
        skill_info = getattr(self._legacy, "_skill", None)
        parent_folder = getattr(skill_info, "parent_folder", None) if skill_info else None
        return [
            {
                "name": meta.name,
                "description": meta.description,
                "path": parent_folder or meta.path,
                "owner": meta.owner,
                "branch": branch,
            }
        ]

    def requires(self, config: Any = None) -> List[str]:
        return []