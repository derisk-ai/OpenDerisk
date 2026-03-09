"""
Edit File 工具兼容层

旧版工具已迁移到统一工具框架。
此文件仅为向后兼容，新代码请使用:

    from derisk.agent.tools.builtin.sandbox import EditFileTool
"""

from derisk.agent.tools.builtin.sandbox.edit_file import EditFileTool

edit_file_tool = EditFileTool()

__all__ = ["EditFileTool", "edit_file_tool"]
