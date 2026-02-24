import logging
from copy import deepcopy
from datetime import datetime
from concurrent.futures import Executor
from typing import Optional, Dict, Any, List, Type

from derisk.agent import LongTermMemory
from derisk.agent.core.memory.base import WriteOperation, T, MemoryFragment
from derisk.core import Chunk
from derisk.storage.vector_store.base import VectorStoreBase
from derisk.storage.vector_store.filters import MetadataFilters, FilterCondition, MetadataFilter
from derisk.util.annotations import mutable
from derisk.util.id_generator import new_id

logger = logging.getLogger(__name__)

_METADATA_AGENT_ID = "agent_id"
_METADATA_CREATE_TIME = "create_time"
_METADATA_KEYWORDS = "keywords"
_METADATA_TOPIC_NAME = "topic_name"
_METADATA_TOPIC_VALUE = "topic_value"
_METADATA_LAST_ACCESSED_TIME = "last_accessed_time"
_METADATA_MEMORY_TYPE = "memory_type"
_METADATA_CONV_SESSION_ID = "conv_session_id"
_METADATA_CONV_SESSION_IDS = "conv_session_ids"
_METADATA_IS_INSIGHT = "is_insight"
_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_SEARCH_TIMES = 3
_TOTAL_SEARCH_LIMIT = 1000


