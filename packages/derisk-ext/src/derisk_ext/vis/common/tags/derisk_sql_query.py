"""SQL Query VIS Component.

Renders SQL query results with:
- SQL statement display
- Table results with pagination
- Database type indicator
- CSV export info for large results

Usage:
    ```d-sql-query
    {
        "sql": "SELECT * FROM users LIMIT 10",
        "db_name": "my_database",
        "db_type": "sqlite",
        "dialect": "sqlite",
        "columns": ["id", "name", "email"],
        "rows": [[1, "Alice", "alice@example.com"], ...],
        "total_rows": 100,
        "page": 1,
        "total_pages": 2,
        "page_size": 50,
        "has_more": true,
        "csv_file": null,
        "csv_export_reason": null
    }
    ```
"""

from typing import Any, Dict, Optional

from derisk.vis import Vis


class DeriskSqlQuery(Vis):
    """SQL Query visualization component.

    Provides structured data for frontend SQL query result rendering.
    Frontend should render:
    1. SQL statement with database type badge
    2. Results table with pagination controls
    3. Export/download link if CSV was generated
    """

    @classmethod
    def vis_tag(cls) -> str:
        """VIS tag identifier."""
        return "d-sql-query"

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate parameters for SQL query visualization.

        Expected kwargs:
            sql: The SQL query string
            db_name: Database name
            db_type: Database type (sqlite, mysql, postgresql, etc.)
            dialect: SQL dialect (same as db_type usually)
            columns: List of column names
            rows: List of row data (each row is a list of values)
            total_rows: Total number of rows in result
            page: Current page number
            total_pages: Total number of pages
            page_size: Number of rows per page
            has_more: Whether there are more pages
            csv_file: Optional CSV file path for exported results
            csv_export_reason: Optional reason for CSV export
            raw_result: Optional raw result string for non-tabular results

        Returns:
            Dict with structured data for frontend rendering
        """
        # Required fields
        sql = kwargs.get("sql", "")
        db_name = kwargs.get("db_name", "")
        db_type = kwargs.get("db_type", "unknown")
        dialect = kwargs.get("dialect", db_type)
        columns = kwargs.get("columns", [])
        rows = kwargs.get("rows", [])
        total_rows = kwargs.get("total_rows", 0)
        page = kwargs.get("page", 1)
        total_pages = kwargs.get("total_pages", 0)
        page_size = kwargs.get("page_size", 50)
        has_more = kwargs.get("has_more", False)

        # Optional fields
        csv_file = kwargs.get("csv_file")
        csv_export_reason = kwargs.get("csv_export_reason")
        raw_result = kwargs.get("raw_result")

        result = {
            "sql": sql,
            "db_name": db_name,
            "db_type": db_type,
            "dialect": dialect,
            "columns": columns,
            "rows": rows,
            "total_rows": total_rows,
            "page": page,
            "total_pages": total_pages,
            "page_size": page_size,
            "has_more": has_more,
        }

        # Add optional fields if present
        if csv_file:
            result["csv_file"] = csv_file
            result["csv_export_reason"] = csv_export_reason

        if raw_result:
            result["raw_result"] = raw_result

        return result

    async def generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Async version of generate_param."""
        return self.sync_generate_param(**kwargs)