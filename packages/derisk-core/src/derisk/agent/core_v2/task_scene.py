"""
TaskScene - 任务场景与策略配置

实现针对不同任务类型的差异化上下文和Prompt策略
支持快速扩展自定义专业模式

设计原则：
- 策略组合：Prompt、Context、Truncation策略可独立配置
- 场景预设：预定义通用/编码/分析等场景
- 用户扩展：支持基于预设快速创建自定义模式
- 最小侵入：扩展现有组件而非重构
"""

from typing import Optional, Dict, Any, List, Callable, Type
from pydantic import BaseModel, Field, validator
from enum import Enum
from datetime import datetime
import copy
import logging

from derisk.agent.core_v2.memory_compaction import CompactionStrategy
from derisk.agent.core_v2.reasoning_strategy import StrategyType

logger = logging.getLogger(__name__)


class TaskScene(str, Enum):
    """
    任务场景类型 - 区分不同任务类型的上下文策略
    
    扩展指南：
    1. 添加新枚举值
    2. 在SceneRegistry中注册对应的SceneProfile
    3. 无需修改其他代码
    """
    GENERAL = "general"
    CODING = "coding"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    RESEARCH = "research"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    REFACTORING = "refactoring"
    DEBUG = "debug"
    CUSTOM = "custom"


class TruncationStrategy(str, Enum):
    """
    截断策略类型
    
    - aggressive: 激进截断，优先保证响应速度
    - balanced: 平衡截断，速度和上下文兼顾
    - conservative: 保守截断，优先保留上下文
    - adaptive: 自适应截断，根据任务类型动态调整
    - code_aware: 代码感知截断，保护代码块完整性
    """
    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    CONSERVATIVE = "conservative"
    ADAPTIVE = "adaptive"
    CODE_AWARE = "code_aware"


class DedupStrategy(str, Enum):
    """去重策略"""
    NONE = "none"
    EXACT = "exact"
    SEMANTIC = "semantic"
    SMART = "smart"


class ValidationLevel(str, Enum):
    """验证级别"""
    STRICT = "strict"
    NORMAL = "normal"
    LOOSE = "loose"


class OutputFormat(str, Enum):
    """输出格式"""
    NATURAL = "natural"
    STRUCTURED = "structured"
    CODE = "code"
    MARKDOWN = "markdown"


class ResponseStyle(str, Enum):
    """响应风格"""
    CONCISE = "concise"
    BALANCED = "balanced"
    DETAILED = "detailed"
    VERBOSE = "verbose"


class TruncationPolicy(BaseModel):
    """
    截断策略配置
    
    控制上下文如何被截断以适应模型限制
    """
    strategy: TruncationStrategy = TruncationStrategy.BALANCED
    
    max_context_ratio: float = Field(default=0.7, ge=0.3, le=0.95)
    preserve_recent_ratio: float = Field(default=0.2, ge=0.1, le=0.5)
    preserve_system_messages: bool = True
    preserve_first_user_message: bool = True
    
    code_block_protection: bool = False
    code_block_max_lines: int = 500
    
    thinking_chain_protection: bool = True
    file_path_protection: bool = False
    
    custom_protect_patterns: List[str] = Field(default_factory=list)
    
    class Config:
        use_enum_values = True


class CompactionPolicy(BaseModel):
    """
    压缩策略配置
    
    控制历史消息如何被压缩
    """
    strategy: CompactionStrategy = CompactionStrategy.HYBRID
    
    trigger_threshold: int = Field(default=40, ge=10, le=200)
    target_message_count: int = Field(default=20, ge=5, le=100)
    keep_recent_count: int = Field(default=5, ge=1, le=20)
    
    importance_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    
    preserve_tool_results: bool = True
    preserve_error_messages: bool = True
    preserve_user_questions: bool = True
    
    summary_style: str = "concise"
    max_summary_length: int = 500
    
    class Config:
        use_enum_values = True


class DedupPolicy(BaseModel):
    """
    去重策略配置
    """
    enabled: bool = True
    strategy: DedupStrategy = DedupStrategy.SMART
    
    similarity_threshold: float = Field(default=0.9, ge=0.5, le=1.0)
    window_size: int = Field(default=10, ge=3, le=50)
    
    preserve_first_occurrence: bool = True
    dedup_tool_results: bool = False
    
    class Config:
        use_enum_values = True


