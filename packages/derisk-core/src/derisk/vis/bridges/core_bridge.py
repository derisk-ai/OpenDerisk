"""
Core架构VIS桥接层

将ConversableAgent的Action输出自动转换为Part系统
提供从传统VIS到新Part系统的兼容层
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from derisk.vis.parts import (
    CodePart,
    PartContainer,
    PartStatus,
    TextPart,
    ThinkingPart,
    ToolUsePart,
    VisPart,
)
from derisk.vis.reactive import Signal

if TYPE_CHECKING:
    from derisk.agent.core.action.base import Action, ActionOutput
    from derisk.agent.core.base_agent import ConversableAgent

logger = logging.getLogger(__name__)


class CoreVisBridge:
    """
    Core架构VIS桥接层
    
    功能:
    1. 自动将ActionOutput转换为Part
    2. 提供响应式Part流
    3. 保持与现有VIS协议的兼容性
    
    示例:
        agent = ConversableAgent(...)
        bridge = CoreVisBridge(agent)
        
        # 订阅Part变化
        bridge.part_stream.subscribe(lambda parts: print(f"{len(parts)} parts"))
        
        # 在Action执行后自动转换
        async def on_action_complete(action: Action, output: ActionOutput):
            await bridge.process_action(action, output)
    """
    
    def __init__(self, agent: "ConversableAgent"):
        """
        初始化Core VIS桥接层
        
        Args:
            agent: ConversableAgent实例
        """
        self.agent = agent
        self.part_stream = Signal(PartContainer())
        self._action_history: List[Dict[str, Any]] = []
    
    async def process_action(
        self,
        action: "Action",
        output: "ActionOutput",
        context: Optional[Dict[str, Any]] = None
    ) -> List[VisPart]:
        """
        处理Action执行结果,转换为Part
        
        Args:
            action: 执行的Action
            output: Action输出
            context: 额外上下文
            
        Returns:
            生成的Part列表
        """
        parts = self._action_to_parts(action, output, context)
        
        # 更新Part流
        container = self.part_stream.value
        for part in parts:
            container.add_part(part)
        
        self.part_stream.value = container
        
        # 记录历史
        self._action_history.append({
            "action": action.name if hasattr(action, 'name') else str(type(action)),
            "output": output.model_dump() if hasattr(output, 'model_dump') else str(output),
            "parts": [p.uid for p in parts]
        })
        
        return parts
    
    def _action_to_parts(
        self,
        action: "Action",
        output: "ActionOutput",
        context: Optional[Dict[str, Any]] = None
    ) -> List[VisPart]:
        """
        将ActionOutput转换为Part列表
        
        Args:
            action: Action实例
            output: Action输出
            context: 额外上下文
            
        Returns:
            Part列表
        """
        parts = []
        
        # 1. 处理思考内容
        if output.thinking:
            thinking_part = ThinkingPart.create(
                content=output.thinking,
                streaming=False
            ).complete()
            parts.append(thinking_part)
        
        # 2. 处理主要输出内容
        if output.view:
            # 判断内容类型
            content_type = self._detect_content_type(output.view)
            
            if content_type == "code":
                code_part = CodePart.create(
                    code=output.view,
                    language=self._detect_language(output.view, action)
                )
                parts.append(code_part)
            else:
                text_part = TextPart.create(
                    content=output.view,
                    format="markdown",
                    streaming=False
                ).complete()
                parts.append(text_part)
        
        # 3. 处理工具调用(如果有)
        if hasattr(output, 'tool_calls') and output.tool_calls:
            for tool_call in output.tool_calls:
                tool_part = ToolUsePart.create(
                    tool_name=tool_call.get('name', 'unknown'),
                    tool_args=tool_call.get('args', {}),
                    streaming=False
                )
                parts.append(tool_part)
        
        # 4. 处理Action特定的元数据
        if output.resource_reports:
            for report in output.resource_reports:
                if report.get('type') == 'file':
                    from derisk.vis.parts import FilePart
                    file_part = FilePart.create(
                        filename=report.get('name', 'unknown'),
                        size=report.get('size', 0),
                        url=report.get('url')
                    )
                    parts.append(file_part)
        
        # 5. 如果没有生成任何Part,创建默认文本Part
        if not parts and output.content:
            text_part = TextPart.create(
                content=output.content,
                streaming=False
            ).complete()
            parts.append(text_part)
        
        return parts
    
    def _detect_content_type(self, content: str) -> str:
        """
        检测内容类型
        
        Args:
            content: 内容字符串
            
        Returns:
            内容类型: text, code, markdown
        """
        # 简单启发式判断
        if content.strip().startswith('```'):
            return "code"
        if 'def ' in content or 'class ' in content or 'function ' in content:
            if content.count('\n') > 5:  # 多行代码
                return "code"
        return "text"
    
    def _detect_language(self, content: str, action: "Action") -> str:
        """
        检测编程语言
        
        Args:
            content: 代码内容
            action: Action实例
            
        Returns:
            语言名称
        """
        # 从代码块标记中提取
        if content.strip().startswith('```'):
            lines = content.strip().split('\n')
            if lines:
                lang = lines[0].replace('```', '').strip()
                if lang:
                    return lang
        
        # 从Action类型推断
        action_name = action.name if hasattr(action, 'name') else ''
        if 'python' in action_name.lower():
            return 'python'
        if 'bash' in action_name.lower() or 'shell' in action_name.lower():
            return 'bash'
        if 'sql' in action_name.lower():
            return 'sql'
        
        return 'python'  # 默认Python
    
    def create_streaming_part(
        self,
        content_type: str = "text",
        **kwargs
    ) -> VisPart:
        """
        创建流式Part
        
        Args:
            content_type: Part类型
            **kwargs: 额外参数
            
        Returns:
            开始流式输出的Part
        """
        if content_type == "text":
            part = TextPart.create(content="", streaming=True)
        elif content_type == "code":
            part = CodePart.create(code="", streaming=True, **kwargs)
        elif content_type == "thinking":
            part = ThinkingPart.create(content="", streaming=True, **kwargs)
        elif content_type == "tool":
            part = ToolUsePart.create(
                tool_name=kwargs.get('tool_name', 'unknown'),
                tool_args=kwargs.get('tool_args', {}),
                streaming=True
            )
        else:
            part = TextPart.create(content="", streaming=True)
        
        # 添加到容器
        container = self.part_stream.value
        container.add_part(part)
        self.part_stream.value = container
        
        return part
    
    def update_streaming_part(self, part_uid: str, chunk: str) -> Optional[VisPart]:
        """
        更新流式Part
        
        Args:
            part_uid: Part的UID
            chunk: 内容片段
            
        Returns:
            更新后的Part,不存在则返回None
        """
        container = self.part_stream.value
        
        def update_fn(old_part: VisPart) -> VisPart:
            if old_part.is_streaming():
                return old_part.append(chunk)
            return old_part
        
        updated_part = container.update_part(part_uid, update_fn)
        if updated_part:
            self.part_stream.value = container
        
        return updated_part
    
    def complete_streaming_part(
        self,
        part_uid: str,
        final_content: Optional[str] = None
    ) -> Optional[VisPart]:
        """
        完成流式Part
        
        Args:
            part_uid: Part的UID
            final_content: 最终内容(可选)
            
        Returns:
            完成后的Part
        """
        container = self.part_stream.value
        
        def update_fn(old_part: VisPart) -> VisPart:
            return old_part.complete(final_content)
        
        completed_part = container.update_part(part_uid, update_fn)
        if completed_part:
            self.part_stream.value = container
        
        return completed_part
    
    def get_parts_as_vis(self) -> List[Dict[str, Any]]:
        """
        获取Part列表作为VIS兼容格式
        
        Returns:
            VIS兼容的字典列表
        """
        container = self.part_stream.value
        return container.to_list()
    
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
    
    def clear_parts(self):
        """清空所有Part"""
        self.part_stream.value = PartContainer()
        self._action_history.clear()
    
    def get_action_history(self) -> List[Dict[str, Any]]:
        """
        获取Action历史记录
        
        Returns:
            Action历史列表
        """
        return self._action_history.copy()
    
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
            "action_history": self._action_history
        }