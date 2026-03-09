"""
Download File 工具兼容层

旧版工具已迁移到统一工具框架。
此文件仅为向后兼容，新代码请使用:

    from derisk.agent.tools.builtin.sandbox import DownloadFileTool
"""

from derisk.agent.tools.builtin.sandbox.download_file import DownloadFileTool

download_file_tool = DownloadFileTool()

__all__ = ["DownloadFileTool", "download_file_tool"]
