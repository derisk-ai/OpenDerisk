"""Cron service implementation.

This module provides the main service for cron job scheduling,
integrating APScheduler for job execution.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import List, Optional, Union

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from derisk.component import SystemApp
from derisk.cron import (
    CronJob,
    CronJobCreate,
    CronJobPatch,
    CronScheduler,
    CronStatusSummary,
    DistributedLock,
    PayloadKind,
    ScheduleKind,
)
from derisk.storage.metadata._base_dao import REQ, RES
from derisk_serve.core import BaseService
from .lock import MemoryLock
from ..api.schemas import (
    CronPayloadSchema,
    CronScheduleSchema,
    ServeRequest,
    ServerResponse,
)
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..models.models import CronJobEntity, ServeDao

logger = logging.getLogger(__name__)


class Service(BaseService[CronJobEntity, ServeRequest, ServerResponse], CronScheduler):
    """Cron scheduling service.

    This service manages cron job scheduling using APScheduler and provides
    methods for job CRUD operations and execution.
    """

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: ServeConfig,
        dao: Optional[ServeDao] = None,
        lock: Optional[DistributedLock] = None,
    ):
        """Initialize the cron service.

        Args:
            system_app: The system application instance.
            config: The service configuration.
            dao: Optional DAO instance for database operations.
            lock: Optional distributed lock instance.
        """
        self._config = config
        self._dao = dao
        self._lock = lock
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._running = False

        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service.

        Args:
            system_app: The system application instance.
        """
        super().init_app(system_app)
        self._dao = self._dao or ServeDao(self._config)
        self._lock = self._lock or MemoryLock()
        self._init_scheduler()

    def _init_scheduler(self) -> None:
        """Initialize the APScheduler instance."""
        self._scheduler = AsyncIOScheduler(
            job_defaults={
                "coalesce": self._config.coalesce,
                "max_instances": self._config.max_instances,
                "misfire_grace_time": self._config.misfire_grace_time,
            }
        )

    @property
    def dao(self) -> ServeDao:
        """Returns the internal DAO."""
        return self._dao

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._config

    def create(self, request: REQ) -> RES:
        """Create a new entity (not used, use add_job instead)."""
        raise NotImplementedError("Use add_job instead")

    async def start(self) -> None:
        """Start the scheduler."""
        if not self._config.enabled:
            logger.info("Cron scheduler is disabled")
            return

        if self._running:
            logger.warning("Cron scheduler is already running")
            return

        logger.info("Starting cron scheduler")
        self._scheduler.start()
        self._running = True

        # Recover existing jobs from database
        await self._recover_jobs()
        logger.info("Cron scheduler started successfully")

    def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return

        logger.info("Stopping cron scheduler")
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("Cron scheduler stopped")

    async def status(self) -> CronStatusSummary:
        """Get the current scheduler status.

        Returns:
            CronStatusSummary: Summary of scheduler state.
        """
        jobs = await self.list_jobs(include_disabled=True)
        enabled_jobs = [j for j in jobs if j.enabled]

        # Get next wake time
        next_wake = None
        if self._scheduler and self._running:
            try:
                next_run_time = self._scheduler.get_next_run_time()
                if next_run_time:
                    next_wake = int(next_run_time.timestamp() * 1000)
            except Exception:
                pass

        return CronStatusSummary(
            enabled=self._config.enabled,
            running=self._running,
            jobs=len(jobs),
            enabled_jobs=len(enabled_jobs),
            next_wake_at_ms=next_wake,
        )

    async def list_jobs(self, include_disabled: bool = False) -> List[CronJob]:
        """List all scheduled jobs.

        Args:
            include_disabled: Whether to include disabled jobs.

        Returns:
            List of cron jobs.
        """
        with self.dao.session() as session:
            query = session.query(CronJobEntity)
            if not include_disabled:
                query = query.filter(CronJobEntity.enabled == 1)
            entities = query.all()
            return [self._entity_to_cron_job(e) for e in entities]

    def list_job_responses(self, include_disabled: bool = False) -> List["ServerResponse"]:
        """List all job responses from database.

        Args:
            include_disabled: Whether to include disabled jobs.

        Returns:
            List of job responses.
        """
        with self.dao.session() as session:
            query = session.query(CronJobEntity)
            if not include_disabled:
                query = query.filter(CronJobEntity.enabled == 1)
            entities = query.all()
            return [self.dao.to_response(entity) for entity in entities]

    async def get_job(self, job_id: str) -> Optional[CronJob]:
        """Get a specific job by ID.

        Args:
            job_id: The unique identifier of the job.

        Returns:
            The cron job if found, None otherwise.
        """
        with self.dao.session() as session:
            entity = session.query(CronJobEntity).filter(
                CronJobEntity.id == job_id
            ).first()
            if entity:
                return self._entity_to_cron_job(entity)
            return None

    def get_job_response(self, job_id: str) -> Optional["ServerResponse"]:
        """Get a job response by ID.

        Args:
            job_id: The unique identifier of the job.

        Returns:
            The job response if found, None otherwise.
        """
        with self.dao.session() as session:
            entity = session.query(CronJobEntity).filter(
                CronJobEntity.id == job_id
            ).first()
            if entity:
                return self.dao.to_response(entity)
            return None

    async def add_job(self, job: Union[CronJobCreate, ServeRequest]) -> "ServerResponse":
        """Add a new cron job.

        Args:
            job: The job creation request.

        Returns:
            The created cron job response.
        """
        if isinstance(job, CronJobCreate):
            request = self._cron_job_create_to_request(job)
        else:
            request = job

        # Create entity
        entity = self.dao.from_request(request)

        # Save to database and convert to response within session
        with self.dao.session() as session:
            session.add(entity)
            session.commit()
            session.refresh(entity)
            job_id = entity.id
            # Convert entity to response while still in session
            response = self.dao.to_response(entity)

        # Schedule the job AFTER session is closed (transaction committed)
        # This ensures the job is visible in new transactions
        self._schedule_job_by_id(job_id)

        return response

    async def update_job(self, job_id: str, patch: Union[CronJobPatch, ServeRequest]) -> "ServerResponse":
        """Update an existing cron job.

        Args:
            job_id: The unique identifier of the job to update.
            patch: The patch request with fields to update.

        Returns:
            The updated cron job response.

        Raises:
            ValueError: If the job does not exist.
        """
        with self.dao.session() as session:
            entity = session.query(CronJobEntity).filter(
                CronJobEntity.id == job_id
            ).first()
            if not entity:
                raise ValueError(f"Job not found: {job_id}")

            # Convert patch to request if needed
            if isinstance(patch, CronJobPatch):
                request = self._cron_job_patch_to_request(patch, entity)
            else:
                request = patch

            # Update entity
            entity = self.dao.update_entity_from_request(entity, request)
            session.commit()
            session.refresh(entity)

            # Convert to response while still in session
            response = self.dao.to_response(entity)
            enabled = bool(entity.enabled)

        # Re-schedule the job (outside session)
        self._unschedule_job(job_id)
        if enabled:
            self._schedule_job_by_id(job_id)

        return response

    async def remove_job(self, job_id: str) -> bool:
        """Remove a cron job.

        Args:
            job_id: The unique identifier of the job to remove.

        Returns:
            True if the job was removed, False if it did not exist.
        """
        # Unschedule first
        self._unschedule_job(job_id)

        # Remove from database
        with self.dao.session() as session:
            result = session.query(CronJobEntity).filter(
                CronJobEntity.id == job_id
            ).delete()
            session.commit()
            return result > 0

    async def run_job(self, job_id: str, force: bool = False) -> bool:
        """Manually trigger a job execution.

        Args:
            job_id: The unique identifier of the job to run.
            force: If True, run even if the job is disabled.

        Returns:
            True if the job was triggered, False otherwise.
        """
        job = await self.get_job(job_id)
        if not job:
            logger.warning(f"Job not found: {job_id}")
            return False

        if not job.enabled and not force:
            logger.warning(f"Job is disabled: {job_id}")
            return False

        # Execute the job
        asyncio.create_task(self._execute_job_safe(job_id))
        return True

    async def _recover_jobs(self) -> None:
        """Recover jobs from database on scheduler start."""
        entities = self.dao.get_enabled_jobs()
        for entity in entities:
            try:
                self._schedule_job(entity)
                logger.info(f"Recovered job: {entity.id} ({entity.name})")
            except Exception as e:
                logger.error(f"Failed to recover job {entity.id}: {e}")

    def _schedule_job(self, entity: CronJobEntity) -> None:
        """Schedule a job with APScheduler.

        Args:
            entity: The job entity to schedule.
        """
        job_id = entity.id

        # Check if scheduler is available
        if not self._scheduler:
            logger.warning(f"Scheduler not initialized, cannot schedule job {job_id}")
            return

        # Create trigger based on schedule kind
        trigger = self._create_trigger(entity)
        if not trigger:
            logger.error(f"Failed to create trigger for job {job_id}")
            return

        # Check if scheduler is running
        if not self._running:
            logger.info(f"Scheduler not running yet, will schedule job {job_id} on recovery")
            # Even if not running, calculate and update next run time
            if trigger:
                from datetime import timezone as tz
                next_run = trigger.get_next_fire_time(None, datetime.now(tz.utc))
                if next_run:
                    with self.dao.session() as session:
                        db_entity = session.query(CronJobEntity).filter(
                            CronJobEntity.id == job_id
                        ).first()
                        if db_entity:
                            db_entity.next_run_at_ms = int(next_run.timestamp() * 1000)
                            session.commit()
                            logger.info(f"Updated next_run_at_ms for job {job_id} to {db_entity.next_run_at_ms}")
            return

        # Add job to scheduler
        self._scheduler.add_job(
            self._execute_job_safe,
            trigger=trigger,
            id=job_id,
            args=[job_id],
            replace_existing=True,
        )

        # Update next run time
        self._update_next_run_time_by_id(job_id)

    def _schedule_job_by_id(self, job_id: str) -> None:
        """Schedule a job by ID (fetches from database in a new session).

        Args:
            job_id: The job ID to schedule.
        """
        with self.dao.session() as session:
            entity = session.query(CronJobEntity).filter(
                CronJobEntity.id == job_id
            ).first()
            if entity:
                logger.info(f"Scheduling job {job_id}: kind={entity.schedule_kind}, enabled={entity.enabled}")
                self._schedule_job(entity)
            else:
                logger.warning(f"Job {job_id} not found in database for scheduling")

    def _unschedule_job(self, job_id: str) -> None:
        """Remove a job from the scheduler.

        Args:
            job_id: The job ID to unschedule.
        """
        if not self._scheduler:
            return

        try:
            self._scheduler.remove_job(job_id)
        except JobLookupError:
            pass  # Job wasn't scheduled

    def _create_trigger(self, entity: CronJobEntity):
        """Create an APScheduler trigger from entity.

        Args:
            entity: The job entity.

        Returns:
            An APScheduler trigger instance.
        """
        kind = ScheduleKind(entity.schedule_kind)

        if kind == ScheduleKind.AT:
            # One-time execution
            if not entity.schedule_at:
                return None
            run_time = datetime.fromisoformat(entity.schedule_at.replace("Z", "+00:00"))
            return DateTrigger(run_date=run_time, timezone=entity.schedule_tz)

        elif kind == ScheduleKind.EVERY:
            # Interval execution
            if not entity.schedule_every_ms:
                return None
            interval_seconds = entity.schedule_every_ms / 1000
            return IntervalTrigger(
                seconds=interval_seconds,
                timezone=entity.schedule_tz,
            )

        elif kind == ScheduleKind.CRON:
            # Cron expression
            if not entity.schedule_expr:
                return None
            fields = entity.schedule_expr.split()
            if len(fields) == 6:
                # 6-field format: second minute hour day month day_of_week
                return CronTrigger(
                    second=fields[0],
                    minute=fields[1],
                    hour=fields[2],
                    day=fields[3],
                    month=fields[4],
                    day_of_week=fields[5],
                    timezone=entity.schedule_tz,
                )
            else:
                # 5-field format: minute hour day month day_of_week
                return CronTrigger.from_crontab(
                    entity.schedule_expr,
                    timezone=entity.schedule_tz,
                )

        return None

    def _update_next_run_time_by_id(self, job_id: str) -> None:
        """Update the next run time in the database by job ID.

        Args:
            job_id: The job ID.
        """
        if not self._scheduler:
            logger.warning(f"Scheduler not initialized, cannot update next run time for {job_id}")
            return

        if not self._running:
            logger.warning(f"Scheduler not running, cannot update next run time for {job_id}")
            return

        try:
            job = self._scheduler.get_job(job_id)
            logger.info(f"Getting job {job_id} from scheduler: found={job is not None}, next_run_time={job.next_run_time if job else None}")
            if job and job.next_run_time:
                next_run_ms = int(job.next_run_time.timestamp() * 1000)
                with self.dao.session() as session:
                    db_entity = session.query(CronJobEntity).filter(
                        CronJobEntity.id == job_id
                    ).first()
                    if db_entity:
                        db_entity.next_run_at_ms = next_run_ms
                        session.commit()
                        logger.info(f"Updated next_run_at_ms for job {job_id} to {next_run_ms}")
            else:
                logger.warning(f"Job {job_id} not found in scheduler or has no next_run_time")
        except Exception as e:
            logger.warning(f"Failed to update next run time: {e}")

    async def _execute_job_safe(self, job_id: str) -> None:
        """Execute a job with error handling and state updates.

        Args:
            job_id: The job ID to execute.
        """
        start_time = time.time()
        job = await self.get_job(job_id)

        if not job:
            logger.warning(f"Job not found: {job_id}")
            return

        # Try to acquire lock
        async with self._lock.acquire(f"cron:{job_id}") as acquired:
            if not acquired:
                logger.info(f"Job {job_id} is already running on another instance")
                return

            # Update running state
            self._update_job_state(job_id, running=True)

            try:
                # Execute based on payload kind
                success = await self._execute_job(job)

                # Update success state
                duration_ms = int((time.time() - start_time) * 1000)
                self._update_job_state(
                    job_id,
                    running=False,
                    status="ok" if success else "error",
                    duration_ms=duration_ms,
                    error=None if success else "Execution failed",
                )

                # Handle delete_after_run
                if success and job.delete_after_run:
                    await self.remove_job(job_id)

            except Exception as e:
                # Update error state
                duration_ms = int((time.time() - start_time) * 1000)
                self._update_job_state(
                    job_id,
                    running=False,
                    status="error",
                    duration_ms=duration_ms,
                    error=str(e),
                )
                logger.error(f"Job {job_id} execution failed: {e}")

        # Update next run time
        if job.enabled:
            self._update_next_run_time_by_id(job_id)

    async def _execute_job(self, job: CronJob) -> bool:
        """Execute a job based on its payload kind.

        Args:
            job: The cron job to execute.

        Returns:
            True if execution succeeded, False otherwise.
        """
        payload = job.payload
        kind = PayloadKind(payload.kind)

        if kind == PayloadKind.AGENT_TURN:
            return await self._execute_agent_turn(job)
        else:
            logger.error(f"Unknown payload kind: {kind}")
            return False

    async def _execute_agent_turn(self, job: CronJob) -> bool:
        """Execute an Agent turn.

        Args:
            job: The cron job with Agent payload.

        Returns:
            True if execution succeeded.
        """
        from derisk.cron import SessionMode
        import uuid

        payload = job.payload
        logger.info(f"Executing Agent turn for job {job.id}: agent={payload.agent_id}, session_mode={payload.session_mode}")

        try:
            # Import here to avoid circular dependencies
            from derisk_serve.agent.agents.controller import multi_agents

            # Determine conversation session ID
            conv_uid = None
            if payload.session_mode == SessionMode.SHARED and payload.conv_session_id:
                # Use the shared session ID
                conv_uid = payload.conv_session_id
            else:
                # Generate a new conversation ID for isolated sessions
                conv_uid = str(uuid.uuid4())

            # Execute the agent chat
            # Note: gpts_name is the agent_id, user_query is the message
            result, agent_conv_id = await multi_agents.app_chat_v3(
                conv_uid=conv_uid,
                gpts_name=payload.agent_id,
                user_query=payload.message or "",
                stream=False,  # Non-streaming for cron jobs
                background_tasks=None,
            )

            # If using shared session and got a new session ID, update the job
            if payload.session_mode == SessionMode.SHARED and agent_conv_id:
                # Update the conv_session_id if it's different
                conv_session_id = session_id_by_conv_id(agent_conv_id)
                if conv_session_id != payload.conv_session_id:
                    with self.dao.session() as session:
                        entity = session.query(CronJobEntity).filter(
                            CronJobEntity.id == job.id
                        ).first()
                        if entity:
                            entity.conv_session_id = conv_session_id
                            session.commit()
                            logger.info(f"Updated conv_session_id for job {job.id} to {conv_session_id}")

            logger.info(f"Agent turn completed for job {job.id}, conv_uid={conv_uid}")
            return True
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            raise

    def _update_job_state(
        self,
        job_id: str,
        running: bool = False,
        status: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update job state in database.

        Args:
            job_id: The job ID.
            running: Whether the job is running.
            status: The execution status.
            duration_ms: The execution duration.
            error: The error message if any.
        """
        with self.dao.session() as session:
            entity = session.query(CronJobEntity).filter(
                CronJobEntity.id == job_id
            ).first()
            if not entity:
                return

            now_ms = int(time.time() * 1000)

            if running:
                entity.running_at_ms = now_ms
            else:
                entity.running_at_ms = None
                entity.last_run_at_ms = now_ms

            if status:
                entity.last_status = status
                if status == "error":
                    entity.consecutive_errors = (entity.consecutive_errors or 0) + 1
                else:
                    entity.consecutive_errors = 0

            if duration_ms is not None:
                entity.last_duration_ms = duration_ms

            if error is not None:
                entity.last_error = error

            session.commit()

    def _entity_to_cron_job(self, entity: CronJobEntity) -> CronJob:
        """Convert an entity to a CronJob model.

        Args:
            entity: The database entity.

        Returns:
            A CronJob instance.
        """
        from derisk.cron import CronPayload, CronSchedule, CronJobState, SessionMode

        return CronJob(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            enabled=bool(entity.enabled),
            delete_after_run=bool(entity.delete_after_run) if entity.delete_after_run else None,
            schedule=CronSchedule(
                kind=ScheduleKind(entity.schedule_kind),
                at=entity.schedule_at,
                every_ms=entity.schedule_every_ms,
                anchor_ms=entity.schedule_anchor_ms,
                expr=entity.schedule_expr,
                tz=entity.schedule_tz,
            ),
            payload=CronPayload(
                kind=PayloadKind(entity.payload_kind),
                message=entity.payload_data.get("message") if entity.payload_data else None,
                agent_id=entity.payload_data.get("agent_id") if entity.payload_data else None,
                timeout_seconds=entity.payload_data.get("timeout_seconds") if entity.payload_data else None,
                session_mode=SessionMode(entity.session_mode) if entity.session_mode else SessionMode.ISOLATED,
                conv_session_id=entity.conv_session_id,
            ),
            state=CronJobState(
                next_run_at_ms=entity.next_run_at_ms,
                running_at_ms=entity.running_at_ms,
                last_run_at_ms=entity.last_run_at_ms,
                last_status=entity.last_status,
                last_error=entity.last_error,
                last_duration_ms=entity.last_duration_ms,
                consecutive_errors=entity.consecutive_errors or 0,
            ),
            created_at=entity.gmt_created or datetime.now(),
            updated_at=entity.gmt_modified or datetime.now(),
        )

    def _cron_job_create_to_request(self, job: CronJobCreate) -> ServeRequest:
        """Convert CronJobCreate to ServeRequest.

        Args:
            job: The CronJobCreate instance.

        Returns:
            A ServeRequest instance.
        """
        from derisk.cron import SessionMode

        return ServeRequest(
            id=job.id,
            name=job.name,
            description=job.description,
            enabled=job.enabled,
            delete_after_run=job.delete_after_run,
            schedule=CronScheduleSchema(
                kind=job.schedule.kind.value,
                at=job.schedule.at,
                every_ms=job.schedule.every_ms,
                anchor_ms=job.schedule.anchor_ms,
                expr=job.schedule.expr,
                tz=job.schedule.tz,
            ),
            payload=CronPayloadSchema(
                kind=job.payload.kind.value,
                message=job.payload.message,
                agent_id=job.payload.agent_id,
                timeout_seconds=job.payload.timeout_seconds,
                session_mode=job.payload.session_mode.value if job.payload.session_mode else SessionMode.ISOLATED.value,
                conv_session_id=job.payload.conv_session_id,
            ),
        )

    def _cron_job_patch_to_request(
        self, patch: CronJobPatch, entity: CronJobEntity
    ) -> ServeRequest:
        """Convert CronJobPatch to ServeRequest.

        Args:
            patch: The CronJobPatch instance.
            entity: The existing entity for default values.

        Returns:
            A ServeRequest instance.
        """
        return ServeRequest(
            id=entity.id,
            name=patch.name if patch.name is not None else entity.name,
            description=patch.description if patch.description is not None else entity.description,
            enabled=patch.enabled if patch.enabled is not None else bool(entity.enabled),
            delete_after_run=patch.delete_after_run if patch.delete_after_run is not None else bool(entity.delete_after_run),
            schedule=CronScheduleSchema(
                kind=patch.schedule.kind.value if patch.schedule and patch.schedule.kind else entity.schedule_kind,
                at=patch.schedule.at if patch.schedule else entity.schedule_at,
                every_ms=patch.schedule.every_ms if patch.schedule else entity.schedule_every_ms,
                anchor_ms=patch.schedule.anchor_ms if patch.schedule else entity.schedule_anchor_ms,
                expr=patch.schedule.expr if patch.schedule else entity.schedule_expr,
                tz=patch.schedule.tz if patch.schedule else entity.schedule_tz,
            ),
            payload=CronPayloadSchema(
                kind=patch.payload.kind.value if patch.payload and patch.payload.kind else entity.payload_kind,
                message=patch.payload.message if patch.payload else (entity.payload_data.get("message") if entity.payload_data else None),
                agent_id=patch.payload.agent_id if patch.payload else (entity.payload_data.get("agent_id") if entity.payload_data else None),
                timeout_seconds=patch.payload.timeout_seconds if patch.payload else (entity.payload_data.get("timeout_seconds") if entity.payload_data else None),
                session_mode=patch.payload.session_mode.value if patch.payload and patch.payload.session_mode else entity.session_mode,
                conv_session_id=patch.payload.conv_session_id if patch.payload else entity.conv_session_id,
            ),
        )


def session_id_by_conv_id(conv_id: str) -> str:
    idx = conv_id.rfind("_")  # 找到最后一个下划线的位置
    if idx != -1:
        result = conv_id[:idx]  # 截取到该位置之前
    else:
        result = conv_id  # 没有下划线就原样返回

    return result  # 输出
