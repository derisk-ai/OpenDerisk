"""
UnifiedContextMiddleware 单元测试

测试中间件核心功能
"""

import pytest
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


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


# ==================== 中间件初始化测试 ====================

def test_middleware_initialization():
    """测试中间件初始化"""
    from derisk.context.unified_context_middleware import UnifiedContextMiddleware
    
    gpts_memory = MockGptsMemory()
    
    middleware = UnifiedContextMiddleware(
        gpts_memory=gpts_memory,
        agent_file_system=None,
        llm_client=None,
    )
    
    assert middleware.gpts_memory == gpts_memory
    assert middleware.file_system is None
    assert middleware.hc_integration is not None
    assert middleware._conv_contexts == {}


# ==================== 推断任务描述测试 ====================

@pytest.mark.asyncio
async def test_infer_task_description():
    """测试推断任务描述"""
    from derisk.context.unified_context_middleware import UnifiedContextMiddleware
    
    gpts_memory = MockGptsMemory()
    gpts_memory.set_messages("test_conv", [
        MockMessage(role="user", content="请帮我分析这个文件"),
        MockMessage(role="assistant", content="好的，我来分析"),
    ])
    
    middleware = UnifiedContextMiddleware(
        gpts_memory=gpts_memory,
        agent_file_system=None,
        llm_client=None,
    )
    
    task_desc = await middleware._infer_task_description("test_conv")
    
    assert "请帮我分析这个文件" == task_desc


@pytest.mark.asyncio
async def test_infer_task_description_no_messages():
    """测试无消息时的任务描述推断"""
    from derisk.context.unified_context_middleware import UnifiedContextMiddleware
    
    gpts_memory = MockGptsMemory()
    
    middleware = UnifiedContextMiddleware(
        gpts_memory=gpts_memory,
        agent_file_system=None,
        llm_client=None,
    )
    
    task_desc = await middleware._infer_task_description("empty_conv")
    
    assert task_desc == "未命名任务"


# ==================== 加载最近消息测试 ====================

@pytest.mark.asyncio
async def test_load_recent_messages():
    """测试加载最近消息"""
    from derisk.context.unified_context_middleware import UnifiedContextMiddleware
    
    gpts_memory = MockGptsMemory()
    messages = [MockMessage(role="user", content=f"消息{i}") for i in range(20)]
    gpts_memory.set_messages("test_conv", messages)
    
    middleware = UnifiedContextMiddleware(
        gpts_memory=gpts_memory,
        agent_file_system=None,
        llm_client=None,
    )
    
    recent = await middleware._load_recent_messages("test_conv", limit=10)
    
    assert len(recent) == 10
    assert recent[0].content == "消息10"


# ==================== 缓存管理测试 ====================

@pytest.mark.asyncio
async def test_cache_mechanism():
    """测试缓存机制"""
    from derisk.context.unified_context_middleware import (
        UnifiedContextMiddleware,
        ContextLoadResult,
    )
    from derisk.agent.shared.hierarchical_context import ChapterIndexer
    
    gpts_memory = MockGptsMemory()
    gpts_memory.set_messages("test_conv", [MockMessage(role="user", content="测试")])
    
    middleware = UnifiedContextMiddleware(
        gpts_memory=gpts_memory,
        agent_file_system=None,
        llm_client=None,
    )
    
    # Mock the hc_integration
    mock_hc_manager = Mock()
    mock_hc_manager._chapter_indexer = ChapterIndexer()
    mock_hc_manager.get_statistics = Mock(return_value={"chapter_count": 0})
    mock_hc_manager._auto_compact_if_needed = AsyncMock()
    
    middleware.hc_integration.start_execution = AsyncMock(return_value=mock_hc_manager)
    middleware.hc_integration.get_context_for_prompt = Mock(return_value="test context")
    middleware.hc_integration.get_recall_tools = Mock(return_value=[])
    
    # 第一次加载
    result1 = await middleware.load_context("test_conv", force_reload=False)
    
    # 检查缓存
    assert "test_conv" in middleware._conv_contexts
    
    # 第二次加载应该使用缓存
    result2 = await middleware.load_context("test_conv", force_reload=False)
    assert result2 == result1


def test_clear_all_cache():
    """测试清理所有缓存"""
    from derisk.context.unified_context_middleware import UnifiedContextMiddleware
    
    gpts_memory = MockGptsMemory()
    middleware = UnifiedContextMiddleware(
        gpts_memory=gpts_memory,
        agent_file_system=None,
        llm_client=None,
    )
    
    # 添加一些缓存
    middleware._conv_contexts["conv1"] = Mock()
    middleware._conv_contexts["conv2"] = Mock()
    
    # 清理
    middleware.clear_all_cache()
    
    assert len(middleware._conv_contexts) == 0


# ==================== 统计信息测试 ====================

def test_get_statistics():
    """测试获取统计信息"""
    from derisk.context.unified_context_middleware import UnifiedContextMiddleware
    
    gpts_memory = MockGptsMemory()
    middleware = UnifiedContextMiddleware(
        gpts_memory=gpts_memory,
        agent_file_system=None,
        llm_client=None,
    )
    
    # 没有上下文时
    stats = middleware.get_statistics("unknown_conv")
    assert "error" in stats


# ==================== 运行测试 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])