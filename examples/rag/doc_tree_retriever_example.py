import asyncio
from derisk.model.proxy import DeepseekLLMClient
from derisk.rag.knowledge.base import ChunkStrategy
from derisk.rag.transformer.keyword_extractor import KeywordExtractor
from derisk_ext.rag import ChunkParameters
from derisk_ext.rag.knowledge import KnowledgeFactory
from derisk_ext.rag.retriever.doc_tree import DocTreeRetriever


async def main():
    knowledge = KnowledgeFactory.from_file_path("../../docs/docs/awel/awel.md")
    chunk_parameters = ChunkParameters(
        chunk_strategy=ChunkStrategy.CHUNK_BY_MARKDOWN_HEADER.name
    )
    docs = knowledge.load()
    docs = knowledge.extract(docs, chunk_parameters)
    llm_client = DeepseekLLMClient(api_key="your_api_key")
    keyword_extractor = KeywordExtractor(
        llm_client=llm_client, model_name="deepseek-chat"
    )
    # doc tree retriever retriever
    retriever = DocTreeRetriever(
        docs=docs,
        top_k=10,
        keywords_extractor=keyword_extractor,
    )
    nodes = await retriever.aretrieve("Introduce awel Operators")
    print(f"doc tree retriever example results:{nodes}")


if __name__ == "__main__":
    asyncio.run(main())
