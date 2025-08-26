"""Markdown Knowledge."""
import re
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional, Union

from derisk.core import Document, Chunk
from derisk.rag.knowledge.base import (
    ChunkStrategy,
    DocumentType,
    Knowledge,
    KnowledgeType,
)
from derisk_ext.rag import ChunkParameters


class MarkdownKnowledge(Knowledge):
    """Markdown Knowledge."""

    def __init__(
        self,
        file_path: Optional[str] = None,
        knowledge_type: KnowledgeType = KnowledgeType.DOCUMENT,
        encoding: Optional[str] = "utf-8",
        loader: Optional[Any] = None,
        metadata: Optional[Dict[str, Union[str, List[str]]]] = None,
        **kwargs: Any,
    ) -> None:
        """Create Markdown Knowledge with Knowledge arguments.

        Args:
            file_path(str,  optional): file path
            knowledge_type(KnowledgeType, optional): knowledge type
            encoding(str, optional): csv encoding
            loader(Any, optional): loader
        """
        super().__init__(
            path=file_path,
            knowledge_type=knowledge_type,
            data_loader=loader,
            metadata=metadata,
            **kwargs,
        )
        self._encoding = encoding

    def _load(self) -> List[Document]:
        """Load markdown document from loader."""
        if self._loader:
            documents = self._loader.load()
        else:
            if not self._path:
                raise ValueError("file path is required")
            with open(self._path, encoding=self._encoding, errors="ignore") as f:
                markdown_text = f.read()
                # remove html tags
                import re

                markdown_text = re.sub(r"<[^>]+>", "", markdown_text)
                # remove extra newlines
                doc_name = self._doc_name or self._path.rsplit("/", 1)[-1].replace(".md", "")
                metadata = {"source": self._path, "doc_name": doc_name}
                if self._metadata:
                    metadata.update(self._metadata)  # type: ignore
                documents = [Document(content=markdown_text, metadata=metadata)]
                return documents
        return [Document.langchain2doc(lc_document) for lc_document in documents]

    def extract(
        self,
        documents: List[Document],
        chunk_parameter: Optional[ChunkParameters] = None,
    ) -> List[Document]:
        """Extract knowledge from text."""
        from derisk_ext.rag.chunk_manager import ChunkManager

        chunk_manager = ChunkManager(knowledge=self, chunk_parameter=chunk_parameter)
        chunks = chunk_manager.split(documents)
        for document in documents:
            document.chunks = chunks
        return documents

    def extract_images(
            self,
            chunks: List[Chunk],
    ):
        """
        Extract Images from chunks using regex.

        Args:
            chunks:
        """
        new_chunks = []
        for chunk in chunks:
            new_chunks.append(chunk)
            text = chunk.content
            pattern = r'!\[.*?\]\((https?://[^\s)]+)\)'
            urls = re.findall(pattern, text)
            if urls:
                for url in urls:
                    new_chunk = deepcopy(chunk)
                    new_chunk.image_url = url
                    new_chunk.chunk_id = str(uuid.uuid4())
                    new_chunk.chunk_type = "image"
                    new_chunk.metadata = {
                        **chunk.metadata,
                        "chunk_type": "image",
                        "image_url": url,
                    }
                    new_chunks.append(new_chunk)
        return new_chunks

    @classmethod
    def support_chunk_strategy(cls) -> List[ChunkStrategy]:
        """Return support chunk strategy."""
        return [
            ChunkStrategy.CHUNK_BY_SIZE,
            ChunkStrategy.CHUNK_BY_MARKDOWN_HEADER,
            ChunkStrategy.CHUNK_BY_SEPARATOR,
        ]

    @classmethod
    def default_chunk_strategy(cls) -> ChunkStrategy:
        """Return default chunk strategy."""
        return ChunkStrategy.CHUNK_BY_MARKDOWN_HEADER

    @classmethod
    def type(cls) -> KnowledgeType:
        """Return knowledge type."""
        return KnowledgeType.DOCUMENT

    @classmethod
    def document_type(cls) -> DocumentType:
        """Return document type."""
        return DocumentType.MARKDOWN

    @property
    def suffix(self) -> Any:
        """Get document suffix."""
        return DocumentType.MARKDOWN.value
