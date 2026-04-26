"""Tests for user identity tools (get_user_info, get_user_permissions)."""

import pytest

from derisk.agent.tools.builtin.user_identity import (
    GetUserInfoTool,
    GetUserPermissionsTool,
    _extract_user_context,
)
from derisk.agent.tools.context import ToolContext


@pytest.fixture
def user_info_tool():
    return GetUserInfoTool()


@pytest.fixture
def user_permissions_tool():
    return GetUserPermissionsTool()


@pytest.fixture
def full_user_context():
    return {
        "user_id": "3",
        "name": "Alice",
        "email": "alice@example.com",
        "avatar_url": "https://example.com/avatar.png",
        "role": "editor",
        "roles": ["editor"],
        "permissions_map": {"agent": ["read", "chat"], "knowledge": ["read"]},
        "permissions_summary": "agent: read, chat; knowledge: read",
        "rbac_enabled": True,
    }


@pytest.fixture
def partial_user_context():
    return {
        "user_id": "5",
        "name": "Bob",
        "email": None,
        "avatar_url": None,
        "role": "viewer",
        "roles": ["viewer"],
        "permissions_map": {"agent": ["read"]},
        "permissions_summary": "agent: read",
        "rbac_enabled": True,
    }


@pytest.fixture
def rbac_disabled_context():
    return {
        "user_id": "001",
        "name": "derisk",
        "email": None,
        "avatar_url": None,
        "role": "admin",
        "roles": ["admin"],
        "permissions_map": None,
        "permissions_summary": "全部权限 (RBAC 未启用)",
        "rbac_enabled": False,
    }


# === GetUserInfoTool Tests ===


@pytest.mark.asyncio
async def test_get_user_info_full_context(user_info_tool, full_user_context):
    context = ToolContext(user_id="3", user_context=full_user_context)
    result = await user_info_tool.execute({}, context)
    assert result.success is True
    assert "Alice" in result.output
    assert "editor" in result.output
    assert "alice@example.com" in result.output
    assert "https://example.com/avatar.png" in result.output


@pytest.mark.asyncio
async def test_get_user_info_partial_context(user_info_tool, partial_user_context):
    context = ToolContext(user_id="5", user_context=partial_user_context)
    result = await user_info_tool.execute({}, context)
    assert result.success is True
    assert "Bob" in result.output
    assert "viewer" in result.output
    assert "未设置" in result.output


@pytest.mark.asyncio
async def test_get_user_info_no_context(user_info_tool):
    context = ToolContext(user_id="3")
    result = await user_info_tool.execute({}, context)
    assert result.success is True
    assert "用户管理未启用" in result.output


@pytest.mark.asyncio
async def test_get_user_info_none_context(user_info_tool):
    result = await user_info_tool.execute({}, None)
    assert result.success is True
    assert "用户管理未启用" in result.output


@pytest.mark.asyncio
async def test_get_user_info_rbac_disabled(user_info_tool, rbac_disabled_context):
    context = ToolContext(user_id="001", user_context=rbac_disabled_context)
    result = await user_info_tool.execute({}, context)
    assert result.success is True
    assert "derisk" in result.output
    assert "管理员模式" in result.output or "未启用" in result.output


# === GetUserPermissionsTool Tests ===


@pytest.mark.asyncio
async def test_get_user_permissions_full_context(
    user_permissions_tool, full_user_context
):
    context = ToolContext(user_id="3", user_context=full_user_context)
    result = await user_permissions_tool.execute({}, context)
    assert result.success is True
    assert "editor" in result.output
    assert "Agent 应用" in result.output
    assert "查看" in result.output
    assert "对话" in result.output


@pytest.mark.asyncio
async def test_get_user_permissions_limited(
    user_permissions_tool, partial_user_context
):
    context = ToolContext(user_id="5", user_context=partial_user_context)
    result = await user_permissions_tool.execute({}, context)
    assert result.success is True
    assert "viewer" in result.output
    assert "Agent 应用" in result.output


@pytest.mark.asyncio
async def test_get_user_permissions_no_context(user_permissions_tool):
    context = ToolContext(user_id="3")
    result = await user_permissions_tool.execute({}, context)
    assert result.success is True
    assert "管理员模式" in result.output


@pytest.mark.asyncio
async def test_get_user_permissions_none_context(user_permissions_tool):
    result = await user_permissions_tool.execute({}, None)
    assert result.success is True
    assert "管理员模式" in result.output or "全部权限" in result.output


@pytest.mark.asyncio
async def test_get_user_permissions_rbac_disabled(
    user_permissions_tool, rbac_disabled_context
):
    context = ToolContext(user_id="001", user_context=rbac_disabled_context)
    result = await user_permissions_tool.execute({}, context)
    assert result.success is True
    assert "管理员" in result.output
    assert "RBAC 未启用" in result.output or "全部权限" in result.output


# === Tool Metadata Tests ===


def test_get_user_info_metadata(user_info_tool):
    meta = user_info_tool.metadata
    assert meta.name == "get_user_info"
    assert meta.category == "utility"
    assert meta.risk_level == "safe"
    assert meta.requires_permission is False


def test_get_user_permissions_metadata(user_permissions_tool):
    meta = user_permissions_tool.metadata
    assert meta.name == "get_user_permissions"
    assert meta.category == "utility"
    assert meta.risk_level == "safe"
    assert meta.requires_permission is False


def test_get_user_info_no_required_params(user_info_tool):
    params = user_info_tool._define_parameters()
    assert params["type"] == "object"
    assert params.get("required", []) == []


def test_get_user_permissions_no_required_params(user_permissions_tool):
    params = user_permissions_tool._define_parameters()
    assert params["type"] == "object"
    assert params.get("required", []) == []


# === _extract_user_context Tests ===


def test_extract_user_context_from_tool_context(full_user_context):
    ctx = ToolContext(user_context=full_user_context)
    result = _extract_user_context(ctx)
    assert result == full_user_context


def test_extract_user_context_from_dict(full_user_context):
    ctx = {"user_context": full_user_context, "sandbox_manager": None}
    result = _extract_user_context(ctx)
    assert result == full_user_context


def test_extract_user_context_from_none():
    result = _extract_user_context(None)
    assert result is None


def test_extract_user_context_from_empty_dict():
    result = _extract_user_context({})
    assert result is None


def test_extract_user_context_from_tool_context_without_user_context():
    ctx = ToolContext(user_id="3")
    result = _extract_user_context(ctx)
    assert result is None


# === Dict context integration Tests (simulates ToolAction._execute_tool flow) ===


@pytest.mark.asyncio
async def test_get_user_info_with_dict_context(user_info_tool, full_user_context):
    """Simulate the actual execution path where context is a plain dict."""
    context_dict = {"user_context": full_user_context}
    result = await user_info_tool.execute({}, context_dict)
    assert result.success is True
    assert "Alice" in result.output
    assert "editor" in result.output


@pytest.mark.asyncio
async def test_get_user_permissions_with_dict_context(
    user_permissions_tool, full_user_context
):
    """Simulate the actual execution path where context is a plain dict."""
    context_dict = {"user_context": full_user_context}
    result = await user_permissions_tool.execute({}, context_dict)
    assert result.success is True
    assert "editor" in result.output