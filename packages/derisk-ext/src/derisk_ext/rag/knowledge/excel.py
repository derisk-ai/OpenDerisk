"""Excel Knowledge."""

from typing import Any, Dict, List, Optional, Union

import pandas as pd

from derisk.core import Document
from derisk.rag.knowledge.base import (
    ChunkStrategy,
    DocumentType,
    Knowledge,
    KnowledgeType,
)


class ExcelKnowledge(Knowledge):
    """Excel Knowledge."""

    def __init__(
        self,
        file_path: Optional[str] = None,
        knowledge_type: Optional[KnowledgeType] = KnowledgeType.DOCUMENT,
        source_columns: Optional[str] = None,
        encoding: Optional[str] = "utf-8",
        loader: Optional[Any] = None,
        metadata: Optional[Dict[str, Union[str, List[str]]]] = None,
        **kwargs: Any,
    ) -> None:
        """Create xlsx Knowledge with Knowledge arguments.

        Args:
            file_path(str,  optional): file path
            knowledge_type(KnowledgeType, optional): knowledge type
            source_column(str, optional): source column
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
        self._source_columns = source_columns.split(",") if source_columns else None

    def _load(self) -> List[Document]:
        """Load csv document from loader."""
        if self._loader:
            documents = self._loader.load()
        else:
            docs = []
            if not self._path:
                raise ValueError("file path is required")

            excel_file = pd.ExcelFile(self._path)
            sheet_names = excel_file.sheet_names
            doc_name = self._doc_name or self._path.rsplit("/", 1)[-1].replace(".xlsx", "")
            metadata = {
                "source": self._path,
                "doc_name": doc_name,
                "data_type": "excel",
            }
            for sheet_name in sheet_names:
                df = excel_file.parse(sheet_name)
                metadata["sheet_name"] = sheet_name
                if (
                    sum(1 for col in df.columns if "Unnamed" in str(col))
                    > len(df.columns) / 2
                ):
                    headers = df.iloc[0].tolist()
                    df = df.iloc[1:]
                    df.columns = headers
                else:
                    headers = df.columns.tolist()

                for index, row in df.iterrows():
                    strs = []
                    # metadata = {"row": index}
                    for header, value in zip(headers, row):
                        if header is None or value is None:
                            continue

                        header_str = str(header).strip()
                        value_str = str(value).strip() if not pd.isna(value) else ""
                        metadata[header_str] = value_str
                        if (
                            self._source_columns
                            and header_str not in self._source_columns
                        ):
                            continue
                        value_str = super().parse_document_body(value_str)
                        strs.append(f"{value_str}")
                    content = "\n".join(strs)
                    metadata["row"] = index
                    if self._metadata:
                        metadata.update(self._metadata)  # type: ignore
                    doc = Document(content=content, metadata=metadata)
                    docs.append(doc)

            return docs

        return [Document.langchain2doc(lc_document) for lc_document in documents]

    @classmethod
    def support_chunk_strategy(cls) -> List[ChunkStrategy]:
        """Return support chunk strategy."""
        return [
            ChunkStrategy.CHUNK_BY_SIZE,
            ChunkStrategy.CHUNK_BY_SEPARATOR,
        ]

    @classmethod
    def default_chunk_strategy(cls) -> ChunkStrategy:
        """Return default chunk strategy."""
        return ChunkStrategy.CHUNK_BY_SIZE

    @classmethod
    def type(cls) -> KnowledgeType:
        """Knowledge type of CSV."""
        return KnowledgeType.DOCUMENT

    @classmethod
    def document_type(cls) -> DocumentType:
        """Return document type."""
        return DocumentType.EXCEL

    @property
    def suffix(self) -> Any:
        """Get document suffix."""
        return DocumentType.EXCEL.value
