import logging
from typing import Optional, List, Union, Callable, Awaitable

from derisk.agent import ConversableAgent, AgentMessage, Agent, ActionOutput
from derisk.agent.core.file_system.file_tree import TreeNodeData
from derisk.agent.core.memory.gpts.gpts_memory import AgentTaskContent, ConversationCache
from derisk.agent.core.role import AgentRunMode
from derisk.agent.core.schema import ActionInferenceMetrics, Status
from derisk.agent.util.llm.llm_client import AgentLLMOut
from derisk.context.event import ChatPayload, StepPayload, ActionPayload, EventType
from derisk.context.window import ContextWindow
from derisk.core.interface.scheduler import SchedulePayload, Stage, Signal
from derisk.util.date_utils import current_ms
from derisk.util.tracer import trace, root_tracer

logger = logging.getLogger(__name__)


class ScheduledAgent(ConversableAgent):
    """分阶段调度的Agent"""

    def handler(self, stage: str) -> Callable[[SchedulePayload], Awaitable[None]]:
        """每个阶段的处理函数"""
        return {
            Stage.THINK.value: self.handle_think,
            Stage.ACT.value: self.handle_act,
            Stage.ANSWER.value: self.handle_answer,
        }.get(stage)

    async def receive(self, message: AgentMessage, sender: Agent, **kwargs) -> None:
        with root_tracer.start_span(
            "agent.receive",
            metadata={
                "sender": sender.name,
                "recipient": self.name,
                "app_code": self.not_null_agent_context.agent_app_code,
                "conv_id": self.not_null_agent_context.conv_id,
            },
        ):
            await self._a_process_received_message(message, sender)

            # 任务上下文
            context_index = await self._ensure_context_node(message=message, sender=sender, **kwargs)
            await self.push_context_event(EventType.ChatStart, ChatPayload(
                received_message_id=message.message_id,
                received_message_content=message.content,
            ), context_index)

            # 进度推进
            await self.push_schedule(Stage.THINK.value, context_index=context_index)
            return None

    async def _ensure_context_node(self, message: AgentMessage, sender: Agent, **kwargs) -> str:
        if hasattr(self, "agents") and sender in self.agents:
            # 小弟发的消息 说明是answer消息 需要回到父(自己)节点的上下文
            cache: ConversationCache = await self.cache()
            return cache.task_manager.get_node(message.goal_id).parent_id

        # 初始化任务上下文
        self.received_message_state[message.message_id] = Status.TODO
        await ContextWindow.create(agent=self, task_id=message.message_id)
        ## 开始当前的任务空间
        await self.memory.gpts_memory.upsert_task(
            conv_id=self.agent_context.conv_id,
            task=TreeNodeData(
                node_id=message.message_id,
                parent_id=message.goal_id,
                content=AgentTaskContent(agent=self),
                state=self.received_message_state[message.message_id].value,
                name=message.current_goal,
                description=message.content
            ))
        return message.message_id

    async def push_schedule(self, stage: str, context_index: str, agent_name: str = None, message_id: str = None):
        agent_name = agent_name or self.name
        await self.scheduler.put(SchedulePayload(
            conv_id=self.agent_context.conv_id,
            agent_name=agent_name,
            stage=stage,
            context_index=context_index,
            message_id=message_id
        ))

    @trace("agent.handle_think")
    async def handle_think(self, payload: SchedulePayload):
        # ===== 1. 取出上下文 =====
        cache: ConversationCache = await self.cache()
        received_message_id: str = payload.message_id or payload.context_index
        received_gpts_message = cache.messages.get(received_message_id)

        received_message = received_gpts_message.to_agent_message()
        sender: Agent = cache.senders.get(received_gpts_message.sender_name)
        node: TreeNodeData[AgentTaskContent] = await self.node(payload.context_index)

        # ===== 2. 调用模型思考 =====
        # 2.0 前置检查
        assert received_gpts_message.receiver_name == self.name
        # 确认所有小弟都完成了任务
        not_done = [node.node_id for child_id in node.child_ids if (node := await self.node(child_id)) and node.state != Status.COMPLETE.value]
        if not_done:
            logger.info(f"{self.name} 部分子任务未完成: ")
            return

        # 2.1 数据准备
        current_step_message = await self.init_reply_message(received_message, goal_id=received_message.message_id)
        current_step_message.rounds = await self.memory.gpts_memory.next_message_rounds(received_gpts_message.conv_id)
        self.received_message_state[received_message_id] = Status.RUNNING
        await self.push_context_event(EventType.StepStart, StepPayload(message_id=current_step_message.message_id), payload.context_index)
        thinking_messages, resource_info, system_prompt, user_prompt = await self.load_thinking_messages(received_message, sender=sender)

        # 2.2 调用模型
        llm_out: AgentLLMOut = await self.thinking(
            thinking_messages, current_step_message.message_id, sender,
            received_message=received_message
        )
        current_step_message.system_prompt = system_prompt
        current_step_message.user_prompt = user_prompt
        current_step_message.resource_info = resource_info
        current_step_message.thinking = llm_out.thinking_content
        current_step_message.model_name = llm_out.llm_name
        current_step_message.content = llm_out.content
        current_step_message.metrics.llm_metrics = llm_out.metrics
        current_step_message.tool_calls = llm_out.tool_calls
        await self._a_append_message(current_step_message, sender=self, save_db=False)

        # ===== 3. 进度推进 =====
        await self.push_schedule(Stage.ACT.value, context_index=payload.context_index, message_id=current_step_message.message_id)

    @trace("agent.handle_act")
    async def handle_act(self, payload: SchedulePayload):
        # ===== 1. 取出上下文 =====
        cache: ConversationCache = await self.cache()
        received_message_id: str = payload.context_index
        received_gpts_message = cache.messages.get(received_message_id)
        received_message = received_gpts_message.to_agent_message()
        sender: Agent = cache.senders.get(received_gpts_message.sender_name)
        current_step_message_id: str = payload.message_id
        current_step_gpts_message = cache.messages.get(current_step_message_id)
        current_step_message = current_step_gpts_message.to_agent_message()

        # ===== 2. 动作执行 =====
        act_extent_param = self.prepare_act_param(
            received_message=received_message,
            sender=sender,
            reply_message=current_step_message,
        )
        act_metrics = ActionInferenceMetrics(start_time_ms=current_ms())
        act_outs: Optional[Union[List[ActionOutput], ActionOutput]] = await self.act(
            message=current_step_message,
            sender=sender,
            received_message=received_message,
            **act_extent_param
        )
        action_report = []
        if act_outs:
            act_reports_dict = []
            if not isinstance(act_outs, list):
                action_report = [act_outs]
                act_reports_dict.extend(act_outs.to_dict())
            else:
                action_report = act_outs
                act_reports_dict = [item.to_dict() for item in act_outs]
            current_step_message.action_report = action_report
        current_step_message.metrics.action_metrics = [ActionInferenceMetrics.create_metrics(act_out.metrics or act_metrics) for act_out in act_outs]
        await self.push_context_event(EventType.AfterStepAction, ActionPayload(action_output=action_report), payload.context_index)
        await self.push_context_event(EventType.StepEnd, StepPayload(
            message_id=current_step_message.message_id), payload.context_index)

        # ===== 3. 进度推进 ======
        terminate = self.run_mode != AgentRunMode.LOOP or any((act_out for act_out in act_outs if act_out.terminate))
        await self._a_append_message(current_step_message, sender=self, save_db=not terminate)
        next_stage = Stage.ANSWER.value if terminate else Stage.THINK.value
        from derisk.agent.core.reasoning.reasoning_action import AgentAction
        if Stage.THINK.value == next_stage and any(act_out for act_out in act_outs if act_out.name == AgentAction.name):
            # 若存在AgentAction 则下游回消息时再推进下一轮THINK 无需重复push
            return

        await self.write_memories(
            question=received_message.content,
            ai_message=current_step_message.content,
            action_output=act_outs,
            agent_id=self.not_null_agent_context.agent_app_code or self.not_null_agent_context.gpts_app_code,
            reply_message=current_step_message,
            terminate=any([act_out.terminate for act_out in act_outs]),
        )
        # 如果是answer则基于当前step消息回复用户 如果是think则基于当前task推进下一轮，此时message传空即可
        message_id = current_step_message_id if next_stage == Stage.ANSWER.value else None
        await self.push_schedule(next_stage, context_index=payload.context_index, message_id=message_id)

    @trace("agent.handle_answer")
    async def handle_answer(self, payload: SchedulePayload):
        # ===== 1. 取出上下文 =====
        cache: ConversationCache = await self.cache()
        received_message_id: str = payload.context_index
        received_gpts_message = cache.messages.get(received_message_id)
        sender: Agent = cache.senders.get(received_gpts_message.sender_name)
        node: TreeNodeData[AgentTaskContent] = await self.node(payload.context_index)

        # ===== 2. 更新上下文 =====
        self.received_message_state[received_message_id] = Status.COMPLETE
        node.state = Status.COMPLETE.value
        await self.memory.gpts_memory.upsert_task(conv_id=payload.conv_id, task=node)

        await self.push_context_event(EventType.ChatEnd, ChatPayload(
            received_message_id=received_gpts_message.message_id,
            received_message_content=received_gpts_message.content,
        ), payload.context_index)

        # ===== 3. 进度推进 =====
        # if isinstance(sender, ScheduledAgent):
        #     # ScheduledAgent 通过调度触发
        #     await self.push_schedule(Stage.THINK.value, agent_name=received_gpts_message.sender_name, context_index=node.parent_id)
        # else:
        # 通过send消息触发
        reply_message_id: str = payload.message_id
        reply_gpts_message = cache.messages.get(reply_message_id)
        reply_message = reply_gpts_message.to_agent_message()
        await self.send(reply_message, recipient=sender, request_reply=False)

        from derisk.agent import UserProxyAgent
        if isinstance(sender, UserProxyAgent):
            # 向用户回复消息 结束调度
            await self.scheduler.put(Signal.STOP)

    async def cache(self) -> ConversationCache:
        return await self.memory.gpts_memory.cache(self.agent_context.conv_id)

    async def node(self, node_id: str) -> Optional[TreeNodeData[AgentTaskContent]]:
        return await self.memory.gpts_memory.get_task(self.agent_context.conv_id, node_id)
