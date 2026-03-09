"""
Create File 工具兼容层

旧版工具已迁移到统一工具框架。
此文件仅为向后兼容，新代码请使用:

    from derisk.agent.tools.builtin.sandbox import CreateFileTool
"""

from derisk.agent.tools.builtin.sandbox.create_file import CreateFileTool

create_file_tool = CreateFileTool()

__all__ = ["CreateFileTool", "create_file_tool"]
