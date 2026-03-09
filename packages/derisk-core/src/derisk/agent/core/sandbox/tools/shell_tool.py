"""
Sandbox 工具兼容层

旧版 sandbox 工具已迁移到统一工具框架。
此文件仅为向后兼容，新代码请使用:

    from derisk.agent.tools.builtin.sandbox import ShellExecTool
"""

# 向后兼容：从统一框架导入
from derisk.agent.tools.builtin.sandbox.shell_exec import ShellExecTool

# 导出工具实例
shell_exec_tool = ShellExecTool()

__all__ = ["ShellExecTool", "shell_exec_tool"]
