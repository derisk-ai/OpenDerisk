"""
Skill - 技能系统

可扩展的技能模块，支持技能注册、发现和执行
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


class SkillMetadata(BaseModel):
    """技能元数据"""

    name: str  # 技能名称
    version: str = "1.0.0"  # 版本号
    description: str  # 描述
    author: str = "Unknown"  # 作者
    tags: List[str] = Field(default_factory=list)  # 标签
    requires: List[str] = Field(default_factory=list)  # 依赖的工具
    enabled: bool = True  # 是否启用


class SkillContext(BaseModel):
    """技能执行上下文"""

    session_id: str  # Session ID
    agent_name: str  # Agent名称
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SkillResult(BaseModel):
    """技能执行结果"""

    success: bool  # 是否成功
    data: Any  # 结果数据
    message: Optional[str] = None  # 消息
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SkillBase(ABC):
    """
    技能基类 - 参考OpenClaw Skills设计

    设计原则:
    1. 模块化 - 每个技能独立封装
    2. 可组合 - 技能可以组合使用
    3. 可发现 - 支持技能注册和发现

    示例:
        class CodeReviewSkill(SkillBase):
            def _define_metadata(self):
                return SkillMetadata(
                    name="code_review",
                    description="代码审查技能"
                )

            async def execute(self, code: str):
                # 执行代码审查
                return SkillResult(success=True, data={...})
    """

    def __init__(self):
        self.metadata = self._define_metadata()

    @abstractmethod
    def _define_metadata(self) -> SkillMetadata:
        """定义技能元数据"""
        pass

    @abstractmethod
    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        """执行技能"""
        pass

    def get_required_tools(self) -> List[str]:
        """获取需要的工具"""
        return self.metadata.requires

    def is_enabled(self) -> bool:
        """是否启用"""
        return self.metadata.enabled


class SkillRegistry:
    """
    技能注册表

    示例:
        registry = SkillRegistry()

        # 注册技能
        registry.register(CodeReviewSkill())

        # 获取技能
        skill = registry.get("code_review")

        # 执行技能
        result = await skill.execute(context, code="...")
    """

    def __init__(self):
        self._skills: Dict[str, SkillBase] = {}

    def register(self, skill: SkillBase):
        """注册技能"""
        name = skill.metadata.name
        self._skills[name] = skill
        logger.info(f"[SkillRegistry] 注册技能: {name} v{skill.metadata.version}")

    def unregister(self, name: str):
        """注销技能"""
        if name in self._skills:
            del self._skills[name]
            logger.info(f"[SkillRegistry] 注销技能: {name}")

    def get(self, name: str) -> Optional[SkillBase]:
        """获取技能"""
        return self._skills.get(name)

    def list_all(self) -> List[SkillMetadata]:
        """列出所有技能"""
        return [skill.metadata for skill in self._skills.values()]

    def list_by_tag(self, tag: str) -> List[SkillBase]:
        """按标签列出技能"""
        return [skill for skill in self._skills.values() if tag in skill.metadata.tags]

    async def execute(self, name: str, context: SkillContext, **kwargs) -> SkillResult:
        """执行技能"""
        skill = self.get(name)
        if not skill:
            return SkillResult(
                success=False, data=None, message=f"技能 '{name}' 不存在"
            )

        if not skill.is_enabled():
            return SkillResult(
                success=False, data=None, message=f"技能 '{name}' 未启用"
            )

        logger.info(f"[SkillRegistry] 执行技能: {name}")
        return await skill.execute(context, **kwargs)


# 全局技能注册表
skill_registry = SkillRegistry()


# ========== 内置技能 ==========


class SummarySkill(SkillBase):
    """摘要生成技能"""

    def _define_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="summary",
            version="1.0.0",
            description="生成文本摘要",
            author="OpenDeRisk",
            tags=["nlp", "text"],
            requires=[],
        )

    async def execute(
        self, context: SkillContext, text: str, max_length: int = 200
    ) -> SkillResult:
        """生成摘要"""
        # 简单实现: 返回前N个字符
        summary = text[:max_length] + "..." if len(text) > max_length else text

        return SkillResult(
            success=True, data={"summary": summary}, message="摘要生成成功"
        )


class CodeAnalysisSkill(SkillBase):
    """代码分析技能"""

    def _define_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="code_analysis",
            version="1.0.0",
            description="分析代码质量",
            author="OpenDeRisk",
            tags=["code", "analysis"],
            requires=["read", "bash"],
        )

    async def execute(
        self, context: SkillContext, code: str, language: str = "python"
    ) -> SkillResult:
        """分析代码"""
        # 简单实现: 统计代码行数
        lines = code.split("\n")
        code_lines = [
            line for line in lines if line.strip() and not line.strip().startswith("#")
        ]

        return SkillResult(
            success=True,
            data={
                "total_lines": len(lines),
                "code_lines": len(code_lines),
                "language": language,
            },
            message="代码分析完成",
        )


# 注册内置技能
skill_registry.register(SummarySkill())
skill_registry.register(CodeAnalysisSkill())
