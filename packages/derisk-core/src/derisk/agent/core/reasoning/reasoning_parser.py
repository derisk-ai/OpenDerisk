import json
import logging
import re
from typing import Tuple, Optional

import orjson

from derisk.agent.core.reasoning.reasoning_action import (
    AgentActionInput,
    ActionOutput,
    KnowledgeRetrieveActionInput,
)
from derisk.agent.core.reasoning.reasoning_engine import (
    ReasoningPlan,
)
from derisk.agent.expand.actions.tool_action import ToolInput
from derisk.core.workflow.workflow_action import WorkflowAction, WorkflowActionInput
from derisk.util.string_utils import is_number

logger = logging.getLogger("reasoning")


def is_str_list(origin) -> bool:
    return isinstance(origin, list) and not any(item for item in origin if not isinstance(item, str))


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
        extra_info=plan.parameters if plan.parameters else {},
    )


def transfer_knowledge_retrieve_action_input(
    plan: ReasoningPlan,
) -> KnowledgeRetrieveActionInput:
    return KnowledgeRetrieveActionInput(
        query=plan.parameters.get("query") if plan.parameters.get("query") else plan.intention,
        knowledge_ids=plan.parameters["knowledge_ids"],
        func=plan.parameters.get("func"),
        doc_uuids=plan.parameters.get("doc_uuids"),
        header=plan.parameters.get("header"),
        intention=plan.intention,
        thought=plan.reason,
    )




def transfer_workflow_action_input(plan: ReasoningPlan) -> WorkflowActionInput:
    intention: str = plan.intention
    parameter: str = json.dumps(plan.parameters) if plan.parameters else None
    return WorkflowActionInput(
        name=plan.id,
        query="\n\n".join([s for s in [intention, parameter] if s]),
        thought=plan.reason,
    )


async def parse_action_reports(text: str) -> list[ActionOutput]:
    async def _parse_sub_action_reports(
        content: str, action_report_list: list[ActionOutput]
    ) -> bool:
        """
        递归解析sub_action_report
        :param content:
        :param action_report_list:
        :return: 是否有sub_action_report
        """
        try:
            sub_action_report_dicts_list = orjson.loads(content) if content else []
            sub_action_report_list = (
                [
                    ActionOutput.from_dict(sub_dict)
                    for sub_dict in sub_action_report_dicts_list
                ]
                if isinstance(sub_action_report_dicts_list, list)
                else []
            )
        except Exception as e:
            return False
        if not sub_action_report_list:
            return False

        sub = False
        for sub_action_report in sub_action_report_list:
            try:
                sub = sub or await _parse_sub_action_reports(
                    sub_action_report.content, action_report_list
                )
            except Exception as e:
                pass
        if not sub:
            action_report_list.extend(sub_action_report_list)
        return True

    try:
        if not text:
            return []
        # 先解析最外层的action_report
        action_report_dict = orjson.loads(text)
        action_report = ActionOutput.from_dict(action_report_dict)
    except Exception as e:
        return []

    result: list[ActionOutput] = []
    if await _parse_sub_action_reports(action_report.content, result):
        return result
    return [action_report]


