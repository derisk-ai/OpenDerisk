"""String Knowledge."""

from typing import Any, Dict, List, Optional, Union

from derisk.core import Document
from derisk.rag.knowledge.base import ChunkStrategy, Knowledge, KnowledgeType
from derisk.util import json_utils


class StringKnowledge(Knowledge):
    """String Knowledge."""

    def __init__(
        self,
        text: str = "",
        knowledge_type: KnowledgeType = KnowledgeType.TEXT,
        encoding: Optional[str] = "utf-8",
        loader: Optional[Any] = None,
        metadata: Optional[Dict[str, Union[str, List[str]]]] = None,
        **kwargs: Any,
    ) -> None:
        """Create String knowledge parameters.

        Args:
            text(str): text
            knowledge_type(KnowledgeType): knowledge type
            encoding(str): encoding
            loader(Any): loader
        """
        super().__init__(
            knowledge_type=knowledge_type,
            data_loader=loader,
            metadata=metadata,
            **kwargs,
        )
        self._text = text
        self._encoding = encoding

    def _load(self) -> List[Document]:
        """Load raw text from loader."""
        metadata = {"chunk_type": "text"}
        json_data = json_utils.find_json_objects(self._text)
        if json_data:
            for item in json_data:
                metadata.update(item)
        if self._metadata:
            metadata.update(self._metadata)  # type: ignore
        text = self.parse_document_body(self._text)
        docs = [Document(content=text, metadata=metadata)]
        return docs

    @classmethod
    def support_chunk_strategy(cls) -> List[ChunkStrategy]:
        """Return support chunk strategy."""
        return [
            ChunkStrategy.CHUNK_BY_SIZE,
            ChunkStrategy.CHUNK_BY_SEPARATOR,
            ChunkStrategy.CHUNK_BY_MARKDOWN_HEADER,
            ChunkStrategy.NO_CHUNK,
            ChunkStrategy.DeriskTest,
        ]

    @classmethod
    def default_chunk_strategy(cls) -> ChunkStrategy:
        """Return default chunk strategy."""
        return ChunkStrategy.CHUNK_BY_MARKDOWN_HEADER

    @classmethod
    def type(cls):
        """Return knowledge type."""
        return KnowledgeType.TEXT
