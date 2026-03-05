"""
WorkLog 转换单元测试

测试 WorkLog 阶段分组和 Section 转换逻辑
"""

import pytest
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, MagicMock

from derisk.context.unified_context_middleware import UnifiedContextMiddleware
from derisk.agent.shared.hierarchical_context import TaskPhase, ContentPriority


@dataclass
class MockWorkEntry:
    """模拟 WorkEntry"""
    timestamp: float
    tool: str
    args: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    result: Optional[str] = None
    success: bool = True
    tags: List[str] = field(default_factory=list)
    tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MockMessage:
    """模拟消息"""
    role: str
    content: str


class MockGptsMemory:
    """模拟 GptsMemory"""
    
    def __init__(self):
        self._messages: Dict[str, List[MockMessage]] = {}
        self._worklog: Dict[str, List[MockWorkEntry]] = {}
    
    async def get_messages(self, conv_id: str) -> List[MockMessage]:
        return self._messages.get(conv_id, [])
    
    async def get_work_log(self, conv_id: str) -> List[MockWorkEntry]:
        return self._worklog.get(conv_id, [])
    
    def set_messages(self, conv_id: str, messages: List[MockMessage]):
        self._messages[conv_id] = messages
    
    def set_worklog(self, conv_id: str, worklog: List[MockWorkEntry]):
        self._worklog[conv_id] = worklog


def create_test_middleware() -> UnifiedContextMiddleware:
    """创建测试用的中间件"""
    gpts_memory = MockGptsMemory()
    return UnifiedContextMiddleware(
        gpts_memory=gpts_memory,
        agent_file_system=None,
        llm_client=None,
    )


# ==================== 阶段分组测试 ====================

@pytest.mark.asyncio
async def test_group_worklog_by_phase_exploration():
    """测试探索阶段分组"""
    middleware = create_test_middleware()
    
    entries = [
        MockWorkEntry(timestamp=1.0, tool="read", success=True),
        MockWorkEntry(timestamp=2.0, tool="glob", success=True),
        MockWorkEntry(timestamp=3.0, tool="grep", success=True),
    ]
    
    result = await middleware._group_worklog_by_phase(entries)
    
    assert TaskPhase.EXPLORATION in result
    assert len(result[TaskPhase.EXPLORATION]) == 3
    assert TaskPhase.DEVELOPMENT not in result or len(result.get(TaskPhase.DEVELOPMENT, [])) == 0


@pytest.mark.asyncio
async def test_group_worklog_by_phase_development():
    """测试开发阶段分组"""
    middleware = create_test_middleware()
    
    entries = [
        MockWorkEntry(timestamp=1.0, tool="write", success=True),
        MockWorkEntry(timestamp=2.0, tool="edit", success=True),
        MockWorkEntry(timestamp=3.0, tool="bash", success=True),
    ]
    
    result = await middleware._group_worklog_by_phase(entries)
    
    assert TaskPhase.DEVELOPMENT in result
    assert len(result[TaskPhase.DEVELOPMENT]) == 3


@pytest.mark.asyncio
async def test_group_worklog_by_phase_debugging():
    """测试调试阶段分组（失败操作）"""
    middleware = create_test_middleware()
    
    entries = [
        MockWorkEntry(timestamp=1.0, tool="write", success=True),
        MockWorkEntry(timestamp=2.0, tool="bash", success=False, result="Error"),
        MockWorkEntry(timestamp=3.0, tool="bash", success=False, result="Failed"),
    ]
    
    result = await middleware._group_worklog_by_phase(entries)
    
    # 失败的操作应该在 DEBUGGING 阶段
    assert TaskPhase.DEBUGGING in result
    assert len(result[TaskPhase.DEBUGGING]) == 2


@pytest.mark.asyncio
async def test_group_worklog_by_phase_refinement():
    """测试优化阶段分组"""
    middleware = create_test_middleware()
    
    entries = [
        MockWorkEntry(timestamp=1.0, tool="read", success=True, tags=["refactor"]),
        MockWorkEntry(timestamp=2.0, tool="edit", success=True, tags=["optimize"]),
    ]
    
    result = await middleware._group_worklog_by_phase(entries)
    
    assert TaskPhase.REFINEMENT in result
    assert len(result[TaskPhase.REFINEMENT]) == 2


@pytest.mark.asyncio
async def test_group_worklog_by_phase_delivery():
    """测试收尾阶段分组"""
    middleware = create_test_middleware()
    
    entries = [
        MockWorkEntry(timestamp=1.0, tool="write", success=True, tags=["summary"]),
        MockWorkEntry(timestamp=2.0, tool="write", success=True, tags=["document"]),
    ]
    
    result = await middleware._group_worklog_by_phase(entries)
    
    assert TaskPhase.DELIVERY in result
    assert len(result[TaskPhase.DELIVERY]) == 2


