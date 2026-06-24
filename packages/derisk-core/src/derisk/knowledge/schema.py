"""schema.md parser and driver (RFC 003).

schema.md is the configuration file of a knowledge space. It declares:
- Page Types: type -> dir routing
- Relation Types: predicate validation
- Ingest Workflow: free-text prompt for LLM
- Lint Rules: which lint checks to run

This module parses schema.md with tolerance for LLM-written malformed
content (missing sections, misaligned tables, etc.) and provides routing
and validation helpers used by VaultFS and the ingest pipeline.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from derisk.knowledge.types import sha256_hash

# Regex for valid type identifiers (lowercase + digits + dashes)
_TYPE_RE = re.compile(r"^[a-z][a-z0-9-]*$")

# Cache TTL (RFC 003 §4.4)
_CACHE_TTL_SECONDS = 5.0
_schema_cache: dict[str, tuple[float, "Schema"]] = {}


@dataclass
class PageType:
    """One row in the `## Page Types` table."""

    type: str
    dir: str
    description: str = ""


@dataclass
class RelationType:
    """One row in the `## Relation Types` table."""

    type: str
    inverse: str
    description: str = ""


@dataclass
class LintRules:
    """Parsed `## Lint Rules` section. Defaults match RFC 003 §3.6."""

    orphan_pages: bool = True
    stale_edges: bool = True
    contradiction_detection: bool = True
    uncited_sources: bool = True
    dangling_links: bool = True
    frontmatter_required: list[str] = field(
        default_factory=lambda: ["type", "title", "created", "updated"]
    )


@dataclass
class Schema:
    """Parsed schema.md content."""

    purpose: str = ""
    page_types: dict[str, PageType] = field(default_factory=dict)
    relation_types: dict[str, RelationType] = field(default_factory=dict)
    ingest_workflow: str = ""
    lint_rules: LintRules = field(default_factory=LintRules)
    raw_hash: str = ""

    def page_type_for_path(self, path: str) -> Optional[PageType]:
        """Reverse lookup: given a wiki/ path, return the matching PageType."""
        # Normalize: strip leading "wiki/" and trailing filename
        p = path.lstrip("/")
        if p.startswith("wiki/"):
            p = p[len("wiki/"):]
        # Take the directory portion
        dir_part = p.rsplit("/", 1)[0] + "/" if "/" in p else ""
        for pt in self.page_types.values():
            pt_dir = pt.dir
            if pt_dir.startswith("wiki/"):
                pt_dir = pt_dir[len("wiki/"):]
            if pt_dir == dir_part:
                return pt
        return None


# ---------------------------------------------------------------------------
# Default schema.md (RFC 003 §3.7)
# ---------------------------------------------------------------------------

DEFAULT_PAGE_TYPES: list[PageType] = [
    PageType("entity", "wiki/entities/", "人/组织/产品/论文"),
    PageType("concept", "wiki/concepts/", "抽象概念、理论、方法"),
    PageType("source", "wiki/sources/", "源文件摘要"),
    PageType("comparison", "wiki/comparisons/", "对比分析"),
    PageType("synthesis", "wiki/synthesis/", "跨源综合分析"),
    PageType("query", "wiki/queries/", "保存的问答与研究"),
    PageType("finding", "wiki/findings/", "研究发现"),
    PageType("thesis", "wiki/thesis/", "论点"),
    PageType("methodology", "wiki/methodology/", "方法论"),
]

DEFAULT_RELATION_TYPES: list[RelationType] = [
    RelationType("cites", "cited-by", "引用关系"),
    RelationType("links-to", "linked-by", "wikilink 关联"),
    RelationType("derived-from", "source-of", "从某 verbatim 派生"),
    RelationType("depends-on", "depends-on", "依赖关系（自反）"),
    RelationType("causes", "caused-by", "因果关系"),
    RelationType("contradicts", "contradicts", "矛盾关系（自反）"),
    RelationType("part-of", "has-part", "包含关系"),
]


def default_schema_md(space_name: str = "Knowledge Space") -> str:
    """Generate the default schema.md content for a new space."""
    return f"""# {space_name} Schema

## Purpose
<待用户填写>

## Page Types
| type | dir | description |
|---|---|---|
| entity | wiki/entities/ | 人/组织/产品/论文 |
| concept | wiki/concepts/ | 抽象概念、理论、方法 |
| source | wiki/sources/ | 源文件摘要 |
| comparison | wiki/comparisons/ | 对比分析 |
| synthesis | wiki/synthesis/ | 跨源综合分析 |
| query | wiki/queries/ | 保存的问答与研究 |
| finding | wiki/findings/ | 研究发现 |
| thesis | wiki/thesis/ | 论点 |
| methodology | wiki/methodology/ | 方法论 |

