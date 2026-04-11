"""File-based schema learning module.

This module provides functionality to learn database schema from design files
(PowerDesigner PDM, DDL SQL, PDMan JSON, ERWin) and link to existing datasources
for sample data collection.
"""

from .parsers import (
    BaseSchemaParser,
    ParsedSchema,
    ParsedTable,
    get_parser_for_file,
    get_supported_types,
)
from .service import FileLearningService

__all__ = [
    "BaseSchemaParser",
    "ParsedSchema",
    "ParsedTable",
    "FileLearningService",
    "get_parser_for_file",
    "get_supported_types",
]