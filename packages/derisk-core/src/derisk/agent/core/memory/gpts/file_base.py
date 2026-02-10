"""Agent File Memory Models.

参考GptsMessage和GptsPlan的设计，实现文件元数据存储机制。
"""

from __future__ import annotations

import dataclasses
import enum
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Union


class FileType(enum.Enum):
    """Agent文件类型分类."""

    TOOL_OUTPUT = "tool_output"           # 工具结果临时文件
    WRITE_FILE = "write_file"             # write工具写入的文件
    SANDBOX_FILE = "sandbox_file"         # 沙箱环境文件
    CONCLUSION = "conclusion"             # 结论文件（需要推送给用户）
    KANBAN = "kanban"                     # 看板相关文件
    DELIVERABLE = "deliverable"           # 交付物文件
    TRUNCATED_OUTPUT = "truncated_output" # 截断输出文件
    WORKFLOW = "workflow"                 # 工作流文件
    KNOWLEDGE = "knowledge"               # 知识库文件
    TEMP = "temp"                         # 临时文件


class FileStatus(enum.Enum):
    """文件状态."""

    PENDING = "pending"       # 待处理
    UPLOADING = "uploading"   # 上传中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败
    EXPIRED = "expired"       # 已过期


@dataclasses.dataclass
class AgentFileMetadata:
    """Agent文件元数据模型.

    类似GptsMessage/GptsPlan的设计，存储文件的完整元数据信息。

    Attributes:
        file_id: 文件唯一标识符
        conv_id: 会话ID
        conv_session_id: 会话会话ID
        file_key: 文件系统内的key
        file_name: 文件名
        file_type: 文件类型(FileType)
        file_size: 文件大小（字节）
        local_path: 本地文件路径
        oss_url: OSS URL
        preview_url: 预览URL
        download_url: 下载URL
        content_hash: 内容哈希（用于去重）
        status: 文件状态
        created_by: 创建者（agent名称）
        created_at: 创建时间
        updated_at: 更新时间
        expires_at: 过期时间
        metadata: 额外的元数据（JSON格式）
        is_public: 是否公开访问
        mime_type: MIME类型
    """

    # 基础标识（无默认值）
    file_id: str
    conv_id: str
    conv_session_id: str
    file_key: str
    file_name: str
    file_type: str  # FileType.value
    local_path: str

    # 可选字段（有默认值）
    file_size: int = 0
    oss_url: Optional[str] = None
    preview_url: Optional[str] = None
    download_url: Optional[str] = None
    content_hash: Optional[str] = None
    status: str = FileStatus.COMPLETED.value  # FileStatus.value
    created_by: str = ""
    created_at: datetime = dataclasses.field(default_factory=datetime.utcnow)
    updated_at: datetime = dataclasses.field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = dataclasses.field(default_factory=dict)
    is_public: bool = False
    mime_type: Optional[str] = None
    task_id: Optional[str] = None  # 关联的任务ID
    message_id: Optional[str] = None  # 关联的消息ID
    tool_name: Optional[str] = None  # 关联的工具名称

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        result = dataclasses.asdict(self)
        # 处理datetime序列化
        for key in ['created_at', 'updated_at', 'expires_at']:
            if result.get(key) and isinstance(result[key], datetime):
                result[key] = result[key].isoformat()
        return result

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AgentFileMetadata":
        """从字典创建."""
        # 处理datetime反序列化
        for key in ['created_at', 'updated_at', 'expires_at']:
            if d.get(key) and isinstance(d[key], str):
                d[key] = datetime.fromisoformat(d[key])
        return AgentFileMetadata(**d)

    def to_attach_content(self) -> Dict[str, Any]:
        """转换为d-attach组件内容格式."""
        return {
            "file_id": self.file_id,
            "file_name": self.file_name,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "oss_url": self.oss_url,
            "preview_url": self.preview_url,
            "download_url": self.download_url,
            "mime_type": self.mime_type,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
        }


@dataclasses.dataclass
class AgentFileCatalog:
    """Agent文件目录（会话级）.

    存储单个会话的所有文件索引，类似Kanban的catalog。
    """

    conv_id: str
    files: Dict[str, str] = dataclasses.field(default_factory=dict)  # file_key -> file_id
    created_at: datetime = dataclasses.field(default_factory=datetime.utcnow)
    updated_at: datetime = dataclasses.field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conv_id": self.conv_id,
            "files": self.files,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AgentFileCatalog":
        return AgentFileCatalog(
            conv_id=d["conv_id"],
            files=d.get("files", {}),
            created_at=datetime.fromisoformat(d["created_at"]),
            updated_at=datetime.fromisoformat(d["updated_at"]),
        )


