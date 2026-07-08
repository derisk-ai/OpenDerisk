"""Tests for dispatch_file_to_sandbox with derisk-fs:// URIs."""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if "derisk_app.config" not in sys.modules:
    sys.modules["derisk_app"] = MagicMock()
    sys.modules["derisk_app.config"] = MagicMock()

from derisk_serve.agent.utils.file_dispatch import dispatch_file_to_sandbox


@pytest.mark.asyncio
async def test_dispatch_derisk_fs_reads_via_storage_client():
    """derisk-fs:// URI 无法生成公开 URL 时，应直接通过 FileStorageClient 读取。"""
    fake_file = MagicMock()
    fake_file.read = MagicMock(return_value=b"# Markdown content")
    fake_file.close = MagicMock()

    fake_storage_system = MagicMock()
    fake_storage_system.get_public_url = MagicMock(return_value=None)
    fake_storage_system.get_file = MagicMock(return_value=(fake_file, MagicMock()))

    fake_file_storage_client = MagicMock()
    fake_file_storage_client.get_public_url = MagicMock(return_value=None)
    fake_file_storage_client.get_file = MagicMock(return_value=(fake_file, MagicMock()))
    fake_file_storage_client.storage_system = fake_storage_system

    sandbox_client = MagicMock()
    sandbox_client.work_dir = "/tmp/sandbox"
    sandbox_client.file = MagicMock()
    sandbox_client.file.create = AsyncMock(return_value=None)

    result = await dispatch_file_to_sandbox(
        file_path="derisk-fs://local/derisk_app_file/abc-123",
        file_name="doc.md",
        sandbox_client=sandbox_client,
        file_storage_client=fake_file_storage_client,
    )

    assert result == "/tmp/sandbox/uploads/doc.md"
    fake_file_storage_client.get_public_url.assert_called_once_with(
        "derisk-fs://local/derisk_app_file/abc-123"
    )
    fake_file_storage_client.get_file.assert_called_once_with(
        "derisk-fs://local/derisk_app_file/abc-123"
    )
    fake_file.read.assert_called_once()
    fake_file.close.assert_called_once()
    sandbox_client.file.create.assert_called_once_with(
        "/tmp/sandbox/uploads/doc.md", "# Markdown content", overwrite=True
    )


@pytest.mark.asyncio
async def test_dispatch_derisk_fs_uses_public_url_when_available():
    """derisk-fs:// URI 能生成公开 HTTP URL 时，应通过 httpx 下载。"""
    fake_response = MagicMock()
    fake_response.content = b"# Public content"

    fake_file_storage_client = MagicMock()
    fake_file_storage_client.get_public_url = MagicMock(
        return_value="http://example.com/public.md"
    )

    sandbox_client = MagicMock()
    sandbox_client.work_dir = "/tmp/sandbox"
    sandbox_client.file = MagicMock()
    sandbox_client.file.create = AsyncMock(return_value=None)

    with patch(
        "derisk_serve.agent.utils.file_dispatch.httpx.AsyncClient"
    ) as mock_client:
        fake_client = MagicMock()
        fake_client.get = AsyncMock(return_value=fake_response)
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value = fake_client

        result = await dispatch_file_to_sandbox(
            file_path="derisk-fs://local/derisk_app_file/abc-123",
            file_name="public.md",
            sandbox_client=sandbox_client,
            file_storage_client=fake_file_storage_client,
        )

    assert result == "/tmp/sandbox/uploads/public.md"
    sandbox_client.file.create.assert_called_once_with(
        "/tmp/sandbox/uploads/public.md", "# Public content", overwrite=True
    )
