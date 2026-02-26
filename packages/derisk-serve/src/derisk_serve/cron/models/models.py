"""Cron job database models and DAO.

This module defines the database entity and data access object for cron jobs.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Union

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import (
    CronJobStateSchema,
    CronPayloadSchema,
    CronScheduleSchema,
    ServeRequest,
    ServerResponse,
)
from ..config import SERVER_APP_TABLE_NAME, ServeConfig


class CronJobEntity(Model):
    """Database entity for cron jobs."""

    __tablename__ = SERVER_APP_TABLE_NAME

    # Primary key
    id = Column(String(64), primary_key=True, comment="Job unique identifier")

    # Basic info
    name = Column(String(255), nullable=False, comment="Job name")
    description = Column(Text, nullable=True, comment="Job description")
    enabled = Column(Integer, default=1, comment="Whether job is enabled (1=yes, 0=no)")
    delete_after_run = Column(Integer, default=0, comment="Delete after run (1=yes, 0=no)")

    # Schedule configuration
    schedule_kind = Column(String(32), nullable=False, comment="Schedule kind (at/every/cron)")
    schedule_at = Column(String(64), nullable=True, comment="ISO datetime for 'at' schedule")
    schedule_every_ms = Column(Integer, nullable=True, comment="Interval in ms for 'every' schedule")
    schedule_anchor_ms = Column(Integer, nullable=True, comment="Anchor time for 'every' schedule")
    schedule_expr = Column(String(128), nullable=True, comment="Cron expression for 'cron' schedule")
    schedule_tz = Column(String(64), nullable=True, comment="Timezone")

    # Payload configuration
    payload_kind = Column(String(32), nullable=False, comment="Payload kind (agentTurn/toolCall/systemEvent)")
    payload_data = Column(JSON, nullable=True, comment="Payload data as JSON")

    # Session configuration for agent execution
    session_mode = Column(String(16), default="isolated", comment="Session mode (isolated/shared)")
    conv_session_id = Column(String(64), nullable=True, comment="Conversation session ID for shared sessions")

    # Runtime state
    next_run_at_ms = Column(Integer, nullable=True, comment="Next run time in ms")
    running_at_ms = Column(Integer, nullable=True, comment="Current run start time in ms")
    last_run_at_ms = Column(Integer, nullable=True, comment="Last run time in ms")
    last_status = Column(String(32), nullable=True, comment="Last run status (ok/error/skipped)")
    last_error = Column(Text, nullable=True, comment="Last error message")
    last_duration_ms = Column(Integer, nullable=True, comment="Last run duration in ms")
    consecutive_errors = Column(Integer, default=0, comment="Consecutive error count")

    # Timestamps
    gmt_created = Column(
        DateTime,
        name="gmt_create",
        default=datetime.now,
        nullable=False,
        comment="Record creation time",
    )
    gmt_modified = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
        comment="Record update time",
    )

    def __repr__(self):
        return (
            f"CronJobEntity(id={self.id}, name='{self.name}', "
            f"enabled={self.enabled}, schedule_kind='{self.schedule_kind}', "
            f"payload_kind='{self.payload_kind}')"
        )


class ServeDao(BaseDao[CronJobEntity, ServeRequest, ServerResponse]):
    """Data Access Object for cron jobs."""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[ServeRequest, Dict[str, Any]]) -> CronJobEntity:
        """Convert a request to an entity.

        Args:
            request: The request object or dictionary.

        Returns:
            A CronJobEntity instance.
        """
        if isinstance(request, dict):
            request = ServeRequest(**request)

        entity = CronJobEntity()

        # Generate ID if not provided
        entity.id = request.id or uuid.uuid4().hex[:16]

        # Basic fields
        entity.name = request.name
        entity.description = request.description
        entity.enabled = 1 if request.enabled else 0
        entity.delete_after_run = 1 if request.delete_after_run else 0

        # Schedule fields
        schedule = request.schedule
        entity.schedule_kind = schedule.kind
        entity.schedule_at = schedule.at
        entity.schedule_every_ms = schedule.every_ms
        entity.schedule_anchor_ms = schedule.anchor_ms
        entity.schedule_expr = schedule.expr
        entity.schedule_tz = schedule.tz

        # Payload fields
        payload = request.payload
        entity.payload_kind = payload.kind
        entity.payload_data = {
            "message": payload.message,
            "agent_id": payload.agent_id,
            "tool_name": getattr(payload, "tool_name", None),
            "tool_args": getattr(payload, "tool_args", None),
            "text": getattr(payload, "text", None),
            "timeout_seconds": payload.timeout_seconds,
        }

        # Session configuration
        entity.session_mode = payload.session_mode or "isolated"
        entity.conv_session_id = payload.conv_session_id

        # Timestamps
        entity.gmt_created = datetime.now()
        entity.gmt_modified = datetime.now()

        return entity

    def to_request(self, entity: CronJobEntity) -> ServeRequest:
        """Convert an entity to a request.

        Args:
            entity: The entity to convert.

        Returns:
            A ServeRequest instance.
        """
        return ServeRequest(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            enabled=bool(entity.enabled),
            delete_after_run=bool(entity.delete_after_run) if entity.delete_after_run else None,
            schedule=CronScheduleSchema(
                kind=entity.schedule_kind,
                at=entity.schedule_at,
                every_ms=entity.schedule_every_ms,
                anchor_ms=entity.schedule_anchor_ms,
                expr=entity.schedule_expr,
                tz=entity.schedule_tz,
            ),
            payload=CronPayloadSchema(
                kind=entity.payload_kind,
                message=entity.payload_data.get("message") if entity.payload_data else None,
                agent_id=entity.payload_data.get("agent_id") if entity.payload_data else None,
                timeout_seconds=entity.payload_data.get("timeout_seconds") if entity.payload_data else None,
                session_mode=entity.session_mode,
                conv_session_id=entity.conv_session_id,
            ),
        )

    def to_response(self, entity: CronJobEntity) -> ServerResponse:
        """Convert an entity to a response.

        Args:
            entity: The entity to convert.

        Returns:
            A ServerResponse instance.
        """
        gmt_created_str = (
            entity.gmt_created.strftime("%Y-%m-%d %H:%M:%S")
            if entity.gmt_created
            else None
        )
        gmt_modified_str = (
            entity.gmt_modified.strftime("%Y-%m-%d %H:%M:%S")
            if entity.gmt_modified
            else None
        )

        return ServerResponse(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            enabled=bool(entity.enabled),
            delete_after_run=bool(entity.delete_after_run) if entity.delete_after_run else None,
            schedule=CronScheduleSchema(
                kind=entity.schedule_kind,
                at=entity.schedule_at,
                every_ms=entity.schedule_every_ms,
                anchor_ms=entity.schedule_anchor_ms,
                expr=entity.schedule_expr,
                tz=entity.schedule_tz,
            ),
            payload=CronPayloadSchema(
                kind=entity.payload_kind,
                message=entity.payload_data.get("message") if entity.payload_data else None,
                agent_id=entity.payload_data.get("agent_id") if entity.payload_data else None,
                timeout_seconds=entity.payload_data.get("timeout_seconds") if entity.payload_data else None,
                session_mode=entity.session_mode,
                conv_session_id=entity.conv_session_id,
            ),
            state=CronJobStateSchema(
                next_run_at_ms=entity.next_run_at_ms,
                running_at_ms=entity.running_at_ms,
                last_run_at_ms=entity.last_run_at_ms,
                last_status=entity.last_status,
                last_error=entity.last_error,
                last_duration_ms=entity.last_duration_ms,
                consecutive_errors=entity.consecutive_errors or 0,
            ),
            gmt_created=gmt_created_str,
            gmt_modified=gmt_modified_str,
        )

    def update_entity_from_request(
        self, entity: CronJobEntity, request: Union[ServeRequest, Dict[str, Any]]
    ) -> CronJobEntity:
        """Update an entity from a request.

        Args:
            entity: The entity to update.
            request: The request with updated values.

        Returns:
            The updated entity.
        """
        if isinstance(request, dict):
            request = ServeRequest(**request)

        if request.name is not None:
            entity.name = request.name
        if request.description is not None:
            entity.description = request.description
        if request.enabled is not None:
            entity.enabled = 1 if request.enabled else 0
        if request.delete_after_run is not None:
            entity.delete_after_run = 1 if request.delete_after_run else 0

        if request.schedule:
            schedule = request.schedule
            if schedule.kind is not None:
                entity.schedule_kind = schedule.kind
            if schedule.at is not None:
                entity.schedule_at = schedule.at
            if schedule.every_ms is not None:
                entity.schedule_every_ms = schedule.every_ms
            if schedule.anchor_ms is not None:
                entity.schedule_anchor_ms = schedule.anchor_ms
            if schedule.expr is not None:
                entity.schedule_expr = schedule.expr
            if schedule.tz is not None:
                entity.schedule_tz = schedule.tz

        if request.payload:
            payload = request.payload
            if payload.kind is not None:
                entity.payload_kind = payload.kind
            # Update payload data
            entity.payload_data = {
                "message": payload.message,
                "agent_id": payload.agent_id,
                "tool_name": getattr(payload, "tool_name", None),
                "tool_args": getattr(payload, "tool_args", None),
                "text": getattr(payload, "text", None),
                "timeout_seconds": payload.timeout_seconds,
            }
            # Update session configuration
            if payload.session_mode is not None:
                entity.session_mode = payload.session_mode
            if payload.conv_session_id is not None:
                entity.conv_session_id = payload.conv_session_id

        entity.gmt_modified = datetime.now()
        return entity

    def get_enabled_jobs(self) -> list[CronJobEntity]:
        """Get all enabled jobs.

        Returns:
            List of enabled job entities.
        """
        with self.session() as session:
            return session.query(CronJobEntity).filter(CronJobEntity.enabled == 1).all()