"""
SceneConfigLoader - 场景配置加载器

支持通过YAML/JSON配置文件定义场景，实现场景的配置化管理

配置文件格式：
- 支持YAML和JSON格式
- 支持继承和覆盖机制
- 支持验证和默认值

使用方式：
    loader = SceneConfigLoader()
    
    # 从文件加载
    profile = loader.load("scene_config.yaml")
    
    # 从目录加载所有场景
    profiles = loader.load_from_directory("scenes/")
    
    # 验证配置
    errors = loader.validate(config_dict)
"""

from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, ValidationError, Field, validator
from pathlib import Path
import yaml
import json
import logging
import copy
from datetime import datetime

from derisk.agent.core_v2.task_scene import (
    TaskScene,
    SceneProfile,
    ContextPolicy,
    PromptPolicy,
    ToolPolicy,
    TruncationPolicy,
    CompactionPolicy,
    DedupPolicy,
    TokenBudget,
    TruncationStrategy,
    DedupStrategy,
    ValidationLevel,
    OutputFormat,
    ResponseStyle,
)
from derisk.agent.core_v2.memory_compaction import CompactionStrategy
from derisk.agent.core_v2.reasoning_strategy import StrategyType
from derisk.agent.core_v2.scene_registry import SceneRegistry

logger = logging.getLogger(__name__)


class SceneConfigError(Exception):
    """场景配置错误"""
    pass


class TruncationPolicyConfig(BaseModel):
    """截断策略配置"""
    strategy: str = "balanced"
    max_context_ratio: float = 0.7
    preserve_recent_ratio: float = 0.2
    preserve_system_messages: bool = True
    preserve_first_user_message: bool = True
    code_block_protection: bool = False
    code_block_max_lines: int = 500
    thinking_chain_protection: bool = True
    file_path_protection: bool = False
    custom_protect_patterns: List[str] = []


class CompactionPolicyConfig(BaseModel):
    """压缩策略配置"""
    strategy: str = "hybrid"
    trigger_threshold: int = 40
    target_message_count: int = 20
    keep_recent_count: int = 5
    importance_threshold: float = 0.7
    preserve_tool_results: bool = True
    preserve_error_messages: bool = True
    preserve_user_questions: bool = True
    summary_style: str = "concise"
    max_summary_length: int = 500


class DedupPolicyConfig(BaseModel):
    """去重策略配置"""
    enabled: bool = True
    strategy: str = "smart"
    similarity_threshold: float = 0.9
    window_size: int = 10
    preserve_first_occurrence: bool = True
    dedup_tool_results: bool = False


class TokenBudgetConfig(BaseModel):
    """Token预算配置"""
    total_budget: int = 128000
    system_prompt_budget: int = 2000
    tools_budget: int = 3000
    history_budget: int = 8000
    working_budget: int = 4000


class ContextPolicyConfig(BaseModel):
    """上下文策略配置"""
    truncation: Optional[TruncationPolicyConfig] = None
    compaction: Optional[CompactionPolicyConfig] = None
    dedup: Optional[DedupPolicyConfig] = None
    token_budget: Optional[TokenBudgetConfig] = None
    validation_level: str = "normal"
    enable_auto_compaction: bool = True
    enable_context_caching: bool = True


class PromptPolicyConfig(BaseModel):
    """Prompt策略配置"""
    system_prompt_type: str = "default"
    custom_system_prompt: Optional[str] = None
    include_examples: bool = True
    examples_count: int = 2
    inject_file_context: bool = True
    inject_workspace_info: bool = True
    inject_git_info: bool = False
    inject_code_style_guide: bool = False
    code_style_rules: List[str] = []
    inject_lint_rules: bool = False
    lint_config_path: Optional[str] = None
    inject_project_structure: bool = False
    project_structure_depth: int = 2
    output_format: str = "natural"
    response_style: str = "balanced"
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 4096


