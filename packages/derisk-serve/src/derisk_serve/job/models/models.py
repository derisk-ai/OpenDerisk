"""Job engine database entity + DAO.

Generic persistent-job table shared across all job_types. The DAO implements
claim/consume:
- PG/MySQL: SELECT ... FOR UPDATE SKIP LOCKED (multi-instance safe)
- SQLite:   atomic conditional UPDATE (single-writer, race-free via
            `AND status='pending'` guard), since SQLite has no SKIP LOCKED
            and FOR UPDATE is a no-op there.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON, func, text, or_

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import ServeRequest, ServeResponse
from ..config import SERVER_APP_TABLE_NAME, ServeConfig

logger = logging.getLogger(__name__)


class JobEntity(Model):
    """Database entity for persistent jobs (table `derisk_serve_job`)."""

    __tablename__ = SERVER_APP_TABLE_NAME

    id = Column(String(64), primary_key=True)
    job_type = Column(String(64), nullable=False, index=True)
    space_slug = Column(String(128), nullable=True, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(
        String(16), nullable=False, default="pending", index=True
    )  # pending | running | done | failed
    priority = Column(Integer, nullable=False, default=5)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    claimed_by = Column(String(128), nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    lease_until = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    result = Column(JSON, nullable=True)
    # v2: scheduled execution — not claimable before this time.
    not_before = Column(DateTime, nullable=True, index=True)
    # v2: worker affinity — token list; claimable only by a worker whose tags
    # are a superset. NULL/empty = any worker.
    required_worker = Column(JSON, nullable=True)
    # v2: execution record — last executor (preserved on ack/nack, unlike
    # claimed_by which is cleared). attempts_history is a JSON array of
    # {worker, started_at, finished_at, status, error} per attempt.
    executed_by = Column(String(128), nullable=True)
    executed_at = Column(DateTime, nullable=True)
    attempts_history = Column(JSON, nullable=True)
    gmt_created = Column(
        DateTime, nullable=False, default=datetime.now, name="gmt_create"
    )
    gmt_modified = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now,
        name="gmt_modified",
    )


class JobDao(BaseDao[JobEntity, ServeRequest, ServeResponse]):
    """DAO with claim/consume primitives."""

    # Columns added in job schema v2. Idempotent ALTER for upgrades from v1
    # (CREATE TABLE IF NOT EXISTS won't add columns to an existing table).
    _V2_COLUMNS = [
        ("not_before", "DateTime"),
        ("required_worker", "JSON"),
        ("executed_by", "String(128)"),
        ("executed_at", "DateTime"),
        ("attempts_history", "JSON"),
    ]

    def __init__(self, serve_config: Optional[ServeConfig] = None, db_manager=None):
        super().__init__(db_manager=db_manager)
        self._serve_config = serve_config
        # Detect SKIP LOCKED support once. SQLite has no row locks.
        self._supports_skip_locked = self._detect_skip_locked()
        self._migrate_v2()

    def _migrate_v2(self) -> None:
        """Add v2 columns to `derisk_serve_job` if missing (idempotent)."""
        try:
            from sqlalchemy import inspect as sa_inspect
            with self.session(commit=False) as session:
                insp = sa_inspect(session.bind)
                if JobEntity.__tablename__ not in insp.get_table_names():
                    return  # table doesn't exist yet; CREATE will handle it
                existing = {c["name"] for c in insp.get_columns(JobEntity.__tablename__)}
                for col, _type in self._V2_COLUMNS:
                    if col in existing:
                        continue
                    # ALTER ADD COLUMN NULL (existing rows stay NULL)
                    session.execute(
                        text(f"ALTER TABLE {JobEntity.__tablename__} ADD COLUMN {col} TEXT")
                    )
                session.commit()
        except Exception as e:
            logger.debug("job v2 migration skipped: %s", e)

    def _dialect_is_sqlite(self) -> bool:
        try:
            sess = self.get_raw_session()
            d = sess.bind.dialect.name if sess.bind else None
            sess.close()
            return d == "sqlite"
        except Exception:
            return False

    def _detect_skip_locked(self) -> bool:
        try:
            sess = self.get_raw_session()
            dialect = None
            if hasattr(sess, "bind") and sess.bind is not None:
                dialect = sess.bind.dialect.name
            sess.close()
        except Exception:
            dialect = None
        return dialect in ("postgresql", "mysql")

    # ---- BaseDao plumbing -------------------------------------------------

    def from_request(self, request: ServeRequest) -> JobEntity:
        return JobEntity(
            id=f"job_{uuid.uuid4().hex[:16]}",
            job_type=request.job_type,
            space_slug=request.space_slug,
            payload=request.payload,
            status="pending",
            priority=request.priority,
            attempts=0,
            max_attempts=request.max_attempts,
            required_worker=request.required_worker,
        )

    def to_request(self, entity: JobEntity) -> ServeRequest:
        return ServeRequest(
            job_type=entity.job_type,
            space_slug=entity.space_slug,
            payload=entity.payload or {},
            priority=entity.priority,
            max_attempts=entity.max_attempts,
        )

    def to_response(self, entity: JobEntity) -> ServeResponse:
        def _dt(v):
            return v.strftime("%Y-%m-%d %H:%M:%S") if v else None

        return ServeResponse(
            id=entity.id,
            job_type=entity.job_type,
            space_slug=entity.space_slug,
            payload=entity.payload or {},
            status=entity.status,
            priority=entity.priority,
            attempts=entity.attempts,
            max_attempts=entity.max_attempts,
            claimed_by=entity.claimed_by,
            claimed_at=_dt(entity.claimed_at),
            lease_until=_dt(entity.lease_until),
            last_error=entity.last_error,
            result=entity.result,
            not_before=_dt(entity.not_before),
            required_worker=entity.required_worker,
            executed_by=entity.executed_by,
            executed_at=_dt(entity.executed_at),
            attempts_history=entity.attempts_history,
            gmt_created=_dt(entity.gmt_created),
            gmt_modified=_dt(entity.gmt_modified),
        )

    # ---- claim / consume --------------------------------------------------

    def submit(self, request: ServeRequest) -> JobEntity:
        entity = self.from_request(request)
        # Resolve scheduling: run_after_seconds → not_before; explicit not_before wins.
        if request.not_before:
            entity.not_before = datetime.fromisoformat(request.not_before)
        elif request.run_after_seconds:
            entity.not_before = datetime.utcnow() + timedelta(seconds=request.run_after_seconds)
        with self.session() as session:
            session.add(entity)
            session.flush()
            session.refresh(entity)
            session.expunge(entity)
        return entity

    def claim_next(
        self,
        job_types: List[str],
        worker_id: str,
        lease_seconds: int,
        worker_tags: Optional[set] = None,
    ) -> Optional[JobEntity]:
        if not job_types:
            return None
        now = datetime.utcnow()
        lease = now + timedelta(seconds=lease_seconds)
        tags = worker_tags or set()
        if self._supports_skip_locked:
            return self._claim_skip_locked(job_types, worker_id, now, lease, tags)
        return self._claim_sqlite(job_types, worker_id, now, lease, tags)

    @staticmethod
    def _worker_can_claim(required_worker, worker_tags: set) -> bool:
        """A worker may claim a job iff the job's required_worker is empty
        (any worker) or is a subset of the worker's tags."""
        if not required_worker:
            return True
        return set(required_worker) <= worker_tags

    def _claim_skip_locked(self, job_types, worker_id, now, lease, tags):
        with self.session(commit=False) as session:
            q = (
                session.query(JobEntity)
                .filter(
                    JobEntity.job_type.in_(job_types),
                    JobEntity.status == "pending",
                    # not_before: not claimable before this time (NULL = now).
                    or_(JobEntity.not_before.is_(None), JobEntity.not_before <= now),
                )
                .order_by(JobEntity.priority.asc(), JobEntity.gmt_created.asc())
                .limit(16)
                .with_for_update(skip_locked=True)
            )
            # required_worker matching is done in Python (JSON queries are
            # dialect-specific; candidate window is small).
            row = None
            for r in q:
                if self._worker_can_claim(r.required_worker, tags):
                    row = r
                    break
            if row is None:
                return None
            row.status = "running"
            row.claimed_by = worker_id
            row.claimed_at = now
            row.lease_until = lease
            row.attempts = (row.attempts or 0) + 1
            self._append_attempt(session, row, "running", None, started_at=now)
            session.commit()
            session.expunge(row)
            return row

    def _claim_sqlite(self, job_types, worker_id, now, lease, tags):
        """Atomic conditional UPDATE — race-free under SQLite's single writer.

        Selects up to N candidates and tries each with the `AND status='pending'`
        guard until one succeeds. This handles the case where two workers both
        picked the same top candidate: the loser's UPDATE affects 0 rows and
        falls through to the next candidate.
        """
        with self.session() as session:
            candidates = (
                session.query(JobEntity.id, JobEntity.required_worker)
                .filter(
                    JobEntity.job_type.in_(job_types),
                    JobEntity.status == "pending",
                    or_(JobEntity.not_before.is_(None), JobEntity.not_before <= now),
                )
                .order_by(JobEntity.priority.asc(), JobEntity.gmt_created.asc())
                .limit(32)
                .all()
            )
            for candidate_id, req in candidates:
                if not self._worker_can_claim(req, tags):
                    continue  # this worker can't run it; try next
                updated = (
                    session.query(JobEntity)
                    .filter(
                        JobEntity.id == candidate_id,
                        JobEntity.status == "pending",
                    )
                    .update(
                        {
                            "status": "running",
                            "claimed_by": worker_id,
                            "claimed_at": now,
                            "lease_until": lease,
                            "attempts": JobEntity.attempts + 1,
                        },
                        synchronize_session=False,
                    )
                )
                if not updated:
                    continue  # someone else grabbed it; try next candidate
                row = session.query(JobEntity).filter(
                    JobEntity.id == candidate_id
                ).first()
                if row:
                    self._append_attempt(session, row, "running", None, started_at=now)
                    session.expunge(row)
                return row
            return None

    def _append_attempt(
        self, session, row, status: str, error: Optional[str], started_at=None,
    ) -> None:
        """Append one attempt record to attempts_history (in-place on `row`)."""
        entry: Dict[str, Any] = {
            "worker": row.claimed_by,
            "status": status,
            "started_at": (started_at or row.claimed_at or datetime.utcnow()).isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
        }
        if error:
            entry["error"] = error[:1000]
        history = list(row.attempts_history or [])
        history.append(entry)
        # Cap history length to avoid unbounded growth on retry loops.
        row.attempts_history = history[-20:]

    def reclaim_stalled(self, job_types: List[str], now: datetime) -> int:
        if not job_types:
            return 0
        with self.session() as session:
            updated = (
                session.query(JobEntity)
                .filter(
                    JobEntity.job_type.in_(job_types),
                    JobEntity.status == "running",
                    JobEntity.lease_until.isnot(None),
                    JobEntity.lease_until < now,
                )
                .update(
                    {
                        "status": "pending",
                        "claimed_by": None,
                        "claimed_at": None,
                        "lease_until": None,
                    },
                    synchronize_session=False,
                )
            )
            return updated

    def ack(self, job_id: str, result: Optional[Dict[str, Any]]) -> bool:
        with self.session(commit=False) as session:
            row = (
                session.query(JobEntity)
                .filter(JobEntity.id == job_id, JobEntity.status == "running")
                .with_for_update()
                .first()
            )
            if row is None:
                return False
            now = datetime.utcnow()
            row.executed_by = row.claimed_by  # preserve executor before clearing
            row.executed_at = now
            row.status = "done"
            self._append_attempt(session, row, "done", None, started_at=row.claimed_at)
            row.claimed_by = None
            row.claimed_at = None
            row.lease_until = None
            row.result = result
            session.commit()
            return True

    def nack(self, job_id: str, error: str) -> str:
        """Flip to pending if attempts < max_attempts else failed.

        attempts was already incremented at claim time.
        """
        with self.session(commit=False) as session:
            row = (
                session.query(JobEntity)
                .filter(JobEntity.id == job_id)
                .with_for_update()
                .first()
            )
            if row is None:
                return "failed"
            next_status = "failed" if row.attempts >= row.max_attempts else "pending"
            row.executed_by = row.claimed_by  # preserve executor
            row.executed_at = datetime.utcnow()
            row.status = next_status
            self._append_attempt(session, row, next_status, error, started_at=row.claimed_at)
            row.claimed_by = None
            row.claimed_at = None
            row.lease_until = None
            row.last_error = (error or "")[:4000]
            session.commit()
            return next_status

    def renew_lease(self, job_id: str, worker_id: str, extend_seconds: int) -> bool:
        with self.session() as session:
            updated = (
                session.query(JobEntity)
                .filter(
                    JobEntity.id == job_id,
                    JobEntity.status == "running",
                    JobEntity.claimed_by == worker_id,
                )
                .update(
                    {"lease_until": datetime.utcnow() + timedelta(seconds=extend_seconds)},
                    synchronize_session=False,
                )
            )
            return updated > 0

    def update_result(self, job_id: str, result: Dict[str, Any]) -> None:
        """Write intermediate progress (e.g. phase) into result."""
        with self.session() as session:
            row = session.query(JobEntity).filter(JobEntity.id == job_id).first()
            if row is None:
                return
            merged = dict(row.result or {})
            merged.update(result)
            row.result = merged

    def retry(self, job_id: str) -> Optional[JobEntity]:
        with self.session(commit=False) as session:
            row = (
                session.query(JobEntity)
                .filter(JobEntity.id == job_id)
                .with_for_update()
                .first()
            )
            if row is None:
                return None
            row.status = "pending"
            row.claimed_by = None
            row.claimed_at = None
            row.lease_until = None
            row.last_error = None
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending job (running jobs must let lease expire)."""
        with self.session() as session:
            updated = (
                session.query(JobEntity)
                .filter(JobEntity.id == job_id, JobEntity.status == "pending")
                .update(
                    {"status": "failed", "last_error": "cancelled by admin"},
                    synchronize_session=False,
                )
            )
            return updated > 0

    def delete(self, job_id: str) -> bool:
        with self.session() as session:
            deleted = (
                session.query(JobEntity)
                .filter(JobEntity.id == job_id)
                .delete(synchronize_session=False)
            )
            return deleted > 0

    # ---- queries ---------------------------------------------------------

    def get(self, job_id: str) -> Optional[JobEntity]:
        with self.session(commit=False) as session:
            row = session.query(JobEntity).filter(JobEntity.id == job_id).first()
            if row:
                session.expunge(row)
            return row

    def list_jobs(
        self,
        *,
        job_type: Optional[str] = None,
        space_slug: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[JobEntity]:
        with self.session(commit=False) as session:
            q = session.query(JobEntity)
            if job_type:
                q = q.filter(JobEntity.job_type == job_type)
            if space_slug:
                q = q.filter(JobEntity.space_slug == space_slug)
            if status:
                q = q.filter(JobEntity.status == status)
            q = q.order_by(JobEntity.gmt_created.desc()).limit(limit).offset(offset)
            rows = q.all()
            for r in rows:
                session.expunge(r)
            return rows

    def count(
        self,
        *,
        job_type: Optional[str] = None,
        space_slug: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        with self.session(commit=False) as session:
            q = session.query(func.count(JobEntity.id))
            if job_type:
                q = q.filter(JobEntity.job_type == job_type)
            if space_slug:
                q = q.filter(JobEntity.space_slug == space_slug)
            if status:
                q = q.filter(JobEntity.status == status)
            return int(q.scalar() or 0)

    def list_for_space(self, space_slug: str, limit: int = 50) -> List[JobEntity]:
        return self.list_jobs(space_slug=space_slug, limit=limit)

    def stats(self) -> Dict[str, Any]:
        with self.session(commit=False) as session:
            rows = (
                session.query(
                    JobEntity.job_type,
                    JobEntity.status,
                    func.count(JobEntity.id),
                )
                .group_by(JobEntity.job_type, JobEntity.status)
                .all()
            )
            exec_rows = (
                session.query(JobEntity.executed_by, func.count(JobEntity.id))
                .filter(JobEntity.executed_by.isnot(None))
                .group_by(JobEntity.executed_by)
                .all()
            )
        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        by_type_status: Dict[str, Dict[str, int]] = {}
        by_executor: Dict[str, int] = {}
        total = 0
        for job_type, status, cnt in rows:
            cnt = int(cnt)
            total += cnt
            by_status[status] = by_status.get(status, 0) + cnt
            by_type[job_type] = by_type.get(job_type, 0) + cnt
            by_type_status.setdefault(job_type, {})[status] = cnt
        for executor, cnt in exec_rows:
            by_executor[executor] = int(cnt)
        return {
            "total": total,
            "by_status": by_status,
            "by_type": by_type,
            "by_type_status": by_type_status,
            "by_executor": by_executor,
        }