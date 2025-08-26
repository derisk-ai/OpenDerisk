import json
from typing import Callable, Any, List, Optional

from derisk.core import Chunk
from derisk.rag.text_splitter import TextSplitter


class DeriskTestSplitter(TextSplitter):
    """The DeriskTestSplitter class."""

    outgoing_edges = 1

    def __init__(
        self,
        chunk_size: int = 4000,
        chunk_overlap: int = 200,
        length_function: Callable[[str], int] = len,
        filters=None,
        separator: str = "",
        **kwargs: Any,
    ):
        """Create a new TextSplitter."""
        if filters is None:
            filters = []
        if chunk_overlap > chunk_size:
            raise ValueError(
                f"Got a larger chunk overlap ({chunk_overlap}) than chunk size "
                f"({chunk_size}), should be smaller."
            )
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._length_function = length_function
        self._filter = filters
        self._separator = separator

    def split_text(self, text: str, **kwargs) -> List[str]:
        """Split text into multiple components."""
        return [text]

    def create_documents(
        self,
        texts: List[str],
        metadatas: Optional[List[dict]] = None,
        separator: Optional[str] = None,
        **kwargs,
    ) -> List[Chunk]:
        """Create documents from a list of texts."""
        json_text = texts[0]
        data = json.loads(json_text)
        _metadatas = data
        chunks = []
        _metadatas.update({"is_derisk_test": True})
        new_doc = Chunk(content=json_text, metadata=_metadatas)
        chunks.append(new_doc)
        return chunks

    def _concatenate_values(self, data):
        """Concatenate all values in a dictionary or list."""
        if isinstance(data, dict):
            return "".join(self._concatenate_values(value) for value in data.values())
        elif isinstance(data, list):
            return "".join(self._concatenate_values(item) for item in data)
        else:
            return str(data)
