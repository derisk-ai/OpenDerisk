"""Derisk Memory 数据库存储实现.

提供 GptsMemory 的数据库持久化存储实现，包括：
- MetaDerisksPlansMemory: 计划存储
- MetaDerisksMessageMemory: 消息存储
- MetaAgentSystemMessageMemory: 系统消息存储
- MetaDerisksWorkLogStorage: 工作日志存储
- MetaDerisksKanbanStorage: 看板存储
- MetaDerisksTodoStorage: 任务列表存储
- MetaDerisksFileMetadataStorage: 文件元数据存储
"""

from typing import List, Optional, Dict, Any

from derisk.agent import AgentSystemMessage
from derisk.agent.core.memory.gpts import (
    GptsMessage,
    GptsMessageMemory,
    GptsPlan,
    GptsPlansMemory,
)
from derisk.agent.core.memory.gpts.base import AgentSystemMessageMemory
from derisk.agent.core.memory.gpts.file_base import (
    WorkEntry,
    Kanban,
    TodoItem,
    AgentFileMetadata,
)

from ..db.gpts_messages_db import GptsMessagesDao
from ..db.gpts_messages_system_db import GptsMessagesSystemDao
from ..db.gpts_plans_db import GptsPlansDao, GptsPlansEntity
from ..db.gpts_worklog_db import GptsWorkLogDao
from ..db.gpts_kanban_db import GptsKanbanDao, GptsPreKanbanLogDao
from ..db.gpts_file_metadata_db import GptsFileMetadataDao, GptsFileCatalogDao


class MetaDerisksPlansMemory(GptsPlansMemory):
    def __init__(self):
        self.gpts_plan = GptsPlansDao()

    async def get_plans_by_msg_round(
        self, conv_id: str, rounds_id: str
    ) -> List[GptsPlan]:
        db_results: List[GptsPlansEntity] = await self.gpts_plan.get_by_conv_id(
            conv_id=conv_id, conv_round_id=rounds_id
        )
        results = []
        for item in db_results:
            results.append(GptsPlan.from_dict(item.__dict__))
        return results

    def batch_save(self, plans: List[GptsPlan]):
        self.gpts_plan.batch_save([item.to_dict() for item in plans])

    async def get_by_conv_id(self, conv_id: str) -> List[GptsPlan]:
        db_results: List[GptsPlansEntity] = await self.gpts_plan.get_by_conv_id(
            conv_id=conv_id
        )
        results = []
        for item in db_results:
            results.append(GptsPlan.from_dict(item.__dict__))
        return results

    def get_by_planner(self, conv_id: str, planner: str) -> List[GptsPlan]:
        db_results: List[GptsPlansEntity] = self.gpts_plan.get_by_planner(
            conv_id=conv_id, planner=planner
        )
        results = []
        for item in db_results:
            results.append(GptsPlan.from_dict(item.__dict__))
        return results

    def get_by_planner_and_round(
        self, conv_id: str, planner: str, round_id: str
    ) -> List[GptsPlan]:
        """Get plans by conv_id and planner."""
        db_results: List[GptsPlansEntity] = self.gpts_plan.get_by_planner(
            conv_id=conv_id, planner=planner
        )
        results = []
        for item in db_results:
            if item.conv_round_id == round_id:
                results.append(GptsPlan.from_dict(item.__dict__))
        return results

    def get_by_conv_id_and_num(
        self, conv_id: str, task_ids: List[str]
    ) -> List[GptsPlan]:
        db_results: List[GptsPlansEntity] = self.gpts_plan.get_by_conv_id_and_num(
            conv_id=conv_id, task_ids=task_ids
        )
        results = []
        for item in db_results:
            results.append(GptsPlan.from_dict(item.__dict__))
        return results

    def get_todo_plans(self, conv_id: str) -> List[GptsPlan]:
        db_results: List[GptsPlansEntity] = self.gpts_plan.get_todo_plans(
            conv_id=conv_id
        )
        results = []
        for item in db_results:
            results.append(GptsPlan.from_dict(item.__dict__))
        return results

    def complete_task(self, conv_id: str, task_id: str, result: str):
        self.gpts_plan.complete_task(conv_id=conv_id, task_id=task_id, result=result)

    def update_task(
        self,
        conv_id: str,
        task_id: str,
        state: str,
        retry_times: int,
        agent: Optional[str] = None,
        model: Optional[str] = None,
        result: Optional[str] = None,
    ):
        self.gpts_plan.update_task(
            conv_id=conv_id,
            task_id=task_id,
            state=state,
            retry_times=retry_times,
            agent=agent,
            model=model,
            result=result,
        )

    def update_by_uid(
        self,
        conv_id: str,
        task_uid: str,
        state: str,
        retry_times: int,
        agent: Optional[str] = None,
        model: Optional[str] = None,
        result: Optional[str] = None,
    ) -> None:
        self.gpts_plan.update_by_uid(
            conv_id=conv_id,
            task_uid=task_uid,
            state=state,
            retry_times=retry_times,
            agent=agent,
            model=model,
            result=result,
        )

    def remove_by_conv_id(self, conv_id: str):
        self.gpts_plan.remove_by_conv_id(conv_id=conv_id)

    def remove_by_conv_planner(self, conv_id: str, planner: str) -> None:
        self.gpts_plan.remove_by_conv_and_planner(conv_id, planner)

    def get_by_conv_and_content(self, conv_id: str, content: str) -> Optional[GptsPlan]:
        item = self.gpts_plan.get_by_conv_id_and_content(
            conv_id=conv_id, content=content
        )
        return GptsPlan.from_dict(item.__dict__)


