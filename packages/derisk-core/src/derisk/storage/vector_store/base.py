"""Vector store base class."""

import logging
import math
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, List, Optional

from derisk.core import Chunk, Embeddings
from derisk.core.awel.flow import Parameter
from derisk.storage.base import IndexStoreBase, IndexStoreConfig
from derisk.storage.vector_store.filters import MetadataFilters
from derisk.util import RegisterParameters
from derisk.util.executor_utils import blocking_func_to_async
from derisk.util.i18n_utils import _

logger = logging.getLogger(__name__)

_COMMON_PARAMETERS = [
    Parameter.build_from(
        _("Collection Name"),
        "name",
        str,
        description=_(
            "The name of vector store, if not set, will use the default name."
        ),
        optional=True,
        default="derisk_collection",
    ),
    Parameter.build_from(
        _("User"),
        "user",
        str,
        description=_(
            "The user of vector store, if not set, will use the default user."
        ),
        optional=True,
        default=None,
    ),
    Parameter.build_from(
        _("Password"),
        "password",
        str,
        description=_(
            "The password of vector store, if not set, will use the default password."
        ),
        optional=True,
        default=None,
    ),
    Parameter.build_from(
        _("Embedding Function"),
        "embedding_fn",
        Embeddings,
        description=_(
            "The embedding function of vector store, if not set, will use "
            "the default embedding function."
        ),
        optional=True,
        default=None,
    ),
    Parameter.build_from(
        _("Max Chunks Once Load"),
        "max_chunks_once_load",
        int,
        description=_(
            "The max number of chunks to load at once. If your document is "
            "large, you can set this value to a larger number to speed up the loading "
            "process. Default is 10."
        ),
        optional=True,
        default=10,
    ),
    Parameter.build_from(
        _("Max Threads"),
        "max_threads",
        int,
        description=_(
            "The max number of threads to use. Default is 1. If you set "
            "this bigger than 1, please make sure your vector store is thread-safe."
        ),
        optional=True,
        default=1,
    ),
]


@dataclass
class VectorStoreConfig(IndexStoreConfig, RegisterParameters):
    """Vector store config."""

    __cfg_type__ = "vector_store"

    user: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "The user of vector store, if not set, will use the default user."
            ),
        },
    )
    password: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "The password of vector store, if not set, "
                "will use the default password."
            ),
        },
    )

    def create_store(self, **kwargs) -> "VectorStoreBase":
        """Create a new index store from the config."""
        raise NotImplementedError("Current vector store does not support create_store")


class VectorStoreBase(IndexStoreBase, ABC):
    """Vector store base class."""

    def __init__(self, executor: Optional[ThreadPoolExecutor] = None):
        """Initialize vector store."""
        super().__init__(executor)

    @abstractmethod
    def get_config(self) -> VectorStoreConfig:
        """Get the vector store config."""

    def filter_by_score_threshold(
        self, chunks: List[Chunk], score_threshold: float
    ) -> List[Chunk]:
        """Filter chunks by score threshold.

        Args:
            chunks(List[Chunks]): The chunks to filter.
            score_threshold(float): The score threshold.
        Return:
            List[Chunks]: The filtered chunks.
        """
        candidates_chunks = chunks
        if score_threshold is not None:
            candidates_chunks = [
                Chunk(
                    metadata=chunk.metadata,
                    content=chunk.content,
                    score=chunk.score,
                    chunk_id=chunk.chunk_id,
                )
                for chunk in chunks
                if chunk.score >= score_threshold
            ]
            if len(candidates_chunks) == 0:
                logger.warning(
                    "No relevant docs were retrieved using the relevance score"
                    f" threshold {score_threshold}"
                )
        return candidates_chunks

    @abstractmethod
    def vector_name_exists(self) -> bool:
        """Whether vector name exists."""
        return False

    def convert_metadata_filters(self, filters: MetadataFilters) -> Any:
        """Convert metadata filters to vector store filters.

        Args:
            filters: (Optional[MetadataFilters]) metadata filters.
        """
        raise NotImplementedError

    def _normalization_vectors(self, vectors):
        """Return L2-normalization vectors to scale[0,1].

        Normalization vectors to scale[0,1].
        """
        import numpy as np

        norm = np.linalg.norm(vectors)
        return vectors / norm

    def _default_relevance_score_fn(self, distance: float) -> float:
        """Return a similarity score on a scale [0, 1]."""
        return 1.0 - distance / math.sqrt(2)

    async def aload_document(self, chunks: List[Chunk]) -> List[str]:  # type: ignore
        """Async load document in index database.

        Args:
            chunks(List[Chunk]): document chunks.

        Return:
            List[str]: chunk ids.
        """
        return await blocking_func_to_async(self._executor, self.load_document, chunks)

    def truncate(self) -> List[str]:
        """Truncate the collection."""
        raise NotImplementedError
