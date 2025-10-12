"""Agent memory module."""

import json
import logging
from datetime import datetime
from typing import Callable, List, Optional, Type, Union, cast

from typing_extensions import TypedDict

from derisk.core import LLMClient
from derisk.storage.vector_store.filters import MetadataFilters
from derisk.util.annotations import immutable, mutable
from derisk.util.id_generator import new_id

from .base import (
    DiscardedMemoryFragments,
    ImportanceScorer,
    InsightExtractor,
    Memory,
    MemoryFragment,
    ShortTermMemory,
    WriteOperation,
)
from .gpts import GptsMemory, GptsMessageMemory, GptsPlansMemory

logger = logging.getLogger(__name__)


class StructuredObservation(TypedDict):
    """Structured observation for agent memory."""

    question: Optional[str]
    thought: Optional[str]
    action: Optional[str]
    action_input: Optional[str]
    observation: Optional[str]


class AgentMemoryFragment(MemoryFragment):
    """Default memory fragment for agent memory."""

    def __init__(
        self,
        observation: str,
        embeddings: Optional[List[float]] = None,
        memory_id: Optional[int] = None,
        importance: Optional[float] = None,
        last_accessed_time: Optional[datetime] = None,
        is_insight: bool = False,
        rounds: Optional[int] = None,
        create_time: Optional[datetime] = None,
        similarity: Optional[float] = None,
        message_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        role: Optional[str] = None,
        task_goal: Optional[str] = None,
        thought: Optional[str] = None,
        action: Optional[str] = None,
        action_result: Optional[str] = None,
        agent_type: Optional[str] = None,
        condense: Optional[bool] = False,
        user_input: Optional[str] = None,
        ai_message: Optional[str] = None,
    ):
        """Create a memory fragment."""
        if not memory_id:
            # Generate a new memory id, we use snowflake id generator here.
            memory_id = new_id()
        self.observation = observation
        self._embeddings = embeddings
        self.memory_id: int = cast(int, memory_id)
        self._importance: Optional[float] = importance
        self._last_accessed_time: Optional[datetime] = last_accessed_time
        self._is_insight = is_insight
        self.rounds: Optional[int] = rounds
        self._create_time: Optional[datetime] = create_time or datetime.utcnow()
        self._similarity: Optional[float] = similarity
        self._message_id: Optional[str] = message_id
        self._agent_id: Optional[str] = agent_id
        self._session_id: Optional[str] = session_id
        self._role: Optional[str] = role
        self._task_goal: Optional[str] = task_goal
        self._thought: Optional[str] = thought
        self._action: Optional[str] = action
        self._action_result: Optional[str] = action_result
        self._agent_type: Optional[str] = agent_type
        self._condense: Optional[bool] = condense
        self._user_input: Optional[bool] = user_input
        self._ai_message: Optional[bool] = ai_message

    @property
    def id(self) -> int:
        """Return the memory id."""
        return self.memory_id

    @property
    def raw_observation(self) -> str:
        """Return the raw observation."""
        return self.observation

    @property
    def embeddings(self) -> Optional[List[float]]:
        """Return the embeddings of the memory fragment."""
        return self._embeddings

    @property
    def similarity(self) -> Optional[float]:
        """Return the similarity of the memory fragment.

        Returns:
            Optional[float]: Similarity of the memory fragment
        """
        return self._similarity

    @property
    def create_time(self) -> Optional[datetime]:
        """Return the create_time of the memory fragment.

        Returns:
            Optional[datetime]: Return the create_time of the memory fragment.
        """
        return self._create_time or datetime.utcnow()

    @property
    def message_id(self) -> Optional[str]:
        """Return the message_id.

        Returns:
            Optional[str]: str.
        """
        return self._message_id

    @property
    def agent_id(self) -> Optional[str]:
        """Return the agent_id.

        Returns:
            Optional[str]: str.
        """
        return self._agent_id

    @property
    def agent_type(self) -> Optional[str]:
        """Return the agent_type.

        Returns:
            Optional[str]: str.
        """
        return self._agent_type

    @property
    def session_id(self) -> Optional[str]:
        """Return the session_id.

        Returns:
            Optional[str]: str.
        """
        return self._session_id

    @property
    def role(self) -> Optional[str]:
        """Return the role.

        Returns:
            Optional[str]: str.
        """
        return self._role

    @property
    def task_goal(self) -> Optional[str]:
        """Return the task_goal.

        Returns:
            Optional[str]: str.
        """
        return self._task_goal

    @property
    def thought(self) -> Optional[str]:
        """Return the task_goal.

        Returns:
            Optional[str]: str.
        """
        return self._thought

    @property
    def action(self) -> Optional[str]:
        """Return the action.

        Returns:
            Optional[str]: str.
        """
        return self._action

    @property
    def action_result(self) -> Optional[str]:
        """Return the action_result.

        Returns:
            Optional[str]: str.
        """
        return self._action_result

    @property
    def user_input(self) -> Optional[str]:
        """Return the user_input.

        Returns:
            Optional[str]: str.
        """
        return self._user_input

    @property
    def ai_message(self) -> Optional[str]:
        """Return the ai_message.

        Returns:
            Optional[str]: str.
        """
        return self._ai_message

    def update_embeddings(self, embeddings: List[float]) -> None:
        """Update the embeddings of the memory fragment.

        Args:
            embeddings(List[float]): embeddings
        """
        self._embeddings = embeddings

    def calculate_current_embeddings(
        self, embedding_func: Callable[[List[str]], List[List[float]]]
    ) -> List[float]:
        """Calculate the embeddings of the memory fragment.

        Args:
            embedding_func(Callable[[List[str]], List[List[float]]]): Function to
                compute embeddings

        Returns:
            List[float]: Embeddings of the memory fragment
        """
        embeddings = embedding_func([self.observation])
        return embeddings[0]

    @property
    def is_insight(self) -> bool:
        """Return whether the memory fragment is an insight.

        Returns:
            bool: Whether the memory fragment is an insight
        """
        return self._is_insight

    @property
    def importance(self) -> Optional[float]:
        """Return the importance of the memory fragment.

        Returns:
            Optional[float]: Importance of the memory fragment
        """
        return self._importance

    @property
    def condense(self) -> Optional[float]:
        """Return condense of the memory fragment.

        Returns:
            Optional[float]: Condense of the memory fragment
        """
        return self._condense

    def update_importance(self, importance: float) -> Optional[float]:
        """Update the importance of the memory fragment.

        Args:
            importance(float): Importance of the memory fragment

        Returns:
            Optional[float]: Old importance
        """
        old_importance = self._importance
        self._importance = importance
        return old_importance

    @property
    def last_accessed_time(self) -> Optional[datetime]:
        """Return the last accessed time of the memory fragment.

        Used to determine the least recently used memory fragment.

        Returns:
            Optional[datetime]: Last accessed time
        """
        return self._last_accessed_time

    def update_accessed_time(self, now: datetime) -> Optional[datetime]:
        """Update the last accessed time of the memory fragment.

        Args:
            now(datetime): Current time

        Returns:
            Optional[datetime]: Old last accessed time
        """
        old_time = self._last_accessed_time
        self._last_accessed_time = now
        return old_time

    @classmethod
    def build_from(
        cls: Type["AgentMemoryFragment"],
        observation: str,
        embeddings: Optional[List[float]] = None,
        memory_id: Optional[int] = None,
        importance: Optional[float] = None,
        is_insight: bool = False,
        last_accessed_time: Optional[datetime] = None,
        rounds: Optional[int] = None,
        create_time: Optional[datetime] = None,
        similarity: Optional[float] = None,
        message_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        role: Optional[str] = None,
        task_goal: Optional[str] = None,
        thought: Optional[str] = None,
        action: Optional[str] = None,
        action_result: Optional[str] = None,
        agent_type: Optional[str] = None,
        condense: Optional[bool] = None,
        user_input: Optional[bool] = None,
        ai_message: Optional[bool] = None,
        **kwargs,
    ) -> "AgentMemoryFragment":
        """Build a memory fragment from the given parameters."""
        return cls(
            observation=observation,
            embeddings=embeddings,
            memory_id=memory_id,
            importance=importance,
            last_accessed_time=last_accessed_time,
            is_insight=is_insight,
            rounds=rounds,
            create_time=create_time,
            similarity=similarity,
            message_id=message_id,
            agent_id=agent_id,
            task_goal=task_goal,
            thought=thought,
            action=action,
            action_result=action_result,
            role=role,
            agent_type=agent_type,
            condense=condense,
            user_input=user_input,
            ai_message=ai_message,
        )

    def copy(self: "AgentMemoryFragment") -> "AgentMemoryFragment":
        """Return a copy of the memory fragment."""
        return AgentMemoryFragment.build_from(
            observation=self.observation,
            embeddings=self._embeddings,
            memory_id=self.memory_id,
            importance=self.importance,
            last_accessed_time=self.last_accessed_time,
            is_insight=self.is_insight,
            rounds=self.rounds,
            create_time=self.create_time,
            similarity=self.similarity,
            message_id=self.message_id,
            agent_id=self.agent_id,
            task_goal=self._task_goal,
            thought=self._thought,
            action=self._action,
            action_result=self._action_result,
            role=self.role,
            agent_type=self.agent_type,
            condense=self.condense,
            user_input=self.user_input,
            ai_message=self.ai_message,
        )

    def to_dict(self):
        """Convert the memory fragment to a dictionary."""
        return {
            "observation": self.observation,
            "embeddings": self._embeddings,
            "memory_id": self.memory_id,
            "importance": self.importance,
            "last_accessed_time": self.last_accessed_time,
            "is_insight": self.is_insight,
            "rounds": self.rounds,
            "create_time": self.create_time,
            "similarity": self.similarity,
            "message_id": self._message_id,
            "role": self._role,
            "task_goal": self._task_goal,
            "thought": self._thought,
            "action": self._action,
            "action_result": self._action_result,
            "agent_type": self._agent_type,
            "condense": self._condense,
            "user_input": self._user_input,
            "ai_message": self._ai_message,
        }


