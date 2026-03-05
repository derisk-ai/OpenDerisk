"""
历史消息API修复补丁

修复Core V2的历史消息无法显示的问题
让API能够同时支持Core V1和Core V2的消息读取
"""
import logging
from typing import List, Union, Dict, Any

logger = logging.getLogger(__name__)


def get_history_messages_unified(
    self, 
    request: Union['ServeRequest', Dict[str, Any]]
) -> List['MessageVo']:
    """
    统一的历史消息获取方法
    
    支持Core V1（chat_history表）和Core V2（gpts_messages表）
    
    Args:
        request: 请求参数
        
    Returns:
        MessageVo列表
    """
    from derisk_serve.conversation.api.schemas import MessageVo
    from derisk_serve.conversation.service.service import ServeRequest
    
    conv_uid = request.conv_uid if isinstance(request, ServeRequest) else request.get('conv_uid')
    
    try:
        # 先尝试从gpts_messages读取（Core V2）
        messages_v2 = _get_messages_from_gpts(conv_uid)
        
        if messages_v2:
            logger.info(f"Loaded {len(messages_v2)} messages from gpts_messages for conv {conv_uid}")
            return messages_v2
    except Exception as e:
        logger.warning(f"Failed to load from gpts_messages: {e}")
    
    try:
        # 回退到chat_history读取（Core V1）
        messages_v1 = _get_messages_from_chat_history(self, request)
        
        if messages_v1:
            logger.info(f"Loaded {len(messages_v1)} messages from chat_history for conv {conv_uid}")
            return messages_v1
    except Exception as e:
        logger.warning(f"Failed to load from chat_history: {e}")
    
    # 都没有，返回空
    logger.warning(f"No messages found for conv {conv_uid}")
    return []


def _get_messages_from_gpts(conv_uid: str) -> List['MessageVo']:
    """从gpts_messages表读取消息（Core V2）
    
    Args:
        conv_uid: 对话ID
        
    Returns:
        MessageVo列表
    """
    from derisk.storage.unified_message_dao import UnifiedMessageDAO
    from derisk_serve.conversation.api.schemas import MessageVo
    from derisk.core.interface.message import _append_view_messages
    from derisk.core.interface.message import HumanMessage, AIMessage
    
    unified_dao = UnifiedMessageDAO()
    
    # 使用同步方法（因为当前API是同步的）
    import asyncio
    unified_messages = asyncio.run(unified_dao.get_messages_by_conv_id(conv_uid))
    
    if not unified_messages:
        return []
    
    # 转换为BaseMessage格式
    base_messages = []
    for unified_msg in unified_messages:
        base_msg = unified_msg.to_base_message()
        base_msg.round_index = unified_msg.rounds
        base_messages.append(base_msg)
    
    # 添加ViewMessage
    messages_with_view = _append_view_messages(base_messages)
    
    # 转换为MessageVo
    result = []
    for idx, msg in enumerate(messages_with_view):
        feedback = {}
        
        result.append(
            MessageVo(
                role=msg.type,
                context=msg.content,
                order=msg.round_index,
                model_name=None,
                feedback=feedback,
            )
        )
    
    return result


def _get_messages_from_chat_history(
    service,
    request: Union['ServeRequest', Dict[str, Any]]
) -> List['MessageVo']:
    """从chat_history表读取消息（Core V1）
    
    Args:
        service: Service实例
        request: 请求参数
        
    Returns:
        MessageVo列表
    """
    from derisk_serve.conversation.service.service import ServeRequest
    from derisk.core.interface.message import _append_view_messages
    from derisk_serve.file.serve import Serve as FileServe
    from derisk_serve.feedback.service import get_service as get_feedback_service
    from derisk_serve.conversation.api.schemas import MessageVo
    
    file_serve = FileServe.get_instance(service.system_app)
    
    # 创建StorageConversation
    conv = service.create_storage_conv(request)
    
    # 检查是否有消息
    if not conv.messages:
        return []
    
    # 添加ViewMessage
    messages = _append_view_messages(conv.messages)
    
    # 加载反馈
    feedback_service = get_feedback_service()
    feedbacks = feedback_service.list_conv_feedbacks(
        conv_uid=request.conv_uid if isinstance(request, ServeRequest) else request.get('conv_uid')
    )
    fb_map = {fb.message_id: fb.to_dict() for fb in feedbacks}
    
    # 转换为MessageVo
    result = []
    for msg in messages:
        feedback = {}
        if (
            msg.round_index is not None
            and fb_map.get(str(msg.round_index)) is not None
        ):
            feedback = fb_map.get(str(msg.round_index))
        
        result.append(
            MessageVo(
                role=msg.type,
                context=msg.get_view_markdown_text(file_serve.replace_uri),
                order=msg.round_index,
                model_name=service.config.default_model,
                feedback=feedback,
            )
        )
    
    return result


# Monkey patch原方法
def apply_patch():
    """应用补丁"""
    from derisk_serve.conversation.service.service import Service
    
    # 保存原方法
    Service._original_get_history_messages = Service.get_history_messages
    
    # 替换为统一方法
    Service.get_history_messages = get_history_messages_unified
    
    logger.info("Applied unified message history patch")


if __name__ == "__main__":
    # 测试补丁
    print("This is a patch module. Import and call apply_patch() to apply.")