"""
内置工具模块

统一工具（自动检测沙箱/本地环境）：
- read: 文件读取（沙箱时支持目录列表/图片预览/交付标记）
- write: 文件写入（沙箱时支持OSS上传/交付标记）
- edit: 文件编辑（沙箱时支持追加模式/OSS上传）
- bash: Shell执行（沙箱时在沙箱中执行）
- glob, grep, list_files: 文件搜索工具

其他工具：
- 网络工具 (webfetch, websearch)
- 交互工具 (ask_user)
- Agent工具 (knowledge_search)
- 沙箱专属工具 (download_file, deliver_file)
- 异步任务工具 (spawn_agent_task, check_tasks, wait_tasks, cancel_task)
- 媒体生成工具 (generate_image, generate_video)
- 调度工具 (create_cron_job)
- Todo工具 (todowrite, todoread)
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

    # 统一文件系统工具 (read, write, edit, glob, grep, list_files)
    register_file_tools(registry)

    # 统一Shell工具 (bash)
    register_shell_tools(registry)

    # 网络工具 (webfetch, websearch)
    register_network_tools(registry)

    # 交互工具 (ask_user)
    register_interaction_tools(registry)

    # 推理工具（已清空）
    register_reasoning_tools(registry)

    # Agent工具 (knowledge_search)
    register_agent_tools(registry)

    # 沙箱专属工具 (download_file, deliver_file)
    register_sandbox_tools(registry)

    # 异步任务工具 (spawn_agent_task, check_tasks, wait_tasks, cancel_task)
    from .async_task import register_async_task_tools

    register_async_task_tools(registry)

    # 媒体生成工具 (generate_image, generate_video)
    from .media_gen import register_media_gen_tools

    register_media_gen_tools(registry)

    # 调度工具 (create_cron_job)
    from .schedule import register_schedule_tools

    register_schedule_tools(registry)

    # Todo工具 (todowrite, todoread)
    from .todo import register_todo_tools

    register_todo_tools(registry)

    # Skill工具 (skill_read, skill_exec, skill_list)
    from .skill import register_skill_tools

    register_skill_tools(registry)
