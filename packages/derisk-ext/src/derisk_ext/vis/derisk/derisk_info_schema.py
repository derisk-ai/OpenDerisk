import json
from enum import Enum
from typing import Optional, List

from derisk._private.pydantic import (
    BaseModel,
    Field,
)
from derisk.agent import ActionOutput
from derisk.agent.core.memory.gpts import GptsMessage
from derisk.util.json_utils import find_json_objects


class OutputType(str, Enum):
    NATURAL_LANGUAGE = "NATURAL_LANGUAGE",
    MARKDOWN = "MARKDOWN",
    JSON = "JSON",
    LIST = "LIST",
    TAB = "TAB",


class MessageInfo(BaseModel):
    title: Optional[str] = Field(
        None, description="nex message extension stage info title"
    )
    outputType: Optional[str] = Field(
        None, description="nex message extension stage info outputType"
    )
    content: Optional[str] = Field(
        None, description="nex message extension stage info content"
    )
    items: Optional[list["MessageInfo"]] = Field(
        None, description="当OutputType为LIST/TAB等时的下层数据"
    )
    level: Optional[str] = Field(
        None, description="nex message extension stage info level"
    )
    suggestion: Optional[str] = Field(
        None, description="nex message extension stage info suggestion"
    )


class MessageStage(BaseModel):
    stage: Optional[str] = Field(..., description="nex message extension stage")
    level: Optional[str] = Field(..., description="nex message extension stage level")
    details: Optional[List[MessageInfo]] = Field(
        default=[], description="nex message extension stage details"
    )


def _is_json(text: str) -> bool:
    return text and text.strip() and text.strip()[0] == "{" and find_json_objects(text)


def _gen_plans_info(message: GptsMessage) -> Optional[MessageStage]:
    details: List[MessageInfo] = [
        MessageInfo(
            title="系统设定",
            content=message.system_prompt,
            level="INFO",
            outputType="MARKDOWN",
        ),
        MessageInfo(
            title="意图",
            content=message.user_prompt,
            level="INFO",
            outputType="MARKDOWN",
        ),
        MessageInfo(
            title="输出",
            content="\n".join(
                [item for item in [message.thinking, message.content] if item]
            ),
            level="INFO",
            outputType="MARKDOWN",
        ),
    ]
    return MessageStage(
        stage="规划",
        level="INFO",
        details=details,
    )


def _gen_select_tool(action_out: ActionOutput) -> MessageStage:
    details: List[MessageInfo] = [
        MessageInfo(
            title="工具选用",
            content=f"{action_out.action}",
            level="INFO",
            outputType="NATURAL_LANGUAGE",
        ),
        MessageInfo(
            title="ToolTag",
            content=f"{action_out.resource_value}",
            level="INFO",
            outputType="NATURAL_LANGUAGE",
        )
        if action_out.resource_value
        else None,
    ]
    return MessageStage(
        stage="工具选用",
        level="INFO",
        details=[detail for detail in details if detail],
    )


def _gen_tool_param(action_out: ActionOutput) -> MessageStage:
    details: List[MessageInfo] = [
        MessageInfo(
            title="工具入参",
            content=f"{action_out.action_input}",
            level="INFO",
            outputType="JSON"
            if _is_json(action_out.action_input)
            else "NATURAL_LANGUAGE",
        ),
    ]
    return MessageStage(
        stage="工具入参",
        level="INFO",
        details=details,
    )


def _gen_tool_execute(action_out: ActionOutput) -> MessageStage:
    details: List[MessageInfo] = [
        MessageInfo(
            title="工具结果",
            content=f"{action_out.content}",
            level="INFO",
            outputType="JSON" if _is_json(action_out.content) else "NATURAL_LANGUAGE",
        ),
    ]
    return MessageStage(
        stage="工具结果",
        level="INFO",
        details=details,
    )


