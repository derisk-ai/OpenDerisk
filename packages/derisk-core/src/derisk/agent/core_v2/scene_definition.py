"""
SceneDefinition - MD 格式的场景定义数据模型

支持通过 Markdown 文件定义 Agent 角色和场景
实现场景化的 Agent 设计

设计原则:
- MD 优先：使用 Markdown 格式定义，易于编辑和维护
- 结构化：将 MD 内容映射到结构化数据模型
- 可扩展：支持自定义字段和扩展
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
from enum import Enum
from datetime import datetime
import logging

from .task_scene import (
    TaskScene,
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


class SceneTriggerType(str, Enum):
    """场景触发类型"""

    KEYWORD = "keyword"  # 关键词触发
    SEMANTIC = "semantic"  # 语义触发
    LLM_CLASSIFY = "llm_classify"  # LLM 分类
    MANUAL = "manual"  # 手动指定


class WorkflowPhase(BaseModel):
    """工作流程阶段"""

    name: str
    description: str
    steps: List[str] = Field(default_factory=list)
    required: bool = True
    tools_needed: List[str] = Field(default_factory=list)


class ToolRule(BaseModel):
    """工具使用规则"""

    tool_name: str
    rule_type: str  # "must", "forbidden", "confirm", "priority"
    condition: Optional[str] = None
    description: str = ""


class SceneHookConfig(BaseModel):
    """场景钩子配置"""

    on_enter: Optional[str] = None  # 进入场景时的钩子函数名
    on_exit: Optional[str] = None  # 退出场景时的钩子函数名
    before_think: Optional[str] = None  # 思考前钩子
    after_think: Optional[str] = None  # 思考后钩子
    before_act: Optional[str] = None  # 行动前钩子
    after_act: Optional[str] = None  # 行动后钩子
    before_tool: Optional[str] = None  # 工具调用前钩子
    after_tool: Optional[str] = None  # 工具调用后钩子
    on_error: Optional[str] = None  # 错误处理钩子
    on_complete: Optional[str] = None  # 完成时钩子


class AgentRoleDefinition(BaseModel):
    """
    Agent 基础角色定义

    从 agent-role.md 解析而来，定义 Agent 的基础能力和角色设定
    """

    # 基本信息
    name: str = Field(..., description="Agent 名称")
    version: str = Field(default="1.0.0", description="版本号")
    description: str = Field(default="", description="描述")
    author: Optional[str] = Field(default=None, description="作者")

    # 角色设定
    role_definition: str = Field(default="", description="角色定位")
    core_capabilities: List[str] = Field(default_factory=list, description="核心能力")
    working_principles: List[str] = Field(default_factory=list, description="工作原则")

    # 知识和专业
    domain_knowledge: List[str] = Field(default_factory=list, description="领域知识")
    expertise_areas: List[str] = Field(default_factory=list, description="专业领域")

    # 可用场景
    available_scenes: List[str] = Field(
        default_factory=list, description="可用场景 ID 列表"
    )

    # 全局工具（所有场景共享）
    global_tools: List[str] = Field(default_factory=list, description="全局工具列表")

    # 全局约束
    global_constraints: List[str] = Field(default_factory=list, description="全局约束")
    forbidden_actions: List[str] = Field(default_factory=list, description="禁止操作")

    # 元数据和扩展
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")

    # MD 文件路径（用于追溯）
    md_file_path: Optional[str] = Field(default=None, description="MD 文件路径")

    class Config:
        use_enum_values = True


class SceneDefinition(BaseModel):
    """
    场景定义

    从 scene-*.md 解析而来，定义一个完整的工作场景
    扩展了 SceneProfile，增加了 MD 格式特有的字段
    """

    # 场景标识
    scene_id: str = Field(..., description="场景 ID（唯一标识）")
    scene_name: str = Field(..., description="场景名称")
    description: str = Field(default="", description="场景描述")

    # 触发条件
    trigger_type: SceneTriggerType = Field(
        default=SceneTriggerType.KEYWORD, description="触发类型"
    )
    trigger_keywords: List[str] = Field(default_factory=list, description="触发关键词")
    trigger_priority: int = Field(
        default=5, ge=1, le=10, description="触发优先级（数字越大优先级越高）"
    )

    # 场景角色设定（会叠加到基础角色上）
    scene_role_prompt: str = Field(default="", description="场景特定的角色设定")
    scene_knowledge: List[str] = Field(
        default_factory=list, description="场景特定的知识"
    )

    # 工作流程
    workflow_phases: List[WorkflowPhase] = Field(
        default_factory=list, description="工作流程阶段"
    )

    # 工具配置
    scene_tools: List[str] = Field(default_factory=list, description="场景专用工具")
    tool_rules: List[ToolRule] = Field(default_factory=list, description="工具使用规则")

    # 输出格式
    output_format_spec: str = Field(default="", description="输出格式规范")
    output_sections: List[str] = Field(default_factory=list, description="输出章节")

    # 钩子配置
    hooks: SceneHookConfig = Field(
        default_factory=SceneHookConfig, description="钩子配置"
    )

    # 继承自 SceneProfile 的策略配置
    context_policy: Optional[ContextPolicy] = None
    prompt_policy: Optional[PromptPolicy] = None
    tool_policy: Optional[ToolPolicy] = None
    reasoning_strategy: Optional[StrategyType] = None
    max_reasoning_steps: Optional[int] = None

    # 元数据
    version: str = Field(default="1.0.0", description="版本号")
    author: Optional[str] = Field(default=None, description="作者")
    tags: List[str] = Field(default_factory=list, description="标签")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")

    # MD 文件路径
    md_file_path: Optional[str] = Field(default=None, description="MD 文件路径")

    # 创建和更新时间
    created_at: Optional[datetime] = Field(default=None, description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")

    class Config:
        use_enum_values = True

    def to_scene_profile(
        self, base_scene: TaskScene = TaskScene.CUSTOM
    ) -> "SceneProfile":
        """
        转换为 SceneProfile（用于与现有系统集成）

        Args:
            base_scene: 基础场景类型

        Returns:
            SceneProfile 实例
        """
        from .task_scene import SceneProfile

        # 构建上下文策略
        context_policy = self.context_policy or ContextPolicy()

        # 构建提示词策略
        prompt_policy = self.prompt_policy or PromptPolicy()
        if self.scene_role_prompt:
            prompt_policy.custom_system_prompt = self.scene_role_prompt

        # 构建工具策略
        tool_policy = self.tool_policy or ToolPolicy()
        if self.scene_tools:
            tool_policy.preferred_tools = self.scene_tools
        if self.tool_rules:
            forbidden = [
                r.tool_name for r in self.tool_rules if r.rule_type == "forbidden"
            ]
            tool_policy.excluded_tools = forbidden

        return SceneProfile(
            scene=base_scene,
            name=self.scene_name,
            description=self.description,
            tags=self.tags,
            context_policy=context_policy,
            prompt_policy=prompt_policy,
            tool_policy=tool_policy,
            reasoning_strategy=self.reasoning_strategy or StrategyType.REACT,
            max_reasoning_steps=self.max_reasoning_steps or 20,
            version=self.version,
            author=self.author,
            metadata={
                **self.metadata,
                "scene_id": self.scene_id,
                "trigger_keywords": self.trigger_keywords,
                "workflow_phases": [p.dict() for p in self.workflow_phases],
            },
        )


class SceneSwitchDecision(BaseModel):
    """场景切换决策"""

    should_switch: bool = Field(..., description="是否切换场景")
    target_scene: Optional[str] = Field(default=None, description="目标场景 ID")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    reasoning: str = Field(default="", description="决策理由")
    matched_keywords: List[str] = Field(
        default_factory=list, description="匹配的关键词"
    )

    class Config:
        use_enum_values = True


class SceneState(BaseModel):
    """场景运行时状态"""

    current_scene_id: Optional[str] = None
    activated_at: Optional[datetime] = None
    tools_injected: List[str] = Field(default_factory=list)
    workflow_phase: int = Field(default=0, description="当前工作流程阶段索引")
    step_count: int = Field(default=0, description="当前场景执行步数")

    class Config:
        use_enum_values = True


class SceneSwitchRecord(BaseModel):
    """场景切换记录"""

    from_scene: Optional[str] = None
    to_scene: str
    timestamp: datetime = Field(default_factory=datetime.now)
    reason: str = ""
    user_input: Optional[str] = None
    confidence: float = Field(default=0.0)

    class Config:
        use_enum_values = True


# ==================== 导出 ====================

__all__ = [
    # 枚举
    "SceneTriggerType",
    # 数据模型
    "WorkflowPhase",
    "ToolRule",
    "SceneHookConfig",
    "AgentRoleDefinition",
    "SceneDefinition",
    "SceneSwitchDecision",
    "SceneState",
    "SceneSwitchRecord",
]
