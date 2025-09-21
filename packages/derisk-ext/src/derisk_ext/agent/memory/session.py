import logging
from concurrent.futures import Executor
from copy import deepcopy
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, Type, List, cast, Callable

from derisk.agent import LongTermMemory, GptsMemory, AgentMemoryFragment
from derisk.agent.core.memory.base import WriteOperation, DiscardedMemoryFragments, \
    MemoryFragment, InsightExtractor, ImportanceScorer, T
from derisk.core import LLMClient, Chunk
from derisk.storage.knowledge_graph.base import KnowledgeGraphBase
from derisk.storage.vector_store.base import VectorStoreBase
from derisk.storage.vector_store.filters import MetadataFilters, MetadataFilter
from derisk.util.annotations import mutable
from derisk.util.id_generator import new_id
from derisk.util.string_utils import determine
from derisk_ext.rag.transformer.memory_extractor import MemoryCondenseExtractor

_FORGET_PLACEHOLDER = "[FORGET]"
_MERGE_PLACEHOLDER = "[MERGE]"
_METADATA_BUFFER_IDX = "buffer_idx"
_METADATA_LAST_ACCESSED_AT = "last_accessed_at"
_METADATA_CREATE_TIME = "create_time"
_METADATA_SESSION_ID = "session_id"
_METADATA_AGENT_ID = "agent_id"
_METADATA_AGENT_TYPE = "agent_type"
_METADAT_IMPORTANCE = "importance"
_METADAT_CONDENSE = "condense"
_METADAT_USER_INPUT = "user_input"
_METADAT_AI_MESSAGE = "ai_message"
_MEMORY_ID = "memory_id"
_MESSAGE_ID = "message_id"
_ROLE = "role"
_TASK_GOAL = "task_goal"
_THOUGHT = "thought"
_ACTION = "action"
_ANSWER_ACTION = "answer"
_ACTION_RESULT = "action_result"
_REASON_AGENT = "ReasoningPlanner"



logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Enum for different types of memory."""
    SESSION = "session"
    AGENT = "agent"
    PREFERENCE = "preference"


class DiscardStrategy(Enum):
    """Discard Strategy."""
    FIFO = "fifo"
    LRU = "lru"
    SIMILARITY = "similarity"
    IMPORTANCE = "importance"
    CONDENSE = "condense"


class SessionMemoryFragment(MemoryFragment):
    """Session memory fragment for Session memory."""

    def __init__(
            self,
            observation: str,
            embeddings: Optional[List[float]] = None,
            memory_id: Optional[int] = None,
            importance: Optional[float] = None,
            last_accessed_time: Optional[datetime] = None,
            rounds: Optional[int] = None,
            is_insight: bool = False,
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
            condense: Optional[bool] = False,
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
            agent_type(Optional[str]):agent_type associated with the memory fragment
            condense(Optional[bool]):condense associated with the memory fragment
        Raises:
            ValueError: If memory_id is not provided and cannot be generated.
        Raises:
            TypeError: If memory_id is not an integer.
        """
        if not memory_id:
            # Generate a new memory id, we use snowflake id generator here.
            memory_id = new_id()
        self.observation = observation
        self._embeddings = embeddings
        self.memory_id: int = cast(int, memory_id)
        self._importance: Optional[float] = importance
        self._last_accessed_time = last_accessed_time or datetime.now()
        self._is_insight = is_insight
        self._rounds = rounds
        self._create_time = create_time or datetime.now()
        self._similarity = similarity
        self._message_id = message_id
        self._role = role
        self._agent_id = agent_id
        self._task_goal = task_goal
        self._thought = thought
        self._action = action
        self._action_result = action_result
        self._agent_type = agent_type
        self._condense = condense

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
        return self._create_time

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
    def role(self) -> Optional[str]:
        """Return the message_id.

        Returns:
            Optional[str]: str.
        """
        return self._role

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

    @property
    def rounds(self) -> Optional[int]:
        """Return the last accessed time of the memory fragment.

        Used to determine the least recently used memory fragment.

        Returns:
            Optional[datetime]: Last accessed time
        """
        return self._rounds

    @property
    def task_goal(self) -> Optional[str]:
        """Return the task_goal.

        Returns:
            Optional[str]: str.
        """
        return self._task_goal

    @property
    def thought(self) -> Optional[str]:
        """Return the thought.

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
    def condense(self) -> Optional[bool]:
        """Return to condense.

        Returns:
            Optional[bool]: str.
        """
        return self._condense

    @classmethod
    def build_from(
            cls: Type["SessionMemoryFragment"],
            observation: str,
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
            agent_type: Optional[str] = None,
            condense: Optional[bool] = False,
            **kwargs,
    ) -> "SessionMemoryFragment":
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
            agent_type=agent_type,
            condense=condense,
        )

    def copy(self: "SessionMemoryFragment") -> "SessionMemoryFragment":
        """Return a copy of the memory fragment."""
        return SessionMemoryFragment.build_from(
            observation=self.observation,
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
            agent_type=self._agent_type,
            condense=self._condense,
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
        }


class SessionMemory(LongTermMemory):
    """
    SessionMemory is a specialized memory class for managing session-specific data.

    It extends LongTermMemory to handle session-related information, providing methods
    for adding, retrieving, and managing session memory fragments.
    """

    def __init__(
            self,
            session_id: str,
            agent_id: str,
            vector_store: VectorStoreBase,
            executor: Executor,
            kg_store: Optional[KnowledgeGraphBase] = None,
            gpts_memory: Optional[GptsMemory] = None,
            now: Optional[datetime] = None,
            reflection_threshold: Optional[float] = None,
            _default_importance: Optional[float] = None,
            metadata: Optional[Dict[str, Any]] = None,
            llm_client: Optional[LLMClient] = None,
    ):
        """Create a session memory.

        Args:
            session_id(str): Unique identifier for the session
            vector_store(VectorStoreBase): Vector store for storing memory fragments
            executor(Executor): Executor to use for running tasks
            kg_store(KnowledgeGraphBase): Knowledge graph store for session-related data
            gpts_memory(GptsMemory): Memory to store GPTs related information
            now(datetime): Current time, used for initializing timestamps
            reflection_threshold(float): Threshold for reflection,
            used to determine when to reflect on memory
        """
        super().__init__(
            vector_store=vector_store,
            executor=executor,
            now=now,
            reflection_threshold=reflection_threshold,
            _default_importance=_default_importance,
            metadata=metadata,
        )
        self._kg_store = kg_store
        self._gpts_memory = gpts_memory
        self._llm_client = llm_client
        self._session_id = session_id
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
            session_id: Optional[str] = None,
    ) -> None:
        """Initialize memory.

        Some agent may need to initialize memory before using it.
        """
        self.name = name
        self.llm_client = llm_client
        self.importance_scorer = importance_scorer
        self.insight_extractor = insight_extractor
        self._real_memory_fragment_class = real_memory_fragment_class
        self.session_id = session_id

    def structure_clone(
            self: "SessionMemory[T]", now: Optional[datetime] = None
    ) -> "SessionMemory[T]":
        """Return a structure clone of the memory."""
        now = now or self.now
        m = SessionMemory(
            session_id=self._session_id,
            agent_id=self._agent_id,
            now=now,
            vector_store=self._vector_store,
            kg_store=self._kg_store,
            executor=self.executor,
            reflection_threshold=self.reflection_threshold,
            _default_importance=self._default_importance,
            metadata=self._metadata,
            llm_client=self._llm_client
        )
        m._copy_from(self)
        return m

    @mutable
    async def write(
            self,
            memory_fragment: AgentMemoryFragment,
            now: Optional[datetime] = None,
            op: WriteOperation = WriteOperation.ADD,
            enable_message_condense: bool = False,
            message_condense_model: str = "deepseek-v3",
            message_condense_prompt: Optional[str] = None,
            check_fail_reason: Optional[str] = None,
            llm_token_limit: int = 56000,
            condense_max_token: int = 4000,
            **kwargs,
    ) -> Optional[DiscardedMemoryFragments[SessionMemoryFragment]]:
        """Write a memory fragment to the memory."""
        last_accessed_time = memory_fragment.last_accessed_time or now or self.now
        msg_content = f"{memory_fragment.raw_observation}"
        metadata = self._metadata
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
        metadata["operation"] = op.ADD.value
        if memory_fragment.rounds:
            metadata["rounds"] = memory_fragment.rounds
        if self.session_id:
            metadata[_METADATA_SESSION_ID] = self.session_id
        if memory_fragment.agent_id:
            metadata[_METADATA_AGENT_ID] = memory_fragment.agent_id
        if memory_fragment.agent_type:
            metadata[_METADATA_AGENT_TYPE] = memory_fragment.agent_type
        if memory_fragment.condense:
            metadata[_METADAT_CONDENSE] = memory_fragment.condense
        if memory_fragment.user_input:
            metadata[_METADAT_USER_INPUT] = memory_fragment.user_input
        if memory_fragment.ai_message:
            metadata[_METADAT_AI_MESSAGE] = memory_fragment.ai_message
        msg_content = (f"TaskGoal:{memory_fragment.task_goal}\n"
                       f"ActionResult:{memory_fragment.action_result}")
        if enable_message_condense:
            memory_extractor = MemoryCondenseExtractor(
                llm_client=self._llm_client,
                model_name=message_condense_model,
                prompt=message_condense_prompt,
            )
            raw_msg = memory_fragment.raw_observation
            try:
                msg_content = await memory_extractor.extract(
                    text=msg_content, max_tokens=condense_max_token
                )
                logger.info(f"After Write Message condense text: {msg_content}")
                while self._calculate_tokens(text=msg_content) > llm_token_limit:
                    msg_content = msg_content[-llm_token_limit:]
                    logger.info(f"Exceed llm token After Write Message condense text: {msg_content}")
            except Exception as e:
                logger.error("Failed to condense message content: %s", e)
                msg_content = raw_msg
            metadata[_ACTION_RESULT] = msg_content
        document = Chunk(
            content=msg_content,
            metadata=metadata,
        )
        if self._vector_store:
            await self._vector_store.aload_document([document])
        if self._kg_store:
            await self._kg_store.aload_document([document])
        return None

    @mutable
    async def write_batch(
            self, memory_fragments: List[T], now: Optional[datetime] = None
    ) -> Optional[DiscardedMemoryFragments[T]]:
        """Write a batch of memory fragments to the memory.

        For memory recovery, we only write to sensory memory and short term memory.
        """
        current_datetime = self.now
        for memory_fragment in memory_fragments:
            memory_fragment.update_accessed_time(now=now)
            await self.write(memory_fragment, now=current_datetime)

    async def read(
            self,
            observation: str,
            alpha: Optional[float] = None,
            beta: Optional[float] = None,
            gamma: Optional[float] = None,
    ) -> List[T]:

        """Read memory fragments related to the observation."""
        return await self.search(observation=observation)

    async def search(
            self,
            observation: str,
            top_k: int = 20,
            retrieve_strategy: str = "semantic",
            score_threshold: float = 0.0,
            discard_strategy: str = DiscardStrategy.FIFO.value,
            llm_token_limit: int = 4096,
            condense_prompt: str = "",
            condense_model: str = "deepseek-v3",
            enable_global_session: bool = False,
            session_id: Optional[str] = None,
            agent_id: Optional[str] = None,
            user_id: Optional[str] = None,
            metadata_filters: Optional[MetadataFilters] = None,
    ) -> List[MemoryFragment]:
        """Search memory fragments related to the observation.

        Args:
            observation(str): Observation
            top_k(int): Number of top results to return
            retrieve_strategy(str): Mode of retrieval, e.g.,"semantic", "all",
            "graph", "hybrid"
            score_threshold(float): Minimum score threshold for results
            discard_strategy(DiscardStrategy): Strategy for discarding results,
            condense_prompt(str): Prompt for generating summary
            condense_model(str): LLM for generating summary
            llm_token_limit(int): Token limit for summary generation
            enable_global_session(bool): Whether to enable global session memory
            session_id(str): Session ID for filtering results
            agent_id(str): Agent ID for filtering results
            user_id(str): User ID for filtering results
            metadata_filters(MetadataFilters): Metadata filters for results

        Returns:
            List[AgentMemoryFragment]: List of memory fragments
        """
        logger.info(f"Session Memory Search session_id-{session_id}, "
                    f"agent_id-{agent_id}, "
                    f"user_id-{user_id}, "
                    f"enable_global_session-{enable_global_session}, "
                    f"retrieve_strategy-{retrieve_strategy}, "
                    f"top_k-{top_k}, "
                    f"discard_strategy-{discard_strategy}, "
                    f"llm_token_limit-{llm_token_limit}, "
                    f"score_threshold-{score_threshold}"
                    )
        metadata_base = deepcopy(metadata_filters) if metadata_filters else {}
        metadata_base[_METADATA_SESSION_ID] = self.session_id
        if agent_id and not enable_global_session:
            metadata_base["agent_id"] = agent_id
        if user_id:
            metadata_base["user_id"] = user_id

        retrieved_memories = []
        filters = []
        for key, value in metadata_base.items():
            if isinstance(value, (str, int, float)):
                filters.append(MetadataFilter(key=key, value=value))
        metadata_filters = MetadataFilters(filters=filters)
        if retrieve_strategy == "semantic":
            logger.info(f"Session Memory-{self.session_id} Semantic retrieval")
            related_memories = await self._semantic_search(
                observation, top_k, score_threshold, metadata_filters
            )
        elif retrieve_strategy == "keyword":
            logger.info(f"Session Memory-{self.session_id} Keyword retrieval")
            related_memories = await self._keyword_search(
                observation, top_k, metadata_filters
            )
        elif retrieve_strategy == "graph":
            logger.info(f"Session Memory-{self.session_id} Graph retrieval")
            related_memories = await self._graph_search(
                observation, top_k, score_threshold, metadata_filters
            )
        elif retrieve_strategy == "hybrid":
            logger.info(f"Session Memory-{self.session_id} Hybrid retrieval")
            related_memories = await self._hybrid_search(
                observation, top_k, score_threshold, metadata_filters
            )
        elif retrieve_strategy == "sliding_window":
            logger.info(f"Session Memory-{self.session_id} Sliding Window retrieval")
            related_memories = await self._sliding_window_search(
                window_size=top_k, metadata_filters=metadata_filters
            )
        else:
            raise ValueError(
                f"Unknown retrieve_mode: {retrieve_strategy}. "
                "Supported modes are: semantic, graph, hybrid, all."
            )

        unique_memories = list(
            {chunk.content: chunk for chunk in related_memories}.values()
        )
        agent_id_memory_map = {}
        if enable_global_session:
            for retrieved_chunk in unique_memories:
                chunk_agent_id = retrieved_chunk.metadata.get(_METADATA_AGENT_ID)
                if chunk_agent_id not in agent_id_memory_map:
                    agent_id_memory_map[chunk_agent_id] = []
                if retrieved_chunk.metadata.get(_ACTION) == _ANSWER_ACTION:
                    agent_id_memory_map[chunk_agent_id].append(retrieved_chunk)
        not_empty_memories = []
        for retrieved_chunk in unique_memories:
            task_goal = retrieved_chunk.metadata.get(_TASK_GOAL)
            # thought = retrieved_chunk.metadata.get(_THOUGHT)
            action = retrieved_chunk.metadata.get(_ACTION)
            observation = retrieved_chunk.metadata.get(_ACTION_RESULT)
            memory_content = []
            if task_goal:
                memory_content.append(f"TaskGoal: {task_goal}")
            if enable_global_session and agent_id != retrieved_chunk.metadata.get(
                    _METADATA_AGENT_ID
            ):
                if agent_id_memory_map.values() and retrieved_chunk.metadata.get(
                        _ACTION) == _ANSWER_ACTION:
                    if action:
                        memory_content.append(f"Action: {action}")
                    if observation:
                        memory_content.append(f"ActionResult: {observation}")
                        logger.info(f"Reasoning SubAgent memories:{observation}")
                elif not agent_id_memory_map.values():
                    logger.info(
                        f"Other SubAgent memories:{agent_id_memory_map.values()}"
                    )
                    if action:
                        memory_content.append(f"Action: {action}")
                    if observation:
                        memory_content.append(f"ActionResult: {observation}")
                else:
                    if retrieved_chunk.metadata.get(
                            _METADATA_AGENT_TYPE) == _REASON_AGENT:
                        logger.info(
                            f"SubAgent {retrieved_chunk.metadata.get('role')} memories are not answer, is filtered"
                        )
                        if action:
                            memory_content.append(f"Action: {action}")
                        if observation:
                            memory_content.append(f"ActionResult: {observation}")
                        self._add_not_empty_memory(
                            not_empty_memories, retrieved_chunk, memory_content
                        )
                        continue
                    else:
                        if action:
                            memory_content.append(f"Action: {action}")
                        if observation:
                            memory_content.append(f"ActionResult: {observation}")
            else:
                if action:
                    memory_content.append(f"Action: {action}")
                if observation:
                    memory_content.append(f"ActionResult: {observation}")
            retrieved_memories.append(
                AgentMemoryFragment.build_from(
                    observation="\n".join(memory_content),
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
                    session_id=retrieved_chunk.metadata.get(_METADATA_SESSION_ID, None),
                    message_id=retrieved_chunk.metadata.get(_MESSAGE_ID, None),
                    task_goal=retrieved_chunk.metadata.get(_TASK_GOAL, None),
                    thought=retrieved_chunk.metadata.get(_THOUGHT, None),
                    action=retrieved_chunk.metadata.get(_ACTION, None),
                    action_result=retrieved_chunk.metadata.get(
                        _ACTION_RESULT, None
                    ),
                    user_input=retrieved_chunk.metadata.get(_METADAT_USER_INPUT, None),
                    ai_message=retrieved_chunk.metadata.get(_METADAT_AI_MESSAGE, None),
                    condense=retrieved_chunk.metadata.get(_METADAT_CONDENSE, None)
                )
            )
        if not_empty_memories and not retrieved_memories:
            logger.info(f"Session retrieved Memory-is empty, return "
                        f"not_empty_memories nums:{len(not_empty_memories)}")
            retrieved_memories = not_empty_memories
        retrieved_memories.sort(key=lambda x: (x.rounds or 0, x.create_time))
        session_memories = await self.discard_memories(
            retrieved_memories=retrieved_memories,
            discard_strategy=discard_strategy,
            llm_token_limit=llm_token_limit,
            similarity_threshold=score_threshold,
            condense_model=condense_model,
            condense_prompt=condense_prompt,
        )
        return session_memories

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
                    self._real_memory_fragment_class.build_from(
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
            condense_max_token: Optional[int] = 4000,
    ):
        """Discard memories based on the discard strategy."""
        while self._calculate_total_tokens(retrieved_memories) > llm_token_limit:
            logger.info(
                f"Session Memory-{self.session_id} "
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
                memory_extractor = MemoryCondenseExtractor(
                    llm_client=self._llm_client,
                    model_name=condense_model,
                    prompt=condense_prompt,
                )
                memory_texts = "\n".join(
                    [m.raw_observation for m in retrieved_memories]
                )

                # condense_content = memory_texts
                try:
                    condense_content = await memory_extractor.extract(
                        memory_texts, max_tokens=condense_max_token
                    )
                    while self._calculate_tokens(text=condense_content) > llm_token_limit:
                        condense_content = condense_content[-llm_token_limit:]
                        logger.info(f"After Search Message condense text: {condense_content}")
                except Exception as e:
                    logger.error("Failed to condense message content: %s", e)
                    condense_content = memory_texts[-llm_token_limit:]
                retrieved_memories = [AgentMemoryFragment.build_from(
                    observation=condense_content,
                    importance=retrieved_memories[0].importance,
                    similarity=retrieved_memories[0].similarity,
                    create_time=retrieved_memories[0].create_time,
                    last_accessed_time=retrieved_memories[0].last_accessed_time,
                    rounds=retrieved_memories[0].rounds,
                )]
        return retrieved_memories

    async def _semantic_search(
            self,
            query: str,
            top_k: int = 20,
            score_threshold: float = 0.0,
            metadata_filters: Optional[MetadataFilters] = None
    ):
        """Perform semantic search on the session memory."""
        tasks = []
        related_memories = []
        import asyncio
        if self._vector_store:
            if not self._vector_store.vector_name_exists():
                return []
            try:
                tasks.append(self._vector_store.asimilar_search_with_scores(
                    query,
                    top_k,
                    score_threshold,
                    metadata_filters,
                    True)
                )
                results = await asyncio.gather(*tasks)
                semantic_memories = results[0]
                related_memories = semantic_memories
            except Exception as e:
                logger.error(
                    f"Session Memory-{self.session_id} "
                    f"Semantic search failed: {e}"
                )
                return []
        return related_memories

    async def _keyword_search(
            self,
            query: str,
            top_k: int = 20,
            metadata_filters: Optional[MetadataFilters] = None
    ):
        """Perform keyword search on the session memory."""
        tasks = []
        related_memories = []
        import asyncio
        if self._vector_store:
            if not self._vector_store.vector_name_exists():
                return []
            try:
                tasks.append(self._vector_store.afull_text_search(
                    query, top_k, metadata_filters, True)
                )
                results = await asyncio.gather(*tasks)
                full_text_memories = results[0]
                related_memories = full_text_memories
            except Exception as e:
                logger.error(
                    f"Session Memory-{self.session_id} "
                    f"Keyword search failed: {e}"
                )
                return []
        return related_memories

    async def _sliding_window_search(
            self,
            window_size: int = 50,
            metadata_filters: Optional[MetadataFilters] = None
    ):
        """Perform sliding window search on the session memory."""
        related_memories = []
        if self._vector_store:
            if not self._vector_store.vector_name_exists():
                return []
            try:
                recent_memories = self._vector_store.exact_search(
                    filters=metadata_filters
                )
                related_memories = recent_memories[-window_size:]
            except Exception as e:
                logger.error(
                    f"Session Memory-{self.session_id} "
                    f"Sliding window search failed: {e}"
                )
                return []
        return related_memories

    async def _graph_search(
            self, query: str,
            top_k: int = 20,
            score_threshold: float = 0.0,
            metadata_filters: Optional[MetadataFilters] = None
    ):
        """Perform graph search on the session memory."""
        tasks = []
        related_memories = []
        import asyncio
        if self._kg_store:
            logger.info(f"Session Memory-{self.session_id} Starting KG retrieval")
            try:
                tasks.append(self._kg_store.asimilar_search_with_scores(
                    query, top_k, score_threshold, metadata_filters)
                )
                results = await asyncio.gather(*tasks)
                related_memories = results[0]
            except Exception as e:
                logger.error(
                    f"Session Memory-{self.session_id} "
                    f"Graph search failed: {e}"
                )
                return []
        return related_memories

    async def _hybrid_search(
            self,
            query: str,
            top_k: int = 20,
            score_threshold: float = 0.0,
            metadata_filters: Optional[MetadataFilters] = None
    ):
        """Perform hybrid search on the session memory."""
        try:
            semantic_memories = await self._semantic_search(
                query, top_k, score_threshold, metadata_filters
            )
            graph_memories = await self._graph_search(
                query, top_k, score_threshold, metadata_filters
            )
            related_memories = semantic_memories + graph_memories
        except Exception as e:
            logger.error(
                f"Session Memory-{self.session_id} "
                f"Hybrid search failed: {e}"
            )
            return []
        return related_memories

    @property
    def session_id(self):
        """Return the session ID."""
        return self._session_id

    @property
    def memory_type(self):
        """Return the session Memory Type."""
        return MemoryType.SESSION.value

    async def clear(self) -> List[T]:
        """Clear all memory fragments.

        Returns:
            List[T]: The all cleared memory fragments.
        """
        if self._vector_store:
            self._vector_store.delete_vector_name(self._session_id)
        return []

    @session_id.setter
    def session_id(self, value):
        pass

    def _add_not_empty_memory(
            self,
            not_empty_memories: List[AgentMemoryFragment],
            retrieved_chunk: Chunk,
            memory_content: List[str],
            ):
        """
        Add not empty memory to not_empty_memories
        Args:
            not_empty_memories:
            retrieved_chunk:
            memory_content:

        Returns:

        """
        not_empty_memories.append(AgentMemoryFragment.build_from(
            observation="\n".join(memory_content),
            importance=retrieved_chunk.score,
            similarity=retrieved_chunk.score,
            create_time=retrieved_chunk.metadata.get(
                _METADATA_CREATE_TIME, None
            ),
            last_accessed_time=retrieved_chunk.metadata.get(
                _METADATA_LAST_ACCESSED_AT, None),
            rounds=retrieved_chunk.metadata.get("rounds", None),
            agent_id=retrieved_chunk.metadata.get(_METADATA_AGENT_ID,
                                                  None),
            role=retrieved_chunk.metadata.get("role", None),
            session_id=retrieved_chunk.metadata.get(
                _METADATA_SESSION_ID, None),
            message_id=retrieved_chunk.metadata.get(_MESSAGE_ID, None),
            task_goal=retrieved_chunk.metadata.get(_TASK_GOAL, None),
            thought=retrieved_chunk.metadata.get(_THOUGHT, None),
            action=retrieved_chunk.metadata.get(_ACTION, None),
            action_result=retrieved_chunk.metadata.get(
                _ACTION_RESULT, None
            ),
            user_input=retrieved_chunk.metadata.get(_METADAT_USER_INPUT,
                                                    None),
            ai_message=retrieved_chunk.metadata.get(_METADAT_AI_MESSAGE,
                                                    None),
            condense=retrieved_chunk.metadata.get(_METADAT_CONDENSE,
                                                  None)
        ))
