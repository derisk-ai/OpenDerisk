"""
分层上下文索引系统 - 使用示例

展示如何在Agent中配置和使用：
1. Memory Prompt自定义
2. 压缩策略配置
3. 异步使用
4. Core V1/V2集成
"""

# ============================================================
# 示例1: 在ReActMasterAgent中配置Memory Prompt
# ============================================================

from derisk._private.pydantic import Field
from derisk.agent import ConversableAgent, ProfileConfig
from derisk.agent.shared.hierarchical_context import (
    MemoryPromptConfig,
    HierarchicalCompactionConfig,
    CompactionStrategy,
    get_memory_prompt_preset,
    create_memory_prompt_config,
)


class MyReActAgent(ConversableAgent):
    """
    自定义Agent示例 - 使用分层上下文管理
    """
    
    # ========== Memory Prompt配置（用户可编辑）==========
    memory_prompt_config: MemoryPromptConfig = Field(
        default_factory=lambda: MemoryPromptConfig(
            # 章节摘要Prompt
            chapter_summary_prompt="""请为以下任务阶段生成摘要：

阶段: {chapter_title} ({chapter_phase})
步骤数: {section_count}

步骤概览:
{sections_overview}

请输出:
1. 主要目标
2. 完成事项
3. 关键发现
4. 后续跟进
""",
            # 节压缩Prompt
            section_compact_prompt="""压缩以下步骤内容：

{step_name}: {step_content}

摘要:""",
            # 上下文模板
            memory_context_system_prompt="""## 任务历史

{hierarchical_context}

可使用 recall_history 工具查看详情。
""",
            # 是否注入到系统提示
            inject_memory_to_system=True,
        )
    )
    
    # ========== 压缩配置 ==========
    hierarchical_compaction_config: HierarchicalCompactionConfig = Field(
        default_factory=lambda: HierarchicalCompactionConfig(
            enabled=True,
            strategy=CompactionStrategy.LLM_SUMMARY,
            token_threshold=50000,
            check_interval=10,
            protect_recent_chapters=2,
        )
    )
    
    # 是否启用分层上下文
    enable_hierarchical_context: bool = True


# ============================================================
# 示例2: 使用预定义的Memory Prompt模板
# ============================================================

class OpenCodeStyleAgent(ConversableAgent):
    """使用OpenCode风格的Memory Prompt"""
    
    memory_prompt_config: MemoryPromptConfig = Field(
        default_factory=lambda: get_memory_prompt_preset("opencode")
    )


class ChineseStyleAgent(ConversableAgent):
    """使用中文优化的Memory Prompt"""
    
    memory_prompt_config: MemoryPromptConfig = Field(
        default_factory=lambda: get_memory_prompt_preset("chinese")
    )


class ConciseStyleAgent(ConversableAgent):
    """使用简洁风格"""
    
    memory_prompt_config: MemoryPromptConfig = Field(
        default_factory=lambda: get_memory_prompt_preset("concise")
    )


# ============================================================
# 示例3: 自定义压缩规则
# ============================================================

from derisk.agent.shared.hierarchical_context import (
    CompactionRuleConfig,
    CompactionTrigger,
)


class CustomCompactionAgent(ConversableAgent):
    """自定义压缩规则的Agent"""
    
    hierarchical_compaction_config: HierarchicalCompactionConfig = Field(
        default_factory=lambda: HierarchicalCompactionConfig(
            enabled=True,
            strategy=CompactionStrategy.LLM_SUMMARY,
            trigger=CompactionTrigger.TOKEN_THRESHOLD,
            token_threshold=30000,  # 更早触发压缩
            
            # 自定义压缩规则
            rules=CompactionRuleConfig(
                # CRITICAL内容永不压缩
                critical_rules={
                    "preserve": True,
                    "max_length": None,
                },
                # HIGH内容保留500字符
                high_rules={
                    "preserve": False,
                    "max_length": 500,
                    "keep_recent": 5,
                },
                # MEDIUM内容保留200字符
                medium_rules={
                    "preserve": False,
                    "max_length": 200,
                    "keep_recent": 10,
                },
                # LOW内容立即压缩到100字符
                low_rules={
                    "preserve": False,
                    "max_length": 100,
                    "keep_recent": 20,
                },
            ),
            
            # 保护最近2章和20000 tokens
            protect_recent_chapters=2,
            protect_recent_tokens=20000,
        )
    )


# ============================================================
# 示例4: 异步使用（高并发场景）
# ============================================================

import asyncio
from derisk.agent.shared.hierarchical_context import (
    AsyncHierarchicalContextManager,
    create_async_manager,
)


