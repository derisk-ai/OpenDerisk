import logging
import os
from abc import ABC
from typing import Optional, Dict, Union, List

import oss2
import requests
from pathlib import Path
from datetime import timedelta
import asyncio
import aiohttp
from pathlib import Path

logger = logging.getLogger(__name__)

class SandBoxFileStorage(ABC):

    def upload_file(self, local_file_path, oss_object_name):
        """
        上传本地文件到OSS
        :param local_file_path: 本地文件路径
        :param oss_object_name: OSS对象名称 (包含路径)
        :return: 上传结果和对象URL
        """

    def upload_directory(self, local_directory: str, oss_prefix: str) -> Dict[str, Union[int, str, List[str]]]:
        """
        上传本地目录及其所有子目录内容到OSS

        :param local_directory: 本地目录路径
        :param oss_prefix: OSS目标路径前缀 (如 'backup/2023/')
        :return: 上传结果统计信息
        """

    def generate_presigned_url(self, oss_object_name, expiration=3600, download=True):
        """
        生成预签名URL用于下载或预览
        :param oss_object_name: OSS对象名称
        :param expiration: URL有效期（秒），默认1小时
        :param download: 是否作为下载链接（添加content-disposition）
        :return: 预签名URL
        """

    def download_file(self, oss_object_name, local_file_path):
        """
        从OSS下载文件到本地
        :param oss_object_name: OSS对象名称
        :param local_file_path: 本地保存路径
        :return: 下载结果
        """
