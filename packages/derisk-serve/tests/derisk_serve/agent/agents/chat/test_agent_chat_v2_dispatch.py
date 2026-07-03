"""Integration tests for V2 agent dispatch in agent_chat._inner_chat."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from derisk.core import HumanMessage
from derisk.agent import AgentContext, AgentMemory
from derisk.agent.core.schema import Status
from derisk_serve.agent.agents.chat.agent_chat import AgentChat
from derisk_serve.building.app.api.schema_app import GptsApp


async def _mock_ai_create(**kwargs):
    """Mock AIWrapper.create — yields two tokens then metrics.

    Uses AgentLLMOut (production type yielded by AIWrapper.create), not
    ModelOutput. AgentLLMOut exposes .content/.metrics/.tool_calls — the
    adapter reads these attributes.
    """
    from derisk.agent.util.llm.llm_client import AgentLLMOut
    from derisk.core.interface.llm import ModelInferenceMetrics

    yield AgentLLMOut(content="Hello", thinking_content=None)
    yield AgentLLMOut(content=" world", thinking_content=None)
    yield AgentLLMOut(
        content="",
        thinking_content=None,
        metrics=ModelInferenceMetrics(
            prompt_tokens=5,
            completion_tokens=2,
            total_tokens=7,
        ),
    )


def _make_v2_gpts_app():
    """Create a minimal GptsApp with agent_version='v2'."""
    from derisk_serve.building.config.api.schemas import LLMResource

    app = GptsApp.model_construct(
        app_code="test_v2_app",
        app_name="Test V2 App",
        agent="BaizeAgent",
        agent_version="v2",
        language="zh",
        team_mode="single_agent",
        llm_config=LLMResource.model_construct(
            llm_strategy="default",
            llm_strategy_value={},
            llm_param={},
        ),
    )
    return app


def _make_cache_mock():
    """Create a mock ConversationCache with an asyncio.Queue channel."""
    cache = MagicMock()
    cache.channel = asyncio.Queue()
    cache.stop_flag = False
    # V2 dispatch reads cache.memory_bundle; explicit None matches production
    # when no bundle has been registered (cache is a MagicMock, so getattr
    # auto-creates a child mock that would otherwise be mistaken for a bundle).
    cache.memory_bundle = None
    return cache


class _ConcreteAgentChat(AgentChat):
    """Concrete AgentChat for testing — implements the abstract chat method."""

    async def chat(self, *args, **kwargs):
        raise NotImplementedError("Test-only subclass")


class TestV2Dispatch:
    """V2 agent dispatch: verify V2 path is taken, BAIZE path is skipped."""

    @pytest.fixture
    def agent_chat(self):
        """Create a minimal AgentChat with mocked dependencies."""
        system_app = MagicMock()
        system_app.config = MagicMock()
        system_app.config.configs = {}

        from derisk_serve.agent.agents.derisks_memory import (
            MetaDerisksPlansMemory,
            MetaDerisksMessageMemory,
            MetaAgentSystemMessageMemory,
            MetaDerisksWorkLogStorage,
            MetaDerisksKanbanStorage,
            MetaDerisksTodoStorage,
            MetaDerisksFileMetadataStorage,
        )
        from derisk.agent import GptsMemory

        memory = GptsMemory(
            plans_memory=MetaDerisksPlansMemory(),
            message_memory=MetaDerisksMessageMemory(),
            message_system_memory=MetaAgentSystemMessageMemory(),
            file_metadata_db_storage=MetaDerisksFileMetadataStorage(),
            work_log_db_storage=MetaDerisksWorkLogStorage(),
            kanban_db_storage=MetaDerisksKanbanStorage(),
            todo_db_storage=MetaDerisksTodoStorage(),
        )

        chat = _ConcreteAgentChat.__new__(_ConcreteAgentChat)
        chat.system_app = system_app
        chat.memory = memory
        # V2 dispatch constructs AIWrapper internally (BAIZE pattern);
        # llm_provider is unused on V2 path. See agent_chat.py:2617-2648.
        chat.llm_provider = None
        chat.agent_manage = MagicMock()
        chat.gpts_conversations = MagicMock()
        chat.gpts_conversations.update = MagicMock()
        chat._running_tasks = {}

        return chat

    @pytest.mark.asyncio
    async def test_v2_dispatch_produces_events(self, agent_chat):
        """V2 agent produces V2 events and BAIZE path is NOT invoked."""
        app = _make_v2_gpts_app()
        cache = _make_cache_mock()

        # Mock memory.cache to return our mock cache
        agent_chat.memory.cache = AsyncMock(return_value=cache)

        # Mock memory.get_session_messages for V2 thinking_fn
        agent_chat.memory.get_session_messages = AsyncMock(return_value=[])

        # Mock memory.init (called before _inner_chat in aggregation_chat)
        agent_chat.memory.init = AsyncMock()

        # Mock memory.complete (called in finally block)
        agent_chat.memory.complete = AsyncMock()

        # Mock _cleanup_sandbox_manager (called in finally block)
        agent_chat._cleanup_sandbox_manager = AsyncMock()

        # Mock _build_agent_by_gpts to verify it's NOT called for V2
        agent_chat._build_agent_by_gpts = AsyncMock()

        # Patch AIWrapper so V2 dispatch uses our mock stream (agent_chat.py:2620,2644)
        # Import is local inside _inner_chat, so patch at source module.
        mock_ai_wrapper = MagicMock()
        mock_ai_wrapper.create = _mock_ai_create
        with patch(
            "derisk.agent.util.llm.llm_client.AIWrapper",
            return_value=mock_ai_wrapper,
        ):
            user_query = HumanMessage(content="Hello V2!")
            conv_session_id = "test_session"
            conv_uid = "test_conv_uid"

            agent_memory = AgentMemory(gpts_memory=agent_chat.memory)

            # Call _inner_chat with V2 agent
            result = await agent_chat._inner_chat(
                user_code="test_user",
                user_query=user_query,
                conv_session_id=conv_session_id,
                conv_uid=conv_uid,
                gpts_app=app,
                agent_memory=agent_memory,
                is_retry_chat=False,
                stream=True,
            )

        # Verify the conv_uid is returned
        assert result == conv_uid

        # Verify _build_agent_by_gpts was NOT called (BAIZE path skipped)
        agent_chat._build_agent_by_gpts.assert_not_called()

        # Verify gpts_conversations was updated with COMPLETE status
        agent_chat.gpts_conversations.update.assert_called_with(
            conv_uid, Status.COMPLETE.value
        )

        # Collect all SSE events from the queue
        events = []
        while not cache.channel.empty():
            events.append(cache.channel.get_nowait())

        # Verify V2 events were produced
        assert len(events) > 0, "Expected at least one SSE event"

        # BAIZE compat: first event is metadata (conv_session_id, conv_uid)
        metadata_events = [
            e for e in events
            if isinstance(e, str) and '"type":"metadata"' in e.replace(" ", "")
        ]
        assert len(metadata_events) > 0, (
            f"Expected metadata SSE event, got: {events}"
        )

        # BAIZE compat: token emitted as string vis: data:{"vis":"Hello"}
        # (NOT as object — frontend would render object as raw text)
        token_events = [
            e for e in events
            if isinstance(e, str) and '"vis":"Hello' in e.replace(" ", "")
        ]
        assert len(token_events) > 0, (
            f"Expected string-vis token events in V2 output, got: {events}"
        )

        # BAIZE compat: internal types (step_start/step_end/tool_call) are suppressed
        for internal_type in ("step_start", "step_end", "tool_call", "tool_result"):
            internal_events = [
                e for e in events
                if isinstance(e, str) and f'"type":"{internal_type}"' in e.replace(" ", "")
            ]
            assert len(internal_events) == 0, (
                f"Expected no {internal_type} SSE events (suppressed for BAIZE compat), got: {events}"
            )

        # Check for DONE signal — _format_vis_msg("[DONE]") yields data:{"vis":"[DONE]"} \n
        done_events = [e for e in events if isinstance(e, str) and "[DONE]" in e]
        assert len(done_events) > 0, (
            f"Expected [DONE] signal in V2 output, got: {events}"
        )

    @pytest.mark.asyncio
    async def test_v1_agent_does_not_trigger_v2_dispatch(self, agent_chat):
        """V1 agent (default) does NOT trigger V2 dispatch."""
        app = _make_v2_gpts_app()
        app.agent_version = "v1"  # Override to v1

        cache = _make_cache_mock()
        agent_chat.memory.cache = AsyncMock(return_value=cache)
        agent_chat.memory.init = AsyncMock()
        agent_chat.memory.complete = AsyncMock()
        agent_chat._cleanup_sandbox_manager = AsyncMock()

        # Mock _build_agent_by_gpts to return a mock agent
        mock_agent = MagicMock()
        mock_agent.profile = MagicMock()
        mock_agent.profile.name = "test_agent"
        agent_chat._build_agent_by_gpts = AsyncMock(return_value=mock_agent)

        # Mock UserProxyAgent to avoid real agent behavior
        with patch(
            "derisk_serve.agent.agents.chat.agent_chat.UserProxyAgent"
        ) as mock_up:
            mock_up_instance = MagicMock()
            mock_up_instance.profile = MagicMock()
            mock_up_instance.have_ask_user = MagicMock(return_value=False)
            mock_up.return_value.bind.return_value.bind.return_value.build = AsyncMock(
                return_value=mock_up_instance
            )
            mock_up_instance.initiate_chat = AsyncMock()

            user_query = HumanMessage(content="Hello V1!")
            conv_session_id = "test_session_v1"
            conv_uid = "test_conv_uid_v1"

            agent_memory = AgentMemory(gpts_memory=agent_chat.memory)

            app_config = MagicMock()
            app_config.service.web.web_url = "http://test"
            agent_chat.system_app.config.configs = {"app_config": app_config}

            result = await agent_chat._inner_chat(
                user_code="test_user",
                user_query=user_query,
                conv_session_id=conv_session_id,
                conv_uid=conv_uid,
                gpts_app=app,
                agent_memory=agent_memory,
                is_retry_chat=False,
                stream=True,
            )

            assert result == conv_uid

            # Verify _build_agent_by_gpts WAS called (BAIZE path)
            agent_chat._build_agent_by_gpts.assert_called_once()

            # Verify UserProxyAgent.initiate_chat WAS called
            mock_up_instance.initiate_chat.assert_called_once()
