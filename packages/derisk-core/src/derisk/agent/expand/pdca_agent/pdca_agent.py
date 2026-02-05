import asyncio
import json
import logging
import time
import uuid
from typing import Optional, List, Dict, Any
from derisk.agent import ProfileConfig, AgentMessage, Agent, AgentSystemMessage, ActionOutput, BlankAction
from derisk.agent.core import system_tool_dict
from derisk.agent.core.file_system.file_tree import TreeNodeData
from derisk.agent.core.memory.gpts.agent_system_message import SystemMessageType, AgentPhase
from derisk.agent.core.memory.gpts.gpts_memory import AgentTaskContent, AgentTaskType
from derisk.agent.core.role import AgentRunMode
from derisk.agent.core.schema import MessageMetrics, Status, ActionInferenceMetrics
from derisk.agent.expand.actions.agent_action import AgentStart
from derisk.agent.expand.actions.kanban_action import KanbanAction
from derisk.agent.expand.actions.knowledge_action import KnowledgeSearch
from derisk.agent.expand.actions.sandbox_action import SandboxAction
from derisk.agent.expand.actions.system_action import SystemAction
from derisk.agent.expand.actions.terminate_action import Terminate
from derisk.agent.expand.actions.tool_action import ToolAction
from derisk.agent.expand.pdca_agent.file_system import FileSystem
from derisk.agent.expand.pdca_agent.plan_manager import AsyncKanbanManager
from derisk.agent.expand.pdca_agent.plan_models import Stage
from derisk.agent.expand.pdca_agent.prompt_v7 import SYSTEM_PROMPT
from derisk.agent.expand.pdca_agent.prompt_v7 import USER_PROMPT
from derisk.agent.expand.react_agent.react_agent import ReActAgent
from derisk.agent.expand.react_agent.react_parser import CONST_LLMOUT_TITLE
from derisk.context.event import EventType, ChatPayload, StepPayload, ActionPayload
from derisk.util.json_utils import serialize
from derisk.util.tracer import root_tracer

_REACT_DEFAULT_GOAL = """通过标准化的 PDCA 循环，在确保数据强一致性与执行可靠性的前提下，独立完成复杂的跨阶段任务。"""

logger = logging.getLogger(__name__)