## Relation Types
| type | inverse | description |
|---|---|---|
| cites | cited-by | 引用关系 |
| links-to | linked-by | wikilink 关联 |
| derived-from | source-of | 从某 verbatim 派生 |
| depends-on | depends-on | 依赖关系（自反） |
| causes | caused-by | 因果关系 |
| contradicts | contradicts | 矛盾关系（自反） |
| part-of | has-part | 包含关系 |

## Ingest Workflow
新源 ingest 时：
1. Step1 分析：抽取实体、识别 type、找关联
2. Step2 生成：写 L1 markdown 页 + frontmatter + sources[]
3. 自动建图：解析 [[wikilink]] / [^N] 脚注 / related / sources
4. 更新 index.md / log.md / overview.md

## Lint Rules
- orphan_pages: true
- stale_edges: true
- contradiction_detection: true
- uncited_sources: true
- dangling_links: true
- frontmatter_required: [type, title, created, updated]
"""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _split_sections(content: str) -> dict[str, str]:
    """Split content by `## ` headers. Returns dict header_title -> body."""
    sections: dict[str, str] = {}
    current_header: Optional[str] = None
    current_lines: list[str] = []

    for line in content.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current_header is not None:
                sections[current_header] = "\n".join(current_lines).strip()
            current_header = m.group(1).strip().lower()
            current_lines = []
        elif current_header is not None:
            current_lines.append(line)

    if current_header is not None:
        sections[current_header] = "\n".join(current_lines).strip()

    return sections


def _parse_table_rows(body: str, expected_cols: int) -> list[list[str]]:
    """Parse a markdown table body, returning list of row-cell-lists.

    Tolerates:
    - Missing or malformed separator rows
    - Extra columns (truncates to expected_cols)
    - Missing columns (pads with empty strings)
    - Blank rows
    """
    rows: list[list[str]] = []
    seen_separator = False

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("|"):
            # Not a table line; skip silently
            continue
        # Split by | and trim the leading/trailing empty from edge pipes
        cells = [c.strip() for c in stripped.split("|")]
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        if not cells:
            continue

        # Skip separator row like |---|---|---|
        if all(re.match(r"^:?-{2,}:?$", c) for c in cells if c):
            seen_separator = True
            continue

        # Skip header row (first non-separator row, but we can't reliably
        # detect it — assume the first row is header if a separator follows
        # it; we handle this by passing expected_cols and letting callers
        # filter). For simplicity we keep all rows; caller dedupes by key.
        if len(cells) < expected_cols:
            cells = cells + [""] * (expected_cols - len(cells))
        elif len(cells) > expected_cols:
            cells = cells[:expected_cols]

        rows.append(cells)

    return rows


def _parse_page_types(body: str) -> dict[str, PageType]:
    """Parse `## Page Types` section. Returns dict keyed by type."""
    result: dict[str, PageType] = {}
    rows = _parse_table_rows(body, expected_cols=3)

    # Drop the first row if it looks like a header (type/dir/description)
    if rows and any(
        h in rows[0][0].lower()
        for h in ("type", "kind")
    ):
        rows = rows[1:]

    for cells in rows:
        type_name, dir_name, desc = cells[0], cells[1], cells[2]
        if not type_name or not _TYPE_RE.match(type_name):
            continue
        if not dir_name:
            continue
        # Normalize dir to end with /
        if not dir_name.endswith("/"):
            dir_name = dir_name + "/"
        result[type_name] = PageType(
            type=type_name, dir=dir_name, description=desc
        )

    return result


def _parse_relation_types(body: str) -> dict[str, RelationType]:
    """Parse `## Relation Types` section."""
    result: dict[str, RelationType] = {}
    rows = _parse_table_rows(body, expected_cols=3)

    if rows and any(
        h in rows[0][0].lower() for h in ("type", "predicate", "relation")
    ):
        rows = rows[1:]

    for cells in rows:
        type_name, inverse, desc = cells[0], cells[1], cells[2]
        if not type_name or not _TYPE_RE.match(type_name):
            continue
        if not inverse or not _TYPE_RE.match(inverse):
            # If inverse is malformed, default to self-inverse
            inverse = type_name
        result[type_name] = RelationType(
            type=type_name, inverse=inverse, description=desc
        )

    return result


def _parse_lint_rules(body: str) -> LintRules:
    """Parse `## Lint Rules` section.

    Accepts both:
        - orphan_pages: true
        - frontmatter_required: [type, title, created, updated]
    """
    rules = LintRules()

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Strip leading "- "
        if stripped.startswith("-"):
            stripped = stripped[1:].strip()
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip().lower()
        value = value.strip()

        if key == "orphan_pages":
            rules.orphan_pages = value.lower() in ("true", "1", "yes", "on")
        elif key == "stale_edges":
            rules.stale_edges = value.lower() in ("true", "1", "yes", "on")
        elif key == "contradiction_detection":
            rules.contradiction_detection = value.lower() in (
                "true", "1", "yes", "on"
            )
        elif key == "uncited_sources":
            rules.uncited_sources = value.lower() in (
                "true", "1", "yes", "on"
            )
        elif key == "dangling_links":
            rules.dangling_links = value.lower() in (
                "true", "1", "yes", "on"
            )
        elif key == "frontmatter_required":
            # Parse [a, b, c] or a, b, c
            v = value.strip()
            if v.startswith("[") and v.endswith("]"):
                v = v[1:-1]
            fields_list = [
                f.strip() for f in v.split(",") if f.strip()
            ]
            if fields_list:
                rules.frontmatter_required = fields_list

    return rules


def parse_schema(content: str) -> Schema:
    """Parse schema.md content. Tolerant of missing/malformed sections."""
    raw_hash = sha256_hash(content)

    # Cache hit
    cached = _schema_cache.get(raw_hash)
    if cached is not None:
        cached_time, cached_schema = cached
        if time.time() - cached_time < _CACHE_TTL_SECONDS:
            return cached_schema

    sections = _split_sections(content)

    purpose = sections.get("purpose", "")
    ingest_workflow = sections.get("ingest workflow", "")

    page_types = _parse_page_types(sections.get("page types", ""))
    if not page_types:
        # Fall back to defaults (RFC 003 §4.3 step 6)
        page_types = {pt.type: pt for pt in DEFAULT_PAGE_TYPES}

    relation_types = _parse_relation_types(sections.get("relation types", ""))
    if not relation_types:
        relation_types = {rt.type: rt for rt in DEFAULT_RELATION_TYPES}

    lint_rules = _parse_lint_rules(sections.get("lint rules", ""))

    schema = Schema(
        purpose=purpose,
        page_types=page_types,
        relation_types=relation_types,
        ingest_workflow=ingest_workflow,
        lint_rules=lint_rules,
        raw_hash=raw_hash,
    )

    _schema_cache[raw_hash] = (time.time(), schema)
    return schema


# ---------------------------------------------------------------------------
# Validators and routers
# ---------------------------------------------------------------------------

def validate_schema(schema: Schema) -> list[str]:
    """Return a list of error messages. Empty list = valid."""
    errors: list[str] = []

    # Page types
    seen_dirs: set[str] = set()
    for pt in schema.page_types.values():
        if not _TYPE_RE.match(pt.type):
            errors.append(f"page type '{pt.type}' violates naming rule")
        if not pt.dir.startswith("wiki/") or not pt.dir.endswith("/"):
            errors.append(
                f"page type '{pt.type}' dir '{pt.dir}' must start with "
                f"'wiki/' and end with '/'"
            )
        if pt.dir in seen_dirs:
            errors.append(f"duplicate dir '{pt.dir}' in page types")
        seen_dirs.add(pt.dir)

    # Relation types
    for rt in schema.relation_types.values():
        if not _TYPE_RE.match(rt.type):
            errors.append(f"relation type '{rt.type}' violates naming rule")
        if not _TYPE_RE.match(rt.inverse):
            errors.append(
                f"relation type '{rt.type}' inverse '{rt.inverse}' "
                f"violates naming rule"
            )

    return errors


def route_path(schema: Schema, page_type: str, slug: str) -> str:
    """Route (page_type, slug) to a full wiki/ path.

    Falls back to `wiki/<page_type>/<slug>.md` if the type is unknown,
    so that doc_create doesn't hard-fail on schemas the user is in the
    middle of editing.
    """
    pt = schema.page_types.get(page_type)
    if pt is None:
        return f"wiki/{page_type}/{slug}.md"
    # dir is like "wiki/entities/" — append slug.md
    return f"{pt.dir}{slug}.md"


def validate_predicate(schema: Schema, predicate: str) -> bool:
    """Check whether a predicate is declared in schema.md."""
    return predicate in schema.relation_types


def inverse_predicate(schema: Schema, predicate: str) -> Optional[str]:
    """Return the inverse predicate declared in schema.md, if any."""
    rt = schema.relation_types.get(predicate)
    return rt.inverse if rt else None


__all__ = [
    "PageType",
    "RelationType",
    "LintRules",
    "Schema",
    "DEFAULT_PAGE_TYPES",
    "DEFAULT_RELATION_TYPES",
    "default_schema_md",
    "parse_schema",
    "validate_schema",
    "route_path",
    "validate_predicate",
    "inverse_predicate",
]
