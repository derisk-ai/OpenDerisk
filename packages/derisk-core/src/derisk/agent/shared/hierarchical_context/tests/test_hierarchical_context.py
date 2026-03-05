"""
分层上下文索引系统 - 测试用例

测试章节索引、优先级分类、回溯工具等核心功能。
"""

import asyncio
from typing import Dict, Any

from derisk.agent.shared.hierarchical_context import (
    ChapterIndexer,
    ContentPrioritizer,
    ContentPriority,
    TaskPhase,
    HierarchicalContextConfig,
    PhaseTransitionDetector,
    RecallToolManager,
)


class MockActionOutput:
    """模拟 ActionOutput"""
    
    def __init__(
        self,
        name: str = "test_action",
        content: str = "test content",
        is_exe_success: bool = True,
    ):
        self.name = name
        self.action = name
        self.content = content
        self.is_exe_success = is_exe_success


class MockAgentFileSystem:
    """模拟 AgentFileSystem"""
    
    def __init__(self):
        self._files: Dict[str, str] = {}
    
    async def save_file(
        self,
        file_key: str,
        data: str,
        file_type: Any = None,
        metadata: Dict[str, Any] = None,
    ) -> Any:
        self._files[file_key] = data
        return type("FileMetadata", (), {
            "file_id": file_key,
            "file_name": file_key.split("/")[-1],
        })()
    
    async def read_file(self, file_key: str) -> str:
        return self._files.get(file_key, "")


async def test_chapter_indexer():
    """测试章节索引器"""
    print("\n" + "=" * 60)
    print("测试 ChapterIndexer")
    print("=" * 60)
    
    indexer = ChapterIndexer()
    
    # 1. 创建章节
    chapter1 = indexer.create_chapter(
        phase=TaskPhase.EXPLORATION,
        title="需求分析",
        description="分析用户需求，探索解决方案",
    )
    print(f"\n创建章节: {chapter1.chapter_id}")
    
    # 2. 添加节
    section1 = await indexer.add_section(
        step_name="read_requirements",
        content="读取需求文档，理解用户目标：构建一个上下文管理系统，支持长任务执行...",
        priority=ContentPriority.HIGH,
    )
    print(f"添加节: {section1.section_id}")
    
    section2 = await indexer.add_section(
        step_name="search_references",
        content="搜索相关项目：OpenCode, OpenClaw, LangChain...",
        priority=ContentPriority.MEDIUM,
    )
    print(f"添加节: {section2.section_id}")
    
    # 3. 创建第二个章节
    chapter2 = indexer.create_chapter(
        phase=TaskPhase.DEVELOPMENT,
        title="系统开发",
        description="实现分层上下文索引系统",
    )
    print(f"\n创建章节: {chapter2.chapter_id}")
    
    await indexer.add_section(
        step_name="design_indexer",
        content="设计 ChapterIndexer 数据结构和接口...",
        priority=ContentPriority.CRITICAL,
    )
    
    await indexer.add_section(
        step_name="implement_prioritizer",
        content="实现 ContentPrioritizer 优先级分类逻辑...",
        priority=ContentPriority.HIGH,
    )
    
    # 4. 获取统计
    stats = indexer.get_statistics()
    print(f"\n统计信息:")
    print(f"  总章节数: {stats['total_chapters']}")
    print(f"  总节数: {stats['total_sections']}")
    print(f"  总Tokens: {stats['total_tokens']}")
    print(f"  当前阶段: {stats['current_phase']}")
    
    # 5. 生成上下文
    context = indexer.get_context_for_prompt(token_budget=5000)
    print(f"\n生成的上下文 (前500字符):")
    print(context[:500] + "...")
    
    return indexer


async def test_content_prioritizer():
    """测试内容优先级分类器"""
    print("\n" + "=" * 60)
    print("测试 ContentPrioritizer")
    print("=" * 60)
    
    prioritizer = ContentPrioritizer()
    
    # 测试不同类型的消息
    test_cases = [
        ("make_decision", "决定使用分层索引架构", True),
        ("execute_code", "成功执行代码，输出结果正确", True),
        ("read_file", "读取文件内容", True),
        ("retry", "重试第3次，仍然失败", False),
    ]
    
    for action_name, content, success in test_cases:
        action_out = MockActionOutput(
            name=action_name,
            content=content,
            is_exe_success=success,
        )
        
        priority = prioritizer.classify_message_from_action(action_out)
        factor = prioritizer.get_compression_factor(priority)
        
        print(f"\n动作: {action_name}")
        print(f"内容: {content[:50]}...")
        print(f"优先级: {priority.value}")
        print(f"压缩因子: {factor:.0%}")


