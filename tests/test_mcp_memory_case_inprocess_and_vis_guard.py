"""Regression tests for builtin memory_case tool/list (no SSE) and vis guards."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from derisk.component import SystemApp
from derisk.util import AppConfig
from derisk.util.fastapi import create_app
from derisk_serve.mcp.config import ServeConfig
from derisk_serve.mcp.service.service import Service


@pytest.fixture
def system_app_with_mcp() -> SystemApp:
    """Registers MCP Service so Service.get_instance(app) works like production."""
    app = SystemApp(create_app(), AppConfig(configs={}))
    app.register(Service, ServeConfig(memory_plugin_enabled=True))
    return app


@pytest.mark.asyncio
async def test_get_mcp_tool_list_memory_case_skips_sse(system_app_with_mcp: SystemApp) -> None:
    """Builtin memory_case must resolve tools in-process; SSE must not be opened."""
    import derisk_serve.agent.resource.tool.mcp_utils as mcp_utils

    cfg = MagicMock()
    cfg.SYSTEM_APP = system_app_with_mcp
    cfg.debug_mode = False

    async def _sse_must_not_run(*_a, **_kw):
        raise AssertionError("sse_client must not be used for builtin memory_case")

    with (
        patch.object(mcp_utils, "CFG", cfg),
        patch.object(mcp_utils, "tool_cache", {}),
        patch.object(mcp_utils, "sse_client", side_effect=_sse_must_not_run),
    ):
        res = await mcp_utils.get_mcp_tool_list(
            "memory_case",
            "http://this-url-should-not-be-contacted.invalid:9/mcp/sse",
            use_cache=False,
        )
    assert res is not None
    assert res.tools, "expected at least one tool from MemoryCasePluginService"
    names = {t.name for t in res.tools}
    assert names & {"memory_case_search", "memory_case_upsert"}


@pytest.mark.asyncio
async def test_get_mcp_tool_list_chinese_display_name_skips_sse(
    system_app_with_mcp: SystemApp,
) -> None:
    import derisk_serve.agent.resource.tool.mcp_utils as mcp_utils

    cfg = MagicMock()
    cfg.SYSTEM_APP = system_app_with_mcp
    cfg.debug_mode = False

    async def _sse_must_not_run(*_a, **_kw):
        raise AssertionError("sse_client must not be used for builtin display name")

    with (
        patch.object(mcp_utils, "CFG", cfg),
        patch.object(mcp_utils, "tool_cache", {}),
        patch.object(mcp_utils, "sse_client", side_effect=_sse_must_not_run),
    ):
        res = await mcp_utils.get_mcp_tool_list(
            "案例记忆",
            "http://ignored.invalid/mcp/sse",
            use_cache=False,
        )
    assert res.tools
    assert any(t.name.startswith("memory_case_") for t in res.tools)


@pytest.mark.asyncio
async def test_running_vis_build_no_keyerror_when_main_agent_none() -> None:
    from derisk_ext.vis.derisk.derisk_vis_window3_converter import (
        DeriskIncrVisWindow3Converter,
    )

    conv = DeriskIncrVisWindow3Converter()
    out = await conv._running_vis_build(
        gpt_msg=None,
        stream_msg={"role": "assistant", "content": "x"},
        senders_map={"real": MagicMock()},
        main_agent_name=None,
    )
    assert out is None


@pytest.mark.asyncio
async def test_running_vis_build_no_keyerror_when_name_not_in_senders() -> None:
    from derisk_ext.vis.derisk.derisk_vis_window3_converter import (
        DeriskIncrVisWindow3Converter,
    )

    conv = DeriskIncrVisWindow3Converter()
    out = await conv._running_vis_build(
        stream_msg="chunk",
        senders_map={"other": MagicMock()},
        main_agent_name="missing",
    )
    assert out is None


@pytest.mark.asyncio
async def test_running_vis_build_no_keyerror_when_senders_empty() -> None:
    from derisk_ext.vis.derisk.derisk_vis_window3_converter import (
        DeriskIncrVisWindow3Converter,
    )

    conv = DeriskIncrVisWindow3Converter()
    out = await conv._running_vis_build(
        stream_msg="chunk",
        senders_map={},
        main_agent_name="any",
    )
    assert out is None


@pytest.mark.asyncio
async def test_mcp_tool_pack_keeps_logical_name_without_gpts_row(
    system_app_with_mcp: SystemApp,
) -> None:
    """When no GptsTool row exists, _mcp_name stays self.name (not a random UUID)."""
    from mcp.types import ListToolsResult, Tool

    import derisk_serve.agent.resource.tool.mcp as mcp_mod

    fake_list = ListToolsResult(
        tools=[
            Tool(
                name="t_one",
                description="d",
                inputSchema={"type": "object", "properties": {}},
            )
        ]
    )

    cfg = MagicMock()
    cfg.SYSTEM_APP = system_app_with_mcp
    cfg.debug_mode = False

    span = MagicMock()
    span.trace_id = "test-trace"
    rt = MagicMock()

    with (
        patch.object(mcp_mod, "CFG", cfg),
        patch.object(mcp_mod, "gpts_tool_dao") as dao,
        patch.object(mcp_mod, "gpts_tool_messages_dao") as msg_dao,
        patch.object(
            mcp_mod,
            "get_mcp_tool_list",
            new=AsyncMock(return_value=fake_list),
        ) as get_list,
        patch("derisk.util.tracer.root_tracer", rt),
    ):
        rt.get_current_span.return_value = span
        rt.get_context_agent_id.return_value = None
        rt.get_context_user_id.return_value = None
        rt.get_context_entrance.return_value = None

        dao.get_tool_by_name.return_value = None
        dao.get_tool_by_tool_id.return_value = None
        msg_dao.create = MagicMock()

        pack = mcp_mod.MCPToolPack(
            "http://unused.example/mcp/sse",
            name="memory_case",
        )
        assert pack._mcp_name == "memory_case"
        await pack.preload_resource()

    assert pack._mcp_name == "memory_case"
    get_list.assert_awaited()
    call_kw = get_list.await_args
    assert call_kw is not None
    assert call_kw.args[0] == "memory_case", "get_mcp_tool_list must use logical MCP name"