class StructuredAgentMemoryFragment(AgentMemoryFragment):
    """Structured memory fragment for agent memory."""

    def __init__(
        self,
        observation: Union[StructuredObservation, List[StructuredObservation]],
        embeddings: Optional[List[float]] = None,
        memory_id: Optional[int] = None,
        importance: Optional[float] = None,
        last_accessed_time: Optional[datetime] = None,
        is_insight: bool = False,
    ):
        """Create a structured memory fragment."""
        super().__init__(
            observation=self.to_raw_observation(observation),
            embeddings=embeddings,
            memory_id=memory_id,
            importance=importance,
            last_accessed_time=last_accessed_time,
            is_insight=is_insight,
        )
        self._structured_observation = observation

    def to_raw_observation(
        self, observation: Union[StructuredObservation, List[StructuredObservation]]
    ) -> str:
        """Convert the structured observation to a raw observation.

        Args:
            observation(StructuredObservation): Structured observation

        Returns:
            str: Raw observation
        """
        return json.dumps(observation, ensure_ascii=False)

    @classmethod
    def build_from(
        cls: Type["AgentMemoryFragment"],
        observation: Union[str, StructuredObservation],
        embeddings: Optional[List[float]] = None,
        memory_id: Optional[int] = None,
        importance: Optional[float] = None,
        is_insight: bool = False,
        last_accessed_time: Optional[datetime] = None,
        **kwargs,
    ) -> "AgentMemoryFragment":
        """Build a memory fragment from the given parameters."""
        if isinstance(observation, str):
            observation = json.loads(observation)
        return cls(
            observation=observation,
            embeddings=embeddings,
            memory_id=memory_id,
            importance=importance,
            last_accessed_time=last_accessed_time,
            is_insight=is_insight,
        )

    def reduce(
        self, memory_fragments: List["StructuredAgentMemoryFragment"], **kwargs
    ) -> "StructuredAgentMemoryFragment":
        """Reduce memory fragments to a single memory fragment.

        Args:
            memory_fragments(List[T]): Memory fragments

        Returns:
            T: The reduced memory fragment
        """
        if len(memory_fragments) == 0:
            raise ValueError("Memory fragments is empty.")
        if len(memory_fragments) == 1:
            return memory_fragments[0]

        obs = []
        for memory_fragment in memory_fragments:
            try:
                obs.append(json.loads(memory_fragment.raw_observation))
            except Exception as e:
                logger.warning(
                    "Failed to parse observation %s: %s",
                    memory_fragment.raw_observation,
                    e,
                )
        return self.current_class.build_from(obs, **kwargs)  # type: ignore


