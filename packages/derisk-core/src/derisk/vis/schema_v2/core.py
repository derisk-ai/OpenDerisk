"""
VIS Protocol V2 - Core Schema Definitions

Provides the foundation for Schema-First development approach.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from derisk._private.pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class VisPropertyType(str, Enum):
    """Property types for VIS component schemas."""
    
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    ENUM = "enum"
    URI = "uri"
    MARKDOWN = "markdown"
    TIMESTAMP = "timestamp"
    
    # Incremental types
    INCREMENTAL_STRING = "incremental_string"
    INCREMENTAL_ARRAY = "incremental_array"


class IncrementalStrategy(str, Enum):
    """Strategies for incremental updates."""
    
    APPEND = "append"
    PREPEND = "prepend"
    REPLACE = "replace"
    MERGE = "merge"
    PATCH = "patch"


@dataclass
class VisPropertyDefinition:
    """Definition of a component property."""
    
    type: VisPropertyType
    description: str = ""
    required: bool = False
    default: Any = None
    
    # For enum type
    enum_values: Optional[List[str]] = None
    
    # For incremental types
    incremental: Optional[IncrementalStrategy] = None
    
    # Validation
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    pattern: Optional[str] = None
    
    # For array/object types
    items: Optional["VisPropertyDefinition"] = None
    properties: Optional[Dict[str, "VisPropertyDefinition"]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.type.value,
            "description": self.description,
            "required": self.required,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.enum_values:
            result["enum_values"] = self.enum_values
        if self.incremental:
            result["incremental"] = self.incremental.value
        if self.min_length is not None:
            result["min_length"] = self.min_length
        if self.max_length is not None:
            result["max_length"] = self.max_length
        if self.minimum is not None:
            result["minimum"] = self.minimum
        if self.maximum is not None:
            result["maximum"] = self.maximum
        if self.pattern:
            result["pattern"] = self.pattern
        if self.items:
            result["items"] = self.items.to_dict()
        if self.properties:
            result["properties"] = {k: v.to_dict() for k, v in self.properties.items()}
        return result


@dataclass
class VisSlotDefinition:
    """Definition of a component slot for composition."""
    
    name: str
    description: str = ""
    type: str = "single"
    required: bool = False
    default_items: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "required": self.required,
        }
        if self.default_items:
            result["default_items"] = self.default_items
        return result


@dataclass
class VisEventDefinition:
    """Definition of a component event."""
    
    name: str
    description: str = ""
    action: str = "emit"
    payload_schema: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "description": self.description,
            "action": self.action,
        }
        if self.payload_schema:
            result["payload_schema"] = self.payload_schema
        return result


class VisComponentSchema(BaseModel):
    """
    Schema definition for a VIS component.
    
    This is the single source of truth for component structure,
    used to generate types, validators, and documentation.
    """
    
    tag: str = Field(..., description="Component tag name (e.g., 'vis-thinking')")
    version: str = Field(default="1.0.0", description="Schema version")
    description: str = Field(default="", description="Component description")
    category: str = Field(default="general", description="Component category")
    
    properties: Dict[str, VisPropertyDefinition] = Field(
        default_factory=dict,
        description="Component properties"
    )
    
    slots: Dict[str, VisSlotDefinition] = Field(
        default_factory=dict,
        description="Component slots for composition"
    )
    
    events: Dict[str, VisEventDefinition] = Field(
        default_factory=dict,
        description="Component events"
    )
    
    examples: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Usage examples"
    )
    
    def get_required_properties(self) -> Set[str]:
        """Get set of required property names."""
        return {name for name, prop in self.properties.items() if prop.required}
    
    def get_incremental_properties(self) -> Dict[str, IncrementalStrategy]:
        """Get properties that support incremental updates."""
        return {
            name: prop.incremental
            for name, prop in self.properties.items()
            if prop.incremental is not None
        }
    
    def validate_data(self, data: Dict[str, Any]) -> "ValidationResult":
        """Validate data against this schema."""
        from .validator import VisValidator
        return VisValidator.validate(data, self)
    
    def to_typescript_interface(self) -> str:
        """Generate TypeScript interface definition."""
        lines = [
            f"/** {self.description} */",
            f"export interface {self._tag_to_class_name()}Props {{",
        ]
        
        for prop_name, prop_def in self.properties.items():
            ts_type = self._property_to_typescript(prop_def)
            optional = "" if prop_def.required else "?"
            lines.append(f"  /** {prop_def.description} */")
            lines.append(f"  {prop_name}{optional}: {ts_type};")
        
        lines.append("}")
        
        return "\n".join(lines)
    
    def to_pydantic_model(self) -> Type[BaseModel]:
        """Generate Pydantic model class dynamically."""
        from pydantic import create_model
        
        fields = {}
        for prop_name, prop_def in self.properties.items():
            field_type = self._property_to_python_type(prop_def)
            if prop_def.required:
                fields[prop_name] = (field_type, Field(..., description=prop_def.description))
            else:
                fields[prop_name] = (Optional[field_type], Field(default=None, description=prop_def.description))
        
        return create_model(
            f"{self._tag_to_class_name()}Content",
            __base__=BaseModel,
            **fields
        )
    
    def _tag_to_class_name(self) -> str:
        """Convert tag name to class name."""
        parts = self.tag.replace("-", "_").split("_")
        return "".join(p.capitalize() for p in parts)
    
    def _property_to_typescript(self, prop_def: VisPropertyDefinition) -> str:
        """Convert property definition to TypeScript type."""
        type_map = {
            VisPropertyType.STRING: "string",
            VisPropertyType.INTEGER: "number",
            VisPropertyType.NUMBER: "number",
            VisPropertyType.BOOLEAN: "boolean",
            VisPropertyType.URI: "string",
            VisPropertyType.MARKDOWN: "string",
            VisPropertyType.TIMESTAMP: "string | Date",
            VisPropertyType.INCREMENTAL_STRING: "string",
        }
        
        if prop_def.type in type_map:
            return type_map[prop_def.type]
        
        if prop_def.type == VisPropertyType.ENUM:
            if prop_def.enum_values:
                values = " | ".join(f"'{v}'" for v in prop_def.enum_values)
                return values
            return "string"
        
        if prop_def.type == VisPropertyType.ARRAY:
            if prop_def.items:
                item_type = self._property_to_typescript(prop_def.items)
                return f"{item_type}[]"
            return "any[]"
        
        if prop_def.type == VisPropertyType.OBJECT:
            return "Record<string, any>"
        
        if prop_def.type == VisPropertyType.INCREMENTAL_ARRAY:
            if prop_def.items:
                item_type = self._property_to_typescript(prop_def.items)
                return f"{item_type}[]"
            return "any[]"
        
        return "any"
    
    def _property_to_python_type(self, prop_def: VisPropertyDefinition) -> type:
        """Convert property definition to Python type."""
        type_map = {
            VisPropertyType.STRING: str,
            VisPropertyType.INTEGER: int,
            VisPropertyType.NUMBER: float,
            VisPropertyType.BOOLEAN: bool,
            VisPropertyType.URI: str,
            VisPropertyType.MARKDOWN: str,
            VisPropertyType.TIMESTAMP: str,
            VisPropertyType.INCREMENTAL_STRING: str,
        }
        
        if prop_def.type in type_map:
            return type_map[prop_def.type]
        
        if prop_def.type == VisPropertyType.ENUM:
            return str
        
        if prop_def.type in (VisPropertyType.ARRAY, VisPropertyType.INCREMENTAL_ARRAY):
            return List[Any]
        
        if prop_def.type == VisPropertyType.OBJECT:
            return Dict[str, Any]
        
        return Any


class ValidationResult(BaseModel):
    """Result of schema validation."""
    
    valid: bool = Field(..., description="Whether validation passed")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    
    def __bool__(self) -> bool:
        return self.valid


class SchemaRegistry:
    """
    Global registry for VIS component schemas.
    
    This is the central place for schema registration and lookup.
    """
    
    _instance: Optional["SchemaRegistry"] = None
    
    def __init__(self):
        self._schemas: Dict[str, VisComponentSchema] = {}
        self._categories: Dict[str, Set[str]] = {}
    
    @classmethod
    def get_instance(cls) -> "SchemaRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register(self, schema: VisComponentSchema) -> None:
        """Register a component schema."""
        if schema.tag in self._schemas:
            logger.warning(f"Overwriting existing schema for tag: {schema.tag}")
        
        self._schemas[schema.tag] = schema
        
        if schema.category not in self._categories:
            self._categories[schema.category] = set()
        self._categories[schema.category].add(schema.tag)
        
        logger.debug(f"Registered schema: {schema.tag}")
    
    def get(self, tag: str) -> Optional[VisComponentSchema]:
        """Get schema by tag name."""
        return self._schemas.get(tag)
    
    def list_all(self) -> Dict[str, VisComponentSchema]:
        """Get all registered schemas."""
        return self._schemas.copy()
    
    def list_by_category(self, category: str) -> Dict[str, VisComponentSchema]:
        """Get schemas by category."""
        tags = self._categories.get(category, set())
        return {tag: self._schemas[tag] for tag in tags if tag in self._schemas}
    
    def get_categories(self) -> Set[str]:
        """Get all categories."""
        return set(self._categories.keys())
    
    def generate_typescript_types(self) -> str:
        """Generate TypeScript type definitions for all schemas."""
        lines = [
            "/**",
            " * VIS Component Types (Auto-generated)",
            " * Do not edit manually - regenerate from schema",
            " */",
            "",
        ]
        
        for schema in self._schemas.values():
            lines.append(schema.to_typescript_interface())
            lines.append("")
        
        return "\n".join(lines)


def get_schema_registry() -> SchemaRegistry:
    """Get the global schema registry."""
    return SchemaRegistry.get_instance()