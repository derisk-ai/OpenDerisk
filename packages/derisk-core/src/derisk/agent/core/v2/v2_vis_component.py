"""简化VIS组件 - 无嵌套，原子操作。

设计文档 §4.1-§4.3。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class VisOperationType(Enum):
    """VIS操作类型"""

    INCR = "incr"
    REPLACE = "replace"
    DELETE = "delete"


class VisComponentTag(Enum):
    """VIS组件类型标签"""

    MESSAGE = "message"
    THINKING = "thinking"
    TOOL_RESULT = "tool_result"
    STEP_STATUS = "step_status"
    USAGE_DISPLAY = "usage_display"
    SUB_AGENT_PANEL = "sub_agent_panel"
    INTERACTION_PROMPT = "interaction_prompt"
    ERROR_BLOCK = "error_block"


@dataclass
class SimplifiedVisComponent:
    """简化VIS组件模型

    设计原则：
    - 单一组件，无嵌套markdown/items
    - UID定位，原子操作
    - meta字段扩展元数据
    """

    type: VisOperationType
    uid: str
    tag: VisComponentTag
    content: str
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为dict，用于JSON序列化"""
        result = {
            "type": self.type.value,
            "uid": self.uid,
            "tag": self.tag.value,
            "content": self.content,
        }
        if self.meta:
            result["meta"] = self.meta
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SimplifiedVisComponent:
        """从dict创建"""
        return cls(
            type=VisOperationType(data["type"]),
            uid=data["uid"],
            tag=VisComponentTag(data["tag"]),
            content=data["content"],
            meta=data.get("meta"),
        )


def make_vis_incr(
    uid: str, tag: VisComponentTag, content: str, meta: Optional[Dict] = None
) -> SimplifiedVisComponent:
    """创建incr操作组件"""
    return SimplifiedVisComponent(
        type=VisOperationType.INCR,
        uid=uid,
        tag=tag,
        content=content,
        meta=meta,
    )


def make_vis_replace(
    uid: str, tag: VisComponentTag, content: str, meta: Optional[Dict] = None
) -> SimplifiedVisComponent:
    """创建replace操作组件"""
    return SimplifiedVisComponent(
        type=VisOperationType.REPLACE,
        uid=uid,
        tag=tag,
        content=content,
        meta=meta,
    )


def make_vis_delete(uid: str) -> SimplifiedVisComponent:
    """创建delete操作组件"""
    return SimplifiedVisComponent(
        type=VisOperationType.DELETE,
        uid=uid,
        tag=VisComponentTag.MESSAGE,
        content="",
    )
