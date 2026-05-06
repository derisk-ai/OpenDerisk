"""Memory tool pack for agent integration.

Exposes memory operations as agent-callable tools so that agents can
proactively search, save, and query knowledge graph entries during
conversations.

Works with any registered MemoryStoreBase provider.
"""

import json
import logging
from functools import partial
from typing import Any, Dict, List, Optional

from derisk.agent.resource.tool.pack import ToolPack, json_parse_execute_args_func
from derisk.storage.memory.base import MemoryStoreBase

logger = logging.getLogger(__name__)


class MemoryToolPack(ToolPack):
    """Tool pack that exposes memory store operations to agents.

    Registers four tools:
    - ``memory_search``: Semantic search over long-term memories.
    - ``memory_save``: Save important information to long-term memory.
    - ``kg_query``: Query knowledge graph for entity relationships.
    - ``kg_add``: Add a fact to the knowledge graph.
    """

    def __init__(
        self,
        memory_store: MemoryStoreBase,
        wing: str = "default",
        **kwargs,
    ):
        super().__init__([], name="Memory Tool Pack", **kwargs)
        self._memory_store = memory_store
        self._wing = wing

    @classmethod
    def type_alias(cls) -> str:
        return "tool(memory)"

    async def preload_resource(self):
        """Register the memory tools."""
        self.add_command(
            command_label=(
                "Search long-term memories by semantic similarity. "
                "Use this to recall past conversations, decisions, and facts."
            ),
            command_name="memory_search",
            args={
                "query": {
                    "type": "string",
                    "description": "The search query text.",
                    "required": True,
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of results (default 5).",
                    "default": 5,
                },
                "room": {
                    "type": "string",
                    "description": "Optional topic filter.",
                },
            },
            function=partial(self._do_search),
            parse_execute_args_func=json_parse_execute_args_func,
        )

        self.add_command(
            command_label=(
                "Save important information to long-term memory. "
                "Use this when the conversation contains facts, decisions, "
                "or knowledge worth remembering across sessions."
            ),
            command_name="memory_save",
            args={
                "content": {
                    "type": "string",
                    "description": "The text content to memorize.",
                    "required": True,
                },
                "room": {
                    "type": "string",
                    "description": "Topic category (e.g. 'backend', 'meetings').",
                    "default": "general",
                },
            },
            function=partial(self._do_save),
            parse_execute_args_func=json_parse_execute_args_func,
        )

        self.add_command(
            command_label=(
                "Query the knowledge graph for entity relationships. "
                "Use this to find facts about people, projects, or concepts."
            ),
            command_name="kg_query",
            args={
                "entity": {
                    "type": "string",
                    "description": "The entity name to query.",
                    "required": True,
                },
            },
            function=partial(self._do_kg_query),
            parse_execute_args_func=json_parse_execute_args_func,
        )

        self.add_command(
            command_label=(
                "Add a fact (triple) to the knowledge graph. "
                "Use this to record entity relationships discovered in "
                "conversations, e.g. 'Alice manages ProjectX'."
            ),
            command_name="kg_add",
            args={
                "subject": {
                    "type": "string",
                    "description": "The subject entity.",
                    "required": True,
                },
                "predicate": {
                    "type": "string",
                    "description": "The relationship type.",
                    "required": True,
                },
                "object": {
                    "type": "string",
                    "description": "The object entity.",
                    "required": True,
                },
            },
            function=partial(self._do_kg_add),
            parse_execute_args_func=json_parse_execute_args_func,
        )

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _do_search(
        self,
        query: str,
        top_k: int = 5,
        room: Optional[str] = None,
        **kwargs,
    ) -> str:
        entries = self._memory_store.search_memory(
            query=query,
            top_k=top_k,
            wing=self._wing,
            room=room,
        )
        if not entries:
            return "No relevant memories found."

        results = []
        for e in entries:
            results.append(
                {
                    "id": e.id,
                    "content": e.content,
                    "wing": e.wing,
                    "room": e.room,
                    "score": round(e.score, 3) if e.score else None,
                }
            )
        return json.dumps(results, ensure_ascii=False, indent=2)

    def _do_save(
        self,
        content: str,
        room: str = "general",
        **kwargs,
    ) -> str:
        entry = self._memory_store.write_memory(
            content=content,
            wing=self._wing,
            room=room,
        )
        return json.dumps(
            {
                "status": "saved",
                "id": entry.id,
                "wing": entry.wing,
                "room": entry.room,
            },
            ensure_ascii=False,
        )

    def _do_kg_query(self, entity: str, **kwargs) -> str:
        try:
            triples = self._memory_store.kg_query(entity=entity)
        except RuntimeError as e:
            return f"Knowledge graph not available: {e}"

        if not triples:
            return f"No knowledge graph entries found for '{entity}'."

        results = []
        for t in triples:
            results.append(
                {
                    "subject": t.subject,
                    "predicate": t.predicate,
                    "object": t.object_,
                    "valid_from": t.valid_from,
                    "valid_to": t.valid_to,
                }
            )
        return json.dumps(results, ensure_ascii=False, indent=2)

    def _do_kg_add(
        self,
        subject: str,
        predicate: str,
        object: str,
        **kwargs,
    ) -> str:
        try:
            triple_id = self._memory_store.kg_add(
                subject=subject,
                predicate=predicate,
                object_=object,
            )
        except RuntimeError as e:
            return f"Knowledge graph not available: {e}"

        return json.dumps(
            {
                "status": "added",
                "triple_id": triple_id,
                "subject": subject,
                "predicate": predicate,
                "object": object,
            },
            ensure_ascii=False,
        )
