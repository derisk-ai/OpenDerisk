"""PDMan JSON file parser.

PDMan is a Chinese database design tool that exports schema in JSON format.
This parser extracts table definitions from PDMan JSON files.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .base_parser import BaseSchemaParser, ParsedSchema, ParsedTable

logger = logging.getLogger(__name__)


class PDManParser(BaseSchemaParser):
    """Parse PDMan JSON schema files."""

    @classmethod
    def supported_extensions(cls) -> List[str]:
        return [".json", ".pdman"]

    @classmethod
    def parser_name(cls) -> str:
        return "pdman"

    def parse(self, file_path: str) -> ParsedSchema:
        """Parse PDMan JSON file.

        Args:
            file_path: Path to the PDMan JSON file

        Returns:
            ParsedSchema with tables and views
        """
        self.validate_file(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tables = []
        views = []
        references = []

        # PDMan structure varies by version
        # Common patterns: modules[].entities, tables, entities

        # Try different structure patterns
        entities = self._find_entities(data)

        for entity in entities:
            try:
                table = self._parse_entity(entity)
                if table:
                    tables.append(table)
            except Exception as e:
                logger.warning(f"Failed to parse entity: {e}")

        # Find relationships
        relationships = self._find_relationships(data)
        for rel in relationships:
            try:
                ref = self._parse_relationship(rel)
                if ref:
                    references.append(ref)
            except Exception as e:
                logger.warning(f"Failed to parse relationship: {e}")

        logger.info(
            f"Parsed PDMan file: {file_path}, "
            f"tables={len(tables)}, refs={len(references)}"
        )

        return ParsedSchema(
            tables=tables,
            views=views,
            references=references,
            source_file=file_path,
            source_type="pdman",
        )

    def _find_entities(self, data: Dict) -> List[Dict]:
        """Find entity/table definitions in PDMan data.

        Args:
            data: PDMan JSON data

        Returns:
            List of entity dicts
        """
        entities = []

        # Pattern 1: direct tables/entities array
        if "tables" in data:
            entities.extend(data["tables"])
        if "entities" in data:
            entities.extend(data["entities"])

        # Pattern 2: modules[].entities (PDMan 2.x)
        if "modules" in data:
            for module in data["modules"]:
                if "entities" in module:
                    entities.extend(module["entities"])
                if "graphs" in module:
                    # Some versions use graphs
                    for graph in module["graphs"]:
                        if "entities" in graph:
                            entities.extend(graph["entities"])

        # Pattern 3: project.entities
        if "project" in data and "entities" in data["project"]:
            entities.extend(data["project"]["entities"])

        return entities

    def _find_relationships(self, data: Dict) -> List[Dict]:
        """Find relationship definitions in PDMan data.

        Args:
            data: PDMan JSON data

        Returns:
            List of relationship dicts
        """
        relationships = []

        # Check various locations
        if "relationships" in data:
            relationships.extend(data["relationships"])

        if "modules" in data:
            for module in data["modules"]:
                if "relationships" in module:
                    relationships.extend(module["relationships"])

        # Some versions use 'links' or 'refs'
        if "links" in data:
            relationships.extend(data["links"])
        if "refs" in data:
            relationships.extend(data["refs"])

        return relationships

    def _parse_entity(self, entity: Dict) -> Optional[ParsedTable]:
        """Parse a PDMan entity/table definition.

        Args:
            entity: Entity dict from PDMan

        Returns:
            ParsedTable or None
        """
        # Get table name (various field names)
        table_name = (
            entity.get("name")
            or entity.get("title")
            or entity.get("tableName")
            or entity.get("code")
        )
        if not table_name:
            return None

        # Get table comment
        table_comment = (
            entity.get("comment")
            or entity.get("description")
            or entity.get("title")
            or entity.get("remark")
            or ""
        )

        # Parse columns/fields
        columns = []
        fields = (
            entity.get("fields")
            or entity.get("columns")
            or entity.get("properties")
            or entity.get("attrs")
            or []
        )

        pk_columns = set()

        for field in fields:
            col = self._parse_field(field)
            if col:
                columns.append(col)
                if col.get("pk"):
                    pk_columns.add(col["name"])

        # Check for explicit primary key definition
        if "primaryKey" in entity:
            pk_def = entity["primaryKey"]
            if isinstance(pk_def, list):
                pk_columns.update(pk_def)
            elif isinstance(pk_def, str):
                pk_columns.add(pk_def)
            elif isinstance(pk_def, dict):
                pk_cols = pk_def.get("columns") or pk_def.get("fields") or []
                pk_columns.update(pk_cols)

        # Update pk status
        for col in columns:
            if col["name"] in pk_columns:
                col["pk"] = True

        # Parse indexes
        indexes = []
        idx_list = entity.get("indexes") or entity.get("index") or []
        for idx in idx_list:
            index = self._parse_index(idx)
            if index:
                indexes.append(index)

        # Parse foreign keys
        foreign_keys = []
        fk_list = entity.get("foreignKeys") or entity.get("relations") or []
        for fk in fk_list:
            fk_def = self._parse_fk(fk)
            if fk_def:
                foreign_keys.append(fk_def)

        # Generate CREATE DDL
        create_ddl = self._generate_ddl(table_name, columns, indexes, table_comment)

        return ParsedTable(
            table_name=table_name,
            table_comment=table_comment,
            columns=columns,
            indexes=indexes,
            foreign_keys=foreign_keys,
            create_ddl=create_ddl,
        )

    def _parse_field(self, field: Dict) -> Optional[Dict[str, Any]]:
        """Parse a PDMan field/column definition.

        Args:
            field: Field dict from PDMan

        Returns:
            Column dict or None
        """
        # Get field name (various field names)
        name = (
            field.get("name")
            or field.get("code")
            or field.get("fieldName")
            or field.get("title")
        )
        if not name:
            return None

        # Get data type
        type_info = field.get("type") or field.get("dataType") or field.get("typeName")
        if isinstance(type_info, dict):
            # Some versions use nested type object
            col_type = type_info.get("name") or type_info.get("type") or "VARCHAR"
            length = type_info.get("len") or type_info.get("length")
            if length:
                col_type = f"{col_type}({length})"
        elif isinstance(type_info, str):
            col_type = type_info.upper()
        else:
            col_type = "VARCHAR"

        # Handle type with length directly
        if field.get("len") or field.get("length"):
            length = field.get("len") or field.get("length")
            if not "(" in col_type:
                col_type = f"{col_type}({length})"

        # Get nullable
        nullable = field.get("nullable", True)
        if isinstance(nullable, str):
            nullable = nullable.lower() != "false"

        # Get default
        default = field.get("defaultValue") or field.get("default") or None

        # Get comment
        comment = (
            field.get("comment")
            or field.get("description")
            or field.get("remark")
            or ""
        )

        # Check if primary key
        is_pk = field.get("primaryKey") or field.get("pk") or field.get("isPrimaryKey")
        if isinstance(is_pk, str):
            is_pk = is_pk.lower() == "true"

        return {
            "name": name,
            "type": col_type,
            "nullable": nullable,
            "default": default,
            "comment": comment,
            "pk": bool(is_pk),
        }

    def _parse_index(self, idx: Dict) -> Optional[Dict[str, Any]]:
        """Parse an index definition.

        Args:
            idx: Index dict

        Returns:
            Index dict or None
        """
        name = idx.get("name") or idx.get("indexName") or ""

        columns = idx.get("columns") or idx.get("fields") or idx.get("columnList") or []
        if isinstance(columns, str):
            columns = [c.strip() for c in columns.split(",")]

        is_unique = idx.get("unique") or idx.get("isUnique") or False
        if isinstance(is_unique, str):
            is_unique = is_unique.lower() == "true"

        return {
            "name": name,
            "columns": columns,
            "unique": is_unique,
        }

    def _parse_fk(self, fk: Dict) -> Optional[Dict[str, Any]]:
        """Parse a foreign key definition.

        Args:
            fk: FK dict

        Returns:
            FK dict or None
        """
        referred_table = (
            fk.get("refTable")
            or fk.get("target")
            or fk.get("targetTable")
            or fk.get("referenceTable")
        )
        if not referred_table:
            return None

        constrained_columns = (
            fk.get("columns")
            or fk.get("fields")
            or fk.get("srcColumns")
            or []
        )
        referred_columns = (
            fk.get("refColumns")
            or fk.get("targetColumns")
            or fk.get("referenceColumns")
            or []
        )

        if isinstance(constrained_columns, str):
            constrained_columns = [c.strip() for c in constrained_columns.split(",")]
        if isinstance(referred_columns, str):
            referred_columns = [c.strip() for c in referred_columns.split(",")]

        return {
            "constrained_columns": constrained_columns,
            "referred_table": referred_table,
            "referred_columns": referred_columns,
        }

    def _parse_relationship(self, rel: Dict) -> Optional[Dict[str, Any]]:
        """Parse a relationship definition.

        Args:
            rel: Relationship dict

        Returns:
            Reference dict or None
        """
        from_entity = (
            rel.get("from")
            or rel.get("source")
            or rel.get("fromEntity")
            or rel.get("srcEntity")
        )
        to_entity = (
            rel.get("to")
            or rel.get("target")
            or rel.get("toEntity")
            or rel.get("targetEntity")
        )

        if not from_entity or not to_entity:
            return None

        # Extract column references if available
        constrained_columns = rel.get("fromColumns") or rel.get("srcColumns") or []
        referred_columns = rel.get("toColumns") or rel.get("targetColumns") or []

        return {
            "from_table": from_entity,
            "to_table": to_entity,
            "constrained_columns": constrained_columns,
            "referred_columns": referred_columns,
            "type": "foreign_key",
        }