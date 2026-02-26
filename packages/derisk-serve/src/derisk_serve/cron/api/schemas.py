"""Cron API schemas.

This module defines the Pydantic schemas for the cron API.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field, model_to_dict

from ..config import SERVE_APP_NAME_HUMP


class CronScheduleSchema(BaseModel):
    """Schema for cron schedule configuration."""

    model_config = ConfigDict(title=f"CronSchedule for {SERVE_APP_NAME_HUMP}")

    kind: str = Field(
        ...,
        description="The schedule kind (at, every, cron)",
        examples=["cron", "every", "at"],
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

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class CronPayloadSchema(BaseModel):
    """Schema for cron job payload."""

    model_config = ConfigDict(title=f"CronPayload for {SERVE_APP_NAME_HUMP}")

    kind: str = Field(
        ...,
        description="The payload kind (agentTurn)",
        examples=["agentTurn"],
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
    session_mode: Optional[str] = Field(
        default="isolated",
        description="Session mode for Agent execution: 'isolated' for new isolated session each run, 'shared' for shared session",
        examples=["isolated", "shared"],
    )
    conv_session_id: Optional[str] = Field(
        default=None,
        description="Conversation session ID for shared session mode or when created from a chat session",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class CronJobStateSchema(BaseModel):
    """Schema for cron job state."""

    model_config = ConfigDict(title=f"CronJobState for {SERVE_APP_NAME_HUMP}")

    next_run_at_ms: Optional[int] = Field(
        default=None,
        description="Next scheduled run time in milliseconds",
    )
    running_at_ms: Optional[int] = Field(
        default=None,
        description="Current run start time if running",
    )
    last_run_at_ms: Optional[int] = Field(
        default=None,
        description="Last run time in milliseconds",
    )
    last_status: Optional[str] = Field(
        default=None,
        description="Last execution status (ok, error, skipped)",
    )
    last_error: Optional[str] = Field(
        default=None,
        description="Last error message",
    )
    last_duration_ms: Optional[int] = Field(
        default=None,
        description="Last execution duration in milliseconds",
    )
    consecutive_errors: int = Field(
        default=0,
        description="Number of consecutive errors",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class ServeRequest(BaseModel):
    """Request schema for creating/updating a cron job."""

    model_config = ConfigDict(title=f"ServeRequest for {SERVE_APP_NAME_HUMP}")

    id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the job (auto-generated if not provided)",
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
    schedule: CronScheduleSchema = Field(
        ...,
        description="Schedule configuration",
    )
    payload: CronPayloadSchema = Field(
        ...,
        description="Job execution payload",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class ServerResponse(BaseModel):
    """Response schema for a cron job."""

    model_config = ConfigDict(
        title=f"ServerResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

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
        description="Whether to delete after one run",
    )
    schedule: CronScheduleSchema = Field(
        ...,
        description="Schedule configuration",
    )
    payload: CronPayloadSchema = Field(
        ...,
        description="Job execution payload",
    )
    state: CronJobStateSchema = Field(
        default_factory=CronJobStateSchema,
        description="Runtime state",
    )
    gmt_created: Optional[str] = Field(
        default=None,
        description="Record creation time",
    )
    gmt_modified: Optional[str] = Field(
        default=None,
        description="Record update time",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class CronStatusResponse(BaseModel):
    """Response schema for scheduler status."""

    model_config = ConfigDict(
        title=f"CronStatusResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

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

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)