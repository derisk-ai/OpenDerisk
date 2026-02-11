"""PDCA Agent File System V3 - 集成 FileStorageClient.

这是 PDCA Agent 专用的 FileSystem 类的 V3 版本，它：
1. 保持与原有 FileSystem 类完全相同的 API
2. 内部使用 AgentFileSystemV3（集成 FileStorageClient）
3. 支持多种存储后端（FileStorageClient、OSS、本地）
4. 通过 FileServe 代理访问文件

与原有 FileSystem 的区别：
- 使用 FileStorageClient 替代直接的 OSS 操作
- 支持通过文件服务代理访问文件
- 更好的存储后端抽象
"""

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from derisk.agent.core.file_system.agent_file_system import AgentFileSystem
from derisk.agent.core.memory.gpts import FileType

from derisk.configs.model_config import DATA_DIR
from derisk.sandbox.base import SandboxBase
from derisk.sandbox.client.file.types import FileInfo

logger = logging.getLogger(__name__)


class FileSystem:
    """PDCA Agent 文件系统 V3 - 集成 FileStorageClient.

    此类保持与原有 FileSystem 完全相同的 API，但内部使用 AgentFileSystemV3
    来实现统一的文件存储接口。

    使用示例:
        # 方式 1: 使用 FileStorageClient（推荐）
        fs = FileSystem(
            session_id="session_001",
            goal_id="goal_001",
            file_storage_client=file_storage_client,  # FileStorageClient
        )

        # 方式 2: 使用 OSS 客户端（兼容）
        fs = FileSystem(
            session_id="session_001",
            goal_id="goal_001",
            sandbox=sandbox,  # sandbox 中包含 oss 客户端
        )

        # 方式 3: 仅本地存储
        fs = FileSystem(
            session_id="session_001",
            goal_id="goal_001",
        )
    """

    def __init__(
        self,
        session_id: str,
        goal_id: str,
        base_working_dir: str = str(Path(DATA_DIR) / "agent_storage"),
        sandbox: Optional[SandboxBase] = None,
        file_storage_client: Optional[Any] = None,
        oss_client=None,
    ):
        """初始化 PDCA Agent FileSystem V3.

        Args:
            session_id: 会话ID
            goal_id: 目标ID
            base_working_dir: 基础工作目录
            sandbox: 沙箱环境（可选）
            file_storage_client: FileStorageClient 实例（可选，推荐）
            oss_client: OSS 客户端（可选）
        """
        self.session_id = session_id
        self.goal_id = goal_id
        self.sandbox = sandbox

        # 根据是否使用沙箱选择存储路径
        if self.sandbox:
            self.base_path = Path(
                f"{self.sandbox.work_dir}/{self.session_id}/{self.goal_id}"
            )
        else:
            self.base_path = Path(base_working_dir) / self.session_id / self.goal_id

        self.meta_path = self.base_path / "__file_catalog__.json"

        # 初始化内部 AgentFileSystem
        # PDCA Agent 的 FileSystem 主要使用 session_id 和 goal_id
        # 我们使用 session_id 作为 conv_id 来兼容 AgentFileSystem
        self._afs = AgentFileSystem(
            conv_id=session_id,
            session_id=session_id,
            goal_id=goal_id,
            base_working_dir=base_working_dir,
            sandbox=sandbox,
            file_storage_client=file_storage_client,
            oss_client=oss_client,
            bucket="pdca_files",  # PDCA Agent 专用 bucket
        )

        # 兼容性：保留内存缓存机制
        self._content_cache: Dict[str, str] = {}

        # 兼容性：保留锁（虽然在 AgentFileSystem 中已处理）
        self._lock = asyncio.Lock()

        logger.info(
            f"[PDCA-FS-V3] Initialized for session: {session_id}, goal: {goal_id}"
        )

    def _ensure_dir(self):
        """确保目录存在（兼容性方法）."""
        if not self.sandbox:
            if not self.base_path.exists():
                self.base_path.mkdir(parents=True, exist_ok=True)

    def _compute_hash(self, data: Union[str, Dict, List]) -> str:
        """计算数据的 MD5 哈希（兼容性方法）."""
        if isinstance(data, (dict, list)):
            content_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        else:
            content_str = str(data)
        return hashlib.md5(content_str.encode("utf-8")).hexdigest()

    def _sanitize_filename(self, key: str) -> str:
        """清理文件名（兼容性方法）."""
        return "".join([c for c in key if c.isalnum() or c in ("-", "_", ".")])

    async def _load_catalog(self) -> Dict:
        """加载元数据（兼容性方法）.

        在 V3 中，元数据存储由 AgentFileSystem 的 metadata_storage 处理。
        此方法保留以兼容旧代码。
        """
        # 从 AgentFileSystem 加载所有文件信息
        files = await self._afs.list_files()
        catalog = {}
        for f in files:
            catalog[f.file_key] = {
                "local_path": f.local_path,
                "filename": f.file_name,
                "oss_url": f.oss_url,
                "timestamp": f.created_at.timestamp()
                if hasattr(f.created_at, "timestamp")
                else time.time(),
                "hash": f.content_hash,
            }
        return catalog

    async def _save_catalog(self):
        """保存元数据（兼容性方法，V3 中元数据自动保存）."""
        # V3 中元数据由 AgentFileSystem 自动管理
        pass

    async def _oss_upload(self, local_path: Path) -> str:
        """上传文件到 OSS（兼容性方法）.

        注意：在 V3 中，此操作由 AgentFileSystem 在 save_file 时自动处理。
        此方法保留以兼容旧代码，但内部直接返回已保存文件的 oss_url。
        """
        # V3 中文件上传在 save_file 时已完成
        # 如果需要获取 URL，请使用 save_file 的返回值
        logger.warning("[PDCA-FS-V3] _oss_upload is deprecated, use save_file instead")
        return f"local://{self.session_id}/{self.goal_id}/{local_path.name}"

    async def _oss_download(self, oss_url: str, local_path: Path):
        """从 OSS 下载文件（兼容性方法）.

        注意：在 V3 中，文件读取会自动处理 OSS 下载。
        此方法保留以兼容旧代码。
        """
        # V3 中文件下载在 read_file 时自动处理
        logger.warning(
            "[PDCA-FS-V3] _oss_download is deprecated, use read_file instead"
        )

    async def sync_workspace(self):
        """同步工作区（兼容性方法）."""
        await self._afs.sync_workspace()

    async def save_file(
        self,
        file_key: str,
        data: Any,
        extension: str = "txt",
        cache_immediately: bool = False,
    ) -> str:
        """保存文件（核心方法）.

        此方法是兼容层，将调用转发到 AgentFileSystemV3。

        Args:
            file_key: 文件 key
            data: 文件内容
            extension: 文件扩展名
            cache_immediately: 是否立即缓存到内存（兼容性参数）

        Returns:
            本地文件路径
        """
        # 使用 AgentFileSystem 保存文件
        metadata = await self._afs.save_file(
            file_key=file_key,
            data=data,
            file_type=FileType.TEMP,  # PDCA Agent 文件默认为 TEMP 类型
            extension=extension,
        )

        # 兼容性：如果请求立即缓存，添加到内存缓存
        if cache_immediately:
            content_str = (
                json.dumps(data, ensure_ascii=False)
                if isinstance(data, (dict, list))
                else str(data)
            )
            self._content_cache[file_key] = content_str

        # 返回本地路径以保持兼容性
        return metadata.local_path

    async def read_file(self, file_key: str, use_cache: bool = False) -> Optional[str]:
        """读取文件内容.

        Args:
            file_key: 文件 key
            use_cache: 是否使用内存缓存（兼容性参数）

        Returns:
            文件内容，如果不存在返回 None
        """
        # 兼容性：检查内存缓存
        if use_cache and file_key in self._content_cache:
            return self._content_cache[file_key]

        # 使用 AgentFileSystem 读取文件
        content = await self._afs.read_file(file_key)

        # 兼容性：如果请求使用缓存，添加到内存缓存
        if use_cache and content:
            self._content_cache[file_key] = content

        return content

    async def get_file_info(self, file_key: str) -> Optional[Dict]:
        """获取文件信息.

        Args:
            file_key: 文件 key

        Returns:
            文件信息字典，如果不存在返回 None
        """
        metadata = await self._afs.get_file_info(file_key)
        if not metadata:
            return None

        # 转换为兼容的格式
        return {
            "local_path": metadata.local_path,
            "filename": metadata.file_name,
            "oss_url": metadata.oss_url,
            "timestamp": metadata.created_at.timestamp()
            if hasattr(metadata.created_at, "timestamp")
            else time.time(),
            "hash": metadata.content_hash,
        }

    async def preload_file(self, file_key: str, content: str):
        """预加载文件到缓存（兼容性方法）."""
        # 检查文件是否已存在
        existing = await self.get_file_info(file_key)
        if not existing:
            # 保存文件
            await self.save_file(file_key, content, cache_immediately=True)
        else:
            # 只更新缓存
            self._content_cache[file_key] = content

    async def delete_file(self, file_key: str) -> bool:
        """删除文件（新增方法，V2 中没有）.

        Args:
            file_key: 文件 key

        Returns:
            是否成功删除
        """
        return await self._afs.delete_file(file_key)

    async def list_files(self) -> List[Dict]:
        """列出所有文件（新增方法，V2 中没有）.

        Returns:
            文件信息列表
        """
        files = await self._afs.list_files()
        return [
            {
                "file_key": f.file_key,
                "file_name": f.file_name,
                "local_path": f.local_path,
                "oss_url": f.oss_url,
            }
            for f in files
        ]

    def get_storage_type(self) -> str:
        """获取当前使用的存储类型（新增方法）.

        Returns:
            "file_storage_client" | "oss" | "local"
        """
        return self._afs.get_storage_type()

    async def get_file_url(
        self, file_key: str, url_type: str = "download"
    ) -> Optional[str]:
        """获取文件 URL（新增方法）.

        Args:
            file_key: 文件 key
            url_type: "download" | "preview"

        Returns:
            文件 URL，如果不支持返回 None
        """
        metadata = await self._afs.get_file_info(file_key)
        if not metadata:
            return None

        if url_type == "preview":
            return metadata.preview_url
        else:
            return metadata.download_url


# 兼容性别名，使旧代码可以直接使用 FileSystem 而不需要改 import
# 如果需要使用 V3 版本，可以显式导入:
# from derisk.agent.expand.pdca_agent.file_system_v3 import FileSystem as FileSystemV3

# 保持与旧版本相同的导出
__all__ = ["FileSystem"]
