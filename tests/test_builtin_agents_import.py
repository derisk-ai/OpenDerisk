#!/usr/bin/env python3
"""
测试脚本 - 验证内置Agent导入是否正常
"""

print("=" * 60)
print("测试开始：验证内置Agent导入")
print("=" * 60)

# 测试1: 导入BaseBuiltinAgent
print("\n[测试1] 导入 BaseBuiltinAgent...")
try:
    from derisk.agent.core_v2.builtin_agents.base_builtin_agent import BaseBuiltinAgent
    print("✅ BaseBuiltinAgent 导入成功")
except Exception as e:
    print(f"❌ BaseBuiltinAgent 导入失败: {e}")

# 测试2: 导入ReActReasoningAgent
print("\n[测试2] 导入 ReActReasoningAgent...")
try:
    from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent
    print("✅ ReActReasoningAgent 导入成功")
except Exception as e:
    print(f"❌ ReActReasoningAgent 导入失败: {e}")

# 测试3: 导入FileExplorerAgent
print("\n[测试3] 导入 FileExplorerAgent...")
try:
    from derisk.agent.core_v2.builtin_agents import FileExplorerAgent
    print("✅ FileExplorerAgent 导入成功")
except Exception as e:
    print(f"❌ FileExplorerAgent 导入失败: {e}")

# 测试4: 导入CodingAgent
print("\n[测试4] 导入 CodingAgent...")
try:
    from derisk.agent.core_v2.builtin_agents import CodingAgent
    print("✅ CodingAgent 导入成功")
except Exception as e:
    print(f"❌ CodingAgent 导入失败: {e}")

# 测试5: 导入Agent工厂
print("\n[测试5] 导入 AgentFactory...")
try:
    from derisk.agent.core_v2.builtin_agents import AgentFactory, create_agent
    print("✅ AgentFactory 和 create_agent 导入成功")
except Exception as e:
    print(f"❌ AgentFactory 导入失败: {e}")

# 测试6: 导入ReAct组件
print("\n[测试6] 导入 ReAct组件...")
try:
    from derisk.agent.core_v2.builtin_agents.react_components import (
        DoomLoopDetector,
        OutputTruncator,
        ContextCompactor,
        HistoryPruner,
    )
    print("✅ ReAct组件导入成功")
    print(f"  - DoomLoopDetector: {DoomLoopDetector}")
    print(f"  - OutputTruncator: {OutputTruncator}")
    print(f"  - ContextCompactor: {ContextCompactor}")
    print(f"  - HistoryPruner: {HistoryPruner}")
except Exception as e:
    print(f"❌ ReAct组件导入失败: {e}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)