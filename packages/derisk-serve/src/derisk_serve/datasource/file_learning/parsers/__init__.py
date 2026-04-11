"""Schema file parsers registry and factory."""

from typing import Any, Dict, List, Optional, Type

from .base_parser import BaseSchemaParser, ParsedSchema, ParsedTable
from .ddl_parser import DDLParser
from .pdman_parser import PDManParser
from .pdm_parser import PDMParser

# Parser registry - maps file type to parser class
PARSER_REGISTRY: Dict[str, Type[BaseSchemaParser]] = {
    "pdm": PDMParser,
    "ddl": DDLParser,
    "pdman": PDManParser,
    # "erwin": ERWinParser,  # To be added
}

# Extension to file type mapping
EXTENSION_TYPE_MAP = {
    ".pdm": "pdm",
    ".xml": "pdm",  # Assume XML files are PDM if not specified
    ".sql": "ddl",
    ".ddl": "ddl",
    ".json": "pdman",
    ".pdman": "pdman",
}


def get_parser_for_file(file_type: str) -> Optional[BaseSchemaParser]:
    """Get appropriate parser instance for file type.

    Args:
        file_type: File type identifier (pdm, ddl, pdman, erwin)

    Returns:
        Parser instance or None if not supported
    """
    parser_cls = PARSER_REGISTRY.get(file_type)
    if parser_cls:
        return parser_cls()
    return None


def get_parser_for_extension(extension: str) -> Optional[BaseSchemaParser]:
    """Get parser for file extension.

    Args:
        extension: File extension (e.g., '.pdm')

    Returns:
        Parser instance or None
    """
    file_type = EXTENSION_TYPE_MAP.get(extension.lower())
    if file_type:
        return get_parser_for_file(file_type)
    return None


def get_supported_types() -> List[Dict[str, Any]]:
    """Get list of supported file types.

    Returns:
        List of file type info dicts
    """
    from typing import Any

    return [
        {
            "type": name,
            "description": cls.parser_name(),
            "extensions": cls.supported_extensions(),
        }
        for name, cls in PARSER_REGISTRY.items()
    ]


def register_parser(file_type: str, parser_cls: Type[BaseSchemaParser]) -> None:
    """Register a new parser type.

    Args:
        file_type: File type identifier
        parser_cls: Parser class
    """
    PARSER_REGISTRY[file_type] = parser_cls
    for ext in parser_cls.supported_extensions():
        EXTENSION_TYPE_MAP[ext] = file_type


__all__ = [
    "BaseSchemaParser",
    "ParsedSchema",
    "ParsedTable",
    "PDMParser",
    "DDLParser",
    "PDManParser",
    "get_parser_for_file",
    "get_parser_for_extension",
    "get_supported_types",
    "register_parser",
]