async def test_phase_detector():
    """测试阶段检测器"""
    print("\n" + "=" * 60)
    print("测试 PhaseTransitionDetector")
    print("=" * 60)
    
    detector = PhaseTransitionDetector()
    
    # 模拟探索阶段
    actions_exploration = [
        MockActionOutput(name="read_file", content="读取需求文档..."),
        MockActionOutput(name="search", content="搜索相关项目..."),
        MockActionOutput(name="explore", content="探索架构..."),
    ]
    
    for action in actions_exploration:
        new_phase = detector.detect_phase(action)
        if new_phase:
            print(f"阶段转换: {new_phase.value}")
    
    print(f"当前阶段: {detector.get_current_phase().value}")
    
    # 模拟开发阶段
    actions_development = [
        MockActionOutput(name="write_file", content="编写代码实现..."),
        MockActionOutput(name="execute_code", content="执行代码..."),
    ]
    
    for action in actions_development:
        new_phase = detector.detect_phase(action)
        if new_phase:
            print(f"阶段转换: {new_phase.value}")
    
    print(f"当前阶段: {detector.get_current_phase().value}")


async def test_recall_tool_manager():
    """测试回溯工具管理器"""
    print("\n" + "=" * 60)
    print("测试 RecallToolManager")
    print("=" * 60)
    
    # 创建带文件系统的索引器
    file_system = MockAgentFileSystem()
    indexer = ChapterIndexer(file_system=file_system)
    
    # 创建章节并添加长内容（触发归档）
    indexer.create_chapter(
        phase=TaskPhase.EXPLORATION,
        title="需求分析",
        description="分析用户需求",
    )
    
    # 添加一个长内容（超过 max_section_tokens）
    long_content = "这是需要归档的长内容。" * 1000
    section = await indexer.add_section(
        step_name="long_analysis",
        content=long_content,
        priority=ContentPriority.HIGH,
    )
    
    print(f"\n添加了需要归档的节: {section.section_id}")
    print(f"归档引用: {section.detail_ref}")
    
    # 创建回溯工具管理器
    recall_manager = RecallToolManager(
        chapter_indexer=indexer,
        file_system=file_system,
    )
    
    # 检查是否应该注入工具
    should_inject = recall_manager.should_inject_tools()
    print(f"\n是否应该注入回溯工具: {should_inject}")
    
    if should_inject:
        tools = recall_manager.get_tools()
        print(f"注入的工具数量: {len(tools)}")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description[:50]}...")


async def test_long_running_task():
    """测试长任务场景"""
    print("\n" + "=" * 60)
    print("测试长任务场景 (模拟100轮对话)")
    print("=" * 60)
    
    indexer = ChapterIndexer()
    prioritizer = ContentPrioritizer()
    detector = PhaseTransitionDetector()
    
    phases = [
        (TaskPhase.EXPLORATION, "探索阶段", 15),
        (TaskPhase.DEVELOPMENT, "开发阶段", 40),
        (TaskPhase.DEBUGGING, "调试阶段", 20),
        (TaskPhase.REFINEMENT, "优化阶段", 15),
        (TaskPhase.DELIVERY, "收尾阶段", 10),
    ]
    
    step_count = 0
    
    for phase, phase_name, num_steps in phases:
        indexer.create_chapter(phase=phase, title=phase_name)
        
        for i in range(num_steps):
            step_count += 1
            
            if i % 5 == 0:
                step_name = "critical_decision"
                content = f"关键决策{step_count}: 确定架构方案..."
                priority = ContentPriority.CRITICAL
            elif i % 3 == 0:
                step_name = "execute_task"
                content = f"执行任务{step_count}: 实现功能..."
                priority = ContentPriority.HIGH
            else:
                step_name = "read_info"
                content = f"读取信息{step_count}: 查看文档..."
                priority = ContentPriority.MEDIUM
            
            await indexer.add_section(
                step_name=step_name,
                content=content,
                priority=priority,
            )
    
    # 生成最终上下文
    context = indexer.get_context_for_prompt(token_budget=8000)
    
    print(f"\n最终统计:")
    stats = indexer.get_statistics()
    print(f"  总章节: {stats['total_chapters']}")
    print(f"  总节: {stats['total_sections']}")
    print(f"  总Tokens: {stats['total_tokens']}")
    
    print(f"\n优先级分布:")
    for priority, count in stats['priority_distribution'].items():
        print(f"  {priority}: {count}")
    
    print(f"\n阶段分布:")
    for phase, phase_stats in stats['phases'].items():
        print(f"  {phase}: {phase_stats['sections']} 节, {phase_stats['tokens']} tokens")
    
    print(f"\n生成的上下文长度: {len(context)} 字符")


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("分层上下文索引系统 - 测试")
    print("=" * 60)
    
    await test_chapter_indexer()
    await test_content_prioritizer()
    await test_phase_detector()
    await test_recall_tool_manager()
    await test_long_running_task()
    
    print("\n" + "=" * 60)
    print("所有测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())