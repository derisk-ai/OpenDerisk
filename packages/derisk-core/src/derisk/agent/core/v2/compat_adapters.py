"""V2 兼容适配器：把 BAIZE 的 DoomLoopDetector / Truncator / Resource pack 适配到
default_acting.py 期望的接口。

default_acting.py 期望：
  doom_loop_detector.check(name, args) -> bool        (async)
  truncator.truncate(content, name, args) -> result   (async, with .truncated, .truncated_content)

BAIZE 实际接口：
  DoomLoopDetector.check_doom_loop(name, args) -> DoomLoopCheckResult  (sync)
  Truncator.truncate(content, name, ...) -> TruncationResult           (sync, .is_truncated, .content)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional


class DoomLoopAdapter:
    """适配 BAIZE DoomLoopDetector 到 V2 接口。

    V2 default_acting.py 调用 `await doom_loop_detector.check(name, args) -> bool`。
    BAIZE DoomLoopDetector 是同步 `check_doom_loop(name, args) -> DoomLoopCheckResult`。
    """

    def __init__(self, detector: Optional[Any]):
        self._detector = detector

    async def check(self, tool_name: str, args: dict) -> bool:
        if self._detector is None:
            return True  # 无检测器，放行
        try:
            result = self._detector.check_doom_loop(tool_name, args)
            # DoomLoopCheckResult 字段：should_block / is_doom_loop / message 等
            return not bool(getattr(result, "should_block", False))
        except Exception:
            return True  # 检测异常不阻塞主流程


class TruncatorAdapter:
    """适配 BAIZE Truncator 到 V2 接口。

    V2 default_acting.py 调用 `await truncator.truncate(content, name, args)`
    期望返回带 `.truncated` (bool) 和 `.truncated_content` (str) 的对象。

    BAIZE Truncator.truncate 是同步，返回 TruncationResult（字段 `.is_truncated` /
    `.content`）。我们用 dataclass 桥接字段名。
    """

    def __init__(self, truncator: Optional[Any]):
        self._truncator = truncator

    async def truncate(self, content: str, tool_name: str, args: dict) -> Any:
        from dataclasses import dataclass

        @dataclass
        class _V2TruncResult:
            truncated: bool
            truncated_content: str

        if self._truncator is None or not content:
            return _V2TruncResult(truncated=False, truncated_content=content)
        try:
            result = self._truncator.truncate(content, tool_name)
            return _V2TruncResult(
                truncated=bool(getattr(result, "is_truncated", False)),
                truncated_content=getattr(result, "content", content),
            )
        except Exception:
            return _V2TruncResult(truncated=False, truncated_content=content)


def extract_resource_map(depend_resource: Optional[Any]) -> Dict[str, List[Any]]:
    """从 BAIZE Resource pack 提取 resource_map（按 type 分组）。

    镜像 base_agent._tidy_resource 的逻辑，但作为独立函数可被 V2 dispatch 复用。
    返回格式：{"DBResource": [...], "RetrieverResource": [...], "AppResource": [...]}
    """
    if depend_resource is None:
        return {}

    resources_map: Dict[str, List[Any]] = defaultdict(list)
    _collect_resources(depend_resource, resources_map)
    return dict(resources_map)


def _collect_resources(resource: Any, out: Dict[str, List[Any]], visited: Optional[set] = None) -> None:
    """递归遍历 Resource pack，按 type 收集叶子节点。"""
    if resource is None:
        return
    if visited is None:
        visited = set()
    rid = id(resource)
    if rid in visited:
        return
    visited.add(rid)

    is_pack = getattr(resource, "is_pack", False)
    if is_pack:
        sub_resources = getattr(resource, "sub_resources", None) or []
        for item in sub_resources:
            _collect_resources(item, out, visited)
    else:
        r_type = resource.type() if callable(getattr(resource, "type", None)) else None
        if hasattr(r_type, "value"):
            r_type = r_type.value
        if isinstance(r_type, str):
            out[r_type].append(resource)

