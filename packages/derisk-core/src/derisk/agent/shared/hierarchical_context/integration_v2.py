"""
Core V2 分层上下文集成

为 Core V2 架构的 AgentHarness 提供分层上下文索引集成。

与 AgentFileSystem 深度集成，支持：
1. 检查点保存/恢复
2. 章节索引持久化
3. 回溯工具动态注入到 Function Call 工具列表
4. Prompt 集成
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .chapter_indexer import ChapterIndexer
from .hierarchical_context_index import TaskPhase, HierarchicalContextConfig
from .hierarchical_context_manager import HierarchicalContextManager, create_hierarchical_context_manager
from .recall_tool import RecallToolManager
from .prompt_integration import integrate_hierarchical_context_to_prompt, DEFAULT_HIERARCHICAL_PROMPT_CONFIG

if TYPE_CHECKING:
    from derisk.agent.core.file_system.agent_file_system import AgentFileSystem
    from derisk.agent.resource.tool.base import FunctionTool

logger = logging.getLogger(__name__)


@dataclass
class HierarchicalContextCheckpoint:
    """分层上下文检查点数据"""
    chapter_indexer_data: Dict[str, Any]
    step_count: int
    current_phase: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_indexer_data": self.chapter_indexer_data,
            "step_count": self.step_count,
            "current_phase": self.current_phase,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HierarchicalContextCheckpoint":
        return cls(
            chapter_indexer_data=data["chapter_indexer_data"],
            step_count=data["step_count"],
            current_phase=data["current_phase"],
        )


class HierarchicalContextV2Integration:
    """
    Core V2 分层上下文集成器
    
    完整功能：
    1. 检查点保存/恢复
    2. 章节索引持久化
    3. 回溯工具动态注入
    4. Prompt 集成
    
    使用示例:
        harness = AgentHarness(agent)
        
        # 创建集成器
        hc_integration = HierarchicalContextV2Integration(
            file_system=afs,
            llm_client=client,
        )
        
        # 开始执行
        await hc_integration.start_execution(execution_id, task)
        
        # 获取回溯工具（动态注入到 Agent）
        tools = hc_integration.get_recall_tools(execution_id)
        for tool in tools:
            agent.available_system_tools[tool.name] = tool
        
        # 获取上下文（注入到 Prompt）
        context = hc_integration.get_context_for_prompt(execution_id)
        system_prompt = integrate_hierarchical_context_to_prompt(
            original_prompt, context
        )
    """
    
    def __init__(
        self,
        file_system: Optional[AgentFileSystem] = None,
        llm_client: Optional[Any] = None,
        config: Optional[HierarchicalContextConfig] = None,
    ):
        self.file_system = file_system
        self.llm_client = llm_client
        self.config = config or HierarchicalContextConfig()
        
        self._managers: Dict[str, HierarchicalContextManager] = {}
        self._recall_tool_managers: Dict[str, RecallToolManager] = {}
        self._is_initialized = False
    
    async def initialize(self) -> None:
        """初始化集成器"""
        if self._is_initialized:
            return
        self._is_initialized = True
        logger.info("[HierarchicalContextV2Integration] Initialized")
    
    async def start_execution(
        self,
        execution_id: str,
        task: str,
    ) -> HierarchicalContextManager:
        """
        开始新执行
        
        Args:
            execution_id: 执行ID
            task: 任务描述
            
        Returns:
            分层上下文管理器
        """
        if not self._is_initialized:
            await self.initialize()
        
        manager = create_hierarchical_context_manager(
            file_system=self.file_system,
            config=self.config,
            session_id=execution_id,
        )
        
        await manager.start_task(task)
        
        self._managers[execution_id] = manager
        
        # 创建回溯工具管理器
        self._recall_tool_managers[execution_id] = RecallToolManager(
            chapter_indexer=manager._chapter_indexer,
            file_system=self.file_system,
        )
        
        logger.info(f"[HierarchicalContextV2Integration] Started execution: {execution_id[:8]}")
        
        return manager
    
    async def record_step(
        self,
        execution_id: str,
        action_out: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """记录执行步骤"""
        manager = self._managers.get(execution_id)
        if not manager:
            return None
        
        return await manager.record_step(action_out, metadata)
    
    def get_context_for_prompt(
        self,
        execution_id: str,
        token_budget: int = 30000,
    ) -> str:
        """获取分层上下文用于prompt（已包含section_id）"""
        manager = self._managers.get(execution_id)
        if not manager:
            return ""
        
        return manager.get_context_for_prompt(token_budget)
    
    def get_recall_tools(self, execution_id: str) -> List[FunctionTool]:
        """
        获取回溯工具列表（动态注入到 Agent 的 available_system_tools）
        
        只在有压缩章节记录时才返回工具
        
        Returns:
            FunctionTool 列表
        """
        manager = self._recall_tool_managers.get(execution_id)
        if not manager:
            return []
        
        return manager.get_tools()
    
    def should_inject_tools(self, execution_id: str) -> bool:
        """判断是否应该注入回溯工具"""
        manager = self._recall_tool_managers.get(execution_id)
        if not manager:
            return False
        return manager.should_inject_tools()
    
    def get_integrated_system_prompt(
        self,
        execution_id: str,
        original_prompt: str,
    ) -> str:
        """
        获取集成了分层上下文的系统提示
        
        Args:
            execution_id: 执行ID
            original_prompt: 原始系统提示
            
        Returns:
            集成后的系统提示
        """
        context = self.get_context_for_prompt(execution_id)
        if not context:
            return original_prompt
        
        return integrate_hierarchical_context_to_prompt(
            original_system_prompt=original_prompt,
            hierarchical_context=context,
        )
    
    def get_checkpoint_data(self, execution_id: str) -> Optional[HierarchicalContextCheckpoint]:
        """获取检查点数据"""
        manager = self._managers.get(execution_id)
        if not manager:
            return None
        
        chapter_indexer_data = manager._chapter_indexer.to_dict()
        current_phase = manager.get_current_phase()
        
        return HierarchicalContextCheckpoint(
            chapter_indexer_data=chapter_indexer_data,
            step_count=manager._step_count,
            current_phase=current_phase.value if current_phase else "unknown",
        )
    
    async def restore_from_checkpoint(
        self,
        execution_id: str,
        checkpoint_data: HierarchicalContextCheckpoint,
    ) -> bool:
        """从检查点恢复"""
        try:
            manager = create_hierarchical_context_manager(
                file_system=self.file_system,
                config=self.config,
                session_id=execution_id,
            )
            
            manager._chapter_indexer = ChapterIndexer.from_dict(
                checkpoint_data.chapter_indexer_data,
                file_system=self.file_system,
            )
            
            manager._step_count = checkpoint_data.step_count
            manager._is_initialized = True
            
            self._managers[execution_id] = manager
            
            # 重新创建回溯工具管理器
            self._recall_tool_managers[execution_id] = RecallToolManager(
                chapter_indexer=manager._chapter_indexer,
                file_system=self.file_system,
            )
            
            logger.info(f"[HierarchicalContextV2Integration] Restored from checkpoint: {execution_id[:8]}")
            
            return True
            
        except Exception as e:
            logger.error(f"[HierarchicalContextV2Integration] Failed to restore: {e}")
            return False
    
    def get_statistics(self, execution_id: str) -> Dict[str, Any]:
        """获取统计信息"""
        manager = self._managers.get(execution_id)
        if not manager:
            return {"error": "No manager for execution"}
        
        return manager.get_statistics()
    
    def update_file_system(self, file_system: AgentFileSystem) -> None:
        """更新文件系统引用"""
        self.file_system = file_system
        
        for manager in self._managers.values():
            manager.set_file_system(file_system)
        
        for tool_manager in self._recall_tool_managers.values():
            tool_manager.update_file_system(file_system)
    
    async def cleanup_execution(self, execution_id: str) -> None:
        """清理执行上下文"""
        if execution_id in self._managers:
            del self._managers[execution_id]
        if execution_id in self._recall_tool_managers:
            del self._recall_tool_managers[execution_id]
        
        logger.info(f"[HierarchicalContextV2Integration] Cleaned up execution: {execution_id[:8]}")


def create_v2_integration(
    file_system: Optional[AgentFileSystem] = None,
    llm_client: Optional[Any] = None,
    config: Optional[HierarchicalContextConfig] = None,
) -> HierarchicalContextV2Integration:
    """创建 Core V2 集成器"""
    return HierarchicalContextV2Integration(
        file_system=file_system,
        llm_client=llm_client,
        config=config,
    )