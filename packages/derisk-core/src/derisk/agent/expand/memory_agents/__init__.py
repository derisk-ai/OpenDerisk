"""Built-in memory agents.

These are normal ConversableAgent subclasses registered via
`scan_agents("derisk.agent.expand")`. They are dispatched by name through
the generic `agent_dispatcher` (see `derisk.agent.core.memory.agent_dispatcher`)
when a `kind=agent` memory hook fires.

Design:
* Tier 0 (prefetch) and tier 1 (per-turn write) are NOT real agents —
  they are `kind=function` endpoints (see
  `hook_dispatcher.memory_prefetch_function` /
  `memory_write_turn_function`), running as in-process callables
  without an LLM fork.
* Tier 2 (cross-turn reflection) and tier 3 (session-end curation) land
  here as real agents. Each agent parses the hook event from
  `received_message.content`, looks up its per-conv bundle via
  `hook_dispatcher.get_memory_bundle(conv_id)`, and delegates the heavy
  LLM-driven consolidation work to the bundle's `LongTermMemoryManager`.

The agents are global singletons (no per-conv `agent_context`) — they
extract `conv_id` from the event payload, never from `self.agent_context`,
so they're safe to call concurrently across conversations.
"""

from .base import MemoryAgentBase
from .reflect_agent import MemoryReflectAgent
from .curate_agent import MemoryCurateAgent

__all__ = [
    "MemoryAgentBase",
    "MemoryReflectAgent",
    "MemoryCurateAgent",
]
