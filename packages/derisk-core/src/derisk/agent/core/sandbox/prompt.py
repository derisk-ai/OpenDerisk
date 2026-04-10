SANDBOX_ENV_PROMPT = """<execution_environment>
- 系统环境：{{sandbox.system_info}}
- 工作目录：{{sandbox.work_dir}}（用于所有临时工作）
- 技能目录：{{sandbox.skill_dir}}（用于存储和读取 Skill 知识包）
- Python 环境：版本：3.12.0，命令：python3, pip3（不支持 python, pip）
- Node.js 环境：版本：18.19.1，命令：node, pnpm（预装 pnpm, yarn）
- 沙箱启动即可用，无需检查。建议使用 sudo 执行需要权限的操作。
</execution_environment>"""

SANDBOX_TOOL_BOUNDARIES = """<tool_boundaries>
以下场景不应使用计算机工具，应直接基于训练知识回答：
- 回答事实性知识问题（技术概念、原理解释、最佳实践等）
- 总结对话中已提供的内容
- 提供通用技术建议和方案讨论
</tool_boundaries>"""

AGENT_SKILL_SYSTEM_PROMPT = """<agent_skill_system>
**Skill** 是经过提炼的专业指令和工作流程知识包，存储在 `{{sandbox.agent_skill_dir}}`。

**使用方法：**
1. 用 `skill_read` 工具加载技能的 SKILL.md 指令
2. 内化指令并立即应用于当前任务

**关键原则：**
- 严格单线程：禁止并发加载多个 Skill
- 按需延迟加载：只加载解决当前步骤所需的最简知识库

**脚本执行：** 使用 `skill_exec` 工具执行技能目录中的脚本。
</agent_skill_system>"""

sandbox_prompt = """\
<computer_use>
{{sandbox.tool_boundaries}}

{{sandbox.execution_env}}
{% if sandbox.use_agent_skill %}

{{sandbox.agent_skill_system}}
{% endif %}
</computer_use>
"""
