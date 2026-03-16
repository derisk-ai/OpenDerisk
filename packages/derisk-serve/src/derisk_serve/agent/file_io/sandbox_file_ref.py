"""Sandbox File Reference and File Input Processing for OpenDeRisk

Handles file routing between model direct consumption and sandbox tool processing.
"""

import json
import logging
import mimetypes
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from derisk.sandbox.base import SandboxBase

logger = logging.getLogger(__name__)

# Sandbox file storage base path
SANDBOX_UPLOAD_DIR = "/home/user/uploads"


class UserInputType(Enum):
    """User input file type enumeration (backward compatible)"""

    IMAGE_URL = "image_url"  # Image type - multimodal message direct consumption
    FILE_URL = "file_url"  # Other file types - Sandbox storage


@dataclass
class SandboxFileRef:
    """Sandbox file reference information for non-model direct consumption files"""

    file_name: str
    url: str
    full_url: Optional[str] = None
    file_type: Optional[str] = None  # File MIME type or extension
    process_mode: str = "sandbox_tool"  # Processing mode: model_direct or sandbox_tool
    sandbox_path: Optional[str] = None  # Complete path in sandbox
    mime_type: Optional[str] = None  # MIME type
    file_size: Optional[int] = None  # File size in bytes
    file_id: Optional[str] = None  # Unique file identifier
    bucket: Optional[str] = None  # Storage bucket
    object_path: Optional[str] = None  # OSS object path
    local_path: Optional[str] = None  # Local file path (for local sandbox)
    content: Optional[bytes] = None  # File content (for small files)

    def to_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "url": self.url,
            "full_url": self.full_url,
            "file_type": self.file_type,
            "process_mode": self.process_mode,
            "sandbox_path": self.sandbox_path,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "file_id": self.file_id,
            "bucket": self.bucket,
            "object_path": self.object_path,
            "local_path": self.local_path,
        }

    def get_sandbox_path(self) -> str:
        """Get complete path in sandbox"""
        if self.sandbox_path:
            return self.sandbox_path
        # Default path rule
        return f"{SANDBOX_UPLOAD_DIR}/{self.file_name}"

    def get_extension(self) -> str:
        """Get file extension"""
        if not self.file_name:
            return ""
        parts = self.file_name.rsplit(".", 1)
        if len(parts) == 2:
            return f".{parts[1].lower()}"
        return ""


def detect_file_type(file_name: str) -> Optional[str]:
    """Detect file type based on file name

    Args:
        file_name: File name

    Returns:
        File type (extension)
    """
    if not file_name:
        return None
    parts = file_name.rsplit(".", 1)
    if len(parts) == 2:
        return parts[1].lower()
    return None


def detect_mime_type(file_name: str) -> Optional[str]:
    """Detect MIME type based on file name

    Args:
        file_name: File name

    Returns:
        MIME type string
    """
    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type


def is_image_file(file_name: str) -> bool:
    """Check if file is an image

    Args:
        file_name: File name

    Returns:
        Whether the file is an image
    """
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}
    ext = f".{detect_file_type(file_name)}" if detect_file_type(file_name) else ""
    return ext.lower() in image_extensions


@dataclass
class FileProcessResult:
    """Result of file processing"""

    multimodal_contents: List[Dict[str, Any]] = field(default_factory=list)
    sandbox_file_refs: List[SandboxFileRef] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


