"""V2 full dispatch integration: verify acting_fn/max_steps/hook_manager wired.

These tests verify that the V2 dispatch in agent_chat._inner_chat constructs
the full BAIZE-parity pipeline (real acting_fn, max_steps=20, hook_manager
from team_context) — not just the LLM-only path that was wired before.
"""
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
    """Mock AIWrapper.create — yields one token then metrics."""
    from derisk.agent.util.llm.llm_client import AgentLLMOut
    from derisk.core.interface.llm import ModelInferenceMetrics

    yield AgentLLMOut(content="Hello from V2 with tools!", thinking_content=None)
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
    # when no bundle has been registered.
    cache.memory_bundle = None
    return cache


class _ConcreteAgentChat(AgentChat):
    """Concrete AgentChat for testing — implements the abstract chat method."""

    async def chat(self, *args, **kwargs):
        raise NotImplementedError("Test-only subclass")


class TestV2FullDispatch:
    """V2 dispatch wires acting_fn, max_steps=20, hook_manager — not LLM-only."""

    @pytest.fixture
    def agent_chat(self):
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
        chat.llm_provider = None  # V2 dispatch uses AIWrapper, not llm_provider
        chat.agent_manage = MagicMock()
        chat.gpts_conversations = MagicMock()
        chat.gpts_conversations.update = MagicMock()
        chat._running_tasks = {}

        return chat

    @pytest.mark.asyncio
    async def test_v2_dispatch_passes_acting_fn_not_none(self, agent_chat):
        """V2 dispatch must construct real acting_fn (not None) so tools can run."""
        app = _make_v2_gpts_app()
        cache = _make_cache_mock()

        agent_chat.memory.cache = AsyncMock(return_value=cache)
        agent_chat.memory.get_session_messages = AsyncMock(return_value=[])
        agent_chat.memory.init = AsyncMock()
        agent_chat.memory.complete = AsyncMock()
        agent_chat._cleanup_sandbox_manager = AsyncMock()
        agent_chat._build_agent_by_gpts = AsyncMock()

        # Capture run_loop kwargs to verify acting_fn is wired
        captured_kwargs = {}

        async def _fake_run_loop(**kwargs):
            captured_kwargs.update(kwargs)
            # Yield one step_event so the stream isn't empty
            from derisk.agent.core.v2.step_event import StepEvent
            from derisk.agent.core.v2.step_state import StepState
            yield StepEvent(
                event_id="evt-test",
                step_id="step-test",
                conv_id="test_conv_uid",
                agent_id="test_v2_app",
                parent_step_id=None,
                state=StepState.DONE,
                event_type="step_done",
                input={},
                output={},
                seq=0,
                timestamp=0.0,
            )

        mock_ai_wrapper = MagicMock()
        mock_ai_wrapper.create = _mock_ai_create

        with patch(
            "derisk.agent.util.llm.llm_client.AIWrapper",
            return_value=mock_ai_wrapper,
        ), patch(
            "derisk.agent.core.v2.run_loop",
            _fake_run_loop,
        ):
            user_query = HumanMessage(content="Use a tool")
            result = await agent_chat._inner_chat(
                user_code="test_user",
                user_query=user_query,
                conv_session_id="test_session",
                conv_uid="test_conv_uid",
                gpts_app=app,
                agent_memory=AgentMemory(gpts_memory=agent_chat.memory),
                is_retry_chat=False,
                stream=True,
            )

        assert result == "test_conv_uid"

        # acting_fn must be a callable, not None
        assert captured_kwargs.get("acting_fn") is not None, (
            "V2 dispatch must pass a real acting_fn (not None) so tools can execute"
        )
        assert callable(captured_kwargs["acting_fn"]), (
            "acting_fn must be callable"
        )

    @pytest.mark.asyncio
    async def test_v2_dispatch_uses_max_steps_20(self, agent_chat):
        """V2 dispatch must pass max_steps=20 (multi-turn tool calling), not 1."""
        app = _make_v2_gpts_app()
        cache = _make_cache_mock()

        agent_chat.memory.cache = AsyncMock(return_value=cache)
        agent_chat.memory.get_session_messages = AsyncMock(return_value=[])
        agent_chat.memory.init = AsyncMock()
        agent_chat.memory.complete = AsyncMock()
        agent_chat._cleanup_sandbox_manager = AsyncMock()
        agent_chat._build_agent_by_gpts = AsyncMock()

        captured_kwargs = {}

        async def _fake_run_loop(**kwargs):
            captured_kwargs.update(kwargs)
            from derisk.agent.core.v2.step_event import StepEvent
            from derisk.agent.core.v2.step_state import StepState
            yield StepEvent(
                event_id="evt-test",
                step_id="step-test",
                conv_id="test_conv_uid",
                agent_id="test_v2_app",
                parent_step_id=None,
                state=StepState.DONE,
                event_type="step_done",
                input={},
                output={},
                seq=0,
                timestamp=0.0,
            )

        mock_ai_wrapper = MagicMock()
        mock_ai_wrapper.create = _mock_ai_create

        with patch(
            "derisk.agent.util.llm.llm_client.AIWrapper",
            return_value=mock_ai_wrapper,
        ), patch(
            "derisk.agent.core.v2.run_loop",
            _fake_run_loop,
        ):
            await agent_chat._inner_chat(
                user_code="test_user",
                user_query=HumanMessage(content="Multi-step"),
                conv_session_id="test_session",
                conv_uid="test_conv_uid",
                gpts_app=app,
                agent_memory=AgentMemory(gpts_memory=agent_chat.memory),
                is_retry_chat=False,
                stream=True,
            )

        assert captured_kwargs.get("max_steps") == 20, (
            f"V2 dispatch must pass max_steps=20 for multi-turn tool calling, "
            f"got: {captured_kwargs.get('max_steps')}"
        )

    @pytest.mark.asyncio
    async def test_v2_dispatch_passes_hook_manager_when_team_context_present(
        self, agent_chat
    ):
        """V2 dispatch builds HookManager from gpts_app.team_context.hook_config."""
        app = _make_v2_gpts_app()
        # Attach a team_context with hook_config — V2 dispatch should build HookManager
        app.team_context = MagicMock()
        app.team_context.hook_config = {
            "enabled": True,
            "hooks": [],
        }

        cache = _make_cache_mock()

        agent_chat.memory.cache = AsyncMock(return_value=cache)
        agent_chat.memory.get_session_messages = AsyncMock(return_value=[])
        agent_chat.memory.init = AsyncMock()
        agent_chat.memory.complete = AsyncMock()
        agent_chat._cleanup_sandbox_manager = AsyncMock()
        agent_chat._build_agent_by_gpts = AsyncMock()

        captured_kwargs = {}

        async def _fake_run_loop(**kwargs):
            captured_kwargs.update(kwargs)
            from derisk.agent.core.v2.step_event import StepEvent
            from derisk.agent.core.v2.step_state import StepState
            yield StepEvent(
                event_id="evt-test",
                step_id="step-test",
                conv_id="test_conv_uid",
                agent_id="test_v2_app",
                parent_step_id=None,
                state=StepState.DONE,
                event_type="step_done",
                input={},
                output={},
                seq=0,
                timestamp=0.0,
            )

        mock_ai_wrapper = MagicMock()
        mock_ai_wrapper.create = _mock_ai_create

        with patch(
            "derisk.agent.util.llm.llm_client.AIWrapper",
            return_value=mock_ai_wrapper,
        ), patch(
            "derisk.agent.core.v2.run_loop",
            _fake_run_loop,
        ):
            await agent_chat._inner_chat(
                user_code="test_user",
                user_query=HumanMessage(content="Hook me"),
                conv_session_id="test_session",
                conv_uid="test_conv_uid",
                gpts_app=app,
                agent_memory=AgentMemory(gpts_memory=agent_chat.memory),
                is_retry_chat=False,
                stream=True,
            )

        # When team_context.hook_config.enabled is True, hook_manager should be built
        # (not None). If enabled=False or no team_context, hook_manager is None.
        assert captured_kwargs.get("hook_manager") is not None, (
            "V2 dispatch must build HookManager when team_context.hook_config.enabled=True; "
            f"got: {captured_kwargs.get('hook_manager')}"
        )

    @pytest.mark.asyncio
    async def test_v2_dispatch_hook_manager_none_when_no_team_context(
        self, agent_chat
    ):
        """V2 dispatch passes hook_manager=None when no team_context."""
        app = _make_v2_gpts_app()
        # No team_context attached

        cache = _make_cache_mock()
        agent_chat.memory.cache = AsyncMock(return_value=cache)
        agent_chat.memory.get_session_messages = AsyncMock(return_value=[])
        agent_chat.memory.init = AsyncMock()
        agent_chat.memory.complete = AsyncMock()
        agent_chat._cleanup_sandbox_manager = AsyncMock()
        agent_chat._build_agent_by_gpts = AsyncMock()

        captured_kwargs = {}

        async def _fake_run_loop(**kwargs):
            captured_kwargs.update(kwargs)
            from derisk.agent.core.v2.step_event import StepEvent
            from derisk.agent.core.v2.step_state import StepState
            yield StepEvent(
                event_id="evt-test",
                step_id="step-test",
                conv_id="test_conv_uid",
                agent_id="test_v2_app",
                parent_step_id=None,
                state=StepState.DONE,
                event_type="step_done",
                input={},
                output={},
                seq=0,
                timestamp=0.0,
            )

        mock_ai_wrapper = MagicMock()
        mock_ai_wrapper.create = _mock_ai_create

        with patch(
            "derisk.agent.util.llm.llm_client.AIWrapper",
            return_value=mock_ai_wrapper,
        ), patch(
            "derisk.agent.core.v2.run_loop",
            _fake_run_loop,
        ):
            await agent_chat._inner_chat(
                user_code="test_user",
                user_query=HumanMessage(content="No hooks"),
                conv_session_id="test_session",
                conv_uid="test_conv_uid",
                gpts_app=app,
                agent_memory=AgentMemory(gpts_memory=agent_chat.memory),
                is_retry_chat=False,
                stream=True,
            )

        # No team_context → hook_manager should be None
        assert captured_kwargs.get("hook_manager") is None, (
            f"V2 dispatch should pass hook_manager=None when no team_context; "
            f"got: {captured_kwargs.get('hook_manager')}"
        )
