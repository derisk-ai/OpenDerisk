from typing import List, Optional

from derisk.agent import AgentSystemMessage
from derisk.agent.core.memory.gpts import (
    GptsMessage,
    GptsMessageMemory,
    GptsPlan,
    GptsPlansMemory,
)
from derisk.agent.core.memory.gpts.base import AgentSystemMessageMemory

from ..db.gpts_messages_db import GptsMessagesDao
from ..db.gpts_messages_system_db import GptsMessagesSystemDao
from ..db.gpts_plans_db import GptsPlansDao, GptsPlansEntity


class MetaDerisksPlansMemory(GptsPlansMemory):

    def __init__(self):
        self.gpts_plan = GptsPlansDao()

    async def get_plans_by_msg_round(self, conv_id: str, rounds_id: str) -> List[GptsPlan]:
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

    def get_by_planner_and_round(self, conv_id: str, planner: str, round_id: str) -> List[GptsPlan]:
        """Get plans by conv_id and planner.

        Args:
            conv_id: conversation id
            planner: planner
            round_id: round_id
        Returns:
            List[GptsPlan]: List of planning steps
        """
        db_results: List[GptsPlansEntity] = self.gpts_plan.get_by_planner(
            conv_id=conv_id, planner=planner
        )
        results = []
        for item in db_results:
            ## 过滤round_id数据
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

    def update_by_uid(self, conv_id: str, task_uid: str, state: str, retry_times: int, agent: Optional[str] = None,
                      model: Optional[str] = None, result: Optional[str] = None) -> None:
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
        db_results = sorted(db_results, key=lambda x: x.rounds)
        for item in db_results:
            results.append(AgentSystemMessage.from_dict(item.__dict__))
        return results

    def get_by_session_id(self, session_id: str) -> Optional[List[AgentSystemMessage]]:
        db_results = self.gpts_message_system_dao.get_by_conv_session_id(session_id)

        results = []
        for item in db_results:
            results.append(AgentSystemMessage.from_dict(item.__dict__))
        return results