class MetaDerisksMessageMemory(GptsMessageMemory):
    def __init__(self):
        self.gpts_message = GptsMessagesDao()

    def append(self, message: GptsMessage):
        self.gpts_message.delete_by_msg_id(message_id=message.message_id)
        self.gpts_message.append(message.to_dict())

    def update(self, message: GptsMessage) -> None:
        self.gpts_message.update_message(message)

    def get_by_session_id(self, session_id: str) -> Optional[List[GptsMessage]]:
        return self.gpts_message.get_by_conv_session_id(session_id)

    async def get_by_conv_id(self, conv_id: str) -> Optional[List[GptsMessage]]:
        db_results = await self.gpts_message.get_by_conv_id(conv_id)
        return sorted(db_results, key=lambda x: x.rounds)

    def get_by_message_id(self, message_id: str) -> Optional[GptsMessage]:
        return self.gpts_message.get_by_message_id(message_id)

    def get_last_message(self, conv_id: str) -> Optional[GptsMessage]:
        return self.gpts_message.get_last_message(conv_id)

    def delete_by_conv_id(self, conv_id: str) -> None:
        self.gpts_message.delete_chat_message(conv_id)

    def delete_by_ms_id(self, msg_id: str) -> None:
        self.gpts_message.delete_by_msg_id(message_id=msg_id)


class MetaAgentSystemMessageMemory(AgentSystemMessageMemory):
    def __init__(self):
        self.gpts_message_system_dao = GptsMessagesSystemDao()

    def append(self, message: AgentSystemMessage) -> None:
        self.gpts_message_system_dao.delete_by_msg_id(message_id=message.message_id)
        self.gpts_message_system_dao.append(message.to_dict())

    def update(self, message: AgentSystemMessage) -> None:
        self.gpts_message_system_dao.update_message(message.to_dict())

    def get_by_conv_id(self, conv_id: str) -> List[AgentSystemMessage]:
        db_results = self.gpts_message_system_dao.get_by_conv_id(conv_id)
        results = []
        if db_results:
            db_results = sorted(db_results, key=lambda x: x.rounds)
            for item in db_results:
                results.append(AgentSystemMessage.from_dict(item.__dict__))
        return results

    def get_by_session_id(self, session_id: str) -> Optional[List[AgentSystemMessage]]:
        db_results = self.gpts_message_system_dao.get_by_conv_session_id(session_id)
        results = []
        if db_results:
            for item in db_results:
                results.append(AgentSystemMessage.from_dict(item.__dict__))
        return results


