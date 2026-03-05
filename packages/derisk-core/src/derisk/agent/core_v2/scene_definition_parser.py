"""
SceneDefinitionParser - MD 格式场景定义解析器

解析 Markdown 格式的 Agent 角色定义和场景定义文件
将 MD 内容映射到结构化的数据模型

设计原则:
- 渐进式解析：支持解析部分内容，忽略无法识别的部分
- 可扩展：易于添加新的 MD 格式规范
- 容错性：遇到格式错误时提供有意义的错误信息
"""

from typing import Optional, Dict, Any, List, Tuple
import re
import logging
from pathlib import Path
from datetime import datetime

from .scene_definition import (
    AgentRoleDefinition,
    SceneDefinition,
    SceneTriggerType,
    WorkflowPhase,
    ToolRule,
    SceneHookConfig,
)
from .task_scene import (
    ContextPolicy,
    PromptPolicy,
    ToolPolicy,
    TruncationStrategy,
    DedupStrategy,
    ValidationLevel,
    OutputFormat,
    ResponseStyle,
)
from .memory_compaction import CompactionStrategy
from .reasoning_strategy import StrategyType

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """解析错误"""

    pass


class SceneDefinitionParser:
    """
    场景定义解析器

    解析 MD 格式的场景定义文件，支持：
    1. Agent 角色定义 (agent-role.md)
    2. 场景定义 (scene-*.md)
    """

    def __init__(self):
        # MD 章节标题模式
        self._section_patterns = {
            "basic_info": r"^#\s+(Agent|Scene)[:：]\s*(.+)$",
            "h2": r"^##\s+(.+)$",
            "h3": r"^###\s+(.+)$",
            "list_item": r"^\s*[-*]\s+(.+)$",
            "numbered_item": r"^\s*\d+\.\s+(.+)$",
            "key_value": r"^[-*]\s+(.+?)[:：]\s*(.+)$",
            "code_block": r"^```(\w*)\s*$",
        }

    async def parse_agent_role(self, md_path: str) -> AgentRoleDefinition:
        """
        解析 Agent 基础角色定义 MD

        Args:
            md_path: MD 文件路径

        Returns:
            AgentRoleDefinition 实例
        """
        # 读取 MD 文件
        content = await self._read_md_file(md_path)

        # 解析结构
        sections = self._parse_sections(content)

        # 提取基本信息
        basic_info = self._extract_basic_info(sections)

        # 构建角色定义
        role_def = AgentRoleDefinition(
            name=basic_info.get("name", "Unnamed Agent"),
            version=basic_info.get("version", "1.0.0"),
            description=basic_info.get("description", ""),
            author=basic_info.get("author"),
            md_file_path=md_path,
        )

        # 解析各个章节
        for section_title, section_content in sections.items():
            self._parse_agent_role_section(role_def, section_title, section_content)

        # 记录解析日志
        logger.info(
            f"[SceneDefinitionParser] Parsed agent role: {role_def.name}, "
            f"scenes={len(role_def.available_scenes)}, "
            f"tools={len(role_def.global_tools)}"
        )

        return role_def

    async def parse_scene_definition(self, md_path: str) -> SceneDefinition:
        """
        解析场景定义 MD

        Args:
            md_path: MD 文件路径

        Returns:
            SceneDefinition 实例
        """
        # 读取 MD 文件
        content = await self._read_md_file(md_path)

        # 解析结构
        sections = self._parse_sections(content)

        # 提取基本信息
        basic_info = self._extract_basic_info(sections)

        # 从文件名提取场景 ID（如果没有在 MD 中指定）
        scene_id = basic_info.get("scene_id") or self._extract_scene_id_from_path(
            md_path
        )

        # 构建场景定义
        scene_def = SceneDefinition(
            scene_id=scene_id,
            scene_name=basic_info.get("name", "Unnamed Scene"),
            description=basic_info.get("description", ""),
            version=basic_info.get("version", "1.0.0"),
            author=basic_info.get("author"),
            md_file_path=md_path,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # 解析各个章节
        for section_title, section_content in sections.items():
            self._parse_scene_definition_section(
                scene_def, section_title, section_content
            )

        # 记录解析日志
        logger.info(
            f"[SceneDefinitionParser] Parsed scene: {scene_def.scene_name} ({scene_def.scene_id}), "
            f"triggers={len(scene_def.trigger_keywords)}, "
            f"tools={len(scene_def.scene_tools)}"
        )

        return scene_def

    async def _read_md_file(self, md_path: str) -> str:
        """读取 MD 文件内容"""
        try:
            path = Path(md_path)
            if not path.exists():
                raise ParseError(f"MD file not found: {md_path}")

            content = path.read_text(encoding="utf-8")
            return content
        except Exception as e:
            logger.error(f"[SceneDefinitionParser] Failed to read MD file: {e}")
            raise ParseError(f"Failed to read MD file: {md_path}, error: {e}")

    def _parse_sections(self, content: str) -> Dict[str, str]:
        """
        解析 MD 文件的章节结构

        Returns:
            Dict[section_title, section_content]
        """
        sections = {}
        lines = content.split("\n")

        current_section = None
        current_content = []

        for line in lines:
            # 检查是否是章标题（## 或 ###）
            h2_match = re.match(self._section_patterns["h2"], line)
            h3_match = re.match(self._section_patterns["h3"], line)

            if h2_match:
                # 保存上一个章节
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()

                current_section = h2_match.group(1).strip()
                current_content = []
            elif h3_match:
                # 三级标题作为子章节，暂时忽略
                current_content.append(line)
            else:
                if current_section:
                    current_content.append(line)

        # 保存最后一个章节
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    def _extract_basic_info(self, sections: Dict[str, str]) -> Dict[str, Any]:
        """提取基本信息"""
        info = {}

        # 在所有章节中查找基本信息
        for section_content in sections.values():
            lines = section_content.split("\n")
            for line in lines:
                kv_match = re.match(self._section_patterns["key_value"], line)
                if kv_match:
                    key = kv_match.group(1).strip().lower()
                    value = kv_match.group(2).strip()

                    # 映射常见字段
                    if key in ["name", "名称"]:
                        info["name"] = value
                    elif key in ["version", "版本"]:
                        info["version"] = value
                    elif key in ["description", "描述"]:
                        info["description"] = value
                    elif key in ["author", "作者"]:
                        info["author"] = value
                    elif key in ["scene_id", "场景id"]:
                        info["scene_id"] = value

        return info

    def _parse_agent_role_section(
        self,
        role_def: AgentRoleDefinition,
        section_title: str,
        section_content: str,
    ) -> None:
        """解析 Agent 角色定义的章节"""
        section_title_lower = section_title.lower()

        if "核心能力" in section_title or "core capabilities" in section_title_lower:
            role_def.core_capabilities = self._parse_list_items(section_content)

        elif "工作原则" in section_title or "working principles" in section_title_lower:
            role_def.working_principles = self._parse_list_items(section_content)

        elif "领域知识" in section_title or "domain knowledge" in section_title_lower:
            role_def.domain_knowledge = self._parse_list_items(section_content)

        elif "专业领域" in section_title or "expertise areas" in section_title_lower:
            role_def.expertise_areas = self._parse_list_items(section_content)

        elif "可用场景" in section_title or "available scenes" in section_title_lower:
            role_def.available_scenes = self._parse_list_items(section_content)

        elif "全局工具" in section_title or "global tools" in section_title_lower:
            role_def.global_tools = self._parse_list_items(section_content)

        elif "全局约束" in section_title or "global constraints" in section_title_lower:
            role_def.global_constraints = self._parse_list_items(section_content)

        elif "禁止操作" in section_title or "forbidden actions" in section_title_lower:
            role_def.forbidden_actions = self._parse_list_items(section_content)

        elif "角色设定" in section_title or "role definition" in section_title_lower:
            role_def.role_definition = section_content.strip()

    def _parse_scene_definition_section(
        self,
        scene_def: SceneDefinition,
        section_title: str,
        section_content: str,
    ) -> None:
        """解析场景定义的章节"""
        section_title_lower = section_title.lower()

        if "触发条件" in section_title or "trigger" in section_title_lower:
            self._parse_trigger_section(scene_def, section_content)

        elif "场景角色" in section_title or "scene role" in section_title_lower:
            scene_def.scene_role_prompt = section_content.strip()

        elif "专业知识" in section_title or "scene knowledge" in section_title_lower:
            scene_def.scene_knowledge = self._parse_list_items(section_content)

        elif "工作流程" in section_title or "workflow" in section_title_lower:
            scene_def.workflow_phases = self._parse_workflow_phases(section_content)

        elif "工具配置" in section_title or "tools" in section_title_lower:
            self._parse_tools_section(scene_def, section_content)

        elif "输出格式" in section_title or "output format" in section_title_lower:
            self._parse_output_format_section(scene_def, section_content)

        elif "场景钩子" in section_title or "hooks" in section_title_lower:
            scene_def.hooks = self._parse_hooks_section(section_content)

        elif "上下文策略" in section_title or "context policy" in section_title_lower:
            scene_def.context_policy = self._parse_context_policy(section_content)

        elif "提示词策略" in section_title or "prompt policy" in section_title_lower:
            scene_def.prompt_policy = self._parse_prompt_policy(section_content)

    def _parse_list_items(self, content: str) -> List[str]:
        """解析列表项"""
        items = []
        lines = content.split("\n")

        for line in lines:
            # 匹配列表项（- 或 *）
            list_match = re.match(self._section_patterns["list_item"], line)
            if list_match:
                items.append(list_match.group(1).strip())

        return items

    def _parse_trigger_section(self, scene_def: SceneDefinition, content: str) -> None:
        """解析触发条件章节"""
        lines = content.split("\n")

        for line in lines:
            kv_match = re.match(self._section_patterns["key_value"], line)
            if kv_match:
                key = kv_match.group(1).strip().lower()
                value = kv_match.group(2).strip()

                if "关键词" in key or "keyword" in key:
                    # 解析关键词列表（逗号分隔）
                    keywords = [k.strip() for k in value.split(",")]
                    scene_def.trigger_keywords = keywords

                elif "优先级" in key or "priority" in key:
                    try:
                        scene_def.trigger_priority = int(value)
                    except ValueError:
                        logger.warning(f"Invalid priority value: {value}")

                elif "类型" in key or "type" in key:
                    try:
                        scene_def.trigger_type = SceneTriggerType(value.lower())
                    except ValueError:
                        logger.warning(f"Invalid trigger type: {value}")

    def _parse_workflow_phases(self, content: str) -> List[WorkflowPhase]:
        """解析工作流程章节"""
        phases = []
        lines = content.split("\n")

        current_phase = None

        for line in lines:
            # 检查阶段标题（### 或 阶段N:）
            phase_match = re.match(r"^###\s+阶段\s*(\d+)[:：]?\s*(.*)$", line)
            if not phase_match:
                phase_match = re.match(r"^阶段\s*(\d+)[:：]\s*(.+)$", line)

            if phase_match:
                # 保存上一个阶段
                if current_phase:
                    phases.append(current_phase)

                phase_num = phase_match.group(1)
                phase_name = phase_match.group(2).strip()

                current_phase = WorkflowPhase(
                    name=f"Phase {phase_num}",
                    description=phase_name,
                    steps=[],
                )

            elif current_phase:
                # 解析步骤
                num_match = re.match(self._section_patterns["numbered_item"], line)
                if num_match:
                    current_phase.steps.append(num_match.group(1).strip())

        # 保存最后一个阶段
        if current_phase:
            phases.append(current_phase)

        return phases

    def _parse_tools_section(self, scene_def: SceneDefinition, content: str) -> None:
        """解析工具配置章节"""
        lines = content.split("\n")

        for line in lines:
            kv_match = re.match(self._section_patterns["key_value"], line)
            if kv_match:
                key = kv_match.group(1).strip().lower()
                value = kv_match.group(2).strip()

                if "场景工具" in key or "scene tools" in key:
                    # 解析工具列表
                    tools = [t.strip() for t in value.split(",")]
                    scene_def.scene_tools.extend(tools)

                elif "工具规则" in key or "tool rules" in key:
                    # 简单的工具规则解析
                    rule = ToolRule(
                        tool_name=value.split()[0] if value else "",
                        rule_type="custom",
                        description=value,
                    )
                    scene_def.tool_rules.append(rule)

    def _parse_output_format_section(
        self, scene_def: SceneDefinition, content: str
    ) -> None:
        """解析输出格式章节"""
        lines = content.split("\n")

        output_sections = []

        for line in lines:
            num_match = re.match(self._section_patterns["numbered_item"], line)
            if num_match:
                output_sections.append(num_match.group(1).strip())

        if output_sections:
            scene_def.output_sections = output_sections
            scene_def.output_format_spec = content.strip()

    def _parse_hooks_section(self, content: str) -> SceneHookConfig:
        """解析钩子配置章节"""
        hooks = SceneHookConfig()
        lines = content.split("\n")

        for line in lines:
            kv_match = re.match(self._section_patterns["key_value"], line)
            if kv_match:
                key = kv_match.group(1).strip().lower()
                value = kv_match.group(2).strip()

                if "on_enter" in key or "进入" in key:
                    hooks.on_enter = value
                elif "on_exit" in key or "退出" in key:
                    hooks.on_exit = value
                elif "before_think" in key or "思考前" in key:
                    hooks.before_think = value
                elif "after_think" in key or "思考后" in key:
                    hooks.after_think = value
                elif "before_act" in key or "行动前" in key:
                    hooks.before_act = value
                elif "after_act" in key or "行动后" in key:
                    hooks.after_act = value
                elif "before_tool" in key or "工具前" in key:
                    hooks.before_tool = value
                elif "after_tool" in key or "工具后" in key:
                    hooks.after_tool = value
                elif "on_error" in key or "错误" in key:
                    hooks.on_error = value
                elif "on_complete" in key or "完成" in key:
                    hooks.on_complete = value

        return hooks

    def _parse_context_policy(self, content: str) -> ContextPolicy:
        """解析上下文策略配置"""
        policy = ContextPolicy()
        lines = content.split("\n")

        for line in lines:
            kv_match = re.match(self._section_patterns["key_value"], line)
            if kv_match:
                key = kv_match.group(1).strip().lower()
                value = kv_match.group(2).strip()

                try:
                    if "truncation_strategy" in key or "截断策略" in key:
                        policy.truncation.strategy = TruncationStrategy(value.lower())
                    elif "compaction_strategy" in key or "压缩策略" in key:
                        policy.compaction.strategy = CompactionStrategy(value.lower())
                    elif "dedup_strategy" in key or "去重策略" in key:
                        policy.dedup.strategy = DedupStrategy(value.lower())
                except ValueError as e:
                    logger.warning(
                        f"Invalid policy value for {key}: {value}, error: {e}"
                    )

        return policy

    def _parse_prompt_policy(self, content: str) -> PromptPolicy:
        """解析提示词策略配置"""
        policy = PromptPolicy()
        lines = content.split("\n")

        for line in lines:
            kv_match = re.match(self._section_patterns["key_value"], line)
            if kv_match:
                key = kv_match.group(1).strip().lower()
                value = kv_match.group(2).strip()

                try:
                    if "output_format" in key or "输出格式" in key:
                        policy.output_format = OutputFormat(value.lower())
                    elif "response_style" in key or "响应风格" in key:
                        policy.response_style = ResponseStyle(value.lower())
                    elif "temperature" in key:
                        policy.temperature = float(value)
                    elif "max_tokens" in key:
                        policy.max_tokens = int(value)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Invalid policy value for {key}: {value}, error: {e}"
                    )

        return policy

    def _extract_scene_id_from_path(self, md_path: str) -> str:
        """从文件路径提取场景 ID"""
        path = Path(md_path)
        filename = path.stem  # 不带扩展名的文件名

        # 如果文件名是 scene-xxx.md，提取 xxx
        if filename.startswith("scene-"):
            return filename[6:]  # 去掉 "scene-" 前缀

        # 否则直接使用文件名
        return filename


# ==================== 导出 ====================

__all__ = [
    "SceneDefinitionParser",
    "ParseError",
]
