"""
Part系统单元测试
"""

import pytest
from datetime import datetime

from derisk.vis.parts import (
    VisPart,
    PartContainer,
    PartStatus,
    PartType,
    TextPart,
    CodePart,
    ToolUsePart,
    ThinkingPart,
    PlanPart,
)


class TestVisPart:
    """VisPart基础测试"""
    
    def test_create_text_part(self):
        """测试创建文本Part"""
        part = TextPart(content="Hello, World!")
        
        assert part.type == PartType.TEXT
        assert part.content == "Hello, World!"
        assert part.status == PartStatus.PENDING
        assert part.uid is not None
    
    def test_part_streaming(self):
        """测试Part流式输出"""
        part = TextPart.create(content="", streaming=True)
        
        assert part.is_streaming()
        
        # 追加内容
        part = part.append("Hello")
        assert part.content == "Hello"
        
        part = part.append(" World")
        assert part.content == "Hello World"
        
        # 完成
        part = part.complete()
        assert part.is_completed()
        assert part.content == "Hello World"
    
    def test_part_error(self):
        """测试Part错误状态"""
        part = TextPart.create(content="Some content")
        part = part.mark_error("Something went wrong")
        
        assert part.is_error()
        assert "Something went wrong" in part.content
    
    def test_part_metadata(self):
        """测试Part元数据"""
        part = TextPart(content="Test")
        part = part.update_metadata(author="AI", version="1.0")
        
        assert part.metadata["author"] == "AI"
        assert part.metadata["version"] == "1.0"
    
    def test_part_to_vis_dict(self):
        """测试Part转换为VIS字典"""
        part = TextPart.create(content="Test", streaming=True)
        vis_dict = part.to_vis_dict()
        
        assert vis_dict["type"] == "incr"
        assert vis_dict["status"] == "streaming"
        assert vis_dict["content"] == "Test"


class TestCodePart:
    """代码Part测试"""
    
    def test_create_code_part(self):
        """测试创建代码Part"""
        part = CodePart.create(
            code="print('hello')",
            language="python"
        )
        
        assert part.type == PartType.CODE
        assert part.content == "print('hello')"
        assert part.language == "python"
    
    def test_code_part_with_filename(self):
        """测试带文件名的代码Part"""
        part = CodePart.create(
            code="def foo(): pass",
            language="python",
            filename="test.py"
        )
        
        assert part.filename == "test.py"
        assert part.line_numbers == True


class TestToolUsePart:
    """工具使用Part测试"""
    
    def test_create_tool_part(self):
        """测试创建工具Part"""
        part = ToolUsePart.create(
            tool_name="bash",
            tool_args={"command": "ls -la"}
        )
        
        assert part.type == PartType.TOOL_USE
        assert part.tool_name == "bash"
        assert part.is_streaming()
    
    def test_tool_result(self):
        """测试工具结果"""
        part = ToolUsePart.create(
            tool_name="bash",
            tool_args={"command": "ls"},
            streaming=True
        )
        
        part = part.set_result("file1.txt\nfile2.txt", execution_time=0.5)
        
        assert part.is_completed()
        assert part.tool_result == "file1.txt\nfile2.txt"
        assert part.execution_time == 0.5
    
    def test_tool_error(self):
        """测试工具错误"""
        part = ToolUsePart.create(
            tool_name="bash",
            tool_args={"command": "invalid"},
            streaming=True
        )
        
        part = part.set_error("Command not found")
        
        assert part.is_error()
        assert "Command not found" in part.tool_error


class TestThinkingPart:
    """思考Part测试"""
    
    def test_create_thinking_part(self):
        """测试创建思考Part"""
        part = ThinkingPart.create(
            content="正在分析问题...",
            expand=True
        )
        
        assert part.type == PartType.THINKING
        assert part.expand == True
    
    def test_thinking_streaming(self):
        """测试思考流式输出"""
        part = ThinkingPart.create(content="思考", streaming=True)
        
        part = part.append("中...")
        assert part.content == "思考中..."
        
        part = part.complete()
        assert part.is_completed()


