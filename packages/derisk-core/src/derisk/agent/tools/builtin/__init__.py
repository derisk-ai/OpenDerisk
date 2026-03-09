"""
内置工具模块

提供核心工具：
- 文件系统工具 (read, write, edit, glob, grep, list_files, search)
- Shell工具 (bash, python)
- 网络工具 (webfetch, websearch)
- 交互工具 (question, confirm, notify, progress, ask_human, file_select)
- 推理工具 (think)
- Agent工具 (browser, sandbox, terminate, knowledge)
- Sandbox工具 (shell_exec, view, create_file, edit_file, download_file, browser_*)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..registry import ToolRegistry


def register_all(registry: "ToolRegistry") -> None:
    """注册所有内置工具"""
    from .file_system import register_file_tools
    from .shell import register_shell_tools
    from .network import register_network_tools
    from .interaction import register_interaction_tools
    from .reasoning import register_reasoning_tools
    from .agent import register_agent_tools
    from .sandbox import register_sandbox_tools

    # 文件系统工具 (已包含 read, write, edit, glob, grep, list_files, search)
    register_file_tools(registry)

    # Shell工具 (bash, python)
    register_shell_tools(registry)

    # 网络工具 (webfetch, websearch)
    register_network_tools(registry)

    # 交互工具 (question, confirm, notify, progress, ask_human, file_select)
    register_interaction_tools(registry)

    # 推理工具 (think)
    register_reasoning_tools(registry)

    # Agent工具 (browser, sandbox, terminate, knowledge)
    register_agent_tools(registry)

    # Sandbox工具 (shell_exec, view, create_file, edit_file, download_file, browser_*)
    register_sandbox_tools(registry)
