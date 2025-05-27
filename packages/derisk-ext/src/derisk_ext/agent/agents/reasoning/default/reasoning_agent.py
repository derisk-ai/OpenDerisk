"""Plugin Assistant Agent."""
import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import Optional, List, Any

from derisk.agent import (
    AgentMessage,
    Agent,
    ActionOutput,
    Resource,
    ResourceType,
    BlankAction, Action, )
from derisk.agent.core.base_team import ManagerAgent
from derisk.agent.core.profile import DynConfig, ProfileConfig
from derisk.agent.core.reasoning.reasoning_action import AgentAction, KnowledgeRetrieveAction, parse_action_reports, UserConfirmAction
from derisk.agent.core.reasoning.reasoning_engine import REASONING_LOGGER as LOGGER, ReasoningEngineOutput
from derisk.agent.core.reasoning.reasoning_engine import (
    ReasoningEngine,
    DEFAULT_REASONING_PLANNER_NAME,
)
from derisk.agent.core.schema import Status
from derisk.agent.expand.actions.tool_action import ToolAction, ToolInput
from derisk.agent.resource import ResourcePack, ToolPack, BaseTool
from derisk.agent.resource.reasoning_engine import ReasoningEngineResource
from derisk.util.json_utils import serialize
from derisk.util.tracer import root_tracer
from derisk.vis import SystemVisTag, Vis
from derisk.vis.schema import VisTextContent, VisTaskContent, StepInfo, VisPlansContent, VisStepContent, VisSelectContent
from derisk_ext.agent.agents.reasoning.default.ability import Ability

_ABILITY_RESOURCE_TYPES = [ResourceType.Tool, ResourceType.KnowledgePack]


