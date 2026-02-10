import json
import logging
import time
from datetime import datetime
from typing import Optional, Dict

from derisk.context.window import ContextWindow
from derisk.vis import SystemVisTag
from ... import GptsMemory, AgentContext, AgentResource, ConversableAgent, AgentMessage, AgentMemory
from ...core.action.base import ToolCall, Action, ActionOutput, AskUserType
from ...core.memory.gpts import GptsMessage
from ...core.reasoning.reasoning_action import AgentActionInput

from derisk.agent.resource import ToolParameter, FunctionTool
from ...core.schema import Status, ActionInferenceMetrics

_AGENT_START_PROMPT = """\
代理(Agent)交互接口。用于使用其他代理(Agent)完成任务进入代理模式。
**注意事项**:* 指定的agent和你的上下文是隔离的，请传递准确、完整的任务描述。
**防御性原则**：在调用任何子 Agent 之前，必须严格评估该 Agent 的能力是否与当前任务目标**精确匹配**。如果收到的指令（如“查询某个监控表”）在当前可用的子 Agent 工具集中没有直接对应的能力，**严禁**选择一个功能不相关的工具进行“尝试性”调用。此时，应将此情况作为发现记录在报告中，并重新评估计划，而不是执行错误的工具调用。
"""

logger = logging.getLogger(__name__)


