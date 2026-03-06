"""
Tests for VIS Protocol V2 - JSON Lines Converter
"""

import pytest
import json
from derisk.vis.protocol.jsonlines import (
    VisJsonLinesConverter,
    VisJsonLinesBuilder,
    VisJsonLine,
    VisMessageType,
    JsonPatchOperation,
    vis_builder,
)


class TestVisJsonLine:
    """Tests for VisJsonLine."""

    def test_component_to_json(self):
        """Test converting component to JSON."""
        line = VisJsonLine(
            type=VisMessageType.COMPONENT,
            tag="vis-thinking",
            uid="test-1",
            props={"markdown": "Thinking..."},
        )
        
        json_str = line.to_json()
        data = json.loads(json_str)
        
        assert data["type"] == "component"
        assert data["tag"] == "vis-thinking"
        assert data["uid"] == "test-1"
        assert data["props"]["markdown"] == "Thinking..."

    def test_patch_to_json(self):
        """Test converting patch to JSON."""
        line = VisJsonLine(
            type=VisMessageType.PATCH,
            uid="test-1",
            ops=[
                JsonPatchOperation.add("/props/markdown", " more")
            ],
        )
        
        json_str = line.to_json()
        data = json.loads(json_str)
        
        assert data["type"] == "patch"
        assert data["uid"] == "test-1"
        assert len(data["ops"]) == 1

    def test_from_json(self):
        """Test parsing from JSON."""
        json_str = '{"type":"component","tag":"vis-thinking","uid":"test-1","props":{"markdown":"test"}}'
        
        line = VisJsonLine.from_json(json_str)
        
        assert line.type == VisMessageType.COMPONENT
        assert line.tag == "vis-thinking"
        assert line.uid == "test-1"

    def test_to_dict(self):
        """Test converting to dictionary."""
        line = VisJsonLine(
            type=VisMessageType.COMPONENT,
            tag="vis-thinking",
            uid="test-1",
            props={"markdown": "test"},
        )
        
        d = line.to_dict()
        
        assert d["type"] == "component"
        assert d["tag"] == "vis-thinking"


class TestJsonPatchOperation:
    """Tests for JSON Patch operations."""

    def test_add_operation(self):
        """Test add operation."""
        op = JsonPatchOperation.add("/props/markdown", "test")
        
        assert op["op"] == "add"
        assert op["path"] == "/props/markdown"
        assert op["value"] == "test"

    def test_remove_operation(self):
        """Test remove operation."""
        op = JsonPatchOperation.remove("/props/extra")
        
        assert op["op"] == "remove"
        assert op["path"] == "/props/extra"

    def test_replace_operation(self):
        """Test replace operation."""
        op = JsonPatchOperation.replace("/props/status", "completed")
        
        assert op["op"] == "replace"
        assert op["value"] == "completed"


class TestVisJsonLinesConverter:
    """Tests for VisJsonLinesConverter."""

    def test_create_component(self):
        """Test creating a component message."""
        converter = VisJsonLinesConverter()
        
        line = converter.create_component(
            tag="vis-thinking",
            uid="test-1",
            props={"markdown": "Thinking..."},
        )
        
        assert line.type == VisMessageType.COMPONENT
        assert line.tag == "vis-thinking"
        assert line.uid == "test-1"

    def test_create_patch(self):
        """Test creating a patch message."""
        converter = VisJsonLinesConverter()
        
        line = converter.create_patch(
            uid="test-1",
            ops=[JsonPatchOperation.add("/props/markdown", "more")],
        )
        
        assert line.type == VisMessageType.PATCH
        assert line.uid == "test-1"
        assert len(line.ops) == 1

    def test_create_incremental_text(self):
        """Test creating incremental text update."""
        converter = VisJsonLinesConverter()
        
        line = converter.create_incremental_text(
            uid="test-1",
            text=" more text",
        )
        
        assert line.type == VisMessageType.PATCH
        assert len(line.ops) == 1

    def test_create_complete(self):
        """Test creating a complete message."""
        converter = VisJsonLinesConverter()
        
        line = converter.create_complete("test-1")
        
        assert line.type == VisMessageType.COMPLETE
        assert line.uid == "test-1"

    def test_create_error(self):
        """Test creating an error message."""
        converter = VisJsonLinesConverter()
        
        line = converter.create_error("test-1", "Something went wrong")
        
        assert line.type == VisMessageType.ERROR
        assert line.message == "Something went wrong"

    def test_to_jsonl(self):
        """Test converting to JSON Lines format."""
        converter = VisJsonLinesConverter()
        
        lines = [
            converter.create_component("vis-thinking", "test-1", {"markdown": "test"}),
            converter.create_complete("test-1"),
        ]
        
        jsonl = converter.to_jsonl(lines)
        
        assert "\n" in jsonl
        assert "vis-thinking" in jsonl

    def test_from_jsonl(self):
        """Test parsing from JSON Lines format."""
        converter = VisJsonLinesConverter()
        
        jsonl = '{"type":"component","tag":"vis-thinking","uid":"test-1"}\n{"type":"complete","uid":"test-1"}'
        
        lines = converter.from_jsonl(jsonl)
        
        assert len(lines) == 2
        assert lines[0].type == VisMessageType.COMPONENT
        assert lines[1].type == VisMessageType.COMPLETE

    def test_to_markdown_compat(self):
        """Test converting to legacy markdown format."""
        converter = VisJsonLinesConverter()
        
        line = converter.create_component(
            tag="vis-thinking",
            uid="test-1",
            props={"markdown": "Thinking..."},
        )
        
        markdown = converter.to_markdown_compat(line)
        
        assert "```vis-thinking" in markdown
        assert "test-1" in markdown

    def test_from_markdown_compat(self):
        """Test parsing from legacy markdown format."""
        converter = VisJsonLinesConverter()
        
        markdown = '```vis-thinking\n{"uid":"test-1","type":"all","markdown":"test"}\n```'
        
        lines = converter.from_markdown_compat(markdown)
        
        assert len(lines) == 1
        assert lines[0].tag == "vis-thinking"
        assert lines[0].uid == "test-1"


