import logging
import re
from typing import Optional, List

from derisk import SystemApp
from derisk.storage.metadata import BaseDao
from derisk.storage.vector_store.filters import MetadataFilters, MetadataFilter
from derisk_ext.rag.retriever.doc_tree import DocumentOutlineParser
from derisk_ext.rag.yuque_index.ant_yuque_loader import AntYuqueLoader
from derisk_serve.core import BaseService
from derisk_serve.rag.api.schemas import KnowledgeSearchResponse
from derisk_serve.rag.config import ServeConfig, SERVE_YUQUE_SERVICE_COMPONENT_NAME
from derisk_serve.rag.models.yuque_db import KnowledgeYuqueDao, KnowledgeYuqueEntity
from derisk_serve.rag.retriever.knowledge_space import KnowledgeSpaceRetriever

logger = logging.getLogger(__name__)

BASE_YUQUE_URL = "https://yuque.com"
YUQUE_URL_REGEX = re.compile(r"https://yuque\.com/[\w\d_/-]+")


class YuqueService(BaseService):
    """The service class for Yuque"""

    name = SERVE_YUQUE_SERVICE_COMPONENT_NAME

    def __init__(
            self,
            system_app: SystemApp,
            config: ServeConfig,
            dao: Optional[KnowledgeYuqueDao] = None,
    ):
        self._system_app = None
        self._dao: KnowledgeYuqueDao = dao or KnowledgeYuqueDao()
        self._serve_config: ServeConfig = config
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service

        Args:
            system_app (SystemApp): The system app
        """
        super().init_app(system_app)
        self._dao = self._dao or KnowledgeYuqueDao
        self._system_app = system_app

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._serve_config

    @property
    def rag_service(self):
        from derisk_serve.rag.service.service import Service as RagService

        return RagService.get_instance(self._system_app)

    @property
    def dao(self) -> BaseDao:
        """Returns the internal DAO."""
        return self._dao

    def get_yuque_by_uuid(self, doc_uuid: str) -> KnowledgeYuqueEntity:
        return self._dao.get_knowledge_yuque(
            query=KnowledgeYuqueEntity(doc_uuid=doc_uuid)
        )

    async def read_document(
            self,
            knowledge_ids: List[str],
            doc_uuids: List[str],
            header: Optional[str] = None,
    ) -> KnowledgeSearchResponse:
        """Read document content.

        Args:
            knowledge_ids(List[str]): knowledge_ids.
            doc_uuids(List[str]): doc_uuids.
            header(Optional[str]): header.
        """
        logger.info(
            f"read_document knowledge_ids is {knowledge_ids}, "
            f"doc_uuids is {doc_uuids}, header is {header}"
        )

        if not knowledge_ids or not doc_uuids:
            raise Exception("knowledge_ids or doc_uuids is empty")

        yuque_docs = self._dao.get_knowledge_yuque(
            query=KnowledgeYuqueEntity(
                knowledge_id=knowledge_ids[0]), doc_uuids=doc_uuids
        )
        if not yuque_docs:
            raise Exception("yuque_docs is empty")

        all_processed_contents = []
        doc_titles = []

        for yuque_doc in yuque_docs:
            token = yuque_doc.token
            yuque_url = f"{BASE_YUQUE_URL}/{yuque_doc.group_login}/{yuque_doc.book_slug}/{yuque_doc.doc_slug}"
            doc_detail = self.get_yuque_doc_form_url(yuque_url=yuque_url,
                                                     yuque_token=token)
            full_doc_body = doc_detail.get("body", "")
            knowledge_retriever = KnowledgeSpaceRetriever(
                space_id=knowledge_ids[0],
                embedding_model=self._serve_config.embedding_model,
                top_k=3,
                retrieve_mode="keyword",
                system_app=self._system_app,
            )
            filters = MetadataFilters(
                filters=[
                    MetadataFilter(
                        key="chunk_type",
                        value="image",
                    ),
                    MetadataFilter(
                        key="doc_id",
                        value=yuque_doc.doc_id,
                    ),
                ]
            )
            current_doc_content = full_doc_body
            if header and full_doc_body:
                parser = DocumentOutlineParser()
                tree_nodes = parser.get_outlines_from_body(full_doc_body)
                if tree_nodes:
                    # 尝试找到匹配 header 的节点
                    tree_node, _ = parser.find_similar_header_node(tree_nodes, header)
                    if tree_node:
                        # current_title = tree_node.title
                        header_section_content = parser.display([tree_node])
                        current_doc_content = header_section_content  # 初始内容设定为header部分
                        # 检查 header 内容长度是否小于200，并且其中是否包含 Yuque 链接
                        if len(header_section_content) < 200:
                            found_yuque_urls = YUQUE_URL_REGEX.findall(
                                header_section_content)
                            if found_yuque_urls:
                                logger.info(
                                    f"Header '{header}' content for doc '{yuque_doc.title}' is short "
                                    f"({len(header_section_content)} chars) and contains Yuque URLs. "
                                    f"Attempting to fetch sub-links: {found_yuque_urls}"
                                )
                                sub_linked_contents = []
                                for sub_url in found_yuque_urls:
                                    try:
                                        sub_doc_detail = self.get_yuque_doc_form_url(
                                            yuque_url=sub_url, yuque_token=token)
                                        sub_doc_body = sub_doc_detail.get("body", "")

                                        if sub_doc_body:
                                            sub_parser = DocumentOutlineParser()  # 为子文档创建新的解析器实例
                                            sub_tree_nodes = sub_parser.get_outlines_from_body(
                                                sub_doc_body)
                                            sub_content_for_header = ""

                                            if sub_tree_nodes:
                                                # 尝试在子文档中找到相同的 header
                                                sub_tree_node, _ = sub_parser.find_similar_header_node(
                                                    sub_tree_nodes, header)
                                                if sub_tree_node:
                                                    sub_content_for_header = sub_parser.display(
                                                        [sub_tree_node])
                                                    logger.info(
                                                        f"Fetched sub-link '{sub_url}' and found matching header '{header}' content.")
                                                else:
                                                    # 如果子文档中没有找到匹配的 header，则提取子文档的部分内容
                                                    sub_content_for_header = f"--- Content from sub-document '{sub_url}' (header '{header}' not found) ---\n{sub_doc_body[:1000]}..."  # 限制长度
                                                    logger.warning(
                                                        f"Sub-link '{sub_url}' found, but header '{header}' not found in it. Appending partial body.")
                                            else:
                                                # 如果子文档没有大纲结构，则提取子文档的部分内容
                                                sub_content_for_header = f"--- Content from sub-document '{sub_url}' (no outline found) ---\n{sub_doc_body[:1000]}..."  # 限制长度
                                                logger.warning(
                                                    f"Sub-link '{sub_url}' found, but no outline. Appending partial body.")

                                            if sub_content_for_header:
                                                sub_linked_contents.append(
                                                    sub_content_for_header)
                                        else:
                                            logger.warning(
                                                f"Sub-link '{sub_url}' returned empty body for '{yuque_doc.title}'.")

                                    except Exception as e:
                                        logger.error(
                                            f"Error fetching sub-link '{sub_url}' for doc '{yuque_doc.title}': {e}")
                                        sub_linked_contents.append(
                                            f"--- Error fetching sub-link '{sub_url}': {e} ---")

                                # 将原始 header 内容与子链接内容组装
                                if sub_linked_contents:
                                    current_doc_content = (
                                            header_section_content
                                            + "\n\n--- Linked Document Content ---\n\n"
                                            + "\n\n".join(sub_linked_contents)
                                    )
                                else:
                                    logger.info(
                                        f"No valid content retrieved from sub-links for header '{header}' in doc '{yuque_doc.title}'.")
                            else:
                                logger.info(
                                    f"Header '{header}' content is short, but no Yuque URLs found in doc '{yuque_doc.title}'.")
                    else:
                        logger.info(
                            f"Header '{header}' not found in document outlines for '{yuque_doc.title}'. Returning full document content.")
                        # 如果指定了 header 但未找到匹配的节点，则返回整个文档内容
                        current_doc_content = full_doc_body
                else:
                    logger.info(
                        f"No outlines found for document '{yuque_doc.title}'. Returning full document content.")
                    # 如果文档没有大纲结构，则返回整个文档内容
                    current_doc_content = full_doc_body
            elif not full_doc_body:
                logger.warning(f"Document '{yuque_doc.title}' has an empty body.")
                current_doc_content = ""
            else:
                logger.info(
                    f"No header specified for document '{yuque_doc.title}' or header processing skipped. Returning full document content.")
            image_knowledge = await knowledge_retriever.aretrieve_with_scores(
                query=header, score_threshold=0.0, filters=filters
            )
            image_text = [image_chunk.content for image_chunk in
                          image_knowledge]
            current_doc_content += "\n相关图片语义:".join(image_text)
            all_processed_contents.append(current_doc_content)
            doc_titles.append(yuque_doc.title)

        return KnowledgeSearchResponse(document_contents=all_processed_contents,
                                       doc_titles=doc_titles)


    def get_yuque_doc_form_url(self, yuque_url: str, yuque_token: str):
        logger.info(
            f"get_yuque_doc_form_url yuque_url is {yuque_url}, yuque_token is {yuque_token}"
        )

        # check params
        if yuque_url is None:
            raise Exception("yuque url is None")
        if yuque_token is None:
            raise Exception("yuque token is None")
        if yuque_url.count("/") < 5:
            raise Exception(f"yuque url {yuque_url} is invalid")

        _, _, _, group, book_slug, doc_id = yuque_url.split("/", 5)
        web_reader = AntYuqueLoader(access_token=yuque_token)
        doc_detail = web_reader.single_doc(
            group=group, book_slug=book_slug, doc_id=doc_id
        )
        if doc_detail is None:
            raise Exception(f"document is None, check yuque url: {yuque_url}")
        logger.info(f"get_yuque_name_form_url document is {doc_detail.get('title')}")

        return doc_detail