class TestPlanPart:
    """计划Part测试"""
    
    def test_create_plan_part(self):
        """测试创建计划Part"""
        items = [
            {"task": "数据收集", "status": "pending"},
            {"task": "数据分析", "status": "pending"},
        ]
        
        part = PlanPart.create(
            title="数据分析任务",
            items=items
        )
        
        assert part.type == PartType.PLAN
        assert part.title == "数据分析任务"
        assert len(part.items) == 2
    
    def test_plan_progress(self):
        """测试计划进度更新"""
        items = [
            {"task": "任务1", "status": "pending"},
            {"task": "任务2", "status": "pending"},
            {"task": "任务3", "status": "pending"},
        ]
        
        part = PlanPart.create(items=items)
        
        # 更新进度到第1项
        part = part.update_progress(0)
        assert part.items[0]["status"] == "working"
        assert part.items[1]["status"] == "pending"
        
        # 更新到第2项
        part = part.update_progress(1)
        assert part.items[0]["status"] == "completed"
        assert part.items[1]["status"] == "working"
    
    def test_plan_complete(self):
        """测试计划完成"""
        items = [
            {"task": "任务1", "status": "pending"},
            {"task": "任务2", "status": "pending"},
        ]
        
        part = PlanPart.create(items=items)
        part = part.complete_plan()
        
        assert part.is_completed()
        assert all(item["status"] == "completed" for item in part.items)


class TestPartContainer:
    """Part容器测试"""
    
    def test_add_part(self):
        """测试添加Part"""
        container = PartContainer()
        
        part1 = TextPart(content="Part 1")
        part2 = TextPart(content="Part 2")
        
        uid1 = container.add_part(part1)
        uid2 = container.add_part(part2)
        
        assert len(container) == 2
        assert uid1 == part1.uid
        assert uid2 == part2.uid
    
    def test_get_part(self):
        """测试获取Part"""
        container = PartContainer()
        part = TextPart(content="Test")
        uid = container.add_part(part)
        
        retrieved = container.get_part(uid)
        assert retrieved == part
        
        # 不存在的UID
        assert container.get_part("non-existent") is None
    
    def test_update_part(self):
        """测试更新Part"""
        container = PartContainer()
        part = TextPart.create(content="Original", streaming=True)
        uid = container.add_part(part)
        
        # 更新Part
        updated = container.update_part(
            uid,
            lambda p: p.append(" Updated")
        )
        
        assert updated.content == "Original Updated"
        assert container.get_part(uid).content == "Original Updated"
    
    def test_remove_part(self):
        """测试移除Part"""
        container = PartContainer()
        part = TextPart(content="Test")
        uid = container.add_part(part)
        
        assert container.remove_part(uid) == True
        assert len(container) == 0
        assert container.get_part(uid) is None
    
    def test_get_by_type(self):
        """测试按类型获取Part"""
        container = PartContainer()
        
        text_part = TextPart(content="Text")
        code_part = CodePart.create(code="print('test')", language="python")
        
        container.add_part(text_part)
        container.add_part(code_part)
        
        text_parts = container.get_parts_by_type(PartType.TEXT)
        assert len(text_parts) == 1
        assert text_parts[0] == text_part
        
        code_parts = container.get_parts_by_type(PartType.CODE)
        assert len(code_parts) == 1
    
    def test_get_by_status(self):
        """测试按状态获取Part"""
        container = PartContainer()
        
        pending_part = TextPart(content="Pending")
        completed_part = TextPart.create(content="Done").complete()
        
        container.add_part(pending_part)
        container.add_part(completed_part)
        
        pending_parts = container.get_parts_by_status(PartStatus.PENDING)
        assert len(pending_parts) == 1
        
        completed_parts = container.get_parts_by_status(PartStatus.COMPLETED)
        assert len(completed_parts) == 1
    
    def test_iteration(self):
        """测试迭代"""
        container = PartContainer()
        
        parts = [
            TextPart(content="Part 1"),
            TextPart(content="Part 2"),
            TextPart(content="Part 3"),
        ]
        
        for part in parts:
            container.add_part(part)
        
        # 测试迭代
        count = 0
        for part in container:
            count += 1
        
        assert count == 3
        
        # 测试索引访问
        assert container[0] == parts[0]
        assert container[1] == parts[1]
    
    def test_to_list(self):
        """测试转换为列表"""
        container = PartContainer()
        
        part1 = TextPart(content="Part 1")
        part2 = TextPart(content="Part 2")
        
        container.add_part(part1)
        container.add_part(part2)
        
        parts_list = container.to_list()
        
        assert len(parts_list) == 2
        assert parts_list[0]["content"] == "Part 1"
        assert parts_list[1]["content"] == "Part 2"