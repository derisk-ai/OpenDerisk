from __future__ import annotations

import logging
import threading
from typing import Any, List, Optional, Type

from derisk.component import ComponentType, SystemApp
from derisk.core import Embeddings, RerankEmbeddings
from derisk.rag.embedding.embedding_factory import (
    EmbeddingFactory,
    RerankEmbeddingFactory,
)

logger = logging.getLogger(__name__)


class EmbeddingModelRegistry:
    """Process-wide registry of available embedding (text2vec) models.

    This is the single source of truth for "which embedding models exist and
    which one is the default", independent of how a model was added — at
    startup from config, or at runtime by deploying a worker via the model
    management page.

    The ``RemoteEmbeddingFactory`` resolves its model name from this registry
    at ``create()`` time, so newly-deployed embedding models become usable by
    the RAG / memory subsystems without restarting the server or
    re-registering the ``embedding_factory`` component.

    "Default = first added" semantics: the default is the first model added,
    and later additions never steal the default unless explicitly set.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Insertion-ordered list of model names (dedup, first-added-first).
        self._models: List[str] = []
        self._default: Optional[str] = None

    def add(self, model_name: str, make_default: bool = False) -> None:
        if not model_name:
            return
        with self._lock:
            if model_name not in self._models:
                self._models.append(model_name)
                logger.info(
                    f"Embedding model registered: '{model_name}' "
                    f"(total={len(self._models)})"
                )
            # First model added becomes the default automatically.
            if make_default or self._default is None:
                self._default = model_name
                logger.info(f"Default embedding model set to '{model_name}'")

    def set_default(self, model_name: str) -> bool:
        with self._lock:
            if model_name not in self._models:
                logger.warning(
                    f"Cannot set default embedding to unknown model "
                    f"'{model_name}'. Known models: {self._models}"
                )
                return False
            self._default = model_name
            logger.info(f"Default embedding model switched to '{model_name}'")
            return True

    def get_default(self) -> Optional[str]:
        with self._lock:
            if self._default:
                return self._default
            # Fall back to the first added model ("multiple -> first").
            return self._models[0] if self._models else None

    def list(self) -> List[str]:
        with self._lock:
            return list(self._models)

    def is_empty(self) -> bool:
        with self._lock:
            return not self._models


# Process-wide singleton. The factory is created once per process and reads
# from this registry, so registry mutations are visible immediately.
_embedding_registry = EmbeddingModelRegistry()


def get_embedding_registry() -> EmbeddingModelRegistry:
    """Return the process-wide embedding model registry singleton."""
    return _embedding_registry


def _initialize_embedding_model(
    system_app: SystemApp,
    default_embedding_name: Optional[str] = None,
):
    """Register the embedding factory (always) and seed the default model.

    The factory is registered unconditionally so that embedding models added
    at runtime are immediately usable. If ``default_embedding_name`` is
    provided (e.g. from a TOML/JSON config at startup), it seeds the registry.
    """
    if default_embedding_name:
        _embedding_registry.add(default_embedding_name)

    if not system_app.get_component(
        "embedding_factory", EmbeddingFactory, default_component=None
    ):
        logger.info("Register RemoteEmbeddingFactory (dynamic default)")
        system_app.register(RemoteEmbeddingFactory)


def _initialize_rerank_model(
    system_app: SystemApp,
    default_rerank_model_name: Optional[str] = None,
):
    if default_rerank_model_name:
        logger.info("Register remote RemoteRerankEmbeddingFactory")
        system_app.register(
            RemoteRerankEmbeddingFactory, model_name=default_rerank_model_name
        )


class RemoteEmbeddingFactory(EmbeddingFactory):
    def __init__(self, system_app, model_name: str = None, **kwargs: Any) -> None:
        super().__init__(system_app=system_app)
        # Optional seed default; the registry is authoritative.
        self._default_model_name = model_name
        if model_name:
            _embedding_registry.add(model_name)
        self.kwargs = kwargs
        self.system_app = system_app

    def init_app(self, system_app):
        self.system_app = system_app

    def create(
        self, model_name: str = None, embedding_cls: Type = None
    ) -> "Embeddings":
        from derisk.model.cluster import WorkerManagerFactory
        from derisk.model.cluster.embedding.remote_embedding import RemoteEmbeddings

        if embedding_cls:
            raise NotImplementedError
        # Explicit model_name (e.g. per knowledge-space) wins; otherwise resolve
        # the current default from the registry at call time.
        resolved = model_name or _embedding_registry.get_default()
        if not resolved:
            raise ValueError(
                "No embedding model available. Add a text2vec (embedding) model "
                "on the model management page (/models) before using knowledge "
                "bases or memory."
            )
        worker_manager = self.system_app.get_component(
            ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
        ).create()
        return RemoteEmbeddings(resolved, worker_manager)


class RemoteRerankEmbeddingFactory(RerankEmbeddingFactory):
    def __init__(self, system_app, model_name: str = None, **kwargs: Any) -> None:
        super().__init__(system_app=system_app)
        self._default_model_name = model_name
        self.kwargs = kwargs
        self.system_app = system_app

    def init_app(self, system_app):
        self.system_app = system_app

    def create(
        self, model_name: str = None, embedding_cls: Type = None
    ) -> "RerankEmbeddings":
        from derisk.model.cluster import WorkerManagerFactory
        from derisk.model.cluster.embedding.remote_embedding import (
            RemoteRerankEmbeddings,
        )

        if embedding_cls:
            raise NotImplementedError
        worker_manager = self.system_app.get_component(
            ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
        ).create()
        return RemoteRerankEmbeddings(
            model_name or self._default_model_name, worker_manager
        )
