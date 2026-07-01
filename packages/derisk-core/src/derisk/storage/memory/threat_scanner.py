"""Memory content threat scanner.

Guard the L1 doc write path against prompt-injection / exfil / invisible
unicode payloads that an LLM extraction step might emit (or that a
malicious user could smuggle into chat history, which tier2 then
promotes to a persistent memory doc).

Mirrors hermes-agent's memory write validation
(tools/memory_tool.py:67-104): regex-based injection patterns + invisible
unicode check. Rejects on first hit — does not attempt to sanitize, since
sanitization of adversarial text is unreliable.

Used by KnowledgeVaultMemoryStore.write_doc / curate_merge before the
content hits vault.doc_create.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

# Prompt-injection patterns. Compiled once at import.
# Inspired by hermes tools/memory_tool.py — covers the common adversarial
# phrasings that try to re-orient the agent mid-context.
_INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+(now|actually|no\s+longer)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*/?\s*(system|prompt|instructions?|memory-context)\s*>", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+(your|the)\s+(rules|instructions)", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all\s+(previous|prior))", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
]

# Invisible / control unicode categories that have no business in a
# memory doc. Zero-width chars, BOM, RTL/LTR overrides, control codes.
# Excludes common whitespace (\n \r \t) which are legitimate.
_INVISIBLE_CATS = {"Cf", "Cc", "Co", "Cn"}


def scan_memory_content(content: str) -> Tuple[bool, List[str]]:
    """Scan memory content for prompt-injection / invisible-unicode threats.

    Args:
        content: The L1 doc body (or frontmatter value) about to be written.

    Returns:
        (is_safe, reasons). is_safe=False if any pattern matched or any
        invisible char found. reasons lists each hit for logging.
    """
    if not content:
        return True, []

    reasons: List[str] = []

    for p in _INJECTION_PATTERNS:
        m = p.search(content)
        if m:
            reasons.append(f"injection: {p.pattern} (matched: {m.group(0)!r})")

    for ch in content:
        if ch in ("\n", "\r", "\t"):
            continue
        cat = unicodedata.category(ch)
        if cat in _INVISIBLE_CATS:
            reasons.append(f"invisible char U+{ord(ch):04X} (cat={cat})")
            break

    return (len(reasons) == 0, reasons)


__all__ = ["scan_memory_content"]