class TokenBudget(BaseModel):
    """
    Token预算分配
    
    控制不同部分占用的token比例
    """
    total_budget: int = Field(default=128000, description="总Token预算")
    
    system_prompt_budget: int = Field(default=2000, ge=500, le=8000)
    tools_budget: int = Field(default=3000, ge=0, le=10000)
    history_budget: int = Field(default=8000, ge=2000, le=50000)
    working_budget: int = Field(default=4000, ge=1000, le=20000)
    
    @property
    def allocated(self) -> int:
        return (
            self.system_prompt_budget + 
            self.tools_budget + 
            self.history_budget + 
            self.working_budget
        )
    
    @property
    def remaining(self) -> int:
        return self.total_budget - self.allocated


class ContextPolicy(BaseModel):
    """
    上下文策略配置
    
    整合截断、压缩、去重等策略
    针对不同任务类型的差异化配置
    """
    truncation: TruncationPolicy = Field(default_factory=TruncationPolicy)
    compaction: CompactionPolicy = Field(default_factory=CompactionPolicy)
    dedup: DedupPolicy = Field(default_factory=DedupPolicy)
    token_budget: TokenBudget = Field(default_factory=TokenBudget)
    
    validation_level: ValidationLevel = ValidationLevel.NORMAL
    
    enable_auto_compaction: bool = True
    enable_context_caching: bool = True
    
    custom_handlers: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
    
    def merge(self, other: "ContextPolicy") -> "ContextPolicy":
        """合并两个策略，other优先"""
        merged = self.copy(deep=True)
        for field in other.__fields__:
            if field != "custom_handlers":
                val = getattr(other, field)
                if val is not None:
                    setattr(merged, field, val)
        if other.custom_handlers:
            merged.custom_handlers.update(other.custom_handlers)
        return merged


class PromptPolicy(BaseModel):
    """
    Prompt策略配置
    
    控制Prompt生成和注入策略
    """
    system_prompt_type: str = Field(default="default", description="default/concise/detailed/custom")
    custom_system_prompt: Optional[str] = None
    
    include_examples: bool = True
    examples_count: int = Field(default=2, ge=0, le=5)
    
    inject_file_context: bool = True
    inject_workspace_info: bool = True
    inject_git_info: bool = False
    
    inject_code_style_guide: bool = False
    code_style_rules: List[str] = Field(default_factory=list)
    inject_lint_rules: bool = False
    lint_config_path: Optional[str] = None
    
    inject_project_structure: bool = False
    project_structure_depth: int = Field(default=2, ge=1, le=5)
    
    output_format: OutputFormat = OutputFormat.NATURAL
    response_style: ResponseStyle = ResponseStyle.BALANCED
    
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    
    max_tokens: int = Field(default=4096, ge=256, le=32000)
    
    custom_prompt_sections: Dict[str, str] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
    
    def merge(self, other: "PromptPolicy") -> "PromptPolicy":
        """合并两个策略，other优先"""
        merged = self.copy(deep=True)
        for field in other.__fields__:
            val = getattr(other, field)
            if val is not None:
                setattr(merged, field, val)
        if other.custom_prompt_sections:
            merged.custom_prompt_sections.update(other.custom_prompt_sections)
        return merged


class ToolPolicy(BaseModel):
    """
    工具策略配置
    """
    preferred_tools: List[str] = Field(default_factory=list)
    excluded_tools: List[str] = Field(default_factory=list)
    tool_priority: Dict[str, int] = Field(default_factory=dict)
    
    require_confirmation: List[str] = Field(default_factory=list)
    auto_execute_safe_tools: bool = True
    
    max_tool_calls_per_step: int = Field(default=5, ge=1, le=20)
    tool_timeout: int = Field(default=60, ge=10, le=600)
    
    class Config:
        use_enum_values = True


