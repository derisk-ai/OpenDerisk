import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from derisk.component import SystemApp
from derisk_serve.core import Result

from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..service.service import MultimodalService

logger = logging.getLogger(__name__)

router = APIRouter()
global_system_app: Optional[SystemApp] = None


def get_service() -> MultimodalService:
    return global_system_app.get_component(
        SERVE_SERVICE_COMPONENT_NAME, MultimodalService
    )


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    bucket: Optional[str] = Form(default=None),
    conv_uid: Optional[str] = Form(default=None),
    message_id: Optional[str] = Form(default=None),
    service: MultimodalService = Depends(get_service),
):
    """上传多模态文件.

    文件会被存储到文件系统，并记录元数据到会话中。
    
    Args:
        file: 上传的文件
        bucket: 存储桶名称
        conv_uid: 会话ID，用于关联文件到会话
        message_id: 消息ID，用于关联文件到特定消息
        
    Returns:
        文件信息，包括URI、预览URL等
    """
    try:
        file_info = service.upload_file(
            file_name=file.filename,
            file_data=file.file,
            bucket=bucket,
            conv_id=conv_uid,
            message_id=message_id,
            custom_metadata={"conv_uid": conv_uid} if conv_uid else None,
        )
        return Result.succ(service.get_file_info(file_info.uri))
    except ValueError as e:
        return Result.failed(msg=str(e))


@router.get("/files/{conv_id}")
async def list_session_files(
    conv_id: str,
    service: MultimodalService = Depends(get_service),
):
    """获取会话中用户上传的文件列表.
    
    Args:
        conv_id: 会话ID
        
    Returns:
        文件列表，包含文件名、类型、预览URL等信息
    """
    files = await service.list_user_files(conv_id)
    return Result.succ(files)


@router.post("/process")
async def process_multimodal(
    text: Optional[str] = Form(default=None),
    file_uris: Optional[str] = Form(default=None),
    preferred_provider: Optional[str] = Form(default=None),
    service: MultimodalService = Depends(get_service),
):
    """处理多模态内容，自动匹配合适的模型.
    
    Args:
        text: 文本内容
        file_uris: 文件URI列表，逗号分隔
        preferred_provider: 首选模型提供商
        
    Returns:
        处理后的内容、匹配的模型、文件信息
    """
    uris = file_uris.split(",") if file_uris else None
    result = service.process_multimodal_content(
        text=text,
        file_uris=uris,
        preferred_provider=preferred_provider,
    )
    return Result.succ(result)


@router.get("/models")
async def list_models(
    capability: Optional[str] = None,
    provider: Optional[str] = None,
    service: MultimodalService = Depends(get_service),
):
    """列出支持的多模态模型.
    
    Args:
        capability: 按能力筛选 (image_input, audio_input, video_input等)
        provider: 按提供商筛选 (openai, anthropic, alibaba, google等)
        
    Returns:
        模型列表
    """
    models = service.list_supported_models(capability=capability, provider=provider)
    return Result.succ(models)


@router.get("/match")
async def match_model(
    media_types: str,
    preferred_provider: Optional[str] = None,
    service: MultimodalService = Depends(get_service),
):
    """根据媒体类型匹配合适的模型.
    
    Args:
        media_types: 媒体类型列表，逗号分隔 (image, audio, video, document)
        preferred_provider: 首选提供商
        
    Returns:
        匹配的模型信息
    """
    from ..model_matcher import MediaType
    
    types = [MediaType(t.strip()) for t in media_types.split(",") if t.strip()]
    model_info = service.model_matcher.match_model_for_media_types(
        media_types=types,
        preferred_provider=preferred_provider,
    )
    
    if model_info:
        return Result.succ({
            "model_name": model_info.model_name,
            "provider": model_info.provider,
            "capabilities": [c.value for c in model_info.capabilities],
        })
    return Result.failed(msg="No matching model found")


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    global global_system_app
    global_system_app = system_app
    system_app.register(MultimodalService, config=config)