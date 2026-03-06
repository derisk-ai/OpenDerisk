"""
Core_V2 Agent VIS集成扩展

将新的Part系统集成到Core_V2 Agent的运行流程中
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from derisk.vis.bridges.core_v2_bridge import CoreV2VisBridge
from derisk.vis.unified_converter import UnifiedVisConverter, UnifiedVisManager

if TYPE_CHECKING:
    from derisk.agent.core_v2.agent_base import AgentBase
    from derisk.agent.core_v2.visualization.progress import ProgressBroadcaster

logger = logging.getLogger(__name__)


class AgentV2VISMixin:
    """
    AgentBase VIS扩展Mixin
    
    为Core_V2的AgentBase提供统一VIS能力
    """
    
    _vis_bridge: Optional[CoreV2VisBridge] = None
    _vis_converter: Optional[UnifiedVisConverter] = None
    _progress_broadcaster: Optional["ProgressBroadcaster"] = None
    
    @classmethod
    def initialize_vis_v2(
        cls,
        agent: "AgentBase",
        broadcaster: Optional["ProgressBroadcaster"] = None
    ):
        """
        初始化Agent V2的VIS能力
        
        Args:
            agent: AgentBase实例
            broadcaster: ProgressBroadcaster实例(可选)
        """
        # 获取或创建统一转换器
        agent._vis_converter = UnifiedVisManager.get_converter()
        
        # 创建桥接层
        agent._vis_bridge = CoreV2VisBridge(
            broadcaster=broadcaster,
            auto_subscribe=False  # 延迟订阅
        )
        
        # 保存broadcaster引用
        agent._progress_broadcaster = broadcaster
        
        # 注册到转换器
        if broadcaster:
            agent._vis_converter.register_core_v2_broadcaster(broadcaster)
        
        logger.info(f"[VIS] 已为Agent V2 初始化VIS能力")
    
    def start_vis_streaming(self):
        """开始VIS流式输出"""
        if self._vis_bridge:
            self._vis_bridge.start()
            logger.info(f"[VIS] Agent V2 开始VIS流式输出")
    
    def stop_vis_streaming(self):
        """停止VIS流式输出"""
        if self._vis_bridge:
            self._vis_bridge.stop()
            logger.info(f"[VIS] Agent V2 停止VIS流式输出")
    
    async def emit_thinking(self, content: str, **metadata):
        """
        发送思考事件
        
        Args:
            content: 思考内容
            **metadata: 额外元数据
        """
        if not self._progress_broadcaster:
            logger.debug("[VIS] 没有ProgressBroadcaster,跳过思考事件")
            return
        
        await self._progress_broadcaster.thinking(content, **metadata)
    
    async def emit_tool_started(self, tool_name: str, args: Dict[str, Any]):
        """
        发送工具开始事件
        
        Args:
            tool_name: 工具名称
            args: 工具参数
        """
        if not self._progress_broadcaster:
            return
        
        await self._progress_broadcaster.tool_started(tool_name, args)
    
    async def emit_tool_completed(
        self,
        tool_name: str,
        result: str,
        execution_time: Optional[float] = None
    ):
        """
        发送工具完成事件
        
        Args:
            tool_name: 工具名称
            result: 执行结果
            execution_time: 执行时间
        """
        if not self._progress_broadcaster:
            return
        
        metadata = {}
        if execution_time is not None:
            metadata["execution_time"] = execution_time
        
        await self._progress_broadcaster.tool_completed(tool_name, result)
    
    async def emit_tool_failed(self, tool_name: str, error: str):
        """
        发送工具失败事件
        
        Args:
            tool_name: 工具名称
            error: 错误信息
        """
        if not self._progress_broadcaster:
            return
        
        await self._progress_broadcaster.tool_failed(tool_name, error)
    
    async def emit_progress(self, current: int, total: int, message: str = ""):
        """
        发送进度事件
        
        Args:
            current: 当前进度
            total: 总数
            message: 消息
        """
        if not self._progress_broadcaster:
            return
        
        await self._progress_broadcaster.progress(current, total, message)
    
    async def emit_complete(self, result: str = ""):
        """
        发送完成事件
        
        Args:
            result: 最终结果
        """
        if not self._progress_broadcaster:
            return
        
        await self._progress_broadcaster.complete(result)


def patch_agent_base_v2():
    """
    补丁函数 - 为AgentBase动态添加VIS能力
    """
    from derisk.agent.core_v2.agent_base import AgentBase
    from derisk.agent.core_v2.visualization.progress import ProgressBroadcaster
    
    # 保存原始方法
    _original_init = AgentBase.__init__
    _original_run = AgentBase.run
    
    def patched_init(self: AgentBase, info):
        """补丁后的__init__方法"""
        _original_init(self, info)
        
        # 创建ProgressBroadcaster(如果不存在)
        if not hasattr(self, '_progress_broadcaster') or self._progress_broadcaster is None:
            self._progress_broadcaster = ProgressBroadcaster(session_id=info.name)
        
        # 初始化VIS
        AgentV2VISMixin.initialize_vis_v2(self, self._progress_broadcaster)
    
    async def patched_run(self: AgentBase, message: str, stream: bool = True, **kwargs):
        """补丁后的run方法"""
        # 开始VIS流式输出
        AgentV2VISMixin.start_vis_streaming(self)
        
        try:
            # 发送开始思考事件
            await AgentV2VISMixin.emit_thinking(self, f"开始处理任务: {message[:50]}...")
            
            # 调用原始run方法
            async for chunk in _original_run(self, message, stream, **kwargs):
                # 根据chunk类型判断是否需要更新Part
                if chunk.startswith("[THINKING]"):
                    # 思考内容
                    thinking_content = chunk.replace("[THINKING] ", "")
                    await AgentV2VISMixin.emit_thinking(self, thinking_content)
                elif chunk.startswith("[ERROR]"):
                    # 错误内容
                    error_content = chunk.replace("[ERROR] ", "")
                    await AgentV2VISMixin.emit_tool_failed(self, "unknown", error_content)
                else:
                    # 普通内容
                    yield chunk
            
            # 发送完成事件
            await AgentV2VISMixin.emit_complete(self, "任务完成")
        
        finally:
            # 停止VIS流式输出
            AgentV2VISMixin.stop_vis_streaming(self)
    
    # 应用补丁
    AgentBase.__init__ = patched_init
    AgentBase.run = patched_run
    
    # 添加VIS方法
    AgentBase.start_vis_streaming = AgentV2VISMixin.start_vis_streaming
    AgentBase.stop_vis_streaming = AgentV2VISMixin.stop_vis_streaming
    AgentBase.emit_thinking = AgentV2VISMixin.emit_thinking
    AgentBase.emit_tool_started = AgentV2VISMixin.emit_tool_started
    AgentBase.emit_tool_completed = AgentV2VISMixin.emit_tool_completed
    AgentBase.emit_tool_failed = AgentV2VISMixin.emit_tool_failed
    AgentBase.emit_progress = AgentV2VISMixin.emit_progress
    AgentBase.emit_complete = AgentV2VISMixin.emit_complete
    
    logger.info("[VIS] 已为AgentBase V2应用VIS集成补丁")


# 条件性应用补丁
AUTO_PATCH_V2_ENABLED = True

if AUTO_PATCH_V2_ENABLED:
    try:
        # 延迟导入,避免循环依赖
        patch_agent_base_v2()
    except ImportError as e:
        logger.debug(f"[VIS] Core_V2未安装,跳过补丁: {e}")
    except Exception as e:
        logger.warning(f"[VIS] 应用Core_V2补丁失败: {e}")