"""Tests: image_url that cannot be confirmed as an image is downgraded to SANDBOX."""
import sys
from unittest.mock import MagicMock, patch

import pytest

if "derisk_app.config" not in sys.modules:
    sys.modules["derisk_app"] = MagicMock()
    sys.modules["derisk_app.config"] = MagicMock()

from derisk_serve.agent.file_io.file_type_config import FileProcessMode
from derisk_serve.agent.file_io.sandbox_file_ref import (
    looks_like_image,
    process_user_input_file,
)

_PROCESS_MODE_PATH = "derisk_serve.agent.file_io.file_type_config.get_file_process_mode"


def _image_url_input(file_name: str, url: str = "derisk-fs://_/bk/id1") -> dict:
    return {"type": "image_url", "image_url": {"url": url, "file_name": file_name}}


@pytest.mark.asyncio
async def test_non_image_claimed_as_image_url_downgrades_to_sandbox():
    """image_url + pdf(被强制 MODEL_DIRECT)→ 守卫降级 SANDBOX_TOOL。"""
    with patch(_PROCESS_MODE_PATH, return_value=FileProcessMode.MODEL_DIRECT):
        multimodal, ref, err = await process_user_input_file(
            _image_url_input("report.pdf")
        )
    assert multimodal is None
    assert ref is not None
    assert ref.process_mode == "sandbox_tool"
    assert err is None


@pytest.mark.asyncio
async def test_extensionless_image_url_with_no_mime_downgrades_to_sandbox():
    """无扩展名 + 无 mime(去硬编码 jpeg 后)→ 降级沙箱。"""
    with patch(_PROCESS_MODE_PATH, return_value=FileProcessMode.MODEL_DIRECT):
        multimodal, ref, err = await process_user_input_file(
            _image_url_input("image_abc12345")
        )
    assert multimodal is None
    assert ref is not None
    assert ref.process_mode == "sandbox_tool"


@pytest.mark.asyncio
async def test_confirmed_image_stays_multimodal():
    """正常 .png image_url → 仍走多模态,不降级。"""
    with patch(_PROCESS_MODE_PATH, return_value=FileProcessMode.MODEL_DIRECT):
        multimodal, ref, err = await process_user_input_file(
            _image_url_input("cat.png")
        )
    assert multimodal is not None
    assert multimodal["type"] == "image_url"
    assert ref is None
    assert err is None


@pytest.mark.asyncio
async def test_jpeg_extension_stays_multimodal():
    """.jpeg 扩展名 → 仍多模态(扩展名路径生效)。"""
    inp = {
        "type": "image_url",
        "image_url": {"url": "derisk-fs://_/bk/id2", "file_name": "photo.jpeg"},
    }
    with patch(_PROCESS_MODE_PATH, return_value=FileProcessMode.MODEL_DIRECT):
        multimodal, ref, err = await process_user_input_file(inp)
    assert multimodal is not None and ref is None


@pytest.mark.asyncio
async def test_file_url_model_direct_forced_to_sandbox():
    """file_url + MODEL_DIRECT → 守卫 else 分支强制 SANDBOX_TOOL。"""
    inp = {
        "type": "file_url",
        "file_url": {"url": "derisk-fs://_/bk/id3", "file_name": "data.csv"},
    }
    with patch(_PROCESS_MODE_PATH, return_value=FileProcessMode.MODEL_DIRECT):
        multimodal, ref, err = await process_user_input_file(inp)
    assert multimodal is None
    assert ref is not None
    assert ref.process_mode == "sandbox_tool"


@pytest.mark.asyncio
async def test_pdf_defaults_to_sandbox_without_mock():
    """默认配置下 .pdf → SANDBOX_TOOL(get_file_process_mode 本就如此)。"""
    multimodal, ref, err = await process_user_input_file(_image_url_input("r.pdf"))
    assert multimodal is None
    assert ref is not None


def test_looks_like_image_helper():
    assert looks_like_image("a.png", None) is True
    assert looks_like_image("a.JPEG", None) is True
    assert looks_like_image("abc", "image/jpeg") is True
    assert looks_like_image("r.pdf", "application/pdf") is False
    assert looks_like_image("abc123", None) is False
    assert looks_like_image("abc", "application/octet-stream") is False
    assert looks_like_image("", None) is False