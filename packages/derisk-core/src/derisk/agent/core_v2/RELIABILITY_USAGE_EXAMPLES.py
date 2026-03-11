"""
Agent Loop Reliability - 使用示例

本文档展示如何在 Core V1 和 Core V2 Agent 中使用新的可靠性机制。
"""

# ============================================================
# 场景 1: Core V1 Agent (ReActMasterAgent) 集成
# ============================================================

from derisk.agent.expand.react_master_agent import ReActMasterAgent
from derisk.agent.core_v2 import (
    make_reliable,
    with_state_machine,
    ReliabilityConfig,
    CheckpointStrategy,
    RedisStateStore,
)

# 方式 1: 简单包装 (推荐用于快速集成)


async def example_simple_wrap():
    agent = ReActMasterAgent()

    reliable = make_reliable(agent)

    result = await reliable.run("分析系统日志")

    if result["success"]:
        print(f"响应: {result['response']}")
        print(f"检查点: {result['checkpoint_id']}")
    else:
        print(f"失败: {result['error']}")
        print(f"已保存检查点: {result['checkpoint_id']}")
        print("可以使用此检查点恢复执行")


# 方式 2: 完整状态机模式 (推荐用于长任务)


async def example_state_machine():
    agent = ReActMasterAgent()

    executor = with_state_machine(agent)

    result = await executor.execute("分析系统日志并生成报告")

    print(f"最终状态: {result.final_state.name}")
    print(f"总步数: {result.total_steps}")
    print(f"健康分数: {executor.get_health_score()}")

    if not result.success:
        checkpoint_id = result.checkpoint_id
        print(f"失败，已保存检查点: {checkpoint_id}")


# 方式 3: 自定义配置


async def example_custom_config():
    config = ReliabilityConfig(
        checkpoint_strategy=CheckpointStrategy.ADAPTIVE,
        state_store=RedisStateStore("redis://localhost:6379/0"),
        working_memory_tokens=10000,
        checkpoint_interval=5,
        enable_metrics=True,
    )

    agent = ReActMasterAgent()
    reliable = make_reliable(agent, config)

    result = await reliable.run("长任务分析")


# ============================================================
# 场景 2: Core V2 Agent (ReActReasoningAgent) 集成
# ============================================================

from derisk.agent.core_v2 import (
    ReActReasoningAgent,
    AgentInfo,
    LLMFactory,
    LLMConfig,
)


async def example_core_v2():
    info = AgentInfo(name="analyst", max_steps=50)
    llm_config = LLMConfig(model="gpt-4", api_key="...")
    llm_adapter = LLMFactory.create(llm_config)

    agent = ReActReasoningAgent(info=info, llm_adapter=llm_adapter)

    reliable = make_reliable(agent)

    result = await reliable.run("分析代码库结构")


# ============================================================
# 场景 3: 从检查点恢复
# ============================================================


async def example_checkpoint_recovery():
    agent = ReActMasterAgent()
    reliable = make_reliable(agent)

    # 第一次执行 (可能失败)
    result1 = await reliable.run("复杂任务")
    checkpoint_id = result1["checkpoint_id"]

    # 稍后从检查点恢复
    result2 = await reliable.run("继续执行", resume_checkpoint=checkpoint_id)


# ============================================================
# 场景 4: 健康监控
# ============================================================


async def example_health_monitoring():
    agent = ReActMasterAgent()
    executor = with_state_machine(agent)

    await executor.execute("任务")

    health_score = executor.get_health_score()
    print(f"健康分数: {health_score}")

    if health_score < 70:
        report = reliable.get_health_report()
        print(f"问题: {report['issues']}")
        print(f"建议: {report['recommendations']}")


# ============================================================
# 场景 5: 产品层集成 (推荐)
# ============================================================

from derisk.agent.core_v2 import (
    SmartCheckpointManager,
    HierarchicalMemoryManager,
    AgentMetrics,
)