class AgentExtractMemoryFragment(MemoryFragment):

    def __init__(
        self,
        agent_id: Optional[str] = None,
        memory_id: Optional[int] = None,
        embeddings: Optional[List[float]] = None,
        last_accessed_time: Optional[datetime] = None,
        importance: Optional[float] = None,
        is_insight: bool = True,
        create_time: Optional[datetime] = None,
        similarity: Optional[float] = None,
        pk_id: Optional[str] = None,
        conv_session_id: Optional[str] = None,
        conv_session_ids: Optional[list[str]] = None,
        memory_type: Optional[str] = None,
        keywords: Optional[str] = None,
        topic_name: Optional[str] = None,
        topic_value: Optional[str] = None,
    ):
        """Create a Session memory fragment.

        Args:
            agent_id: Agent ID associated with the memory fragment
            memory_id: Memory ID associated with the memory fragment
            embeddings(List[float]): Embeddings of the memory content
            last_accessed_time(Optional[datetime]): Last accessed time of the memory fragment
            importance(Optional[float]): Importance of the memory fragment
            is_insight(bool): Whether the memory can be used
            create_time(Optional[datetime]): Creation time of the memory
            similarity(Optional[float]): Similarity score of the memory
            pk_id(Optional[str]): unique ID associated with the memory fragment
            conv_session_ids(Optional[list[str]]): Session ID associated with the memory fragment
        """
        if not memory_id:
            memory_id = new_id()
        self.memory_id = memory_id
        self._agent_id = agent_id
        self._embeddings = embeddings
        self._create_time = create_time
        self._last_accessed_time = last_accessed_time
        self._similarity = similarity
        self._pk_id = pk_id
        self._is_insight = is_insight
        self._conv_session_id = conv_session_id
        self._conv_session_ids = conv_session_ids
        self._memory_type = memory_type
        self._keywords = keywords
        self._topic_name = topic_name
        self._topic_value = topic_value
        self._importance = importance

    @property
    def id(self) -> int:
        """Return the memory id."""
        return self.memory_id

    @property
    def is_insight(self) -> bool:
        """Return whether the memory is insight."""
        return self._is_insight

    @property
    def pk_id(self) -> str:
        """Return the memory pk id."""
        return self._pk_id

    @property
    def agent_id(self) -> Optional[str]:
        """Return the agent_id."""
        return self._agent_id

    @property
    def raw_observation(self) -> str:
        """Return the raw observation."""
        if not self._topic_value:
            return ""
        return self._topic_value.strip()

    @property
    def importance(self) -> Optional[float]:
        """Return the importance of the memory fragment."""
        return self._importance

    @property
    def similarity(self) -> Optional[float]:
        """Return the similarity of the memory fragment."""
        return self._similarity

    @property
    def create_time(self) -> Optional[datetime]:
        """Return the create_time of the memory fragment."""
        return self._create_time

    @property
    def memory_type(self) -> Optional[str]:
        """Return the memory_type."""
        return self._memory_type

    @property
    def conv_session_ids(self) -> Optional[list[str]]:
        """Return the conv_session_ids."""
        return self._conv_session_ids

    @property
    def keywords(self) -> str:
        """Return the keywords.
        Returns:
            List[str]: List of keywords.
        """
        return self._keywords

    @property
    def conv_session_id(self) -> Optional[str]:
        """Return the conv_session_id."""
        return self._conv_session_id

    @property
    def topic_name(self) -> Optional[str]:
        """Return the topic_name."""
        return self._topic_name

    @property
    def topic_value(self) -> Optional[str]:
        """Return the topic_value."""
        return self._topic_value

    def update_embeddings(self, embeddings: List[float]) -> None:
        """Update the embeddings of the memory fragment.

        Args:
            embeddings(List[float]): embeddings
        """
        self._embeddings = embeddings

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

    def copy(self: "AgentExtractMemoryFragment") -> "AgentExtractMemoryFragment":
        return AgentExtractMemoryFragment.build_from(
            agent_id=self._agent_id,
            embeddings=self._embeddings,
            memory_id=self.memory_id,
            importance=self.importance,
            last_accessed_time=self.last_accessed_time,
            is_insight=self.is_insight,
            create_time=self.create_time,
            similarity=self.similarity,
            memory_type=self._memory_type,
            keywords=self.keywords,
            topic_name=self.topic_name,
            topic_value=self.topic_value,
            conv_session_ids=self.conv_session_ids
        )

    @classmethod
    def build_from(
            cls: Type["AgentExtractMemoryFragment"],
            agent_id: Optional[str] = None,
            memory_id: Optional[int] = None,
            embeddings: Optional[List[float]] = None,
            last_accessed_time: Optional[datetime] = None,
            importance: Optional[float] = None,
            is_insight: bool = True,
            create_time: Optional[datetime] = None,
            similarity: Optional[float] = None,
            pk_id: Optional[str] = None,
            conv_session_id: Optional[str] = None,
            conv_session_ids: Optional[list[str]] = None,
            memory_type: Optional[str] = None,
            keywords: Optional[str] = None,
            topic_name: Optional[str] = None,
            topic_value: Optional[str] = None,
            **kwargs
    ) -> "AgentExtractMemoryFragment":
        return cls(
            agent_id=agent_id,
            memory_id=memory_id,
            embeddings=embeddings,
            last_accessed_time=last_accessed_time,
            importance=importance,
            is_insight=is_insight,
            create_time=create_time,
            similarity=similarity,
            pk_id=pk_id,
            conv_session_id=conv_session_id,
            conv_session_ids=conv_session_ids,
            memory_type=memory_type,
            keywords=keywords,
            topic_name=topic_name,
            topic_value=topic_value,
        )

    def to_dict(self):
        """Convert the memory to a dictionary."""
        return {
            "pk_id": self.pk_id,
            "agent_id": self.agent_id,
            "conv_session_id":self.conv_session_id,
            "conv_session_ids": self.conv_session_ids,
            "is_insight": self.is_insight,
            "memory_type": self.memory_type,
            "last_accessed_time": self.last_accessed_time,
            "create_time": self.create_time,
            "keywords": self.keywords,
            "topic_name": self.topic_name,
            "topic_value": self.topic_value,
        }


