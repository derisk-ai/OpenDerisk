"""
View 工具兼容层

旧版工具已迁移到统一工具框架。
此文件仅为向后兼容，新代码请使用:

    from derisk.agent.tools.builtin.sandbox import ViewTool
"""

from derisk.agent.tools.builtin.sandbox.view import ViewTool

view_tool = ViewTool()

__all__ = ["ViewTool", "view_tool"]
