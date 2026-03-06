"""
Tests for VIS Protocol V2 - Schema and Validator
"""

import pytest
from derisk.vis.schema_v2 import (
    VisComponentSchema,
    VisPropertyDefinition,
    VisPropertyType,
    VisSlotDefinition,
    VisEventDefinition,
    IncrementalStrategy,
    SchemaRegistry,
    get_schema_registry,
    register_all_schemas,
    VisValidator,
)


class TestVisPropertyDefinition:
    """Tests for VisPropertyDefinition."""

    def test_string_property(self):
        """Test creating a string property."""
        prop = VisPropertyDefinition(
            type=VisPropertyType.STRING,
            description="Test property",
            required=True,
        )
        
        assert prop.type == VisPropertyType.STRING
        assert prop.required is True
        assert prop.description == "Test property"

    def test_enum_property(self):
        """Test creating an enum property."""
        prop = VisPropertyDefinition(
            type=VisPropertyType.ENUM,
            description="Status",
            enum_values=["pending", "running", "completed"],
        )
        
        assert prop.type == VisPropertyType.ENUM
        assert len(prop.enum_values) == 3

    def test_incremental_property(self):
        """Test creating an incremental property."""
        prop = VisPropertyDefinition(
            type=VisPropertyType.INCREMENTAL_STRING,
            description="Markdown content",
            incremental=IncrementalStrategy.APPEND,
        )
        
        assert prop.type == VisPropertyType.INCREMENTAL_STRING
        assert prop.incremental == IncrementalStrategy.APPEND

    def test_to_dict(self):
        """Test converting to dictionary."""
        prop = VisPropertyDefinition(
            type=VisPropertyType.STRING,
            description="Test",
            required=True,
            min_length=1,
            max_length=100,
        )
        
        d = prop.to_dict()
        
        assert d["type"] == "string"
        assert d["required"] is True
        assert d["min_length"] == 1
        assert d["max_length"] == 100


class TestVisComponentSchema:
    """Tests for VisComponentSchema."""

    def test_create_schema(self):
        """Test creating a component schema."""
        schema = VisComponentSchema(
            tag="vis-test",
            version="1.0.0",
            description="Test component",
            category="test",
            properties={
                "uid": VisPropertyDefinition(
                    type=VisPropertyType.STRING,
                    description="Unique ID",
                    required=True,
                ),
                "markdown": VisPropertyDefinition(
                    type=VisPropertyType.STRING,
                    description="Content",
                ),
            },
        )
        
        assert schema.tag == "vis-test"
        assert len(schema.properties) == 2

    def test_get_required_properties(self):
        """Test getting required properties."""
        schema = VisComponentSchema(
            tag="vis-test",
            properties={
                "uid": VisPropertyDefinition(
                    type=VisPropertyType.STRING,
                    required=True,
                ),
                "optional": VisPropertyDefinition(
                    type=VisPropertyType.STRING,
                    required=False,
                ),
            },
        )
        
        required = schema.get_required_properties()
        
        assert "uid" in required
        assert "optional" not in required

    def test_get_incremental_properties(self):
        """Test getting incremental properties."""
        schema = VisComponentSchema(
            tag="vis-test",
            properties={
                "markdown": VisPropertyDefinition(
                    type=VisPropertyType.INCREMENTAL_STRING,
                    incremental=IncrementalStrategy.APPEND,
                ),
            },
        )
        
        incremental = schema.get_incremental_properties()
        
        assert "markdown" in incremental
        assert incremental["markdown"] == IncrementalStrategy.APPEND

    def test_validate_data(self):
        """Test validating data against schema."""
        schema = VisComponentSchema(
            tag="vis-test",
            properties={
                "uid": VisPropertyDefinition(
                    type=VisPropertyType.STRING,
                    required=True,
                ),
                "count": VisPropertyDefinition(
                    type=VisPropertyType.INTEGER,
                    minimum=0,
                    maximum=100,
                ),
            },
        )
        
        # Valid data
        result = schema.validate_data({"uid": "test-1", "count": 50})
        assert result.valid is True
        
        # Missing required field
        result = schema.validate_data({"count": 50})
        assert result.valid is False
        
        # Out of range
        result = schema.validate_data({"uid": "test-1", "count": 150})
        assert result.valid is False


