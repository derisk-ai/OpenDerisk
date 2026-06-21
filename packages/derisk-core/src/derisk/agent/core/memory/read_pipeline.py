"""Memory read pipeline: prefetch cache + context fencing + stream scrubber.

Mirrors hermes-agent's memory read path:

* `MemoryPrefetchCache` — per-conversation async cache. The previous turn's
  `turn_complete` hook kicks off a background retrieval; the next turn
  consumes the result non-blockingly (returns empty if not ready).

* `build_memory_context_block(raw)` — wraps retrieved memory in a fenced
  `<memory-context>` block with a system-note preamble, so the LLM treats
  it as reference data rather than new user input.

* `sanitize_context(text)` — strips fence tags and injected blocks from
  provider output (one-shot, for non-streaming paths).

* `StreamingContextScrubber` — stateful scrubber that strips
  `<memory-context>...</memory-context>` spans from streaming deltas,
  including spans that straddle chunk boundaries. Ported from hermes.

* `MemoryReadPipeline` — per-conversation coordinator owning a prefetch
  cache, a scrubber, and the frozen static-layer block (room=profile/
  preference memories injected into system prompt).
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Static layer config
# ---------------------------------------------------------------------------

# Rooms whose memories are treated as static (frozen into system prompt for
# the whole session) rather than dynamically retrieved per turn.
STATIC_ROOMS: List[str] = ["profile", "preference"]


# ---------------------------------------------------------------------------
# Context fencing helpers (ported from hermes-agent)
# ---------------------------------------------------------------------------

_FENCE_TAG_RE = re.compile(r"</?\s*memory-context\s*>", re.IGNORECASE)
_INTERNAL_CONTEXT_RE = re.compile(
    r"<\s*memory-context\s*>[\s\S]*?</\s*memory-context\s*>",
    re.IGNORECASE,
)
_INTERNAL_NOTE_RE = re.compile(
    r"\[System note:\s*The following is recalled memory context,\s*"
    r"NOT new user input\.\s*Treat as (?:informational background data"
    r"|authoritative reference data[^\]]*)\.\]\s*",
    re.IGNORECASE,
)


def sanitize_context(text: str) -> str:
    """Strip fence tags, injected context blocks, and system notes."""
    if not text:
        return ""
    text = _INTERNAL_CONTEXT_RE.sub("", text)
    text = _INTERNAL_NOTE_RE.sub("", text)
    text = _FENCE_TAG_RE.sub("", text)
    return text


def build_memory_context_block(raw_context: str) -> str:
    """Wrap prefetched memory in a fenced block with system note.

    Returns empty string if raw_context is empty/whitespace.
    """
    if not raw_context or not raw_context.strip():
        return ""
    clean = sanitize_context(raw_context)
    if not clean.strip():
        return ""
    return (
        "<memory-context>\n"
        "[System note: The following is recalled memory context, "
        "NOT new user input. Treat as authoritative reference data — "
        "this is the agent's persistent memory and should inform all responses.]\n\n"
        f"{clean}\n"
        "</memory-context>"
    )


# ---------------------------------------------------------------------------
# StreamingContextScrubber (ported from hermes-agent)
# ---------------------------------------------------------------------------


class StreamingContextScrubber:
    """Stateful scrubber for streaming text that may contain split memory-context spans.

    The one-shot `sanitize_context` regex cannot survive chunk boundaries:
    a `<memory-context>` opened in one delta and closed in a later delta
    leaks its payload to the UI because the non-greedy block regex needs
    both tags in one string. This scrubber runs a small state machine
    across deltas, holding back partial-tag tails and discarding
    everything inside a span (including the system-note line).
    """

    _OPEN_TAG = "<memory-context>"
    _CLOSE_TAG = "</memory-context>"

    def __init__(self) -> None:
        self._in_span: bool = False
        self._buf: str = ""

    def reset(self) -> None:
        self._in_span = False
        self._buf = ""

    def feed(self, text: str) -> str:
        """Return the visible portion of `text` after scrubbing."""
        if not text:
            return ""
        buf = self._buf + text
        self._buf = ""
        out: List[str] = []

        while buf:
            if self._in_span:
                idx = buf.lower().find(self._CLOSE_TAG)
                if idx == -1:
                    held = self._max_partial_suffix(buf, self._CLOSE_TAG)
                    self._buf = buf[-held:] if held else ""
                    return "".join(out)
                buf = buf[idx + len(self._CLOSE_TAG):]
                self._in_span = False
            else:
                idx = buf.lower().find(self._OPEN_TAG)
                if idx == -1:
                    held = self._max_partial_suffix(buf, self._OPEN_TAG)
                    if held:
                        out.append(buf[:-held])
                        self._buf = buf[-held:]
                    else:
                        out.append(buf)
                    return "".join(out)
                if idx > 0:
                    out.append(buf[:idx])
                buf = buf[idx + len(self._OPEN_TAG):]
                self._in_span = True

        return "".join(out)

    def flush(self) -> str:
        """Emit any held-back buffer at end-of-stream."""
        if self._in_span:
            self._buf = ""
            self._in_span = False
            return ""
        tail = self._buf
        self._buf = ""
        return tail

    @staticmethod
    def _max_partial_suffix(buf: str, tag: str) -> int:
        """Return the length of the longest buf-suffix that is a tag-prefix."""
        tag_lower = tag.lower()
        buf_lower = buf.lower()
        max_check = min(len(buf_lower), len(tag_lower) - 1)
        for i in range(max_check, 0, -1):
            if tag_lower.startswith(buf_lower[-i:]):
                return i
        return 0


# ---------------------------------------------------------------------------
# MemoryPrefetchCache
# ---------------------------------------------------------------------------


class MemoryPrefetchCache:
    """Per-conversation async prefetch cache.

    Producer: the tier-0 prefetch hook calls `set_result(...)` after the
    background retrieval completes.

    Consumer: `consume(timeout=0.0)` returns the cached result if ready,
    or None if not ready (non-blocking by default). After consume, the
    cache is cleared — one shot per turn.
    """

    def __init__(self) -> None:
        self._result: Optional[str] = None
        self._ready: asyncio.Event = asyncio.Event()
        self._query: Optional[str] = None
        self._lock = asyncio.Lock()

    def reset(self) -> None:
        self._result = None
        self._query = None
        self._ready.clear()

    def set_result(self, query: str, result: str) -> None:
        self._query = query
        self._result = result
        self._ready.set()

    async def consume(self, timeout: float = 0.0) -> Optional[str]:
        """Pop the cached result. Returns None if not ready within timeout."""
        if timeout <= 0:
            if not self._ready.is_set():
                return None
        else:
            try:
                await asyncio.wait_for(self._ready.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                return None
        result = self._result
        # One-shot: clear after consume so next turn starts fresh.
        self.reset()
        return result

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    @property
    def query(self) -> Optional[str]:
        return self._query


# ---------------------------------------------------------------------------
# MemoryReadPipeline — per-conversation coordinator
# ---------------------------------------------------------------------------


class MemoryReadPipeline:
    """Per-conversation read pipeline state.

    Owns:
    - prefetch cache (consumed by react_master_agent at turn start)
    - stream scrubber (fed by listen_thinking_stream on each delta)
    - static block (frozen memory loaded once at session start, injected
      into system prompt)
    """

    def __init__(self) -> None:
        self._prefetch = MemoryPrefetchCache()
        self._scrubber = StreamingContextScrubber()
        self._static_block: Optional[str] = None
        self._static_loaded: bool = False

    # -- prefetch --
    def get_prefetch_cache(self) -> MemoryPrefetchCache:
        return self._prefetch

    async def consume_prefetch(self, timeout: float = 0.0) -> Optional[str]:
        return await self._prefetch.consume(timeout=timeout)

    # -- scrubber --
    def get_scrubber(self) -> StreamingContextScrubber:
        return self._scrubber

    def reset_scrubber(self) -> None:
        self._scrubber.reset()

    def scrub_stream_delta(self, delta: str) -> str:
        """Feed a stream delta through the scrubber; returns visible text."""
        if not delta:
            return ""
        return self._scrubber.feed(delta)

    def flush_scrubber(self) -> str:
        return self._scrubber.flush()

    # -- static block --
    @property
    def static_block(self) -> Optional[str]:
        return self._static_block

    @property
    def static_loaded(self) -> bool:
        return self._static_loaded

    def set_static_block(self, block: Optional[str]) -> None:
        self._static_block = block
        self._static_loaded = True

    async def load_static_block(self, bundle: Any) -> Optional[str]:
        """Load static-layer memories (room in STATIC_ROOMS) from all bound spaces.

        Called once at session start. Result is frozen for the whole session
        to keep the system-prompt prefix cache stable. Subsequent calls are
        no-ops.
        """
        if self._static_loaded:
            return self._static_block
        if bundle is None or getattr(bundle, "manager", None) is None:
            self._static_loaded = True
            return None

        manager = bundle.manager
        stores = getattr(manager, "memory_stores", {}) or {}
        if not stores:
            self._static_loaded = True
            return None

        lines: List[str] = []
        wing = getattr(manager.config, "wing", "default")
        for space_id, store in stores.items():
            for room in STATIC_ROOMS:
                try:
                    entries = await _fetch_room_entries(store, room, wing)
                    for e in entries:
                        content = getattr(e, "content", "") or ""
                        if content.strip():
                            lines.append(f"- {content.strip()}")
                except Exception as e:  # noqa: BLE001
                    logger.debug(
                        "static block load failed for space=%s room=%s: %s",
                        space_id, room, e,
                    )

        if lines:
            block = "## 用户画像与偏好\n\n" + "\n".join(lines)
        else:
            block = None
        self._static_block = block
        self._static_loaded = True
        logger.info(
            "[MemoryReadPipeline] static block loaded: %d entries",
            len(lines),
        )
        return block


async def _fetch_room_entries(store: Any, room: str, wing: str) -> List[Any]:
    """Best-effort fetch of all entries in a room.

    Prefers a dedicated `alist_by_room` API if the store exposes one;
    otherwise falls back to asearch_memory with an empty query and a
    large top_k.
    """
    if hasattr(store, "alist_by_room"):
        return await store.alist_by_room(room=room, wing=wing)
    if hasattr(store, "asearch_memory"):
        try:
            return await store.asearch_memory(
                query="",
                top_k=200,
                wing=wing,
                room=room,
                max_distance=10.0,  # accept everything when no real query
            )
        except Exception:
            return []
    return []


__all__ = [
    "STATIC_ROOMS",
    "MemoryPrefetchCache",
    "MemoryReadPipeline",
    "StreamingContextScrubber",
    "build_memory_context_block",
    "sanitize_context",
]
