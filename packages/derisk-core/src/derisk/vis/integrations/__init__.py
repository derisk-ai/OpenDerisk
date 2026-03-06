"""
VIS系统集成初始化

自动应用所有补丁和集成
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# 全局初始化标志
_INITIALIZED = False


def initialize_vis_system():
    """
    初始化VIS系统
    
    包括:
    1. 应用Core Agent补丁
    2. 应用Core_V2 Agent补丁
    3. 初始化实时推送系统
    4. 注册全局组件
    """
    global _INITIALIZED
    
    if _INITIALIZED:
        logger.info("[VIS] 系统已初始化,跳过")
        return
    
    logger.info("[VIS] 开始初始化VIS系统...")
    
    try:
        # 1. 应用Core Agent补丁
        from .integrations.core_integration import patch_conversable_agent
        try:
            patch_conversable_agent()
            logger.info("[VIS] ✅ Core Agent集成完成")
        except Exception as e:
            logger.warning(f"[VIS] ❌ Core Agent集成失败: {e}")
        
        # 2. 应用Core_V2 Agent补丁
        from .integrations.core_v2_integration import patch_agent_base_v2
        try:
            patch_agent_base_v2()
            logger.info("[VIS] ✅ Core_V2 Agent集成完成")
        except Exception as e:
            logger.debug(f"[VIS] Core_V2 Agent集成跳过: {e}")
        
        # 3. 初始化实时推送
        from .realtime import initialize_realtime_pusher
        try:
            initialize_realtime_pusher()
            logger.info("[VIS] ✅ 实时推送系统初始化完成")
        except Exception as e:
            logger.warning(f"[VIS] 实时推送系统初始化失败: {e}")
        
        # 4. 注册默认VIS组件
        from .unified_converter import UnifiedVisManager
        try:
            converter = UnifiedVisManager.get_converter()
            logger.info("[VIS] ✅ 统一转换器初始化完成")
        except Exception as e:
            logger.warning(f"[VIS] 统一转换器初始化失败: {e}")
        
        _INITIALIZED = True
        logger.info("[VIS] 🎉 VIS系统初始化完成!")
        
    except Exception as e:
        logger.error(f"[VIS] 系统初始化失败: {e}", exc_info=True)
        raise


def get_vis_system_status() -> dict:
    """
    获取VIS系统状态
    
    Returns:
        状态信息字典
    """
    from .unified_converter import UnifiedVisManager
    
    status = {
        "initialized": _INITIALIZED,
        "core_integration": False,
        "core_v2_integration": False,
        "realtime_pusher": False,
    }
    
    try:
        from derisk.agent.core.base_agent import ConversableAgent
        if hasattr(ConversableAgent, 'initialize_vis'):
            status["core_integration"] = True
    except:
        pass
    
    try:
        from derisk.agent.core_v2.agent_base import AgentBase
        if hasattr(AgentBase, 'emit_thinking'):
            status["core_v2_integration"] = True
    except:
        pass
    
    try:
        from .realtime import get_realtime_pusher
        if get_realtime_pusher() is not None:
            status["realtime_pusher"] = True
    except:
        pass
    
    try:
        converter = UnifiedVisManager.get_converter()
        stats = converter.get_statistics()
        status["converter_stats"] = stats
    except:
        pass
    
    return status


# 自动初始化(可通过环境变量控制)
import os

AUTO_INITIALIZE = os.getenv("DERISK_VIS_AUTO_INIT", "true").lower() == "true"

if AUTO_INITIALIZE:
    # 延迟初始化,在首次使用时触发
    import atexit
    atexit.register(lambda: logger.info("[VIS] 模块退出"))