class AgentAction(Action[AgentActionInput]):
    name = "Agent"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.action_view_tag = SystemVisTag.VisPlans.value

    async def _action_init_push(self, gpts_memory: GptsMemory, agent: "ConversableAgent", current_message: AgentMessage,
                                agent_context: AgentContext, start_time):
        init_action_outs = [ActionOutput(
            name=self.name,
            content=f"### {agent.name}Agent运行中\n** {self.action_input.content} **",
            start_time=start_time,
            action_id=self.action_uid,
            thoughts=self.action_input.thought,
            action=self.action_input.agent_name,
            action_input=self.action_input.to_dict(),
            state=Status.RUNNING.value,
        )]

        ## 展示工具任务基础信息
        await gpts_memory.push_message(conv_id=agent.agent_context.conv_id, stream_msg={
            "uid": current_message.message_id,
            "type": "all",
            "sender": agent.name or agent.role,
            "sender_role": agent.role,
            "message_id": current_message.message_id,
            "goal_id": current_message.goal_id,
            "conv_id": agent_context.conv_id,
            "conv_session_uid": agent_context.conv_session_id,
            "app_code": agent_context.gpts_app_code,
            "start_time": start_time,
            "action_report": init_action_outs
        }, )

    async def run(
        self,
        ai_message: str = None,
        resource: Optional[AgentResource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        **kwargs,
    ) -> ActionOutput:
        """Perform the action."""
        action_input = self.action_input or AgentActionInput.model_validate_json(
            json_data=ai_message
        )
        metrics = ActionInferenceMetrics()
        metrics.start_time_ms = time.time_ns() // 1_000_000
        try:

            action_id = kwargs.get("action_id", None)
            sender: ConversableAgent = kwargs["agent"]
            logger.warning(
                f"[AgentAction] sender.agents: {[f'{a.name}({a.agent_context.agent_app_code})' for a in sender.agents]}")
            logger.warning(f"[AgentAction] Looking for agent with agent_name={action_input.agent_name}")
            recipient = next(
                (agent for agent in sender.agents if
                 agent.name == action_input.agent_name or agent.agent_context.agent_app_code == action_input.agent_name),
                None,
            )
            if not recipient:
                logger.error(
                    f"[AgentAction] recipient can't be empty! sender.agents={[(a.name, a.agent_context.agent_app_code) for a in sender.agents]}, trying to find={action_input.agent_name}")
                raise RuntimeError("recipient can't be empty")

            received_message = (
                kwargs["message"] if "message" in kwargs else AgentMessage.init_new()
            )
            start_time = datetime.now()
            memory: AgentMemory = kwargs.get('memory')
            agent: ConversableAgent = kwargs.get('agent')
            agent_context: AgentContext = kwargs.get('agent_context')
            message_id: str = kwargs.get('message_id')
            current_message: AgentMessage = kwargs.get('current_message')
            self._render = kwargs.get("render_protocol") or self._render

            if memory:
                logger.info("任务分派前先记录当前agent启动消息！")
                ## agent 转发消息 需要提前记录，否则等子agent返回再记录会导致显示混乱
                await memory.gpts_memory.append_message(conv_id=agent_context.conv_id,
                                                        message=GptsMessage.from_agent_message(current_message,
                                                                                               sender=agent,
                                                                                               receiver=agent),
                                                        save_db=False)

            # 初始化AgentAction的展示
            await self._action_init_push(gpts_memory=memory.gpts_memory, agent=agent, current_message=current_message,
                                         agent_context=agent_context, start_time=start_time)
            #  构建转发给Agent的新消息
            # 注意：这里使用 self.action_uid 作为 goal_id，让子Agent的任务节点挂载到agent_start动作下
            # 形成正确的层级关系：A Agent -> agent_start -> B Agent -> B的工具
            message = AgentMessage.init_new(
                content=(
                    action_input.content
                    + "\n\n"
                    + json.dumps(action_input.extra_info, ensure_ascii=False)
                ),
                context=(received_message.context or {}) | (action_input.extra_info or {}),
                rounds=await sender.memory.gpts_memory.next_message_rounds(sender.not_null_agent_context.conv_id),
                name=sender.name,
                role=sender.role,
                show_message=False,
                observation=action_input.content,
                current_goal=action_input.content,
                goal_id=current_message.message_id,
            )
            # message.goal_id = kwargs["action_id"] if "action_id" in kwargs else ""
            # message.current_goal = action_input.content
            # 合并context 且action_input.extra_info优先级更高
            # 注意：不修改 message_id，让它保持 init_new 生成的唯一 ID
            # 这样 B Agent 的任务节点会有唯一的 node_id，且不同于 parent_id (goal_id)
            message.context = (message.context or {}) | (action_input.extra_info or {})

            logger.info(f"[ACTION]---------->   Agent Action [{sender.name}] --> [{recipient.name}]")

            # B Agent 应该使用 agent_start 的 action_uid 作为父节点
            # 但 message_id 应该保持自动生成，确保 B Agent 的任务节点有唯一的 ID
            # 并且 parent_id (goal_id) ≠ node_id，避免被判定为根节点
            await ContextWindow.create(agent=recipient, task_id=message.message_id)
            answer: AgentMessage = await sender.send(message=message, recipient=recipient, request_reply=True,
                                                     request_sender_reply=False)

            from derisk.agent.core.scheduled_agent import ScheduledAgent
            if isinstance(recipient, ScheduledAgent) and recipient.scheduler and recipient.scheduler.running():
                # ScheduledAgent由scheduler驱动，其他Agent由send/receive/generate_reply的loop驱动
                # ScheduledAgent receive后直接就return了，再异步act
                # 因此这里不能直接return，而需要确保所有异步act都执行完成了
                await recipient.scheduler.schedule()

            metrics.end_time_ms = time.time_ns() // 1_000_000
            ask_user = True if answer and answer.action_report and any(
                [act_out.ask_user for act_out in answer.action_report]) else False
            ## 终止状态要排除正常返回的报告Agent
            # terminate = True if answer and answer.action_report and any([act_out.terminate for act_out in answer.action_report]) else False
            ask_type = AskUserType.NESTED_AGENT if ask_user else None
            logger.info(f"[ACTION]---------->   Agent Action [{sender.name}] --> answer: {answer}")
            return ActionOutput.from_dict({
                "action_id": action_id or self.action_uid,
                "is_exe_success": True,
                "thoughts": action_input.thought,
                "action": self.name,
                "name": self.name,
                "state": Status.TODO.value,
                "action_input": action_input.dict,
                "content": answer.content if answer else "Not Have Answer！",
                "observations": answer.content if answer else "Not Have Answer！",
                "ask_user": ask_user,
                "ask_type": ask_type,
                "metrics": metrics,
            })

        except Exception as e:
            logger.exception(f"Agent Action Run Failed!{str(e)}")
            metrics.end_time_ms = time.time_ns() // 1_000_000
            return ActionOutput.from_dict({
                "action_id": self.action_uid,
                "is_exe_success": False,
                "thoughts": action_input.thought,
                "action": action_input.agent_name,
                "name": self.name,
                "state": Status.FAILED.value,
                "action_input": action_input.content,
                "content": f"Agent启动异常！{str(e)}",
                "metrics": metrics,
            })


class AgentStart(AgentAction, FunctionTool):
    name = "agent_start"
    """Terminate action.

    It is a special action to terminate the conversation, at same time, it can be a
    tool to return the final answer.
    """

    @classmethod
    def get_action_description(cls) -> str:
        return _AGENT_START_PROMPT

    @property
    def description(self):
        return self.get_action_description()

    @property
    def args(self):
        return {
            "agent_id": ToolParameter(
                type="string",
                name="agent_id",
                description="目标子Agent的唯一标识，必须为系统中已注册的Agent。",
                required=True
            ),
            "input": ToolParameter(
                type="string",
                name="input",
                description="需要完成的任务目标指令内容。",
                required=True
            ),
            "sync": ToolParameter(
                type="bool",
                name="input",
                description="分派任务是否需要等待结果返回再进行下一步(默认同步需要等待结果，如果后续步骤可以不依赖当前分派任务结果可以使用异步）。",
                required=False,
                default=True
            ),
            "background": ToolParameter(
                type="string",
                name="background",
                description="和目标任务相关的背景知识信息。",
                required=False
            ),
        }

    def execute(self, *args, **kwargs):
        raise RuntimeError("当前工具需要转AgentAction执行, 不能直接作为工具调用！")

    async def async_execute(self, *args, **kwargs):
        return self.execute(*args, **kwargs)

    @classmethod
    def parse_action(
        cls,
        tool_call: ToolCall,
        default_action: Optional["Action"] = None,
        resource: Optional["Resource"] = None,
        **kwargs,
    ) -> Optional["Action"]:
        """Parse the action from the message.

        If you want skip the action, return None.
        """
        if tool_call.name == cls.name:
            if not tool_call.args:
                raise ValueError("Agent转发任务异常，没有转发参数！")
            else:
                if not tool_call.args.get("agent_id"):
                    raise ValueError("没有可委派转发的AgentId信息！")
                if not tool_call.args.get("input"):
                    raise ValueError("没有给委派Agent指定任务目标！")
            extra_info = None
            if tool_call.args.get("background"):
                extra_info: Dict = {
                    "background": tool_call.args.get("background")
                }

            return cls(action_uid=tool_call.tool_call_id,
                       action_input=AgentActionInput(agent_name=tool_call.args.get("agent_id"),
                                                     content=tool_call.args.get("input"),
                                                     extra_info=extra_info))
        else:
            return None