class SceneProfile(BaseModel):
    """
    场景配置集
    
    组合所有策略，定义一个完整的任务场景
    支持快速扩展和自定义
    """
    scene: TaskScene
    name: str
    description: str = ""
    icon: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    context_policy: ContextPolicy = Field(default_factory=ContextPolicy)
    prompt_policy: PromptPolicy = Field(default_factory=PromptPolicy)
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)
    
    reasoning_strategy: StrategyType = StrategyType.REACT
    max_reasoning_steps: int = Field(default=20, ge=1, le=100)
    
    base_scene: Optional[TaskScene] = None
    version: str = "1.0.0"
    author: Optional[str] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
    
    def create_derived(
        self,
        name: str,
        scene: TaskScene = TaskScene.CUSTOM,
        **overrides
    ) -> "SceneProfile":
        """
        基于当前配置创建派生配置
        
        用于快速创建自定义模式
        """
        base_dict = self.dict()
        base_dict["name"] = name
        base_dict["scene"] = scene
        base_dict["base_scene"] = self.scene
        
        for key, value in overrides.items():
            if key == "context_policy" and isinstance(value, dict):
                base_dict["context_policy"] = {
                    **base_dict["context_policy"],
                    **self._flatten_policy_dict(value)
                }
            elif key == "prompt_policy" and isinstance(value, dict):
                base_dict["prompt_policy"] = {
                    **base_dict["prompt_policy"],
                    **self._flatten_policy_dict(value)
                }
            elif key == "tool_policy" and isinstance(value, dict):
                base_dict["tool_policy"] = {
                    **base_dict["tool_policy"],
                    **value
                }
            elif "." in key:
                parts = key.split(".", 1)
                policy_name = parts[0]
                field_name = parts[1]
                if policy_name in base_dict:
                    if isinstance(base_dict[policy_name], dict):
                        base_dict[policy_name][field_name] = value
                    else:
                        base_dict[key] = value
            else:
                base_dict[key] = value
        
        return SceneProfile(**base_dict)
    
    def _flatten_policy_dict(self, d: Dict) -> Dict:
        """处理嵌套的策略字典"""
        result = {}
        for k, v in d.items():
            if isinstance(v, dict) and k in result and isinstance(result[k], dict):
                result[k].update(v)
            else:
                result[k] = v
        return result
    
    def to_display_dict(self) -> Dict[str, Any]:
        """转换为UI展示用的字典"""
        return {
            "scene": self.scene,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "tags": self.tags,
            "is_custom": self.scene == TaskScene.CUSTOM,
            "base_scene": self.base_scene,
        }


class SceneProfileBuilder:
    """
    场景配置构建器
    
    流式构建SceneProfile，便于自定义扩展
    """
    
    def __init__(self, scene: TaskScene, name: str):
        self._scene = scene
        self._name = name
        self._description = ""
        self._icon = None
        self._tags = []
        
        self._context_policy = ContextPolicy()
        self._prompt_policy = PromptPolicy()
        self._tool_policy = ToolPolicy()
        
        self._reasoning_strategy = StrategyType.REACT
        self._max_reasoning_steps = 20
        
        self._base_scene = None
        self._metadata = {}
    
    def description(self, desc: str) -> "SceneProfileBuilder":
        self._description = desc
        return self
    
    def icon(self, icon: str) -> "SceneProfileBuilder":
        self._icon = icon
        return self
    
    def tags(self, tags: List[str]) -> "SceneProfileBuilder":
        self._tags = tags
        return self
    
    def context(self, **kwargs) -> "SceneProfileBuilder":
        policy_dict = self._context_policy.dict()
        for k, v in kwargs.items():
            if "." in k:
                parts = k.split(".")
                d = policy_dict
                for p in parts[:-1]:
                    d = d.setdefault(p, {})
                d[parts[-1]] = v
            else:
                policy_dict[k] = v
        self._context_policy = ContextPolicy(**policy_dict)
        return self
    
    def prompt(self, **kwargs) -> "SceneProfileBuilder":
        policy_dict = self._prompt_policy.dict()
        for k, v in kwargs.items():
            if "." in k:
                parts = k.split(".")
                d = policy_dict
                for p in parts[:-1]:
                    d = d.setdefault(p, {})
                d[parts[-1]] = v
            else:
                policy_dict[k] = v
        self._prompt_policy = PromptPolicy(**policy_dict)
        return self
    
    def tools(self, **kwargs) -> "SceneProfileBuilder":
        policy_dict = self._tool_policy.dict()
        policy_dict.update(kwargs)
        self._tool_policy = ToolPolicy(**policy_dict)
        return self
    
    def reasoning(self, strategy: StrategyType, max_steps: int = 20) -> "SceneProfileBuilder":
        self._reasoning_strategy = strategy
        self._max_reasoning_steps = max_steps
        return self
    
    def base_on(self, base: TaskScene) -> "SceneProfileBuilder":
        self._base_scene = base
        return self
    
    def metadata(self, **kwargs) -> "SceneProfileBuilder":
        self._metadata.update(kwargs)
        return self
    
    def build(self) -> SceneProfile:
        return SceneProfile(
            scene=self._scene,
            name=self._name,
            description=self._description,
            icon=self._icon,
            tags=self._tags,
            context_policy=self._context_policy,
            prompt_policy=self._prompt_policy,
            tool_policy=self._tool_policy,
            reasoning_strategy=self._reasoning_strategy,
            max_reasoning_steps=self._max_reasoning_steps,
            base_scene=self._base_scene,
            metadata=self._metadata,
        )


def create_scene(scene: TaskScene, name: str) -> SceneProfileBuilder:
    """便捷函数：创建场景构建器"""
    return SceneProfileBuilder(scene, name)