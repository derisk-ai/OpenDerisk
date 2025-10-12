import json
import logging
import re
import timeit
import uuid
from datetime import datetime
from typing import Dict, Iterator, List, Optional
from urllib.parse import unquote

import requests

from requests import HTTPError

from derisk.core import Document
from derisk.rag.knowledge.base import KnowledgeType
from derisk_serve.rag.api.schemas import CreateDocRequest, UpdateTocRequest, CreateBookRequest
from derisk_serve.rag.models.document_db import (
    KnowledgeDocumentDao,
    KnowledgeDocumentEntity,
)
from derisk_serve.rag.models.yuque_db import KnowledgeYuqueEntity, KnowledgeYuqueDao
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


knowledge_yuque_dao = KnowledgeYuqueDao()
knowledge_document_dao = KnowledgeDocumentDao()

ant_yuque_api_url = "https://yuque-api.antfin-inc.com"

API_GROUP_BOOK_DOCS_PATH = "/api/v2/repos/{group_login}/{book_slug}/docs"


class AntYuqueLoader:
    """Load documents from `ANt Yuque`."""

    def __init__(self, access_token: str):
        """Initialize with Yuque access_token and api_url.

        Args:
            access_token: group access token - see https://yuque.antfin-inc.com/lark/openapi/api
            api_url: Yuque API url.
        """
        self.access_token = access_token

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Auth-Token": self.access_token,
        }

    def get_user_id(self) -> int:
        try:
            url = f"{self.api_url}/api/v2/user"
            response = self.http_get(url=url)
            if response.status_code == 404:
                raise Exception("没有该知识库权限，请重新填写团队token")
        except HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except Exception as e:
            print(f"API failed! {str(e)}")

        return response["data"]["id"]

    def get_books(self, user_id: int) -> List[Dict]:
        try:
            url = f"{self.api_url}/api/v2/users/{user_id}/repos"
            response = self.http_get(url=url)
            if response.status_code == 404:
                raise Exception("没有该知识库权限，请重新填写团队token")
        except HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except Exception as e:
            print(f"API failed! {str(e)}")

        return response["data"]

    def get_document_ids(self, book_id: int) -> List[int]:
        try:
            url = f"{self.api_url}/api/v2/repos/{book_id}/docs"
            response = self.http_get(url=url)
            if response.status_code == 404:
                raise Exception("没有该知识库权限，请重新填写团队token")
        except HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except Exception as e:
            print(f"API failed! {str(e)}")

        return [document["id"] for document in response["data"]]

    def get_document(self, book_id: int, document_id: int) -> Dict:
        try:
            url = f"{self.api_url}/api/v2/repos/{book_id}/docs/{document_id}"
            response = self.http_get(url=url)
            if response.status_code == 404:
                raise Exception("没有该知识库权限，请重新填写团队token")
        except HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except Exception as e:
            print(f"API failed!{str(e)}")

        return response["data"]

    def get_book_slug_info(
        self, group_login: str, book_slug: str, yuque_token: str
    ) -> dict:
        logger.info(
            f"get_book_slug_info group_login is {group_login}, book_slug is {book_slug}, yuque_token is {yuque_token}"
        )

        path: str = f"/api/v2/repos/{group_login}/{book_slug}"
        headers = {"X-Auth-Token": yuque_token}
        response = requests.get(ant_yuque_api_url + path, headers=headers)
        logger.info(
            f"get_user_details_by_token: url is {ant_yuque_api_url + path}, headers is {headers}, response is {response}"
        )

        response.raise_for_status()
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")

        resp_json = json.loads(response.text)
        book_details = resp_json.get("data")

        return book_details

    def update_or_insert_knowledge_yuque(
        self, doc_id: str, knowledge_yuque: KnowledgeYuqueEntity
    ):
        # get yuque doc
        yuque_docs = knowledge_yuque_dao.get_knowledge_yuque(
            query=KnowledgeYuqueEntity(doc_id=doc_id)
        )

        if yuque_docs is None or len(yuque_docs) == 0:
            # insert knowledge_yuque table

            knowledge_yuque.yuque_id = str(uuid.uuid4())
            knowledge_yuque.doc_id = doc_id
            knowledge_yuque.doc_type = KnowledgeType.YUQUEURL.name

            docs = knowledge_document_dao.get_documents(
                query=KnowledgeDocumentEntity(doc_id=doc_id)
            )
            if docs is None or len(docs) == 0:
                raise Exception(f"not found doc by doc_id {doc_id}")

            knowledge_yuque.knowledge_id = docs[0].knowledge_id
            return knowledge_yuque_dao.create_knowledge_yuque(docs=[knowledge_yuque])
        else:
            # update knowledge_yuque table
            yuque_doc = yuque_docs[0]

            yuque_doc.title = knowledge_yuque.title
            yuque_doc.token = knowledge_yuque.token
            yuque_doc.group_login = knowledge_yuque.group_login
            yuque_doc.book_slug_name = knowledge_yuque.book_slug_name
            yuque_doc.book_slug = knowledge_yuque.book_slug
            yuque_doc.doc_slug = knowledge_yuque.doc_slug
            yuque_doc.doc_uuid = knowledge_yuque.doc_uuid
            yuque_doc.yuque_doc_id = knowledge_yuque.yuque_doc_id
            yuque_doc.word_cnt = knowledge_yuque.word_cnt
            yuque_doc.latest_version_id = knowledge_yuque.latest_version_id
            yuque_doc.gmt_modified = knowledge_yuque.gmt_modified
            yuque_doc.description = knowledge_yuque.description
            yuque_doc.created_at = knowledge_yuque.created_at
            yuque_doc.updated_at = knowledge_yuque.updated_at
            yuque_doc.cover = knowledge_yuque.cover
            yuque_doc.creator_login_name = knowledge_yuque.creator_login_name
            yuque_doc.avatar_url = knowledge_yuque.avatar_url
            yuque_doc.likes_count = knowledge_yuque.likes_count
            yuque_doc.read_count = knowledge_yuque.read_count
            yuque_doc.comments_count = knowledge_yuque.comments_count

            return knowledge_yuque_dao.update_knowledge_yuque(yuque_doc=yuque_doc)


    def parse_document_with_sheet(self, book: dict, yuque_url: str, yuque_token: str,  doc_id: str, doc_uuid: str)-> List[Document]:
        documents = []
        _, _, _, group_login, book_slug, doc_slug = yuque_url.split("/", 5)
        book_details = self.get_book_slug_info(
            group_login=group_login, book_slug=book_slug, yuque_token=yuque_token
        )
        book_slug_name = book_details.get("name") if book_details is not None else ""

        # 获取内容
        if 'body_sheet' not in book.keys():
            raise ValueError(f"find no body_sheet key in yuque api")
        content = book['body_sheet']
        content_json = json.loads(content)

        # 考虑多个sheet
        records = content_json['data']
        if records is None or len(records) != 1:
            raise ValueError(f"not support multiple sheet!")

        record = records[0]
        col_count = record['colCount']
        row_count = record['rowCount']
        sheet_name = record['name']
        tables = record['table']

        col_names = []
        for row in range(row_count):
            if row == 0:
                # 处理列名
                col_names = tables[row]
            else:
                # 处理内容：只保留value
                cell_content = tables[row] if tables[row] else []
                metadata = {
                    "title": book["title"],
                    "description": book["description"],
                    "created_at": book["created_at"],
                    "updated_at": book["updated_at"],
                    "yuque_url": yuque_url,
                    "group_login": group_login,
                    "book_slug": book_slug,
                    "book_slug_name": book_slug_name,
                    "row_index": row,
                    "sheet_name": sheet_name,
                    "type":"yuque_excel"
                }

                # 更新内容到metadata
                new_contents = []
                for col in range(col_count):
                    col_name = col_names[col]
                    col_value = cell_content[col] if col < len(cell_content) else ""

                    # 有合并单元格的情况
                    last_col_value = tables[row - 1][col] if row > 0 and col < len(cell_content) else ""
                    if col_name:
                        if col_value:
                            metadata[col_name] = col_value
                        elif last_col_value:
                            metadata[col_name] = last_col_value
                            tables[row][col] = last_col_value
                        else:
                            metadata[col_name] = col_value

                    new_content = f"\"{tables[0][col]}\":\"{tables[row][col]}\""
                    new_contents.append(new_content)

                cell_content = "\n".join(new_contents)
                documents.append(Document(content=cell_content, metadata=metadata))

                # 更新语雀表
                self.update_or_insert_knowledge_yuque(
                    doc_id=doc_id,
                    knowledge_yuque=KnowledgeYuqueEntity(
                        title=book["title"],
                        token=yuque_token,
                        group_login=group_login,
                        book_slug=book_slug,
                        book_slug_name=book_slug_name,
                        doc_slug=doc_slug,
                        doc_uuid=doc_uuid,
                        word_cnt=int(book["word_count"]),
                        latest_version_id=book["latest_version_id"]
                        if "latest_version_id" in book.keys()
                        else "not found latest_version_id key in yuque api",
                        gmt_modified=datetime.now(),
                    ),
                )

        return documents


    def parse_document(
        self,
        document: Dict,
        yuque_url: Optional[str] = None,
        yuque_token: Optional[str] = None,
        doc_id: Optional[str] = None,
        doc_uuid: Optional[str] = None,
    ) -> Document:
        if document['type'] == 'Doc':
            content = self.parse_document_body(document["body"])
        elif document['type'] == 'Sheet':
            # 兼容 sheet场景
            content = self.parse_document_body(document["body_sheet"])
        else:
            # 考虑其他情况
            content = self.parse_document_body(document["body"])
        _, _, _, group_login, book_slug, doc_slug = yuque_url.split("/", 5)
        book_details = self.get_book_slug_info(
            group_login=group_login, book_slug=book_slug, yuque_token=yuque_token
        )
        book_slug_name = book_details.get("name") if book_details is not None else ""
        metadata = {
            "title": document["title"],
            "description": document["description"],
            "created_at": document["created_at"],
            "updated_at": document["updated_at"],
            "yuque_url": yuque_url,
            "group_login": group_login,
            "book_slug": book_slug,
            "book_slug_name": book_slug_name,
        }

        self.update_or_insert_knowledge_yuque(
            doc_id=doc_id,
            knowledge_yuque=KnowledgeYuqueEntity(
                title=document["title"],
                token=yuque_token,
                group_login=group_login,
                book_slug=book_slug,
                book_slug_name=book_slug_name,
                doc_slug=doc_slug,
                doc_uuid=doc_uuid,
                yuque_doc_id=document["id"],
                word_cnt=int(document["word_count"]),
                latest_version_id=document["latest_version_id"]
                if "latest_version_id" in document.keys()
                else "not found latest_version_id key in yuque api",
                gmt_modified=datetime.now(),
                description=document["description"],
                created_at=document["created_at"],
                updated_at=document["updated_at"],
                cover=document["cover"],
                creator_login_name=document['creator'].get('login'),
                avatar_url=document['creator'].get('avatar_url'),
                likes_count=document['likes_count'],
                read_count=document['read_count'],
                comments_count=document['comments_count'],
            ),
        )

        return Document(content=content, metadata=metadata)

    @staticmethod
    def parse_document_body(body: str) -> str:
        result = re.sub(r'<a name="(.*)"></a>', "", body)
        result = re.sub(r"<br\s*/?>", "", result)
        soup = BeautifulSoup(result, 'html.parser')
        result = soup.get_text()
        return result

    def http_get(self, url: str) -> Dict:
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()

        return response.json()

    def get_documents(self) -> Iterator[Document]:
        user_id = self.get_user_id()
        books = self.get_books(user_id)

        for book in books:
            book_id = book["id"]
            document_ids = self.get_document_ids(book_id)
            for document_id in document_ids:
                document = self.get_document(book_id, document_id)
                parsed_document = self.parse_document(document)
                yield parsed_document

    def load(self) -> List[Document]:
        """Load documents from `Yuque`."""
        return list(self.get_documents())

    def get_uml_content_from_doc(self, doc: str):
        try:
            # 0.获取原始语雀lake内容
            body_lake = doc.get("body_lake")

            # 1.url编码格式解码
            body_lake = unquote(body_lake)

            # 2.找到card标签
            pattern = r'<card(.*?)></card>'
            cards = re.findall(pattern, body_lake)

            # 3.过滤uml卡片
            cards = [card for card in cards if 'name="diagram"' in card]
            logger.info(f"find card len is {len(cards)}")

            # 4.提取uml知识
            uml_data = []
            for card in cards:
                data = re.findall(r'value="data:({.+?})"', card)[0]
                json_data = json.loads(data)
                uml_data.append(json_data)
            logger.info(f"find uml_data len is {len(uml_data)}")

            return uml_data
        except Exception as e:
            logger.error(f"get_uml_content_from_doc error, error is {e}")

    def single_doc(self, group: str, book_slug: str, doc_id: str):
        logger.info(f"single_doc: group is {group}, book_slug is {book_slug}, doc_id is {doc_id}")

        path: str = f"/api/v2/repos/{group}/{book_slug}/docs/{doc_id}"
        headers = {"X-Auth-Token": self.access_token}
        response = requests.get(ant_yuque_api_url + path, headers=headers)
        response.raise_for_status()  # 如果请求返回一个错误状态码，则抛出HTTPError异常
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")

        resp_json = json.loads(response.text)
        doc_detail = resp_json.get("data")
        return doc_detail

    def get_user_details_by_token(self):
        path: str = f"/api/v2/user"
        headers = {"X-Auth-Token": self.access_token}
        response = requests.get(ant_yuque_api_url + path, headers=headers)
        logger.info(
            f"get_user_details_by_token: url is {ant_yuque_api_url + path}, headers is {headers}, response is {response}"
        )

        response.raise_for_status()
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")

        resp_json = json.loads(response.text)
        user_details = resp_json.get("data")

        return user_details

    def get_user_groups_by_token(self, user_id):
        path: str = f"/api/v2/users/{user_id}/groups"
        headers = {"X-Auth-Token": self.access_token}
        response = requests.get(ant_yuque_api_url + path, headers=headers)
        logger.info(
            f"get_user_groups_by_token: url is {ant_yuque_api_url + path}, headers is {headers}, response is {response}"
        )

        response.raise_for_status()
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")

        resp_json = json.loads(response.text)
        user_details = resp_json.get("data")

        return user_details

    def get_books_by_group_login(
        self, group_login: str, offset: int, page_size: 100, temp_books: []
    ):
        logger.info(
            f"get_books_by_group_login: group login is {group_login}, offset is {offset}, page_size is {page_size}, len of temp_books is {len(temp_books)}"
        )

        if group_login is None:
            raise Exception("group login is None")

        path: str = f"/api/v2/groups/{group_login}/repos?offset={offset}"
        headers = {"X-Auth-Token": self.access_token}
        response = requests.get(ant_yuque_api_url + path, headers=headers)
        logger.info(
            f"get_books_by_group_login: url is {ant_yuque_api_url + path}, headers is {headers}, response is {response}"
        )

        response.raise_for_status()
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")

        resp_json = json.loads(response.text)
        books = resp_json.get("data")
        all_books = temp_books + books

        if len(books) < page_size:
            logger.info(
                f"find the last page {len(books)}, {len(temp_books)}, {len(all_books)}"
            )

            return all_books
        else:
            logger.info(f"need to continue find books")

            offset += page_size
            return self.get_books_by_group_login(
                group_login, offset, page_size, all_books
            )

    def get_toc_by_group_login_and_book_slug(self, group_login: str, book_slug: str):
        logger.info(
            f"get_toc_by_group_login_and_book_slug: group login is {group_login}, book slug is {book_slug}"
        )

        path: str = f"/api/v2/repos/{group_login}/{book_slug}/toc"
        headers = {"X-Auth-Token": self.access_token}
        response = requests.get(ant_yuque_api_url + path, headers=headers)
        response.raise_for_status()
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")

        resp_json = json.loads(response.text)
        doc_toc = resp_json.get("data")
        logger.info(
            f"get_toc_by_group_login_and_book_slug: url is {ant_yuque_api_url + path}, headers is {headers}, response is {len(doc_toc)}"
        )

        return doc_toc


    def build_toc_tree(self, tocs: [], is_simple: bool = True):
        logger.info(f"build_toc_tree: tocs len is {len(tocs)}")

        roots = []
        if len(tocs) == 0:
            return roots

        # 构建节点字典
        if is_simple:
            node_dict = {node.get("uuid"): {"uuid": node.get("uuid"), "type": node.get("type"),
                                            "title": node.get("title"), "slug": node.get("slug"),
                                            "parent_uuid": node.get("parent_uuid"), "children": []} for node in tocs}
        else:
            node_dict = {node.get("uuid"): {**node, "children": []} for node in tocs}

        for node in node_dict.values():
            parent_uuid = node.get("parent_uuid")

            # 如果父节点存在，那么就挂靠到父节点下; 如果父节点不存在，直接添加到目录树roots
            if parent_uuid and parent_uuid in node_dict.keys():
                parent_node = node_dict.get(parent_uuid)
                parent_node.get("children").append(node)
            else:
                roots.append(node)
        logger.info(f"build_toc_tree: roots len is {len(roots)}")

        return roots

    def update_toc_by_group_login_and_book_slug(self, group_login: str, book_slug: str, update_toc_request: UpdateTocRequest):
        logger.info(f"update_toc_by_group_login_and_book_slug: group login is {group_login}, book slug is {book_slug}, update_toc_request is {update_toc_request}")

        path: str = f"/api/v2/repos/{group_login}/{book_slug}/toc"
        headers = {"X-Auth-Token": self.access_token}
        response = requests.put(ant_yuque_api_url + path, headers=headers, json=update_toc_request.dict())
        response.raise_for_status()
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")

        resp_json = json.loads(response.text)
        doc_toc = resp_json.get("data")
        logger.info(
            f"update_toc_by_group_login_and_book_slug: url is {ant_yuque_api_url + path}, headers is {headers}, response is {len(doc_toc)}"
        )

        return doc_toc

    def get_outlines_from_body(self, body: str):
        try:
            # 匹配代码块（使用 ``` 或者 ~~~ 包围的文本）
            code_block_regex = re.compile(r"(```.*?```|~~~.*?~~~)", re.DOTALL)
            # 首先，替换所有代码块为占位符
            body = code_block_regex.sub("", body)
            # # 再次，替换所有代码块为占位符
            # body = code_block_regex.sub("```", body)
            # # 最终，替换所有代码块为占位符
            # body = code_block_regex.sub("", body)

            # Regular expression to find headers and their levels
            header_regex = re.compile(r"^(#+)\s+(.*)", re.MULTILINE)

            # Find all headers in the body
            headers = header_regex.findall(body)

            # Function to insert headers into a hierarchy
            def insert_headers(headers):
                hierarchy = {}
                stack = [(hierarchy, 0)]  # Stack to manage hierarchy and levels

                for level_symbols, title in headers:
                    level = len(
                        level_symbols
                    )  # Number of '#' indicates the header level

                    # Manage hierarchy stack based on level
                    while stack and stack[-1][1] >= level:
                        stack.pop()

                    current_level = stack[-1][0]
                    current_level[title] = {}
                    stack.append((current_level[title], level))

                return hierarchy

            def clean_html_tags(data):
                if not isinstance(data, dict):
                    return data
                cleaned = {}
                for key, value in data.items():
                    # 去除当前键中的HTML标签
                    new_key = re.sub(r'<.*?>', '', key)
                    # 递归处理子字典
                    cleaned[new_key] = clean_html_tags(value)
                return cleaned

            outlines = insert_headers(headers)

            return clean_html_tags(outlines)
        except Exception as e:
            logger.error(f"get_outlines_from_body error: {str(e)}")

            return []

    def get_outlines_by_group_book_slug(
        self, group_login: str, book_slug: str, doc_slug: str
    ):
        start_time = timeit.default_timer()
        logger.info(
            f"get_outlines_by_group_book_slug: group login is {group_login}, book slug is {book_slug}, doc slug is {doc_slug}"
        )

        path: str = f"/api/v2/repos/{group_login}/{book_slug}/docs/{doc_slug}"
        headers = {"X-Auth-Token": self.access_token}
        response = requests.get(ant_yuque_api_url + path, headers=headers)
        response.raise_for_status()
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")
        resp_json = json.loads(response.text)
        data = resp_json.get("data")
        if data is None or not data.get("body"):
            logger.info(
                f"get_outlines_by_group_book_slug body is None: {group_login}, {book_slug}, {doc_slug}"
            )

            return {}

        outlines = self.get_outlines_from_body(data.get("body"))
        cost_time = round(timeit.default_timer() - start_time, 2)
        logger.info(
            f"get_outlines_by_group_book_slug: url is {ant_yuque_api_url + path}, headers is {headers}, "
            f"outlines is {outlines}, cost time is {cost_time}"
        )

        return outlines

    def update_yuque_doc(self, group_login: str, book_slug: str, doc_id: str, update_doc_request: CreateDocRequest):
        logger.info(f"update_yuque_doc: group login is {group_login}, book slug is {book_slug}, doc id is {doc_id}, update_doc_request is {update_doc_request}")

        path: str = f"/api/v2/repos/{group_login}/{book_slug}/docs/{doc_id}"
        headers = {"X-Auth-Token": self.access_token}
        response = requests.put(ant_yuque_api_url + path, json=update_doc_request.dict(), headers=headers)
        response.raise_for_status()
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")
        resp_json = json.loads(response.text)
        data = resp_json.get("data")
        logger.info(f"update_yuque_doc: url is {ant_yuque_api_url + path}, headers is {headers}, data title is {data.get('title')}")

        return data


    def create_doc_by_group_book_slug(
        self, group_login: str, book_slug: str, create_doc_request: CreateDocRequest,
    ):
        """注意: 创建文档后不会自动添加到目录，需要调用"知识库目录更新接口"更新到目录中"""
        start_time = timeit.default_timer()
        logger.info(f"create_doc_by_group_book_slug: group login is {group_login}, book slug is {book_slug}")

        if not group_login or not book_slug or not create_doc_request:
            raise Exception("group login or book slug or create_doc_request is None")
        if not create_doc_request.slug or not create_doc_request.title or not create_doc_request.body:
            raise Exception("create_doc_request content is None")

        path: str = f"/api/v2/repos/{group_login}/{book_slug}/docs"
        headers = {"X-Auth-Token": self.access_token}
        response = requests.post(ant_yuque_api_url + path, json=create_doc_request.dict(), headers=headers)
        response.raise_for_status()
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")
        resp_json = json.loads(response.text)
        data = resp_json.get("data")

        cost_time = round(timeit.default_timer() - start_time, 2)
        logger.info(f"create_doc_by_group_book_slug: url is {ant_yuque_api_url + path}, headers is {headers}, data is {data.get('id')}, cost time is {cost_time}")

        return data


    def get_docs_by_group_book_slug(self, group_login: str, book_slug: str):
        start_time = timeit.default_timer()
        logger.info(f"get_docs_by_group_book_slug: group login is {group_login}, book slug is {book_slug}")

        path: str = API_GROUP_BOOK_DOCS_PATH.format(group_login=group_login, book_slug=book_slug)
        headers = {"X-Auth-Token": self.access_token}
        response = requests.get(ant_yuque_api_url + path, headers=headers)
        response.raise_for_status()
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")
        resp_json = json.loads(response.text)
        data = resp_json.get("data")

        cost_time = round(timeit.default_timer() - start_time, 2)
        logger.info(f"create_doc_by_group_book_slug: url is {ant_yuque_api_url + path}, headers is {headers}, cost time is {cost_time}")

        return data


    def create_book(self, group_login: str, create_book_request: CreateBookRequest):
        path: str = f"/api/v2/groups/{group_login}/repos"
        headers = {"X-Auth-Token": self.access_token}
        response = requests.post(ant_yuque_api_url + path, json=create_book_request.dict(), headers=headers)
        response.raise_for_status()
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")
        resp_json = json.loads(response.text)
        data = resp_json.get("data")
        logger.info(f"create_book: url is {ant_yuque_api_url + path}, headers is {headers}")

        return data


    def delete_doc(self, group_login: str, book_slug: str, doc_id: str):
        path: str = f"/api/v2/repos/{group_login}/{book_slug}/docs/{doc_id}"
        headers = {"X-Auth-Token": self.access_token}
        response = requests.delete(ant_yuque_api_url + path, headers=headers)
        response.raise_for_status()
        if (response.status_code == 404) or (response.status_code == 401):
            raise Exception("没有该知识库权限，请重新填写团队token")

        resp_json = json.loads(response.text)
        data = resp_json.get("data")
        logger.info(f"delete_doc: url is {ant_yuque_api_url + path}, headers is {headers}")

        return data
