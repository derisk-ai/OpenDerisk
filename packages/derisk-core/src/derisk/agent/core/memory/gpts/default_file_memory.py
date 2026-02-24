"""Default Agent File Memory Implementation."""

import logging
from typing import Dict, List, Optional, Union

from .file_base import (
    AgentFileMemory,
    AgentFileMetadata,
    FileType,
)

logger = logging.getLogger(__name__)


class DefaultAgentFileMemory(AgentFileMemory):
    """默认的文件元数据内存存储实现.

    支持同步和异步操作，可以在内存中快速访问。
    内部使用 _key_index 维护 file_key -> file_id 的映射（即catalog功能）。
    注意：这是一个基础实现，生产环境应该使用数据库持久化。
    """

    def __init__(self):
        # 内存存储: conv_id -> {file_id -> AgentFileMetadata}
        self._storage: Dict[str, Dict[str, AgentFileMetadata]] = {}
        # Catalog索引: conv_id -> {file_key -> file_id}
        self._key_index: Dict[str, Dict[str, str]] = {}

    def append(self, file_metadata: AgentFileMetadata) -> None:
        """添加文件元数据."""
        conv_id = file_metadata.conv_id
        file_id = file_metadata.file_id

        if conv_id not in self._storage:
            self._storage[conv_id] = {}
            self._key_index[conv_id] = {}

        self._storage[conv_id][file_id] = file_metadata
        self._key_index[conv_id][file_metadata.file_key] = file_id

        logger.debug(f"Added file metadata: {file_id} for conv: {conv_id}")

    def update(self, file_metadata: AgentFileMetadata) -> None:
        """更新文件元数据."""
        conv_id = file_metadata.conv_id
        file_id = file_metadata.file_id

        if conv_id in self._storage and file_id in self._storage[conv_id]:
            self._storage[conv_id][file_id] = file_metadata
            logger.debug(f"Updated file metadata: {file_id}")
        else:
            logger.warning(f"File metadata not found: {file_id}")

    async def get_by_conv_id(self, conv_id: str) -> List[AgentFileMetadata]:
        """获取会话的所有文件."""
        if conv_id not in self._storage:
            return []
        return list(self._storage[conv_id].values())

    def get_by_file_id(self, file_id: str) -> Optional[AgentFileMetadata]:
        """获取单个文件元数据."""
        for conv_files in self._storage.values():
            if file_id in conv_files:
                return conv_files[file_id]
        return None

    def get_by_file_key(self, conv_id: str, file_key: str) -> Optional[AgentFileMetadata]:
        """通过file_key获取文件元数据."""
        if conv_id not in self._key_index:
            return None
        file_id = self._key_index[conv_id].get(file_key)
        if file_id:
            return self._storage[conv_id].get(file_id)
        return None

    def delete_by_conv_id(self, conv_id: str) -> None:
        """删除会话的所有文件元数据（包括catalog）."""
        if conv_id in self._storage:
            del self._storage[conv_id]
        if conv_id in self._key_index:
            del self._key_index[conv_id]
        logger.info(f"Deleted all file metadata and catalog for conv: {conv_id}")

    def get_by_file_type(
        self, conv_id: str, file_type: Union[str, FileType]
    ) -> List[AgentFileMetadata]:
        """获取指定类型的所有文件."""
        if conv_id not in self._storage:
            return []

        target_type = file_type.value if isinstance(file_type, FileType) else file_type

        return [
            f for f in self._storage[conv_id].values()
            if f.file_type == target_type
        ]

    def get_conclusion_files(self, conv_id: str) -> List[AgentFileMetadata]:
        """获取所有结论文件（需要推送给用户的）."""
        return self.get_by_file_type(conv_id, FileType.CONCLUSION)

    def get_tool_output_files(self, conv_id: str) -> List[AgentFileMetadata]:
        """获取所有工具输出文件."""
        return self.get_by_file_type(conv_id, FileType.TOOL_OUTPUT)

    # ==================== Catalog 方法 ====================

    def save_catalog(self, conv_id: str, file_key: str, file_id: str) -> None:
        """保存文件到catalog（file_key -> file_id映射）.

        注意：append方法已经自动维护了catalog，此方法用于单独更新catalog场景。
        """
        if conv_id not in self._key_index:
            self._key_index[conv_id] = {}
        self._key_index[conv_id][file_key] = file_id
        logger.debug(f"Updated catalog: {file_key} -> {file_id} for conv: {conv_id}")

    def get_catalog(self, conv_id: str) -> Dict[str, str]:
        """获取文件目录（所有file_key -> file_id映射）."""
        return dict(self._key_index.get(conv_id, {}))

    def get_file_id_by_key(self, conv_id: str, file_key: str) -> Optional[str]:
        """通过file_key获取file_id."""
        if conv_id not in self._key_index:
            return None
        return self._key_index[conv_id].get(file_key)

    def delete_catalog(self, conv_id: str) -> None:
        """删除文件目录."""
        if conv_id in self._key_index:
            del self._key_index[conv_id]
            logger.info(f"Deleted file catalog for conv: {conv_id}")

    def delete_by_file_key(self, conv_id: str, file_key: str) -> bool:
        """通过file_key删除文件元数据.

        Args:
            conv_id: 会话ID
            file_key: 文件key

        Returns:
            是否成功删除
        """
        if conv_id not in self._storage:
            return False

        file_id = self._key_index.get(conv_id, {}).get(file_key)
        if file_id:
            del self._storage[conv_id][file_id]
            del self._key_index[conv_id][file_key]
            logger.debug(f"Deleted file by key: {file_key}")
            return True
        return False
