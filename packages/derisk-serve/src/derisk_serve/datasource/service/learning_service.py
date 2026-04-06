"""Service for database schema learning and spec generation."""

import json
import logging
import re
import traceback
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from derisk_serve.datasource.manages.connect_config_db import ConnectConfigDao
from derisk_serve.datasource.manages.db_spec_db import DbSpecDao
from derisk_serve.datasource.manages.learning_task_db import DbLearningTaskDao
from derisk_serve.datasource.manages.table_spec_db import TableSpecDao

logger = logging.getLogger(__name__)

# Threshold for table grouping
TABLE_GROUP_THRESHOLD = 30
# Max sample rows per table
MAX_SAMPLE_ROWS = 5
# Max characters per sample value
MAX_SAMPLE_VALUE_LENGTH = 100


class SchemaLearningService:
    """Service for learning database schema and generating spec documents.

    Connects to a database, introspects all tables, collects metadata
    (columns, indexes, comments, sample data, DDL), and generates
    per-table specs and a database-level spec index.
    """

    def __init__(self, connector_manager):
        """Initialize with a ConnectorManager instance.

        Args:
            connector_manager: The ConnectorManager used to create
                database connectors.
        """
        self._connector_manager = connector_manager
        self._db_spec_dao = DbSpecDao()
        self._table_spec_dao = TableSpecDao()
        self._learning_task_dao = DbLearningTaskDao()
        self._config_dao = ConnectConfigDao()

    def learn_database(
        self,
        datasource_id: int,
        db_name: str,
        db_type: str,
        trigger_type: str = "manual",
    ) -> Dict[str, Any]:
        """Run a full schema learning task for a database.

        This is designed to run in a background thread. It:
        1. Creates a learning task record
        2. Connects to the database
        3. Iterates all tables, collecting metadata
        4. Generates per-table specs
        5. Generates the database-level spec index

        Args:
            datasource_id: The datasource config ID.
            db_name: The database name (used to get connector).
            db_type: The database type string.
            trigger_type: How the learning was triggered.

        Returns:
            The learning task dict.
        """
        # Check for already-running task
        running = self._learning_task_dao.get_running_by_datasource(datasource_id)
        if running:
            logger.warning(
                f"Learning task already running for datasource {datasource_id}"
            )
            return running

        # Create learning task
        task = self._learning_task_dao.create({
            "datasource_id": datasource_id,
            "task_type": "full_learn",
            "status": "running",
            "progress": 0,
            "trigger_type": trigger_type,
        })
        task_id = task["id"]

        # Update db spec status to generating
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
            total_tables = len(table_names)

            self._learning_task_dao.update_progress(
                task_id, 0, total_tables
            )

            spec_entries = []
            processed = 0

            for table_name in table_names:
                try:
                    table_spec = self._learn_single_table(
                        connector, datasource_id, table_name
                    )
                    # Build spec entry for db-level index
                    columns = table_spec.get("columns", [])
                    col_summary = ", ".join(
                        c.get("name", "") for c in (columns or [])[:8]
                    )
                    if len(columns or []) > 8:
                        col_summary += ", ..."

                    comment = table_spec.get("table_comment", "") or ""
                    summary = f"{table_name}({col_summary})"
                    if comment:
                        summary += f" -- {comment}"

                    spec_entries.append({
                        "table_name": table_name,
                        "summary": summary,
                        "row_count": table_spec.get("row_count"),
                        "column_count": len(columns or []),
                        "group": "default",
                    })
                except Exception as e:
                    logger.error(
                        f"Error learning table {table_name}: {e}\n"
                        f"{traceback.format_exc()}"
                    )
                    # Continue with other tables
                    spec_entries.append({
                        "table_name": table_name,
                        "summary": f"{table_name} -- [error: {str(e)[:100]}]",
                        "row_count": None,
                        "column_count": 0,
                        "group": "default",
                    })

                processed += 1
                self._learning_task_dao.update_progress(
                    task_id, processed, total_tables
                )

            # Apply table grouping if needed
            group_config = None
            if total_tables > TABLE_GROUP_THRESHOLD:
                spec_entries, group_config = self._apply_grouping(spec_entries)

            # Detect table relations
            relations = self._detect_table_relations(datasource_id)

            # Auto-detect sensitive columns
            self._detect_sensitive_columns(datasource_id)

            # Save db-level spec (including relations)
            spec_data = {
                "db_name": db_name,
                "db_type": db_type,
                "spec_content": json.dumps(spec_entries, ensure_ascii=False),
                "table_count": total_tables,
                "group_config": (
                    json.dumps(group_config, ensure_ascii=False)
                    if group_config
                    else None
                ),
                "status": "ready",
            }
            if relations:
                spec_data["relations"] = json.dumps(
                    relations, ensure_ascii=False
                )
            self._db_spec_dao.upsert(datasource_id, spec_data)

            # Mark task completed
            self._learning_task_dao.update_progress(
                task_id, total_tables, total_tables, status="completed"
            )

            return self._learning_task_dao.get_one({"id": task_id})

        except Exception as e:
            logger.error(
                f"Learning failed for datasource {datasource_id}: {e}\n"
                f"{traceback.format_exc()}"
            )
            self._learning_task_dao.update_progress(
                task_id, 0, 0, status="failed", error_message=str(e)[:2000]
            )
            self._db_spec_dao.upsert(datasource_id, {
                "db_name": db_name,
                "db_type": db_type,
                "spec_content": "[]",
                "table_count": 0,
                "status": "failed",
            })
            raise

    def _learn_single_table(
        self, connector, datasource_id: int, table_name: str
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
            pk_info = connector._inspector.get_pk_constraint(table_name)
            if pk_info and pk_info.get("constrained_columns"):
                pk_columns = set(pk_info["constrained_columns"])
        except Exception:
            pass

        # Foreign keys
        foreign_keys = []
        try:
            fk_list = connector._inspector.get_foreign_keys(table_name)
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
        row_count = None
        try:
            result = connector.run(f"SELECT COUNT(*) FROM `{table_name}`")
            if result and len(result) > 0:
                row_val = result[0]
                if isinstance(row_val, (list, tuple)) and len(row_val) > 0:
                    row_count = int(row_val[0])
                elif isinstance(row_val, (int, float)):
                    row_count = int(row_val)
        except Exception:
            pass

        # Sample data
        sample_data = None
        try:
            sample_result = connector.run(
                f"SELECT * FROM `{table_name}` LIMIT {MAX_SAMPLE_ROWS}"
            )
            if sample_result:
                sample_cols = [c.get("name", "") for c in columns_raw]
                sample_rows = []
                for row in sample_result:
                    if isinstance(row, (list, tuple)):
                        truncated = [
                            str(v)[:MAX_SAMPLE_VALUE_LENGTH] if v is not None else None
                            for v in row
                        ]
                        sample_rows.append(truncated)
                if sample_rows:
                    sample_data = {
                        "columns": sample_cols,
                        "rows": sample_rows,
                    }
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
                        f"SELECT DISTINCT `{col_name}` FROM `{table_name}` LIMIT 20"
                    )
                    if dist_result and len(dist_result) <= 15:
                        values = []
                        for row in dist_result:
                            if isinstance(row, (list, tuple)) and len(row) > 0:
                                if row[0] is not None:
                                    values.append(
                                        str(row[0])[:MAX_SAMPLE_VALUE_LENGTH]
                                    )
                            elif row is not None:
                                values.append(str(row)[:MAX_SAMPLE_VALUE_LENGTH])
                        if values:
                            col["distribution"] = {
                                "type": "enum",
                                "values": values,
                            }
                except Exception:
                    pass

        # Determine group name from table name prefix
        group_name = "default"

        # Persist
        table_data = {
            "table_comment": table_comment,
            "row_count": row_count,
            "columns_json": json.dumps(columns, ensure_ascii=False),
            "indexes_json": json.dumps(indexes, ensure_ascii=False),
            "sample_data_json": (
                json.dumps(sample_data, ensure_ascii=False) if sample_data else None
            ),
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
            "sample_data": sample_data,
            "create_ddl": create_ddl,
            "group_name": group_name,
        }

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
            col_summary = ", ".join(
                c.get("name", "") for c in (columns or [])[:8]
            )
            if len(columns or []) > 8:
                col_summary += ", ..."

            comment = spec.get("table_comment", "") or ""
            table_name = spec.get("table_name", "")
            summary = f"{table_name}({col_summary})"
            if comment:
                summary += f" -- {comment}"

            spec_entries.append({
                "table_name": table_name,
                "summary": summary,
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
        self._learning_task_dao.delete_by_datasource_id(datasource_id)
