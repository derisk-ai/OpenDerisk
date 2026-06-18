"""context_engine 测试共享 fixtures。

全部使用轻量假数据（FakeMsg / FakeWE），不依赖 GptsMemory / 真实 LLM。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest


@dataclass
class FakeMsg:
    """模拟 GptsMessage（仅含引擎用到的字段）。"""

    conv_id: str
    role: str
    message_id: str
    content: Any = ""
    tool_calls: Optional[List[Dict]] = None
    rounds: int = 0
    created_at: float = 0.0
    goal_id: Optional[str] = None
    current_goal: Optional[str] = None
    sender: Optional[str] = None
    content_types: Optional[List[str]] = None
    context: Optional[Dict] = None


@dataclass
class FakeWE:
    """模拟 WorkEntry。"""

    tool: str
    tool_call_id: str
    result: str = ""
    message_id: str = ""
    success: bool = True
    summary: str = ""
    full_result_archive: Optional[str] = None
    tokens: int = 0
    args: Dict[str, Any] = field(default_factory=dict)


def ai_tool_call(tc_id: str, name: str, arguments: str = "{}") -> Dict:
    return {
        "id": tc_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


class RecordingEmitter:
    """录制式 EventEmitter，断言压缩事件。"""

    def __init__(self):
        self.events: List[tuple] = []

    def emit(self, event_type, title, description="", metadata=None):
        self.events.append((event_type, title, description, metadata or {}))

    def types(self):
        return [e[0] for e in self.events]


class CountingSummarizer:
    """记录调用次数的 summarize_fn，返回固定摘要。"""

    def __init__(self, text: str = "SUMMARY", raises: bool = False):
        self.text = text
        self.calls = 0
        self.raises = raises

    async def __call__(self, prompt: str, max_tokens: int) -> str:
        self.calls += 1
        if self.raises:
            raise RuntimeError("llm down")
        return self.text


@pytest.fixture
def emitter():
    return RecordingEmitter()