class AgentFileMemory(ABC):
    """Agent文件元数据存储接口.

    类似GptsMessageMemory/GptsPlansMemory的设计。
    """

    @abstractmethod
    def append(self, file_metadata: AgentFileMetadata) -> None:
        """添加文件元数据.

        Args:
            file_metadata: 文件元数据对象
        """

    @abstractmethod
    def update(self, file_metadata: AgentFileMetadata) -> None:
        """更新文件元数据.

        Args:
            file_metadata: 文件元数据对象
        """

    @abstractmethod
    async def get_by_conv_id(self, conv_id: str) -> List[AgentFileMetadata]:
        """获取会话的所有文件.

        Args:
            conv_id: 会话ID

        Returns:
            文件元数据列表
        """

    @abstractmethod
    def get_by_file_id(self, file_id: str) -> Optional[AgentFileMetadata]:
        """获取单个文件元数据.

        Args:
            file_id: 文件ID

        Returns:
            文件元数据对象
        """

    @abstractmethod
    def get_by_file_key(self, conv_id: str, file_key: str) -> Optional[AgentFileMetadata]:
        """通过file_key获取文件元数据.

        Args:
            conv_id: 会话ID
            file_key: 文件key

        Returns:
            文件元数据对象
        """

    @abstractmethod
    def delete_by_conv_id(self, conv_id: str) -> None:
        """删除会话的所有文件元数据.

        Args:
            conv_id: 会话ID
        """

    @abstractmethod
    def delete_by_file_key(self, conv_id: str, file_key: str) -> bool:
        """通过file_key删除文件元数据.

        Args:
            conv_id: 会话ID
            file_key: 文件key

        Returns:
            是否成功删除
        """

    @abstractmethod
    def get_by_file_type(
        self, conv_id: str, file_type: Union[str, FileType]
    ) -> List[AgentFileMetadata]:
        """获取指定类型的所有文件.

        Args:
            conv_id: 会话ID
            file_type: 文件类型

        Returns:
            文件元数据列表
        """

    @abstractmethod
    def save_catalog(self, conv_id: str, file_key: str, file_id: str) -> None:
        """保存文件到目录（file_key -> file_id映射）.

        Args:
            conv_id: 会话ID
            file_key: 文件key
            file_id: 文件ID
        """

    @abstractmethod
    def get_catalog(self, conv_id: str) -> Dict[str, str]:
        """获取文件目录（所有file_key -> file_id映射）.

        Args:
            conv_id: 会话ID

        Returns:
            文件目录字典
        """

    @abstractmethod
    def get_file_id_by_key(self, conv_id: str, file_key: str) -> Optional[str]:
        """通过file_key获取file_id.

        Args:
            conv_id: 会话ID
            file_key: 文件key

        Returns:
            文件ID
        """

    @abstractmethod
    def delete_catalog(self, conv_id: str) -> None:
        """删除文件目录.

        Args:
            conv_id: 会话ID
        """


# ============================================================================
# FileMetadataStorage Interface - 用于AgentFileSystem的存储抽象
# ============================================================================

