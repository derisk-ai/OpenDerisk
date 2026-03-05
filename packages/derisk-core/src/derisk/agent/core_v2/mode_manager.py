"""
ModeManager - 模式切换管理器

产品层接口，提供场景模式切换能力
支持快速切换通用模式、编码模式等

使用方式:
    # 获取模式管理器
    manager = ModeManager(agent)
    
    # 切换模式
    manager.switch_mode(TaskScene.CODING)
    
    # 获取可用模式列表（用于UI渲染）
    modes = manager.get_available_modes()
    
    # 创建自定义模式
    custom = manager.create_custom_mode("我的模式", TaskScene.CODING, {...})
"""

from typing import Dict, Any, List, Optional, Callable
from pydantic import BaseModel
from datetime import datetime
from enum import Enum
import logging
import asyncio
import copy

from derisk.agent.core_v2.task_scene import (
    TaskScene,
    SceneProfile,
    ContextPolicy,
    PromptPolicy,
)
from derisk.agent.core_v2.scene_registry import SceneRegistry
from derisk.agent.core_v2.context_processor import ContextProcessor, ContextProcessorFactory

logger = logging.getLogger(__name__)


class ModeSwitchResult(BaseModel):
    """模式切换结果"""
    success: bool
    from_scene: TaskScene
    to_scene: TaskScene
    message: str = ""
    timestamp: datetime
    
    applied_policies: List[str] = []
    warnings: List[str] = []


class ModeHistory(BaseModel):
    """模式历史记录"""
    scene: TaskScene
    name: str
    timestamp: datetime
    duration_seconds: float = 0


