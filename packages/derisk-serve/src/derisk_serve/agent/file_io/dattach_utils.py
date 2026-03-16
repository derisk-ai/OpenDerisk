"""D-Attach Component Utilities for OpenDeRisk

Provides convenient methods to convert file URLs to d-attach component format.
Supports outputting files during Agent execution or in conclusions, with frontend preview and download functionality.
"""

import mimetypes
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

logger = __import__("logging").getLogger(__name__)


def get_mime_type(file_name: str) -> str:
    """Get MIME type based on file name."""
    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type or "application/octet-stream"


def create_dattach_content(
    file_name: str,
    file_url: str,
    file_size: Optional[int] = None,
    mime_type: Optional[str] = None,
    file_type: str = "deliverable",
    file_id: Optional[str] = None,
    object_path: Optional[str] = None,
    preview_url: Optional[str] = None,
    download_url: Optional[str] = None,
    created_at: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a single d-attach component content.

    Args:
        file_name: File name
        file_url: File URL (OSS URL or other URL)
        file_size: File size in bytes, optional
        mime_type: MIME type, optional (will be inferred from file name if not provided)
        file_type: File type, default "deliverable"
        file_id: File ID, optional (will be auto-generated if not provided)
        object_path: OSS object path (file key), optional
        preview_url: Preview URL, optional (will use file_url if not provided)
        download_url: Download URL, optional (will use file_url if not provided)
        created_at: Created at ISO format, optional
        description: File description, optional

    Returns:
        d-attach component content dictionary

    Example:
        ```python
        from derisk_serve.agent.file_io.dattach_utils import create_dattach_content

        content = create_dattach_content(
            file_name="report.md",
            file_url="derisk-fs://bucket/path/report.md",
            object_path="bucket/path/report.md",
            file_size=1024,
            file_type="conclusion",
        )
        ```
    """
    if mime_type is None:
        mime_type = get_mime_type(file_name)

    if file_id is None:
        file_id = str(uuid4())

    if preview_url is None:
        preview_url = file_url

    if download_url is None:
        download_url = file_url

    if created_at is None:
        created_at = datetime.utcnow().isoformat()

    return {
        "file_id": file_id,
        "file_name": file_name,
        "file_type": file_type,
        "file_size": file_size or 0,
        "object_path": object_path,
        "oss_url": file_url,
        "preview_url": preview_url,
        "download_url": download_url,
        "mime_type": mime_type,
        "created_at": created_at,
        "description": description,
    }


def create_dattach_list_content(
    files: List[Dict[str, Any]],
    title: str = "Delivered Files",
    description: Optional[str] = None,
    show_batch_download: bool = True,
) -> Dict[str, Any]:
    """Create d-attach-list component content (multi-file list).

    Args:
        files: File list, each file is a dictionary containing create_dattach_content parameters
        title: File list title
        description: File list description
        show_batch_download: Whether to show batch download button

    Returns:
        d-attach-list component content dictionary

    Example:
        ```python
        from derisk_serve.agent.file_io.dattach_utils import (
            create_dattach_list_content,
        )

        content = create_dattach_list_content(
            files=[
                {"file_name": "report.md", "file_url": "derisk-fs://bucket/report.md"},
                {"file_name": "data.csv", "file_url": "derisk-fs://bucket/data.csv"},
            ],
            title="Analysis Report",
        )
        ```
    """
    file_items = []
    total_size = 0

    for file_info in files:
        if isinstance(file_info, dict):
            file_content = create_dattach_content(**file_info)
            file_items.append(file_content)
            total_size += file_content.get("file_size", 0)

    return {
        "title": title,
        "description": description,
        "files": file_items,
        "total_count": len(file_items),
        "total_size": total_size,
        "show_batch_download": show_batch_download,
    }


def render_dattach(
    file_name: str,
    file_url: str,
    file_size: Optional[int] = None,
    mime_type: Optional[str] = None,
    file_type: str = "deliverable",
    **kwargs,
) -> str:
    """Render a single d-attach component (returns markdown format string).

    This function generates a markdown string that can be directly inserted into Agent output,
    and the frontend will automatically render it as a clickable attachment component.

    Args:
        file_name: File name
        file_url: File URL
        file_size: File size in bytes
        mime_type: MIME type
        file_type: File type
        **kwargs: Other parameters passed to create_dattach_content

    Returns:
        d-attach component markdown string

    Example:
        ```python
        from derisk_serve.agent.file_io.dattach_utils import render_dattach

        # Use in Agent output
        output = f"\\n\\nAnalysis complete, generated report file:\\n{render_dattach('report.md', 'derisk-fs://bucket/report.md')}"
        ```
    """
    content = create_dattach_content(
        file_name=file_name,
        file_url=file_url,
        file_size=file_size,
        mime_type=mime_type,
        file_type=file_type,
        **kwargs,
    )

    # Generate markdown format for d-attach
    # Format: [d-attach:{"file_name": "...", ...}]
    import json

    content_json = json.dumps(content, ensure_ascii=False)
    return f"[d-attach:{content_json}]"


def render_dattach_list(
    files: List[Dict[str, Any]],
    title: str = "Delivered Files",
    description: Optional[str] = None,
    show_batch_download: bool = True,
) -> str:
    """Render d-attach-list component (returns markdown format string).

    Args:
        files: File list
        title: File list title
        description: File list description
        show_batch_download: Whether to show batch download button

    Returns:
        d-attach-list component markdown string

    Example:
        ```python
        from derisk_serve.agent.file_io.dattach_utils import render_dattach_list

        output = f"\\n\\nTask complete, generated files:\\n{
            render_dattach_list(
                [
                    {
                        'file_name': 'report.md',
                        'file_url': 'derisk-fs://bucket/report.md',
                    },
                    {
                        'file_name': 'data.csv',
                        'file_url': 'derisk-fs://bucket/data.csv',
                    },
                ]
            )
        }"
        ```
    """
    content = create_dattach_list_content(
        files=files,
        title=title,
        description=description,
        show_batch_download=show_batch_download,
    )

    # Generate markdown format for d-attach-list
    import json

    content_json = json.dumps(content, ensure_ascii=False)
    return f"[d-attach-list:{content_json}]"


# Convenience function aliases
def attach(
    file_name: str,
    file_url: str,
    file_size: Optional[int] = None,
    file_type: str = "deliverable",
    **kwargs,
) -> str:
    """attach function alias, simplifies calling.

    Example:
        ```python
        from derisk_serve.agent.file_io.dattach_utils import attach

        output = f"File: {attach('report.md', 'https://...')}"
        ```
    """
    return render_dattach(
        file_name=file_name,
        file_url=file_url,
        file_size=file_size,
        file_type=file_type,
        **kwargs,
    )


def attach_list(
    files: List[Dict[str, Any]],
    title: str = "Delivered Files",
    **kwargs,
) -> str:
    """attach_list function alias, simplifies calling.

    Example:
        ```python
        from derisk_serve.agent.file_io.dattach_utils import attach_list

        output = attach_list(
            [
                {"file_name": "report.md", "file_url": "derisk-fs://bucket/report.md"},
            ]
        )
        ```
    """
    return render_dattach_list(files=files, title=title, **kwargs)


class DAttachBuilder:
    """Builder pattern for creating d-attach content.

    Provides a fluent interface for building d-attach components.

    Example:
        ```python
        from derisk_serve.agent.file_io.dattach_utils import DAttachBuilder

        # Single file
        dattach = (
            DAttachBuilder()
            .file_name("report.md")
            .file_url("derisk-fs://bucket/report.md")
            .file_size(1024)
            .description("Analysis Report")
            .build()
        )

        # Multiple files
        dattach_list = (
            DAttachBuilder()
            .add_file("report.md", "derisk-fs://bucket/report.md", 1024)
            .add_file("data.csv", "derisk-fs://bucket/data.csv", 2048)
            .title("Deliverables")
            .build_list()
        )
        ```
    """

    def __init__(self):
        self._file_name: Optional[str] = None
        self._file_url: Optional[str] = None
        self._file_size: Optional[int] = None
        self._mime_type: Optional[str] = None
        self._file_type: str = "deliverable"
        self._file_id: Optional[str] = None
        self._object_path: Optional[str] = None
        self._preview_url: Optional[str] = None
        self._download_url: Optional[str] = None
        self._description: Optional[str] = None
        self._created_at: Optional[str] = None

        # For list building
        self._files: List[Dict[str, Any]] = []
        self._title: str = "Delivered Files"
        self._list_description: Optional[str] = None
        self._show_batch_download: bool = True

    def file_name(self, name: str) -> "DAttachBuilder":
        """Set file name."""
        self._file_name = name
        return self

    def file_url(self, url: str) -> "DAttachBuilder":
        """Set file URL."""
        self._file_url = url
        return self

    def file_size(self, size: int) -> "DAttachBuilder":
        """Set file size."""
        self._file_size = size
        return self

    def mime_type(self, mime: str) -> "DAttachBuilder":
        """Set MIME type."""
        self._mime_type = mime
        return self

    def file_type(self, ftype: str) -> "DAttachBuilder":
        """Set file type."""
        self._file_type = ftype
        return self

    def file_id(self, fid: str) -> "DAttachBuilder":
        """Set file ID."""
        self._file_id = fid
        return self

    def object_path(self, path: str) -> "DAttachBuilder":
        """Set object path."""
        self._object_path = path
        return self

    def preview_url(self, url: str) -> "DAttachBuilder":
        """Set preview URL."""
        self._preview_url = url
        return self

    def download_url(self, url: str) -> "DAttachBuilder":
        """Set download URL."""
        self._download_url = url
        return self

    def description(self, desc: str) -> "DAttachBuilder":
        """Set description."""
        self._description = desc
        return self

    def created_at(self, time: str) -> "DAttachBuilder":
        """Set created at time."""
        self._created_at = time
        return self

    def add_file(
        self,
        name: str,
        url: str,
        size: Optional[int] = None,
        description: Optional[str] = None,
    ) -> "DAttachBuilder":
        """Add a file to the list."""
        self._files.append(
            {
                "file_name": name,
                "file_url": url,
                "file_size": size,
                "description": description,
            }
        )
        return self

    def title(self, title: str) -> "DAttachBuilder":
        """Set list title."""
        self._title = title
        return self

    def list_description(self, desc: str) -> "DAttachBuilder":
        """Set list description."""
        self._list_description = desc
        return self

    def show_batch_download(self, show: bool) -> "DAttachBuilder":
        """Set whether to show batch download button."""
        self._show_batch_download = show
        return self

    def build(self) -> str:
        """Build single d-attach component."""
        if not self._file_name or not self._file_url:
            raise ValueError("file_name and file_url are required")

        return render_dattach(
            file_name=self._file_name,
            file_url=self._file_url,
            file_size=self._file_size,
            mime_type=self._mime_type,
            file_type=self._file_type,
            file_id=self._file_id,
            object_path=self._object_path,
            preview_url=self._preview_url,
            download_url=self._download_url,
            description=self._description,
            created_at=self._created_at,
        )

    def build_list(self) -> str:
        """Build d-attach-list component."""
        return render_dattach_list(
            files=self._files,
            title=self._title,
            description=self._list_description,
            show_batch_download=self._show_batch_download,
        )
