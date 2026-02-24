import datetime
import json
import logging
from enum import Enum
from typing import Optional, List, Dict, Tuple

from derisk.agent import ConversableAgent, AgentMessage
from derisk.agent.expand.actions.schedule_action import BaseScheduledAction
from derisk.agent.expand.parsers.tracking_parser import TrackingInfo
from derisk.vis import SystemVisTag

logger = logging.getLogger(__name__)


class TrackingStatus(Enum):
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"
    UPDATE = "update"


class TrackingAction(BaseScheduledAction[TrackingInfo]):

    def __init__(self, language: str = "en", name: Optional[str] = None, **kwargs):
        super().__init__(language=language, name=name, **kwargs)
        self.agent_parser = kwargs.get("agent_parser")
        self.action_view_tag: str = SystemVisTag.VisPlans.value

    async def execute_task(self, task_id: str, **kwargs) -> Tuple[AgentMessage, Optional[AgentMessage]]:
        """跟踪目标Agent执行
        Access parameters directly from kwargs without context unpacking
        Example:
            async def execute_task(self, user_query: str, agent_context: AgentContext, **kwargs):
                # Implementation using named parameters
        """

        sender: ConversableAgent = kwargs["self_agent"]
        agents: List[ConversableAgent] = kwargs["agents"]
        action_input: TrackingInfo = kwargs.get('action_input')

        recipient = next(
            (agent for agent in agents if agent.name == action_input.agent),
            None,
        )
        if not recipient:
            raise RuntimeError("recipient can't by empty")

        received_message = (
            kwargs["received_message"] if "received_message" in kwargs else AgentMessage.init_new()
        )

        # goal_id = uuid.uuid4().hex
        message = await sender.init_reply_message(received_message=received_message)
        message.rounds = await sender.memory.gpts_memory.next_message_rounds(
            sender.not_null_agent_context.conv_id
        )
        message.show_message = False
        message.content = (
            action_input.intent
            + "\n\n"
            + json.dumps(action_input.extra_info, ensure_ascii=False)
        )
        # message.goal_id = kwargs["action_id"] if "action_id" in kwargs else ""
        # message.current_goal = action_input.content
        # 合并context 且action_input.extra_info优先级更高
        message.context = (message.context or {}) | (action_input.extra_info or {})

        logger.info(f"[ACTION]---------->   Agent Action [{sender.name}] --> [{recipient.name}]")

        return message, await sender.send(message=message, recipient=recipient, request_reply=True,
                                          request_sender_reply=False)

    async def check_completion(self, task_id: str, **kwargs) -> bool:
        """跟踪目标结果完成判断
        Evaluate result object from execute_task()
        Return True if task should terminate
        """
        return False

    def view_result(self, task_id: str, task_data: Dict, **kwargs) -> Tuple[
        Optional[str], Optional[str]]:
        """跟踪目标可视化
        """
        # bind_message_id = kwargs.get('bind_message_id')
        # # bind_message_id = kwargs['message_id']
        # action_input: TrackingInfo = kwargs.get('action_input')

        excute_content = task_data.get("result") or task_data.get("error")
        try:
            poll_count = task_data.get("poll_count")
            run_time = task_data.get("run_time", datetime.datetime.now())

            result_message: AgentMessage = task_data.get("result")
            excute_view = result_message.content
            excute_content = result_message.content
            if result_message.action_report:
                excute_view = result_message.action_report.view
                excute_content = result_message.action_report.content

            # view_content = VisPlansContent(
            #     uid=f"{bind_message_id}_action",
            #     type="incr",
            #     message_id=bind_message_id,
            #     round_title="",
            #     round_description="",
            #
            #     tasks=[VisTaskContent(
            #         task_uid=f"{bind_message_id}_action_{str(poll_count)}",
            #         task_id=str(poll_count),
            #         task_title=excute_view,
            #         task_name=f"[{run_time.strftime('%Y-%m-%d %H:%M:%S')}]调度执行",
            #         task_content=excute_view,
            #         task_parent=task_id,
            #         task_link=None,
            #         agent_name=action_input.agent,
            #         agent_link="",
            #         avatar="",
            #     )]
            # )
            #
            # view = None
            # if self.render_protocol:
            #     view = self.render_protocol.sync_display(
            #         content=view_content.to_dict()
            #     )
            view = f"\n\n### [📅 {run_time.strftime('%Y-%m-%d %H:%M:%S')}]跟踪结果 \n\n {excute_view}"
            return excute_content, view

        except Exception as e:
            logger.error(f"Tracking Result Can't View!{str(e)}")
            return excute_content, None
