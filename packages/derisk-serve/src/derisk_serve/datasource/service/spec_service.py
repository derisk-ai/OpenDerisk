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

    def get_db_stats(self, datasource_id: int) -> Dict[str, Any]:
        """Get database statistics including table count and group distribution.

        Returns:
            Dict with keys:
            - total_tables: Total number of tables
            - groups: Dict of group_name -> table_count
            - has_spec: Whether spec document exists
            - spec_status: Status of spec document
        """
        spec = self._db_spec_dao.get_by_datasource_id(datasource_id)

        if not spec:
            return {
                "total_tables": 0,
                "groups": {},
                "has_spec": False,
                "spec_status": "not_found",
            }

        spec_content = spec.get("spec_content", [])
        if isinstance(spec_content, str):
            try:
                spec_content = json.loads(spec_content)
            except (json.JSONDecodeError, TypeError):
                spec_content = []

        # Count tables by group
        groups: Dict[str, int] = {}
        for table_info in spec_content:
            group = table_info.get("group", "default")
            groups[group] = groups.get(group, 0) + 1

        return {
            "total_tables": len(spec_content),
            "groups": groups,
            "has_spec": spec.get("status") == "ready",
            "spec_status": spec.get("status", "unknown"),
        }

    def format_db_spec_for_prompt(
        self,
        datasource_id: int,
        mode: str = "small",
        max_tables: Optional[int] = None,
    ) -> str:
        """Format the database spec for injection into agent prompt.

        Args:
            datasource_id: The datasource ID
            mode: Injection mode - "small" (full), "medium" (compact), "large" (stats)
            max_tables: Maximum tables to display (for medium mode truncation)

        Returns:
            Formatted table list or stats summary based on mode
        """
        # Large mode: return stats only
        if mode == "large":
            stats = self.get_db_stats(datasource_id)
            return self._format_db_stats(stats)

        spec = self._db_spec_dao.get_by_datasource_id(datasource_id)
        if not spec:
            return ""

        spec_content = spec.get("spec_content", [])
        if not spec_content:
            return ""

        # Apply truncation for medium mode
        total_tables = len(spec_content)
        if mode == "medium" and max_tables:
            spec_content = spec_content[:max_tables]

        # Group tables
        groups: Dict[str, List[Dict]] = {}
        for table_info in spec_content:
            group = table_info.get("group", "default")
            if group not in groups:
                groups[group] = []
            groups[group].append(table_info)

        lines: List[str] = []

        def _fmt_table(t: Dict, compact: bool = False) -> str:
            name = t.get("table_name", "")
            if compact:
                return f"- {name}"
            summary = t.get("summary", "")
            if summary:
                return f"- {name}: {summary}"
            return f"- {name}"

        compact = mode == "medium"

        if len(groups) == 1 and "default" in groups:
            for t in groups["default"]:
                lines.append(_fmt_table(t, compact))
        else:
            for group_name, tables in groups.items():
                lines.append(f"\n[{group_name}]")
                for t in tables:
                    lines.append(_fmt_table(t, compact))

        # Add truncation notice for medium mode
        if mode == "medium" and max_tables and total_tables > max_tables:
            lines.append(f"\n... (共 {total_tables} 张表，显示前 {max_tables} 张)")
            lines.append("_使用 list_tables 或 search_tables 工具查看完整列表_")

        # Relations only in small mode
        if mode == "small":
            relations = spec.get("relations", [])
            if relations:
                lines.append("\nRelations:")
                for rel in relations:
                    from_t = rel.get("from_table", "")
                    to_t = rel.get("to_table", "")
                    col = rel.get("column", "")
                    if col:
                        lines.append(f"- {from_t}.{col} -> {to_t}")
                    else:
                        lines.append(f"- {from_t} -> {to_t}")

        return "\n".join(lines)

    def _format_db_stats(self, stats: Dict[str, Any]) -> str:
        """Format database stats for large DB injection."""
        if not stats.get("has_spec"):
            return "（数据库规格文档尚未生成，请使用 list_tables 工具获取表列表）"

        total = stats.get("total_tables", 0)
        groups = stats.get("groups", {})

        lines = [f"**数据库统计信息**"]
        lines.append(f"- 总表数: {total}")

        if groups:
            lines.append("- 表分组统计:")
            for group_name, count in sorted(groups.items(), key=lambda x: -x[1]):
                lines.append(f"  - {group_name}: {count} 张表")

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
            foreign_keys = spec.get("foreign_keys", [])
            row_count = spec.get("row_count")
            sample_data = spec.get("sample_data")
            ddl = spec.get("create_ddl", "")

            lines = [f"## Table: {table_name}"]
            if comment:
                lines.append(f"Comment: {comment}")

            # Data profile: row count + enum columns summary
            profile_parts = []
            if row_count is not None:
                profile_parts.append(f"Rows: {row_count}")
            profile_parts.append(f"Columns: {len(columns)}")
            # Collect enum columns
            enum_cols = []
            for col in columns:
                dist = col.get("distribution")
                if dist and dist.get("type") == "enum":
                    values = dist.get("values", [])
                    if values:
                        enum_cols.append(
                            f"{col.get('name', '')}=[{', '.join(str(v) for v in values[:10])}]"
                        )
            if enum_cols:
                profile_parts.append(f"Enum columns: {', '.join(enum_cols)}")
            lines.append("\nData profile: " + " | ".join(profile_parts))

            # DDL
            if ddl:
                lines.append(f"\nCREATE TABLE statement:\n{ddl}")

            # Column extra info (comment, sensitive) not in DDL
            # (enum distribution already shown in Data profile)
            extra_lines = []
            if columns:
                for col in columns:
                    col_name = col.get("name", "")
                    parts_col = []
                    # Column comment
                    col_comment = col.get("comment", "")
                    if col_comment:
                        parts_col.append(f"comment: {col_comment}")
                    # Sensitive column annotation
                    sens_key = f"{table_name}.{col_name}"
                    sens_info = sensitive_map.get(sens_key)
                    if sens_info:
                        stype = sens_info["sensitive_type"]
                        smode = sens_info["masking_mode"]
                        parts_col.append(f"MASKED:{stype}/{smode}")
                    if parts_col:
                        extra_lines.append(
                            f"  - {col_name}: {', '.join(parts_col)}"
                        )
            if extra_lines:
                lines.append("\nColumn details:")
                lines.extend(extra_lines)

            # Indexes
            if indexes:
                lines.append("\nIndexes:")
                for idx in indexes:
                    idx_name = idx.get("name", "")
                    idx_cols = ", ".join(idx.get("columns", []))
                    unique = " (UNIQUE)" if idx.get("unique", False) else ""
                    lines.append(f"  - {idx_name}({idx_cols}){unique}")

            # Foreign keys
            if foreign_keys:
                lines.append("\nForeign keys:")
                for fk in foreign_keys:
                    src_cols = ", ".join(fk.get("constrained_columns", []))
                    ref_table = fk.get("referred_table", "")
                    ref_cols = ", ".join(fk.get("referred_columns", []))
                    lines.append(
                        f"  - ({src_cols}) -> {ref_table}({ref_cols})"
                    )

            # Sample data - 应用隐私策略脱敏
            if sample_data:
                sample_cols = sample_data.get("columns", [])
                sample_rows = sample_data.get("rows", [])
                if sample_cols and sample_rows:
                    # 应用脱敏
                    masked_rows = self._mask_sample_data(
                        sample_cols, sample_rows, table_name, sensitive_map
                    )
                    lines.append(f"\nSample data ({len(sample_rows)} rows):")
                    lines.append(" | ".join(str(c) for c in sample_cols))
                    for row in masked_rows:
                        lines.append(
                            " | ".join(str(v) for v in row)
                        )

            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    def delete_by_datasource_id(self, datasource_id: int) -> None:
        """Delete all specs for a datasource."""
        self._db_spec_dao.delete_by_datasource_id(datasource_id)
        self._table_spec_dao.delete_by_datasource_id(datasource_id)

    def _mask_sample_data(
        self,
        columns: List[str],
        rows: List[List],
        table_name: str,
        sensitive_map: Dict[str, Dict[str, str]],
    ) -> List[List]:
        """Mask sensitive columns in sample data.

        Uses DataMasker._partial_mask static method to apply format-preserving
        masking to sensitive column values (phone, email, id_card, etc.).

        Args:
            columns: Column name list
            rows: Data rows list
            table_name: Table name for config lookup
            sensitive_map: Dict mapping "table.column" -> {sensitive_type, masking_mode}

        Returns:
            List of masked rows
        """
        # Import DataMasker for partial_mask method
        try:
            from derisk_serve.sql_guard.masking.masker import DataMasker
        except ImportError:
            return rows  # Masker not available, return original

        # Build column index -> sensitive_type mapping
        mask_plan = {}
        for idx, col_name in enumerate(columns):
            key = f"{table_name}.{col_name}"
            if key in sensitive_map:
                mask_plan[idx] = sensitive_map[key]["sensitive_type"]

        if not mask_plan:
            return rows  # No sensitive columns, return original

        # Apply masking
        masked_rows = []
        for row in rows:
            masked_row = list(row)
            for idx, sensitive_type in mask_plan.items():
                if idx < len(masked_row) and masked_row[idx] is not None:
                    # Apply format-preserving partial masking
                    masked_row[idx] = DataMasker._partial_mask(
                        str(masked_row[idx]), sensitive_type
                    )
            masked_rows.append(masked_row)

        return masked_rows