class MetaDerisksWorkLogStorage:
    """基于数据库的 WorkLog 存储实现（用于 GptsMemory 集成）.

    类似于 MetaDerisksMessageMemory，封装 GptsWorkLogDao 以实现数据库持久化。
    """

    def __init__(self):
        self._dao = GptsWorkLogDao()

    def append(
        self, conv_id: str, session_id: str, agent_id: str, entry: WorkEntry
    ) -> int:
        """添加工作日志条目到数据库.

        Args:
            conv_id: 会话 ID
            session_id: Session ID
            agent_id: Agent ID
            entry: WorkEntry 实例

        Returns:
            记录 ID
        """
        return self._dao.append(conv_id, session_id, agent_id, entry.to_dict())

    async def append_async(
        self, conv_id: str, session_id: str, agent_id: str, entry: WorkEntry
    ) -> int:
        """异步添加工作日志条目到数据库."""
        return await self._dao.append_async(
            conv_id, session_id, agent_id, entry.to_dict()
        )

    def get_by_session(self, conv_id: str, session_id: str) -> List[WorkEntry]:
        """获取指定会话的所有工作日志."""
        entries = self._dao.get_by_session(conv_id, session_id)
        return [WorkEntry.from_dict(e) for e in entries]

    async def get_by_session_async(
        self, conv_id: str, session_id: str
    ) -> List[WorkEntry]:
        """异步获取指定会话的所有工作日志."""
        entries = await self._dao.get_by_session_async(conv_id, session_id)
        return [WorkEntry.from_dict(e) for e in entries]

    def delete_by_session(self, conv_id: str, session_id: str) -> bool:
        """删除指定会话的所有工作日志."""
        return self._dao.delete_by_session(conv_id, session_id)

    async def delete_by_session_async(self, conv_id: str, session_id: str) -> bool:
        """异步删除指定会话的所有工作日志."""
        return await self._dao.delete_by_session_async(conv_id, session_id)

    def get_stats(self, conv_id: str, session_id: str) -> Dict[str, Any]:
        """获取工作日志统计信息."""
        return self._dao.get_stats_by_session(conv_id, session_id)


