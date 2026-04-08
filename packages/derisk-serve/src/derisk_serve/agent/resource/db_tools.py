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
from typing import Any, Dict, List, Optional

from derisk.agent.tools.decorators import tool, ToolCategory
from derisk.vis import Vis

logger = logging.getLogger(__name__)

# 常量配置
MAX_DISPLAY_ROWS = 200  # 默认显示行数
MAX_EXPORT_ROWS = 200  # 超过此行数导出为 CSV
PAGE_SIZE = 200  # 分页大小


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
        "获取一个或多个表的详细 schema 信息，包括列定义、类型、注释、索引、样本数据等。"
        "支持两种模式：(1) 指定表名获取多张表的详细信息；(2) 传入问题让 AI 推荐相关表。"
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
                "要查询的表名，支持多张表，用逗号分隔。"
                "例如: 'users,orders,products'。"
                "如果不指定，则使用 question 参数让系统推荐相关表。"
            ),
            "required": False,
        },
        "question": {
            "type": "string",
            "description": (
                "自然语言问题，系统会根据问题推荐相关的表。"
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
                        rec_lines.append(
                            f"  - {rec.table_name} (score: {rec.score:.1f}, "
                            f"reasons: {reason_str})"
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

        # Exact mode: parse table names
        if table_names:
            names = [n.strip() for n in table_names.split(",") if n.strip()]
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

            # 构建结果
            result_data = {
                "sql": sql,
                "db_name": db_name,
                "db_type": db_type,
                "dialect": dialect,
                "columns": columns,
                "rows": display_rows,
                "total_rows": total_rows,
                "page": page,
                "total_pages": total_pages,
                "page_size": PAGE_SIZE,
                "has_more": page < total_pages,
            }

            # 如果结果超过 MAX_EXPORT_ROWS，需要导出 CSV
            csv_file_path = None
            if total_rows > MAX_EXPORT_ROWS:
                csv_file_path = await _export_to_csv(
                    columns=columns,
                    rows=all_rows,
                    db_name=db_name,
                    sql=sql,
                    kwargs=kwargs,
                )
                if csv_file_path:
                    result_data["csv_file"] = csv_file_path
                    result_data["csv_export_reason"] = f"结果超过 {MAX_EXPORT_ROWS} 行，已导出为 CSV 文件"

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
        return _format_error(error_msg, db_type=dialect if 'dialect' in dir() else 'unknown')


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


def _format_error(error_msg: str, db_type: str) -> str:
    """格式化错误信息"""

    lines = ["❌ **SQL 执行错误**", ""]
    lines.append(f"**数据库类型**: {db_type}")
    lines.append(f"**错误信息**: {error_msg}")
    lines.append("")

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
        "列出指定数据库中的所有表名。"
        "使用场景：(1) 表列表未注入到 system prompt；(2) 表太多需要完整列表；"
        "(3) 需要确认数据库中有哪些表。"
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
    },
    category=ToolCategory.UTILITY,
)
async def list_tables(
    db_name: str,
    **kwargs,
) -> str:
    """List all tables in the specified database.

    Use this tool when:
    1. Table list was not injected into the system prompt
    2. There are too many tables and you need a complete list
    3. You need to confirm what tables exist in the database

    Args:
        db_name: The database name from the available databases list

    Returns:
        A list of table names in the database
    """
    try:
        from derisk._private.config import Config

        CFG = Config()

        # 优先从 agent 的 resource_map 中获取已初始化的 connector
        agent_connector, _ = _resolve_db_from_agent(db_name, kwargs)
        connector = agent_connector
        if not connector:
            connector = CFG.local_db_manager.get_connector(db_name)
        if not connector:
            return f"Error: Database '{db_name}' not found. Please check the db_name."

        # Get table names
        table_names = connector.get_table_names()

        if not table_names:
            return f"No tables found in database '{db_name}'."

        # Format output
        lines = [f"**Tables in database '{db_name}'**:", ""]
        for i, name in enumerate(table_names, 1):
            lines.append(f"{i}. `{name}`")

        lines.append(f"\n**Total: {len(table_names)} tables**")
        lines.append("\n_Use `get_table_spec` to get detailed schema for specific tables._")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error listing tables for {db_name}: {e}")
        return f"Error listing tables: {str(e)}"