async def high_concurrency_example():
    """高并发使用示例"""
    
    # 创建异步管理器
    manager = await create_async_manager(
        max_concurrent_sessions=100,
        max_concurrent_operations=20,
    )
    
    try:
        # 并发处理多个会话
        sessions = ["session_1", "session_2", "session_3"]
        
        # 批量启动任务
        for session_id in sessions:
            await manager.start_task(session_id, f"任务 {session_id}")
        
        # 模拟记录步骤
        class MockAction:
            def __init__(self, name, content):
                self.name = name
                self.action = name
                self.content = content
                self.is_exe_success = True
        
        # 批量记录（异步无阻塞）
        for session_id in sessions:
            actions = [
                MockAction("read_file", f"读取文件...{session_id}"),
                MockAction("execute_code", f"执行代码...{session_id}"),
            ]
            await manager.record_steps_batch(session_id, actions)
        
        # 获取上下文
        for session_id in sessions:
            context = await manager.get_context_for_prompt(session_id)
            print(f"[{session_id}] Context length: {len(context)}")
        
        # 获取统计
        stats = manager.get_statistics()
        print(f"Statistics: {stats}")
        
    finally:
        await manager.shutdown()


# ============================================================
# 示例5: Core V1 集成
# ============================================================

from derisk.agent.shared.hierarchical_context import (
    HierarchicalContextMixin,
    integrate_hierarchical_context,
)


class IntegratedReActAgent(HierarchicalContextMixin, ConversableAgent):
    """
    使用Mixin集成分层上下文的Agent
    
    自动获得:
    - _start_hierarchical_task()
    - _record_hierarchical_step()
    - _get_hierarchical_context_for_prompt()
    """
    
    enable_hierarchical_context: bool = True
    memory_prompt_config: MemoryPromptConfig = Field(
        default_factory=MemoryPromptConfig
    )
    
    async def run(self, task: str):
        """运行任务"""
        # 开始分层记录
        await self._start_hierarchical_task(task)
        
        # ... 执行任务 ...
        
        # 记录步骤
        # await self._record_hierarchical_step(action_out)
        
        # 获取上下文注入到prompt
        context = self._get_hierarchical_context_for_prompt()
        
        # ... 继续处理 ...


# 或者使用装饰器方式
@integrate_hierarchical_context
class DecoratedAgent(ConversableAgent):
    enable_hierarchical_context = True


# ============================================================
# 示例6: Core V2 集成
# ============================================================

from derisk.agent.core_v2.agent_harness import AgentHarness
from derisk.agent.shared.hierarchical_context import (
    extend_agent_harness_with_hierarchical_context,
)


async def core_v2_example():
    """Core V2集成示例"""
    
    # 创建AgentHarness
    agent = MyReActAgent()
    harness = AgentHarness(agent)
    
    # 扩展分层上下文能力
    hc_integration = extend_agent_harness_with_hierarchical_context(harness)
    
    # 开始执行
    execution_id = await harness.start_execution(
        task="构建一个上下文管理系统",
    )
    
    # 分层上下文自动记录和压缩
    
    # 获取检查点数据
    checkpoint_data = hc_integration.get_checkpoint_data(execution_id)
    
    # 恢复
    # await hc_integration.restore_from_checkpoint(execution_id, checkpoint_data, file_system)


# ============================================================
# 示例7: 完整配置示例
# ============================================================

class FullyConfiguredAgent(ConversableAgent):
    """
    完全配置的Agent示例
    
    用户可以通过修改这些配置来自定义所有行为
    """
    
    # ========== 分层上下文开关 ==========
    enable_hierarchical_context: bool = True
    
    # ========== Memory Prompt配置（用户可编辑）==========
    memory_prompt_config: MemoryPromptConfig = Field(
        default_factory=lambda: create_memory_prompt_config(
            preset="chinese",  # 使用中文预设
            # 自定义覆盖
            chapter_summary_prompt="""自定义章节摘要模板...

阶段: {chapter_title}
...

请输出:
1. ...
2. ...
""",
            inject_memory_to_system=True,
            max_context_length=15000,
        )
    )
    
    # ========== 压缩配置 ==========
    hierarchical_compaction_config: HierarchicalCompactionConfig = Field(
        default_factory=lambda: HierarchicalCompactionConfig(
            enabled=True,
            strategy=CompactionStrategy.LLM_SUMMARY,
            trigger=CompactionTrigger.TOKEN_THRESHOLD,
            token_threshold=40000,
            check_interval=5,
            llm_max_tokens=500,
            llm_temperature=0.3,
            protect_recent_chapters=2,
            protect_recent_tokens=15000,
            archive_enabled=True,
            archive_to_filesystem=True,
        )
    )
    
    # ========== 上下文结构配置 ==========
    hierarchical_context_config = Field(
        default_factory=lambda: HierarchicalContextConfig(
            max_chapter_tokens=8000,
            max_section_tokens=1500,
            recent_chapters_full=2,
            middle_chapters_index=3,
            early_chapters_summary=5,
        )
    )


# ============================================================
# 运行示例
# ============================================================

if __name__ == "__main__":
    # 运行高并发示例
    asyncio.run(high_concurrency_example())
    
    print("\n" + "=" * 60)
    print("更多示例请参考 tests/test_hierarchical_context.py")
    print("=" * 60)