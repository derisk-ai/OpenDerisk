"""DDL SQL file parser.

Parse SQL DDL files containing CREATE TABLE statements and extract
table definitions, columns, constraints, and comments.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from .base_parser import BaseSchemaParser, ParsedSchema, ParsedTable

logger = logging.getLogger(__name__)


class DDLParser(BaseSchemaParser):
    """Parse SQL DDL files containing CREATE TABLE statements."""

    @classmethod
    def supported_extensions(cls) -> List[str]:
        return [".sql", ".ddl"]

    @classmethod
    def parser_name(cls) -> str:
        return "ddl"

    def parse(self, file_path: str) -> ParsedSchema:
        """Parse SQL DDL file and extract table definitions.

        Args:
            file_path: Path to the DDL file

        Returns:
            ParsedSchema with tables and views
        """
        self.validate_file(file_path)

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        tables = []
        views = []

        # Parse CREATE TABLE statements
        table_matches = self._find_create_tables(content)
        for match in table_matches:
            try:
                table = self._parse_create_table(match, content)
                if table:
                    tables.append(table)
            except Exception as e:
                logger.warning(f"Failed to parse CREATE TABLE: {e}")

        # Parse CREATE VIEW statements
        view_matches = self._find_create_views(content)
        for match in view_matches:
            try:
                view = self._parse_create_view(match, content)
                if view:
                    views.append(view)
            except Exception as e:
                logger.warning(f"Failed to parse CREATE VIEW: {e}")

        logger.info(
            f"Parsed DDL file: {file_path}, tables={len(tables)}, views={len(views)}"
        )

        return ParsedSchema(
            tables=tables,
            views=views,
            references=[],  # FKs are within CREATE TABLE
            source_file=file_path,
            source_type="ddl",
        )

    def _find_create_tables(self, content: str) -> List[Dict[str, Any]]:
        """Find all CREATE TABLE statements in content.

        Args:
            content: SQL file content

        Returns:
            List of match dicts with table_name and body
        """
        matches = []

        # Pattern: CREATE TABLE [IF NOT EXISTS] name (body)
        # Handle various quote styles: `name`, "name", [name], or plain name
        pattern = re.compile(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"[`\"\[]?(\w+)[`\"\]]?\s*\((.*?)\)",
            re.IGNORECASE | re.DOTALL,
        )

        for match in pattern.finditer(content):
            matches.append({
                "table_name": match.group(1),
                "body": match.group(2),
                "full_match": match.group(0),
            })

        return matches

    def _find_create_views(self, content: str) -> List[Dict[str, Any]]:
        """Find all CREATE VIEW statements.

        Args:
            content: SQL file content

        Returns:
            List of match dicts
        """
        matches = []

        pattern = re.compile(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+"
            r"[`\"\[]?(\w+)[`\"\]]?\s*(?:AS\s+)?(.+?)(?:;|$)",
            re.IGNORECASE | re.DOTALL,
        )

        for match in pattern.finditer(content):
            matches.append({
                "view_name": match.group(1),
                "body": match.group(2),
            })

        return matches

    def _parse_create_table(
        self, match: Dict[str, Any], full_content: str
    ) -> Optional[ParsedTable]:
        """Parse a CREATE TABLE match.

        Args:
            match: Match dict with table_name and body
            full_content: Full SQL file content (for comment extraction)

        Returns:
            ParsedTable or None
        """
        table_name = match["table_name"]
        body = match["body"]

        columns = []
        indexes = []
        foreign_keys = []
        pk_columns = set()

        # Split body by lines and parse each definition
        # Handle multi-line definitions carefully
        lines = self._split_body(body)

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Column definition: name type [constraints]
            col = self._parse_column_line(line)
            if col:
                columns.append(col)
                if col.get("pk"):
                    pk_columns.add(col["name"])
                continue

            # PRIMARY KEY constraint
            pk_match = re.match(
                r"PRIMARY\s+KEY\s*\(([^)]+)\)", line, re.IGNORECASE
            )
            if pk_match:
                pk_cols = self._parse_column_list(pk_match.group(1))
                pk_columns.update(pk_cols)
                continue

            # FOREIGN KEY constraint
            fk = self._parse_fk_line(line)
            if fk:
                foreign_keys.append(fk)
                continue

            # UNIQUE/INDEX constraint
            idx = self._parse_index_line(line)
            if idx:
                indexes.append(idx)
                continue

        # Update pk status for columns
        for col in columns:
            if col["name"] in pk_columns:
                col["pk"] = True

        # Extract table comment from COMMENT ON TABLE
        table_comment = self._extract_table_comment(table_name, full_content)

        # Extract column comments
        for col in columns:
            col_comment = self._extract_column_comment(
                table_name, col["name"], full_content
            )
            if col_comment:
                col["comment"] = col_comment

        # Build CREATE DDL
        create_ddl = match.get("full_match", f"CREATE TABLE {table_name} ({body});")

        return ParsedTable(
            table_name=table_name,
            table_comment=table_comment,
            columns=columns,
            indexes=indexes,
            foreign_keys=foreign_keys,
            create_ddl=create_ddl,
        )

    def _parse_create_view(
        self, match: Dict[str, Any], full_content: str
    ) -> Optional[ParsedTable]:
        """Parse a CREATE VIEW match.

        Args:
            match: Match dict with view_name and body
            full_content: Full SQL content

        Returns:
            ParsedTable for the view
        """
        view_name = match["view_name"]

        # Views don't have column definitions in CREATE VIEW
        # We'd need to analyze the SELECT statement to infer columns
        # For now, return empty columns

        table_comment = self._extract_table_comment(view_name, full_content)

        return ParsedTable(
            table_name=view_name,
            table_comment=table_comment,
            columns=[],  # Would need SELECT analysis
            indexes=[],  # Views don't have indexes
            foreign_keys=[],
            create_ddl=f"CREATE VIEW {view_name} AS {match['body']};",
        )

    def _split_body(self, body: str) -> List[str]:
        """Split CREATE TABLE body into individual definitions.

        Args:
            body: The body content between parentheses

        Returns:
            List of definition lines
        """
        # Simple split by comma, but need to handle nested parens
        # For complex cases like CHECK constraints or function calls

        lines = []
        current_line = ""
        paren_depth = 0

        for char in body:
            if char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth -= 1

            if char == "," and paren_depth == 0:
                lines.append(current_line.strip())
                current_line = ""
            else:
                current_line += char

        if current_line.strip():
            lines.append(current_line.strip())

        return lines

    def _parse_column_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a column definition line.

        Args:
            line: Column definition line

        Returns:
            Column dict or None if not a column
        """
        # Skip constraint lines
        if re.match(
            r"(PRIMARY|FOREIGN|UNIQUE|INDEX|KEY|CONSTRAINT|CHECK)",
            line,
            re.IGNORECASE,
        ):
            return None

        # Pattern: name type[(size)] [constraints]
        match = re.match(
            r"[`\"\[]?(\w+)[`\"\]]?\s+"
            r"(\w+(?:\s*\([^)]*\))?)"
            r"(.*)$",
            line,
            re.IGNORECASE,
        )
        if not match:
            return None

        col_name = match.group(1)
        col_type = match.group(2).upper()
        constraints = match.group(3) or ""

        # Parse constraints
        nullable = "NOT NULL" not in constraints.upper()
        is_pk = "PRIMARY KEY" in constraints.upper()

        # Default value
        default = None
        default_match = re.search(
            r"DEFAULT\s+([^\s,]+|'[^']*'|\([^)]*\))",
            constraints,
            re.IGNORECASE,
        )
        if default_match:
            default = default_match.group(1).strip("'\"")

        return {
            "name": col_name,
            "type": col_type,
            "nullable": nullable,
            "default": default,
            "comment": "",
            "pk": is_pk,
        }

    def _parse_column_list(self, col_list: str) -> List[str]:
        """Parse column list like 'col1, col2, col3'.

        Args:
            col_list: Comma-separated column names

        Returns:
            List of column names
        """
        cols = []
        for col in col_list.split(","):
            col = col.strip().strip("`\"[]'")
            if col:
                cols.append(col)
        return cols

    def _parse_fk_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a FOREIGN KEY constraint line.

        Args:
            line: FK constraint line

        Returns:
            FK dict or None
        """
        match = re.match(
            r"(?:CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY\s*\(([^)]+)\)\s*"
            r"REFERENCES\s+[`\"\[]?(\w+)[`\"\]]?\s*\(([^)]+)\)",
            line,
            re.IGNORECASE,
        )
        if not match:
            return None

        return {
            "constrained_columns": self._parse_column_list(match.group(1)),
            "referred_table": match.group(2),
            "referred_columns": self._parse_column_list(match.group(3)),
        }

    def _parse_index_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse an INDEX/UNIQUE constraint line.

        Args:
            line: Index definition line

        Returns:
            Index dict or None
        """
        # UNIQUE (col1, col2) or INDEX idx_name (col1, col2)
        match = re.match(
            r"(?:UNIQUE\s+)?(?:INDEX|KEY)\s+(?:\w+\s+)?\(([^)]+)\)",
            line,
            re.IGNORECASE,
        )
        if not match:
            return None

        is_unique = "UNIQUE" in line.upper()

        return {
            "name": "",
            "columns": self._parse_column_list(match.group(1)),
            "unique": is_unique,
        }

    def _extract_table_comment(
        self, table_name: str, content: str
    ) -> Optional[str]:
        """Extract COMMENT ON TABLE from content.

        Args:
            table_name: Table name
            content: Full SQL content

        Returns:
            Comment string or None
        """
        match = re.search(
            rf"COMMENT\s+ON\s+TABLE\s+[`\"\[]?{table_name}[`\"\]]?\s+IS\s+"
            r"['\"]([^'\"]+)['\"]",
            content,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
        return None

    def _extract_column_comment(
        self, table_name: str, col_name: str, content: str
    ) -> Optional[str]:
        """Extract COMMENT ON COLUMN from content.

        Args:
            table_name: Table name
            col_name: Column name
            content: Full SQL content

        Returns:
            Comment string or None
        """
        match = re.search(
            rf"COMMENT\s+ON\s+COLUMN\s+[`\"\[]?{table_name}[`\"\]]?\."
            rf"[`\"\[]?{col_name}[`\"\]]?\s+IS\s+['\"]([^'\"]+)['\"]",
            content,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
        return None