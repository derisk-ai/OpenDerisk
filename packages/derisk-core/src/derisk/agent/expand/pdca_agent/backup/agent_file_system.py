"""Agent File System (AFS) - Complete Implementation.

基于元数据驱动的Agent文件系统，支持：
1. 文件分类管理（工具输出、写入文件、结论文件等）
2. 元数据持久化存储
3. OSS上传和URL生成
4. d-attach组件推送
5. 会话恢复
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import time
import uuid
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable, Awaitable

from derisk.agent.core.memory.gpts import (
    AgentFileMetadata,
    FileType,
    FileStatus,
    GptsMemory,
)
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
    """Agent文件系统 - 完整实现.

    功能：
    1. 透明地管理本地文件与远端OSS存储的同步
    2. 文件元数据持久化
    3. 分类管理文件（工具输出、写入文件、结论文件等）
    4. 生成预览和下载URL
    5. 推送文件到前端展示
    6. 支持会话恢复

    适用场景：对话恢复、多Agent协作、大数据持久化。
    """

    def __init__(
        self,
        conv_id: str,
        session_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        base_working_dir: str = str(os.path.join(DATA_DIR, "agent_storage")),
        sandbox: Optional[SandboxBase] = None,
        gpts_memory: Optional[GptsMemory] = None,
        oss_client=None,
    ):
        """初始化Agent文件系统.

        Args:
            conv_id: 会话ID
            session_id: 会话会话ID（用于子任务隔离）
            goal_id: 目标ID（用于任务隔离）
            base_working_dir: 基础工作目录
            sandbox: 沙箱环境
            gpts_memory: GPTS内存管理器（用于元数据存储）
            oss_client: OSS客户端
        """
        self.conv_id = conv_id
        self.session_id = session_id or conv_id
        self.goal_id = goal_id or "default"
        self.sandbox = sandbox
        self.gpts_memory = gpts_memory
        self._oss_client = oss_client

        # 构建存储路径
        self.base_path = Path(base_working_dir) / self.session_id / self.goal_id
        self.meta_path = self.base_path / "__file_catalog__.json"

        # 内存缓存
        self._catalog: Dict[str, Dict[str, Any]] = {}
        self._hash_index: Dict[str, str] = {}
        self._loaded = False

        logger.info(f"[AFS] Initialized for conv: {conv_id}, path: {self.base_path}")

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

    # ==================== Catalog 管理 ====================

    def _load_catalog_sync(self) -> Dict[str, Any]:
        """同步加载catalog（带缓存）."""
        if self._loaded:
            return self._catalog

        if self.sandbox:
            # 沙箱环境
            try:
                # 沙箱环境不支持直接读取，跳过catalog加载
                self._catalog = {}
                self._loaded = True
                return self._catalog
            except Exception as e:
                logger.warning(f"[AFS] Failed to load catalog from sandbox: {e}")
                self._catalog = {}
        else:
            # 本地文件系统
            if self.meta_path.exists():
                try:
                    with open(self.meta_path, 'r', encoding='utf-8') as f:
                        self._catalog = json.load(f)
                    logger.info(f"[AFS] Loaded catalog with {len(self._catalog)} files")
                except Exception as e:
                    logger.error(f"[AFS] Failed to load catalog: {e}")
                    self._catalog = {}
            else:
                self._catalog = {}

        # 重建hash索引
        self._hash_index = {
            info.get('hash'): key
            for key, info in self._catalog.items()
            if info.get('hash')
        }

        self._loaded = True
        return self._catalog

    def _save_catalog_sync(self):
        """同步保存catalog."""
        if self.sandbox:
            # 沙箱环境：写入沙箱文件
            try:
                content = json.dumps(self._catalog, ensure_ascii=False, indent=2)
                # 沙箱写入需要异步，这里先不处理
                logger.debug("[AFS] Catalog in sandbox mode, skip sync save")
            except Exception as e:
                logger.error(f"[AFS] Failed to save catalog to sandbox: {e}")
        else:
            # 本地文件系统
            self._ensure_dir()
            temp_path = self.meta_path.with_suffix('.tmp')
            try:
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(self._catalog, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                temp_path.replace(self.meta_path)
                logger.debug(f"[AFS] Saved catalog with {len(self._catalog)} files")
            except Exception as e:
                if temp_path.exists():
                    temp_path.unlink()
                logger.error(f"[AFS] Failed to save catalog: {e}")

    async def _load_catalog(self) -> Dict[str, Any]:
        """异步加载catalog."""
        import asyncio
        return await asyncio.to_thread(self._load_catalog_sync)

    async def _save_catalog(self):
        """异步保存catalog."""
        import asyncio
        await asyncio.to_thread(self._save_catalog_sync)

    # ==================== OSS 操作 ====================

    async def _upload_to_oss(self, local_path: Path) -> str:
        """上传文件到OSS.

        Returns:
            OSS URL
        """
        if not self._oss_client:
            # 模拟OSS URL
            await self._simulate_delay()
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
            logger.error(f"[AFS] OSS upload failed: {e}")
            return f"local://chat/{self.session_id}/{self.goal_id}/{local_path.name}"

    async def _download_from_oss(self, oss_url: str, local_path: Path):
        """从OSS下载文件."""
        if not self._oss_client or oss_url.startswith("local://"):
            await self._simulate_delay()
            return

        try:
            # 解析OSS对象名
            if oss_url.startswith(f"oss://{self._oss_client.bucket_name}/"):
                oss_object_name = oss_url.replace(f"oss://{self._oss_client.bucket_name}/", "")
            else:
                logger.warning(f"[AFS] Unknown OSS URL format: {oss_url}")
                return

            self._ensure_dir()

            if self.sandbox:
                # 沙箱环境：先下载到临时文件，再写入沙箱
                temp_dir = Path("/tmp") / self.session_id / self.goal_id
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_file = temp_dir / local_path.name

                self._oss_client.download_file(oss_object_name, str(temp_file))
                content = temp_file.read_text(encoding='utf-8')
                await self.sandbox.file.create(str(local_path), content)
                temp_file.unlink()
            else:
                # 本地文件系统：直接下载
                self._oss_client.download_file(oss_object_name, str(local_path))

        except Exception as e:
            logger.error(f"[AFS] OSS download failed: {e}")

    async def _simulate_delay(self, seconds: float = 0.01):
        """模拟网络延迟."""
        import asyncio
        await asyncio.sleep(seconds)

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

        Args:
            file_key: 文件key（唯一标识）
            data: 文件内容
            file_type: 文件类型
            extension: 文件扩展名
            file_name: 文件名（可选，默认使用file_key）
            created_by: 创建者
            task_id: 关联任务ID
            message_id: 关联消息ID
            tool_name: 关联工具名称
            is_conclusion: 是否为结论文件
            metadata: 额外元数据

        Returns:
            文件元数据
        """
        import asyncio

        self._ensure_dir()

        # 加载catalog
        catalog = await self._load_catalog()

        # 计算哈希
        content_hash = self._compute_hash(data)

        # 检查去重
        if content_hash in self._hash_index:
            existing_key = self._hash_index[content_hash]
            if existing_key in catalog:
                existing_info = catalog[existing_key]
                existing_file_id = existing_info.get('file_id', '')
                # 返回已存在的文件元数据
                return AgentFileMetadata(
                    file_id=existing_file_id,
                    conv_id=self.conv_id,
                    conv_session_id=self.session_id,
                    file_key=existing_key,
                    file_name=existing_info.get('file_name', existing_key),
                    file_type=existing_info.get('file_type', FileType.TEMP.value),
                    local_path=existing_info.get('local_path', ''),
                    oss_url=existing_info.get('oss_url'),
                    content_hash=content_hash,
                    status=FileStatus.COMPLETED.value,
                    created_by=existing_info.get('created_by', ''),
                    created_at=datetime.fromisoformat(existing_info['created_at']) if isinstance(existing_info.get('created_at'), str) else datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

        # 构建文件路径
        if '.' in file_key and len(file_key.split('.')[-1]) <= 4:
            safe_key = self._sanitize_filename(file_key)
        else:
            safe_key = f"{self._sanitize_filename(file_key)}.{extension}"

        local_path = self.base_path / safe_key
        actual_file_name = file_name or safe_key

        # 准备内容
        if isinstance(data, (dict, list)):
            content_str = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            content_str = str(data)

        # 写入文件
        file_size = len(content_str.encode('utf-8'))

        if self.sandbox:
            await self.sandbox.file.create(str(local_path), content_str)
        else:
            await asyncio.to_thread(local_path.write_text, content_str, encoding='utf-8')

        # 上传到OSS
        oss_url = await self._upload_to_oss(local_path)

        # 获取文件元数据
        mime_type = self._get_mime_type(actual_file_name)
        file_id = str(uuid.uuid4())

        # 确定文件类型
        if is_conclusion:
            actual_file_type = FileType.CONCLUSION.value
        else:
            actual_file_type = file_type.value if isinstance(file_type, FileType) else file_type

        # 生成预览和下载URL
        preview_url = await self._generate_preview_url(oss_url, mime_type)
        download_url = await self._generate_download_url(oss_url, actual_file_name)

        # 构建文件元数据
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
            preview_url=preview_url,
            download_url=download_url,
            content_hash=content_hash,
            status=FileStatus.COMPLETED.value,
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7),  # 默认7天过期
            metadata=metadata or {},
            mime_type=mime_type,
            task_id=task_id,
            message_id=message_id,
            tool_name=tool_name,
        )

        # 更新catalog
        catalog[file_key] = {
            "file_id": file_id,
            "file_name": actual_file_name,
            "file_type": actual_file_type,
            "local_path": str(local_path),
            "oss_url": oss_url,
            "hash": content_hash,
            "created_at": file_metadata.created_at.isoformat(),
            "created_by": created_by,
        }
        self._hash_index[content_hash] = file_key

        await self._save_catalog()

        # 保存到GPTS内存
        if self.gpts_memory:
            await self.gpts_memory.append_file(self.conv_id, file_metadata)

        logger.info(f"[AFS] Saved file: {file_key} ({file_size} bytes) -> {oss_url}")

        # 如果是结论文件，推送d-attach组件
        if is_conclusion or actual_file_type == FileType.CONCLUSION.value:
            await self._push_file_attach(file_metadata)

        return file_metadata

    async def read_file(self, file_key: str) -> Optional[str]:
        """读取文件内容.

        Args:
            file_key: 文件key

        Returns:
            文件内容，如果不存在返回None
        """
        import asyncio

        catalog = await self._load_catalog()
        info = catalog.get(file_key)

        if not info:
            return None

        local_path = Path(info['local_path'])

        # 检查文件是否存在
        file_exists = False
        if self.sandbox:
            try:
                file_info = await self.sandbox.file.read(str(local_path))
                if file_info.content is not None:
                    return file_info.content
            except Exception:
                pass
        else:
            file_exists = await asyncio.to_thread(local_path.exists)

        # 如果本地不存在，从OSS下载
        if not file_exists:
            await self._download_from_oss(info['oss_url'], local_path)

        # 读取文件
        if self.sandbox:
            try:
                file_info = await self.sandbox.file.read(str(local_path))
                return file_info.content
            except Exception as e:
                logger.error(f"[AFS] Failed to read file from sandbox: {e}")
                return None
        else:
            try:
                return await asyncio.to_thread(local_path.read_text, encoding='utf-8')
            except Exception as e:
                logger.error(f"[AFS] Failed to read file: {e}")
                return None

    async def delete_file(self, file_key: str) -> bool:
        """删除文件.

        Args:
            file_key: 文件key

        Returns:
            是否成功
        """
        import asyncio

        catalog = await self._load_catalog()

        if file_key not in catalog:
            return False

        info = catalog[file_key]
        local_path = Path(info['local_path'])

        # 删除本地文件
        try:
            if self.sandbox:
                await self.sandbox.file.remove(str(local_path))
            else:
                if await asyncio.to_thread(local_path.exists):
                    await asyncio.to_thread(local_path.unlink)
        except Exception as e:
            logger.warning(f"[AFS] Failed to delete local file: {e}")

        # 从catalog移除
        content_hash = info.get('hash')
        if content_hash and content_hash in self._hash_index:
            del self._hash_index[content_hash]
        del catalog[file_key]

        await self._save_catalog()

        logger.info(f"[AFS] Deleted file: {file_key}")
        return True

    # ==================== URL 生成 ====================

    async def _generate_preview_url(self, oss_url: str, mime_type: str) -> Optional[str]:
        """生成预览URL.

        Args:
            oss_url: OSS URL
            mime_type: MIME类型

        Returns:
            预览URL
        """
        if not self._oss_client:
            return None

        # 只有特定类型支持预览
        previewable_types = [
            'text/plain',
            'text/html',
            'text/markdown',
            'text/csv',
            'application/json',
            'application/pdf',
            'image/',
        ]

        is_previewable = any(mime_type.startswith(t) if t.endswith('/') else mime_type == t
                             for t in previewable_types)

        if not is_previewable:
            return None

        try:
            # 生成临时预览URL（带签名）
            return self._oss_client.generate_preview_url(oss_url, expires=3600)
        except Exception:
            return oss_url

    async def _generate_download_url(self, oss_url: str, file_name: str) -> Optional[str]:
        """生成下载URL.

        Args:
            oss_url: OSS URL
            file_name: 文件名

        Returns:
            下载URL
        """
        if not self._oss_client:
            return None

        try:
            # 生成带签名的下载URL
            return self._oss_client.generate_download_url(oss_url, file_name, expires=3600)
        except Exception:
            return oss_url

    # ==================== 查询方法 ====================

    async def get_file_info(self, file_key: str) -> Optional[Dict[str, Any]]:
        """获取文件信息.

        Args:
            file_key: 文件key

        Returns:
            文件信息字典
        """
        catalog = await self._load_catalog()
        return catalog.get(file_key)

    async def list_files(
        self,
        file_type: Optional[Union[str, FileType]] = None,
        category: Optional[FileCategory] = None,
    ) -> List[Dict[str, Any]]:
        """列出文件.

        Args:
            file_type: 文件类型过滤
            category: 文件分类过滤

        Returns:
            文件信息列表
        """
        catalog = await self._load_catalog()

        files = []
        target_type = None
        if file_type:
            target_type = file_type.value if isinstance(file_type, FileType) else file_type

        for key, info in catalog.items():
            # 类型过滤
            if target_type and info.get('file_type') != target_type:
                continue

            # 分类过滤
            if category:
                info_category = self._get_file_category(info.get('file_type', ''))
                if info_category != category:
                    continue

            info_copy = dict(info)
            info_copy['file_key'] = key
            files.append(info_copy)

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

    # ==================== 可视化交互 ====================

    async def _push_file_attach(self, file_metadata: AgentFileMetadata):
        """推送d-attach组件到前端.

        Args:
            file_metadata: 文件元数据
        """
        if not self.gpts_memory:
            return

        from derisk.vis import Vis
        from derisk.vis.schema import VisAttachContent

        try:
            # 构建附件内容
            attach_content = VisAttachContent(
                file_id=file_metadata.file_id,
                file_name=file_metadata.file_name,
                file_type=file_metadata.file_type,
                file_size=file_metadata.file_size,
                oss_url=file_metadata.oss_url,
                preview_url=file_metadata.preview_url,
                download_url=file_metadata.download_url,
                mime_type=file_metadata.mime_type,
            )

            # 使用vis系统推送
            vis_attach = Vis.of("d-attach")
            output = vis_attach.sync_display(content=attach_content.to_dict())

            # 推送到消息通道
            await self.gpts_memory.push_message(
                self.conv_id,
                stream_msg={
                    "type": "file_attach",
                    "content": output,
                    "file_id": file_metadata.file_id,
                    "file_name": file_metadata.file_name,
                },
            )

            logger.info(f"[AFS] Pushed d-attach for file: {file_metadata.file_name}")

        except Exception as e:
            logger.error(f"[AFS] Failed to push d-attach: {e}")

    async def push_conclusion_files(self):
        """推送所有结论文件."""
        if not self.gpts_memory:
            return

        conclusion_files = await self.list_files(file_type=FileType.CONCLUSION)

        for file_info in conclusion_files:
            file_key = file_info['file_key']
            file_metadata = AgentFileMetadata(
                file_id=file_info.get('file_id', ''),
                conv_id=self.conv_id,
                conv_session_id=self.session_id,
                file_key=file_key,
                file_name=file_info.get('file_name', file_key),
                file_type=file_info.get('file_type', FileType.CONCLUSION.value),
                local_path=file_info.get('local_path', ''),
                oss_url=file_info.get('oss_url'),
                created_at=datetime.fromisoformat(file_info['created_at']) if isinstance(file_info.get('created_at'), str) else datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            await self._push_file_attach(file_metadata)

    # ==================== 会话恢复 ====================

    async def sync_workspace(self):
        """同步工作区（恢复时调用）.

        1. 从数据库加载文件元数据
        2. 检查本地文件完整性
        3. 从OSS恢复缺失的文件
        """
        logger.info(f"[AFS] Syncing workspace for {self.conv_id}")

        # 加载本地catalog
        catalog = await self._load_catalog()

        # 如果从GPTS内存有持久化数据，合并进来
        if self.gpts_memory:
            try:
                persisted_files = await self.gpts_memory.get_files(self.conv_id)
                for file_meta in persisted_files:
                    if file_meta.file_key not in catalog:
                        catalog[file_meta.file_key] = {
                            "file_id": file_meta.file_id,
                            "file_name": file_meta.file_name,
                            "file_type": file_meta.file_type,
                            "local_path": file_meta.local_path,
                            "oss_url": file_meta.oss_url,
                            "hash": file_meta.content_hash,
                            "created_at": file_meta.created_at.isoformat() if isinstance(file_meta.created_at, datetime) else datetime.utcnow().isoformat(),
                            "created_by": file_meta.created_by,
                        }
                        if file_meta.content_hash:
                            self._hash_index[file_meta.content_hash] = file_meta.file_key

                await self._save_catalog()
                logger.info(f"[AFS] Merged {len(persisted_files)} files from persistent storage")
            except Exception as e:
                logger.warning(f"[AFS] Failed to load from persistent storage: {e}")

        # 恢复缺失的文件
        recovered_count = 0
        for file_key, info in catalog.items():
            local_path = Path(info['local_path'])

            # 检查文件是否存在
            file_exists = False
            if self.sandbox:
                try:
                    file_info = await self.sandbox.file.read(str(local_path))
                    file_exists = file_info.content is not None
                except Exception:
                    pass
            else:
                import asyncio
                file_exists = await asyncio.to_thread(local_path.exists)

            if not file_exists and info.get('oss_url'):
                await self._download_from_oss(info['oss_url'], local_path)
                recovered_count += 1

        if recovered_count > 0:
            logger.info(f"[AFS] Recovered {recovered_count} files from OSS")

        logger.info(f"[AFS] Workspace synced: {len(catalog)} files ready")

    # ==================== 便捷方法 ====================

    async def save_tool_output(
        self,
        tool_name: str,
        output: Any,
        file_key: Optional[str] = None,
        extension: str = "log",
    ) -> AgentFileMetadata:
        """保存工具输出.

        Args:
            tool_name: 工具名称
            output: 输出内容
            file_key: 文件key（可选）
            extension: 扩展名

        Returns:
            文件元数据
        """
        key = file_key or f"tool_{tool_name}_{int(time.time() * 1000)}"
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
        """保存结论文件（自动推送d-attach）.

        Args:
            data: 文件内容
            file_name: 文件名
            extension: 扩展名
            created_by: 创建者
            task_id: 任务ID

        Returns:
            文件元数据
        """
        file_key = f"conclusion_{int(time.time() * 1000)}_{file_name}"
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
        """保存截断输出.

        Args:
            original_content: 原始内容
            tool_name: 工具名称
            truncated_info: 截断信息

        Returns:
            文件元数据
        """
        file_key = f"truncated_{tool_name}_{int(time.time() * 1000)}"

        # 构建截断文件内容
        data = {
            "tool_name": tool_name,
            "truncated_info": truncated_info,
            "original_preview": original_content[:1000] if len(original_content) > 1000 else original_content,
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

    async def get_file_for_attach(self, file_key: str) -> Optional[Dict[str, Any]]:
        """获取文件用于d-attach组件展示.

        Args:
            file_key: 文件key

        Returns:
            d-attach组件内容字典
        """
        info = await self.get_file_info(file_key)
        if not info:
            return None

        # 从catalog或GPTS内存获取完整元数据
        file_metadata = None
        if self.gpts_memory:
            file_metadata = await self.gpts_memory.get_file_by_key(self.conv_id, file_key)

        if not file_metadata:
            # 从catalog构建
            file_metadata = AgentFileMetadata(
                file_id=info.get('file_id', str(uuid.uuid4())),
                conv_id=self.conv_id,
                conv_session_id=self.session_id,
                file_key=file_key,
                file_name=info.get('file_name', file_key),
                file_type=info.get('file_type', FileType.TEMP.value),
                local_path=info.get('local_path', ''),
                oss_url=info.get('oss_url'),
                created_at=datetime.fromisoformat(info['created_at']) if 'created_at' in info else datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

        return file_metadata.to_attach_content()
