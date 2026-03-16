"""Tests for File I/O functionality.

This module tests the file input/output functionality including:
- File type configuration
- Sandbox file reference handling
- D-attach utilities
- Deliver file tool
"""

import pytest
import tempfile
import os
from pathlib import Path


class TestFileTypeConfig:
    """Tests for file type configuration."""

    def test_import_file_type_config(self):
        """Test that file type config can be imported."""
        from derisk_serve.agent.file_io.file_type_config import (
            FileProcessMode,
            FileTypeConfig,
            FileTypeConfigManager,
            get_file_process_mode,
            is_model_direct_file,
            is_sandbox_tool_file,
        )

        assert FileProcessMode.MODEL_DIRECT.value == "model_direct"
        assert FileProcessMode.SANDBOX_TOOL.value == "sandbox_tool"

    def test_default_config_image_types(self):
        """Test that image types are processed as MODEL_DIRECT."""
        from derisk_serve.agent.file_io.file_type_config import (
            DEFAULT_CONFIG,
            FileProcessMode,
        )

        assert DEFAULT_CONFIG.get_process_mode("test.jpg") == FileProcessMode.MODEL_DIRECT
        assert DEFAULT_CONFIG.get_process_mode("test.png") == FileProcessMode.MODEL_DIRECT
        assert DEFAULT_CONFIG.get_process_mode("test.gif") == FileProcessMode.MODEL_DIRECT

    def test_default_config_document_types(self):
        """Test that document types are processed as SANDBOX_TOOL."""
        from derisk_serve.agent.file_io.file_type_config import (
            DEFAULT_CONFIG,
            FileProcessMode,
        )

        assert DEFAULT_CONFIG.get_process_mode("test.pdf") == FileProcessMode.SANDBOX_TOOL
        assert DEFAULT_CONFIG.get_process_mode("test.docx") == FileProcessMode.SANDBOX_TOOL
        assert DEFAULT_CONFIG.get_process_mode("test.xlsx") == FileProcessMode.SANDBOX_TOOL

    def test_default_config_code_types(self):
        """Test that code types are processed as SANDBOX_TOOL."""
        from derisk_serve.agent.file_io.file_type_config import (
            DEFAULT_CONFIG,
            FileProcessMode,
        )

        assert DEFAULT_CONFIG.get_process_mode("test.py") == FileProcessMode.SANDBOX_TOOL
        assert DEFAULT_CONFIG.get_process_mode("test.js") == FileProcessMode.SANDBOX_TOOL
        assert DEFAULT_CONFIG.get_process_mode("test.go") == FileProcessMode.SANDBOX_TOOL

    def test_get_file_process_mode(self):
        """Test convenience function for getting file process mode."""
        from derisk_serve.agent.file_io.file_type_config import (
            get_file_process_mode,
            FileProcessMode,
        )

        assert get_file_process_mode("image.jpg") == FileProcessMode.MODEL_DIRECT
        assert get_file_process_mode("document.pdf") == FileProcessMode.SANDBOX_TOOL


class TestSandboxFileRef:
    """Tests for SandboxFileRef."""

    def test_sandbox_file_ref_creation(self):
        """Test creating a SandboxFileRef."""
        from derisk_serve.agent.file_io.sandbox_file_ref import SandboxFileRef

        ref = SandboxFileRef(
            file_name="test.pdf",
            url="https://example.com/test.pdf",
            file_type="pdf",
            process_mode="sandbox_tool",
        )

        assert ref.file_name == "test.pdf"
        assert ref.url == "https://example.com/test.pdf"
        assert ref.file_type == "pdf"
        assert ref.process_mode == "sandbox_tool"

    def test_sandbox_file_ref_to_dict(self):
        """Test converting SandboxFileRef to dictionary."""
        from derisk_serve.agent.file_io.sandbox_file_ref import SandboxFileRef

        ref = SandboxFileRef(
            file_name="test.pdf",
            url="https://example.com/test.pdf",
        )

        d = ref.to_dict()
        assert d["file_name"] == "test.pdf"
        assert d["url"] == "https://example.com/test.pdf"
        assert d["process_mode"] == "sandbox_tool"

    def test_sandbox_file_ref_get_sandbox_path(self):
        """Test getting sandbox path."""
        from derisk_serve.agent.file_io.sandbox_file_ref import SandboxFileRef

        ref = SandboxFileRef(
            file_name="test.pdf",
            url="https://example.com/test.pdf",
        )

        path = ref.get_sandbox_path()
        assert "test.pdf" in path


