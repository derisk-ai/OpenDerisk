"""File dispatch utilities for chat input processing.

文件分流工具，用于在对话入口处理上传的文件：
- 图片/音频/视频文件 → 直接给多模态模型消费
- 其他文件 → 加入AgentFileSystem并同步写入沙箱
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from derisk.core.interface.media import MediaContent, MediaObject, MediaContentType

logger = logging.getLogger(__name__)


def _is_uuid_like(filename: str) -> bool:
    """Check if filename looks like a UUID (file_id)."""
    if not filename:
        return False
    name_without_ext = filename.rsplit(".", 1)[0]
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    return bool(uuid_pattern.match(name_without_ext))


def _get_original_file_name(
    file_path: str, file_name: str, file_storage_client=None
) -> str:
    """Get original file name from metadata if current name is UUID.

    When files are uploaded, they are stored with UUID as file_id, but original
    filename is saved in metadata. This function retrieves the original filename.
    """
    if not _is_uuid_like(file_name):
        return file_name

    if file_storage_client and file_path:
        try:
            if file_path.startswith("derisk-fs://"):
                metadata = file_storage_client.storage_system.get_file_metadata_by_uri(
                    file_path
                )
                if metadata and metadata.file_name:
                    logger.info(
                        f"[FileDispatch] Retrieved original filename: {metadata.file_name} from UUID: {file_name}"
                    )
                    return metadata.file_name
        except Exception as e:
            logger.warning(f"[FileDispatch] Failed to get metadata: {e}")

    return file_name


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".ico",
    ".tiff",
}

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma", ".opus"}

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm", ".m4v"}


class FileDispatchType(str, Enum):
    MULTIMODAL = "multimodal"
    SANDBOX = "sandbox"


@dataclass
class DispatchedFileInfo:
    file_id: str
    file_name: str
    file_size: int
    dispatch_type: FileDispatchType
    mime_type: str
    file_path: str
    bucket: Optional[str] = None
    sandbox_path: Optional[str] = None
    media_content: Optional[MediaContent] = None
    custom_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "file_id": self.file_id,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "dispatch_type": self.dispatch_type.value,
            "mime_type": self.mime_type,
            "file_path": self.file_path,
            "bucket": self.bucket,
            "sandbox_path": self.sandbox_path,
        }
        if self.media_content:
            result["media_content"] = {
                "type": self.media_content.type,
                "data": self.media_content.object.data,
                "format": self.media_content.object.format,
            }
        return result


def get_mime_type(file_name: str) -> str:
    import mimetypes

    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type or "application/octet-stream"


def detect_dispatch_type(
    file_name: str, mime_type: Optional[str] = None
) -> FileDispatchType:
    """检测文件分发类型.

    图片/音频/视频文件返回 MULTIMODAL，其他返回 SANDBOX。
    """
    _, ext = os.path.splitext(file_name.lower())

    if ext in IMAGE_EXTENSIONS or ext in AUDIO_EXTENSIONS or ext in VIDEO_EXTENSIONS:
        return FileDispatchType.MULTIMODAL

    if mime_type:
        if mime_type.startswith(("image/", "audio/", "video/")):
            return FileDispatchType.MULTIMODAL

    return FileDispatchType.SANDBOX


def build_media_content(file_path: str, file_name: str, mime_type: str) -> MediaContent:
    """构建多模态媒体内容."""
    content_type_map = {
        "image": MediaContentType.IMAGE,
        "audio": MediaContentType.AUDIO,
        "video": MediaContentType.VIDEO,
    }

    mime_category = mime_type.split("/")[0] if mime_type else "application"
    content_type = content_type_map.get(mime_category, MediaContentType.FILE)

    return MediaContent(
        type=content_type,
        object=MediaObject(
            data=file_path,
            format=f"url@{mime_type}",
        ),
    )


async def dispatch_file_to_sandbox(
    file_path: str,
    file_name: str,
    file_content: Optional[bytes] = None,
    sandbox_client=None,
    conv_id: Optional[str] = None,
    file_storage_client=None,
) -> Optional[str]:
    """将文件写入沙箱.

    Args:
        file_path: 文件存储路径/URL
        file_name: 文件名
        file_content: 文件内容（可选，如果不提供则从file_path下载）
        sandbox_client: 沙箱客户端
        conv_id: 会话ID
        file_storage_client: 文件存储客户端（用于处理 derisk-fs:// 协议）

    Returns:
        沙箱中的文件路径
    """
    logger.info(
        f"[FileDispatch] dispatch_file_to_sandbox: file_path={file_path}, file_name={file_name}"
    )

    if not sandbox_client:
        logger.warning("No sandbox client available, skipping sandbox write")
        return None

    if not file_path:
        logger.warning(f"Empty file_path for file: {file_name}")
        return None

    try:
        work_dir = sandbox_client.work_dir or "/home/ubuntu"
        sandbox_path = f"{work_dir}/uploads/{file_name}"

        if sandbox_client.file:
            content = None

            if file_content:
                content = file_content
            else:
                # 处理不同类型的文件路径
                actual_file_path = file_path

                if file_path.startswith("derisk-fs://"):
                    # 使用 FileStorageClient 获取公开URL
                    if file_storage_client:
                        try:
                            actual_file_path = file_storage_client.get_public_url(
                                file_path
                            )
                            logger.info(
                                f"Converted derisk-fs URI to public URL: {actual_file_path}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to get public URL for derisk-fs URI: {e}"
                            )
                            return None
                    else:
                        logger.warning(
                            "FileStorageClient not available for derisk-fs:// URI"
                        )
                        return None

                # 下载文件内容
                if actual_file_path.startswith(
                    "http://"
                ) or actual_file_path.startswith("https://"):
                    import httpx

                    async with httpx.AsyncClient() as client:
                        response = await client.get(actual_file_path)
                        content = response.content
                elif os.path.exists(actual_file_path):
                    # 本地文件路径
                    with open(actual_file_path, "rb") as f:
                        content = f.read()
                else:
                    logger.warning(
                        f"Unsupported file path or file not found: {actual_file_path}"
                    )
                    return None

            if content is None:
                logger.warning(f"Failed to get content for file: {file_name}")
                return None

            # 处理内容格式
            if isinstance(content, bytes):
                try:
                    content = content.decode("utf-8")
                except UnicodeDecodeError:
                    import base64

                    content = base64.b64encode(content).decode("utf-8")
                    logger.info(f"Binary file encoded as base64: {file_name}")

            await sandbox_client.file.create(sandbox_path, content, overwrite=True)
            logger.info(f"Wrote file to sandbox: {sandbox_path}")
            return sandbox_path

    except Exception as e:
        logger.warning(f"Failed to write file to sandbox: {e}")

    return None

    try:
        work_dir = sandbox_client.work_dir or "/home/ubuntu"
        sandbox_path = f"{work_dir}/uploads/{file_name}"

        if sandbox_client.file:
            content = None

            if file_content:
                content = file_content
            else:
                # 处理不同类型的文件路径
                if file_path.startswith("derisk-fs://"):
                    # 使用 FileStorageClient 处理 derisk-fs:// 协议
                    if file_storage_client:
                        try:
                            # 先尝试获取公开URL
                            public_url = file_storage_client.get_public_url(file_path)
                            if public_url and public_url.startswith("http"):
                                # 使用公开URL下载
                                import httpx

                                async with httpx.AsyncClient() as client:
                                    response = await client.get(public_url)
                                    content = response.content
                            else:
                                # 直接读取文件内容
                                file_obj = (
                                    file_storage_client.storage_system.load_by_uri(
                                        file_path
                                    )
                                )
                                if file_obj:
                                    content = file_obj.read()
                                    file_obj.close()
                        except Exception as e:
                            logger.warning(f"Failed to read derisk-fs file: {e}")
                    else:
                        logger.warning(
                            "FileStorageClient not available for derisk-fs:// URI"
                        )
                elif file_path.startswith("http://") or file_path.startswith(
                    "https://"
                ):
                    # HTTP URL，使用httpx下载
                    import httpx

                    async with httpx.AsyncClient() as client:
                        response = await client.get(file_path)
                        content = response.content
                else:
                    # 本地文件路径
                    if os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            content = f.read()
                    else:
                        logger.warning(f"File not found: {file_path}")
                        return None

            if content is None:
                logger.warning(f"Failed to get content for file: {file_name}")
                return None

            # 处理内容格式
            if isinstance(content, bytes):
                try:
                    content = content.decode("utf-8")
                except UnicodeDecodeError:
                    import base64

                    content = base64.b64encode(content).decode("utf-8")
                    logger.info(f"Binary file encoded as base64: {file_name}")

            await sandbox_client.file.create(sandbox_path, content, overwrite=True)
            logger.info(f"Wrote file to sandbox: {sandbox_path}")
            return sandbox_path

    except Exception as e:
        logger.warning(f"Failed to write file to sandbox: {e}")

    return None


async def save_file_metadata_to_gpts_memory(
    file_info: DispatchedFileInfo,
    conv_id: str,
    system_app=None,
) -> bool:
    """保存文件元数据到GptsMemory.

    Args:
        file_info: 文件信息
        conv_id: 会话ID
        system_app: 系统应用实例

    Returns:
        是否保存成功
    """
    try:
        from derisk.agent.core.memory.gpts import (
            GptsMemory,
            AgentFileMetadata,
            FileType,
        )
        from derisk.component import ComponentType
        import uuid

        if system_app:
            gpts_memory = system_app.get_component(
                ComponentType.GPTS_MEMORY, GptsMemory
            )
        else:
            logger.debug("system_app not available")
            return False

        if not gpts_memory:
            logger.debug("GptsMemory not available")
            return False

        file_metadata = AgentFileMetadata(
            file_id=file_info.file_id or str(uuid.uuid4()).replace("-", ""),
            conv_id=conv_id,
            conv_session_id=conv_id,
            file_key=f"user_upload/{file_info.file_name}",
            file_name=file_info.file_name,
            file_type=FileType.RESOURCE.value,
            file_size=file_info.file_size,
            local_path=file_info.file_path,
            oss_url=file_info.file_path,
            preview_url=file_info.file_path,
            download_url=file_info.file_path,
            content_hash="",
            status="completed",
            created_by="user",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            metadata={
                "dispatch_type": file_info.dispatch_type.value,
                "mime_type": file_info.mime_type,
                "bucket": file_info.bucket,
                "sandbox_path": file_info.sandbox_path,
            },
            mime_type=file_info.mime_type,
        )

        await gpts_memory.save_file_metadata(file_metadata)
        logger.info(f"Saved file metadata: {file_info.file_name} for conv {conv_id}")
        return True

    except Exception as e:
        logger.warning(f"Failed to save file metadata: {e}")
        return False


def build_file_info_message(sandbox_files: List[DispatchedFileInfo]) -> str:
    """构建沙箱文件信息提示消息.

    Args:
        sandbox_files: 沙箱文件列表

    Returns:
        提示消息文本
    """
    if not sandbox_files:
        return ""

    message = "\n\n[用户上传了以下文件]\n"
    for f in sandbox_files:
        message += f"- 文件名: {f.file_name}\n"
        message += f"  沙箱路径: {f.sandbox_path}\n"
        message += f"  文件大小: {f.file_size} bytes\n"
        message += f"  MIME类型: {f.mime_type}\n"
        if f.bucket:
            message += f"  存储桶: {f.bucket}\n"

    return message


async def process_uploaded_files(
    file_resources: List[Dict[str, Any]],
    conv_id: str,
    sandbox_client=None,
    system_app=None,
    file_storage_client=None,
) -> tuple[List[MediaContent], List[DispatchedFileInfo]]:
    """处理上传的文件，根据类型分流.

    Args:
        file_resources: 文件资源列表（从chat_in_params解析）
        conv_id: 会话ID
        sandbox_client: 沙箱客户端
        system_app: 系统应用实例
        file_storage_client: 文件存储客户端（可选，用于处理 derisk-fs:// 协议）

    Returns:
        tuple: (多模态内容列表, 所有文件信息列表)
    """
    media_contents: List[MediaContent] = []
    all_file_infos: List[DispatchedFileInfo] = []
    sandbox_files: List[DispatchedFileInfo] = []

    for file_res in file_resources:
        # Handle both flat format and OpenAI file_url format
        if file_res.get("type") == "file_url" and "file_url" in file_res:
            # OpenAI compatible format: {"type": "file_url", "file_url": {"url": "...", "file_name": "..."}}
            file_url_data = file_res["file_url"]
            file_name = file_url_data.get("file_name", "unknown")
            file_path = file_url_data.get("url", file_url_data.get("preview_url", ""))
            file_size = file_url_data.get("file_size", 0)
            bucket = file_url_data.get("bucket", "")
            file_id = file_url_data.get("file_id", "")
            logger.info(
                f"[FileDispatch] Processing OpenAI file_url format: name={file_name}, path={file_path}"
            )
        else:
            # Flat format: {"file_path": "...", "file_name": "...", "file_size": ...}
            file_name = file_res.get("file_name", "unknown")
            file_path = file_res.get("file_path", file_res.get("oss_url", ""))
            file_size = file_res.get("file_size", 0)
            bucket = file_res.get("bucket", "")
            file_id = file_res.get("file_id", "")
            logger.info(
                f"[FileDispatch] Processing flat format: name={file_name}, path={file_path}"
            )

        if _is_uuid_like(file_name):
            original_name = _get_original_file_name(
                file_path, file_name, file_storage_client
            )
            if original_name and not _is_uuid_like(original_name):
                file_name = original_name

        mime_type = get_mime_type(file_name)
        dispatch_type = detect_dispatch_type(file_name, mime_type)

        file_info = DispatchedFileInfo(
            file_id=file_id,
            file_name=file_name,
            file_size=file_size,
            dispatch_type=dispatch_type,
            mime_type=mime_type,
            file_path=file_path,
            bucket=bucket,
        )

        if dispatch_type == FileDispatchType.MULTIMODAL:
            file_info.media_content = build_media_content(
                file_path, file_name, mime_type
            )
            media_contents.append(file_info.media_content)
        else:
            sandbox_path = await dispatch_file_to_sandbox(
                file_path=file_path,
                file_name=file_name,
                sandbox_client=sandbox_client,
                conv_id=conv_id,
                file_storage_client=file_storage_client,
            )
            file_info.sandbox_path = sandbox_path
            sandbox_files.append(file_info)

        all_file_infos.append(file_info)

        await save_file_metadata_to_gpts_memory(
            file_info=file_info,
            conv_id=conv_id,
            system_app=system_app,
        )

    # 只有当 sandbox_files 有有效的 sandbox_path 时才添加文件提示
    # 如果 sandbox_path 为 None，说明文件没有写入沙箱，不应该添加提示
    valid_sandbox_files = [f for f in sandbox_files if f.sandbox_path]
    if valid_sandbox_files:
        file_info_text = build_file_info_message(valid_sandbox_files)
        media_contents.insert(0, MediaContent.build_text(file_info_text))
        logger.info(
            f"[FileDispatch] Added file info for {len(valid_sandbox_files)} sandbox files"
        )
    elif sandbox_files:
        logger.warning(
            f"[FileDispatch] {len(sandbox_files)} sandbox files have no sandbox_path, "
            f"skipping file info message"
        )

    return media_contents, all_file_infos
