"""Workspace context builder — assembles 'workspace memory' for Agent specialization.

Given a workspace_id and (optional) task, returns a dict summary containing:
- workspace basic info + members
- recent N tasks of the same type (so the Agent sees prior similar work)
- recently produced assets (historical_artifact/case) — the 'memory'
- bound resources (data sources / knowledge spaces)

The playbook_runtime injects this into ext_info.workspace_context before
calling app_chat, so the prompt renderer can stitch it into the system prompt.
"""
import logging
from typing import Any, Dict, List, Optional

from derisk_serve.workspace.materializer import materialize_resources
from derisk_serve.workspace.service.service import (
    WORKSPACE_SERVICE_COMPONENT_NAME,
    WorkspaceService,
)

logger = logging.getLogger(__name__)


def build_workspace_context(
    system_app, workspace_id: int, task_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Build workspace context dict for Agent prompt injection.

    Args:
        system_app: SystemApp instance to look up serve components
        workspace_id: workspace id
        task_id: optional current task id — its details/artifacts/interventions
                 are injected so the Agent enters task-specific context.

    Returns:
        dict with keys: workspace, members, resources, current_task,
                        recent_tasks, recent_assets, task_artifacts,
                        task_interventions, materialized
    """
    context: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "workspace": None,
        "members": [],
        "resources": [],
        "current_task": None,
        "recent_tasks": [],
        "recent_assets": [],
        "task_artifacts": [],
        "task_interventions": [],
        "materialized": {"dynamic_resources": [], "extra_agents": []},
    }

    try:
        ws_service = system_app.get_component(
            WORKSPACE_SERVICE_COMPONENT_NAME, WorkspaceService,
        )
        ws = ws_service.get_by_id(workspace_id)
        if ws:
            context["workspace"] = {
                "id": ws.id,
                "workspace_code": getattr(ws, "workspace_code", None),
                "name": ws.name,
                "description": ws.description,
                "scenario_type": getattr(ws, "scenario_type", None),
                "default_agent_app_code": getattr(ws, "default_agent_app_code", None),
            }
        members = ws_service.list_members(workspace_id)
        context["members"] = [
            {"user_id": m.user_id, "role": m.role} for m in (members or [])
        ]
        resources = ws_service.list_resources(workspace_id)
        context["resources"] = [
            {
                "type": r.type, "name": r.name,
                "category": getattr(r, "category", None),
                "physical_ref": getattr(r, "physical_ref", None),
            }
            for r in (resources or [])
            if getattr(r, "is_active", True)
        ]
        # 物化资源为 AgentResource（运行时给 Agent 工具列表用）
        try:
            materialized = materialize_resources(system_app, workspace_id)
            context["materialized"] = {
                "dynamic_resources": materialized.dynamic_resources,
                "extra_agents": materialized.extra_agents,
            }
        except Exception as e:
            logger.warning(f"materialize_resources failed: {e}")
            context["materialized"] = {"dynamic_resources": [], "extra_agents": []}
    except Exception as e:
        logger.warning(f"context_builder workspace lookup failed: {e}")

    # current task + recent tasks of same type
    try:
        from derisk_serve.task.service.service import (
            TASK_SERVICE_COMPONENT_NAME, TaskService,
        )
        from derisk_serve.task.api.schemas import TaskListFilter
        task_service: TaskService = system_app.get_component(
            TASK_SERVICE_COMPONENT_NAME, TaskService,
        )
        task_type = None
        if task_id is not None:
            current = task_service.get_by_id(task_id)
            if current:
                task_type = current.type
                context["current_task"] = {
                    "id": current.id,
                    "title": current.title,
                    "type": current.type,
                    "status": current.status,
                    "description": current.description,
                    "triggered_by": current.triggered_by,
                    "playbook_id": current.playbook_id,
                    "conv_session_id": current.conv_session_id,
                }
        f = TaskListFilter(workspace_id=workspace_id, limit=10)
        tasks = task_service.list_tasks(f)
        if task_type:
            tasks = [t for t in tasks if t.type == task_type and t.id != task_id][:5]
        else:
            tasks = tasks[:5]
        context["recent_tasks"] = [
            {
                "id": t.id, "title": t.title, "type": t.type,
                "status": t.status, "triggered_by": t.triggered_by,
                "gmt_created": t.gmt_created,
            }
            for t in tasks
        ]
    except Exception as e:
        logger.warning(f"context_builder task lookup failed: {e}")

    # task artifacts
    try:
        from derisk_serve.artifact.service.service import (
            ARTIFACT_SERVICE_COMPONENT_NAME, ArtifactService,
        )
        from derisk_serve.artifact.api.schemas import ArtifactListFilter
        artifact_service: ArtifactService = system_app.get_component(
            ARTIFACT_SERVICE_COMPONENT_NAME, ArtifactService,
        )
        if task_id is not None:
            artifacts = artifact_service.list_artifacts(ArtifactListFilter(
                workspace_id=workspace_id, task_id=task_id, limit=20,
            ))
            context["task_artifacts"] = [
                {
                    "id": a.id, "type": a.type, "title": a.title,
                    "current_version": a.current_version,
                }
                for a in artifacts
            ]
    except Exception as e:
        logger.warning(f"context_builder artifact lookup failed: {e}")

    # task interventions (pending reviews the Agent should know about)
    try:
        from derisk_serve.intervention.service.service import (
            INTERVENTION_SERVICE_COMPONENT_NAME, InterventionService,
        )
        from derisk_serve.intervention.api.schemas import InterventionListFilter
        intervention_service: InterventionService = system_app.get_component(
            INTERVENTION_SERVICE_COMPONENT_NAME, InterventionService,
        )
        if task_id is not None:
            interventions = intervention_service.list_interventions(InterventionListFilter(
                workspace_id=workspace_id, task_id=task_id, limit=20,
            ))
            context["task_interventions"] = [
                {
                    "id": i.id, "type": i.type, "status": i.status,
                    "requested_by": i.requested_by,
                    "question": i.question,
                }
                for i in interventions
            ]
    except Exception as e:
        logger.warning(f"context_builder intervention lookup failed: {e}")

    # recent assets (memory)
    try:
        from derisk_serve.workspace_asset.service.service import (
            ASSET_SERVICE_COMPONENT_NAME, AssetService,
        )
        from derisk_serve.workspace_asset.api.schemas import AssetListFilter
        asset_service: AssetService = system_app.get_component(
            ASSET_SERVICE_COMPONENT_NAME, AssetService,
        )
        assets = asset_service.list_assets(AssetListFilter(
            workspace_id=workspace_id, is_published=True, limit=5,
        ))
        context["recent_assets"] = [
            {
                "id": a.id, "type": a.type, "name": a.name,
                "description": a.description,
                "source_task_id": a.source_task_id,
                "tags": a.tags,
            }
            for a in assets
        ]
    except Exception as e:
        logger.warning(f"context_builder asset lookup failed: {e}")

    return context


def render_workspace_context_summary(ctx: Dict[str, Any]) -> str:
    """Render the workspace context dict as a compact text summary
    suitable for splicing into a system prompt.
    """
    if not ctx:
        return ""
    lines: List[str] = []
    ws = ctx.get("workspace") or {}
    if ws:
        lines.append(
            f"# Workspace Context\n"
            f"- Name: {ws.get('name', '')}\n"
            f"- Description: {ws.get('description', '')}\n"
            f"- Scenario: {ws.get('scenario_type', '')}"
        )
    members = ctx.get("members") or []
    if members:
        lines.append(
            "- Members: " + ", ".join(
                f"user_{m['user_id']}({m['role']})" for m in members
            )
        )
    resources = ctx.get("resources") or []
    if resources:
        lines.append("# Bound Resources")
        for r in resources:
            lines.append(
                f"- [{r.get('type')}] {r.get('name')} → {r.get('physical_ref')}"
            )

    current_task = ctx.get("current_task")
    if current_task:
        lines.append("# Current Task")
        lines.append(
            f"- #{current_task['id']} {current_task['title']} "
            f"({current_task['type']}/{current_task['status']})"
        )
        if current_task.get("description"):
            lines.append(f"- Description: {current_task['description']}")

    task_artifacts = ctx.get("task_artifacts") or []
    if task_artifacts:
        lines.append("# Task Artifacts")
        for a in task_artifacts:
            lines.append(f"- [{a['type']}] {a['title']} (v{a.get('current_version', 1)})")

    task_interventions = ctx.get("task_interventions") or []
    pending = [i for i in task_interventions if i.get("status") == "requested"]
    if pending:
        lines.append("# Pending Human Interventions")
        for i in pending:
            lines.append(
                f"- #{i['id']} requested by {i.get('requested_by')}: "
                f"{i.get('question', {})}"
            )

    recent_tasks = ctx.get("recent_tasks") or []
    if recent_tasks:
        lines.append("# Recent Similar Tasks")
        for t in recent_tasks:
            lines.append(
                f"- #{t['id']} {t['title']} ({t['type']}/{t['status']}, {t.get('gmt_created', '')})"
            )
    recent_assets = ctx.get("recent_assets") or []
    if recent_assets:
        lines.append("# Workspace Memory (recent Assets)")
        for a in recent_assets:
            tags = ",".join(a.get("tags") or [])
            lines.append(
                f"- [{a['type']}] {a['name']} (id={a['id']}, tags={tags})"
            )
    return "\n".join(lines)
