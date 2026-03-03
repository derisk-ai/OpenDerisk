import logging
from typing import Any, Dict, List, Optional, BinaryIO

from derisk.component import SystemApp
from derisk.core.interface.file import FileStorageClient
from derisk.core.interface.media import MediaContent

from ..config import ServeConfig, SERVE_SERVICE_COMPONENT_NAME
from ..file_processor import MultimodalFileProcessor, MultimodalFileInfo, MediaType
from ..model_matcher import (
    MultimodalModelMatcher,
    ModelInfo,
    ModelCapability,
)

logger = logging.getLogger(__name__)

USER_UPLOAD_FILE_TYPE = "user_upload"


class MultimodalService:
    """Multimodal service for handling multi-modal content.

    集成文件存储、元数据管理和模型匹配功能。
    用户上传的文件会被记录到 AgentFileMetadata 系统中，
    以便在对话历史和 Agent 消息系统中可查看。
    """

    def __init__(self, system_app: SystemApp, config: ServeConfig):
        self.system_app = system_app
        self.config = config
        self._file_storage_client: Optional[FileStorageClient] = None
        self._file_processor: Optional[MultimodalFileProcessor] = None
        self._model_matcher: Optional[MultimodalModelMatcher] = None
        self._file_serve = None
        self._file_metadata_storage = None

    def init_app(self, system_app: SystemApp) -> None:
        self.system_app = system_app

    def _get_file_serve(self):
        if self._file_serve:
            return self._file_serve
        try:
            from derisk_serve.file.serve import Serve as FileServe
            self._file_serve = FileServe.get_instance(self.system_app)
            return self._file_serve
        except Exception as e:
            logger.warning(f"Failed to get FileServe: {e}")
            return None

    def _get_file_metadata_storage(self):
        """获取文件元数据存储（用于记录用户上传的文件）."""
        if self._file_metadata_storage:
            return self._file_metadata_storage
        try:
            from derisk.agent.core.memory.gpts import GptsMemory
            gpts_memory = GptsMemory.get_instance(self.system_app)
            if gpts_memory:
                self._file_metadata_storage = gpts_memory
                return self._file_metadata_storage
        except Exception as e:
            logger.debug(f"GptsMemory not available: {e}")
        return None

    @property
    def file_storage_client(self) -> FileStorageClient:
        if self._file_storage_client:
            return self._file_storage_client

        file_serve = self._get_file_serve()
        if file_serve:
            self._file_storage_client = file_serve.file_storage_client
            return self._file_storage_client

        client = FileStorageClient.get_instance(
            self.system_app, default_component=None
        )
        if client:
            self._file_storage_client = client
            return client

        self._file_storage_client = FileStorageClient()
        return self._file_storage_client

    @property
    def file_processor(self) -> MultimodalFileProcessor:
        if not self._file_processor:
            self._file_processor = MultimodalFileProcessor(
                file_storage_client=self.file_storage_client,
                max_file_size=self.config.max_file_size or 100 * 1024 * 1024,
            )
        return self._file_processor

    @property
    def model_matcher(self) -> MultimodalModelMatcher:
        if not self._model_matcher:
            self._model_matcher = MultimodalModelMatcher(
                default_text_model=self.config.default_text_model or "gpt-4o-mini",
                default_image_model=self.config.default_image_model or "gpt-4o",
                default_audio_model=self.config.default_audio_model or "qwen-audio-turbo",
                default_video_model=self.config.default_video_model or "qwen-vl-max",
            )
        return self._model_matcher

    def replace_uri(self, uri: str) -> str:
        """Replace internal URI with accessible URL."""
        file_serve = self._get_file_serve()
        if file_serve:
            return file_serve.replace_uri(uri)
        return self.file_storage_client.get_public_url(uri) or uri

    def upload_file(
        self,
        file_name: str,
        file_data: BinaryIO,
        bucket: Optional[str] = None,
        conv_id: Optional[str] = None,
        message_id: Optional[str] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> MultimodalFileInfo:
        """Upload a file and return file info.
        
        Args:
            file_name: 文件名
            file_data: 文件数据
            bucket: 存储桶名称
            conv_id: 会话ID（用于关联到会话）
            message_id: 消息ID（用于关联到消息）
            custom_metadata: 自定义元数据
        """
        bucket = bucket or self.config.default_bucket or "multimodal_files"

        from derisk.util.utils import blocking_func_to_async
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()

        file_info = loop.run_until_complete(
            self.file_processor.process_upload(
                bucket=bucket,
                file_name=file_name,
                file_data=file_data,
                custom_metadata=custom_metadata,
            )
        )
        
        if conv_id:
            loop.run_until_complete(
                self._save_file_metadata(
                    file_info=file_info,
                    conv_id=conv_id,
                    message_id=message_id,
                )
            )
        
        return file_info

    async def _save_file_metadata(
        self,
        file_info: MultimodalFileInfo,
        conv_id: str,
        message_id: Optional[str] = None,
    ) -> None:
        """保存文件元数据到存储系统，以便在Agent消息系统中可查看."""
        metadata_storage = self._get_file_metadata_storage()
        if not metadata_storage:
            logger.debug("FileMetadataStorage not available, skip saving metadata")
            return
        
        try:
            from derisk.agent.core.memory.gpts import AgentFileMetadata, FileType
            
            import uuid
            from datetime import datetime
            
            public_url = self.replace_uri(file_info.uri)
            
            file_metadata = AgentFileMetadata(
                file_id=file_info.file_id or str(uuid.uuid4().hex),
                conv_id=conv_id,
                conv_session_id=conv_id,
                file_key=f"user_upload/{file_info.file_id or uuid.uuid4().hex}",
                file_name=file_info.file_name,
                file_type=USER_UPLOAD_FILE_TYPE,
                local_path=file_info.uri,
                file_size=file_info.file_size,
                oss_url=public_url,
                preview_url=public_url,
                download_url=public_url,
                content_hash=file_info.file_hash,
                status="completed",
                created_by="user",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                metadata={
                    "media_type": file_info.media_type.value,
                    "mime_type": file_info.mime_type,
                    "extension": file_info.extension,
                    "bucket": file_info.bucket,
                },
                mime_type=file_info.mime_type,
                message_id=message_id,
            )
            
            await metadata_storage.save_file_metadata(file_metadata)
            logger.info(f"Saved file metadata for {file_info.file_name} in conv {conv_id}")
            
        except Exception as e:
            logger.warning(f"Failed to save file metadata: {e}")

    async def list_user_files(
        self,
        conv_id: str,
    ) -> List[Dict[str, Any]]:
        """列出会话中用户上传的文件.
        
        Args:
            conv_id: 会话ID
            
        Returns:
            文件信息列表
        """
        metadata_storage = self._get_file_metadata_storage()
        if not metadata_storage:
            return []
        
        try:
            files = await metadata_storage.list_files(conv_id, USER_UPLOAD_FILE_TYPE)
            return [f.to_dict() for f in files]
        except Exception as e:
            logger.warning(f"Failed to list user files: {e}")
            return []

    def get_file_info(self, uri: str) -> Optional[Dict[str, Any]]:
        """Get file info by URI."""
        file_info = self.file_processor.get_file_info_by_uri(uri)
        if not file_info:
            return None

        public_url = self.replace_uri(uri)

        return {
            "file_id": file_info.file_id,
            "file_name": file_info.file_name,
            "file_size": file_info.file_size,
            "media_type": file_info.media_type.value,
            "mime_type": file_info.mime_type,
            "uri": file_info.uri,
            "public_url": public_url,
            "extension": file_info.extension,
            "file_hash": file_info.file_hash,
        }

    def match_model_for_content(
        self,
        content: List[MediaContent],
        preferred_provider: Optional[str] = None,
    ) -> Optional[str]:
        """Match best model for given content."""
        from derisk.core.interface.media import MediaContentType

        media_types = []
        for c in content:
            if isinstance(c, MediaContent):
                if c.type == MediaContentType.IMAGE:
                    media_types.append(MediaType.IMAGE)
                elif c.type == MediaContentType.AUDIO:
                    media_types.append(MediaType.AUDIO)
                elif c.type == MediaContentType.VIDEO:
                    media_types.append(MediaType.VIDEO)
                elif c.type == MediaContentType.FILE:
                    media_types.append(MediaType.DOCUMENT)
            elif isinstance(c, dict):
                content_type = c.get("type", "")
                if content_type == "image":
                    media_types.append(MediaType.IMAGE)
                elif content_type == "audio":
                    media_types.append(MediaType.AUDIO)
                elif content_type == "video":
                    media_types.append(MediaType.VIDEO)

        if not media_types:
            return self.model_matcher.default_text_model

        model_info = self.model_matcher.match_model_for_media_types(
            media_types=media_types,
            preferred_provider=preferred_provider,
        )
        return model_info.model_name if model_info else None

    def process_multimodal_content(
        self,
        text: Optional[str] = None,
        file_uris: Optional[List[str]] = None,
        preferred_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process multimodal content and return processed result."""
        file_infos: List[MultimodalFileInfo] = []
        file_responses: List[Dict[str, Any]] = []

        if file_uris:
            for uri in file_uris:
                file_info = self.file_processor.get_file_info_by_uri(uri)
                if file_info:
                    file_infos.append(file_info)
                    file_responses.append(self.get_file_info(uri))

        media_contents = self.file_processor.build_multimodal_message(
            text=text or "",
            file_infos=file_infos,
            replace_uri_func=self.replace_uri,
        )

        matched_model = self.match_model_for_content(
            media_contents, preferred_provider
        )

        return {
            "content": media_contents,
            "matched_model": matched_model,
            "file_infos": file_responses,
        }

    def list_supported_models(
        self,
        capability: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List supported models with optional filtering."""
        models = []

        if capability:
            try:
                cap = ModelCapability(capability)
                model_infos = self.model_matcher.list_models_for_capability(
                    cap, provider
                )
            except ValueError:
                model_infos = list(self.model_matcher.model_registry.values())
                if provider:
                    model_infos = [m for m in model_infos if m.provider == provider]
        else:
            model_infos = list(self.model_matcher.model_registry.values())
            if provider:
                model_infos = [m for m in model_infos if m.provider == provider]

        for model_info in model_infos:
            models.append({
                "model_name": model_info.model_name,
                "provider": model_info.provider,
                "capabilities": [cap.value for cap in model_info.capabilities],
                "context_length": model_info.context_length,
                "max_output_tokens": model_info.max_output_tokens,
                "priority": model_info.priority,
            })

        return models

    @classmethod
    def get_instance(
        cls, system_app: SystemApp
    ) -> Optional["MultimodalService"]:
        return system_app.get_component(
            SERVE_SERVICE_COMPONENT_NAME, MultimodalService
        )