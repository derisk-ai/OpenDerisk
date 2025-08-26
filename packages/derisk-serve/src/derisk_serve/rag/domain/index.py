import logging
import timeit
from typing import List, Optional

from derisk.core import Chunk
from derisk.rag.knowledge.base import Knowledge
from derisk.rag.transformer.llm_extractor import LLMExtractor
from derisk.storage.full_text.base import FullTextStoreBase
from derisk.storage.knowledge_graph.base import KnowledgeGraphBase
from derisk.storage.vector_store.base import VectorStoreBase
from derisk.util.tracer import root_tracer
from derisk_ext.rag import ChunkParameters
from derisk_ext.rag.chunk_manager import ChunkManager
from derisk_ext.rag.transformer.image_extractor import ImageExtractor
from derisk_ext.rag.yuque_index.ant_yuque_loader import AntYuqueLoader
from derisk_serve.rag.domain.base import DomainKnowledgeIndex
from derisk_serve.rag.models.chunk_db import DocumentChunkDao, DocumentChunkEntity
from derisk_serve.rag.models.document_db import KnowledgeDocumentDao, KnowledgeDocumentEntity

logger = logging.getLogger(__name__)


chunk_dao = DocumentChunkDao()
document_dao = KnowledgeDocumentDao()

class DomainGeneralIndex(DomainKnowledgeIndex):
    async def extract(
        self,
            knowledge: Knowledge,
            chunk_parameter: ChunkParameters,
            extract_image: bool = False,
            **kwargs
    ) -> list[Chunk]:
        if not knowledge:
            raise ValueError("knowledge must be provided.")
        with root_tracer.start_span("DomainGeneralIndex.knowledge.load"):
            # documents = knowledge.load()
            documents = await knowledge.aload()
        with root_tracer.start_span("DomainGeneralIndex.chunk_manager.split"):
            chunk_manager = ChunkManager(
                knowledge=knowledge, chunk_parameter=chunk_parameter
            )
            chunks = chunk_manager.split(documents)
            for chunk in chunks:
                chunk.metadata["chunk_id"] = chunk.chunk_id
        with root_tracer.start_span("DomainGeneralIndex.knowledge.extract"):
            if extract_image:
                new_chunks = knowledge.extract_images(chunks)
                return new_chunks
            return chunks

    async def transform(
            self,
            chunks: List[Chunk],
            image_extractor: Optional[LLMExtractor] = None,
            summary_extractor: Optional[LLMExtractor] = None,
            batch_size: int = 1,
            **kwargs
    ) -> List[Chunk]:
        """Transform knowledge chunks using extractors.

        Args:
            chunks (List[Chunk]): List of knowledge chunks to transform.
            image_extractor (Optional[LLMExtractor]): Extractor for images.
            summary_extractor (Optional[LLMExtractor]): Extractor for summaries.
            batch_size: (int): Number of chunks to process in each batch.
        Returns
            List[Chunk]: Transformed knowledge chunks.
        """
        transform_chunks = chunks
        if image_extractor:
            with root_tracer.start_span(
                "DomainGeneralIndex.chunk_manager.transform.image_extractor"
            ):
                image_url_code_dict = get_image_url_code_dict(chunks)

                transform_chunks = await process_images_in_batches(
                    chunks,
                    image_extractor,
                    batch_size=1,
                    image_url_code_dict=image_url_code_dict
                )
        if summary_extractor:
            with root_tracer.start_span(
                "DomainGeneralIndex.chunk_manager.transform.summary_extractor"
            ):
                for chunk in transform_chunks:
                    """ Extract text from summary using the extractor."""
                    summary_text = await summary_extractor.extract(
                        text=chunk.content
                    )
                    chunk.summary = summary_text
        return transform_chunks

    async def load(
        self,
        chunks: list[Chunk],
        vector_store: Optional[VectorStoreBase] = None,
        full_text_store: Optional[FullTextStoreBase] = None,
        kg_store: Optional[KnowledgeGraphBase] = None,
        keywords: bool = True,
        max_chunks_once_load: int = 10,
        max_threads: int = 1,
        **kwargs,
    ) -> list[Chunk]:
        """Load knowledge chunks into storage."""
        if vector_store:
            vector_ids = await vector_store.aload_document_with_limit(
                chunks, max_chunks_once_load, max_threads
            )
            for chunk, vector_id in zip(chunks, vector_ids):
                chunk.vector_id = vector_id
        if full_text_store:
            await full_text_store.aload_document_with_limit(
                chunks, max_chunks_once_load, max_threads
            )
        if kg_store:
            await kg_store.aload_document_with_limit(
                chunks, max_chunks_once_load, max_threads
            )
        return chunks

    async def clean(
        self,
        chunks: list[Chunk],
        node_ids: Optional[list[str]],
        with_keywords: bool = True,
        **kwargs,
    ):
        raise NotImplementedError

    @property
    def domain_type(self):
        return "general"