class ModeManager:
    """
    模式切换管理器
    
    职责:
    1. 管理当前模式状态
    2. 处理模式切换逻辑
    3. 应用策略配置到Agent
    4. 记录模式切换历史
    
    示例:
        manager = ModeManager(agent)
        manager.switch_mode(TaskScene.CODING)
    """
    
    def __init__(
        self,
        agent: Any,
        default_scene: TaskScene = TaskScene.GENERAL,
    ):
        """
        初始化模式管理器
        
        Args:
            agent: Agent实例
            default_scene: 默认场景
        """
        self.agent = agent
        self._current_scene = default_scene
        self._current_profile: Optional[SceneProfile] = None
        self._context_processor: Optional[ContextProcessor] = None
        
        self._scene_history: List[ModeHistory] = []
        self._switch_callbacks: List[Callable[[ModeSwitchResult], None]] = []
        self._scene_start_time: Optional[datetime] = None
        
        self._apply_default_profile()
    
    def _apply_default_profile(self) -> None:
        """应用默认场景配置"""
        profile = SceneRegistry.get(self._current_scene)
        if profile:
            self._current_profile = profile
            self._apply_profile(profile)
    
    def _apply_profile(self, profile: SceneProfile) -> List[str]:
        """
        应用场景配置到Agent
        
        Args:
            profile: 场景配置
            
        Returns:
            List[str]: 应用的策略列表
        """
        applied = []
        
        if hasattr(self.agent, 'context_policy'):
            self.agent.context_policy = profile.context_policy
            applied.append("context_policy")
        elif hasattr(self.agent, '_context_policy'):
            self.agent._context_policy = profile.context_policy
            applied.append("context_policy")
        
        if hasattr(self.agent, 'prompt_policy'):
            self.agent.prompt_policy = profile.prompt_policy
            applied.append("prompt_policy")
        elif hasattr(self.agent, '_prompt_policy'):
            self.agent._prompt_policy = profile.prompt_policy
            applied.append("prompt_policy")
        
        if hasattr(self.agent, 'max_steps'):
            self.agent.max_steps = profile.max_reasoning_steps
            applied.append("max_steps")
        
        if hasattr(self.agent, 'temperature'):
            self.agent.temperature = profile.prompt_policy.temperature
            applied.append("temperature")
        
        if hasattr(self.agent, 'max_tokens'):
            self.agent.max_tokens = profile.prompt_policy.max_tokens
            applied.append("max_tokens")
        
        if hasattr(self.agent, 'reasoning_strategy'):
            self.agent.reasoning_strategy = profile.reasoning_strategy
            applied.append("reasoning_strategy")
        
        if profile.tool_policy.preferred_tools and hasattr(self.agent, 'preferred_tools'):
            self.agent.preferred_tools = profile.tool_policy.preferred_tools
            applied.append("preferred_tools")
        
        self._rebuild_context_processor(profile)
        
        return applied
    
    def _rebuild_context_processor(self, profile: SceneProfile) -> None:
        """重建上下文处理器"""
        llm_client = getattr(self.agent, 'llm_client', None)
        self._context_processor = ContextProcessor(
            policy=profile.context_policy,
            llm_client=llm_client,
        )
    
    @property
    def current_scene(self) -> TaskScene:
        """获取当前场景"""
        return self._current_scene
    
    @property
    def current_profile(self) -> Optional[SceneProfile]:
        """获取当前场景配置"""
        return self._current_profile
    
    @property
    def context_processor(self) -> Optional[ContextProcessor]:
        """获取上下文处理器"""
        return self._context_processor
    
    def switch_mode(
        self,
        scene: TaskScene,
        force: bool = False,
    ) -> ModeSwitchResult:
        """
        切换任务模式
        
        Args:
            scene: 目标场景
            force: 是否强制切换（即使场景相同）
            
        Returns:
            ModeSwitchResult: 切换结果
        """
        result = ModeSwitchResult(
            success=False,
            from_scene=self._current_scene,
            to_scene=scene,
            timestamp=datetime.now(),
        )
        
        if scene == self._current_scene and not force:
            result.message = f"Already in {scene.value} mode"
            return result
        
        profile = SceneRegistry.get(scene)
        if not profile:
            result.message = f"Scene {scene.value} not found"
            return result
        
        self._record_history()
        
        try:
            applied = self._apply_profile(profile)
            
            old_scene = self._current_scene
            self._current_scene = scene
            self._current_profile = profile
            self._scene_start_time = datetime.now()
            
            result.success = True
            result.applied_policies = applied
            result.message = f"Switched from {old_scene.value} to {scene.value}"
            
            handler = SceneRegistry.get_handler(scene)
            if handler:
                try:
                    handler(self.agent, profile)
                except Exception as e:
                    result.warnings.append(f"Handler error: {str(e)}")
            
            self._notify_callbacks(result)
            
            logger.info(f"[ModeManager] Switched to {scene.value} mode, applied: {applied}")
            
        except Exception as e:
            result.message = f"Failed to switch: {str(e)}"
            logger.error(f"[ModeManager] Mode switch failed: {e}")
        
        return result
    
    def _record_history(self) -> None:
        """记录模式历史"""
        if self._scene_start_time:
            duration = (datetime.now() - self._scene_start_time).total_seconds()
            self._scene_history.append(ModeHistory(
                scene=self._current_scene,
                name=self._current_profile.name if self._current_profile else self._current_scene.value,
                timestamp=self._scene_start_time,
                duration_seconds=duration,
            ))
    
    def _notify_callbacks(self, result: ModeSwitchResult) -> None:
        """通知回调函数"""
        for callback in self._switch_callbacks:
            try:
                callback(result)
            except Exception as e:
                logger.error(f"[ModeManager] Callback error: {e}")
    
    def on_mode_switch(self, callback: Callable[[ModeSwitchResult], None]) -> None:
        """
        注册模式切换回调
        
        Args:
            callback: 回调函数
        """
        self._switch_callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[ModeSwitchResult], None]) -> None:
        """移除回调"""
        if callback in self._switch_callbacks:
            self._switch_callbacks.remove(callback)
    
    def get_available_modes(self) -> List[Dict[str, Any]]:
        """
        获取可用模式列表
        
        用于UI渲染模式选择
        
        Returns:
            List[Dict]: 模式列表
        """
        modes = SceneRegistry.list_scene_names()
        
        for mode in modes:
            mode["is_current"] = (mode["scene"] == self._current_scene.value)
        
        return modes
    
    def create_custom_mode(
        self,
        name: str,
        base: TaskScene,
        context_overrides: Optional[Dict[str, Any]] = None,
        prompt_overrides: Optional[Dict[str, Any]] = None,
        tool_overrides: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_register: bool = True,
    ) -> SceneProfile:
        """
        创建自定义模式
        
        Args:
            name: 模式名称
            base: 基础场景
            context_overrides: 上下文策略覆盖
            prompt_overrides: Prompt策略覆盖
            tool_overrides: 工具策略覆盖
            metadata: 元数据
            auto_register: 是否自动注册
            
        Returns:
            SceneProfile: 创建的场景配置
        """
        custom_profile = SceneRegistry.create_custom(
            name=name,
            base=base,
            context_overrides=context_overrides,
            prompt_overrides=prompt_overrides,
            tool_overrides=tool_overrides,
            metadata=metadata,
        )
        
        if auto_register:
            SceneRegistry.register_custom(custom_profile)
        
        logger.info(f"[ModeManager] Created custom mode: {name}")
        
        return custom_profile
    
    def switch_to_custom_mode(
        self,
        name: str,
        base: TaskScene = TaskScene.GENERAL,
        **overrides
    ) -> ModeSwitchResult:
        """
        创建并切换到自定义模式
        
        Args:
            name: 模式名称
            base: 基础场景
            **overrides: 策略覆盖配置
            
        Returns:
            ModeSwitchResult: 切换结果
        """
        custom_profile = self.create_custom_mode(name, base, auto_register=True, **overrides)
        
        return self.switch_mode(custom_profile.scene, force=True)
    
    def suggest_mode(self, task_description: str) -> TaskScene:
        """
        根据任务描述建议最合适的模式
        
        Args:
            task_description: 任务描述
            
        Returns:
            TaskScene: 建议的场景
        """
        desc_lower = task_description.lower()
        
        coding_keywords = [
            "代码", "code", "编程", "programming", "实现", "implement",
            "开发", "develop", "写", "write", "修改", "modify", "重构", "refactor",
            "bug", "fix", "修复", "调试", "debug", "测试", "test",
            "函数", "function", "类", "class", "方法", "method",
        ]
        
        analysis_keywords = [
            "分析", "analyze", "数据", "data", "统计", "statistics",
            "日志", "log", "性能", "performance", "问题", "problem",
        ]
        
        creative_keywords = [
            "创意", "creative", "设计", "design", "写作", "write",
            "故事", "story", "文章", "article", "头脑风暴", "brainstorm",
        ]
        
        research_keywords = [
            "研究", "research", "调查", "investigate", "探索", "explore",
            "收集", "collect", "整理", "organize", "学习", "learn",
        ]
        
        doc_keywords = [
            "文档", "documentation", "readme", "说明", "instruction",
            "注释", "comment", "帮助", "help",
        ]
        
        def count_matches(keywords: List[str]) -> int:
            return sum(1 for kw in keywords if kw in desc_lower)
        
        scores = {
            TaskScene.CODING: count_matches(coding_keywords),
            TaskScene.ANALYSIS: count_matches(analysis_keywords),
            TaskScene.CREATIVE: count_matches(creative_keywords),
            TaskScene.RESEARCH: count_matches(research_keywords),
            TaskScene.DOCUMENTATION: count_matches(doc_keywords),
        }
        
        if max(scores.values()) >= 2:
            return max(scores, key=scores.get)
        
        if "test" in desc_lower or "测试" in desc_lower:
            return TaskScene.TESTING
        
        if "refactor" in desc_lower or "重构" in desc_lower:
            return TaskScene.REFACTORING
        
        if "debug" in desc_lower or "调试" in desc_lower or "bug" in desc_lower:
            return TaskScene.DEBUG
        
        return TaskScene.GENERAL
    
    def auto_switch_mode(self, task_description: str) -> ModeSwitchResult:
        """
        根据任务描述自动切换模式
        
        Args:
            task_description: 任务描述
            
        Returns:
            ModeSwitchResult: 切换结果
        """
        suggested_scene = self.suggest_mode(task_description)
        return self.switch_mode(suggested_scene)
    
    def get_history(self, limit: int = 10) -> List[ModeHistory]:
        """
        获取模式切换历史
        
        Args:
            limit: 最大返回数量
            
        Returns:
            List[ModeHistory]: 历史记录
        """
        return self._scene_history[-limit:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict: 统计信息
        """
        scene_durations: Dict[str, float] = {}
        
        for history in self._scene_history:
            scene_key = history.scene.value
            scene_durations[scene_key] = scene_durations.get(scene_key, 0) + history.duration_seconds
        
        total_duration = sum(scene_durations.values())
        
        return {
            "current_scene": self._current_scene.value,
            "total_switches": len(self._scene_history),
            "scene_durations": scene_durations,
            "total_duration_seconds": total_duration,
            "most_used_scene": max(scene_durations, key=scene_durations.get) if scene_durations else None,
        }
    
    def reset_to_default(self) -> ModeSwitchResult:
        """重置为默认模式"""
        return self.switch_mode(TaskScene.GENERAL)
    
    def update_current_policy(
        self,
        context_updates: Optional[Dict[str, Any]] = None,
        prompt_updates: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        更新当前模式的策略配置
        
        Args:
            context_updates: 上下文策略更新
            prompt_updates: Prompt策略更新
            
        Returns:
            bool: 是否成功
        """
        if not self._current_profile:
            return False
        
        try:
            if context_updates:
                policy_dict = self._current_profile.context_policy.dict()
                for k, v in context_updates.items():
                    if "." in k:
                        parts = k.split(".")
                        d = policy_dict
                        for p in parts[:-1]:
                            d = d.setdefault(p, {})
                        d[parts[-1]] = v
                    else:
                        policy_dict[k] = v
                self._current_profile.context_policy = ContextPolicy(**policy_dict)
            
            if prompt_updates:
                policy_dict = self._current_profile.prompt_policy.dict()
                for k, v in prompt_updates.items():
                    if "." in k:
                        parts = k.split(".")
                        d = policy_dict
                        for p in parts[:-1]:
                            d = d.setdefault(p, {})
                        d[parts[-1]] = v
                    else:
                        policy_dict[k] = v
                self._current_profile.prompt_policy = PromptPolicy(**policy_dict)
            
            self._apply_profile(self._current_profile)
            
            return True
        except Exception as e:
            logger.error(f"[ModeManager] Failed to update policy: {e}")
            return False


class ModeManagerFactory:
    """模式管理器工厂"""
    
    _instances: Dict[str, ModeManager] = {}
    
    @classmethod
    def get(cls, agent_id: str, agent: Any) -> ModeManager:
        """获取或创建模式管理器"""
        if agent_id not in cls._instances:
            cls._instances[agent_id] = ModeManager(agent)
        return cls._instances[agent_id]
    
    @classmethod
    def get_by_agent(cls, agent: Any) -> ModeManager:
        """通过Agent实例获取模式管理器"""
        agent_id = getattr(agent, 'agent_id', id(agent))
        return cls.get(str(agent_id), agent)
    
    @classmethod
    def remove(cls, agent_id: str) -> None:
        """移除模式管理器"""
        cls._instances.pop(agent_id, None)
    
    @classmethod
    def clear(cls) -> None:
        """清除所有实例"""
        cls._instances.clear()


def get_mode_manager(agent: Any) -> ModeManager:
    """便捷函数：获取模式管理器"""
    return ModeManagerFactory.get_by_agent(agent)