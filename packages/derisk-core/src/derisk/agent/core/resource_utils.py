"""extract_resource_map: 从 Resource pack 提取 resource_map（按 type 分组）。

镜像 base_agent._tidy_resource 的逻辑，作为独立函数可被 sub_agent 工具复用。
返回格式：{"DBResource": [...], "RetrieverResource": [...], "AppResource": [...]}
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional


def extract_resource_map(depend_resource: Optional[Any]) -> Dict[str, List[Any]]:
    """从 Resource pack 提取 resource_map（按 type 分组）。

    递归遍历 Resource pack，按 type 收集叶子节点。
    镜像 base_agent._tidy_resource 的逻辑，作为独立函数可被 sub_agent 工具复用。

    Args:
        depend_resource: Resource pack 或单个 Resource，可为 None。

    Returns:
        按 type 分组的 resource map，如 {"DBResource": [...], "RetrieverResource": [...]}。
        无资源时返回空 dict。
    """
    if depend_resource is None:
        return {}

    resources_map: Dict[str, List[Any]] = defaultdict(list)
    _collect_resources(depend_resource, resources_map)
    return dict(resources_map)


def _collect_resources(
    resource: Any,
    out: Dict[str, List[Any]],
    visited: Optional[set] = None,
) -> None:
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
