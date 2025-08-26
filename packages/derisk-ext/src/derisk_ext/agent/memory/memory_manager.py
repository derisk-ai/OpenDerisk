"""Agent memory module."""

from datetime import datetime
from typing import List, Optional, Type

from derisk.agent import AgentMemoryFragment, Memory, ImportanceScorer, \
    InsightExtractor, GptsMemory, ShortTermMemory
from derisk.agent.core.memory.base import WriteOperation, DiscardedMemoryFragments, \
    MemoryFragment
from derisk.agent.core.memory.gpts import GptsPlansMemory, GptsMessageMemory
from derisk.core import LLMClient
from derisk.storage.vector_store.filters import MetadataFilters
from derisk.util.annotations import immutable, mutable


class AgentMemoryManager(Memory[AgentMemoryFragment]):
    """Agent memory Manager."""

    def __init__(
        self,
        session_memory: Optional[Memory[AgentMemoryFragment]] = None,
        global_memory: Optional[Memory[AgentMemoryFragment]] = None,
        preference_memory: Optional[Memory[AgentMemoryFragment]] = None,
        importance_scorer: Optional[ImportanceScorer[AgentMemoryFragment]] = None,
        insight_extractor: Optional[InsightExtractor[AgentMemoryFragment]] = None,
        gpts_memory: Optional[GptsMemory] = None,
    ):
        """Create an agent memory.

        Args: session_memory(Memory[AgentMemoryFragment]): Memory to store session
        fragments importance_scorer(ImportanceScorer[AgentMemoryFragment]): Scorer to
        calculate the importance of memory fragments insight_extractor(
        InsightExtractor[AgentMemoryFragment]): Extractor to extract insights from
        memory fragments gpts_memory(GptsMemory): Memory to store GPTs related
        information
        """
        if not session_memory:
            session_memory = ShortTermMemory(buffer_size=5)
        if not gpts_memory:
            gpts_memory = GptsMemory()
        self.memory = session_memory
        self.importance_scorer = importance_scorer
        self.insight_extractor = insight_extractor
        self.gpts_memory = gpts_memory
        self.global_memory = global_memory
        self.preference_memory = preference_memory

    @immutable
    def structure_clone(
        self: "AgentMemoryManager", now: Optional[datetime] = None
    ) -> "AgentMemoryManager":
        """Return a structure clone of the memory.

        The gpst_memory is not cloned, it will be shared in whole agent memory.
        """
        m = AgentMemoryManager(
            session_memory=self.memory.structure_clone(now),
            importance_scorer=self.importance_scorer,
            insight_extractor=self.insight_extractor,
            gpts_memory=self.gpts_memory,
        )
        m._copy_from(self)
        return m

    @mutable
    def initialize(
        self,
        name: Optional[str] = None,
        llm_client: Optional[LLMClient] = None,
        importance_scorer: Optional[ImportanceScorer[AgentMemoryFragment]] = None,
        insight_extractor: Optional[InsightExtractor[AgentMemoryFragment]] = None,
        real_memory_fragment_class: Optional[Type[AgentMemoryFragment]] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """Initialize the memory."""
        self.memory.initialize(
            name=name,
            llm_client=llm_client,
            importance_scorer=importance_scorer or self.importance_scorer,
            insight_extractor=insight_extractor or self.insight_extractor,
            real_memory_fragment_class=real_memory_fragment_class
            or AgentMemoryFragment,
            session_id=session_id,
        )

    @mutable
    async def write(
        self,
        memory_fragment: AgentMemoryFragment,
        now: Optional[datetime] = None,
        op: WriteOperation = WriteOperation.ADD,
    ) -> Optional[DiscardedMemoryFragments[AgentMemoryFragment]]:
        """Write a memory fragment to the memory."""
        return await self.memory.write(memory_fragment, now)

    @mutable
    async def write_batch(
        self,
        memory_fragments: List[AgentMemoryFragment],
        now: Optional[datetime] = None,
    ) -> Optional[DiscardedMemoryFragments[AgentMemoryFragment]]:
        """Write a batch of memory fragments to the memory."""
        return await self.memory.write_batch(memory_fragments, now)

    @immutable
    async def read(
        self,
        observation: str,
        alpha: Optional[float] = None,
        beta: Optional[float] = None,
        gamma: Optional[float] = None,
    ) -> List[AgentMemoryFragment]:
        """Read memory fragments related to the observation.

        Args:
            observation(str): Observation
            alpha(float): Importance weight
            beta(float): Time weight
            gamma(float): Randomness weight

        Returns:
            List[AgentMemoryFragment]: List of memory fragments
        """
        return await self.memory.read(observation, alpha, beta, gamma)

    async def search(
        self,
        observation: str,
        top_k: int = 20,
        retrieve_strategy: str = "semantic",
        score_threshold: float = 0.0,
        discard_strategy: str = "fifo",
        condense_prompt: str = "",
        llm_token_limit: int = 4096,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata_filters: Optional[MetadataFilters] = None,
        alpha: Optional[float] = None,
        beta: Optional[float] = None,
        gamma: Optional[float] = None,
    ) -> List[MemoryFragment]:
        """Search memory fragments related to the observation.

         Args:
            observation(str): Observation
            top_k(int): Number of top results to return
            retrieve_strategy(str): Mode of retrieval, e.g.,"semantic", "all",
            "graph", "hybrid"
            score_threshold(float): Minimum score threshold for results
            discard_strategy:(str): Strategy for discarding results, e.g.,"fifo", "lru",
            condense_prompt(str): Prompt for generating summary
            llm_token_limit(int): Token limit for summary generation
            session_id(str): Session ID for filtering results
            agent_id(str): Agent ID for filtering results
            user_id(str): User ID for filtering results
            metadata_filters(MetadataFilters): Metadata filters for results
            alpha(float): Importance weight
            beta(float): Time weight
            gamma(float): Randomness weight

        Returns:
            List[AgentMemoryFragment]: List of memory fragments

        Returns:
            List[AgentMemoryFragment]: List of memory fragments
        """
        return await self.memory.search(
            observation=observation,
            top_k=top_k,
            retrieve_strategy=retrieve_strategy,
            score_threshold=score_threshold,
            discard_strategy=discard_strategy,
            condense_prompt=condense_prompt,
            llm_token_limit=llm_token_limit,
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
            metadata_filters=metadata_filters,
        )

    @mutable
    async def clear(self) -> List[AgentMemoryFragment]:
        """Clear the memory."""
        return await self.memory.clear()

    @property
    def plans_memory(self) -> GptsPlansMemory:
        """Return the plan memory."""
        return self.gpts_memory.plans_memory

    @property
    def message_memory(self) -> GptsMessageMemory:
        """Return the message memory."""
        return self.gpts_memory.message_memory