@pytest.mark.asyncio
async def test_group_worklog_with_manual_phase():
    """测试手动标记阶段"""
    middleware = create_test_middleware()
    
    entries = [
        MockWorkEntry(timestamp=1.0, tool="read", success=True, metadata={"phase": "debugging"}),
    ]
    
    result = await middleware._group_worklog_by_phase(entries)
    
    assert TaskPhase.DEBUGGING in result
    assert len(result[TaskPhase.DEBUGGING]) == 1


# ==================== 优先级判断测试 ====================

@pytest.mark.asyncio
async def test_determine_section_priority_critical():
    """测试 CRITICAL 优先级"""
    middleware = create_test_middleware()
    
    entry = MockWorkEntry(
        timestamp=1.0,
        tool="write",
        success=True,
        tags=["critical", "decision"],
    )
    
    priority = middleware._determine_section_priority(entry)
    
    assert priority == ContentPriority.CRITICAL


@pytest.mark.asyncio
async def test_determine_section_priority_high():
    """测试 HIGH 优先级"""
    middleware = create_test_middleware()
    
    entry = MockWorkEntry(
        timestamp=1.0,
        tool="bash",
        success=True,
        tags=[],
    )
    
    priority = middleware._determine_section_priority(entry)
    
    assert priority == ContentPriority.HIGH


@pytest.mark.asyncio
async def test_determine_section_priority_medium():
    """测试 MEDIUM 优先级"""
    middleware = create_test_middleware()
    
    entry = MockWorkEntry(
        timestamp=1.0,
        tool="read",
        success=True,
        tags=[],
    )
    
    priority = middleware._determine_section_priority(entry)
    
    assert priority == ContentPriority.MEDIUM


@pytest.mark.asyncio
async def test_determine_section_priority_low():
    """测试 LOW 优先级（失败操作）"""
    middleware = create_test_middleware()
    
    entry = MockWorkEntry(
        timestamp=1.0,
        tool="read",
        success=False,
    )
    
    priority = middleware._determine_section_priority(entry)
    
    assert priority == ContentPriority.LOW


# ==================== Section 转换测试 ====================

@pytest.mark.asyncio
async def test_work_entry_to_section_basic():
    """测试基本 WorkEntry → Section 转换"""
    middleware = create_test_middleware()
    
    entry = MockWorkEntry(
        timestamp=1.0,
        tool="read",
        args={"file": "test.py"},
        summary="读取文件成功",
        result="file content...",
        success=True,
    )
    
    section = await middleware._work_entry_to_section(entry, 0)
    
    assert "read" in section.content
    assert "读取文件成功" in section.content
    assert section.priority in [ContentPriority.MEDIUM, ContentPriority.HIGH]
    assert section.metadata["success"] == True


@pytest.mark.asyncio
async def test_work_entry_to_section_with_long_content():
    """测试长内容自动归档"""
    middleware = create_test_middleware()
    
    entry = MockWorkEntry(
        timestamp=1.0,
        tool="bash",
        args={"command": "pytest"},
        summary="运行测试",
        result="x" * 1000,  # 长内容
        success=True,
    )
    
    section = await middleware._work_entry_to_section(entry, 0)
    
    # 由于没有文件系统，detail_ref 应该为 None
    assert section.detail_ref is None
    # 内容应该被截断或使用摘要
    assert len(section.content) < len(entry.result) + 100


@pytest.mark.asyncio
async def test_work_entry_to_section_with_failure():
    """测试失败操作的 Section 转换"""
    middleware = create_test_middleware()
    
    entry = MockWorkEntry(
        timestamp=1.0,
        tool="bash",
        summary="运行测试",
        result="Error: test failed",
        success=False,
    )
    
    section = await middleware._work_entry_to_section(entry, 0)
    
    assert "❌ 失败" in section.content
    assert section.priority == ContentPriority.LOW


# ==================== 章节标题生成测试 ====================

def test_generate_chapter_title():
    """测试章节标题生成"""
    middleware = create_test_middleware()
    
    entries = [
        MockWorkEntry(timestamp=1.0, tool="read", success=True),
        MockWorkEntry(timestamp=2.0, tool="glob", success=True),
    ]
    
    title = middleware._generate_chapter_title(TaskPhase.EXPLORATION, entries)
    
    assert "需求探索与分析" in title
    assert "read" in title or "glob" in title


# ==================== 运行测试 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])