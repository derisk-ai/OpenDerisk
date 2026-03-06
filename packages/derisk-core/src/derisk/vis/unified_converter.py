"""
统一的VIS转换器

整合Core和Core_V2架构的VIS桥接层
提供统一的可视化接口
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from derisk.vis.base import Vis
from derisk.vis.parts import PartContainer, PartStatus, VisPart
from derisk.vis.reactive import Effect, Signal
from derisk.vis.vis_converter import VisProtocolConverter

if TYPE_CHECKING:
    from derisk.agent.core.base_agent import ConversableAgent
    from derisk.agent.core_v2.visualization.progress import ProgressBroadcaster

logger = logging.getLogger(__name__)


class UnifiedVisConverter(VisProtocolConverter):
    """
    统一的VIS转换器
    
    功能:
    1. 整合Core和Core_V2的VIS桥接层
    2. 自动渲染Part为VIS组件
    3. 支持流式更新和增量传输
    4. 保持向后兼容
    
    示例:
        # 方式1: 注册Core Agent
        from derisk.agent.core.base_agent import ConversableAgent
        
        agent = ConversableAgent(...)
        converter = UnifiedVisConverter()
        converter.register_core_agent(agent)
        
        # 方式2: 注册Core_V2 Broadcaster
        from derisk.agent.core_v2.visualization.progress import ProgressBroadcaster
        
        broadcaster = ProgressBroadcaster()
        converter.register_core_v2_broadcaster(broadcaster)
        
        # 自动渲染
        async for vis_output in converter.render_stream():
            print(vis_output)
    """
    
    def __init__(self, **kwargs):
        """初始化统一转换器"""
        super().__init__(paths=[], **kwargs)
        
        # Part流(响应式)
        self._part_stream = Signal(PartContainer())
        
        # 桥接层实例
        self._core_bridge = None
        self._core_v2_bridge = None
        
        # 渲染效果
        self._render_effect: Optional[Effect] = None
        
        # VIS组件缓存
        self._vis_cache: Dict[str, str] = {}
    
    @property
    def render_name(self) -> str:
        """渲染器名称"""
        return "unified_vis"
    
    @property
    def description(self) -> str:
        """描述"""
        return "统一的VIS转换器,支持Core和Core_V2架构"
    
    @property
    def incremental(self) -> bool:
        """是否支持增量更新"""
        return True
    
    @property
    def web_use(self) -> bool:
        """是否用于Web"""
        return True
    
    def register_core_agent(self, agent: "ConversableAgent"):
        """
        注册Core Agent
        
        Args:
            agent: ConversableAgent实例
        """
        from .bridges.core_bridge import CoreVisBridge
        
        self._core_bridge = CoreVisBridge(agent)
        
        # 订阅Part变化
        self._core_bridge.part_stream.subscribe(self._on_parts_update)
        
        logger.info(f"[UnifiedVisConverter] 已注册Core Agent: {agent.name}")
    
    def register_core_v2_broadcaster(
        self,
        broadcaster: "ProgressBroadcaster",
        auto_subscribe: bool = True
    ):
        """
        注册Core_V2 Broadcaster
        
        Args:
            broadcaster: ProgressBroadcaster实例
            auto_subscribe: 是否自动订阅
        """
        from .bridges.core_v2_bridge import CoreV2VisBridge
        
        self._core_v2_bridge = CoreV2VisBridge(
            broadcaster=broadcaster,
            auto_subscribe=auto_subscribe
        )
        
        # 订阅Part变化
        self._core_v2_bridge.part_stream.subscribe(self._on_parts_update)
        
        logger.info("[UnifiedVisConverter] 已注册Core_V2 Broadcaster")
    
    def _on_parts_update(self, container: PartContainer):
        """
        Part更新回调
        
        Args:
            container: Part容器
        """
        self._part_stream.value = container
    
    async def render_stream(self):
        """
        渲染Part流
        
        Yields:
            str: VIS组件输出
        """
        for part in self._part_stream.value:
            vis_output = await self._render_part(part)
            if vis_output:
                yield vis_output
    
    async def _render_part(self, part: VisPart) -> Optional[str]:
        """
        渲染单个Part为VIS组件
        
        Args:
            part: Part实例
            
        Returns:
            VIS组件字符串
        """
        # 检查缓存
        cache_key = f"{part.uid}_{part.status}"
        if cache_key in self._vis_cache:
            return self._vis_cache[cache_key]
        
        # 根据Part类型选择VIS组件
        vis_inst = self._get_vis_instance_for_part(part)
        
        if not vis_inst:
            # 没有对应的VIS组件,使用默认文本渲染
            return self._render_default(part)
        
        # 渲染
        vis_output = vis_inst.sync_display(content=part.to_vis_dict())
        
        # 缓存
        self._vis_cache[cache_key] = vis_output
        
        return vis_output
    
    def _get_vis_instance_for_part(self, part: VisPart) -> Optional[Vis]:
        """
        根据Part类型获取VIS实例
        
        Args:
            part: Part实例
            
        Returns:
            VIS实例
        """
        part_type = part.type.value if hasattr(part.type, 'value') else str(part.type)
        
        # Part类型到VIS tag的映射
        part_vis_map = {
            "text": "d-text",
            "code": "d-code",
            "tool_use": "d-tool",
            "thinking": "d-thinking",
            "plan": "d-plan",
            "image": "d-image",
            "file": "d-attach",
            "interaction": "d-interact",
            "error": "d-error"
        }
        
        vis_tag = part_vis_map.get(part_type)
        if vis_tag:
            return self.vis_inst(vis_tag)
        
        return None
    
    def _render_default(self, part: VisPart) -> str:
        """
        默认渲染方式
        
        Args:
            part: Part实例
            
        Returns:
            默认VIS输出
        """
        import json
        
        return f"```vis-default\n{json.dumps(part.to_vis_dict(), ensure_ascii=False)}\n```"
    
    async def visualization(
        self,
        messages: Optional[List] = None,
        plans_map: Optional[Dict] = None,
        gpt_msg: Optional[Any] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        new_plans: Optional[List] = None,
        is_first_chunk: bool = False,
        incremental: bool = False,
        senders_map: Optional[Dict] = None,
        main_agent_name: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        VIS可视化转换
        
        Args:
            messages: 消息列表(兼容旧接口)
            plans_map: 计划映射(兼容旧接口)
            gpt_msg: GPT消息(兼容旧接口)
            stream_msg: 流消息(兼容旧接口)
            new_plans: 新计划(兼容旧接口)
            is_first_chunk: 是否第一个chunk
            incremental: 是否增量模式
            senders_map: 发送者映射
            main_agent_name: 主Agent名称
            **kwargs: 额外参数
            
        Returns:
            VIS输出字符串
        """
        # 如果有Part,优先渲染Part
        parts = self._part_stream.value
        if len(parts) > 0:
            vis_outputs = []
            for part in parts:
                vis_output = await self._render_part(part)
                if vis_output:
                    vis_outputs.append(vis_output)
            
            return "\n".join(vis_outputs)
        
        # 如果没有Part,使用传统消息渲染(向后兼容)
        if messages:
            return await self._render_traditional_messages(
                messages, gpt_msg, stream_msg, incremental
            )
        
        return ""
    
    async def _render_traditional_messages(
        self,
        messages: List,
        gpt_msg: Optional[Any] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        incremental: bool = False
    ) -> str:
        """
        渲染传统消息格式(向后兼容)
        
        Args:
            messages: 消息列表
            gpt_msg: GPT消息
            stream_msg: 流消息
            incremental: 是否增量
            
        Returns:
            VIS输出
        """
        # 使用默认转换器
        from derisk.vis.vis_converter import DefaultVisConverter
        
        default_converter = DefaultVisConverter()
        return await default_converter.visualization(
            messages=messages,
            gpt_msg=gpt_msg,
            stream_msg=stream_msg,
            incremental=incremental
        )
    
    async def final_view(
        self,
        messages: List,
        plans_map: Optional[Dict] = None,
        senders_map: Optional[Dict] = None,
        **kwargs
    ) -> str:
        """
        最终视图
        
        Args:
            messages: 消息列表
            plans_map: 计划映射
            senders_map: 发送者映射
            **kwargs: 额外参数
            
        Returns:
            VIS输出
        """
        return await self.visualization(
            messages=messages,
            plans_map=plans_map,
            senders_map=senders_map,
            incremental=False
        )
    
    def add_part_manually(self, part: VisPart):
        """
        手动添加Part
        
        Args:
            part: Part实例
        """
        container = self._part_stream.value
        container.add_part(part)
        self._part_stream.value = container
    
    def get_parts(self) -> List[VisPart]:
        """
        获取所有Part
        
        Returns:
            Part列表
        """
        return list(self._part_stream.value)
    
    def get_part_by_uid(self, uid: str) -> Optional[VisPart]:
        """
        根据UID获取Part
        
        Args:
            uid: Part的UID
            
        Returns:
            Part实例
        """
        return self._part_stream.value.get_part(uid)
    
    def clear_parts(self):
        """清空所有Part"""
        self._part_stream.value = PartContainer()
        self._vis_cache.clear()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计数据
        """
        parts = self._part_stream.value
        
        status_count = {}
        type_count = {}
        
        for part in parts:
            status = part.status.value if hasattr(part.status, 'value') else str(part.status)
            type_ = part.type.value if hasattr(part.type, 'value') else str(part.type)
            
            status_count[status] = status_count.get(status, 0) + 1
            type_count[type_] = type_count.get(type_, 0) + 1
        
        return {
            "total_parts": len(parts),
            "status_distribution": status_count,
            "type_distribution": type_count,
            "cache_size": len(self._vis_cache),
            "has_core_bridge": self._core_bridge is not None,
            "has_core_v2_bridge": self._core_v2_bridge is not None,
        }


class UnifiedVisManager:
    """
    统一VIS管理器
    
    单例模式,全局管理VIS转换器
    """
    
    _instance: Optional["UnifiedVisManager"] = None
    _converter: Optional[UnifiedVisConverter] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "UnifiedVisManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def get_converter(cls) -> UnifiedVisConverter:
        """获取转换器实例"""
        if cls._converter is None:
            cls._converter = UnifiedVisConverter()
        return cls._converter
    
    @classmethod
    def reset(cls):
        """重置管理器"""
        if cls._converter:
            cls._converter.clear_parts()
        cls._converter = None