"""Tests for the memory/hook integration (three-tier decoupled memory).

Covers:
1. `every_n_turns` filter on turn_complete trigger
2. Tier 0/1 memory functions (`memory_prefetch_function`,
   `memory_write_turn_function`) — deterministic in-process callables
   registered with FunctionRegistry. They call LongTermMemoryManager
   directly, no LLM fork.
3. `agent_dispatcher` routing for real agent names (tier 2/3) —
   AgentManager.get + generate_reply. Failures never propagate (always
   returns continue).
4. `default_memory_hooks` produces the four expected HookConfig entries:
   tier 0/1 use `kind=FUNCTION` + `function_name`; tier 2/3 use
   `kind=AGENT` + real agent_name.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from derisk.agent.core.hook.schema import (
    HookConfig,
    HookEndpointConfig,
    HookKind,
    HookTriggerConfig,
    HookTriggerType,
)
from derisk.agent.core.hook.trigger_checker import HookTriggerChecker
from derisk.agent.core.memory.hook_dispatcher import (
    default_memory_hooks,
    get_memory_bundle,
    memory_prefetch_function,
    memory_write_turn_function,
    register_memory_bundle,
    unregister_memory_bundle,
)
from derisk.agent.core.memory.agent_dispatcher import agent_dispatcher


# -----------------------------------------------------------------------------
# every_n_turns filter
# -----------------------------------------------------------------------------


def _make_hook(every_n: int = None) -> HookConfig:
    return HookConfig(
        name="t",
        trigger=HookTriggerConfig(
            trigger_type=HookTriggerType.TURN_COMPLETE.value,
            every_n_turns=every_n,
        ),
        endpoint=HookEndpointConfig(kind=HookKind.FUNCTION, function_name="t"),
    )


class TestEveryNTurnsFilter:
    def test_none_means_every_turn(self):
        checker = HookTriggerChecker()
        hook = _make_hook(every_n=None)
        for r in [1, 2, 5, 10, 11]:
            assert checker.should_trigger(hook, "turn_complete", {"round": r})

    def test_one_means_every_turn(self):
        checker = HookTriggerChecker()
        hook = _make_hook(every_n=1)
        for r in [1, 2, 3]:
            assert checker.should_trigger(hook, "turn_complete", {"round": r})

    def test_n_ten_fires_only_on_multiples(self):
        checker = HookTriggerChecker()
        hook = _make_hook(every_n=10)
        for r in [1, 2, 5, 9, 11, 19]:
            assert not checker.should_trigger(hook, "turn_complete", {"round": r})
        for r in [10, 20, 100]:
            assert checker.should_trigger(hook, "turn_complete", {"round": r})

    def test_round_zero_does_not_fire_when_n_gt_one(self):
        checker = HookTriggerChecker()
        hook = _make_hook(every_n=5)
        assert not checker.should_trigger(hook, "turn_complete", {"round": 0})
        assert not checker.should_trigger(hook, "turn_complete", {"round": None})

    def test_wrong_trigger_type_unaffected(self):
        checker = HookTriggerChecker()
        hook = HookConfig(
            name="t",
            trigger=HookTriggerConfig(
                trigger_type=HookTriggerType.CONVERSATION_COMPLETE.value,
                every_n_turns=10,
            ),
            endpoint=HookEndpointConfig(kind=HookKind.AGENT, agent_name="x"),
        )
        assert checker.should_trigger(hook, "conversation_complete", {})


# -----------------------------------------------------------------------------
# default_memory_hooks
# -----------------------------------------------------------------------------


class TestDefaultMemoryHooks:
    def test_returns_four_hooks(self):
        cfg = MagicMock()
        cfg.reflection_interval = 10
        hooks = default_memory_hooks(cfg)
        assert len(hooks) == 4

    def test_tier0_uses_prefetch_function(self):
        cfg = MagicMock()
        cfg.reflection_interval = 10
        hooks = default_memory_hooks(cfg)
        t0 = next(h for h in hooks if h.name == "memory_tier0_prefetch")
        assert t0.trigger.trigger_type == HookTriggerType.TURN_COMPLETE.value
        assert t0.trigger.every_n_turns == 1
        assert t0.trigger.extra.get("tier") == 0
        assert t0.endpoint.kind == HookKind.FUNCTION
        assert t0.endpoint.function_name == "memory_prefetch"
        assert t0.endpoint.blocking is False

    def test_tier1_uses_write_function(self):
        cfg = MagicMock()
        cfg.reflection_interval = 10
        hooks = default_memory_hooks(cfg)
        t1 = next(h for h in hooks if h.name == "memory_tier1_turn")
        assert t1.trigger.trigger_type == HookTriggerType.TURN_COMPLETE.value
        assert t1.trigger.every_n_turns == 1
        assert t1.trigger.extra.get("tier") == 1
        assert t1.endpoint.kind == HookKind.FUNCTION
        assert t1.endpoint.function_name == "memory_write_turn"
        assert t1.endpoint.blocking is False

    def test_tier2_uses_reflect_agent_name(self):
        cfg = MagicMock()
        cfg.reflection_interval = 7
        hooks = default_memory_hooks(cfg)
        t2 = next(h for h in hooks if h.name == "memory_tier2_reflect")
        assert t2.trigger.every_n_turns == 7
        assert t2.trigger.extra.get("tier") == 2
        assert t2.endpoint.kind == HookKind.AGENT
        assert t2.endpoint.agent_name == "MemoryReflectAgent"

    def test_tier2_falls_back_to_default_ten(self):
        cfg = MagicMock()
        cfg.reflection_interval = None
        hooks = default_memory_hooks(cfg, reflection_interval=None)
        t2 = next(h for h in hooks if h.name == "memory_tier2_reflect")
        assert t2.trigger.every_n_turns == 10

    def test_tier3_uses_curate_agent_name(self):
        cfg = MagicMock()
        cfg.reflection_interval = 10
        hooks = default_memory_hooks(cfg)
        t3 = next(h for h in hooks if h.name == "memory_tier3_curate")
        assert t3.trigger.trigger_type == HookTriggerType.CONVERSATION_COMPLETE.value
        assert t3.trigger.every_n_turns is None
        assert t3.trigger.extra.get("tier") == 3
        assert t3.endpoint.kind == HookKind.AGENT
        assert t3.endpoint.agent_name == "MemoryCurateAgent"

    def test_tier01_functions_registered(self):
        from derisk.agent.core.hook.executors import FunctionRegistry

        assert FunctionRegistry.get("memory_prefetch") is memory_prefetch_function
        assert FunctionRegistry.get("memory_write_turn") is memory_write_turn_function


# -----------------------------------------------------------------------------
# Tier 0/1 memory functions
# -----------------------------------------------------------------------------


def _make_bundle(manager: Any) -> Any:
    bundle = MagicMock()
    bundle.manager = manager
    bundle.config = MagicMock(reflection_interval=10)
    return bundle


class TestMemoryFunctions:
    def setup_method(self):
        from derisk.agent.core.memory import hook_dispatcher as hd
        hd._BUNDLE_REGISTRY.clear()

    def test_write_no_conv_id_returns_continue(self):
        result = asyncio.get_event_loop().run_until_complete(
            memory_write_turn_function({}, None)
        )
        assert result == {"action": "continue"}

    def test_write_no_bundle_returns_continue(self):
        result = asyncio.get_event_loop().run_until_complete(
            memory_write_turn_function({"conv_id": "missing"}, None)
        )
        assert result == {"action": "continue"}

    def test_write_calls_write_turn_lightweight(self):
        manager = MagicMock()
        manager.write_turn_lightweight = AsyncMock(return_value={"s": True})
        bundle = _make_bundle(manager)
        register_memory_bundle("c1", bundle)
        asyncio.get_event_loop().run_until_complete(memory_write_turn_function({
            "conv_id": "c1",
            "user_prompt": "hello",
            "final_answer": "world",
        }, None))
        manager.write_turn_lightweight.assert_awaited_once()
        manager.reflect_on_last_n_turns.assert_not_called()
        manager.curate_session.assert_not_called()

    def test_prefetch_interrupted_skips(self):
        manager = MagicMock()
        manager.retrieve_relevant_memories = AsyncMock(return_value="")
        bundle = _make_bundle(manager)
        register_memory_bundle("c_int", bundle)
        result = asyncio.get_event_loop().run_until_complete(memory_prefetch_function({
            "conv_id": "c_int",
            "user_prompt": "hello",
            "extra": {"interrupted": True},
        }, None))
        assert result == {"action": "continue"}
        manager.retrieve_relevant_memories.assert_not_called()

    def test_prefetch_failed_skips(self):
        manager = MagicMock()
        manager.retrieve_relevant_memories = AsyncMock(return_value="")
        bundle = _make_bundle(manager)
        register_memory_bundle("c_fail", bundle)
        result = asyncio.get_event_loop().run_until_complete(memory_prefetch_function({
            "conv_id": "c_fail",
            "user_prompt": "hello",
            "success": False,
        }, None))
        assert result == {"action": "continue"}
        manager.retrieve_relevant_memories.assert_not_called()

    def test_write_failure_returns_continue(self):
        manager = MagicMock()
        manager.write_turn_lightweight = AsyncMock(side_effect=RuntimeError("boom"))
        bundle = _make_bundle(manager)
        register_memory_bundle("c4", bundle)
        result = asyncio.get_event_loop().run_until_complete(memory_write_turn_function({
            "conv_id": "c4",
            "user_prompt": "x",
            "final_answer": "y",
        }, None))
        assert result == {"action": "continue"}

    def test_unregister_clears_registry(self):
        manager = MagicMock()
        bundle = _make_bundle(manager)
        register_memory_bundle("c7", bundle)
        assert get_memory_bundle("c7") is bundle
        unregister_memory_bundle("c7")
        assert get_memory_bundle("c7") is None


# -----------------------------------------------------------------------------
# agent_dispatcher routing (real agents only — tier 2/3)
# -----------------------------------------------------------------------------


class TestAgentDispatcher:
    def setup_method(self):
        from derisk.agent.core.memory import hook_dispatcher as hd
        hd._BUNDLE_REGISTRY.clear()

    def test_unknown_real_agent_returns_continue(self):
        result = asyncio.get_event_loop().run_until_complete(agent_dispatcher(
            agent_name="NonexistentAgent",
            event={"conv_id": "c5"},
        ))
        assert result == {"action": "continue"}

    def test_real_agent_dispatch_calls_generate_reply(self):
        fake_agent = MagicMock()
        fake_agent.generate_reply = AsyncMock(return_value=MagicMock(content="ok"))

        with patch(
            "derisk.agent.core.agent_manage.get_agent_manager"
        ) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get.return_value = fake_agent
            mock_get_mgr.return_value = mock_mgr

            result = asyncio.get_event_loop().run_until_complete(agent_dispatcher(
                agent_name="MemoryReflectAgent",
                event={"conv_id": "c6", "extra": {"tier": 2}},
            ))
        assert result == {"action": "continue"}
        fake_agent.generate_reply.assert_awaited_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
