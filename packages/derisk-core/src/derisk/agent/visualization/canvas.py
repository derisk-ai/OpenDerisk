"""
Canvas - Web 可视化工作区

参考 OpenClaw 的 Canvas 设计
实现 Agent 执行过程的可视化展示
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio
import logging

from .canvas_blocks import (
    CanvasElement, CanvasBlock, ThinkingBlock, ToolCallBlock,
    MessageBlock, TaskBlock, PlanBlock, ErrorBlock, FileBlock,
    CodeBlock, ChartBlock, ElementType,
)

logger = logging.getLogger(__name__)


class Canvas:
    """
    Canvas 可视化工作区
    
    核心功能:
    1. 元素管理 - 添加/更新/删除元素
    2. 块级渲染 - 支持 Block 级别的内容组织
    3. 流式推送 - 实时推送到前端
    4. 快照导出 - 支持导出完整状态
    """
    
    def __init__(self, session_id: str, gateway=None, gpts_memory=None):
        self.session_id = session_id
        self.gateway = gateway
        self.gpts_memory = gpts_memory
        self.elements: Dict[str, CanvasElement] = {}
        self.blocks: Dict[str, CanvasBlock] = {}
        self._block_order: List[str] = []
        self._version = 0
        self._listeners: List = []
    
    async def render_block(self, block: CanvasBlock) -> str:
        self.blocks[block.block_id] = block
        if block.block_id not in self._block_order:
            self._block_order.append(block.block_id)
        self._version += 1
        await self._push_block_update(block)
        return block.block_id
    
    async def update_block(self, block_id: str, updates: Dict[str, Any]) -> bool:
        if block_id not in self.blocks:
            return False
        block = self.blocks[block_id]
        for key, value in updates.items():
            if hasattr(block, key):
                setattr(block, key, value)
        self._version += 1
        await self._push_block_update(block)
        return True
    
    async def add_thinking(self, content: str, thoughts: List[str] = None, reasoning: str = None) -> str:
        block = ThinkingBlock(content=content, thoughts=thoughts or [], reasoning=reasoning)
        return await self.render_block(block)
    
    async def add_tool_call(self, tool_name: str, tool_args: Dict[str, Any], status: str = "pending") -> str:
        block = ToolCallBlock(tool_name=tool_name, tool_args=tool_args, status=status, content=f"执行工具: {tool_name}")
        return await self.render_block(block)
    
    async def complete_tool_call(self, block_id: str, result: str, execution_time: float = None):
        await self.update_block(block_id, {"result": result, "status": "completed", "execution_time": execution_time})
    
    async def add_message(self, role: str, content: str, round: int = 0) -> str:
        block = MessageBlock(role=role, content=content, round=round)
        return await self.render_block(block)
    
    async def add_task(self, task_name: str, description: str = None, status: str = "pending") -> str:
        block = TaskBlock(task_name=task_name, description=description, status=status, content=f"任务: {task_name}")
        return await self.render_block(block)
    
    async def add_plan(self, stages: List[Dict[str, Any]], title: str = "执行计划") -> str:
        block = PlanBlock(title=title, stages=stages, content=f"共 {len(stages)} 个阶段")
        return await self.render_block(block)
    
    async def add_error(self, error_type: str, error_message: str, stack_trace: str = None) -> str:
        block = ErrorBlock(error_type=error_type, error_message=error_message, stack_trace=stack_trace)
        return await self.render_block(block)
    
    async def add_code(self, code: str, language: str = "python", title: str = None) -> str:
        block = CodeBlock(language=language, code=code, title=title)
        return await self.render_block(block)
    
    async def add_chart(self, chart_type: str, data: Dict[str, Any], title: str = None) -> str:
        block = ChartBlock(chart_type=chart_type, data=data, title=title)
        return await self.render_block(block)
    
    async def _push_block_update(self, block: CanvasBlock):
        message = {
            "type": "canvas_block",
            "session_id": self.session_id,
            "action": "add",
            "block": block.model_dump(),
            "version": self._version,
        }
        await self._send_message(message)
        if self.gpts_memory:
            await self._sync_to_gpts_memory(block)
    
    async def _send_message(self, message: Dict[str, Any]):
        for listener in self._listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(message)
                else:
                    listener(message)
            except Exception as e:
                logger.error(f"[Canvas] listener error: {e}")
        if self.gateway:
            try:
                if hasattr(self.gateway, "send_to_session"):
                    await self.gateway.send_to_session(self.session_id, message)
            except Exception as e:
                logger.error(f"[Canvas] gateway error: {e}")
    
    async def _sync_to_gpts_memory(self, block: CanvasBlock):
        if not self.gpts_memory:
            return
        try:
            vis_content = self._block_to_vis(block)
            await self.gpts_memory.push_message(self.session_id, stream_msg={
                "type": "canvas", "block_type": block.block_type,
                "content": vis_content, "block_id": block.block_id,
            })
        except Exception as e:
            logger.error(f"[Canvas] sync error: {e}")
    
    def _block_to_vis(self, block: CanvasBlock) -> str:
        if isinstance(block, ThinkingBlock):
            return f"[THINKING]{block.content}[/THINKING]"
        elif isinstance(block, ToolCallBlock):
            return f"[TOOL:{block.tool_name}]{block.result or 'executing...'}[/TOOL]"
        elif isinstance(block, MessageBlock):
            return f"[{block.role.upper()}]{block.content}[/{block.role.upper()}]"
        elif isinstance(block, TaskBlock):
            return f"[TASK:{block.status}]{block.task_name}[/TASK]"
        elif isinstance(block, PlanBlock):
            return f"[PLAN]{len(block.stages)} stages, current: {block.current_stage}[/PLAN]"
        elif isinstance(block, ErrorBlock):
            return f"[ERROR]{block.error_type}: {block.error_message}[/ERROR]"
        elif isinstance(block, CodeBlock):
            return f"[CODE:{block.language}]{block.code}[/CODE]"
        return str(block.content) if block.content else ""
    
    def subscribe(self, callback):
        self._listeners.append(callback)
    
    def unsubscribe(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)
    
    def snapshot(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "version": self._version,
            "blocks": [b.model_dump() for b in self.blocks.values()],
            "block_order": self._block_order,
        }
    
    async def clear(self):
        self.elements.clear()
        self.blocks.clear()
        self._block_order.clear()
        self._version += 1


class CanvasManager:
    """Canvas 管理器"""
    
    def __init__(self, gateway=None, gpts_memory=None):
        self.gateway = gateway
        self.gpts_memory = gpts_memory
        self._canvases: Dict[str, Canvas] = {}
    
    def get_canvas(self, session_id: str) -> Canvas:
        if session_id not in self._canvases:
            self._canvases[session_id] = Canvas(
                session_id, self.gateway, self.gpts_memory
            )
        return self._canvases[session_id]
    
    def remove_canvas(self, session_id: str):
        if session_id in self._canvases:
            del self._canvases[session_id]


_canvas_manager: Optional[CanvasManager] = None

def get_canvas_manager() -> CanvasManager:
    global _canvas_manager
    if _canvas_manager is None:
        _canvas_manager = CanvasManager()
    return _canvas_manager
