"""File extractor protocol & registry (RFC 004 §6 ingest pipeline).

An Extractor turns an uploaded file (path + mime) into one or more VerbatimSpec
records that the ingest orchestrator then writes into the vault via
`vault.verbat_add`.

The registry mirrors the `ToolRegistry` pattern (derisk-core/agent/tools/registry.py):
a global singleton with `register(mime_pattern, extractor)`, `get(mime)`,
and an `@extractor` decorator for declarative registration.

Built-in extractors live in `builtin.py` and are registered at app startup via
`register_builtin_extractors()` (registry_init.py).

Extractors stay decoupled from the model layer: instead of calling
the LLM client directly, they receive a `model_caller` callable from
the orchestrator. Signature:

    async def model_caller(model: str, prompt: str, images: list[Path] = None) -> str

This lets extractors invoke an LLM (e.g., to caption an image, transcribe
audio) without knowing how the LLM is wired up. Plain-text extractors
ignore the callable.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional, Protocol, runtime_checkable

from derisk.knowledge.types import ExtractMode

logger = logging.getLogger(__name__)

# Callable the orchestrator passes to extractors for invoking an LLM.
# Returns the model's text output. `images` is a list of local file paths
# for multimodal models.
ModelCaller = Callable[
    ...,
    Coroutine[Any, Any, str],
]


@dataclass
class VerbatimSpec:
    """Extractor output: one spec becomes one Verbat written by the orchestrator."""

    content: str
    source_file: str
    extract_mode: ExtractMode
    content_date: Optional[str] = None  # ISO 8601; extractor may set from file mtime
    source_mtime: Optional[int] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Extractor(Protocol):
    """File to list[VerbatimSpec].

    `model` is the resolved model name (or None for plain-text extractors).
    `model_caller` is provided by the orchestrator; extractors that do not
    need an LLM may ignore it. Extractors MUST NOT call `verbat_add`:
    the orchestrator owns verbat creation.
    """

    name: str
    mime_patterns: List[str]  # glob patterns, e.g., ["application/pdf"]

    async def extract(
        self,
        path: Path,
        mime: str,
        model: Optional[str],
        model_caller: Optional[ModelCaller],
    ) -> List[VerbatimSpec]: ...


class ExtractorRegistry:
    """Global registry of file extractors keyed by mime glob pattern."""

    def __init__(self) -> None:
        self._extractors: List[Extractor] = []
        self._by_name: Dict[str, Extractor] = {}

    def register(self, extractor: Extractor) -> None:
        if extractor.name in self._by_name:
            logger.warning("Extractor '%s' already registered, overwriting", extractor.name)
            self._extractors = [e for e in self._extractors if e.name != extractor.name]
        self._extractors.append(extractor)
        self._by_name[extractor.name] = extractor

    def get(self, mime: str) -> Optional[Extractor]:
        """Return the first registered extractor whose pattern matches `mime`.

        Patterns are matched as glob (fnmatch): `image/*` matches any image
        mime. First-registered wins, so register more specific patterns first.
        """
        for ext in self._extractors:
            for pat in ext.mime_patterns:
                if fnmatch.fnmatch(mime, pat):
                    return ext
        return None

    def get_by_name(self, name: str) -> Optional[Extractor]:
        return self._by_name.get(name)

    def list_all(self) -> List[Extractor]:
        return list(self._extractors)

    def clear(self) -> None:
        self._extractors.clear()
        self._by_name.clear()


_global_registry = ExtractorRegistry()


def get_extractor_registry() -> ExtractorRegistry:
    return _global_registry


def extractor(
    name: str, mime_patterns: List[str]
) -> Callable[[type], type]:
    """Class decorator: instantiate and register with the global registry.

    Mirrors the `@tool` decorator in derisk-core/agent/tools/decorators.py.
    The decorated class must implement the `Extractor` protocol and accept
    no required constructor args.
    """

    def _wrap(cls: type) -> type:
        instance = cls()
        instance.name = name  # type: ignore[attr-defined]
        instance.mime_patterns = mime_patterns  # type: ignore[attr-defined]
        _global_registry.register(instance)
        return cls

    return _wrap
