import os
import mimetypes
import logging
import base64
from typing import Any, Dict, List, Optional, Tuple, BinaryIO
from dataclasses import dataclass, field

from derisk.core.interface.file import FileStorageClient
from derisk.core.interface.media import MediaContent, MediaObject, MediaContentType

logger = logging.getLogger(__name__)


IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico", ".tiff"
}

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma", ".opus"
}

VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm", ".m4v"
}

DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".md", ".csv", ".json", ".xml", ".html"
}


@dataclass
class MultimodalFileInfo:
    file_id: str
    file_name: str
    file_size: int
    media_type: "MediaType"
    mime_type: str
    uri: str
    bucket: str
    extension: str
    custom_metadata: Dict[str, Any] = field(default_factory=dict)
    file_hash: str = ""


from .model_matcher import MediaType


class MultimodalFileProcessor:

    def __init__(
        self,
        file_storage_client: FileStorageClient,
        max_file_size: int = 100 * 1024 * 1024,
    ):
        self.file_storage_client = file_storage_client
        self.max_file_size = max_file_size

    def detect_media_type(
        self, file_name: str, mime_type: Optional[str] = None
    ) -> MediaType:
        _, ext = os.path.splitext(file_name.lower())

        if ext in IMAGE_EXTENSIONS:
            return MediaType.IMAGE
        if ext in AUDIO_EXTENSIONS:
            return MediaType.AUDIO
        if ext in VIDEO_EXTENSIONS:
            return MediaType.VIDEO
        if ext in DOCUMENT_EXTENSIONS:
            return MediaType.DOCUMENT

        if mime_type:
            if mime_type.startswith("image/"):
                return MediaType.IMAGE
            if mime_type.startswith("audio/"):
                return MediaType.AUDIO
            if mime_type.startswith("video/"):
                return MediaType.VIDEO
            if mime_type.startswith(("application/pdf", "text/", "application/msword")):
                return MediaType.DOCUMENT

        return MediaType.UNKNOWN

    def get_mime_type(self, file_name: str) -> str:
        mime_type, _ = mimetypes.guess_type(file_name)
        return mime_type or "application/octet-stream"

    def validate_file(
        self, file_data: BinaryIO, file_name: str
    ) -> Tuple[bool, Optional[str]]:
        file_data.seek(0, 2)
        file_size = file_data.tell()
        file_data.seek(0)

        if file_size > self.max_file_size:
            return False, f"File size {file_size} exceeds max {self.max_file_size}"

        media_type = self.detect_media_type(file_name)
        if media_type == MediaType.UNKNOWN:
            return False, f"Unsupported file type: {file_name}"

        return True, None

    async def process_upload(
        self,
        bucket: str,
        file_name: str,
        file_data: BinaryIO,
        custom_metadata: Optional[Dict[str, Any]] = None,
        storage_type: Optional[str] = None,
    ) -> MultimodalFileInfo:
        from derisk.util.utils import blocking_func_to_async

        is_valid, error = self.validate_file(file_data, file_name)
        if not is_valid:
            raise ValueError(error)

        mime_type = self.get_mime_type(file_name)
        media_type = self.detect_media_type(file_name, mime_type)
        _, extension = os.path.splitext(file_name.lower())

        uri = self.file_storage_client.save_file(
            bucket=bucket,
            file_name=file_name,
            file_data=file_data,
            storage_type=storage_type,
            custom_metadata=custom_metadata,
        )

        metadata = self.file_storage_client.storage_system.get_file_metadata_by_uri(uri)

        return MultimodalFileInfo(
            file_id=metadata.file_id if metadata else "",
            file_name=file_name,
            file_size=metadata.file_size if metadata else 0,
            media_type=media_type,
            mime_type=mime_type,
            uri=uri,
            bucket=bucket,
            extension=extension,
            custom_metadata=custom_metadata or {},
            file_hash=metadata.file_hash if metadata else "",
        )

    def to_media_content(
        self,
        file_info: MultimodalFileInfo,
        replace_uri_func=None,
    ) -> MediaContent:
        content_type_map = {
            MediaType.IMAGE: MediaContentType.IMAGE,
            MediaType.AUDIO: MediaContentType.AUDIO,
            MediaType.VIDEO: MediaContentType.VIDEO,
            MediaType.DOCUMENT: MediaContentType.FILE,
            MediaType.UNKNOWN: MediaContentType.FILE,
        }

        if replace_uri_func:
            url = replace_uri_func(file_info.uri)
        else:
            url = self.file_storage_client.get_public_url(file_info.uri)

        return MediaContent(
            type=content_type_map.get(file_info.media_type, MediaContentType.FILE),
            object=MediaObject(
                data=url or file_info.uri,
                format=f"url@{file_info.mime_type}",
            ),
        )

    def build_multimodal_message(
        self,
        text: str,
        file_infos: List[MultimodalFileInfo],
        replace_uri_func=None,
    ) -> List[MediaContent]:
        contents: List[MediaContent] = []

        if text:
            contents.append(MediaContent.build_text(text))

        for file_info in file_infos:
            contents.append(self.to_media_content(file_info, replace_uri_func))

        return contents

    def get_file_info_by_uri(self, uri: str) -> Optional[MultimodalFileInfo]:
        metadata = self.file_storage_client.storage_system.get_file_metadata_by_uri(uri)
        if not metadata:
            return None

        media_type = self.detect_media_type(metadata.file_name)
        mime_type = self.get_mime_type(metadata.file_name)
        _, extension = os.path.splitext(metadata.file_name.lower())

        return MultimodalFileInfo(
            file_id=metadata.file_id,
            file_name=metadata.file_name,
            file_size=metadata.file_size,
            media_type=media_type,
            mime_type=mime_type,
            uri=metadata.uri,
            bucket=metadata.bucket,
            extension=extension,
            custom_metadata=metadata.custom_metadata,
            file_hash=metadata.file_hash,
        )