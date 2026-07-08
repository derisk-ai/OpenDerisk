"""Job engine service: submit / claim / ack / nack + worker loop.

A single JobService runs one worker loop (asyncio background task in the web
process) that polls `derisk_serve_job`, claims pending jobs (SKIP LOCKED on
PG/MySQL, atomic conditional UPDATE on SQLite), dispatches to registered
handlers by `job_type`, and ack/nacks on completion.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata._base_dao import REQ, RES  # noqa: F401
from derisk_serve.core import BaseService

from ..api.schemas import ServeRequest, ServeResponse
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..models.models import JobDao, JobEntity

logger = logging.getLogger(__name__)

JobHandler = Callable[[JobEntity], Awaitable[Optional[Dict[str, Any]]]]


class Service(BaseService[JobEntity, ServeRequest, ServeResponse]):
    """Persistent job engine service."""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: Optional[ServeConfig] = None,
        dao: Optional[JobDao] = None,
    ):
        # Set all attributes BEFORE super().__init__ — BaseComponent.__init__
        # calls init_app() when system_app is not None, so the attributes must
        # exist by then.
        self._config: Optional[ServeConfig] = config
        self._dao: Optional[JobDao] = dao
        self._handlers: Dict[str, JobHandler] = {}
        # Per-job-type metadata: {job_type: {"description": str, "params_schema": dict|None}}
        self._handler_meta: Dict[str, Dict[str, Any]] = {}
        self._worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self._worker_tags: set = set(
            t.strip() for t in (config.worker_tags or "default").split(",") if t.strip()
        ) if config else {"default"}
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._in_flight: Dict[str, asyncio.Task] = {}
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp):
        super().init_app(system_app)
        if self._dao is None:
            self._dao = JobDao(self._config)

    @property
    def dao(self) -> JobDao:
        if self._dao is None:
            self._dao = JobDao(self._config)
        return self._dao

    @property
    def config(self) -> ServeConfig:
        if self._config is None:
            self._config = ServeConfig()
        return self._config

    # ---- handler registry ----
    def register_handler(
        self,
        job_type: str,
        handler: JobHandler,
        *,
        description: str = "",
        params_schema: Optional[type] = None,
    ) -> None:
        """Register a handler for a job_type.

        params_schema: optional pydantic BaseModel class declaring the
        expected payload fields. Exposed via GET /jobs/types so the admin UI
        can render a dynamic form. The handler is still free to read
        job.payload directly.
        """
        if job_type in self._handlers and self._handlers[job_type] is not handler:
            logger.warning("overwriting existing handler for job_type=%s", job_type)
        self._handlers[job_type] = handler
        schema_dict = None
        if params_schema is not None:
            try:
                schema_dict = params_schema.model_json_schema()
            except Exception as e:
                logger.warning("could not derive schema for %s: %s", job_type, e)
        self._handler_meta[job_type] = {
            "description": description,
            "params_schema": schema_dict,
        }
        logger.info("registered job handler: %s (schema=%s)", job_type, bool(schema_dict))

    def handler_meta(self) -> List[Dict[str, Any]]:
        """Expose all registered job types + their param schemas for the admin
        UI (GET /jobs/types)."""
        return [
            {
                "job_type": jt,
                "description": self._handler_meta.get(jt, {}).get("description", ""),
                "params_schema": self._handler_meta.get(jt, {}).get("params_schema"),
            }
            for jt in self._handlers.keys()
        ]

    def handler_types(self) -> List[str]:
        return list(self._handlers.keys())

    def _subscribed_types(self) -> List[str]:
        """job_types this worker consumes: config.subscribe_types (comma-sep)
        ∩ registered handlers, or all registered handlers if empty."""
        registered = set(self._handlers.keys())
        raw = self.config.subscribe_types or ""
        sub = {t.strip() for t in raw.split(",") if t.strip()}
        if not sub:
            return list(registered)
        return list(registered & sub)

    def worker_info(self) -> Dict[str, Any]:
        """Introspection for the admin /workers endpoint."""
        return {
            "worker_id": self._worker_id,
            "tags": sorted(self._worker_tags),
            "subscribe_types": self._subscribed_types(),
            "concurrency": self.config.concurrency,
            "running": self._running,
            "in_flight": len(self._in_flight),
        }

    # ---- submit / transitions (async wrappers over sync DAO) ----
    async def submit(
        self,
        job_type: str,
        payload: Dict[str, Any],
        *,
        space_slug: Optional[str] = None,
        priority: int = 5,
        max_attempts: Optional[int] = None,
        not_before: Optional[str] = None,
        run_after_seconds: Optional[int] = None,
        required_worker: Optional[List[str]] = None,
    ) -> str:
        ma = max_attempts if max_attempts is not None else self.config.max_attempts_default
        req = ServeRequest(
            job_type=job_type, space_slug=space_slug, payload=payload,
            priority=priority, max_attempts=ma,
            not_before=not_before, run_after_seconds=run_after_seconds,
            required_worker=required_worker,
        )
        entity = await asyncio.to_thread(self.dao.submit, req)
        return entity.id

    async def update_result(self, job_id: str, result: Dict[str, Any]) -> None:
        await asyncio.to_thread(self.dao.update_result, job_id, result)

    async def ack(self, job_id: str, result: Optional[Dict[str, Any]]) -> bool:
        return await asyncio.to_thread(self.dao.ack, job_id, result)

    async def nack(self, job_id: str, error: str) -> str:
        return await asyncio.to_thread(self.dao.nack, job_id, error)

    async def renew_lease(self, job_id: str, extend_seconds: int) -> bool:
        return await asyncio.to_thread(
            self.dao.renew_lease, job_id, self._worker_id, extend_seconds
        )

    # ---- listing (sync, for callers in thread) ----
    def list_jobs(self, **kw) -> List[JobEntity]:
        return self.dao.list_jobs(**kw)

    def list_for_space(self, space_slug: str, limit: int = 50) -> List[JobEntity]:
        return self.dao.list_for_space(space_slug, limit)

    def get(self, job_id: str) -> Optional[JobEntity]:
        return self.dao.get(job_id)

    # ---- worker loop ----
    async def start(self) -> None:
        if self._running:
            return
        if not self._config or not self._config.enabled:
            logger.info("Job engine disabled; worker loop not started")
            return
        if not self._handlers:
            logger.error(
                "Job engine starting with NO handlers registered; "
                "jobs will be nacked. Register handlers before start()."
            )
        self._running = True
        try:
            await asyncio.to_thread(
                self.dao.reclaim_stalled,
                self._subscribed_types() or ["__none__"],
                datetime.utcnow(),
            )
        except Exception:
            logger.exception("initial reclaim_stalled failed")
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info(
            "Job engine started (worker=%s, tags=%s, subscribe=%s, concurrency=%d, poll=%.1fs, lease=%ds)",
            self._worker_id, sorted(self._worker_tags), self._subscribed_types(),
            self._config.concurrency, self._config.poll_interval_seconds,
            self._config.lease_seconds,
        )

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except (asyncio.CancelledError, Exception):
                pass
            self._worker_task = None
        for t in list(self._in_flight.values()):
            t.cancel()
        self._in_flight.clear()
        logger.info("Job engine stopped")

    async def _worker_loop(self) -> None:
        sem = asyncio.Semaphore(self._config.concurrency)
        while self._running:
            for jid, t in list(self._in_flight.items()):
                if t.done():
                    self._in_flight.pop(jid, None)
            try:
                subscribed = self._subscribed_types()
                if subscribed:
                    await asyncio.to_thread(
                        self.dao.reclaim_stalled,
                        subscribed,
                        datetime.utcnow(),
                    )
                while (
                    self._running
                    and len(self._in_flight) < self._config.concurrency
                    and subscribed
                ):
                    job = await asyncio.to_thread(
                        self.dao.claim_next,
                        subscribed,
                        self._worker_id,
                        self._config.lease_seconds,
                        self._worker_tags,
                    )
                    if job is None:
                        break
                    await sem.acquire()
                    t = asyncio.create_task(self._run_one(job, sem))
                    self._in_flight[job.id] = t
            except Exception:
                logger.exception("worker loop iteration failed")
            try:
                await asyncio.sleep(self._config.poll_interval_seconds)
            except asyncio.CancelledError:
                break

    async def _run_one(self, job: JobEntity, sem: asyncio.Semaphore) -> None:
        try:
            handler = self._handlers.get(job.job_type)
            if handler is None:
                await self.nack(job.id, f"no handler registered for {job.job_type}")
                return
            renewer = asyncio.create_task(self._renew_loop(job.id))
            try:
                result = await handler(job)
                renewer.cancel()
                await self.ack(job.id, result if isinstance(result, dict) else None)
            except Exception as e:
                renewer.cancel()
                err = f"{type(e).__name__}: {e}"
                logger.exception("job %s (%s) failed", job.id, job.job_type)
                await self.nack(job.id, err)
        finally:
            sem.release()

    async def _renew_loop(self, job_id: str) -> None:
        lease = self._config.lease_seconds
        try:
            while True:
                await asyncio.sleep(max(1.0, lease * 0.4))
                await self.renew_lease(job_id, int(lease * 0.8))
        except asyncio.CancelledError:
            return
        except Exception:
            logger.debug("renew_lease failed for %s", job_id)