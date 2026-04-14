"""Database tools for agent interaction.

Provides tools that allow agents to retrieve detailed table specs
during execution, enabling progressive loading of schema information.
Supports both exact mode (specify table names) and recommend mode
(pass a question to get table suggestions via Schema Linking).
"""

import csv
import io
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from derisk.agent.tools.decorators import tool, ToolCategory
from derisk.vis import Vis

logger = logging.getLogger(__name__)

# 常量配置
MAX_DISPLAY_ROWS = 200  # 默认显示行数
MAX_EXPORT_ROWS = 200  # 超过此行数导出为 CSV
PAGE_SIZE = 200  # 分页大小

# SQL 写操作类型（DML 和 DDL）
WRITE_SQL_TYPES = {
    # DML - 数据修改
    "INSERT", "UPDATE", "DELETE", "MERGE", "REPLACE", "UPSERT",
    # DDL - 结构修改
    "CREATE", "DROP", "ALTER", "TRUNCATE", "RENAME", "GRANT", "REVOKE",
}


def _detect_sql_type(sql: str) -> Tuple[str, bool]:
    """检测 SQL 语句类型，判断是否是写操作。

    Args:
        sql: SQL 语句字符串

    Returns:
        (sql_type, is_write): SQL 类型字符串，是否是写操作
    """
    sql = sql.strip().upper()

    # 移除注释
    sql = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    sql = sql.strip()

    if not sql:
        return ("EMPTY", False)

    # 获取第一个关键字
    first_word = sql.split()[0] if sql.split() else ""

    # 检查是否是写操作
    is_write = first_word in WRITE_SQL_TYPES

    return (first_word, is_write)


def _check_write_permission(sql_type: str) -> Tuple[bool, str]:
    """检查写操作权限。

    Args:
        sql_type: SQL 类型（INSERT/UPDATE/DELETE/CREATE 等）

    Returns:
        (allowed, error_message): 是否允许执行，错误消息（如果不允许）
    """
    from derisk._private.config import Config

    CFG = Config()

    # DDL 类型检查
    ddl_types = {"CREATE", "DROP", "ALTER", "TRUNCATE", "RENAME", "GRANT", "REVOKE"}
    dml_write_types = {"INSERT", "UPDATE", "DELETE", "MERGE", "REPLACE", "UPSERT"}

    if sql_type in ddl_types:
        if not CFG.NATIVE_SQL_CAN_RUN_DDL:
            return (
                False,
                f"DDL 操作 '{sql_type}' 已被禁用。"
                f"\n当前处于只读模式，只允许执行 SELECT 查询。"
                f"\n如需开启 DDL 权限，请设置环境变量 NATIVE_SQL_CAN_RUN_DDL=true"
                f"\n或联系管理员修改系统配置。"
            )
    elif sql_type in dml_write_types:
        if not CFG.NATIVE_SQL_CAN_RUN_WRITE:
            return (
                False,
                f"数据修改操作 '{sql_type}' 已被禁用。"
                f"\n当前处于只读模式，只允许执行 SELECT 查询。"
                f"\n如需开启写操作权限，请设置环境变量 NATIVE_SQL_CAN_RUN_WRITE=true"
                f"\n或联系管理员修改系统配置。"
            )

    return (True, "")


def _resolve_db_from_agent(db_name: str, kwargs: Dict) -> tuple:
    """从 agent 的 resource_map 中解析数据库连接和 datasource_id。

    agent 初始化时 DatasourceResource 已通过 db_id fallback 成功创建了 connector，
    这里复用该 connector，避免仅靠 db_name 查找 connect_config 失败的问题。

    Returns:
        (connector, datasource_id): connector 可能为 None
    """
    agent = kwargs.get("agent")
    if not agent:
        return None, None

    resource_map = getattr(agent, "resource_map", None)
    if not resource_map:
        return None, None

    from derisk.agent.resource.database import DBResource

    for resources in resource_map.values():
        if not resources:
            continue
        for r in resources:
            if not isinstance(r, DBResource):
                continue
            r_db_name = getattr(r, "_db_name", None)
            if r_db_name == db_name:
                connector = getattr(r, "_connector", None) or getattr(
                    r, "connector", None
                )
                ds_id = getattr(r, "_datasource_id", None)
                if connector:
                    logger.info(
                        f"[db_tools] Resolved connector from agent resource_map "
                        f"for db_name={db_name}, ds_id={ds_id}"
                    )
                    return connector, ds_id

    return None, None