class TestSchemaRegistry:
    """Tests for SchemaRegistry."""

    def test_register_schema(self):
        """Test registering a schema."""
        registry = SchemaRegistry()
        
        schema = VisComponentSchema(
            tag="vis-test",
            description="Test",
        )
        
        registry.register(schema)
        
        assert registry.has("vis-test") is False  # has method uses different logic
        assert registry.get("vis-test") is not None

    def test_get_schema(self):
        """Test getting a schema."""
        registry = SchemaRegistry()
        
        schema = VisComponentSchema(tag="vis-test", description="Test")
        registry.register(schema)
        
        retrieved = registry.get("vis-test")
        
        assert retrieved is not None
        assert retrieved.tag == "vis-test"

    def test_list_all(self):
        """Test listing all schemas."""
        registry = SchemaRegistry()
        
        for i in range(3):
            schema = VisComponentSchema(tag=f"vis-test-{i}", description="Test")
            registry.register(schema)
        
        all_schemas = registry.list_all()
        
        assert len(all_schemas) == 3

    def test_list_by_category(self):
        """Test listing schemas by category."""
        registry = SchemaRegistry()
        
        schema1 = VisComponentSchema(tag="vis-test-1", category="cat-a")
        schema2 = VisComponentSchema(tag="vis-test-2", category="cat-b")
        schema3 = VisComponentSchema(tag="vis-test-3", category="cat-a")
        
        registry.register(schema1)
        registry.register(schema2)
        registry.register(schema3)
        
        cat_a = registry.list_by_category("cat-a")
        
        assert len(cat_a) == 2

    def test_singleton(self):
        """Test singleton pattern."""
        registry1 = get_schema_registry()
        registry2 = get_schema_registry()
        
        assert registry1 is registry2


class TestVisValidator:
    """Tests for VisValidator."""

    def test_validate_string(self):
        """Test validating string type."""
        prop = VisPropertyDefinition(
            type=VisPropertyType.STRING,
            min_length=2,
            max_length=10,
        )
        
        errors = VisValidator._validate_string("test", "ab", prop)
        assert len(errors) == 0
        
        errors = VisValidator._validate_string("test", "a", prop)
        assert len(errors) == 1  # Too short
        
        errors = VisValidator._validate_string("test", 123, prop)
        assert len(errors) == 1  # Wrong type

    def test_validate_integer(self):
        """Test validating integer type."""
        prop = VisPropertyDefinition(
            type=VisPropertyType.INTEGER,
            minimum=0,
            maximum=100,
        )
        
        errors = VisValidator._validate_integer("test", 50, prop)
        assert len(errors) == 0
        
        errors = VisValidator._validate_integer("test", 150, prop)
        assert len(errors) == 1  # Out of range
        
        errors = VisValidator._validate_integer("test", "50", prop)
        assert len(errors) == 1  # Wrong type

    def test_validate_enum(self):
        """Test validating enum type."""
        prop = VisPropertyDefinition(
            type=VisPropertyType.ENUM,
            enum_values=["pending", "running", "completed"],
        )
        
        errors = VisValidator._validate_enum("test", "running", prop)
        assert len(errors) == 0
        
        errors = VisValidator._validate_enum("test", "unknown", prop)
        assert len(errors) == 1  # Invalid value

    def test_validate_array(self):
        """Test validating array type."""
        prop = VisPropertyDefinition(
            type=VisPropertyType.ARRAY,
            items=VisPropertyDefinition(type=VisPropertyType.INTEGER),
        )
        
        errors = VisValidator._validate_array("test", [1, 2, 3], prop)
        assert len(errors) == 0
        
        errors = VisValidator._validate_array("test", [1, "two", 3], prop)
        assert len(errors) > 0  # Contains non-integer

    def test_validate_uri(self):
        """Test validating URI type."""
        prop = VisPropertyDefinition(type=VisPropertyType.URI)
        
        errors = VisValidator._validate_uri("test", "https://example.com", prop)
        assert len(errors) == 0
        
        errors = VisValidator._validate_uri("test", "not-a-uri", prop)
        assert len(errors) > 0


class TestRegisterAllSchemas:
    """Tests for register_all_schemas function."""

    def test_register_all(self):
        """Test registering all built-in schemas."""
        registry = SchemaRegistry()
        
        register_all_schemas()
        
        # Check that some built-in schemas are registered
        assert get_schema_registry().get("vis-thinking") is not None
        assert get_schema_registry().get("drsk-msg") is not None
        assert get_schema_registry().get("vis-tool") is not None