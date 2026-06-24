"""Tests for schema.md parser and driver (RFC 003)."""

import pytest

from derisk.knowledge.schema import (
    DEFAULT_PAGE_TYPES,
    DEFAULT_RELATION_TYPES,
    Schema,
    default_schema_md,
    inverse_predicate,
    parse_schema,
    route_path,
    validate_predicate,
    validate_schema,
)


def test_default_schema_md_parses():
    md = default_schema_md("Test Space")
    s = parse_schema(md)
    assert len(s.page_types) >= 9
    assert len(s.relation_types) >= 7
    assert "entity" in s.page_types
    assert "cites" in s.relation_types
    errs = validate_schema(s)
    assert errs == [], f"default schema has errors: {errs}"


def test_parse_tolerates_missing_sections():
    md = """# My Schema

## Purpose
Just a test.

## Page Types
| type | dir | description |
|---|---|---|
| entity | wiki/entities/ | people |
"""
    s = parse_schema(md)
    assert s.purpose == "Just a test."
    assert "entity" in s.page_types
    # Missing relation types -> defaults
    assert "cites" in s.relation_types
    # Missing lint rules -> defaults
    assert s.lint_rules.orphan_pages is True


def test_parse_tolerates_misaligned_table():
    md = """# Schema

## Page Types
| type | dir | description |
|---|---|---|
| entity | wiki/entities/ |
| concept | wiki/concepts/ | a concept | extra col |
"""
    s = parse_schema(md)
    assert "entity" in s.page_types
    assert "concept" in s.page_types
    assert s.page_types["entity"].description == ""
    assert s.page_types["concept"].description == "a concept"


def test_parse_tolerates_unknown_type_names():
    md = """# Schema

## Page Types
| type | dir | description |
|---|---|---|
| Bad Type | wiki/bad/ | x |
|  | wiki/empty/ | x |
| good | wiki/good/ | x |
"""
    s = parse_schema(md)
    assert "good" in s.page_types
    assert "Bad Type" not in s.page_types  # spaces violate naming rule
    # When user specifies any valid page types, defaults do NOT merge in —
    # schema.md is authoritative for the page types section.
    assert "entity" not in s.page_types


def test_parse_lint_rules_with_list_value():
    md = """# Schema

## Lint Rules
- orphan_pages: false
- frontmatter_required: [type, title, slug]
"""
    s = parse_schema(md)
    assert s.lint_rules.orphan_pages is False
    assert s.lint_rules.frontmatter_required == ["type", "title", "slug"]


def test_route_path_known_type():
    s = parse_schema(default_schema_md("X"))
    assert route_path(s, "entity", "alice") == "wiki/entities/alice.md"
    assert route_path(s, "concept", "attention") == "wiki/concepts/attention.md"


def test_route_path_unknown_type_falls_back():
    s = parse_schema(default_schema_md("X"))
    assert route_path(s, "custom", "thing") == "wiki/custom/thing.md"


def test_validate_predicate():
    s = parse_schema(default_schema_md("X"))
    assert validate_predicate(s, "cites") is True
    assert validate_predicate(s, "totally-made-up") is False


def test_inverse_predicate():
    s = parse_schema(default_schema_md("X"))
    assert inverse_predicate(s, "cites") == "cited-by"
    assert inverse_predicate(s, "depends-on") == "depends-on"  # self-inverse
    assert inverse_predicate(s, "nonexistent") is None


def test_cache_returns_same_object_for_same_content():
    md = default_schema_md("X")
    s1 = parse_schema(md)
    s2 = parse_schema(md)
    assert s1 is s2  # cache hit


def test_schema_hash_changes_with_content():
    s1 = parse_schema(default_schema_md("A"))
    s2 = parse_schema(default_schema_md("B"))
    assert s1.raw_hash != s2.raw_hash


def test_user_added_page_type_takes_effect_immediately():
    md = """# Schema

## Page Types
| type | dir | description |
|---|---|---|
| runbook | wiki/runbooks/ | ops runbook |
"""
    s = parse_schema(md)
    assert "runbook" in s.page_types
    assert route_path(s, "runbook", "deploy") == "wiki/runbooks/deploy.md"
    # Defaults still merged in because user only specified runbook? No —
    # user-specified page_types fully replace defaults when non-empty.
    # That's by design: schema.md is authoritative for page types.


def test_user_added_relation_type_validates():
    md = """# Schema

## Relation Types
| type | inverse | description |
|---|---|---|
| runs-on | runs | service runs on host |
"""
    s = parse_schema(md)
    assert validate_predicate(s, "runs-on") is True
    assert inverse_predicate(s, "runs-on") == "runs"
    assert validate_predicate(s, "cites") is False  # user replaced defaults
