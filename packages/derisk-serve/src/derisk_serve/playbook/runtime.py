"""Playbook runtime — executes a Task by driving the workspace Agent in the task's
conversation session, then materializes deliverables and deliveries.

MVP scope:
- Assemble playbook declaration + workspace/task context
- Send the initial user query via app_chat_v3 (async background chat)
- Poll conversation status until COMPLETE / FAILED
- Create Artifact(s) from the final output
- Create Delivery record(s) from declaration and attempt to send them
- Transition task status: running -> delivered / awaiting_human / failed
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks

from derisk.core.interface.message import HumanMessage
from derisk_serve.agent.agents.controller import multi_agents
from derisk_serve.playbook.service.service import (
    PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService,
)
from derisk_serve.workspace.materializer import materialize_resources
from derisk_serve.workspace.service.service import (
    WORKSPACE_SERVICE_COMPONENT_NAME, WorkspaceService,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 3.0
MAX_POLL_MINUTES = 30


async def run_task(
    system_app,
    task_id: int,
    user_code: Optional[str] = None,
    sys_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a task through its bound playbook.

    Args:
        system_app: SystemApp to look up services
        task_id: task id to execute
        user_code: optional user code for the agent run
        sys_code: optional system code

    Returns:
        dict with task_id, status, artifact_ids, delivery_ids
    """
    from derisk_serve.task.service.service import (
        TASK_SERVICE_COMPONENT_NAME, TaskService,
    )
    from derisk_serve.artifact.service.service import (
        ARTIFACT_SERVICE_COMPONENT_NAME, ArtifactService,
    )
    from derisk_serve.delivery.service.service import (
        DELIVERY_SERVICE_COMPONENT_NAME, DeliveryService,
    )
    from derisk_serve.intervention.service.service import (
        INTERVENTION_SERVICE_COMPONENT_NAME, InterventionService,
    )
    from derisk_serve.artifact.api.schemas import ArtifactRequest
    from derisk_serve.delivery.api.schemas import DeliveryRequest
    from derisk_serve.intervention.api.schemas import InterventionRequest

    task_service: TaskService = system_app.get_component(
        TASK_SERVICE_COMPONENT_NAME, TaskService,
    )
    playbook_service: PlaybookService = system_app.get_component(
        PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService,
    )
    workspace_service: WorkspaceService = system_app.get_component(
        WORKSPACE_SERVICE_COMPONENT_NAME, WorkspaceService,
    )
    artifact_service: ArtifactService = system_app.get_component(
        ARTIFACT_SERVICE_COMPONENT_NAME, ArtifactService,
    )
    delivery_service: DeliveryService = system_app.get_component(
        DELIVERY_SERVICE_COMPONENT_NAME, DeliveryService,
    )
    intervention_service: InterventionService = system_app.get_component(
        INTERVENTION_SERVICE_COMPONENT_NAME, InterventionService,
    )

    task = task_service.get_by_id(task_id)
    if not task:
        raise ValueError(f"task {task_id} not found")
    if not task.playbook_id:
        raise ValueError(f"task {task_id} has no playbook")
    playbook = playbook_service.get_by_id(task.playbook_id)
    if not playbook:
        raise ValueError(f"playbook {task.playbook_id} not found")
    workspace = workspace_service.get_by_id(task.workspace_id)
    if not workspace:
        raise ValueError(f"workspace {task.workspace_id} not found")

    declaration = playbook.declaration or {}
    app_code = workspace.default_agent_app_code or "chat_normal"

    # Build the initial user query from playbook + task
    user_query = _build_user_query(playbook, task, workspace, declaration)

    # Ensure task is running (idempotent when caller already transitioned it)
    if task.status != "running":
        try:
            task_service.start(task_id)
        except Exception as e:
            logger.warning(f"task start skipped or failed: {e}")

    # 物化空间资源，透传给 Agent
    materialized = materialize_resources(system_app, task.workspace_id)

    # Launch agent in the task's conversation session
    logger.info(
        f"[playbook runtime] starting task={task_id} conv={task.conv_session_id} "
        f"app={app_code} playbook={playbook.id}"
    )
    _, agent_conv_id = await multi_agents.app_chat_v3(
        conv_uid=task.conv_session_id,
        gpts_name=app_code,
        user_query=HumanMessage(content=user_query),
        background_tasks=BackgroundTasks(),
        user_code=user_code or str(task.created_by_user_id or "system"),
        sys_code=sys_code,
        workspace_id=task.workspace_id,
        task_id=task.id,
        dynamic_resources=materialized.dynamic_resources,
        extra_agents=materialized.extra_agents,
    )

    if not agent_conv_id:
        task_service.transition(task_id, "failed")
        return {"task_id": task_id, "status": "failed", "error": "agent did not return conv id"}

    # Poll until the agent run finishes
    final_state = await _poll_chat_completion(agent_conv_id)
    logger.info(f"[playbook runtime] task={task_id} final_state={final_state}")

    if final_state.get("state") == "FAILED":
        task_service.transition(task_id, "failed")
        return {"task_id": task_id, "status": "failed"}

    vis_final = final_state.get("vis_final") or final_state.get("user_answer") or ""

    # Create artifact(s) from deliverables
    artifact_ids: List[int] = []
    deliverables = declaration.get("deliverables") or []
    for idx, d in enumerate(deliverables):
        artifact_type = d.get("type", "report")
        title = d.get("title") or f"{playbook.name} — {artifact_type} #{idx + 1}"
        artifact = artifact_service.create(ArtifactRequest(
            task_id=task.id,
            workspace_id=task.workspace_id,
            type=artifact_type,
            title=title,
            content_text=str(vis_final)[:16000],
            created_by_agent=app_code,
            provenance={
                "playbook_id": playbook.id,
                "playbook_name": playbook.name,
                "agent_conv_id": agent_conv_id,
                "deliverable_index": idx,
            },
        ))
        artifact_ids.append(artifact.id)

    # Create deliveries from deliverable declarations
    delivery_ids: List[int] = []
    for idx, d in enumerate(deliverables):
        for delivery_decl in d.get("delivery") or []:
            if delivery_decl.get("category") != "notify":
                continue
            delivery = delivery_service.create(DeliveryRequest(
                artifact_id=artifact_ids[idx] if idx < len(artifact_ids) else None,
                task_id=task.id,
                workspace_id=task.workspace_id,
                category="notify",
                channel=delivery_decl.get("channel", "in_app"),
                target=delivery_decl.get("target", ""),
                title=f"[{playbook.name}] {d.get('type', 'report')} delivered",
                message=str(vis_final)[:8000],
                format=delivery_decl.get("format", "message_card"),
                require_intervention=delivery_decl.get("require_intervention", "none"),
            ))
            delivery_ids.append(delivery.id)
            # Attempt immediate send; failures are recorded on the record
            try:
                delivery_service.send(delivery.id)
            except Exception as e:
                logger.warning(f"delivery send failed for {delivery.id}: {e}")

    # If any delivery requires review, raise an intervention and stop at awaiting_human
    requires_review = any(
        d.get("require_intervention") == "review"
        for dlv in deliverables
        for d in dlv.get("delivery") or []
    )
    if requires_review:
        try:
            intervention_service.create(InterventionRequest(
                task_id=task.id,
                workspace_id=task.workspace_id,
                type="review",
                requested_by="system",
                question={
                    "playbook_id": playbook.id,
                    "playbook_name": playbook.name,
                    "reason": "delivery requires human review before close",
                },
                context={"agent_conv_id": agent_conv_id, "artifact_ids": artifact_ids},
            ))
        except Exception as e:
            logger.warning(f"failed to create review intervention: {e}")
        task_service.transition(task_id, "awaiting_human")
        return {
            "task_id": task_id,
            "status": "awaiting_human",
            "agent_conv_id": agent_conv_id,
            "artifact_ids": artifact_ids,
            "delivery_ids": delivery_ids,
        }

    # Normal path: mark delivered
    task_service.transition(task_id, "delivered")
    return {
        "task_id": task_id,
        "status": "delivered",
        "agent_conv_id": agent_conv_id,
        "artifact_ids": artifact_ids,
        "delivery_ids": delivery_ids,
    }