@tool(
    "get_table_spec",
    description=(
        "获取表的详细 schema 信息，包括列定义、类型、注释、索引、样本数据等。"
        "**限制**: 每次最多查询 3 张表，避免输出过大。"
        "如果需要更多表，请分多次调用。"
    ),
    args={
        "db_name": {
            "type": "string",
            "description": (
                "数据库名称，使用可用数据库列表中的 db_name 字段值。"
            ),
            "required": True,
        },
        "table_names": {
            "type": "string",
            "description": (
                "要查询的表名，最多支持 3 张表，用逗号分隔。"
                "例如: 'users,orders,products'。"
                "超过 3 张表时只会返回前 3 张的详细信息。"
                "如果不指定，则使用 question 参数让系统推荐相关表。"
            ),
            "required": False,
        },
        "question": {
            "type": "string",
            "description": (
                "自然语言问题，系统会根据问题推荐相关的表（最多 3 张）。"
                "当你不确定需要查询哪些表时使用此参数。"
            ),
            "required": False,
        },
    },
    category=ToolCategory.UTILITY,
)
async def get_table_spec(
    db_name: str,
    table_names: Optional[str] = None,
    question: Optional[str] = None,
    **kwargs,
) -> str:
    """Get detailed table specs for specific tables in a database.

    This is Stage 2 of the progressive loading flow:
    - Stage 1: Agent receives DB-level spec (table index) via get_prompt()
    - Stage 2: Agent calls this tool to get detailed specs for relevant tables
    - Stage 3: Agent generates SQL from the loaded context

    Supports two modes:
    - Exact mode: provide table_names directly (comma-separated for multiple tables)
    - Recommend mode: provide question, uses Schema Linking to suggest tables
    """
    try:
        from derisk._private.config import Config

        CFG = Config()

        # 优先从 agent 的 resource_map 中获取已初始化的 connector
        agent_connector, agent_ds_id = _resolve_db_from_agent(db_name, kwargs)

        # Resolve datasource
        ds_id = agent_ds_id
        spec_service = None
        try:
            from derisk_serve.datasource.manages.connect_config_db import (
                ConnectConfigDao,
            )
            from derisk_serve.datasource.service.spec_service import (
                DbSpecService,
            )

            if not ds_id:
                dao = ConnectConfigDao()
                entity = dao.get_by_names(db_name)
                if entity:
                    ds_id = entity.id
            if ds_id:
                spec_service = DbSpecService()
        except ImportError:
            pass

        def _get_connector():
            """获取 connector：优先使用 agent 中已有的，否则新建"""
            if agent_connector:
                return agent_connector
            return CFG.local_db_manager.get_connector(db_name)

        # Recommend mode: use Schema Linking
        if not table_names and question and ds_id:
            try:
                from derisk_serve.datasource.service.schema_link_service import (
                    SchemaLinkService,
                )

                link_service = SchemaLinkService()
                recommendations = link_service.suggest_tables(ds_id, question)
                if recommendations:
                    # Format recommendations header
                    rec_lines = ["Recommended tables based on your question:"]
                    for rec in recommendations:
                        reason_str = "; ".join(rec.reasons[:3])
                        # 添加行数信息显示
                        row_info = f", rows: {rec.row_count}" if rec.row_count else ""
                        rec_lines.append(
                            f"  - {rec.table_name} (score: {rec.score:.1f}"
                            f"{row_info}, reasons: {reason_str})"
                        )
                    rec_header = "\n".join(rec_lines) + "\n\n"

                    # Get specs for recommended tables
                    rec_names = [r.table_name for r in recommendations]
                    if spec_service and spec_service.has_spec(ds_id):
                        specs = spec_service.format_table_specs_for_prompt(
                            ds_id, rec_names
                        )
                        if specs:
                            return rec_header + specs
                    # Fallback
                    connector = _get_connector()
                    return rec_header + connector.get_table_info(rec_names)
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"Schema linking failed, falling back: {e}")

        # Exact mode: parse table names (limit to 3 tables max)
        if table_names:
            names = [n.strip() for n in table_names.split(",") if n.strip()]
            # 限制最多查询 3 张表，避免输出过大超过上下文限制
            MAX_TABLES_PER_QUERY = 3
            if len(names) > MAX_TABLES_PER_QUERY:
                logger.warning(
                    f"[get_table_spec] Too many tables requested ({len(names)}), "
                    f"limiting to {MAX_TABLES_PER_QUERY}. "
                    f"Requested: {names}, Returned: {names[:MAX_TABLES_PER_QUERY]}"
                )
                names = names[:MAX_TABLES_PER_QUERY]
        else:
            return (
                "Error: Please provide either 'table_names' or 'question'. "
                "Use table_names for specific tables, or question for "
                "automatic table recommendation."
            )

        if not names:
            return "Error: No table names provided."

        # Try spec-based retrieval
        if ds_id and spec_service and spec_service.has_spec(ds_id):
            result = spec_service.format_table_specs_for_prompt(ds_id, names)
            if result:
                return result

        # Fallback: live introspection
        connector = _get_connector()
        return connector.get_table_info(names)

    except Exception as e:
        logger.error(f"Error getting table spec: {e}")
        return f"Error getting table spec: {str(e)}"


