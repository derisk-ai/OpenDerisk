import logging
from concurrent.futures import Executor
from copy import deepcopy
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, Type, List, cast, Callable

from derisk.agent import LongTermMemory, GptsMemory
from derisk.agent.core.memory.base import WriteOperation, DiscardedMemoryFragments, \
    MemoryFragment, InsightExtractor, ImportanceScorer, T
from derisk.core import LLMClient, Chunk
from derisk.storage.vector_store.base import VectorStoreBase
from derisk.storage.vector_store.filters import MetadataFilters, MetadataFilter, FilterCondition
from derisk.util.annotations import mutable
from derisk.util.id_generator import new_id
from derisk_ext.agent.memory.session import SessionMemoryFragment, MemoryType, DiscardStrategy

_FORGET_PLACEHOLDER = "[FORGET]"
_MERGE_PLACEHOLDER = "[MERGE]"
_METADATA_BUFFER_IDX = "buffer_idx"
_METADATA_LAST_ACCESSED_AT = "last_accessed_at"
_METADATA_CREATE_TIME = "create_time"
_METADATA_SESSION_ID = "session_id"
_METADATA_AGENT_ID = "agent_id"
_METADAT_IMPORTANCE = "importance"
_MEMORY_ID = "memory_id"
_MESSAGE_ID = "message_id"
_ROLE = "role"
_TASK_GOAL = "task_goal"
_THOUGHT = "thought"
_ACTION = "action"
_ACTION_RESULT = "action_result"

COMP_RATE = {
            "math": 1.2,
            "code": 3.67,
            "ch": 1.86,
            "en": 3.23
        }

logger = logging.getLogger(__name__)


class PreferenceMemoryFragment(SessionMemoryFragment):
    """Session memory fragment for Session memory."""

    def __init__(
        self,
        observation: Optional[str] = None,
        agent_id: Optional[str] = None,
        embeddings: Optional[List[float]] = None,
        memory_id: Optional[int] = None,
        importance: Optional[float] = None,
        last_accessed_time: Optional[datetime] = None,
        rounds: Optional[int] = None,
        is_insight: bool = False,
        create_time: Optional[datetime] = None,
        similarity: Optional[float] = None,
        message_id: Optional[str] = None,
        role: Optional[str] = None,
        task_goal: Optional[str] = None,
        thought: Optional[str] = None,
        action: Optional[str] = None,
        action_result: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """Create a Session memory fragment.

        Args:
            observation(str): Observation content
            embeddings(List[float]): Embeddings of the observation
            memory_id(int): Unique identifier for the memory fragment
            importance(Optional[float]): Importance score of the memory fragment
            last_accessed_time(Optional[datetime]): Last accessed time of the memory fragment
            is_insight(bool): Whether the memory fragment is an insight
            create_time(Optional[datetime]): Creation time of the memory fragment
            similarity(Optional[float]): Similarity score of the memory fragment
            rounds(Optional[int]): Rounds of the memory fragment
            is_insight(bool): Whether the memory fragment is an insight
            message_id(Optional[str]): Message ID associated with the memory fragment
            agent_id(Optional[str]): Agent ID associated with the memory fragment
            role(Optional[str]): Role of the memory fragment
            task_goal(Optional[str]): Task goal associated with the memory fragment
            thought(Optional[str]): Thought associated with the memory fragment
            action(Optional[str]): Action associated with the memory fragment
            action_result(Optional[str]): Action result associated with the memory fragment
        Raises:
            ValueError: If memory_id is not provided and cannot be generated.
        Raises:
            TypeError: If memory_id is not an integer.
        """
        if not memory_id:
            # Generate a new memory id, we use snowflake id generator here.
            memory_id = new_id()
        super().__init__(
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
            role=role,
            task_goal=task_goal,
            thought=thought,
            action=action,
            action_result=action_result,
        )
        self._metadata = metadata
        self._agent_id = agent_id

    @classmethod
    def build_from(
        cls: Type["PreferenceMemoryFragment"],
        observation: Optional[str] = None,
        agent_id: Optional[str] = None,
        embeddings: Optional[List[float]] = None,
        memory_id: Optional[int] = None,
        importance: Optional[float] = None,
        is_insight: bool = False,
        last_accessed_time: Optional[datetime] = None,
        create_time: Optional[datetime] = None,
        similarity: Optional[float] = None,
        rounds: Optional[int] = None,
        message_id: Optional[str] = None,
        role: Optional[str] = None,
        task_goal: Optional[str] = None,
        thought: Optional[str] = None,
        action: Optional[str] = None,
        action_result: Optional[str] = None,
        metadata: Optional[Dict] = None,
        **kwargs,
    ) -> "PreferenceMemoryFragment":
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
            role=role,
            task_goal=task_goal,
            thought=thought,
            action=action,
            action_result=action_result,
            metadata=metadata,
            agent_id=agent_id,
        )

    def copy(self: "PreferenceMemoryFragment") -> "PreferenceMemoryFragment":
        """Return a copy of the memory fragment."""
        return PreferenceMemoryFragment.build_from(
            observation=self.observation,
            agent_id=self._agent_id,
            embeddings=self._embeddings,
            memory_id=self.memory_id,
            importance=self.importance,
            last_accessed_time=self.last_accessed_time,
            is_insight=self.is_insight,
            rounds=self.rounds,
            create_time=self.create_time,
            similarity=self.similarity,
            message_id=self._message_id,
            role=self._role,
            task_goal=self._task_goal,
            thought=self._thought,
            action=self._action,
            action_result=self._action_result,
            metadata=self._metadata,
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
            "metadata": self._metadata,
            "agent_id": self._agent_id,
        }

    @property
    def metadata(self):
        """Return the metadata of the memory."""
        return self._metadata

    @property
    def agent_id(self):
        """Return the agent ID associated with this memory."""
        return self._agent_id