class TestDAttachUtils:
    """Tests for d-attach utilities."""

    def test_create_dattach_content(self):
        """Test creating d-attach content."""
        from derisk_serve.agent.file_io.dattach_utils import create_dattach_content

        content = create_dattach_content(
            file_name="report.md",
            file_url="https://example.com/report.md",
            file_size=1024,
            file_type="deliverable",
        )

        assert content["file_name"] == "report.md"
        assert content["file_url"] == "https://example.com/report.md"
        assert content["file_size"] == 1024
        assert content["file_type"] == "deliverable"

    def test_create_dattach_list_content(self):
        """Test creating d-attach list content."""
        from derisk_serve.agent.file_io.dattach_utils import create_dattach_list_content

        content = create_dattach_list_content(
            files=[
                {"file_name": "report.md", "file_url": "https://example.com/report.md"},
                {"file_name": "data.csv", "file_url": "https://example.com/data.csv"},
            ],
            title="Delivered Files",
        )

        assert content["title"] == "Delivered Files"
        assert content["total_count"] == 2
        assert len(content["files"]) == 2

    def test_render_dattach(self):
        """Test rendering d-attach component."""
        from derisk_serve.agent.file_io.dattach_utils import render_dattach

        output = render_dattach(
            file_name="report.md",
            file_url="https://example.com/report.md",
            file_size=1024,
        )

        assert "[d-attach:" in output
        assert "report.md" in output

    def test_render_dattach_list(self):
        """Test rendering d-attach list component."""
        from derisk_serve.agent.file_io.dattach_utils import render_dattach_list

        output = render_dattach_list(
            files=[
                {"file_name": "report.md", "file_url": "https://example.com/report.md"},
            ],
            title="Test Files",
        )

        assert "[d-attach-list:" in output
        assert "Test Files" in output

    def test_dattach_builder(self):
        """Test DAttachBuilder."""
        from derisk_serve.agent.file_io.dattach_utils import DAttachBuilder

        output = (
            DAttachBuilder()
            .file_name("report.md")
            .file_url("https://example.com/report.md")
            .file_size(1024)
            .description("Test Report")
            .build()
        )

        assert "[d-attach:" in output
        assert "report.md" in output


class TestFileIOIntegration:
    """Tests for file I/O integration helpers."""

    def test_import_core_integration(self):
        """Test importing core file I/O integration."""
        from derisk.agent.core.file_io_integration import (
            get_file_storage_client,
            create_agent_file_system,
            process_user_files,
            FileIOContext,
            initialize_file_io_for_agent,
        )

    def test_import_core_v2_integration(self):
        """Test importing core_v2 file I/O integration."""
        from derisk.agent.core_v2.file_io_manager import (
            DeliverableFile,
            CoreV2FileIOManager,
            create_file_io_manager,
        )


class TestDeliverFileTool:
    """Tests for deliver file tool."""

    def test_deliver_file_tool_import(self):
        """Test that deliver file tool can be imported."""
        from derisk.agent.tools.builtin.sandbox.deliver_file import (
            DeliverFileTool,
            _validate_string_param,
            _get_mime_type,
        )

        tool = DeliverFileTool()
        assert tool.name == "deliver_file"

    def test_validate_string_param(self):
        """Test string parameter validation."""
        from derisk.agent.tools.builtin.sandbox.deliver_file import _validate_string_param

        assert _validate_string_param("test", "field") is None
        assert _validate_string_param(None, "field") == "Error: field cannot be empty"
        assert _validate_string_param("", "field") == "Error: field cannot be an empty string"

    def test_get_mime_type(self):
        """Test MIME type detection."""
        from derisk.agent.tools.builtin.sandbox.deliver_file import _get_mime_type

        assert _get_mime_type("test.pdf") == "application/pdf"
        assert _get_mime_type("test.txt") == "text/plain"
        assert _get_mime_type("test.json") == "application/json"


class TestLocalFileClient:
    """Tests for LocalFileClient."""

    @pytest.mark.asyncio
    async def test_local_file_client_import(self):
        """Test that LocalFileClient can be imported."""
        from derisk_ext.sandbox.local.file_client import LocalFileClient

    @pytest.mark.asyncio
    async def test_local_file_client_operations(self):
        """Test LocalFileClient file operations."""
        from derisk_ext.sandbox.local.file_client import LocalFileClient

        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox_dir = os.path.join(tmpdir, "sandbox_001")
            os.makedirs(sandbox_dir)

            class MockRuntime:
                base_dir = tmpdir

            client = LocalFileClient(
                sandbox_id="sandbox_001",
                work_dir="/workspace",
                runtime=MockRuntime(),
            )

            test_file_path = os.path.join(sandbox_dir, "test.txt")
            test_content = "Hello, World!"

            await client.write("test.txt", test_content, overwrite=True)
            assert os.path.exists(test_file_path)

            file_info = await client.read("test.txt")
            assert file_info.content == test_content

            exists = await client.exists("test.txt")
            assert exists is True

            await client.remove("test.txt")
            exists = await client.exists("test.txt")
            assert exists is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])