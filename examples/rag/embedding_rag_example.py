import asyncio
import os

from derisk.configs.model_config import PILOT_PATH, ROOT_PATH
from derisk_ext.rag import ChunkParameters
from derisk_ext.rag.assembler import EmbeddingAssembler
from derisk_ext.rag.knowledge import KnowledgeFactory
from derisk_ext.storage.vector_store.chroma_store import ChromaStore, ChromaVectorConfig

"""Embedding rag example.
    pre-requirements:
    set your embedding model path in your example code.
    ```
    embedding_model_path = "{your_embedding_model_path}"
    ```

    Examples:
        ..code-block:: shell
            python examples/rag/embedding_rag_example.py
"""


def _create_vector_connector():
    """Create vector connector."""
    from derisk_ext.rag.embeddings.derisk import DeriskEmbeddings

    embeddings = DeriskEmbeddings()
    embeddings.model_name = "bge_m3"
    config = ChromaVectorConfig(
        persist_path=PILOT_PATH,
    )

    return ChromaStore(
        vector_store_config=config, name="embedding_rag_test", embedding_fn=embeddings
    )


async def main():
    file_path = os.path.join(ROOT_PATH, "README.md")
    knowledge = KnowledgeFactory.from_file_path(file_path)
    vector_store = _create_vector_connector()
    chunk_parameters = ChunkParameters(chunk_strategy="CHUNK_BY_SIZE")
    # get embedding assembler
    assembler = EmbeddingAssembler.load_from_knowledge(
        knowledge=knowledge,
        chunk_parameters=chunk_parameters,
        index_store=vector_store,
    )
    assembler.persist()
    # get embeddings retriever
    retriever = assembler.as_retriever(3)
    chunks = await retriever.aretrieve_with_scores("what is derisk quick start", 0.3)
    print(f"embedding rag example results:{chunks}")


if __name__ == "__main__":
    asyncio.run(main())
