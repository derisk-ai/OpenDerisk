import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from derisk.agent import ConversableAgent, ProfileConfig, AgentMessage, Agent
from derisk.agent.core.base_parser import AgentParser
from derisk.agent.core.base_team import ManagerAgent
from derisk.agent.core.role import AgentRunMode
from derisk.agent.expand.actions.tracking_action import TrackingAction
from derisk.agent.expand.parsers.tracking_parser import TrackingAgentParaser, TrackingInfo
from derisk.context.window import ContextWindow
from derisk.util.configure import DynConfig
from derisk.util.json_utils import serialize
from derisk.util.tracer import root_tracer

logger = logging.getLogger(__name__)
SYSTEM_PROMPT_TEMPLATE = """
你是一个任务跟踪管理专家，名字叫{{name}}.仔细阅读并理解用户的任务需求，根据下面信息和约束规范，按要求格式输出一个跟踪任务的配置。

## 可用代理
{{agents}}

## 约束规范
1.当前时间是:{{now_time}}

## 请使按如下结构描述输出你的答案
{{out_schema}}
"""


class TrackingAgent(ManagerAgent):
    max_retry_count: int = 15
    run_mode: AgentRunMode = AgentRunMode.TRACKING

    profile: ProfileConfig = ProfileConfig(
        name=DynConfig("stalker"),
        role=DynConfig("TrackingMaster"),
        goal=DynConfig("I can continuously track and provide feedback on the target according to user requirements."),
        system_prompt_template=SYSTEM_PROMPT_TEMPLATE,
    )

    # Agent解析器(如果不配置默认走Action解析)
    agent_paraser: Optional[AgentParser] = TrackingAgentParaser()

    def __init__(self, **kwargs):
        """Init indicator AssistantAgent."""
        super().__init__(**kwargs)

        self._init_actions([TrackingAction])

    def register_variables(self):
        """子类通过重写此方法注册变量"""
        logger.info(f"tracking agent register_variables {self.role}")
        super().register_variables()

        @self._vm.register('out_schema', 'Agent模型输出结构定义')
        def var_out_schema(instance):
            if instance.agent_paraser:
                return instance.agent_paraser.schema()
            else:
                return None

        @self._vm.register('agents', '规划可用的代理信息')
        def var_out_schema(instance):
            return "\n".join([f"- 代理名称:'{item.name}'    能力描述:'{item.desc}'" for item in instance.agents])

    async def receive(
        self,
        message: AgentMessage,
        sender: Agent,
        reviewer: Optional[Agent] = None,
        request_reply: Optional[bool] = None,
        reply_to_sender: Optional[bool] = True,  # 是否向sender发送回复消息
        request_sender_reply: Optional[bool] = True,  # 向sender发送消息是是否仍request_reply
        silent: Optional[bool] = False,
        is_recovery: Optional[bool] = False,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> Optional[AgentMessage]:
        """Receive a message from another agent."""

        origin_current_agent_id = root_tracer.get_current_agent_id()
        try:
            root_tracer.set_current_agent_id(self.agent_context.agent_app_code)
            with root_tracer.start_span(
                "agent.receive",
                metadata={
                    "sender": sender.name,
                    "recipient": self.name,
                    "reviewer": reviewer.name if reviewer else None,
                    "agent_message": json.dumps(message.to_dict(), default=serialize, ensure_ascii=False),
                    "request_reply": request_reply,
                    "silent": silent,
                    "is_recovery": is_recovery,
                    "conv_uid": self.not_null_agent_context.conv_id,
                    "is_human": self.is_human,
                },
            ):
                await ContextWindow.create(agent=self, task_id=message.message_id)
                if silent:
                    message.show_message = False
                await self._a_process_received_message(message, sender)
                if request_reply is False or request_reply is None:
                    return None

                if not self.is_human:
                    if isinstance(sender, ConversableAgent) and sender.is_human:

                        scheduler = AsyncIOScheduler()
                        loop = asyncio.get_running_loop()
                        future = loop.create_future()  # 创建一个 Future 用于挂起协程

                        reply = await self.generate_reply(
                            received_message=message,
                            sender=sender,
                            reviewer=reviewer,
                            is_retry_chat=is_retry_chat,
                            last_speaker_name=last_speaker_name,
                            historical_dialogues=historical_dialogues,
                            rely_messages=rely_messages,
                        )
                        tracking_info: TrackingInfo = self.agent_paraser.parse(reply.content)

                        # 添加生成的用户消息调度存活保持的任务时长
                        shutdown_time = datetime.now(timezone.utc) + timedelta(minutes=tracking_info.duration)

                        scheduler.add_job(
                            lambda: (scheduler.shutdown(), future.cancel()),  # 关闭调度器并取消 Future
                            "date",
                            run_date=shutdown_time,
                            timezone="UTC"
                        )
                        scheduler.start()
                        try:
                            result = await future  # 挂起协程，直到 future 被取消
                        except asyncio.CancelledError:
                            logger.info("当前跟踪任务已经结束！")
                        finally:
                            if scheduler.running:
                                scheduler.shutdown()  # 确保资源释放
                        logger.info("用户对话已经完成跟踪调度！")
                        for action in self.actions:
                            await action.terminate(message_id=reply.message_id)
                    else:
                        reply = await self.generate_reply(
                            received_message=message,
                            sender=sender,
                            reviewer=reviewer,
                            is_retry_chat=is_retry_chat,
                            historical_dialogues=historical_dialogues,
                            rely_messages=rely_messages,
                        )

                    if reply is not None and reply_to_sender:
                        await self.send(reply, sender, request_reply=request_sender_reply)

                    return reply
        finally:
            root_tracer.set_current_agent_id(origin_current_agent_id)

    def prepare_act_param(
        self,
        received_message: Optional[AgentMessage],
        sender: Agent,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Prepare the parameters for the act method."""
        reply_message: AgentMessage = kwargs['reply_message']
        tracking_info: TrackingInfo = self.agent_paraser.parse(reply_message.content)

        return {
            "agents": self.agents,
            "action_input": tracking_info,
            "interval": tracking_info.interval,
            "duration": tracking_info.duration * 60,
            "gpts_memory": self.memory.gpts_memory,
            "self_agent": self,
            "self_message": kwargs.get('reply_message'),
        }
