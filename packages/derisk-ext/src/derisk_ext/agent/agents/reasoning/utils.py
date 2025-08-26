from typing import Optional
from pydantic import BaseModel
import json

from derisk.agent import Action, ResourceType
from derisk.agent.core.reasoning.reasoning_action import AgentAction, AgentActionInput, KnowledgeRetrieveAction, \
    KnowledgeRetrieveActionInput
from derisk.agent.core.reasoning.reasoning_engine import REASONING_LOGGER as LOGGER
from derisk.agent.expand.actions.tool_action import ToolAction, ToolInput


class ActionCounter(BaseModel):
    counter_size: int = 5  # 同样的动作，(全局)最多执行几次
    order_size: int = 3  # 同样的动作，(连续)最多执行几次
    buffer: dict[str, int] = {}
    order: list[str] = []

    def _make_key(self, action: Action) -> Optional[str]:
        try:
            if isinstance(action, AgentAction):
                return "#".join([
                    type(action).__name__,
                    action.action_input.agent_name,
                    action.action_input.content,
                ])
            elif isinstance(action, ToolAction):
                return "#".join([
                    type(action).__name__,
                    action.action_input.tool_name,
                    json.dumps(action.action_input.args, ensure_ascii=False),
                ])
            else:
                return None
        except Exception as e:
            return None

    def add_and_count(self, action: Action) -> bool:
        key: str = self._make_key(action)
        LOGGER.info(f"ActionCounter, add_and_count, key: {key}")
        if not key:
            return True

        count: int = self.buffer.get(key, 0) + 1
        self.buffer[key] = count
        LOGGER.info(f"ActionCounter, add_and_count, count: {count}, key: {key}")

        self.order.append(key)
        # 踢掉不连续的action
        index: int = 0
        for idx, _k in enumerate(self.order):
            if _k != key:
                index = idx
        LOGGER.info(f"ActionCounter, add_and_count, old_count: {len(self.order)}, index: {index}")
        self.order = self.order[index:]

        return count <= self.counter_size and len(self.order) <= self.order_size


def identify_action_info(action: Action):
    ### 处理Action的类型，目前可枚举工具、agent、知识，暂无动态扩展诉求
    match action:
        case AgentAction():
            action_input: AgentActionInput = action.action_input
            agent = action_input.agent_name
            agent_type = ResourceType.Agent.value
        case KnowledgeRetrieveAction():
            action_input: KnowledgeRetrieveActionInput = action.action_input
            if action_input.knowledge_ids and isinstance(
                action_input.knowledge_ids, list
            ):
                agent = json.dumps(action_input.knowledge_ids, ensure_ascii=False)
            else:
                agent = action_input.knowledge_ids
            agent_type = ResourceType.KnowledgePack.value
        case ToolAction():
            action_input: ToolInput = action.action_input
            agent = action_input.tool_name
            agent_type = ResourceType.Tool.value
        case _:
            LOGGER.error(
                f"[AGENT][Action规划结果解析异常] <---- "
                f"Action:[{action.name}][{action.action_uid}]], except:[无法识别action]"
            )
            raise ValueError(f"Action规划结果解析异常,无法识别action,{action}!")

    return action_input, agent, agent_type
