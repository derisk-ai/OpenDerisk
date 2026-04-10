"""
PromptAssembler - Prompt 分层组装器

核心功能：
1. 分层组装：身份层 + 资源层 + 控制层
2. 新旧兼容：智能检测旧模式模板，自动适配
3. 架构适配：支持 core_v1 和 core_v2 两种架构

分层结构：
┌─────────────────────────────────────────────────────────────────┐
│                         最终 System Prompt                        │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: 身份层（用户输入 system_prompt_template 作为 identity）  │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: 动态资源层（系统自动注入 sandbox/agents/knowledge/skills）│
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: 系统控制层（开发者维护的 workflow/exceptions/delivery）  │
└─────────────────────────────────────────────────────────────────┘

兼容逻辑：
- 旧模式：检测到流程控制标记 → 直接使用用户模板
- 新模式：无流程控制标记 → 分层组装

设计原则：
- 零前端改动：继续使用现有字段
- 零接口改动：API 保持不变
- 自动兼容：智能判断新旧模式
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .prompt_registry import get_registry, PromptTemplate
from .resource_injector import ResourceInjector, ResourceContext, ResourceType

if TYPE_CHECKING:
    from derisk.util.template_utils import render

logger = logging.getLogger(__name__)


class PromptMode(str, Enum):
    """Prompt 模式"""

    LEGACY = "legacy"  # 旧模式：完整模板直接使用
    LAYERED = "layered"  # 新模式：分层组装
    AUTO = "auto"  # 自动检测（默认）


@dataclass
class PromptAssemblyConfig:
    """
    Prompt 组装配置

    用于控制组装行为，支持两种架构的自定义配置。
    """

    # 架构版本
    architecture: str = "v1"  # "v1" or "v2"

    # 模式：auto（自动检测）、legacy（强制旧模式）、layered（强制新模式）
    mode: PromptMode = PromptMode.AUTO

    # 工作流版本
    workflow_version: str = "v3"

    # 语言
    language: str = "zh"

    # 用户可用变量白名单
    user_allowed_vars: List[str] = field(
        default_factory=lambda: [
            "role",
            "name",
            "goal",
            "now",
            "now_time",
            "conv_start_time",
            "user_name",
            "user_id",
            "language",
            "expand_prompt",
            "agent_name",
            "max_steps",
            "user_input",
            "context",
            "memory",  # 历史对话记录
        ]
    )

    # 旧模式检测标记
    legacy_markers: List[str] = field(
        default_factory=lambda: [
            "## 核心工作流",
            "## 工作流程",
            "## 异常处理机制",
            "## 成果交付规范",
            "Doom Loop",
            "死循环检测",
            "<available_agents>",
            "<available_knowledges>",
            "<available_skills>",
            "### 环境信息",
            "### 资源空间",
            "## 资源空间",
        ]
    )

    # 模板分隔符
    section_separator: str = "\n\n---\n\n"

    # 自定义模板目录
    custom_template_dirs: List[str] = field(default_factory=list)


class PromptAssembler:
    """
    Prompt 组装器 - 分层组装，新旧兼容

    用法：
        # 方式1：直接使用
        assembler = PromptAssembler()
        system_prompt = await assembler.assemble_system_prompt(
            user_system_prompt="你是一个专家...",
            resource_context=ResourceContext.from_v1_agent(agent),
            role="AI助手",
            name="Assistant",
        )

        # 方式2：使用配置
        config = PromptAssemblyConfig(architecture="v2", language="en")
        assembler = PromptAssembler(config)
        system_prompt = await assembler.assemble_system_prompt(...)

    兼容两种架构：
        # core_v1
        ctx = ResourceContext.from_v1_agent(agent)
        prompt = await assembler.assemble_system_prompt(
            user_system_prompt=profile.system_prompt_template,
            resource_context=ctx,
            **profile_vars
        )

        # core_v2
        ctx = ResourceContext.from_v2_agent(agent)
        prompt = await assembler.assemble_system_prompt(
            user_system_prompt=info.system_prompt,
            resource_context=ctx,
            agent_name=info.name,
        )
    """

    def __init__(
        self,
        config: Optional[PromptAssemblyConfig] = None,
    ):
        """
        初始化

        Args:
            config: 组装配置，如果为 None 则使用默认配置
        """
        self.config = config or PromptAssemblyConfig()
        self.registry = get_registry()
        self.resource_injector = ResourceInjector()

    # ==================== 核心组装方法 ====================

    async def assemble_system_prompt(
        self,
        user_system_prompt: Optional[str] = None,
        resource_context: Optional[ResourceContext] = None,
        **kwargs,
    ) -> str:
        """
        组装完整的 System Prompt

        Args:
            user_system_prompt: 用户输入的系统提示模板
                - 旧模式：完整模板，直接使用
                - 新模式：身份内容，替换 identity 模板
            resource_context: 资源上下文（用于注入资源层）
            **kwargs: 模板变量

        Returns:
            完整的 system prompt
        """
        # 确定模式
        mode = self._determine_mode(user_system_prompt)

        if mode == PromptMode.LEGACY:
            logger.info("Using legacy mode: direct template rendering")
            return await self._render_legacy_template(
                user_system_prompt, resource_context=resource_context, **kwargs
            )

        # 新模式：分层组装
        logger.info("Using layered mode: assembling layers")
        sections = []

        # Layer 1: 身份层
        identity_content = await self._assemble_identity(user_system_prompt, **kwargs)
        sections.append(identity_content)

        # Layer 2: 动态资源层
        if resource_context:
            resource_content = await self._assemble_resources(resource_context)
            if resource_content:
                sections.append(resource_content)

        # Layer 3: 系统控制层
        control_content = await self._assemble_control_flow(**kwargs)
        sections.append(control_content)

        return self.config.section_separator.join(sections)

    async def assemble_user_prompt(
        self,
        user_prompt_prefix: Optional[str] = None,
        memory_content: Optional[str] = None,
        question: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
                组装 User Prompt

        Args:
                    user_prompt_prefix: 用户输入的用户提示模板，作为前缀拼接
                    memory_content: 历史对话内容（可能已包含标题）
                    question: 用户问题
                    **kwargs: 其他变量

                Returns:
                    完整的 user prompt
        """
        sections = []

        # 将 memory_content 作为 memory 变量传入，支持用户模板使用 {% if memory %} 语法
        render_kwargs = {**kwargs, "memory": memory_content}

        # 用户自定义前缀
        if user_prompt_prefix and user_prompt_prefix.strip():
            rendered_prefix = await self._render_with_user_variables(
                user_prompt_prefix, **render_kwargs
            )
            sections.append(rendered_prefix)

        # 如果用户模板没有使用 memory 变量，且 memory_content 有实际内容，则追加历史对话
        # 注意：memory_content 可能已经包含 "## 历史对话记录" 标题，直接追加即可
        has_memory = memory_content and memory_content.strip()
        if has_memory and (
            not user_prompt_prefix
            or (
                "{{ memory }}" not in user_prompt_prefix
                and "{% if memory" not in user_prompt_prefix
            )
        ):
            sections.append(memory_content)

        # 用户问题
        if question:
            user_name = kwargs.get("user_name", "")
            user_id = kwargs.get("user_id", "")
            question_section = f"## 当前用户输入\n\n{question}"
            if user_name or user_id:
                parts = []
                if user_name:
                    parts.append(user_name)
                if user_id:
                    parts.append(user_id)
                question_section += f"\n\n> 以上需求由 {' / '.join(parts)} 提交"
            sections.append(question_section)

        return "\n\n".join(sections) if sections else ""

    # ==================== 分层组装方法 ====================

    async def _assemble_identity(self, user_identity: Optional[str], **kwargs) -> str:
        """
        组装身份层

        - 有用户输入：作为身份内容
        - 无用户输入：使用默认 identity/default 模板
        """
        if user_identity and user_identity.strip():
            # 用户输入作为身份内容，支持变量替换
            return await self._render_with_user_variables(user_identity, **kwargs)

        # 使用默认身份模板
        language = kwargs.get("language", self.config.language)
        template_name = f"default_{language}" if language != "zh" else "default"

        template = self.registry.get("identity", template_name)
        if template:
            return template.render(**kwargs)

        # 回退到内置默认
        return self._get_builtin_identity(**kwargs)

    async def _assemble_resources(self, ctx: ResourceContext) -> str:
        """组装资源层 - 动态注入"""
        return await self.resource_injector.inject_all(ctx)

    async def _assemble_control_flow(self, **kwargs) -> str:
        """
        组装系统控制层

        组装顺序：
        1. 工作流
        2. 异常处理
        3. 交付规范
        """
        sections = []
        language = kwargs.get("language", self.config.language)

        # 1. 工作流
        workflow_version = kwargs.get("workflow_version", self.config.workflow_version)
        workflow_name = (
            f"{workflow_version}_{language}" if language != "zh" else workflow_version
        )
        workflow = self.registry.get("workflow", workflow_name)
        if not workflow:
            workflow = self.registry.get("workflow", workflow_version)
        if workflow:
            sections.append(workflow.content)
        else:
            # 使用内置工作流
            sections.append(self._get_builtin_workflow(**kwargs))

        # 2. 异常处理
        exceptions_name = f"main_{language}" if language != "zh" else "main"
        exceptions = self.registry.get("exceptions", exceptions_name)
        if not exceptions:
            exceptions = self.registry.get("exceptions", "main")
        if exceptions:
            sections.append(exceptions.content)

        # 3. 交付规范
        delivery_name = f"main_{language}" if language != "zh" else "main"
        delivery = self.registry.get("delivery", delivery_name)
        if not delivery:
            delivery = self.registry.get("delivery", "main")
        if delivery:
            sections.append(delivery.content)

        return "\n\n".join(sections)

    # ==================== 模式检测与渲染 ====================

    def _determine_mode(self, user_system_prompt: Optional[str]) -> PromptMode:
        """
        确定使用哪种模式

        逻辑：
        1. 如果配置了强制模式，使用配置的模式
        2. 如果是 auto 模式，检测是否包含旧模式标记
        """
        if self.config.mode != PromptMode.AUTO:
            return self.config.mode

        # 自动检测
        if self._is_legacy_mode(user_system_prompt):
            return PromptMode.LEGACY

        return PromptMode.LAYERED

    def _is_legacy_mode(self, system_prompt_template: Optional[str]) -> bool:
        """
        判断是否是旧模式（完整模板）

        检测逻辑：
        - 包含流程控制标记 → 旧模式
        - 不包含 → 新模式
        """
        if not system_prompt_template:
            return False

        for marker in self.config.legacy_markers:
            if marker in system_prompt_template:
                logger.info(f"Detected legacy mode: found marker '{marker}'")
                return True

        return False

    async def _render_legacy_template(
        self,
        template: Optional[str],
        resource_context: Optional[ResourceContext] = None,
        **kwargs,
    ) -> str:
        """渲染旧模式模板（保持原有逻辑）

        Args:
            template: 用户提供的完整模板
            resource_context: 资源上下文，用于提取 sandbox、agents 等变量
            **kwargs: 其他变量
        """
        if not template:
            return ""

        try:
            from derisk.util.template_utils import render
        except ImportError:
            # 回退到简单替换
            return await self._render_with_user_variables(template, **kwargs)

        # 构建变量上下文，包含资源变量
        context = self._build_render_context(
            resource_context=resource_context, **kwargs
        )

        return render(template, context)

    async def _render_with_user_variables(self, content: str, **kwargs) -> str:
        """渲染用户内容，支持完整 Jinja2 语法

        支持：
        - {{ variable }} 变量替换
        - {% if variable %} 条件判断
        - {% for item in list %} 循环
        - 其他 Jinja2 语法
        """
        if not kwargs:
            return content

        try:
            from derisk.util.template_utils import render

            return render(content, kwargs)
        except Exception as e:
            logger.warning(f"Jinja2 渲染失败，回退到简单替换: {e}")
            result = content
            for key, value in kwargs.items():
                if value is None:
                    continue
                result = result.replace(f"{{{{{key}}}}}", str(value))
            return result

    def _build_render_context(
        self, resource_context: Optional[ResourceContext] = None, **kwargs
    ) -> Dict[str, Any]:
        """构建渲染上下文，包含资源变量

        Args:
            resource_context: 资源上下文，用于提取 sandbox、agents 等变量
            **kwargs: 其他变量
        """
        now_time = kwargs.get("now_time") or datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        now = kwargs.get("now") or datetime.now().strftime("%Y-%m-%d")

        context = {
            "role": kwargs.get("role", ""),
            "name": kwargs.get("name", ""),
            "goal": kwargs.get("goal", ""),
            "now": now,
            "now_time": now_time,
            "conv_start_time": kwargs.get("conv_start_time", ""),
            "user_name": kwargs.get("user_name", ""),
            "user_id": kwargs.get("user_id", ""),
            "language": kwargs.get("language", self.config.language),
            "expand_prompt": kwargs.get("expand_prompt", ""),
            "agent_name": kwargs.get("agent_name", kwargs.get("name", "")),
            "max_steps": kwargs.get("max_steps", 20),
        }

        # 从 resource_context 提取资源变量
        if resource_context:
            # 提取沙箱信息
            sandbox_info = self._extract_sandbox_info(resource_context)
            context["sandbox"] = sandbox_info

            # 提取 Agent 列表
            agents_info = self._extract_agents_info(resource_context)
            context["available_agents"] = agents_info

            # 提取知识库列表
            knowledge_info = self._extract_knowledge_info(resource_context)
            context["available_knowledges"] = knowledge_info

            # 提取技能列表
            skills_info = self._extract_skills_info(resource_context)
            context["available_skills"] = skills_info

            # 提取数据库列表
            database_info = self._extract_database_info(resource_context)
            context["available_databases"] = database_info

        # 合并其他变量（允许覆盖）
        context.update(kwargs)

        return context

    def _extract_sandbox_info(self, ctx: ResourceContext) -> Dict[str, Any]:
        """从 ResourceContext 提取沙箱信息"""
        resources = ctx.get_resources(ResourceType.SANDBOX)
        if not resources:
            return {"enable": False, "prompt": ""}

        resource = resources[0]
        return {
            "enable": True,
            "prompt": resource.metadata.get("prompt", ""),
            "work_dir": resource.metadata.get("work_dir", "/workspace"),
        }

    def _extract_agents_info(self, ctx: ResourceContext) -> str:
        """从 ResourceContext 提取 Agent 信息（XML 格式字符串）"""
        resources = ctx.get_resources(ResourceType.AGENTS)
        if not resources:
            return ""

        lines = []
        for r in resources:
            lines.append(f"""- <agent>
  <code>{r.code}</code>
  <name>{r.name}</name>
  <description>{r.description}</description>
</agent>""")

        return "\n".join(lines)

    def _extract_knowledge_info(self, ctx: ResourceContext) -> str:
        """从 ResourceContext 提取知识库信息（XML 格式字符串）"""
        resources = ctx.get_resources(ResourceType.KNOWLEDGE)
        if not resources:
            return ""

        lines = []
        for r in resources:
            lines.append(f"""- <knowledge>
  <id>{r.code}</id>
  <name>{r.name}</name>
  <description>{r.description}</description>
</knowledge>""")

        return "\n".join(lines)

    def _extract_skills_info(self, ctx: ResourceContext) -> str:
        """从 ResourceContext 提取技能信息（XML 格式字符串）"""
        resources = ctx.get_resources(ResourceType.SKILLS)
        if not resources:
            return ""

        lines = []
        for r in resources:
            path = r.metadata.get("path", "")
            branch = r.metadata.get("branch", "master")
            lines.append(f"""- <skill>
  <name>{r.name}</name>
  <description>{r.description}</description>
  <path>{path}</path>
  <branch>{branch}</branch>
</skill>""")

        return "\n".join(lines)

    def _extract_database_info(self, ctx: ResourceContext) -> str:
        """从 ResourceContext 提取数据库信息（XML 格式字符串）"""
        resources = ctx.get_resources(ResourceType.DATABASE)
        if not resources:
            return ""

        lines = []
        for r in resources:
            db_name = r.metadata.get("db_name", r.code)
            db_type = r.metadata.get("db_type", "")
            dialect = r.metadata.get("dialect", db_type)
            db_block = f"""- <database>
  <name>{r.name}</name>
  <db_name>{db_name}</db_name>
  <db_type>{db_type}</db_type>
  <dialect>{dialect}</dialect>
  <description>{r.description}</description>
</database>"""
            lines.append(db_block)

        return "\n".join(lines)

    # ==================== 内置默认模板 ====================

    def _get_builtin_identity(self, **kwargs) -> str:
        """获取内置身份模板（当没有文件模板时使用）"""
        role = kwargs.get("role", "AI 助手")
        name = kwargs.get("name", "")
        goal = kwargs.get("goal", "帮助用户解决问题")

        name_part = f"，名字叫 {name}" if name else ""

        return f"""# 角色定位

你是一个{role}{name_part}。

## 核心使命

{goal}

## 领域专注

通用问题解决、数据分析、代码开发、文档处理等领域。

## 工作风格

- 系统化思考：分解复杂问题，制定清晰计划
- 结果导向：关注实际交付成果
- 持续优化：根据反馈不断改进方案"""

    def _get_builtin_workflow(self, **kwargs) -> str:
        """获取内置工作流模板"""
        language = kwargs.get("language", self.config.language)

        if language == "en":
            return """## Core Workflow

You complete tasks through the following iterative loop:

1. **Analysis**
   - Understand user requirements and current context
   - Evaluate task complexity and required resources
   - Formulate a clear execution plan

2. **Tool Execution**
   - Select appropriate tools based on analysis
   - Execute tool calls and process results
   - Handle errors and retry if necessary

3. **Iteration**
   - Evaluate current execution results
   - Decide if further iteration is needed
   - Adjust strategy to optimize results

4. **Delivery**
   - When task is complete or termination condition is reached
   - Output final results according to delivery specifications"""

        return """## 核心工作流

你通过以下迭代循环完成任务：

1. **任务分析**
   - 深入理解用户需求和当前上下文
   - 评估任务复杂度和所需资源
   - 制定清晰的执行计划

2. **工具调用**
   - 根据分析结果选择合适的工具
   - 执行工具调用并处理返回结果
   - 必要时进行错误处理和重试

3. **迭代优化**
   - 评估当前执行结果
   - 决定是否需要继续迭代
   - 调整策略以优化结果

4. **结果交付**
   - 当任务完成或达到终止条件时
   - 按照交付规范输出最终结果"""


def create_prompt_assembler(
    architecture: str = "v1",
    mode: PromptMode = PromptMode.AUTO,
    workflow_version: str = "v3",
    language: str = "zh",
    **kwargs,
) -> PromptAssembler:
    """
    创建 Prompt 组装器的便捷函数

    Args:
        architecture: 架构版本 "v1" 或 "v2"
        mode: 模式 AUTO/LEGACY/LAYERED
        workflow_version: 工作流版本
        language: 语言
        **kwargs: 其他配置

    Returns:
        PromptAssembler 实例
    """
    config = PromptAssemblyConfig(
        architecture=architecture,
        mode=mode,
        workflow_version=workflow_version,
        language=language,
        **kwargs,
    )
    return PromptAssembler(config)