class ToolPolicyConfig(BaseModel):
    """工具策略配置"""
    preferred_tools: List[str] = []
    excluded_tools: List[str] = []
    tool_priority: Dict[str, int] = {}
    require_confirmation: List[str] = []
    auto_execute_safe_tools: bool = True
    max_tool_calls_per_step: int = 5
    tool_timeout: int = 60


class ReasoningConfig(BaseModel):
    """推理策略配置"""
    strategy: str = "react"
    max_steps: int = 20


class SceneConfigFile(BaseModel):
    """
    场景配置文件格式
    
    支持的场景定义：
    - scene: 场景标识
    - name: 场景名称
    - description: 场景描述
    - extends: 继承的父场景
    - context: 上下文策略
    - prompt: Prompt策略
    - tools: 工具策略
    - reasoning: 推理策略
    """
    scene: str
    name: str
    description: str = ""
    icon: Optional[str] = None
    tags: List[str] = []
    extends: Optional[str] = None
    
    context: Optional[ContextPolicyConfig] = None
    prompt: Optional[PromptPolicyConfig] = None
    tools: Optional[ToolPolicyConfig] = None
    reasoning: Optional[ReasoningConfig] = None
    
    version: str = "1.0.0"
    author: Optional[str] = None
    metadata: Dict[str, Any] = {}


