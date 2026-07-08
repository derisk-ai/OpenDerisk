"""Workspace context builder for agent prompt injection.

Builds a focused ``WorkspaceContextSnapshot`` that later tasks can render into
an agent system prompt. It intentionally keeps only the information an agent
needs to behave in a workspace-aware way:

- workspace identity and default app
- materialized resources (tools / sub-agents)
- optional current task
- optional playbook declaration DSL (when a task is bound to a playbook)
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional

from derisk_serve.workspace.materializer import (
    MaterializedResources,
    materialize_resources,
)
from derisk_serve.workspace.service.service import (
    WORKSPACE_SERVICE_COMPONENT_NAME,
    WorkspaceService,
)

# Task and playbook services are imported lazily below to avoid pulling in
# heavy endpoint/runtime dependencies (e.g. derisk_app) at module load time.


@dataclass
class WorkspaceContextSnapshot:
    """Lightweight snapshot of the context an agent needs inside a workspace."""

    workspace: Any
    materialized_resources: MaterializedResources
    task: Optional[Any] = None
    playbook_declaration: Optional[dict] = None
    user_id: Optional[str] = None
    workspace_id: Optional[int] = None
    task_id: Optional[int] = None
    playbooks: List[Any] = field(default_factory=list)
    active_tasks: List[Any] = field(default_factory=list)


def get_workspace_service(system_app) -> WorkspaceService:
    """Resolve the workspace service from ``system_app``."""
    return system_app.get_component(
        WORKSPACE_SERVICE_COMPONENT_NAME,
        WorkspaceService,
    )


def get_task_service(system_app):
    """Resolve the task service from ``system_app``."""
    from derisk_serve.task.service.service import (
        TASK_SERVICE_COMPONENT_NAME,
        TaskService,
    )

    return system_app.get_component(TASK_SERVICE_COMPONENT_NAME, TaskService)


def get_playbook_service(system_app):
    """Resolve the playbook service from ``system_app``."""
    from derisk_serve.playbook.service.service import (
        PLAYBOOK_SERVICE_COMPONENT_NAME,
        PlaybookService,
    )

    return system_app.get_component(
        PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService
    )


def build_workspace_context(
    system_app,
    workspace_id: int,
    user_id: Optional[str] = None,
    task_id: Optional[int] = None,
    mode: str = "lobby",
) -> WorkspaceContextSnapshot:
    """Build a workspace context snapshot.

    Args:
        system_app: The running ``SystemApp`` used to look up services.
        workspace_id: Identifier of the workspace to contextualize.
        user_id: Optional user identifier for personalization / auditing.
        task_id: Optional current task identifier. When provided, the task and
            its bound playbook declaration are loaded.
        mode: "lobby" for open workspace chat, "workbench" for task-focused work.
            Stored only for rendering; the snapshot itself is mode-agnostic.

    Returns:
        A ``WorkspaceContextSnapshot`` even when the workspace or task is not
        found, so callers can safely render a degraded summary.
    """
    ws_service = get_workspace_service(system_app)
    workspace = ws_service.get_by_id(workspace_id)

    materialized = materialize_resources(system_app, workspace_id)

    task = None
    playbook_declaration = None
    if task_id is not None:
        task_service = get_task_service(system_app)
        task = task_service.get_by_id(task_id)
        if task and getattr(task, "playbook_id", None):
            pb_service = get_playbook_service(system_app)
            playbook = pb_service.get_by_id(task.playbook_id)
            if playbook and getattr(playbook, "declaration", None):
                playbook_declaration = playbook.declaration
    active_tasks: List[Any] = []
    if mode == "lobby":
        try:
            task_service = get_task_service(system_app)
            from derisk_serve.task.api.schemas import TaskListFilter

            active_tasks = task_service.list_tasks(
                TaskListFilter(workspace_id=workspace_id)
            ) or []
            # Keep only tasks that are not terminal/archived
            active_tasks = [
                t
                for t in active_tasks
                if getattr(t, "status", None) not in {"done", "archived", "cancelled"}
            ]
        except Exception:
            pass

    playbooks: List[Any] = []
    if mode == "lobby":
        try:
            pb_service = get_playbook_service(system_app)
            from derisk_serve.playbook.api.schemas import PlaybookListFilter

            playbooks = pb_service.list_playbooks(
                PlaybookListFilter(workspace_id=workspace_id, is_active=True)
            ) or []
        except Exception:
            pass

    return WorkspaceContextSnapshot(
        workspace=workspace,
        materialized_resources=materialized,
        task=task,
        playbook_declaration=playbook_declaration,
        user_id=user_id,
        workspace_id=workspace_id,
        task_id=task_id,
        active_tasks=active_tasks,
        playbooks=playbooks,
    )


def render_workspace_context_summary(
    ctx: WorkspaceContextSnapshot,
    mode: str = "lobby",
) -> str:
    """Render the snapshot as a compact, human-readable summary for prompts."""
    ws = ctx.workspace
    name = (
        getattr(ws, "name", f"workspace_{ctx.workspace_id}")
        if ws
        else f"workspace_{ctx.workspace_id}"
    )
    lines = [
        f"# 当前空间：{name} (id={ctx.workspace_id})",
        f"模式：{mode}",
    ]

    materialized = ctx.materialized_resources
    if materialized:
        dynamic = getattr(materialized, "dynamic_resources", []) or []
        extra = getattr(materialized, "extra_agents", []) or []
        if dynamic:
            lines.append(f"已挂载动态资源：{len(dynamic)}")
        if extra:
            lines.append(f"已挂载子 Agent：{len(extra)}")

    if ctx.task:
        lines.append(
            f"当前任务：{getattr(ctx.task, 'title', '')} "
            f"(id={getattr(ctx.task, 'id', '')})"
        )

    if ctx.playbooks:
        pb_names = [getattr(pb, "name", str(pb)) for pb in ctx.playbooks]
        lines.append(f"可用剧本：{', '.join(pb_names)}")

    if ctx.playbook_declaration:
        skills = (ctx.playbook_declaration or {}).get("skills", []) or []
        if skills:
            skill_names = [
                s.get("name", str(s)) if isinstance(s, dict) else str(s)
                for s in skills
            ]
            lines.append(f"剧本技能：{', '.join(skill_names)}")

    return "\n".join(lines)
