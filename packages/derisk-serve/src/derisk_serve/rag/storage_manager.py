"""RAG STORAGE MANAGER manager."""

import json
import logging
import threading
from typing import List, Optional, Type

from derisk import BaseComponent
from derisk.component import ComponentType, SystemApp
from derisk.model import DefaultLLMClient
from derisk.model.cluster import WorkerManagerFactory
from derisk.rag.embedding import EmbeddingFactory, DefaultEmbeddingFactory
from derisk.storage.base import IndexStoreBase
from derisk.storage.full_text.base import FullTextStoreBase
from derisk.storage.memory.base import MemoryStoreBase, MemoryStoreConfig
from derisk.storage.vector_store.base import VectorStoreBase, VectorStoreConfig
from derisk.util.executor_utils import DefaultExecutorFactory
from derisk_ext.storage.full_text.elasticsearch import ElasticDocumentStore
from derisk_ext.storage.knowledge_graph.knowledge_graph import BuiltinKnowledgeGraph

logger = logging.getLogger(__name__)


class StorageManager(BaseComponent):
    """RAG STORAGE MANAGER manager."""

    name = ComponentType.RAG_STORAGE_MANAGER

    def __init__(self, system_app: SystemApp):
        """Create a new ConnectorManager."""
        self.system_app = system_app
        self._store_cache = {}
        self._cache_lock = threading.Lock()
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp):
        """Init component."""
        self.system_app = system_app

    def invalidate_embedding_cache(self):
        """Drop cached vector/memory stores.

        Called when the set of embedding models or the default embedding model
        changes at runtime, so subsequently created knowledge spaces / memory
        stores pick up the new embedding model instead of a stale cached store.
        """
        with self._cache_lock:
            count = len(self._store_cache)
            self._store_cache.clear()
        logger.info(
            f"Embedding-related store cache invalidated ({count} entries cleared)."
        )

    def storage_config(self):
        """Storage config."""
        app_config = self.system_app.config.configs.get("app_config")
        return app_config.rag.storage

    def get_storage_connector(
        self, index_name: str, storage_type: str, llm_model: Optional[str] = None
    ) -> Optional[IndexStoreBase]:
        """Get storage connector."""
        import threading

        logger.info(
            f"get_storage_connector start, 当前线程数：{threading.active_count()}"
        )

        supported_vector_types = self.get_vector_supported_types
        storage_config = self.storage_config()
        if storage_type.lower() in supported_vector_types:
            return self.create_vector_store(index_name)
        elif storage_type == "KnowledgeGraph":
            if not storage_config or not storage_config.graph:
                raise ValueError(
                    "Graph storage is not configured.please check your config."
                    "reference configs/derisk-graphrag.toml"
                )
            raise NotImplementedError("KnowledgeGraph storage is not implemented")
        elif storage_type == "FullText":
            if not storage_config or not storage_config.full_text:
                raise ValueError(
                    "FullText storage is not configured.please check your config."
                    "reference configs/derisk-bm25-rag.toml"
                )
            raise NotImplementedError("FullText storage is not implemented")
        elif storage_type == "Memory":
            return self.create_memory_store(index_name)
        else:
            raise ValueError(f"Does not support storage type {storage_type}")

    def create_vector_store(
        self, index_name, extra_indexes: Optional[List[str]] = None
    ) -> Optional[VectorStoreBase]:
        """Create vector store.

        Returns None if embedding factory is not configured.
        """
        collection_name = self.gen_collection_by_id(index_name)
        app_config = self.system_app.config.configs.get("app_config")
        storage_config = app_config.rag.storage
        if collection_name in self._store_cache:
            return self._store_cache[collection_name]
        try:
            embedding_factory = self.system_app.get_component(
                "embedding_factory", EmbeddingFactory
            )
            embedding_fn = embedding_factory.create()
        except ValueError as e:
            logger.error(
                f"No embedding model available for vector store: {e}. "
                "Vector store will NOT be available. Add a text2vec (embedding) "
                "model on the model management page (/models), or configure "
                "[[models.embeddings]] in your config file."
            )
            return None

        # Try to get type from config object, handling both dict-like and object-like access
        vector_store_type = getattr(storage_config.vector, "type", None)
        if not vector_store_type:
            vector_store_type = getattr(storage_config.vector, "__type__", None)

        if vector_store_type == "chroma":
            from derisk_ext.storage.vector_store.chroma_store import (
                ChromaStore,
                ChromaVectorConfig,
            )

            # Extract persist_path safely
            persist_path = getattr(storage_config.vector, "persist_path", None)

            vector_store_config = ChromaVectorConfig(persist_path=persist_path)
            new_store = ChromaStore(
                vector_store_config=vector_store_config,
                name=index_name,
                embedding_fn=embedding_fn,
            )
            self._store_cache[index_name] = new_store
            return new_store

        account = storage_config.full_text.account
        secret = storage_config.full_text.secret

        from derisk_ext.storage.full_text.zsearch import ZSearchStoreConfig

        zsearch_config = ZSearchStoreConfig(
            index_name=index_name,
            account=account,
            secret=secret,
        )
        from derisk_ext.storage.full_text.zsearch import ZsearchStore

        new_store = ZsearchStore(
            name=index_name,
            embedding_fn=embedding_fn,
            vector_store_config=zsearch_config,
        )
        self._store_cache[index_name] = new_store
        return new_store

    def create_memory_store(
        self, index_name: str
    ) -> Optional[MemoryStoreBase]:
        """Create a memory store.

        Auto-discovers registered MemoryStoreConfig subclasses (by
        ``__type__``) and instantiates the matching provider.  Falls back
        to the first available provider if no explicit type is configured.
        """
        cache_key = f"memory_{index_name}"
        if cache_key in self._store_cache:
            return self._store_cache[cache_key]

        app_config = self.system_app.config.configs.get("app_config")
        storage_config = app_config.rag.storage

        # Read memory provider type from config (e.g. "mempalace")
        memory_cfg = getattr(storage_config, "memory", None)
        provider_type = None
        if memory_cfg:
            provider_type = getattr(memory_cfg, "type", None) or getattr(
                memory_cfg, "__type__", None
            )

        # Discover registered providers
        available_providers = _get_all_memory_subclasses()
        if not available_providers:
            # Try importing providers to trigger registration
            # First try MemPalace (preferred), then fallback to SimpleSQLite
            try:
                from derisk_ext.storage.memory.mempalace_store import (  # noqa: F401
                    MemPalaceMemoryConfig,
                )
                available_providers = _get_all_memory_subclasses()
            except ImportError:
                logger.info(
                    "MemPalace not available, trying SimpleSQLite fallback..."
                )

            # Fallback to SimpleSQLite (no external dependencies)
            if not available_providers:
                try:
                    from derisk_ext.storage.memory.simple_sqlite_store import (  # noqa: F401
                        SimpleSQLiteMemoryConfig,
                    )
                    available_providers = _get_all_memory_subclasses()
                    logger.info(
                        "Using SimpleSQLiteMemoryStore as fallback (no vector search)"
                    )
                except ImportError as e:
                    logger.warning(
                        f"No memory store providers found: {e}. "
                        "Install mempalace (pip install mempalace) or ensure "
                        "derisk_ext.storage.memory.simple_sqlite_store is available."
                    )
                    return None

        # Match by type or use first available
        config_cls = None
        for cls in available_providers:
            if provider_type and getattr(cls, "__type__", None) == provider_type:
                config_cls = cls
                break
        if config_cls is None and available_providers:
            config_cls = available_providers[0]

        if config_cls is None:
            logger.warning("No memory store provider matched.")
            return None

        # Build config with any overrides from app config
        config_kwargs = {}
        if memory_cfg:
            for k in ("palace_path", "enable_kg", "default_wing", "use_builtin_embedding"):
                v = getattr(memory_cfg, k, None)
                if v is not None:
                    config_kwargs[k] = v

        config_instance = config_cls(**config_kwargs)

        # Try to pass OpenDerisk's embedding_fn to the memory store so it
        # can reuse the centrally configured embedding model instead of its
        # own built-in one.
        embedding_fn = None
        try:
            embedding_factory = self.system_app.get_component(
                "embedding_factory", EmbeddingFactory
            )

            # Check if the knowledge space has a specific embedding model configured
            space_model_name = self._get_space_embedding_model(index_name)
            if space_model_name:
                logger.info(
                    f"Using space-specific embedding model: {space_model_name}"
                )
                embedding_fn = embedding_factory.create(model_name=space_model_name)
            else:
                embedding_fn = embedding_factory.create()
        except (ValueError, Exception) as e:
            logger.error(
                f"No embedding model available for memory store: {e}. "
                "Add a text2vec (embedding) model on the model management page "
                "(/models), or configure [[models.embeddings]] in your config "
                "file. The memory store may fail without a configured model."
            )

        store = config_instance.create_store(
            name=index_name, embedding_fn=embedding_fn
        )

        with self._cache_lock:
            self._store_cache[cache_key] = store
        return store

    def _get_space_embedding_model(self, knowledge_id: str) -> Optional[str]:
        """Read the embedding model name from a knowledge space's context.

        Args:
            knowledge_id: The UUID of the knowledge space.

        Returns:
            The embedding model name if configured, otherwise None.
        """
        try:
            from derisk_serve.rag.models.models import KnowledgeSpaceDao, KnowledgeSpaceEntity

            dao = KnowledgeSpaceDao()
            spaces = dao.get_knowledge_space(KnowledgeSpaceEntity(knowledge_id=knowledge_id))
            if not spaces:
                return None
            space = spaces[0]
            if not space.context:
                return None
            ctx = json.loads(space.context)
            embedding = ctx.get("embedding", {})
            model = embedding.get("model")
            if model:
                # Extract just the model name if it's a path
                return model.rsplit("/", 1)[-1] if "/" in model else model
        except Exception as e:
            logger.info(f"Failed to read space embedding model: {e}")
        return None

    @property
    def get_vector_supported_types(self) -> List[str]:
        """Get all supported types."""
        support_types = []
        vector_store_classes = _get_all_subclasses()
        for vector_cls in vector_store_classes:
            support_types.append(vector_cls.__type__)
        return support_types

    @staticmethod
    def gen_collection_by_id(knowledge_id: str) -> str:
        index_knowledge_id = knowledge_id.replace("-", "_")
        logger.info(f"index_knowledge_id is {index_knowledge_id}")

        return f"derisk_collection_{index_knowledge_id}"


def _get_all_subclasses() -> List[Type[VectorStoreConfig]]:
    """Get all subclasses of VectorStoreConfig."""
    return VectorStoreConfig.__subclasses__()


def _get_all_memory_subclasses() -> List[Type[MemoryStoreConfig]]:
    """Get all registered MemoryStoreConfig subclasses."""
    return MemoryStoreConfig.__subclasses__()
