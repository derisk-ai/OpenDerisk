"""Create cron job tool for Agent.

This tool allows Agents to create scheduled tasks during conversations.
"""

import logging
from typing import Optional

from derisk.agent.core.system_tool_registry import system_tool
from derisk.cron import (
    CronJobCreate,
    CronPayload,
    CronSchedule,
    PayloadKind,
    ScheduleKind,
    SessionMode,
)

logger = logging.getLogger(__name__)


def _get_cron_service():
    """Get the cron service from system app."""
    from ..config import SERVE_SERVICE_COMPONENT_NAME
    from ..service.service import Service

    from derisk._private.config import Config
    system_app = Config().SYSTEM_APP
    if not system_app:
        raise RuntimeError("SystemApp not initialized")

    service = system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)
    if not service:
        raise RuntimeError("Cron service not initialized")

    return service


@system_tool(
    name="create_cron_job",
    description="""Create a scheduled task (cron job) that will be executed automatically at specified times.

This tool allows you to set up recurring or one-time tasks for the user.

Schedule types:
- 'cron': Standard cron expression (e.g., '0 9 * * *' for every day at 9 AM)
- 'every': Fixed interval in minutes (e.g., every 60 minutes)
- 'at': One-time execution at a specific datetime (ISO format)

Session modes:
- 'isolated': Each execution creates a new isolated session (default)
- 'shared': Use a shared session across all executions

IMPORTANT: The 'message' parameter is the instruction/command that will be sent to the Agent when the task triggers. The Agent will receive this message and act on it. This is NOT a template - variables like {{now}} or {{date}} are NOT supported. Just write a clear instruction for the Agent to execute.

Examples:
1. Daily reminder: schedule_kind='cron', cron_expr='0 9 * * *', message='Remind the user to do daily check-in'
2. Hourly system check: schedule_kind='every', every_minutes=60, message='Check the system status and report any issues'
3. Current time reminder: schedule_kind='every', every_minutes=1, message='Tell the user the current time'
4. One-time greeting: schedule_kind='at', at_time='2024-12-25T09:00:00', message='Send a Christmas greeting to the user'
""",
    owner="derisk",
)
async def create_cron_job(
    name: str,
    schedule_kind: str,
    message: Optional[str] = None,
    agent_id: Optional[str] = None,
    cron_expr: Optional[str] = None,
    every_minutes: Optional[int] = None,
    at_time: Optional[str] = None,
    timezone: Optional[str] = None,
    enabled: bool = True,
    session_mode: str = "isolated",
    conv_session_id: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Create a scheduled cron job.

    Args:
        name: Human-readable name for the scheduled task.
        schedule_kind: Type of schedule ('cron', 'every', or 'at').
        message: The instruction to send to the Agent when the task triggers. Write a clear command for the Agent to execute (e.g., 'Tell the user the current time'). Do NOT use template variables like {{now}} - they are not supported.
        agent_id: Agent ID for execution (uses current agent if not specified).
        cron_expr: Cron expression (e.g., '0 9 * * *') for 'cron' schedule.
        every_minutes: Interval in minutes for 'every' schedule.
        at_time: ISO datetime string for 'at' schedule.
        timezone: Timezone for the schedule (default: system timezone).
        enabled: Whether the job is enabled immediately.
        session_mode: Session mode for agent execution ('isolated' or 'shared', default 'isolated').
        conv_session_id: Conversation session ID for shared session mode.
        description: Optional description of the job.

    Returns:
        A message indicating success or failure with job details.
    """
    try:
        # Validate schedule_kind
        try:
            schedule_kind_enum = ScheduleKind(schedule_kind)
        except ValueError:
            return f"Error: Invalid schedule_kind '{schedule_kind}'. Must be 'cron', 'every', or 'at'."

        # Validate session_mode
        try:
            session_mode_enum = SessionMode(session_mode)
        except ValueError:
            return f"Error: Invalid session_mode '{session_mode}'. Must be 'isolated' or 'shared'."

        # Build schedule
        schedule = CronSchedule(
            kind=schedule_kind_enum,
            tz=timezone,
        )

        if schedule_kind_enum == ScheduleKind.CRON:
            if not cron_expr:
                return "Error: cron_expr is required for 'cron' schedule."
            schedule.expr = cron_expr
        elif schedule_kind_enum == ScheduleKind.EVERY:
            if not every_minutes:
                return "Error: every_minutes is required for 'every' schedule."
            schedule.every_ms = every_minutes * 60 * 1000  # Convert to milliseconds
        elif schedule_kind_enum == ScheduleKind.AT:
            if not at_time:
                return "Error: at_time is required for 'at' schedule."
            schedule.at = at_time

        # Build payload - only agentTurn is supported
        payload = CronPayload(
            kind=PayloadKind.AGENT_TURN,
            message=message,
            agent_id=agent_id,
            session_mode=session_mode_enum,
            conv_session_id=conv_session_id,
        )

        # Validate message is provided
        if not message:
            return "Error: message is required."

        # Create the job
        job_create = CronJobCreate(
            name=name,
            description=description,
            enabled=enabled,
            schedule=schedule,
            payload=payload,
        )

        # Get service and create job
        service = _get_cron_service()
        job = await service.add_job(job_create)

        return f"Successfully created scheduled task '{name}' (ID: {job.id}). The task will be executed automatically according to the schedule: {schedule_kind}"

    except Exception as e:
        logger.error(f"Failed to create cron job: {e}")
        return f"Failed to create scheduled task: {str(e)}"