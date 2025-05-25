"""Module for Knowledge Base."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from derisk.core import Document
from derisk.rag.text_splitter.text_splitter import (
    MarkdownHeaderTextSplitter,
    PageTextSplitter,
    ParagraphTextSplitter,
    RecursiveCharacterTextSplitter,
    SeparatorTextSplitter,
    TextSplitter,
)


class DocumentType(Enum):
    """Document Type Enum."""

    PDF = "pdf"
    CSV = "csv"
    MARKDOWN = "md"
    PPTX = "pptx"
    DOCX = "docx"
    TXT = "txt"
    HTML = "html"
    DATASOURCE = "datasource"
    EXCEL = "xlsx"


class TaskStatusType(Enum):
    """Task Status Type Enum."""

    TODO = "TODO"
    RUNNING = "RUNNING"
    SUCCEED = "SUCCEED"
    FAILED = "FAILED"
    FINISHED = "FINISHED"

class KnowledgeType(Enum):
    """Knowledge Type Enum."""

    DOCUMENT = "DOCUMENT"
    URL = "URL"
    TEXT = "TEXT"

    @property
    def type(self):
        """Get type."""
        return DocumentType

    @classmethod
    def get_by_value(cls, value) -> "KnowledgeType":
        """Get Enum member by value.

        Args:
            value(any): value

        Returns:
            KnowledgeType: Enum member
        """
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"{value} is not a valid value for {cls.__name__}")


_STRATEGY_ENUM_TYPE = Tuple[Type[TextSplitter], List, str, str]


class ChunkStrategy(Enum):
    """Chunk Strategy Enum."""

    CHUNK_BY_SIZE: _STRATEGY_ENUM_TYPE = (
        RecursiveCharacterTextSplitter,
        [
            {
                "param_name": "chunk_size",
                "param_type": "int",
                "default_value": 512,
                "description": "分段最大长度",
            },
            {
                "param_name": "chunk_overlap",
                "param_type": "int",
                "default_value": 50,
                "description": "分段最大重叠长度",
            },
        ],
        "chunk size",
        "split document by chunk size",
        "固定长度切分",
    )
    CHUNK_BY_PAGE: _STRATEGY_ENUM_TYPE = (
        PageTextSplitter,
        [],
        "page",
        "split document by page",
        "按页切分",
    )
    CHUNK_BY_PARAGRAPH: _STRATEGY_ENUM_TYPE = (
        ParagraphTextSplitter,
        [
            {
                "param_name": "separator",
                "param_type": "string",
                "default_value": "\\n",
                "description": "段落分隔符号",
            }
        ],
        "paragraph",
        "split document by paragraph",
        "按段落切分",
    )
    CHUNK_BY_SEPARATOR: _STRATEGY_ENUM_TYPE = (
        SeparatorTextSplitter,
        [
            {
                "param_name": "separator",
                "param_type": "string",
                "default_value": "\\n",
                "description": "分隔符号",
            },
            {
                "param_name": "enable_merge",
                "param_type": "boolean",
                "default_value": False,
                "description": "是否允许分隔后再次合并文本段",
            },
        ],
        "separator",
        "split document by separator",
        "分割符切分",
    )
    CHUNK_BY_MARKDOWN_HEADER: _STRATEGY_ENUM_TYPE = (
        MarkdownHeaderTextSplitter,
        [
            {
                "param_name": "header_level",
                "param_type": "string",
                "default_value": "##",
                "description": "标题层级",
            },
            {
                "param_name": "max_split_chunk_size",
                "param_type": "int",
                "default_value": 3072,
                "description": "最大切分的文本段长度",
            },
        ],
        "markdown header",
        "split document by markdown header",
        "标题层级切分",
    )

    def __init__(self, splitter_class, parameters, alias, description, chinese_name):
        """Create a new ChunkStrategy with the given splitter_class."""
        self.splitter_class = splitter_class
        self.parameters = parameters
        self.alias = alias
        self.description = description
        self.chinese_name = chinese_name

    def match(self, *args, **kwargs) -> TextSplitter:
        """Match and build splitter."""
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        return self.value[0](*args, **kwargs)


class Knowledge(ABC):
    """Knowledge Base Class."""

    def __init__(
        self,
        path: Optional[str] = None,
        knowledge_type: Optional[KnowledgeType] = None,
        loader: Optional[Any] = None,
        metadata: Optional[Dict[str, Union[str, List[str]]]] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize with Knowledge arguments."""
        self._path = path
        self._type = knowledge_type
        self._loader = loader
        self._metadata = metadata

    def load(self) -> List[Document]:
        """Load knowledge from data loader."""
        documents = self._load()
        return self._postprocess(documents)

    def extract(
        self,
        documents: List[Document],
        chunk_parameter: Optional["ChunkParameters"] = None,
    ) -> List[Document]:
        """Extract knowledge from text."""
        return documents

    @classmethod
    @abstractmethod
    def type(cls) -> KnowledgeType:
        """Get knowledge type."""

    @classmethod
    def document_type(cls) -> Any:
        """Get document type."""
        return None

    def _postprocess(self, docs: List[Document]) -> List[Document]:
        """Post process knowledge from data loader."""
        return docs

    @property
    def file_path(self):
        """Get file path."""
        return self._path

    @abstractmethod
    def _load(self) -> List[Document]:
        """Preprocess knowledge from data loader."""

    @classmethod
    def support_chunk_strategy(cls) -> List[ChunkStrategy]:
        """Return supported chunk strategy."""
        return ChunkStrategy.CHUNK_BY_SIZE

    @classmethod
    def default_chunk_strategy(cls) -> ChunkStrategy:
        """Return default chunk strategy.

        Returns:
            ChunkStrategy: default chunk strategy
        """
        return ChunkStrategy.CHUNK_BY_SIZE
