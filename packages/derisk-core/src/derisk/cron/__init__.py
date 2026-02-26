"""Cron scheduling module for Derisk.

This module provides types and interfaces for cron job scheduling,
including:
- Schedule types (at, every, cron)
- Job payloads (agentTurn, toolCall, systemEvent)
- Scheduler interface
- Distributed lock interface

Example:
    ```python
    from derisk.cron import (
        CronJob,
        CronSchedule,
        CronPayload,
        ScheduleKind,
        PayloadKind,
        CronScheduler,
    )

    # Create a cron job
    job = CronJob(
        id="my-job",
        name="Daily Report",
        schedule=CronSchedule(
            kind=ScheduleKind.CRON,
            expr="0 9 * * *",
            tz="Asia/Shanghai",
        ),
        payload=CronPayload(
            kind=PayloadKind.AGENT_TURN,
            agent_id="report-agent",
            message="Generate daily report",
        ),
    )
    ```
"""

from .lock import DistributedLock
from .scheduler import CronScheduler
from .types import (
    CronJob,
    CronJobCreate,
    CronJobPatch,
    CronJobState,
    CronPayload,
    CronSchedule,
    CronStatusSummary,
    PayloadKind,
    ScheduleKind,
    SessionMode,
)

__all__ = [
    # Types
    "ScheduleKind",
    "PayloadKind",
    "SessionMode",
    "CronSchedule",
    "CronPayload",
    "CronJobState",
    "CronJob",
    "CronJobCreate",
    "CronJobPatch",
    "CronStatusSummary",
    # Interfaces
    "CronScheduler",
    "DistributedLock",
]