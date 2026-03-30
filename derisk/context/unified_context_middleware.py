"""
统一上下文中间件

核心职责：
1. 整合 HierarchicalContextV2Integration
2. 实现 WorkLog → Section 转换
3. 协调 GptsMemory 和 AgentFileSystem
4. 提供统一的历史加载接口
5. 整合 WorkLogManager.build_tool_messages() 支持原生 Function Call 模式
6. 整合 SessionHistoryManager 实现 Hot/Warm/Cold 跨对话分层
"""

from typing import Optional, Dict, Any, List, TYPE_CHECKING
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

if TYPE_CHECKING:
    from derisk.agent.core.memory.session_history import SessionHistoryManager

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
    tool_messages: List[Dict[str, Any]] = field(default_factory=list)
    history_context_messages: List[Dict[str, Any]] = field(default_factory=list)


class UnifiedContextMiddleware:
    """
    统一上下文中间件

    核心职责：
    1. 整合 HierarchicalContextV2Integration
    2. 实现 WorkLog → Section 转换
    3. 协调 GptsMemory 和 AgentFileSystem
    4. 提供统一的历史加载接口
    5. 整合 WorkLogManager.build_tool_messages() 支持原生 Function Call 模式
    6. 整合 SessionHistoryManager 实现 Hot/Warm/Cold 跨对话分层
    """

    def __init__(
        self,
        gpts_memory: Any,
        agent_file_system: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        hc_config: Optional[HierarchicalContextConfig] = None,
        compaction_config: Optional[HierarchicalCompactionConfig] = None,
        work_log_manager: Optional[Any] = None,
        session_history_manager: Optional["SessionHistoryManager"] = None,
        system_event_manager: Optional[Any] = None,
    ):
        self.gpts_memory = gpts_memory
        self.file_system = agent_file_system
        self.llm_client = llm_client
        self.work_log_manager = work_log_manager
        self.session_history_manager = session_history_manager
        self._system_event_manager = system_event_manager

        if work_log_manager and system_event_manager:
            work_log_manager.set_system_event_manager(system_event_manager)

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
        include_tool_messages: bool = True,
        include_history_context: bool = True,
    ) -> ContextLoadResult:
        """
        加载完整的历史上下文（主入口）

        Args:
            conv_id: 对话ID
            task_description: 任务描述
            include_worklog: 是否包含 WorkLog
            token_budget: token 预算
            force_reload: 是否强制重新加载
            include_tool_messages: 是否包含原生 tool_messages (用于 Function Call 模式)
            include_history_context: 是否包含跨对话历史上下文 (Hot/Warm/Cold 分层)
        """

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

            tool_messages = []
            if include_tool_messages and self.work_log_manager:
                tool_messages = await self._build_tool_messages_from_worklog(
                    conv_id=conv_id,
                    max_tokens=token_budget,
                )

            history_context_messages = []
            if include_history_context and self.session_history_manager:
                history_context_messages = await self._build_history_context(
                    current_conv_id=conv_id,
                    max_tokens=token_budget,
                )

            result = ContextLoadResult(
                conv_id=conv_id,
                task_description=task_description,
                chapter_index=hc_manager._chapter_indexer,
                hierarchical_context_text=hierarchical_context_text,
                recent_messages=recent_messages,
                recall_tools=recall_tools,
                stats=hc_manager.get_statistics(),
                hc_integration=self.hc_integration,
                tool_messages=tool_messages,
                history_context_messages=history_context_messages,
            )

            self._conv_contexts[conv_id] = result

            logger.info(
                f"[UnifiedContextMiddleware] 已加载上下文 {conv_id[:8]}: "
                f"chapters={result.stats.get('chapter_count', 0)}, "
                f"context_tokens={len(hierarchical_context_text) // 4}, "
                f"tool_messages={len(tool_messages)}, "
                f"history_context={len(history_context_messages)}"
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
        exploration_tools = {"read", "glob", "grep", "search"}
        development_tools = {"write", "edit", "bash", "execute", "run"}
        refinement_keywords = {"refactor", "optimize", "improve", "enhance"}
        delivery_keywords = {"summary", "document", "conclusion", "report"}

        for entry in worklog:
            if hasattr(entry, "metadata") and "phase" in entry.metadata:
                phase_value = entry.metadata["phase"]
                if isinstance(phase_value, str):
                    try:
                        current_phase = TaskPhase(phase_value)
                    except ValueError:
                        pass
            elif hasattr(entry, "success") and not entry.success:
                current_phase = TaskPhase.DEBUGGING
            elif hasattr(entry, "tool"):
                if entry.tool in exploration_tools:
                    current_phase = TaskPhase.EXPLORATION
                elif entry.tool in development_tools:
                    current_phase = TaskPhase.DEVELOPMENT
                elif hasattr(entry, "tags") and any(
                    kw in entry.tags for kw in refinement_keywords
                ):
                    current_phase = TaskPhase.REFINEMENT
                elif hasattr(entry, "tags") and any(
                    kw in entry.tags for kw in delivery_keywords
                ):
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

        first_timestamp = (
            int(entries[0].timestamp) if hasattr(entries[0], "timestamp") else 0
        )
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
            created_at=entries[0].timestamp
            if hasattr(entries[0], "timestamp")
            else datetime.now().timestamp(),
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
        key_tools = list(set(e.tool for e in entries[:5] if hasattr(e, "tool")))

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
        timestamp = int(entry.timestamp) if hasattr(entry, "timestamp") else 0
        tool = entry.tool if hasattr(entry, "tool") else "unknown"
        section_id = f"section_{timestamp}_{tool}_{index}"

        content = entry.summary if hasattr(entry, "summary") and entry.summary else ""
        detail_ref = None

        if hasattr(entry, "result") and entry.result and len(str(entry.result)) > 500:
            detail_ref = await self._archive_long_content(entry)
            content = (
                entry.summary
                if hasattr(entry, "summary") and entry.summary
                else str(entry.result)[:200] + "..."
            )

        full_content = f"**工具**: {tool}\n"
        if hasattr(entry, "summary") and entry.summary:
            full_content += f"**摘要**: {entry.summary}\n"
        if content:
            full_content += f"**内容**: {content}\n"
        if hasattr(entry, "success") and not entry.success:
            full_content += f"**状态**: ❌ 失败\n"
            if hasattr(entry, "result") and entry.result:
                full_content += f"**错误**: {str(entry.result)[:200]}\n"

        summary_text = (
            entry.summary[:30]
            if hasattr(entry, "summary") and entry.summary
            else "执行"
        )

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
                "args": entry.args if hasattr(entry, "args") else {},
                "success": entry.success if hasattr(entry, "success") else True,
                "original_tokens": entry.tokens if hasattr(entry, "tokens") else 0,
                "tags": entry.tags if hasattr(entry, "tags") else [],
            },
        )

    def _determine_section_priority(self, entry: Any) -> ContentPriority:
        """确定 Section 优先级"""

        if hasattr(entry, "tags") and (
            "critical" in entry.tags or "decision" in entry.tags
        ):
            return ContentPriority.CRITICAL

        critical_tools = {"write", "bash", "edit", "execute"}
        if hasattr(entry, "tool") and entry.tool in critical_tools:
            if hasattr(entry, "success") and entry.success:
                return ContentPriority.HIGH

        if hasattr(entry, "success") and entry.success:
            return ContentPriority.MEDIUM

        return ContentPriority.LOW

    async def _archive_long_content(self, entry: Any) -> Optional[str]:
        """归档长内容到文件系统"""

        if not self.file_system:
            return None

        try:
            timestamp = entry.timestamp if hasattr(entry, "timestamp") else 0
            tool = entry.tool if hasattr(entry, "tool") else "unknown"

            archive_dir = f"worklog_archive/{timestamp}"
            archive_file = f"{archive_dir}/{tool}.json"

            archive_data = {
                "timestamp": timestamp,
                "tool": tool,
                "args": entry.args if hasattr(entry, "args") else {},
                "result": str(entry.result) if hasattr(entry, "result") else "",
                "summary": entry.summary if hasattr(entry, "summary") else "",
                "success": entry.success if hasattr(entry, "success") else True,
                "tokens": entry.tokens if hasattr(entry, "tokens") else 0,
            }

            if hasattr(self.file_system, "write_file"):
                await self.file_system.write_file(
                    file_path=archive_file,
                    content=json.dumps(archive_data, ensure_ascii=False, indent=2),
                )
            else:
                import os

                os.makedirs(os.path.dirname(archive_file), exist_ok=True)
                with open(archive_file, "w", encoding="utf-8") as f:
                    json.dump(archive_data, f, ensure_ascii=False, indent=2)

            return archive_file

        except Exception as e:
            logger.warning(f"[UnifiedContextMiddleware] 归档失败: {e}")
            return None

    async def _build_tool_messages_from_worklog(
        self,
        conv_id: str,
        max_tokens: int = 80000,
    ) -> List[Dict[str, Any]]:
        """
        从 WorkLogManager 构建 tool_messages (原生 Function Call 模式)

        这是四层压缩的核心实现：
        1. Layer 1 - 活跃层: 最近 N 个工具调用保持完整
        2. Layer 2 - 压缩层: 旧工具结果替换为占位符+归档引用
        3. Layer 3 - 摘要层: 多工具调用合并为摘要
        4. Layer 4 - 归档层: 大结果归档到文件系统

        Args:
            conv_id: 对话ID
            max_tokens: 最大 token 数

        Returns:
            tool_messages 列表，可直接传递给 LLM
        """
        if not self.work_log_manager:
            logger.debug(
                f"[UnifiedContextMiddleware] 无 WorkLogManager，跳过 tool_messages 构建"
            )
            return []

        try:
            await self.work_log_manager.initialize()

            tool_messages = self.work_log_manager.build_tool_messages(
                max_tokens=max_tokens,
                keep_recent_count=20,
                apply_prune=True,
                conv_id=conv_id,
            )

            logger.info(
                f"[UnifiedContextMiddleware] 构建了 {len(tool_messages)} 条 tool_messages "
                f"from WorkLog (conv_id={conv_id[:8]})"
            )

            return tool_messages

        except Exception as e:
            logger.error(f"[UnifiedContextMiddleware] 构建 tool_messages 失败: {e}")
            return []

    def build_tool_messages(
        self,
        conv_id: str,
        max_tokens: int = 80000,
    ) -> List[Dict[str, Any]]:
        """
        同步版本的 tool_messages 构建方法

        Args:
            conv_id: 对话ID
            max_tokens: 最大 token 数

        Returns:
            tool_messages 列表
        """
        if not self.work_log_manager:
            return []

        if not self.work_log_manager._loaded:
            logger.warning(
                f"[UnifiedContextMiddleware] WorkLogManager 未初始化，返回空列表"
            )
            return []

        return self.work_log_manager.build_tool_messages(
            max_tokens=max_tokens,
            keep_recent_count=20,
            apply_prune=True,
            conv_id=conv_id,
        )

    def set_work_log_manager(self, work_log_manager: Any) -> None:
        """设置 WorkLogManager"""
        self.work_log_manager = work_log_manager
        logger.info("[UnifiedContextMiddleware] WorkLogManager 已设置")

    def set_session_history_manager(
        self, session_history_manager: "SessionHistoryManager"
    ) -> None:
        """设置 SessionHistoryManager"""
        self.session_history_manager = session_history_manager
        logger.info("[UnifiedContextMiddleware] SessionHistoryManager 已设置")

    def set_system_event_manager(self, system_event_manager: Any) -> None:
        """设置 SystemEventManager"""
        self._system_event_manager = system_event_manager
        if self.work_log_manager:
            self.work_log_manager.set_system_event_manager(system_event_manager)
        logger.info("[UnifiedContextMiddleware] SystemEventManager 已设置")

    async def _build_history_context(
        self,
        current_conv_id: str,
        max_tokens: int = 8000,
    ) -> List[Dict[str, Any]]:
        """
        构建 Hot/Warm/Cold 跨对话历史上下文

        这是跨对话分层压缩的核心实现：
        - Hot Layer (70% token): 最近 N 次对话，保留完整细节
        - Warm Layer (30% token): 压缩为摘要，保留关键结论
        - Cold Layer: 归档提示

        Args:
            current_conv_id: 当前对话ID（会被跳过）
            max_tokens: 最大 token 数

        Returns:
            Message List 格式的历史上下文
        """
        if not self.session_history_manager:
            logger.debug(
                "[UnifiedContextMiddleware] 无 SessionHistoryManager，跳过历史上下文构建"
            )
            return []

        try:
            history_messages = await self.session_history_manager.build_history_context(
                current_conv_id=current_conv_id,
                max_tokens=max_tokens,
            )

            logger.info(
                f"[UnifiedContextMiddleware] 构建了 {len(history_messages)} 条历史上下文消息 "
                f"(Hot/Warm/Cold 分层)"
            )

            return history_messages

        except Exception as e:
            logger.error(f"[UnifiedContextMiddleware] 构建历史上下文失败: {e}")
            return []

    def build_history_context(
        self,
        current_conv_id: str,
        max_tokens: int = 8000,
    ) -> List[Dict[str, Any]]:
        """
        同步版本的历史上下文构建方法

        Args:
            current_conv_id: 当前对话ID
            max_tokens: 最大 token 数

        Returns:
            历史上下文消息列表
        """
        if not self.session_history_manager:
            return []

        if not self.session_history_manager._initialized:
            logger.warning(
                "[UnifiedContextMiddleware] SessionHistoryManager 未初始化，返回空列表"
            )
            return []

        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.warning(
                    "[UnifiedContextMiddleware] 事件循环正在运行，无法同步调用异步方法"
                )
                return []
            return loop.run_until_complete(
                self.session_history_manager.build_history_context(
                    current_conv_id=current_conv_id,
                    max_tokens=max_tokens,
                )
            )
        except Exception as e:
            logger.error(f"[UnifiedContextMiddleware] 同步构建历史上下文失败: {e}")
            return []

    async def _infer_task_description(self, conv_id: str) -> str:
        """推断任务描述"""
        messages = await self.gpts_memory.get_messages(conv_id)
        if messages:
            first_user_msg = next(
                (m for m in messages if hasattr(m, "role") and m.role == "user"), None
            )
            if first_user_msg and hasattr(first_user_msg, "content"):
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

        if self.file_system and hasattr(self.file_system, "write_file"):
            await self.file_system.write_file(
                file_path=checkpoint_path,
                content=checkpoint_data.to_json(),
            )
        else:
            import os

            os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                f.write(checkpoint_data.to_json())

        logger.info(f"[UnifiedContextMiddleware] 保存检查点: {checkpoint_path}")
        return checkpoint_path

    async def restore_checkpoint(
        self,
        conv_id: str,
        checkpoint_path: str,
    ) -> ContextLoadResult:
        """从检查点恢复"""

        if self.file_system and hasattr(self.file_system, "read_file"):
            checkpoint_json = await self.file_system.read_file(checkpoint_path)
        else:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint_json = f.read()

        from derisk.agent.shared.hierarchical_context import (
            HierarchicalContextCheckpoint,
        )

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

    async def build_messages(
        self,
        conv_id: str,
        context_window: int = 128000,
    ) -> List[Dict[str, Any]]:
        """
        统一入口：构建完整的 Message List

        整合三层架构：
        1. 跨对话历史 (SessionHistoryManager): Hot/Warm/Cold
        2. 对话内工具调用 (WorkLogManager): Hot/Warm/Cold
        3. 分层上下文 (HierarchicalContext): Chapter/Section

        输出格式：
        [
            # Cold Layer
            {"role": "system", "content": "[历史对话摘要] ..."},
            {"role": "system", "content": "[更早的工具调用摘要] ..."},

            # Warm Layer
            {"role": "human", "content": "用户的完整问题..."},
            {"role": "assistant", "content": "[对话摘要] ..."},

            # Hot Layer
            {"role": "human", "content": "最近对话的问题..."},
            {"role": "assistant", "content": "完整的AI回复...", "tool_calls": [...]},
            {"role": "tool", "tool_call_id": "...", "content": "完整的工具结果..."},
        ]

        Args:
            conv_id: 当前对话ID
            context_window: LLM上下文窗口大小

        Returns:
            Message List，可直接传递给 LLM
        """
        messages: List[Dict[str, Any]] = []

        history_messages = await self._build_history_context(
            current_conv_id=conv_id,
            max_tokens=int(context_window * 0.3),
        )
        messages.extend(history_messages)

        tool_messages = await self._build_tool_messages_from_worklog(
            conv_id=conv_id,
            max_tokens=int(context_window * 0.5),
        )
        messages.extend(tool_messages)

        total_tokens = sum(len(str(m.get("content", ""))) // 4 for m in messages)

        logger.info(
            f"[UnifiedContextMiddleware] build_messages: {len(messages)} messages, "
            f"~{total_tokens} tokens, context_window={context_window}"
        )

        return messages

    def get_compression_stats(self) -> Dict[str, Any]:
        """获取压缩统计信息"""
        stats = {
            "work_log": None,
            "session_history": None,
        }

        if self.work_log_manager:
            stats["work_log"] = {
                "compression_summary": self.work_log_manager.get_compression_summary(),
                "last_budget_info": self.work_log_manager.get_last_budget_info(),
            }

        if self.session_history_manager:
            stats["session_history"] = self.session_history_manager.get_stats()

        return stats
