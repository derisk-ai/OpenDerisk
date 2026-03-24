"""
Sandbox 工具模块

沙箱专属工具（无本地对应，仅沙箱环境可用）：
- download_file: 从沙箱下载文件
- deliver_file: 沙箱文件交付（标记为交付物并生成下载链接）

注意：shell_exec, view, create_file, edit_file 已统一到 bash, read, write, edit。
统一工具会自动检测沙箱环境并委托给对应的沙箱实现。
浏览器工具 (browser_*) 暂不注册，后续按需启用。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_sandbox_tools(registry: "ToolRegistry") -> None:
    """注册沙箱专属工具"""
    from .download_file import DownloadFileTool
    from .deliver_file import DeliverFileTool

    # 沙箱专属工具（无本地对应）
    registry.register(DownloadFileTool())
    registry.register(DeliverFileTool())


__all__ = [
    "register_sandbox_tools",
    "DownloadFileTool",
    "DeliverFileTool",
]
