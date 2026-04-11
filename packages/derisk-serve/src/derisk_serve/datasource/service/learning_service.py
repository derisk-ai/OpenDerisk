"""Service for database schema learning and spec generation.

Supports distributed execution: multiple web server nodes can share
the table-level learning workload via DB row-lock based task claiming.
"""

import json
import logging
import os
import re
import socket
import threading
import time
import traceback
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text as sa_text

from derisk_serve.datasource.manages.connect_config_db import ConnectConfigDao
from derisk_serve.datasource.manages.db_spec_db import DbSpecDao
from derisk_serve.datasource.manages.learning_subtask_db import (
    DbLearningSubtaskDao,
)
from derisk_serve.datasource.manages.learning_task_db import DbLearningTaskDao
from derisk_serve.datasource.manages.table_spec_db import TableSpecDao

logger = logging.getLogger(__name__)

# Threshold for table grouping
TABLE_GROUP_THRESHOLD = 30
# Max characters per sample value
MAX_SAMPLE_VALUE_LENGTH = 100
# Timeout for stale subtask reclaim (seconds)
SUBTASK_STALE_TIMEOUT = 300
# Max idle iterations before a worker exits the loop
WORKER_MAX_IDLE = 60
# Default number of concurrent worker threads per node
DEFAULT_WORKER_CONCURRENCY = 5


