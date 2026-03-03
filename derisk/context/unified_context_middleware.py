"""
统一上下文中间件

核心职责：
1. 整合 HierarchicalContextV2Integration
2. 实现 WorkLog → Section 转换
3. 协调 GptsMemory 和 AgentFileSystem
4. 提供统一的历史加载接口
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import logging
import json

from derisk.agent.shared.hierarchical_context import (
    HierarchicalContextV2Integration,
    HierarchicalContextConfig,
    HierarchicalContextManager,
    ChapterIndexer,
    TaskPhase,
    ContentPriority,
    Section,
    Chapter,
    CompactionStrategy,
    HierarchicalCompactionConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class ContextLoadResult:
    """上下文加载结果"""
    
    conv_id: str
    task_description: str
    chapter_index: ChapterIndexer
    hierarchical_context_text: str
    recent_messages: List[Any]
    recall_tools: List[Any]
    stats: Dict[str, Any] = field(default_factory=dict)
    hc_integration: Optional[HierarchicalContextV2Integration] = None


class UnifiedContextMiddleware:
    """
    统一上下文中间件
    
    核心职责：
    1. 整合 HierarchicalContextV2Integration
    2. 实现 WorkLog → Section 转换
    3. 协调 GptsMemory 和 AgentFileSystem
    4. 提供统一的历史加载接口
    """
    
    def __init__(
        self,
        gpts_memory: Any,
        agent_file_system: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        hc_config: Optional[HierarchicalContextConfig] = None,
        compaction_config: Optional[HierarchicalCompactionConfig] = None,
    ):
        self.gpts_memory = gpts_memory
        self.file_system = agent_file_system
        self.llm_client = llm_client
        
        self.hc_config = hc_config or HierarchicalContextConfig()
        self.compaction_config = compaction_config or HierarchicalCompactionConfig(
            enabled=True,
            strategy=CompactionStrategy.LLM_SUMMARY,
            token_threshold=40000,
        )
        
        self.hc_integration = HierarchicalContextV2Integration(
            file_system=agent_file_system,
            llm_client=llm_client,
            config=self.hc_config,
        )
        
        self._conv_contexts: Dict[str, ContextLoadResult] = {}
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """初始化中间件"""
        await self.hc_integration.initialize()
        logger.info("[UnifiedContextMiddleware] 初始化完成")
    
    async def load_context(
        self,
        conv_id: str,
        task_description: Optional[str] = None,
        include_worklog: bool = True,
        token_budget: int = 12000,
        force_reload: bool = False,
    ) -> ContextLoadResult:
        """加载完整的历史上下文（主入口）"""
        
        if not force_reload and conv_id in self._conv_contexts:
            logger.debug(f"[UnifiedContextMiddleware] 使用缓存上下文: {conv_id[:8]}")
            return self._conv_contexts[conv_id]
        
        async with self._lock:
            if not task_description:
                task_description = await self._infer_task_description(conv_id)
            
            hc_manager = await self.hc_integration.start_execution(
                execution_id=conv_id,
                task=task_description,
            )
            
            recent_messages = await self._load_recent_messages(conv_id)
            
            if include_worklog:
                await self._load_and_convert_worklog(conv_id, hc_manager)
            
            if self.compaction_config.enabled:
                await hc_manager._auto_compact_if_needed()
            
            hierarchical_context_text = self.hc_integration.get_context_for_prompt(
                execution_id=conv_id,
                token_budget=token_budget,
            )
            
            recall_tools = self.hc_integration.get_recall_tools(conv_id)
            
            result = ContextLoadResult(
                conv_id=conv_id,
                task_description=task_description,
                chapter_index=hc_manager._chapter_indexer,
                hierarchical_context_text=hierarchical_context_text,
                recent_messages=recent_messages,
                recall_tools=recall_tools,
                stats=hc_manager.get_statistics(),
                hc_integration=self.hc_integration,
            )
            
            self._conv_contexts[conv_id] = result
            
            logger.info(
                f"[UnifiedContextMiddleware] 已加载上下文 {conv_id[:8]}: "
                f"chapters={result.stats.get('chapter_count', 0)}, "
                f"context_tokens={len(hierarchical_context_text) // 4}"
            )
            
            return result
    
    async def _load_and_convert_worklog(
        self,
        conv_id: str,
        hc_manager: HierarchicalContextManager,
    ) -> None:
        """加载 WorkLog 并转换为 Section 结构"""
        
        worklog = await self.gpts_memory.get_work_log(conv_id)
        
        if not worklog:
            logger.debug(f"[UnifiedContextMiddleware] 无 WorkLog: {conv_id[:8]}")
            return
        
        logger.info(f"[UnifiedContextMiddleware] 转换 {len(worklog)} 个 WorkEntry")
        
        phase_entries = await self._group_worklog_by_phase(worklog)
        
        for phase, entries in phase_entries.items():
            if not entries:
                continue
            
            chapter = await self._create_chapter_from_phase(conv_id, phase, entries)
            hc_manager._chapter_indexer.add_chapter(chapter)
        
        logger.info(
            f"[UnifiedContextMiddleware] 创建 {len(phase_entries)} 个章节 "
            f"从 WorkLog: {conv_id[:8]}"
        )
    
    async def _group_worklog_by_phase(
        self,
        worklog: List[Any],
    ) -> Dict[TaskPhase, List[Any]]:
        """将 WorkLog 按任务阶段分组"""
        
        phase_entries = {
            TaskPhase.EXPLORATION: [],
            TaskPhase.DEVELOPMENT: [],
            TaskPhase.DEBUGGING: [],
            TaskPhase.REFINEMENT: [],
            TaskPhase.DELIVERY: [],
        }
        
        current_phase = TaskPhase.EXPLORATION
        exploration_tools = {"read", "glob", "grep", "search", "think"}
        development_tools = {"write", "edit", "bash", "execute", "run"}
        refinement_keywords = {"refactor", "optimize", "improve", "enhance"}
        delivery_keywords = {"summary", "document", "conclusion", "report"}
        
        for entry in worklog:
            if hasattr(entry, 'metadata') and "phase" in entry.metadata:
                phase_value = entry.metadata["phase"]
                if isinstance(phase_value, str):
                    try:
                        current_phase = TaskPhase(phase_value)
                    except ValueError:
                        pass
            elif hasattr(entry, 'success') and not entry.success:
                current_phase = TaskPhase.DEBUGGING
            elif hasattr(entry, 'tool'):
                if entry.tool in exploration_tools:
                    current_phase = TaskPhase.EXPLORATION
                elif entry.tool in development_tools:
                    current_phase = TaskPhase.DEVELOPMENT
                elif hasattr(entry, 'tags') and any(kw in entry.tags for kw in refinement_keywords):
                    current_phase = TaskPhase.REFINEMENT
                elif hasattr(entry, 'tags') and any(kw in entry.tags for kw in delivery_keywords):
                    current_phase = TaskPhase.DELIVERY
            
            phase_entries[current_phase].append(entry)
        
        return {phase: entries for phase, entries in phase_entries.items() if entries}
    
    async def _create_chapter_from_phase(
        self,
        conv_id: str,
        phase: TaskPhase,
        entries: List[Any],
    ) -> Chapter:
        """从阶段和 WorkEntry 创建章节"""
        
        first_timestamp = int(entries[0].timestamp) if hasattr(entries[0], 'timestamp') else 0
        chapter_id = f"chapter_{phase.value}_{first_timestamp}"
        title = self._generate_chapter_title(phase, entries)
        
        sections = []
        for idx, entry in enumerate(entries):
            section = await self._work_entry_to_section(entry, idx)
            sections.append(section)
        
        chapter = Chapter(
            chapter_id=chapter_id,
            phase=phase,
            title=title,
            summary="",
            sections=sections,
            created_at=entries[0].timestamp if hasattr(entries[0], 'timestamp') else datetime.now().timestamp(),
            tokens=sum(s.tokens for s in sections),
            is_compacted=False,
        )
        
        return chapter
    
    def _generate_chapter_title(
        self,
        phase: TaskPhase,
        entries: List[Any],
    ) -> str:
        """生成章节标题"""
        
        phase_titles = {
            TaskPhase.EXPLORATION: "需求探索与分析",
            TaskPhase.DEVELOPMENT: "功能开发与实现",
            TaskPhase.DEBUGGING: "问题调试与修复",
            TaskPhase.REFINEMENT: "优化与改进",
            TaskPhase.DELIVERY: "总结与交付",
        }
        
        base_title = phase_titles.get(phase, phase.value)
        key_tools = list(set(e.tool for e in entries[:5] if hasattr(e, 'tool')))
        
        if key_tools:
            tools_str = ", ".join(key_tools[:3])
            return f"{base_title} ({tools_str})"
        
        return base_title
    
    async def _work_entry_to_section(
        self,
        entry: Any,
        index: int,
    ) -> Section:
        """将 WorkEntry 转换为 Section"""
        
        priority = self._determine_section_priority(entry)
        timestamp = int(entry.timestamp) if hasattr(entry, 'timestamp') else 0
        tool = entry.tool if hasattr(entry, 'tool') else "unknown"
        section_id = f"section_{timestamp}_{tool}_{index}"
        
        content = entry.summary if hasattr(entry, 'summary') and entry.summary else ""
        detail_ref = None
        
        if hasattr(entry, 'result') and entry.result and len(str(entry.result)) > 500:
            detail_ref = await self._archive_long_content(entry)
            content = (entry.summary if hasattr(entry, 'summary') and entry.summary 
                      else str(entry.result)[:200] + "...")
        
        full_content = f"**工具**: {tool}\n"
        if hasattr(entry, 'summary') and entry.summary:
            full_content += f"**摘要**: {entry.summary}\n"
        if content:
            full_content += f"**内容**: {content}\n"
        if hasattr(entry, 'success') and not entry.success:
            full_content += f"**状态**: ❌ 失败\n"
            if hasattr(entry, 'result') and entry.result:
                full_content += f"**错误**: {str(entry.result)[:200]}\n"
        
        summary_text = entry.summary[:30] if hasattr(entry, 'summary') and entry.summary else "执行"
        
        return Section(
            section_id=section_id,
            step_name=f"{tool} - {summary_text}",
            content=full_content,
            detail_ref=detail_ref,
            priority=priority,
            timestamp=timestamp,
            tokens=len(full_content) // 4,
            metadata={
                "tool": tool,
                "args": entry.args if hasattr(entry, 'args') else {},
                "success": entry.success if hasattr(entry, 'success') else True,
                "original_tokens": entry.tokens if hasattr(entry, 'tokens') else 0,
                "tags": entry.tags if hasattr(entry, 'tags') else [],
            },
        )
    
    def _determine_section_priority(self, entry: Any) -> ContentPriority:
        """确定 Section 优先级"""
        
        if hasattr(entry, 'tags') and ("critical" in entry.tags or "decision" in entry.tags):
            return ContentPriority.CRITICAL
        
        critical_tools = {"write", "bash", "edit", "execute"}
        if hasattr(entry, 'tool') and entry.tool in critical_tools:
            if hasattr(entry, 'success') and entry.success:
                return ContentPriority.HIGH
        
        if hasattr(entry, 'success') and entry.success:
            return ContentPriority.MEDIUM
        
        return ContentPriority.LOW
    
    async def _archive_long_content(self, entry: Any) -> Optional[str]:
        """归档长内容到文件系统"""
        
        if not self.file_system:
            return None
        
        try:
            timestamp = entry.timestamp if hasattr(entry, 'timestamp') else 0
            tool = entry.tool if hasattr(entry, 'tool') else "unknown"
            
            archive_dir = f"worklog_archive/{timestamp}"
            archive_file = f"{archive_dir}/{tool}.json"
            
            archive_data = {
                "timestamp": timestamp,
                "tool": tool,
                "args": entry.args if hasattr(entry, 'args') else {},
                "result": str(entry.result) if hasattr(entry, 'result') else "",
                "summary": entry.summary if hasattr(entry, 'summary') else "",
                "success": entry.success if hasattr(entry, 'success') else True,
                "tokens": entry.tokens if hasattr(entry, 'tokens') else 0,
            }
            
            if hasattr(self.file_system, 'write_file'):
                await self.file_system.write_file(
                    file_path=archive_file,
                    content=json.dumps(archive_data, ensure_ascii=False, indent=2),
                )
            else:
                import os
                os.makedirs(os.path.dirname(archive_file), exist_ok=True)
                with open(archive_file, 'w', encoding='utf-8') as f:
                    json.dump(archive_data, f, ensure_ascii=False, indent=2)
            
            return archive_file
            
        except Exception as e:
            logger.warning(f"[UnifiedContextMiddleware] 归档失败: {e}")
            return None
    
    async def _infer_task_description(self, conv_id: str) -> str:
        """推断任务描述"""
        messages = await self.gpts_memory.get_messages(conv_id)
        if messages:
            first_user_msg = next(
                (m for m in messages if hasattr(m, 'role') and m.role == "user"),
                None
            )
            if first_user_msg and hasattr(first_user_msg, 'content'):
                return first_user_msg.content[:200]
        return "未命名任务"
    
    async def _load_recent_messages(
        self,
        conv_id: str,
        limit: int = 10,
    ) -> List[Any]:
        """加载最近的消息"""
        messages = await self.gpts_memory.get_messages(conv_id)
        return messages[-limit:] if messages else []
    
    async def record_step(
        self,
        conv_id: str,
        action_out: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """记录执行步骤到 HierarchicalContext"""
        
        if conv_id not in self.hc_integration._managers:
            logger.warning(f"[UnifiedContextMiddleware] 无管理器: {conv_id[:8]}")
            return None
        
        section_id = await self.hc_integration.record_step(
            execution_id=conv_id,
            action_out=action_out,
            metadata=metadata,
        )
        
        if conv_id in self._conv_contexts:
            del self._conv_contexts[conv_id]
        
        return section_id
    
    async def save_checkpoint(
        self,
        conv_id: str,
        checkpoint_path: Optional[str] = None,
    ) -> str:
        """保存检查点"""
        
        checkpoint_data = self.hc_integration.get_checkpoint_data(conv_id)
        
        if not checkpoint_data:
            raise ValueError(f"No context found for conv_id: {conv_id}")
        
        if not checkpoint_path:
            checkpoint_path = f"checkpoints/{conv_id}_checkpoint.json"
        
        if self.file_system and hasattr(self.file_system, 'write_file'):
            await self.file_system.write_file(
                file_path=checkpoint_path,
                content=checkpoint_data.to_json(),
            )
        else:
            import os
            os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                f.write(checkpoint_data.to_json())
        
        logger.info(f"[UnifiedContextMiddleware] 保存检查点: {checkpoint_path}")
        return checkpoint_path
    
    async def restore_checkpoint(
        self,
        conv_id: str,
        checkpoint_path: str,
    ) -> ContextLoadResult:
        """从检查点恢复"""
        
        if self.file_system and hasattr(self.file_system, 'read_file'):
            checkpoint_json = await self.file_system.read_file(checkpoint_path)
        else:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                checkpoint_json = f.read()
        
        from derisk.agent.shared.hierarchical_context import HierarchicalContextCheckpoint
        checkpoint_data = HierarchicalContextCheckpoint.from_json(checkpoint_json)
        
        await self.hc_integration.restore_from_checkpoint(conv_id, checkpoint_data)
        
        return await self.load_context(conv_id, force_reload=True)
    
    async def cleanup_context(self, conv_id: str) -> None:
        """清理上下文"""
        await self.hc_integration.cleanup_execution(conv_id)
        if conv_id in self._conv_contexts:
            del self._conv_contexts[conv_id]
        logger.info(f"[UnifiedContextMiddleware] 清理上下文: {conv_id[:8]}")
    
    def clear_all_cache(self) -> None:
        """清理所有缓存"""
        self._conv_contexts.clear()
        logger.info("[UnifiedContextMiddleware] 清理所有缓存")
    
    def get_statistics(self, conv_id: str) -> Dict[str, Any]:
        """获取统计信息"""
        if conv_id not in self._conv_contexts:
            return {"error": "No context loaded"}
        
        return self._conv_contexts[conv_id].stats