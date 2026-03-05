"""
统一可视化适配器实现
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .models import VisMessageType, VisOutput

logger = logging.getLogger(__name__)


class UnifiedVisAdapter:
    """
    统一可视化适配器
    
    核心职责：
    1. 统一的消息渲染
    2. 自动适配V1/V2消息格式
    3. 统一的VIS输出格式
    """
    
    def __init__(self, system_app: Any = None):
        self._system_app = system_app
        self._v2_chunk_parsers = {
            "thinking": self._parse_thinking_chunk,
            "tool_call": self._parse_tool_call_chunk,
            "response": self._parse_response_chunk,
            "error": self._parse_error_chunk,
        }
    
    async def render_message(
        self,
        message: Any,
        agent_version: str = "v2"
    ) -> VisOutput:
        """
        统一的消息渲染
        
        Args:
            message: 消息内容（可以是V1/V2格式）
            agent_version: Agent版本
            
        Returns:
            VisOutput: 统一的可视化输出
        """
        if agent_version == "v2":
            return await self._render_v2_message(message)
        else:
            return await self._render_v1_message(message)
    
    async def render_stream_chunk(
        self,
        chunk: Any,
        agent_version: str = "v2"
    ) -> VisOutput:
        """
        渲染流式消息块
        
        Args:
            chunk: 流式块
            agent_version: Agent版本
            
        Returns:
            VisOutput: 统一的可视化输出
        """
        if agent_version == "v2":
            return await self._render_v2_chunk(chunk)
        else:
            return await self._render_v1_chunk(chunk)
    
    async def _render_v2_message(self, message: Any) -> VisOutput:
        """
        渲染V2消息
        
        支持多种消息类型：
        1. V2StreamChunk
        2. UnifiedMessage
        3. 字典格式
        """
        if hasattr(message, "type") and hasattr(message, "content"):
            return await self._render_v2_chunk(message)
        
        if isinstance(message, dict):
            return await self._render_v2_dict_message(message)
        
        return VisOutput(
            type=VisMessageType.RESPONSE,
            content=str(message),
            metadata={"version": "v2"}
        )
    
    async def _render_v1_message(self, message: Any) -> VisOutput:
        """
        渲染V1消息
        
        解析VIS标签格式
        """
        content = ""
        
        if hasattr(message, "content"):
            content = message.content
        elif hasattr(message, "context"):
            content = message.context
        elif isinstance(message, dict):
            content = message.get("content", message.get("context", ""))
        else:
            content = str(message)
        
        if content.startswith("[THINKING]"):
            return VisOutput(
                type=VisMessageType.THINKING,
                content=self._extract_tag_content(content, "THINKING"),
                metadata={"version": "v1"}
            )
        elif content.startswith("[TOOL:"):
            tool_name = self._extract_tool_name(content)
            tool_content = self._extract_tag_content(content, "TOOL")
            return VisOutput(
                type=VisMessageType.TOOL_CALL,
                content=tool_content,
                metadata={"tool_name": tool_name, "version": "v1"}
            )
        elif content.startswith("[ERROR]"):
            return VisOutput(
                type=VisMessageType.ERROR,
                content=self._extract_tag_content(content, "ERROR"),
                metadata={"version": "v1"}
            )
        elif content.startswith("```vis-"):
            return await self._parse_vis_code_block(content)
        
        return VisOutput(
            type=VisMessageType.RESPONSE,
            content=content,
            metadata={"version": "v1"}
        )
    
    async def _render_v2_chunk(self, chunk: Any) -> VisOutput:
        """
        渲染V2流式块
        
        支持V2StreamChunk格式
        """
        chunk_type = getattr(chunk, "type", "response")
        content = getattr(chunk, "content", "")
        metadata = getattr(chunk, "metadata", {})
        
        parser = self._v2_chunk_parsers.get(chunk_type, self._parse_response_chunk)
        return await parser(content, metadata)
    
    async def _render_v1_chunk(self, chunk: Any) -> VisOutput:
        """渲染V1流式块"""
        return await self._render_v1_message(chunk)
    
    async def _render_v2_dict_message(self, message: Dict) -> VisOutput:
        """渲染V2字典消息"""
        msg_type = message.get("type", "response")
        content = message.get("content", "")
        metadata = message.get("metadata", {})
        
        parser = self._v2_chunk_parsers.get(msg_type, self._parse_response_chunk)
        return await parser(content, metadata)
    
    async def _parse_thinking_chunk(
        self,
        content: str,
        metadata: Dict[str, Any]
    ) -> VisOutput:
        """解析思考块"""
        return VisOutput(
            type=VisMessageType.THINKING,
            content=content,
            metadata={
                **metadata,
                "version": "v2",
                "agent_version": "v2"
            }
        )
    
    async def _parse_tool_call_chunk(
        self,
        content: str,
        metadata: Dict[str, Any]
    ) -> VisOutput:
        """解析工具调用块"""
        tool_name = metadata.get("tool_name", "unknown")
        return VisOutput(
            type=VisMessageType.TOOL_CALL,
            content=content,
            metadata={
                "tool_name": tool_name,
                "version": "v2",
                "agent_version": "v2"
            }
        )
    
    async def _parse_response_chunk(
        self,
        content: str,
        metadata: Dict[str, Any]
    ) -> VisOutput:
        """解析响应块"""
        return VisOutput(
            type=VisMessageType.RESPONSE,
            content=content,
            metadata={
                **metadata,
                "version": "v2",
                "agent_version": "v2"
            }
        )
    
    async def _parse_error_chunk(
        self,
        content: str,
        metadata: Dict[str, Any]
    ) -> VisOutput:
        """解析错误块"""
        return VisOutput(
            type=VisMessageType.ERROR,
            content=content,
            metadata={
                **metadata,
                "version": "v2",
                "agent_version": "v2"
            }
        )
    
    async def _parse_vis_code_block(self, content: str) -> VisOutput:
        """
        解析VIS代码块
        
        示例：```vis-chart\n{"type": "bar", ...}\n```
        """
        try:
            lines = content.split("\n")
            if len(lines) < 2:
                return VisOutput(
                    type=VisMessageType.RESPONSE,
                    content=content,
                    metadata={"version": "v1"}
                )
            
            vis_type = lines[0].replace("```vis-", "").strip()
            vis_content = "\n".join(lines[1:-1])
            
            vis_data = json.loads(vis_content)
            
            if vis_type == "chart":
                return VisOutput(
                    type=VisMessageType.CHART,
                    content=vis_content,
                    metadata={
                        "chart_type": vis_data.get("type"),
                        "version": "v1"
                    }
                )
            elif vis_type == "code":
                return VisOutput(
                    type=VisMessageType.CODE,
                    content=vis_content,
                    metadata={
                        "language": vis_data.get("language", "python"),
                        "version": "v1"
                    }
                )
            else:
                return VisOutput(
                    type=VisMessageType.RESPONSE,
                    content=content,
                    metadata={"vis_type": vis_type, "version": "v1"}
                )
        except Exception as e:
            logger.error(f"[UnifiedVisAdapter] 解析VIS代码块失败: {e}")
            return VisOutput(
                type=VisMessageType.RESPONSE,
                content=content,
                metadata={"error": str(e), "version": "v1"}
            )
    
    def _extract_tag_content(self, content: str, tag: str) -> str:
        """提取标签内容"""
        start = f"[{tag}]"
        end = f"[/{tag}]"
        
        if start in content and end in content:
            return content.split(start)[1].split(end)[0]
        elif start in content:
            return content.replace(start, "")
        return content
    
    def _extract_tool_name(self, content: str) -> str:
        """提取工具名称"""
        if "[TOOL:" in content:
            parts = content.split("[TOOL:")
            if len(parts) > 1:
                return parts[1].split("]")[0]
        return "unknown"
    
    async def batch_render(
        self,
        messages: List[Any],
        agent_version: str = "v2"
    ) -> List[VisOutput]:
        """批量渲染消息"""
        outputs = []
        for msg in messages:
            output = await self.render_message(msg, agent_version)
            outputs.append(output)
        return outputs