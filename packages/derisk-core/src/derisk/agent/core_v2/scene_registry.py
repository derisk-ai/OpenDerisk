"""
SceneRegistry - 场景注册中心

管理所有预定义和自定义的任务场景
支持快速扩展新的专业模式

使用方式:
    # 获取场景配置
    profile = SceneRegistry.get(TaskScene.CODING)
    
    # 注册自定义场景
    SceneRegistry.register(my_custom_profile)
    
    # 列出所有场景
    scenes = SceneRegistry.list_scenes()
"""

from typing import Dict, List, Optional, Any, Callable, Type
from pydantic import BaseModel
from enum import Enum
import copy
import json
import logging
from pathlib import Path

from derisk.agent.core_v2.task_scene import (
    TaskScene,
    SceneProfile,
    SceneProfileBuilder,
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
    create_scene,
)
from derisk.agent.core_v2.memory_compaction import CompactionStrategy
from derisk.agent.core_v2.reasoning_strategy import StrategyType

logger = logging.getLogger(__name__)


class SceneRegistry:
    """
    场景注册中心
    
    职责:
    1. 管理预定义场景
    2. 注册自定义场景
    3. 查询和列出场景
    4. 场景配置持久化
    
    扩展指南:
    1. 在_register_builtin_scenes中添加新场景
    2. 或使用register()方法注册自定义场景
    """
    
    _profiles: Dict[str, SceneProfile] = {}
    _user_profiles: Dict[str, SceneProfile] = {}
    _scene_handlers: Dict[str, Callable] = {}
    _initialized: bool = False
    
    @classmethod
    def _ensure_initialized(cls):
        """确保内置场景已注册"""
        if not cls._initialized:
            cls._register_builtin_scenes()
            cls._initialized = True
    
    @classmethod
    def _register_builtin_scenes(cls):
        """注册内置场景"""
        cls._profiles[TaskScene.GENERAL.value] = cls._create_general_profile()
        cls._profiles[TaskScene.CODING.value] = cls._create_coding_profile()
        cls._profiles[TaskScene.ANALYSIS.value] = cls._create_analysis_profile()
        cls._profiles[TaskScene.CREATIVE.value] = cls._create_creative_profile()
        cls._profiles[TaskScene.RESEARCH.value] = cls._create_research_profile()
        cls._profiles[TaskScene.DOCUMENTATION.value] = cls._create_documentation_profile()
        cls._profiles[TaskScene.TESTING.value] = cls._create_testing_profile()
        cls._profiles[TaskScene.REFACTORING.value] = cls._create_refactoring_profile()
        cls._profiles[TaskScene.DEBUG.value] = cls._create_debug_profile()
        
        logger.info(f"[SceneRegistry] Registered {len(cls._profiles)} builtin scenes")
    
    @classmethod
    def _create_general_profile(cls) -> SceneProfile:
        """创建通用任务场景配置"""
        return create_scene(TaskScene.GENERAL, "通用模式"). \
            description("适用于大多数任务，平衡上下文保留和响应速度"). \
            icon("🎯"). \
            tags(["default", "balanced"]). \
            context(
                truncation__strategy=TruncationStrategy.BALANCED,
                truncation__preserve_recent_ratio=0.2,
                compaction__strategy=CompactionStrategy.HYBRID,
                compaction__trigger_threshold=40,
                compaction__target_message_count=20,
                dedup__enabled=True,
                dedup__strategy=DedupStrategy.SMART,
            ). \
            prompt(
                output_format=OutputFormat.NATURAL,
                response_style=ResponseStyle.BALANCED,
                temperature=0.7,
            ). \
            tools(). \
            reasoning(strategy=StrategyType.REACT, max_steps=20). \
            build()
    
    @classmethod
    def _create_coding_profile(cls) -> SceneProfile:
        """创建编码任务场景配置"""
        return create_scene(TaskScene.CODING, "编码模式"). \
            description("针对代码编写优化，保留完整代码上下文，代码感知截断"). \
            icon("💻"). \
            tags(["coding", "development", "programming"]). \
            context(
                truncation__strategy=TruncationStrategy.CODE_AWARE,
                truncation__code_block_protection=True,
                truncation__thinking_chain_protection=True,
                truncation__file_path_protection=True,
                truncation__preserve_recent_ratio=0.25,
                compaction__strategy=CompactionStrategy.IMPORTANCE_BASED,
                compaction__trigger_threshold=50,
                compaction__target_message_count=25,
                compaction__keep_recent_count=10,
                dedup__enabled=True,
                dedup__strategy=DedupStrategy.SMART,
                dedup__dedup_tool_results=False,
                token_budget__history_budget=12000,
            ). \
            prompt(
                inject_file_context=True,
                inject_workspace_info=True,
                inject_code_style_guide=True,
                inject_project_structure=True,
                project_structure_depth=2,
                output_format=OutputFormat.CODE,
                response_style=ResponseStyle.CONCISE,
                temperature=0.3,
                max_tokens=8192,
            ). \
            tools(
                preferred_tools=["read", "write", "edit", "grep", "glob", "bash"],
                excluded_tools=[],
                require_confirmation=["bash"],
            ). \
            reasoning(strategy=StrategyType.REACT, max_steps=30). \
            build()
    
    @classmethod
    def _create_analysis_profile(cls) -> SceneProfile:
        """创建分析任务场景配置"""
        return create_scene(TaskScene.ANALYSIS, "分析模式"). \
            description("数据分析、日志分析等场景，保留完整上下文链"). \
            icon("📊"). \
            tags(["analysis", "data", "logging"]). \
            context(
                truncation__strategy=TruncationStrategy.CONSERVATIVE,
                truncation__preserve_recent_ratio=0.3,
                compaction__strategy=CompactionStrategy.LLM_SUMMARY,
                compaction__trigger_threshold=60,
                compaction__target_message_count=30,
                dedup__enabled=False,
                token_budget__history_budget=16000,
            ). \
            prompt(
                inject_file_context=True,
                output_format=OutputFormat.MARKDOWN,
                response_style=ResponseStyle.DETAILED,
                temperature=0.5,
                max_tokens=6144,
            ). \
            tools(
                preferred_tools=["read", "grep", "glob", "bash"],
                excluded_tools=["write", "edit"],
            ). \
            reasoning(strategy=StrategyType.CHAIN_OF_THOUGHT, max_steps=15). \
            build()
    
    @classmethod
    def _create_creative_profile(cls) -> SceneProfile:
        """创建创意任务场景配置"""
        return create_scene(TaskScene.CREATIVE, "创意模式"). \
            description("创意写作、头脑风暴等场景，宽松上下文限制"). \
            icon("🎨"). \
            tags(["creative", "writing", "brainstorm"]). \
            context(
                truncation__strategy=TruncationStrategy.CONSERVATIVE,
                truncation__preserve_recent_ratio=0.15,
                compaction__strategy=CompactionStrategy.HYBRID,
                compaction__trigger_threshold=30,
                dedup__enabled=False,
                validation_level=ValidationLevel.LOOSE,
            ). \
            prompt(
                output_format=OutputFormat.NATURAL,
                response_style=ResponseStyle.VERBOSE,
                temperature=0.9,
                top_p=0.95,
                max_tokens=4096,
            ). \
            tools(
                preferred_tools=["read", "write"],
                excluded_tools=["bash"],
            ). \
            reasoning(strategy=StrategyType.REFLECTION, max_steps=10). \
            build()
    
    @classmethod
    def _create_research_profile(cls) -> SceneProfile:
        """创建研究任务场景配置"""
        return create_scene(TaskScene.RESEARCH, "研究模式"). \
            description("深度研究、信息收集场景，最大化上下文保留"). \
            icon("🔬"). \
            tags(["research", "investigation", "exploration"]). \
            context(
                truncation__strategy=TruncationStrategy.CONSERVATIVE,
                truncation__preserve_recent_ratio=0.4,
                compaction__strategy=CompactionStrategy.IMPORTANCE_BASED,
                compaction__trigger_threshold=80,
                compaction__target_message_count=40,
                compaction__importance_threshold=0.6,
                dedup__enabled=True,
                dedup__strategy=DedupStrategy.SEMANTIC,
                token_budget__history_budget=20000,
            ). \
            prompt(
                inject_file_context=True,
                inject_workspace_info=True,
                output_format=OutputFormat.MARKDOWN,
                response_style=ResponseStyle.DETAILED,
                temperature=0.4,
                max_tokens=6144,
            ). \
            tools(
                preferred_tools=["read", "grep", "glob", "webfetch"],
                excluded_tools=["write", "edit", "bash"],
            ). \
            reasoning(strategy=StrategyType.PLAN_AND_EXECUTE, max_steps=25). \
            build()
    
    @classmethod
    def _create_documentation_profile(cls) -> SceneProfile:
        """创建文档任务场景配置"""
        return create_scene(TaskScene.DOCUMENTATION, "文档模式"). \
            description("文档编写、README生成等场景"). \
            icon("📝"). \
            tags(["documentation", "writing", "readme"]). \
            context(
                truncation__strategy=TruncationStrategy.BALANCED,
                truncation__file_path_protection=True,
                compaction__strategy=CompactionStrategy.HYBRID,
                compaction__trigger_threshold=35,
            ). \
            prompt(
                inject_file_context=True,
                inject_project_structure=True,
                project_structure_depth=3,
                output_format=OutputFormat.MARKDOWN,
                response_style=ResponseStyle.BALANCED,
                temperature=0.5,
            ). \
            tools(
                preferred_tools=["read", "glob", "grep", "write"],
                excluded_tools=["bash"],
            ). \
            reasoning(strategy=StrategyType.REACT, max_steps=15). \
            build()
    
    @classmethod
    def _create_testing_profile(cls) -> SceneProfile:
        """创建测试任务场景配置"""
        return create_scene(TaskScene.TESTING, "测试模式"). \
            description("单元测试、集成测试编写场景"). \
            icon("🧪"). \
            tags(["testing", "unit-test", "integration"]). \
            context(
                truncation__strategy=TruncationStrategy.CODE_AWARE,
                truncation__code_block_protection=True,
                compaction__strategy=CompactionStrategy.IMPORTANCE_BASED,
                compaction__trigger_threshold=40,
            ). \
            prompt(
                inject_file_context=True,
                inject_code_style_guide=True,
                output_format=OutputFormat.CODE,
                response_style=ResponseStyle.CONCISE,
                temperature=0.2,
            ). \
            tools(
                preferred_tools=["read", "write", "edit", "glob", "grep", "bash"],
                require_confirmation=["bash"],
            ). \
            reasoning(strategy=StrategyType.REACT, max_steps=20). \
            build()
    
    @classmethod
    def _create_refactoring_profile(cls) -> SceneProfile:
        """创建重构任务场景配置"""
        return create_scene(TaskScene.REFACTORING, "重构模式"). \
            description("代码重构、架构优化场景，高度重视代码上下文"). \
            icon("🔧"). \
            tags(["refactoring", "architecture", "optimization"]). \
            context(
                truncation__strategy=TruncationStrategy.CODE_AWARE,
                truncation__code_block_protection=True,
                truncation__file_path_protection=True,
                truncation__preserve_recent_ratio=0.3,
                compaction__strategy=CompactionStrategy.IMPORTANCE_BASED,
                compaction__trigger_threshold=60,
                compaction__target_message_count=35,
                token_budget__history_budget=15000,
            ). \
            prompt(
                inject_file_context=True,
                inject_workspace_info=True,
                inject_code_style_guide=True,
                inject_project_structure=True,
                project_structure_depth=3,
                output_format=OutputFormat.CODE,
                response_style=ResponseStyle.DETAILED,
                temperature=0.3,
            ). \
            tools(
                preferred_tools=["read", "edit", "write", "grep", "glob"],
                require_confirmation=["bash"],
            ). \
            reasoning(strategy=StrategyType.PLAN_AND_EXECUTE, max_steps=25). \
            build()
    
    @classmethod
    def _create_debug_profile(cls) -> SceneProfile:
        """创建调试任务场景配置"""
        return create_scene(TaskScene.DEBUG, "调试模式"). \
            description("Bug调试、问题排查场景，保留错误上下文"). \
            icon("🐛"). \
            tags(["debug", "troubleshooting", "bug-fix"]). \
            context(
                truncation__strategy=TruncationStrategy.ADAPTIVE,
                truncation__thinking_chain_protection=True,
                compaction__strategy=CompactionStrategy.HYBRID,
                compaction__trigger_threshold=50,
                compaction__preserve_error_messages=True,
                dedup__enabled=True,
                dedup__dedup_tool_results=False,
            ). \
            prompt(
                inject_file_context=True,
                inject_workspace_info=True,
                output_format=OutputFormat.NATURAL,
                response_style=ResponseStyle.DETAILED,
                temperature=0.4,
            ). \
            tools(
                preferred_tools=["read", "grep", "glob", "bash"],
                require_confirmation=["bash"],
            ). \
            reasoning(strategy=StrategyType.REACT, max_steps=30). \
            build()
    
    @classmethod
    def register(cls, profile: SceneProfile, is_user_defined: bool = False) -> None:
        """
        注册场景配置
        
        Args:
            profile: 场景配置
            is_user_defined: 是否为用户自定义场景
        """
        cls._ensure_initialized()
        
        key = profile.scene.value
        
        if is_user_defined:
            cls._user_profiles[key] = profile
        else:
            cls._profiles[key] = profile
        
        logger.info(f"[SceneRegistry] Registered scene: {profile.name} ({key})")
    
    @classmethod
    def get(cls, scene: TaskScene) -> Optional[SceneProfile]:
        """
        获取场景配置
        
        优先返回用户自定义配置，其次内置配置
        
        Args:
            scene: 任务场景类型
            
        Returns:
            SceneProfile or None
        """
        cls._ensure_initialized()
        
        key = scene.value
        
        if key in cls._user_profiles:
            return copy.deepcopy(cls._user_profiles[key])
        
        if key in cls._profiles:
            return copy.deepcopy(cls._profiles[key])
        
        return None
    
    @classmethod
    def get_by_name(cls, name: str) -> Optional[SceneProfile]:
        """
        通过名称获取场景配置
        
        Args:
            name: 场景名称或scene值
            
        Returns:
            SceneProfile or None
        """
        cls._ensure_initialized()
        
        for profile in cls._user_profiles.values():
            if profile.name == name:
                return copy.deepcopy(profile)
        
        for profile in cls._profiles.values():
            if profile.name == name:
                return copy.deepcopy(profile)
        
        return None
    
    @classmethod
    def list_scenes(cls, include_user_defined: bool = True) -> List[SceneProfile]:
        """
        列出所有可用场景
        
        Args:
            include_user_defined: 是否包含用户自定义场景
            
        Returns:
            List[SceneProfile]
        """
        cls._ensure_initialized()
        
        scenes = list(cls._profiles.values())
        
        if include_user_defined:
            scenes.extend(cls._user_profiles.values())
        
        return [copy.deepcopy(s) for s in scenes]
    
    @classmethod
    def list_scene_names(cls) -> List[Dict[str, Any]]:
        """
        列出所有场景名称和基本信息
        
        用于UI渲染场景选择列表
        
        Returns:
            List[Dict]: 场景基本信息列表
        """
        cls._ensure_initialized()
        
        result = []
        
        for profile in cls._profiles.values():
            result.append(profile.to_display_dict())
        
        for profile in cls._user_profiles.values():
            info = profile.to_display_dict()
            info["is_custom"] = True
            result.append(info)
        
        return result
    
    @classmethod
    def create_custom(
        cls,
        name: str,
        base: TaskScene,
        context_overrides: Optional[Dict[str, Any]] = None,
        prompt_overrides: Optional[Dict[str, Any]] = None,
        tool_overrides: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SceneProfile:
        """
        基于现有场景创建自定义场景
        
        Args:
            name: 新场景名称
            base: 基础场景
            context_overrides: 上下文策略覆盖配置
            prompt_overrides: Prompt策略覆盖配置
            tool_overrides: 工具策略覆盖配置
            metadata: 元数据
            
        Returns:
            SceneProfile: 新创建的场景配置
        """
        cls._ensure_initialized()
        
        base_profile = cls.get(base)
        if not base_profile:
            base_profile = cls.get(TaskScene.GENERAL)
        
        overrides = {}
        if context_overrides:
            overrides["context_policy"] = context_overrides
        if prompt_overrides:
            overrides["prompt_policy"] = prompt_overrides
        if tool_overrides:
            overrides["tool_policy"] = tool_overrides
        if metadata:
            overrides["metadata"] = metadata
        
        custom_profile = base_profile.create_derived(
            name=name,
            scene=TaskScene.CUSTOM,
            **overrides
        )
        
        return custom_profile
    
    @classmethod
    def register_custom(cls, profile: SceneProfile) -> None:
        """
        注册用户自定义场景
        
        Args:
            profile: 自定义场景配置
        """
        cls.register(profile, is_user_defined=True)
    
    @classmethod
    def unregister(cls, scene: TaskScene) -> bool:
        """
        注销场景（仅限用户自定义场景）
        
        Args:
            scene: 任务场景类型
            
        Returns:
            bool: 是否注销成功
        """
        key = scene.value
        
        if key in cls._user_profiles:
            del cls._user_profiles[key]
            logger.info(f"[SceneRegistry] Unregistered user scene: {key}")
            return True
        
        return False
    
    @classmethod
    def register_handler(cls, scene: TaskScene, handler: Callable) -> None:
        """
        注册场景处理器
        
        用于场景特定的初始化或处理逻辑
        
        Args:
            scene: 任务场景类型
            handler: 处理函数
        """
        cls._scene_handlers[scene.value] = handler
    
    @classmethod
    def get_handler(cls, scene: TaskScene) -> Optional[Callable]:
        """获取场景处理器"""
        return cls._scene_handlers.get(scene.value)
    
    @classmethod
    def export_profiles(cls, path: str) -> None:
        """
        导出场景配置到文件
        
        Args:
            path: 导出文件路径
        """
        cls._ensure_initialized()
        
        data = {
            "builtin": {k: v.dict() for k, v in cls._profiles.items()},
            "user_defined": {k: v.dict() for k, v in cls._user_profiles.items()},
        }
        
        Path(path).write_text(json.dumps(data, indent=2, default=str))
        logger.info(f"[SceneRegistry] Exported profiles to {path}")
    
    @classmethod
    def import_profiles(cls, path: str, as_user_defined: bool = True) -> int:
        """
        从文件导入场景配置
        
        Args:
            path: 导入文件路径
            as_user_defined: 是否作为用户自定义场景导入
            
        Returns:
            int: 导入的场景数量
        """
        content = Path(path).read_text()
        data = json.loads(content)
        
        count = 0
        
        if "user_defined" in data:
            for key, profile_dict in data["user_defined"].items():
                try:
                    profile = SceneProfile(**profile_dict)
                    cls.register(profile, is_user_defined=True)
                    count += 1
                except Exception as e:
                    logger.error(f"[SceneRegistry] Failed to import profile {key}: {e}")
        
        if not as_user_defined and "builtin" in data:
            for key, profile_dict in data["builtin"].items():
                try:
                    profile = SceneProfile(**profile_dict)
                    cls.register(profile, is_user_defined=False)
                    count += 1
                except Exception as e:
                    logger.error(f"[SceneRegistry] Failed to import profile {key}: {e}")
        
        logger.info(f"[SceneRegistry] Imported {count} profiles from {path}")
        return count
    
    @classmethod
    def clear_user_profiles(cls) -> None:
        """清除所有用户自定义场景"""
        cls._user_profiles.clear()
        logger.info("[SceneRegistry] Cleared all user-defined profiles")
    
    @classmethod
    def get_statistics(cls) -> Dict[str, Any]:
        """获取统计信息"""
        cls._ensure_initialized()
        
        return {
            "builtin_count": len(cls._profiles),
            "user_defined_count": len(cls._user_profiles),
            "handler_count": len(cls._scene_handlers),
            "total_count": len(cls._profiles) + len(cls._user_profiles),
        }


def get_scene_profile(scene: TaskScene) -> Optional[SceneProfile]:
    """便捷函数：获取场景配置"""
    return SceneRegistry.get(scene)


def list_available_scenes() -> List[Dict[str, Any]]:
    """便捷函数：列出可用场景"""
    return SceneRegistry.list_scene_names()


def create_custom_scene(
    name: str,
    base: TaskScene = TaskScene.GENERAL,
    **overrides
) -> SceneProfile:
    """便捷函数：创建自定义场景"""
    return SceneRegistry.create_custom(name, base, **overrides)