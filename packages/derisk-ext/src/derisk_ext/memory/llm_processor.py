"""LLM-based Memory Processor implementation.

This module provides a concrete MemoryProcessor that uses LLM calls
for extraction, consolidation, importance scoring, and triple extraction.
It reuses existing components (LLMInsightExtractor, LLMImportanceScorer)
from the Agent Memory system.
"""

import logging
from typing import Any, Dict, List, Optional

from derisk.core import LLMClient
from derisk.storage.memory.base import KGTriple
from derisk.storage.memory.processor import (
    ConsolidationResult,
    ExtractedMemory,
    MemoryProcessor,
)

logger = logging.getLogger(__name__)

# Default extraction prompt
DEFAULT_EXTRACTION_PROMPT = """You are a memory extraction assistant. Analyze the following conversation and extract key information worth remembering across sessions.

Extract content that falls into these categories:
1. User preferences or requirements
2. Technical decisions or architectural choices
3. Important facts about people, projects, or systems
4. Action items or deadlines
5. Lessons learned or best practices

For each extracted item, provide:
- content: The actual content to remember
- room: A topic category (e.g. "backend", "frontend", "meetings", "preferences", "architecture", "bug", "general")
- importance: A score from 0.0 to 1.0

Respond in JSON format:
[{"content": "...", "room": "...", "importance": 0.8}]

Conversation:
{conversation}

Extraction:"""

# Default consolidation prompt
DEFAULT_CONSOLIDATION_PROMPT = """You are a memory consolidation assistant. Compare new content with existing memories and decide how to merge them.

Rules:
1. If new content is very similar to existing content (same topic, same facts), merge them into a single entry
2. If new content adds detail to existing content, update the existing entry
3. If new content is completely different, keep it as a new entry
4. Remove duplicate or contradictory entries, keeping the more recent/accurate one

Existing memories:
{existing}

New content:
{new}

Respond in JSON format:
{{"new": [{"content": "...", "room": "...", "importance": 0.8}], "updated": [{"id": "...", "content": "..."}], "discarded": ["id1", "id2"]}}

Consolidation:"""


class LLMMemoryProcessor(MemoryProcessor):
    """LLM-based memory processor.

    Uses LLM calls to:
    - Extract key content from conversations
    - Consolidate new content with existing memories
    - Score importance of memory content
    - Extract knowledge graph triples
    """

    def __init__(
        self,
        llm_client: LLMClient,
        model: Optional[str] = None,
    ):
        self._llm = llm_client
        self._model = model

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with a prompt."""
        from derisk.core import (
            ChatPromptTemplate,
            HumanPromptTemplate,
            ModelMessage,
            ModelRequest,
        )

        model = self._model
        if not model:
            models = await self._llm_client.models()
            if models:
                model = models[0].model

        prompt_template = ChatPromptTemplate(
            messages=[HumanPromptTemplate.from_template(prompt)]
        )
        messages = prompt_template.format_messages()
        model_messages = ModelMessage.from_base_messages(messages)
        model_request = ModelRequest.build_request(model, messages=model_messages)
        model_output = await self._llm.generate(model_request)

        if not model_output.success:
            raise ValueError("LLM call failed.")

        return model_output.text

    async def extract_key_content(
        self,
        conversation: str,
        extraction_prompt: Optional[str] = None,
    ) -> List[ExtractedMemory]:
        """Extract key content from conversation using LLM."""
        prompt = extraction_prompt or DEFAULT_EXTRACTION_PROMPT
        prompt = prompt.format(conversation=conversation)

        try:
            response = await self._call_llm(prompt)
            import json
            import re

            # Try to extract JSON from response
            json_match = re.search(r"\[.*\]", response, re.DOTALL)
            if json_match:
                items = json.loads(json_match.group())
                return [
                    ExtractedMemory(
                        content=item.get("content", ""),
                        room=item.get("room", "general"),
                        importance=item.get("importance", 0.5),
                    )
                    for item in items
                    if item.get("content")
                ]
        except Exception as e:
            logger.warning(f"Failed to extract key content: {e}")

        return []

    async def consolidate_memories(
        self,
        existing: List[Any],
        new: List[ExtractedMemory],
        consolidation_threshold: float = 0.7,
    ) -> ConsolidationResult:
        """Consolidate new content with existing memories using LLM."""
        if not existing:
            return ConsolidationResult(new_memories=new)

        existing_text = "\n".join(
            f"- [{e.id}] {e.content}" for e in existing[:10]
        )
        new_text = "\n".join(
            f"- {n.content} (room={n.room}, importance={n.importance})"
            for n in new
        )

        prompt = DEFAULT_CONSOLIDATION_PROMPT.format(
            existing=existing_text,
            new=new_text,
        )

        try:
            response = await self._call_llm(prompt)
            import json
            import re

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())

                new_memories = [
                    ExtractedMemory(
                        content=item.get("content", ""),
                        room=item.get("room", "general"),
                        importance=item.get("importance", 0.5),
                    )
                    for item in result.get("new", [])
                    if item.get("content")
                ]

                updated_memories = result.get("updated", [])
                discarded_ids = result.get("discarded", [])

                return ConsolidationResult(
                    new_memories=new_memories,
                    updated_memories=updated_memories,
                    discarded_ids=discarded_ids,
                )
        except Exception as e:
            logger.warning(f"Failed to consolidate memories: {e}")

        # Fallback: just return new content
        return ConsolidationResult(new_memories=new)

    async def score_importance(
        self,
        content: str,
        context: Optional[str] = None,
    ) -> float:
        """Score importance of memory content using LLM."""
        context_str = f"\nContext: {context}" if context else ""

        prompt = f"""Please give an importance score between 1 to 10 for the following observation.

Rules:
1. Learning experience of a skill is important
2. Occurrence of a particular event is important
3. User thoughts and emotions matter
4. More informative indicates more important

Respond with a single integer.

Observation:
{content}{context_str}

Rating:"""

        try:
            response = await self._call_llm(prompt)
            import re

            match = re.search(r"(\d+)", response)
            if match:
                score = int(match.group(1))
                return min(1.0, max(0.0, score / 10.0))
        except Exception as e:
            logger.warning(f"Failed to score importance: {e}")

        # Fallback: keyword-based scoring
        importance_keywords = {
            "decision", "decided", "agreed", "conclusion", "important",
            "remember", "note", "key point", "action item", "deadline",
        }
        has_keywords = any(
            kw in content.lower() for kw in importance_keywords
        )
        return 0.7 if has_keywords else 0.3

    async def extract_triples(
        self,
        content: str,
    ) -> List[Dict[str, Any]]:
        """Extract knowledge graph triples using LLM."""
        prompt = f"""Extract entity relationship triples from the following content.

For each relationship, provide:
- subject: The subject entity
- predicate: The relationship type
- object: The object entity
- confidence: Confidence score (0.0 to 1.0)

Respond in JSON format:
[{"subject": "...", "predicate": "...", "object": "...", "confidence": 0.8}]

Content:
{content}

Triples:"""

        try:
            response = await self._call_llm(prompt)
            import json
            import re

            json_match = re.search(r"\[.*\]", response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"Failed to extract triples: {e}")

        return []
