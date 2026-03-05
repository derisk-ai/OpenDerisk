"""
Scene Strategy API Schemas

场景策略API数据结构定义
支持前端管理和维护场景策略
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator

from derisk._private.pydantic import ConfigDict
from derisk.agent.core_v2.task_scene import (
    TaskScene,
    TruncationStrategy,
    DedupStrategy,
    ValidationLevel,
    OutputFormat,
    ResponseStyle,
)
from derisk.agent.core_v2.memory_compaction import CompactionStrategy
from derisk.agent.core_v2.reasoning_strategy import StrategyType


class TruncationPolicySchema(BaseModel):
    """截断策略配置Schema"""
    model_config = ConfigDict(use_enum_values=True)
    
    strategy: str = Field(default="balanced", description="截断策略")
    max_context_ratio: float = Field(default=0.7, ge=0.3, le=0.95)
    preserve_recent_ratio: float = Field(default=0.2, ge=0.1, le=0.5)
    preserve_system_messages: bool = Field(default=True)
    preserve_first_user_message: bool = Field(default=True)
    code_block_protection: bool = Field(default=False, description="是否保护代码块")
    code_block_max_lines: int = Field(default=500, description="代码块最大行数")
    thinking_chain_protection: bool = Field(default=True)
    file_path_protection: bool = Field(default=False, description="是否保护文件路径")


class CompactionPolicySchema(BaseModel):
    """压缩策略配置Schema"""
    model_config = ConfigDict(use_enum_values=True)
    
    strategy: str = Field(default="hybrid")
    trigger_threshold: int = Field(default=40, ge=10, le=200)
    target_message_count: int = Field(default=20, ge=5, le=100)
    keep_recent_count: int = Field(default=5, ge=1, le=20)
    importance_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    preserve_tool_results: bool = Field(default=True)
    preserve_error_messages: bool = Field(default=True)
    preserve_user_questions: bool = Field(default=True)


class DedupPolicySchema(BaseModel):
    """去重策略配置Schema"""
    model_config = ConfigDict(use_enum_values=True)
    
    enabled: bool = Field(default=True)
    strategy: str = Field(default="smart")
    similarity_threshold: float = Field(default=0.9, ge=0.5, le=1.0)
    window_size: int = Field(default=10, ge=3, le=50)
    preserve_first_occurrence: bool = Field(default=True)


class TokenBudgetSchema(BaseModel):
    """Token预算配置Schema"""
    total_budget: int = Field(default=128000)
    system_prompt_budget: int = Field(default=2000)
    tools_budget: int = Field(default=3000)
    history_budget: int = Field(default=8000)
    working_budget: int = Field(default=4000)


class ContextPolicySchema(BaseModel):
    """上下文策略配置Schema"""
    model_config = ConfigDict(use_enum_values=True)
    
    truncation: Optional[TruncationPolicySchema] = None
    compaction: Optional[CompactionPolicySchema] = None
    dedup: Optional[DedupPolicySchema] = None
    token_budget: Optional[TokenBudgetSchema] = None
    validation_level: str = Field(default="normal")
    enable_auto_compaction: bool = Field(default=True)


class SystemPromptSectionSchema(BaseModel):
    """System Prompt段落Schema"""
    role_definition: Optional[str] = Field(default="", description="角色定义")
    capabilities: Optional[str] = Field(default="", description="能力描述")
    constraints: Optional[str] = Field(default="", description="约束条件")
    guidelines: Optional[str] = Field(default="", description="指导原则")
    examples: Optional[str] = Field(default="", description="示例")


class PromptPolicySchema(BaseModel):
    """Prompt策略配置Schema"""
    model_config = ConfigDict(use_enum_values=True)
    
    system_prompt_type: str = Field(default="default")
    custom_system_prompt: Optional[str] = Field(default=None)
    
    include_examples: bool = Field(default=True)
    examples_count: int = Field(default=2)
    
    inject_file_context: bool = Field(default=True)
    inject_workspace_info: bool = Field(default=True)
    inject_git_info: bool = Field(default=False)
    
    inject_code_style_guide: bool = Field(default=False, description="是否注入代码风格")
    code_style_rules: List[str] = Field(default_factory=list, description="代码风格规则")
    inject_lint_rules: bool = Field(default=False)
    inject_project_structure: bool = Field(default=False)
    
    output_format: str = Field(default="natural", description="输出格式")
    response_style: str = Field(default="balanced", description="响应风格")
    
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, description="最大Token数")


class ToolPolicySchema(BaseModel):
    """工具策略配置Schema"""
    preferred_tools: List[str] = Field(default_factory=list, description="首选工具")
    excluded_tools: List[str] = Field(default_factory=list, description="排除工具")
    require_confirmation: List[str] = Field(default_factory=list, description="需要确认的工具")
    auto_execute_safe_tools: bool = Field(default=True)
    max_tool_calls_per_step: int = Field(default=5, ge=1, le=20)
    tool_timeout: int = Field(default=60, ge=10, le=600)


class ReasoningPolicySchema(BaseModel):
    """推理策略配置Schema"""
    strategy: str = Field(default="react")
    max_steps: int = Field(default=20, ge=1, le=100)


class HookConfigSchema(BaseModel):
    """钩子配置Schema"""
    hook_name: str = Field(description="钩子名称")
    enabled: bool = Field(default=True, description="是否启用")
    priority: int = Field(default=50, description="优先级")
    phases: List[str] = Field(default_factory=list, description="执行的阶段")
    config: Dict[str, Any] = Field(default_factory=dict, description="钩子配置参数")


class SystemPromptTemplateSchema(BaseModel):
    """System Prompt模板Schema"""
    base_template: Optional[str] = Field(default="", description="基础模板")
    role_definition: Optional[str] = Field(default="", description="角色定义")
    capabilities: Optional[str] = Field(default="", description="能力描述")
    constraints: Optional[str] = Field(default="", description="约束条件")
    guidelines: Optional[str] = Field(default="", description="指导原则")
    examples: Optional[str] = Field(default="", description="示例")
    sections_order: List[str] = Field(
        default_factory=lambda: ["role", "capabilities", "constraints", "guidelines", "examples"],
        description="段落顺序"
    )


class SceneStrategyCreateRequest(BaseModel):
    """创建场景策略请求"""
    model_config = ConfigDict(use_enum_values=True)
    
    scene_code: str = Field(description="场景编码", min_length=1, max_length=128)
    scene_name: str = Field(description="场景名称", min_length=1, max_length=256)
    scene_type: str = Field(default="custom", description="场景类型")
    description: Optional[str] = Field(default="", description="场景描述")
    icon: Optional[str] = Field(default=None, description="场景图标")
    tags: List[str] = Field(default_factory=list, description="场景标签")
    
    base_scene: Optional[str] = Field(default=None, description="继承的基础场景")
    
    system_prompt: Optional[SystemPromptTemplateSchema] = Field(
        default=None, description="System Prompt模板"
    )
    context_policy: Optional[ContextPolicySchema] = Field(
        default=None, description="上下文策略"
    )
    prompt_policy: Optional[PromptPolicySchema] = Field(
        default=None, description="Prompt策略"
    )
    tool_policy: Optional[ToolPolicySchema] = Field(
        default=None, description="工具策略"
    )
    reasoning: Optional[ReasoningPolicySchema] = Field(
        default=None, description="推理策略"
    )
    hooks: List[HookConfigSchema] = Field(
        default_factory=list, description="钩子配置"
    )
    
    user_code: Optional[str] = Field(default=None)
    sys_code: Optional[str] = Field(default=None)
    
    @field_validator("scene_code")
    @classmethod
    def validate_scene_code(cls, v):
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("scene_code can only contain letters, numbers, underscores and hyphens")
        return v.lower()


class SceneStrategyUpdateRequest(BaseModel):
    """更新场景策略请求"""
    model_config = ConfigDict(use_enum_values=True)
    
    scene_name: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    icon: Optional[str] = Field(default=None)
    tags: Optional[List[str]] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)
    
    system_prompt: Optional[SystemPromptTemplateSchema] = Field(default=None)
    context_policy: Optional[ContextPolicySchema] = Field(default=None)
    prompt_policy: Optional[PromptPolicySchema] = Field(default=None)
    tool_policy: Optional[ToolPolicySchema] = Field(default=None)
    reasoning: Optional[ReasoningPolicySchema] = Field(default=None)
    hooks: Optional[List[HookConfigSchema]] = Field(default=None)


class SceneStrategyResponse(BaseModel):
    """场景策略响应"""
    model_config = ConfigDict(use_enum_values=True, from_attributes=True)
    
    scene_code: str
    scene_name: str
    scene_type: str
    description: Optional[str] = None
    icon: Optional[str] = None
    tags: List[str] = []
    
    base_scene: Optional[str] = None
    
    system_prompt: Optional[SystemPromptTemplateSchema] = None
    context_policy: Optional[ContextPolicySchema] = None
    prompt_policy: Optional[PromptPolicySchema] = None
    tool_policy: Optional[ToolPolicySchema] = None
    reasoning: Optional[ReasoningPolicySchema] = None
    hooks: List[HookConfigSchema] = []
    
    is_builtin: bool = False
    is_active: bool = True
    
    user_code: Optional[str] = None
    sys_code: Optional[str] = None
    
    version: str = "1.0.0"
    author: Optional[str] = None
    
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SceneStrategyListResponse(BaseModel):
    """场景策略列表响应"""
    total_count: int = 0
    total_page: int = 0
    current_page: int = 1
    page_size: int = 20
    items: List[SceneStrategyResponse] = []


class SceneStrategyBriefResponse(BaseModel):
    """场景策略简要响应（用于选择列表）"""
    scene_code: str
    scene_name: str
    scene_type: str
    description: Optional[str] = None
    icon: Optional[str] = None
    is_builtin: bool = False
    is_active: bool = True


class AppSceneBindingRequest(BaseModel):
    """应用场景绑定请求"""
    app_code: str = Field(description="应用编码")
    scene_code: str = Field(description="场景编码")
    is_primary: bool = Field(default=True, description="是否主要场景")
    custom_overrides: Dict[str, Any] = Field(
        default_factory=dict, 
        description="自定义覆盖配置"
    )


class AppSceneBindingResponse(BaseModel):
    """应用场景绑定响应"""
    model_config = ConfigDict(use_enum_values=True)
    
    app_code: str
    scene_code: str
    scene_name: str
    scene_icon: Optional[str] = None
    is_primary: bool
    custom_overrides: Dict[str, Any] = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PreviewSystemPromptRequest(BaseModel):
    """预览System Prompt请求"""
    scene_code: Optional[str] = Field(default=None, description="场景编码")
    system_prompt: Optional[SystemPromptTemplateSchema] = Field(default=None)
    variables: Dict[str, Any] = Field(default_factory=dict, description="模板变量")


class PreviewSystemPromptResponse(BaseModel):
    """预览System Prompt响应"""
    rendered_prompt: str = Field(description="渲染后的Prompt")
    scene_code: Optional[str] = None
    variables_used: List[str] = Field(default_factory=list, description="使用的变量")


class SceneComparisonResponse(BaseModel):
    """场景对比响应"""
    scene_code: str
    scene_name: str
    differences: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="差异对比 {字段名: {scene1: value1, scene2: value2}}"
    )


class AvailableHookResponse(BaseModel):
    """可用钩子响应"""
    hook_name: str
    description: str
    default_priority: int
    available_phases: List[str]
    config_schema: Dict[str, Any] = Field(default_factory=dict)