"""
Skill Lifecycle Manager - Skill生命周期管理器

管理Skill的加载、激活、休眠和退出，实现主动退出机制。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .slot_manager import (
    ContextSlot,
    ContextSlotManager,
    EvictionPolicy,
    SlotState,
    SlotType,
)

logger = logging.getLogger(__name__)


class ExitTrigger(str, Enum):
    """退出触发器"""
    TASK_COMPLETE = "task_complete"
    ERROR_OCCURRED = "error_occurred"
    TIMEOUT = "timeout"
    MANUAL = "manual"
    CONTEXT_PRESSURE = "context_pressure"
    NEW_SKILL_LOAD = "new_skill_load"


@dataclass
class SkillExitResult:
    """Skill退出结果"""
    skill_name: str
    exit_trigger: ExitTrigger
    summary: str
    key_outputs: List[str]
    next_skill_hint: Optional[str] = None
    tokens_freed: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "exit_trigger": self.exit_trigger.value,
            "summary": self.summary,
            "key_outputs": self.key_outputs,
            "tokens_freed": self.tokens_freed,
        }


@dataclass
class SkillManifest:
    """Skill清单"""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    required_tools: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    priority: int = 5
    auto_exit: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "required_tools": self.required_tools,
            "tags": self.tags,
            "priority": self.priority,
            "auto_exit": self.auto_exit,
        }


class SkillLifecycleManager:
    """
    Skill生命周期管理器
    
    核心功能:
    1. 管理Skill的加载、激活、休眠、退出
    2. 生成Skill退出摘要
    3. 协调多个Skill之间的上下文切换
    """
    
    def __init__(
        self,
        context_slot_manager: ContextSlotManager,
        summary_generator: Optional[Callable] = None,
        max_active_skills: int = 3,
    ):
        self._slot_manager = context_slot_manager
        self._summary_generator = summary_generator
        self._max_active_skills = max_active_skills
        
        self._active_skills: Dict[str, ContextSlot] = {}
        self._dormant_skills: Dict[str, ContextSlot] = {}
        self._skill_history: List[SkillExitResult] = []
        self._skill_manifests: Dict[str, SkillManifest] = {}
    
    def register_manifest(self, manifest: SkillManifest) -> None:
        """注册Skill清单"""
        self._skill_manifests[manifest.name] = manifest
        logger.debug(f"[SkillLifecycle] Registered manifest: {manifest.name}")
    
    async def load_skill(
        self,
        skill_name: str,
        skill_content: str,
        metadata: Optional[Dict[str, Any]] = None,
        required_tools: Optional[List[str]] = None,
    ) -> ContextSlot:
        """加载Skill到上下文"""
        if skill_name in self._active_skills:
            slot = self._active_skills[skill_name]
            slot.touch()
            logger.debug(f"[SkillLifecycle] Skill '{skill_name}' already active")
            return slot
        
        if skill_name in self._dormant_skills:
            slot = self._reactivate_skill(skill_name)
            if slot:
                return slot
        
        if len(self._active_skills) >= self._max_active_skills:
            await self._evict_lru_skill()
        
        manifest = self._skill_manifests.get(skill_name)
        priority = manifest.priority if manifest else 5
        
        slot = await self._slot_manager.allocate(
            slot_type=SlotType.SKILL,
            content=skill_content,
            source_name=skill_name,
            metadata=metadata or {},
            eviction_policy=EvictionPolicy.LRU,
            priority=priority,
        )
        
        self._active_skills[skill_name] = slot
        
        logger.info(
            f"[SkillLifecycle] Loaded skill '{skill_name}', "
            f"active: {len(self._active_skills)}/{self._max_active_skills}"
        )
        
        return slot
    
    async def activate_skill(self, skill_name: str) -> Optional[ContextSlot]:
        """激活休眠的Skill"""
        return self._reactivate_skill(skill_name)
    
    def _reactivate_skill(self, skill_name: str) -> Optional[ContextSlot]:
        """重新激活Skill"""
        if skill_name not in self._dormant_skills:
            return None
        
        if len(self._active_skills) >= self._max_active_skills:
            return None
        
        slot = self._dormant_skills.pop(skill_name)
        slot.state = SlotState.ACTIVE
        slot.touch()
        self._active_skills[skill_name] = slot
        
        logger.info(f"[SkillLifecycle] Reactivated skill '{skill_name}'")
        return slot
    
    async def exit_skill(
        self,
        skill_name: str,
        trigger: ExitTrigger = ExitTrigger.TASK_COMPLETE,
        summary: Optional[str] = None,
        key_outputs: Optional[List[str]] = None,
        next_skill_hint: Optional[str] = None,
    ) -> SkillExitResult:
        """Skill主动退出"""
        if skill_name not in self._active_skills:
            if skill_name in self._dormant_skills:
                return SkillExitResult(
                    skill_name=skill_name,
                    exit_trigger=trigger,
                    summary="Skill is dormant",
                    key_outputs=[],
                )
            logger.warning(f"[SkillLifecycle] Skill '{skill_name}' not active")
            return SkillExitResult(
                skill_name=skill_name,
                exit_trigger=trigger,
                summary="Skill not active",
                key_outputs=[],
            )
        
        slot = self._active_skills.pop(skill_name)
        
        if not summary:
            summary = self._generate_summary(slot)
        
        key_outputs = key_outputs or []
        
        compact_content = self._create_compact_representation(
            skill_name=skill_name,
            summary=summary,
            key_outputs=key_outputs[:5],
        )
        
        tokens_freed = slot.token_count - len(compact_content) // 4
        
        slot.content = compact_content
        slot.token_count = len(compact_content) // 4
        slot.state = SlotState.DORMANT
        slot.exit_summary = summary
        
        self._slot_manager.update_slot_content(slot.slot_id, compact_content)
        self._dormant_skills[skill_name] = slot
        
        result = SkillExitResult(
            skill_name=skill_name,
            exit_trigger=trigger,
            summary=summary,
            key_outputs=key_outputs,
            next_skill_hint=next_skill_hint,
            tokens_freed=max(0, tokens_freed),
        )
        self._skill_history.append(result)
        
        logger.info(
            f"[SkillLifecycle] Skill '{skill_name}' exited, "
            f"tokens freed: {tokens_freed}, trigger: {trigger.value}"
        )
        
        return result
    
    async def unload_skill(self, skill_name: str) -> bool:
        """完全卸载Skill（包括压缩形式）"""
        if skill_name in self._active_skills:
            self._active_skills.pop(skill_name)
        if skill_name in self._dormant_skills:
            self._dormant_skills.pop(skill_name)
        
        result = await self._slot_manager.evict(
            slot_type=SlotType.SKILL,
            source_name=skill_name,
        )
        
        if result:
            logger.info(f"[SkillLifecycle] Unloaded skill '{skill_name}'")
            return True
        return False
    
    def _generate_summary(self, slot: ContextSlot) -> str:
        """生成Skill执行摘要"""
        duration = (datetime.now() - slot.created_at).seconds
        return (
            f"[Skill {slot.source_name} Completed]\n"
            f"- Tasks performed: {slot.access_count} operations\n"
            f"- Duration: {duration}s\n"
            f"- Status: Success"
        )
    
    def _create_compact_representation(
        self,
        skill_name: str,
        summary: str,
        key_outputs: List[str],
    ) -> str:
        """创建压缩表示"""
        lines = [
            f'<skill-result name="{skill_name}">',
            f"<summary>{summary}</summary>",
        ]
        
        if key_outputs:
            lines.append("<key-outputs>")
            for output in key_outputs[:5]:
                lines.append(f"  - {output}")
            lines.append("</key-outputs>")
        
        lines.append("</skill-result>")
        return "\n".join(lines)
    
    async def _evict_lru_skill(self) -> Optional[SkillExitResult]:
        """驱逐最近最少使用的Skill"""
        if not self._active_skills:
            return None
        
        lru_skill = min(
            self._active_skills.items(),
            key=lambda x: x[1].last_accessed.timestamp()
        )
        
        return await self.exit_skill(
            skill_name=lru_skill[0],
            trigger=ExitTrigger.CONTEXT_PRESSURE,
        )
    
    def get_active_skills(self) -> List[str]:
        """获取当前活跃的Skill列表"""
        return list(self._active_skills.keys())
    
    def get_dormant_skills(self) -> List[str]:
        """获取休眠的Skill列表"""
        return list(self._dormant_skills.keys())
    
    def get_skill_history(self) -> List[SkillExitResult]:
        """获取Skill执行历史"""
        return self._skill_history.copy()
    
    def get_skill_status(self, skill_name: str) -> Optional[str]:
        """获取Skill状态"""
        if skill_name in self._active_skills:
            return "active"
        elif skill_name in self._dormant_skills:
            return "dormant"
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "active_count": len(self._active_skills),
            "dormant_count": len(self._dormant_skills),
            "max_active": self._max_active_skills,
            "total_exits": len(self._skill_history),
            "active_skills": list(self._active_skills.keys()),
            "dormant_skills": list(self._dormant_skills.keys()),
        }