class ExtractMemory(LongTermMemory):

    def __init__(
            self,
            agent_id: str,
            vector_store: VectorStoreBase,
            executor: Optional[Executor] = None,
            now: Optional[datetime] = None,
            metadata: Optional[Dict[str, Any]] = None,
    ):
        """Create a session extract memory.

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

    @mutable
    async def write(
        self,
        memory_fragment: AgentExtractMemoryFragment,
        now: Optional[datetime] = None,
        op: WriteOperation = WriteOperation.ADD,
        **kwargs,
    ):
        """Write a memory fragment to the memory."""
        if self._vector_store:
            document = self._memory_to_chunk(memory_fragment, op=op)
            try:
                await self._vector_store.aload_document([document])
                logger.info(f"save memory {document.metadata} into vector store.")
            except Exception as e:
                logger.info(f"save memory {document.metadata} into vector store failed.")
                raise Exception(f"save {document.metadata} memory into vector store failed:{str(e)}")

    async def write_batch(
            self,
            memory_fragments: List[T],
            now: Optional[datetime] = None,
            **kwargs
    ) -> Optional[list[T]]:
        """Write a memory fragment to the memory."""
        for memory_fragment in memory_fragments:
            await self.write(memory_fragment, now=now)

    async def upsert_memory(
            self,
            upsert_memories: List[AgentExtractMemoryFragment],
            op: WriteOperation = WriteOperation.ADD
    ):
        if self._vector_store:
            documents = [self._memory_to_chunk(memory, op=op) for memory in upsert_memories]
            try:
                await self._vector_store.async_upsert(documents)
                logger.info(f"upsert {len(documents)} memory into vector store success.")
            except Exception as e:
                logger.info(f"upsert {len(documents)} memory into vector store failed.")
                raise Exception(f"upsert {len(documents)} memory into vector store failed:{str(e)}")

    async def update_memories(self, set_data: List[AgentExtractMemoryFragment]) -> list[Any] | None:
        """Update memory  based on memory fragments."""
        if self._vector_store:
            update_data = []
            for memory in set_data:
                documents = self._memory_to_chunk(memory, op=WriteOperation.RETRIEVAL)
                update_data.append({"set_data": {"metadata":documents.metadata}, "pk_id": memory.pk_id})
            try:
                await self._vector_store.async_update_by_chunk_ids(set_data=update_data)
                logger.info(f"update {len(update_data)} memory into vector store success.")
            except Exception as e:
                logger.info(f"update {len(update_data)} memory into vector store failed.")
                raise Exception(f"update {len(update_data)} memory into vector store failed:{str(e)}")

    async def total_search(
            self,
            memory_type: Optional[str] = None,
            top_k: Optional[int] = _TOTAL_SEARCH_LIMIT,
            metadata_filters: Optional[MetadataFilters] = None,
    ) -> List[Dict[str, Any]]:
        query = True
        result = []
        offset = 0
        search_times = 0
        while query and search_times < _MAX_SEARCH_TIMES:
            search_times += 1
            query_result = await self.search(
                memory_type=memory_type,
                top_k=top_k,
                offset=offset,
                metadata_filters=metadata_filters,
            )
            result.extend(query_result)
            offset += top_k
            if len(query_result) < top_k:
                query = False
        return result

    def delete_by_ids(self, ids: str):
        if self._vector_store:
            if not self._vector_store.vector_name_exists():
                return []
            return self._vector_store.delete_by_ids(ids=ids)
        return []


    async def search(
            self,
            memory_type: Optional[str] = None,
            top_k: int = 50,
            offset: int = 0,
            agent_id: Optional[str] = None,
            desc: Optional[bool] = True,
            metadata_filters: Optional[MetadataFilters] = None,
    ) -> List[Dict[str, Any]]:
        """Search memories related to the agent_id and key.
        """
        logger.info(f"Agent Memory Search, "
                    f"memory_type-{memory_type}, "
                    f"metadata_filters-{metadata_filters}, "
                    )
        metadata_base = {}
        if agent_id:
            metadata_base["agent_id"] = agent_id
        if memory_type:
            metadata_base["memory_type"] = memory_type

        retrieved_memories = []
        filters = deepcopy(metadata_filters.filters) if metadata_filters else []
        condition = metadata_filters.condition if metadata_filters else FilterCondition.AND
        for key, value in metadata_base.items():
            if isinstance(value, (str, int, float)):
                filters.append(MetadataFilter(key=key, value=value))
        search_filters = MetadataFilters(filters=filters, condition=condition)
        if self._vector_store:
            if not self._vector_store.vector_name_exists():
                return []

            search_memories = await self._vector_store.aexact_search(
                filters=search_filters,
                topk=top_k,
                desc=desc,
                offset=offset,
            )
            for retrieved_chunk in search_memories:
                if self._is_correct_data(retrieved_chunk):
                    retrieved_memories.append(self._chunk_to_memory(retrieved_chunk).to_dict())
            return retrieved_memories
        return []

    def _is_correct_data(self, chunk: Chunk) -> bool:
        if not chunk or not chunk.metadata:
            logger.info(f"Chunk {chunk.pk_id} has no metadata")
            return False
        metadata = chunk.metadata
        if not metadata.get(_METADATA_CONV_SESSION_IDS):
            logger.info(f"Chunk {chunk.pk_id} has no metadata.conv_session_ids")
            return False
        return True


    def _chunk_to_memory(self, chunk: Chunk) -> AgentExtractMemoryFragment:
        metadata = chunk.metadata
        conv_session_ids = metadata.get(_METADATA_CONV_SESSION_IDS)
        if conv_session_ids:
            # Handle both list format and comma-separated string format
            if isinstance(conv_session_ids, list):
                if len(conv_session_ids) == 1 and isinstance(conv_session_ids[0], str):
                    conv_session_ids = conv_session_ids[0].split(",")
                # else: already a list of ids
            elif isinstance(conv_session_ids, str):
                conv_session_ids = conv_session_ids.split(",")
        return AgentExtractMemoryFragment(
            pk_id=chunk.pk_id,
            agent_id=metadata.get(_METADATA_AGENT_ID, None),
            conv_session_ids=conv_session_ids,
            memory_type=metadata.get(_METADATA_MEMORY_TYPE, None),
            keywords=metadata.get(_METADATA_KEYWORDS, None),
            conv_session_id=metadata.get(_METADATA_CONV_SESSION_ID, None),
            topic_name=metadata.get(_METADATA_TOPIC_NAME, None),
            topic_value=metadata.get(_METADATA_TOPIC_VALUE, None),
            is_insight=metadata.get(_METADATA_IS_INSIGHT, True),
            create_time=datetime.strptime(metadata.get(_METADATA_CREATE_TIME),
                                          _TIME_FORMAT) if metadata.get(_METADATA_CREATE_TIME) else None,
            last_accessed_time=datetime.strptime(metadata.get(_METADATA_LAST_ACCESSED_TIME),
                                                 _TIME_FORMAT) if metadata.get(_METADATA_LAST_ACCESSED_TIME) else None,
        )

    async def related_memory_search(
            self,
            agent_id: str,
            query: str,
            top_k: int = 50,
            score_threshold: float = 0.0,
            memory_type: str = "long_term"
    ) -> list[AgentExtractMemoryFragment]:
        """Search related memory search on the long term memory."""
        metadata_filters = MetadataFilters(filters=[
            MetadataFilter(key="agent_id", value=agent_id),
            MetadataFilter(key="memory_type", value=memory_type)
        ], condition=FilterCondition.AND)

        related_chunks = await self._semantic_search(query, top_k, score_threshold, metadata_filters=metadata_filters)
        logger.info(f"search {len(related_chunks)} related long term memories for {query}, filters: {metadata_filters}")
        related_memories = []
        for memory in related_chunks:
            memory_fragment = self._chunk_to_memory(memory)
            related_memories.append(memory_fragment)
        return related_memories

    def count_memories(self, filters: MetadataFilters = None, **kwargs) -> int:
        if self._vector_store:
            if not self._vector_store.vector_name_exists():
                return 0
            return self._vector_store.count_documents(filters=filters, **kwargs)
        return 0

    async def fuzzy_memory_search(
            self,
            query: str,
            top_k: int = 50,
            score_threshold: float = 0.0,
            metadata_filters: Optional[MetadataFilters] = None,
    ) -> list[Dict[str, Any]]:
        """Search related memory search on the long term memory."""
        related_chunks = await self._semantic_search(query, top_k, score_threshold, metadata_filters=metadata_filters)
        logger.info(f"search {len(related_chunks)} related long term memories for {query}, filters: {metadata_filters}")
        related_memories = []
        if not related_chunks:
            logger.info(f"No related memories found by semantic search, query: {query}")
            # 如果模糊搜索没有结果，走准确搜索
            metadata_filters.filters.append(MetadataFilter(key="keywords", value=query))
            return await self.search(top_k=top_k, metadata_filters=metadata_filters)
        else:
            for memory in related_chunks:
                if self._is_correct_data(memory):
                    memory_fragment = self._chunk_to_memory(memory).to_dict()
                    related_memories.append(memory_fragment)
        return related_memories

    async def _semantic_search(
            self,
            query: str,
            top_k: int,
            score_threshold: float,
            metadata_filters: Optional[MetadataFilters] = None,
    ):
        """Perform semantic search on the long term memory."""
        related_memories = []
        if self._vector_store:
            if not self._vector_store.vector_name_exists():
                return []
            try:
                related_memories = await self._vector_store.asimilar_search_with_scores(query, top_k,
                    score_threshold, metadata_filters, True)
            except Exception as e:
                logger.error(
                    f"Long Term Memory Semantic search failed: {e}"
                    f"-query: {query}, -filters: {metadata_filters}"
                )
                return []
        return related_memories

    async def _keyword_search(
            self,
            query: str,
            top_k: int = 20,
            metadata_filters: Optional[MetadataFilters] = None
    ):
        """Perform keyword search on the long term memory."""
        related_memories = []
        if self._vector_store:
            if not self._vector_store.vector_name_exists():
                return []
            try:
                related_memories = await self._vector_store.afull_text_search(
                    query, top_k, metadata_filters, True)
            except Exception as e:
                logger.error(
                    f"Long Term Memory keyword search failed: {e} "
                    f"query: {query}, -filters: {metadata_filters}"
                )
                return []
        return related_memories

    def _memory_to_chunk(
        self,
        memory_item: AgentExtractMemoryFragment,
        op: WriteOperation = WriteOperation.ADD,
    ):
        msg_content = memory_item.keywords + ":\n" + memory_item.raw_observation
        metadata = {k: v for k, v in self._metadata.items()}
        if memory_item.agent_id:
            metadata[_METADATA_AGENT_ID] = memory_item.agent_id
        if memory_item.conv_session_ids:
            metadata[_METADATA_CONV_SESSION_IDS] = memory_item.conv_session_ids
        if memory_item.create_time:
            metadata[_METADATA_CREATE_TIME] = memory_item.create_time.strftime(_TIME_FORMAT)
        if memory_item.last_accessed_time:
            metadata[_METADATA_LAST_ACCESSED_TIME] = memory_item.last_accessed_time.strftime(_TIME_FORMAT)
        if memory_item.keywords:
            metadata[_METADATA_KEYWORDS] = memory_item.keywords
        if memory_item.conv_session_id:
            metadata[_METADATA_CONV_SESSION_ID] = memory_item.conv_session_id
        if memory_item.topic_name:
            metadata[_METADATA_TOPIC_NAME] = memory_item.topic_name
        if memory_item.topic_value:
            metadata[_METADATA_TOPIC_VALUE] = memory_item.topic_value
        if memory_item.memory_type:
            metadata[_METADATA_MEMORY_TYPE] = memory_item.memory_type
        metadata["operation"] = op.value
        if memory_item.agent_id:
            metadata[_METADATA_AGENT_ID] = memory_item.agent_id
        if memory_item.is_insight:
            metadata[_METADATA_IS_INSIGHT] = memory_item.is_insight
        if memory_item.pk_id:
            pk_id = memory_item.pk_id
            return Chunk(
                pk_id=pk_id,
                content=msg_content,
                metadata=metadata,
            )

        return Chunk(
            content=msg_content,
            metadata=metadata,
        )

    @property
    def memory_type(self):
        """Return the session Memory Type."""
        return "agent"
