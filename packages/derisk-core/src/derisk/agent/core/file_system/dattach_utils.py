"""D-Attach 组件工具函数.

提供便捷的方法将文件 URL 转换为 d-attach 组件格式。
支持在 Agent 运行过程或结论中输出文件，并在前端展示预览和下载功能。
"""

import json
import mimetypes
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from derisk.vis import Vis


def get_mime_type(file_name: str) -> str:
    """根据文件名获取 MIME 类型."""
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
    """创建单个 d-attach 组件内容.

    Args:
        file_name: 文件名
        file_url: 文件 URL（OSS URL 或其他 URL）
        file_size: 文件大小（字节），可选
        mime_type: MIME 类型，可选（如果不提供会根据文件名自动推断）
        file_type: 文件类型，默认 "deliverable"
        file_id: 文件 ID，可选（如果不提供会自动生成）
        object_path: OSS 对象路径（文件 key），可选
        preview_url: 预览 URL，可选（如果不提供则使用 file_url）
        download_url: 下载 URL，可选（如果不提供则使用 file_url）
        created_at: 创建时间 ISO 格式，可选
        description: 文件描述，可选

    Returns:
        d-attach 组件内容字典

    Example:
        ```python
        from derisk.agent.core.file_system.dattach_utils import create_dattach_content

        content = create_dattach_content(
            file_name="report.md",
            file_url="oss://bucket/path/report.md",
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
    title: str = "交付文件",
    description: Optional[str] = None,
    show_batch_download: bool = True,
) -> Dict[str, Any]:
    """创建 d-attach-list 组件内容（多文件列表）.

    Args:
        files: 文件列表，每个文件是一个字典，包含 create_dattach_content 的参数
        title: 文件列表标题
        description: 文件列表描述
        show_batch_download: 是否显示批量下载按钮

    Returns:
        d-attach-list 组件内容字典

    Example:
        ```python
        from derisk.agent.core.file_system.dattach_utils import (
            create_dattach_list_content,
        )

        content = create_dattach_list_content(
            files=[
                {"file_name": "report.md", "file_url": "oss://bucket/report.md"},
                {"file_name": "data.csv", "file_url": "oss://bucket/data.csv"},
            ],
            title="分析报告",
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
    """渲染单个 d-attach 组件（返回 markdown 格式字符串）.

    这个函数会生成可以直接插入到 Agent 输出中的 markdown 字符串，
    前端会自动将其渲染为可点击的附件组件。

    Args:
        file_name: 文件名
        file_url: 文件 URL
        file_size: 文件大小（字节）
        mime_type: MIME 类型
        file_type: 文件类型
        **kwargs: 其他传递给 create_dattach_content 的参数

    Returns:
        d-attach 组件的 markdown 字符串

    Example:
        ```python
        from derisk.agent.core.file_system.dattach_utils import render_dattach

        # 在 Agent 输出中使用
        output = f"\\n\\n分析完成，生成的报告文件：\\n{render_dattach('report.md', 'oss://bucket/report.md')}"
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

    vis_attach = Vis.of("d-attach")
    if vis_attach is None:
        content_json = json.dumps(content, ensure_ascii=False)
        return f"[d-attach:{content_json}]"
    result = vis_attach.sync_display(content=content)
    if result is None:
        return f"[d-attach:{json.dumps(content, ensure_ascii=False)}]"
    return result


def render_dattach_list(
    files: List[Dict[str, Any]],
    title: str = "交付文件",
    description: Optional[str] = None,
    show_batch_download: bool = True,
) -> str:
    """渲染 d-attach-list 组件（返回 markdown 格式字符串）.

    Args:
        files: 文件列表
        title: 文件列表标题
        description: 文件列表描述
        show_batch_download: 是否显示批量下载按钮

    Returns:
        d-attach-list 组件的 markdown 字符串

    Example:
        ```python
        from derisk.agent.core.file_system.dattach_utils import render_dattach_list

        output = f"\\n\\n任务完成，生成的文件：\\n{
            render_dattach_list(
                [
                    {'file_name': 'report.md', 'file_url': 'oss://bucket/report.md'},
                    {'file_name': 'data.csv', 'file_url': 'oss://bucket/data.csv'},
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

    vis_attach_list = Vis.of("d-attach-list")
    if vis_attach_list is None:
        content_json = json.dumps(content, ensure_ascii=False)
        return f"[d-attach-list:{content_json}]"
    return (
        vis_attach_list.sync_display(content=content)
        or f"[d-attach-list:{json.dumps(content, ensure_ascii=False)}]"
    )


# 便捷函数别名
def attach(
    file_name: str,
    file_url: str,
    file_size: Optional[int] = None,
    file_type: str = "deliverable",
    **kwargs,
) -> str:
    """attach 函数别名，简化调用.

    Example:
        ```python
        from derisk.agent.core.file_system.dattach_utils import attach

        output = f"文件：{attach('report.md', 'https://...')}"
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
    title: str = "交付文件",
    **kwargs,
) -> str:
    """attach_list 函数别名，简化调用.

    Example:
        ```python
        from derisk.agent.core.file_system.dattach_utils import attach_list

        output = attach_list(
            [
                {"file_name": "report.md", "file_url": "oss://bucket/report.md"},
            ]
        )
        ```
    """
    return render_dattach_list(files=files, title=title, **kwargs)