def get_image_url_code_dict_from_yuque(yuque_url: str, yuque_token: str):
    logger.info(f"get_image_url_code_dict_from_yuque yuque_url is {yuque_url}")

    # 查询语雀文档
    group_login, book_slug, doc_slug = yuque_url.split("/")[-3:]
    web_reader = AntYuqueLoader(access_token=yuque_token)
    doc = web_reader.single_doc(group_login, book_slug, doc_slug)

    # 解析图片uml信息
    uml_data = web_reader.get_uml_content_from_doc(doc)
    image_url_code_dict = {}
    for data in uml_data:
        image_url = data["url"]
        source_code = data["code"]
        image_url_code_dict[image_url] = source_code

    return image_url_code_dict


def get_image_url_code_dict(chunks: List[Chunk]):
    logger.info(f"get_image_url_code_dict chunks is {chunks}f")

    image_url_code_dict = {}
    if not chunks:
        return image_url_code_dict

    # 查询chunk 表
    chunk_id = chunks[0].chunk_id
    db_chunks = chunk_dao.get_document_chunks(query=DocumentChunkEntity(chunk_id=chunk_id))
    if not db_chunks:
        return image_url_code_dict
    doc_id = db_chunks[0].doc_id

    # 查询doc表
    db_docs = document_dao.get_knowledge_documents(query=KnowledgeDocumentEntity(doc_id=doc_id))
    if not db_docs:
        return image_url_code_dict

    # 获取语雀uml图的源码
    yuque_url = db_docs[0].content
    yuque_token = db_docs[0].doc_token
    image_url_code_dict = get_image_url_code_dict_from_yuque(yuque_url, yuque_token)
    logger.info(f"get_image_url_code_dict image_url_code_dict len is {len(image_url_code_dict.keys())}")

    return image_url_code_dict


async def process_images_in_batches(chunks, image_extractor, batch_size=5, image_url_code_dict={}):
    """
    Process image URLs in chunks concurrently.

    Args:
        chunks: chunks
        image_extractor: image extractor.
        batch_size: batch size for processing
    """
    start_time = timeit.default_timer()
    processed_chunks = chunks

    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i:i + batch_size]

        batch_image_tasks = []
        for chunk in batch_chunks:
            if chunk.image_url:
                batch_image_tasks.append((chunk,  chunk.image_url))
        import asyncio
        batch_results = await asyncio.gather(
            *[extract_image_task(chunk, image_url, image_extractor, image_url_code_dict)
              for chunk, image_url in batch_image_tasks]
        )

        for result in batch_results:
            if result:
                processed_chunks.append(result)

    cost_time = round(timeit.default_timer() - start_time, 2)
    logger.info(f"transform chunks text info cost time is {cost_time} seconds")

    return processed_chunks


async def extract_image_task(
        chunk: Chunk,
        image_url: str,
        image_extractor: ImageExtractor,
        image_url_code_dict: dict
) -> Optional[Chunk]:
    """
    Process a single image URL and extract text from it.

    Args:
        chunk: The chunk containing metadata.
        image_url: The URL of the image to process.
        image_extractor: The extractor to use for extracting text from the image.
    """
    try:
        logger.info(f"Processing image {image_url}")
        from derisk.util import oss_utils
        image = oss_utils.get_oss_url(image_url)

        if not image:
            return None

        if image_url_code_dict.get(image_url):
            # 提取图片源代码
            chunk.content = image_url_code_dict[image_url]
        else:
            # VLM提取图片文本
            image_text = await image_extractor.extract(image=image, text=chunk.content)
            chunk.content = image_text
        return chunk

    except Exception as e:
        logger.error(f"Error processing image {image_url}: {e}")
        return None