class ReasoningAgent(ManagerAgent):
    """Reasoning Agent."""

    profile: ProfileConfig = ProfileConfig(
        name=DynConfig(
            "ReasoningPlanner",
            category="agent",
            key="derisk_agent_expand_plugin_assistant_agent_name",
        ),
        role=DynConfig(
            "ReasoningPlanner",
            category="agent",
            key="derisk_agent_expand_plugin_assistant_agent_role",
        ),
    )

    def __init__(self, **kwargs):
        """Create a new instance of ReasoningAgent."""
        super().__init__(**kwargs)
        self._init_actions([BlankAction])

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
    ) -> Optional[AgentMessage]:
        """Generate a reply based on the received messages."""
        conv_id = self.not_null_agent_context.conv_id
        trace_id = self.not_null_agent_context.trace_id
        received_action_id = (received_message.goal_id if received_message.goal_id  # 上游传入的action_id优先级更高
                              else conv_id.split(sep="_")[-1])  # 否则取当前session下的第几轮会话

        LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][推理流程:开始] --------> [{self.name}]"
                    f"received_message_id=[{received_message.message_id}], "
                    f"sender=[{sender.role}][{sender.name}], "
                    f"app_code[{self.agent_context.gpts_app_code}], "
                    f"content=[{received_message.content}]"
                    )
        agent_success = True
        agent_ms = _current_ms()
        try:
            with root_tracer.start_span(
                "reasoning.agent.generate_reply",
                metadata={
                    "sender": sender.name,
                    "recipient": self.name,
                    "received_message": json.dumps(received_message.to_dict()),
                    "conv_id": conv_id
                },
            ):
                done = False
                step_counter = 0  # 第几次循环
                retry_counter = 0  # 模型连续重试了几次
                max_retry_counter = 1#0
                while (not done) and (step_counter < 100) and (retry_counter < max_retry_counter):
                    retry_ms = _current_ms()
                    step_id = f"{received_action_id}-{step_counter}"
                    engine_cost_ms = 0
                    action_cost_ms = 0
                    reply_cost_ms = 0
                    step_success = True
                    action_size = 0

                    # ================================↓↓↓ 初始化current_step_message ↓↓↓================================ #
                    #
                    # 必须先初始化current_step_message，以便通过其message_id串接后续流程，包括但不限于:
                    # * 模型调用: 流式输出需要message_id以确认更新前端哪个卡片
                    # * Action执行(尤其是Tool)，用于后续Action结果更新显示
                    #
                    # current_step_message可能有3种用途:
                    #
                    #  |         场景        |     消息receiver    |
                    #  |        :---:       |        :---:        |
                    #  | 需要下游Agent执行任务 |      (每个下游会再new一条消息)      |
                    #  | 需要执行Tool/检索知识 |      Agent自己      |
                    #  |     任务有结论了     |   上游Agent(或User)  |
                    #
                    rounds = await self.memory.gpts_memory.next_message_rounds(self.agent_context.conv_id)
                    current_step_message = await self.init_reply_message(received_message=received_message, rounds=rounds)
                    current_step_message.content = None
                    current_step_message.action_report = None
                    current_step_message_id = current_step_message.message_id
                    # ================================↑↑↑ 初始化current_step_message ↑↑↑================================ #

                    with root_tracer.start_span(
                        "reasoning.agent.reasoning",
                        metadata={
                            "conv_id": conv_id,
                            "received_message_id": received_message.message_id,
                            "current_step_message_id": current_step_message_id,
                            "tl_app_code": self.agent_context.gpts_app_code,
                            "agent_name": self.name,
                            "step_counter": step_counter,
                            "retry_counter": retry_counter,
                        },
                    ) as span_reasoning:
                        try:
                            output: Optional[ReasoningEngineOutput] = None  # 调用推理引擎抛异常可能导致output未定义 提前初始化为None
                            engine_error_msg = "推理引擎异常退出"
                            try:
                                LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][调用推理引擎:开始] ----> "
                                            f"agent:[{self.name}], engine:[{self.reasoning_engine.name}]"
                                            f"[step:{step_counter},retry:{retry_counter}],"
                                            f"message:[{current_step_message_id}],rounds"[current_step_message.rounds])
                                # ================================↓↓↓ 调用推理引擎 ↓↓↓================================ #
                                output = await self.reasoning_engine.invoke(
                                    agent=self,
                                    agent_context=self.agent_context,
                                    received_message=received_message,
                                    current_step_message=current_step_message,
                                    step_id=step_id,
                                )
                                # ================================↑↑↑ 调用推理引擎 ↑↑↑================================ #

                                done = done or output.done
                                current_step_message.model_name = output.model_name
                                current_step_message.thinking = output.model_thinking
                                current_step_message.content = output.model_content
                                current_step_message.user_prompt = output.user_prompt
                                current_step_message.system_prompt = output.system_prompt

                                retry_counter = 0  # 引擎调用成功 重置计数器
                                engine_error_msg = None
                                span_reasoning.metadata.update(_format_engine_output_span(output))
                            except Exception as e:
                                LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][调用推理引擎:异常] agent:[{self.name}], engine:[{self.reasoning_engine.name}], except:[{repr(e)}]")
                                engine_error_msg = repr(e)
                                retry_counter += 1
                                raise ReasoningEngineException(repr(e))
                            finally:
                                engine_cost_ms = _current_ms() - retry_ms
                                LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][调用推理引擎:结束] <---- "
                                            f"agent:[{self.name}], engine:[{self.reasoning_engine.name}], cost_ms:[{engine_cost_ms}], "
                                            f"output:[{output}]")
                                LOGGER.info(f"[{trace_id}][{conv_id}]"
                                            f"[DIGEST][ENGINE]"
                                            f"agent_name=[{self.name.replace('[', '(').replace(']', ')')}],"  # 监控采集配的是左起'['、右至']'，统一替换以兼容
                                            f"reasoning_engine_name=[{self.reasoning_engine.name}],"
                                            f"received_message_id=[{received_message.message_id}],"
                                            f"current_step_message_id=[{current_step_message_id}],"
                                            f"step_counter=[{step_counter}],"  # 第几个step(轮次)
                                            f"retry_counter=[{retry_counter}],"  # 模型连续重试了几次
                                            f"engine_cost_ms=[{engine_cost_ms}],"  # 推理引擎耗时
                                            f"engine_success=[{output and not engine_error_msg}],"  # 推理引擎是否成功
                                            f"engine_error_msg=[{engine_error_msg.replace('[', '(').replace(']', ')') if engine_error_msg else None}],"  # 推理引擎异常描述
                                            )
                            if self.need_user_confirm(output=output, sender=sender, step_counter=step_counter):
                                await self.send_confirm_message(output=output, current_step_message=current_step_message, received_message=received_message, received_action_id=received_action_id)
                                return None

                            # 流程向上游回消息 需要写DB 上游读DB后再Plan
                            if output.answer and not output.actions:
                                LOGGER.info(f"[{trace_id}][{conv_id}][AGENT]开始组装回复消息 agent:[{self.name}], reply_message[{current_step_message.message_id}]")
                                answer_ms = _current_ms()
                                current_step_message.action_report = ActionOutput.from_dict({
                                    "view": await self._render_protocol(vis_tag=SystemVisTag.VisText).display(content=VisTextContent(
                                        markdown=output.answer, type="all", uid=current_step_message_id + "_answer", message_id=current_step_message_id
                                    ).to_dict()),
                                    "model_view": output.answer,
                                    "action_id": received_action_id + "-answer",
                                    "extra": received_message.context | {"title": "结论"},
                                    "content": output.answer,
                                    "action": self.name,
                                    "action_name": AgentAction().name,
                                    "action_input": received_message.content,
                                })
                                LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][消息回复:开始] ----> "
                                            f"agent:[{self.name}], reply_message[{current_step_message.message_id}], to [{sender.name}]")
                                # ================================↓↓↓ 消息回复 ↓↓↓================================ #
                                await self.send(message=current_step_message, recipient=sender, request_reply=False)
                                # ================================↑↑↑ 消息回复 ↑↑↑================================ #

                                reply_cost_ms = _current_ms() - answer_ms
                                LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][消息回复:完成] <---- "
                                            f"agent:[{self.name}], reply_message[{current_step_message.message_id}], to [{sender.name}]")
                                if output.actions:
                                    LOGGER.info(f"[{trace_id}][{conv_id}][AGENT]模型幻觉，既有结论又有action，size={len(output.actions)}。"
                                                f"agent:[{self.name}], reply_message[{current_step_message.message_id}], to [{sender.name}]")

                                await self._push_summary_action(conv_id, current_step_message, output, sender, trace_id)
                                # return

                            # 流程向前推进(可能给下游Agent发消息/可能自己执行Tool)
                            if output.actions:
                                # if len(output.actions) != 1:
                                #     output.actions = [output.actions[0]]
                                action_size = len(output.actions)
                                action_ms = _current_ms()
                                LOGGER.info(f"[{trace_id}][{conv_id}][AGENT]actions size:{action_size}")

                                # 先初始化action需要的数据
                                self._init_actions_before(actions=output.actions)
                                current_step_message.action_report = ActionOutput(content="", action_id=step_id, extra={"title": output.plans_brief_description})
                                action_reports: list[ActionOutput] = [
                                    ActionOutput(content="", action="", action_name=action.name, action_input=action.action_input.json(),
                                                 action_id=format_action_id(received_action_id=received_action_id, step_counter=step_counter, action_idx=idx), )
                                    for idx, action in enumerate(output.actions)]

                                # 动作执行前先展示出来
                                reason_view = await self._render_markdown_view(output.action_reason, uid=current_step_message_id + "_reason", message_id=current_step_message_id) if output.action_reason else ""
                                # human_view = await self._format_view(reason_view=reason_view,
                                #                                      action_and_reports=[(output.actions[i], action_reports[i]) for i in range(len(output.actions))],
                                #                                      message_id=current_step_message.message_id)
                                # _update_action_report_view(action_report=current_step_message.action_report, human_view=human_view, model_view=None)
                                await self._update_step_action_report(
                                    step_action_report=current_step_message.action_report,
                                    sub_action_and_reports=[(output.actions[i], action_reports[i]) for i in range(len(output.actions))],
                                    message_id=current_step_message.message_id,
                                    reason_view=reason_view,
                                )
                                LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][Action前先发消息] ----> agent:[{self.name}]")
                                await self._push_action_message_with_update(message=current_step_message)

                                for idx, action in enumerate(output.actions):
                                    with root_tracer.start_span(
                                        "reasoning.agent.action.run",
                                        metadata={"action": action.name},
                                    ):
                                        action_item_ms = _current_ms()
                                        action_success = True
                                        action_id = action_reports[idx].action_id
                                        try:
                                            LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][执行Action:开始] ----> "
                                                        f"agent:[{self.name}], step:{step_counter}, retry:{retry_counter}, Action:[{action.name}][{idx}]/[{action_size}]")
                                            # ================================↓↓↓ 执行Action ↓↓↓================================ #
                                            action_reports[idx]: Optional[ActionOutput] = await action.run(
                                                agent=self,
                                                message_id=current_step_message.message_id,
                                                resource=self.resource,
                                                message=current_step_message,
                                                action_id=action_id,
                                            )
                                            # ================================↑↑↑ 执行Action ↑↑↑================================ #
                                            action_success = action_reports[idx].is_exe_success
                                            span_reasoning.metadata["actions"] = span_reasoning.metadata["actions"] if "actions" in span_reasoning.metadata else []
                                            span_reasoning.metadata["actions"].append({
                                                "name": action.name,
                                                "input": action.action_input.dict(),
                                                "is_exe_success": action_reports[idx].is_exe_success,
                                                "action_output_content": action_reports[idx].content,
                                                "cost_ms": _current_ms() - action_item_ms
                                            })

                                            # 动作执行后 更新message并展示/落表
                                            action_reports[idx].action_id = action_id
                                            action_reports[idx].action = action_reports[idx].action or action.name
                                            action_reports[idx].action_input = action_reports[idx].action_input or action.action_input.json()
                                            action_reports[idx].model_view = _format_action_model_view(action=action, action_output=action_reports[idx])
                                            action_reports[idx].action_intention = action.intention
                                            action_reports[idx].action_reason = action.reason
                                            # human_view = await self._format_view(reason_view=reason_view,
                                            #                                      action_and_reports=[(output.actions[i], action_reports[i]) for i in range(len(output.actions))],
                                            #                                      message_id=current_step_message.message_id)
                                            # _update_action_report_view(action_report=current_step_message.action_report, human_view=human_view, model_view=model_view)
                                            await self._update_step_action_report(
                                                step_action_report=current_step_message.action_report,
                                                sub_action_and_reports=[(output.actions[i], action_reports[i]) for i in range(len(output.actions))],
                                                message_id=current_step_message.message_id,
                                                reason_view=reason_view,
                                            )
                                            LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][Action 已更新] <---- agent:[{self.name}]")
                                            await self._push_action_message_with_update(message=current_step_message)
                                        except Exception as e:
                                            action_success = False
                                            LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][执行Action:异常] <---- "
                                                        f"agent:[{self.name}], Action:[{action.name}][{idx}]/[{action_size}], except:[{repr(e)}]")
                                            raise ReasoningActionException(repr(e))
                                        finally:
                                            LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][执行Action:结束] <---- "
                                                        f"agent:[{self.name}], step:{step_counter}, retry:{retry_counter}, Action:[{action.name}][{idx}]/[{action_size}], "
                                                        f"action_id:[{action_id}], success:[{action_success}], content:[{action_reports[idx].content if action_reports[idx] else None}]")
                                            LOGGER.info(f"[{trace_id}][{conv_id}]"
                                                        f"[DIGEST][ACTION]"
                                                        f"agent_name=[{self.name.replace('[', '(').replace(']', ')')}],"  # 监控采集配的是左起'['、右至']'，统一替换以兼容
                                                        f"received_message_id=[{received_message.message_id}],"
                                                        f"current_step_message_id=[{current_step_message_id}],"
                                                        f"reasoning_engine_name=[{self.reasoning_engine.name}],"
                                                        f"step_counter=[{step_counter}],"  # 第几个step(轮次)
                                                        f"retry_counter=[{retry_counter}],"  # 模型连续重试了几次
                                                        f"action_size=[{action_size}],"  # 共几个action
                                                        f"current_action_index=[{idx}],"  # 当前是第几个action
                                                        f"action_ms=[{_current_ms() - action_item_ms}],"  # 本action执行耗时
                                                        f"step_action_ms=[{_current_ms() - action_ms}],"  # 本轮action执行总耗时
                                                        f"action_success=[{action_success}],"  # 本action是否成功
                                                        f"action_name=[{action.name}],"  # action name
                                                        f"action_id=[{action_id}],"
                                                        )

                                action_cost_ms = _current_ms() - action_ms
                                LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][所有Action均已执行完成] <---- agent:[{self.name}], step:[{step_counter}]")

                            # # 动作执行完后更新任务关系
                            # # 第一个step挂在received_message下 其他step挂在前一个step下
                            # # 不能在actions执行完前更新关系的原因: AgentAction会让小弟Agent生成多条消息，TL Agent 后续的消息应该挂在所有小弟消息的下面
                            # parent_message_ids = [received_message.message_id] if not last_message_id else await _find_all_leaf_message_id(agent=self, conv_id=conv_id, root_message_id=last_message_id)
                            # await _store_message_relation(agent=self, conv_id=conv_id, child_message=current_step_message, parent_message_ids=parent_message_ids)
                            # LOGGER.info(f"[{trace_id}][{conv_id}][AGENT]任务关系更新完成 agent:[{self.name}], current_step_message_id[{current_step_message_id}], parent_message_ids[{parent_message_ids}]")

                        except Exception as e:
                            LOGGER.exception(f"[{trace_id}]{conv_id}[AGENT]step执行失败 "
                                             f"step_counter=[{step_counter}],"  # 当前第几个step(轮次)
                                             f"retry_counter=[{retry_counter}],"  # 模型连续重试了几次
                                             f"received_message_id:[{received_message.message_id}],"
                                             f"reply_message_id:[{current_step_message_id}],"
                                             f"got exception:[{repr(e)}]")

                            step_success = False
                            agent_success = False
                            should_retry = isinstance(e, ReasoningEngineException) and retry_counter < max_retry_counter
                            error_catalog = "任务拆解" if isinstance(e, ReasoningEngineException) else "Action执行" if isinstance(e, ReasoningActionException) else "未知"
                            error_content = error_catalog + "失败: " + repr(e) + (f"\n\n准备发起第{retry_counter}次重试" if should_retry else "")
                            # _must_fill_message_view(message=current_step_message,
                            #                         action_output=None,
                            #                         model_view=error_content,
                            #                         view=await self._render_markdown_view(error_content))
                            current_step_message.action_report = ActionOutput.from_dict({
                                "view": await self._render_markdown_view(error_content, uid=current_step_message_id + "_err", message_id=current_step_message_id),
                                "model_view": error_content,
                                "action_id": step_id,
                                "extra": {"title": "执行异常"},
                                "content": error_content,
                            })
                            LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][step失败回消息] <---- "
                                        f"agent:[{self.name}], reply_message[{current_step_message.message_id}], to [{sender.name}]")
                            await self._push_action_message_with_update(message=current_step_message)
                            if should_retry:
                                await asyncio.sleep(3)
                        finally:
                            span_reasoning.metadata["step_success"] = step_success
                            LOGGER.info(f"[{trace_id}][{conv_id}]"
                                        f"[DIGEST][STEP]"
                                        f"agent_name=[{self.name.replace('[', '(').replace(']', ')')}],"  # 监控采集配的是左起'['、右至']'，统一替换以兼容
                                        f"received_message_id=[{received_message.message_id}],"
                                        f"current_step_message_id=[{current_step_message_id}],"
                                        f"reasoning_engine_name=[{self.reasoning_engine.name}],"
                                        f"step_counter=[{step_counter}],"  # 第几个step(轮次)
                                        f"retry_counter=[{retry_counter}],"  # 模型连续重试了几次
                                        f"step_success=[{step_success}],"  # 本次step循环是否成功
                                        f"current_step_ms=[{_current_ms() - retry_ms}],"  # 本次step循环耗时
                                        f"engine_cost_ms=[{engine_cost_ms}],"  # 引擎调用耗时
                                        f"action_cost_ms=[{action_cost_ms}],"  # action执行耗时
                                        f"reply_cost_ms=[{reply_cost_ms}],"  # 消息回复耗时
                                        f"done=[{done}],"  # 是否结束循环
                                        f"action_size=[{action_size}],"  # action size
                                        f"has_answer=[{True if output and output.answer else False}]"  # 是否有结论
                                        )
                            # last_message_id = current_step_message.message_id
                            step_counter += 1
        except BaseException as e:
            LOGGER.exception(f"[{trace_id}]{conv_id}[AGENT]Agent任务失败 "
                             f"agent:[{self.name}],"
                             f"received_message_id:[{received_message.message_id}],"
                             f"got exception:[{repr(e)}]")
            raise
        finally:
            LOGGER.info(f"[{trace_id}][{conv_id}]"
                        f"[DIGEST][AGENT]"
                        f"agent_name=[{self.name.replace('[', '(').replace(']', ')')}],"  # 监控采集配的是左起'['、右至']'，统一替换以兼容
                        f"received_message=[{received_message.message_id}],"
                        f"reasoning_engine_name=[{self.reasoning_engine.name}],"
                        f"agent_success=[{agent_success}],"  # 是否成功
                        f"cost_ms=[{_current_ms() - agent_ms}],"  # 耗时
                        f"sender=[{sender.name.replace('[', '(').replace(']', ')')}],"  # 监控采集配的是左起'['、右至']'，统一替换以兼容
                        )
            LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][推理流程:结束] <-------- [{self.name}]"
                        f"received_message_id=[{received_message.message_id}]")

    @property
    def reasoning_engine(self) -> Optional[ReasoningEngine]:
        def _default_reasoning_engine():
            return ReasoningEngine.get_reasoning_engine(DEFAULT_REASONING_PLANNER_NAME)

        def _transfer(resource: Resource) -> Optional[ReasoningEngine]:
            return (
                None
                if not resource
                else ReasoningEngine.get_reasoning_engine(resource.name)
                if isinstance(
                    resource, ReasoningEngineResource
                )  # TODO 若resource.name非法导致取出的reasoning_engine为空怎么办
                else next(
                    (
                        _engine
                        for sub_resource in resource.sub_resources
                        if (_engine := _transfer(sub_resource))
                    ),
                    None,
                )
                if isinstance(resource, ResourcePack)
                else None
            )

        return _transfer(self.resource) or _default_reasoning_engine()

    @property
    def ability_resources(self) -> list[Resource]:
        def _unpack(resource: Resource) -> Optional[list[Resource]]:
            if not resource:
                return []

            elif resource.type() in _ABILITY_RESOURCE_TYPES:
                return [resource]

            elif isinstance(resource, ResourcePack) and resource.sub_resources:
                result = []
                for r in resource.sub_resources:
                    if r.type() in _ABILITY_RESOURCE_TYPES:
                        result.append(r)
                    elif isinstance(r, ResourcePack):
                        result.extend(_unpack(r))
                return result

            return []

        return _unpack(self.resource)

    @property
    def abilities(self) -> list[Ability]:
        result = []
        result.extend([
            ability
            for agent in self.agents
            if (ability := Ability.by(agent)) and agent.name != self.name
        ])
        result.extend([
            ability
            for resource in self.ability_resources
            if (ability := Ability.by(resource))
        ])
        return result

    def _render_protocol(self, vis_tag: SystemVisTag) -> Vis:
        return self.memory.gpts_memory.vis_converter.vis_inst(vis_tag.value)

    async def _render_markdown_view(self, text: str, uid: str, message_id: Optional[str] = None) -> str:
        return self._render_protocol(vis_tag=SystemVisTag.VisText).sync_display(content=VisTextContent(
            markdown=text, type="all", uid=uid, message_id=message_id
        ).to_dict())

    async def _render_action_view(self, action_and_reports: list[tuple[Action, ActionOutput]], message_id: str) -> str:
        # AgentAction放前面 统一放在VisPlansContent里
        agent_action_and_reports = [(action, report) for (action, report) in action_and_reports if isinstance(action, AgentAction)]
        agent_actions_view = await self._render_protocol(vis_tag=SystemVisTag.VisPlans).display(content=VisPlansContent(
            uid=message_id + "_action_agent",
            type="all",
            message_id=message_id + "_action_agent",
            tasks=[await _format_vis_content(action=action, output=report) for (action, report) in agent_action_and_reports],
        ).to_dict()) if agent_action_and_reports else None

        # 其他Action(Tool/RAG)放后面 统一放在VisStepContent里
        other_action_views = []
        for idx, (action, report) in enumerate(action_and_reports):
            if isinstance(action, AgentAction):
                continue
            step_content: StepInfo = await _format_vis_content(action=action, output=report)
            if not step_content:
                continue

            other_action_views.append(await self._render_protocol(vis_tag=SystemVisTag.VisTool).display(content=VisStepContent(
                uid=message_id + "_action_" + str(idx),
                message_id=message_id + "_action_" + str(idx),
                type="all",
                status=step_content.status,
                tool_name=step_content.tool_name,
                tool_args=step_content.tool_args,
                tool_result=step_content.tool_result,
            ).to_dict()))

        return "\n".join([view for view in [agent_actions_view] + other_action_views if view])

    async def _render_confirm_view(self, output: ReasoningEngineOutput, message_id: str) -> str:
        assert output and output.actions is not None and len(output.actions) > 0, "模型未输出Action，无法供用户确认"

        items = []

        items.append(await self._render_markdown_view(text=output.action_reason, uid=uuid.uuid4().hex) if output.action_reason else None)
        for idx, action in enumerate(output.actions):
            confirm_view = await self._render_protocol(vis_tag=SystemVisTag.VisSelect).display(content=VisSelectContent(
                uid=message_id + "_action_" + str(idx),
                message_id=message_id + "_action_" + str(idx),
                type="all",
                # markdown=action.action_input,
                # confirm_message=action.action_input,
                markdown="测试测试-执行xx动作",
                confirm_message="确认执行xx动作",
                extra={},
            ).to_dict())
            items.append(confirm_view)

        return "\n".join([item for item in items if item])

    async def _format_view(self, reason_view: str, action_and_reports: list[tuple[Action, ActionOutput]], message_id: str) -> str:
        # 页面显示给人看的信息包含两部分：1)上面是一段描述(可能为空)，介绍要执行这些动作的原因; 2)下面是执行的具体动作
        return ((reason_view + "\n") if reason_view else "") + (await self._render_action_view(action_and_reports=action_and_reports, message_id=message_id))

    async def _update_step_action_report(self, step_action_report: ActionOutput, sub_action_and_reports: list[tuple[Action, ActionOutput]], message_id: str, reason_view: str = None) -> None:
        step_action_report.content = json.dumps([action_report.to_dict() for action, action_report in sub_action_and_reports], ensure_ascii=False)
        step_action_report.view = await self._format_view(reason_view=reason_view, action_and_reports=sub_action_and_reports, message_id=message_id)

    async def _push_action_message_with_update(self, message: AgentMessage) -> None:
        await self.memory.gpts_memory.append_message(conv_id=self.agent_context.conv_id, message=message.to_gpts_message(sender=self, role=None, receiver=self))
        LOGGER.info("_push_action_message_with_update, view: " + message.action_report.view)

    def _init_actions_before(self, actions: list[Action]):
        for action in actions:
            action.init_resource(self.resource) if action.resource_need else None
            action.init_action(render_protocol=self.memory.gpts_memory.vis_converter)

    async def _push_summary_action(self, conv_id, current_step_message, output, sender, trace_id):
        # 总结信息里面的引用摘要
        summary_actions = await self._get_summary_action(conv_id, output, trace_id)
        if len(summary_actions) > 0:
            LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][总结更新:开始] ----> "
                        f"agent:[{self.name}], reply_message[{current_step_message.message_id}], to [{sender.name}]")
            actions = []
            for idx, action_output in enumerate(summary_actions):
                if action_output is None:
                    continue
                action_input: Optional[ToolInput] = ToolInput(tool_name=action_output.action, thought='thought')
                action_input.args = action_output.action_input
                action: Optional[ToolAction] = ToolAction()
                action.action_input = action_input
                actions.append(action)
            await self._update_step_action_report(
                step_action_report=current_step_message.action_report,
                sub_action_and_reports=[(actions[i], summary_actions[i]) for i in range(len(summary_actions))],
                message_id=current_step_message.message_id,
                reason_view=await self._render_protocol(vis_tag=SystemVisTag.VisText).display(content=VisTextContent(
                    markdown=output.answer, type="all", uid=current_step_message.message_id + "_answer", message_id=current_step_message.message_id
                ).to_dict()),
            )
            await self._push_action_message_with_update(message=current_step_message)
            LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][总结更新:完成] ----> "
                        f"agent:[{self.name}], reply_message[{current_step_message.message_id}], to [{sender.name}]")

    async def _get_summary_action(self, conv_id, output, trace_id):
        summary_actions = []
        if "<message_id>" in output.answer:
            try:
                LOGGER.info(f"[{trace_id}][{conv_id}][AGENT]_get_summary_action agent:[{self.name}], {output.answer}")
                # 使用正则表达式提取<message_id>并移除相关内容
                pattern = r"<message_id>:\s*([a-f0-9]{32})"
                message_ids = re.findall(pattern, output.answer)  # 提取所有<message_id>
                text_cleaned = re.sub(pattern, "", output.answer)  # 从文本中移除匹配的部分
                output.answer = text_cleaned

                intentions = re.findall(r"意图: ([^)]*)", text_cleaned)

                all_messages = await self.memory.gpts_memory.get_messages(conv_id)
                for idx, message_id in enumerate(message_ids):
                    # 根据message_id回查
                    message = next(
                        (msg for msg in all_messages if msg.message_id == message_id),
                        None
                    )
                    if message is None:
                        continue
                    action_reports = parse_action_reports(message.action_report)
                    for _, action_report in enumerate(action_reports):
                        # 拍平
                        LOGGER.info(f"[{trace_id}][{conv_id}][AGENT]_get_summary_action agent:[{self.name}], content:[{action_report.content if action_report else None}]")
                        if len(intentions) > idx:
                            action_report.action = "意图: " + intentions[idx]
                        summary_actions.append(action_report)
            except Exception as e:
                LOGGER.info(f"[{trace_id}][{conv_id}][AGENT][_get_summary_action:异常] agent:[{self.name}], output:[{output.answer}], except:[{repr(e)}]")
        return summary_actions

    def need_user_confirm(self, output: ReasoningEngineOutput, sender: Agent, step_counter: int) -> bool:
        return False

    async def send_confirm_message(self, output: ReasoningEngineOutput, current_step_message: AgentMessage, received_message: AgentMessage, received_action_id: str):
        current_step_message.action_report = ActionOutput.from_dict({
            "view": await self._render_confirm_view(output=output, message_id=current_step_message.message_id),
            "model_view": output.answer,
            "action_id": received_action_id + "-confirm",
            "extra": received_message.context | {"title": "待用户确认"},
            "content": "待用户确认",
            "action": self.name,
            "action_name": UserConfirmAction().name,
            "action_input": received_message.content,
        })
        pass


