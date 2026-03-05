"""
ConversableAgent VIS集成扩展

将新的Part系统集成到Core Agent的运行流程中
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from derisk.vis.bridges.core_bridge import CoreVisBridge
from derisk.vis.unified_converter import UnifiedVisConverter, UnifiedVisManager
from derisk.vis.parts import (
    TextPart,
    CodePart,
    ThinkingPart,
    ToolUsePart,
    PartStatus,
)

if TYPE_CHECKING:
    from derisk.agent.core.action.base import ActionOutput
    from derisk.agent.core.base_agent import ConversableAgent

logger = logging.getLogger(__name__)


class AgentVISMixin:
    """
    Agent VIS扩展Mixin
    
    为ConversableAgent提供统一VIS能力
    使用Mixin模式避免修改核心代码
    
    使用方式:
        class MyAgent(AgentVISMixin, ConversableAgent):
            pass
        
        # 或者在运行时注入
        agent = ConversableAgent(...)
        AgentVISMixin.initialize_vis(agent)
    """
    
    _vis_bridge: Optional[CoreVisBridge] = None
    _vis_converter: Optional[UnifiedVisConverter] = None
    
    @classmethod
    def initialize_vis(cls, agent: "ConversableAgent"):
        """
        初始化Agent的VIS能力
        
        Args:
            agent: ConversableAgent实例
        """
        # 获取或创建统一转换器
        agent._vis_converter = UnifiedVisManager.get_converter()
        
        # 创建桥接层
        agent._vis_bridge = CoreVisBridge(agent)
        
        # 注册到转换器
        agent._vis_converter.register_core_agent(agent)
        
        logger.info(f"[VIS] 已为Agent {agent.name} 初始化VIS能力")
    
    async def process_action_output_with_vis(
        self,
        action: Any,
        output: "ActionOutput",
        context: Optional[Dict[str, Any]] = None
    ):
        """
        处理Action输出并转换为Part
        
        集成点: 在act()方法中调用
        
        Args:
            action: Action实例
            output: ActionOutput
            context: 额外上下文
        """
        if not self._vis_bridge:
            logger.debug(f"[VIS] Agent {self.name} 未初始化VIS,跳过处理")
            return
        
        # 转换为Part
        parts = await self._vis_bridge.process_action(action, output, context)
        
        logger.debug(f"[VIS] Agent {self.name} 生成了 {len(parts)} 个Part")
        
        # 触发实时推送(如果有WebSocket连接)
        await self._push_parts_realtime(parts)
    
    async def _push_parts_realtime(self, parts: List[Any]):
        """
        实时推送Part到前端
        
        Args:
            parts: Part列表
        """
        if not hasattr(self, 'agent_context') or not self.agent_context:
            return
        
        # 获取推送管理器
        from derisk.vis.realtime import get_realtime_pusher
        
        pusher = get_realtime_pusher()
        if not pusher:
            return
        
        # 推送到对应的会话
        conv_id = self.agent_context.conv_id
        for part in parts:
            await pusher.push_part(conv_id, part)
    
    def create_streaming_thinking(self, content: str = "") -> ThinkingPart:
        """
        创建流式思考Part
        
        集成点: 在thinking()方法开始时调用
        
        Args:
            content: 初始内容
            
        Returns:
            ThinkingPart实例
        """
        if not self._vis_bridge:
            return ThinkingPart.create(content=content, streaming=True)
        
        return self._vis_bridge.create_streaming_part(
            content_type="thinking",
            content=content
        )
    
    def update_streaming_thinking(self, part_uid: str, chunk: str):
        """
        更新流式思考Part
        
        集成点: 在thinking()流式输出时调用
        
        Args:
            part_uid: Part的UID
            chunk: 内容片段
        """
        if not self._vis_bridge:
            return
        
        self._vis_bridge.update_streaming_part(part_uid, chunk)
    
    def complete_streaming_thinking(
        self,
        part_uid: str,
        final_content: Optional[str] = None
    ):
        """
        完成流式思考Part
        
        集成点: 在thinking()完成时调用
        
        Args:
            part_uid: Part的UID
            final_content: 最终内容
        """
        if not self._vis_bridge:
            return
        
        self._vis_bridge.complete_streaming_part(part_uid, final_content)
    
    def get_vis_parts(self) -> List[Dict[str, Any]]:
        """
        获取所有Part(用于调试或查询)
        
        Returns:
            Part字典列表
        """
        if not self._vis_bridge:
            return []
        
        return self._vis_bridge.get_parts_as_vis()
    
    def clear_vis_parts(self):
        """清空所有Part"""
        if self._vis_bridge:
            self._vis_bridge.clear_parts()


def patch_conversable_agent():
    """
    补丁函数 - 为ConversableAgent动态添加VIS能力
    
    不修改原文件,通过动态添加方法实现集成
    """
    from derisk.agent.core.base_agent import ConversableAgent
    from derisk.agent.core.action.base import ActionOutput
    
    # 保存原始方法
    _original_act = ConversableAgent.act
    _original_build = ConversableAgent.build
    _original_thinking = ConversableAgent.thinking if hasattr(ConversableAgent, 'thinking') else None
    
    async def patched_build(self: ConversableAgent) -> "ConversableAgent":
        """补丁后的build方法"""
        result = await _original_build(self)
        
        # 初始化VIS
        AgentVISMixin.initialize_vis(self)
        
        return result
    
    async def patched_act(
        self: ConversableAgent,
        message,
        sender,
        reviewer=None,
        is_retry_chat=False,
        last_speaker_name=None,
        received_message=None,
        **kwargs
    ) -> List[ActionOutput]:
        """补丁后的act方法"""
        # 调用原始方法
        act_outs = await _original_act(
            self, message, sender, reviewer, is_retry_chat,
            last_speaker_name, received_message, **kwargs
        )
        
        # 处理每个ActionOutput
        if hasattr(self, '_vis_bridge') and self._vis_bridge:
            for i, (action, output) in enumerate(zip(self.actions, act_outs)):
                if output:
                    await AgentVISMixin.process_action_output_with_vis(
                        self, action, output
                    )
        
        return act_outs
    
    # 应用补丁
    ConversableAgent.build = patched_build
    ConversableAgent.act = patched_act
    
    # 添加VIS相关方法
    ConversableAgent.initialize_vis = AgentVISMixin.initialize_vis
    ConversableAgent.get_vis_parts = AgentVISMixin.get_vis_parts
    ConversableAgent.clear_vis_parts = AgentVISMixin.clear_vis_parts
    
    logger.info("[VIS] 已为ConversableAgent应用VIS集成补丁")


def unpatch_conversable_agent():
    """
    移除补丁 - 恢复原始方法
    
    用于测试或回滚
    """
    from derisk.agent.core.base_agent import ConversableAgent
    
    # 这里需要保存原始方法的引用
    # 实际使用时应该更仔细地管理
    logger.warning("[VIS] unpatch_conversable_agent 暂未实现完整恢复逻辑")


# 自动应用补丁的条件
AUTO_PATCH_ENABLED = True

if AUTO_PATCH_ENABLED:
    # 延迟应用补丁,避免循环导入
    import atexit
    
    def _auto_patch():
        try:
            patch_conversable_agent()
        except Exception as e:
            logger.warning(f"[VIS] 自动应用补丁失败: {e}")
    
    # 在首次导入时应用
    # 实际应该通过配置控制
    atexit.register(lambda: logger.info("[VIS] 模块退出"))