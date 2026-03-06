"""
分层上下文索引集成模块

为 ReActMasterAgent 提供 Hierarchical Context Index 系统的集成。

核心特性：
1. 章节式索引：按任务阶段组织历史
2. 优先级压缩：基于内容重要性差异化处理
3. 主动回溯：Agent可通过工具回顾历史
4. 文件系统集成：压缩内容持久化
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from derisk.agent.shared.hierarchical_context import (
    ChapterIndexer,
    ContentPrioritizer,
    ContentPriority,
    PhaseTransitionDetector,
    RecallTool,
    TaskPhase,
    HierarchicalContextConfig,
)

if TYPE_CHECKING:
    from derisk.agent import ActionOutput, AgentMessage
    from derisk.agent.core.file_system.agent_file_system import AgentFileSystem

logger = logging.getLogger(__name__)


class HierarchicalContextManager:
    """
    分层上下文管理器
    
    统一管理章节索引、优先级分类、阶段检测等组件。
    
    使用示例:
        manager = HierarchicalContextManager(file_system=afs)
        
        # 初始化任务
        await manager.start_task("构建上下文管理系统")
        
        # 记录执行步骤
        await manager.record_step(action_out)
        
        # 获取上下文
        context = manager.get_context_for_prompt()
    """
    
    def __init__(
        self,
        file_system: Optional[AgentFileSystem] = None,
        config: Optional[HierarchicalContextConfig] = None,
        session_id: Optional[str] = None,
        enable_phase_detection: bool = True,
        enable_recall_tool: bool = True,
    ):
        self.file_system = file_system
        self.config = config or HierarchicalContextConfig()
        self.session_id = session_id or "default"
        self.enable_phase_detection = enable_phase_detection
        self.enable_recall_tool = enable_recall_tool
        
        self._chapter_indexer = ChapterIndexer(
            file_system=file_system,
            config=self.config,
            session_id=self.session_id,
        )
        
        self._content_prioritizer = ContentPrioritizer()
        
        self._phase_detector = None
        if enable_phase_detection:
            self._phase_detector = PhaseTransitionDetector()
        
        self._recall_tool = None
        if enable_recall_tool:
            self._recall_tool = RecallTool(chapter_indexer=self._chapter_indexer)
        
        self._is_initialized = False
        self._step_count = 0
    
    async def initialize(self, task_description: str = "") -> None:
        """
        初始化管理器
        
        Args:
            task_description: 任务描述
        """
        if self._is_initialized:
            return
        
        self._chapter_indexer.create_chapter(
            phase=TaskPhase.EXPLORATION,
            title="任务开始",
            description=task_description or "开始执行任务",
        )
        
        self._is_initialized = True
        logger.info(f"[HierarchicalContextManager] Initialized for task: {task_description[:50]}...")
    
    async def start_task(self, task: str) -> None:
        """
        开始新任务
        
        Args:
            task: 任务描述
        """
        await self.initialize(task)
    
    async def record_step(
        self,
        action_out: ActionOutput,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        记录执行步骤
        
        Args:
            action_out: 动作输出
            metadata: 元数据
            
        Returns:
            创建的 section_id
        """
        self._step_count += 1
        
        action_name = getattr(action_out, "name", "") or getattr(action_out, "action", "") or "unknown"
        content = getattr(action_out, "content", "") or ""
        success = getattr(action_out, "is_exe_success", True)
        
        priority = self._content_prioritizer.classify_message_from_action(action_out)
        
        if self._phase_detector:
            new_phase = self._phase_detector.detect_phase(action_out)
            if new_phase:
                await self._handle_phase_transition(new_phase)
        
        section = await self._chapter_indexer.add_section(
            step_name=action_name,
            content=str(content),
            priority=priority,
            metadata={
                "success": success,
                "step_number": self._step_count,
                **(metadata or {}),
            },
        )
        
        logger.debug(
            f"[HierarchicalContextManager] Recorded step {self._step_count}: "
            f"{action_name} ({priority.value})"
        )
        
        return section.section_id
    
    async def _handle_phase_transition(self, new_phase: TaskPhase) -> None:
        """处理阶段转换"""
        current_chapter = self._chapter_indexer.get_current_chapter()
        
        if current_chapter:
            current_chapter.is_compacted = True
            current_chapter.summary = f"Completed {current_chapter.phase.value} phase with {len(current_chapter.sections)} steps"
        
        self._chapter_indexer.create_chapter(
            phase=new_phase,
            title=f"{new_phase.value.capitalize()} Phase",
            description=f"Transitioned to {new_phase.value} phase",
        )
        
        logger.info(f"[HierarchicalContextManager] Phase transition to: {new_phase.value}")
    
    def get_context_for_prompt(self, token_budget: int = 30000) -> str:
        """
        获取分层上下文用于prompt
        
        Args:
            token_budget: token预算
            
        Returns:
            格式化的上下文字符串
        """
        return self._chapter_indexer.get_context_for_prompt(token_budget=token_budget)
    
    def get_recall_tool(self) -> Optional[RecallTool]:
        """获取回溯工具"""
        return self._recall_tool
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self._chapter_indexer.get_statistics()
        stats["step_count"] = self._step_count
        stats["is_initialized"] = self._is_initialized
        
        if self._phase_detector:
            stats["phase_detector"] = self._phase_detector.get_statistics()
        
        if self._content_prioritizer:
            stats["prioritizer"] = self._content_prioritizer.get_statistics()
        
        return stats
    
    def get_current_phase(self) -> Optional[TaskPhase]:
        """获取当前阶段"""
        if self._phase_detector:
            return self._phase_detector.get_current_phase()
        return self._chapter_indexer.get_current_phase()
    
    async def recall_section(self, section_id: str) -> Optional[str]:
        """回溯特定步骤"""
        return await self._chapter_indexer.recall_section(section_id)
    
    async def search_history(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索历史"""
        return await self._chapter_indexer.search_by_query(query, limit)
    
    def set_file_system(self, file_system: AgentFileSystem) -> None:
        """设置文件系统"""
        self.file_system = file_system
        self._chapter_indexer.file_system = file_system
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化"""
        return {
            "session_id": self.session_id,
            "config": self.config.to_dict(),
            "chapter_indexer": self._chapter_indexer.to_dict(),
            "step_count": self._step_count,
            "is_initialized": self._is_initialized,
        }
    
    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        file_system: Optional[AgentFileSystem] = None,
    ) -> "HierarchicalContextManager":
        """反序列化"""
        config = HierarchicalContextConfig.from_dict(data.get("config", {}))
        
        manager = cls(
            file_system=file_system,
            config=config,
            session_id=data.get("session_id", "default"),
        )
        
        if "chapter_indexer" in data:
            manager._chapter_indexer = ChapterIndexer.from_dict(
                data["chapter_indexer"],
                file_system=file_system,
            )
        
        manager._step_count = data.get("step_count", 0)
        manager._is_initialized = data.get("is_initialized", False)
        
        return manager


def create_hierarchical_context_manager(
    file_system: Optional[AgentFileSystem] = None,
    config: Optional[HierarchicalContextConfig] = None,
    session_id: Optional[str] = None,
    **kwargs,
) -> HierarchicalContextManager:
    """
    创建分层上下文管理器
    
    Args:
        file_system: Agent文件系统
        config: 配置
        session_id: 会话ID
        **kwargs: 其他参数
        
    Returns:
        HierarchicalContextManager 实例
    """
    return HierarchicalContextManager(
        file_system=file_system,
        config=config,
        session_id=session_id,
        **kwargs,
    )