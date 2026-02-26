"""Cron types and models for the scheduler.

This module defines the core types used for cron job scheduling,
including schedule configurations, job payloads, and job states.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class ScheduleKind(str, Enum):
    """Schedule kind for cron jobs."""

    AT = "at"          # One-time execution at a specific time
    EVERY = "every"    # Fixed interval execution
    CRON = "cron"      # Cron expression execution


class PayloadKind(str, Enum):
    """Payload kind for cron jobs."""

    AGENT_TURN = "agentTurn"  # Call an Agent


class SessionMode(str, Enum):
    """Session mode for Agent execution in cron jobs."""

    ISOLATED = "isolated"  # Create a new isolated session for each run (default)
    SHARED = "shared"      # Use a shared session across runs


class CronSchedule(BaseModel):
    """Schedule configuration for a cron job.

    Supports three scheduling strategies:
    - at: One-time execution at a specific datetime
    - every: Fixed interval execution with optional anchor time
    - cron: Standard cron expression
    """

    kind: ScheduleKind = Field(
        ...,
        description="The schedule kind (at, every, cron)",
    )
    at: Optional[str] = Field(
        default=None,
        description="ISO datetime string for one-time execution",
        examples=["2024-01-01T00:00:00Z"],
    )
    every_ms: Optional[int] = Field(
        default=None,
        description="Interval in milliseconds for 'every' schedule",
        examples=[60000, 3600000],
    )
    anchor_ms: Optional[int] = Field(
        default=None,
        description="Anchor time in milliseconds for 'every' schedule alignment",
    )
    expr: Optional[str] = Field(
        default=None,
        description="Cron expression for 'cron' schedule",
        examples=["0 * * * *", "0 0 * * *"],
    )
    tz: Optional[str] = Field(
        default=None,
        description="Timezone for the schedule",
        examples=["UTC", "Asia/Shanghai"],
    )


class CronPayload(BaseModel):
    """Payload for a cron job execution.

    Executes an Agent conversation with a message.
    """

    kind: PayloadKind = Field(
        ...,
        description="The payload kind (agentTurn)",
    )
    message: Optional[str] = Field(
        default=None,
        description="Message for Agent turn execution",
    )
    agent_id: Optional[str] = Field(
        default=None,
        description="Agent ID for Agent turn execution",
    )
    timeout_seconds: Optional[int] = Field(
        default=None,
        description="Timeout in seconds for job execution",
    )
    session_mode: Optional[SessionMode] = Field(
        default=SessionMode.ISOLATED,
        description="Session mode for Agent execution: 'isolated' for new isolated session each run, 'shared' for shared session",
    )
    conv_session_id: Optional[str] = Field(
        default=None,
        description="Conversation session ID for shared session mode or when created from a chat session",
    )


class CronJobState(BaseModel):
    """Runtime state for a cron job."""

    next_run_at_ms: Optional[int] = Field(
        default=None,
        description="Next scheduled run time in milliseconds since epoch",
    )
    running_at_ms: Optional[int] = Field(
        default=None,
        description="Current run start time in milliseconds since epoch (if running)",
    )
    last_run_at_ms: Optional[int] = Field(
        default=None,
        description="Last run time in milliseconds since epoch",
    )
    last_status: Optional[Literal["ok", "error", "skipped"]] = Field(
        default=None,
        description="Last execution status",
    )
    last_error: Optional[str] = Field(
        default=None,
        description="Last error message if status is 'error'",
    )
    last_duration_ms: Optional[int] = Field(
        default=None,
        description="Last execution duration in milliseconds",
    )
    consecutive_errors: int = Field(
        default=0,
        description="Number of consecutive execution errors",
    )


class CronJob(BaseModel):
    """Complete cron job definition."""

    id: str = Field(
        ...,
        description="Unique identifier for the job",
    )
    name: str = Field(
        ...,
        description="Human-readable name for the job",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the job",
    )
    enabled: bool = Field(
        default=True,
        description="Whether the job is enabled",
    )
    delete_after_run: Optional[bool] = Field(
        default=None,
        description="Whether to delete the job after one successful run (for 'at' schedule)",
    )
    schedule: CronSchedule = Field(
        ...,
        description="Schedule configuration",
    )
    payload: CronPayload = Field(
        ...,
        description="Job execution payload",
    )
    state: CronJobState = Field(
        default_factory=CronJobState,
        description="Runtime state",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Job creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="Job last update timestamp",
    )


class CronJobCreate(BaseModel):
    """Request model for creating a cron job."""

    id: Optional[str] = Field(
        default=None,
        description="Optional unique identifier (auto-generated if not provided)",
    )
    name: str = Field(
        ...,
        description="Human-readable name for the job",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the job",
    )
    enabled: bool = Field(
        default=True,
        description="Whether the job is enabled",
    )
    delete_after_run: Optional[bool] = Field(
        default=None,
        description="Whether to delete after one run",
    )
    schedule: CronSchedule = Field(
        ...,
        description="Schedule configuration",
    )
    payload: CronPayload = Field(
        ...,
        description="Job execution payload",
    )


class CronJobPatch(BaseModel):
    """Request model for patching a cron job."""

    name: Optional[str] = Field(
        default=None,
        description="Human-readable name for the job",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the job",
    )
    enabled: Optional[bool] = Field(
        default=None,
        description="Whether the job is enabled",
    )
    delete_after_run: Optional[bool] = Field(
        default=None,
        description="Whether to delete after one run",
    )
    schedule: Optional[CronSchedule] = Field(
        default=None,
        description="Schedule configuration",
    )
    payload: Optional[CronPayload] = Field(
        default=None,
        description="Job execution payload",
    )


class CronStatusSummary(BaseModel):
    """Summary of the cron scheduler status."""

    enabled: bool = Field(
        ...,
        description="Whether the scheduler is enabled",
    )
    running: bool = Field(
        ...,
        description="Whether the scheduler is running",
    )
    jobs: int = Field(
        ...,
        description="Total number of jobs",
    )
    enabled_jobs: int = Field(
        ...,
        description="Number of enabled jobs",
    )
    next_wake_at_ms: Optional[int] = Field(
        default=None,
        description="Next scheduled wake time in milliseconds",
    )