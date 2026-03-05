"""
Core V2 VIS Adapter 测试

测试 VIS 适配器的功能
"""

import pytest
import json
from datetime import datetime

from derisk.agent.core_v2.vis_adapter import CoreV2VisAdapter, VisStep, VisArtifact
from derisk.agent.core_v2.vis_protocol import (
    VisWindow3Data,
    PlanningWindow,
    RunningWindow,
    PlanningStep,
    StepStatus,
)


class TestVisAdapter:
    """VIS 适配器测试"""
    
    def test_init(self):
        """测试初始化"""
        adapter = CoreV2VisAdapter(
            agent_name="test-agent",
            conv_id="test-conv",
            conv_session_id="test-session",
        )
        
        assert adapter.agent_name == "test-agent"
        assert adapter.conv_id == "test-conv"
        assert adapter.conv_session_id == "test-session"
        assert len(adapter.steps) == 0
        assert len(adapter.artifacts) == 0
    
    def test_add_step(self):
        """测试添加步骤"""
        adapter = CoreV2VisAdapter()
        
        step = adapter.add_step(
            step_id="step1",
            title="分析需求",
            status="pending",
        )
        
        assert step.step_id == "step1"
        assert step.title == "分析需求"
        assert step.status == "pending"
        assert "step1" in adapter.steps
        assert "step1" in adapter.step_order
    
    def test_update_step(self):
        """测试更新步骤"""
        adapter = CoreV2VisAdapter()
        adapter.add_step("step1", "分析需求", "running")
        
        updated = adapter.update_step(
            step_id="step1",
            status="completed",
            result_summary="完成分析",
        )
        
        assert updated is not None
        assert updated.status == "completed"
        assert updated.result_summary == "完成分析"
        assert updated.end_time is not None
    
    def test_update_nonexistent_step(self):
        """测试更新不存在的步骤"""
        adapter = CoreV2VisAdapter()
        
        result = adapter.update_step("nonexistent", status="completed")
        
        assert result is None
    
    def test_set_current_step(self):
        """测试设置当前步骤"""
        adapter = CoreV2VisAdapter()
        adapter.add_step("step1", "Step 1")
        
        adapter.set_current_step("step1")
        
        assert adapter.current_step_id == "step1"
    
    def test_add_artifact(self):
        """测试添加产物"""
        adapter = CoreV2VisAdapter()
        
        adapter.add_artifact(
            artifact_id="artifact1",
            artifact_type="tool_output",
            content="Query result",
            title="数据库查询",
            size=1024,
        )
        
        assert len(adapter.artifacts) == 1
        artifact = adapter.artifacts[0]
        assert artifact.artifact_id == "artifact1"
        assert artifact.artifact_type == "tool_output"
        assert artifact.title == "数据库查询"
        assert artifact.metadata["size"] == 1024
    
    def test_set_thinking_and_content(self):
        """测试设置思考和内容"""
        adapter = CoreV2VisAdapter()
        
        adapter.set_thinking("正在思考...")
        adapter.set_content("最终结果")
        
        assert adapter.thinking_content == "正在思考..."
        assert adapter.content == "最终结果"
    
    def test_generate_planning_window(self):
        """测试生成规划窗口"""
        adapter = CoreV2VisAdapter()
        adapter.add_step("1", "步骤1", "completed", result_summary="完成")
        adapter.add_step("2", "步骤2", "running")
        adapter.set_current_step("2")
        
        planning = adapter.generate_planning_window()
        
        assert len(planning["steps"]) == 2
        assert planning["current_step_id"] == "2"
        assert planning["steps"][0]["status"] == "completed"
        assert planning["steps"][1]["status"] == "running"
    
    def test_generate_running_window(self):
        """测试生成运行窗口"""
        adapter = CoreV2VisAdapter()
        adapter.add_step("1", "步骤1", "running")
        adapter.set_current_step("1")
        adapter.set_thinking("思考中...")
        adapter.set_content("结果内容")
        adapter.add_artifact("a1", "code", "print('hello')")
        
        running = adapter.generate_running_window()
        
        assert running["current_step"]["step_id"] == "1"
        assert running["thinking"] == "思考中..."
        assert running["content"] == "结果内容"
        assert len(running["artifacts"]) == 1
    
    def test_generate_running_window_no_current_step(self):
        """测试没有当前步骤时的运行窗口"""
        adapter = CoreV2VisAdapter()
        
        running = adapter.generate_running_window()
        
        assert running["current_step"] is None
        assert running["thinking"] is None
        assert running["content"] is None
        assert len(running["artifacts"]) == 0
    
    @pytest.mark.asyncio
    async def test_generate_vis_output_simple(self):
        """测试生成简单 VIS 输出"""
        adapter = CoreV2VisAdapter()
        adapter.add_step("1", "步骤1", "completed")
        
        output = await adapter.generate_vis_output(use_gpts_format=False)
        
        assert output is not None
        assert "planning_window" in output
        assert "running_window" in output
    
    @pytest.mark.asyncio
    async def test_generate_vis_output_gpts_format(self):
        """测试生成 Gpts 格式的 VIS 输出"""
        adapter = CoreV2VisAdapter()
        adapter.add_step("1", "步骤1", "completed", result_summary="完成")
        
        output = await adapter.generate_vis_output(use_gpts_format=True)
        
        assert output is not None
        data = json.loads(output)
        assert "planning_window" in data
        assert "running_window" in data
    
    def test_steps_to_gpts_messages(self):
        """测试转换步骤为 GptsMessage"""
        adapter = CoreV2VisAdapter()
        adapter.add_step("1", "分析需求", "completed", result_summary="完成分析")
        adapter.add_step("2", "执行查询", "running")
        
        messages = adapter._steps_to_gpts_messages()
        
        assert len(messages) == 2
        assert messages[0].sender_name == adapter.agent_name
        assert len(messages[0].action_report) > 0
    
    def test_map_status(self):
        """测试状态映射"""
        adapter = CoreV2VisAdapter()
        
        assert adapter._map_status("pending") == "WAITING"
        assert adapter._map_status("running") == "RUNNING"
        assert adapter._map_status("completed") == "COMPLETE"
        assert adapter._map_status("failed") == "FAILED"
        assert adapter._map_status("unknown") == "WAITING"
    
    def test_clear(self):
        """测试清空数据"""
        adapter = CoreV2VisAdapter()
        adapter.add_step("1", "Step 1")
        adapter.add_artifact("a1", "type", "content")
        adapter.set_thinking("thinking")
        adapter.set_current_step("1")
        
        adapter.clear()
        
        assert len(adapter.steps) == 0
        assert len(adapter.step_order) == 0
        assert len(adapter.artifacts) == 0
        assert adapter.current_step_id is None
        assert adapter.thinking_content is None
        assert adapter.content is None


