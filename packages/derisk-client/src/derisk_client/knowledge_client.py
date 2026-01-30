import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, List, Union, Dict, Any

import requests
from dateutil import parser
from pydantic import BaseModel

from derisk_client.schema import BaseAssetModel


class KnowledgeModel(BaseAssetModel):
    knowledge_base_id: str
    knowledge_base_name: str
    category: str
    knowledge_base_desc: Optional[str] = None
    creator: Optional[str] = None
    tags: Optional[List[str]] = None
    storage_type: Optional[str] = None
    knowledge_type: Optional[str] = "document"


class DocumentModel(BaseModel):
    document_name: str
    document_id: str
    document_content: str
    document_desc: str
    document_tags: Optional[List[str]] = None
    document_type: str
    document_create_at: Optional[Union[datetime, str]] = None
    document_update_at: Optional[Union[datetime, str]] = None
    word_count: Optional[int] = None
    read_count: Optional[int] = None
    like_count: Optional[int] = None
    creator: Optional[str] = None
    avatar_url: Optional[str] = None
    document_cover: Optional[str] = None
    document_link: Optional[str] = None

class KnowledgeClient:
    """
    A client for interacting with the Alipay Knowledge Base API.
    """

    def __init__(self,
                 nex_client_id: Optional[str] = None,
                 nex_token: Optional[str] = None,
                 deriskcore_prod_base_url: str = "",
                 # deriskcore_prod_base_url: str = "http://localhost:8080",
                 nexa_api_pre_base_url: str = "https://nexa-api-pre.alipay.com",
                 cookie_header: str = None,
                 iam_token_header: str = None):
        """
        Initializes the KnowledgeClient.

        Args:
            nex_client_id: The client ID for NEX-related API calls.
            nex_token: The NEX token for NEX-related API calls.
            deriskcore_prod_base_url: Base URL for production deriskcore APIs.
            nexa_api_pre_base_url: Base URL for pre-release nexa-api APIs.
            deriskcore_pre_base_url: Base URL for pre-release deriskcore APIs.
            cookie_header: The full Cookie header string, used for certain APIs.
            iam_token_header: The IAM_TOKEN string, used for certain APIs.
        """
        self.nex_client_id = nex_client_id
        self.nex_token = nex_token
        self.deriskcore_prod_base_url = deriskcore_prod_base_url
        self.nexa_api_pre_base_url = nexa_api_pre_base_url

        self.cookie_header = cookie_header
        self.iam_token_header = iam_token_header

    def _get_default_nex_headers(self) -> dict:
        """Returns the common headers for NEX-authenticated calls."""
        return {
            "Content-Type": "application/json",
            "NEX-CLIENT-ID": self.nex_client_id,
            "NEX-TOKEN": self.nex_token,
        }

    def _get_cookie_iam_headers(self) -> dict:
        """
        Returns headers including Cookie and IAM_TOKEN for specific API calls.
        Note: These tokens are very long and are likely session-specific.
              Passing them dynamically is crucial for a production client.
        """
        headers = {
            "Content-Type": "application/json",
        }
        if self.cookie_header:
            headers["Cookie"] = self.cookie_header
        if self.iam_token_header:
            headers["IAM_TOKEN"] = self.iam_token_header
        return headers

    def get_knowledges(self) -> dict:
        """
        Retrieves a list of knowledge spaces.

        Returns:
            A dictionary containing the JSON response from the API.
        """
        url = f"{self.deriskcore_prod_base_url}/openapi/v1/knowledge/spaces"
        headers = self._get_default_nex_headers()
        response = requests.get(url, headers=headers, params={
            "page": 1, "page_size": 10000, "is_public": True}
        )
        response.raise_for_status() # Raise an exception for HTTP errors
        data = response.json()
        return self.parse_knowledge_api_response(data)

    def get_kgs(self) -> dict:
        """
        Retrieves a list of knowledge spaces.

        Returns:
            A dictionary containing the JSON response from the API.
        """
        url = f"{self.deriskcore_prod_base_url}/openapi/v1/knowledge/spaces"
        headers = self._get_default_nex_headers()
        response = requests.get(url, headers=headers, params={
            "page": 1, "page_size": 10000, "is_public": True}
                                )
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()
        return self.parse_knowledge_api_response(data, is_kg=True)


    def parse_knowledge_api_response(self,api_response: Dict[str, Any], is_kg: Optional[bool] = False) -> List[
        KnowledgeModel]:
        """
        Parses the raw API response for knowledge spaces into a list of KnowledgeModel objects.

        Args:
            api_response: The dictionary received from the knowledge spaces API.

        Returns:
            A list of KnowledgeModel objects, or an empty list if parsing fails
            or no items are found.
        """
        knowledge_models: List[KnowledgeModel] = []

        if not api_response.get('success'):
            print(f"API response indicates failure: {api_response.get('err_msg')}")
            return []

        data = api_response.get('data')
        if not data or not isinstance(data, dict):
            print("API response 'data' field is missing or malformed.")
            return []

        items = data.get('items')
        if not items or not isinstance(items, list):
            print("API response 'data.items' field is missing or malformed.")
            return []

        for item in items:
            is_public = item.get('knowledge_type')
            if is_public != 'PUBLIC':
                continue
            category = item.get('category')

            model_owner = None
            if item.get('owner') is not None and item.get('owner') != "":
                model_owner = [item['owner']]

            model_tags = None
            raw_tags = item.get('tags')
            if isinstance(raw_tags, str) and raw_tags.lower() != 'null':
                model_tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
                if not model_tags:
                    model_tags = None
            elif isinstance(raw_tags, list):
                model_tags = raw_tags
            knowledge_type = "document"
            if is_kg:
                knowledge_type = "kg"
                if item.get('storage_type') != "AKG":
                    continue
            try:
                knowledge_models.append(KnowledgeModel(
                    category=category,
                    asset_type='knowledge',
                    knowledge_base_id=item.get('knowledge_id'),
                    knowledge_base_name=item.get('name'),
                    knowledge_base_desc=item.get('desc'),
                    creator=item.get('owner'),
                    knowledge_type=knowledge_type,
                    tags=model_tags or [],
                    create_time=item.get('gmt_create') or datetime.now(),
                    update_time=item.get('gmt_modified') or datetime.now(),
                ))
            except Exception as e:
                print(
                    f"Failed to parse item (ID: {item.get('id')}, Name: {item.get('name')}): {e}")

        return knowledge_models

    def create_document(self, content: str, doc_name: str) -> dict:
        """
        Creates a new text document in a specific knowledge space (hardcoded ID 19000001).

        Args:
            content: The text content of the document.
            doc_name: The name of the document.

        Returns:
            A dictionary containing the JSON response from the API.
        """
        # Note: The knowledge ID 19000001 is hardcoded in the original URL.
        # It might be better to pass this as a parameter if it varies.
        url = f"{self.nexa_api_pre_base_url}/openapi/v1/knowledge/19000001/documents/create-text"
        headers = self._get_default_nex_headers()
        data = {
            "content": content,
            "docName": doc_name,
            "docType": "TEXT",
            "chunkParameter": {"chunkStrategy": "NO_CHUNK"},
        }
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()

    def get_documents(self, knowledge_id: str) -> List[DocumentModel]:
        """
        Retrieves documents from a specified knowledge space.

        Args:
            knowledge_id: The ID of the knowledge space.

        Returns:
            A dictionary containing the JSON response from the API.
        """
        url = f"{self.deriskcore_prod_base_url}/openapi/v1/knowledge/spaces/{knowledge_id}/documents"
        headers = self._get_cookie_iam_headers()
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        result = response.json()
        doc_models = []
        max_workers = 10  # 允许最多10个线程同时处理文档
        documents_data = result.get("data")
        if not documents_data:
            print("No documents found for the given knowledge_id.")
            return []
        # 使用 ThreadPoolExecutor 进行并发处理
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._process_single_document, data_item,
                                knowledge_id): data_item
                for data_item in documents_data
            }

            for future in as_completed(futures):
                # original_data_item = futures[future] # 如果需要访问原始数据来记录错误
                try:
                    doc_model = future.result()  # 获取线程执行的结果
                    if doc_model:  # 只有当文档成功处理并返回 DocumentModel 时才添加
                        doc_models.append(doc_model)
                except Exception as exc:
                    # 这会捕获 _process_single_document 中未捕获的任何异常
                    # 但我们已经在 _process_single_document 中做了异常处理，所以这里可能不需要
                    # 除非 _process_single_document 返回 None 后，你还想做更高级的错误处理
                    print(f"A task generated an unhandled exception: {exc}")
                    # 可以在这里记录哪个文档导致了问题，例如：
                    # errored_data = futures[future]
                    # print(f"Error processing document {errored_data.get('id')}")

        return doc_models
        # if result.get("data"):
        #     for i, data in enumerate(result.get("data")):
        #         doc_id = data.get('id')
        #         document_name = data.get('doc_name').rsplit('_', 1)[0]
        #         chunks = self.get_chunks(knowledge_id,
        #                                  space_name=data.get('space'),
        #                                  doc_id=doc_id)
        #         document_content = ""
        #         for chunk in chunks:
        #             document_content +=chunk.get("content")
        #         from examples.client.yuque import YuqueClient
        #         if data.get('doc_type') == "YUQUEURL":
        #             client = YuqueClient(auth_token= data.get('doc_token'))
        #             yuque_url = data.get('content')
        #             group, book, doc_id = (
        #                 yuque_url.split("/")[-3],
        #                 data.get('content').split("/")[-2],
        #                 data.get('content').split("/")[-1]
        #             )
        #             yuque_data = client.get_yuque_document_content(group, book, doc_id)
        #             doc_model = DocumentModel(
        #                 document_name=document_name,
        #                 document_id=data.get('doc_id'),
        #                 document_link=data.get('content'),
        #                 document_content=document_content,
        #                 document_tags=data.get('tags'),
        #                 document_type="yuque" if data.get(
        #                     'doc_type'
        #                 ) == "YUQUEURL" else data.get('doc_type').lower(),
        #                 document_cover=yuque_data.get('cover') if yuque_data else None,
        #                 document_desc=yuque_data.get('description')if yuque_data else None,
        #                 word_count=yuque_data.get('word_count')if yuque_data else None,
        #                 creator=yuque_data.get('creator')if yuque_data else None,
        #                 read_count=yuque_data.get('read_count')if yuque_data else None,
        #                 like_count=yuque_data.get('like_count')if yuque_data else None,
        #                 document_create_at= parser.parse(timestr=yuque_data.get('created_at')).strftime('%Y-%m-%d %H:%M:%S') if yuque_data else None,
        #                 document_update_at=parser.parse(yuque_data.get('updated_at')).strftime('%Y-%m-%d %H:%M:%S') if yuque_data else None,
        #                 avatar_url=yuque_data.get('avatar_url')if yuque_data else None,
        #             )
        #         else:
        #             doc_model = DocumentModel(
        #                 document_name=document_name,
        #                 document_id=data.get('doc_id'),
        #                 document_link=data.get('content'),
        #                 document_content=document_content,
        #                 document_type= data.get('doc_type').lower(),
        #             )
        #         doc_models.append(doc_model)


        # return doc_models

    def _process_single_document(self, data: Dict, knowledge_id: str) -> Optional[
        DocumentModel]:
        """
        Helper method to process a single document data item.
        This method will be executed by the thread pool.
        """
        try:
            doc_id = data.get('id')
            if not doc_id:
                print(f"Skipping document due to missing 'id' in data: {data}")
                return None

            document_name_raw = data.get('doc_name', '')
            document_name = document_name_raw.rsplit('_', 1)[
                0] if '_' in document_name_raw else document_name_raw

            chunks = self.get_chunks(knowledge_id, space_name=data.get('space'),
                                     doc_id=doc_id)
            document_content = "".join(chunk.get("content", "") for chunk in chunks if
                                       chunk and chunk.get("content"))

            doc_type = data.get('doc_type', '').lower()

            doc_model: Optional[DocumentModel] = None  # 初始化为None

            if doc_type == "yuqueurl":
                from examples.client.yuque import YuqueClient
                yuque_client = YuqueClient(auth_token=data.get('doc_token'))
                yuque_url = data.get('content')

                yuque_path_parts = yuque_url.strip('/').split("/")
                group = yuque_path_parts[-3] if len(yuque_path_parts) >= 3 else None
                book = yuque_path_parts[-2] if len(yuque_path_parts) >= 2 else None
                doc_id_yuque = yuque_path_parts[-1] if len(
                    yuque_path_parts) >= 1 else None

                yuque_data = None
                try:
                    if not all([group, book, doc_id_yuque]):
                        print(
                            f"Warning: Could not parse Yuque URL parts for {yuque_url}. Skipping Yuque data fetching.")
                        yuque_data = None
                    else:
                        yuque_data = yuque_client.get_yuque_document_content(group, book,
                                                                         doc_id_yuque)
                except Exception as e:
                    print(
                        f"Error fetching Yuque data for {yuque_url}: {e}")
                doc_model = DocumentModel(
                    document_name=document_name,
                    document_id=data.get('doc_id'),
                    document_link=data.get('content'),
                    document_content=document_content,
                    document_tags=data.get('tags'),
                    document_type="yuque",
                    document_cover=yuque_data.get('cover') if yuque_data else "",
                    document_desc=yuque_data.get('description') if yuque_data else "",
                    word_count=yuque_data.get('word_count') if yuque_data else 0,
                    creator=yuque_data.get('creator') if yuque_data else None,
                    read_count=yuque_data.get('read_count') if yuque_data else 0,
                    like_count=yuque_data.get('like_count') if yuque_data else 0,
                    document_create_at=parser.parse(
                        timestr=yuque_data.get('created_at')).strftime(
                        '%Y-%m-%d %H:%M:%S') if yuque_data and yuque_data.get(
                        'created_at') else None,
                    document_update_at=parser.parse(
                        timestr=yuque_data.get('updated_at')).strftime(
                        '%Y-%m-%d %H:%M:%S') if yuque_data and yuque_data.get(
                        'updated_at') else None,
                    avatar_url=yuque_data.get('avatar_url') if yuque_data else "",
                )
            else:
                doc_model = DocumentModel(
                    document_name=document_name,
                    document_id=data.get('doc_id'),
                    document_link=data.get('content'),
                    document_content=document_content,
                    document_type=doc_type,
                    document_tags=data.get('tags'),
                    document_cover=None,
                    document_desc="",
                    word_count=None,
                    creator=None,
                    read_count=None,
                    like_count=None,
                    document_create_at=None,
                    document_update_at=None,
                    avatar_url=None,
                )
            return doc_model
        except Exception as e:
            print(f"Error processing document {data.get('id', 'N/A')}: {e}")
            # import traceback
            # traceback.print_exc()
            return None

    def get_chunks(self,
                   knowledge_id: str,
                   space_name: Optional[str] = None,
                   doc_id: Optional[str] = None,
                   doc_name: Optional[str] = None):
        """
        Retrieves documents from a specified knowledge space.

        Args:
            knowledge_id: The ID of the knowledge space.

        Returns:
            A dictionary containing the JSON response from the API.
        """
        url = f"{self.deriskcore_prod_base_url}/knowledge/{space_name}/chunk/list"
        headers = self._get_cookie_iam_headers()
        response = requests.post(url, headers=headers, json={
            "document_id": doc_id,
            "page": 1,
            "page_size": 1000,
        }
        )
        response.raise_for_status()
        return response.json().get("data").get("data")

    def get_yuque(self, doc_id: str) -> dict:
        """
        Retrieves documents from a specified knowledge space.

        Args:
            knowledge_id: The ID of the knowledge space.

        Returns:
            A dictionary containing the JSON response from the API.
        """
        url = f"{self.deriskcore_prod_base_url}/openapi/v1/knowledge/spaces/{knowledge_id}/documents"
        headers = self._get_cookie_iam_headers()
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_documents_v2(self) -> dict:
        """
        Retrieves Yuque documents using a specific, hardcoded URL with query parameters.

        Note: This URL and its parameters are very specific and hardcoded in the original.
              It implies a direct integration with a Yuque-like system,
              and might not be a general API endpoint.

        Returns:
            A dictionary containing the JSON response from the API.
        """
        url = (f"{self.nexa_api_pre_base_url}/api/yuque/docs?"
               "ctoken=w1at7bUaQNK1qe1p&bookSlug=hdvygy&groupLogin=yvk07c&knowledgeBaseId=20400003")
        headers = self._get_cookie_iam_headers()
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def update_document(self, knowledge_id: str, document_id: str, data: dict) -> dict:
        """
        Updates a specific document within a knowledge space.

        Args:
            knowledge_id: The ID of the knowledge space.
            document_id: The ID of the document to update.
            data: A dictionary containing the update payload (e.g., {"meta_data": {"year": "2023"}}).

        Returns:
            A dictionary containing the JSON response from the API.
        """
        url = f"{self.deriskcore_pre_base_url}/openapi/v1/knowledge/spaces/{knowledge_id}/documents/{document_id}"
        # When `json=data` is used with requests.put, Content-Type is typically set automatically.
        # If specific headers from _get_cookie_iam_headers() are needed beyond Content-Type,
        # they should be explicitly merged or passed. For now, assuming basic JSON PUT.
        # Original code commented out these headers for PUT, so sticking to that.
        response = requests.put(url=url, json=data)
        response.raise_for_status()
        return response.json()

