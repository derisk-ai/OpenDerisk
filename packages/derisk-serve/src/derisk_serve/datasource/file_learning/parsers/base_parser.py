"""Base parser for schema definition files."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParsedTable:
    """Parsed table definition from file.

    Attributes:
        table_name: Table name (code/identifier)
        table_comment: Table comment/description
        columns: List of column definitions
        indexes: List of index definitions
        foreign_keys: List of foreign key definitions
        create_ddl: Generated or original CREATE TABLE DDL
    """

    table_name: str
    table_comment: Optional[str] = None
    columns: List[Dict[str, Any]] = field(default_factory=list)
    indexes: List[Dict[str, Any]] = field(default_factory=list)
    foreign_keys: List[Dict[str, Any]] = field(default_factory=list)
    create_ddl: Optional[str] = None


@dataclass
class ParsedSchema:
    """Parsed schema definition from file.

    Attributes:
        tables: List of parsed tables
        views: List of parsed views (treated similarly to tables)
        references: Cross-table references (foreign key relationships)
        source_file: Original file path
        source_type: File type identifier (pdm, ddl, pdman, erwin)
    """

    tables: List[ParsedTable] = field(default_factory=list)
    views: List[ParsedTable] = field(default_factory=list)
    references: List[Dict[str, Any]] = field(default_factory=list)
    source_file: Optional[str] = None
    source_type: Optional[str] = None


class BaseSchemaParser(ABC):
    """Abstract base class for schema file parsers.

    All schema file parsers (PDM, DDL, PDMan, ERWin) should inherit from this
    class and implement the parse() method.
    """

    @classmethod
    @abstractmethod
    def supported_extensions(cls) -> List[str]:
        """Return supported file extensions.

        Returns:
            List of file extensions (e.g., ['.pdm', '.xml'])
        """
        pass

    @classmethod
    @abstractmethod
    def parser_name(cls) -> str:
        """Return parser name for identification.

        Returns:
            Parser name string (e.g., 'pdm', 'ddl')
        """
        pass

    @abstractmethod
    def parse(self, file_path: str) -> ParsedSchema:
        """Parse the schema file and return structured data.

        Args:
            file_path: Path to the schema file

        Returns:
            ParsedSchema with tables, views, and references

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        pass

    def validate_file(self, file_path: str) -> bool:
        """Validate file exists and has correct extension.

        Args:
            file_path: Path to the file

        Returns:
            True if valid

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If extension is not supported
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.supported_extensions():
            raise ValueError(
                f"Unsupported file extension: {ext}. "
                f"Supported: {self.supported_extensions()}"
            )
        return True

    def _generate_ddl(
        self,
        table_name: str,
        columns: List[Dict[str, Any]],
        indexes: List[Dict[str, Any]] = None,
        comment: str = None,
    ) -> str:
        """Generate CREATE TABLE DDL from parsed structure.

        Args:
            table_name: Table name
            columns: Column definitions
            indexes: Index definitions (optional)
            comment: Table comment (optional)

        Returns:
            CREATE TABLE DDL string
        """
        lines = [f"CREATE TABLE {table_name} ("]

        col_defs = []
        pk_columns = []

        for col in columns:
            col_def = f"  {col.get('name', '')} {col.get('type', 'VARCHAR')}"
            if not col.get("nullable", True):
                col_def += " NOT NULL"
            if col.get("default"):
                col_def += f" DEFAULT {col.get('default')}"
            col_defs.append(col_def)
            if col.get("pk"):
                pk_columns.append(col.get("name"))

        lines.append(",\n".join(col_defs))

        # Add PRIMARY KEY constraint
        if pk_columns:
            lines.append(f",  PRIMARY KEY ({', '.join(pk_columns)})")

        lines.append(");")

        if comment:
            lines.append(f"COMMENT ON TABLE {table_name} IS '{comment}';")

        return "\n".join(lines)