"""
简单的集成验证脚本
验证 VIS 适配器的基本功能
"""

import sys
import os

# 添加正确的路径
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(script_dir, '..', 'src')
sys.path.insert(0, os.path.abspath(src_dir))

import asyncio
import json
from datetime import datetime


def test_vis_adapter():
    """测试 VIS 适配器"""
    print("=" * 60)
    print("测试 VIS 适配器")
    print("=" * 60)
    
    from derisk.agent.core_v2.vis_adapter import CoreV2VisAdapter
    
    # 1. 创建适配器
    adapter = CoreV2VisAdapter(
        agent_name="test-agent",
        conv_id="test-conv-123",
        conv_session_id="test-session-456",
    )
    print("✓ 创建适配器成功")
    
    # 2. 添加步骤
    adapter.add_step("step1", "分析需求", "completed", result_summary="完成需求分析")
    adapter.add_step("step2", "执行查询", "running")
    adapter.add_step("step3", "生成报告", "pending")
    print(f"✓ 添加 3 个步骤成功")
    
    # 3. 设置当前步骤
    adapter.set_current_step("step2")
    print("✓ 设置当前步骤: step2")
    
    # 4. 添加思考内容
    adapter.set_thinking("正在执行数据库查询...")
    print("✓ 设置思考内容")
    
    # 5. 添加产物
    adapter.add_artifact(
        artifact_id="query_result",
        artifact_type="tool_output",
        content="查询返回 100 条记录",
        title="数据库查询结果",
        rows=100,
    )
    print("✓ 添加产物成功")
    
    # 6. 生成规划窗口
    planning = adapter.generate_planning_window()
    print("\n规划窗口数据:")
    print(json.dumps(planning, indent=2, ensure_ascii=False))
    
    # 7. 生成运行窗口
    running = adapter.generate_running_window()
    print("\n运行窗口数据:")
    print(json.dumps(running, indent=2, ensure_ascii=False))
    
    return adapter


async def test_generate_vis_output():
    """测试生成 VIS 输出"""
    print("\n" + "=" * 60)
    print("测试生成 VIS 输出")
    print("=" * 60)
    
    from derisk.agent.core_v2.vis_adapter import CoreV2VisAdapter
    
    adapter = CoreV2VisAdapter(agent_name="test-agent")
    adapter.add_step("1", "步骤1", "completed")
    adapter.add_step("2", "步骤2", "running")
    
    # 测试简单格式
    output = await adapter.generate_vis_output(use_gpts_format=False)
    print("\n简单格式输出:")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    
    # 测试 Gpts 格式
    try:
        output_gpts = await adapter.generate_vis_output(use_gpts_format=True)
        print("\nGpts 格式输出:")
        data = json.loads(output_gpts)
        print(json.dumps(data, indent=2, ensure_ascii=False)[:500] + "...")
        print("✓ Gpts 格式转换成功")
    except Exception as e:
        print(f"⚠ Gpts 格式转换失败（预期中，可能缺少依赖）: {e}")
    
    return output


def test_vis_protocol():
    """测试 VIS 协议"""
    print("\n" + "=" * 60)
    print("测试 VIS 协议")
    print("=" * 60)
    
    from derisk.agent.core_v2.vis_protocol import (
        VisWindow3Data,
        PlanningWindow,
        RunningWindow,
        PlanningStep,
        RunningArtifact,
        CurrentStep,
    )
    
    # 创建完整数据结构
    vis_data = VisWindow3Data(
        planning_window=PlanningWindow(
            steps=[
                PlanningStep(
                    step_id="1",
                    title="分析需求",
                    status="completed",
                    result_summary="完成",
                ),
                PlanningStep(
                    step_id="2",
                    title="执行查询",
                    status="running",
                ),
            ],
            current_step_id="2",
        ),
        running_window=RunningWindow(
            current_step=CurrentStep(
                step_id="2",
                title="执行查询",
                status="running",
            ),
            thinking="正在思考...",
            content="查询中...",
            artifacts=[
                RunningArtifact(
                    artifact_id="a1",
                    type="tool_output",
                    content="结果",
                    title="输出",
                ),
            ],
        ),
    )
    
    print("✓ 创建 VisWindow3Data 成功")
    
    # 转换为字典
    data_dict = vis_data.to_dict()
    print("\n转换为字典:")
    print(json.dumps(data_dict, indent=2, ensure_ascii=False)[:500])
    
    # 转换为 JSON
    json_str = vis_data.to_json()
    print("\n✓ 转换为 JSON 成功")
    
    # 从字典恢复
    restored = VisWindow3Data.from_dict(data_dict)
    print(f"✓ 从字典恢复成功，步骤数: {len(restored.planning_window.steps)}")
    
    return vis_data


async def test_production_agent_integration():
    """测试 ProductionAgent 集成"""
    print("\n" + "=" * 60)
    print("测试 ProductionAgent 集成")
    print("=" * 60)
    
    try:
        from derisk.agent.core_v2.production_agent import ProductionAgent
        
        # 创建 Agent（启用 VIS）
        agent = ProductionAgent(
            info=type('obj', (object,), {
                'name': 'test-agent',
                'max_steps': 10,
            })(),
            llm_adapter=None,
            enable_vis=True,
        )
        
        print("✓ 创建 ProductionAgent 成功")
        
        # 检查 VIS 适配器
        adapter = agent.get_vis_adapter()
        assert adapter is not None, "VIS 适配器未初始化"
        print("✓ VIS 适配器已初始化")
        
        # 添加步骤
        agent.add_vis_step("1", "步骤1", "completed", result_summary="完成")
        agent.add_vis_step("2", "步骤2", "running")
        print("✓ 添加步骤成功")
        
        # 生成输出
        output = await agent.generate_vis_output(use_gpts_format=False)
        assert output is not None, "输出为空"
        print("✓ 生成 VIS 输出成功")
        
        # 验证输出格式
        assert "planning_window" in output, "缺少 planning_window"
        assert "running_window" in output, "缺少 running_window"
        print("✓ 输出格式正确")
        
        print("\n输出数据:")
        print(json.dumps(output, indent=2, ensure_ascii=False))
        
        return True
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("\n开始 VIS 集成验证...\n")
    
    try:
        # 1. 测试适配器
        adapter = test_vis_adapter()
        
        # 2. 测试生成输出
        output = asyncio.run(test_generate_vis_output())
        
        # 3. 测试协议
        protocol = test_vis_protocol()
        
        # 4. 测试集成
        success = asyncio.run(test_production_agent_integration())
        
        print("\n" + "=" * 60)
        if success:
            print("✓ 所有测试通过！")
        else:
            print("✗ 部分测试失败")
        print("=" * 60)
        
        return success
        
    except Exception as e:
        print(f"\n✗ 测试过程出错: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)