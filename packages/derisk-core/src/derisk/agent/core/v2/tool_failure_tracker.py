"""工具连续失败跟踪器。

从 BAIZE react_master_agent.py:2517-2575 的 _tool_failure_counts 抽出。
无 agent 反向依赖。
"""
from typing import Dict


class ToolFailureTracker:
    def __init__(self, max_failures: int = 3):
        self._counts: Dict[str, int] = {}
        self._max_failures = max_failures

    def record_failure(self, tool_name: str) -> bool:
        """记录一次失败。返回是否达到阈值。"""
        self._counts[tool_name] = self._counts.get(tool_name, 0) + 1
        return self._counts[tool_name] >= self._max_failures

    def is_blocked(self, tool_name: str) -> bool:
        return self._counts.get(tool_name, 0) >= self._max_failures

    def reset(self, tool_name: str) -> None:
        self._counts.pop(tool_name, None)
