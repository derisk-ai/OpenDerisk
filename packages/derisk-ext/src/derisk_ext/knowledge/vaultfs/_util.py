"""Pure helpers shared by all VaultFS backends.

No I/O, no DB, no asyncio — just path manipulation, markdown serialization,
datetime parsing, and text chunking. Both LocalVaultFS and DistributedVaultFS
import these to avoid duplication.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ParsedMarkdown:
    """Result of parsing a markdown file with optional YAML frontmatter."""

    content: str
    frontmatter: dict


# Files protected from deletion (spec llm-wiki.md + RFC 001 §4.5)
PROTECTED_FILES = {
    "index.md",
    "log.md",
    "overview.md",
    "schema.md",
    "purpose.md",
}

# Inline content threshold: verbats smaller than this are stored inline,
# larger ones are stored as blobs (file on disk, S3 object, etc.) and
# referenced by path.
INLINE_THRESHOLD = 32 * 1024  # 32 KiB


def normalize_wiki_path(path: str) -> str:
    """Normalize a wiki path: strip leading slashes, prevent path traversal.

    Also strips a leading ``wiki/`` segment so callers may pass either the
    bare doc path (``sources/foo.md``) or the path as returned by the wiki
    tree endpoint (``wiki/sources/foo.md``). DB rows and the on-disk wiki/
    directory both use the bare form.
    """
    p = path.strip().lstrip("/")
    if p.startswith("wiki/"):
        p = p[len("wiki/"):]
    if ".." in p.split("/"):
        raise ValueError(f"Illegal path traversal: {path}")
    return p


def validate_wiki_path(path: str) -> None:
    if not path:
        raise ValueError("Empty wiki path")
    if path.startswith("/"):
        raise ValueError(f"Absolute path not allowed: {path}")
    if ".." in path.split("/"):
        raise ValueError(f"Path traversal not allowed: {path}")


def serialize_markdown(frontmatter: dict, body: str) -> str:
    """Reconstruct markdown with YAML frontmatter fence."""
    import yaml as _yaml

    if not frontmatter:
        return body
    fm_text = _yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm_text}\n---\n\n{body}"


def parse_markdown(raw: str) -> ParsedMarkdown:
    """Split a markdown file into YAML frontmatter and body.

    Supports the ``---`` fence style. If no frontmatter is present, the whole
    text is returned as content and frontmatter is empty.
    """
    import yaml as _yaml

    raw = raw.replace("\r\n", "\n")
    if raw.startswith("---\n"):
        # Find the closing fence on its own line.
        close_idx = raw.find("\n---", 4)
        if close_idx != -1:
            fm_text = raw[4:close_idx]
            try:
                frontmatter = _yaml.safe_load(fm_text) or {}
            except Exception:
                frontmatter = {}
            content = raw[close_idx + 4 :].lstrip("\n")
            return ParsedMarkdown(content=content, frontmatter=frontmatter)
    return ParsedMarkdown(content=raw, frontmatter={})


def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def make_snippet(content: str, query: str, context: int = 50) -> str:
    """Extract a snippet around the first occurrence of query."""
    idx = content.lower().find(query.lower())
    if idx == -1:
        return content[:200]
    start = max(0, idx - context)
    end = min(len(content), idx + len(query) + context)
    snippet = content[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    return snippet


def chunk_text(text: str, max_chars: int = 2000) -> list[tuple[int, str, str]]:
    """Naive paragraph-based chunking with content-hash IDs.

    Splits on double-newlines, accumulates until max_chars. Returns a
    list of `(chunk_index, chunk_text, content_hash)` tuples where
    `content_hash = sha256(chunk_text)[:16]`. The hash is stable across
    re-chunking for unchanged chunks, so vector IDs derived from it
    (`doc:{doc_id}:chunk:{hash}`) survive edits to other parts of the
    document.
    """
    import hashlib

    paragraphs = text.split("\n\n")
    pieces: list[str] = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 2 > max_chars and current:
            pieces.append(current.strip())
            current = p
        else:
            current = current + "\n\n" + p if current else p
    if current.strip():
        pieces.append(current.strip())
    if not pieces:
        pieces = [text]

    return [
        (i, piece, hashlib.sha256(piece.encode("utf-8")).hexdigest()[:16])
        for i, piece in enumerate(pieces)
    ]


def chunk_text_plain(text: str, max_chars: int = 2000) -> list[str]:
    """Return just the chunk texts (no indices/hashes)."""
    return [c[1] for c in chunk_text(text, max_chars)]
