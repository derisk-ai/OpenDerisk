"""
Skill 工具模块

提供专用的 Skill 操作工具：
- skill_read: 读取 Skill 的 SKILL.md 内容（不截断）
- skill_exec: 在 Skill 目录下执行脚本
- skill_list: 列出可用 Skill 及其元数据
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_skill_tools(registry: "ToolRegistry") -> None:
    """注册所有 Skill 工具"""
    from .read_skill import ReadSkillTool
    from .execute_skill import ExecuteSkillScriptTool
    from .list_skills import ListSkillsTool

    registry.register(ReadSkillTool())
    registry.register(ExecuteSkillScriptTool())
    registry.register(ListSkillsTool())
