"""Database tools for agent interaction.

Provides tools that allow agents to retrieve detailed table specs
during execution, enabling progressive loading of schema information.
Supports both exact mode (specify table names) and recommend mode
(pass a question to get table suggestions via Schema Linking).
"""

import logging
from typing import Any, Dict, List, Optional

from derisk.agent.tools.decorators import tool, ToolCategory

logger = logging.getLogger(__name__)


@tool(
    "get_table_spec",
    description=(
        "Get detailed schema information for database tables. "
        "Two modes: (1) Pass table_names for specific tables, "
        "(2) Pass question to get AI-recommended relevant tables. "
        "Use after reviewing the database overview."
    ),
    args={
        "table_names": {
            "type": "string",
            "description": (
                "Comma-separated list of table names to get specs for, "
                "e.g. 'users,orders'. If omitted, use 'question' for "
                "automatic table recommendation."
            ),
            "required": False,
        },
        "question": {
            "type": "string",
            "description": (
                "Natural language question for automatic table recommendation. "
                "The system will suggest relevant tables based on the question. "
                "Use this when you're unsure which tables to query."
            ),
            "required": False,
        },
        "db_name": {
            "type": "string",
            "description": (
                "The database name to look up tables in. "
                "Use the database name from the bound datasource resource."
            ),
            "required": True,
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
    - Exact mode: provide table_names directly
    - Recommend mode: provide question, uses Schema Linking to suggest tables
    """
    try:
        from derisk._private.config import Config

        CFG = Config()

        # Resolve datasource
        ds_id = None
        spec_service = None
        try:
            from derisk_serve.datasource.manages.connect_config_db import (
                ConnectConfigDao,
            )
            from derisk_serve.datasource.service.spec_service import (
                DbSpecService,
            )

            dao = ConnectConfigDao()
            entity = dao.get_by_names(db_name)
            if entity:
                ds_id = entity.id
                spec_service = DbSpecService()
        except ImportError:
            pass

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
                    connector = CFG.local_db_manager.get_connector(db_name)
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
        connector = CFG.local_db_manager.get_connector(db_name)
        return connector.get_table_info(names)

    except Exception as e:
        logger.error(f"Error getting table spec: {e}")
        return f"Error getting table spec: {str(e)}"
