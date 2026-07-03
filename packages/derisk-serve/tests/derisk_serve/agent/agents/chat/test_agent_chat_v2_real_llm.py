"""V2 real LLM dispatch integration test.

Verifies that make_default_thinking_fn + run_loop produces real LLM-driven
responses through the V2 dispatch path, replacing the old mock thinking_fn.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from derisk.agent.core.v2.step_state import StepState


class TestV2RealLLMDispatch:
    """V2 dispatch with real make_default_thinking_fn — token and DONE assertions."""

    @pytest.mark.asyncio
    async def test_v2_real_llm_produces_thinking_tokens(self):
        """V2 dispatch with mock LLMClient yields token events from real thinking_fn."""
        from derisk.core.interface.llm import ModelOutput
        from derisk.agent.core.v2 import (
            run_loop,
            DbStateStore,
            make_default_thinking_fn,
            make_derisk_llm_stream_fn,
        )
        from derisk.agent.expand.react_master_agent.context_engine.engine import ContextEngine

        # Mock LLMClient that yields sequential tokens
        llm_client = MagicMock()

        async def _fake_generate_stream(request):
            yield ModelOutput(error_code=0, text="Hello")
            yield ModelOutput(error_code=0, text=" from V2!")
            yield ModelOutput(
                error_code=0,
                text="",
                usage={"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            )

        llm_client.generate_stream = _fake_generate_stream

        # Build real thinking_fn
        llm_stream_fn = make_derisk_llm_stream_fn(llm_client, model_alias="test-model")

        context_engine = ContextEngine()

        thinking_fn = make_default_thinking_fn(
            llm_stream_fn=llm_stream_fn,
            model_alias="test-model",
            context_engine=context_engine,
            memory_bundle=None,
            get_session_messages=lambda sid: [],
            get_work_log=lambda cid: [],
            get_context_window=lambda model: 4096,
            system_prompt="You are a helpful assistant.",
        )

        # Run run_loop with the real thinking_fn
        import tempfile
        import os
        db_path = os.path.join(tempfile.mkdtemp(), "test.db")
        state_store = DbStateStore(db_path)

        events = []
        async for step_event in run_loop(
            agent_id="test_agent",
            conv_id="test_conv",
            input_={"prompt": "Hi!", "conv_id": "test_conv", "session_id": "test_session"},
            state_store=state_store,
            thinking_fn=thinking_fn,
            acting_fn=None,
            max_steps=1,
        ):
            events.append(step_event)

        # Verify THINKING state with tokens
        thinking_events = [e for e in events if e.state == StepState.THINKING]
        assert len(thinking_events) > 0, f"Expected THINKING events, got: {[e.state for e in events]}"

        # Collect tokens
        tokens = [
            e.output.get("token", "")
            for e in thinking_events
            if e.event_type == "llm_token" and e.output
        ]
        full_text = "".join(tokens)
        assert "Hello" in full_text, f"Expected 'Hello' in tokens, got: {full_text}"
        assert "from V2!" in full_text, f"Expected 'from V2!' in tokens, got: {full_text}"

        # Verify DONE state is reached
        done_events = [e for e in events if e.state == StepState.DONE]
        assert len(done_events) > 0, "Expected DONE state"

    @pytest.mark.asyncio
    async def test_v2_real_llm_handles_tool_calls(self):
        """V2 dispatch yields tool_call events when LLM emits tool_calls."""
        from derisk.core.interface.llm import ModelOutput
        from derisk.agent.core.v2 import (
            run_loop,
            DbStateStore,
            make_default_thinking_fn,
            make_derisk_llm_stream_fn,
        )
        from derisk.agent.expand.react_master_agent.context_engine.engine import ContextEngine

        llm_client = MagicMock()

        async def _fake_generate_stream(request):
            yield ModelOutput(
                error_code=0,
                text="Let me check that.",
                tool_calls=[
                    {
                        "id": "call_1",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path": "/tmp/x"}',
                        },
                    }
                ],
            )
            yield ModelOutput(
                error_code=0,
                text="",
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )

        llm_client.generate_stream = _fake_generate_stream

        llm_stream_fn = make_derisk_llm_stream_fn(llm_client, model_alias="test-model")
        context_engine = ContextEngine()

        thinking_fn = make_default_thinking_fn(
            llm_stream_fn=llm_stream_fn,
            model_alias="test-model",
            context_engine=context_engine,
            memory_bundle=None,
            get_session_messages=lambda sid: [],
            get_work_log=lambda cid: [],
            get_context_window=lambda model: 4096,
        )

        import tempfile
        import os
        db_path = os.path.join(tempfile.mkdtemp(), "test.db")
        state_store = DbStateStore(db_path)

        events = []
        async for step_event in run_loop(
            agent_id="test_agent",
            conv_id="test_conv",
            input_={"prompt": "Read /tmp/x", "conv_id": "test_conv", "session_id": "test_session"},
            state_store=state_store,
            thinking_fn=thinking_fn,
            acting_fn=None,
            max_steps=1,
        ):
            events.append(step_event)

        # Verify tool_call event
        tool_call_events = [e for e in events if e.event_type == "tool_call"]
        assert len(tool_call_events) > 0, (
            f"Expected tool_call events, got event types: {[e.event_type for e in events]}"
        )

        # Verify DONE state
        done_events = [e for e in events if e.state == StepState.DONE]
        assert len(done_events) > 0, "Expected DONE state"