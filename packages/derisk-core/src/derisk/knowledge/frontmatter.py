"""Frontmatter parser with LLM-output tolerance (RFC 001 §4.4).

LLM-generated frontmatter is frequently malformed. This parser implements
two strategies + repair heuristics, porting the design from llm_wiki's
`frontmatter.ts:76-130`:

1. Strict strategy: a YAML block fenced by `---` at the very top of the file.
2. Anywhere-fallback: scan for the first `---\\n...\\n---` block anywhere.

Plus:
- `repair_wikilink_lists`: bare `[[a]], [[b]]` flow sequences get quoted so
  the YAML parser doesn't choke on `[a, b]` ambiguity.
- Fence repair: tolerate a missing closing `---`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

import yaml


_FRONTMATTER_FENCE = "---"
_FRONTMATTER_RE = re.compile(
    r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL
)
_ANYWHERE_RE = re.compile(
    r"\n---\s*\n(.*?)\n---\s*\n", re.DOTALL
)
# Bare wikilink list items like "- [[transformer]]" or "related: [[a]], [[b]]"
_BARE_WIKILINK_RE = re.compile(r"(\[\[[^\]]+\]\])")


@dataclass
class ParsedDocument:
    """Result of parsing a markdown file with frontmatter."""

    frontmatter: dict[str, Any]
    content: str           # markdown body without frontmatter fence
    raw_frontmatter: str   # original YAML text (for debugging / lint)
    strategy: str          # "strict" | "anywhere" | "empty"
    repaired: bool         # True if repair heuristics were applied


def parse_markdown(raw: str) -> ParsedDocument:
    """Parse a markdown string into frontmatter + body.

    Never raises on malformed input; returns an empty frontmatter dict and
    the raw content as body if parsing fails entirely.
    """
    if not raw or not raw.strip():
        return ParsedDocument(
            frontmatter={}, content="", raw_frontmatter="", strategy="empty", repaired=False
        )

    # Strategy 1: strict (fence at the very top)
    match = _FRONTMATTER_RE.match(raw)
    if match:
        yaml_text, body = match.group(1), match.group(2)
        fm, repaired = _safe_load_yaml(yaml_text)
        if fm is not None:
            return ParsedDocument(
                frontmatter=fm,
                content=body,
                raw_frontmatter=yaml_text,
                strategy="strict",
                repaired=repaired,
            )

    # Strategy 2: anywhere-fallback
    match = _ANYWHERE_RE.search("\n" + raw)
    if match:
        yaml_text, body = match.group(1), raw.replace(match.group(0), "\n", 1)
        fm, repaired = _safe_load_yaml(yaml_text)
        if fm is not None:
            return ParsedDocument(
                frontmatter=fm,
                content=body,
                raw_frontmatter=yaml_text,
                strategy="anywhere",
                repaired=repaired,
            )

    # No frontmatter found; treat whole content as body
    return ParsedDocument(
        frontmatter={},
        content=raw,
        raw_frontmatter="",
        strategy="empty",
        repaired=False,
    )


def _safe_load_yaml(text: str) -> tuple[Optional[dict], bool]:
    """Load YAML with repair attempts. Returns (parsed, was_repaired)."""
    # First try as-is
    try:
        result = yaml.safe_load(text)
        if isinstance(result, dict):
            return result, False
        if result is None:
            return {}, False
        # Non-dict (list / scalar) - treat as empty
        return {}, False
    except yaml.YAMLError:
        pass

    # Repair attempt 1: quote bare wikilink lists
    repaired = repair_wikilink_lists(text)
    try:
        result = yaml.safe_load(repaired)
        if isinstance(result, dict):
            return result, True
    except yaml.YAMLError:
        pass

    # Repair attempt 2: add closing fence if missing
    if not text.rstrip().endswith("---"):
        repaired2 = text + "\n---"
        try:
            result = yaml.safe_load(repaired2)
            if isinstance(result, dict):
                return result, True
        except yaml.YAMLError:
            pass

    # Give up
    return None, False


def repair_wikilink_lists(text: str) -> str:
    """Quote bare `[[wikilink]]` values so YAML parses them as strings.

    LLM often writes:
        related: [[transformer]], [[attention]]
    YAML interprets `[[transformer]]` as nested list-of-list, which fails.
    We wrap each `[[...]]` in double quotes.
    """

    def _quote(m: re.Match) -> str:
        return f'"{m.group(1)}"'

    # Only quote when not already quoted
    lines = []
    for line in text.split("\n"):
        # Skip lines that are already fully quoted values
        if _has_unquoted_wikilink(line):
            line = _BARE_WIKILINK_RE.sub(_quote, line)
        lines.append(line)
    return "\n".join(lines)


def _has_unquoted_wikilink(line: str) -> bool:
    """Check if a line contains a [[wikilink]] not inside quotes."""
    in_quote = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            in_quote = not in_quote
        elif not in_quote and line[i : i + 2] == "[[":
            return True
        i += 1
    return False


def extract_wikilinks(content: str) -> list[str]:
    """Extract all `[[wikilink]]` targets from markdown body.

    Returns slugs (the text inside the brackets), not the display text.
    Handles `[[target|display]]` syntax.
    """
    links: list[str] = []
    # Match [[...]] but not inside code spans / code blocks
    in_code_block = False
    in_inline_code = False
    i = 0
    while i < len(content):
        # Track ``` code blocks
        if content[i : i + 3] == "```":
            in_code_block = not in_code_block
            i += 3
            continue
        # Track ` inline code
        if content[i] == "`" and not in_code_block:
            in_inline_code = not in_inline_code
            i += 1
            continue
        if not in_code_block and not in_inline_code and content[i : i + 2] == "[[":
            end = content.find("]]", i + 2)
            if end == -1:
                break
            target = content[i + 2 : end]
            # Strip display text: [[target|display]] -> target
            if "|" in target:
                target = target.split("|", 1)[0]
            target = target.strip()
            if target:
                links.append(target)
            i = end + 2
        else:
            i += 1
    return links


def extract_footnotes(content: str) -> list[dict]:
    """Extract `[^N]: <source>, p.<page>` footnote references.

    Returns list of {"ref": "1", "source": "paper.pdf", "page": "3"}.
    """
    footnotes: list[dict] = []
    pattern = re.compile(
        r"^\[\^(\w+)\]:\s*([^,]+?)(?:,\s*p?\.\s*(\d+))?\s*$",
        re.MULTILINE,
    )
    for m in pattern.finditer(content):
        footnotes.append(
            {
                "ref": m.group(1),
                "source": m.group(2).strip(),
                "page": m.group(3),
            }
        )
    return footnotes


def split_frontmatter(raw: str) -> tuple[str, str]:
    """Split a markdown file into (frontmatter_yaml, body).

    If no frontmatter, returns ("", raw).
    """
    parsed = parse_markdown(raw)
    return parsed.raw_frontmatter, parsed.content
