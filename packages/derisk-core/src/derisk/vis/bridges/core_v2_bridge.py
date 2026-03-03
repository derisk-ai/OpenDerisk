"""
Core_V2架构VIS桥接层

将ProgressBroadcaster的进度事件自动转换为Part系统
实现事件驱动的可视化更新
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from derisk.vis.parts import (
    ErrorPart,
    PartContainer,
    PartStatus,
    TextPart,
    ThinkingPart,
    ToolUsePart,
    VisPart,
)
from derisk.vis.reactive import Signal

if TYPE_CHECKING:
    from derisk.agent.core_v2.visualization.progress import (
        ProgressBroadcaster,
        ProgressEvent,
        ProgressEventType,
    )

logger = logging.getLogger(__name__)


class CoreV2VisBridge:
    """
    Core_V2架构VIS桥接层
    
    功能:
    1. 自动订阅ProgressBroadcaster事件
    2. 将ProgressEvent转换为Part
    3. 提供响应式Part流
    4. 支持实时推送和WebSocket集成
    
    示例:
        broadcaster = ProgressBroadcaster()
        bridge = CoreV2VisBridge(broadcaster)
        
        # 自动订阅事件
        bridge.start()
        
        # 订阅Part变化
        bridge.part_stream.subscribe(lambda container: print(f"{len(container)} parts"))
        
        # 停止订阅
        bridge.stop()
    """
    
    def __init__(
        self,
        broadcaster: Optional["ProgressBroadcaster"] = None,
        auto_subscribe: bool = True
    ):
        """
        初始化Core_V2 VIS桥接层
        
        Args:
            broadcaster: ProgressBroadcaster实例(可选)
            auto_subscribe: 是否自动订阅事件
        """
        self.broadcaster = broadcaster
        self.part_stream = Signal(PartContainer())
        self._event_history: List[Dict[str, Any]] = []
        self._subscribed = False
        self._event_handlers: Dict[str, Callable] = {}
        
        # 注册事件处理器
        self._register_event_handlers()
        
        # 自动订阅
        if broadcaster and auto_subscribe:
            self.start()
    
    def _register_event_handlers(self):
        """注册各类事件的处理函数"""
        self._event_handlers = {
            "thinking": self._handle_thinking_event,
            "tool_started": self._handle_tool_started_event,
            "tool_completed": self._handle_tool_completed_event,
            "tool_failed": self._handle_tool_failed_event,
            "info": self._handle_info_event,
            "warning": self._handle_warning_event,
            "error": self._handle_error_event,
            "progress": self._handle_progress_event,
            "complete": self._handle_complete_event,
        }
    
    def start(self):
        """开始订阅ProgressBroadcaster事件"""
        if self._subscribed or not self.broadcaster:
            return
        
        self.broadcaster.subscribe(self._on_progress_event)
        self._subscribed = True
        logger.info("[CoreV2VisBridge] 已开始订阅ProgressBroadcaster事件")
    
    def stop(self):
        """停止订阅ProgressBroadcaster事件"""
        if not self._subscribed or not self.broadcaster:
            return
        
        self.broadcaster.unsubscribe(self._on_progress_event)
        self._subscribed = False
        logger.info("[CoreV2VisBridge] 已停止订阅ProgressBroadcaster事件")
    
    async def _on_progress_event(self, event: "ProgressEvent"):
        """
        处理Progress事件
        
        Args:
            event: Progress事件
        """
        # 记录历史
        self._event_history.append(event.to_dict())
        
        # 根据事件类型分发处理器
        event_type = event.type.value if hasattr(event.type, 'value') else str(event.type)
        handler = self._event_handlers.get(event_type)
        
        if handler:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"[CoreV2VisBridge] 事件处理失败: {e}", exc_info=True)
        else:
            logger.warning(f"[CoreV2VisBridge] 未知事件类型: {event_type}")
    
    async def _handle_thinking_event(self, event: "ProgressEvent"):
        """处理思考事件"""
        thinking_part = ThinkingPart.create(
            content=event.content,
            expand=event.metadata.get('expand', False),
            streaming=event.metadata.get('streaming', False)
        )
        
        # 如果有UID,尝试更新现有Part
        part_uid = event.metadata.get('uid')
        if part_uid:
            container = self.part_stream.value
            existing_part = container.get_part(part_uid)
            
            if existing_part and existing_part.is_streaming():
                # 流式更新
                container.update_part(
                    part_uid,
                    lambda p: p.append(event.content) if p.is_streaming() else p
                )
                self.part_stream.value = container
                return
        
        # 创建新Part
        self._add_part(thinking_part)
    
    async def _handle_tool_started_event(self, event: "ProgressEvent"):
        """处理工具开始事件"""
        tool_name = event.metadata.get('tool_name', 'unknown')
        tool_args = event.metadata.get('args', {})
        
        tool_part = ToolUsePart.create(
            tool_name=tool_name,
            tool_args=tool_args,
            streaming=True
        )
        
        self._add_part(tool_part)
    
    async def _handle_tool_completed_event(self, event: "ProgressEvent"):
        """处理工具完成事件"""
        tool_name = event.metadata.get('tool_name')
        result = event.metadata.get('result', '')
        execution_time = event.metadata.get('execution_time')
        
        # 查找对应的流式Tool Part并完成
        container = self.part_stream.value
        
        for part in container:
            if (part.type.value == "tool_use" and 
                isinstance(part, ToolUsePart) and 
                part.tool_name == tool_name and 
                part.is_streaming()):
                
                container.update_part(
                    part.uid,
                    lambda p: p.set_result(result, execution_time)
                )
                self.part_stream.value = container
                return
        
        # 如果没有找到流式Part,创建新的完成Part
        tool_part = ToolUsePart.create(
            tool_name=tool_name,
            tool_args={},
            streaming=False
        ).set_result(result, execution_time)
        
        self._add_part(tool_part)
    
    async def _handle_tool_failed_event(self, event: "ProgressEvent"):
        """处理工具失败事件"""
        tool_name = event.metadata.get('tool_name')
        error = event.metadata.get('error', 'Unknown error')
        
        # 查找对应的流式Tool Part并标记错误
        container = self.part_stream.value
        
        for part in container:
            if (part.type.value == "tool_use" and
                isinstance(part, ToolUsePart) and
                part.tool_name == tool_name and
                part.is_streaming()):
                
                container.update_part(
                    part.uid,
                    lambda p: p.set_error(error)
                )
                self.part_stream.value = container
                return
        
        # 创建错误Part
        error_part = ErrorPart.create(
            error_type="ToolExecutionError",
            message=f"Tool '{tool_name}' failed: {error}"
        )
        
        self._add_part(error_part)
    
    async def _handle_info_event(self, event: "ProgressEvent"):
        """处理信息事件"""
        text_part = TextPart.create(
            content=event.content,
            format="markdown",
            streaming=False
        ).complete()
        
        self._add_part(text_part)
    
    async def _handle_warning_event(self, event: "ProgressEvent"):
        """处理警告事件"""
        text_part = TextPart.create(
            content=f"⚠️ {event.content}",
            format="markdown",
            streaming=False
        ).complete()
        
        text_part = text_part.update_metadata(level="warning")
        self._add_part(text_part)
    
    async def _handle_error_event(self, event: "ProgressEvent"):
        """处理错误事件"""
        error_part = ErrorPart.create(
            error_type="ExecutionError",
            message=event.content,
            stack_trace=event.metadata.get('stack_trace')
        )
        
        self._add_part(error_part)
    
    async def _handle_progress_event(self, event: "ProgressEvent"):
        """处理进度事件"""
        current = event.metadata.get('current', 0)
        total = event.metadata.get('total', 1)
        percent = event.metadata.get('percent', 0)
        
        progress_content = f"**进度**: {current}/{total} ({percent:.1f}%)"
        if event.content:
            progress_content += f"\n\n{event.content}"
        
        text_part = TextPart.create(
            content=progress_content,
            format="markdown",
            streaming=False
        ).complete()
        
        text_part = text_part.update_metadata(
            progress=True,
            current=current,
            total=total,
            percent=percent
        )
        
        self._add_part(text_part)
    
    async def _handle_complete_event(self, event: "ProgressEvent"):
        """处理完成事件"""
        text_part = TextPart.create(
            content=f"✅ {event.content or '任务完成'}",
            format="markdown",
            streaming=False
        ).complete()
        
        text_part = text_part.update_metadata(final=True)
        self._add_part(text_part)
    
    def _add_part(self, part: VisPart):
        """
        添加Part到容器
        
        Args:
            part: 要添加的Part
        """
        container = self.part_stream.value
        container.add_part(part)
        self.part_stream.value = container
    
    def create_manual_part(
        self,
        part_type: str,
        content: str = "",
        **kwargs
    ) -> VisPart:
        """
        手动创建Part
        
        Args:
            part_type: Part类型
            content: 内容
            **kwargs: 额外参数
            
        Returns:
            创建的Part
        """
        if part_type == "text":
            part = TextPart.create(content=content, **kwargs)
        elif part_type == "thinking":
            part = ThinkingPart.create(content=content, **kwargs)
        elif part_type == "tool":
            part = ToolUsePart.create(
                tool_name=kwargs.get('tool_name', 'unknown'),
                tool_args=kwargs.get('tool_args', {}),
                streaming=kwargs.get('streaming', False)
            )
        else:
            part = TextPart.create(content=content, **kwargs)
        
        self._add_part(part)
        return part
    
    def get_part_by_uid(self, uid: str) -> Optional[VisPart]:
        """
        根据UID获取Part
        
        Args:
            uid: Part的UID
            
        Returns:
            Part实例,不存在则返回None
        """
        container = self.part_stream.value
        return container.get_part(uid)
    
    def get_parts_as_vis(self) -> List[Dict[str, Any]]:
        """
        获取Part列表作为VIS兼容格式
        
        Returns:
            VIS兼容的字典列表
        """
        container = self.part_stream.value
        return container.to_list()
    
    def clear_parts(self):
        """清空所有Part"""
        self.part_stream.value = PartContainer()
        self._event_history.clear()
    
    def get_event_history(self) -> List[Dict[str, Any]]:
        """
        获取事件历史记录
        
        Returns:
            事件历史列表
        """
        return self._event_history.copy()
    
    async def export_to_vis_converter(self) -> Dict[str, Any]:
        """
        导出为VIS转换器兼容格式
        
        用于与现有VIS系统集成
        
        Returns:
            VIS转换器兼容的数据结构
        """
        parts = self.get_parts_as_vis()
        
        # 转换为VIS消息格式
        messages = []
        for i, part in enumerate(parts):
            message = {
                "uid": part.get("uid", str(i)),
                "type": part.get("type", "all"),
                "status": part.get("status", "completed"),
                "content": part.get("content", ""),
                "metadata": part.get("metadata", {})
            }
            messages.append(message)
        
        return {
            "parts": parts,
            "messages": messages,
            "event_history": self._event_history
        }
    
    def set_broadcaster(self, broadcaster: "ProgressBroadcaster", auto_subscribe: bool = True):
        """
        设置新的ProgressBroadcaster
        
        Args:
            broadcaster: ProgressBroadcaster实例
            auto_subscribe: 是否自动订阅
        """
        # 停止旧的订阅
        self.stop()
        
        # 设置新的broadcaster
        self.broadcaster = broadcaster
        
        # 自动订阅
        if auto_subscribe:
            self.start()
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop()
        return False