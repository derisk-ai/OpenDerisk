"""数据库存储适配器.

实现 WorkLogStorage 和 KanbanStorage 接口，将数据持久化到数据库。
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from derisk.agent.core.memory.gpts.file_base import (
    KanbanStorage,
    Kanban,
    KanbanStage,
    WorkLogStorage,
    WorkEntry,
    WorkLogSummary,
)
from derisk.util.executor_utils import ExecutorFactory


class DatabaseWorkLogStorage(WorkLogStorage):
    """基于数据库的 WorkLog 存储实现.

    将工作日志持久化到 gpts_work_log 表。
    """

    def __init__(self, executor: Optional[ThreadPoolExecutor] = None):
        """初始化数据库存储.

        Args:
            executor: 线程池执行器，用于异步化同步数据库操作
        """
        self._executor = executor or ExecutorFactory.create_default_executor(
            "worklog_storage"
        )
        self._dao = None

    def _get_dao(self):
        """延迟加载 DAO，避免循环导入问题."""
        if self._dao is None:
            from derisk_serve.agent.db.gpts_worklog_db import GptsWorkLogDao

            self._dao = GptsWorkLogDao()
        return self._dao

    async def append_work_entry(
        self,
        conv_id: str,
        entry: WorkEntry,
        save_db: bool = True,
    ) -> None:
        """添加工作日志条目."""
        if not save_db:
            return

        entry_dict = entry.to_dict()
        await asyncio.get_event_loop().run_in_executor(
            self._executor,
            self._get_dao().append,
            conv_id,
            conv_id,  # session_id 使用 conv_id
            conv_id,  # agent_id 使用 conv_id
            entry_dict,
        )

    async def get_work_log(self, conv_id: str) -> List[WorkEntry]:
        """获取会话的工作日志."""
        entries = await asyncio.get_event_loop().run_in_executor(
            self._executor,
            self._get_dao().get_by_session,
            conv_id,
            conv_id,
        )
        return [WorkEntry.from_dict(e) for e in entries]

    async def get_work_log_summaries(self, conv_id: str) -> List[WorkLogSummary]:
        """获取工作日志摘要列表.

        注意：当前数据库模型不直接存储摘要，摘要由内存层计算。
        """
        # 数据库存储不直接存储摘要，由 GptsMemory 缓存层管理
        return []

    async def append_work_log_summary(
        self,
        conv_id: str,
        summary: WorkLogSummary,
        save_db: bool = True,
    ) -> None:
        """添加工作日志摘要.

        注意：当前数据库模型不直接存储摘要，摘要由内存层计算。
        """
        # 数据库存储不直接存储摘要，由 GptsMemory 缓存层管理
        pass

    async def get_work_log_context(
        self,
        conv_id: str,
        max_entries: int = 50,
        max_tokens: int = 8000,
    ) -> str:
        """获取用于 prompt 的工作日志上下文."""
        import time

        entries = await self.get_work_log(conv_id)
        if not entries:
            return "\n暂无工作日志记录。"

        lines = ["## 工作日志", ""]
        total_tokens = 0
        chars_per_token = 4

        for entry in entries[-max_entries:]:
            if entry.status != "active":
                continue
            time_str = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
            entry_text = f"[{time_str}] {entry.tool}"
            if entry.args:
                important_args = {
                    k: v
                    for k, v in entry.args.items()
                    if k in ["file_key", "path", "query", "pattern"]
                }
                if important_args:
                    entry_text += f" 参数: {important_args}"
            if entry.result:
                preview = entry.result[:200]
                entry_text += f"\n  {preview}"
            elif entry.full_result_archive:
                entry_text += f"\n  完整结果已归档: {entry.full_result_archive}"

            lines.append(entry_text)
            total_tokens += len(entry_text) // chars_per_token
            if total_tokens > max_tokens:
                break

        return "\n".join(lines)

    async def clear_work_log(self, conv_id: str) -> None:
        """清空会话的工作日志."""
        await asyncio.get_event_loop().run_in_executor(
            self._executor,
            self._get_dao().delete_by_session,
            conv_id,
            conv_id,
        )

    async def get_work_log_stats(self, conv_id: str) -> Dict[str, Any]:
        """获取工作日志统计信息."""
        return await asyncio.get_event_loop().run_in_executor(
            self._executor,
            self._get_dao().get_stats_by_session,
            conv_id,
            conv_id,
        )


class DatabaseKanbanStorage(KanbanStorage):
    """基于数据库的 Kanban 存储实现.

    将看板数据持久化到 gpts_kanban 和 gpts_pre_kanban_log 表。
    """

    def __init__(self, executor: Optional[ThreadPoolExecutor] = None):
        """初始化数据库存储.

        Args:
            executor: 线程池执行器，用于异步化同步数据库操作
        """
        self._executor = executor or ExecutorFactory.create_default_executor(
            "kanban_storage"
        )
        self._kanban_dao = None
        self._pre_log_dao = None

    def _get_kanban_dao(self):
        """延迟加载 Kanban DAO."""
        if self._kanban_dao is None:
            from derisk_serve.agent.db.gpts_kanban_db import GptsKanbanDao

            self._kanban_dao = GptsKanbanDao()
        return self._kanban_dao

    def _get_pre_log_dao(self):
        """延迟加载 PreKanbanLog DAO."""
        if self._pre_log_dao is None:
            from derisk_serve.agent.db.gpts_kanban_db import GptsPreKanbanLogDao

            self._pre_log_dao = GptsPreKanbanLogDao()
        return self._pre_log_dao

    def _kanban_to_dict(self, kanban: Kanban) -> dict:
        """将 Kanban 对象转换为字典."""
        return {
            "kanban_id": kanban.kanban_id,
            "mission": kanban.mission,
            "current_stage_index": kanban.current_stage_index,
            "stages": [self._stage_to_dict(s) for s in kanban.stages],
            "created_at": kanban.created_at,
        }

    def _stage_to_dict(self, stage: KanbanStage) -> dict:
        """将 KanbanStage 对象转换为字典."""
        return {
            "stage_id": stage.stage_id,
            "description": stage.description,
            "status": stage.status,
            "deliverable_type": stage.deliverable_type,
            "deliverable_schema": stage.deliverable_schema,
            "deliverable_file": stage.deliverable_file,
            "work_log": [e.to_dict() for e in stage.work_log],
            "started_at": stage.started_at,
            "completed_at": stage.completed_at,
            "depends_on": stage.depends_on,
            "reflection": stage.reflection,
        }

    def _dict_to_kanban(self, data: dict) -> Kanban:
        """将字典转换为 Kanban 对象."""
        stages = [self._dict_to_stage(s) for s in data.get("stages", [])]
        return Kanban(
            kanban_id=data.get("kanban_id", ""),
            mission=data.get("mission", ""),
            stages=stages,
            current_stage_index=data.get("current_stage_index", 0),
            created_at=data.get("created_at"),
        )

    def _dict_to_stage(self, data: dict) -> KanbanStage:
        """将字典转换为 KanbanStage 对象."""
        work_log = [WorkEntry.from_dict(e) for e in data.get("work_log", [])]
        return KanbanStage(
            stage_id=data.get("stage_id", ""),
            description=data.get("description", ""),
            status=data.get("status", "working"),
            deliverable_type=data.get("deliverable_type", ""),
            deliverable_schema=data.get("deliverable_schema", {}),
            deliverable_file=data.get("deliverable_file", ""),
            work_log=work_log,
            started_at=data.get("started_at", 0.0),
            completed_at=data.get("completed_at", 0.0),
            depends_on=data.get("depends_on", []),
            reflection=data.get("reflection", ""),
        )

    async def save_kanban(self, conv_id: str, kanban: Kanban) -> None:
        """保存看板."""
        kanban_data = self._kanban_to_dict(kanban)
        await asyncio.get_event_loop().run_in_executor(
            self._executor,
            self._get_kanban_dao().save_kanban,
            conv_id,
            conv_id,
            conv_id,
            kanban_data,
        )

    async def get_kanban(self, conv_id: str) -> Optional[Kanban]:
        """获取看板."""
        data = await asyncio.get_event_loop().run_in_executor(
            self._executor,
            self._get_kanban_dao().get_kanban,
            conv_id,
            conv_id,
        )
        if data:
            return self._dict_to_kanban(data)
        return None

    async def delete_kanban(self, conv_id: str) -> bool:
        """删除看板."""
        return await asyncio.get_event_loop().run_in_executor(
            self._executor,
            self._get_kanban_dao().delete_kanban,
            conv_id,
            conv_id,
        )

    async def save_deliverable(
        self,
        conv_id: str,
        stage_id: str,
        deliverable: Dict[str, Any],
        deliverable_type: str = "",
    ) -> str:
        """保存交付物.

        注意：交付物内容通过文件系统存储，数据库只存储元数据引用。
        """
        # 交付物内容通过文件系统存储
        # 数据库中的 deliverables 字段存储元数据引用
        kanban = await self.get_kanban(conv_id)
        if kanban:
            stage = kanban.get_stage_by_id(stage_id)
            if stage:
                stage.deliverable_file = f"{conv_id}_{stage_id}_deliverable"
                stage.deliverable_type = deliverable_type
                await self.save_kanban(conv_id, kanban)
                return stage.deliverable_file
        return ""

    async def get_deliverable(
        self, conv_id: str, stage_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取交付物.

        注意：交付物内容需要从文件系统读取，数据库只存储元数据。
        """
        # 数据库只存储元数据引用，实际内容需要从文件系统读取
        kanban = await self.get_kanban(conv_id)
        if kanban:
            stage = kanban.get_stage_by_id(stage_id)
            if stage and stage.deliverable_file:
                return {
                    "stage_id": stage_id,
                    "deliverable_type": stage.deliverable_type,
                    "file_key": stage.deliverable_file,
                }
        return None

    async def get_all_deliverables(self, conv_id: str) -> Dict[str, Dict[str, Any]]:
        """获取所有交付物."""
        result = {}
        kanban = await self.get_kanban(conv_id)
        if kanban:
            for stage in kanban.get_completed_stages():
                if stage.deliverable_file:
                    result[stage.stage_id] = {
                        "stage_id": stage.stage_id,
                        "deliverable_type": stage.deliverable_type,
                        "file_key": stage.deliverable_file,
                    }
        return result

    async def add_work_entry_to_stage(
        self,
        conv_id: str,
        stage_id: str,
        entry: WorkEntry,
    ) -> bool:
        """向指定阶段添加工作日志条目."""
        kanban = await self.get_kanban(conv_id)
        if not kanban:
            return False

        stage = kanban.get_stage_by_id(stage_id)
        if not stage:
            return False

        stage.work_log.append(entry)
        await self.save_kanban(conv_id, kanban)
        return True

    async def get_pre_kanban_logs(self, conv_id: str) -> List[WorkEntry]:
        """获取看板创建前的预研日志."""
        logs = await asyncio.get_event_loop().run_in_executor(
            self._executor,
            self._get_pre_log_dao().get_logs,
            conv_id,
            conv_id,
        )
        return [WorkEntry.from_dict(e) for e in logs]

    async def add_pre_kanban_log(
        self,
        conv_id: str,
        entry: WorkEntry,
    ) -> None:
        """添加预研日志条目."""
        entry_dict = entry.to_dict()
        await asyncio.get_event_loop().run_in_executor(
            self._executor,
            self._get_pre_log_dao().append_log,
            conv_id,
            conv_id,
            conv_id,
            entry_dict,
        )

    async def clear_pre_kanban_logs(self, conv_id: str) -> None:
        """清空预研日志."""
        await asyncio.get_event_loop().run_in_executor(
            self._executor,
            self._get_pre_log_dao().clear_logs,
            conv_id,
            conv_id,
        )
