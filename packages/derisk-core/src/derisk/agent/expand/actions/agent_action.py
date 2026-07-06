import asyncio
import concurrent.futures
import json
import logging
import time
import uuid
import warnings
from datetime import datetime
from typing import Optional, Dict, Literal

from derisk.context.window import ContextWindow
from derisk.vis import SystemVisTag
from ... import GptsMemory, AgentContext, AgentResource, ConversableAgent, AgentMessage, AgentMemory
from ...core.action.base import ToolCall, Action, ActionOutput, AskUserType
from ...core.memory.gpts import GptsMessage
from ...core.reasoning.reasoning_action import AgentActionInput
from ...core.subagent_handle import MAX_SUBAGENT_DEPTH, SubagentDepthExceededError, SubAgentMode

from derisk.agent.resource import ToolParameter, FunctionTool
from derisk.agent.tools.context import ToolContext
from ...core.schema import Status, ActionInferenceMetrics

_AGENT_START_PROMPT = """\
代理(Agent)交互接口。用于使用其他代理(Agent)完成任务进入代理模式。
**注意事项:** * 指定的agent和你的上下文是隔离的，请传递准确、完整的任务描述。
**防御性原则**：在调用任何子 Agent 之前，必须严格评估该 Agent 的能力是否与当前任务目标**精确匹配**。如果收到的指令（如"查询某个监控表")在当前可用的子 Agent 工具集中没有直接对应的能力，**严禁**选择一个功能不相关的工具进行"尝试性"调用。此时，应将此情况作为发现记录在报告中，并重新评估计划，而不是执行错误的工具调用。
**参数说明**:
  - agent_id: 目标子 Agent 的唯一标识（必填，自模板 spawn 暂未实现）
  - input: 任务目标指令内容（必填）
  - mode: "sync"（默认，等待子 Agent 完成）或 "async"（后台运行，全完成后回调主 resume；单进程异步优先，分布式调度未来演进）
  - background: 相关背景知识（可选）
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
            agent_context: AgentContext = kwargs.get('agent_context')

            # 子 agent 深度守卫（早于 recipient lookup，fail-fast）
            parent_extra = (agent_context.extra or {}) if agent_context else {}
            parent_depth = parent_extra.get("subagent_depth", 0) or 0
            if parent_depth >= MAX_SUBAGENT_DEPTH:
                raise SubagentDepthExceededError(parent_depth, MAX_SUBAGENT_DEPTH)

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

            # 深度传播：把 parent_depth+1 写入 recipient.agent_context.extra
            if recipient.agent_context is not None:
                child_extra = recipient.agent_context.extra or {}
                child_extra["subagent_depth"] = parent_depth + 1
                recipient.agent_context.extra = child_extra

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

        except SubagentDepthExceededError:
            # 安全守卫违规不掩盖为普通 action 失败，向上抛
            raise
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


class SubAgent(AgentAction, FunctionTool):
    name = "agent_start"  # 工具名保留 agent_start 以兼容历史 vis 渲染（按 name 索引）；类名已迁移到 SubAgent，AgentStart 作 deprecated 别名
    """Sub-agent dispatch tool.

    Spawns or dispatches to a sub-agent. Supports sync mode (wait for result)
    and async mode (background, main resumes when all subagents done).

    Note: 自模板 spawn (agent_id=None → 用当前 agent 的 app_code) 与 async 模式的
    完整实现在 V1 架构治理 PR 2 中作为 API surface 落地，完整路径需要跨包
    (derisk-core ↔ derisk-serve GptAppResource) 协作，作为后续 PR 推进。
    当前 BAIZE 路径下：sync 模式按 V1 AgentAction 逻辑（dispatch to team member）
    工作；async 模式暂以 warning + 同步降级处理。
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
                description="[deprecated] 旧参数，等价于 mode='sync'。请优先使用 mode 参数。",
                required=False,
                default=True
            ),
            "mode": ToolParameter(
                type="string",
                name="mode",
                description='执行模式: "sync" (默认, 等待子 Agent 完成) 或 "async" (后台运行, 全完成后触发主 resume)。旧参数 sync=True 等价于 mode="sync"。',
                required=False,
                default="sync"
            ),
            "background": ToolParameter(
                type="string",
                name="background",
                description="和目标任务相关的背景知识信息。",
                required=False
            ),
        }

    def execute(self, *args, **kwargs):
        # V2 路径: 从 ToolContext 获取 app_resource（V2 dispatch 已在 PR 0 关闭，此处保留以兼容 V2 单元测试资产）
        context = kwargs.get("context")
        if isinstance(context, ToolContext):
            app_resource = context.get_resource("app_resource")
            if app_resource is not None:
                return self._execute_with_app_resource(app_resource, args, kwargs)
            return f"sub_agent: no app_resource in context, args={args}"
        # BAIZE 回退
        raise RuntimeError("当前工具需要转AgentAction执行, 不能直接作为工具调用！")

    async def async_execute(self, *args, **kwargs):
        # V2 路径: 从 ToolContext 获取 app_resource
        context = kwargs.get("context")
        if isinstance(context, ToolContext):
            app_resource = context.get_resource("app_resource")
            if app_resource is not None:
                return await self._async_execute_with_app_resource(app_resource, args, kwargs)
            return self.execute(*args, **kwargs)
        return self.execute(*args, **kwargs)

    def _execute_with_app_resource(self, app_resource, args, kwargs):
        """V2 路径: 使用 app_resource 执行 sub_agent。"""
        tool_input = args[0] if args else kwargs
        user_input = tool_input.get("input", "")

        def _run():
            return asyncio.run(app_resource.async_execute(user_input=user_input))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(_run).result()

        return str(result)

    async def _async_execute_with_app_resource(self, app_resource, args, kwargs):
        """V2 异步路径: 使用 app_resource 执行 sub_agent。"""
        tool_input = args[0] if args else kwargs
        user_input = tool_input.get("input", "")
        result = await app_resource.async_execute(user_input=user_input)
        return str(result)

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
        # 兼容未来重命名：当前 cls.name == "agent_start"，未来切到 "sub_agent" 时仍接受旧名
        accepted_names = {cls.name, "sub_agent"}
        if tool_call.name in accepted_names:
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

            # 解析 mode：优先 mode 参数，回退到 deprecated sync 参数
            mode = tool_call.args.get("mode")
            if not mode:
                sync_flag = tool_call.args.get("sync")
                if sync_flag is False:
                    mode = "async"
                else:
                    mode = "sync"

            return cls(action_uid=tool_call.tool_call_id,
                       action_input=AgentActionInput(agent_name=tool_call.args.get("agent_id"),
                                                     content=tool_call.args.get("input"),
                                                     extra_info=extra_info,
                                                     mode=mode))
        else:
            return None

    async def run(
        self,
        ai_message: str = None,
        resource: Optional[AgentResource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        **kwargs,
    ) -> ActionOutput:
        """Dispatch to sub-agent. Sync mode delegates to V1 team dispatch;
        async mode spawns a new conversation in the background and returns immediately.

        Async mode requires derisk_serve SubagentCoordinator to be registered globally
        (via ``set_subagent_coordinator``) and ``GptAppResource`` to be importable. If
        either is unavailable, async degrades to sync with a warning.
        """
        action_input = self.action_input or AgentActionInput.model_validate_json(
            json_data=ai_message
        )
        mode_str = (action_input.mode or "sync").lower()
        if mode_str != "async":
            return await super().run(
                ai_message=ai_message,
                resource=resource,
                rely_action_out=rely_action_out,
                need_vis_render=need_vis_render,
                **kwargs,
            )

        # ---- async branch ----
        metrics = ActionInferenceMetrics()
        metrics.start_time_ms = time.time_ns() // 1_000_000
        try:
            sender: ConversableAgent = kwargs["agent"]
            agent_context: AgentContext = kwargs.get("agent_context")
            main_conv_id = agent_context.conv_id if agent_context else None
            if not main_conv_id:
                logger.warning(
                    "[SubAgent.async] missing main_conv_id; degrading to sync"
                )
                return await super().run(
                    ai_message=ai_message,
                    resource=resource,
                    rely_action_out=rely_action_out,
                    need_vis_render=need_vis_render,
                    **kwargs,
                )

            # 拿全局 coordinator（derisk_serve 启动时注册）
            try:
                from derisk_serve.agent.subagent_coordinator import (
                    get_subagent_coordinator,
                )
            except ImportError:
                get_subagent_coordinator = None  # type: ignore[assignment]
            coordinator = get_subagent_coordinator() if get_subagent_coordinator else None
            if coordinator is None:
                logger.warning(
                    "[SubAgent.async] no global coordinator registered; degrading to sync"
                )
                return await super().run(
                    ai_message=ai_message,
                    resource=resource,
                    rely_action_out=rely_action_out,
                    need_vis_render=need_vis_render,
                    **kwargs,
                )

            # 构造 GptAppResource，用 action_input.agent_name 当 app_code
            try:
                from derisk_serve.agent.resource.app import GptAppResource
            except ImportError as ie:
                logger.warning(
                    f"[SubAgent.async] derisk_serve not importable ({ie}); degrading to sync"
                )
                return await super().run(
                    ai_message=ai_message,
                    resource=resource,
                    rely_action_out=rely_action_out,
                    need_vis_render=need_vis_render,
                    **kwargs,
                )
            app_resource = GptAppResource(
                name=action_input.agent_name,
                app_code=action_input.agent_name,
            )

            # 深度守卫（与 sync 路径一致）
            parent_extra = (agent_context.extra or {}) if agent_context else {}
            parent_depth = parent_extra.get("subagent_depth", 0) or 0
            if parent_depth >= MAX_SUBAGENT_DEPTH:
                raise SubagentDepthExceededError(parent_depth, MAX_SUBAGENT_DEPTH)

            # 新 sub_conv_id
            sub_conv_id = str(uuid.uuid4())

            # 注册到 coordinator（持久化 pending_subagents）
            await coordinator.register_subagent(
                main_conv_id=main_conv_id,
                sub_conv_id=sub_conv_id,
                mode=SubAgentMode.ASYNC,
            )

            # 后台跑子 agent，不 await
            asyncio.create_task(
                self._run_subagent_background(
                    app_resource=app_resource,
                    user_input=action_input.content,
                    sender=sender,
                    sub_conv_id=sub_conv_id,
                    main_conv_id=main_conv_id,
                    parent_depth=parent_depth,
                )
            )

            metrics.end_time_ms = time.time_ns() // 1_000_000
            logger.info(
                f"[SubAgent.async] spawned sub_conv={sub_conv_id} for main={main_conv_id}"
            )
            return ActionOutput.from_dict({
                "action_id": self.action_uid,
                "is_exe_success": True,
                "thoughts": action_input.thought,
                "action": self.name,
                "name": self.name,
                "state": Status.RUNNING.value,
                "action_input": action_input.dict,
                "content": (
                    f"子 Agent 已后台启动 (sub_conv_id={sub_conv_id})，"
                    f"主会话将在所有子 Agent 完成后自动 resume。"
                ),
                "observations": (
                    f"async subagent spawned: sub_conv_id={sub_conv_id}"
                ),
                "metrics": metrics,
            })

        except SubagentDepthExceededError:
            raise
        except Exception as e:
            logger.exception(f"[SubAgent.async] failed: {e}")
            metrics.end_time_ms = time.time_ns() // 1_000_000
            return ActionOutput.from_dict({
                "action_id": self.action_uid,
                "is_exe_success": False,
                "thoughts": action_input.thought,
                "action": action_input.agent_name,
                "name": self.name,
                "state": Status.FAILED.value,
                "action_input": action_input.content,
                "content": f"async SubAgent 启动异常！{str(e)}",
                "metrics": metrics,
            })

    async def _run_subagent_background(
        self,
        app_resource,
        user_input: str,
        sender: ConversableAgent,
        sub_conv_id: str,
        main_conv_id: str,
        parent_depth: int,
    ) -> None:
        """后台跑子 agent，完成后回调 coordinator.on_subagent_done/failed。

        Runs in a fire-and-forget asyncio task. Any exception is routed to the
        coordinator as a sub-agent failure — never raised to the caller.
        """
        try:
            # 深度传播：parent_depth → child AgentContext.extra["subagent_depth"] = parent_depth+1
            answer = await app_resource._start_app(
                user_input=user_input,
                sender=sender,
                conv_uid=sub_conv_id,
                parent_depth=parent_depth,
            )
            content = getattr(answer, "content", None) or ""
            try:
                from derisk_serve.agent.subagent_coordinator import (
                    get_subagent_coordinator,
                )
                coordinator = get_subagent_coordinator()
                if coordinator is not None:
                    await coordinator.on_subagent_done(
                        main_conv_id=main_conv_id,
                        sub_conv_id=sub_conv_id,
                        result=content,
                    )
            except Exception as cb_err:
                logger.warning(
                    f"[SubAgent.async] on_done callback failed for sub={sub_conv_id}: {cb_err}"
                )
        except Exception as run_err:
            logger.exception(
                f"[SubAgent.async] background run failed for sub={sub_conv_id}: {run_err}"
            )
            try:
                from derisk_serve.agent.subagent_coordinator import (
                    get_subagent_coordinator,
                )
                coordinator = get_subagent_coordinator()
                if coordinator is not None:
                    await coordinator.on_subagent_failed(
                        main_conv_id=main_conv_id,
                        sub_conv_id=sub_conv_id,
                        error=str(run_err),
                    )
            except Exception as cb_err:
                logger.warning(
                    f"[SubAgent.async] on_failed callback failed for sub={sub_conv_id}: {cb_err}"
                )


# Deprecated alias — 1 个版本后删除
AgentStart = SubAgent