class SchemaLearningService:
    """Service for learning database schema and generating spec documents.

    Supports distributed execution across multiple nodes. The learning
    task is split into per-table subtasks that workers claim atomically.
    """

    def __init__(self, connector_manager, system_app=None):
        self._connector_manager = connector_manager
        self._system_app = system_app
        self._db_spec_dao = DbSpecDao()
        self._table_spec_dao = TableSpecDao()
        self._learning_task_dao = DbLearningTaskDao()
        self._subtask_dao = DbLearningSubtaskDao()
        self._config_dao = ConnectConfigDao()

    @staticmethod
    def _get_datasource_config():
        """Read datasource config from ConfigManager (fallback to defaults)."""
        try:
            from derisk_core.config import ConfigManager
            config = ConfigManager.get()
            return config.datasource
        except Exception:
            return None

    @property
    def _worker_concurrency(self) -> int:
        ds_cfg = self._get_datasource_config()
        if ds_cfg is not None:
            return ds_cfg.learning_worker_concurrency
        return DEFAULT_WORKER_CONCURRENCY

    @property
    def _subtask_stale_timeout(self) -> int:
        ds_cfg = self._get_datasource_config()
        if ds_cfg is not None:
            return ds_cfg.learning_subtask_timeout
        return SUBTASK_STALE_TIMEOUT

    @staticmethod
    def _worker_id() -> str:
        return (
            f"{socket.gethostname()}:{os.getpid()}"
            f":{threading.current_thread().ident}"
        )

    # ==============================================================
    # Public entry point — coordinator + worker
    # ==============================================================

    def learn_database(
        self,
        datasource_id: int,
        db_name: str,
        db_type: str,
        trigger_type: str = "manual",
    ) -> Dict[str, Any]:
        """Run a full schema learning task for a database.

        Phase 1 (Coordinator): Creates the parent task and per-table
        subtasks. Only the first node to call this succeeds; others
        skip to Phase 2.

        Phase 2 (Worker Loop): Atomically claims pending subtasks and
        processes them. Multiple nodes can run this concurrently.

        Args:
            datasource_id: The datasource config ID.
            db_name: The database name (used to get connector).
            db_type: The database type string.
            trigger_type: How the learning was triggered.

        Returns:
            The learning task dict.
        """
        # Phase 1: Coordinator — create task + subtasks (only one node)
        task_id = self._coordinate(
            datasource_id, db_name, db_type, trigger_type
        )
        if task_id is None:
            # Already running — just return the existing task
            existing = self._learning_task_dao.get_running_by_datasource(
                datasource_id
            )
            return existing or {}

        # Phase 2: Worker loop — process subtasks
        try:
            self._run_worker_loop(task_id, datasource_id, db_name, db_type)
        except Exception as e:
            logger.error(
                f"Worker loop failed for task {task_id}: {e}\n"
                f"{traceback.format_exc()}"
            )

        # Phase 3: Finalization — only one node runs post-processing
        self._try_finalize_task(task_id, datasource_id, db_name, db_type)

        return self._learning_task_dao.get_one({"id": task_id}) or {}

    def join_worker(
        self,
        datasource_id: int,
        db_name: str,
        db_type: str,
    ) -> None:
        """Join an already-running learning task as a worker.

        Called when a second node receives a learn request while a task
        is already running. The node skips coordination and directly
        enters the worker loop to help process remaining subtasks.
        """
        running = self._learning_task_dao.get_running_by_datasource(
            datasource_id
        )
        if not running:
            return
        task_id = running["id"]
        logger.info(
            f"[WORKER] Joining task {task_id} for ds={datasource_id} "
            f"as worker {self._worker_id()}"
        )
        try:
            self._run_worker_loop(task_id, datasource_id, db_name, db_type)
        except Exception as e:
            logger.error(f"Worker loop failed: {e}")
        self._try_finalize_task(task_id, datasource_id, db_name, db_type)

    def cancel_task(self, datasource_id: int) -> Dict[str, Any]:
        """Cancel a running learning task for a datasource.

        Sets the task status to 'cancelled' atomically and cancels all
        pending subtasks. In-flight subtasks will complete gracefully;
        workers check for cancellation on each loop iteration and exit.

        Returns:
            Dict with 'cancelled' bool and details.
        """
        running = self._learning_task_dao.get_running_by_datasource(
            datasource_id
        )
        if not running:
            # Also check finalizing
            latest = self._learning_task_dao.get_latest_by_datasource(
                datasource_id
            )
            if latest and latest.get("status") == "finalizing":
                running = latest
        if not running:
            return {"cancelled": False, "reason": "no active task"}

        task_id = running["id"]
        success = self._learning_task_dao.cancel_task(task_id)
        if success:
            cancelled_count = self._subtask_dao.cancel_pending(task_id)
            logger.info(
                f"[CANCEL] Task {task_id} cancelled, "
                f"{cancelled_count} pending subtasks cancelled"
            )
            return {
                "cancelled": True,
                "task_id": task_id,
                "cancelled_subtasks": cancelled_count,
            }
        return {"cancelled": False, "reason": "task already completed"}

    def resume_stale_task(
        self,
        task_id: int,
        datasource_id: int,
        db_name: str,
        db_type: str,
    ) -> None:
        """Resume a task that was interrupted by a server crash.

        Called from the crash-recovery hook in service.after_start().
        """
        task = self._learning_task_dao.get_one({"id": task_id})
        if not task:
            return

        status = task["status"]
        logger.info(
            f"[RECOVERY] Resuming task {task_id} (status={status}) "
            f"for ds={datasource_id}"
        )

        if status == "finalizing":
            # Re-attempt finalization directly (skip atomic transition)
            self._do_finalize(task_id, datasource_id, db_name, db_type)
        elif status == "running":
            # Reclaim stale subtasks, then enter normal worker loop
            self._subtask_dao.reclaim_stale(task_id, self._subtask_stale_timeout)
            try:
                self._run_worker_loop(
                    task_id, datasource_id, db_name, db_type
                )
            except Exception as e:
                logger.error(f"[RECOVERY] Worker loop failed: {e}")
            self._try_finalize_task(
                task_id, datasource_id, db_name, db_type
            )

    def get_learning_status(
        self, datasource_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get the latest learning task status for a datasource."""
        return self._learning_task_dao.get_latest_by_datasource(datasource_id)

    # ==============================================================
    # Phase 1: Coordination
    # ==============================================================

    def _coordinate(
        self,
        datasource_id: int,
        db_name: str,
        db_type: str,
        trigger_type: str,
    ) -> Optional[int]:
        """Create the parent task and subtasks atomically.

        Returns the task_id if this node is the coordinator, or None
        if another node already created the task.
        """
        # Atomic check-and-create
        running = self._learning_task_dao.get_running_by_datasource(
            datasource_id
        )
        if running:
            logger.info(
                f"[COORD] Task already running for ds={datasource_id}, "
                f"joining as worker"
            )
            return None

        # Create parent task
        task = self._learning_task_dao.create({
            "datasource_id": datasource_id,
            "task_type": "full_learn",
            "status": "running",
            "progress": 0,
            "trigger_type": trigger_type,
        })
        task_id = task["id"]
        logger.info(f"[COORD] Created task {task_id} for ds={datasource_id}")

        # Set db spec to generating
        self._db_spec_dao.upsert(datasource_id, {
            "db_name": db_name,
            "db_type": db_type,
            "spec_content": "[]",
            "table_count": 0,
            "status": "generating",
        })

        try:
            connector = self._connector_manager.get_connector(db_name)
            table_names = list(connector.get_table_names())

            # Create per-table subtasks
            self._subtask_dao.bulk_create(task_id, datasource_id, table_names)
            self._learning_task_dao.update_progress(
                task_id, 0, len(table_names)
            )
            logger.info(
                f"[COORD] Created {len(table_names)} subtasks for task {task_id}"
            )
        except Exception as e:
            logger.error(f"[COORD] Failed to create subtasks: {e}")
            self._learning_task_dao.update_progress(
                task_id, 0, 0, status="failed", error_message=str(e)[:2000]
            )
            self._db_spec_dao.upsert(datasource_id, {
                "db_name": db_name, "db_type": db_type,
                "spec_content": "[]", "table_count": 0, "status": "failed",
            })
            return task_id

        return task_id

    # ==============================================================
    # Phase 2: Worker loop
    # ==============================================================

    def _run_worker_loop(
        self,
        task_id: int,
        datasource_id: int,
        db_name: str,
        db_type: str,
    ) -> None:
        """Spawn WORKER_CONCURRENCY threads, each claiming subtasks.

        Builds shared read-only db_context once, then distributes work
        across concurrent worker threads. Each thread gets its own
        database connector (SQLAlchemy sessions are not thread-safe).
        """
        # Build shared LLM context once (read-only, safe to share)
        connector = self._connector_manager.get_connector(db_name)
        try:
            all_tables = [
                s["table_name"]
                for s in self._table_spec_dao.get_all_by_datasource(datasource_id)
            ]
        except Exception:
            all_tables = []
        if not all_tables:
            try:
                all_tables = list(connector.get_table_names())
            except Exception:
                all_tables = []
        db_context = self._build_db_context(
            datasource_id, db_name, db_type, all_tables
        )

        concurrency = self._worker_concurrency
        if concurrency <= 1:
            # Single-threaded mode: reuse the connector we already have
            self._single_worker_loop(
                task_id, datasource_id, db_name, db_type,
                connector, db_context,
            )
            return

        # Multi-threaded: each thread gets its own connector
        from concurrent.futures import ThreadPoolExecutor, as_completed

        logger.info(
            f"[WORKER] Starting {concurrency} concurrent workers "
            f"for task {task_id}"
        )
        with ThreadPoolExecutor(
            max_workers=concurrency,
            thread_name_prefix="learn-worker",
        ) as pool:
            futures = []
            for i in range(concurrency):
                # First thread reuses existing connector; others create new
                conn = (
                    connector if i == 0
                    else self._connector_manager.get_connector(db_name)
                )
                futures.append(pool.submit(
                    self._single_worker_loop,
                    task_id, datasource_id, db_name, db_type,
                    conn, db_context,
                ))
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    logger.error(f"[WORKER] Thread failed: {e}")

    def _single_worker_loop(
        self,
        task_id: int,
        datasource_id: int,
        db_name: str,
        db_type: str,
        connector,
        db_context: dict,
    ) -> None:
        """Single worker thread: claim and process subtasks until done."""
        worker_id = self._worker_id()
        logger.info(f"[WORKER] Starting loop: task={task_id}, worker={worker_id}")

        idle_count = 0
        processed = 0

        while True:
            # Check cancellation
            if self._learning_task_dao.is_cancelled(task_id):
                logger.info(
                    f"[WORKER] Task {task_id} cancelled, exiting "
                    f"(processed {processed})"
                )
                break

            # Reclaim stale subtasks periodically
            self._subtask_dao.reclaim_stale(task_id, self._subtask_stale_timeout)

            # Try to claim a subtask
            subtask = self._subtask_dao.claim_one(task_id, worker_id)
            if subtask is None:
                stats = self._subtask_dao.get_task_stats(task_id)
                if stats["pending"] == 0 and stats["claimed"] == 0:
                    logger.info(
                        f"[WORKER] All subtasks done for task {task_id}, "
                        f"processed {processed} tables"
                    )
                    break
                idle_count += 1
                if idle_count > WORKER_MAX_IDLE:
                    logger.info(
                        f"[WORKER] Max idle reached, exiting task {task_id}"
                    )
                    break
                time.sleep(2)
                continue

            idle_count = 0
            table_name = subtask["table_name"]
            subtask_id = subtask["id"]

            try:
                self._learn_single_table(
                    connector, datasource_id, table_name,
                    db_context=db_context,
                )
                self._subtask_dao.mark_completed(subtask_id)
                processed += 1
            except Exception as e:
                logger.error(
                    f"[WORKER] Error learning {table_name}: {e}\n"
                    f"{traceback.format_exc()}"
                )
                self._subtask_dao.mark_failed(subtask_id, str(e)[:2000])

            # Update parent task progress
            self._update_parent_progress(task_id)

    def _update_parent_progress(self, task_id: int) -> None:
        """Sync parent task progress from subtask stats."""
        stats = self._subtask_dao.get_task_stats(task_id)
        processed = stats["completed"] + stats["failed"]
        total = stats["total"]
        self._learning_task_dao.update_progress(task_id, processed, total)

    # ==============================================================
    # Phase 3: Finalization (exactly-once via atomic status transition)
    # ==============================================================

    def _try_finalize_task(
        self,
        task_id: int,
        datasource_id: int,
        db_name: str,
        db_type: str,
    ) -> None:
        """Run post-processing. Only one node succeeds via atomic UPDATE."""
        # Atomic: running → finalizing (cancelled tasks get rowcount=0)
        with self._learning_task_dao.session() as session:
            result = session.execute(sa_text("""
                UPDATE db_learning_task
                SET status = 'finalizing',
                    gmt_modified = :now
                WHERE id = :task_id AND status = 'running'
            """), {
                "task_id": task_id,
                "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            if result.rowcount == 0:
                return  # Another node is finalizing, or task was cancelled

        self._do_finalize(task_id, datasource_id, db_name, db_type)

    def _do_finalize(
        self,
        task_id: int,
        datasource_id: int,
        db_name: str,
        db_type: str,
    ) -> None:
        """Execute the finalization logic (spec assembly, relation detection).

        Called by _try_finalize_task (normal path) and resume_stale_task
        (crash recovery path for tasks already in 'finalizing' state).
        """
        logger.info(f"[FINALIZE] Running post-processing for task {task_id}")

        try:
            # Build spec entries from learned table specs
            spec_entries = self._build_spec_entries(datasource_id)
            total_tables = len(spec_entries)

            # Apply grouping
            group_config = None
            if total_tables > TABLE_GROUP_THRESHOLD:
                spec_entries, group_config = self._apply_grouping(spec_entries)

            # Detect relations and sensitive columns
            relations = self._detect_table_relations(datasource_id)
            self._detect_sensitive_columns(datasource_id)

            # Save db-level spec
            spec_data = {
                "db_name": db_name,
                "db_type": db_type,
                "spec_content": json.dumps(spec_entries, ensure_ascii=False),
                "table_count": total_tables,
                "group_config": (
                    json.dumps(group_config, ensure_ascii=False)
                    if group_config else None
                ),
                "status": "ready",
            }
            if relations:
                spec_data["relations"] = json.dumps(
                    relations, ensure_ascii=False
                )
            self._db_spec_dao.upsert(datasource_id, spec_data)

            # Build error summary
            error_msg = self._subtask_dao.get_error_summary(task_id)

            stats = self._subtask_dao.get_task_stats(task_id)
            self._learning_task_dao.update_progress(
                task_id, stats["total"], stats["total"],
                status="completed",
                error_message=error_msg,
            )
            logger.info(
                f"[FINALIZE] Task {task_id} completed: "
                f"{stats['completed']} ok, {stats['failed']} failed"
            )
        except Exception as e:
            logger.error(
                f"[FINALIZE] Failed for task {task_id}: {e}\n"
                f"{traceback.format_exc()}"
            )
            self._learning_task_dao.update_progress(
                task_id, 0, 0, status="failed",
                error_message=str(e)[:2000],
            )
            self._db_spec_dao.upsert(datasource_id, {
                "db_name": db_name, "db_type": db_type,
                "spec_content": "[]", "table_count": 0, "status": "failed",
            })

    def _build_spec_entries(
        self, datasource_id: int
    ) -> List[Dict[str, Any]]:
        """Build db-level spec entries from persisted table specs.

        ``summary`` stores the LLM-generated table description (from
        ``table_comment``).  The prompt layer formats it as
        ``table_name: summary``, so we only keep the description here.
        """
        table_specs = self._table_spec_dao.get_all_by_datasource(datasource_id)
        spec_entries = []
        for spec in table_specs:
            columns = spec.get("columns", [])
            table_name = spec.get("table_name", "")
            comment = spec.get("table_comment", "") or ""
            spec_entries.append({
                "table_name": table_name,
                "summary": comment,
                "row_count": spec.get("row_count"),
                "column_count": len(columns or []),
                "group": spec.get("group_name", "default"),
            })
        return spec_entries

    def _learn_single_table(
        self, connector, datasource_id: int, table_name: str,
        db_context: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Learn a single table's schema and data profile.

        Args:
            connector: The database connector instance.
            datasource_id: The datasource config ID.
            table_name: The table to learn.

        Returns:
            The table spec dict.
        """
        # Primary key columns
        pk_columns = set()
        try:
            pk_info = connector.get_pk_constraint(table_name)
            if pk_info and pk_info.get("constrained_columns"):
                pk_columns = set(pk_info["constrained_columns"])
        except Exception:
            pass

        # Foreign keys
        foreign_keys = []
        try:
            fk_list = connector.get_foreign_keys(table_name)
            for fk in (fk_list or []):
                foreign_keys.append({
                    "constrained_columns": fk.get("constrained_columns", []),
                    "referred_table": fk.get("referred_table", ""),
                    "referred_columns": fk.get("referred_columns", []),
                })
        except Exception:
            pass

        # Columns
        columns_raw = connector.get_columns(table_name)
        columns = []
        for col in columns_raw:
            col_name = col.get("name", "")
            columns.append({
                "name": col_name,
                "type": str(col.get("type", "")),
                "nullable": col.get("nullable", True),
                "default": str(col.get("default", "")) if col.get("default") else None,
                "comment": col.get("comment", ""),
                "pk": col_name in pk_columns,
            })

        # Indexes
        indexes_raw = connector.get_indexes(table_name)
        indexes = []
        for idx in indexes_raw:
            indexes.append({
                "name": idx.get("name", ""),
                "columns": idx.get("column_names", []),
                "unique": idx.get("unique", False),
            })

        # Table comment
        table_comment = ""
        try:
            comment_info = connector.get_table_comment(table_name)
            if isinstance(comment_info, dict):
                table_comment = comment_info.get("text", "") or ""
            elif isinstance(comment_info, str):
                table_comment = comment_info
        except Exception:
            pass

        # DDL
        create_ddl = ""
        try:
            create_ddl = connector.get_show_create_table(table_name)
        except Exception:
            pass

        # Row count
        # Note: connector.run() returns [column_names, row1, row2, ...]
        # so data rows start at index 1
        row_count = None
        try:
            result = connector.run(
                f"SELECT COUNT(*) FROM {connector.quote_identifier(table_name)}"
            )
            if result and len(result) > 1:
                # SQLAlchemy 2.x Row is NOT a tuple subclass, convert first
                row_val = tuple(result[1])
                if len(row_val) > 0:
                    row_count = int(row_val[0])
        except Exception:
            pass

        # Column value distribution for low-cardinality columns
        for col in columns:
            col_name = col.get("name", "")
            col_type = col.get("type", "").lower()
            if any(t in col_type for t in (
                "varchar", "char", "enum", "tinyint", "boolean", "bool",
                "smallint", "status", "type", "category",
            )):
                try:
                    dist_result = connector.run(
                        connector.limit_sql(
                            f"SELECT DISTINCT {connector.quote_identifier(col_name)}"
                            f" FROM {connector.quote_identifier(table_name)}",
                            20,
                        )
                    )
                    # Skip first row (column names)
                    dist_data = dist_result[1:] if dist_result else []
                    if dist_data and len(dist_data) <= 15:
                        values = []
                        for row in dist_data:
                            # SQLAlchemy 2.x Row → tuple
                            row = tuple(row)
                            if len(row) > 0 and row[0] is not None:
                                values.append(
                                    str(row[0])[:MAX_SAMPLE_VALUE_LENGTH]
                                )
                        if values:
                            col["distribution"] = {
                                "type": "enum",
                                "values": values,
                            }
                except Exception:
                    pass

        # LLM-generated description (when table_comment is empty/short)
        llm_summary_attempted = False
        llm_summary_ok = False
        if not table_comment or len(table_comment) < 10:
            llm_summary_attempted = True
            llm_desc = self._generate_single_table_summary(
                connector, table_name, columns, row_count, table_comment,
                db_context=db_context,
            )
            if llm_desc:
                table_comment = llm_desc
                llm_summary_ok = True
                logger.info(f"[LEARN] Table '{table_name}': LLM desc OK")

        # Determine group name from table name prefix
        group_name = "default"

        # Sample data: first 2 rows + last 2 rows for a realistic preview
        sample_data_json = None
        try:
            sample_data_json = self._collect_sample_data(
                connector, table_name, columns, row_count
            )
        except Exception:
            logger.debug(f"[LEARN] Failed to collect sample data for '{table_name}'")

        # Persist
        table_data = {
            "table_comment": table_comment,
            "row_count": row_count,
            "columns_json": json.dumps(columns, ensure_ascii=False),
            "indexes_json": json.dumps(indexes, ensure_ascii=False),
            "foreign_keys_json": (
                json.dumps(foreign_keys, ensure_ascii=False)
                if foreign_keys else None
            ),
            "sample_data_json": sample_data_json,
            "create_ddl": create_ddl,
            "group_name": group_name,
        }
        self._table_spec_dao.upsert(datasource_id, table_name, table_data)

        return {
            "table_name": table_name,
            "table_comment": table_comment,
            "row_count": row_count,
            "columns": columns,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
            "create_ddl": create_ddl,
            "group_name": group_name,
            "llm_summary_attempted": llm_summary_attempted,
            "llm_summary_ok": llm_summary_ok,
        }

    def _collect_sample_data(
        self, connector, table_name: str, columns: list, row_count
    ) -> str | None:
        """Collect sample rows for a table: first 2 + last 2 rows.

        If total rows <= 4, return all rows.
        Each cell value is truncated to 1000 chars.
        Returns JSON string or None.
        """
        quoted = connector.quote_identifier(table_name)
        col_names = [c.get("name", "") for c in columns]
        max_cell_len = 1000

        effective_count = row_count if row_count and row_count > 0 else 0

        def _parse_rows(result):
            """Parse connector.run() result, skipping header row.

            connector.run() returns [field_names_tuple, Row1, Row2, ...].
            We skip index 0 (field names) and convert each Row to a list
            of string values.
            """
            if not result or len(result) <= 1:
                return []
            rows = []
            for r in result[1:]:
                # Convert SQLAlchemy Row to plain list of values
                row = list(r)
                rows.append([
                    str(v)[:max_cell_len] if v is not None else "NULL"
                    for v in row
                ])
            logger.debug(
                f"[LEARN] _parse_rows: input len={len(result)}, "
                f"output rows={len(rows)}, "
                f"first_row={rows[0][:3] if rows else 'empty'}..."
            )
            return rows

        if effective_count <= 4:
            # Small table: fetch all
            sql = connector.limit_sql(f"SELECT * FROM {quoted}", 4)
            result = connector.run(sql)
            all_rows = _parse_rows(result)
            if not all_rows:
                return None
            return json.dumps(
                {"columns": col_names, "rows": all_rows},
                ensure_ascii=False,
            )

        # First 2 rows
        head_sql = connector.limit_sql(f"SELECT * FROM {quoted}", 2)
        head_result = connector.run(head_sql)
        head_rows = _parse_rows(head_result)

        # Last 2 rows: use ORDER BY rowid/ctid DESC or subquery
        # Universal approach: offset = max(0, count - 2)
        tail_rows = []
        try:
            offset = max(0, effective_count - 2)
            tail_sql = connector.limit_sql(
                f"SELECT * FROM {quoted}", 2, offset
            )
            tail_result = connector.run(tail_sql)
            tail_rows = _parse_rows(tail_result)
        except Exception:
            logger.debug(
                f"[LEARN] Failed to get tail rows for '{table_name}', "
                "using head only"
            )

        all_rows = head_rows + tail_rows
        if not all_rows:
            return None

        return json.dumps(
            {"columns": col_names, "rows": all_rows},
            ensure_ascii=False,
        )

    def _get_llm_config(self):
        """Lazy-init LLM API config from ModelConfigCache.

        Returns a dict with base_url, api_key, model or None.
        """
        if hasattr(self, "_llm_config_cache"):
            return self._llm_config_cache

        try:
            from derisk.agent.util.llm.model_config_cache import (
                ModelConfigCache,
            )
            all_models = ModelConfigCache.get_all_models()
            logger.info(f"[LLM-INIT] ModelConfigCache models: {all_models}")

            if not all_models:
                logger.warning("[LLM-INIT] No models in ModelConfigCache")
                self._llm_config_cache = None
                return None

            model_name = all_models[0]
            config = ModelConfigCache.get_config(model_name)
            if not config:
                logger.warning(
                    f"[LLM-INIT] No config for model '{model_name}'"
                )
                self._llm_config_cache = None
                return None

            base_url = config.get("base_url") or config.get("api_base", "")
            api_key = config.get("api_key", "")
            model = config.get("model") or model_name

            if not base_url:
                logger.warning("[LLM-INIT] No base_url in model config")
                self._llm_config_cache = None
                return None

            # Ensure base_url ends properly for chat completions
            base_url = base_url.rstrip("/")
            if not base_url.endswith("/v1"):
                if "/v1/" not in base_url and "/v1" not in base_url:
                    base_url += "/v1"

            logger.info(
                f"[LLM-INIT] Success! model='{model}', "
                f"base_url='{base_url}'"
            )
            self._llm_config_cache = {
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
            }
            return self._llm_config_cache
        except Exception as e:
            logger.error(
                f"[LLM-INIT] Failed: {e}\n{traceback.format_exc()}"
            )
            self._llm_config_cache = None
            return None

    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call LLM via OpenAI-compatible API using config from ModelConfigCache."""
        import httpx

        config = self._get_llm_config()
        if not config:
            return None

        url = f"{config['base_url']}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if config["api_key"]:
            headers["Authorization"] = f"Bearer {config['api_key']}"

        payload = {
            "model": config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 200,
        }

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    text = choices[0].get("message", {}).get("content", "")
                    return text.strip() if text else None
        except Exception as e:
            logger.error(
                f"[LLM-API] Request failed: {e}\n{traceback.format_exc()}"
            )
        return None

    def _build_db_context(
        self,
        datasource_id: int,
        db_name: str,
        db_type: str,
        table_names: List[str],
    ) -> Dict[str, str]:
        """Build database-level context for LLM prompts."""
        db_comment = ""
        try:
            config = self._config_dao.get_one({"id": datasource_id})
            if config and hasattr(config, "comment"):
                db_comment = config.comment or ""
        except Exception:
            pass

        return {
            "db_name": db_name,
            "db_type": db_type,
            "db_comment": db_comment,
            "table_list": ", ".join(table_names[:50]),
            "table_count": str(len(table_names)),
        }

    def _generate_single_table_summary(
        self,
        connector,
        table_name: str,
        columns: List[Dict[str, Any]],
        row_count: Optional[int],
        existing_comment: str,
        db_context: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Generate an LLM description for a single table using live data."""
        # Check LLM availability early
        if not self._get_llm_config():
            return None

        logger.info(f"[LLM-GEN] Generating summary for table: {table_name}")

        # --- Build context sections ---

        # Database-level context
        db_section = ""
        if db_context:
            db_section = (
                f"数据库: {db_context.get('db_name', '')} "
                f"(类型: {db_context.get('db_type', '')})\n"
            )
            db_comment = db_context.get("db_comment", "")
            if db_comment:
                db_section += f"数据库描述: {db_comment}\n"
            db_section += (
                f"所有表 ({db_context.get('table_count', '')}个):"
                f" {db_context.get('table_list', '')}\n"
            )

        # Column info (with comments)
        col_parts = []
        for c in columns[:20]:
            name = c.get("name", "")
            ctype = c.get("type", "")
            ccomment = c.get("comment", "")
            pk = " [PK]" if c.get("pk") else ""
            if ccomment:
                col_parts.append(f"{name}({ctype}{pk}) -- {ccomment}")
            else:
                col_parts.append(f"{name}({ctype}{pk})")
        col_desc = "\n".join(col_parts)
        if len(columns) > 20:
            col_desc += f"\n... (共{len(columns)}列)"

        # Table comment
        comment_section = ""
        if existing_comment:
            comment_section = f"表注释: {existing_comment}\n"

        # Row count
        row_section = ""
        if row_count is not None:
            row_section = f"数据行数: {row_count}\n"

        # Sample data (3 rows)
        sample_section = ""
        try:
            sample_result = connector.run(
                connector.limit_sql(
                    f"SELECT * FROM {connector.quote_identifier(table_name)}", 3
                )
            )
            if sample_result and len(sample_result) > 1:
                col_names = [c.get("name", "") for c in columns[:10]]
                sample_section = (
                    f"样例数据 (列: {', '.join(col_names)}):\n"
                )
                for row in sample_result[1:]:
                    row = tuple(row)
                    vals = [
                        str(v)[:50] if v is not None else "NULL"
                        for v in row[:10]
                    ]
                    sample_section += f"  {vals}\n"
        except Exception:
            pass

        prompt = (
            f"你是一个数据库专家。根据以下数据库表的背景信息、结构、注释和样例数据，"
            f"用中文写一句话介绍这个表存储的数据内容和用途。\n"
            f"要求：只输出介绍内容，不超过100个字，不要输出其他任何内容。\n\n"
            f"{db_section}"
            f"表名: {table_name}\n"
            f"{comment_section}"
            f"{row_section}"
            f"字段:\n{col_desc}\n"
            f"{sample_section}"
        )

        result = self._call_llm(prompt)
        if result:
            # Remove surrounding quotes if present
            if (
                len(result) > 2
                and result[0] in ('"', "'", "\u201c")
                and result[-1] in ('"', "'", "\u201d")
            ):
                result = result[1:-1]
            if len(result) > 200:
                result = result[:200]
            logger.info(
                f"[LLM-GEN] Summary for {table_name}: {result[:80]}"
            )
            return result

        logger.warning(
            f"[LLM-GEN] No summary generated for {table_name}"
        )
        return None

    def _detect_table_relations(
        self, datasource_id: int
    ) -> List[Dict[str, Any]]:
        """Detect table relationships from DDL foreign keys and naming conventions.

        Called after all tables are learned. Results stored in DbSpec.
        """
        table_specs = self._table_spec_dao.get_all_by_datasource(datasource_id)
        all_tables: Set[str] = set()
        for spec in table_specs:
            tname = spec.get("table_name", "")
            if tname:
                all_tables.add(tname)

        relations = []
        seen: Set[tuple] = set()

        for spec in table_specs:
            tname = spec.get("table_name", "")
            if not tname:
                continue

            # Method 1: Foreign keys from DDL
            ddl = spec.get("create_ddl", "") or ""
            fk_matches = re.findall(
                r"FOREIGN\s+KEY.*?REFERENCES\s+`?(\w+)`?", ddl, re.IGNORECASE
            )
            for ref_table in fk_matches:
                key = (tname, ref_table, "foreign_key")
                if key not in seen:
                    seen.add(key)
                    relations.append({
                        "from_table": tname,
                        "to_table": ref_table,
                        "type": "foreign_key",
                    })

            # Method 2: Naming convention (xxx_id → xxx / xxxs table)
            columns = spec.get("columns", []) or []
            for col in columns:
                col_name = col.get("name", "")
                if col_name.endswith("_id") and col_name != "id":
                    candidate = col_name[:-3]
                    for t in all_tables:
                        if t == tname:
                            continue
                        if t.lower() == candidate.lower() or t.lower() == (
                            candidate + "s"
                        ).lower():
                            key = (tname, t, "naming_convention")
                            if key not in seen:
                                seen.add(key)
                                relations.append({
                                    "from_table": tname,
                                    "to_table": t,
                                    "type": "naming_convention",
                                    "column": col_name,
                                })

        return relations

    def _detect_sensitive_columns(self, datasource_id: int) -> None:
        """Auto-detect sensitive columns from learned table specs.

        Runs the SensitiveColumnDetector on all table specs and saves
        detected columns to the config database.
        """
        try:
            from derisk_serve.sql_guard.masking.config_db import SensitiveColumnDao
            from derisk_serve.sql_guard.masking.detector import (
                SensitiveColumnDetector,
            )
            from derisk_serve.sql_guard.masking.masker import (
                ColumnMaskingConfig,
                get_data_masker,
            )

            detector = SensitiveColumnDetector()
            dao = SensitiveColumnDao()
            table_specs = self._table_spec_dao.get_all_by_datasource(datasource_id)

            detections = detector.detect_batch(table_specs)
            count = 0

            for table_name, columns in detections.items():
                for col_info in columns:
                    dao.upsert(
                        datasource_id=datasource_id,
                        table_name=col_info.table_name,
                        column_name=col_info.column_name,
                        data={
                            "sensitive_type": col_info.sensitive_type,
                            "masking_mode": (
                                "mask" if col_info.masking_strategy == "full"
                                else col_info.masking_strategy
                            ),
                            "confidence": col_info.confidence,
                            "source": "auto",
                            "enabled": 1,
                        },
                    )
                    count += 1

            # Load detected configs into the masker singleton
            if count > 0:
                self._load_masking_configs(datasource_id)
                logger.info(
                    f"Detected {count} sensitive columns for "
                    f"datasource {datasource_id}"
                )

        except ImportError:
            logger.debug("Masking module not available, skipping detection")
        except Exception as e:
            logger.warning(f"Sensitive column detection failed: {e}")

    def _load_masking_configs(self, datasource_id: int) -> None:
        """Load sensitive column configs into the DataMasker singleton."""
        try:
            from derisk_serve.sql_guard.masking.config_db import SensitiveColumnDao
            from derisk_serve.sql_guard.masking.masker import (
                ColumnMaskingConfig,
                get_data_masker,
            )

            dao = SensitiveColumnDao()
            masker = get_data_masker()
            configs = dao.get_enabled_by_datasource(datasource_id)

            for cfg in configs:
                masker.configure_column(ColumnMaskingConfig(
                    table_name=cfg["table_name"],
                    column_name=cfg["column_name"],
                    sensitive_type=cfg["sensitive_type"],
                    mode=cfg.get("masking_mode", "mask"),
                ))
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to load masking configs: {e}")

    def _apply_grouping(
        self, spec_entries: List[Dict[str, Any]]
    ) -> tuple:
        """Apply table grouping based on naming prefix.

        When there are many tables (>30), group them by common naming
        prefix (e.g., 'sys_', 'biz_', 'log_') for better organization.

        Returns:
            Tuple of (updated spec entries, group config dict).
        """
        prefix_groups = defaultdict(list)

        for entry in spec_entries:
            table_name = entry["table_name"]
            # Extract prefix: everything before the first underscore
            parts = table_name.split("_", 1)
            if len(parts) > 1 and len(parts[0]) <= 10:
                prefix = parts[0]
            else:
                prefix = "other"
            prefix_groups[prefix].append(entry)

        # Only keep groups with at least 2 tables
        final_groups = {}
        ungrouped = []
        for prefix, entries in prefix_groups.items():
            if len(entries) >= 2:
                final_groups[prefix] = entries
            else:
                ungrouped.extend(entries)

        if ungrouped:
            final_groups["other"] = ungrouped

        # Update group names in entries
        updated_entries = []
        for group_name, entries in final_groups.items():
            for entry in entries:
                entry["group"] = group_name
                updated_entries.append(entry)

        group_config = {
            "strategy": "prefix",
            "groups": {
                name: len(entries) for name, entries in final_groups.items()
            },
        }

        return updated_entries, group_config

    def learn_incremental(
        self,
        datasource_id: int,
        db_name: str,
        db_type: str,
        trigger_type: str = "manual",
    ) -> Dict[str, Any]:
        """Incremental learning: only process new, changed, or removed tables.

        Compares current database state with stored specs to detect:
        - New tables (not in specs)
        - Removed tables (in specs but not in database)
        - Changed tables (DDL differs from stored DDL)

        Only the affected tables are re-learned, which is much faster
        than full learning for large databases.
        """
        running = self._learning_task_dao.get_running_by_datasource(datasource_id)
        if running:
            return running

        task = self._learning_task_dao.create({
            "datasource_id": datasource_id,
            "task_type": "incremental",
            "status": "running",
            "progress": 0,
            "trigger_type": trigger_type,
        })
        task_id = task["id"]

        try:
            connector = self._connector_manager.get_connector(db_name)
            current_tables = set(connector.get_table_names())

            existing_specs = self._table_spec_dao.get_all_by_datasource(
                datasource_id
            )
            existing_tables = {s["table_name"] for s in existing_specs}
            existing_ddls = {
                s["table_name"]: s.get("create_ddl", "") for s in existing_specs
            }

            new_tables = current_tables - existing_tables
            removed_tables = existing_tables - current_tables

            # Detect DDL changes
            changed_tables = set()
            for table_name in current_tables & existing_tables:
                try:
                    current_ddl = connector.get_show_create_table(table_name)
                    if current_ddl != existing_ddls.get(table_name, ""):
                        changed_tables.add(table_name)
                except Exception:
                    pass

            tables_to_learn = new_tables | changed_tables
            total_work = len(tables_to_learn) + len(removed_tables)

            self._learning_task_dao.update_progress(task_id, 0, total_work)

            # Remove specs for deleted tables
            for t in removed_tables:
                self._table_spec_dao.delete_by_table(datasource_id, t)

            # Learn new/changed tables
            processed = len(removed_tables)
            for table_name in tables_to_learn:
                try:
                    self._learn_single_table(
                        connector, datasource_id, table_name
                    )
                except Exception as e:
                    logger.error(f"Error learning table {table_name}: {e}")

                processed += 1
                self._learning_task_dao.update_progress(
                    task_id, processed, total_work
                )

            # Regenerate db-level spec
            self._regenerate_db_spec(datasource_id, db_name)

            # Re-detect relations
            relations = self._detect_table_relations(datasource_id)
            if relations:
                self._db_spec_dao.upsert(datasource_id, {
                    "relations": json.dumps(relations, ensure_ascii=False),
                })

            # Re-detect sensitive columns
            self._detect_sensitive_columns(datasource_id)

            self._learning_task_dao.update_progress(
                task_id, total_work, total_work, status="completed"
            )

            logger.info(
                f"Incremental learning for ds={datasource_id}: "
                f"new={len(new_tables)}, changed={len(changed_tables)}, "
                f"removed={len(removed_tables)}"
            )

            return self._learning_task_dao.get_one({"id": task_id})

        except Exception as e:
            logger.error(f"Incremental learning failed: {e}")
            self._learning_task_dao.update_progress(
                task_id, 0, 0, status="failed", error_message=str(e)[:2000]
            )
            raise

    def learn_single_table(
        self, datasource_id: int, db_name: str, table_name: str
    ) -> Dict[str, Any]:
        """Learn a single table and update its spec.

        Args:
            datasource_id: The datasource config ID.
            db_name: The database name.
            table_name: The table to learn.

        Returns:
            The updated table spec dict.
        """
        connector = self._connector_manager.get_connector(db_name)
        result = self._learn_single_table(connector, datasource_id, table_name)

        # Regenerate db-level spec
        self._regenerate_db_spec(datasource_id, db_name)

        return result

    def _regenerate_db_spec(
        self, datasource_id: int, db_name: str
    ) -> None:
        """Regenerate the database-level spec from existing table specs."""
        table_specs = self._table_spec_dao.get_all_by_datasource(datasource_id)
        existing_db_spec = self._db_spec_dao.get_by_datasource_id(datasource_id)
        db_type = existing_db_spec.get("db_type", "") if existing_db_spec else ""

        spec_entries = []
        for spec in table_specs:
            columns = spec.get("columns", [])
            table_name = spec.get("table_name", "")
            comment = spec.get("table_comment", "") or ""
            spec_entries.append({
                "table_name": table_name,
                "summary": comment,
                "row_count": spec.get("row_count"),
                "column_count": len(columns or []),
                "group": spec.get("group_name", "default"),
            })

        group_config = None
        if len(spec_entries) > TABLE_GROUP_THRESHOLD:
            spec_entries, group_config = self._apply_grouping(spec_entries)

        self._db_spec_dao.upsert(datasource_id, {
            "db_name": db_name,
            "db_type": db_type,
            "spec_content": json.dumps(spec_entries, ensure_ascii=False),
            "table_count": len(spec_entries),
            "group_config": (
                json.dumps(group_config, ensure_ascii=False)
                if group_config
                else None
            ),
            "status": "ready",
        })

    def get_learning_status(
        self, datasource_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get the latest learning task status for a datasource."""
        return self._learning_task_dao.get_latest_by_datasource(datasource_id)

    def delete_by_datasource_id(self, datasource_id: int) -> None:
        """Delete all learning data for a datasource."""
        self._db_spec_dao.delete_by_datasource_id(datasource_id)
        self._table_spec_dao.delete_by_datasource_id(datasource_id)
        self._subtask_dao.delete_by_datasource_id(datasource_id)
        self._learning_task_dao.delete_by_datasource_id(datasource_id)
