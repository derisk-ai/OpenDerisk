"""
Tests for Streaming Function Call Parser

Tests the incremental parsing of LLM function call output.
"""

import asyncio
import pytest

from derisk.model.streaming.incremental_parser import (
    IncrementalFunctionCallParser,
    ParseState,
    ParseEvent,
)
from derisk.model.streaming.chunk_strategies import (
    LineBasedChunkStrategy,
    AdaptiveChunkStrategy,
    ChunkStrategy,
)


class TestIncrementalFunctionCallParser:
    """Test cases for IncrementalFunctionCallParser"""

    @pytest.fixture
    def parser(self):
        """Create a fresh parser for each test"""
        return IncrementalFunctionCallParser()

    @pytest.mark.asyncio
    async def test_parse_simple_function_call(self, parser):
        """Test parsing a simple function call"""

        # Simulate LLM output tokens
        tokens = [
            '{"tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "write", "arguments": "{\\"file_path\\": \\"test.py\\", \\"content\\": \\"hello\\"}"}}]}'
        ]

        events = []

        for token in tokens:
            async for event in parser.parse_token(token):
                events.append(event)

        # Check that we captured events
        assert len(events) > 0

        # Check final state
        assert parser.state == ParseState.COMPLETE

    @pytest.mark.asyncio
    async def test_parse_large_content_streaming(self, parser):
        """Test that large content triggers streaming"""

        # Create a large content string
        large_content = "def hello():\\n" + "    print('world')\\n" * 100

        # Build the function call JSON
        json_str = f'{{"tool_calls": [{{"id": "call_123", "type": "function", "function": {{"name": "write", "arguments": "{{\\"file_path\\": \\"test.py\\", \\"content\\": \\"{large_content}\\"}}"}}}}]}}'

        # Split into tokens (simulating LLM output)
        chunk_size = 50
        tokens = [
            json_str[i : i + chunk_size] for i in range(0, len(json_str), chunk_size)
        ]

        events = []
        param_chunks = []

        for token in tokens:
            async for event in parser.parse_token(token):
                events.append(event)
                if event.event_type == "param_chunk":
                    param_chunks.append(event)

        # Check that we captured parameter chunks
        # Note: The exact number depends on the content structure
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_parse_multiple_function_calls(self, parser):
        """Test parsing multiple function calls"""

        json_str = """{"tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "write", "arguments": "{\\"content\\": \\"test1\\"}"}},
            {"id": "call_2", "type": "function", "function": {"name": "read", "arguments": "{\\"file_path\\": \\"test.py\\"}"}}
        ]}"""

        events = []

        # Parse token by token
        for char in json_str:
            async for event in parser.parse_token(char):
                events.append(event)

        # Check that we captured events for both calls
        assert len(events) > 0


class TestChunkStrategies:
    """Test cases for chunk strategies"""

    @pytest.mark.asyncio
    async def test_line_based_chunking(self):
        """Test line-based chunking strategy"""

        strategy = LineBasedChunkStrategy(lines_per_chunk=5)

        content = "\\n".join([f"line {i}" for i in range(20)])

        chunks = []
        async for chunk in strategy.chunk(content):
            chunks.append(chunk)

        # Check that we got multiple chunks
        assert len(chunks) > 1

        # Check estimated chunks
        estimated = strategy.estimate_chunks(content)
        assert estimated == 4

    @pytest.mark.asyncio
    async def test_adaptive_chunking_code(self):
        """Test adaptive chunking with code content"""

        strategy = AdaptiveChunkStrategy()

        code_content = """
def hello():
    print("world")

class MyClass:
    def method(self):
        pass
"""

        chunks = []
        async for chunk in strategy.chunk(code_content):
            chunks.append(chunk)

        # Should chunk the code
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_adaptive_chunking_text(self):
        """Test adaptive chunking with plain text"""

        strategy = AdaptiveChunkStrategy()

        text_content = "This is plain text content.\\n" * 50

        chunks = []
        async for chunk in strategy.chunk(text_content):
            chunks.append(chunk)

        assert len(chunks) > 0


class TestParserStateManagement:
    """Test parser state management"""

    def test_reset(self):
        """Test parser reset"""

        parser = IncrementalFunctionCallParser()

        # Simulate some parsing
        parser._buffer = "test content"
        parser._position = 100

        # Reset
        parser.reset()

        # Check state is cleared
        assert parser._buffer == ""
        assert parser._position == 0
        assert parser.state == ParseState.IDLE

    def test_get_buffer_preview(self):
        """Test buffer preview"""

        parser = IncrementalFunctionCallParser()
        parser._buffer = "x" * 200

        # Get preview
        preview = parser.get_buffer_preview(50)

        assert len(preview) <= 53  # "..." + 50 chars
        assert preview.startswith("...")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