# --- Helper function (remains outside the class as it's a general utility) ---
def extract_year(text: str) -> str | None:
    """
    Extracts a four-digit year or 'CY' followed by two digits from the start of a string.

    Args:
        text: The string to search within.

    Returns:
        The extracted year string (e.g., "2023", "CY23") or None if no match.
    """
    pattern = r'^(\d{4}|CY\d{2})'
    match = re.match(pattern, text)
    if match:
        return match.group(1)
    return None

# --- Example Usage (main function refactored to use the class) ---
def main():
    # Placeholder values for NEX_CLIENT_ID and NEX_TOKEN
    # Replace with your actual credentials
    # NEX_CLIENT_ID = "SMARTUNITMNG"
    # NEX_TOKEN = "bd8c683a-29a4-8e41-f696-4a0914a84667"

    # The long Cookie and IAM_TOKEN headers from your original code.
    # These are highly specific and likely session-dependent.
    # In a real application, you'd obtain these via an authentication flow.
    # For demonstration, copying them directly.
    # VERY_LONG_COOKIE = (
    #     "receive-cookie-deprecation=1; cna=NJeUIE5NSj0CATtSWYU3443B; antLoginLang=zh_CN; "
    #     "buservice_domain_id=KOUBEI_SALESCRM; tenant=alipay; ordv=1s9g948CBw..; "
    #     "A3_USER_COOKIE=a90a8adb7c934cf39f501a36c6ee3f08f7589a8ea6ae7e0be5cbbd3ae2eb0f4334472874cbf65e7377011c01346333afaed9108d6a1ecf4dfa0d009ad10972fee9879499176a63a73716e7fa43fcf9857fdb3dfe5125a24747935dae9c9f64f52a70d2688d6d10a489614269bdbded6927cf6222a7063cb6dd0e3d60f7b58895f8558f86ad1b923bfd07260d15b60ad35f81ef0a671d75c0ed7e9606ef69a95102755bcb043790cca9bf08061e9de375a3c7bac76ce54848f403e430c0f921580596976e8c04a576c198a584b737747a87df12b01afa78e45fc28af443c07bb563030ebeb78bc61979dfa19edb6e6e3ab09c1dbcb123f4d4098464843be9e648c4a358ccfae6c62fe721e04772906f769b2cefaad8717b9c5811c3a38c8dca2635b2c14281f7bca20459c99a42c985209a6073e4bacf7e0079f24d241afa575509ee1ddb4631d64c28afabaeae51d52c; IAM_TOKEN=eyJraWQiOiJkZWZhdWx0IiwidHlwIjoiSldUIiwiYWxnIjoiUlMyNTYifQ.eyJjbmwiOiJCVUMiLCJzdWIiOiJjaGVua2V0aW5nLmNrdCIsImF1dGhfdHAiOlsiWkZBUkIiXSwiaXNzIjoiYnVtbmcuYWxpcGF5LmNvbSIsIm5vbmNlIjoiNGNkMzliNWIiLCJzaWQiOiIzNjg0MDczIiwiYXVkIjoiKiIsIm5iZiI6MTc0Nzk4MDU3Miwic25vIjoiMzM5Nzc3IiwidG50X2lkIjoiQUxJUFczQ04iLCJuYW1lIjoi5p-v5bu3IiwiZXhwIjoxNzQ4MDY3MDkyLCJpYXQiOjE3NDc5ODA2OTIsImp0aSI6IjM1NmE2YWYxMzQyNDRkNjZhNjdkOGNiYzQ5M2Q0MzgwIn0.ERRU4qYAvNhiEDhBegcdTV8Ig01xDXFydx4UIxcIXes2Aq-08Ih9ckTj2cxn-b7_7kYPSMBNJvItGYhdDXo-Eg; antcode_user_extern_no=339777; ALIPAYJSESSIONID=GZ0021EF8F58F8734683ACE727C90888A93CkujutaGZ00; zone=GZ00F; __TRACERT_COOKIE_bucUserId=339777; ALIPAYBUMNGJSESSIONID=GZ007B2WEAzJqozai9Ub2ENd09NsiLantbuserviceGZ00; ctoken=S3crxZo-5pcJAg9H; session.cookieNameId=ALIPAYBUMNGJSESSIONID; userId=339777; rtk=aZOc3gApUoocpCO15yl6jfj48JFcTGP2cQ5PVc83r8LWlfkc5yR; tfstk=g0PiqHMsdDt5FvIKpWG1EFgIkPXdyfGxghrxDmUq0VmIbxQ6MW44ouDV5oeTuj4tv5nTWfo0mk4jXjQs_mz4Dowtbxka8yujumuq_OtDik4zmx_sDmo0DryOJ_C85PGjg-jRw_dtnHFUjKl2_ZkEr4bK7ZBWP0hjggIppIk1ZjZZ0GA47y7nkqK2booZYDoIrmo40ckeY40Sgjrq32oEPV-23qJwTw0jYmlqgozF-qnE0Awyg0V4OWSBDUct0P86AVki4PoHZyNn7ZolNcA2gW23M0zaKIR4tVDaG6M73Rl4QPEneRjksYaaFogzbhSmcW4U_8rF9Cc088PmTWSeJcy7-ScT_ZCZa8Z3iYllHNMaoJqj6W72Q0yTXxFsKH7ic5EgiANP2BiaKWNm6JIMwmM4p5M76MRia8at6-rPvdnaEqSyopJzacOj8ZFehKMZR2m8O25G_X-9Bnbh-L6sQ2gO2wbHhs-WgQjR-wvr0AuIW0C..; isg=BPn5SMpatdhYkmGD6JZoQZ16CGPTBu24JYk3axsu3CCfoh00Y1SiiW46IKZUJYXw; BUSERVICE_SSO_V2=A1AC31D1C5E10AA332FAAA34CE71EDB9E80AE64F3D66CF7D9D02682E290498C141C2340DBA5DC94D7C4CCCC64FFA41B8; spanner=7xe1pCiD2fiN2bxWf2KfwQe0wG2wlGblXt2T4qEYgj0="
    # )
    # VERY_LONG_IAM_TOKEN = (
    #     "eyJraWQiOiJkZWZhdWx0IiwidHlwIjoiSldUIiwiYWxnIjoiUlMyNTYifQ.eyJjbmwiOiJCVUMiLCJzdWIiOiJjaGVua2"
    #     "V0aW5nLmNrdCIsImF1dGhfdHAiOlsiWkZBUkIiXSwiaXNzIjoiYnVtbmcuYWxpcGF5LmNvbSIsIm5vbmNlIjoiODFkOGU5"
    #     "MDAiLCJzaWQiOiIzNjg0MDczIiwiYXVkIjoiKiIsIm5iZiI6MTc1MDAzNzg5Mywic25vIjoiMzM5Nzc3IiwidG50X2lkIj"
    #     "oiQUxJUFczQ04iLCJuYW1lIjoi5p-v5bu3IiwiZXhwIjoxNzUwMTI0NDEzLCJpYXQiOjE3NTAwMzgwMTMsImp0aSI6IjFi"
    #     "MzEwZjE3NWY4ZjQzNjE4NzE4OGYzYTczNzhhZmZiIn0.m5lHs02ceep4xjZKBgH1mMnmTcBlyjC9YB5C69zHhLNjucsfpn"
    #     "rPvcJ0n5YeLEQfurVNdhBJfl_HtRymJgplow"
    # )

    client = KnowledgeClient()

    # Example: Get all knowledge spaces
    try:
        # knowledge_spaces = client.get_knowledges()
        # print("Knowledge Spaces:", knowledge_spaces)
        pass # Commenting out to focus on the main task
    except requests.exceptions.RequestException as e:
        print(f"Error getting knowledge spaces: {e}")

    knowledge_id = "1978422c-f8cc-4423-b54a-1078908239d7"

    try:
        # Using the get_documents method to retrieve documents from a specific knowledge space
        documents_v2 = client.get_documents(knowledge_id)

        if documents_v2 and documents_v2.get("success"):
            for doc in documents_v2.get("data", []):
                doc_id = doc.get("doc_id")
                doc_name = doc.get("doc_name")
                # Check if doc_id and doc_name exist,
                # if a year can be extracted, and if meta_data is not already present.
                if doc_id and doc_name and extract_year(doc_name) and not doc.get("meta_data"):
                    year_value = extract_year(doc_name)
                    metadata = {"meta_data": {"year": year_value}}

                    try:
                        result = client.update_document(knowledge_id, doc_id, metadata)
                        print(f"Update document '{doc_name}' (ID: {doc_id}): Success={result.get('success')}, Message={result.get('message')}, Data={metadata}")
                    except requests.exceptions.RequestException as e:
                        print(f"Error updating document '{doc_name}' (ID: {doc_id}): {e}")
                else:
                    # Optional: Print why a document was skipped
                    # print(f"Skipping document '{doc_name}' (ID: {doc_id}): "
                    #       f"Year: {extract_year(doc_name)}, Has meta_data: {bool(doc.get('meta_data'))}")
                    pass
        else:
            print(f"Failed to retrieve documents for knowledge_id '{knowledge_id}': {documents_v2}")

    except requests.exceptions.RequestException as e:
        print(f"Error retrieving documents for knowledge_id '{knowledge_id}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    client = KnowledgeClient()
    knowledges = client.get_knowledges()
    print(knowledges)
    # main()
