"""
VIS Protocol V2 - Schema-First Design

This module provides a unified schema definition for VIS components,
ensuring type safety and consistency between frontend and backend.
"""

from .core import (
    VisComponentSchema,
    VisPropertyType,
    VisSlotDefinition,
    VisEventDefinition,
    SchemaRegistry,
    get_schema_registry,
)
from .components import register_all_schemas
from .validator import VisValidator, ValidationResult

__all__ = [
    "VisComponentSchema",
    "VisPropertyType",
    "VisSlotDefinition",
    "VisEventDefinition",
    "SchemaRegistry",
    "get_schema_registry",
    "register_all_schemas",
    "VisValidator",
    "ValidationResult",
]