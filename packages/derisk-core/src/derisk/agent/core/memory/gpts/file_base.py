"""Agent File Memory Models.

参考GptsMessage和GptsPlan的设计，实现文件元数据存储机制。
"""

from __future__ import annotations

import dataclasses
import enum
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Tuple


class FileType(enum.Enum):
    """Agent文件类型分类."""

    TOOL_OUTPUT = "tool_output"  # 工具结果临时文件
    WRITE_FILE = "write_file"  # write工具写入的文件
    SANDBOX_FILE = "sandbox_file"  # 沙箱环境文件
    CONCLUSION = "conclusion"  # 结论文件（需要推送给用户）
    KANBAN = "kanban"  # 看板相关文件
    DELIVERABLE = "deliverable"  # 交付物文件
    TRUNCATED_OUTPUT = "truncated_output"  # 截断输出文件
    WORKFLOW = "workflow"  # 工作流文件
    KNOWLEDGE = "knowledge"  # 知识库文件
    TEMP = "temp"  # 临时文件
    WORK_LOG = "work_log"  # 工作日志文件
    WORK_LOG_SUMMARY = "work_log_summary"  # 工作日志摘要文件
    TODO = "todo"  # 任务列表文件
    HISTORY_CHAPTER = "history_chapter"  # 历史章节归档文件
    HISTORY_CATALOG = "history_catalog"  # 历史目录索引文件
    HISTORY_SUMMARY = "history_summary"  # 历史摘要文件


class FileStatus(enum.Enum):
    """文件状态."""

    PENDING = "pending"  # 待处理
    UPLOADING = "uploading"  # 上传中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    EXPIRED = "expired"  # 已过期


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
        for key in ["created_at", "updated_at", "expires_at"]:
            if result.get(key) and isinstance(result[key], datetime):
                result[key] = result[key].isoformat()
        return result

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AgentFileMetadata":
        """从字典创建."""
        # 处理datetime反序列化
        for key in ["created_at", "updated_at", "expires_at"]:
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
            "created_at": self.created_at.isoformat()
            if isinstance(self.created_at, datetime)
            else self.created_at,
        }


