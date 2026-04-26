"""Tests for build_user_context and format_permissions_summary in auth.py."""

import pytest

from derisk_serve.utils.auth import UserRequest, build_user_context, format_permissions_summary


# === format_permissions_summary Tests ===


def test_format_permissions_summary_rbac_disabled():
    result = format_permissions_summary(None, rbac_enabled=False)
    assert result == "全部权限 (RBAC 未启用)"


def test_format_permissions_summary_empty_permissions():
    result = format_permissions_summary({}, rbac_enabled=True)
    assert result == "none"


def test_format_permissions_summary_none_permissions():
    result = format_permissions_summary(None, rbac_enabled=True)
    assert result == "none"


def test_format_permissions_summary_single_resource():
    result = format_permissions_summary(
        {"agent": ["read", "chat"]}, rbac_enabled=True
    )
    assert result == "agent: read, chat"


def test_format_permissions_summary_multiple_resources():
    result = format_permissions_summary(
        {"agent": ["read", "chat"], "knowledge": ["read"], "tool": ["execute"]},
        rbac_enabled=True,
    )
    assert "agent: read, chat" in result
    assert "knowledge: read" in result
    assert "tool: execute" in result


def test_format_permissions_summary_empty_actions():
    result = format_permissions_summary(
        {"agent": []}, rbac_enabled=True
    )
    # Empty actions list should be skipped
    assert result == "none"


# === build_user_context Tests ===


def test_build_user_context_full_rbac():
    user = UserRequest(
        user_id="3",
        real_name="Alice",
        email="alice@example.com",
        avatar_url="https://example.com/avatar.png",
        role="editor",
        roles=["editor"],
        permissions={"agent": ["read", "chat"], "knowledge": ["read"]},
    )
    result = build_user_context(user, rbac_enabled=True)

    assert result["user_id"] == "3"
    assert result["name"] == "Alice"
    assert result["email"] == "alice@example.com"
    assert result["avatar_url"] == "https://example.com/avatar.png"
    assert result["role"] == "editor"
    assert result["roles"] == ["editor"]
    assert result["permissions_map"] == {"agent": ["read", "chat"], "knowledge": ["read"]}
    assert "agent: read, chat" in result["permissions_summary"]
    assert result["rbac_enabled"] is True


def test_build_user_context_rbac_disabled():
    user = UserRequest(
        user_id="001",
        nick_name="derisk",
        role="admin",
    )
    result = build_user_context(user, rbac_enabled=False)

    assert result["user_id"] == "001"
    assert result["name"] == "derisk"
    assert result["email"] is None
    assert result["avatar_url"] is None
    assert result["role"] == "admin"
    assert result["roles"] == ["admin"]
    assert result["permissions_map"] is None
    assert result["permissions_summary"] == "全部权限 (RBAC 未启用)"
    assert result["rbac_enabled"] is False


def test_build_user_context_name_fallback():
    # real_name takes priority over nick_name
    user = UserRequest(user_id="5", nick_name="Bob", real_name="Robert")
    result = build_user_context(user, rbac_enabled=True)
    assert result["name"] == "Robert"

    # Falls back to nick_name when real_name is None
    user2 = UserRequest(user_id="5", nick_name="Bob")
    result2 = build_user_context(user2, rbac_enabled=True)
    assert result2["name"] == "Bob"

    # Falls back to user_id when both are None
    user3 = UserRequest(user_id="5")
    result3 = build_user_context(user3, rbac_enabled=True)
    assert result3["name"] == "5"


def test_build_user_context_no_permissions():
    user = UserRequest(user_id="10", real_name="Viewer", role="viewer")
    result = build_user_context(user, rbac_enabled=True)

    assert result["role"] == "viewer"
    assert result["roles"] == ["viewer"]  # Falls back to [role]
    assert result["permissions_map"] is None
    assert result["permissions_summary"] == "none"


# === ToolContext user_context field Tests ===


def test_tool_context_user_context_default():
    from derisk.agent.tools.context import ToolContext

    ctx = ToolContext()
    assert ctx.user_context is None


def test_tool_context_user_context_set():
    from derisk.agent.tools.context import ToolContext

    user_ctx = {"user_id": "3", "name": "Alice", "role": "editor"}
    ctx = ToolContext(user_context=user_ctx)
    assert ctx.user_context == user_ctx


def test_tool_context_user_context_in_dict():
    from derisk.agent.tools.context import ToolContext

    user_ctx = {"user_id": "3", "name": "Alice", "role": "editor"}
    ctx = ToolContext(user_context=user_ctx)
    d = ctx.to_dict()
    assert d["user_context"] == user_ctx