async def download_file_from_url(
    url: str, timeout: int = 300
) -> Tuple[Optional[bytes], Optional[str]]:
    """Download file from URL

    Args:
        url: File URL
        timeout: Download timeout in seconds

    Returns:
        Tuple of (file_content, error_message)
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    content = await response.read()
                    return content, None
                else:
                    return None, f"HTTP error: {response.status}"
    except Exception as e:
        return None, str(e)


async def process_user_input_file(
    user_input: dict,
    sandbox: Optional["SandboxBase"] = None,
    conv_id: Optional[str] = None,
    local_upload_dir: Optional[str] = None,
) -> Tuple[Optional[dict], Optional[SandboxFileRef], Optional[str]]:
    """Process a single user input file

    Processing logic:
    1. First check input_type (image_url/file_url)
    2. Then determine processing mode based on file extension

    Args:
        user_input: User input item containing type and file info
        sandbox: Sandbox instance (optional)
        conv_id: Conversation ID
        local_upload_dir: Local upload directory (for local sandbox)

    Returns:
        Tuple[Optional[dict], Optional[SandboxFileRef], Optional[str]]:
            - Multimodal message content (for model direct consumption)
            - Sandbox file reference (for tool consumption)
            - Error message (if any)
    """
    from .file_type_config import (
        FileProcessMode,
        get_file_process_mode,
    )

    input_type = user_input.get("type")

    # Get file information
    file_name = ""
    file_url = ""
    full_url = None
    file_id = None
    bucket = None
    object_path = None
    file_size = None
    mime_type = None

    if input_type == "image_url":
        image_url_data = user_input.get("image_url", {})
        file_name = image_url_data.get("file_name", "")
        file_url = image_url_data.get("url", "")
        full_url = image_url_data.get("full_url")
        file_id = image_url_data.get("file_id")
        mime_type = detect_mime_type(file_name) or "image/jpeg"
    elif input_type == "file_url":
        file_url_data = user_input.get("file_url", {})
        file_name = file_url_data.get("file_name", "")
        file_url = file_url_data.get("url", "")
        full_url = file_url_data.get("full_url")
        file_id = file_url_data.get("file_id")
        bucket = file_url_data.get("bucket")
        object_path = file_url_data.get("object_path")
        file_size = file_url_data.get("file_size")
        mime_type = file_url_data.get("mime_type") or detect_mime_type(file_name)
    else:
        logger.warning(f"[FileIO] Unknown user input type: {input_type}")
        return None, None, f"Unknown input type: {input_type}"

    # Use dynamic configuration to determine processing mode
    file_ext = detect_file_type(file_name)
    process_mode = get_file_process_mode(file_name, mime_type)

    if process_mode == FileProcessMode.MODEL_DIRECT:
        # Model direct consumption: as multimodal message
        if input_type == "image_url":
            image_url_data = user_input.get("image_url", {})
            return (
                {
                    "type": "image_url",
                    "image_url": image_url_data,
                },
                None,
                None,
            )
        else:
            # Other types also try as multimodal message (like file_url)
            file_url_data = user_input.get("file_url", {})
            return (
                {
                    "type": "file_url",
                    "file_url": file_url_data,
                },
                None,
                None,
            )
    else:
        # Sandbox tool consumption: create file reference
        sandbox_path = f"{SANDBOX_UPLOAD_DIR}/{file_name}"

        # For local sandbox, we need to handle file download/storage
        local_path = None
        content = None

        # Check if it's a derisk-fs URI or local file path
        if file_url and file_url.startswith("derisk-fs://"):
            # This is a stored file, will be handled by the storage system
            pass
        elif file_url and (
            file_url.startswith("http://") or file_url.startswith("https://")
        ):
            # Download file content
            if sandbox is None and local_upload_dir:
                # Local sandbox mode - download to local directory
                try:
                    content, error = await download_file_from_url(file_url)
                    if content:
                        os.makedirs(local_upload_dir, exist_ok=True)
                        local_path = os.path.join(local_upload_dir, file_name)
                        with open(local_path, "wb") as f:
                            f.write(content)
                        file_size = len(content)
                except Exception as e:
                    logger.warning(f"[FileIO] Failed to download file: {e}")

        sandbox_ref = SandboxFileRef(
            file_name=file_name,
            url=file_url,
            full_url=full_url,
            file_type=file_ext,
            process_mode="sandbox_tool",
            sandbox_path=sandbox_path,
            mime_type=mime_type,
            file_size=file_size,
            file_id=file_id,
            bucket=bucket,
            object_path=object_path,
            local_path=local_path,
            content=content,
        )
        return None, sandbox_ref, None


async def process_chat_input_files(
    user_inputs: List[dict],
    sandbox: Optional["SandboxBase"] = None,
    conv_id: Optional[str] = None,
    local_upload_dir: Optional[str] = None,
) -> FileProcessResult:
    """Process user input files from chat request

    Supports two formats:
    1. extendContext.userInputs - New format (image_url/file_url)
    2. chat_in_params - Old format (resource type parameters)

    Args:
        user_inputs: List of user input items
        sandbox: Sandbox instance (optional)
        conv_id: Conversation ID
        local_upload_dir: Local upload directory (for local sandbox)

    Returns:
        FileProcessResult containing multimodal contents and sandbox file refs
    """
    result = FileProcessResult()

    for user_input in user_inputs:
        try:
            content, sandbox_ref, error = await process_user_input_file(
                user_input, sandbox, conv_id, local_upload_dir
            )
            if content is not None:
                result.multimodal_contents.append(content)
            if sandbox_ref is not None:
                result.sandbox_file_refs.append(sandbox_ref)
            if error:
                result.errors.append(error)
        except Exception as e:
            logger.error(f"[FileIO] Error processing user input: {e}")
            result.errors.append(str(e))

    return result


def build_enhanced_query_with_files(
    original_query: str, sandbox_file_refs: List[SandboxFileRef]
) -> str:
    """Build enhanced query message with file information

    Associates uploaded files with the original question to help the model understand context.
    Displays complete sandbox paths for model to use directly.

    Args:
        original_query: User's original question
        sandbox_file_refs: List of sandbox file references

    Returns:
        Enhanced query message
    """
    # Build file list (including complete sandbox paths)
    file_list_lines = []
    for i, ref in enumerate(sandbox_file_refs, 1):
        sandbox_path = ref.get_sandbox_path()
        file_info = f"{i}. `{sandbox_path}`"
        if ref.file_type:
            file_info += f" (.{ref.file_type})"
        if ref.file_size:
            file_info += f" - {ref.file_size} bytes"
        file_list_lines.append(file_info)

    file_list_str = "\n".join(file_list_lines)

    # Build enhanced message
    enhanced_query = f"""{original_query}