class SceneConfigLoader:
    """
    场景配置加载器
    
    职责：
    1. 从文件/目录加载场景配置
    2. 解析配置并转换为SceneProfile
    3. 验证配置有效性
    4. 处理继承关系
    
    示例：
        loader = SceneConfigLoader()
        
        # 加载单个配置
        profile = loader.load("scenes/coding.yaml")
        
        # 加载目录下所有配置
        profiles = loader.load_from_directory("scenes/")
        
        # 从字符串加载
        profile = loader.loads(yaml_content, format="yaml")
    """
    
    def __init__(self):
        self._loaded_configs: Dict[str, SceneConfigFile] = {}
        self._load_errors: Dict[str, List[str]] = {}
    
    def load(self, path: str) -> SceneProfile:
        """
        从文件加载场景配置
        
        Args:
            path: 配置文件路径（支持.yaml, .yml, .json）
            
        Returns:
            SceneProfile: 场景配置
            
        Raises:
            SceneConfigError: 配置加载或解析错误
        """
        path_obj = Path(path)
        
        if not path_obj.exists():
            raise SceneConfigError(f"Config file not found: {path}")
        
        format_type = path_obj.suffix.lstrip(".")
        
        if format_type not in ["yaml", "yml", "json"]:
            raise SceneConfigError(f"Unsupported config format: {format_type}")
        
        content = path_obj.read_text(encoding="utf-8")
        
        return self.loads(content, format=format_type, source=path)
    
    def loads(
        self,
        content: str,
        format: str = "yaml",
        source: Optional[str] = None
    ) -> SceneProfile:
        """
        从字符串加载场景配置
        
        Args:
            content: 配置内容
            format: 格式类型（yaml/json）
            source: 来源标识（用于错误信息）
            
        Returns:
            SceneProfile: 场景配置
        """
        try:
            if format in ["yaml", "yml"]:
                config_dict = yaml.safe_load(content)
            elif format == "json":
                config_dict = json.loads(content)
            else:
                raise SceneConfigError(f"Unsupported format: {format}")
            
            if not isinstance(config_dict, dict):
                raise SceneConfigError("Config must be a dictionary")
            
            return self._parse_config(config_dict, source)
            
        except yaml.YAMLError as e:
            raise SceneConfigError(f"YAML parse error: {e}")
        except json.JSONDecodeError as e:
            raise SceneConfigError(f"JSON parse error: {e}")
    
    def load_from_directory(
        self,
        directory: str,
        recursive: bool = False,
        register: bool = True
    ) -> List[SceneProfile]:
        """
        从目录加载所有场景配置
        
        Args:
            directory: 目录路径
            recursive: 是否递归加载子目录
            register: 是否自动注册到SceneRegistry
            
        Returns:
            List[SceneProfile]: 加载的场景配置列表
        """
        dir_path = Path(directory)
        
        if not dir_path.exists():
            raise SceneConfigError(f"Directory not found: {directory}")
        
        patterns = ["*.yaml", "*.yml", "*.json"]
        profiles = []
        
        for pattern in patterns:
            if recursive:
                files = list(dir_path.rglob(pattern))
            else:
                files = list(dir_path.glob(pattern))
            
            for file_path in files:
                try:
                    profile = self.load(str(file_path))
                    profiles.append(profile)
                    
                    if register:
                        SceneRegistry.register_custom(profile)
                        
                except SceneConfigError as e:
                    key = str(file_path)
                    if key not in self._load_errors:
                        self._load_errors[key] = []
                    self._load_errors[key].append(str(e))
                    logger.error(f"[SceneConfigLoader] Failed to load {file_path}: {e}")
        
        logger.info(f"[SceneConfigLoader] Loaded {len(profiles)} scenes from {directory}")
        return profiles
    
    def _parse_config(
        self,
        config_dict: Dict[str, Any],
        source: Optional[str] = None
    ) -> SceneProfile:
        """
        解析配置字典为SceneProfile
        
        Args:
            config_dict: 配置字典
            source: 来源标识
            
        Returns:
            SceneProfile: 场景配置
        """
        errors = self.validate_config(config_dict)
        if errors:
            raise SceneConfigError(f"Validation errors: {errors}")
        
        config = SceneConfigFile(**config_dict)
        
        if config.extends:
            base_profile = self._resolve_extends(config.extends)
            if base_profile:
                return self._create_derived_profile(config, base_profile)
        
        return self._create_profile(config)
    
    def _resolve_extends(self, extends: str) -> Optional[SceneProfile]:
        """解析继承关系"""
        try:
            scene_enum = TaskScene(extends)
            return SceneRegistry.get(scene_enum)
        except ValueError:
            pass
        
        if extends in self._loaded_configs:
            return self._create_profile(self._loaded_configs[extends])
        
        return SceneRegistry.get_by_name(extends)
    
    def _create_profile(self, config: SceneConfigFile) -> SceneProfile:
        """从配置创建SceneProfile"""
        try:
            scene_enum = TaskScene(config.scene)
        except ValueError:
            scene_enum = TaskScene.CUSTOM
        
        context_policy = self._build_context_policy(config.context)
        prompt_policy = self._build_prompt_policy(config.prompt)
        tool_policy = self._build_tool_policy(config.tools)
        
        reasoning_strategy = StrategyType.REACT
        max_reasoning_steps = 20
        if config.reasoning:
            try:
                reasoning_strategy = StrategyType(config.reasoning.strategy)
            except ValueError:
                pass
            max_reasoning_steps = config.reasoning.max_steps
        
        profile = SceneProfile(
            scene=scene_enum,
            name=config.name,
            description=config.description,
            icon=config.icon,
            tags=config.tags,
            context_policy=context_policy,
            prompt_policy=prompt_policy,
            tool_policy=tool_policy,
            reasoning_strategy=reasoning_strategy,
            max_reasoning_steps=max_reasoning_steps,
            version=config.version,
            author=config.author,
            metadata=config.metadata,
        )
        
        self._loaded_configs[config.scene] = config
        return profile
    
    def _create_derived_profile(
        self,
        config: SceneConfigFile,
        base: SceneProfile
    ) -> SceneProfile:
        """创建派生场景配置"""
        base_dict = base.dict()
        
        if config.context:
            context_overrides = self._config_to_dict(config.context)
            base_dict["context_policy"] = self._merge_dicts(
                base_dict.get("context_policy", {}),
                context_overrides
            )
        
        if config.prompt:
            prompt_overrides = self._config_to_dict(config.prompt)
            base_dict["prompt_policy"] = self._merge_dicts(
                base_dict.get("prompt_policy", {}),
                prompt_overrides
            )
        
        if config.tools:
            tool_overrides = self._config_to_dict(config.tools)
            base_dict["tool_policy"] = self._merge_dicts(
                base_dict.get("tool_policy", {}),
                tool_overrides
            )
        
        base_dict["scene"] = config.scene
        base_dict["name"] = config.name
        base_dict["description"] = config.description or base_dict.get("description", "")
        base_dict["base_scene"] = base.scene.value
        
        if config.icon:
            base_dict["icon"] = config.icon
        if config.tags:
            base_dict["tags"] = config.tags
        if config.metadata:
            base_dict["metadata"].update(config.metadata)
        
        return SceneProfile(**base_dict)
    
    def _merge_dicts(self, base: Dict, override: Dict) -> Dict:
        """深度合并字典"""
        result = copy.deepcopy(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_dicts(result[key], value)
            else:
                result[key] = value
        return result
    
    def _config_to_dict(self, config: BaseModel) -> Dict:
        """将配置对象转为字典（排除None值）"""
        return {k: v for k, v in config.dict().items() if v is not None}
    
    def _build_context_policy(self, config: Optional[ContextPolicyConfig]) -> ContextPolicy:
        """构建上下文策略"""
        if not config:
            return ContextPolicy()
        
        truncation = None
        if config.truncation:
            truncation = self._build_truncation_policy(config.truncation)
        
        compaction = None
        if config.compaction:
            compaction = self._build_compaction_policy(config.compaction)
        
        dedup = None
        if config.dedup:
            dedup = self._build_dedup_policy(config.dedup)
        
        token_budget = None
        if config.token_budget:
            token_budget = TokenBudget(**config.token_budget.dict())
        
        return ContextPolicy(
            truncation=truncation or TruncationPolicy(),
            compaction=compaction or CompactionPolicy(),
            dedup=dedup or DedupPolicy(),
            token_budget=token_budget or TokenBudget(),
            validation_level=ValidationLevel(config.validation_level),
            enable_auto_compaction=config.enable_auto_compaction,
            enable_context_caching=config.enable_context_caching,
        )
    
    def _build_truncation_policy(self, config: TruncationPolicyConfig) -> TruncationPolicy:
        """构建截断策略"""
        try:
            strategy = TruncationStrategy(config.strategy)
        except ValueError:
            strategy = TruncationStrategy.BALANCED
        
        return TruncationPolicy(
            strategy=strategy,
            max_context_ratio=config.max_context_ratio,
            preserve_recent_ratio=config.preserve_recent_ratio,
            preserve_system_messages=config.preserve_system_messages,
            preserve_first_user_message=config.preserve_first_user_message,
            code_block_protection=config.code_block_protection,
            code_block_max_lines=config.code_block_max_lines,
            thinking_chain_protection=config.thinking_chain_protection,
            file_path_protection=config.file_path_protection,
            custom_protect_patterns=config.custom_protect_patterns,
        )
    
    def _build_compaction_policy(self, config: CompactionPolicyConfig) -> CompactionPolicy:
        """构建压缩策略"""
        try:
            strategy = CompactionStrategy(config.strategy)
        except ValueError:
            strategy = CompactionStrategy.HYBRID
        
        return CompactionPolicy(
            strategy=strategy,
            trigger_threshold=config.trigger_threshold,
            target_message_count=config.target_message_count,
            keep_recent_count=config.keep_recent_count,
            importance_threshold=config.importance_threshold,
            preserve_tool_results=config.preserve_tool_results,
            preserve_error_messages=config.preserve_error_messages,
            preserve_user_questions=config.preserve_user_questions,
            summary_style=config.summary_style,
            max_summary_length=config.max_summary_length,
        )
    
    def _build_dedup_policy(self, config: DedupPolicyConfig) -> DedupPolicy:
        """构建去重策略"""
        try:
            strategy = DedupStrategy(config.strategy)
        except ValueError:
            strategy = DedupStrategy.SMART
        
        return DedupPolicy(
            enabled=config.enabled,
            strategy=strategy,
            similarity_threshold=config.similarity_threshold,
            window_size=config.window_size,
            preserve_first_occurrence=config.preserve_first_occurrence,
            dedup_tool_results=config.dedup_tool_results,
        )
    
    def _build_prompt_policy(self, config: Optional[PromptPolicyConfig]) -> PromptPolicy:
        """构建Prompt策略"""
        if not config:
            return PromptPolicy()
        
        try:
            output_format = OutputFormat(config.output_format)
        except ValueError:
            output_format = OutputFormat.NATURAL
        
        try:
            response_style = ResponseStyle(config.response_style)
        except ValueError:
            response_style = ResponseStyle.BALANCED
        
        return PromptPolicy(
            system_prompt_type=config.system_prompt_type,
            custom_system_prompt=config.custom_system_prompt,
            include_examples=config.include_examples,
            examples_count=config.examples_count,
            inject_file_context=config.inject_file_context,
            inject_workspace_info=config.inject_workspace_info,
            inject_git_info=config.inject_git_info,
            inject_code_style_guide=config.inject_code_style_guide,
            code_style_rules=config.code_style_rules,
            inject_lint_rules=config.inject_lint_rules,
            lint_config_path=config.lint_config_path,
            inject_project_structure=config.inject_project_structure,
            project_structure_depth=config.project_structure_depth,
            output_format=output_format,
            response_style=response_style,
            temperature=config.temperature,
            top_p=config.top_p,
            max_tokens=config.max_tokens,
        )
    
    def _build_tool_policy(self, config: Optional[ToolPolicyConfig]) -> ToolPolicy:
        """构建工具策略"""
        if not config:
            return ToolPolicy()
        
        return ToolPolicy(
            preferred_tools=config.preferred_tools,
            excluded_tools=config.excluded_tools,
            tool_priority=config.tool_priority,
            require_confirmation=config.require_confirmation,
            auto_execute_safe_tools=config.auto_execute_safe_tools,
            max_tool_calls_per_step=config.max_tool_calls_per_step,
            tool_timeout=config.tool_timeout,
        )
    
    def validate_config(self, config_dict: Dict[str, Any]) -> List[str]:
        """
        验证配置字典
        
        Args:
            config_dict: 配置字典
            
        Returns:
            List[str]: 错误信息列表，空列表表示验证通过
        """
        errors = []
        
        if "scene" not in config_dict:
            errors.append("Missing required field: scene")
        if "name" not in config_dict:
            errors.append("Missing required field: name")
        
        if "scene" in config_dict:
            scene = config_dict["scene"]
            valid_scenes = [s.value for s in TaskScene]
            if scene not in valid_scenes and scene != "custom":
                pass
        
        if "context" in config_dict:
            errors.extend(self._validate_context_config(config_dict["context"]))
        
        if "prompt" in config_dict:
            errors.extend(self._validate_prompt_config(config_dict["prompt"]))
        
        if "extends" in config_dict:
            extends = config_dict["extends"]
        
        return errors
    
    def _validate_context_config(self, config: Dict) -> List[str]:
        """验证上下文配置"""
        errors = []
        
        if "truncation" in config:
            trunc = config["truncation"]
            if "strategy" in trunc:
                valid = [s.value for s in TruncationStrategy]
                if trunc["strategy"] not in valid:
                    errors.append(f"Invalid truncation strategy: {trunc['strategy']}")
        
        if "compaction" in config:
            comp = config["compaction"]
            if "strategy" in comp:
                valid = [s.value for s in CompactionStrategy]
                if comp["strategy"] not in valid:
                    errors.append(f"Invalid compaction strategy: {comp['strategy']}")
        
        return errors
    
    def _validate_prompt_config(self, config: Dict) -> List[str]:
        """验证Prompt配置"""
        errors = []
        
        if "output_format" in config:
            valid = [f.value for f in OutputFormat]
            if config["output_format"] not in valid:
                errors.append(f"Invalid output format: {config['output_format']}")
        
        if "response_style" in config:
            valid = [s.value for s in ResponseStyle]
            if config["response_style"] not in valid:
                errors.append(f"Invalid response style: {config['response_style']}")
        
        if "temperature" in config:
            temp = config["temperature"]
            if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
                errors.append("temperature must be between 0 and 2")
        
        return errors
    
    def get_load_errors(self) -> Dict[str, List[str]]:
        """获取加载错误"""
        return self._load_errors.copy()
    
    def export_profile(
        self,
        profile: SceneProfile,
        format: str = "yaml",
        path: Optional[str] = None
    ) -> str:
        """
        导出场景配置
        
        Args:
            profile: 场景配置
            format: 导出格式（yaml/json）
            path: 导出文件路径（可选）
            
        Returns:
            str: 配置内容
        """
        config_dict = {
            "scene": profile.scene.value,
            "name": profile.name,
            "description": profile.description,
            "icon": profile.icon,
            "tags": profile.tags,
            "extends": profile.base_scene.value if profile.base_scene else None,
            "version": profile.version,
            "author": profile.author,
            "metadata": profile.metadata,
            "context": {
                "truncation": {
                    "strategy": profile.context_policy.truncation.strategy.value,
                    "max_context_ratio": profile.context_policy.truncation.max_context_ratio,
                    "preserve_recent_ratio": profile.context_policy.truncation.preserve_recent_ratio,
                    "code_block_protection": profile.context_policy.truncation.code_block_protection,
                    "thinking_chain_protection": profile.context_policy.truncation.thinking_chain_protection,
                },
                "compaction": {
                    "strategy": profile.context_policy.compaction.strategy.value,
                    "trigger_threshold": profile.context_policy.compaction.trigger_threshold,
                    "target_message_count": profile.context_policy.compaction.target_message_count,
                },
                "dedup": {
                    "enabled": profile.context_policy.dedup.enabled,
                    "strategy": profile.context_policy.dedup.strategy.value,
                },
            },
            "prompt": {
                "output_format": profile.prompt_policy.output_format.value,
                "response_style": profile.prompt_policy.response_style.value,
                "temperature": profile.prompt_policy.temperature,
                "max_tokens": profile.prompt_policy.max_tokens,
            },
            "tools": {
                "preferred_tools": profile.tool_policy.preferred_tools,
                "excluded_tools": profile.tool_policy.excluded_tools,
            },
            "reasoning": {
                "strategy": profile.reasoning_strategy.value,
                "max_steps": profile.max_reasoning_steps,
            },
        }
        
        config_dict = self._remove_none_values(config_dict)
        
        if format in ["yaml", "yml"]:
            content = yaml.dump(config_dict, default_flow_style=False, allow_unicode=True)
        elif format == "json":
            content = json.dumps(config_dict, indent=2, ensure_ascii=False)
        else:
            raise SceneConfigError(f"Unsupported format: {format}")
        
        if path:
            Path(path).write_text(content, encoding="utf-8")
            logger.info(f"[SceneConfigLoader] Exported profile to {path}")
        
        return content
    
    def _remove_none_values(self, d: Any) -> Any:
        """递归移除None值"""
        if isinstance(d, dict):
            return {k: self._remove_none_values(v) for k, v in d.items() if v is not None}
        elif isinstance(d, list):
            return [self._remove_none_values(item) for item in d]
        else:
            return d


scene_config_loader = SceneConfigLoader()


def load_scene_config(path: str) -> SceneProfile:
    """便捷函数：加载场景配置"""
    return scene_config_loader.load(path)


def load_scenes_from_directory(directory: str, register: bool = True) -> List[SceneProfile]:
    """便捷函数：从目录加载场景"""
    return scene_config_loader.load_from_directory(directory, register=register)