class ReliableConversationService:
    """
    产品层可靠性服务

    在对话级别集成可靠性机制，不修改 Agent 本身。
    适用于:
    - 现有系统无缝升级
    - 多租户场景
    - 分布式部署
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.checkpoint_manager = SmartCheckpointManager(
            strategy=CheckpointStrategy.ADAPTIVE,
            checkpoint_store=RedisStateStore(redis_url),
            checkpoint_interval=10,
        )
        self.memory_manager = HierarchicalMemoryManager(
            working_memory_tokens=8000,
            episodic_memory_tokens=32000,
            semantic_memory_tokens=128000,
        )
        self.metrics = AgentMetrics()
        self.agents = {}

    async def create_session(
        self,
        session_id: str,
        agent_type: str = "react_master",
    ) -> str:
        """创建会话"""
        if agent_type == "react_master":
            agent = ReActMasterAgent()
        else:
            from derisk.agent.core_v2 import ReActReasoningAgent, AgentInfo, LLMFactory

            agent = ReActReasoningAgent.create(name=session_id)

        self.agents[session_id] = {
            "agent": agent,
            "checkpoint_id": None,
            "step": 0,
        }

        return session_id

    async def chat(
        self,
        session_id: str,
        message: str,
        resume: bool = False,
    ) -> dict:
        """对话"""
        session = self.agents.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        agent = session["agent"]

        # 恢复检查点
        if resume and session["checkpoint_id"]:
            restored = await self.checkpoint_manager.restore_checkpoint(
                session["checkpoint_id"]
            )
            if restored:
                session["step"] = restored["step_index"]

        # 执行
        import time

        start_time = time.time()

        try:
            if hasattr(agent, "generate_reply"):
                from derisk.agent import AgentMessage

                reply = await agent.generate_reply(
                    received_message=AgentMessage(content=message),
                    sender=None,
                )
                response = reply.content if hasattr(reply, "content") else str(reply)
            else:
                chunks = []
                async for chunk in agent.run(message):
                    chunks.append(chunk)
                response = "".join(chunks)

            success = True
            error = None

        except Exception as e:
            response = None
            success = False
            error = str(e)

        duration_ms = (time.time() - start_time) * 1000

        # 保存检查点
        from derisk.agent.core_v2 import CheckpointType

        checkpoint = await self.checkpoint_manager.create_checkpoint(
            execution_id=session_id,
            checkpoint_type=CheckpointType.AUTOMATIC,
            state={"step": session["step"] + 1},
            step_index=session["step"] + 1,
        )
        session["checkpoint_id"] = checkpoint.checkpoint_id
        session["step"] += 1

        # 记录指标
        self.metrics.record_step(
            step_index=session["step"],
            state="COMPLETED" if success else "FAILED",
            duration_ms=duration_ms,
            success=success,
        )

        return {
            "success": success,
            "response": response,
            "error": error,
            "checkpoint_id": checkpoint.checkpoint_id,
            "step": session["step"],
        }

    async def pause_session(self, session_id: str) -> str:
        """暂停会话"""
        session = self.agents.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        from derisk.agent.core_v2 import CheckpointType

        checkpoint = await self.checkpoint_manager.create_checkpoint(
            execution_id=session_id,
            checkpoint_type=CheckpointType.MANUAL,
            state={"step": session["step"]},
            step_index=session["step"],
            message="User paused",
        )
        session["checkpoint_id"] = checkpoint.checkpoint_id

        return checkpoint.checkpoint_id

    async def resume_session(
        self,
        session_id: str,
        checkpoint_id: str = None,
    ) -> bool:
        """恢复会话"""
        session = self.agents.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        cp_id = checkpoint_id or session["checkpoint_id"]
        if not cp_id:
            return False

        restored = await self.checkpoint_manager.restore_checkpoint(cp_id)
        if restored:
            session["step"] = restored["step_index"]
            session["checkpoint_id"] = cp_id
            return True

        return False

    def get_health(self, session_id: str = None) -> dict:
        """获取健康状态"""
        return self.metrics.get_summary()


# 产品层使用示例


async def example_product_layer():
    service = ReliableConversationService(redis_url="redis://localhost:6379/0")

    # 创建会话
    session_id = await service.create_session("session-001")

    # 对话
    result = await service.chat(session_id, "分析日志文件")
    print(f"响应: {result['response']}")
    print(f"检查点: {result['checkpoint_id']}")

    # 暂停
    checkpoint_id = await service.pause_session(session_id)
    print(f"已暂停，检查点: {checkpoint_id}")

    # 稍后恢复
    await service.resume_session(session_id)
    result = await service.chat(session_id, "继续分析", resume=True)

    # 健康状态
    health = service.get_health()
    print(f"健康分数: {health['health_score']}")


# ============================================================
# 场景 6: ReActMasterAgent 内置集成 (原生支持)
# ============================================================


async def example_react_master_builtin():
    """
    ReActMasterAgent 已经内置了部分可靠性特性:
    - Doom Loop 检测
    - 上下文压缩
    - 输出截断

    可以通过参数启用或禁用。
    """
    agent = ReActMasterAgent(
        # 可靠性配置
        enable_doom_loop_detection=True,
        doom_loop_threshold=3,
        enable_session_compaction=True,
        context_window=128000,
        compaction_threshold_ratio=0.8,
        enable_output_truncation=True,
        enable_history_pruning=True,
    )

    # 使用 make_reliable 添加更多能力
    reliable = make_reliable(agent)
    result = await reliable.run("任务")


# ============================================================
# 场景 7: ReActReasoningAgent (Core V2) 内置集成
# ============================================================


async def example_react_reasoning_builtin():
    """
    ReActReasoningAgent 也内置了可靠性特性:
    - Doom Loop 检测
    - 输出截断
    - 上下文压缩 (通过 UnifiedCompactionPipeline)
    """
    from derisk.agent.core_v2 import (
        ReActReasoningAgent,
        AgentInfo,
        LLMFactory,
        LLMConfig,
    )

    info = AgentInfo(name="analyst", max_steps=50)
    llm_config = LLMConfig(model="gpt-4", api_key="...")
    llm_adapter = LLMFactory.create(llm_config)

    agent = ReActReasoningAgent(
        info=info,
        llm_adapter=llm_adapter,
        # 可靠性配置
        enable_doom_loop_detection=True,
        enable_output_truncation=True,
        enable_context_compaction=True,
        enable_compaction_pipeline=True,
    )

    # 直接运行 (已内置可靠性)
    async for chunk in agent.run("分析代码"):
        print(chunk)


# ============================================================
# 完整配置参考
# ============================================================

from derisk.agent.core_v2 import (
    ReliabilityConfig,
    CheckpointStrategy,
    FileStateStore,
    MemoryStateStore,
    RedisStateStore,
)

config = ReliabilityConfig(
    # 检查点策略
    checkpoint_strategy=CheckpointStrategy.ADAPTIVE,  # TIME_BASED, STEP_BASED, MILESTONE_BASED, ADAPTIVE
    # 状态存储
    state_store=RedisStateStore(
        "redis://localhost:6379/0"
    ),  # FileStateStore(), MemoryStateStore(), RedisStateStore()
    # 记忆配置
    working_memory_tokens=8000,  # 工作记忆容量
    episodic_memory_tokens=32000,  # 情景记忆容量
    semantic_memory_tokens=128000,  # 语义记忆容量
    # 检查点配置
    checkpoint_interval=10,  # 步数间隔
    max_checkpoints=20,  # 最大保存数量
    # 指标配置
    enable_metrics=True,
)


if __name__ == "__main__":
    import asyncio

    # 运行示例
    asyncio.run(example_simple_wrap())
    asyncio.run(example_state_machine())
    asyncio.run(example_product_layer())
