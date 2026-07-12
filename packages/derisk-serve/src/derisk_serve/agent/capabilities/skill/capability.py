"""SkillCapability —— 技能自管理资源能力(RFC-006 Stage 7/8)。

技能纯声明:declare 渲染 <agent-skills> 列表进 SYSTEM。

prepare 自管 skill_code/path 解析(facade 时序已改 prepare 先于 declare,RFC-006 Stage 8):
若 skills 已带 path(from_legacy/config 完整)则免 I/O;否则按 skill_name 查 Skill service
补 skill_code + 解析 sandbox path(get_skill_directory + FS 检查)。无 _SYSTEM_APP/
service 不可用时降级不崩(declare 用现有 path/空)。

execute 不收编:read_skill/list_skills 工具暂走 Route A builtin(沙箱/local fs 读,
SandboxToolBase)。本轮 SkillCapability 自管 prepare/declare,execute 保持 Route A。

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
        """补 skill_code/path(若 config 已带 path 则免 I/O;否则查 Skill service)。

        facets 时序已改 prepare 先于 declare(RFC-006 Stage 8)。config 多数已带
        skill_code/path(derisk_skill params 完整),仅边角(只给 skill_name)触发查码。
        path 解析:查码后用 service.get_skill_directory 获取 sandbox path。
        """
        if not self._skills:
            self._status = ExecutorStatus.READY
            return
        # 已带 path → 免 I/O
        if all(sk.get("path") for sk in self._skills):
            self._status = ExecutorStatus.READY
            return
        try:
            import asyncio
            import os

            from derisk_serve.skill.service.service import (
                Service,
                SKILL_SERVICE_COMPONENT_NAME,
            )
            from derisk_serve.skill.api.schemas import SkillRequest
            from derisk.agent.resource.manage import _SYSTEM_APP

            if not _SYSTEM_APP:
                self._status = ExecutorStatus.READY
                return
            service = _SYSTEM_APP.get_component(
                SKILL_SERVICE_COMPONENT_NAME, Service, default=None
            )
            if not service:
                self._status = ExecutorStatus.READY
                return

            for sk in self._skills:
                if sk.get("path"):
                    continue
                skill_name = sk.get("name") or ""
                # 查 skill_code(精确名 + 前缀回退)
                skill_code = await asyncio.to_thread(
                    self._lookup_skill_code, service, skill_name
                )
                if not skill_code:
                    continue
                sk_code = skill_code or skill_name
                # 解析 sandbox path
                skill_dir = await asyncio.to_thread(
                    self._get_skill_directory, service, sk_code
                )
                if skill_dir:
                    sk["path"] = skill_dir
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[skill-capability] prepare resolve code/path failed: {e}")
        self._status = ExecutorStatus.READY

    @staticmethod
    def _lookup_skill_code(service, skill_name: str):
        """复刻 derisk_skill._lookup_skill_code_by_name(精确名 + 前缀回退)。"""
        try:
            skills = service.get_list(SkillRequest(name=skill_name))
            if skills:
                return skills[0].skill_code
            for skill in service.get_list(SkillRequest()):
                if skill.name == skill_name or skill.skill_code.startswith(f"{skill_name}-"):
                    return skill.skill_code
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[skill-capability] lookup skill_code for '{skill_name}': {e}")
        return None

    @staticmethod
    def _get_skill_directory(service, skill_code: str):
        """复刻 derisk_skill._get_sandbox_path(service.get_skill_directory + FS 检查)。"""
        try:
            skill_dir = service.get_skill_directory(skill_code)
            import os

            if skill_dir and os.path.exists(skill_dir):
                return skill_dir
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[skill-capability] get_skill_directory for '{skill_code}': {e}")
        return None

    async def execute(self, call: ExecutorCall) -> Any:
        # read_skill/list_skills 暂走 Route A builtin(SandboxToolBase)。
        raise NotImplementedError(
            "SkillCapability.execute 未收编 —— skill 工具暂走 Route A builtin"
        )

    async def release(self, reason: ReleaseReason) -> None:
        self._status = ExecutorStatus.RELEASED