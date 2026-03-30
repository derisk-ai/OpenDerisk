"""
统一用户交互网关实现
"""

import uuid
import logging
from typing import Any, Dict, List, Optional

from .models import (
    InteractionType,
    InteractionStatus,
    InteractionRequest,
    InteractionResponse,
    FileUploadRequest,
    FileUploadResponse,
)

logger = logging.getLogger(__name__)


class UnifiedInteractionGateway:
    """
    统一用户交互网关

    核心职责：
    1. 统一的用户输入请求
    2. 统一的文件上传
    3. 自动适配V1/V2交互协议
    """

    def __init__(self, system_app: Any = None):
        self._system_app = system_app
        self._pending_requests: Dict[str, InteractionRequest] = {}
        self._completed_responses: Dict[str, InteractionResponse] = {}

    async def request_user_input(
        self,
        question: str,
        interaction_type: InteractionType = InteractionType.TEXT_INPUT,
        options: Optional[List[str]] = None,
        default_value: Optional[str] = None,
        timeout: int = 300,
        agent_version: str = "v2",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InteractionResponse:
        """
        统一的用户输入请求

        Args:
            question: 问题内容
            interaction_type: 交互类型
            options: 选项列表（用于选择类型）
            default_value: 默认值
            timeout: 超时时间（秒）
            agent_version: Agent版本
            metadata: 元数据

        Returns:
            InteractionResponse: 用户响应
        """
        request_id = str(uuid.uuid4().hex)

        request = InteractionRequest(
            request_id=request_id,
            interaction_type=interaction_type,
            question=question,
            options=options,
            default_value=default_value,
            timeout=timeout,
            metadata=metadata or {},
        )

        self._pending_requests[request_id] = request

        logger.info(
            f"[UnifiedInteractionGateway] 发起用户交互请求: "
            f"request_id={request_id}, type={interaction_type}, version={agent_version}"
        )

        if agent_version == "v2":
            response = await self._handle_v2_interaction(request)
        else:
            response = await self._handle_v1_interaction(request)

        self._completed_responses[request_id] = response
        self._pending_requests.pop(request_id, None)

        return response

    async def request_file_upload(
        self,
        allowed_types: Optional[List[str]] = None,
        max_size: int = 10 * 1024 * 1024,
        multiple: bool = False,
        agent_version: str = "v2",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FileUploadResponse:
        """
        统一的文件上传请求

        Args:
            allowed_types: 允许的文件类型
            max_size: 最大文件大小
            multiple: 是否允许多文件
            agent_version: Agent版本
            metadata: 元数据

        Returns:
            FileUploadResponse: 文件上传响应
        """
        request_id = str(uuid.uuid4().hex)

        request = FileUploadRequest(
            request_id=request_id,
            allowed_types=allowed_types or [],
            max_size=max_size,
            multiple=multiple,
            metadata=metadata or {},
        )

        logger.info(
            f"[UnifiedInteractionGateway] 发起文件上传请求: "
            f"request_id={request_id}, version={agent_version}"
        )

        if agent_version == "v2":
            response = await self._handle_v2_file_upload(request)
        else:
            response = await self._handle_v1_file_upload(request)

        return response

    async def submit_response(
        self, request_id: str, response: str, metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        提交用户响应

        Args:
            request_id: 请求ID
            response: 用户响应
            metadata: 元数据

        Returns:
            bool: 是否提交成功
        """
        request = self._pending_requests.get(request_id)
        if not request:
            logger.warning(
                f"[UnifiedInteractionGateway] 请求不存在或已过期: {request_id}"
            )
            return False

        interaction_response = InteractionResponse(
            request_id=request_id,
            response=response,
            status=InteractionStatus.COMPLETED,
            metadata=metadata or {},
        )

        self._completed_responses[request_id] = interaction_response
        self._pending_requests.pop(request_id, None)

        logger.info(f"[UnifiedInteractionGateway] 用户响应已提交: {request_id}")
        return True

    async def get_pending_requests(self) -> List[InteractionRequest]:
        """获取待处理的请求列表"""
        return list(self._pending_requests.values())

    async def get_response(self, request_id: str) -> Optional[InteractionResponse]:
        """获取已完成的响应"""
        return self._completed_responses.get(request_id)

    async def _handle_v1_interaction(
        self, request: InteractionRequest
    ) -> InteractionResponse:
        """
        处理V1交互

        使用原有的InteractionGateway
        """
        try:
            from derisk.agent.interaction.interaction_gateway import (
                get_interaction_gateway,
                InteractionStatus as V1Status,
            )

            gateway = get_interaction_gateway()

            v1_response = await gateway.request_input(
                request.question, options=request.options, timeout=request.timeout
            )

            status_map = {
                V1Status.COMPLETED: InteractionStatus.COMPLETED,
                V1Status.TIMEOUT: InteractionStatus.TIMEOUT,
                V1Status.CANCELLED: InteractionStatus.CANCELLED,
            }

            return InteractionResponse(
                request_id=request.request_id,
                response=v1_response.response,
                status=status_map.get(v1_response.status, InteractionStatus.COMPLETED),
                metadata={"version": "v1"},
            )
        except Exception as e:
            logger.error(f"[UnifiedInteractionGateway] V1交互处理失败: {e}")
            return InteractionResponse(
                request_id=request.request_id,
                response=request.default_value or "",
                status=InteractionStatus.COMPLETED,
                metadata={"error": str(e)},
            )

    async def _handle_v2_interaction(
        self, request: InteractionRequest
    ) -> InteractionResponse:
        """
        处理V2交互

        使用V2的交互工具
        """
        try:
            from derisk.agent.tools.builtin.interaction import AskUserTool

            tool = AskUserTool()
            result = await tool.execute(
                question=request.question,
                options=request.options,
                timeout=request.timeout,
            )

            return InteractionResponse(
                request_id=request.request_id,
                response=result.get("response", request.default_value or ""),
                status=InteractionStatus.COMPLETED,
                metadata={"version": "v2", "result": result},
            )
        except Exception as e:
            logger.error(f"[UnifiedInteractionGateway] V2交互处理失败: {e}")
            return InteractionResponse(
                request_id=request.request_id,
                response=request.default_value or "",
                status=InteractionStatus.COMPLETED,
                metadata={"error": str(e)},
            )

    async def _handle_v1_file_upload(
        self, request: FileUploadRequest
    ) -> FileUploadResponse:
        """处理V1文件上传"""
        return FileUploadResponse(
            request_id=request.request_id,
            file_ids=[],
            file_names=[],
            status=InteractionStatus.CANCELLED,
            metadata={"message": "V1文件上传未实现"},
        )

    async def _handle_v2_file_upload(
        self, request: FileUploadRequest
    ) -> FileUploadResponse:
        """处理V2文件上传"""
        try:
            from derisk.agent.tools.builtin.interaction import (
                AskUserTool as UploadFileTool,
            )

            tool = UploadFileTool()
            result = await tool.execute(
                allowed_types=request.allowed_types,
                max_size=request.max_size,
                multiple=request.multiple,
            )

            return FileUploadResponse(
                request_id=request.request_id,
                file_ids=result.get("file_ids", []),
                file_names=result.get("file_names", []),
                status=InteractionStatus.COMPLETED,
                metadata={"version": "v2"},
            )
        except Exception as e:
            logger.error(f"[UnifiedInteractionGateway] V2文件上传失败: {e}")
            return FileUploadResponse(
                request_id=request.request_id,
                file_ids=[],
                file_names=[],
                status=InteractionStatus.CANCELLED,
                metadata={"error": str(e)},
            )
