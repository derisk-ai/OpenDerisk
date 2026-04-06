"""Service for managing database and table spec documents."""

import json
import logging
from typing import Any, Dict, List, Optional

from derisk_serve.datasource.manages.db_spec_db import DbSpecDao
from derisk_serve.datasource.manages.table_spec_db import TableSpecDao

logger = logging.getLogger(__name__)


class DbSpecService:
    """Service for querying and formatting spec documents."""

    def __init__(self):
        self._db_spec_dao = DbSpecDao()
        self._table_spec_dao = TableSpecDao()

    def get_db_spec(self, datasource_id: int) -> Optional[Dict[str, Any]]:
        """Get the database-level spec document."""
        return self._db_spec_dao.get_by_datasource_id(datasource_id)

    def get_table_spec(
        self, datasource_id: int, table_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get a single table spec."""
        return self._table_spec_dao.get_by_datasource_and_table(
            datasource_id, table_name
        )

    def get_table_specs(
        self, datasource_id: int, table_names: List[str]
    ) -> List[Dict[str, Any]]:
        """Get multiple table specs by name."""
        results = []
        for name in table_names:
            spec = self._table_spec_dao.get_by_datasource_and_table(
                datasource_id, name
            )
            if spec:
                results.append(spec)
        return results

    def get_all_table_specs(
        self, datasource_id: int
    ) -> List[Dict[str, Any]]:
        """Get all table specs for a datasource."""
        return self._table_spec_dao.get_all_by_datasource(datasource_id)

    def has_spec(self, datasource_id: int) -> bool:
        """Check if a datasource has a ready spec."""
        spec = self._db_spec_dao.get_by_datasource_id(datasource_id)
        if spec and spec.get("status") == "ready":
            return True
        return False

    def format_db_spec_for_prompt(self, datasource_id: int) -> str:
        """Format the database spec for injection into agent prompt.

        Returns a compact overview of all tables grouped by category.
        """
        spec = self._db_spec_dao.get_by_datasource_id(datasource_id)
        if not spec:
            return ""

        db_type = spec.get("db_type", "unknown")
        spec_content = spec.get("spec_content", [])
        if not spec_content:
            return ""

        # Group tables
        groups: Dict[str, List[Dict]] = {}
        for table_info in spec_content:
            group = table_info.get("group", "default")
            if group not in groups:
                groups[group] = []
            groups[group].append(table_info)

        lines = [f"Database type: {db_type}, database tables overview:"]

        if len(groups) == 1 and "default" in groups:
            # No grouping needed
            for t in groups["default"]:
                summary = t.get("summary", t.get("table_name", ""))
                row_count = t.get("row_count")
                row_info = f", {row_count} rows" if row_count is not None else ""
                lines.append(f"- {summary}{row_info}")
        else:
            for group_name, tables in groups.items():
                lines.append(f"\n[{group_name}]")
                for t in tables:
                    summary = t.get("summary", t.get("table_name", ""))
                    row_count = t.get("row_count")
                    row_info = (
                        f", {row_count} rows" if row_count is not None else ""
                    )
                    lines.append(f"- {summary}{row_info}")

        # Add relations if present
        relations = spec.get("relations", [])
        if relations:
            lines.append("\nTable relations:")
            for rel in relations:
                from_t = rel.get("from_table", "")
                to_t = rel.get("to_table", "")
                col = rel.get("column", "")
                rel_type = rel.get("type", "")
                if col:
                    lines.append(f"- {from_t}.{col} -> {to_t} ({rel_type})")
                else:
                    lines.append(f"- {from_t} -> {to_t} ({rel_type})")

        return "\n".join(lines)

    def _get_sensitive_columns(
        self, datasource_id: int
    ) -> Dict[str, Dict[str, str]]:
        """Get sensitive column configs indexed by table.column key.

        Returns:
            Dict mapping "table_name.column_name" -> {sensitive_type, masking_mode}
        """
        try:
            from derisk_serve.sql_guard.masking.config_db import SensitiveColumnDao

            dao = SensitiveColumnDao()
            configs = dao.get_enabled_by_datasource(datasource_id)
            result = {}
            for cfg in configs:
                key = f"{cfg['table_name']}.{cfg['column_name']}"
                result[key] = {
                    "sensitive_type": cfg["sensitive_type"],
                    "masking_mode": cfg.get("masking_mode", "mask"),
                }
            return result
        except ImportError:
            return {}
        except Exception:
            return {}

    def format_table_specs_for_prompt(
        self, datasource_id: int, table_names: List[str]
    ) -> str:
        """Format specific table specs for injection into agent prompt.

        Returns detailed schema information for the requested tables.
        Sensitive columns are annotated so the Agent knows they are masked.
        """
        specs = self.get_table_specs(datasource_id, table_names)
        if not specs:
            return ""

        # Load sensitive column info
        sensitive_map = self._get_sensitive_columns(datasource_id)

        parts = []
        for spec in specs:
            table_name = spec.get("table_name", "")
            comment = spec.get("table_comment", "")
            columns = spec.get("columns", [])
            indexes = spec.get("indexes", [])
            sample_data = spec.get("sample_data")
            ddl = spec.get("create_ddl", "")

            lines = [f"## Table: {table_name}"]
            if comment:
                lines.append(f"Comment: {comment}")

            # DDL
            if ddl:
                lines.append(f"\nCREATE TABLE statement:\n{ddl}")

            # Columns
            if columns:
                lines.append("\nColumns:")
                for col in columns:
                    col_name = col.get("name", "")
                    col_type = col.get("type", "")
                    col_comment = col.get("comment", "")
                    nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
                    pk = " [PK]" if col.get("pk", False) else ""
                    comment_str = f" -- {col_comment}" if col_comment else ""
                    # Distribution info
                    dist = col.get("distribution")
                    dist_str = ""
                    if dist and dist.get("type") == "enum":
                        values = dist.get("values", [])
                        if values:
                            dist_str = (
                                f" values: [{', '.join(str(v) for v in values[:10])}]"
                            )
                    # Sensitive column annotation
                    sens_key = f"{table_name}.{col_name}"
                    sens_info = sensitive_map.get(sens_key)
                    sens_str = ""
                    if sens_info:
                        stype = sens_info["sensitive_type"]
                        smode = sens_info["masking_mode"]
                        sens_str = f" [MASKED:{stype}/{smode}]"
                    lines.append(
                        f"  - {col_name} {col_type} {nullable}{pk}{comment_str}{dist_str}{sens_str}"
                    )

            # Indexes
            if indexes:
                lines.append("\nIndexes:")
                for idx in indexes:
                    idx_name = idx.get("name", "")
                    idx_cols = ", ".join(idx.get("columns", []))
                    unique = " (UNIQUE)" if idx.get("unique", False) else ""
                    lines.append(f"  - {idx_name}({idx_cols}){unique}")

            # Sample data
            if sample_data:
                sample_cols = sample_data.get("columns", [])
                sample_rows = sample_data.get("rows", [])
                if sample_cols and sample_rows:
                    lines.append(f"\nSample data ({len(sample_rows)} rows):")
                    lines.append("  " + " | ".join(str(c) for c in sample_cols))
                    lines.append("  " + "-" * 40)
                    for row in sample_rows[:5]:
                        lines.append(
                            "  " + " | ".join(str(v) for v in row)
                        )

            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    def delete_by_datasource_id(self, datasource_id: int) -> None:
        """Delete all specs for a datasource."""
        self._db_spec_dao.delete_by_datasource_id(datasource_id)
        self._table_spec_dao.delete_by_datasource_id(datasource_id)