class OSSUtils:
    def __init__(self, access_key_id, access_key_secret, endpoint, bucket_name, chat_uid: Optional[str] = None):
        """
        初始化OSS客户端
        :param access_key_id: 阿里云AccessKey ID
        :param access_key_secret: 阿里云AccessKey Secret
        :param endpoint: OSS访问端点
        :param bucket_name: OSS存储桶名称
        """
        auth = oss2.Auth(access_key_id, access_key_secret)
        self.bucket = oss2.Bucket(auth, endpoint, bucket_name)
        self.bucket_name = bucket_name
        self.endpoint = endpoint
        self.chat_uid: str = chat_uid

    def upload_file(self, local_file_path, oss_object_name):
        """
        上传本地文件到OSS
        :param local_file_path: 本地文件路径
        :param oss_object_name: OSS对象名称 (包含路径)
        :return: 上传结果和对象URL
        """
        if not os.path.isfile(local_file_path):
            raise FileNotFoundError(f"Local file not found: {local_file_path}")

        try:
            result = self.bucket.put_object_from_file(oss_object_name, local_file_path)
            if result.status == 200:
                # 返回标准对象URL（非签名）
                object_url = f"https://{self.bucket_name}.{self.endpoint.replace('https://', '')}/{oss_object_name}"
                return {
                    "status": "success",
                    "message": f"File uploaded successfully. ETag: {result.etag}",
                    "object_url": object_url,
                    "object_name": oss_object_name
                }
            else:
                raise RuntimeError(f"Upload failed with status: {result.status}")
        except oss2.exceptions.OssError as e:
            raise RuntimeError(f"OSS error: {e}") from e

    def upload_directory(self, local_directory: str, oss_prefix: str) -> Dict[str, Union[int, str, List[str]]]:
        """
        上传本地目录及其所有子目录内容到OSS

        :param local_directory: 本地目录路径
        :param oss_prefix: OSS目标路径前缀 (如 'backup/2023/')
        :return: 上传结果统计信息
        """
        # 规范化路径
        local_dir = Path(local_directory).resolve()
        if not local_dir.is_dir():
            raise NotADirectoryError(f"Local directory not found: {local_directory}")

        # 确保OSS前缀以斜杠结尾
        oss_prefix = oss_prefix.rstrip('/') + '/'

        uploaded_files = []
        skipped_files = []
        error_files = []

        # 遍历本地目录
        for root, _, files in os.walk(local_dir):
            for filename in files:
                local_path = Path(root) / filename
                # 计算相对路径
                relative_path = local_path.relative_to(local_dir)
                # 构建OSS对象路径
                oss_object_name = oss_prefix + str(relative_path).replace('\\', '/')

                try:
                    # 上传文件
                    result = self.upload_file(str(local_path), oss_object_name)
                    uploaded_files.append(oss_object_name)
                    logger.info(f"Uploaded: {local_path} -> {oss_object_name}")
                except Exception as e:
                    error_files.append(str(local_path))
                    logger.error(f"Failed to upload {local_path}: {str(e)}")

        # 返回统计结果
        return {
            "status": "completed",
            "uploaded_count": len(uploaded_files),
            "error_count": len(error_files),
            "skipped_count": len(skipped_files),
            "uploaded_files": uploaded_files,
            "error_files": error_files,
            "message": f"Uploaded {len(uploaded_files)} files, {len(error_files)} errors"
        }

    def generate_presigned_url(self, oss_object_name, expiration=3600, download=True):
        """
        生成预签名URL用于下载或预览
        :param oss_object_name: OSS对象名称
        :param expiration: URL有效期（秒），默认1小时
        :param download: 是否作为下载链接（添加content-disposition）
        :return: 预签名URL
        """
        try:
            # 设置下载参数（可选）
            params = {}
            if download:
                params['response-content-disposition'] = f'attachment; filename="{os.path.basename(oss_object_name)}"'

            # 生成预签名URL
            url = self.bucket.sign_url(
                'GET',
                oss_object_name,
                expiration,
                params=params
            )
            return url
        except oss2.exceptions.NoSuchKey:
            raise FileNotFoundError(f"OSS object not found: {oss_object_name}")
        except oss2.exceptions.OssError as e:
            raise RuntimeError(f"OSS error: {e}") from e

    def download_file(self, oss_object_name, local_file_path):
        """
        从OSS下载文件到本地
        :param oss_object_name: OSS对象名称
        :param local_file_path: 本地保存路径
        :return: 下载结果
        """
        # 确保目录存在
        Path(local_file_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            self.bucket.get_object_to_file(oss_object_name, local_file_path)
            if os.path.exists(local_file_path):
                return f"File downloaded to: {local_file_path}"
            else:
                raise RuntimeError("Download failed: local file not created")
        except oss2.exceptions.NoSuchKey:
            raise FileNotFoundError(f"OSS object not found: {oss_object_name}")
        except oss2.exceptions.OssError as e:
            raise RuntimeError(f"OSS error: {e}") from e

    def download_directory(self, oss_prefix: str, local_directory: str) -> Dict[str, Union[int, str, List[str]]]:
        """
        下载OSS目录下的所有文件到本地目录

        :param oss_prefix: OSS目录路径（如 'user/data/'）
        :param local_directory: 本地目标目录
        :return: 下载结果统计信息
        """
        # 确保本地目录存在
        local_dir = Path(local_directory)
        local_dir.mkdir(parents=True, exist_ok=True)

        # 确保OSS前缀以斜杠结尾
        oss_prefix = oss_prefix.rstrip('/') + '/'

        downloaded_files = []
        skipped_files = []
        error_files = []

        # 遍历所有对象（自动处理分页）
        for obj in oss2.ObjectIterator(self.bucket, prefix=oss_prefix):
            # 跳过目录标记对象（0字节且以/结尾）
            if obj.key.endswith('/') and obj.size == 0:
                continue

            # 计算本地文件路径（保留相对目录结构）
            relative_path = obj.key[len(oss_prefix):]
            if not relative_path:  # 跳过目录本身
                continue

            local_path = local_dir / relative_path

            # 确保子目录存在
            local_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                # 下载文件
                self.bucket.get_object_to_file(obj.key, str(local_path))
                downloaded_files.append(obj.key)
                logger.info(f"Downloaded: {obj.key} -> {local_path}")
            except Exception as e:
                error_files.append(obj.key)
                logger.error(f"Failed to download {obj.key}: {str(e)}")

        # 返回统计结果
        return {
            "status": "completed",
            "downloaded_count": len(downloaded_files),
            "error_count": len(error_files),
            "skipped_count": len(skipped_files),
            "downloaded_files": downloaded_files,
            "error_files": error_files,
            "message": f"Downloaded {len(downloaded_files)} files, {len(error_files)} errors"
        }

    def transfer_from_url(self, source_url, target_object_name, chunk_size=10 * 1024 ** 2):
        try:
            logger.info(f"OSS URL转存: {source_url} -> {target_object_name}")
            with requests.get(source_url, stream=True) as response:
                response.raise_for_status()

                # 保留原始Content-Type
                content_type = response.headers.get('Content-Type', 'application/octet-stream')

                # 初始化分片上传（携带原始Content-Type）
                init_result = self.bucket.init_multipart_upload(
                    target_object_name,
                    headers={'Content-Type': content_type}
                )
                upload_id = init_result.upload_id
                total_size = int(response.headers.get('content-length', 0))
                parts = []
                part_number = 1

                # 分块读取并上传（二进制原样传输）
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        break
                    result = self.bucket.upload_part(
                        target_object_name,
                        upload_id,
                        part_number,
                        chunk
                    )
                    parts.append(oss2.models.PartInfo(part_number, result.etag))
                    part_number += 1

                # 完成分片上传
                self.bucket.complete_multipart_upload(
                    target_object_name,
                    upload_id,
                    parts
                )

                # 返回标准对象URL
                from urllib.parse import quote
                encoded_name = quote(target_object_name)
                object_url = f"https://{self.bucket_name}.{self.endpoint.replace('https://', '')}/{encoded_name}"

                return {
                    "status": "success",
                    "message": f"Transfer completed! Size: {total_size} bytes",
                    "object_url": object_url,
                    "object_name": target_object_name
                }

        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"源URL错误: {e}") from e
        except oss2.exceptions.OssError as e:
            if 'upload_id' in locals():
                self.bucket.abort_multipart_upload(target_object_name, upload_id)
            raise RuntimeError(f"OSS传输错误: {e}") from e

    def generate_directory_download_urls(self, oss_prefix: str, expiration: int = 3600, download: bool = True) -> Dict[
        str, Union[int, str, List[Dict[str, str]]]]:
        """
        生成目录下所有文件的下载URL（预签名URL）

        :param oss_prefix: OSS目录前缀（如 'user/data/'）
        :param expiration: URL有效期（秒），默认1小时
        :param download: 是否作为下载链接（添加content-disposition）
        :return: 包含文件URL列表和统计信息的结果字典
        """
        # 确保前缀以斜杠结尾
        oss_prefix = oss_prefix.rstrip('/') + '/'

        file_urls = []
        error_files = []

        try:
            # 测试存储桶访问权限
            self.bucket.get_bucket_info()
            print("Bucket access verified")
        except oss2.exceptions.AccessDenied as e:
            print(f"ACCESS DENIED: Check permissions for bucket {self.bucket.bucket_name}")
            print(f"Endpoint: {self.bucket.endpoint}")
            print(f"Used AccessKey: {self.bucket.auth.access_key_id[:4]}...")
            raise

        # 遍历目录下的所有对象
        for obj in oss2.ObjectIterator(self.bucket, prefix=oss_prefix):
            # 跳过目录标记对象（0字节且以/结尾）
            if obj.key.endswith('/') and obj.size == 0:
                continue

            try:
                # 生成预签名URL
                url = self.generate_presigned_url(
                    oss_object_name=obj.key,
                    expiration=expiration,
                    download=download
                )
                # 获取相对路径（相对于目录前缀）
                relative_path = obj.key[len(oss_prefix):]

                file_urls.append({
                    "object_name": obj.key,
                    "relative_path": relative_path,
                    "url": url,
                    "size": obj.size
                })
            except Exception as e:
                error_files.append({
                    "object_name": obj.key,
                    "error": str(e)
                })
                logger.error(f"Failed to generate URL for {obj.key}: {str(e)}")

        return {
            "status": "completed",
            "file_count": len(file_urls),
            "error_count": len(error_files),
            "file_urls": file_urls,
            "error_files": error_files,
            "message": f"Generated {len(file_urls)} URLs, {len(error_files)} errors"
        }