def parse_action_id(id: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    从原始id中解析出task_id、step_id、action_id
    * 若输入的是task_id，则输出的step_id、action_id都为None
    * 若输入的是step_d，则输出只有task_id、step_id，而action_id为None
    * 若输入的是action_id，则输出的task_id、step_id、action_id都不为None
    * 若输入的是非法数据，则输出三个None
    :param id: 原始id 可能是task_id/step_id/action_id
    :return: 解析出的task_id、step_id、action_id
    """
    if is_number(id):
        # 输入的是task_id
        return id, None, None

    # 找到最后一个- 用于切割出task_id
    idx1 = id.rfind("-")
    if idx1 <= 0 or idx1 >= len(id):
        return None, None, None

    task_id = id[:idx1]  # todo: 待校验task_id合法性
    step_part = id[idx1 + 1:]
    if re.match("^\w+$", step_part):  # 不含.-等step_id、action_id分隔符
        # `task_id-`后面跟的是数字 说明id是step_id
        return task_id, id, None

    sps = step_part.split(".")
    if not len(sps) == 2 or not is_number(sps[0]):
        return None, None, None

    return task_id, id[: idx1 + 1 + len(sps[0])], id


def compare_action_id(left: str, right: str) -> int:
    l: list[str] = re.split("[.-]", left)
    r: list[str] = re.split("[.-]", right)
    for i in range(len(l)):
        if len(r) <= i:
            # 短的 说明是上游 排在前面
            break

        if l[i] == r[i]:
            continue

        # 走到这里两者必然不相等

        nl: bool = is_number(l[i])
        nr: bool = is_number(r[i])

        if nl and nr:
            # 都是数字 小的排前面
            return 1 if int(l[i]) > int(r[i]) else -1
        elif (not nl) and (not nr):
            # 都不是数字 按照字符串排序
            return 1 if l[i] > r[i] else -1
        else:
            # 数字排前面 字符串排最后
            return 1 if is_number(r[i]) else -1
    # 前面一截字符串都相同 短的排前面
    return 1 if len(l) > len(r) else -1


if __name__ == "__main__":

    def test_parse_action_id():
        for i, (_id, expected) in enumerate(
            [
                ("2", ("2", None, None)),
                ("1", ("1", None, None)),
                ("1-0", ("1", "1-0", None)),
                ("1-0.0", ("1", "1-0", "1-0.0")),
                ("1-0.0-0", ("1-0.0", "1-0.0-0", None)),
                ("1-0.0-0.0", ("1-0.0", "1-0.0-0", "1-0.0-0.0")),
                ("1-0.0-answer", ("1-0.0", "1-0.0-answer", None)),
                ("1-0.1", ("1", "1-0", "1-0.1")),
                ("1-0.1-0", ("1-0.1", "1-0.1-0", None)),
                ("1-0.1-0.0", ("1-0.1", "1-0.1-0", "1-0.1-0.0")),
                ("1-0.1-1", ("1-0.1", "1-0.1-1", None)),
                ("1-0.1-1.0", ("1-0.1", "1-0.1-1", "1-0.1-1.0")),
                ("1-0.1-answer", ("1-0.1", "1-0.1-answer", None)),
                ("1-1", ("1", "1-1", None)),
                ("1-1.0", ("1", "1-1", "1-1.0")),
                ("1-1.0-0", ("1-1.0", "1-1.0-0", None)),
                ("1-1.0-answer", ("1-1.0", "1-1.0-answer", None)),
                ("1-answer", ("1", "1-answer", None)),
            ]
        ):
            actual = parse_action_id(_id)
            le = list(expected)
            la = list(actual)
            for j in range(len(le)):
                assert (le[j] is None and la[j] is None) or (
                    le[j] is not None and la[j] is not None and le[j] == la[j]
                ), f"第{i}个测试用例的第{j}个值不相等"


    # test_parse_action_id()

    def test_compare_action_id():
        tests: list[str] = [
            "10",
            "1",
            "1-0",
            "1-0.0-0",
            "1-0.0-answer",
            "1-0.1-0",
            "1-0.1-1",
            "1-0.1-answer",
            "1-1",
            "1-1.0-0",
            "1-1.0-answer",
            "1-answer",
            "2-answer",
            "3",
            "3-0",
            "3-0.0-0",
            "3-0.0-answer",
            "3-answer",
            "4",
            "4-0",
            "4-0.0-0",
            "4-0.0-answer",
            "4-answer",
        ]
        for i in range(len(tests)):
            for j in range(i + 1, len(tests)):
                cmp = compare_action_id(tests[i], tests[j])
                op = (
                    "=="
                    if cmp == 0
                    else ">"
                    if cmp == 1
                    else "<"
                    if cmp == -1
                    else None
                )
                print(f"{tests[i]} {op} {tests[j]}")

    # test_compare_action_id()
