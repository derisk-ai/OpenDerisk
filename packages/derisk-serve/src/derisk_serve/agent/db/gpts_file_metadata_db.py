"""Gpts File Metadata 数据库模型和 DAO.

用于持久化存储 Agent 文件系统的元数据信息，支持文件恢复和管理。
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Boolean,
    select,
)

from derisk.storage.metadata import BaseDao, Model


class GptsFileMetadataEntity(Model):
    """Gpts 文件元数据实体.

    存储文件的完整元数据信息，支持文件系统恢复。
    """

    __tablename__ = "gpts_file_metadata"
    __table_args__ = (
        Index("idx_file_meta_conv_session", "conv_id", "conv_session_id"),
        Index("idx_file_meta_file_key", "conv_id", "file_key"),
        Index("idx_file_meta_file_type", "conv_id", "file_type"),
    )

    id = Column(Integer, primary_key=True, comment="autoincrement id")

    conv_id = Column(
        String(255), nullable=False, comment="The unique id of the conversation"
    )
    conv_session_id = Column(
        String(255), nullable=False, comment="The session id within conversation"
    )
    file_id = Column(
        String(255), nullable=False, unique=True, comment="The unique id of the file"
    )
    file_key = Column(
        String(512), nullable=False, comment="The key of the file in file system"
    )
    file_name = Column(String(512), nullable=False, comment="The name of the file")
    file_type = Column(String(64), nullable=False, comment="The type of the file")
    file_size = Column(Integer, nullable=False, default=0, comment="The size of file in bytes")
    local_path = Column(String(1024), nullable=False, default="", comment="The local path of the file")

    oss_url = Column(String(1024), nullable=True, comment="The OSS URL of the file")
    preview_url = Column(String(1024), nullable=True, comment="The preview URL of the file")
    download_url = Column(String(1024), nullable=True, comment="The download URL of the file")
    content_hash = Column(String(128), nullable=True, comment="The content hash for deduplication")

    status = Column(
        String(32),
        nullable=False,
        default="completed",
        comment="Status: pending/uploading/completed/failed/expired",
    )
    mime_type = Column(String(128), nullable=True, comment="The MIME type of the file")
    is_public = Column(Boolean, nullable=False, default=False, comment="Whether the file is public")

    created_by = Column(String(255), nullable=True, comment="The agent name that created this file")
    task_id = Column(String(255), nullable=True, comment="The related task id")
    message_id = Column(String(255), nullable=True, comment="The related message id")
    tool_name = Column(String(255), nullable=True, comment="The related tool name")

    file_metadata = Column(Text, name="metadata", nullable=True, comment="Additional metadata (JSON)")

    expires_at = Column(DateTime, nullable=True, comment="The expiration time")
    created_at = Column(
        DateTime, name="gmt_create", default=datetime.utcnow, comment="create time"
    )
    updated_at = Column(
        DateTime,
        name="gmt_modified",
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="last update time",
    )


class GptsFileMetadataDao(BaseDao):
    """Gpts 文件元数据 DAO."""

    def _from_metadata(self, metadata: Dict[str, Any]) -> GptsFileMetadataEntity:
        """将 AgentFileMetadata 字典转换为 GptsFileMetadataEntity."""
        return GptsFileMetadataEntity(
            conv_id=metadata.get("conv_id", ""),
            conv_session_id=metadata.get("conv_session_id", ""),
            file_id=metadata.get("file_id", ""),
            file_key=metadata.get("file_key", ""),
            file_name=metadata.get("file_name", ""),
            file_type=metadata.get("file_type", ""),
            file_size=metadata.get("file_size", 0),
            local_path=metadata.get("local_path", ""),
            oss_url=metadata.get("oss_url"),
            preview_url=metadata.get("preview_url"),
            download_url=metadata.get("download_url"),
            content_hash=metadata.get("content_hash"),
            status=metadata.get("status", "completed"),
            mime_type=metadata.get("mime_type"),
            is_public=metadata.get("is_public", False),
            created_by=metadata.get("created_by"),
            task_id=metadata.get("task_id"),
            message_id=metadata.get("message_id"),
            tool_name=metadata.get("tool_name"),
            file_metadata=json.dumps(metadata.get("metadata"), ensure_ascii=False)
            if metadata.get("metadata")
            else None,
            expires_at=datetime.fromisoformat(metadata["expires_at"])
            if metadata.get("expires_at")
            else None,
            created_at=datetime.fromisoformat(metadata["created_at"])
            if metadata.get("created_at") and isinstance(metadata["created_at"], str)
            else metadata.get("created_at"),
            updated_at=datetime.fromisoformat(metadata["updated_at"])
            if metadata.get("updated_at") and isinstance(metadata["updated_at"], str)
            else metadata.get("updated_at"),
        )

    def _to_metadata(self, entity: GptsFileMetadataEntity) -> Dict[str, Any]:
        """将 GptsFileMetadataEntity 转换为 AgentFileMetadata 字典."""
        return {
            "id": entity.id,
            "conv_id": entity.conv_id,
            "conv_session_id": entity.conv_session_id,
            "file_id": entity.file_id,
            "file_key": entity.file_key,
            "file_name": entity.file_name,
            "file_type": entity.file_type,
            "file_size": entity.file_size,
            "local_path": entity.local_path,
            "oss_url": entity.oss_url,
            "preview_url": entity.preview_url,
            "download_url": entity.download_url,
            "content_hash": entity.content_hash,
            "status": entity.status,
            "mime_type": entity.mime_type,
            "is_public": entity.is_public,
            "created_by": entity.created_by,
            "task_id": entity.task_id,
            "message_id": entity.message_id,
            "tool_name": entity.tool_name,
            "metadata": json.loads(entity.file_metadata) if entity.file_metadata else {},
            "expires_at": entity.expires_at.isoformat() if entity.expires_at else None,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        }

    def save(self, metadata: Dict[str, Any]) -> int:
        """保存文件元数据.

        Args:
            metadata: AgentFileMetadata 字典

        Returns:
            插入记录的 ID
        """
        entity = self._from_metadata(metadata)
        session = self.get_raw_session()
        session.add(entity)
        session.commit()
        record_id = entity.id
        session.close()
        return record_id

    async def save_async(self, metadata: Dict[str, Any]) -> int:
        """异步保存文件元数据."""
        entity = self._from_metadata(metadata)
        async with self.a_session(commit=True) as session:
            session.add(entity)
            await session.flush()
            return entity.id

    def update(self, metadata: Dict[str, Any]) -> bool:
        """更新文件元数据.

        Args:
            metadata: AgentFileMetadata 字典

        Returns:
            是否成功
        """
        session = self.get_raw_session()
        entity = (
            session.query(GptsFileMetadataEntity)
            .filter(GptsFileMetadataEntity.file_id == metadata.get("file_id"))
            .first()
        )
        if not entity:
            session.close()
            return False

        entity.file_name = metadata.get("file_name", entity.file_name)
        entity.file_type = metadata.get("file_type", entity.file_type)
        entity.file_size = metadata.get("file_size", entity.file_size)
        entity.local_path = metadata.get("local_path", entity.local_path)
        entity.oss_url = metadata.get("oss_url", entity.oss_url)
        entity.preview_url = metadata.get("preview_url", entity.preview_url)
        entity.download_url = metadata.get("download_url", entity.download_url)
        entity.content_hash = metadata.get("content_hash", entity.content_hash)
        entity.status = metadata.get("status", entity.status)
        entity.mime_type = metadata.get("mime_type", entity.mime_type)
        entity.is_public = metadata.get("is_public", entity.is_public)
        entity.created_by = metadata.get("created_by", entity.created_by)
        entity.task_id = metadata.get("task_id", entity.task_id)
        entity.message_id = metadata.get("message_id", entity.message_id)
        entity.tool_name = metadata.get("tool_name", entity.tool_name)
        if metadata.get("metadata"):
            entity.file_metadata = json.dumps(metadata.get("metadata"), ensure_ascii=False)
        if metadata.get("expires_at"):
            entity.expires_at = datetime.fromisoformat(metadata["expires_at"])

        session.commit()
        session.close()
        return True

    async def update_async(self, metadata: Dict[str, Any]) -> bool:
        """异步更新文件元数据."""
        async with self.a_session(commit=True) as session:
            result = await session.execute(
                select(GptsFileMetadataEntity).where(
                    GptsFileMetadataEntity.file_id == metadata.get("file_id")
                )
            )
            entity = result.scalar_one_or_none()
            if not entity:
                return False

            entity.file_name = metadata.get("file_name", entity.file_name)
            entity.file_type = metadata.get("file_type", entity.file_type)
            entity.file_size = metadata.get("file_size", entity.file_size)
            entity.local_path = metadata.get("local_path", entity.local_path)
            entity.oss_url = metadata.get("oss_url", entity.oss_url)
            entity.preview_url = metadata.get("preview_url", entity.preview_url)
            entity.download_url = metadata.get("download_url", entity.download_url)
            entity.content_hash = metadata.get("content_hash", entity.content_hash)
            entity.status = metadata.get("status", entity.status)
            entity.mime_type = metadata.get("mime_type", entity.mime_type)
            entity.is_public = metadata.get("is_public", entity.is_public)
            entity.created_by = metadata.get("created_by", entity.created_by)
            entity.task_id = metadata.get("task_id", entity.task_id)
            entity.message_id = metadata.get("message_id", entity.message_id)
            entity.tool_name = metadata.get("tool_name", entity.tool_name)
            if metadata.get("metadata"):
                entity.file_metadata = json.dumps(metadata.get("metadata"), ensure_ascii=False)
            if metadata.get("expires_at"):
                entity.expires_at = datetime.fromisoformat(metadata["expires_at"])

            return True

    def get_by_file_id(self, file_id: str) -> Optional[Dict[str, Any]]:
        """通过 file_id 获取文件元数据."""
        session = self.get_raw_session()
        entity = (
            session.query(GptsFileMetadataEntity)
            .filter(GptsFileMetadataEntity.file_id == file_id)
            .first()
        )
        session.close()
        return self._to_metadata(entity) if entity else None

    async def get_by_file_id_async(self, file_id: str) -> Optional[Dict[str, Any]]:
        """异步通过 file_id 获取文件元数据."""
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsFileMetadataEntity).where(
                    GptsFileMetadataEntity.file_id == file_id
                )
            )
            entity = result.scalar_one_or_none()
            return self._to_metadata(entity) if entity else None

    def get_by_file_key(self, conv_id: str, file_key: str) -> Optional[Dict[str, Any]]:
        """通过 file_key 获取文件元数据."""
        session = self.get_raw_session()
        entity = (
            session.query(GptsFileMetadataEntity)
            .filter(
                GptsFileMetadataEntity.conv_id == conv_id,
                GptsFileMetadataEntity.file_key == file_key,
            )
            .first()
        )
        session.close()
        return self._to_metadata(entity) if entity else None

    async def get_by_file_key_async(
        self, conv_id: str, file_key: str
    ) -> Optional[Dict[str, Any]]:
        """异步通过 file_key 获取文件元数据."""
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsFileMetadataEntity).where(
                    GptsFileMetadataEntity.conv_id == conv_id,
                    GptsFileMetadataEntity.file_key == file_key,
                )
            )
            entity = result.scalar_one_or_none()
            return self._to_metadata(entity) if entity else None

    def get_by_conv_id(self, conv_id: str) -> List[Dict[str, Any]]:
        """获取会话的所有文件元数据."""
        session = self.get_raw_session()
        entities = (
            session.query(GptsFileMetadataEntity)
            .filter(GptsFileMetadataEntity.conv_id == conv_id)
            .order_by(GptsFileMetadataEntity.created_at)
            .all()
        )
        session.close()
        return [self._to_metadata(e) for e in entities]

    async def get_by_conv_id_async(self, conv_id: str) -> List[Dict[str, Any]]:
        """异步获取会话的所有文件元数据."""
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsFileMetadataEntity)
                .where(GptsFileMetadataEntity.conv_id == conv_id)
                .order_by(GptsFileMetadataEntity.created_at)
            )
            entities = result.scalars().all()
            return [self._to_metadata(e) for e in entities]

    def get_by_file_type(
        self, conv_id: str, file_type: str
    ) -> List[Dict[str, Any]]:
        """获取会话指定类型的文件元数据."""
        session = self.get_raw_session()
        entities = (
            session.query(GptsFileMetadataEntity)
            .filter(
                GptsFileMetadataEntity.conv_id == conv_id,
                GptsFileMetadataEntity.file_type == file_type,
            )
            .order_by(GptsFileMetadataEntity.created_at)
            .all()
        )
        session.close()
        return [self._to_metadata(e) for e in entities]

    async def get_by_file_type_async(
        self, conv_id: str, file_type: str
    ) -> List[Dict[str, Any]]:
        """异步获取会话指定类型的文件元数据."""
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsFileMetadataEntity)
                .where(
                    GptsFileMetadataEntity.conv_id == conv_id,
                    GptsFileMetadataEntity.file_type == file_type,
                )
                .order_by(GptsFileMetadataEntity.created_at)
            )
            entities = result.scalars().all()
            return [self._to_metadata(e) for e in entities]

    def delete_by_file_id(self, file_id: str) -> bool:
        """通过 file_id 删除文件元数据."""
        session = self.get_raw_session()
        (
            session.query(GptsFileMetadataEntity)
            .filter(GptsFileMetadataEntity.file_id == file_id)
            .delete()
        )
        session.commit()
        session.close()
        return True

    async def delete_by_file_id_async(self, file_id: str) -> bool:
        """异步通过 file_id 删除文件元数据."""
        async with self.a_session(commit=True) as session:
            await session.execute(
                GptsFileMetadataEntity.__table__.delete().where(
                    GptsFileMetadataEntity.file_id == file_id
                )
            )
        return True

    def delete_by_file_key(self, conv_id: str, file_key: str) -> bool:
        """通过 file_key 删除文件元数据."""
        session = self.get_raw_session()
        (
            session.query(GptsFileMetadataEntity)
            .filter(
                GptsFileMetadataEntity.conv_id == conv_id,
                GptsFileMetadataEntity.file_key == file_key,
            )
            .delete()
        )
        session.commit()
        session.close()
        return True

    async def delete_by_file_key_async(self, conv_id: str, file_key: str) -> bool:
        """异步通过 file_key 删除文件元数据."""
        async with self.a_session(commit=True) as session:
            await session.execute(
                GptsFileMetadataEntity.__table__.delete().where(
                    GptsFileMetadataEntity.conv_id == conv_id,
                    GptsFileMetadataEntity.file_key == file_key,
                )
            )
        return True

    def delete_by_conv_id(self, conv_id: str) -> bool:
        """删除会话的所有文件元数据."""
        session = self.get_raw_session()
        (
            session.query(GptsFileMetadataEntity)
            .filter(GptsFileMetadataEntity.conv_id == conv_id)
            .delete()
        )
        session.commit()
        session.close()
        return True

    async def delete_by_conv_id_async(self, conv_id: str) -> bool:
        """异步删除会话的所有文件元数据."""
        async with self.a_session(commit=True) as session:
            await session.execute(
                GptsFileMetadataEntity.__table__.delete().where(
                    GptsFileMetadataEntity.conv_id == conv_id
                )
            )
        return True

    def get_catalog(self, conv_id: str) -> Dict[str, str]:
        """获取文件目录（file_key -> file_id 映射）."""
        session = self.get_raw_session()
        entities = (
            session.query(GptsFileMetadataEntity.file_key, GptsFileMetadataEntity.file_id)
            .filter(GptsFileMetadataEntity.conv_id == conv_id)
            .all()
        )
        session.close()
        return {e.file_key: e.file_id for e in entities}

    async def get_catalog_async(self, conv_id: str) -> Dict[str, str]:
        """异步获取文件目录（file_key -> file_id 映射）."""
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsFileMetadataEntity.file_key, GptsFileMetadataEntity.file_id)
                .where(GptsFileMetadataEntity.conv_id == conv_id)
            )
            entities = result.all()
            return {e.file_key: e.file_id for e in entities}


class GptsFileCatalogEntity(Model):
    """Gpts 文件目录实体.

    存储会话级别的 file_key -> file_id 映射，用于快速查找。
    """

    __tablename__ = "gpts_file_catalog"
    __table_args__ = (
        Index("idx_file_catalog_conv", "conv_id"),
    )

    id = Column(Integer, primary_key=True, comment="autoincrement id")
    conv_id = Column(
        String(255), nullable=False, comment="The unique id of the conversation"
    )
    file_key = Column(
        String(512), nullable=False, comment="The key of the file in file system"
    )
    file_id = Column(
        String(255), nullable=False, comment="The unique id of the file"
    )
    created_at = Column(
        DateTime, name="gmt_create", default=datetime.utcnow, comment="create time"
    )
    updated_at = Column(
        DateTime,
        name="gmt_modified",
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="last update time"
    )


class GptsFileCatalogDao(BaseDao):
    """Gpts 文件目录 DAO."""

    def save(self, conv_id: str, file_key: str, file_id: str) -> int:
        """保存目录映射."""
        session = self.get_raw_session()
        existing = (
            session.query(GptsFileCatalogEntity)
            .filter(
                GptsFileCatalogEntity.conv_id == conv_id,
                GptsFileCatalogEntity.file_key == file_key,
            )
            .first()
        )
        if existing:
            existing.file_id = file_id
            session.commit()
            session.close()
            return existing.id

        entity = GptsFileCatalogEntity(
            conv_id=conv_id,
            file_key=file_key,
            file_id=file_id,
        )
        session.add(entity)
        session.commit()
        record_id = entity.id
        session.close()
        return record_id

    async def save_async(self, conv_id: str, file_key: str, file_id: str) -> int:
        """异步保存目录映射."""
        async with self.a_session(commit=True) as session:
            result = await session.execute(
                select(GptsFileCatalogEntity).where(
                    GptsFileCatalogEntity.conv_id == conv_id,
                    GptsFileCatalogEntity.file_key == file_key,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.file_id = file_id
                return existing.id

            entity = GptsFileCatalogEntity(
                conv_id=conv_id,
                file_key=file_key,
                file_id=file_id,
            )
            session.add(entity)
            await session.flush()
            return entity.id

    def get_catalog(self, conv_id: str) -> Dict[str, str]:
        """获取会话的文件目录."""
        session = self.get_raw_session()
        entities = (
            session.query(GptsFileCatalogEntity)
            .filter(GptsFileCatalogEntity.conv_id == conv_id)
            .all()
        )
        session.close()
        return {e.file_key: e.file_id for e in entities}

    async def get_catalog_async(self, conv_id: str) -> Dict[str, str]:
        """异步获取会话的文件目录."""
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsFileCatalogEntity).where(
                    GptsFileCatalogEntity.conv_id == conv_id
                )
            )
            entities = result.scalars().all()
            return {e.file_key: e.file_id for e in entities}

    def delete_by_file_key(self, conv_id: str, file_key: str) -> bool:
        """删除目录映射."""
        session = self.get_raw_session()
        (
            session.query(GptsFileCatalogEntity)
            .filter(
                GptsFileCatalogEntity.conv_id == conv_id,
                GptsFileCatalogEntity.file_key == file_key,
            )
            .delete()
        )
        session.commit()
        session.close()
        return True

    async def delete_by_file_key_async(self, conv_id: str, file_key: str) -> bool:
        """异步删除目录映射."""
        async with self.a_session(commit=True) as session:
            await session.execute(
                GptsFileCatalogEntity.__table__.delete().where(
                    GptsFileCatalogEntity.conv_id == conv_id,
                    GptsFileCatalogEntity.file_key == file_key,
                )
            )
        return True

    def delete_by_conv_id(self, conv_id: str) -> bool:
        """删除会话的所有目录映射."""
        session = self.get_raw_session()
        (
            session.query(GptsFileCatalogEntity)
            .filter(GptsFileCatalogEntity.conv_id == conv_id)
            .delete()
        )
        session.commit()
        session.close()
        return True

    async def delete_by_conv_id_async(self, conv_id: str) -> bool:
        """异步删除会话的所有目录映射."""
        async with self.a_session(commit=True) as session:
            await session.execute(
                GptsFileCatalogEntity.__table__.delete().where(
                    GptsFileCatalogEntity.conv_id == conv_id
                )
            )
        return True