class AsyncOSSUtils:
    def __init__(self, access_key_id: str, access_key_secret: str, endpoint: str, bucket_name: str,
                 chat_uid: Optional[str] = None):
        """
        初始化OSS客户端

        Args:
            access_key_id: 阿里云AccessKey ID
            access_key_secret: 阿里云AccessKey Secret
            endpoint: OSS访问端点
            bucket_name: OSS存储桶名称
            chat_uid: 可选的聊天用户ID
        """
        self.auth = oss2.Auth(access_key_id, access_key_secret)
        self.bucket = oss2.Bucket(self.auth, endpoint, bucket_name)
        self.bucket_name = bucket_name
        self.endpoint = endpoint
        self.chat_uid = chat_uid

    async def upload_file(self, local_file_path: str, oss_object_name: str) -> Dict[str, str]:
        """
        异步上传本地文件到OSS

        Args:
            local_file_path: 本地文件路径
            oss_object_name: OSS对象名称

        Returns:
            包含上传结果的字典
        """
        if not os.path.isfile(local_file_path):
            raise FileNotFoundError(f"Local file not found: {local_file_path}")

        try:
            result = await asyncio.to_thread(
                self.bucket.put_object_from_file,
                oss_object_name,
                local_file_path
            )

            if result.status == 200:
                object_url = f"https://{self.bucket_name}.{self.endpoint.replace('https://', '')}/{oss_object_name}"
                return {
                    "status": "success",
                    "message": f"File uploaded successfully. ETag: {result.etag}",
                    "object_url": object_url,
                    "object_name": oss_object_name
                }
            else:
                raise RuntimeError(f"Upload failed with status: {result.status}")
        except oss2.exceptions.OssError as e:
            raise RuntimeError(f"OSS error: {e}") from e

    async def upload_directory(self, local_directory: str, oss_prefix: str) -> Dict[str, Union[int, str, List[str]]]:
        """
        异步上传本地目录及其所有子目录内容到OSS

        Args:
            local_directory: 本地目录路径
            oss_prefix: OSS目标路径前缀

        Returns:
            包含上传统计信息的字典
        """
        local_dir = Path(local_directory).resolve()
        if not local_dir.is_dir():
            raise NotADirectoryError(f"Local directory not found: {local_directory}")

        oss_prefix = oss_prefix.rstrip('/') + '/'
        uploaded_files = []
        skipped_files = []
        error_files = []
        upload_tasks = []

        for root, _, files in os.walk(local_dir):
            for filename in files:
                local_path = Path(root) / filename
                relative_path = local_path.relative_to(local_dir)
                oss_object_name = oss_prefix + str(relative_path).replace('\\', '/')
                upload_tasks.append(self.upload_file(str(local_path), oss_object_name))

        results = await asyncio.gather(*upload_tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                error_files.append(str(result))
            else:
                uploaded_files.append(result["object_name"])

        return {
            "status": "completed",
            "uploaded_count": len(uploaded_files),
            "error_count": len(error_files),
            "skipped_count": len(skipped_files),
            "uploaded_files": uploaded_files,
            "error_files": error_files,
            "message": f"Uploaded {len(uploaded_files)} files, {len(error_files)} errors"
        }

    async def generate_presigned_url(self, oss_object_name: str, expiration: int = 3600, download: bool = True) -> str:
        """
        异步生成预签名URL

        Args:
            oss_object_name: OSS对象名称
            expiration: URL有效期（秒）
            download: 是否作为下载链接

        Returns:
            预签名URL字符串
        """
        try:
            params = {}
            if download:
                params['response-content-disposition'] = f'attachment; filename="{os.path.basename(oss_object_name)}"'

            url = await asyncio.to_thread(
                self.bucket.sign_url,
                'GET',
                oss_object_name,
                expiration,
                params=params
            )
            return url
        except oss2.exceptions.NoSuchKey:
            raise FileNotFoundError(f"OSS object not found: {oss_object_name}")
        except oss2.exceptions.OssError as e:
            raise RuntimeError(f"OSS error: {e}") from e

    async def download_file(self, oss_object_name: str, local_file_path: str) -> str:
        """
        异步从OSS下载文件到本地

        Args:
            oss_object_name: OSS对象名称
            local_file_path: 本地保存路径

        Returns:
            下载成功消息
        """
        Path(local_file_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            await asyncio.to_thread(
                self.bucket.get_object_to_file,
                oss_object_name,
                local_file_path
            )

            if os.path.exists(local_file_path):
                return f"File downloaded to: {local_file_path}"
            else:
                raise RuntimeError("Download failed: local file not created")
        except oss2.exceptions.NoSuchKey:
            raise FileNotFoundError(f"OSS object not found: {oss_object_name}")
        except oss2.exceptions.OssError as e:
            raise RuntimeError(f"OSS error: {e}") from e

    async def download_directory(self, oss_prefix: str, local_directory: str) -> Dict[str, Union[int, str, List[str]]]:
        """
        异步下载OSS目录下的所有文件到本地目录

        Args:
            oss_prefix: OSS目录路径
            local_directory: 本地目标目录

        Returns:
            包含下载统计信息的字典
        """
        local_dir = Path(local_directory)
        local_dir.mkdir(parents=True, exist_ok=True)
        oss_prefix = oss_prefix.rstrip('/') + '/'

        downloaded_files = []
        skipped_files = []
        error_files = []

        # 列出所有对象
        objects = await asyncio.to_thread(
            lambda: list(oss2.ObjectIterator(self.bucket, prefix=oss_prefix))
        )

        download_tasks = []
        for obj in objects:
            if obj.key.endswith('/') and obj.size == 0:
                continue

            relative_path = obj.key[len(oss_prefix):]
            if not relative_path:
                continue

            local_path = local_dir / relative_path
            local_path.parent.mkdir(parents=True, exist_ok=True)
            download_tasks.append(self.download_file(obj.key, str(local_path)))

        results = await asyncio.gather(*download_tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_files.append(objects[i].key)
            else:
                downloaded_files.append(objects[i].key)

        return {
            "status": "completed",
            "downloaded_count": len(downloaded_files),
            "error_count": len(error_files),
            "skipped_count": len(skipped_files),
            "downloaded_files": downloaded_files,
            "error_files": error_files,
            "message": f"Downloaded {len(downloaded_files)} files, {len(error_files)} errors"
        }

    async def transfer_from_url(self, source_url: str, target_object_name: str, chunk_size: int = 10 * 1024 ** 2) -> \
    Dict[str, str]:
        """
        异步从URL传输文件到OSS

        Args:
            source_url: 源文件URL
            target_object_name: OSS目标对象名称
            chunk_size: 分片大小（字节）

        Returns:
            包含传输结果的字典
        """
        try:
            logger.info(f"OSS URL转存: {source_url} -> {target_object_name}")

            async with aiohttp.ClientSession() as session:
                async with session.get(source_url) as response:
                    response.raise_for_status()

                    content_type = response.headers.get('Content-Type', 'application/octet-stream')
                    total_size = int(response.headers.get('content-length', 0))

                    # 初始化分片上传
                    init_result = await asyncio.to_thread(
                        self.bucket.init_multipart_upload,
                        target_object_name,
                        headers={'Content-Type': content_type}
                    )

                    upload_id = init_result.upload_id
                    parts = []
                    part_number = 1

                    # 分块读取并上传
                    while True:
                        chunk = await response.content.read(chunk_size)
                        if not chunk:
                            break

                        result = await asyncio.to_thread(
                            self.bucket.upload_part,
                            target_object_name,
                            upload_id,
                            part_number,
                            chunk
                        )

                        parts.append(oss2.models.PartInfo(part_number, result.etag))
                        part_number += 1

                    # 完成分片上传
                    await asyncio.to_thread(
                        self.bucket.complete_multipart_upload,
                        target_object_name,
                        upload_id,
                        parts
                    )

                    from urllib.parse import quote
                    encoded_name = quote(target_object_name)
                    object_url = f"https://{self.bucket_name}.{self.endpoint.replace('https://', '')}/{encoded_name}"

                    return {
                        "status": "success",
                        "message": f"Transfer completed! Size: {total_size} bytes",
                        "object_url": object_url,
                        "object_name": target_object_name
                    }

        except aiohttp.ClientError as e:
            raise ConnectionError(f"源URL错误: {e}") from e
        except oss2.exceptions.OssError as e:
            if 'upload_id' in locals():
                await asyncio.to_thread(
                    self.bucket.abort_multipart_upload,
                    target_object_name,
                    upload_id
                )
            raise RuntimeError(f"OSS传输错误: {e}") from e

    async def generate_directory_download_urls(
        self,
        oss_prefix: str,
        expiration: int = 3600,
        download: bool = True
    ) -> Dict[str, Union[int, str, List[Dict[str, str]]]]:
        """
        异步生成目录下所有文件的下载URL

        Args:
            oss_prefix: OSS目录前缀
            expiration: URL有效期（秒）
            download: 是否作为下载链接

        Returns:
            包含文件URL列表和统计信息的字典
        """
        oss_prefix = oss_prefix.rstrip('/') + '/'
        file_urls = []
        error_files = []

        # 列出所有对象
        objects = await asyncio.to_thread(
            lambda: list(oss2.ObjectIterator(self.bucket, prefix=oss_prefix))
        )

        # 为每个对象生成URL的任务
        url_tasks = []
        for obj in objects:
            if not (obj.key.endswith('/') and obj.size == 0):
                url_tasks.append(self.generate_presigned_url(obj.key, expiration, download))

        # 并发生成URL
        urls = await asyncio.gather(*url_tasks, return_exceptions=True)

        for i, url_result in enumerate(urls):
            obj = objects[i]
            if isinstance(url_result, Exception):
                error_files.append({
                    "object_name": obj.key,
                    "error": str(url_result)
                })
                logger.error(f"Failed to generate URL for {obj.key}: {str(url_result)}")
            else:
                relative_path = obj.key[len(oss_prefix):]
                file_urls.append({
                    "object_name": obj.key,
                    "relative_path": relative_path,
                    "url": url_result,
                    "size": obj.size
                })

        return {
            "status": "completed",
            "file_count": len(file_urls),
            "error_count": len(error_files),
            "file_urls": file_urls,
            "error_files": error_files,
            "message": f"Generated {len(file_urls)} URLs, {len(error_files)} errors"
        }
