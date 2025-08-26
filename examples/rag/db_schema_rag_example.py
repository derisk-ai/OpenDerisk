import os

from derisk.configs.model_config import PILOT_PATH
from derisk_ext.datasource.rdbms.conn_sqlite import SQLiteTempConnector
from derisk_ext.rag.assembler import DBSchemaAssembler
from derisk_ext.storage.vector_store.chroma_store import ChromaVectorConfig, ChromaStore

"""DB struct rag example.
    pre-requirements:
    set your embedding model path in your example code.
    ```
    embedding_model_path = "{your_embedding_model_path}"
    ```

    Examples:
        ..code-block:: shell
            uv run examples/rag/db_schema_rag_example.py
"""


def _create_temporary_connection():
    """Create a temporary database connection for testing."""
    connect = SQLiteTempConnector.create_temporary_db()
    connect.create_temp_tables(
        {
            "user": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "name": "TEXT",
                    "age": "INTEGER",
                },
                "data": [
                    (1, "Tom", 10),
                    (2, "Jerry", 16),
                    (3, "Jack", 18),
                    (4, "Alice", 20),
                    (5, "Bob", 22),
                ],
            }
        }
    )
    return connect


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


if __name__ == "__main__":
    connection = _create_temporary_connection()
    vector_connector = _create_vector_connector()
    assembler = DBSchemaAssembler.load_from_connection(
        connector=connection, table_vector_store_connector=vector_connector
    )
    assembler.persist()
    # get db schema retriever
    retriever = assembler.as_retriever(top_k=1)
    chunks = retriever.retrieve("show columns from user")
    print(f"db schema rag example results:{[chunk.content for chunk in chunks]}")