# def _update_action_report_view(action_report: ActionOutput, human_view: Optional[str], model_view: Optional[str]) -> None:
#     action_report.view = human_view if human_view else None
#     action_report.model_view = model_view if model_view else None


# def _must_fill_message_view(message: AgentMessage, view: str, model_view: str = None) -> None:
#     message.action_report = action_output or message.action_report or ActionOutput(content="")  # TODO: 当前只支持每轮一个action_report
#     message.action_report.view = view
#     message.action_report.model_view = model_view
#
#     message.action_report.action = action_output.action if action_output and action_output.action else message.action_report.action
#     message.action_report.action_input = (
#         action_output.action_input if action_output and action_output.action_input
#         else message.action_report.action_input)
#     message.action_report.content = (
#         action_output.content if (action_output and action_output.content)
#         else message.action_report.content if message.action_report.content
#         else model_view if model_view else "")
#
#     message.action_report.extra = message.action_report.extra or {}
#     message.action_report.extra["title"] = title


async def _format_vis_content(action: Action, output: ActionOutput = None) -> Any:
    if isinstance(action, AgentAction):
        content = VisTaskContent(task_uid=uuid.uuid4().hex)
        content.task_content = action.action_input.content
        content.task_name = action.action_input.content
        content.agent_name = action.action_input.agent_name
    elif isinstance(action, ToolAction):
        tool_name = action.action_input.tool_name
        tool_packs = ToolPack.from_resource(action.resource)
        for tool_pack in tool_packs:
            if not tool_pack:
                continue
            base_tool: BaseTool = await tool_pack.get_resources_info(resource_name=action.action_input.tool_name)
            if not (base_tool and base_tool.description):
                continue
            tool_name = base_tool.description
            break

        content = StepInfo()
        content.tool_name = tool_name
        content.tool_args = json.dumps(action.action_input.args, default=serialize, ensure_ascii=False)
        content.tool_result = output.content if output else None
        content.status = Status.TODO.value if not output else Status.COMPLETE if output.is_exe_success else Status.FAILED

    elif isinstance(action, KnowledgeRetrieveAction):
        content = StepInfo()
        content.tool_name = "知识检索"
        content.tool_args = json.dumps({"query": action.action_input.query}, default=serialize, ensure_ascii=False)
        content.tool_result = output.content if output else None
        content.status = Status.TODO.value if not output else Status.COMPLETE if output.is_exe_success else Status.FAILED
    else:
        raise NotImplementedError

    return content