def _build_user_query(
    playbook: Any, task: Any, workspace: Any, declaration: Dict[str, Any],
) -> str:
    """Build the initial user prompt that drives the Agent to execute the playbook."""
    lines: List[str] = [
        f"Execute playbook: {playbook.name}",
        f"Workspace: {workspace.name} (scenario: {getattr(workspace, 'scenario_type', '-')})",
        f"Task #{task.id}: {task.title}",
    ]
    if task.description:
        lines.append(f"Description: {task.description}")

    skills = declaration.get("skills") or []
    if skills:
        lines.append(f"Required skills: {', '.join(str(s) for s in skills)}")

    ctx = declaration.get("context") or {}
    resources = ctx.get("resources") or []
    if resources:
        lines.append(f"Bound resources: {', '.join(str(r) for r in resources)}")

    deliverables = declaration.get("deliverables") or []
    if deliverables:
        lines.append("Expected deliverables:")
        for d in deliverables:
            lines.append(f"- {d.get('type')}: {d.get('title', '')}")

    distill = declaration.get("distill") or {}
    if distill.get("forced"):
        lines.append("Note: this task requires distilling outcomes into a workspace asset before closing.")

    return "\n".join(lines)


async def _poll_chat_completion(agent_conv_id: str) -> Dict[str, Any]:
    """Poll query_chat until the agent run reaches a final state."""
    max_attempts = int((MAX_POLL_MINUTES * 60) / POLL_INTERVAL_SECONDS)
    for attempt in range(max_attempts):
        try:
            result = await multi_agents.query_chat(conv_id=agent_conv_id)
            if result is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue
            vis_final, user_answer, current_vis_render, is_final, state = result
            if state in ("COMPLETE", "FAILED") or is_final:
                return {
                    "state": state,
                    "is_final": is_final,
                    "vis_final": vis_final,
                    "user_answer": user_answer,
                    "vis_render": current_vis_render,
                }
        except Exception as e:
            logger.warning(f"playbook runtime poll error: {e}")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return {"state": "FAILED", "error": "polling timeout"}