class FileMetadataStorage(ABC):
    """文件元数据存储接口 - 为AgentFileSystem提供存储抽象.

    设计目的:
    1. 解耦AgentFileSystem与具体存储实现(GptsMemory/SimpleStorage/Database)
    2. 支持不同场景下的灵活存储选择:
       - 完整场景: 使用GptsMemory(带缓存+持久化)
       - 轻量场景: 使用SimpleFileMetadataStorage(仅内存)
       - 自定义场景: 实现自定义存储(数据库/Redis等)

    使用示例:
        # 方式1: 使用GptsMemory(推荐用于完整应用)
        gpts_memory = GptsMemory()
        afs = AgentFileSystem(conv_id="xxx", metadata_storage=gpts_memory)

        # 方式2: 使用简单内存存储(轻量级场景)
        simple_storage = SimpleFileMetadataStorage()
        afs = AgentFileSystem(conv_id="xxx", metadata_storage=simple_storage)
    """

    @abstractmethod
    async def save_file_metadata(self, file_metadata: AgentFileMetadata) -> None:
        """保存文件元数据.

        Args:
            file_metadata: 文件元数据对象
        """

    @abstractmethod
    async def update_file_metadata(self, file_metadata: AgentFileMetadata) -> None:
        """更新文件元数据.

        Args:
            file_metadata: 文件元数据对象
        """

    @abstractmethod
    async def get_file_by_key(self, conv_id: str, file_key: str) -> Optional[AgentFileMetadata]:
        """通过file_key获取文件元数据.

        Args:
            conv_id: 会话ID
            file_key: 文件key

        Returns:
            文件元数据对象，不存在返回None
        """

    @abstractmethod
    async def get_file_by_id(self, conv_id: str, file_id: str) -> Optional[AgentFileMetadata]:
        """通过file_id获取文件元数据.

        Args:
            conv_id: 会话ID
            file_id: 文件ID

        Returns:
            文件元数据对象，不存在返回None
        """

    @abstractmethod
    async def list_files(
        self,
        conv_id: str,
        file_type: Optional[Union[str, FileType]] = None
    ) -> List[AgentFileMetadata]:
        """列出会话的所有文件.

        Args:
            conv_id: 会话ID
            file_type: 可选的文件类型过滤

        Returns:
            文件元数据列表
        """

    @abstractmethod
    async def delete_file(self, conv_id: str, file_key: str) -> bool:
        """删除文件元数据.

        Args:
            conv_id: 会话ID
            file_key: 文件key

        Returns:
            是否成功删除
        """

    @abstractmethod
    async def get_conclusion_files(self, conv_id: str) -> List[AgentFileMetadata]:
        """获取所有结论文件.

        Args:
            conv_id: 会话ID

        Returns:
            结论文件元数据列表
        """

    @abstractmethod
    async def clear_conv_files(self, conv_id: str) -> None:
        """清空会话的所有文件元数据.

        Args:
            conv_id: 会话ID
        """


class SimpleFileMetadataStorage(FileMetadataStorage):
    """简单的文件元数据内存存储实现.

    适用于:
    - AgentFileSystem独立使用场景
    - 测试环境
    - 不需要持久化的临时场景

    特点:
    - 纯内存存储，重启数据丢失
    - 无额外依赖
    - 轻量级实现
    """

    def __init__(self):
        # 存储结构: conv_id -> {file_key -> AgentFileMetadata}
        self._storage: Dict[str, Dict[str, AgentFileMetadata]] = {}

    async def save_file_metadata(self, file_metadata: AgentFileMetadata) -> None:
        """保存文件元数据."""
        conv_id = file_metadata.conv_id
        file_key = file_metadata.file_key

        if conv_id not in self._storage:
            self._storage[conv_id] = {}

        self._storage[conv_id][file_key] = file_metadata

    async def update_file_metadata(self, file_metadata: AgentFileMetadata) -> None:
        """更新文件元数据."""
        await self.save_file_metadata(file_metadata)

    async def get_file_by_key(self, conv_id: str, file_key: str) -> Optional[AgentFileMetadata]:
        """通过file_key获取文件元数据."""
        if conv_id not in self._storage:
            return None
        return self._storage[conv_id].get(file_key)

    async def get_file_by_id(self, conv_id: str, file_id: str) -> Optional[AgentFileMetadata]:
        """通过file_id获取文件元数据."""
        if conv_id not in self._storage:
            return None
        for metadata in self._storage[conv_id].values():
            if metadata.file_id == file_id:
                return metadata
        return None

    async def list_files(
        self,
        conv_id: str,
        file_type: Optional[Union[str, FileType]] = None
    ) -> List[AgentFileMetadata]:
        """列出会话的所有文件."""
        if conv_id not in self._storage:
            return []

        files = list(self._storage[conv_id].values())

        if file_type:
            target_type = file_type.value if isinstance(file_type, FileType) else file_type
            files = [f for f in files if f.file_type == target_type]

        return files

    async def delete_file(self, conv_id: str, file_key: str) -> bool:
        """删除文件元数据."""
        if conv_id not in self._storage:
            return False
        if file_key in self._storage[conv_id]:
            del self._storage[conv_id][file_key]
            return True
        return False

    async def get_conclusion_files(self, conv_id: str) -> List[AgentFileMetadata]:
        """获取所有结论文件."""
        return await self.list_files(conv_id, FileType.CONCLUSION)

    async def clear_conv_files(self, conv_id: str) -> None:
        """清空会话的所有文件元数据."""
        if conv_id in self._storage:
            del self._storage[conv_id]
