"""Module for Knowledge Base."""
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from derisk._private.config import Config
from derisk.core import Document, Chunk
from derisk.rag.text_splitter.text_splitter import (
    MarkdownHeaderTextSplitter,
    PageTextSplitter,
    ParagraphTextSplitter,
    RecursiveCharacterTextSplitter,
    SeparatorTextSplitter,
    TextSplitter,
    BlankSplitter,
)
from derisk_ext.rag.text_splitter.derisk_test_splitter import DeriskTestSplitter
from derisk_serve.core import blocking_func_to_async
from bs4 import BeautifulSoup


cfg = Config()

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


class DirectoryModeType(Enum):

    DOCUMENT = "document"
    BOOK = "book"


class KnowledgeType(Enum):
    """Knowledge Type Enum."""

    DOCUMENT = "DOCUMENT"
    URL = "URL"
    TEXT = "TEXT"
    YUQUEURL = "YUQUEURL"

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
    NO_CHUNK: _STRATEGY_ENUM_TYPE = (
        BlankSplitter,
        [],
        "no chunk",
        "do not split",
        "不需要切分",
    )

    # 质量团队切分策略
    DeriskTest: _STRATEGY_ENUM_TYPE = (
        DeriskTestSplitter,
        [],
        "dirisk test",
        "dirisk test split",
        "derisk 测试切分",
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
        self._system_app = cfg.SYSTEM_APP
        doc_name = kwargs.get("doc_name", None)
        self._doc_name = doc_name.replace(f".{self.suffix}", "") if doc_name else None

    def load(self) -> List[Document]:
        """Load knowledge from data loader."""
        documents = self._load()
        return self._postprocess(documents)

    async def aload(self) -> List[Document]:
        """Load knowledge from data loader."""
        return await blocking_func_to_async(
            self._system_app, self.load
        )

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

    @property
    def suffix(self) -> Any:
        """Get document suffix."""
        return ""

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

    @staticmethod
    def parse_document_body(body: str) -> str:
        result = re.sub(r'<a name="(.*)"></a>', "", body)
        result = re.sub(r"<br\s*/?>", "", result)
        soup = BeautifulSoup(result, 'html.parser')
        result = soup.get_text()
        return result

    def extract_images(
            self,
            chunks: List[Chunk],
    ):
        """
        Extract Images from chunks using regex.

        Args:
            chunks:
        """
        return chunks

    def get_image_by_url(
        self, url: str, encoding: Optional[str] = "utf-8"
    ) -> Union[str, None]:
        """Get image by url."""
        if not url:
            return None
        try:
            return oss_utils.get_oss_url(url, encoding=encoding)
        except Exception as e:
            raise ValueError(f"Failed to get image from url {url}: {e}")