class TestVisJsonLinesBuilder:
    """Tests for VisJsonLinesBuilder."""

    def test_component_method(self):
        """Test component method."""
        builder = VisJsonLinesBuilder()
        
        builder.component(
            tag="vis-thinking",
            uid="test-1",
            props={"markdown": "test"},
        )
        
        lines = builder.build()
        assert len(lines) == 1
        assert lines[0].tag == "vis-thinking"

    def test_thinking_method(self):
        """Test thinking method."""
        builder = VisJsonLinesBuilder()
        
        builder.thinking("test-1", "Thinking...")
        
        lines = builder.build()
        assert len(lines) == 1
        assert lines[0].tag == "vis-thinking"

    def test_thinking_incremental(self):
        """Test incremental thinking."""
        builder = VisJsonLinesBuilder()
        
        builder.thinking("test-1", "Thinking...", incremental=True)
        
        lines = builder.build()
        assert len(lines) == 1
        assert lines[0].type == VisMessageType.PATCH

    def test_message_method(self):
        """Test message method."""
        builder = VisJsonLinesBuilder()
        
        builder.message(
            uid="test-1",
            markdown="Hello!",
            role="assistant",
            name="AI",
        )
        
        lines = builder.build()
        assert len(lines) == 1
        assert lines[0].tag == "drsk-msg"

    def test_tool_methods(self):
        """Test tool methods."""
        builder = VisJsonLinesBuilder()
        
        builder.tool("tool-1", "search", {"query": "test"})
        builder.tool_complete("tool-1", "result")
        
        lines = builder.build()
        assert len(lines) == 2
        assert lines[0].tag == "vis-tool"
        assert lines[1].type == VisMessageType.PATCH

    def test_to_jsonl(self):
        """Test to_jsonl method."""
        builder = VisJsonLinesBuilder()
        
        builder.thinking("test-1", "Thinking...")
        builder.message("msg-1", "Hello!")
        
        jsonl = builder.to_jsonl()
        
        assert "\n" in jsonl

    def test_to_markdown_compat(self):
        """Test to_markdown_compat method."""
        builder = VisJsonLinesBuilder()
        
        builder.thinking("test-1", "Thinking...")
        
        markdown = builder.to_markdown_compat()
        
        assert "```vis-thinking" in markdown

    def test_clear(self):
        """Test clear method."""
        builder = VisJsonLinesBuilder()
        
        builder.thinking("test-1", "Thinking...")
        assert len(builder.build()) == 1
        
        builder.clear()
        assert len(builder.build()) == 0

    def test_vis_builder_function(self):
        """Test vis_builder function."""
        builder = vis_builder()
        
        assert isinstance(builder, VisJsonLinesBuilder)


class TestStreaming:
    """Tests for streaming functionality."""

    @pytest.mark.asyncio
    async def test_stream_to_jsonl(self):
        """Test streaming to JSON Lines."""
        converter = VisJsonLinesConverter()
        
        async def line_generator():
            yield VisJsonLine(type=VisMessageType.COMPONENT, tag="vis-thinking", uid="test-1")
            yield VisJsonLine(type=VisMessageType.COMPLETE, uid="test-1")
        
        results = []
        async for json_str in converter.stream_to_jsonl(line_generator()):
            results.append(json_str)
        
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_stream_from_jsonl(self):
        """Test streaming from JSON Lines."""
        converter = VisJsonLinesConverter()
        
        async def chunk_generator():
            yield '{"type":"component","tag":"vis-thinking","uid":"test-1"}\n'
            yield '{"type":"complete","uid":"test-1"}\n'
        
        results = []
        async for line in converter.stream_from_jsonl(chunk_generator()):
            results.append(line)
        
        assert len(results) == 2
        assert results[0].type == VisMessageType.COMPONENT