"""PowerDesigner PDM file parser.

PowerDesigner Physical Data Model (.pdm) files are XML format containing
table definitions, columns, relationships, and other schema metadata.
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from .base_parser import BaseSchemaParser, ParsedSchema, ParsedTable

logger = logging.getLogger(__name__)


class PDMParser(BaseSchemaParser):
    """Parse PowerDesigner Physical Data Model (.pdm) files."""

    # Common PDM namespace patterns (varies by version)
    NS_MAP = {
        "o": "http://www.powerdesigner.com",
        "c": "http://www.powerdesigner.com/collection",
        "a": "http://www.powerdesigner.com/attribute",
    }

    @classmethod
    def supported_extensions(cls) -> List[str]:
        return [".pdm", ".xml"]

    @classmethod
    def parser_name(cls) -> str:
        return "pdm"

    def parse(self, file_path: str) -> ParsedSchema:
        """Parse PDM file and extract table definitions.

        Args:
            file_path: Path to the PDM file

        Returns:
            ParsedSchema with tables, views, and references
        """
        self.validate_file(file_path)

        tree = ET.parse(file_path)
        root = tree.getroot()

        tables = []
        views = []
        references = []

        # Register namespaces if present
        namespaces = self._detect_namespaces(root)

        # Find all Table elements
        for table_elem in self._find_elements(root, "Table", namespaces):
            try:
                table = self._parse_table(table_elem, namespaces)
                if table:
                    tables.append(table)
            except Exception as e:
                logger.warning(f"Failed to parse table element: {e}")

        # Find all View elements
        for view_elem in self._find_elements(root, "View", namespaces):
            try:
                view = self._parse_table(view_elem, namespaces, is_view=True)
                if view:
                    views.append(view)
            except Exception as e:
                logger.warning(f"Failed to parse view element: {e}")

        # Find all Reference elements (foreign key relationships)
        for ref_elem in self._find_elements(root, "Reference", namespaces):
            try:
                ref = self._parse_reference(ref_elem, namespaces)
                if ref:
                    references.append(ref)
            except Exception as e:
                logger.warning(f"Failed to parse reference element: {e}")

        logger.info(
            f"Parsed PDM file: {file_path}, tables={len(tables)}, "
            f"views={len(views)}, refs={len(references)}"
        )

        return ParsedSchema(
            tables=tables,
            views=views,
            references=references,
            source_file=file_path,
            source_type="pdm",
        )

    def _detect_namespaces(self, root: ET.Element) -> Dict[str, str]:
        """Detect XML namespaces from root element.

        Args:
            root: XML root element

        Returns:
            Dictionary of namespace prefixes to URIs
        """
        namespaces = {}
        # Check for namespace declarations
        if hasattr(root, "attrib"):
            for key, value in root.attrib.items():
                if key.startswith("xmlns"):
                    if ":" in key:
                        prefix = key.split(":")[1]
                        namespaces[prefix] = value
                    else:
                        namespaces["default"] = value
        return namespaces

    def _find_elements(
        self,
        root: ET.Element,
        tag: str,
        namespaces: Dict[str, str],
    ) -> List[ET.Element]:
        """Find elements by tag name, handling namespace variations.

        Args:
            root: XML root element
            tag: Tag name to find
            namespaces: Namespace dictionary

        Returns:
            List of matching elements
        """
        # Try direct tag name
        elements = list(root.iter(tag))

        # Try with common namespace prefixes
        for prefix in ["o", "c", "a"]:
            ns_tag = f"{prefix}:{tag}"
            elements.extend(list(root.iter(ns_tag)))

        # Try full namespace path
        for ns_uri in namespaces.values():
            if ns_uri:
                ns_tag = f"{{{ns_uri}}}{tag}"
                elements.extend(list(root.iter(ns_tag)))

        return elements

    def _parse_table(
        self,
        elem: ET.Element,
        namespaces: Dict[str, str],
        is_view: bool = False,
    ) -> Optional[ParsedTable]:
        """Parse a Table/View element.

        Args:
            elem: Table or View XML element
            namespaces: Namespace dictionary
            is_view: Whether this is a view

        Returns:
            ParsedTable or None
        """
        # PDM attributes: Name, Code, Comment
        table_name = self._get_attr(elem, "Code") or self._get_attr(elem, "Name")
        if not table_name:
            return None

        table_comment = self._get_attr(elem, "Comment") or ""

        columns = []
        pk_columns = set()

        # Parse Columns
        for col_elem in self._find_elements(elem, "Column", namespaces):
            col = self._parse_column(col_elem, namespaces)
            if col:
                columns.append(col)
                if col.get("pk"):
                    pk_columns.add(col["name"])

        # Parse Keys (primary/unique)
        indexes = []
        for key_elem in self._find_elements(elem, "Key", namespaces):
            idx = self._parse_key(key_elem, namespaces)
            if idx:
                indexes.append(idx)
                # Mark columns as PK if they're in the primary key
                if idx.get("primary"):
                    for col_name in idx.get("columns", []):
                        pk_columns.add(col_name)

        # Update column pk status
        for col in columns:
            if col["name"] in pk_columns:
                col["pk"] = True

        # Parse Foreign Keys within table
        foreign_keys = []
        for fk_elem in self._find_elements(elem, "ForeignKey", namespaces):
            fk = self._parse_fk_in_table(fk_elem, namespaces)
            if fk:
                foreign_keys.append(fk)

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

    def _parse_column(
        self, elem: ET.Element, namespaces: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Parse a Column element.

        Args:
            elem: Column XML element
            namespaces: Namespace dictionary

        Returns:
            Column definition dict or None
        """
        col_name = self._get_attr(elem, "Code") or self._get_attr(elem, "Name")
        if not col_name:
            return None

        # Column attributes
        col_type = self._get_attr(elem, "DataType") or self._get_attr(elem, "Type")
        if not col_type:
            # Try to infer from other attributes
            length = self._get_attr(elem, "Length")
            precision = self._get_attr(elem, "Precision")
            scale = self._get_attr(elem, "Scale")
            if length:
                col_type = f"VARCHAR({length})"
            else:
                col_type = "VARCHAR(255)"

        col_comment = self._get_attr(elem, "Comment") or ""
        mandatory = self._get_attr(elem, "Mandatory")
        nullable = mandatory.lower() != "true" if mandatory else True
        default = self._get_attr(elem, "DefaultValue") or None

        # Check if column is part of primary key
        is_pk = False
        pk_attr = self._get_attr(elem, "Primary")
        if pk_attr and pk_attr.lower() == "true":
            is_pk = True

        return {
            "name": col_name,
            "type": col_type,
            "nullable": nullable,
            "default": default,
            "comment": col_comment,
            "pk": is_pk,
        }

    def _parse_key(
        self, elem: ET.Element, namespaces: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Parse a Key element (index/constraint).

        Args:
            elem: Key XML element
            namespaces: Namespace dictionary

        Returns:
            Key definition dict or None
        """
        key_name = self._get_attr(elem, "Code") or self._get_attr(elem, "Name")
        if not key_name:
            return None

        # Check if it's a primary key
        is_primary = False
        primary_attr = self._get_attr(elem, "Primary")
        if primary_attr and primary_attr.lower() == "true":
            is_primary = True

        # Check uniqueness
        cluster_attr = self._get_attr(elem, "Cluster")
        is_unique = cluster_attr.lower() != "true" if cluster_attr else True

        # Find columns in the key
        columns = []
        for col_ref in self._find_elements(elem, "Column", namespaces):
            col_name = self._get_attr(col_ref, "Code") or self._get_attr(col_ref, "Ref")
            if col_name:
                columns.append(col_name)

        # Also check for Column.Ref elements
        for ref_elem in elem.iter():
            if "Ref" in ref_elem.tag:
                ref_val = ref_elem.text or self._get_attr(ref_elem, "Ref")
                if ref_val:
                    columns.append(ref_val)

        return {
            "name": key_name,
            "columns": columns,
            "unique": is_unique,
            "primary": is_primary,
        }

    def _parse_fk_in_table(
        self, elem: ET.Element, namespaces: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Parse a ForeignKey element within a table.

        Args:
            elem: ForeignKey XML element
            namespaces: Namespace dictionary

        Returns:
            Foreign key definition dict or None
        """
        fk_name = self._get_attr(elem, "Code") or self._get_attr(elem, "Name")

        # Find referenced table
        ref_table = None
        for ref_elem in self._find_elements(elem, "ParentTable", namespaces):
            ref_table = self._get_attr(ref_elem, "Code") or self._get_attr(ref_elem, "Ref")

        # Find constrained columns (child columns)
        constrained_columns = []
        referred_columns = []

        for join_elem in self._find_elements(elem, "Join", namespaces):
            child_col = self._get_attr(join_elem, "ChildColumn")
            parent_col = self._get_attr(join_elem, "ParentColumn")
            if child_col:
                constrained_columns.append(child_col)
            if parent_col:
                referred_columns.append(parent_col)

        if not ref_table:
            return None

        return {
            "name": fk_name or "",
            "constrained_columns": constrained_columns,
            "referred_table": ref_table,
            "referred_columns": referred_columns,
        }

    def _parse_reference(
        self, elem: ET.Element, namespaces: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Parse a Reference element (relationship between tables).

        Args:
            elem: Reference XML element
            namespaces: Namespace dictionary

        Returns:
            Reference definition dict or None
        """
        ref_name = self._get_attr(elem, "Code") or self._get_attr(elem, "Name")

        # Find parent and child tables
        parent_table = None
        child_table = None

        for pt_elem in self._find_elements(elem, "ParentTable", namespaces):
            parent_table = self._get_attr(pt_elem, "Code") or self._get_attr(pt_elem, "Ref")

        for ct_elem in self._find_elements(elem, "ChildTable", namespaces):
            child_table = self._get_attr(ct_elem, "Code") or self._get_attr(ct_elem, "Ref")

        # Find join columns
        constrained_columns = []
        referred_columns = []

        for join_elem in self._find_elements(elem, "Join", namespaces):
            # ChildColumn/ParentColumn or Object2/Object1
            child_col = self._get_attr(join_elem, "ChildColumn") or self._get_attr(
                join_elem, "Object2"
            )
            parent_col = self._get_attr(join_elem, "ParentColumn") or self._get_attr(
                join_elem, "Object1"
            )
            if child_col:
                constrained_columns.append(child_col)
            if parent_col:
                referred_columns.append(parent_col)

        if not parent_table or not child_table:
            return None

        return {
            "name": ref_name or "",
            "from_table": child_table,
            "to_table": parent_table,
            "constrained_columns": constrained_columns,
            "referred_columns": referred_columns,
            "type": "foreign_key",
        }

    def _get_attr(self, elem: ET.Element, attr_name: str) -> Optional[str]:
        """Get attribute value from element, handling variations.

        Args:
            elem: XML element
            attr_name: Attribute name

        Returns:
            Attribute value or None
        """
        # Try direct attribute
        value = elem.get(attr_name)
        if value:
            return value

        # Try with namespace prefix
        for prefix in ["a", "o"]:
            ns_attr = f"{prefix}:{attr_name}"
            value = elem.get(ns_attr)
            if value:
                return value

        # Try child element with the attribute name
        for child in elem:
            tag_name = child.tag.split(":")[-1] if ":" in child.tag else child.tag
            if tag_name == attr_name:
                return child.text

        return None