class PDCAAgent(ReActAgent):
    max_retry_count: int = 100
    run_mode: AgentRunMode = AgentRunMode.LOOP

    profile: ProfileConfig = ProfileConfig(
        name="Derisk(PDCA)",
        role="PDCAMaster",
        goal=_REACT_DEFAULT_GOAL,
        system_prompt_template=SYSTEM_PROMPT,
        user_prompt_template=USER_PROMPT,
    )

    def __init__(self, **kwargs):
        """Init indicator AssistantAgent."""
        super().__init__(**kwargs)
        ## 注意顺序，解析有优先级，工具如果前面没匹配都会兜底到ToolAction，没有工具会兜底到BlankAction
        self._init_actions(
            [AgentStart, KnowledgeSearch,KanbanAction, SandboxAction, SystemAction, Terminate, ToolAction, BlankAction])

    async def system_tool_injection(self):
        await super().system_tool_injection()
        ## 注入当前需要的系统工具
        from derisk.agent.expand.pdca_agent.tools.todo_plan_tools import PDCA_SYSTEM_TOOLS
        for k, _ in PDCA_SYSTEM_TOOLS.items():
            if k in system_tool_dict:
                self.available_system_tools[k] = system_tool_dict[k]

    async def generate_reply(
        self,
        received_message: AgentMessage,
        sender: Agent,
        reviewer: Optional[Agent] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        **kwargs,
    ) -> AgentMessage:
        """Generate a reply based on the received messages."""
        logger.info(
            f"generate agent reply!message_id={received_message.message_id},sender={sender}, message_content={received_message.content}"
        )
        message_metrics = MessageMetrics()
        message_metrics.start_time_ms = time.time_ns() // 1_000_000

        await self.push_context_event(EventType.ChatStart, ChatPayload(
            received_message_id=received_message.message_id,
            received_message_content=received_message.content,
        ), await self.task_id_by_received_message(received_message))

        root_span = root_tracer.start_span(
            "agent.generate_reply",
            metadata={
                "app_code": self.agent_context.agent_app_code,
                "sender": sender.name,
                "recipient": self.name,
                "reviewer": reviewer.name if reviewer else None,
                "received_message": json.dumps(received_message.to_dict(), default=serialize, ensure_ascii=False),
                "conv_id": self.not_null_agent_context.conv_id,
                "rely_messages": (
                    [msg.to_dict() for msg in rely_messages] if rely_messages else None
                ),
            },
        )
        reply_message = None
        agent_system_message: Optional[AgentSystemMessage] = AgentSystemMessage.build(
            agent_context=self.agent_context, agent=self, type=SystemMessageType.STATUS,
            phase=AgentPhase.AGENT_RUN)
        self.received_message_state[received_message.message_id] = Status.TODO
        try:

            ## 开始当前的任务空间
            await self.memory.gpts_memory.upsert_task(conv_id=self.agent_context.conv_id,
                                                      task=TreeNodeData(
                                                          node_id=received_message.message_id,
                                                          parent_id=received_message.goal_id,
                                                          content=AgentTaskContent(agent_name=self.name,
                                                                                   task_type=AgentTaskType.AGENT.value,
                                                                                   message_id=received_message.message_id),
                                                          state=self.received_message_state[
                                                              received_message.message_id].value,
                                                          name=received_message.current_goal,
                                                          description=received_message.content
                                                      ))

            self.received_message_state[received_message.message_id] = Status.RUNNING
            fs = FileSystem(session_id=self.agent_context.conv_session_id, goal_id=received_message.message_id,
                            sandbox=self.sandbox_manager.client)
            pm: AsyncKanbanManager = AsyncKanbanManager(agent_id=self.name, session_id=received_message.message_id,
                                                        file_system=fs)

            is_success = True
            all_tool_messages: List[Dict] = []
            step = 0
            while step < self.max_retry_count:
                with (root_tracer.start_span(
                    "agent.generate_reply.loop",
                    metadata={
                        "app_code": self.agent_context.agent_app_code,
                        "conv_id": self.agent_context.conv_id,
                        "current_retry_counter": self.current_retry_counter
                    }
                )):
                    # 根据收到的消息对当前恢复消息的参数进行初始化
                    rounds = received_message.rounds + 1
                    goal_id = received_message.message_id
                    current_goal = received_message.current_goal
                    observation = received_message.observation

                    if step > 0:
                        if self.run_mode != AgentRunMode.LOOP:
                            if self.enable_function_call:
                                ## 基于当前action的结果，构建history_dialogue 和 tool_message
                                tool_messages = self.function_callning_reply_messages(agent_llm_out, act_outs)
                                all_tool_messages.extend(tool_messages)

                        observation = reply_message.observation
                        rounds = reply_message.rounds + 1
                    self._update_recovering(is_retry_chat)

                    step += 1
                    ### 0.生成当前轮次的新消息

                    reply_message = await self.init_reply_message(
                        received_message=received_message, sender=sender, rounds=rounds, goal_id=goal_id,
                        current_goal=current_goal, observation=observation
                    )

                    await self.push_context_event(EventType.StepStart, StepPayload(
                        message_id=reply_message.message_id), await self.task_id_by_received_message(received_message))

                    reply_message, agent_llm_out = await self._generate_think_message(
                        received_message=received_message,
                        sender=sender,
                        new_reply_message=reply_message,
                        rely_messages=rely_messages,
                        historical_dialogues=historical_dialogues,
                        is_retry_chat=is_retry_chat,
                        message_metrics=message_metrics,
                        tool_messages=all_tool_messages,
                        pm=pm,
                        **kwargs
                    )


                    current_stage: Optional[Stage] = pm.kanban.get_current_stage() if pm.kanban else None

                    if current_stage:
                        reply_message.goal_id = current_stage.stage_id
                        reply_message.current_goal = current_stage.description
                        logger.info(f"创建当前stage任务节点: {current_stage.stage_id}")
                        await self.memory.gpts_memory.upsert_task(conv_id=self.agent_context.conv_id,
                                                                  task=TreeNodeData(
                                                                      node_id=current_stage.stage_id,
                                                                      parent_id=received_message.message_id,
                                                                      content=AgentTaskContent(
                                                                          agent_name=self.name,
                                                                          task_type=AgentTaskType.STAGE.value,
                                                                          message_id=reply_message.message_id),
                                                                      state=Status.TODO.value,
                                                                      name=current_stage.description,
                                                                      description=""
                                                                  ))
                    # 4. 执行 (Do)
                    act_extent_param = self.prepare_act_param(
                        received_message=received_message,
                        sender=sender,
                        rely_messages=rely_messages,
                        historical_dialogues=historical_dialogues,
                        reply_message=reply_message,
                        agent_llm_out=agent_llm_out,
                        pm=pm,
                        **kwargs,
                    )
                    with root_tracer.start_span(
                        "agent.generate_reply.act",
                    ) as span:
                        # 3.Act based on the results of your thinking
                        act_outs: List[ActionOutput] = await self.act(
                            message=reply_message,
                            sender=sender,
                            reviewer=reviewer,
                            is_retry_chat=is_retry_chat,
                            last_speaker_name=last_speaker_name,
                            received_message=received_message,
                            agent_context=self.agent_context,
                            agent_llm_out=agent_llm_out,
                            agent=self,
                            **act_extent_param,
                        )
                        if act_outs:
                            action_report = act_outs
                            reply_message.action_report = action_report

                    for act_out in act_outs:
                        if not act_out.is_exe_success:
                            logger.error(f"{act_out.action} execute failed!")
                        if act_out.action in ["create_kanban"]:
                            # 注意：通常这里意味着 Task 结束了
                            logger.info("📋 create kanban...")

                        elif act_out.action == "submit_deliverable":
                            ## 更新当前的任务空间
                            await self.memory.gpts_memory.upsert_task(conv_id=self.agent_context.conv_id,
                                                                      task=TreeNodeData(
                                                                          node_id=current_stage.stage_id,
                                                                          name=current_stage.description,
                                                                          state=Status.COMPLETE.value,
                                                                      ))
                        else:
                            # [FIX] 使用循环开始时锁定的 current_task_id，而不是现在去查询
                            await pm.record_work(
                                tool=act_out.action,
                                args=act_out.action_input,
                                summary=act_out.content,
                                # result=act_out.content
                            )

                    ### 非LOOP模式以及非FunctionCall模式
                    if self.run_mode != AgentRunMode.LOOP and not self.enable_function_call:
                        logger.debug(f"Agent {self.name} reply success!{reply_message}")
                        break
                    ## Action明确结束的，成功后直接退出
                    if any([act_out.terminate for act_out in act_outs]):
                        break

                    # Continue to run the next round
                    self.current_retry_counter += 1


                    # 发送当前轮的结果消息(fuctioncall执行结果、非LOOP模式下的异常记录、LOOP模式的上一轮消息)
                    await self.send(reply_message, recipient=self, request_reply=False)

                    # 记录当前消息的任务关系




            reply_message.success = is_success
            # 6.final message adjustment
            await self.adjust_final_message(is_success, reply_message)

            await self.push_context_event(EventType.ChatEnd, ChatPayload(
                received_message_id=received_message.message_id,
                received_message_content=received_message.content,
            ), await self.task_id_by_received_message(received_message))

            self.received_message_state[received_message.message_id] = Status.COMPLETE
            reply_message.metrics.action_metrics = [
                ActionInferenceMetrics.create_metrics(
                    act_out.metrics or ActionInferenceMetrics(start_time_ms=time.time_ns() // 1_000_000)) for act_out in
                act_outs]
            reply_message.metrics.end_time_ms = time.time_ns() // 1_000_000
            return reply_message

        except Exception as e:
            logger.exception("Generate reply exception!")
            err_message = AgentMessage(message_id=uuid.uuid4().hex, content=str(e),
                                       action_report=[ActionOutput(is_exe_success=False,
                                                                   content=f"Generate reply exception:{str(e)}")])
            err_message.rounds = 9999
            err_message.success = False

            agent_system_message.update(1, content=json.dumps({self.name: str(e)}, ensure_ascii=False),
                                        final_status=Status.FAILED, type=SystemMessageType.ERROR)
            self.received_message_state[received_message.message_id] = Status.FAILED

            return err_message
        finally:
            if reply_message:
                root_span.metadata["reply_message"] = reply_message.to_dict()
                if agent_system_message:
                    agent_system_message.agent_message_id = reply_message.message_id
                    await self.memory.gpts_memory.append_system_message(agent_system_message)

            await self.memory.gpts_memory.upsert_task(conv_id=self.agent_context.conv_id,
                                                      task=TreeNodeData(
                                                          node_id=received_message.message_id,
                                                          parent_id=received_message.goal_id,
                                                          state=self.received_message_state[
                                                              received_message.message_id].value,
                                                          name=received_message.current_goal,
                                                          description=received_message.content
                                                      ))
            ## 处理消息状态
            self.received_message_state.pop(received_message.message_id)
            root_span.end()

    def prepare_act_param(
        self,
        received_message: Optional[AgentMessage],
        sender: Agent,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Prepare the parameters for the act method."""
        return {
            "pm": kwargs.get("pm"),

        }

    async def act(
        self,
        message: AgentMessage,
        sender: Agent,
        reviewer: Optional[Agent] = None,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        received_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> List[ActionOutput]:
        """Perform actions."""
        if not message:
            raise ValueError("The message content is empty!")

        act_outs: List[ActionOutput] = []
        # 第一阶段：解析所有可能的action
        real_actions = self.agent_parser.parse_actions(
            llm_out=kwargs.get("agent_llm_out"), action_cls_list=self.actions, received_message=received_message,
            **kwargs
        )

        # 第二阶段：并行执行所有解析出的action
        if real_actions:
            explicit_keys = ['ai_message', 'resource', 'rely_action_out', 'render_protocol', 'message_id', 'sender',
                             'agent', 'received_message', 'agent_context', "memory"]

            # 创建一个新的kwargs，它不包含explicit_keys中出现的键
            filtered_kwargs = {k: v for k, v in kwargs.items() if k not in explicit_keys}

            # 创建所有action的执行任务
            tasks = []
            for real_action in real_actions:
                task = real_action.run(
                    ai_message=message.content if message.content else "",
                    resource=self.resource,
                    resource_map=self.resource_map,
                    render_protocol=await self.memory.gpts_memory.async_vis_converter(
                        self.not_null_agent_context.conv_id),
                    message_id=message.message_id,
                    sender=sender,
                    agent=self,
                    received_message=received_message,
                    agent_context=self.agent_context,
                    memory=self.memory,
                    **filtered_kwargs,
                )
                tasks.append((real_action, task))

            # 并行执行所有任务
            results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

            # 处理执行结果
            for (real_action, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    # 处理执行异常
                    logger.exception(f"Action execution failed: {result}")
                    # 可以选择创建一个表示失败的ActionOutput，或者跳过
                    act_outs.append(ActionOutput(content=str(result), name=real_action.name, is_exe_success=False))
                else:
                    if result:
                        act_outs.append(result)
                await self.push_context_event(
                    EventType.AfterAction,
                    ActionPayload(action_output=result),
                    await self.task_id_by_received_message(received_message)
                )

        return act_outs

    def register_variables(self):
        """子类通过重写此方法注册变量"""
        logger.info(f"register_variables {self.role}")
        super().register_variables()

        @self._vm.register('system_tools', '系统工具')
        async def var_tools(instance):
            result = ""
            if self.available_system_tools:
                logger.info("注入系统工具")
                tool_prompts = ""
                for k, v in self.available_system_tools.items():
                    tool_prompts += (f"<tool>\n{await v.get_prompt(lang=instance.agent_context.language)}\n</tool>\n")

                result = f"""### 可用系统工具\n<tools>\n{tool_prompts}</tools>\n"""

            if result:
                return result

            return None

        @self._vm.register('kanban_overview', '任务看版')
        async def task_board(instance, pm: AsyncKanbanManager):
            return await pm.get_kanban_status()

        @self._vm.register('current_stage_detail', '当前任务')
        async def current_task(instance, pm: AsyncKanbanManager):
            return await pm.get_current_stage_detail()

        @self._vm.register('available_deliverables', '当前任务')
        async def current_task(instance, pm: AsyncKanbanManager):
            return await pm.get_available_deliverables()
