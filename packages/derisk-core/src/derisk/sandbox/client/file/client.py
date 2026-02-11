import logging
import os
import posixpath
from typing import Union, IO, Optional, Literal, List

from .types import EntryInfo, FileInfo, OSSFile, TaskResult
from ..base import BaseClient
from ...connection_config import Username
from ...utils.oss_utils import OSSUtils

## TODO
DEFAULT_OSS_AK = os.getenv("OSS_AK")
DEFAULT_OSS_SK = os.getenv("OSS_SK")
DEFAULT_OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "")
DEFAULT_OSS_BUCKET_NAME = os.getenv("OSS_BUCKET_NAME")
logger = logging.Logger(__name__)


class FileClient(BaseClient):

    def __init__(self, sandbox_id: str, work_dir: str, **kwargs):
        super().__init__(**kwargs)
        self._sandbox_id = sandbox_id
        self._work_dir = work_dir
        oss_ak = kwargs.get("oss_ak", DEFAULT_OSS_AK)
        oss_sk = kwargs.get("oss_sk", DEFAULT_OSS_SK)
        oss_endpoint = kwargs.get("oss_endpoint", DEFAULT_OSS_ENDPOINT)
        oss_bucket_name = kwargs.get("oss_bucket_name", DEFAULT_OSS_BUCKET_NAME)
        self._oss = None
        if  oss_ak and  oss_sk:
            self._oss = OSSUtils(oss_ak, oss_sk, oss_endpoint, oss_bucket_name)

    def _get_env_stage(self) -> str:
        env = (os.getenv("SERVER_ENV") or "local").lower()
        return "dev" if env in {"local", "dev"} else "prod"

    def _get_app_name(self) -> str:
        return os.getenv("app_name", "sregpt")

    def _get_oss_prefix(self) -> str:
        prefix = f"{self._get_env_stage()}/{self._get_app_name()}"
        return prefix.strip("/")

    def build_oss_path(self, path: str) -> str:
        normalized = (path or "").lstrip("/")
        prefix = self._get_oss_prefix()
        return f"{prefix}/{normalized}" if normalized else prefix

    @property
    def work_dir(self) -> str:
        return self._work_dir

    @property
    def sandbox_id(self):
        return self._sandbox_id

    @property
    def oss(self) -> OSSUtils:
        return self._oss

    async def create(self, path: str, content: Optional[str] = None, user: Optional[str] = None,
                     overwrite: bool = True) -> FileInfo:
        """
        create file .

        :param content: content to the file
        :param path: Path to the file
        :param user: Run the operation as this user
        :param overwrite: Overwrite old content

        :return: File content as a `str`
        """
        ...

    async def find_file(self, path: str, glob: str) -> List[str]:
        """
           find file .

           :param path: Path to the file
           :param glob: 全局模式匹配文件

           :return: File content as a `str`
           """
        ...

    async def find_content(self, path: str, reg_ex: str) -> FileInfo:
        """
           find file .

           :param path: Path to the file
           :param reg_ex: 要搜索的正则表达式模式

           :return: File content as a `str`
           """
        ...

    async def str_replace(self, path: str, old_str: str, new_str: str, user: Optional[str] = None) -> FileInfo:
        """
        str replace.

        :param path: Path to the file
        :param old_str: 要修改的内容
        :param new_str: 修改后的内容
        :param user: 修改的用户
        """

    async def read(
        self,
        path: str,
        format: Literal["text", "bytes", "stream"] = "text",
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ):
        """
        Read file content as a `str`.

        :param path: Path to the file
        :param user: Run the operation as this user
        :param format: Format of the file content—`text` by default
        :param request_timeout: Timeout for the request in **seconds**

        :return: File content as a `str`
        """

        ...
        # if format == "text":
        #     return r.text
        # elif format == "bytes":
        #     return bytearray(r.content)
        # elif format == "stream":
        #     return r.aiter_bytes()
        #

    async def write_chat_file(
        self,
        conversation_id: str,
        path: str,
        data: Union[str, bytes, IO],
        user: Optional[Username] = None,
        overwrite: bool = False,
    ) -> FileInfo:
        """写入对 Agent 对话文件并将其持久化至 conversation 专属 OSS 路径。"""

        normalized_path = (path or "").strip()
        if not normalized_path:
            raise ValueError("写入对话文件失败: path 不能为空")

        if normalized_path.startswith("/"):
            normalized_path = posixpath.normpath(normalized_path)
        else:
            normalized_path = posixpath.normpath(posixpath.join(self._work_dir, normalized_path))

        workspace_root = posixpath.normpath(self._work_dir.rstrip("/") or "/") or "/"
        try:
            relative_path = posixpath.relpath(normalized_path, workspace_root)
            if relative_path.startswith("../"):
                raise ValueError
        except ValueError:
            # 回退到移除前导斜杠的绝对路径，确保不会抛异常
            relative_path = normalized_path.lstrip("/")

        file_info = await self.write(path=normalized_path, data=data, user=user, overwrite=overwrite, save_oss=False)

        if conversation_id:
            try:
                oss_source = await self.upload_to_oss(normalized_path)
                storage_key = self.build_oss_path(
                    posixpath.join("conversations", str(conversation_id), relative_path)
                )
                transfer_result = self.oss.transfer_from_url(oss_source.temp_url, storage_key)
                preview_url = self.oss.generate_presigned_url(storage_key, download=False)
                file_info.oss_info = OSSFile(
                    object_name=storage_key,
                    object_url=transfer_result.get("object_url"),
                    temp_url=preview_url,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("写入 OSS 失败: conversation_id=%s path=%s error=%s", conversation_id, normalized_path,
                               exc)

        return file_info

    async def write(
        self,
        path: str,
        data: Union[str, bytes, IO],
        user: Optional[Username] = None,
        overwrite: bool = False,
        save_oss: bool = False
    ) -> FileInfo:
        """
        Write content to a file on the path.
        Writing to a file that doesn't exist creates the file.
        Writing to a file that already exists overwrites the file.
        Writing to a file at path that doesn't exist creates the necessary directories.

        :param path: Path to the file
        :param data: Data to write to the file, can be a `str`, `bytes`, or `IO`.
        :param user: Run the operation as this user
        :param overwrite: 是否覆盖已有内容，默认不覆盖
        :param save_oss: 是否将文件写到oss

        :return: Information about the written file
        """
        ...

    async def list(
        self,
        path: str,
        depth: Optional[int] = 1,
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ) -> List[EntryInfo]:
        """
        List entries in a directory.

        :param path: Path to the directory
        :param depth: Depth of the directory to list
        :param user: Run the operation as this user
        :param request_timeout: Timeout for the request in **seconds**

        :return: List of entries in the directory
        """
        ...

    async def exists(
        self,
        path: str,
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ) -> bool:
        """
        Check if a file or a directory exists.

        :param path: Path to a file or a directory
        :param user: Run the operation as this user
        :param request_timeout: Timeout for the request in **seconds**

        :return: `True` if the file or directory exists, `False` otherwise
        """
        ...

    async def get_info(
        self,
        path: str,
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ) -> EntryInfo:
        """
        Get information about a file or directory.

        :param path: Path to a file or a directory
        :param user: Run the operation as this user
        :param request_timeout: Timeout for the request in **seconds**

        :return: Information about the file or directory like name, type, and path
        """
        ...

    async def remove(
        self,
        path: str,
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ) -> None:
        """
        Remove a file or a directory.

        :param path: Path to a file or a directory
        :param user: Run the operation as this user
        :param request_timeout: Timeout for the request in **seconds**
        """
        ...

    async def rename(
        self,
        old_path: str,
        new_path: str,
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ) -> EntryInfo:
        """
        Rename a file or directory.

        :param old_path: Path to the file or directory to rename
        :param new_path: New path to the file or directory
        :param user: Run the operation as this user
        :param request_timeout: Timeout for the request in **seconds**

        :return: Information about the renamed file or directory
        """
        ...

    async def make_dir(
        self,
        path: str,
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ) -> bool:
        """
        Create a new directory and all directories along the way if needed on the specified path.

        :param path: Path to a new directory. For example '/dirA/dirB' when creating 'dirB'.
        :param user: Run the operation as this user
        :param request_timeout: Timeout for the request in **seconds**

        :return: `True` if the directory was created, `False` if the directory already exists
        """
        ...

    async def upload_to_oss(
        self,
        file_path: str,
    ) -> OSSFile:
        """
        Upload local files to OSS.
        :param file_path: 要上传的文件.

        :return: OSS文件信息
        """
        ...

    async def start_upload_to_oss(
        self,
        file_path: str,
    ) -> str:
        """
        Upload local files to OSS.
        :param file_path: 要上传的文件.

        :return: 上传文件到OSS的任务id
        """
        ...

    async def download_to_local(
        self,
        url: str,
        filename: str,
        path: str,
        user: Optional[Username] = None,
    ) -> bool:
        """
        Download files from OSS to local.

        :param url: 要下载文件的url.
        :param filename: 下载到本地后的文件名字.
        :param path: 下载到本地的路径.
        :param user: Run the operation as this user


        :return: `True` 文件下载完成, `False` 下载失败
        """
        ...

    async def start_download_to_local(
        self,
        url: str,
        filename: str,
        path: str,
        user: Optional[Username] = None,
    ) -> str:
        """
        开启一个下载文件到本地的任务

        :param url: 要下载文件的url.
        :param filename: 下载到本地后的文件名字.
        :param path: 下载到本地的路径.
        :param user: Run the operation as this user


        :return: 下载任务id
        """
        ...

    async def get_task_result(self, task_id: str) -> TaskResult:
        """
        获取文件任务的结果

        :param task_id: 任务id.

        :return: 任务结果信息
        """
        ...

    async def cancel_tasks(self, task_ids: List[str]) -> bool:
        """
        取消文件任务

        :param task_ids: 任务id.

        :return: 任务结果信息
        """
        ...
