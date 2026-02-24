"""RAG STORAGE MANAGER manager."""

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

    def storage_config(self):
        """Storage config."""
        app_config = self.system_app.config.configs.get("app_config")
        return app_config.rag.storage

    def get_storage_connector(
        self, index_name: str, storage_type: str, llm_model: Optional[str] = None
    ) -> IndexStoreBase:
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
            if not storage_config.graph:
                raise ValueError(
                    "Graph storage is not configured.please check your config."
                    "reference configs/derisk-graphrag.toml"
                )
            return self.create_kg_store(index_name, llm_model)
        elif storage_type == "FullText":
            if not storage_config.full_text:
                raise ValueError(
                    "FullText storage is not configured.please check your config."
                    "reference configs/derisk-bm25-rag.toml"
                )
            return self.create_full_text_store(index_name)
        else:
            raise ValueError(f"Does not support storage type {storage_type}")

    def create_vector_store(
            self,
            index_name,
            extra_indexes: Optional[List[str]] = None
    ) -> VectorStoreBase:
        """Create vector store."""
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
            logger.warning(
                f"embedding factory not found: {e}, try to use DefaultEmbeddingFactory"
            )
            # Check if default_embedding is configured, otherwise fallback to a safe default
            default_model_name = getattr(app_config.models, "default_embedding", "text2vec")
            if not default_model_name:
                 default_model_name = "text2vec"
                 
            embedding_fn = DefaultEmbeddingFactory(
                self.system_app, default_model_name=default_model_name
            ).create()

        # Try to get type from config object, handling both dict-like and object-like access
        vector_store_type = getattr(storage_config.vector, "type", None)
        if not vector_store_type:
            vector_store_type = getattr(storage_config.vector, "__type__", None)
            
        if vector_store_type == "chroma":
             from derisk_ext.storage.vector_store.chroma_store import ChromaStore, ChromaVectorConfig
             
             # Extract persist_path safely
             persist_path = getattr(storage_config.vector, "persist_path", None)
             
             vector_store_config = ChromaVectorConfig(
                 persist_path=persist_path
             )
             new_store = ChromaStore(
                 vector_store_config=vector_store_config,
                 name=index_name,
                 embedding_fn=embedding_fn
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
            vector_store_config=zsearch_config
        )
        self._store_cache[index_name] = new_store
        return new_store


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
    """Get all subclasses of cls."""

    return VectorStoreConfig.__subclasses__()
