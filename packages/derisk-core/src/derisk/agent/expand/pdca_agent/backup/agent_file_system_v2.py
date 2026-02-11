"""Agent File System (AFS) V2 - 基于FileMetadataStorage接口的实现.

架构设计:
- AgentFileSystem 只负责文件IO操作（本地文件读写 + OSS上传下载）
- 文件元数据存储委托给 FileMetadataStorage 接口
- GptsMemory 作为主要存储实现（带缓存+持久化）
- SimpleFileMetadataStorage 作为轻量级实现（仅内存）

扩展性:
- 通过FileMetadataStorage接口，支持自定义存储实现（数据库/Redis等）
- 不涉及具体存储细节，解耦文件操作与元数据管理
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from derisk.agent.core.memory.gpts import (
    AgentFileMetadata,
    FileMetadataStorage,
    FileType,
    FileStatus,
)
from derisk.agent.core.memory.gpts.file_base import SimpleFileMetadataStorage
from derisk.configs.model_config import DATA_DIR
from derisk.sandbox.base import SandboxBase
from derisk.sandbox.client.file.types import FileInfo

logger = logging.getLogger(__name__)


class FileCategory(Enum):
    """文件分类（用于前端展示分组）."""

    WORKSPACE = "workspace"      # 工作区文件
    TOOL_OUTPUT = "tool_output"  # 工具输出
    CONCLUSION = "conclusion"    # 结论文件
    RESOURCE = "resource"        # 资源文件


class AgentFileSystem:
    """Agent文件系统 V2 - 基于FileMetadataStorage接口.

    职责:
    1. 本地文件IO操作（读写删除）
    2. OSS上传下载操作
    3. URL生成（预览/下载）
    4. 文件内容去重（基于哈希）
    5. d-attach组件推送

    存储:
    - 文件元数据通过FileMetadataStorage接口管理
    - 支持GptsMemory（完整功能）或SimpleFileMetadataStorage（轻量级）

    使用示例:
        # 方式1: 使用GptsMemory（推荐，带缓存+持久化）
        from derisk.agent.core.memory.gpts import GptsMemory
        gpts_memory = GptsMemory()
        afs = AgentFileSystem(
            conv_id="session_001",
            metadata_storage=gpts_memory,
        )

        # 方式2: 使用简单存储（轻量级，无持久化）
        from derisk.agent.core.memory.gpts.file_base import SimpleFileMetadataStorage
        simple_storage = SimpleFileMetadataStorage()
        afs = AgentFileSystem(
            conv_id="session_001",
            metadata_storage=simple_storage,
        )
    """

    def __init__(
        self,
        conv_id: str,
        session_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        base_working_dir: str = str(os.path.join(DATA_DIR, "agent_storage")),
        sandbox: Optional[SandboxBase] = None,
        metadata_storage: Optional[FileMetadataStorage] = None,
        oss_client=None,
    ):
        """初始化Agent文件系统 V2.

        Args:
            conv_id: 会话ID
            session_id: 会话会话ID（用于子任务隔离，默认使用conv_id）
            goal_id: 目标ID（用于任务隔离，默认"default"）
            base_working_dir: 基础工作目录
            sandbox: 沙箱环境（可选）
            metadata_storage: 文件元数据存储接口（可选，默认SimpleFileMetadataStorage）
            oss_client: OSS客户端（可选）
        """
        self.conv_id = conv_id
        self.session_id = session_id or conv_id
        self.goal_id = goal_id or "default"
        self.sandbox = sandbox
        self.metadata_storage = metadata_storage or SimpleFileMetadataStorage()
        self._oss_client = oss_client

        # 构建存储路径
        self.base_path = Path(base_working_dir) / self.session_id / self.goal_id

        # 内容哈希索引（用于去重，仅内存缓存）
        self._hash_index: Dict[str, str] = {}  # content_hash -> file_key

        logger.info(f"[AFSv2] Initialized for conv: {conv_id}, path: {self.base_path}")

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
        return hashlib.md5(content_str.encode('utf-8')).hexdigest()

    def _get_mime_type(self, filename: str) -> str:
        """获取文件MIME类型."""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    def _sanitize_filename(self, key: str) -> str:
        """清理文件名."""
        return "".join([c for c in key if c.isalnum() or c in ('-', '_', '.')])

    # ==================== OSS 操作 ====================

    async def _upload_to_oss(self, local_path: Path) -> str:
        """上传文件到OSS.

        Returns:
            OSS URL
        """
        if not self._oss_client:
            # 模拟OSS URL
            return f"local://chat/{self.session_id}/{self.goal_id}/{local_path.name}"

        try:
            oss_object_name = f"{self.session_id}/{self.goal_id}/{local_path.name}"

            if self.sandbox:
                # 沙箱环境：先下载到本地临时文件，再上传
                temp_dir = Path("/tmp") / self.session_id / self.goal_id
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_file = temp_dir / local_path.name

                file_info = await self.sandbox.file.read(str(local_path))
                if file_info.content:
                    temp_file.write_text(file_info.content, encoding='utf-8')
                    self._oss_client.upload_file(str(temp_file), oss_object_name)
                    temp_file.unlink()

                return f"oss://{self._oss_client.bucket_name}/{oss_object_name}"
            else:
                # 本地文件系统：直接上传
                self._oss_client.upload_file(str(local_path), oss_object_name)
                return f"oss://{self._oss_client.bucket_name}/{oss_object_name}"

        except Exception as e:
            logger.error(f"[AFSv2] OSS upload failed: {e}")
            return f"local://chat/{self.session_id}/{self.goal_id}/{local_path.name}"

    async def _download_from_oss(self, oss_url: str, local_path: Path):
        """从OSS下载文件."""
        if not self._oss_client or oss_url.startswith("local://"):
            return

        try:
            if oss_url.startswith(f"oss://{self._oss_client.bucket_name}/"):
                oss_object_name = oss_url.replace(f"oss://{self._oss_client.bucket_name}/", "")
            else:
                return

            self._ensure_dir()

            if self.sandbox:
                temp_dir = Path("/tmp") / self.session_id / self.goal_id
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_file = temp_dir / local_path.name

                self._oss_client.download_file(oss_object_name, str(temp_file))
                content = temp_file.read_text(encoding='utf-8')
                await self.sandbox.file.create(str(local_path), content)
                temp_file.unlink()
            else:
                self._oss_client.download_file(oss_object_name, str(local_path))

        except Exception as e:
            logger.error(f"[AFSv2] OSS download failed: {e}")

    # ==================== 本地文件操作 ====================

    async def _write_local(self, file_key: str, data: Any, extension: str = "txt") -> Path:
        """写入本地文件.

        Returns:
            本地文件路径
        """
        import asyncio

        self._ensure_dir()

        if '.' in file_key and len(file_key.split('.')[-1]) <= 4:
            safe_key = self._sanitize_filename(file_key)
        else:
            safe_key = f"{self._sanitize_filename(file_key)}.{extension}"

        local_path = self.base_path / safe_key

        if isinstance(data, (dict, list)):
            content_str = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            content_str = str(data)

        if self.sandbox:
            await self.sandbox.file.create(str(local_path), content_str)
        else:
            await asyncio.to_thread(local_path.write_text, content_str, encoding='utf-8')

        return local_path

    async def _read_local(self, local_path: Path) -> Optional[str]:
        """读取本地文件."""
        import asyncio

        if self.sandbox:
            try:
                file_info = await self.sandbox.file.read(str(local_path))
                return file_info.content
            except Exception as e:
                logger.error(f"[AFSv2] Failed to read from sandbox: {e}")
                return None
        else:
            try:
                if not await asyncio.to_thread(local_path.exists):
                    return None
                return await asyncio.to_thread(local_path.read_text, encoding='utf-8')
            except Exception as e:
                logger.error(f"[AFSv2] Failed to read local file: {e}")
                return None

    async def _delete_local(self, local_path: Path) -> bool:
        """删除本地文件."""
        import asyncio

        try:
            if self.sandbox:
                await self.sandbox.file.remove(str(local_path))
            else:
                if await asyncio.to_thread(local_path.exists):
                    await asyncio.to_thread(local_path.unlink)
            return True
        except Exception as e:
            logger.warning(f"[AFSv2] Failed to delete local file: {e}")
            return False

    # ==================== URL 生成 ====================

    async def _generate_preview_url(self, oss_url: str, mime_type: str) -> Optional[str]:
        """生成预览URL."""
        if not self._oss_client:
            return None

        previewable_types = ['text/', 'image/', 'application/pdf', 'application/json']
        if not any(mime_type.startswith(t.rstrip('/')) if t.endswith('/') else mime_type == t
                   for t in previewable_types):
            return None

        try:
            return self._oss_client.generate_preview_url(oss_url, expires=3600)
        except Exception:
            return oss_url

    async def _generate_download_url(self, oss_url: str, file_name: str) -> Optional[str]:
        """生成下载URL."""
        if not self._oss_client:
            return None

        try:
            return self._oss_client.generate_download_url(oss_url, file_name, expires=3600)
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
        2. 写入本地文件
        3. 上传到OSS
        4. 创建元数据
        5. 保存到FileMetadataStorage

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
                logger.info(f"[AFSv2] Deduplication: '{file_key}' matches existing '{existing_key}'")
                return existing_metadata

        # 3. 写入本地文件
        local_path = await self._write_local(file_key, data, extension)

        # 4. 上传到OSS
        oss_url = await self._upload_to_oss(local_path)

        # 5. 准备文件信息
        file_size = len(data.encode('utf-8')) if isinstance(data, str) else len(str(data).encode('utf-8'))
        actual_file_name = file_name or local_path.name
        mime_type = self._get_mime_type(actual_file_name)
        file_id = str(uuid.uuid4())

        # 确定文件类型
        actual_file_type = FileType.CONCLUSION.value if is_conclusion else (
            file_type.value if isinstance(file_type, FileType) else file_type
        )

        # 6. 创建元数据对象
        file_metadata = AgentFileMetadata(
            file_id=file_id,
            conv_id=self.conv_id,
            conv_session_id=self.session_id,
            file_key=file_key,
            file_name=actual_file_name,
            file_type=actual_file_type,
            file_size=file_size,
            local_path=str(local_path),
            oss_url=oss_url,
            preview_url=await self._generate_preview_url(oss_url, mime_type),
            download_url=await self._generate_download_url(oss_url, actual_file_name),
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

        # 7. 保存到存储
        await self.metadata_storage.save_file_metadata(file_metadata)

        # 8. 更新哈希索引
        self._hash_index[content_hash] = file_key

        logger.info(f"[AFSv2] Saved file: {file_key} ({file_size} bytes) -> {oss_url}")

        # 9. 如果是结论文件，推送d-attach
        if is_conclusion or actual_file_type == FileType.CONCLUSION.value:
            await self._push_file_attach(file_metadata)

        return file_metadata

    async def read_file(self, file_key: str) -> Optional[str]:
        """读取文件内容.

        流程:
        1. 从FileMetadataStorage获取元数据
        2. 读取本地文件（如果不存在则从OSS下载）

        Returns:
            文件内容，不存在返回None
        """
        # 1. 获取元数据
        metadata = await self.metadata_storage.get_file_by_key(self.conv_id, file_key)
        if not metadata:
            logger.warning(f"[AFSv2] File not found: {file_key}")
            return None

        local_path = Path(metadata.local_path)

        # 2. 检查本地文件是否存在
        content = await self._read_local(local_path)

        # 3. 如果本地不存在，从OSS下载
        if content is None and metadata.oss_url:
            await self._download_from_oss(metadata.oss_url, local_path)
            content = await self._read_local(local_path)

        return content

    async def delete_file(self, file_key: str) -> bool:
        """删除文件.

        删除本地文件和元数据（不处理OSS文件）
        """
        # 1. 获取元数据
        metadata = await self.metadata_storage.get_file_by_key(self.conv_id, file_key)
        if not metadata:
            return False

        # 2. 删除本地文件
        await self._delete_local(Path(metadata.local_path))

        # 3. 删除元数据
        await self.metadata_storage.delete_file(self.conv_id, file_key)

        # 4. 从哈希索引移除
        if metadata.content_hash and metadata.content_hash in self._hash_index:
            del self._hash_index[metadata.content_hash]

        logger.info(f"[AFSv2] Deleted file: {file_key}")
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
            files = [f for f in files if self._get_file_category(f.file_type) == category]

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
        key = file_key or f"tool_{tool_name}_{int(datetime.utcnow().timestamp() * 1000)}"
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

    # ==================== 可视化交互 ====================

    async def _push_file_attach(self, file_metadata: AgentFileMetadata):
        """推送d-attach组件到前端."""
        # 检查metadata_storage是否是GptsMemory（只有GptsMemory支持push_message）
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
            logger.info(f"[AFSv2] Pushed d-attach for file: {file_metadata.file_name}")
        except Exception as e:
            logger.error(f"[AFSv2] Failed to push d-attach: {e}")

    async def push_conclusion_files(self):
        """推送所有结论文件到前端."""
        conclusion_files = await self.metadata_storage.get_conclusion_files(self.conv_id)
        for file_metadata in conclusion_files:
            await self._push_file_attach(file_metadata)

    async def collect_delivery_files(self, file_types: Optional[List[Union[str, FileType]]] = None) -> List[Dict[str, Any]]:
        """收集用于交付的文件列表.

        适用于terminate时收集所有相关文件进行交付。

        Args:
            file_types: 要收集的文件类型列表，默认收集结论文件和交付物文件

        Returns:
            文件信息字典列表，每个字典包含：
            - file_id: 文件ID
            - file_name: 文件名
            - file_type: 文件类型
            - file_size: 文件大小
            - oss_url: OSS地址
            - preview_url: 预览地址
            - download_url: 下载地址
            - mime_type: MIME类型
            - created_at: 创建时间
            - task_id: 关联任务ID
            - description: 文件描述
        """
        if file_types is None:
            # 默认收集结论文件和交付物文件
            file_types = [FileType.CONCLUSION, FileType.DELIVERABLE]

        all_files = []
        for file_type in file_types:
            files = await self.metadata_storage.list_files(self.conv_id, file_type)
            all_files.extend(files)

        # 去重（可能同一份文件有多个类型标记）
        seen_ids = set()
        unique_files = []
        for f in all_files:
            if f.file_id not in seen_ids:
                seen_ids.add(f.file_id)
                unique_files.append(f)

        # 转换为字典格式（用于ActionOutput.output_files）
        result = []
        for f in unique_files:
            result.append({
                "file_id": f.file_id,
                "file_name": f.file_name,
                "file_type": f.file_type,
                "file_size": f.file_size,
                "oss_url": f.oss_url,
                "preview_url": f.preview_url,
                "download_url": f.download_url,
                "mime_type": f.mime_type,
                "created_at": f.created_at.isoformat() if isinstance(f.created_at, datetime) else f.created_at,
                "task_id": f.task_id,
                "description": f.metadata.get("description") if f.metadata else None,
            })

        logger.info(f"[AFSv2] Collected {len(result)} delivery files")
        return result

    # ==================== 会话恢复 ====================

    async def sync_workspace(self):
        """同步工作区（恢复时调用）.

        流程:
        1. 从FileMetadataStorage加载所有文件元数据
        2. 检查本地文件完整性
        3. 从OSS下载缺失的文件
        4. 重建哈希索引
        """
        logger.info(f"[AFSv2] Syncing workspace for {self.conv_id}")

        # 1. 加载元数据
        files = await self.metadata_storage.list_files(self.conv_id)

        # 2. 恢复缺失的文件并重建哈希索引
        recovered_count = 0
        for metadata in files:
            # 重建哈希索引
            if metadata.content_hash:
                self._hash_index[metadata.content_hash] = metadata.file_key

            # 检查本地文件
            local_path = Path(metadata.local_path)
            content = await self._read_local(local_path)

            if content is None and metadata.oss_url:
                await self._download_from_oss(metadata.oss_url, local_path)
                recovered_count += 1

        if recovered_count > 0:
            logger.info(f"[AFSv2] Recovered {recovered_count} files from OSS")

        logger.info(f"[AFSv2] Workspace synced: {len(files)} files ready")
