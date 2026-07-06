"""V2 SSE事件类型定义。

设计文档 §3.1-§3.2。
"""
from typing import Any, Dict


class V2EventType:
    """V2事件类型常量

    使用 class + str 子类，既是类型提示又是运行时常量。
    """

    STEP_START = "step_start"
    STEP_STATUS = "step_status"
    LLM_TOKEN = "llm_token"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    INTERACTION_REQUEST = "interaction_request"
    USAGE_METRIC = "usage_metric"
    SUB_AGENT_START = "sub_agent_start"
    SUB_AGENT_RESULT = "sub_agent_result"
    STEP_END = "step_end"
    VIS_UPDATE = "vis_update"
    ERROR = "error"
    DONE = "done"


# 便捷常量
STEP_START = "step_start"
STEP_STATUS = "step_status"
LLM_TOKEN = "llm_token"
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"
INTERACTION_REQUEST = "interaction_request"
USAGE_METRIC = "usage_metric"
SUB_AGENT_START = "sub_agent_start"
SUB_AGENT_RESULT = "sub_agent_result"
STEP_END = "step_end"
VIS_UPDATE = "vis_update"
ERROR = "error"
DONE = "done"


class V2Event(dict):
    """V2 SSE事件格式

    设计文档 §3.1：
    {
        "event": string,   // 事件类型
        "seq": number,     // 序列号（单调递增）
        "ts": number,      // 时间戳（毫秒）
        "payload": object, // 事件数据
    }
    """

    def __init__(
        self,
        event: str,
        seq: int,
        ts: int,
        payload: Dict[str, Any],
    ):
        super().__init__(event=event, seq=seq, ts=ts, payload=payload)
