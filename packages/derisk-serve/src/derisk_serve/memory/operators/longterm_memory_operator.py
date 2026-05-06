"""Long-term memory pipeline operators.

Two operators that plug into the agent generate pipeline:

- ``LongTermMemoryRetrievalOperator`` — runs **before** agent reasoning,
  recalls relevant memories from a Memory-type knowledge space and
  injects them into the agent context.

- ``LongTermMemoryWriteOperator`` — runs **after** agent reasoning,
  evaluates the conversation for important content and persists it
  to long-term memory.

Both are provider-agnostic — they operate on the ``MemoryStoreBase``
interface.
"""

import logging
from typing import Optional

from derisk import SystemApp
from derisk.agent import AgentGenerateContext
from derisk.core.awel import MapOperator
from derisk.core.awel.flow import (
    IOField,
    OperatorCategory,
    Parameter,
    ViewMetadata,
)
from derisk.core.awel.task.base import OUT
from derisk.storage.memory.base import MemoryStoreBase

logger = logging.getLogger(__name__)


class LongTermMemoryRetrievalOperator(MapOperator[AgentGenerateContext, OUT]):
    """Recall relevant long-term memories before agent reasoning.

    Searches the bound ``MemoryStoreBase`` with the current user message
    and injects matching memories into the agent context as formatted text.
    The ``PromptAssembler`` already accepts a ``memory_content`` parameter
    in ``assemble_user_prompt`` — this operator populates that.
    """

    metadata = ViewMetadata(
        label="LongTermMemoryRetrievalOperator",
        name="longterm_memory_retrieval_operator",
        category=OperatorCategory.DATABASE,
        description="Retrieve relevant long-term memories before reasoning.",
        parameters=[],
        inputs=[
            IOField.build_from(
                "Operator Request",
                "operator_request",
                AgentGenerateContext,
                "The Operator request.",
            )
        ],
        outputs=[
            IOField.build_from(
                "Operator Output",
                "operator_output",
                AgentGenerateContext,
                description="The Operator output with injected memories.",
            )
        ],
    )

    def __init__(
        self,
        memory_store: MemoryStoreBase,
        wing: str = "default",
        top_k: int = 5,
        max_distance: float = 0.4,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._memory_store = memory_store
        self._wing = wing
        self._top_k = top_k
        self._max_distance = max_distance

    async def map(self, context: AgentGenerateContext) -> OUT:
        """Search memory and inject results into context."""
        if not context.message or not context.message.content:
            return context

        query = context.message.content
        try:
            entries = await self._memory_store.asearch_memory(
                query=query,
                top_k=self._top_k,
                wing=self._wing,
                max_distance=self._max_distance,
            )
        except Exception as e:
            logger.warning(f"Long-term memory retrieval failed: {e}")
            return context

        if not entries:
            return context

        # Format memories as structured text for injection
        memory_lines = []
        for i, entry in enumerate(entries, 1):
            score_str = f" (relevance: {entry.score:.2f})" if entry.score else ""
            room_str = f" [{entry.room}]" if entry.room else ""
            memory_lines.append(
                f"{i}. {entry.content}{room_str}{score_str}"
            )

        memory_text = (
            "## Relevant Long-Term Memories\n\n" + "\n".join(memory_lines)
        )

        # Inject into the message context for PromptAssembler to pick up
        if context.message.context is None:
            context.message.context = {}
        if isinstance(context.message.context, dict):
            context.message.context["long_term_memory"] = memory_text
        else:
            # context might be a string — append
            pass

        logger.info(
            f"Injected {len(entries)} long-term memories for query: "
            f"{query[:80]}..."
        )
        return context


class LongTermMemoryWriteOperator(MapOperator[AgentGenerateContext, OUT]):
    """Evaluate and persist important content after agent reasoning.

    Extracts the user question and agent response from the context,
    checks a basic importance heuristic (length / keywords), and writes
    noteworthy content to the memory store.
    """

    metadata = ViewMetadata(
        label="LongTermMemoryWriteOperator",
        name="longterm_memory_write_operator",
        category=OperatorCategory.DATABASE,
        description="Write important conversation content to long-term memory.",
        parameters=[],
        inputs=[
            IOField.build_from(
                "Operator Request",
                "operator_request",
                AgentGenerateContext,
                "The Operator request.",
            )
        ],
        outputs=[
            IOField.build_from(
                "Operator Output",
                "operator_output",
                AgentGenerateContext,
                description="The Operator output.",
            )
        ],
    )

    # Keywords that suggest important content worth memorizing
    _IMPORTANCE_KEYWORDS = {
        "decision", "decided", "agreed", "conclusion", "important",
        "remember", "note", "key point", "action item", "deadline",
        "决定", "结论", "重要", "记住", "注意", "关键", "截止",
    }

    def __init__(
        self,
        memory_store: MemoryStoreBase,
        wing: str = "default",
        min_content_length: int = 50,
        auto_write: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._memory_store = memory_store
        self._wing = wing
        self._min_content_length = min_content_length
        self._auto_write = auto_write

    async def map(self, context: AgentGenerateContext) -> OUT:
        """Evaluate and write to memory if content is important."""
        if not self._auto_write:
            return context

        content = self._extract_content(context)
        if not content:
            return context

        if not self._is_important(content):
            return context

        room = self._classify_room(content)

        try:
            await self._memory_store.awrite_memory(
                content=content,
                wing=self._wing,
                room=room,
            )
            logger.info(
                f"Wrote to long-term memory: wing={self._wing}, room={room}, "
                f"length={len(content)}"
            )
        except Exception as e:
            logger.warning(f"Failed to write long-term memory: {e}")

        return context

    def _extract_content(self, context: AgentGenerateContext) -> Optional[str]:
        """Extract noteworthy content from the conversation context."""
        parts = []

        # User question
        if context.message and context.message.content:
            user_msg = context.message.content.strip()
            if user_msg:
                parts.append(f"User: {user_msg}")

        # Agent response (from rely_messages or last message)
        if context.rely_messages:
            for msg in context.rely_messages:
                if msg.content and msg.content.strip():
                    parts.append(f"Agent: {msg.content.strip()}")

        if not parts:
            return None

        combined = "\n".join(parts)
        if len(combined) < self._min_content_length:
            return None

        return combined

    def _is_important(self, content: str) -> bool:
        """Basic importance heuristic based on content length and keywords."""
        content_lower = content.lower()

        # Check for importance keywords
        for keyword in self._IMPORTANCE_KEYWORDS:
            if keyword in content_lower:
                return True

        # Long content is more likely to be important
        if len(content) > 500:
            return True

        return False

    def _classify_room(self, content: str) -> str:
        """Simple keyword-based topic classification."""
        content_lower = content.lower()

        topic_keywords = {
            "backend": {"api", "database", "server", "endpoint", "sql", "后端", "数据库"},
            "frontend": {"ui", "component", "css", "react", "vue", "前端", "页面"},
            "devops": {"deploy", "ci", "docker", "kubernetes", "部署", "运维"},
            "architecture": {"design", "pattern", "architecture", "refactor", "架构", "设计"},
            "bug": {"bug", "fix", "error", "issue", "缺陷", "修复"},
            "meeting": {"meeting", "discuss", "agree", "会议", "讨论"},
        }

        best_room = "general"
        best_score = 0
        for room, keywords in topic_keywords.items():
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > best_score:
                best_score = score
                best_room = room

        return best_room
