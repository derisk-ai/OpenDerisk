"""Tests for the built-in memory agents (MemoryReflectAgent / MemoryCurateAgent).

Covers:
1. `MemoryAgentBase._parse_event` parses event JSON + conv_id from
   `received_message.content`
2. `MemoryReflectAgent.generate_reply` delegates to
   `bundle.manager.reflect_on_last_n_turns`
3. `MemoryCurateAgent.generate_reply` delegates to
   `bundle.manager.curate_session`
4. Missing conv_id / missing bundle / manager failure never raise —
   always returns an empty reply
"""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from derisk.agent.core.memory.hook_dispatcher import (
    register_memory_bundle,
    unregister_memory_bundle,
)
from derisk.agent.core.types import AgentMessage
from derisk.agent.expand.memory_agents.base import MemoryAgentBase
from derisk.agent.expand.memory_agents.curate_agent import MemoryCurateAgent
from derisk.agent.expand.memory_agents.reflect_agent import MemoryReflectAgent


def _event_msg(event: dict) -> AgentMessage:
    return AgentMessage(
        message_id="m1",
        content=json.dumps(event, ensure_ascii=False),
        current_goal="handle turn_complete",
        role="user",
    )


def _make_bundle(manager: Any) -> Any:
    bundle = MagicMock()
    bundle.manager = manager
    bundle.config = MagicMock(reflection_interval=10)
    return bundle


class TestParseEvent:
    def test_parses_json_content(self):
        agent = MemoryReflectAgent()
        msg = _event_msg({"conv_id": "c1", "extra": {"tier": 2}})
        event, conv_id = agent._parse_event(msg)
        assert event["conv_id"] == "c1"
        assert conv_id == "c1"
        assert event["extra"]["tier"] == 2

    def test_handles_dict_content(self):
        agent = MemoryReflectAgent()
        msg = AgentMessage(content={"conv_id": "c2"})
        event, conv_id = agent._parse_event(msg)
        assert conv_id == "c2"

    def test_invalid_json_returns_empty_event(self):
        agent = MemoryReflectAgent()
        msg = AgentMessage(content="not-json")
        event, conv_id = agent._parse_event(msg)
        assert event == {}
        assert conv_id == ""

    def test_empty_content_returns_empty_event(self):
        agent = MemoryReflectAgent()
        msg = AgentMessage(content="")
        event, conv_id = agent._parse_event(msg)
        assert event == {}
        assert conv_id == ""


class TestMemoryReflectAgent:
    def setup_method(self):
        from derisk.agent.core.memory import hook_dispatcher as hd
        hd._BUNDLE_REGISTRY.clear()

    def test_generate_reply_calls_reflect(self):
        manager = MagicMock()
        manager.reflect_on_last_n_turns = AsyncMock(return_value={"ok": True})
        bundle = _make_bundle(manager)
        register_memory_bundle("c_reflect", bundle)

        agent = MemoryReflectAgent()
        loop = asyncio.get_event_loop()
        reply = loop.run_until_complete(agent.generate_reply(
            _event_msg({"conv_id": "c_reflect", "extra": {"tier": 2, "n": 10}}),
            sender=agent,
        ))
        manager.reflect_on_last_n_turns.assert_awaited_once()
        # n defaults from extra
        args, kwargs = manager.reflect_on_last_n_turns.call_args
        assert kwargs.get("n") == 10
        assert reply.role == "assistant"
        assert reply.success is True

    def test_no_conv_id_returns_empty(self):
        agent = MemoryReflectAgent()
        loop = asyncio.get_event_loop()
        reply = loop.run_until_complete(agent.generate_reply(
            _event_msg({}), sender=agent,
        ))
        assert reply.content == ""

    def test_no_bundle_returns_empty(self):
        agent = MemoryReflectAgent()
        loop = asyncio.get_event_loop()
        reply = loop.run_until_complete(agent.generate_reply(
            _event_msg({"conv_id": "no_such_bundle"}), sender=agent,
        ))
        assert reply.content == ""

    def test_manager_failure_swallowed(self):
        manager = MagicMock()
        manager.reflect_on_last_n_turns = AsyncMock(side_effect=RuntimeError("boom"))
        bundle = _make_bundle(manager)
        register_memory_bundle("c_fail", bundle)

        agent = MemoryReflectAgent()
        loop = asyncio.get_event_loop()
        reply = loop.run_until_complete(agent.generate_reply(
            _event_msg({"conv_id": "c_fail"}), sender=agent,
        ))
        # Must not raise — failure swallowed
        assert reply.content == ""
        assert reply.success is True


class TestMemoryCurateAgent:
    def setup_method(self):
        from derisk.agent.core.memory import hook_dispatcher as hd
        hd._BUNDLE_REGISTRY.clear()

    def test_generate_reply_calls_curate(self):
        manager = MagicMock()
        manager.curate_session = AsyncMock(return_value={"spaces": {}})
        bundle = _make_bundle(manager)
        register_memory_bundle("c_curate", bundle)

        agent = MemoryCurateAgent()
        loop = asyncio.get_event_loop()
        reply = loop.run_until_complete(agent.generate_reply(
            _event_msg({
                "conv_id": "c_curate",
                "extra": {"tier": 3, "conversation_history": []},
            }),
            sender=agent,
        ))
        manager.curate_session.assert_awaited_once()
        assert reply.role == "assistant"
        assert reply.success is True

    def test_manager_failure_swallowed(self):
        manager = MagicMock()
        manager.curate_session = AsyncMock(side_effect=RuntimeError("boom"))
        bundle = _make_bundle(manager)
        register_memory_bundle("c_fail", bundle)

        agent = MemoryCurateAgent()
        loop = asyncio.get_event_loop()
        reply = loop.run_until_complete(agent.generate_reply(
            _event_msg({"conv_id": "c_fail"}), sender=agent,
        ))
        assert reply.content == ""


class TestAgentRegistry:
    """Smoke test: agents are ConversableAgent subclasses with the right names."""

    def test_reflect_agent_name(self):
        agent = MemoryReflectAgent()
        assert agent.name == "MemoryReflectAgent"

    def test_curate_agent_name(self):
        agent = MemoryCurateAgent()
        assert agent.name == "MemoryCurateAgent"

    def test_base_is_conversable(self):
        from derisk.agent.core.base_agent import ConversableAgent
        assert issubclass(MemoryAgentBase, ConversableAgent)
        assert issubclass(MemoryReflectAgent, MemoryAgentBase)
        assert issubclass(MemoryCurateAgent, MemoryAgentBase)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
