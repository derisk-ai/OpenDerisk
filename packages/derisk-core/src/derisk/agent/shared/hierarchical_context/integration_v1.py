"""
ReActMasterAgent 分层上下文集成

为 ReActMasterAgent 提供 Hierarchical Context Index 系统的集成 Mixin。

使用方式：
    class ReActMasterAgent(HierarchicalContextMixin, ConversableAgent):
        ...
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from derisk.agent.shared.hierarchical_context import (
    HierarchicalContextConfig,
    HierarchicalContextManager,
    TaskPhase,
    create_hierarchical_context_manager,
)

if TYPE_CHECKING:
    from derisk.agent import ActionOutput, AgentMessage
    from derisk.agent.core.file_system.agent_file_system import AgentFileSystem

logger = logging.getLogger(__name__)


class HierarchicalContextMixin:
    """
    分层上下文集成 Mixin
    
    为 Agent 提供分层上下文索引能力。
    
    需要在 Agent 类中添加以下属性和配置：
    - enable_hierarchical_context: bool
    - _hierarchical_context_manager: Optional[HierarchicalContextManager]
    - _agent_file_system: Optional[AgentFileSystem]
    """
    
    @property
    def hierarchical_context(self) -> Optional[HierarchicalContextManager]:
        """获取分层上下文管理器"""
        return getattr(self, "_hierarchical_context_manager", None)
    
    def _init_hierarchical_context(self) -> None:
        """初始化分层上下文系统"""
        if not getattr(self, "enable_hierarchical_context", False):
            return
        
        config = self._get_hierarchical_context_config()
        
        self._hierarchical_context_manager = create_hierarchical_context_manager(
            file_system=getattr(self, "_agent_file_system", None),
            config=config,
            session_id=getattr(self, "conv_id", "default"),
        )
        
        logger.info("[HierarchicalContextMixin] Initialized hierarchical context system")
    
    def _get_hierarchical_context_config(self) -> HierarchicalContextConfig:
        """获取分层上下文配置"""
        return HierarchicalContextConfig(
            max_chapter_tokens=getattr(self, "hierarchical_max_chapter_tokens", 10000),
            max_section_tokens=getattr(self, "hierarchical_max_section_tokens", 2000),
            recent_chapters_full=getattr(self, "hierarchical_recent_chapters_full", 2),
            middle_chapters_index=getattr(self, "hierarchical_middle_chapters_index", 3),
            early_chapters_summary=getattr(self, "hierarchical_early_chapters_summary", 5),
        )
    
    async def _ensure_hierarchical_context_initialized(self) -> None:
        """确保分层上下文系统已初始化"""
        if not getattr(self, "_hierarchical_context_manager", None):
            self._init_hierarchical_context()
        
        manager = self._hierarchical_context_manager
        if manager and not manager._is_initialized:
            task = getattr(self, "_current_task", "执行任务")
            await manager.initialize(task)
    
    async def _start_hierarchical_task(self, task: str) -> None:
        """开始新任务的分层记录"""
        self._current_task = task
        
        if not getattr(self, "enable_hierarchical_context", False):
            return
        
        await self._ensure_hierarchical_context_initialized()
        
        if self._hierarchical_context_manager:
            await self._hierarchical_context_manager.start_task(task)
            logger.debug(f"[HierarchicalContextMixin] Started task: {task[:50]}...")
    
    async def _record_hierarchical_step(
        self,
        action_out: ActionOutput,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """记录执行步骤到分层索引"""
        if not getattr(self, "enable_hierarchical_context", False):
            return None
        
        if not getattr(self, "_hierarchical_context_manager", None):
            return None
        
        return await self._hierarchical_context_manager.record_step(action_out, metadata)
    
    def _get_hierarchical_context_for_prompt(self, token_budget: int = 30000) -> str:
        """获取分层上下文用于prompt"""
        if not getattr(self, "_hierarchical_context_manager", None):
            return ""
        
        return self._hierarchical_context_manager.get_context_for_prompt(token_budget)
    
    def _get_hierarchical_recall_tools(self) -> List[Any]:
        """获取分层上下文回溯工具"""
        if not getattr(self, "_hierarchical_context_manager", None):
            return []
        
        recall_tool = self._hierarchical_context_manager.get_recall_tool()
        if recall_tool:
            return [recall_tool]
        return []
    
    def _get_hierarchical_statistics(self) -> Dict[str, Any]:
        """获取分层上下文统计信息"""
        if not getattr(self, "_hierarchical_context_manager", None):
            return {"enabled": False}
        
        stats = self._hierarchical_context_manager.get_statistics()
        stats["enabled"] = True
        return stats
    
    def _update_hierarchical_file_system(self, file_system: AgentFileSystem) -> None:
        """更新分层上下文的文件系统"""
        if getattr(self, "_hierarchical_context_manager", None):
            self._hierarchical_context_manager.set_file_system(file_system)


def integrate_hierarchical_context(agent_class: type) -> type:
    """
    装饰器：为 Agent 类集成分层上下文能力
    
    使用示例：
        @integrate_hierarchical_context
        class MyAgent(ConversableAgent):
            enable_hierarchical_context = True
            ...
    """
    
    original_init = agent_class.__init__
    original_preload = getattr(agent_class, "preload_resource", None)
    
    def new_init(self, **kwargs):
        original_init(self, **kwargs)
        
        if getattr(self, "enable_hierarchical_context", False):
            self._init_hierarchical_context()
    
    async def new_preload(self):
        if original_preload:
            await original_preload(self)
        
        if getattr(self, "enable_hierarchical_context", False):
            afs = getattr(self, "_agent_file_system", None)
            if afs and hasattr(self, "_update_hierarchical_file_system"):
                self._update_hierarchical_file_system(afs)
    
    agent_class.__init__ = new_init
    if original_preload:
        agent_class.preload_resource = new_preload
    
    return agent_class


class HierarchicalContextIntegration:
    """
    分层上下文集成器
    
    提供便捷的集成方法。
    """
    
    @staticmethod
    def add_to_agent(agent: Any, config: Optional[HierarchicalContextConfig] = None) -> None:
        """
        为现有 Agent 添加分层上下文能力
        
        Args:
            agent: Agent 实例
            config: 配置
        """
        agent.enable_hierarchical_context = True
        
        if config:
            agent._hierarchical_context_config = config
        
        agent._hierarchical_context_manager = create_hierarchical_context_manager(
            file_system=getattr(agent, "_agent_file_system", None),
            config=config,
            session_id=getattr(agent, "conv_id", "default"),
        )
        
        logger.info(f"[HierarchicalContextIntegration] Added to agent: {agent}")
    
    @staticmethod
    def get_context_report(agent: Any) -> Dict[str, Any]:
        """
        获取 Agent 的分层上下文报告
        
        Args:
            agent: Agent 实例
            
        Returns:
            上下文报告
        """
        manager = getattr(agent, "_hierarchical_context_manager", None)
        if not manager:
            return {"error": "Hierarchical context not enabled"}
        
        return {
            "statistics": manager.get_statistics(),
            "current_phase": manager.get_current_phase().value if manager.get_current_phase() else None,
            "chapters": [
                {
                    "id": c.chapter_id,
                    "phase": c.phase.value,
                    "title": c.title,
                    "sections": len(c.sections),
                }
                for c in manager._chapter_indexer._chapters
            ],
        }