class PreferenceMemory(LongTermMemory):
    """
    SessionMemory is a specialized memory class for managing session-specific data.

    It extends LongTermMemory to handle session-related information, providing methods
    for adding, retrieving, and managing session memory fragments.
    """

    def __init__(
        self,
        agent_id: str,
        vector_store: VectorStoreBase,
        executor: Optional[Executor] = None,
        now: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Create a session memory.

        Args:
            agent_id(str): Unique identifier for the agent
            vector_store(VectorStoreBase): Vector store for storing memory fragments
            executor(Executor): Executor to use for running tasks
            now(datetime): Current time, used for initializing timestamps
            used to determine when to reflect on memory
        """
        super().__init__(
            vector_store=vector_store,
            executor=executor,
            now=now,
            metadata=metadata,
        )
        self._agent_id = agent_id
        self._metadata: Dict[str, Any] = metadata or {
            "memory_type": self.memory_type
        }

    def initialize(
        self,
        name: Optional[str] = None,
        llm_client: Optional[LLMClient] = None,
        importance_scorer: Optional[ImportanceScorer] = None,
        insight_extractor: Optional[InsightExtractor] = None,
        real_memory_fragment_class: Optional[Type[T]] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        """Initialize memory.

        Some agent may need to initialize memory before using it.
        """
        self.name = name
        self.llm_client = llm_client
        self.importance_scorer = importance_scorer
        self.insight_extractor = insight_extractor
        self._real_memory_fragment_class = real_memory_fragment_class
        self._agent_id = agent_id

    def structure_clone(
        self: "PreferenceMemory[T]", now: Optional[datetime] = None
    ) -> "PreferenceMemory[T]":
        """Return a structure clone of the memory."""
        now = now or self.now
        m = PreferenceMemory(
            agent_id=self._agent_id,
            now=now,
            vector_store=self._vector_store,
            executor=self.executor,
            metadata=self._metadata,
        )
        m._copy_from(self)
        return m

    def _fragment_to_chunk(
        self,
        memory_fragment: PreferenceMemoryFragment,
        now: Optional[datetime] = None,
        op: WriteOperation = WriteOperation.ADD,
    ):
        last_accessed_time = memory_fragment.last_accessed_time or now or self.now
        msg_content = f"{memory_fragment.raw_observation}" or "EMPTY"
        metadata = {k: v for k, v in self._metadata.items()}
        metadata[_MEMORY_ID] = memory_fragment.id
        if memory_fragment.role:
            metadata[_ROLE] = memory_fragment.role
        if memory_fragment.task_goal:
            metadata[_TASK_GOAL] = memory_fragment.task_goal
        if memory_fragment.thought:
            metadata[_THOUGHT] = memory_fragment.thought
        if memory_fragment.action:
            metadata[_ACTION] = memory_fragment.action
        metadata[_ACTION_RESULT] = memory_fragment.action_result
        if memory_fragment.message_id:
            metadata[_MESSAGE_ID] = memory_fragment.message_id
        metadata[_METADATA_LAST_ACCESSED_AT] = (
            last_accessed_time
        ).strftime("%Y-%m-%d %H:%M:%S")
        if memory_fragment.create_time:
            metadata[_METADATA_CREATE_TIME] = (
                memory_fragment.create_time
            ).strftime("%Y-%m-%d %H:%M:%S")
        metadata["operation"] = op.value
        if memory_fragment.rounds:
            metadata["rounds"] = memory_fragment.rounds
        if memory_fragment.agent_id:
            metadata[_METADATA_AGENT_ID] = memory_fragment.agent_id
        if memory_fragment.metadata:
            for key, value in memory_fragment.metadata.items():
                if isinstance(value, (str, int, float)):
                    metadata[key] = value
                if isinstance(value, (List, set, tuple, dict)):
                    metadata[key] = str(value)
        return Chunk(
            content=msg_content,
            metadata=metadata,
        )

    async def write(
        self,
        memory_fragment: MemoryFragment,
        now: Optional[datetime] = None,
        op: WriteOperation = WriteOperation.ADD,
        **kwargs,
    ) -> Optional[DiscardedMemoryFragments[SessionMemoryFragment]]:
        """Write a memory fragment to the memory."""
        return await self.write_batch(memory_fragments=[memory_fragment], now=now, op=op, **kwargs)

    @mutable
    async def write_batch(
        self,
        memory_fragments: List[T],
        now: Optional[datetime] = None,
        op: WriteOperation = WriteOperation.ADD,
        **kwargs
    ) -> Optional[DiscardedMemoryFragments[T]]:
        """Write a batch of memory fragments to the memory.

        For memory recovery, we only write to sensory memory and short term memory.
        """
        if self._vector_store:
            documents = [self._fragment_to_chunk(fragment, now=now, op=op) for fragment in memory_fragments]
            await self._vector_store.aload_document(documents)

    async def read(
        self,
        observation: Optional[str] = None,
        alpha: Optional[float] = None,
        beta: Optional[float] = None,
        gamma: Optional[float] = None,
    ) -> List[T]:
        """Read memory fragments related to the observation."""
        return await self.search(observation=observation, now=self.now)

    async def search(
        self,
        observation: Optional[str] = None,
        top_k: int = 50,
        retrieve_strategy: str = "exact",
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        score_threshold: Optional[float] = None,
        desc: Optional[bool] = True,
        discard_strategy: Optional[str] = None,
        llm_token_limit: int = 4096,
        condense_prompt: Optional[str] = None,
        condense_model: Optional[str] = None,
        enable_global_session: bool = False,
        metadata_filters: Optional[MetadataFilters] = None,
    ) -> List[MemoryFragment]:
        """Search memory fragments related to the observation.

        Args:
            observation(str): Observation
            top_k(int): Number of top results to return
            retrieve_strategy(str): Mode of retrieval, e.g.,"semantic", "all",
            "graph", "hybrid"
            agent_id(str): Agent ID for filtering results
            user_id(str): User ID for filtering results
            score_threshold(float): Minimum score threshold for results
            desc(bool): Whether to sort results in descending order
            metadata_filters(MetadataFilters): Metadata filters for results

        Returns:
            List[AgentMemoryFragment]: List of memory fragments
        """
        logger.info(f"Preference Memory Search agent_id-{agent_id}, "
                    f"user_id-{user_id}, "
                    f"retrieve_strategy-{retrieve_strategy}, "
                    f"observation-{observation}, "
                    f"top_k-{top_k}, "
                    f"metadata_filters-{metadata_filters}, "
                    )
        metadata_base = {}
        if agent_id:
            metadata_base["agent_id"] = agent_id
        if user_id:
            metadata_base["user_id"] = user_id

        retrieved_memories = []
        filters = metadata_filters.filters if metadata_filters else []
        condition = metadata_filters.condition if metadata_filters else FilterCondition.AND
        for key, value in metadata_base.items():
            if isinstance(value, (str, int, float)):
                filters.append(MetadataFilter(key=key, value=value))
        metadata_filters = MetadataFilters(filters=filters, condition=condition)
        if retrieve_strategy == "exact":
            if self._vector_store:
                if not self._vector_store.vector_name_exists():
                    return []

                search_memories = self._vector_store.exact_search(
                    filters=metadata_filters,
                    topk=top_k,
                    desc=desc,
                )
        else:
            raise ValueError(
                f"Unknown retrieve_mode: {retrieve_strategy}. "
                "Supported modes are: semantic, graph, hybrid, all."
            )

        for retrieved_chunk in search_memories:
            # task_goal = retrieved_chunk.metadata.get(_TASK_GOAL)
            # thought = retrieved_chunk.metadata.get(_THOUGHT)
            # action = retrieved_chunk.metadata.get(_ACTION)
            # observation = retrieved_chunk.metadata.get(_ACTION_RESULT)
            # memory_content = []
            retrieved_memories.append(
                PreferenceMemoryFragment.build_from(
                    observation=retrieved_chunk.content,
                    importance=retrieved_chunk.score,
                    similarity=retrieved_chunk.score,
                    create_time=retrieved_chunk.metadata.get(
                        _METADATA_CREATE_TIME, None
                    ),
                    last_accessed_time=retrieved_chunk.metadata.get(
                        _METADATA_LAST_ACCESSED_AT, None),
                    agent_id=retrieved_chunk.metadata.get(_METADATA_AGENT_ID, None),
                    metadata=retrieved_chunk.metadata,
                )
            )
        preference_memories = await self.discard_memories(
            retrieved_memories=retrieved_memories,
            discard_strategy=discard_strategy,
            llm_token_limit=llm_token_limit,
            similarity_threshold=score_threshold,
            condense_model=condense_model,
            condense_prompt=condense_prompt,
        )
        return preference_memories

    def list(
        self,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        message_id: Optional[str] = None,
        metadata_filters: Optional[MetadataFilters] = None
    ):
        """List all memories in the session memory.

        Args:
            session_id(str): Session ID to filter memories
            message_id(str): Message ID to filter memories
            agent_id(str): Agent ID to filter memories
            metadata_filters(MetadataFilters): Additional metadata filters
        """
        metadata_base = deepcopy(metadata_filters) if metadata_filters else {}
        if session_id:
            metadata_base[_METADATA_SESSION_ID] = session_id
        if agent_id:
            metadata_base[_METADATA_AGENT_ID] = agent_id
        if message_id:
            metadata_base["message_id"] = message_id

        filters = []
        for key, value in metadata_base.items():
            if isinstance(value, (str, int, float)):
                filters.append(MetadataFilter(key=key, value=value))
        metadata_filters = MetadataFilters(filters=filters)
        memory_fragments = []
        if self._vector_store:
            if not self._vector_store.vector_name_exists():
                return []

            memories = self._vector_store.exact_search(
                filters=metadata_filters
            )
            for retrieved_chunk in memories:
                memory_fragments.append(
                    PreferenceMemoryFragment.build_from(
                        observation=retrieved_chunk.content,
                        importance=retrieved_chunk.score,
                        similarity=retrieved_chunk.score,
                        create_time=retrieved_chunk.metadata.get(
                            _METADATA_CREATE_TIME, None
                        ),
                        last_accessed_time=retrieved_chunk.metadata.get(
                            _METADATA_LAST_ACCESSED_AT, None),
                        rounds=retrieved_chunk.metadata.get("rounds", None),
                        agent_id=retrieved_chunk.metadata.get(_METADATA_AGENT_ID, None),
                        role=retrieved_chunk.metadata.get("role", None),
                        session_id=retrieved_chunk.metadata.get(
                            _METADATA_SESSION_ID, None
                        ),
                        message_id=retrieved_chunk.metadata.get(_MESSAGE_ID, None),
                        task_goal=retrieved_chunk.metadata.get(_TASK_GOAL, None),
                        thought=retrieved_chunk.metadata.get(_THOUGHT, None),
                        action=retrieved_chunk.metadata.get(_ACTION, None),
                        action_result=retrieved_chunk.metadata.get(
                            _ACTION_RESULT, None
                        )
                    )
                )
        return memory_fragments


    async def discard_memories(
            self,
            retrieved_memories: List[SessionMemoryFragment],
            discard_strategy: str = DiscardStrategy.FIFO.value,
            llm_token_limit: int = 8192,
            similarity_threshold: float = 0.0,
            condense_model: str = "deepseek-v3",
            condense_prompt: Optional[str] = None,
    ):
        """Discard memories based on the discard strategy."""
        while self._calculate_total_tokens(retrieved_memories) > llm_token_limit:
            logger.info(
                f"Preference Memory-{self._agent_id} "
                f"Discarding memories with {discard_strategy}"
            )
            if discard_strategy == DiscardStrategy.FIFO.value:
                retrieved_memories.sort(key=lambda x: x.create_time)
                discard_fragment = retrieved_memories.pop(0)
                logger.info("FIFO Discarded memory fragment: %s",
                            discard_fragment.raw_observation)
            elif discard_strategy == DiscardStrategy.LRU.value:
                retrieved_memories.sort(key=lambda x: x.last_accessed_time)
                discard_fragment = retrieved_memories.pop(0)
                logger.info("LRU Discarded memory fragment: %s",
                            discard_fragment.raw_observation)
            elif discard_strategy == DiscardStrategy.SIMILARITY.value:
                low_similarity_memories = [m for m in retrieved_memories if
                                           m.similarity < similarity_threshold]
                if low_similarity_memories:
                    retrieved_memories.remove(
                        min(low_similarity_memories, key=lambda x: x.similarity))
                else:
                    retrieved_memories.remove(
                        min(retrieved_memories, key=lambda x: x.similarity))
            elif discard_strategy == DiscardStrategy.IMPORTANCE.value:
                retrieved_memories.sort(key=lambda x: x.importance)
                retrieved_memories.pop(0)
            elif discard_strategy == DiscardStrategy.CONDENSE.value:
                from derisk_ext.rag.transformer.memory_extractor import \
                    MemoryCondenseExtractor
                memory_extractor = MemoryCondenseExtractor(
                    llm_client=self._llm_client,
                    model_name=condense_model,
                    prompt=condense_prompt,
                )
                memory_texts = "\n".join(
                    [m.raw_observation for m in retrieved_memories]
                )

                condense_content = await memory_extractor.extract(memory_texts)
                from derisk.agent import AgentMemoryFragment
                retrieved_memories = [AgentMemoryFragment.build_from(
                    observation=condense_content,
                    importance=retrieved_memories[0].importance,
                    similarity=retrieved_memories[0].similarity,
                    create_time=retrieved_memories[0].create_time,
                    last_accessed_time=retrieved_memories[0].last_accessed_time,
                    rounds=retrieved_memories[0].rounds,
                )]
        return retrieved_memories


    @property
    def session_id(self):
        """Return the session ID."""
        return self._session_id

    async def clear(self) -> List[T]:
        """Clear all memory fragments in the session memory.

        Returns:
            List[T]: The all cleared memory fragments.
        """
        if self._vector_store:
            self._vector_store.delete_vector_name(self._agent_id)
        return []

    @property
    def memory_type(self):
        """Return the session Memory Type."""
        return MemoryType.PREFERENCE.value

    @session_id.setter
    def session_id(self, value):
        pass
