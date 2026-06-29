"""Materialize workspace_resource.physical_ref into AgentResource at runtime.

这是场景空间能力的命脉——把空间挂载的资源从 prompt 字符串装饰
物化成 Agent 可实际调用的工具/能力。
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from derisk.agent.resource.base import AgentResource

from derisk_serve.workspace.config import ServeConfig
from derisk_serve.workspace.service.service import WorkspaceService

logger = logging.getLogger(__name__)


@dataclass
class MaterializedResources:
    """物化结果：dynamic_resources 给 Agent 工具列表，extra_agents 给多 Agent 协作。"""

    dynamic_resources: List[AgentResource] = field(default_factory=list)
    extra_agents: List[Dict[str, Any]] = field(default_factory=list)


def _parse_config(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return {}


def _get_mcp_field(mcp_info: Any, key: str, default: Any = None) -> Any:
    """Support both dict-like mocks and ServerResponse objects."""
    if isinstance(mcp_info, dict):
        return mcp_info.get(key, default)
    return getattr(mcp_info, key, default)


def _materialize_mcp(physical_ref: str, config: Dict[str, Any]) -> Optional[AgentResource]:
    """type=mcp → AgentResource(type=mcp(derisk))，复用 get_mcp_info。"""
    # Lazy import: mcp_collect pulls heavy/optional runtime dependencies
    # (mcp, tenacity, derisk_app) that should not block importing this module.
    from derisk_serve.agent.resource.tool.mcp_collect import get_mcp_info

    mcp_info = get_mcp_info(physical_ref)
    if not mcp_info:
        logger.warning(f"mcp not found: {physical_ref}")
        return None
    return AgentResource.from_dict(
        {
            "type": "mcp(derisk)",
            "value": {
                "mcp_servers": _get_mcp_field(mcp_info, "mcp_servers", []),
                "headers": _get_mcp_field(mcp_info, "headers", {}),
                "source": _get_mcp_field(mcp_info, "source", "sse"),
                "timeout": _get_mcp_field(mcp_info, "timeout", 30),
            },
        }
    )


def _materialize_datasource(
    physical_ref: str, config: Dict[str, Any]
) -> Optional[AgentResource]:
    """type=data_source → AgentResource(type=datasource)。"""
    return AgentResource.from_dict(
        {"type": "datasource", "value": physical_ref, **config}
    )


def _materialize_skill(
    physical_ref: str, config: Dict[str, Any]
) -> Optional[AgentResource]:
    """type=skill → AgentResource(type=agent_skill)。"""
    return AgentResource.from_dict(
        {"type": "agent_skill", "value": physical_ref, **config}
    )


def _materialize_knowledge_space(
    physical_ref: str, config: Dict[str, Any]
) -> Optional[AgentResource]:
    """type=knowledge_space → AgentResource(type=knowledge)。"""
    return AgentResource.from_dict(
        {"type": "knowledge", "value": physical_ref, **config}
    )


def _materialize_app_as_extra_agent(
    physical_ref: str, config: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """type=app（子 Agent）→ extra_agents 项。"""
    return {"app_code": physical_ref, **config}


def _materialize_llm_model(
    physical_ref: str, config: Dict[str, Any]
) -> Optional[AgentResource]:
    """type=llm_model → 暂不物化（Agent 架构 llm 渠道是静态配置），返回 None。"""
    return None


# type → 物化函数分派表
_MATERIALIZE_DISPATCH = {
    "mcp": _materialize_mcp,
    "data_source": _materialize_datasource,
    "skill": _materialize_skill,
    "agent_skill": _materialize_skill,
    "knowledge_space": _materialize_knowledge_space,
    "app": _materialize_app_as_extra_agent,
    "llm_model": _materialize_llm_model,
}


def materialize_resources(system_app, workspace_id: int) -> MaterializedResources:
    """把 workspace 下所有 active 资源物化成 AgentResource / extra_agents。

    未知 type（slo/oncall_rotation/data_pipeline/bi_dashboard/code_repo/api_endpoint/
    environment/runbook_target）当前跳过——这些是场景专属逻辑资源，
    P2 阶段通过 ResourceManager.register_resource 注册自定义类型后再物化。
    """
    result = MaterializedResources()
    try:
        ws_service = WorkspaceService(system_app=system_app, config=ServeConfig())
        resources = ws_service.list_resources(workspace_id) or []
    except Exception as e:
        logger.warning(f"materializer list_resources failed: {e}")
        return result

    for r in resources:
        if not getattr(r, "is_active", True):
            continue
        rtype = r.type
        handler = _MATERIALIZE_DISPATCH.get(rtype)
        if handler is None:
            logger.warning(
                f"materializer skip unsupported type={rtype} name={r.name} "
                f"(P2 will register via ResourceManager)"
            )
            continue
        try:
            config = _parse_config(getattr(r, "config_json", None))
            physical_ref = getattr(r, "physical_ref", None)
            materialized = handler(physical_ref, config)
            if materialized is None:
                continue
            if rtype == "app":
                result.extra_agents.append(materialized)
            else:
                result.dynamic_resources.append(materialized)
        except Exception as e:
            logger.warning(
                f"materializer fail type={rtype} name={r.name}: {e}"
            )
    return result