class MetaDerisksKanbanStorage:
    """基于数据库的 Kanban 存储实现（用于 GptsMemory 集成）.

    类似于 MetaDerisksPlansMemory，封装 GptsKanbanDao 以实现数据库持久化。
    """

    def __init__(self):
        self._kanban_dao = GptsKanbanDao()
        self._pre_log_dao = GptsPreKanbanLogDao()

    def save_kanban(
        self, conv_id: str, session_id: str, agent_id: str, kanban_data: dict
    ) -> int:
        """保存看板到数据库."""
        return self._kanban_dao.save_kanban(conv_id, session_id, agent_id, kanban_data)

    async def save_kanban_async(
        self, conv_id: str, session_id: str, agent_id: str, kanban_data: dict
    ) -> int:
        """异步保存看板到数据库."""
        return await self._kanban_dao.save_kanban_async(
            conv_id, session_id, agent_id, kanban_data
        )

    def get_kanban(self, conv_id: str, session_id: str) -> Optional[dict]:
        """从数据库获取看板."""
        return self._kanban_dao.get_kanban(conv_id, session_id)

    async def get_kanban_async(self, conv_id: str, session_id: str) -> Optional[dict]:
        """异步从数据库获取看板."""
        return await self._kanban_dao.get_kanban_async(conv_id, session_id)

    def delete_kanban(self, conv_id: str, session_id: str) -> bool:
        """删除看板."""
        return self._kanban_dao.delete_kanban(conv_id, session_id)

    async def delete_kanban_async(self, conv_id: str, session_id: str) -> bool:
        """异步删除看板."""
        return await self._kanban_dao.delete_kanban_async(conv_id, session_id)

    def get_pre_kanban_logs(self, conv_id: str, session_id: str) -> List[dict]:
        """获取预研日志."""
        return self._pre_log_dao.get_logs(conv_id, session_id)

    async def get_pre_kanban_logs_async(
        self, conv_id: str, session_id: str
    ) -> List[dict]:
        """异步获取预研日志."""
        return await self._pre_log_dao.get_logs_async(conv_id, session_id)

    def append_pre_kanban_log(
        self, conv_id: str, session_id: str, agent_id: str, log_entry: dict
    ) -> int:
        """追加预研日志."""
        return self._pre_log_dao.append_log(conv_id, session_id, agent_id, log_entry)

    async def append_pre_kanban_log_async(
        self, conv_id: str, session_id: str, agent_id: str, log_entry: dict
    ) -> int:
        """异步追加预研日志."""
        return await self._pre_log_dao.append_log_async(
            conv_id, session_id, agent_id, log_entry
        )

    def clear_pre_kanban_logs(self, conv_id: str, session_id: str) -> bool:
        """清空预研日志."""
        return self._pre_log_dao.clear_logs(conv_id, session_id)

    async def clear_pre_kanban_logs_async(self, conv_id: str, session_id: str) -> bool:
        """异步清空预研日志."""
        return await self._pre_log_dao.clear_logs_async(conv_id, session_id)

    def kanban_to_dict(self, kanban: Kanban) -> dict:
        """将 Kanban 对象转换为字典用于数据库存储."""
        return {
            "kanban_id": kanban.kanban_id,
            "mission": kanban.mission,
            "current_stage_index": kanban.current_stage_index,
            "stages": [self._stage_to_dict(s) for s in kanban.stages],
            "created_at": kanban.created_at,
        }

    def _stage_to_dict(self, stage) -> dict:
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


class MetaDerisksTodoStorage:
    """基于数据库的 Todo 存储实现（用于 GptsMemory 集成）.

    参考 opencode 的设计，保持简洁。
    复用 gpts_kanban 表，通过 file_type='todo' 区分。
    """

    def __init__(self):
        from ..db.gpts_kanban_db import GptsKanbanDao
        self._dao = GptsKanbanDao()

    async def write_todos(self, conv_id: str, todos: List[TodoItem]) -> None:
        """写入任务列表."""
        todos_data = [t.to_dict() for t in todos]
        kanban_data = {
            "kanban_id": f"todo_{conv_id}",
            "mission": "todo_list",
            "current_stage_index": 0,
            "stages": [],
            "todos": todos_data,
        }
        await self._dao.save_kanban_async(conv_id, conv_id, "todo", kanban_data)

    async def read_todos(self, conv_id: str) -> List[TodoItem]:
        """读取任务列表."""
        data = await self._dao.get_kanban_async(conv_id, conv_id)
        if not data or "todos" not in data:
            return []
        return [TodoItem.from_dict(t) for t in data.get("todos", [])]

    async def clear_todos(self, conv_id: str) -> None:
        """清空任务列表."""
        await self._dao.delete_kanban_async(conv_id, conv_id)


