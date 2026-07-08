"""Gap #178: _start_app 深度传播测试。

验证 parent_depth 传入时，子 agent 的 AgentContext.extra["subagent_depth"] = parent_depth + 1。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from derisk.agent.core.agent import AgentContext


@pytest.mark.asyncio
async def test_start_app_propagates_parent_depth_to_child_context():
    """parent_depth=2 → child AgentContext.extra["subagent_depth"] = 3。"""
    from derisk_serve.agent.resource.app import GptAppResource

    captured_contexts: list = []

    async def fake_create_agent_by_app_code(gpts_app, conv_uid=None, context=None, **kwargs):
        captured_contexts.append(context)
        mock_agent = MagicMock()
        mock_agent.generate_reply = AsyncMock(return_value=MagicMock(content="ok"))
        return mock_agent

    mock_gpts_app = MagicMock(app_code="sub_app", app_name="Sub", language="zh")

    with patch(
        "derisk_serve.agent.resource.app.get_app_manager"
    ) as mock_app_mgr:
        mock_app_mgr.return_value.get_app.return_value = mock_gpts_app
        mock_app_mgr.return_value.create_agent_by_app_code = fake_create_agent_by_app_code

        resource = GptAppResource(name="sub_app", app_code="sub_app")
        await resource._start_app(
            user_input="hi",
            sender=MagicMock(),
            conv_uid="sub_conv_1",
            parent_depth=2,
        )

    assert len(captured_contexts) == 1
    ctx = captured_contexts[0]
    assert ctx is not None
    assert ctx.extra is not None
    assert ctx.extra.get("subagent_depth") == 3, (
        f"expected depth=3 (parent 2 + 1), got {ctx.extra.get('subagent_depth')}"
    )


@pytest.mark.asyncio
async def test_start_app_no_parent_depth_keeps_default():
    """parent_depth=None → 不写入 extra，保持默认。"""
    from derisk_serve.agent.resource.app import GptAppResource

    captured_contexts: list = []

    async def fake_create_agent_by_app_code(gpts_app, conv_uid=None, context=None, **kwargs):
        captured_contexts.append(context)
        mock_agent = MagicMock()
        mock_agent.generate_reply = AsyncMock(return_value=MagicMock(content="ok"))
        return mock_agent

    mock_gpts_app = MagicMock(app_code="sub_app", app_name="Sub", language="zh")

    with patch(
        "derisk_serve.agent.resource.app.get_app_manager"
    ) as mock_app_mgr:
        mock_app_mgr.return_value.get_app.return_value = mock_gpts_app
        mock_app_mgr.return_value.create_agent_by_app_code = fake_create_agent_by_app_code

        resource = GptAppResource(name="sub_app", app_code="sub_app")
        await resource._start_app(
            user_input="hi",
            sender=MagicMock(),
            conv_uid="sub_conv_2",
            parent_depth=None,
        )

    assert len(captured_contexts) == 1
    ctx = captured_contexts[0]
    # parent_depth=None → child_context is None → create_agent_by_app_code 内部默认创建
    assert ctx is None
