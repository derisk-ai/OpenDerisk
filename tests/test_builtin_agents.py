"""
CoreV2 Built-in Agents 测试示例

演示三种内置Agent的使用方法
"""

import asyncio
import os
from derisk.agent.core_v2.builtin_agents import (
    ReActReasoningAgent,
    FileExplorerAgent,
    CodingAgent,
    create_agent,
    create_agent_from_config,
)


async def test_react_reasoning_agent():
    """测试ReAct推理Agent"""
    print("=" * 60)
    print("测试 1: ReActReasoningAgent")
    print("=" * 60)
    
    # 创建Agent
    agent = ReActReasoningAgent.create(
        name="test-reasoning-agent",
        model="gpt-4",
        max_steps=20,
        enable_doom_loop_detection=True,
        enable_output_truncation=True
    )
    
    print(f"Agent创建成功: {agent.info.name}")
    print(f"最大步数: {agent.info.max_steps}")
    print(f"默认工具: {agent.default_tools}")
    
    # 执行简单任务（示例，需要API Key才能运行）
    if os.getenv("OPENAI_API_KEY"):
        print("\n开始执行任务: '列出当前目录的文件'")
        async for chunk in agent.run("列出当前目录的文件"):
            print(chunk, end="", flush=True)
        print("\n")
        
        # 获取统计
        stats = agent.get_statistics()
        print(f"执行统计: {stats}")
    else:
        print("\n跳过实际执行（未设置OPENAI_API_KEY）")


async def test_file_explorer_agent():
    """测试文件探索Agent"""
    print("\n" + "=" * 60)
    print("测试 2: FileExplorerAgent")
    print("=" * 60)
    
    # 创建Agent
    agent = FileExplorerAgent.create(
        name="test-explorer-agent",
        project_path="./",
        enable_auto_exploration=True
    )
    
    print(f"Agent创建成功: {agent.info.name}")
    print(f"项目路径: {agent.project_path}")
    print(f"默认工具: {agent.default_tools}")
    
    # 探索项目
    if os.getenv("OPENAI_API_KEY"):
        print("\n开始探索项目...")
        structure = await agent.explore_project()
        
        print(f"项目类型: {structure.get('project_type')}")
        print(f"关键文件数量: {len(structure.get('key_files', []))}")
        
        if structure.get("summary"):
            print(f"项目摘要:\n{structure['summary']}")
    else:
        print("\n跳过实际探索（未设置OPENAI_API_KEY）")


async def test_coding_agent():
    """测试编程Agent"""
    print("\n" + "=" * 60)
    print("测试 3: CodingAgent")
    print("=" * 60)
    
    # 创建Agent
    agent = CodingAgent.create(
        name="test-coding-agent",
        workspace_path="./",
        enable_auto_exploration=True,
        enable_code_quality_check=True
    )
    
    print(f"Agent创建成功: {agent.info.name}")
    print(f"工作目录: {agent.workspace_path}")
    print(f"默认工具: {agent.default_tools}")
    print(f"代码规范:")
    for rule in agent.code_style_rules:
        print(f"  - {rule}")
    
    # 探索代码库
    if os.getenv("OPENAI_API_KEY"):
        print("\n开始探索代码库...")
        codebase_info = await agent.explore_codebase()
        
        print(f"项目类型: {codebase_info.get('project_type')}")
        print(f"关键文件数量: {len(codebase_info.get('key_files', []))}")
        print(f"依赖数量: {len(codebase_info.get('dependencies', []))}")
    else:
        print("\n跳过实际探索（未设置OPENAI_API_KEY）")


async def test_agent_factory():
    """测试Agent工厂"""
    print("\n" + "=" * 60)
    print("测试 4: AgentFactory")
    print("=" * 60)
    
    # 使用工厂创建Agent
    agent = create_agent(
        agent_type="react_reasoning",
        name="factory-created-agent",
        model="gpt-4"
    )
    
    print(f"工厂创建成功: {agent.info.name}")
    print(f"Agent类型: {type(agent).__name__}")


async def test_config_loader():
    """测试配置加载器"""
    print("\n" + "=" * 60)
    print("测试 5: Config Loader")
    print("=" * 60)
    
    config_path = "configs/agents/react_reasoning_agent.yaml"
    
    if os.path.exists(config_path):
        print(f"配置文件存在: {config_path}")
        
        if os.getenv("OPENAI_API_KEY"):
            agent = create_agent_from_config(config_path)
            print(f"从配置创建成功: {agent.info.name}")
        else:
            print("跳过实际创建（未设置OPENAI_API_KEY）")
    else:
        print(f"配置文件不存在: {config_path}")


async def test_react_components():
    """测试ReAct组件"""
    print("\n" + "=" * 60)
    print("测试 6: ReAct Components")
    print("=" * 60)
    
    from derisk.agent.core_v2.builtin_agents.react_components import (
        DoomLoopDetector,
        OutputTruncator,
        ContextCompactor,
        HistoryPruner,
    )
    
    # 测试末日循环检测器
    detector = DoomLoopDetector(threshold=3)
    
    # 模拟重复调用
    for i in range(4):
        detector.record_call("test_tool", {"param": "value"})
    
    result = detector.check_doom_loop()
    print(f"末日循环检测: is_doom_loop={result.is_doom_loop}")
    
    # 测试输出截断器
    truncator = OutputTruncator(max_lines=10, max_bytes=1000)
    
    large_content = "\n".join([f"Line {i}" for i in range(100)])
    truncation_result = truncator.truncate(large_content, tool_name="test")
    
    print(f"输出截断: is_truncated={truncation_result.is_truncated}")
    print(f"原始行数: {truncation_result.original_lines}")
    print(f"截断后行数: {truncation_result.truncated_lines}")
    
    # 测试上下文压缩器
    compactor = ContextCompactor(max_tokens=1000)
    
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    
    compaction_result = compactor.compact(messages)
    print(f"上下文压缩: compact_needed={compaction_result.compact_needed}")
    
    # 测试历史修剪器
    pruner = HistoryPruner(max_tool_outputs=5)
    
    messages_with_tools = [
        {"role": "user", "content": "Run command"},
        {"role": "assistant", "content": "工具 bash 执行结果: ..."},
    ] * 10
    
    prune_result = pruner.prune(messages_with_tools)
    print(f"历史修剪: prune_needed={prune_result.prune_needed}")
    print(f"移除消息数: {prune_result.messages_removed}")


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("CoreV2 Built-in Agents 测试套件")
    print("=" * 60)
    
    # 运行所有测试
    await test_react_reasoning_agent()
    await test_file_explorer_agent()
    await test_coding_agent()
    await test_agent_factory()
    await test_config_loader()
    await test_react_components()
    
    print("\n" + "=" * 60)
    print("所有测试完成")
    print("=" * 60)
    
    if not os.getenv("OPENAI_API_KEY"):
        print("\n提示: 设置OPENAI_API_KEY环境变量以运行完整测试")
        print("export OPENAI_API_KEY='your-api-key'")


if __name__ == "__main__":
    asyncio.run(main())