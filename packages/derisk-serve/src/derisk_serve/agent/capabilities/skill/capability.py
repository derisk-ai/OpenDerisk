"""SkillCapability —— 技能自管理资源能力(RFC-006 Stage 7)。

技能是纯声明类:declare 渲染 <agent-skills> 列表进 SYSTEM。无 I/O。

**架构约束(facade 时序锁)**:facade declare 先于 prepare。skill_code/path 解析在旧
DeriskSkillResource.__init__(I/O)。declare 读 skill_meta(旧实例构造期已解析并存),
故 SkillCapability 不自管 prepare 的 path I/O——from_legacy 复用旧实例已解析的
skill_meta/_skill,无新增 I/O。prepare no-op。

execute 不收编:read_skill/list_skills 工具暂走 Route A builtin(沙箱/local fs 读,
SandboxToolBase)。本轮 SkillCapability 自管 declare,execute 保持 Route A。
注:config 若已带 skill_code/path(derisk_skill params 多数情况),from_config 可纯配置态。

双轨:register_wrappers 与 register_capability 并存,Stage 9 删前者。
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
from derisk.core.interface.resource.capability import Capability
from derisk.core.interface.resource.executor import (
    ExecutorCall,
    ExecutorStatus,
    ReleaseReason,
)

from .resource import _render_skills

logger = logging.getLogger(__name__)


class SkillCapability(Capability):
    """技能自管理能力:declare <agent-skills> 列表进 SYSTEM。

    capability_id="skill";executor_id="skill"。
    """

    capability_id = "skill"

    def __init__(self, skills: Optional[List[dict]] = None):
        self._skills = skills
        self._legacy: Any = None
        self._status = ExecutorStatus.UNINITIALIZED

    @classmethod
    def from_config(cls, value: dict, system_app: Any = None) -> "SkillCapability":
        """从 config dict 构造(若 config 已带 name/description/path 则纯配置态)。"""
        value = value or {}
        skills = None
        if value.get("skill_name") or value.get("name"):
            skills = [
                {
                    "name": value.get("skill_name") or value.get("name") or "",
                    "description": value.get("skill_description")
                    or value.get("description")
                    or "",
                    "path": value.get("skill_path") or value.get("path") or "",
                    "owner": value.get("skill_author") or value.get("owner") or "",
                    "branch": value.get("skill_branch") or value.get("branch") or "master",
                }
            ]
        return cls(skills=skills)

    @classmethod
    def from_legacy(cls, legacy_instance: Any) -> "SkillCapability":
        """从旧 AgentSkillResource/DeriskSkillResource 实例构造(过渡期)。

        declare 委托旧实例 skill_meta(构造期已解析),无新增 I/O。
        """
        cap = cls(skills=None)
        cap._legacy = legacy_instance
        return cap

    @property
    def executor_id(self) -> str:
        return "skill"

    # ----------------------------- 输入投影(declare 纯) ------------------ #
    def declare(self, config: Any = None) -> List[Contribution]:
        skills = self._resolve_skills()
        if not skills:
            return []
        try:
            text = _render_skills(skills)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[skill-capability] render skills failed: {e}")
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
            logger.warning(f"[skill-capability] skill_meta failed: {e}")
            return []
        if not meta:
            return []
        skill_info = getattr(self._legacy, "_skill", None)
        parent_folder = getattr(skill_info, "parent_folder", None) if skill_info else None
        return [
            {
                "name": meta.name,
                "description": meta.description,
                "path": parent_folder or getattr(meta, "path", None),
                "owner": getattr(meta, "owner", None),
                "branch": branch,
            }
        ]

    def requires(self, config: Any = None) -> List[str]:
        return []

    # ----------------------------- 生命周期(无 I/O) ----------------------- #
    async def prepare(self) -> None:
        self._status = ExecutorStatus.READY

    async def execute(self, call: ExecutorCall) -> Any:
        # read_skill/list_skills 暂走 Route A builtin(SandboxToolBase)。
        raise NotImplementedError(
            "SkillCapability.execute 未收编 —— skill 工具暂走 Route A builtin"
        )

    async def release(self, reason: ReleaseReason) -> None:
        self._status = ExecutorStatus.RELEASED