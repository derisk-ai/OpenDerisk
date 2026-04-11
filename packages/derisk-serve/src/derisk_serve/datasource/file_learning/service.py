"""Service for learning database schema from uploaded design files.

This service parses schema files (PDM, DDL, PDMan, ERWin) and creates
table specs linked to an existing datasource for sample data collection.
"""

import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from derisk.component import SystemApp

from derisk_serve.datasource.manages.connect_config_db import ConnectConfigDao
from derisk_serve.datasource.manages.connector_manager import ConnectorManager
from derisk_serve.datasource.manages.db_spec_db import DbSpecDao
from derisk_serve.datasource.manages.table_spec_db import TableSpecDao

from .parsers import (
    BaseSchemaParser,
    ParsedSchema,
    ParsedTable,
    get_parser_for_extension,
    get_parser_for_file,
    get_supported_types,
)

logger = logging.getLogger(__name__)

# Storage directory for uploaded schema files
SCHEMA_FILE_STORAGE_DIR = os.path.expanduser("~/.cache/derisk/schema_files")

# Max cell length for sample data
MAX_SAMPLE_CELL_LENGTH = 1000


class FileLearningService:
    """Service for learning schema from design files and linking to datasource.

    This service:
    1. Accepts uploaded schema design files (PDM, DDL, PDMan, ERWin)
    2. Parses table structure from files
    3. Links to an existing datasource for sample data collection
    4. Creates table_spec and db_spec records

    Example usage:
        service = FileLearningService(system_app)

        # Upload and preview
        upload_result = service.upload_schema_file(file_content, "model.pdm")
        preview = service.preview_parsed_tables(upload_result["file_path"])

        # Learn and link to datasource
        learn_result = service.learn_from_file(
            upload_result["file_path"],
            datasource_id=123
        )
    """

    def __init__(self, system_app: SystemApp):
        """Initialize the service.

        Args:
            system_app: SystemApp instance for dependency injection
        """
        self._system_app = system_app
        self._table_spec_dao = TableSpecDao()
        self._db_spec_dao = DbSpecDao()
        self._config_dao = ConnectConfigDao()
        self._connector_manager: Optional[ConnectorManager] = None

        # Ensure storage directory exists
        os.makedirs(SCHEMA_FILE_STORAGE_DIR, exist_ok=True)

    @property
    def connector_manager(self) -> ConnectorManager:
        """Get ConnectorManager instance."""
        if not self._connector_manager:
            self._connector_manager = ConnectorManager.get_instance(self._system_app)
        return self._connector_manager

    # ==============================================================
    # File Upload and Management
    # ==============================================================

    def upload_schema_file(
        self, file_content: bytes, filename: str
    ) -> Dict[str, Any]:
        """Upload and store a schema design file temporarily.

        Args:
            file_content: Raw file content bytes
            filename: Original filename (used to detect type)

        Returns:
            Dict with file_id, file_path, file_type, original_name
        """
        # Detect file type from extension
        ext = os.path.splitext(filename)[1].lower()
        file_type = self._detect_file_type(ext)

        # Generate unique file ID and storage path
        file_id = uuid.uuid4().hex[:16]
        stored_name = f"{file_id}_{filename}"
        file_path = os.path.join(SCHEMA_FILE_STORAGE_DIR, stored_name)

        # Write file content
        with open(file_path, "wb") as f:
            f.write(file_content)

        logger.info(f"Schema file uploaded: {filename} -> {file_path}")

        return {
            "file_id": file_id,
            "file_path": file_path,
            "file_type": file_type,
            "original_name": filename,
        }

    def get_file_path(self, file_id: str) -> Optional[str]:
        """Get file path by file_id.

        Args:
            file_id: Unique file identifier

        Returns:
            File path or None if not found
        """
        # Find file matching file_id prefix
        for fname in os.listdir(SCHEMA_FILE_STORAGE_DIR):
            if fname.startswith(f"{file_id}_"):
                return os.path.join(SCHEMA_FILE_STORAGE_DIR, fname)
        return None

    def cleanup_file(self, file_path: str) -> None:
        """Remove uploaded file after processing.

        Args:
            file_path: Path to the file to remove
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleaned up file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup file {file_path}: {e}")

    # ==============================================================
    # Parsing and Preview
    # ==============================================================

    def parse_schema_file(
        self, file_path: str, file_type: Optional[str] = None
    ) -> ParsedSchema:
        """Parse a schema file and return structured definitions.

        Args:
            file_path: Path to the uploaded file
            file_type: Override file type detection (optional)

        Returns:
            ParsedSchema with tables, views, and references

        Raises:
            ValueError: If file type is not supported
        """
        if not file_type:
            ext = os.path.splitext(file_path)[1].lower()
            file_type = self._detect_file_type(ext)

        parser = get_parser_for_file(file_type)
        if not parser:
            raise ValueError(f"No parser available for file type: {file_type}")

        parsed = parser.parse(file_path)
        logger.info(
            f"Parsed schema file: {file_path}, "
            f"type={file_type}, tables={len(parsed.tables)}"
        )

        return parsed

    def preview_parsed_tables(
        self, file_path: str, file_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Preview parsed tables without creating specs.

        Useful for showing user what tables will be learned.

        Args:
            file_path: Path to the uploaded file
            file_type: Override file type detection

        Returns:
            Dict with tables list, views list, source_type, total_count
        """
        parsed = self.parse_schema_file(file_path, file_type)

        return {
            "tables": [
                {
                    "name": t.table_name,
                    "comment": t.table_comment,
                    "column_count": len(t.columns or []),
                    "has_fk": bool(t.foreign_keys),
                }
                for t in parsed.tables
            ],
            "views": [
                {
                    "name": v.table_name,
                    "comment": v.table_comment,
                    "column_count": len(v.columns or []),
                }
                for v in (parsed.views or [])
            ],
            "source_type": parsed.source_type,
            "total_count": len(parsed.tables) + len(parsed.views or []),
        }

    # ==============================================================
    # Learning from File
    # ==============================================================

    def learn_from_file(
        self,
        file_path: str,
        datasource_id: int,
        file_type: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Learn schema from file and link to existing datasource.

        This is the main entry point for file-based learning.

        Args:
            file_path: Path to the uploaded schema file
            datasource_id: ID of the datasource to link (for sample data)
            file_type: Override file type detection
            options: Additional options (cleanup_file, generate_llm_desc)

        Returns:
            Dict with learning results: datasource_id, source_type,
            total_tables, processed_tables, failed_tables, status
        """
        options = options or {}
        cleanup_file = options.get("cleanup_file", True)
        generate_llm_desc = options.get("generate_llm_desc", True)

        # 1. Parse the file
        parsed = self.parse_schema_file(file_path, file_type)

        # 2. Validate datasource exists
        db_config = self._config_dao.get_one({"id": datasource_id})
        if not db_config:
            raise ValueError(f"Datasource {datasource_id} not found")

        db_name = db_config.get("db_name")
        db_type = db_config.get("db_type")

        # 3. Get connector for sample data collection
        connector = None
        try:
            connector = self.connector_manager.get_connector(db_name)
        except Exception as e:
            logger.warning(
                f"Could not get connector for {db_name}: {e}. "
                "Sample data will be empty."
            )

        # 4. Process each table
        processed_tables = 0
        failed_tables = []

        all_tables = parsed.tables + (parsed.views or [])
        total_tables = len(all_tables)

        for parsed_table in all_tables:
            try:
                self._create_table_spec_from_parsed(
                    parsed_table=parsed_table,
                    datasource_id=datasource_id,
                    connector=connector,
                    db_name=db_name,
                    parsed=parsed,
                    generate_llm_desc=generate_llm_desc,
                )
                processed_tables += 1
            except Exception as e:
                logger.error(
                    f"Failed to process table {parsed_table.table_name}: {e}"
                )
                failed_tables.append({
                    "table_name": parsed_table.table_name,
                    "error": str(e),
                })

        # 5. Apply foreign key relationships from file
        if parsed.references:
            self._apply_file_references(datasource_id, parsed.references)

        # 6. Build db-level spec
        self._regenerate_db_spec(datasource_id, db_name, db_type, total_tables)

        # 7. Cleanup uploaded file
        if cleanup_file:
            self.cleanup_file(file_path)

        status = "completed" if not failed_tables else "partial"
        if processed_tables == 0:
            status = "failed"

        result = {
            "datasource_id": datasource_id,
            "source_file": file_path,
            "source_type": parsed.source_type,
            "total_tables": total_tables,
            "processed_tables": processed_tables,
            "failed_tables": failed_tables,
            "status": status,
        }

        logger.info(f"File learning completed: {result}")
        return result

    def _create_table_spec_from_parsed(
        self,
        parsed_table: ParsedTable,
        datasource_id: int,
        connector: Optional[Any],
        db_name: str,
        parsed: ParsedSchema,
        generate_llm_desc: bool = True,
    ) -> None:
        """Create table_spec from parsed file data.

        Args:
            parsed_table: Parsed table definition
            datasource_id: Datasource ID
            connector: Database connector (optional, for sample data)
            db_name: Database name
            parsed: Full parsed schema
            generate_llm_desc: Whether to generate LLM description
        """
        table_name = parsed_table.table_name

        # Base table data from parsed file
        table_data = {
            "datasource_id": datasource_id,
            "table_name": table_name,
            "table_comment": parsed_table.table_comment or "",
            "row_count": None,
            "columns_json": json.dumps(
                parsed_table.columns or [], ensure_ascii=False
            ),
            "indexes_json": json.dumps(
                parsed_table.indexes or [], ensure_ascii=False
            ),
            "foreign_keys_json": json.dumps(
                parsed_table.foreign_keys or [], ensure_ascii=False
            ) if parsed_table.foreign_keys else None,
            "create_ddl": parsed_table.create_ddl or "",
            "group_name": "default",
            "sample_data_json": None,
        }

        # Try to get row count and sample data from linked datasource
        if connector:
            try:
                row_count = self._get_row_count(connector, table_name)
                table_data["row_count"] = row_count

                # Collect sample data if table exists
                if row_count and row_count > 0:
                    sample_data = self._collect_sample_data(
                        connector, table_name, parsed_table.columns, row_count
                    )
                    if sample_data:
                        table_data["sample_data_json"] = sample_data
            except Exception as e:
                logger.warning(
                    f"Could not get sample data for {table_name} "
                    f"(may not exist in datasource): {e}"
                )

        # LLM-generated description if table_comment is empty
        if (
            generate_llm_desc
            and (not parsed_table.table_comment or len(parsed_table.table_comment) < 10)
            and connector
            and table_data.get("row_count")
        ):
            try:
                db_context = {
                    "db_name": db_name,
                    "db_type": parsed.source_type or "",
                    "db_comment": "",
                    "table_list": ", ".join(
                        [t.table_name for t in parsed.tables[:20]]
                    ),
                    "table_count": str(len(parsed.tables)),
                }

                llm_desc = self._generate_table_summary(
                    connector=connector,
                    table_name=table_name,
                    columns=parsed_table.columns,
                    row_count=table_data.get("row_count"),
                    existing_comment=parsed_table.table_comment or "",
                    db_context=db_context,
                )
                if llm_desc:
                    table_data["table_comment"] = llm_desc
            except Exception as e:
                logger.warning(f"LLM description failed for {table_name}: {e}")

        # Upsert table spec
        self._table_spec_dao.upsert(datasource_id, table_name, table_data)

    def _get_row_count(self, connector: Any, table_name: str) -> Optional[int]:
        """Get row count from datasource.

        Args:
            connector: Database connector
            table_name: Table name

        Returns:
            Row count or None if table doesn't exist
        """
        try:
            quoted = connector.quote_identifier(table_name)
            result = connector.run(f"SELECT COUNT(*) FROM {quoted}")
            if result and len(result) > 1:
                row_val = tuple(result[1])
                if len(row_val) > 0:
                    return int(row_val[0])
        except Exception:
            pass
        return None

    def _collect_sample_data(
        self,
        connector: Any,
        table_name: str,
        columns: List[Dict[str, Any]],
        row_count: int,
    ) -> Optional[str]:
        """Collect sample rows from datasource.

        Args:
            connector: Database connector
            table_name: Table name
            columns: Column definitions
            row_count: Total row count

        Returns:
            JSON string of sample data or None
        """
        quoted = connector.quote_identifier(table_name)
        col_names = [c.get("name", "") for c in columns]

        def _parse_rows(result):
            """Parse connector.run() result, skipping header row."""
            if not result or len(result) <= 1:
                return []
            rows = []
            for r in result[1:]:
                row = list(r)
                rows.append([
                    str(v)[:MAX_SAMPLE_CELL_LENGTH] if v is not None else "NULL"
                    for v in row
                ])
            return rows

        try:
            # For small tables (<=4 rows), fetch all
            if row_count <= 4:
                sql = connector.limit_sql(f"SELECT * FROM {quoted}", 4)
                result = connector.run(sql)
                all_rows = _parse_rows(result)
                if not all_rows:
                    return None
                return json.dumps(
                    {"columns": col_names, "rows": all_rows},
                    ensure_ascii=False,
                )

            # For larger tables, fetch first 2 + last 2 rows
            head_sql = connector.limit_sql(f"SELECT * FROM {quoted}", 2)
            head_result = connector.run(head_sql)
            head_rows = _parse_rows(head_result)

            tail_rows = []
            try:
                offset = max(0, row_count - 2)
                tail_sql = connector.limit_sql(f"SELECT * FROM {quoted}", 2, offset)
                tail_result = connector.run(tail_sql)
                tail_rows = _parse_rows(tail_result)
            except Exception:
                pass

            all_rows = head_rows + tail_rows
            if not all_rows:
                return None

            return json.dumps(
                {"columns": col_names, "rows": all_rows},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.warning(f"Failed to collect sample data for {table_name}: {e}")
            return None

    def _generate_table_summary(
        self,
        connector: Any,
        table_name: str,
        columns: List[Dict[str, Any]],
        row_count: Optional[int],
        existing_comment: str,
        db_context: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Generate LLM description for a table.

        Args:
            connector: Database connector
            table_name: Table name
            columns: Column definitions
            row_count: Row count
            existing_comment: Existing table comment
            db_context: Database context info

        Returns:
            Generated description or None
        """
        # Get LLM config
        llm_config = self._get_llm_config()
        if not llm_config:
            return None

        # Build context sections
        db_section = ""
        if db_context:
            db_section = (
                f"数据库: {db_context.get('db_name', '')} "
                f"(类型: {db_context.get('db_type', '')})\n"
            )
            db_section += (
                f"所有表 ({db_context.get('table_count', '')}个):"
                f" {db_context.get('table_list', '')}\n"
            )

        # Column info
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

        # Build prompt
        prompt = (
            f"你是一个数据库专家。根据以下数据库表的背景信息、结构、注释和样例数据，"
            f"用中文写一句话介绍这个表存储的数据内容和用途。\n"
            f"要求：只输出介绍内容，不超过100个字，不要输出其他任何内容。\n\n"
            f"{db_section}"
            f"表名: {table_name}\n"
            f"表注释: {existing_comment or '无'}\n"
            f"数据行数: {row_count or '未知'}\n"
            f"字段:\n{col_desc}\n"
        )

        result = self._call_llm(prompt, llm_config)
        if result:
            # Remove surrounding quotes if present
            if (
                len(result) > 2
                and result[0] in ('"', "'", "\u201c")
                and result[-1] in ('"', "'", "\u201d")
            ):
                result = result[1:-1]
            return result.strip()
        return None

    def _get_llm_config(self) -> Optional[Dict[str, Any]]:
        """Get LLM API config from ModelConfigCache.

        Returns:
            Dict with base_url, api_key, model or None
        """
        try:
            from derisk.agent.util.llm.model_config_cache import ModelConfigCache

            all_models = ModelConfigCache.get_all_models()
            if not all_models:
                return None

            # Get first available model
            model_info = all_models[0]
            return {
                "base_url": model_info.get("api_base_url"),
                "api_key": model_info.get("api_key"),
                "model": model_info.get("model_name"),
            }
        except Exception as e:
            logger.warning(f"Failed to get LLM config: {e}")
            return None

    def _call_llm(
        self, prompt: str, llm_config: Dict[str, Any]
    ) -> Optional[str]:
        """Call LLM API to generate response.

        Args:
            prompt: Prompt text
            llm_config: LLM configuration

        Returns:
            LLM response or None
        """
        import requests

        try:
            headers = {
                "Authorization": f"Bearer {llm_config.get('api_key')}",
                "Content-Type": "application/json",
            }
            data = {
                "model": llm_config.get("model"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.7,
            }
            response = requests.post(
                f"{llm_config.get('base_url')}/chat/completions",
                headers=headers,
                json=data,
                timeout=30,
            )
            if response.status_code == 200:
                result = response.json()
                choices = result.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.warning(f"LLM API call failed: {e}")

        return None

    def _apply_file_references(
        self, datasource_id: int, references: List[Dict[str, Any]]
    ) -> None:
        """Apply foreign key relationships parsed from file.

        Args:
            datasource_id: Datasource ID
            references: List of reference definitions from file
        """
        for ref in references:
            from_table = ref.get("from_table")
            to_table = ref.get("to_table")

            if not from_table or not to_table:
                continue

            # Get from_table spec
            from_spec = self._table_spec_dao.get_by_datasource_and_table(
                datasource_id, from_table
            )
            if not from_spec:
                continue

            # Append new foreign key
            existing_fks = from_spec.get("foreign_keys") or []
            new_fk = {
                "constrained_columns": ref.get("constrained_columns", []),
                "referred_table": to_table,
                "referred_columns": ref.get("referred_columns", []),
                "source": "file_definition",
            }
            existing_fks.append(new_fk)

            # Update
            self._table_spec_dao.update(
                {"datasource_id": datasource_id, "table_name": from_table},
                {"foreign_keys_json": json.dumps(existing_fks, ensure_ascii=False)},
            )

    def _regenerate_db_spec(
        self,
        datasource_id: int,
        db_name: str,
        db_type: str,
        table_count: int,
    ) -> None:
        """Regenerate db-level spec from learned table specs.

        Args:
            datasource_id: Datasource ID
            db_name: Database name
            db_type: Database type
            table_count: Total table count
        """
        table_specs = self._table_spec_dao.get_all_by_datasource(datasource_id)

        spec_entries = []
        for spec in table_specs:
            columns = spec.get("columns") or []
            spec_entries.append({
                "table_name": spec.get("table_name", ""),
                "summary": spec.get("table_comment", "") or "",
                "row_count": spec.get("row_count"),
                "column_count": len(columns),
                "group": spec.get("group_name", "default"),
            })

        self._db_spec_dao.upsert(datasource_id, {
            "db_name": db_name,
            "db_type": db_type,
            "spec_content": json.dumps(spec_entries, ensure_ascii=False),
            "table_count": table_count,
            "status": "ready",
        })

    # ==============================================================
    # Utility Methods
    # ==============================================================

    def _detect_file_type(self, extension: str) -> str:
        """Detect file type from extension.

        Args:
            extension: File extension (e.g., '.pdm')

        Returns:
            File type identifier

        Raises:
            ValueError: If extension is unknown
        """
        ext = extension.lower()
        type_map = {
            ".pdm": "pdm",
            ".xml": "pdm",  # Assume XML is PDM
            ".sql": "ddl",
            ".ddl": "ddl",
            ".json": "pdman",
            ".pdman": "pdman",
        }
        file_type = type_map.get(ext)
        if not file_type:
            raise ValueError(f"Unknown file extension: {ext}")
        return file_type

    def get_supported_file_types(self) -> List[Dict[str, Any]]:
        """Get list of supported file types.

        Returns:
            List of file type info dicts
        """
        return get_supported_types()