def _format_action_model_view(action: Action, action_output: ActionOutput) -> str:
    # 如果是给下游agent发消息 content应该是发送的消息
    # 如果是执行工具/检索 content应该是执行结果
    # return action_output.action_input if isinstance(action, AgentAction) else f"动作: {action_output.action}\n\n参数: {action_output.action_input}\n\n结果:\n{action_output.content}"
    return None if isinstance(action, AgentAction) else f"动作: {action_output.action}\n\n参数: {action_output.action_input}\n\n结果:\n{action_output.content or None}"


def _format_engine_output_span(output: Optional[ReasoningEngineOutput]) -> dict:
    if not output:
        return {}

    return {
        "done": output.done,
        "answer": output.answer,
        # "actions": [{"name": action.name, "input": action.action_input} for action in output.actions],
        "action_reason": output.action_reason,
        "model_name": output.model_name,
        "messages": [message.to_llm_message() for message in output.messages],
        "user_prompt": output.user_prompt,
        "system_prompt": output.system_prompt,
        "model_content": output.model_content,
        "model_thinking": output.model_thinking,
    }


# async def _store_message_relation(agent: ConversableAgent, conv_id: str, child_message: AgentMessage, parent_message_ids: list[str]) -> None:
#     plans = [GptsPlan(
#         conv_id=conv_id,
#         sub_task_id=child_message.message_id,
#         task_parent=parent_message_id,
#         task_uid=uuid.uuid4().hex,
#         conv_round=child_message.rounds or 0,
#         # sub_task_num=int(datetime.now().timestamp() * 1000) & 0xFFFFFFFF,  # 暂时用不到 绕过DB的唯一索引
#         sub_task_num=child_message.rounds,
#         sub_task_title="",
#         sub_task_content=""
#     ) for parent_message_id in parent_message_ids]
#     await agent.memory.gpts_memory.append_plans(conv_id=conv_id, plans=plans)
#
#
# async def _find_all_leaf_message_id(agent: ConversableAgent, conv_id: str, root_message_id: str) -> list[str]:
#     """
#     找出所有消息 构建树形关系 找到所有叶子节点
#
#     :param conv_id:  会话的conv_id
#     :param root_message_id:  从哪条消息开始找叶子节点消息
#     :return:
#     """
#     plans = await agent.memory.gpts_memory.get_plans(conv_id=conv_id)
#
#     # 构建边的关系
#     children: dict[str, set[str]] = {}
#     for plan in plans:
#         if not plan or not plan.task_parent or not plan.sub_task_id:
#             continue
#         _children = children.get(plan.task_parent, set())
#         _children.add(plan.sub_task_id)
#         children[plan.task_parent] = _children
#
#     leafs = []
#
#     # 深度遍历找叶子节点
#     message_stack = [root_message_id]
#     while message_stack and (current_message_id := message_stack[-1]):
#         message_stack = message_stack[:-1]  # 出栈
#         if (current_message_id not in children) or (not children[current_message_id]):
#             leafs.append(current_message_id)
#             continue
#
#         message_stack.extend(children[current_message_id])
#
#     # 有叶子节点返回叶子节点 没有叶子节点说明root本身就是叶子节点
#     return leafs if leafs else [root_message_id]


def format_action_id(step_counter: int, action_idx: int, received_action_id: str = None) -> str:
    """
    组装action_id
    :param step_counter: action位于当前agent的第几轮step
    :param action_idx:  action位于当前agent当前step轮次的第几个action
    :param received_action_id: 接收到的action_id，表示从哪个action_id派生而来
    :return:
    """
    return f"{received_action_id}-{step_counter}.{action_idx}"


def _current_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


class ReasoningEngineException(Exception):
    """
    推理引擎相关异常
    """
    pass


class ReasoningActionException(Exception):
    """
    ACTION执行相关异常
    """
    pass
