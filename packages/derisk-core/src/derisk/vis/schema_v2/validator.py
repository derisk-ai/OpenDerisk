"""
VIS Protocol V2 - Schema Validator

Provides runtime validation for VIS component data.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

from .core import (
    VisComponentSchema,
    VisPropertyDefinition,
    VisPropertyType,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class VisValidator:
    """Validator for VIS component data against schemas."""
    
    @staticmethod
    def validate(
        data: Dict[str, Any],
        schema: VisComponentSchema
    ) -> ValidationResult:
        """
        Validate data against a component schema.
        
        Args:
            data: The data to validate
            schema: The schema to validate against
            
        Returns:
            ValidationResult with valid status and any errors/warnings
        """
        errors: List[str] = []
        warnings: List[str] = []
        
        VisValidator._validate_properties(data, schema, errors, warnings)
        VisValidator._validate_slots(data, schema, warnings)
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    @staticmethod
    def _validate_properties(
        data: Dict[str, Any],
        schema: VisComponentSchema,
        errors: List[str],
        warnings: List[str]
    ) -> None:
        """Validate all properties."""
        required_props = schema.get_required_properties()
        
        for prop_name, prop_def in schema.properties.items():
            value = data.get(prop_name)
            
            if prop_name in required_props and value is None:
                errors.append(f"Required property '{prop_name}' is missing")
                continue
            
            if value is not None:
                prop_errors = VisValidator._validate_property_value(
                    prop_name, value, prop_def
                )
                errors.extend(prop_errors)
        
        unknown_props = set(data.keys()) - set(schema.properties.keys())
        if unknown_props:
            for prop in unknown_props:
                if not prop.startswith('_'):
                    warnings.append(f"Unknown property '{prop}'")
    
    @staticmethod
    def _validate_property_value(
        prop_name: str,
        value: Any,
        prop_def: VisPropertyDefinition
    ) -> List[str]:
        """Validate a single property value."""
        errors = []
        
        if value is None:
            if prop_def.required:
                errors.append(f"Property '{prop_name}' cannot be null")
            return errors
        
        type_validators = {
            VisPropertyType.STRING: VisValidator._validate_string,
            VisPropertyType.INTEGER: VisValidator._validate_integer,
            VisPropertyType.NUMBER: VisValidator._validate_number,
            VisPropertyType.BOOLEAN: VisValidator._validate_boolean,
            VisPropertyType.ENUM: VisValidator._validate_enum,
            VisPropertyType.ARRAY: VisValidator._validate_array,
            VisPropertyType.OBJECT: VisValidator._validate_object,
            VisPropertyType.URI: VisValidator._validate_uri,
            VisPropertyType.MARKDOWN: VisValidator._validate_markdown,
            VisPropertyType.TIMESTAMP: VisValidator._validate_timestamp,
            VisPropertyType.INCREMENTAL_STRING: VisValidator._validate_string,
            VisPropertyType.INCREMENTAL_ARRAY: VisValidator._validate_array,
        }
        
        validator = type_validators.get(prop_def.type)
        if validator:
            prop_errors = validator(prop_name, value, prop_def)
            errors.extend(prop_errors)
        
        return errors
    
    @staticmethod
    def _validate_string(
        prop_name: str,
        value: Any,
        prop_def: VisPropertyDefinition
    ) -> List[str]:
        """Validate string type."""
        errors = []
        
        if not isinstance(value, str):
            errors.append(
                f"Property '{prop_name}' must be a string, got {type(value).__name__}"
            )
            return errors
        
        if prop_def.min_length is not None and len(value) < prop_def.min_length:
            errors.append(
                f"Property '{prop_name}' must be at least {prop_def.min_length} characters"
            )
        
        if prop_def.max_length is not None and len(value) > prop_def.max_length:
            errors.append(
                f"Property '{prop_name}' must be at most {prop_def.max_length} characters"
            )
        
        if prop_def.pattern and not re.match(prop_def.pattern, value):
            errors.append(
                f"Property '{prop_name}' does not match pattern {prop_def.pattern}"
            )
        
        return errors
    
    @staticmethod
    def _validate_integer(
        prop_name: str,
        value: Any,
        prop_def: VisPropertyDefinition
    ) -> List[str]:
        """Validate integer type."""
        errors = []
        
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(
                f"Property '{prop_name}' must be an integer, got {type(value).__name__}"
            )
            return errors
        
        if prop_def.minimum is not None and value < prop_def.minimum:
            errors.append(
                f"Property '{prop_name}' must be >= {prop_def.minimum}"
            )
        
        if prop_def.maximum is not None and value > prop_def.maximum:
            errors.append(
                f"Property '{prop_name}' must be <= {prop_def.maximum}"
            )
        
        return errors
    
    @staticmethod
    def _validate_number(
        prop_name: str,
        value: Any,
        prop_def: VisPropertyDefinition
    ) -> List[str]:
        """Validate number type."""
        errors = []
        
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(
                f"Property '{prop_name}' must be a number, got {type(value).__name__}"
            )
            return errors
        
        if prop_def.minimum is not None and value < prop_def.minimum:
            errors.append(
                f"Property '{prop_name}' must be >= {prop_def.minimum}"
            )
        
        if prop_def.maximum is not None and value > prop_def.maximum:
            errors.append(
                f"Property '{prop_name}' must be <= {prop_def.maximum}"
            )
        
        return errors
    
    @staticmethod
    def _validate_boolean(
        prop_name: str,
        value: Any,
        prop_def: VisPropertyDefinition
    ) -> List[str]:
        """Validate boolean type."""
        if not isinstance(value, bool):
            return [
                f"Property '{prop_name}' must be a boolean, got {type(value).__name__}"
            ]
        return []
    
    @staticmethod
    def _validate_enum(
        prop_name: str,
        value: Any,
        prop_def: VisPropertyDefinition
    ) -> List[str]:
        """Validate enum type."""
        if prop_def.enum_values and value not in prop_def.enum_values:
            return [
                f"Property '{prop_name}' must be one of {prop_def.enum_values}, got '{value}'"
            ]
        return []
    
    @staticmethod
    def _validate_array(
        prop_name: str,
        value: Any,
        prop_def: VisPropertyDefinition
    ) -> List[str]:
        """Validate array type."""
        errors = []
        
        if not isinstance(value, list):
            errors.append(
                f"Property '{prop_name}' must be an array, got {type(value).__name__}"
            )
            return errors
        
        if prop_def.items:
            for i, item in enumerate(value):
                item_errors = VisValidator._validate_property_value(
                    f"{prop_name}[{i}]", item, prop_def.items
                )
                errors.extend(item_errors)
        
        return errors
    
    @staticmethod
    def _validate_object(
        prop_name: str,
        value: Any,
        prop_def: VisPropertyDefinition
    ) -> List[str]:
        """Validate object type."""
        errors = []
        
        if not isinstance(value, dict):
            errors.append(
                f"Property '{prop_name}' must be an object, got {type(value).__name__}"
            )
            return errors
        
        if prop_def.properties:
            for sub_prop_name, sub_prop_def in prop_def.properties.items():
                sub_value = value.get(sub_prop_name)
                if sub_value is not None:
                    sub_errors = VisValidator._validate_property_value(
                        f"{prop_name}.{sub_prop_name}", sub_value, sub_prop_def
                    )
                    errors.extend(sub_errors)
        
        return errors
    
    @staticmethod
    def _validate_uri(
        prop_name: str,
        value: Any,
        prop_def: VisPropertyDefinition
    ) -> List[str]:
        """Validate URI type."""
        errors = VisValidator._validate_string(prop_name, value, prop_def)
        
        if not errors:
            uri_pattern = r'^https?://[^\s/$.?#].[^\s]*$'
            if not re.match(uri_pattern, str(value)):
                errors.append(f"Property '{prop_name}' is not a valid URI")
        
        return errors
    
    @staticmethod
    def _validate_markdown(
        prop_name: str,
        value: Any,
        prop_def: VisPropertyDefinition
    ) -> List[str]:
        """Validate markdown type (same as string for now)."""
        return VisValidator._validate_string(prop_name, value, prop_def)
    
    @staticmethod
    def _validate_timestamp(
        prop_name: str,
        value: Any,
        prop_def: VisPropertyDefinition
    ) -> List[str]:
        """Validate timestamp type."""
        if isinstance(value, str):
            try:
                from datetime import datetime
                datetime.fromisoformat(value.replace('Z', '+00:00'))
                return []
            except ValueError:
                return [f"Property '{prop_name}' is not a valid ISO timestamp"]
        
        return [
            f"Property '{prop_name}' must be an ISO timestamp string, got {type(value).__name__}"
        ]
    
    @staticmethod
    def _validate_slots(
        data: Dict[str, Any],
        schema: VisComponentSchema,
        warnings: List[str]
    ) -> None:
        """Validate slots."""
        slots_data = data.get('_slots', {})
        
        for slot_name, slot_def in schema.slots.items():
            slot_value = slots_data.get(slot_name)
            
            if slot_def.required and slot_value is None:
                warnings.append(f"Required slot '{slot_name}' is empty")
            
            if slot_value is not None:
                if slot_def.type == 'single':
                    if isinstance(slot_value, list) and len(slot_value) > 1:
                        warnings.append(
                            f"Slot '{slot_name}' is single type but has multiple items"
                        )
                elif slot_def.type == 'list':
                    if not isinstance(slot_value, list):
                        warnings.append(
                            f"Slot '{slot_name}' is list type but value is not an array"
                        )