class TestVisProtocol:
    """VIS 协议测试"""
    
    def test_planning_step_to_dict(self):
        """测试规划步骤转换"""
        step = PlanningStep(
            step_id="1",
            title="分析需求",
            status=StepStatus.COMPLETED.value,
            result_summary="完成",
        )
        
        data = step.to_dict()
        
        assert data["step_id"] == "1"
        assert data["title"] == "分析需求"
        assert data["status"] == "completed"
        assert data["result_summary"] == "完成"
    
    def test_planning_step_from_dict(self):
        """测试从字典创建规划步骤"""
        data = {
            "step_id": "1",
            "title": "分析需求",
            "status": "completed",
            "result_summary": "完成",
        }
        
        step = PlanningStep.from_dict(data)
        
        assert step.step_id == "1"
        assert step.title == "分析需求"
        assert step.status == "completed"
    
    def test_planning_window_to_dict(self):
        """测试规划窗口转换"""
        window = PlanningWindow(
            steps=[
                PlanningStep(step_id="1", title="Step 1"),
                PlanningStep(step_id="2", title="Step 2"),
            ],
            current_step_id="2",
        )
        
        data = window.to_dict()
        
        assert len(data["steps"]) == 2
        assert data["current_step_id"] == "2"
    
    def test_running_window_to_dict(self):
        """测试运行窗口转换"""
        from derisk.agent.core_v2.vis_protocol import CurrentStep, RunningArtifact
        
        window = RunningWindow(
            current_step=CurrentStep(step_id="1", title="Step 1", status="running"),
            thinking="思考中...",
            content="内容",
            artifacts=[
                RunningArtifact(artifact_id="a1", type="code", content="code"),
            ],
        )
        
        data = window.to_dict()
        
        assert data["current_step"]["step_id"] == "1"
        assert data["thinking"] == "思考中..."
        assert len(data["artifacts"]) == 1
    
    def test_vis_window3_data_roundtrip(self):
        """测试完整数据结构的往返转换"""
        original = VisWindow3Data(
            planning_window=PlanningWindow(
                steps=[
                    PlanningStep(step_id="1", title="Step 1", status="completed"),
                ]
            ),
            running_window=RunningWindow(
                thinking="thinking",
                content="content",
            ),
        )
        
        data = original.to_dict()
        restored = VisWindow3Data.from_dict(data)
        
        assert len(restored.planning_window.steps) == 1
        assert restored.running_window.thinking == "thinking"
        assert restored.running_window.content == "content"
    
    def test_vis_window3_to_json(self):
        """测试转换为 JSON"""
        data = VisWindow3Data(
            planning_window=PlanningWindow(
                steps=[PlanningStep(step_id="1", title="Test")]
            )
        )
        
        json_str = data.to_json()
        
        assert json_str is not None
        parsed = json.loads(json_str)
        assert "planning_window" in parsed


class TestProductionAgentIntegration:
    """ProductionAgent 集成测试"""
    
    @pytest.mark.asyncio
    async def test_agent_vis_integration(self):
        """测试 Agent VIS 集成"""
        from derisk.agent.core_v2.production_agent import ProductionAgent
        
        agent = ProductionAgent.create(
            name="test-agent",
            enable_vis=True,
        )
        
        assert agent.get_vis_adapter() is not None
        
        agent.add_vis_step("1", "步骤1", "completed", result_summary="完成")
        agent.add_vis_step("2", "步骤2", "running")
        
        vis_output = await agent.generate_vis_output(use_gpts_format=False)
        
        assert vis_output is not None
        assert "planning_window" in vis_output
        assert len(vis_output["planning_window"]["steps"]) == 2
    
    @pytest.mark.asyncio
    async def test_agent_without_vis(self):
        """测试未启用 VIS 的 Agent"""
        from derisk.agent.core_v2.production_agent import ProductionAgent
        
        agent = ProductionAgent.create(
            name="test-agent",
            enable_vis=False,
        )
        
        assert agent.get_vis_adapter() is None
        
        vis_output = await agent.generate_vis_output()
        
        assert vis_output is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])