def _gen_resource_ref(action_out: ActionOutput) -> Optional[MessageStage]:
    if action_out and action_out.resource_value:
        details: List[MessageInfo] = [
            MessageInfo(
                title="资源详情",
                content=f"{action_out.resource_value}",
                level="INFO",
                outputType="Markdown",
            ),
        ]
        return MessageStage(
            stage="资源引用",
            level="INFO",
            details=details,
        )
    return None


def gen_tool_excute_info(action_out: ActionOutput):
    # 定义生成各阶段的函数列表
    step_functions = [
        _gen_select_tool,
        _gen_tool_param,
        _gen_tool_execute,
        _gen_resource_ref,
    ]

    step_stages: List[MessageStage] = []
    for func in step_functions:
        result = func(action_out=action_out)
        if result is not None:
            step_stages.append(result)

    return step_stages


def gen_thinking_info(message: GptsMessage):
    thinking_stages: List[MessageStage] = [_gen_plans_info(message)]
    return thinking_stages


def gen_thinking_info_v2(message: GptsMessage):
    llm_params = ["trace_id"]
    message_context = json.loads(message.context) if message.context else {}
    model_params = {"model_name": message.model_name}
    model_params.update({k: message_context[k] for k in llm_params if message_context.get(k) is not None})

    def _format_input_info() -> MessageInfo:
        return MessageInfo(
            outputType=OutputType.LIST,
            title="模型输入",
            items=[item for item in [
                MessageInfo(outputType=OutputType.MARKDOWN, title="系统提示词", content=message.system_prompt),
                MessageInfo(outputType=OutputType.MARKDOWN, title="用户提示词", content=message.user_prompt),
            ] if item.content],
        )

    def _format_output_info() -> MessageInfo:
        return MessageInfo(
            outputType=OutputType.MARKDOWN,
            title="模型输出",
            content=message.content,
        ) if not message.thinking else MessageInfo(
            outputType=OutputType.LIST,
            title="模型输出",
            items=[
                MessageInfo(
                    outputType=OutputType.MARKDOWN,
                    title="thinking",
                    content=message.thinking,
                ), MessageInfo(
                    outputType=OutputType.MARKDOWN,
                    title="content",
                    content=message.content,
                ),
            ]
        )

    return MessageInfo(
        outputType=OutputType.LIST,
        items=[
            MessageInfo(
                outputType=OutputType.JSON,
                title="模型选用",
                content=json.dumps(model_params, ensure_ascii=False)
            ),
            MessageInfo(
                outputType=OutputType.TAB,
                items=[
                    _format_input_info(),
                    _format_output_info(),
                ]
            )
        ]
    )


def gen_knowledge_execute_info(action_out: ActionOutput):
    """Generate knowledge execute steps"""
    if action_out and action_out.resource_value:
        stages: List[MessageStage] = []
        knowledge_res = action_out.resource_value
        sub_queries = (
            knowledge_res.get("sub_queries").keys()
            if knowledge_res.get("sub_queries")
            else []
        )
        query_stage = MessageStage(
            stage="问题拆解",
            level="INFO",
            details=[
                MessageInfo(
                    title=knowledge_res.get("raw_query"),
                    content=json.dumps(list(sub_queries), ensure_ascii=False),
                    level="INFO",
                    outputType=OutputType.JSON,
                ),
            ],
        )
        stages.append(query_stage)
        retrieve_stage = MessageStage(
            stage="知识搜索",
            level="INFO",
        )
        retrieve_details = []
        for sub_query, sub_summary in knowledge_res.get("sub_queries").items():
            retrieve_details.append(
                MessageInfo(
                    title=sub_query,
                    content=sub_summary,
                    level="INFO",
                    outputType="MARKDOWN",
                )
            )
        retrieve_stage.details = retrieve_details
        stages.append(retrieve_stage)
        summary_stage = MessageStage(
            stage="生成总结",
            level="INFO",
            details=[
                MessageInfo(
                    title=knowledge_res.get("raw_query"),
                    content=knowledge_res.get("summary_content"),
                    level="INFO",
                    outputType="MARKDOWN",
                ),
            ],
        )
        stages.append(summary_stage)
        return stages
    return []