class MetaDerisksFileMetadataStorage:
    """基于数据库的文件元数据存储实现（用于 GptsMemory 集成）.

    与 MetaDerisksWorkLogStorage/MetaDerisksKanbanStorage/MetaDerisksTodoStorage 保持一致的架构，
    提供文件元数据和文件目录的数据库持久化存储。
    """

    def __init__(self):
        self._metadata_dao = GptsFileMetadataDao()
        self._catalog_dao = GptsFileCatalogDao()

    async def save_file_metadata(self, file_metadata: AgentFileMetadata) -> None:
        """保存文件元数据.

        Args:
            file_metadata: 文件元数据对象
        """
        await self._metadata_dao.save_async(file_metadata.to_dict())
        await self._catalog_dao.save_async(
            file_metadata.conv_id, file_metadata.file_key, file_metadata.file_id
        )

    async def update_file_metadata(self, file_metadata: AgentFileMetadata) -> None:
        """更新文件元数据.

        Args:
            file_metadata: 文件元数据对象
        """
        await self._metadata_dao.update_async(file_metadata.to_dict())

    async def get_file_by_key(
        self, conv_id: str, file_key: str
    ) -> Optional[AgentFileMetadata]:
        """通过 file_key 获取文件元数据.

        Args:
            conv_id: 会话 ID
            file_key: 文件 key

        Returns:
            文件元数据对象，不存在返回 None
        """
        data = await self._metadata_dao.get_by_file_key_async(conv_id, file_key)
        return AgentFileMetadata.from_dict(data) if data else None

    async def get_file_by_id(
        self, conv_id: str, file_id: str
    ) -> Optional[AgentFileMetadata]:
        """通过 file_id 获取文件元数据.

        Args:
            conv_id: 会话 ID
            file_id: 文件 ID

        Returns:
            文件元数据对象，不存在返回 None
        """
        data = await self._metadata_dao.get_by_file_id_async(file_id)
        if data and data.get("conv_id") == conv_id:
            return AgentFileMetadata.from_dict(data)
        return None

    async def list_files(
        self, conv_id: str, file_type: Optional[str] = None
    ) -> List[AgentFileMetadata]:
        """列出会话的所有文件.

        Args:
            conv_id: 会话 ID
            file_type: 可选的文件类型过滤

        Returns:
            文件元数据列表
        """
        if file_type:
            data_list = await self._metadata_dao.get_by_file_type_async(conv_id, file_type)
        else:
            data_list = await self._metadata_dao.get_by_conv_id_async(conv_id)
        return [AgentFileMetadata.from_dict(d) for d in data_list]

    async def delete_file(self, conv_id: str, file_key: str) -> bool:
        """删除文件元数据.

        Args:
            conv_id: 会话 ID
            file_key: 文件 key

        Returns:
            是否成功删除
        """
        await self._metadata_dao.delete_by_file_key_async(conv_id, file_key)
        await self._catalog_dao.delete_by_file_key_async(conv_id, file_key)
        return True

    async def get_conclusion_files(self, conv_id: str) -> List[AgentFileMetadata]:
        """获取所有结论文件.

        Args:
            conv_id: 会话 ID

        Returns:
            结论文件元数据列表
        """
        return await self.list_files(conv_id, file_type="conclusion")

    async def clear_conv_files(self, conv_id: str) -> None:
        """清空会话的所有文件元数据.

        Args:
            conv_id: 会话 ID
        """
        await self._metadata_dao.delete_by_conv_id_async(conv_id)
        await self._catalog_dao.delete_by_conv_id_async(conv_id)

    async def get_catalog(self, conv_id: str) -> Dict[str, str]:
        """获取文件目录（file_key -> file_id 映射）.

        Args:
            conv_id: 会话 ID

        Returns:
            文件目录字典
        """
        return await self._catalog_dao.get_catalog_async(conv_id)

    async def save_catalog(self, conv_id: str, file_key: str, file_id: str) -> None:
        """保存文件目录映射.

        Args:
            conv_id: 会话 ID
            file_key: 文件 key
            file_id: 文件 ID
        """
        await self._catalog_dao.save_async(conv_id, file_key, file_id)

    async def get_file_id_by_key(self, conv_id: str, file_key: str) -> Optional[str]:
        """通过 file_key 获取 file_id.

        Args:
            conv_id: 会话 ID
            file_key: 文件 key

        Returns:
            文件 ID，不存在返回 None
        """
        catalog = await self.get_catalog(conv_id)
        return catalog.get(file_key)