@tool(
    "execute_sql",
    description=(
        "在指定数据库上执行 SQL 查询并返回结果。"
        "**重要**: SQL 语法必须完全符合目标数据库类型（db_type/dialect）。"
        "例如：SQLite 使用 LIMIT，MySQL 可用 LIMIT，Oracle 使用 ROWNUM，SQL Server 使用 TOP。"
        "执行前请先通过 get_table_spec 了解表结构。"
    ),
    args={
        "db_name": {
            "type": "string",
            "description": (
                "数据库名称，使用可用数据库列表中的 db_name 字段值。"
            ),
            "required": True,
        },
        "sql": {
            "type": "string",
            "description": (
                "要执行的 SQL 查询语句。"
                "**关键**: SQL 语法必须严格匹配数据库类型："
                "- SQLite: 标准 SQL，LIMIT 语法"
                "- MySQL: LIMIT，反引号 `` 包裹标识符"
                "- PostgreSQL: LIMIT，双引号 \"\" 包裹标识符"
                "- Oracle: ROWNUM，无 LIMIT"
                "- SQL Server: TOP 关键字，方括号 [] 包裹标识符"
                "- 使用 get_table_spec 获取正确的表名和列名"
            ),
            "required": True,
        },
        "page": {
            "type": "integer",
            "description": (
                "分页页码，从 1 开始。默认为 1。"
                "当结果超过 50 行时，使用分页查看更多数据。"
            ),
            "required": False,
        },
    },
    category=ToolCategory.UTILITY,
)
async def execute_sql(
    db_name: str,
    sql: str,
    page: int = 1,
    **kwargs,
) -> str:
    """Execute a SQL query on the specified database.

    This tool allows the agent to run SQL queries against the bound database resource.
    Results are returned in a structured format with pagination support.

    Args:
        db_name: The database name from the available databases list
        sql: The SQL query to execute (must match database type/dialect)
        page: Page number for pagination (starts from 1)

    Returns:
        SQL query results in a structured format with pagination and export info
    """
    try:
        from derisk._private.config import Config

        CFG = Config()

        # 检测 SQL 类型并拦截写操作（安全检查）
        sql_type, is_write = _detect_sql_type(sql)
        if is_write:
            allowed, error_msg = _check_write_permission(sql_type)
            if not allowed:
                logger.warning(f"[execute_sql] Blocked write operation: {sql_type} on {db_name}")
                return _format_error(error_msg, db_type="unknown", sql_type=sql_type)

        # 优先从 agent 的 resource_map 中获取已初始化的 connector
        agent_connector, _ = _resolve_db_from_agent(db_name, kwargs)
        connector = agent_connector
        if not connector:
            connector = CFG.local_db_manager.get_connector(db_name)
        if not connector:
            return _format_error(
                f"Database '{db_name}' not found. Please check the db_name.",
                db_type="unknown"
            )

        # Get database type for error messages
        db_type = getattr(connector, 'db_type', 'unknown')
        dialect = getattr(connector, 'dialect', db_type)

        # Get database version for version-specific syntax hints
        db_version = None
        if hasattr(connector, 'get_db_version'):
            try:
                db_version = connector.get_db_version()
            except Exception as e:
                logger.debug(f"Failed to get db version: {e}")

        # Execute the query
        result = connector.run(sql)

        if not result:
            return _format_sql_result(
                sql=sql,
                db_name=db_name,
                db_type=db_type,
                columns=[],
                rows=[],
                total_rows=0,
                page=1,
                total_pages=0,
            )

        # Parse results
        if isinstance(result, (list, tuple)) and len(result) > 0:
            columns = list(result[0]) if result[0] else []
            # Convert SQLAlchemy Row objects to plain lists for proper serialization
            all_rows = [list(row) for row in result[1:]] if len(result) > 1 else []
            total_rows = len(all_rows)

            if not all_rows:
                return _format_sql_result(
                    sql=sql,
                    db_name=db_name,
                    db_type=db_type,
                    columns=columns,
                    rows=[],
                    total_rows=0,
                    page=1,
                    total_pages=0,
                )

            # 计算分页
            total_pages = (total_rows + PAGE_SIZE - 1) // PAGE_SIZE
            page = max(1, min(page, total_pages))  # 确保页码在有效范围内
            start_idx = (page - 1) * PAGE_SIZE
            end_idx = start_idx + PAGE_SIZE
            display_rows = all_rows[start_idx:end_idx]

            # 如果结果超过 MAX_EXPORT_ROWS，需要导出 CSV
            csv_file_path = None
            csv_export_reason = None
            if total_rows > MAX_EXPORT_ROWS:
                csv_file_path = await _export_to_csv(
                    columns=columns,
                    rows=all_rows,
                    db_name=db_name,
                    sql=sql,
                    kwargs=kwargs,
                )
                if csv_file_path:
                    csv_export_reason = f"结果共 {total_rows} 行，超过 {MAX_EXPORT_ROWS} 行，已导出为 CSV 文件"

            # 智能控制展示行数：确保 d-sql-query JSON 不会过大
            # （过大会导致嵌入 manus-right-panel 后整体 JSON 被截断）
            MAX_VIS_OUTPUT_BYTES = 3 * 1024  # 3KB，为 manus-right-panel 留足空间
            vis_display_rows = display_rows
            display_truncated = False

            try:
                test_data = {
                    "sql": sql, "db_name": db_name, "db_type": db_type,
                    "dialect": dialect, "columns": columns, "rows": vis_display_rows,
                }
                test_json = json.dumps(test_data, ensure_ascii=False)
                if len(test_json.encode('utf-8')) > MAX_VIS_OUTPUT_BYTES and vis_display_rows:
                    # 逐步减少展示行数
                    for limit in [100, 50, 20, 10, 5]:
                        if limit >= len(vis_display_rows):
                            continue
                        test_data["rows"] = vis_display_rows[:limit]
                        test_json = json.dumps(test_data, ensure_ascii=False)
                        if len(test_json.encode('utf-8')) <= MAX_VIS_OUTPUT_BYTES:
                            vis_display_rows = vis_display_rows[:limit]
                            display_truncated = True
                            logger.info(
                                f"[execute_sql] Reduced display rows from {len(display_rows)} to {limit} "
                                f"to keep d-sql-query output under {MAX_VIS_OUTPUT_BYTES} bytes"
                            )
                            break
                    else:
                        # 即使最小 limit 也超过阈值，取最少的
                        vis_display_rows = vis_display_rows[:5]
                        display_truncated = True

                    # 如果因为展示截断而尚未导出 CSV，则导出完整结果
                    if display_truncated and not csv_file_path:
                        csv_file_path = await _export_to_csv(
                            columns=columns,
                            rows=all_rows,
                            db_name=db_name,
                            sql=sql,
                            kwargs=kwargs,
                        )
                        if csv_file_path:
                            csv_export_reason = (
                                f"结果共 {total_rows} 行，展示数据因体积过大已缩减为 {len(vis_display_rows)} 行，"
                                f"完整数据已导出为 CSV 文件"
                            )
            except Exception as e:
                logger.warning(f"[execute_sql] Failed to check vis output size: {e}")

            # 构建结果
            result_data = {
                "sql": sql,
                "db_name": db_name,
                "db_type": db_type,
                "dialect": dialect,
                "columns": columns,
                "rows": vis_display_rows,
                "total_rows": total_rows,
                "page": page,
                "total_pages": total_pages,
                "page_size": PAGE_SIZE,
                "has_more": page < total_pages,
            }

            if csv_file_path:
                result_data["csv_file"] = csv_file_path
                result_data["csv_export_reason"] = csv_export_reason

            if display_truncated:
                result_data["display_truncated"] = True
                result_data["display_row_count"] = len(vis_display_rows)

            # 返回结构化结果
            return _format_sql_result(**result_data)

        return _format_sql_result(
            sql=sql,
            db_name=db_name,
            db_type=db_type,
            columns=[],
            rows=[],
            total_rows=0,
            page=1,
            total_pages=0,
            raw_result=str(result),
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error executing SQL on {db_name}: {error_msg}")
        return _format_error(
            error_msg,
            db_type=dialect if 'dialect' in dir() else 'unknown',
            db_version=db_version if 'db_version' in dir() else None
        )


async def _export_to_csv(
    columns: List,
    rows: List,
    db_name: str,
    sql: str,
    kwargs: Dict,
) -> Optional[str]:
    """导出查询结果到 CSV 文件

    Returns:
        CSV 文件路径，如果失败返回 None
    """
    try:
        import hashlib
        from datetime import datetime

        # 生成文件名
        sql_hash = hashlib.md5(sql.encode()).hexdigest()[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"query_{db_name}_{timestamp}_{sql_hash}.csv"

        # 尝试使用 AgentFileSystem 或 sandbox
        agent_file_system = kwargs.get("agent_file_system")
        sandbox_manager = kwargs.get("context", {}).get("sandbox_manager") if kwargs.get("context") else None

        # 生成 CSV 内容
        csv_content = io.StringIO()
        writer = csv.writer(csv_content)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([str(v) if v is not None else "NULL" for v in row])

        csv_data = csv_content.getvalue()

        # 优先使用 sandbox
        if sandbox_manager:
            try:
                work_dir = getattr(sandbox_manager, "work_dir", "/workspace")
                goal_id = getattr(sandbox_manager, "goal_id", "default")
                csv_dir = f"{work_dir}/{goal_id}/exports"
                csv_path = f"{csv_dir}/{file_name}"

                # 创建目录并写入文件
                sandbox_manager.run_command(f"mkdir -p {csv_dir}")
                sandbox_manager.write_file(csv_path, csv_data)

                logger.info(f"Exported query results to sandbox: {csv_path}")
                return csv_path
            except Exception as e:
                logger.warning(f"Failed to export to sandbox: {e}")

        # 使用 AgentFileSystem
        if agent_file_system:
            try:
                from derisk.agent.core.memory.gpts.file_base import FileType

                file_metadata = await agent_file_system.save_file(
                    file_key=file_name,
                    data=csv_data,
                    file_type=FileType.QUERY_RESULT,
                    extension="csv",
                    tool_name="execute_sql",
                )

                logger.info(f"Exported query results via AgentFileSystem: {file_metadata.local_path}")
                return file_metadata.local_path or file_name
            except Exception as e:
                logger.warning(f"Failed to export via AgentFileSystem: {e}")

        # 回退到本地临时目录
        import tempfile
        import os

        temp_dir = tempfile.gettempdir()
        csv_path = os.path.join(temp_dir, file_name)

        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            f.write(csv_data)

        logger.info(f"Exported query results to temp file: {csv_path}")
        return csv_path

    except Exception as e:
        logger.error(f"Failed to export CSV: {e}")
        return None


def _format_sql_result(
    sql: str,
    db_name: str,
    db_type: str,
    columns: List,
    rows: List,
    total_rows: int,
    page: int,
    total_pages: int,
    dialect: str = "",
    page_size: int = PAGE_SIZE,
    csv_file: Optional[str] = None,
    csv_export_reason: Optional[str] = None,
    has_more: bool = False,
    raw_result: Optional[str] = None,
) -> str:
    """格式化 SQL 查询结果，返回 SQL 查询组件格式"""

    result_data = {
        "sql": sql,
        "db_name": db_name,
        "db_type": db_type,
        "dialect": dialect or db_type,
        "columns": columns,
        "rows": rows,
        "total_rows": total_rows,
        "page": page,
        "total_pages": total_pages,
        "page_size": page_size,
        "has_more": has_more,
    }

    if csv_file:
        result_data["csv_file"] = csv_file
        result_data["csv_export_reason"] = csv_export_reason

    if raw_result:
        result_data["raw_result"] = raw_result

    # 使用 d-sql-query 组件渲染
    try:
        vis = Vis.of("d-sql-query")
        return vis.sync_display(**result_data)
    except Exception as e:
        logger.warning(f"Failed to render d-sql-query component: {e}")
        # 回退到 markdown 表格格式
        return _format_markdown_table(
            sql=sql,
            columns=columns,
            rows=rows,
            total_rows=total_rows,
            page=page,
            total_pages=total_pages,
            csv_file=csv_file,
            db_type=db_type,
        )


def _format_markdown_table(
    sql: str,
    columns: List,
    rows: List,
    total_rows: int,
    page: int,
    total_pages: int,
    csv_file: Optional[str],
    db_type: str,
) -> str:
    """回退格式：Markdown 表格"""

    lines = []

    # SQL 信息
    lines.append(f"**SQL 查询** ({db_type}):")
    lines.append(f"```sql")
    lines.append(sql)
    lines.append("```")
    lines.append("")

    if not columns:
        lines.append("查询执行成功，无结果返回。")
        return "\n".join(lines)

    # 结果统计
    lines.append(f"**查询结果**: 共 {total_rows} 行")
    if total_pages > 1:
        lines.append(f"（第 {page}/{total_pages} 页，每页 {PAGE_SIZE} 行）")
    lines.append("")

    # 表格
    lines.append("| " + " | ".join(str(c) for c in columns) + " |")
    lines.append("| " + " | ".join("-" * min(len(str(c)), 10) for c in columns) + " |")

    for row in rows:
        lines.append("| " + " | ".join(str(v) if v is not None else "NULL" for v in row) + " |")

    # 分页提示
    if total_pages > 1:
        lines.append("")
        if page < total_pages:
            lines.append(f"_提示: 使用 page={page + 1} 查看下一页_")

    # CSV 导出提示
    if csv_file:
        lines.append("")
        lines.append(f"📁 **完整结果已导出**: `{csv_file}`")

    return "\n".join(lines)


def _format_error(
    error_msg: str,
    db_type: str,
    sql_type: Optional[str] = None,
    db_version: Optional[str] = None,
) -> str:
    """格式化错误信息"""

    lines = ["❌ **SQL 执行错误**", ""]
    lines.append(f"**数据库类型**: {db_type}")
    if db_version:
        lines.append(f"**数据库版本**: {db_version}")
    if sql_type:
        lines.append(f"**SQL 类型**: {sql_type}")
    lines.append(f"**错误信息**: {error_msg}")
    lines.append("")

    # 写操作被拦截的特殊提示
    if sql_type and sql_type in WRITE_SQL_TYPES:
        lines.append("**安全提示**: 当前系统处于只读模式，禁止执行数据修改操作。")
        lines.append("")
        lines.append("只允许的操作：")
        lines.append("- SELECT - 查询数据")
        lines.append("")
        lines.append("如需开启写操作权限，请联系管理员设置以下环境变量：")
        lines.append("- NATIVE_SQL_CAN_RUN_WRITE=true (允许 INSERT/UPDATE/DELETE)")
        lines.append("- NATIVE_SQL_CAN_RUN_DDL=true (允许 CREATE/DROP/ALTER)")
        return "\n".join(lines)

    # Oracle 特定语法提示
    db_type_lower = db_type.lower() if db_type else ""
    if db_type_lower == "oracle":
        lines.append("**Oracle SQL 语法规范**:")
        lines.append("")
        # 针对常见 Oracle 错误的具体提示
        error_lower = error_msg.lower()

        # ORA-00904: invalid identifier（如 COUNT 作为标识符）
        if "ora-00904" in error_lower or "invalid identifier" in error_lower:
            lines.append("错误原因: 使用了无效的标识符（可能是保留字或函数名）")
            lines.append("")
            lines.append("**常见问题修复**:")
            lines.append("- ❌ ORDER BY COUNT DESC → ✅ ORDER BY COUNT(*) DESC")
            lines.append("- ❌ ORDER BY SUM DESC → ✅ ORDER BY SUM(*) DESC")
            lines.append("- ❌ 列别名使用 COUNT → ✅ 使用非保留字作为别名，如 cnt 或 人数")
            lines.append("")
            lines.append("正确示例:")
            lines.append("```sql")
            lines.append("SELECT")
            lines.append("  CASE WHEN ... END AS 类别,")
            lines.append("  COUNT(*) AS 人数  -- 使用非保留字作为别名")
            lines.append("FROM table")
            lines.append("ORDER BY 人数 DESC  -- 按别名排序")
            lines.append("或 ORDER BY COUNT(*) DESC  -- 使用完整函数")
            lines.append("```")

        # ORA-00923: FROM keyword not found（语法错误）
        elif "ora-00923" in error_lower or "from keyword" in error_lower:
            lines.append("错误原因: SQL 语法错误，FROM 关键字位置不正确")
            lines.append("")
            lines.append("**常见问题修复**:")
            lines.append("- Oracle 不支持 LIMIT，使用 ROWNUM 或 FETCH FIRST")
            lines.append("- ❌ SELECT * FROM table LIMIT 10")
            lines.append("- ✅ SELECT * FROM (SELECT * FROM table) WHERE ROWNUM <= 10")

        # ORA-00933: SQL command not properly ended
        elif "ora-00933" in error_lower or "not properly ended" in error_lower:
            lines.append("错误原因: SQL 语句结束位置有问题")
            lines.append("")
            lines.append("**常见问题修复**:")
            lines.append("- 检查是否有不支持的语法（如 LIMIT）")
            lines.append("- Oracle 11g: 使用 ROWNUM 代替 LIMIT")
            lines.append("- Oracle 12c+: 使用 FETCH FIRST n ROWS ONLY")

        # 通用 Oracle 语法提示
        else:
            lines.append("**Oracle 语法要点**:")
            if db_version:
                try:
                    major, minor = map(int, db_version.split('.')[:2])
                    if (major, minor) >= (12, 1):
                        lines.append(f"- Oracle {db_version} (12c+): 使用 FETCH FIRST 代替 LIMIT")
                        lines.append("  示例: SELECT * FROM table FETCH FIRST 10 ROWS ONLY")
                    else:
                        lines.append(f"- Oracle {db_version} (11g 及更早): 使用 ROWNUM 代替 LIMIT")
                        lines.append("  示例: SELECT * FROM (SELECT * FROM table) WHERE ROWNUM <= 10")
                except (ValueError, AttributeError):
                    lines.append(f"- Oracle {db_version}: 优先使用 ROWNUM（兼容所有版本）")
            else:
                lines.append("- Oracle 11g 及更早: 使用 ROWNUM（无 LIMIT 关键字）")
                lines.append("- Oracle 12c+: 可使用 FETCH FIRST n ROWS ONLY")

            lines.append("")
            lines.append("**ORDER BY 聚合函数**:")
            lines.append("- ❌ ORDER BY COUNT DESC（错误：COUNT 是保留字）")
            lines.append("- ✅ ORDER BY COUNT(*) DESC（正确：完整函数名）")
            lines.append("- ✅ ORDER BY 别名 DESC（正确：先定义别名再排序）")
            lines.append("")
            lines.append("**标识符引用**:")
            lines.append("- 表名格式: OWNER.TABLE_NAME")
            lines.append("- 使用双引号: \"OWNER\".\"TABLE_NAME\"")
            lines.append("- 日期函数: TO_DATE('YYYY-MM-DD', 'YYYY-MM-DD')")

        return "\n".join(lines)

    # 提供语法提示
    if "syntax" in error_msg.lower() or "parse" in error_msg.lower():
        lines.append("**SQL 语法提示**:")
        lines.append(f"- SQLite: 标准 SQL，使用 LIMIT")
        lines.append(f"- MySQL: 使用 LIMIT，标识符用反引号 ``")
        lines.append(f"- PostgreSQL: 使用 LIMIT，标识符用双引号 \"\"")
        lines.append(f"- SQL Server: 使用 TOP，标识符用方括号 []")
        lines.append(f"- Oracle: 使用 ROWNUM，无 LIMIT")

    elif "table" in error_msg.lower() and ("not found" in error_msg.lower() or "no such" in error_msg.lower()):
        lines.append("**建议**: 使用 `list_tables` 查看可用表，或使用 `get_table_spec` 获取表结构")

    elif "column" in error_msg.lower() and ("unknown" in error_msg.lower() or "invalid" in error_msg.lower()):
        lines.append("**建议**: 使用 `get_table_spec` 查看表的列定义")

    return "\n".join(lines)


@tool(
    "list_tables",
    description=(
        "列出指定数据库中的所有表名，支持按分组筛选和分页。"
        "使用场景：(1) 表列表未注入到 system prompt；(2) 表太多需要完整列表；"
        "(3) 需要查看特定分组的表；(4) 确认数据库中有哪些表。"
        "获取表名后使用 get_table_spec 查看详细结构。"
    ),
    args={
        "db_name": {
            "type": "string",
            "description": (
                "数据库名称，使用可用数据库列表中的 db_name 字段值。"
            ),
            "required": True,
        },
        "group": {
            "type": "string",
            "description": (
                "可选的分组名称，只列出该分组的表。"
                "如果不指定，列出所有表。"
            ),
            "required": False,
        },
        "page": {
            "type": "integer",
            "description": (
                "分页页码，从 1 开始，默认为 1。"
                "当表数量很多时，使用分页查看。"
            ),
            "required": False,
        },
        "page_size": {
            "type": "integer",
            "description": (
                "每页显示的表数量，默认为 100。"
            ),
            "required": False,
        },
    },
    category=ToolCategory.UTILITY,
)
async def list_tables(
    db_name: str,
    group: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
    **kwargs,
) -> str:
    """List all tables in the specified database with optional group filter and pagination.

    Use this tool when:
    1. Table list was not injected into the system prompt
    2. There are too many tables and you need a complete list
    3. You need to view tables in a specific group
    4. You need to confirm what tables exist in the database

    Args:
        db_name: The database name from the available databases list
        group: Optional group name to filter tables
        page: Page number for pagination (starts from 1)
        page_size: Number of tables per page (default 100)

    Returns:
        A list of table names in the database, optionally filtered by group
    """
    try:
        from derisk._private.config import Config

        CFG = Config()

        # 优先从 agent 的 resource_map 中获取已初始化的 connector
        agent_connector, agent_ds_id = _resolve_db_from_agent(db_name, kwargs)
        ds_id = agent_ds_id

        # Resolve datasource_id if not from agent
        if not ds_id:
            try:
                from derisk_serve.datasource.manages.connect_config_db import (
                    ConnectConfigDao,
                )
                dao = ConnectConfigDao()
                entity = dao.get_by_names(db_name)
                if entity:
                    ds_id = entity.id
            except ImportError:
                pass

        # Try spec service for structured table list (preferred)
        if ds_id:
            try:
                from derisk_serve.datasource.service.spec_service import DbSpecService

                spec_service = DbSpecService()

                if spec_service.has_spec(ds_id):
                    stats = spec_service.get_db_stats(ds_id)
                    all_specs = spec_service.get_all_table_specs(ds_id)

                    # Filter by group if specified
                    if group:
                        filtered = [
                            t for t in all_specs
                            if t.get("group_name") == group or t.get("group") == group
                        ]
                        if not filtered:
                            available_groups = list(stats.get("groups", {}).keys())
                            return (
                                f"No tables found in group '{group}'.\n"
                                f"Available groups: {', '.join(available_groups)}"
                            )
                        all_specs = filtered

                    total = len(all_specs)
                    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
                    page = max(1, min(page, total_pages))
                    start = (page - 1) * page_size
                    display = all_specs[start:start + page_size]

                    lines = [f"**Tables in '{db_name}'**"]
                    if group:
                        lines.append(f"(Group: {group})")
                    lines.append("")

                    for i, t in enumerate(display, start + 1):
                        name = t.get("table_name", "")
                        comment = ""
                        # Get comment from table_comment or comment field
                        tc = t.get("table_comment", "") or t.get("comment", "")
                        if tc:
                            comment = tc[:50] + "..." if len(tc) > 50 else tc
                        lines.append(f"{i}. `{name}`" + (f" - {comment}" if comment else ""))

                    lines.append("")
                    lines.append(f"**Total: {total} tables**")
                    if total_pages > 1:
                        lines.append(f"Page {page}/{total_pages} (page_size={page_size})")

                    # Show available groups
                    if stats.get("groups") and not group:
                        lines.append("")
                        lines.append("**Available groups:**")
                        for g_name, g_count in sorted(
                            stats["groups"].items(), key=lambda x: -x[1]
                        ):
                            lines.append(f"- {g_name}: {g_count} tables")

                    lines.append("")
                    lines.append("_Use `get_table_spec` to get detailed schema for specific tables._")

                    return "\n".join(lines)
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"Failed to get table list from spec_service: {e}")

        # Fallback: use connector
        connector = agent_connector or CFG.local_db_manager.get_connector(db_name)
        if not connector:
            return f"Error: Database '{db_name}' not found. Please check the db_name."

        table_names = connector.get_table_names()

        if not table_names:
            return f"No tables found in database '{db_name}'."

        # Apply pagination to connector results
        total = len(table_names)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        display = table_names[start:start + page_size]

        lines = [f"**Tables in database '{db_name}'**:", ""]
        for i, name in enumerate(display, start + 1):
            lines.append(f"{i}. `{name}`")

        lines.append("")
        lines.append(f"**Total: {total} tables**")
        if total_pages > 1:
            lines.append(f"Page {page}/{total_pages} (page_size={page_size})")

        lines.append("")
        lines.append("_Use `get_table_spec` to get detailed schema for specific tables._")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error listing tables for {db_name}: {e}")
        return f"Error listing tables: {str(e)}"


@tool(
    "search_tables",
    description=(
        "根据自然语言问题或多个检索意图搜索数据库中相关的表。"
        "适用于大型数据库（表数量多）或不确定需要查询哪些表的情况。"
        "\n\n**三种检索模式：**"
        "\n1. 关键词模式（question）: 根据关键词匹配表名、列名、注释"
        "\n2. 多意图模式（intents）: 支持多个检索维度，如 ['销售记录', '天气数据']"
        "\n3. LLM模式（use_llm=true）: 让LLM根据所有表的名称和简介智能筛选"
        "\n\n**使用场景：**"
        "\n- 用户问题涉及多方面数据时，用 intents 参数拆分检索意图"
        "\n- 表数量很多且关键词匹配不准时，用 use_llm=true 开启LLM智能筛选"
    ),
    args={
        "db_name": {
            "type": "string",
            "description": (
                "数据库名称，使用可用数据库列表中的 db_name 字段值。"
            ),
            "required": True,
        },
        "question": {
            "type": "string",
            "description": (
                "自然语言描述，例如：'用户订单相关的表'。"
                "如果不指定，则必须提供 intents 参数。"
            ),
            "required": False,
        },
        "intents": {
            "type": "string",
            "description": (
                "多个检索意图/标签，用逗号分隔。"
                "例如：'销售记录,天气数据,用户信息'。"
                "适用于问题涉及多方面数据时，系统会对每个意图分别检索并合并结果。"
                "这样可以找到隐藏在问题外的信息维度相关的表。"
            ),
            "required": False,
        },
        "use_llm": {
            "type": "boolean",
            "description": (
                "是否使用LLM进行智能筛选（默认false）。"
                "开启后，系统会将所有表的名称和简介发送给LLM，"
                "LLM根据问题/意图智能返回相关表名列表。"
                "适用于表数量很多且关键词匹配不准的场景。"
            ),
            "required": False,
        },
        "max_results": {
            "type": "integer",
            "description": "返回的最大表数量，默认为 15。",
            "required": False,
        },
    },
    category=ToolCategory.UTILITY,
)
async def search_tables(
    db_name: str,
    question: Optional[str] = None,
    intents: Optional[str] = None,
    use_llm: bool = False,
    max_results: int = 15,
    **kwargs,
) -> str:
    """Search for relevant tables based on natural language question or multiple intents.

    Supports three search modes:
    1. Keyword mode (question): Match against table names, column names, comments
    2. Multi-intent mode (intents): Support multiple search dimensions
    3. LLM mode (use_llm=True): Let LLM intelligently filter based on all table info

    Args:
        db_name: The database name from the available databases list
        question: Natural language question describing what tables you need
        intents: Multiple search intents separated by comma, e.g., "sales,weather,user"
        use_llm: Whether to use LLM for intelligent filtering
        max_results: Maximum number of tables to return (default 15)

    Returns:
        A list of recommended tables with match scores and reasons
    """
    try:
        from derisk._private.config import Config

        CFG = Config()

        # 优先从 agent 的 resource_map 中获取 datasource_id
        agent_connector, agent_ds_id = _resolve_db_from_agent(db_name, kwargs)
        ds_id = agent_ds_id

        # Resolve datasource_id if not from agent
        if not ds_id:
            try:
                from derisk_serve.datasource.manages.connect_config_db import (
                    ConnectConfigDao,
                )
                dao = ConnectConfigDao()
                entity = dao.get_by_names(db_name)
                if entity:
                    ds_id = entity.id
            except ImportError:
                pass

        if not ds_id:
            return f"Error: Could not resolve datasource ID for '{db_name}'. " \
                   f"Please ensure the database is registered."

        # Parse intents if provided
        intent_list = []
        if intents:
            intent_list = [i.strip() for i in intents.split(",") if i.strip()]

        # Build search queries: combine question and intents
        search_queries = []
        if question:
            search_queries.append(question)
        if intent_list:
            search_queries.extend(intent_list)

        if not search_queries:
            return (
                "Error: Please provide either 'question' or 'intents' parameter.\n\n"
                "Examples:\n"
                "- question: '用户订单相关的表'\n"
                "- intents: '销售记录,天气数据,用户信息'\n"
                "- Both: question='分析运营数据', intents='销售,用户,订单'"
            )

        # LLM Mode: Use LLM for intelligent filtering
        if use_llm:
            return await _search_tables_with_llm(
                db_name, ds_id, search_queries, max_results, kwargs
            )

        # Keyword Mode: Use Schema Linking service
        try:
            from derisk_serve.datasource.service.schema_link_service import (
                SchemaLinkService,
            )

            link_service = SchemaLinkService()

            # Collect all recommendations from each query
            all_recommendations = {}  # table_name -> (score, reasons, matched_queries, group, row_count)

            for query in search_queries:
                recs = link_service.suggest_tables(ds_id, query, max_results=max_results)
                for rec in recs:
                    if rec.table_name in all_recommendations:
                        # Merge: add score and reason
                        existing = all_recommendations[rec.table_name]
                        existing[0] += rec.score  # Accumulate score
                        existing[1].extend(rec.reasons[:2])  # Add reasons
                        existing[2].append(query)  # Track which query matched
                    else:
                        all_recommendations[rec.table_name] = [
                            rec.score,
                            list(rec.reasons[:3]),
                            [query],
                            rec.group,
                            rec.row_count  # 新增：行数信息
                        ]

            if not all_recommendations:
                return (
                    f"**搜索结果**\n\n"
                    f"检索意图: {', '.join(search_queries)}\n\n"
                    f"No matching tables found.\n\n"
                    f"_Suggestions:\n"
                    f"- Try different keywords or intents\n"
                    f"- Use `list_tables` to see all available tables\n"
                    f"- Try use_llm=true for LLM intelligent filtering_"
                )

            # Sort by score and limit results
            sorted_tables = sorted(
                all_recommendations.items(),
                key=lambda x: -x[1][0]
            )[:max_results]

            # Build output
            lines = [f"**搜索结果**"]
            if len(search_queries) > 1:
                lines.append(f"检索意图: \"{', '.join(search_queries)}\"")
            else:
                lines.append(f"问题: \"{search_queries[0]}\"")
            lines.append(f"找到 {len(sorted_tables)} 张相关表：")
            lines.append("")

            for i, (table_name, info) in enumerate(sorted_tables, 1):
                score, reasons, matched_queries, group, row_count = info
                score_display = f"{score:.1f}"
                reason_str = "; ".join(reasons[:3])
                lines.append(f"{i}. **{table_name}**")
                lines.append(f"   - 匹配分数: {score_display}")
                if row_count:
                    lines.append(f"   - 数据行数: {row_count}")
                if len(matched_queries) > 1:
                    lines.append(f"   - 匹配意图: {', '.join(matched_queries)}")
                lines.append(f"   - 匹配原因: {reason_str}")
                if group and group != "default":
                    lines.append(f"   - 所属分组: {group}")
                lines.append("")  # Add spacing

            # Provide recommended table names for easy copy
            top_names = [t[0] for t in sorted_tables]
            lines.append("**推荐的表名（可直接用于 get_table_spec）:**")
            lines.append(f"`{', '.join(top_names)}`")
            lines.append("")
            lines.append("_使用 `get_table_spec(db_name, table_names)` 获取表的详细结构_")

            return "\n".join(lines)

        except ImportError:
            return (
                "Error: Schema Linking service not available.\n"
                "Please use `list_tables` to see all available tables."
            )
        except Exception as e:
            logger.error(f"Error in Schema Linking search: {e}")
            return f"Error searching tables: {str(e)}\n\n" \
                   f"_Fallback: Use `list_tables` to see all available tables._"

    except Exception as e:
        logger.error(f"Error in search_tables: {e}")
        return f"Error: {str(e)}"


async def _search_tables_with_llm(
    db_name: str,
    ds_id: int,
    search_queries: List[str],
    max_results: int,
    kwargs: Dict,
) -> str:
    """Use LLM to intelligently filter relevant tables.

    This mode sends all table names and descriptions to LLM,
    and asks LLM to return the most relevant tables.
    """
    try:
        from derisk_serve.datasource.service.spec_service import DbSpecService

        spec_service = DbSpecService()

        if not spec_service.has_spec(ds_id):
            return (
                "**LLM搜索模式**\n\n"
                f"Error: Database spec not available for '{db_name}'.\n"
                "LLM mode requires generated database spec.\n\n"
                "_Fallback: Use keyword mode (use_llm=false) or `list_tables`_"
            )

        # Get all table info
        all_specs = spec_service.get_all_table_specs(ds_id)

        if not all_specs:
            return f"No tables found in database '{db_name}'."

        # Build table list for LLM prompt
        table_info_lines = []
        for spec in all_specs:
            table_name = spec.get("table_name", "")
            comment = spec.get("table_comment", "") or spec.get("comment", "")
            group = spec.get("group_name", "") or spec.get("group", "")
            # Include column names for better matching
            columns = spec.get("columns", [])
            col_names = [c.get("name", "") for c in columns[:10] if c.get("name")]
            col_str = ", ".join(col_names) if col_names else ""

            line = f"- {table_name}"
            if comment:
                line += f": {comment[:80]}"
            if group and group != "default":
                line += f" [group:{group}]"
            if col_str:
                line += f" (columns: {col_str})"
            table_info_lines.append(line)

        tables_text = "\n".join(table_info_lines)

        # Build LLM prompt
        search_context = ", ".join(search_queries)
        llm_prompt = f"""你是一个数据库专家。用户需要查找数据库中与以下需求相关的表：

需求/意图：{search_context}

数据库中的所有表（共{len(all_specs)}张）：
{tables_text}

请根据以上表信息，找出与用户需求最相关的表。返回格式要求：
1. 只返回表名列表，用逗号分隔
2. 最多返回{max_results}张表
3. 按相关性排序，最相关的表在前
4. 不要返回任何解释，只返回表名

示例输出格式：
orders,customers,products,order_items

你的回答："""

        # Get agent's LLM client if available
        agent = kwargs.get("agent")
        llm_client = None

        if agent and hasattr(agent, "not_null_llm_client"):
            try:
                llm_client = agent.not_null_llm_client
            except Exception:
                pass

        # Try to get LLM client from Config
        if not llm_client:
            try:
                from derisk.model import DefaultLLMClient
                from derisk.model.cluster import WorkerManagerFactory
                from derisk.component import ComponentType

                # Try to get from system app if available
                system_app = kwargs.get("context", {}).get("system_app") if kwargs.get("context") else None
                if system_app:
                    worker_manager = system_app.get_component(
                        ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
                    ).create()
                    llm_client = DefaultLLMClient(worker_manager, auto_convert_message=True)
            except Exception as e:
                logger.warning(f"Failed to get LLM client: {e}")

        if not llm_client:
            return (
                "**LLM搜索模式**\n\n"
                "Error: LLM client not available.\n"
                "Please use keyword mode (use_llm=false) instead.\n\n"
                f"_关键词搜索: search_tables(db_name='{db_name}', question='{search_context}')_"
            )

        # Call LLM
        from derisk.core import ModelRequest

        model_request = ModelRequest(
            model="",  # Use default model
            messages=[{"role": "user", "content": llm_prompt}],
            temperature=0.1,  # Low temperature for deterministic output
        )

        llm_response = ""
        async for output in llm_client.generate_stream(model_request):
            llm_response += output.text or ""

        # Parse LLM response - extract table names
        llm_response = llm_response.strip()

        # Remove potential markdown formatting
        if llm_response.startswith("```"):
            lines = llm_response.split("\n")
            llm_response = "\n".join(lines[1:-1] if len(lines) > 2 else lines)

        # Parse table names from response
        suggested_tables = []
        for part in llm_response.replace("\n", ",").split(","):
            table_name = part.strip()
            # Clean up table name (remove quotes, brackets, etc.)
            table_name = table_name.replace("`", "").replace("'", "").replace('"', "")
            table_name = table_name.replace("[", "").replace("]", "")
            table_name = table_name.strip()
            if table_name and table_name in [s.get("table_name") for s in all_specs]:
                suggested_tables.append(table_name)

        if not suggested_tables:
            # Fallback: try to extract any table-like names
            import re
            potential_names = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', llm_response)
            all_table_names = [s.get("table_name") for s in all_specs]
            suggested_tables = [n for n in potential_names if n in all_table_names][:max_results]

        if not suggested_tables:
            return (
                f"**LLM搜索结果**\n\n"
                f"检索意图: {search_context}\n\n"
                f"LLM未能识别相关表名。\n"
                f"LLM回答: {llm_response[:200]}\n\n"
                f"_Fallback: Use keyword mode (use_llm=false)_"
            )

        # Build output
        lines = [f"**LLM智能搜索结果**"]
        lines.append(f"检索意图: \"{search_context}\"")
        lines.append(f"数据库表总数: {len(all_specs)}")
        lines.append(f"LLM推荐: {len(suggested_tables)} 张表")
        lines.append("")

        for i, table_name in enumerate(suggested_tables, 1):
            # Get table info for display
            spec = next((s for s in all_specs if s.get("table_name") == table_name), None)
            if spec:
                comment = spec.get("table_comment", "") or spec.get("comment", "")
                group = spec.get("group_name", "") or spec.get("group", "")
                lines.append(f"{i}. **{table_name}**")
                if comment:
                    lines.append(f"   - 简介: {comment[:80]}")
                if group and group != "default":
                    lines.append(f"   - 分组: {group}")
            else:
                lines.append(f"{i}. **{table_name}**")
            lines.append("")  # Add spacing

        lines.append("**推荐的表名（可直接用于 get_table_spec）:**")
        lines.append(f"`{', '.join(suggested_tables)}`")
        lines.append("")
        lines.append("_使用 `get_table_spec(db_name, table_names)` 获取表的详细结构_")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error in LLM search: {e}")
        return f"Error in LLM search: {str(e)}\n\n" \
               f"_Fallback: Use keyword mode (use_llm=false)_"