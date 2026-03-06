"""
Context Lifecycle Orchestrator - 上下文生命周期编排器

统一协调Skill和工具的生命周期管理。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .skill_lifecycle import (
    ExitTrigger,
    SkillExitResult,
    SkillLifecycleManager,
    SkillManifest,
)
from .slot_manager import (
    ContextSlot,
    ContextSlotManager,
    SlotType,
)
from .tool_lifecycle import (
    ToolCategory,
    ToolLifecycleManager,
    ToolManifest,
)

logger = logging.getLogger(__name__)


@dataclass
class ContextLifecycleConfig:
    """上下文生命周期配置"""
    token_budget: int = 100000
    max_slots: int = 50
    max_active_skills: int = 3
    max_tool_definitions: int = 20
    pressure_threshold: float = 0.8
    critical_threshold: float = 0.95
    auto_compact: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_budget": self.token_budget,
            "max_slots": self.max_slots,
            "max_active_skills": self.max_active_skills,
            "max_tool_definitions": self.max_tool_definitions,
            "pressure_threshold": self.pressure_threshold,
            "critical_threshold": self.critical_threshold,
            "auto_compact": self.auto_compact,
        }


@dataclass
class SkillExecutionContext:
    """Skill执行上下文"""
    skill_name: str
    skill_slot: Optional[ContextSlot] = None
    loaded_tools: Dict[str, bool] = field(default_factory=dict)
    active_skills: List[str] = field(default_factory=list)
    context_stats: Dict[str, Any] = field(default_factory=dict)


class ContextLifecycleOrchestrator:
    """
    上下文生命周期编排器
    
    统一协调Skill和工具的生命周期管理
    """
    
    def __init__(
        self,
        config: Optional[ContextLifecycleConfig] = None,
        summary_generator: Optional[Callable] = None,
    ):
        self._config = config or ContextLifecycleConfig()
        
        self._slot_manager = ContextSlotManager(
            max_slots=self._config.max_slots,
            token_budget=self._config.token_budget,
        )
        
        self._skill_manager = SkillLifecycleManager(
            context_slot_manager=self._slot_manager,
            summary_generator=summary_generator,
            max_active_skills=self._config.max_active_skills,
        )
        
        self._tool_manager = ToolLifecycleManager(
            context_slot_manager=self._slot_manager,
            max_tool_definitions=self._config.max_tool_definitions,
        )
        
        self._session_id: Optional[str] = None
        self._initialized = False
        self._skill_contexts: Dict[str, SkillExecutionContext] = {}
    
    async def initialize(
        self,
        session_id: str,
        initial_tools: Optional[List[ToolManifest]] = None,
        initial_skills: Optional[List[SkillManifest]] = None,
    ) -> None:
        """初始化"""
        self._session_id = session_id
        self._initialized = True
        
        if initial_tools:
            for manifest in initial_tools:
                self._tool_manager.register_manifest(manifest)
                if manifest.auto_load:
                    await self._tool_manager.ensure_tools_loaded([manifest.name])
        
        if initial_skills:
            for manifest in initial_skills:
                self._skill_manager.register_manifest(manifest)
        
        logger.info(f"[Orchestrator] Initialized for session: {session_id}")
    
    async def prepare_skill_context(
        self,
        skill_name: str,
        skill_content: str,
        required_tools: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SkillExecutionContext:
        """准备Skill执行的上下文环境"""
        manifest = self._skill_manager._skill_manifests.get(skill_name)
        tools_to_load = required_tools or []
        
        if manifest and manifest.required_tools:
            tools_to_load = list(set(tools_to_load + manifest.required_tools))
        
        slot = await self._skill_manager.load_skill(
            skill_name=skill_name,
            skill_content=skill_content,
            metadata=metadata,
        )
        
        loaded_tools = {}
        if tools_to_load:
            loaded_tools = await self._tool_manager.ensure_tools_loaded(tools_to_load)
        
        context = SkillExecutionContext(
            skill_name=skill_name,
            skill_slot=slot,
            loaded_tools=loaded_tools,
            active_skills=self._skill_manager.get_active_skills(),
            context_stats=self._slot_manager.get_statistics(),
        )
        
        self._skill_contexts[skill_name] = context
        
        return context
    
    async def complete_skill(
        self,
        skill_name: str,
        task_summary: str,
        key_outputs: Optional[List[str]] = None,
        next_skill_hint: Optional[str] = None,
        trigger: ExitTrigger = ExitTrigger.TASK_COMPLETE,
    ) -> SkillExitResult:
        """完成Skill执行并退出"""
        result = await self._skill_manager.exit_skill(
            skill_name=skill_name,
            trigger=trigger,
            summary=task_summary,
            key_outputs=key_outputs,
            next_skill_hint=next_skill_hint,
        )
        
        if skill_name in self._skill_contexts:
            del self._skill_contexts[skill_name]
        
        return result
    
    async def activate_skill(self, skill_name: str) -> Optional[ContextSlot]:
        """激活休眠的Skill"""
        return await self._skill_manager.activate_skill(skill_name)
    
    async def unload_skill(self, skill_name: str) -> bool:
        """完全卸载Skill"""
        if skill_name in self._skill_contexts:
            del self._skill_contexts[skill_name]
        return await self._skill_manager.unload_skill(skill_name)
    
    async def ensure_tools_loaded(
        self,
        tool_names: List[str],
    ) -> Dict[str, bool]:
        """确保工具已加载"""
        return await self._tool_manager.ensure_tools_loaded(tool_names)
    
    async def unload_tools(
        self,
        tool_names: List[str],
        keep_system: bool = True,
    ) -> List[str]:
        """卸载工具"""
        return await self._tool_manager.unload_tools(tool_names, keep_system)
    
    def register_tool_manifest(self, manifest: ToolManifest) -> None:
        """注册工具清单"""
        self._tool_manager.register_manifest(manifest)
    
    def register_skill_manifest(self, manifest: SkillManifest) -> None:
        """注册Skill清单"""
        self._skill_manager.register_manifest(manifest)
    
    async def handle_context_pressure(self) -> Dict[str, Any]:
        """处理上下文压力"""
        stats = self._slot_manager.get_statistics()
        pressure_level = stats["token_usage_ratio"]
        
        actions = []
        
        if pressure_level > self._config.critical_threshold:
            for skill_name in list(self._skill_manager.get_active_skills()):
                result = await self._skill_manager.exit_skill(
                    skill_name=skill_name,
                    trigger=ExitTrigger.CONTEXT_PRESSURE,
                )
                actions.append({
                    "action": "evict_skill",
                    "skill": skill_name,
                    "tokens_freed": result.tokens_freed,
                })
            
            unused = await self._tool_manager.unload_unused_tools()
            if unused:
                actions.append({
                    "action": "unload_tools",
                    "tools": unused,
                })
        
        elif pressure_level > self._config.pressure_threshold:
            result = await self._skill_manager._evict_lru_skill()
            if result:
                actions.append({
                    "action": "evict_lru_skill",
                    "skill": result.skill_name,
                    "tokens_freed": result.tokens_freed,
                })
        
        return {
            "pressure_level": pressure_level,
            "actions_taken": actions,
            "new_stats": self._slot_manager.get_statistics(),
        }
    
    def check_context_pressure(self) -> float:
        """检查上下文压力级别"""
        stats = self._slot_manager.get_statistics()
        return stats["token_usage_ratio"]
    
    def get_context_report(self) -> Dict[str, Any]:
        """获取上下文报告"""
        return {
            "session_id": self._session_id,
            "initialized": self._initialized,
            "config": self._config.to_dict(),
            "slot_stats": self._slot_manager.get_statistics(),
            "skill_stats": self._skill_manager.get_statistics(),
            "tool_stats": self._tool_manager.get_statistics(),
            "skill_history": [
                r.to_dict() for r in self._skill_manager.get_skill_history()
            ],
        }
    
    def get_active_skills(self) -> List[str]:
        """获取活跃的Skill列表"""
        return self._skill_manager.get_active_skills()
    
    def get_dormant_skills(self) -> List[str]:
        """获取休眠的Skill列表"""
        return self._skill_manager.get_dormant_skills()
    
    def get_loaded_tools(self) -> List[str]:
        """获取已加载的工具列表"""
        return list(self._tool_manager.get_loaded_tools())
    
    def get_slot_manager(self) -> ContextSlotManager:
        """获取槽位管理器"""
        return self._slot_manager
    
    def get_skill_manager(self) -> SkillLifecycleManager:
        """获取Skill管理器"""
        return self._skill_manager
    
    def get_tool_manager(self) -> ToolLifecycleManager:
        """获取工具管理器"""
        return self._tool_manager
    
    def record_tool_usage(self, tool_name: str) -> None:
        """记录工具使用"""
        self._tool_manager.record_tool_usage(tool_name)
    
    async def shutdown(self) -> None:
        """关闭"""
        for skill_name in list(self._skill_manager.get_active_skills()):
            await self._skill_manager.exit_skill(
                skill_name=skill_name,
                trigger=ExitTrigger.MANUAL,
            )
        
        self._slot_manager.clear_all(keep_system=False)
        self._initialized = False
        
        logger.info(f"[Orchestrator] Shutdown for session: {self._session_id}")


def create_context_lifecycle(
    token_budget: int = 100000,
    max_active_skills: int = 3,
    max_tool_definitions: int = 20,
    pressure_threshold: float = 0.8,
    summary_generator: Optional[Callable] = None,
) -> ContextLifecycleOrchestrator:
    """创建上下文生命周期管理器"""
    config = ContextLifecycleConfig(
        token_budget=token_budget,
        max_active_skills=max_active_skills,
        max_tool_definitions=max_tool_definitions,
        pressure_threshold=pressure_threshold,
    )
    
    return ContextLifecycleOrchestrator(
        config=config,
        summary_generator=summary_generator,
    )