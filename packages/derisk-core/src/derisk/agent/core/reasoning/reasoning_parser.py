import json
from typing import Tuple, Optional

from derisk.agent import Action, ConversableAgent
from derisk.agent.core.reasoning.reasoning_action import (
    AgentAction,
    AgentActionInput,
    KnowledgeRetrieveAction,
    KnowledgeRetrieveActionInput,
)
from derisk.agent.core.reasoning.reasoning_engine import (
    ReasoningModelOutput,
    ReasoningPlan,
)
from derisk.agent.expand.actions.tool_action import ToolAction, ToolInput
from derisk.agent.resource import FunctionTool
from derisk.util.json_utils import find_json_objects
from derisk_ext.agent.agents.reasoning.default.ability import Ability
from derisk_serve.agent.resource.knowledge_pack import KnowledgePackSearchResource


def parse_actions(
    text: str, abilities: list[Ability]
) -> Tuple[ReasoningModelOutput, bool, str, Optional[list[Action]]]:
    json_parsed = find_json_objects(text)
    if isinstance(json_parsed, list) and len(json_parsed) >= 1:
        json_parsed = json_parsed[0]

    if "summary" in json_parsed:
        # 有时模型返回的summary是list 需要兼容
        if isinstance(json_parsed["summary"], list):
            json_parsed["summary"] = "\n".join(json_parsed["summary"])
        # 也有可能是别的类型
        elif not isinstance(json_parsed["summary"], str):
            json_parsed["summary"] = json.dumps(json_parsed["summary"], ensure_ascii=False)

    if "plan" in json_parsed:
        if not isinstance(json_parsed["plan"], list):
            json_parsed["plans"] = [json_parsed["plan"]]

    result = ReasoningModelOutput.model_validate(json_parsed)

    # # Remove non-JSON parts.
    # json_matches = re.search(r"```json\s*({.*})\s*```", text, re.IGNORECASE | re.DOTALL)
    # if json_matches:
    #     text = json_matches[1]
    #
    # def _load() -> ReasoningModelOutput:
    #     _SPLITER = " "
    #     json_parsed = json.loads(text)
    #     if "summary" in json_parsed and isinstance(json_parsed["summary"], list):
    #         json_parsed["summary"] = _SPLITER.join(json_parsed["summary"])
    #
    #     if "conclusion" in json_parsed and isinstance(json_parsed["conclusion"], list):
    #         json_parsed["conclusion"] = _SPLITER.join(json_parsed["conclusion"])
    #
    #     return ReasoningModelOutput.model_validate(json_parsed)
    #
    # try:
    #     result = _load()
    # except Exception:
    #     # todo 待优化: 模型返回结果可能包含换行等特殊字符导致解析失败 直接替换可能带来其他问题
    #     text = text.replace("\n", " ")
    #     result = _load()

    assert result, "failed to parse model output: " + text

    done = True if result.status in ["done", "abort"] else False
    answer = result.answer or result.summary or (result.reason if done else None)
    actions = format_actions(plans=result.plans, abilities=abilities)
    return result, done, answer, actions


def transfer_tool_action_input(plan: ReasoningPlan) -> ToolInput:
    return ToolInput(
        tool_name=plan.id,
        args=plan.parameters,
        thought="\n\n".join([s for s in [plan.intention, plan.reason] if s]),
    )


def transfer_agent_action_input(plan: ReasoningPlan) -> AgentActionInput:
    return AgentActionInput(
        agent_name=plan.id,
        content=plan.intention,
        thought=plan.reason,
        extra_info=plan.parameters,
    )


def transfer_knowledge_retrieve_action_input(
    plan: ReasoningPlan,
) -> KnowledgeRetrieveActionInput:
    return KnowledgeRetrieveActionInput(
        query=plan.parameters["query"],
        knowledge_ids=plan.parameters["knowledge_ids"],
        intention=plan.intention,
        thought=plan.reason,
    )


def format_action(
    plan: Optional[ReasoningPlan], ability: Optional[Ability]
) -> Optional[Action]:
    _dict = {
        FunctionTool: (ToolAction, transfer_tool_action_input),
        ConversableAgent: (AgentAction, transfer_agent_action_input),
        KnowledgePackSearchResource: (
            KnowledgeRetrieveAction,
            transfer_knowledge_retrieve_action_input,
        ),
    }

    if (not plan) or (not ability) or (not ability.name in plan.id):
        return None

    if not ability.actual_type in _dict:
        raise NotImplementedError

    action_cls, input_transfer = _dict[ability.actual_type]
    action = action_cls()
    action.action_input = input_transfer(plan)
    action.intention = plan.intention
    action.reason = plan.reason
    return action


def format_actions(
    plans: Optional[list[ReasoningPlan]], abilities: list[Ability]
) -> Optional[list[Action]]:
    if not plans or not abilities:
        return None

    return [
        action
        for plan in plans
        for ability in abilities
        if (action := format_action(plan=plan, ability=ability))
    ]
