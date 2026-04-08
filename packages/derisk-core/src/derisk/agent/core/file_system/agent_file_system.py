"""Agent File System (AFS) V3 - 集成 FileStorageClient 的实现.

架构设计:
- AgentFileSystem 集成 FileStorageClient，支持统一的文件存储接口
- 支持多种存储后端 (本地文件系统、OSS、分布式存储)
- URL 生成委托给 FileStorageClient，支持代理和直接访问
- 保持与 V1/V2 版本的 API 兼容性

存储策略:
1. 优先使用 FileStorageClient (如果提供)
2. 回退到 OSS 客户端 (如果提供)
3. 最后使用本地文件系统

URL 生成:
- FileStorageClient 支持时：使用 get_public_url() 生成代理URL或OSS直链
- OSS 客户端支持时：使用 generate_preview_url/download_url 生成OSS直链
- 仅本地存储：返回本地文件路径
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Union

from derisk.agent.core.memory.gpts.file_base import (
    AgentFileMetadata,
    FileMetadataStorage,
    FileType,
    FileStatus,
)
from derisk.agent.core.memory.gpts.file_base import SimpleFileMetadataStorage
from derisk.configs.model_config import DATA_DIR
from derisk.sandbox.base import SandboxBase

logger = logging.getLogger(__name__)


class FileCategory(Enum):
    """文件分类（用于前端展示分组）."""

    WORKSPACE = "workspace"  # 工作区文件
    TOOL_OUTPUT = "tool_output"  # 工具输出
    CONCLUSION = "conclusion"  # 结论文件
    RESOURCE = "resource"  # 资源文件


class AgentFileSystem:
    """Agent文件系统 V3 - 集成 FileStorageClient.

    功能:
    1. 统一的文件存储接口（通过 FileStorageClient）
    2. 支持多种存储后端 (本地、OSS、分布式)
    3. 代理URL生成（通过文件服务）
    4. 文件内容去重（基于哈希）
    5. d-attach组件推送
    6. 向后兼容 OSS 客户端模式

    使用示例:
        # 方式1: 使用 FileStorageClient（推荐）
        from derisk.core.interface.file import FileStorageClient
        file_storage_client = FileStorageClient.get_instance(system_app)
        afs = AgentFileSystem(
            conv_id="session_001",
            file_storage_client=file_storage_client,
        )

        # 方式2: 使用 OSS 客户端（兼容模式）
        oss_client = OSSClient(...)
        afs = AgentFileSystem(
            conv_id="session_001",
            oss_client=oss_client,
        )

        # 方式3: 仅本地存储
        afs = AgentFileSystem(conv_id="session_001")
    """

    def __init__(
        self,
        conv_id: str,
        session_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        base_working_dir: str = str(os.path.join(DATA_DIR, "agent_storage")),
        sandbox: Optional[SandboxBase] = None,
        metadata_storage: Optional[FileMetadataStorage] = None,
        file_storage_client: Optional[Any] = None,  # FileStorageClient
        oss_client=None,  # 兼容旧版 OSS 客户端
        bucket: Optional[str] = None,  # FileStorageClient 使用的 bucket
    ):
        """初始化Agent文件系统 V3.

        Args:
            conv_id: 会话ID
            session_id: 会话会话ID（用于子任务隔离，默认使用conv_id）
            goal_id: 目标ID（用于任务隔离，默认"default"）
            base_working_dir: 基础工作目录
            sandbox: 沙箱环境（可选）
            metadata_storage: 文件元数据存储接口（可选，默认SimpleFileMetadataStorage）
            file_storage_client: FileStorageClient 实例（可选，推荐）
            oss_client: OSS客户端（可选，兼容模式）
            bucket: FileStorageClient 使用的 bucket 名称（可选，默认"agent_files"）
        """
        self.conv_id = conv_id
        self.session_id = session_id or conv_id
        self.goal_id = goal_id or "default"
        self.sandbox = sandbox
        self.metadata_storage = metadata_storage or SimpleFileMetadataStorage()
        self._file_storage_client = file_storage_client
        self._oss_client = oss_client  # 兼容旧版
        self._bucket = bucket or "agent_files"

        # 构建存储路径（用于本地缓存或回退）
        self.base_path = Path(base_working_dir) / self.session_id / self.goal_id

        # 内容哈希索引（用于去重，仅内存缓存）
        self._hash_index: Dict[str, str] = {}  # content_hash -> file_key

        # 记录使用的存储模式
        if file_storage_client:
            logger.info(
                f"[AFSv3] Initialized with FileStorageClient for conv: {conv_id}"
            )
        elif oss_client:
            logger.info(f"[AFSv3] Initialized with OSS client for conv: {conv_id}")
        else:
            logger.info(f"[AFSv3] Initialized with local storage for conv: {conv_id}")

    def _ensure_dir(self):
        """确保目录存在."""
        if not self.sandbox:
            self.base_path.mkdir(parents=True, exist_ok=True)

    def _compute_hash(self, data: Union[str, Dict, List]) -> str:
        """计算数据哈希（用于去重）."""
        if isinstance(data, (dict, list)):
            content_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        else:
            content_str = str(data)
        return hashlib.md5(content_str.encode("utf-8")).hexdigest()

    def _get_mime_type(self, filename: str) -> str:
        """获取文件MIME类型."""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    def _sanitize_filename(self, key: str) -> str:
        """清理文件名."""
        return "".join([c for c in key if c.isalnum() or c in ("-", "_", ".")])

    def _get_file_path(self, file_key: str, extension: str = "txt") -> Path:
        """获取本地文件路径."""
        if "." in file_key and len(file_key.split(".")[-1]) <= 4:
            safe_key = self._sanitize_filename(file_key)
        else:
            safe_key = f"{self._sanitize_filename(file_key)}.{extension}"
        return self.base_path / safe_key

    # ==================== 存储适配层 ====================

    async def _save_to_storage(
        self,
        file_key: str,
        data: Union[str, bytes],
        extension: str = "txt",
        file_name: Optional[str] = None,
    ) -> tuple[str, int]:
        """保存文件到存储系统.

        Returns:
            tuple: (storage_uri, file_size)
        """
        # 准备内容
        if isinstance(data, str):
            content_bytes = data.encode("utf-8")
        else:
            content_bytes = data

        file_size = len(content_bytes)

        # 优先使用 FileStorageClient
        if self._file_storage_client:
            return await self._save_with_file_storage_client(
                file_key, content_bytes, extension
            )

        # 其次使用 OSS 客户端
        if self._oss_client:
            return await self._save_with_oss_client(file_key, content_bytes, extension)

        # 最后使用本地存储
        return await self._save_to_local(file_key, content_bytes, extension)

    async def _save_with_file_storage_client(
        self,
        file_key: str,
        content_bytes: bytes,
        extension: str = "txt",
    ) -> tuple[str, int]:
        """使用 FileStorageClient 保存文件."""
        import asyncio

        actual_file_name = (
            f"{file_key}.{extension}" if "." not in file_key else file_key
        )
        bucket = self._bucket

        file_data = io.BytesIO(content_bytes)

        custom_metadata = {
            "conv_id": self.conv_id,
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "file_key": file_key,
        }

        try:
            uri = await asyncio.to_thread(
                self._file_storage_client.save_file,
                bucket=bucket,
                file_name=actual_file_name,
                file_data=file_data,
                custom_metadata=custom_metadata,
            )
            logger.info(f"[AFSv3] Saved to FileStorage: {uri}")

            if self.sandbox:
                safe_key = self._sanitize_filename(file_key)
                if "." not in safe_key:
                    safe_key = f"{safe_key}.{extension}"
                work_dir = getattr(self.sandbox, "work_dir", "/home/ubuntu")
                sandbox_path = f"{work_dir}/{self.goal_id}/{safe_key}"
                await self.sandbox.file.create(
                    sandbox_path, content_bytes.decode("utf-8")
                )
                logger.info(f"[AFSv3] Saved to sandbox: {sandbox_path}")

            return uri, len(content_bytes)
        except Exception as e:
            logger.error(f"[AFSv3] Failed to save with FileStorageClient: {e}")
            raise

    async def _save_with_oss_client(
        self,
        file_key: str,
        content_bytes: bytes,
        extension: str = "txt",
    ) -> tuple[str, int]:
        """使用 OSS 客户端保存文件（兼容模式）."""
        import asyncio

        self._ensure_dir()

        safe_key = self._sanitize_filename(file_key)
        if "." not in safe_key:
            safe_key = f"{safe_key}.{extension}"

        local_path = self.base_path / safe_key

        if self.sandbox:
            work_dir = getattr(self.sandbox, "work_dir", "/home/ubuntu")
            sandbox_path = f"{work_dir}/{self.goal_id}/{safe_key}"
            await self.sandbox.file.create(sandbox_path, content_bytes.decode("utf-8"))
            logger.info(f"[AFSv3] Saved to sandbox: {sandbox_path}")
        else:
            await asyncio.to_thread(local_path.write_bytes, content_bytes)

        try:
            oss_object_name = f"{self.session_id}/{self.goal_id}/{local_path.name}"

            if self.sandbox:
                temp_dir = Path("/tmp") / self.session_id / self.goal_id
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_file = temp_dir / local_path.name

                work_dir = getattr(self.sandbox, "work_dir", "/home/ubuntu")
                sandbox_path = f"{work_dir}/{self.goal_id}/{safe_key}"
                file_info = await self.sandbox.file.read(sandbox_path)
                if file_info.content:
                    temp_file.write_text(file_info.content, encoding="utf-8")
                    await asyncio.to_thread(
                        self._oss_client.upload_file, str(temp_file), oss_object_name
                    )
                    temp_file.unlink()

                oss_url = f"oss://{self._oss_client.bucket_name}/{oss_object_name}"
            else:
                await asyncio.to_thread(
                    self._oss_client.upload_file, str(local_path), oss_object_name
                )
                oss_url = f"oss://{self._oss_client.bucket_name}/{oss_object_name}"

            logger.info(f"[AFSv3] Saved to OSS: {oss_url}")
            return oss_url, len(content_bytes)

        except Exception as e:
            logger.error(f"[AFSv3] OSS upload failed: {e}")
            return f"local://{self.session_id}/{self.goal_id}/{local_path.name}", len(
                content_bytes
            )

    async def _save_to_local(
        self,
        file_key: str,
        content_bytes: bytes,
        extension: str = "txt",
    ) -> tuple[str, int]:
        """保存到本地文件系统或 sandbox."""
        import asyncio

        self._ensure_dir()

        safe_key = self._sanitize_filename(file_key)
        if "." not in safe_key:
            safe_key = f"{safe_key}.{extension}"

        local_path = self.base_path / safe_key

        if self.sandbox:
            work_dir = getattr(self.sandbox, "work_dir", "/home/ubuntu")
            sandbox_path = f"{work_dir}/{self.goal_id}/{safe_key}"
            await self.sandbox.file.create(sandbox_path, content_bytes.decode("utf-8"))
            logger.info(f"[AFSv3] Saved to sandbox: {sandbox_path}")
        else:
            await asyncio.to_thread(local_path.write_bytes, content_bytes)

        local_uri = f"local://{local_path}"
        logger.info(f"[AFSv3] Saved to local: {local_uri}")
        return local_uri, len(content_bytes)

    async def _read_from_storage(self, storage_uri: str) -> Optional[bytes]:
        """从存储系统读取文件."""
        # 优先使用 FileStorageClient
        if self._file_storage_client:
            return await self._read_with_file_storage_client(storage_uri)

        # 其次使用 OSS 客户端
        if self._oss_client and storage_uri.startswith("oss://"):
            return await self._read_with_oss_client(storage_uri)

        # 本地存储
        return await self._read_from_local(storage_uri)

    async def _read_with_file_storage_client(self, uri: str) -> Optional[bytes]:
        """使用 FileStorageClient 读取文件."""
        import asyncio

        try:
            file_data, metadata = await asyncio.to_thread(
                self._file_storage_client.get_file, uri
            )
            content = file_data.read()
            return content if isinstance(content, bytes) else content.encode("utf-8")
        except Exception as e:
            logger.error(f"[AFSv3] Failed to read with FileStorageClient: {e}")
            return None

    async def _read_with_oss_client(self, oss_url: str) -> Optional[bytes]:
        """使用 OSS 客户端读取文件."""
        import asyncio

        if not self._oss_client or oss_url.startswith("local://"):
            return None

        try:
            if oss_url.startswith(f"oss://{self._oss_client.bucket_name}/"):
                oss_object_name = oss_url.replace(
                    f"oss://{self._oss_client.bucket_name}/", ""
                )
            else:
                return None

            temp_dir = Path("/tmp") / self.session_id / self.goal_id
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file = temp_dir / "download_temp"

            await asyncio.to_thread(
                self._oss_client.download_file, oss_object_name, str(temp_file)
            )

            content = await asyncio.to_thread(temp_file.read_bytes)
            temp_file.unlink()
            return content

        except Exception as e:
            logger.error(f"[AFSv3] OSS download failed: {e}")
            return None

    async def _read_from_local(self, uri: str) -> Optional[bytes]:
        """从本地文件系统读取."""
        import asyncio

        try:
            if uri.startswith("local://"):
                path = uri.replace("local://", "")
            else:
                path = uri

            local_path = Path(path)

            if self.sandbox:
                file_info = await self.sandbox.file.read(str(local_path))
                return file_info.content.encode("utf-8") if file_info.content else None
            else:
                if await asyncio.to_thread(local_path.exists):
                    return await asyncio.to_thread(local_path.read_bytes)
                return None
        except Exception as e:
            logger.error(f"[AFSv3] Failed to read local file: {e}")
            return None

    # ==================== URL 生成 ====================

    async def _generate_preview_url(
        self, storage_uri: str, mime_type: str
    ) -> Optional[str]:
        """生成预览URL."""
        # 使用 FileStorageClient 生成 URL
        if self._file_storage_client:
            return await self._generate_url_with_file_storage_client(
                storage_uri, mime_type
            )

        # 使用 OSS 客户端生成 URL（兼容模式）
        if self._oss_client and storage_uri.startswith("oss://"):
            return await self._generate_oss_preview_url(storage_uri, mime_type)

        # 本地文件无法生成预览URL
        return None

    async def _generate_download_url(
        self, storage_uri: str, file_name: str
    ) -> Optional[str]:
        """生成下载URL."""
        # 使用 FileStorageClient 生成 URL
        if self._file_storage_client:
            return await self._generate_url_with_file_storage_client(
                storage_uri, file_name=file_name
            )

        # 使用 OSS 客户端生成 URL（兼容模式）
        if self._oss_client and storage_uri.startswith("oss://"):
            return await self._generate_oss_download_url(storage_uri, file_name)

        # 本地文件返回本地路径
        return storage_uri if storage_uri.startswith("local://") else None

    async def _generate_url_with_file_storage_client(
        self,
        uri: str,
        mime_type: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> Optional[str]:
        """使用 FileStorageClient 生成公开URL."""
        import asyncio

        try:
            # 生成公开 URL（FileStorageClient 会自动处理代理或直链）
            url = await asyncio.to_thread(
                self._file_storage_client.get_public_url,
                uri,
                expire=3600,  # 1小时有效期
            )
            return url
        except Exception as e:
            logger.warning(
                f"[AFSv3] Failed to generate URL with FileStorageClient: {e}"
            )
            return uri

    async def _generate_oss_preview_url(
        self, oss_url: str, mime_type: str
    ) -> Optional[str]:
        """使用 OSS 客户端生成预览URL（兼容模式）."""
        if not self._oss_client:
            return None

        # 检查是否可预览
        previewable_types = [
            "text/plain",
            "text/html",
            "text/markdown",
            "text/csv",
            "application/json",
            "application/pdf",
            "image/",
        ]

        is_previewable = any(
            mime_type.startswith(t) if t.endswith("/") else mime_type == t
            for t in previewable_types
        )

        if not is_previewable:
            return None

        try:
            import asyncio

            return await asyncio.to_thread(
                self._oss_client.generate_preview_url, oss_url, expires=3600
            )
        except Exception:
            return oss_url

    async def _generate_oss_download_url(
        self, oss_url: str, file_name: str
    ) -> Optional[str]:
        """使用 OSS 客户端生成下载URL（兼容模式）."""
        if not self._oss_client:
            return None

        try:
            import asyncio

            return await asyncio.to_thread(
                self._oss_client.generate_download_url, oss_url, file_name, expires=3600
            )
        except Exception:
            return oss_url

    # ==================== 核心文件操作 ====================

    async def save_file(
        self,
        file_key: str,
        data: Any,
        file_type: Union[str, FileType],
        extension: str = "txt",
        file_name: Optional[str] = None,
        created_by: str = "",
        task_id: Optional[str] = None,
        message_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        is_conclusion: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentFileMetadata:
        """保存文件（核心方法）.

        流程:
        1. 计算哈希检查去重
        2. 保存到存储系统（FileStorageClient、OSS或本地）
        3. 创建元数据
        4. 保存到 FileMetadataStorage
        5. 生成预览/下载 URL

        Returns:
            文件元数据对象
        """
        # 1. 计算哈希
        content_hash = self._compute_hash(data)

        # 2. 检查去重
        if content_hash in self._hash_index:
            existing_key = self._hash_index[content_hash]
            existing_metadata = await self.metadata_storage.get_file_by_key(
                self.conv_id, existing_key
            )
            if existing_metadata:
                logger.info(
                    f"[AFSv3] Deduplication: '{file_key}' matches existing '{existing_key}'"
                )
                return existing_metadata

        # 3. 准备内容
        if isinstance(data, (dict, list)):
            content_str = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            content_str = str(data)

        actual_file_name = file_name or (
            file_key if "." in file_key else f"{file_key}.{extension}"
        )
        mime_type = self._get_mime_type(actual_file_name)

        # 4. 保存到存储系统
        storage_uri, file_size = await self._save_to_storage(
            file_key, content_str, extension, actual_file_name
        )

        # 5. 获取本地路径（用于缓存）
        local_path = self._get_file_path(file_key, extension)

        # 6. 确定文件类型
        actual_file_type = (
            FileType.CONCLUSION.value
            if is_conclusion
            else (file_type.value if isinstance(file_type, FileType) else file_type)
        )

        # 7. 生成预览和下载URL
        preview_url = await self._generate_preview_url(storage_uri, mime_type)
        download_url = await self._generate_download_url(storage_uri, actual_file_name)

        # 8. 创建元数据对象
        file_metadata = AgentFileMetadata(
            file_id=str(uuid.uuid4()),
            conv_id=self.conv_id,
            conv_session_id=self.session_id,
            file_key=file_key,
            file_name=actual_file_name,
            file_type=actual_file_type,
            file_size=file_size,
            local_path=str(local_path),
            oss_url=storage_uri
            if storage_uri.startswith(("oss://", "derisk-fs://"))
            else None,
            preview_url=preview_url,
            download_url=download_url,
            content_hash=content_hash,
            status=FileStatus.COMPLETED.value,
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7),
            metadata=metadata or {},
            mime_type=mime_type,
            task_id=task_id,
            message_id=message_id,
            tool_name=tool_name,
        )

        # 9. 保存到元数据存储
        await self.metadata_storage.save_file_metadata(file_metadata)

        # 10. 更新哈希索引
        self._hash_index[content_hash] = file_key

        logger.info(
            f"[AFSv3] Saved file: {file_key} ({file_size} bytes) -> {storage_uri}"
        )

        # 11. 如果是结论文件，推送d-attach
        if is_conclusion or actual_file_type == FileType.CONCLUSION.value:
            await self._push_file_attach(file_metadata)

        return file_metadata

    async def save_binary_file(
        self,
        file_key: str,
        data: bytes,
        file_type: Union[str, FileType],
        extension: str = "bin",
        file_name: Optional[str] = None,
        created_by: str = "",
        task_id: Optional[str] = None,
        message_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        is_deliverable: bool = False,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentFileMetadata:
        """保存二进制文件（如图片、视频等）.

        与 save_file() 的区别: 直接接收 bytes 数据，不做 str() 转换，
        适用于图片、视频等二进制内容。

        Args:
            file_key: 文件标识
            data: 二进制文件内容
            file_type: 文件类型
            extension: 文件扩展名
            file_name: 文件名（可选）
            created_by: 创建者
            task_id: 任务ID
            message_id: 消息ID
            tool_name: 工具名称
            is_deliverable: 是否为交付物
            description: 文件描述
            meta 额外元数据

        Returns:
            文件元数据对象
        """
        # 1. 计算哈希
        content_hash = hashlib.md5(data).hexdigest()

        # 2. 检查去重
        if content_hash in self._hash_index:
            existing_key = self._hash_index[content_hash]
            existing_metadata = await self.metadata_storage.get_file_by_key(
                self.conv_id, existing_key
            )
            if existing_metadata:
                logger.info(
                    f"[AFSv3] Binary dedup: '{file_key}' matches '{existing_key}'"
                )
                return existing_metadata

        # 3. 准备文件名和 MIME 类型
        actual_file_name = file_name or (
            file_key if "." in file_key else f"{file_key}.{extension}"
        )
        mime_type = self._get_mime_type(actual_file_name)

        # 4. 直接保存 bytes 到存储系统
        storage_uri, file_size = await self._save_to_storage(
            file_key, data, extension, actual_file_name
        )

        # 5. 获取本地路径
        local_path = self._get_file_path(file_key, extension)

        # 6. 确定文件类型
        actual_file_type = (
            file_type.value if isinstance(file_type, FileType) else file_type
        )

        # 7. 生成 URL
        preview_url = await self._generate_preview_url(storage_uri, mime_type)
        download_url = await self._generate_download_url(storage_uri, actual_file_name)

        # 8. 构建元数据
        file_metadata_dict = metadata or {}
        if description:
            file_metadata_dict["description"] = description

        file_metadata = AgentFileMetadata(
            file_id=str(uuid.uuid4()),
            conv_id=self.conv_id,
            conv_session_id=self.session_id,
            file_key=file_key,
            file_name=actual_file_name,
            file_type=actual_file_type,
            file_size=file_size,
            local_path=str(local_path),
            oss_url=storage_uri
            if storage_uri.startswith(("oss://", "derisk-fs://"))
            else None,
            preview_url=preview_url,
            download_url=download_url,
            content_hash=content_hash,
            status=FileStatus.COMPLETED.value,
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7),
            metadata=file_metadata_dict,
            mime_type=mime_type,
            task_id=task_id,
            message_id=message_id,
            tool_name=tool_name,
        )

        # 9. 保存元数据
        await self.metadata_storage.save_file_metadata(file_metadata)

        # 10. 更新哈希索引
        self._hash_index[content_hash] = file_key

        logger.info(
            f"[AFSv3] Saved binary file: {file_key} ({file_size} bytes) -> {storage_uri}"
        )

        # 11. 如果是交付物，推送 d-attach
        if is_deliverable:
            await self._push_file_attach(file_metadata)

        return file_metadata

    async def read_file(self, file_key: str) -> Optional[str]:
        """读取文件内容.

        流程:
        1. 从 FileMetadataStorage 获取元数据
        2. 从存储系统读取文件内容

        Returns:
            文件内容，不存在返回None
        """
        # 1. 获取元数据
        metadata = await self.metadata_storage.get_file_by_key(self.conv_id, file_key)
        if not metadata:
            logger.warning(f"[AFSv3] File not found: {file_key}")
            return None

        # 2. 确定存储 URI
        storage_uri = (
            metadata.oss_url if metadata.oss_url else f"local://{metadata.local_path}"
        )

        # 3. 读取内容
        content_bytes = await self._read_from_storage(storage_uri)

        if content_bytes is None:
            logger.warning(f"[AFSv3] Failed to read file: {file_key}")
            return None

        try:
            return content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # 二进制文件，返回 base64 或保持字节
            return content_bytes.decode("utf-8", errors="replace")

    async def delete_file(self, file_key: str) -> bool:
        """删除文件.

        删除元数据和存储系统中的文件（如果支持）
        """
        # 1. 获取元数据
        metadata = await self.metadata_storage.get_file_by_key(self.conv_id, file_key)
        if not metadata:
            return False

        # 2. 从存储系统删除（如果支持）
        if self._file_storage_client and metadata.oss_url:
            try:
                import asyncio

                await asyncio.to_thread(
                    self._file_storage_client.delete_file, metadata.oss_url
                )
            except Exception as e:
                logger.warning(f"[AFSv3] Failed to delete from storage: {e}")

        # 3. 删除本地文件
        try:
            local_path = Path(metadata.local_path)
            if self.sandbox:
                await self.sandbox.file.remove(str(local_path))
            else:
                import asyncio

                if await asyncio.to_thread(local_path.exists):
                    await asyncio.to_thread(local_path.unlink)
        except Exception as e:
            logger.warning(f"[AFSv3] Failed to delete local file: {e}")

        # 4. 删除元数据
        await self.metadata_storage.delete_file(self.conv_id, file_key)

        # 5. 从哈希索引移除
        if metadata.content_hash and metadata.content_hash in self._hash_index:
            del self._hash_index[metadata.content_hash]

        logger.info(f"[AFSv3] Deleted file: {file_key}")
        return True

    async def get_file_info(self, file_key: str) -> Optional[AgentFileMetadata]:
        """获取文件元数据."""
        return await self.metadata_storage.get_file_by_key(self.conv_id, file_key)

    async def list_files(
        self,
        file_type: Optional[Union[str, FileType]] = None,
        category: Optional[FileCategory] = None,
    ) -> List[AgentFileMetadata]:
        """列出文件.

        Args:
            file_type: 文件类型过滤
            category: 文件分类过滤

        Returns:
            文件元数据列表
        """
        files = await self.metadata_storage.list_files(self.conv_id, file_type)

        if category:
            files = [
                f for f in files if self._get_file_category(f.file_type) == category
            ]

        return files

    def _get_file_category(self, file_type: str) -> FileCategory:
        """获取文件分类."""
        category_map = {
            FileType.CONCLUSION.value: FileCategory.CONCLUSION,
            FileType.TOOL_OUTPUT.value: FileCategory.TOOL_OUTPUT,
            FileType.TRUNCATED_OUTPUT.value: FileCategory.TOOL_OUTPUT,
            FileType.KANBAN.value: FileCategory.WORKSPACE,
            FileType.DELIVERABLE.value: FileCategory.WORKSPACE,
        }
        return category_map.get(file_type, FileCategory.RESOURCE)

    # ==================== 便捷方法 ====================

    async def save_tool_output(
        self,
        tool_name: str,
        output: Any,
        file_key: Optional[str] = None,
        extension: str = "log",
    ) -> AgentFileMetadata:
        """保存工具输出."""
        key = (
            file_key or f"tool_{tool_name}_{int(datetime.utcnow().timestamp() * 1000)}"
        )
        return await self.save_file(
            file_key=key,
            data=output,
            file_type=FileType.TOOL_OUTPUT,
            extension=extension,
            file_name=f"{tool_name}_output.{extension}",
            tool_name=tool_name,
        )

    async def save_conclusion(
        self,
        data: Any,
        file_name: str,
        extension: str = "md",
        created_by: str = "",
        task_id: Optional[str] = None,
    ) -> AgentFileMetadata:
        """保存结论文件（自动推送d-attach）."""
        file_key = f"conclusion_{int(datetime.utcnow().timestamp() * 1000)}_{file_name}"
        return await self.save_file(
            file_key=file_key,
            data=data,
            file_type=FileType.CONCLUSION,
            extension=extension,
            file_name=file_name,
            created_by=created_by,
            task_id=task_id,
            is_conclusion=True,
        )

    async def save_truncated_output(
        self,
        original_content: str,
        tool_name: str,
        truncated_info: Dict[str, Any],
    ) -> AgentFileMetadata:
        """保存截断输出."""
        file_key = f"truncated_{tool_name}_{int(datetime.utcnow().timestamp() * 1000)}"

        data = {
            "tool_name": tool_name,
            "truncated_info": truncated_info,
            "original_preview": original_content[:1000]
            if len(original_content) > 1000
            else original_content,
            "saved_at": datetime.utcnow().isoformat(),
        }

        return await self.save_file(
            file_key=file_key,
            data=data,
            file_type=FileType.TRUNCATED_OUTPUT,
            extension="json",
            file_name=f"{tool_name}_full_output.json",
            tool_name=tool_name,
        )

    # ==================== 可视化交互 ====================

    async def _push_file_attach(self, file_metadata: AgentFileMetadata):
        """推送d-attach组件到前端."""
        from derisk.agent.core.memory.gpts import GptsMemory

        if not isinstance(self.metadata_storage, GptsMemory):
            return

        from derisk.vis import Vis

        try:
            attach_content = file_metadata.to_attach_content()
            vis_attach = Vis.of("d-attach")
            output = vis_attach.sync_display(content=attach_content)

            await self.metadata_storage.push_message(
                self.conv_id,
                stream_msg={
                    "type": "file_attach",
                    "content": output,
                    "file_id": file_metadata.file_id,
                    "file_name": file_metadata.file_name,
                },
            )
            logger.info(f"[AFSv3] Pushed d-attach for file: {file_metadata.file_name}")
        except Exception as e:
            logger.error(f"[AFSv3] Failed to push d-attach: {e}")

    async def push_conclusion_files(self):
        """推送所有结论文件到前端."""
        conclusion_files = await self.metadata_storage.get_conclusion_files(
            self.conv_id
        )
        for file_metadata in conclusion_files:
            await self._push_file_attach(file_metadata)

    async def collect_delivery_files(
        self, file_types: Optional[List[Union[str, FileType]]] = None
    ) -> List[Dict[str, Any]]:
        """收集用于交付的文件列表.

        适用于terminate时收集所有相关文件进行交付。
        默认收集所有对话过程中产生的文件，包括：
        - CONCLUSION: 结论文件
        - DELIVERABLE: 交付物
        - TRUNCATED_OUTPUT: 工具大结果归档
        - TOOL_OUTPUT: 工具输出文件
        - WRITE_FILE: write工具创建的文件

        Returns:
            文件信息字典列表
        """
        if file_types is None:
            file_types = [
                FileType.CONCLUSION,
                FileType.DELIVERABLE,
                FileType.TRUNCATED_OUTPUT,
                FileType.TOOL_OUTPUT,
                FileType.WRITE_FILE,
            ]

        all_files = []
        for file_type in file_types:
            files = await self.metadata_storage.list_files(self.conv_id, file_type)
            all_files.extend(files)

        # 去重
        seen_ids = set()
        unique_files = []
        for f in all_files:
            if f.file_id not in seen_ids:
                seen_ids.add(f.file_id)
                unique_files.append(f)

        # 转换为字典格式
        result = []
        for f in unique_files:
            result.append(
                {
                    "file_id": f.file_id,
                    "file_name": f.file_name,
                    "file_type": f.file_type,
                    "file_size": f.file_size,
                    "oss_url": f.oss_url,
                    "preview_url": f.preview_url,
                    "download_url": f.download_url,
                    "mime_type": f.mime_type,
                    "created_at": f.created_at.isoformat()
                    if isinstance(f.created_at, datetime)
                    else f.created_at,
                    "task_id": f.task_id,
                    "description": f.metadata.get("description")
                    if f.metadata
                    else None,
                    "object_path": f.metadata.get("object_path")
                    if f.metadata
                    else None,
                }
            )

        # DEBUG: log each delivery file's URL fields
        for r in result:
            logger.info(
                f"[AFSv3] delivery file detail: file_name={r.get('file_name')}, "
                f"file_type={r.get('file_type')}, "
                f"oss_url={r.get('oss_url')}, "
                f"preview_url={r.get('preview_url')}, "
                f"download_url={r.get('download_url')}, "
                f"object_path={r.get('object_path')}"
            )
        logger.info(f"[AFSv3] Collected {len(result)} delivery files")
        return result

    # ==================== 会话恢复 ====================

    async def sync_workspace(self):
        """同步工作区（恢复时调用）.

        流程:
        1. 从 FileMetadataStorage 加载所有文件元数据
        2. 重建哈希索引
        3. 检查文件可访问性（不强制下载，按需加载）
        """
        logger.info(f"[AFSv3] Syncing workspace for {self.conv_id}")

        # 1. 加载元数据
        files = await self.metadata_storage.list_files(self.conv_id)

        # 2. 重建哈希索引
        for metadata in files:
            if metadata.content_hash:
                self._hash_index[metadata.content_hash] = metadata.file_key

        logger.info(f"[AFSv3] Workspace synced: {len(files)} files ready")

    # ==================== 工具方法 ====================

    def get_storage_type(self) -> str:
        """获取当前使用的存储类型.

        Returns:
            "file_storage_client" | "oss" | "local"
        """
        if self._file_storage_client:
            return "file_storage_client"
        elif self._oss_client:
            return "oss"
        else:
            return "local"

    async def get_file_public_url(
        self, file_key: str, expire: int = 3600
    ) -> Optional[str]:
        """获取文件的公开URL.

        Args:
            file_key: 文件key
            expire: URL 有效期（秒）

        Returns:
            公开URL，如果不支持则返回None
        """
        metadata = await self.get_file_info(file_key)
        if not metadata:
            return None

        storage_uri = (
            metadata.oss_url if metadata.oss_url else f"local://{metadata.local_path}"
        )

        if self._file_storage_client:
            import asyncio

            try:
                return await asyncio.to_thread(
                    self._file_storage_client.get_public_url, storage_uri, expire
                )
            except Exception as e:
                logger.warning(f"[AFSv3] Failed to get public URL: {e}")

        return metadata.download_url or metadata.preview_url

    # ==================== 沙箱文件统一管理（新增） ====================

    def _get_env_stage(self) -> str:
        """获取环境阶段（dev/prod）."""
        import os

        env = (os.getenv("SERVER_ENV") or "local").lower()
        return "dev" if env in {"local", "dev"} else "prod"

    def _get_app_name(self) -> str:
        """获取应用名称."""
        import os

        return os.getenv("app_name", "openderisk")

    def _generate_object_key(
        self,
        file_name: str,
        sandbox_path: Optional[str] = None,
    ) -> str:
        """生成 Object Key（不含 bucket 前缀）.

        格式: {env}/{app}/conversations/{conv_id}/{goal_id?}/{file_name}
        示例: dev/openderisk/conversations/conv-123/goal-1/report.md

        注意: bucket 前缀由 write_chat_file 或 FileStorageClient 添加，
        这里只生成相对路径。

        Args:
            file_name: 文件名
            sandbox_path: 沙箱路径（可选，用于调试日志）

        Returns:
            Object key（不含 bucket 前缀）
        """
        env = self._get_env_stage()
        app = self._get_app_name()

        parts = [env, app, "conversations", self.conv_id]

        if self.goal_id and self.goal_id != "default":
            parts.append(self.goal_id)

        parts.append(file_name)

        object_key = "/".join(parts)
        logger.debug(
            f"[AFSv3] Generated object_key: {object_key} "
            f"(sandbox_path={sandbox_path}, file_name={file_name})"
        )
        return object_key

    def _extract_object_path_from_url(self, url: Optional[str]) -> Optional[str]:
        """从 OSS URL 中提取 object path（去除 OSS 物理 bucket 名）.

        URL 格式: https://{oss-bucket}.{endpoint}/{object_path}?...
        例如: https://antsys-antdbgpt-dev.oss.../agent_files/dev/openderisk/...?...
        返回: agent_files/dev/openderisk/...

        Args:
            url: OSS 预签名 URL

        Returns:
            object_path（不含 OSS 物理 bucket 名），如果 URL 无效则返回 None
        """
        if not url or not url.startswith("https://"):
            return None

        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            path = parsed.path
            if path.startswith("/"):
                path = path[1:]
            return path
        except Exception as e:
            logger.warning(f"[AFSv3] Failed to extract object_path from URL: {e}")
            return None

    async def _check_sandbox_file_exists(
        self,
        sandbox_path: str,
        content_hash: Optional[str] = None,
    ) -> Optional[AgentFileMetadata]:
        """检查沙箱文件是否已转存（去重检查）.

        检查逻辑:
        1. 如果提供了 content_hash，通过哈希索引检查
        2. 通过 sandbox_path 元数据检查

        Args:
            sandbox_path: 沙箱文件路径
            content_hash: 内容哈希（可选）

        Returns:
            如果已存在返回已有的元数据，否则返回 None
        """
        # 1. 通过内容哈希检查
        if content_hash and content_hash in self._hash_index:
            existing_key = self._hash_index[content_hash]
            existing_metadata = await self.metadata_storage.get_file_by_key(
                self.conv_id, existing_key
            )
            if existing_metadata:
                logger.info(
                    f"[AFSv3] Dedup by content_hash: sandbox_path={sandbox_path}, "
                    f"existing_key={existing_key}"
                )
                return existing_metadata

        # 2. 通过 sandbox_path 元数据检查
        # 查找是否有相同 sandbox_path 的文件
        all_files = await self.metadata_storage.list_files(self.conv_id)
        for f in all_files:
            if f.metadata and f.metadata.get("sandbox_path") == sandbox_path:
                logger.info(
                    f"[AFSv3] Dedup by sandbox_path: {sandbox_path}, "
                    f"existing_file_id={f.file_id}"
                )
                return f

        return None

    async def save_file_from_sandbox(
        self,
        sandbox_path: str,
        file_type: Union[str, FileType],
        file_name: Optional[str] = None,
        file_content: Optional[Union[str, bytes]] = None,
        is_deliverable: bool = True,
        description: Optional[str] = None,
        tool_name: Optional[str] = None,
        task_id: Optional[str] = None,
        message_id: Optional[str] = None,
        created_by: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentFileMetadata:
        """从沙箱保存文件到OSS并记录元数据（统一入口）.

        这是沙箱工具（create_file, edit_file, deliver_file）的统一文件管理接口。
        职责：
        1. 去重检查（避免重复转存）
        2. 统一 Object Key 生成
        3. 调用 sandbox.file.write_chat_file() 或 upload_to_oss() 执行转存
        4. 记录元数据到 FileMetadataStorage
        5. 返回完整的文件元数据

        Args:
            sandbox_path: 沙箱中文件的绝对路径
            file_type: 文件类型（FileType 枚举或字符串）
            file_name: 文件名（可选，默认从 sandbox_path 提取）
            file_content: 文件内容（可选，如果不提供会从沙箱读取）
            is_deliverable: 是否标记为交付物
            description: 文件描述
            tool_name: 调用工具名称
            task_id: 任务ID
            message_id: 消息ID
            created_by: 创建者
            metadata: 额外的元数据

        Returns:
            AgentFileMetadata: 文件元数据对象
        """
        import os

        # 1. 提取文件名
        actual_file_name = file_name or os.path.basename(sandbox_path)
        file_extension = (
            os.path.splitext(actual_file_name)[1][1:]
            if os.path.splitext(actual_file_name)[1]
            else "txt"
        )

        # 2. 如果没有提供内容，从沙箱读取
        if file_content is None:
            if not self.sandbox:
                raise ValueError(
                    f"Cannot read from sandbox: sandbox not configured. "
                    f"Please provide file_content for {sandbox_path}"
                )
            try:
                file_info = await self.sandbox.file.read(sandbox_path)
                file_content = getattr(file_info, "content", "")
                if not file_content:
                    raise ValueError(f"Empty content from sandbox: {sandbox_path}")
            except Exception as e:
                logger.error(f"[AFSv3] Failed to read from sandbox: {e}")
                raise

        # 3. 计算内容哈希
        content_hash = self._compute_hash(file_content)

        # 4. 去重检查
        existing = await self._check_sandbox_file_exists(sandbox_path, content_hash)
        if existing:
            logger.info(
                f"[AFSv3] File already exists, skipping: sandbox_path={sandbox_path}, "
                f"file_id={existing.file_id}"
            )
            # 更新元数据中的访问时间
            existing.updated_at = datetime.utcnow()
            await self.metadata_storage.save_file_metadata(existing)
            return existing

        # 5. 生成统一的 Object Key（不含 bucket 前缀）
        # 格式: {env}/{app}/conversations/{conv_id}/{file_name}
        object_key = self._generate_object_key(actual_file_name, sandbox_path)

        # 6. 执行 OSS 转存
        oss_url = None
        oss_object_path = None

        logger.info(
            f"[AFSv3] save_file_from_sandbox: sandbox={self.sandbox is not None}, "
            f"file_storage_client={self._file_storage_client is not None}"
        )

        if self.sandbox and hasattr(self.sandbox.file, "write_chat_file"):
            try:
                import asyncio

                file_info = await self.sandbox.file.write_chat_file(
                    conversation_id=self.conv_id,
                    path=sandbox_path,
                    data=file_content,
                    overwrite=True,
                )

                logger.info(
                    f"[AFSv3] write_chat_file result: "
                    f"file_info={file_info is not None}, "
                    f"oss_info={file_info.oss_info if file_info else None}, "
                    f"temp_url={file_info.oss_info.temp_url if file_info and file_info.oss_info else None}"
                )
                if file_info and file_info.oss_info and file_info.oss_info.temp_url:
                    oss_url = file_info.oss_info.temp_url
                    oss_object_path = self._extract_object_path_from_url(oss_url)
                    logger.info(
                        f"[AFSv3] OSS transfer via write_chat_file: "
                        f"sandbox_path={sandbox_path}, "
                        f"oss_url={oss_url[:80] if oss_url else None}..., "
                        f"extracted_object_path={oss_object_path}"
                    )
            except Exception as e:
                logger.warning(f"[AFSv3] write_chat_file failed, trying fallback: {e}")

        # 7. 如果 write_chat_file 失败，尝试使用 FileStorageClient
        if not oss_url and self._file_storage_client:
            try:
                storage_uri, file_size = await self._save_to_storage(
                    file_key=actual_file_name,
                    data=file_content,
                    extension=file_extension,
                    file_name=actual_file_name,
                )
                if storage_uri.startswith(("https://", "derisk-fs://")):
                    oss_url = storage_uri
                    if storage_uri.startswith("https://"):
                        oss_object_path = self._extract_object_path_from_url(oss_url)
                logger.info(
                    f"[AFSv3] OSS transfer via FileStorageClient: "
                    f"object_key={object_key}, extracted_object_path={oss_object_path}"
                )
            except Exception as e:
                logger.warning(f"[AFSv3] FileStorageClient save failed: {e}")

        # 8. 如果仍然没有 URL，记录警告
        if not oss_url:
            logger.warning(
                f"[AFSv3] No OSS URL generated for {sandbox_path}. "
                f"File saved to metadata only, may not be accessible via web."
            )

        # 9. 准备元数据
        mime_type = self._get_mime_type(actual_file_name)
        actual_file_type = (
            file_type.value if isinstance(file_type, FileType) else file_type
        )

        # 合并元数据
        merged_metadata = metadata or {}
        merged_metadata.update(
            {
                "sandbox_path": sandbox_path,
                "is_deliverable": is_deliverable,
                "description": description or "",
                "oss_url": oss_url,
                "content_hash": content_hash,
            }
        )

        # 10. 生成预览和下载 URL
        preview_url = None
        download_url = None
        if oss_url:
            if oss_url.startswith("https://"):
                preview_url = oss_url
                download_url = oss_url
            elif self._file_storage_client:
                preview_url = await self._generate_preview_url(oss_url, mime_type)
                download_url = await self._generate_download_url(
                    oss_url, actual_file_name
                )

        # 11. 计算文件大小
        file_size = 0
        if isinstance(file_content, bytes):
            file_size = len(file_content)
        elif file_content:
            file_size = len(file_content.encode("utf-8"))

        # 12. 创建元数据对象
        # Store object_path in metadata since AgentFileMetadata doesn't have this attribute
        if oss_object_path:
            merged_metadata["object_path"] = oss_object_path

        file_metadata = AgentFileMetadata(
            file_id=str(uuid.uuid4()),
            conv_id=self.conv_id,
            conv_session_id=self.session_id,
            file_key=actual_file_name,
            file_name=actual_file_name,
            file_type=actual_file_type,
            file_size=file_size,
            local_path=sandbox_path,
            oss_url=oss_url,
            preview_url=preview_url,
            download_url=download_url,
            content_hash=content_hash,
            status=FileStatus.COMPLETED.value,
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7),
            metadata=merged_metadata,
            mime_type=mime_type,
            task_id=task_id,
            message_id=message_id,
            tool_name=tool_name,
        )

        # 13. 保存到元数据存储
        await self.metadata_storage.save_file_metadata(file_metadata)

        # 14. 更新哈希索引
        self._hash_index[content_hash] = actual_file_name

        logger.info(
            f"[AFSv3] Saved file from sandbox: {sandbox_path} -> {oss_url or 'metadata only'}"
        )

        return file_metadata

    async def update_file_from_sandbox(
        self,
        sandbox_path: str,
        file_content: Optional[Union[str, bytes]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AgentFileMetadata]:
        """更新沙箱文件到存储（编辑文件时使用）.

        Args:
            sandbox_path: 沙箱中文件的绝对路径
            file_content: 文件内容（可选，如果不提供会从沙箱读取）
            metadata: 更新的元数据

        Returns:
            更新后的文件元数据对象
        """
        import os

        file_name = os.path.basename(sandbox_path)

        # 1. 检查是否已存在元数据
        existing = await self.metadata_storage.get_file_by_key(self.conv_id, file_name)

        # 2. 如果没有提供内容，从沙箱读取
        if file_content is None:
            if self.sandbox:
                try:
                    file_info = await self.sandbox.file.read(sandbox_path)
                    file_content = getattr(file_info, "content", "")
                except Exception as e:
                    logger.warning(f"[AFSv3] Failed to read from sandbox: {e}")

        # 3. 执行 OSS 更新（重新上传）
        oss_url = None
        oss_object_path = None

        if (
            self.sandbox
            and hasattr(self.sandbox.file, "write_chat_file")
            and file_content
        ):
            try:
                file_info = await self.sandbox.file.write_chat_file(
                    conversation_id=self.conv_id,
                    path=sandbox_path,
                    data=file_content,
                    overwrite=True,
                )

                if file_info and file_info.oss_info and file_info.oss_info.temp_url:
                    oss_url = file_info.oss_info.temp_url
                    oss_object_path = self._extract_object_path_from_url(oss_url)
                    logger.info(
                        f"[AFSv3] Updated file via write_chat_file: "
                        f"sandbox_path={sandbox_path}, oss_url={oss_url[:80] if oss_url else None}..."
                    )
            except Exception as e:
                logger.warning(f"[AFSv3] write_chat_file update failed: {e}")

        # 4. 更新元数据
        if existing:
            existing.updated_at = datetime.utcnow()
            if oss_url:
                existing.oss_url = oss_url
                existing.preview_url = oss_url
                existing.download_url = oss_url
            if metadata:
                if existing.metadata:
                    existing.metadata.update(metadata)
                else:
                    existing.metadata = metadata
            # Store object_path in metadata since AgentFileMetadata doesn't have this attribute
            if oss_object_path:
                if existing.metadata:
                    existing.metadata["object_path"] = oss_object_path
                else:
                    existing.metadata = {"object_path": oss_object_path}
            if file_content:
                existing.file_size = (
                    len(file_content)
                    if isinstance(file_content, bytes)
                    else len(file_content.encode("utf-8"))
                )
                existing.content_hash = self._compute_hash(file_content)

            await self.metadata_storage.save_file_metadata(existing)
            return existing

        # 5. 如果不存在，创建新记录
        if file_content:
            actual_file_type = FileType.DELIVERABLE.value
            if metadata and metadata.get("is_deliverable") is False:
                actual_file_type = FileType.WRITE_FILE.value

            return await self.save_file_from_sandbox(
                sandbox_path=sandbox_path,
                file_type=actual_file_type,
                file_content=file_content,
                is_deliverable=metadata.get("is_deliverable", True)
                if metadata
                else True,
                description=metadata.get("description") if metadata else None,
            )

        return None
