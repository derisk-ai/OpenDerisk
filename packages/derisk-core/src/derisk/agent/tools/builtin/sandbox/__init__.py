"""
Sandbox 工具模块

提供沙箱环境下的工具：
- shell_exec: 沙箱内 Shell 命令执行
- view: 沙箱文件/目录查看
- create_file: 沙箱内创建文件
- edit_file: 沙箱内编辑文件
- download_file: 从沙箱下载文件
- deliver_file: 沙箱文件交付（标记为交付物并生成下载链接）
- browser_*: 浏览器自动化工具

这些工具需要在沙箱环境中运行，通过 ToolContext 获取 SandboxClient。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_sandbox_tools(registry: "ToolRegistry") -> None:
    """注册所有沙箱工具"""
    from .shell_exec import ShellExecTool
    from .view import ViewTool
    from .create_file import CreateFileTool
    from .edit_file import EditFileTool
    from .download_file import DownloadFileTool
    from .deliver_file import DeliverFileTool
    from .browser import register_browser_tools

    # 核心沙箱工具
    registry.register(ShellExecTool())
    registry.register(ViewTool())
    registry.register(CreateFileTool())
    registry.register(EditFileTool())
    registry.register(DownloadFileTool())
    registry.register(DeliverFileTool())

    # 浏览器工具
    register_browser_tools(registry)


__all__ = [
    "register_sandbox_tools",
    "ShellExecTool",
    "ViewTool",
    "CreateFileTool",
    "EditFileTool",
    "DownloadFileTool",
    "DeliverFileTool",
]
