"""
Core_v2 Complete Test Suite

测试所有新增模块的功能
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from derisk.agent.core_v2 import (
    # Goal Management
    Goal, GoalStatus, GoalPriority, GoalManager, SuccessCriterion, CriterionType,
    # Interaction
    InteractionManager, InteractionType, InteractionRequest, InteractionResponse,
    # Model Provider
    ModelRegistry, ModelConfig, ModelMessage, OpenAIProvider, AnthropicProvider,
    # Model Monitor
    ModelMonitor, CallStatus, SpanKind, CostBudget,
    # Memory Compaction
    MemoryCompactor, CompactionStrategy, MemoryMessage,
    # Memory Vector
    VectorMemoryStore, SimpleEmbedding, InMemoryVectorStore,
    # Sandbox
    SandboxManager, SandboxConfig, LocalSandbox, SandboxType,
    # Reasoning
    ReasoningStrategyFactory, StrategyType, ReActStrategy,
    # Observability
    ObservabilityManager, MetricsCollector, Tracer, LogLevel,
    # Config
    ConfigManager, AgentConfig, ConfigSource,
)


class TestGoalManager:
    """目标管理系统测试"""
    
    def test_create_goal(self):
        manager = GoalManager()
        goal = asyncio.run(manager.create_goal(
            name="测试目标",
            description="这是一个测试目标"
        ))
        
        assert goal.name == "测试目标"
        assert goal.status == GoalStatus.PENDING
        assert goal.id is not None
    
    def test_start_goal(self):
        manager = GoalManager()
        goal = asyncio.run(manager.create_goal(
            name="测试目标",
            description="测试"
        ))
        
        result = asyncio.run(manager.start_goal(goal.id))
        assert result is True
        
        updated_goal = manager.get_goal(goal.id)
        assert updated_goal.status == GoalStatus.GOAL_IN_PROGRESS
    
    def test_complete_goal(self):
        manager = GoalManager()
        goal = asyncio.run(manager.create_goal(
            name="测试目标",
            description="测试"
        ))
        
        asyncio.run(manager.start_goal(goal.id))
        asyncio.run(manager.complete_goal(goal.id, "完成"))
        
        updated_goal = manager.get_goal(goal.id)
        assert updated_goal.status == GoalStatus.COMPLETED
    
    def test_goal_with_criteria(self):
        manager = GoalManager()
        
        criteria = [
            SuccessCriterion(
                description="测试通过",
                type=CriterionType.EXACT_MATCH,
                config={"expected": "success", "field": "result"}
            )
        ]
        
        goal = asyncio.run(manager.create_goal(
            name="带标准的目标",
            description="测试",
            criteria=criteria
        ))
        
        assert len(goal.success_criteria) == 1
    
    def test_goal_statistics(self):
        manager = GoalManager()
        asyncio.run(manager.create_goal(name="目标1", description="测试"))
        asyncio.run(manager.create_goal(name="目标2", description="测试"))
        
        stats = manager.get_statistics()
        assert stats["total_goals"] == 2


class TestInteractionManager:
    """交互协议系统测试"""
    
    def test_create_interaction_request(self):
        request = InteractionRequest(
            type=InteractionType.ASK,
            title="测试询问",
            content="这是一个问题"
        )
        
        assert request.type == InteractionType.ASK
        assert request.title == "测试询问"
        assert request.id is not None
    
    def test_interaction_response(self):
        response = InteractionResponse(
            request_id="test-123",
            choice="yes"
        )
        
        assert response.request_id == "test-123"
        assert response.choice == "yes"
    
    @pytest.mark.asyncio
    async def test_confirm_interaction(self):
        manager = InteractionManager()
        
        with patch.object(manager, '_dispatch', new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = InteractionResponse(
                request_id="test",
                choice="yes"
            )
            
            result = await manager.confirm("确认吗？")
            assert result is True
    
    def test_interaction_statistics(self):
        manager = InteractionManager()
        manager._request_count = 5
        manager._timeout_count = 1
        
        stats = manager.get_statistics()
        assert stats["total_requests"] == 5
        assert stats["timeout_count"] == 1


class TestModelProvider:
    """模型Provider测试"""
    
    def test_model_config(self):
        config = ModelConfig(
            model_id="gpt-4",
            model_name="gpt-4",
            provider="openai",
            max_tokens=4096
        )
        
        assert config.model_id == "gpt-4"
        assert config.max_tokens == 4096
    
    def test_model_registry(self):
        registry = ModelRegistry()
        
        config = ModelConfig(
            model_id="test-model",
            model_name="test",
            provider="openai"
        )
        
        provider = OpenAIProvider(config, api_key="test-key")
        registry.register_provider(provider)
        
        assert registry.get_provider("test-model") is not None
        assert "test-model" in registry.list_providers()
    
    def test_model_call_options(self):
        from derisk.agent.core_v2 import CallOptions
        
        options = CallOptions(
            temperature=0.8,
            max_tokens=1000
        )
        
        assert options.temperature == 0.8
        assert options.max_tokens == 1000


class TestModelMonitor:
    """模型监控测试"""
    
    def test_start_span(self):
        monitor = ModelMonitor()
        
        span = monitor.start_span(
            kind=SpanKind.CHAT,
            model_id="gpt-4",
            provider="openai"
        )
        
        assert span.model_id == "gpt-4"
        assert span.status == CallStatus.PENDING
    
    def test_end_span(self):
        monitor = ModelMonitor()
        
        span = monitor.start_span(
            kind=SpanKind.CHAT,
            model_id="gpt-4",
            provider="openai"
        )
        
        monitor.end_span(span, output_content="测试输出")
        
        assert span.status == CallStatus.SUCCESS
        assert span.output_content == "测试输出"
    
    def test_cost_budget(self):
        budget = CostBudget(daily_limit=10.0)
        
        assert budget.can_spend(5.0) is True
        assert budget.can_spend(15.0) is False
    
    def test_usage_stats(self):
        monitor = ModelMonitor()
        
        span = monitor.start_span(kind=SpanKind.CHAT, model_id="gpt-4", provider="openai")
        span.prompt_tokens = 100
        span.completion_tokens = 50
        monitor.end_span(span)
        
        stats = monitor.get_usage_stats()
        assert stats["call_count"] == 1


class TestMemoryCompaction:
    """记忆压缩测试"""
    
    def test_importance_scorer(self):
        from derisk.agent.core_v2 import ImportanceScorer
        
        scorer = ImportanceScorer()
        
        msg = MemoryMessage(
            id="msg-1",
            role="user",
            content="这是一个重要的测试消息"
        )
        
        score = scorer.score_message(msg)
        assert 0.0 <= score <= 1.0
    
    @pytest.mark.asyncio
    async def test_memory_compactor(self):
        compactor = MemoryCompactor()
        
        messages = [
            MemoryMessage(id=str(i), role="user", content=f"消息{i}") 
            for i in range(60)
        ]
        
        result = await compactor.compact(messages, target_count=20)
        
        assert result.original_count == 60
        assert result.compacted_count <= 25


class TestMemoryVector:
    """向量检索测试"""
    
    @pytest.mark.asyncio
    async def test_vector_store(self):
        embedding_model = SimpleEmbedding(dimension=64)
        vector_store = InMemoryVectorStore()
        
        store = VectorMemoryStore(embedding_model, vector_store)
        
        doc = await store.add_memory(
            session_id="session-1",
            content="这是一个测试记忆"
        )
        
        assert doc.id is not None
        assert doc.embedding is not None
    
    @pytest.mark.asyncio
    async def test_semantic_search(self):
        embedding_model = SimpleEmbedding(dimension=64)
        vector_store = InMemoryVectorStore()
        store = VectorMemoryStore(embedding_model, vector_store)
        
        await store.add_memory("session-1", "Python是一种编程语言")
        await store.add_memory("session-1", "今天天气很好")
        await store.add_memory("session-1", "机器学习是AI的重要分支")
        
        results = await store.search("编程", top_k=2)
        
        assert len(results) > 0


class TestSandbox:
    """沙箱执行测试"""
    
    @pytest.mark.asyncio
    async def test_local_sandbox(self):
        config = SandboxConfig(sandbox_type=SandboxType.LOCAL, timeout=30)
        sandbox = LocalSandbox(config)
        
        await sandbox.start()
        
        result = await sandbox.execute("echo 'hello'")
        
        assert result.success is True
        assert "hello" in result.output
        
        await sandbox.cleanup()
    
    def test_sandbox_config(self):
        config = SandboxConfig(
            sandbox_type=SandboxType.DOCKER,
            image="python:3.11",
            memory_limit="512m"
        )
        
        assert config.sandbox_type == SandboxType.DOCKER
        assert config.memory_limit == "512m"
    
    @pytest.mark.asyncio
    async def test_sandbox_manager(self):
        manager = SandboxManager()
        
        config = SandboxConfig(sandbox_type=SandboxType.LOCAL)
        sandbox = await manager.create_sandbox(config)
        
        stats = manager.get_statistics()
        assert stats["active_sandboxes"] == 1
        
        await manager.cleanup_all()


class TestReasoningStrategy:
    """推理策略测试"""
    
    def test_strategy_factory(self):
        mock_llm = Mock()
        factory = ReasoningStrategyFactory(mock_llm)
        
        strategies = factory.list_strategies()
        assert StrategyType.REACT.value in strategies
    
    @pytest.mark.asyncio
    async def test_react_strategy(self):
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value="测试思考")
        
        strategy = ReActStrategy(mock_llm, max_steps=5)
        
        assert strategy.get_strategy_name() == "ReAct"
    
    @pytest.mark.asyncio
    async def test_chain_of_thought(self):
        from derisk.agent.core_v2 import ChainOfThoughtStrategy
        
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value="Therefore, the answer is 42.")
        
        strategy = ChainOfThoughtStrategy(mock_llm)
        
        assert strategy.get_strategy_name() == "ChainOfThought"


class TestObservability:
    """可观测性测试"""
    
    def test_metrics_collector(self):
        metrics = MetricsCollector(prefix="agent_")
        
        metrics.counter("requests_total", value=1)
        metrics.gauge("active_sessions", value=10)
        metrics.histogram("latency_ms", value=150)
        
        assert metrics.get_counts("requests_total") == 1
        assert metrics.get_gauge("active_sessions") == 10
    
    def test_tracer(self):
        tracer = Tracer("test-service")
        
        span = tracer.start_span("test_operation")
        span.set_tag("key", "value")
        span.add_event("event_name")
        
        tracer.end_span(span)
        
        assert span.duration_ms > 0
        assert len(tracer.get_trace(span.trace_id)) == 1
    
    def test_observability_manager(self):
        obs = ObservabilityManager("test-service")
        
        span = obs.start_span("test")
        obs.metrics.counter("test_metric")
        obs.logger.info("Test message")
        
        obs.end_span(span)
        
        health = obs.get_health_check()
        assert health["status"] == "healthy"


class TestConfigManager:
    """配置管理测试"""
    
    def test_set_get(self):
        config = ConfigManager()
        
        config.set("model_name", "gpt-4")
        config.set("temperature", 0.8)
        
        assert config.get("model_name") == "gpt-4"
        assert config.get("temperature") == 0.8
    
    def test_default_value(self):
        config = ConfigManager()
        
        assert config.get("non_existent", "default") == "default"
    
    def test_watch(self):
        config = ConfigManager()
        
        changes = []
        
        def on_change(key, value):
            changes.append((key, value))
        
        config.watch("test_key", on_change)
        config.set("test_key", "test_value")
        
        assert len(changes) == 1
        assert changes[0] == ("test_key", "test_value")
    
    def test_config_validation(self):
        config = ConfigManager()
        config.set("max_steps", 100)
        
        errors = config.validate()
        assert len(errors) == 0
    
    def test_sensitive_config(self):
        config = ConfigManager()
        config.set("api_key", "sk-secret-key-12345")
        
        masked = config.get("api_key", sensitive=True)
        assert "secret" not in masked
        assert "****" in masked or "*" in masked
    
    def test_global_config(self):
        from derisk.agent.core_v2 import GlobalConfig, get_config, set_config
        
        GlobalConfig.initialize({"test": "value"})
        
        assert get_config("test") == "value"
        
        set_config("new_key", "new_value")
        assert get_config("new_key") == "new_value"


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_agent_flow(self):
        config_manager = ConfigManager()
        config_manager.set("model_name", "gpt-4")
        config_manager.set("max_steps", 10)
        
        obs = ObservabilityManager("agent-test")
        
        goal_manager = GoalManager()
        goal = await goal_manager.create_goal(
            name="执行任务",
            description="测试完整流程"
        )
        
        interaction = InteractionManager()
        
        span = obs.start_span("agent_execution")
        
        await goal_manager.start_goal(goal.id)
        
        obs.metrics.counter("goals_started")
        
        await goal_manager.complete_goal(goal.id, "任务完成")
        
        obs.metrics.counter("goals_completed")
        
        obs.end_span(span)
        
        final_goal = goal_manager.get_goal(goal.id)
        assert final_goal.status == GoalStatus.COMPLETED
        
        stats = obs.metrics.get_counts("goals_started")
        assert stats == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])