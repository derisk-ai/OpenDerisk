"""
Test TaskScene - 任务场景与策略配置测试

测试内容：
1. TaskScene枚举和策略配置
2. SceneRegistry注册和查询
3. ContextProcessor上下文处理
4. ModeManager模式切换
5. AgentInfo扩展功能
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from derisk.agent.core_v2.task_scene import (
    TaskScene,
    TruncationStrategy,
    DedupStrategy,
    ValidationLevel,
    OutputFormat,
    ResponseStyle,
    TruncationPolicy,
    CompactionPolicy,
    DedupPolicy,
    TokenBudget,
    ContextPolicy,
    PromptPolicy,
    ToolPolicy,
    SceneProfile,
    SceneProfileBuilder,
    create_scene,
)

from derisk.agent.core_v2.scene_registry import (
    SceneRegistry,
    get_scene_profile,
    list_available_scenes,
    create_custom_scene,
)

from derisk.agent.core_v2.context_processor import (
    ProcessResult,
    ProtectedBlock,
    ContextProcessor,
    ContextProcessorFactory,
)

from derisk.agent.core_v2.mode_manager import (
    ModeSwitchResult,
    ModeHistory,
    ModeManager,
    ModeManagerFactory,
    get_mode_manager,
)

from derisk.agent.core_v2.agent_info import (
    AgentInfo,
    AgentMode,
    PermissionRuleset,
)


class TestTaskSceneEnums:
    """测试任务场景枚举"""
    
    def test_task_scene_values(self):
        """测试TaskScene枚举值"""
        assert TaskScene.GENERAL.value == "general"
        assert TaskScene.CODING.value == "coding"
        assert TaskScene.ANALYSIS.value == "analysis"
        assert TaskScene.CREATIVE.value == "creative"
        assert TaskScene.RESEARCH.value == "research"
        assert TaskScene.CUSTOM.value == "custom"
    
    def test_truncation_strategy_values(self):
        """测试截断策略枚举"""
        assert TruncationStrategy.AGGRESSIVE.value == "aggressive"
        assert TruncationStrategy.BALANCED.value == "balanced"
        assert TruncationStrategy.CONSERVATIVE.value == "conservative"
        assert TruncationStrategy.ADAPTIVE.value == "adaptive"
        assert TruncationStrategy.CODE_AWARE.value == "code_aware"


class TestPolicyConfigs:
    """测试策略配置"""
    
    def test_truncation_policy_defaults(self):
        """测试截断策略默认值"""
        policy = TruncationPolicy()
        assert policy.strategy == TruncationStrategy.BALANCED
        assert policy.max_context_ratio == 0.7
        assert policy.preserve_system_messages == True
        assert policy.code_block_protection == False
    
    def test_truncation_policy_custom(self):
        """测试自定义截断策略"""
        policy = TruncationPolicy(
            strategy=TruncationStrategy.CODE_AWARE,
            code_block_protection=True,
            code_block_max_lines=300,
        )
        assert policy.strategy == TruncationStrategy.CODE_AWARE
        assert policy.code_block_protection == True
        assert policy.code_block_max_lines == 300
    
    def test_compaction_policy_defaults(self):
        """测试压缩策略默认值"""
        policy = CompactionPolicy()
        assert policy.trigger_threshold == 40
        assert policy.target_message_count == 20
        assert policy.preserve_tool_results == True
    
    def test_token_budget(self):
        """测试Token预算"""
        budget = TokenBudget()
        assert budget.total_budget == 128000
        assert budget.allocated > 0
        assert budget.remaining >= 0
    
    def test_context_policy_merge(self):
        """测试上下文策略合并"""
        base = ContextPolicy()
        override = ContextPolicy(
            truncation=TruncationPolicy(strategy=TruncationStrategy.CONSERVATIVE)
        )
        merged = base.merge(override)
        assert merged.truncation.strategy == TruncationStrategy.CONSERVATIVE
    
    def test_prompt_policy_defaults(self):
        """测试Prompt策略默认值"""
        policy = PromptPolicy()
        assert policy.output_format == OutputFormat.NATURAL
        assert policy.response_style == ResponseStyle.BALANCED
        assert policy.temperature == 0.7


class TestSceneProfile:
    """测试场景配置"""
    
    def test_scene_profile_builder(self):
        """测试场景配置构建器"""
        profile = create_scene(TaskScene.CODING, "测试编码模式"). \
            description("用于测试的编码模式"). \
            icon("💻"). \
            tags(["test", "coding"]). \
            context(
                truncation__strategy=TruncationStrategy.CODE_AWARE,
                compaction__trigger_threshold=50,
            ). \
            prompt(
                temperature=0.3,
                output_format=OutputFormat.CODE,
            ). \
            build()
        
        assert profile.scene == TaskScene.CODING
        assert profile.name == "测试编码模式"
        assert profile.description == "用于测试的编码模式"
        assert profile.icon == "💻"
        assert "test" in profile.tags
        assert profile.context_policy.truncation.strategy == TruncationStrategy.CODE_AWARE
        assert profile.context_policy.compaction.trigger_threshold == 50
        assert profile.prompt_policy.temperature == 0.3
    
    def test_scene_profile_create_derived(self):
        """测试创建派生场景"""
        base = SceneProfile(
            scene=TaskScene.CODING,
            name="基础编码模式",
            context_policy=ContextPolicy(),
            prompt_policy=PromptPolicy(temperature=0.3),
            tool_policy=ToolPolicy(),
        )
        
        derived = base.create_derived(
            name="派生编码模式",
            scene=TaskScene.CUSTOM,
            prompt_policy={"temperature": 0.2},
        )
        
        assert derived.name == "派生编码模式"
        assert derived.scene == TaskScene.CUSTOM
        assert derived.base_scene == TaskScene.CODING
        assert derived.prompt_policy.temperature == 0.2
    
    def test_scene_profile_to_display_dict(self):
        """测试场景配置展示字典"""
        profile = SceneProfile(
            scene=TaskScene.CODING,
            name="编码模式",
            description="测试描述",
            icon="💻",
            context_policy=ContextPolicy(),
            prompt_policy=PromptPolicy(),
            tool_policy=ToolPolicy(),
        )
        
        display = profile.to_display_dict()
        assert display["scene"] == TaskScene.CODING
        assert display["name"] == "编码模式"
        assert display["description"] == "测试描述"
        assert display["icon"] == "💻"


class TestSceneRegistry:
    """测试场景注册中心"""
    
    def test_get_builtin_scene(self):
        """测试获取内置场景"""
        profile = SceneRegistry.get(TaskScene.GENERAL)
        assert profile is not None
        assert profile.scene == TaskScene.GENERAL
        assert profile.name == "通用模式"
    
    def test_get_coding_scene(self):
        """测试获取编码场景"""
        profile = SceneRegistry.get(TaskScene.CODING)
        assert profile is not None
        assert profile.scene == TaskScene.CODING
        assert profile.context_policy.truncation.strategy == TruncationStrategy.CODE_AWARE
        assert profile.prompt_policy.temperature == 0.3
    
    def test_list_scenes(self):
        """测试列出场景"""
        scenes = SceneRegistry.list_scenes()
        assert len(scenes) >= 9
        
        scene_names = [s.name for s in scenes]
        assert "通用模式" in scene_names
        assert "编码模式" in scene_names
    
    def test_list_scene_names(self):
        """测试列出场景名称"""
        names = SceneRegistry.list_scene_names()
        assert len(names) >= 9
        
        general = next((n for n in names if n["scene"] == "general"), None)
        assert general is not None
        assert general["name"] == "通用模式"
    
    def test_register_custom_scene(self):
        """测试注册自定义场景"""
        custom_profile = SceneProfile(
            scene=TaskScene.CUSTOM,
            name="我的自定义模式",
            description="测试自定义模式",
            context_policy=ContextPolicy(),
            prompt_policy=PromptPolicy(temperature=0.5),
            tool_policy=ToolPolicy(),
        )
        
        SceneRegistry.register_custom(custom_profile)
        
        retrieved = SceneRegistry.get(TaskScene.CUSTOM)
        assert retrieved is not None
        assert retrieved.name == "我的自定义模式"
    
    def test_create_custom_scene(self):
        """测试创建自定义场景"""
        custom = SceneRegistry.create_custom(
            name="自定义编码模式",
            base=TaskScene.CODING,
            prompt_overrides={"temperature": 0.1},
        )
        
        assert custom.name == "自定义编码模式"
        assert custom.base_scene == TaskScene.CODING
        assert custom.prompt_policy.temperature == 0.1
    
    def test_get_statistics(self):
        """测试获取统计信息"""
        stats = SceneRegistry.get_statistics()
        assert "builtin_count" in stats
        assert "user_defined_count" in stats
        assert stats["builtin_count"] >= 9


class TestContextProcessor:
    """测试上下文处理器"""
    
    def test_processor_initialization(self):
        """测试处理器初始化"""
        policy = ContextPolicy()
        processor = ContextProcessor(policy)
        
        assert processor.policy == policy
        assert processor.token_counter is not None
    
    def test_process_empty_messages(self):
        """测试处理空消息"""
        policy = ContextPolicy()
        processor = ContextProcessor(policy)
        
        result = asyncio.run(processor.process([]))
        messages, process_result = result
        
        assert len(messages) == 0
        assert process_result.original_count == 0
    
    def test_process_simple_messages(self):
        """测试处理简单消息"""
        policy = ContextPolicy()
        processor = ContextProcessor(policy)
        
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        
        result = asyncio.run(processor.process(messages))
        processed, process_result = result
        
        assert len(processed) == 2
        assert process_result.original_count == 2
        assert process_result.processed_count == 2
    
    def test_protect_code_blocks(self):
        """测试保护代码块"""
        policy = ContextPolicy(
            truncation=TruncationPolicy(code_block_protection=True)
        )
        processor = ContextProcessor(policy)
        
        messages = [
            {
                "role": "user",
                "content": "Here is some code:\n```python\nprint('hello')\n```\nEnd"
            },
        ]
        
        result = asyncio.run(processor.process(messages))
        processed, process_result = result
        
        assert process_result.protected_blocks > 0
    
    def test_deduplication(self):
        """测试去重"""
        policy = ContextPolicy(
            dedup=DedupPolicy(enabled=True, strategy=DedupStrategy.EXACT)
        )
        processor = ContextProcessor(policy)
        
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "World"},
        ]
        
        result = asyncio.run(processor.process(messages))
        processed, process_result = result
        
        assert process_result.deduped_count >= 1
    
    def test_truncation_aggressive(self):
        """测试激进截断"""
        policy = ContextPolicy(
            truncation=TruncationPolicy(strategy=TruncationStrategy.AGGRESSIVE)
        )
        processor = ContextProcessor(policy)
        
        messages = [
            {"role": "system", "content": "System message"},
        ]
        for i in range(100):
            messages.append({"role": "user", "content": f"Message {i}"})
        
        result = asyncio.run(processor.process(messages))
        processed, process_result = result
        
        assert len(processed) < len(messages)
        assert process_result.truncated_count > 0


class TestModeManager:
    """测试模式管理器"""
    
    @pytest.fixture
    def mock_agent(self):
        """创建模拟Agent"""
        agent = MagicMock()
        agent.context_policy = None
        agent.prompt_policy = None
        agent.max_steps = 20
        agent.temperature = 0.7
        agent.max_tokens = 4096
        agent.preferred_tools = []
        agent.llm_client = None
        return agent
    
    def test_mode_manager_initialization(self, mock_agent):
        """测试模式管理器初始化"""
        manager = ModeManager(mock_agent)
        
        assert manager.current_scene == TaskScene.GENERAL
        assert manager.current_profile is not None
    
    def test_switch_mode(self, mock_agent):
        """测试切换模式"""
        manager = ModeManager(mock_agent)
        
        result = manager.switch_mode(TaskScene.CODING)
        
        assert result.success == True
        assert result.to_scene == TaskScene.CODING
        assert manager.current_scene == TaskScene.CODING
    
    def test_switch_mode_same_scene(self, mock_agent):
        """测试切换到相同模式"""
        manager = ModeManager(mock_agent)
        
        result = manager.switch_mode(TaskScene.GENERAL)
        
        assert result.success == False
        assert "Already in" in result.message
    
    def test_get_available_modes(self, mock_agent):
        """测试获取可用模式列表"""
        manager = ModeManager(mock_agent)
        
        modes = manager.get_available_modes()
        
        assert len(modes) >= 9
        
        current = next((m for m in modes if m.get("is_current")), None)
        assert current is not None
    
    def test_create_custom_mode(self, mock_agent):
        """测试创建自定义模式"""
        manager = ModeManager(mock_agent)
        
        custom = manager.create_custom_mode(
            name="测试自定义模式",
            base=TaskScene.CODING,
            prompt_overrides={"temperature": 0.1},
        )
        
        assert custom.name == "测试自定义模式"
        assert custom.base_scene == TaskScene.CODING
        assert custom.prompt_policy.temperature == 0.1
    
    def test_suggest_mode(self, mock_agent):
        """测试建议模式"""
        manager = ModeManager(mock_agent)
        
        assert manager.suggest_mode("写一个函数") == TaskScene.CODING
        assert manager.suggest_mode("analyze the data") == TaskScene.ANALYSIS
        assert manager.suggest_mode("写一个故事") == TaskScene.CREATIVE
    
    def test_get_history(self, mock_agent):
        """测试获取历史"""
        manager = ModeManager(mock_agent)
        manager.switch_mode(TaskScene.CODING)
        
        history = manager.get_history()
        
        assert len(history) >= 1
        assert history[0].scene == TaskScene.GENERAL
    
    def test_update_current_policy(self, mock_agent):
        """测试更新当前策略"""
        manager = ModeManager(mock_agent)
        
        success = manager.update_current_policy(
            prompt_updates={"temperature": 0.9}
        )
        
        assert success == True


class TestAgentInfoExtension:
    """测试AgentInfo扩展"""
    
    def test_agent_info_with_scene(self):
        """测试AgentInfo任务场景"""
        info = AgentInfo(
            name="test_agent",
            task_scene=TaskScene.CODING,
        )
        
        assert info.task_scene == TaskScene.CODING
    
    def test_agent_info_get_effective_context_policy(self):
        """测试获取生效的上下文策略"""
        info = AgentInfo(
            name="test_agent",
            task_scene=TaskScene.CODING,
        )
        
        policy = info.get_effective_context_policy()
        
        assert policy.truncation.strategy == TruncationStrategy.CODE_AWARE
    
    def test_agent_info_get_effective_prompt_policy(self):
        """测试获取生效的Prompt策略"""
        info = AgentInfo(
            name="test_agent",
            task_scene=TaskScene.CODING,
        )
        
        policy = info.get_effective_prompt_policy()
        
        assert policy.temperature == 0.3
    
    def test_agent_info_with_custom_policy(self):
        """测试自定义策略覆盖"""
        custom_policy = ContextPolicy(
            truncation=TruncationPolicy(strategy=TruncationStrategy.AGGRESSIVE)
        )
        
        info = AgentInfo(
            name="test_agent",
            task_scene=TaskScene.CODING,
            context_policy=custom_policy,
        )
        
        policy = info.get_effective_context_policy()
        
        assert policy.truncation.strategy == TruncationStrategy.AGGRESSIVE
    
    def test_agent_info_with_scene_method(self):
        """测试with_scene方法"""
        info = AgentInfo(
            name="test_agent",
            task_scene=TaskScene.GENERAL,
        )
        
        new_info = info.with_scene(TaskScene.CODING)
        
        assert new_info.task_scene == TaskScene.CODING
        assert info.task_scene == TaskScene.GENERAL


class TestIntegration:
    """集成测试"""
    
    @pytest.fixture
    def mock_agent(self):
        """创建模拟Agent"""
        agent = MagicMock()
        agent.context_policy = None
        agent.prompt_policy = None
        agent.max_steps = 20
        agent.temperature = 0.7
        agent.max_tokens = 4096
        agent.preferred_tools = []
        agent.llm_client = None
        agent.agent_id = "test_agent_001"
        return agent
    
    def test_full_workflow(self, mock_agent):
        """测试完整工作流"""
        manager = ModeManager(mock_agent)
        
        modes = manager.get_available_modes()
        assert len(modes) >= 9
        
        result = manager.switch_mode(TaskScene.CODING)
        assert result.success == True
        
        processor = manager.context_processor
        assert processor is not None
        
        messages = [
            {"role": "user", "content": "Write a function"},
            {"role": "assistant", "content": "```python\ndef hello():\n    print('hello')\n```"},
        ]
        
        processed, process_result = asyncio.run(processor.process(messages))
        assert process_result.original_count == 2
        
        stats = manager.get_statistics()
        assert stats["current_scene"] == "coding"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])