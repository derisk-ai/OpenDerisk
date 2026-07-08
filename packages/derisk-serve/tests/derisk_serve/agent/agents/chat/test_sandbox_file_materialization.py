"""Tests for sandbox file materialization from uploaded file references."""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if "derisk_app.config" not in sys.modules:
    sys.modules["derisk_app"] = MagicMock()
    sys.modules["derisk_app.config"] = MagicMock()

from derisk_serve.agent.agents.chat.agent_chat import (
    _materialize_sandbox_file_refs,
)


def _make_fake_file_storage_client(file_content: bytes = b"hello world"):
    """Build a FileStorageClient whose download_file writes file_content."""
    fake_metadata = MagicMock()
    fake_metadata.file_name = "test.md"

    def fake_download_file(uri, dest_path=None, dest_dir=None, cache=True):
        with open(dest_path, "wb") as f:
            f.write(file_content)
        return dest_path, fake_metadata

    client = MagicMock()
    client.download_file = MagicMock(wraps=fake_download_file)
    return client


async def _passthrough_blocking_func_to_async(system_app, func, *args, **kwargs):
    """Run the wrapped sync function directly in tests."""
    return func(*args, **kwargs)


@pytest.mark.asyncio
async def test_materialize_derisk_fs_ref_writes_file_to_sandbox(tmp_path):
    """derisk-fs:// URI 应该被直接写入沙箱，而不是依赖公开 HTTP URL。"""
    system_app = MagicMock()
    sandbox_client = MagicMock()
    sandbox_client.work_dir = str(tmp_path)

    ref = {
        "file_name": "test.md",
        "url": "derisk-fs://local/derisk_app_file/abc-123",
    }

    fake_file_storage_client = _make_fake_file_storage_client(b"# Hello")

    with patch(
        "derisk_serve.agent.agents.chat.agent_chat.FileStorageClient.get_instance",
        return_value=fake_file_storage_client,
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.blocking_func_to_async",
        side_effect=_passthrough_blocking_func_to_async,
    ):
        updated_refs = await _materialize_sandbox_file_refs(
            system_app=system_app,
            sandbox_client=sandbox_client,
            sandbox_file_refs=[ref],
        )

    expected_path = str(tmp_path / "uploads" / "test.md")
    assert len(updated_refs) == 1
    assert expected_path in updated_refs[0]
    assert ref["sandbox_path"] == expected_path
    assert (tmp_path / "uploads" / "test.md").read_bytes() == b"# Hello"
    fake_file_storage_client.download_file.assert_called_once_with(
        "derisk-fs://local/derisk_app_file/abc-123",
        dest_path=expected_path,
    )


@pytest.mark.asyncio
async def test_materialize_http_ref_downloads_via_httpx(tmp_path):
    """http:// URL 继续通过 httpx 下载。"""
    system_app = MagicMock()
    sandbox_client = MagicMock()
    sandbox_client.work_dir = str(tmp_path)

    ref = {
        "file_name": "remote.md",
        "url": "http://example.com/remote.md",
    }

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = b"# Remote"

    fake_httpx_client = MagicMock()
    fake_httpx_client.get = AsyncMock(return_value=fake_response)
    fake_async_client = MagicMock()
    fake_async_client.__aenter__ = AsyncMock(return_value=fake_httpx_client)
    fake_async_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "derisk_serve.agent.agents.chat.agent_chat.FileStorageClient.get_instance",
        return_value=None,
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.httpx.AsyncClient",
        return_value=fake_async_client,
    ):
        updated_refs = await _materialize_sandbox_file_refs(
            system_app=system_app,
            sandbox_client=sandbox_client,
            sandbox_file_refs=[ref],
        )

    expected_path = str(tmp_path / "uploads" / "remote.md")
    assert len(updated_refs) == 1
    assert ref["sandbox_path"] == expected_path
    fake_httpx_client.get.assert_awaited_once_with("http://example.com/remote.md")
    assert (tmp_path / "uploads" / "remote.md").read_bytes() == b"# Remote"
