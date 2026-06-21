"""Tests for the memory read pipeline (prefetch cache + fencing + scrubber)."""

import asyncio
from typing import Any, List, Optional

import pytest

from derisk.agent.core.memory.read_pipeline import (
    STATIC_ROOMS,
    MemoryPrefetchCache,
    MemoryReadPipeline,
    StreamingContextScrubber,
    build_memory_context_block,
    sanitize_context,
)


# -----------------------------------------------------------------------------
# build_memory_context_block / sanitize_context
# -----------------------------------------------------------------------------


class TestFencing:
    def test_empty_returns_empty(self):
        assert build_memory_context_block("") == ""
        assert build_memory_context_block("   \n  ") == ""

    def test_wraps_with_fence_and_note(self):
        out = build_memory_context_block("user likes go")
        assert out.startswith("<memory-context>")
        assert out.endswith("</memory-context>")
        assert "[System note:" in out
        assert "user likes go" in out

    def test_strips_pre_existing_fence(self):
        raw = "<memory-context>foo</memory-context>"
        out = build_memory_context_block(raw)
        # Pre-wrapped input is stripped entirely (don't double-wrap).
        assert out == ""

    def test_sanitize_strips_whole_block(self):
        # Hermes semantics: a complete <memory-context>...</memory-context>
        # block is stripped as a unit, not just the tags.
        assert sanitize_context("<memory-context>hi</memory-context>") == ""

    def test_sanitize_strips_lone_tags(self):
        assert sanitize_context("<memory-context>") == ""
        assert sanitize_context("</memory-context>") == ""

    def test_sanitize_strips_system_note(self):
        text = "[System note: The following is recalled memory context, NOT new user input. Treat as authoritative reference data — this is the agent's persistent memory and should inform all responses.]\nfoo"
        # The note + trailing whitespace is consumed; "foo" remains.
        assert sanitize_context(text) == "foo"

    def test_sanitize_handles_nested_block(self):
        text = "before <memory-context>inner stuff</memory-context> after"
        assert sanitize_context(text) == "before  after"


# -----------------------------------------------------------------------------
# StreamingContextScrubber
# -----------------------------------------------------------------------------


class TestScrubber:
    def test_no_fence_passes_through(self):
        s = StreamingContextScrubber()
        assert s.feed("hello world") == "hello world"

    def test_complete_fence_in_one_chunk(self):
        s = StreamingContextScrubber()
        out = s.feed("before <memory-context>secret</memory-context> after")
        assert out == "before  after"

    def test_fence_split_across_chunks(self):
        s = StreamingContextScrubber()
        out1 = s.feed("before <memory-context>sec")
        assert out1 == "before "
        out2 = s.feed("ret is here</memory-context> after")
        assert out2 == " after"

    def test_open_tag_split_across_chunks(self):
        s = StreamingContextScrubber()
        # "<memory-" then "context>" — partial open tag should be held back
        out1 = s.feed("text <memory-")
        assert out1 == "text "
        out2 = s.feed("context>secret</memory-context> end")
        assert out2 == " end"

    def test_flush_inside_span_discards(self):
        s = StreamingContextScrubber()
        s.feed("before <memory-context>partial")
        # Stream ended without closing — discard (safer than leaking)
        tail = s.flush()
        assert tail == ""

    def test_flush_outside_span_emits_held_tail(self):
        s = StreamingContextScrubber()
        # Trailing "<memory" that turns out not to be a real tag — emit on flush
        s.feed("text <memory")
        tail = s.flush()
        assert tail == "<memory"

    def test_reset_clears_state(self):
        s = StreamingContextScrubber()
        s.feed("before <memory-context>secret")
        s.reset()
        # After reset, fresh feed is treated as outside a span
        assert s.feed("clean text") == "clean text"


# -----------------------------------------------------------------------------
# MemoryPrefetchCache
# -----------------------------------------------------------------------------


class TestPrefetchCache:
    def test_consume_empty_returns_none(self):
        cache = MemoryPrefetchCache()
        result = asyncio.get_event_loop().run_until_complete(cache.consume(timeout=0.0))
        assert result is None

    def test_set_then_consume_returns_result(self):
        cache = MemoryPrefetchCache()
        cache.set_result("query", "result text")
        result = asyncio.get_event_loop().run_until_complete(cache.consume(timeout=0.0))
        assert result == "result text"

    def test_consume_clears_cache(self):
        cache = MemoryPrefetchCache()
        cache.set_result("q", "r")
        loop = asyncio.get_event_loop()
        first = loop.run_until_complete(cache.consume(timeout=0.0))
        second = loop.run_until_complete(cache.consume(timeout=0.0))
        assert first == "r"
        assert second is None  # cleared after first consume

    def test_consume_with_timeout_returns_none_if_not_ready(self):
        cache = MemoryPrefetchCache()
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(cache.consume(timeout=0.05))
        assert result is None

    def test_reset_clears(self):
        cache = MemoryPrefetchCache()
        cache.set_result("q", "r")
        cache.reset()
        assert not cache.is_ready
        loop = asyncio.get_event_loop()
        assert loop.run_until_complete(cache.consume(timeout=0.0)) is None


# -----------------------------------------------------------------------------
# MemoryReadPipeline
# -----------------------------------------------------------------------------


class TestReadPipeline:
    def test_scrubber_reset(self):
        p = MemoryReadPipeline()
        p.scrub_stream_delta("before <memory-context>secret")
        p.reset_scrubber()
        assert p.scrub_stream_delta("clean") == "clean"

    def test_scrub_stream_delta_uses_internal_scrubber(self):
        p = MemoryReadPipeline()
        out = p.scrub_stream_delta("a <memory-context>x</memory-context> b")
        assert out == "a  b"

    def test_static_block_initially_none(self):
        p = MemoryReadPipeline()
        assert p.static_block is None
        assert not p.static_loaded

    def test_load_static_block_with_no_bundle(self):
        p = MemoryReadPipeline()
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(p.load_static_block(None))
        assert result is None
        assert p.static_loaded  # marked loaded to avoid retrying

    def test_load_static_block_idempotent(self):
        p = MemoryReadPipeline()
        p.set_static_block("frozen")
        loop = asyncio.get_event_loop()
        # Second call should not re-fetch
        result = loop.run_until_complete(p.load_static_block(MagicMock_bundle()))
        assert result == "frozen"

    def test_load_static_block_from_stores(self):
        from unittest.mock import MagicMock

        # Build a fake bundle with one store that has alist_by_room
        store = MagicMock()
        async def _alist(room, wing):
            return [
                MagicMock(content="user prefers dark mode", room=room),
                MagicMock(content="user is a Go developer", room=room),
            ]
        store.alist_by_room = _alist

        manager = MagicMock()
        manager.memory_stores = {"space1": store}
        manager.config = MagicMock(wing="default")

        bundle = MagicMock()
        bundle.manager = manager

        p = MemoryReadPipeline()
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(p.load_static_block(bundle))
        assert result is not None
        assert "用户画像与偏好" in result
        assert "dark mode" in result
        assert "Go developer" in result
        assert p.static_loaded


def MagicMock_bundle() -> Any:
    from unittest.mock import MagicMock
    b = MagicMock()
    b.manager = MagicMock()
    b.manager.memory_stores = {}
    b.manager.config = MagicMock(wing="default")
    return b


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