@dataclasses.dataclass
class AgentFileCatalog:
    """Agent文件目录（会话级）.

    存储单个会话的所有文件索引，类似Kanban的catalog。
    """

    conv_id: str
    files: Dict[str, str] = dataclasses.field(
        default_factory=dict
    )  # file_key -> file_id
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
    def get_by_file_key(
        self, conv_id: str, file_key: str
    ) -> Optional[AgentFileMetadata]:
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
    async def get_file_by_key(
        self, conv_id: str, file_key: str
    ) -> Optional[AgentFileMetadata]:
        """通过file_key获取文件元数据.

        Args:
            conv_id: 会话ID
            file_key: 文件key

        Returns:
            文件元数据对象，不存在返回None
        """

    @abstractmethod
    async def get_file_by_id(
        self, conv_id: str, file_id: str
    ) -> Optional[AgentFileMetadata]:
        """通过file_id获取文件元数据.

        Args:
            conv_id: 会话ID
            file_id: 文件ID

        Returns:
            文件元数据对象，不存在返回None
        """

    @abstractmethod
    async def list_files(
        self, conv_id: str, file_type: Optional[Union[str, FileType]] = None
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

    async def get_file_by_key(
        self, conv_id: str, file_key: str
    ) -> Optional[AgentFileMetadata]:
        """通过file_key获取文件元数据."""
        if conv_id not in self._storage:
            return None
        return self._storage[conv_id].get(file_key)

    async def get_file_by_id(
        self, conv_id: str, file_id: str
    ) -> Optional[AgentFileMetadata]:
        """通过file_id获取文件元数据."""
        if conv_id not in self._storage:
            return None
        for metadata in self._storage[conv_id].values():
            if metadata.file_id == file_id:
                return metadata
        return None

    async def list_files(
        self, conv_id: str, file_type: Optional[Union[str, FileType]] = None
    ) -> List[AgentFileMetadata]:
        """列出会话的所有文件."""
        if conv_id not in self._storage:
            return []

        files = list(self._storage[conv_id].values())

        if file_type:
            target_type = (
                file_type.value if isinstance(file_type, FileType) else file_type
            )
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


# ============================================================================
# WorkLog Data Models - 工作日志数据模型
# ============================================================================


class WorkLogStatus(str, enum.Enum):
    """工作日志状态."""

    ACTIVE = "active"
    COMPRESSED = "compressed"
    ARCHIVED = "archived"
    CHAPTER_ARCHIVED = "chapter_archived"


@dataclasses.dataclass
class WorkEntry:
    """
    工作日志条目.

    记录一个工具调用的完整信息，包括输入、输出、时间戳等。
    对于大型输出，使用 full_result_archive 或 archives 引用文件系统中的文件。

    统一了 ReActAgent WorkLog 和 PDCA Agent Kanban 的 WorkEntry 定义。

    新增字段（用于原生 Function Call 模式）：
    - tool_call_id: 工具调用 ID，用于关联 tool message
    - assistant_content: 触发工具调用的 AI 消息内容
    - round_index: 当前轮次索引
    - conv_id: 对话 ID（用于隔离不同对话的工具调用记录）
    """

    timestamp: float
    tool: str
    args: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    result: Optional[str] = None
    full_result_archive: Optional[str] = None
    archives: Optional[List[str]] = None  # 归档文件列表 (PDCA 兼容)
    success: bool = True
    tags: List[str] = dataclasses.field(default_factory=list)
    tokens: int = 0
    status: str = WorkLogStatus.ACTIVE.value
    step_index: int = 0
    # 新增字段：原生 Function Call 模式支持
    tool_call_id: Optional[str] = None  # 工具调用 ID
    assistant_content: Optional[str] = None  # 触发工具调用的 AI 消息内容
    round_index: int = 0  # 当前轮次索引
    conv_id: Optional[str] = None  # 对话 ID（用于隔离不同对话的工具调用记录）
    human_content: Optional[str] = None  # 用户消息内容（用于 __user_message__ 类型条目）
    message_id: Optional[str] = None  # 关联的 GptsMessage ID

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典."""
        return {
            "timestamp": self.timestamp,
            "tool": self.tool,
            "args": self.args,
            "summary": self.summary,
            "result": self.result,
            "full_result_archive": self.full_result_archive,
            "archives": self.archives,
            "success": self.success,
            "tags": self.tags,
            "tokens": self.tokens,
            "status": self.status,
            "step_index": self.step_index,
            "tool_call_id": self.tool_call_id,
            "assistant_content": self.assistant_content,
            "round_index": self.round_index,
            "conv_id": self.conv_id,
            "human_content": self.human_content,
            "message_id": self.message_id,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "WorkEntry":
        """从字典反序列化."""
        status_data = data.pop("status", WorkLogStatus.ACTIVE.value)
        if isinstance(status_data, str):
            pass
        return cls(status=status_data, **data)

    def to_action_output(self) -> "ActionOutput":
        """
        转换为 ActionOutput (用于可视化和其他 Agent).

        映射关系:
        - tool -> action_name
        - args -> action_input
        - result -> content / observations
        - tool_call_id -> action_id
        - success -> is_exe_success
        """
        from derisk.agent.core.action.base import ActionOutput

        view_content = None
        if self.result:
            if len(self.result) > 2000:
                view_content = self.result[:2000] + "\n... (已截断)"
                if self.full_result_archive:
                    view_content += f"\n完整结果: {self.full_result_archive}"
            else:
                view_content = self.result

        simple_view_content = None
        if self.result:
            if len(self.result) > 200:
                simple_view_content = self.result[:200] + "..."
            else:
                simple_view_content = self.result

        extra_data = None
        if self.full_result_archive or self.tokens > 0:
            extra_data = {
                "archive_ref": self.full_result_archive,
                "tokens": self.tokens,
                "timestamp": self.timestamp,
            }

        # ask_user 工具需要恢复 ask_user/ask_type 标记
        # 否则 _recovery_message() 无法识别 ask_user 场景，导致错误恢复旧消息
        is_ask_user = self.tool in ("ask_user", "send_message")
        ask_type_value = None
        if is_ask_user:
            from derisk.agent.core.action.base import AskUserType

            ask_type_value = AskUserType.CONCLUSION_INCOMPLETE.value

        return ActionOutput(
            action_id=self.tool_call_id or "",
            action_name=self.tool,
            action=self.tool,
            action_input=self.args,
            content=self.result or "",
            observations=self.result if not self.success else None,
            is_exe_success=self.success,
            view=view_content,
            simple_view=simple_view_content,
            extra=extra_data,
            ask_user=is_ask_user,
            ask_type=ask_type_value,
        )

    @classmethod
    def from_pdca_entry(cls, data: Dict) -> "WorkEntry":
        """从 PDCA 格式转换 (向后兼容).

        PDCA WorkEntry 格式:
        - timestamp: float
        - tool: str
        - result: Optional[str]
        - summary: Optional[str]
        - archives: Optional[List[str]]
        """
        return cls(
            timestamp=data.get("timestamp", 0.0),
            tool=data.get("tool", ""),
            summary=data.get("summary"),
            result=data.get("result"),
            archives=data.get("archives"),
            success=True,
        )


@dataclasses.dataclass
class WorkLogSummary:
    """
    工作日志摘要.

    当工作日志被压缩时生成摘要，保留关键信息。
    """

    compressed_entries_count: int
    time_range: Tuple[float, float]
    summary_content: str
    key_tools: List[str]
    archive_file: Optional[str] = None
    created_at: float = dataclasses.field(
        default_factory=lambda: datetime.utcnow().timestamp()
    )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典."""
        return {
            "compressed_entries_count": self.compressed_entries_count,
            "time_range": self.time_range,
            "summary_content": self.summary_content,
            "key_tools": self.key_tools,
            "archive_file": self.archive_file,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "WorkLogSummary":
        """从字典反序列化."""
        return cls(**data)


# ============================================================================
# WorkLogStorage Interface - 工作日志存储接口
# ============================================================================


class WorkLogStorage(ABC):
    """工作日志存储接口.

    设计目的:
    1. 将 WorkLog 存储能力统一到 Memory 体系
    2. 支持不同场景下的灵活存储选择:
       - 完整场景: 使用 GptsMemory (带缓存+持久化)
       - 轻量场景: 使用 SimpleWorkLogStorage (仅内存)

    使用示例:
        # 方式1: 使用 GptsMemory (推荐)
        gpts_memory = GptsMemory()
        gpts_memory.append_work_entry(conv_id, entry)

        # 方式2: 直接通过 AgentMemory 访问
        await agent.memory.gpts_memory.append_work_entry(conv_id, entry)
    """

    @abstractmethod
    async def append_work_entry(
        self,
        conv_id: str,
        entry: WorkEntry,
        save_db: bool = True,
    ) -> None:
        """添加工作日志条目.

        Args:
            conv_id: 会话ID
            entry: 工作日志条目
            save_db: 是否持久化到数据库
        """

    @abstractmethod
    async def get_work_log(self, conv_id: str) -> List[WorkEntry]:
        """获取会话的工作日志.

        Args:
            conv_id: 会话ID

        Returns:
            工作日志条目列表
        """

    @abstractmethod
    async def get_work_log_summaries(self, conv_id: str) -> List[WorkLogSummary]:
        """获取会话的工作日志摘要.

        Args:
            conv_id: 会话ID

        Returns:
            工作日志摘要列表
        """

    @abstractmethod
    async def append_work_log_summary(
        self,
        conv_id: str,
        summary: WorkLogSummary,
        save_db: bool = True,
    ) -> None:
        """添加工作日志摘要.

        Args:
            conv_id: 会话ID
            summary: 工作日志摘要
            save_db: 是否持久化到数据库
        """

    @abstractmethod
    async def get_work_log_context(
        self,
        conv_id: str,
        max_entries: int = 50,
        max_tokens: int = 8000,
    ) -> str:
        """获取用于 prompt 的工作日志上下文.

        Args:
            conv_id: 会话ID
            max_entries: 最大条目数
            max_tokens: 最大 token 数

        Returns:
            格式化的上下文文本
        """

    @abstractmethod
    async def clear_work_log(self, conv_id: str) -> None:
        """清空会话的工作日志.

        Args:
            conv_id: 会话ID
        """

    @abstractmethod
    async def get_work_log_stats(self, conv_id: str) -> Dict[str, Any]:
        """获取工作日志统计信息.

        Args:
            conv_id: 会话ID

        Returns:
            统计信息字典
        """

    async def get_history_catalog(self, conv_id: str) -> Optional[Dict[str, Any]]:
        """Get history catalog for a session (optional, for compaction pipeline)."""
        return None

    async def save_history_catalog(
        self, conv_id: str, catalog_data: Dict[str, Any]
    ) -> None:
        """Save history catalog for a session (optional, for compaction pipeline)."""
        pass


class SimpleWorkLogStorage(WorkLogStorage):
    """简单的内存工作日志存储.

    适用于:
    - 测试环境
    - 不需要持久化的临时场景
    """

    def __init__(self):
        self._storage: Dict[str, Dict[str, Any]] = {}

    async def append_work_entry(
        self,
        conv_id: str,
        entry: WorkEntry,
        save_db: bool = True,
    ) -> None:
        if conv_id not in self._storage:
            self._storage[conv_id] = {
                "entries": [],
                "summaries": [],
            }
        self._storage[conv_id]["entries"].append(entry)

    async def get_work_log(self, conv_id: str) -> List[WorkEntry]:
        if conv_id not in self._storage:
            return []
        return self._storage[conv_id]["entries"]

    async def get_work_log_summaries(self, conv_id: str) -> List[WorkLogSummary]:
        if conv_id not in self._storage:
            return []
        return self._storage[conv_id]["summaries"]

    async def append_work_log_summary(
        self,
        conv_id: str,
        summary: WorkLogSummary,
        save_db: bool = True,
    ) -> None:
        if conv_id not in self._storage:
            self._storage[conv_id] = {
                "entries": [],
                "summaries": [],
            }
        self._storage[conv_id]["summaries"].append(summary)

    async def get_work_log_context(
        self,
        conv_id: str,
        max_entries: int = 50,
        max_tokens: int = 8000,
    ) -> str:
        entries = await self.get_work_log(conv_id)
        if not entries:
            return "\n暂无工作日志记录。"

        import time

        lines = ["## 工作日志", ""]
        total_tokens = 0
        chars_per_token = 4

        for entry in entries[-max_entries:]:
            time_str = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
            entry_text = f"[{time_str}] {entry.tool}"
            if entry.args:
                important_args = {
                    k: v
                    for k, v in entry.args.items()
                    if k in ["file_key", "path", "query", "pattern"]
                }
                if important_args:
                    entry_text += f" 参数: {important_args}"
            if entry.result:
                preview = entry.result[:200]
                entry_text += f"\n  {preview}"
            elif entry.full_result_archive:
                entry_text += f"\n  💡 完整结果已归档: {entry.full_result_archive}"

            lines.append(entry_text)
            total_tokens += len(entry_text) // chars_per_token
            if total_tokens > max_tokens:
                break

        return "\n".join(lines)

    async def clear_work_log(self, conv_id: str) -> None:
        if conv_id in self._storage:
            del self._storage[conv_id]

    async def get_work_log_stats(self, conv_id: str) -> Dict[str, Any]:
        entries = await self.get_work_log(conv_id)
        summaries = await self.get_work_log_summaries(conv_id)
        return {
            "total_entries": len(entries),
            "compressed_summaries": len(summaries),
            "success_count": sum(1 for e in entries if e.success),
            "fail_count": sum(1 for e in entries if not e.success),
        }

    async def get_history_catalog(self, conv_id: str) -> Optional[Dict[str, Any]]:
        if conv_id not in self._storage:
            return None
        return self._storage[conv_id].get("history_catalog")

    async def save_history_catalog(
        self, conv_id: str, catalog_data: Dict[str, Any]
    ) -> None:
        if conv_id not in self._storage:
            self._storage[conv_id] = {
                "entries": [],
                "summaries": [],
            }
        self._storage[conv_id]["history_catalog"] = catalog_data


# ============================================================================
# Kanban Data Models - 看板数据模型
# ============================================================================


class StageStatus(str, enum.Enum):
    """阶段状态."""

    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"


@dataclasses.dataclass
class KanbanStage:
    """
    看板阶段.

    每个阶段有明确的交付物定义，以结论为导向。
    """

    stage_id: str
    description: str
    status: str = StageStatus.WORKING.value
    deliverable_type: str = ""
    deliverable_schema: Dict[str, Any] = dataclasses.field(default_factory=dict)
    deliverable_file: str = ""
    work_log: List[WorkEntry] = dataclasses.field(default_factory=list)
    started_at: float = 0.0
    completed_at: float = 0.0
    depends_on: List[str] = dataclasses.field(default_factory=list)
    reflection: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典."""
        return {
            "stage_id": self.stage_id,
            "description": self.description,
            "status": self.status,
            "deliverable_type": self.deliverable_type,
            "deliverable_schema": self.deliverable_schema,
            "deliverable_file": self.deliverable_file,
            "work_log": [e.to_dict() for e in self.work_log],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "depends_on": self.depends_on,
            "reflection": self.reflection,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KanbanStage":
        """从字典反序列化."""
        work_log_data = data.pop("work_log", [])
        work_log = [WorkEntry.from_dict(e) for e in work_log_data]
        return cls(work_log=work_log, **data)

    def is_completed(self) -> bool:
        """判断是否已完成."""
        return self.status == StageStatus.COMPLETED.value

    def is_working(self) -> bool:
        """判断是否工作中."""
        return self.status == StageStatus.WORKING.value


@dataclasses.dataclass
class Kanban:
    """
    看板：线性阶段序列.

    代表整个任务的执行计划。
    """

    kanban_id: str
    mission: str
    stages: List[KanbanStage] = dataclasses.field(default_factory=list)
    current_stage_index: int = 0
    created_at: float = dataclasses.field(
        default_factory=lambda: datetime.utcnow().timestamp()
    )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典."""
        return {
            "kanban_id": self.kanban_id,
            "mission": self.mission,
            "stages": [s.to_dict() for s in self.stages],
            "current_stage_index": self.current_stage_index,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Kanban":
        """从字典反序列化."""
        stages_data = data.pop("stages", [])
        stages = [KanbanStage.from_dict(s) for s in stages_data]
        return cls(stages=stages, **data)

    def get_current_stage(self) -> Optional[KanbanStage]:
        """获取当前正在执行的阶段."""
        if 0 <= self.current_stage_index < len(self.stages):
            return self.stages[self.current_stage_index]
        return None

    def get_stage_by_id(self, stage_id: str) -> Optional[KanbanStage]:
        """根据ID查找阶段."""
        for stage in self.stages:
            if stage.stage_id == stage_id:
                return stage
        return None

    def get_completed_stages(self) -> List[KanbanStage]:
        """获取所有已完成的阶段."""
        return [s for s in self.stages if s.is_completed()]

    def get_pending_stages(self) -> List[KanbanStage]:
        """获取所有待执行的阶段."""
        return [s for s in self.stages[self.current_stage_index + 1 :]]

    def is_all_completed(self) -> bool:
        """判断是否所有阶段都已完成."""
        return all(stage.is_completed() for stage in self.stages)

    def advance_to_next_stage(self) -> bool:
        """推进到下一阶段."""
        if self.current_stage_index < len(self.stages) - 1:
            self.current_stage_index += 1
            next_stage = self.get_current_stage()
            if next_stage:
                next_stage.status = StageStatus.WORKING.value
                next_stage.started_at = datetime.utcnow().timestamp()
            return True
        return False

    def generate_overview(self) -> str:
        """生成看板概览（Markdown格式）."""
        lines = [
            f"# Kanban Overview",
            f"Mission: {self.mission}",
            "",
            "## Progress",
        ]

        progress_icons = []
        for i, stage in enumerate(self.stages):
            if stage.is_completed():
                icon = "✅"
            elif i == self.current_stage_index:
                icon = "🔄"
            else:
                icon = "⏳"
            progress_icons.append(f"[{icon} {stage.stage_id}]")

        lines.append(" -> ".join(progress_icons))
        lines.append("")

        completed = self.get_completed_stages()
        if completed:
            lines.append("## Completed Stages")
            for stage in completed:
                lines.append(f"- **{stage.stage_id}**: {stage.description}")
                if stage.deliverable_file:
                    lines.append(f"  - Deliverable: `{stage.deliverable_file}`")
            lines.append("")

        current = self.get_current_stage()
        if current and not current.is_completed():
            lines.append("## Current Stage")
            lines.append(f"**{current.stage_id}**: {current.description}")
            lines.append("")

        pending = self.get_pending_stages()
        if pending:
            lines.append("## Pending Stages")
            for stage in pending:
                lines.append(f"- **{stage.stage_id}**: {stage.description}")

        return "\n".join(lines)


# ============================================================================
# KanbanStorage Interface - 看板存储接口
# ============================================================================


class KanbanStorage(ABC):
    """看板存储接口.

    设计目的:
    1. 将 Kanban 存储能力统一到 Memory 体系
    2. 支持不同场景下的灵活存储选择:
       - 完整场景: 使用 GptsMemory (带缓存+持久化)
       - 轻量场景: 使用 SimpleKanbanStorage (仅内存)

    使用示例:
        # 方式1: 使用 GptsMemory (推荐)
        gpts_memory = GptsMemory()
        kanban = await gpts_memory.get_kanban(conv_id)
        await gpts_memory.save_kanban(conv_id, kanban)
    """

    @abstractmethod
    async def save_kanban(self, conv_id: str, kanban: Kanban) -> None:
        """保存看板.

        Args:
            conv_id: 会话ID
            kanban: 看板对象
        """

    @abstractmethod
    async def get_kanban(self, conv_id: str) -> Optional[Kanban]:
        """获取看板.

        Args:
            conv_id: 会话ID

        Returns:
            看板对象，不存在返回 None
        """

    @abstractmethod
    async def delete_kanban(self, conv_id: str) -> bool:
        """删除看板.

        Args:
            conv_id: 会话ID

        Returns:
            是否成功删除
        """

    @abstractmethod
    async def save_deliverable(
        self,
        conv_id: str,
        stage_id: str,
        deliverable: Dict[str, Any],
        deliverable_type: str = "",
    ) -> str:
        """保存交付物.

        Args:
            conv_id: 会话ID
            stage_id: 阶段ID
            deliverable: 交付物数据
            deliverable_type: 交付物类型

        Returns:
            交付物文件 key
        """

    @abstractmethod
    async def get_deliverable(
        self, conv_id: str, stage_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取交付物.

        Args:
            conv_id: 会话ID
            stage_id: 阶段ID

        Returns:
            交付物数据，不存在返回 None
        """

    @abstractmethod
    async def get_all_deliverables(self, conv_id: str) -> Dict[str, Dict[str, Any]]:
        """获取所有交付物.

        Args:
            conv_id: 会话ID

        Returns:
            {stage_id: deliverable} 字典
        """

    @abstractmethod
    async def add_work_entry_to_stage(
        self,
        conv_id: str,
        stage_id: str,
        entry: WorkEntry,
    ) -> bool:
        """向指定阶段添加工作日志条目.

        Args:
            conv_id: 会话ID
            stage_id: 阶段ID
            entry: 工作日志条目

        Returns:
            是否成功添加
        """

    @abstractmethod
    async def get_pre_kanban_logs(self, conv_id: str) -> List[WorkEntry]:
        """获取看板创建前的预研日志.

        Args:
            conv_id: 会话ID

        Returns:
            预研日志列表
        """

    @abstractmethod
    async def add_pre_kanban_log(
        self,
        conv_id: str,
        entry: WorkEntry,
    ) -> None:
        """添加预研日志条目.

        Args:
            conv_id: 会话ID
            entry: 工作日志条目
        """

    @abstractmethod
    async def clear_pre_kanban_logs(self, conv_id: str) -> None:
        """清空预研日志.

        Args:
            conv_id: 会话ID
        """


class SimpleKanbanStorage(KanbanStorage):
    """简单的内存看板存储.

    适用于测试环境或不需要持久化的临时场景。
    """

    def __init__(self):
        self._kanbans: Dict[str, Kanban] = {}
        self._deliverables: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._pre_kanban_logs: Dict[str, List[WorkEntry]] = {}

    async def save_kanban(self, conv_id: str, kanban: Kanban) -> None:
        self._kanbans[conv_id] = kanban

    async def get_kanban(self, conv_id: str) -> Optional[Kanban]:
        return self._kanbans.get(conv_id)

    async def delete_kanban(self, conv_id: str) -> bool:
        if conv_id in self._kanbans:
            del self._kanbans[conv_id]
            return True
        return False

    async def save_deliverable(
        self,
        conv_id: str,
        stage_id: str,
        deliverable: Dict[str, Any],
        deliverable_type: str = "",
    ) -> str:
        if conv_id not in self._deliverables:
            self._deliverables[conv_id] = {}
        key = f"{conv_id}_{stage_id}_deliverable"
        self._deliverables[conv_id][stage_id] = deliverable
        return key

    async def get_deliverable(
        self, conv_id: str, stage_id: str
    ) -> Optional[Dict[str, Any]]:
        if conv_id not in self._deliverables:
            return None
        return self._deliverables[conv_id].get(stage_id)

    async def get_all_deliverables(self, conv_id: str) -> Dict[str, Dict[str, Any]]:
        return self._deliverables.get(conv_id, {})

    async def add_work_entry_to_stage(
        self,
        conv_id: str,
        stage_id: str,
        entry: WorkEntry,
    ) -> bool:
        kanban = await self.get_kanban(conv_id)
        if not kanban:
            return False
        stage = kanban.get_stage_by_id(stage_id)
        if not stage:
            return False
        stage.work_log.append(entry)
        return True

    async def get_pre_kanban_logs(self, conv_id: str) -> List[WorkEntry]:
        return self._pre_kanban_logs.get(conv_id, [])

    async def add_pre_kanban_log(
        self,
        conv_id: str,
        entry: WorkEntry,
    ) -> None:
        if conv_id not in self._pre_kanban_logs:
            self._pre_kanban_logs[conv_id] = []
        self._pre_kanban_logs[conv_id].append(entry)

    async def clear_pre_kanban_logs(self, conv_id: str) -> None:
        self._pre_kanban_logs[conv_id] = []


# ============================================================================
# Todo Data Models - 任务列表数据模型（参考 opencode）
# ============================================================================


class TodoStatus(str, enum.Enum):
    """任务状态."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TodoPriority(str, enum.Enum):
    """任务优先级."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclasses.dataclass
class TodoItem:
    """
    任务项.

    参考 opencode 的设计，保持简洁。
    """

    id: str
    content: str
    status: str = TodoStatus.PENDING.value
    priority: str = TodoPriority.MEDIUM.value
    created_at: float = dataclasses.field(
        default_factory=lambda: datetime.utcnow().timestamp()
    )
    updated_at: float = dataclasses.field(
        default_factory=lambda: datetime.utcnow().timestamp()
    )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典."""
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status,
            "priority": self.priority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TodoItem":
        """从字典反序列化."""
        return cls(
            id=data.get("id", ""),
            content=data.get("content", ""),
            status=data.get("status", TodoStatus.PENDING.value),
            priority=data.get("priority", TodoPriority.MEDIUM.value),
            created_at=data.get("created_at", datetime.utcnow().timestamp()),
            updated_at=data.get("updated_at", datetime.utcnow().timestamp()),
        )

    def update_status(self, new_status: str) -> "TodoItem":
        """更新状态并返回新实例."""
        return TodoItem(
            id=self.id,
            content=self.content,
            status=new_status,
            priority=self.priority,
            created_at=self.created_at,
            updated_at=datetime.utcnow().timestamp(),
        )


# ============================================================================
# TodoStorage Interface - 任务列表存储接口
# ============================================================================


class TodoStorage(ABC):
    """任务列表存储接口.

    参考 opencode 的 todowrite/todoread 工具设计，保持简洁。

    设计目的:
    1. 简单的任务列表管理
    2. LLM 自主决策何时使用
    3. 状态仅包含 pending/in_progress/completed/cancelled
    4. 无需定义交付物 Schema
    """

    @abstractmethod
    async def write_todos(self, conv_id: str, todos: List[TodoItem]) -> None:
        """写入任务列表.

        Args:
            conv_id: 会话ID
            todos: 任务列表
        """

    @abstractmethod
    async def read_todos(self, conv_id: str) -> List[TodoItem]:
        """读取任务列表.

        Args:
            conv_id: 会话ID

        Returns:
            任务列表
        """

    @abstractmethod
    async def clear_todos(self, conv_id: str) -> None:
        """清空任务列表.

        Args:
            conv_id: 会话ID
        """


class SimpleTodoStorage(TodoStorage):
    """简单的内存任务列表存储."""

    def __init__(self):
        self._storage: Dict[str, List[TodoItem]] = {}

    async def write_todos(self, conv_id: str, todos: List[TodoItem]) -> None:
        self._storage[conv_id] = todos

    async def read_todos(self, conv_id: str) -> List[TodoItem]:
        return self._storage.get(conv_id, [])

    async def clear_todos(self, conv_id: str) -> None:
        if conv_id in self._storage:
            del self._storage[conv_id]