class AgentMemory(Memory[AgentMemoryFragment]):
    """Agent memory."""

    def __init__(
        self,
        memory: Optional[Memory[AgentMemoryFragment]] = None,
        preference_memory: Optional[Memory[AgentMemoryFragment]] = None,
        importance_scorer: Optional[ImportanceScorer[AgentMemoryFragment]] = None,
        insight_extractor: Optional[InsightExtractor[AgentMemoryFragment]] = None,
        gpts_memory: Optional[GptsMemory] = None,
    ):
        """Create an agent memory.

        Args:
            memory(Memory[AgentMemoryFragment]): Memory to store fragments
            importance_scorer(ImportanceScorer[AgentMemoryFragment]): Scorer to
                calculate the importance of memory fragments
            insight_extractor(InsightExtractor[AgentMemoryFragment]): Extractor to
                extract insights from memory fragments
            gpts_memory(GptsMemory): Memory to store GPTs related information
        """
        if not memory:
            memory = ShortTermMemory(buffer_size=5)
        if not gpts_memory:
            gpts_memory = GptsMemory()
        self.memory: Memory[AgentMemoryFragment] = cast(
            Memory[AgentMemoryFragment], memory
        )
        if preference_memory:
            self.preference_memory: Memory[AgentMemoryFragment] = cast(
                Memory[AgentMemoryFragment], preference_memory
            )
        self.importance_scorer = importance_scorer
        self.insight_extractor = insight_extractor
        self.gpts_memory = gpts_memory

    @immutable
    def structure_clone(
        self: "AgentMemory", now: Optional[datetime] = None
    ) -> "AgentMemory":
        """Return a structure clone of the memory.

        The gpst_memory is not cloned, it will be shared in whole agent memory.
        """
        m = AgentMemory(
            memory=self.memory.structure_clone(now),
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
        **kwargs
    ) -> Optional[DiscardedMemoryFragments[AgentMemoryFragment]]:
        """Write a memory fragment to the memory."""
        return await self.memory.write(memory_fragment, now, op, **kwargs)

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
        discard_strategy: Optional[str] = "fifo",
        score_threshold: Optional[float] = 0.0,
        condense_prompt: Optional[str] = "",
        condense_model: Optional[str] = "deepseek-v3",
        llm_token_limit: Optional[int] = 4096,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        enable_global_session: Optional[bool] = False,
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
            discard_strategy:(str): Mode of discard memory, e.g.,"fifo", "lru",
             "similarity",
            condense_prompt(str): Prompt for generating summary
            condense_model(str): LLM for generating summary
            llm_token_limit(int): Token limit for summary generation
            session_id(str): Session ID for filtering results
            agent_id(str): Agent ID for filtering results
            user_id(str): User ID for filtering results
            enable_global_session(bool): False to use session_id, True to use global
            session.
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
            condense_model=condense_model,
            enable_global_session=enable_global_session,
            llm_token_limit=llm_token_limit,
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
            metadata_filters=metadata_filters,
        )

    def list(
        self,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        message_id: Optional[str] = None,
        metadata_filters: Optional[MetadataFilters] = None
    ):
        """List all memories in the session memory.

        Args:
            session_id(str): Session ID to filter memories
            agent_id(str): Agent ID to filter memories
            message_id(str): Message ID to filter memories
            metadata_filters(MetadataFilters): Additional metadata filters
        """
        return self.memory.list(
            session_id=session_id,
            agent_id=agent_id,
            message_id=message_id,
            metadata_filters=metadata_filters,
        )

    @mutable
    async def clear(self) -> List[AgentMemoryFragment]:
        """Clear the memory."""
        return await self.memory.clear()

    # @property
    # def plans_memory(self) -> GptsPlansMemory:
    #     """Return the plan memory."""
    #     return self.gpts_memory.plans_memory

    # @property
    # def message_memory(self) -> GptsMessageMemory:
    #     """Return the message memory."""
    #     return self.gpts_memory.message_memory