---

📎 **User uploaded files**:

{file_list_str}"""

    return enhanced_query


async def initialize_files_in_sandbox(
    sandbox: "SandboxBase",
    sandbox_file_refs: List[SandboxFileRef],
    conv_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Initialize files in sandbox

    Downloads files from URLs and stores them in the sandbox working directory.

    Args:
        sandbox: Sandbox instance
        sandbox_file_refs: List of sandbox file references
        conv_id: Conversation ID

    Returns:
        Dictionary with initialization results
    """
    results = {
        "success": [],
        "failed": [],
        "skipped": [],
    }

    if not sandbox:
        logger.warning("[FileIO] No sandbox provided, skipping file initialization")
        return results

    for ref in sandbox_file_refs:
        try:
            sandbox_path = ref.get_sandbox_path()

            # Check if file has local content
            if ref.local_path and os.path.exists(ref.local_path):
                # Read local file and upload to sandbox
                with open(ref.local_path, "rb") as f:
                    content = f.read()

                # Try to use sandbox file client if available
                if hasattr(sandbox, "file") and sandbox.file:
                    try:
                        await sandbox.file.create(
                            sandbox_path, content.decode("utf-8", errors="replace")
                        )
                        results["success"].append(
                            {
                                "file_name": ref.file_name,
                                "sandbox_path": sandbox_path,
                            }
                        )
                        continue
                    except Exception as e:
                        logger.warning(f"[FileIO] Sandbox file.create failed: {e}")

                # Fallback: use shell command to create file
                try:
                    # Create directory
                    dir_path = os.path.dirname(sandbox_path)
                    if dir_path:
                        await sandbox.shell.exec_command(f"mkdir -p {dir_path}")

                    # Write file using base64 encoding
                    import base64

                    encoded_content = base64.b64encode(content).decode("utf-8")
                    await sandbox.shell.exec_command(
                        f"echo '{encoded_content}' | base64 -d > {sandbox_path}"
                    )
                    results["success"].append(
                        {
                            "file_name": ref.file_name,
                            "sandbox_path": sandbox_path,
                        }
                    )
                except Exception as e:
                    logger.error(f"[FileIO] Failed to write file to sandbox: {e}")
                    results["failed"].append(
                        {
                            "file_name": ref.file_name,
                            "error": str(e),
                        }
                    )

            elif ref.url:
                # Download from URL
                content, error = await download_file_from_url(ref.url)
                if content:
                    # Write to sandbox
                    if hasattr(sandbox, "file") and sandbox.file:
                        try:
                            await sandbox.file.create(
                                sandbox_path, content.decode("utf-8", errors="replace")
                            )
                            results["success"].append(
                                {
                                    "file_name": ref.file_name,
                                    "sandbox_path": sandbox_path,
                                }
                            )
                            continue
                        except Exception as e:
                            logger.warning(f"[FileIO] Sandbox file.create failed: {e}")

                    # Fallback: use wget/curl
                    try:
                        dir_path = os.path.dirname(sandbox_path)
                        if dir_path:
                            await sandbox.shell.exec_command(f"mkdir -p {dir_path}")
                        await sandbox.shell.exec_command(
                            f"wget -q -O {sandbox_path} '{ref.url}' || curl -s -o {sandbox_path} '{ref.url}'"
                        )
                        results["success"].append(
                            {
                                "file_name": ref.file_name,
                                "sandbox_path": sandbox_path,
                            }
                        )
                    except Exception as e:
                        logger.error(f"[FileIO] Failed to download to sandbox: {e}")
                        results["failed"].append(
                            {
                                "file_name": ref.file_name,
                                "error": str(e),
                            }
                        )
                else:
                    results["failed"].append(
                        {
                            "file_name": ref.file_name,
                            "error": error or "Failed to download file",
                        }
                    )
            else:
                results["skipped"].append(
                    {
                        "file_name": ref.file_name,
                        "reason": "No URL or local content",
                    }
                )

        except Exception as e:
            logger.error(f"[FileIO] Error initializing file {ref.file_name}: {e}")
            results["failed"].append(
                {
                    "file_name": ref.file_name,
                    "error": str(e),
                }
            )

    logger.info(
        f"[FileIO] File initialization complete: {len(results['success'])} success, "
        f"{len(results['failed'])} failed, {len(results['skipped'])} skipped"
    )
    return results
