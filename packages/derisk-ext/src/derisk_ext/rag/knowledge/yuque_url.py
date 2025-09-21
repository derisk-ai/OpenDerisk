"""YUQUEURL Knowledge."""
import json
import logging
import re
import uuid
from copy import deepcopy
from typing import Any, List, Optional

from derisk.core import Document, Chunk
from derisk.rag.knowledge.base import ChunkStrategy, Knowledge, KnowledgeType
from derisk.util import oss_utils
from derisk_ext.rag.yuque_index.ant_yuque_loader import AntYuqueLoader
from derisk_serve.rag.models.yuque_db import KnowledgeYuqueEntity

logger = logging.getLogger(__name__)


class YUQUEURLKnowledge(Knowledge):
    """YUQUEURL Knowledge."""

    def __init__(
        self,
        url: str = "",
        knowledge_type: KnowledgeType = KnowledgeType.YUQUEURL,
        source_column: Optional[str] = None,
        encoding: Optional[str] = "utf-8",
        loader: Optional[Any] = None,
        doc_token: Optional[str] = None,
        doc_id: Optional[str] = None,
        yuque_doc_uuid: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Create YUQUE URL Knowledge with Knowledge arguments.

        Args:
            url(str,  optional): url
            knowledge_type(KnowledgeType, optional): knowledge type
            source_column(str, optional): source column
            encoding(str, optional): csv encoding
            loader(Any, optional): loader
        """
        super().__init__(
            path=url, knowledge_type=knowledge_type, loader=loader, **kwargs
        )
        self._encoding = encoding
        self._source_column = source_column
        self._doc_token = doc_token
        self._doc_id = doc_id
        self._doc_uuid = yuque_doc_uuid

    # @property
    def _load(self) -> List[Document]:
        """Fetch URL document from loader."""
        if self._loader:
            documents = self._loader.load()
        else:
            if self._path is not None:
                if self._path.count("/") < 5:
                    raise ValueError(f"yuque url: {self._path} format is incorrect!")
                _, _, _, group, book_slug, doc_id = self._path.split("/", 5)
                web_reader = AntYuqueLoader(access_token=self._doc_token)
                book = web_reader.single_doc(
                    group=group, book_slug=book_slug, doc_id=doc_id
                )
                yuque_url = f"https://yuque.antfin.com/{group}/{book_slug}/{doc_id}"

                if book['type'] == 'Sheet':
                    logger.info(f"yuque url {yuque_url} type is sheet, need sheet split method")

                    return web_reader.parse_document_with_sheet(book, yuque_url, self._doc_token, self._doc_id, self._doc_uuid)

                documents = web_reader.parse_document(
                    book, yuque_url, self._doc_token, self._doc_id, self._doc_uuid
                )
            else:
                raise ValueError("web_path cannot be None")
        return [documents]

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
            ChunkStrategy.CHUNK_BY_SEPARATOR,
            ChunkStrategy.CHUNK_BY_MARKDOWN_HEADER,
        ]

    @classmethod
    def default_chunk_strategy(cls) -> ChunkStrategy:
        """Return default chunk strategy."""
        return ChunkStrategy.CHUNK_BY_MARKDOWN_HEADER

    @classmethod
    def type(cls):
        """Return knowledge type."""
        return KnowledgeType.YUQUEURL
