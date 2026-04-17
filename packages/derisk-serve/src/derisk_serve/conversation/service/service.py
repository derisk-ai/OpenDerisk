import logging
from typing import Any, Dict, List, Optional, Union

from derisk.component import SystemApp

logger = logging.getLogger(__name__)
from derisk.core import (
    MessageStorageItem,
    StorageConversation,
    StorageInterface,
)
from derisk.core.interface.message import _append_view_messages
from derisk.storage.metadata._base_dao import REQ, RES
from derisk.util.pagination_utils import PaginationResult
from derisk_serve.core import BaseService

from ...feedback.api.endpoints import get_service
from ..api.schemas import MessageVo, ServeRequest, ServerResponse
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..models.models import ServeDao, ServeEntity


## Compatible with historical old messages
def vis_name_change(vis_message: str) -> str:
    """Change vis tag name use new name."""
    replacements = {
        "```vis-chart": "```vis-db-chart",
    }

    for old_tag, new_tag in replacements.items():
        vis_message = vis_message.replace(old_tag, new_tag)

    return vis_message


class Service(BaseService[ServeEntity, ServeRequest, ServerResponse]):
    """The service class for Conversation"""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: ServeConfig,
        dao: Optional[ServeDao] = None,
        storage: Optional[StorageInterface[StorageConversation, Any]] = None,
        message_storage: Optional[StorageInterface[MessageStorageItem, Any]] = None,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: ServeDao = dao
        self._storage = storage
        self._message_storage = message_storage
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service

        Args:
            system_app (SystemApp): The system app
        """
        super().init_app(system_app)
        self._dao = self._dao or ServeDao(self._serve_config)
        self._system_app = system_app

    @property
    def dao(self) -> ServeDao:
        """Returns the internal DAO."""
        return self._dao

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._serve_config

    def create(self, request: REQ) -> RES:
        raise NotImplementedError()

    @property
    def conv_storage(self) -> StorageInterface:
        """The conversation storage, store the conversation items."""
        if self._storage:
            return self._storage
        from ..serve import Serve

        return Serve.call_on_current_serve(
            self._system_app, lambda serve: serve.conv_storage
        )

    @property
    def message_storage(self) -> StorageInterface:
        """The message storage, store the messages of one conversation."""
        if self._message_storage:
            return self._message_storage
        from ..serve import Serve

        return Serve.call_on_current_serve(
            self._system_app,
            lambda serve: serve.message_storage,
        )

    def create_storage_conv(
        self, request: Union[ServeRequest, Dict[str, Any]], load_message: bool = True
    ) -> StorageConversation:
        conv_storage = self.conv_storage
        message_storage = self.message_storage
        if not conv_storage or not message_storage:
            raise RuntimeError(
                "Can't get the conversation storage or message storage from current "
                "serve component."
            )
        if isinstance(request, dict):
            request = ServeRequest(**request)
        storage_conv: StorageConversation = StorageConversation(
            conv_uid=request.conv_uid,
            chat_mode=request.chat_mode,
            user_name=request.user_name,
            sys_code=request.sys_code,
            conv_storage=conv_storage,
            message_storage=message_storage,
            load_message=load_message,
        )
        return storage_conv

    def update(self, request: ServeRequest) -> ServerResponse:
        """Update a Conversation entity

        Args:
            request (ServeRequest): The request

        Returns:
            ServerResponse: The response
        """
        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = {
            # "id": request.id
        }
        return self.dao.update(query_request, update_request=request)

    def get(self, request: ServeRequest) -> Optional[ServerResponse]:
        """Get a Conversation entity

        Args:
            request (ServeRequest): The request

        Returns:
            ServerResponse: The response
        """
        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = request
        return self.dao.get_one(query_request)

    def delete(self, request: ServeRequest) -> None:
        """Delete current conversation and its messages

        Args:
            request (ServeRequest): The request
        """
        conv: StorageConversation = self.create_storage_conv(request)
        conv.delete()

    def clear(self, request: ServeRequest) -> None:
        """Clear current conversation and its messages

        Args:
            request (ServeRequest): The request
        """
        conv: StorageConversation = self.create_storage_conv(request)
        conv.clear()

    def get_list(self, request: ServeRequest) -> List[ServerResponse]:
        """Get a list of Conversation entities

        Args:
            request (ServeRequest): The request

        Returns:
            List[ServerResponse]: The response
        """
        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = request
        return self.dao.get_list(query_request)

    def get_list_by_page(
        self,
        request: ServeRequest,
        page: int,
        page_size: int,
        filter: Optional[str] = None,
    ) -> PaginationResult[ServerResponse]:
        """Get a list of Conversation entities by page

        Args:
            request (ServeRequest): The request
            page (int): The page number
            page_size (int): The page size

        Returns:
            List[ServerResponse]: The response
        """
        import asyncio
        import concurrent.futures
        from derisk.storage.unified_message_dao import UnifiedMessageDAO

        try:
            unified_dao = UnifiedMessageDAO()

            def _run_async():
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(
                        unified_dao.list_conversations(
                            user_id=request.user_name,
                            sys_code=request.sys_code,
                            filter_text=filter,
                            page=page,
                            page_size=page_size,
                        )
                    )
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_async)
                result = future.result(timeout=30)

            items = [
                ServerResponse(
                    conv_uid=item.conv_id,
                    conv_session_id=item.conv_session_id,
                    user_input=item.goal,
                    chat_mode=item.chat_mode,
                    app_code=item.app_code,
                    user_name=item.user_id,
                    sys_code=request.sys_code,
                    gmt_created=item.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if item.created_at
                    else None,
                    gmt_modified=item.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                    if item.updated_at
                    else None,
                )
                for item in result["items"]
            ]

            return PaginationResult(
                items=items,
                total_count=result["total_count"],
                total_pages=result["total_pages"],
                page=result["page"],
                page_size=result["page_size"],
            )
        except Exception as e:
            logger.warning(
                f"Failed to use unified list_conversations, fallback to v1: {e}"
            )
            if filter:
                additional_filters = [ServeEntity.summary.like(f"%{filter}%")]
            else:
                additional_filters = None
            return self.dao.get_conv_by_page(
                request, page, page_size, additional_filters=additional_filters
            )

    def get_history_messages(
        self, request: Union[ServeRequest, Dict[str, Any]]
    ) -> List[MessageVo]:
        """Get a list of Conversation entities

        Args:
            request (ServeRequest): The request

        Returns:
            List[ServerResponse]: The response
        """
        import time

        _total_start = time.time()

        # ===== 统一消息读取策略 =====
        # 先尝试从gpts_messages读取（Core V2）
        # 如果没有，再从chat_history读取（Core V1）

        conv_uid = (
            request.conv_uid
            if isinstance(request, ServeRequest)
            else request.get("conv_uid")
        )

        # 1. 尝试从gpts_messages读取（Core V2）
        _step_start = time.time()
        messages_v2 = self._get_messages_from_gpts(conv_uid)
        logger.info(
            f"[MESSAGES_HISTORY][PERF] 从gpts_messages读取耗时: {(time.time() - _step_start) * 1000:.2f}ms"
        )

        if messages_v2:
            logger.info(
                f"Loaded {len(messages_v2)} messages from gpts_messages for conv {conv_uid}"
            )
            logger.info(
                f"[MESSAGES_HISTORY][PERF] get_history_messages总耗时: {(time.time() - _total_start) * 1000:.2f}ms"
            )
            return messages_v2

        # 2. 回退到从chat_history读取（Core V1）
        _step_start = time.time()
        from ...file.serve import Serve as FileServe

        file_serve = FileServe.get_instance(self.system_app)
        logger.info(
            f"[MESSAGES_HISTORY][PERF] 获取FileServe耗时: {(time.time() - _step_start) * 1000:.2f}ms"
        )

        _step_start = time.time()
        conv: StorageConversation = self.create_storage_conv(request)
        logger.info(
            f"[MESSAGES_HISTORY][PERF] 创建StorageConversation耗时: {(time.time() - _step_start) * 1000:.2f}ms"
        )

        result = []

        _step_start = time.time()
        messages = _append_view_messages(conv.messages)
        logger.info(
            f"[MESSAGES_HISTORY][PERF] _append_view_messages耗时: {(time.time() - _step_start) * 1000:.2f}ms"
        )

        if not messages:
            logger.warning(f"No messages found for conv {conv_uid}")
            logger.info(
                f"[MESSAGES_HISTORY][PERF] get_history_messages总耗时: {(time.time() - _total_start) * 1000:.2f}ms (无消息)"
            )
            return []

        _step_start = time.time()
        feedback_service = get_service()

        feedbacks = feedback_service.list_conv_feedbacks(conv_uid=request.conv_uid)
        fb_map = {fb.message_id: fb.to_dict() for fb in feedbacks}
        logger.info(
            f"[MESSAGES_HISTORY][PERF] 查询feedback耗时: {(time.time() - _step_start) * 1000:.2f}ms"
        )

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
                    model_name=self.config.default_model,
                    feedback=feedback,
                )
            )
        logger.info(
            f"[MESSAGES_HISTORY][PERF] get_history_messages总耗时: {(time.time() - _total_start) * 1000:.2f}ms"
        )
        return result

    def _get_messages_from_gpts(self, conv_uid: str) -> List[MessageVo]:
        """从gpts_messages表读取消息（Core V2）

        Args:
            conv_uid: 对话ID，可能是 conv_id 或 conv_session_id

        Returns:
            MessageVo列表，如果没有消息返回空列表
        """
        import time

        _start = time.time()

        try:
            from derisk_serve.agent.db.gpts_messages_db import GptsMessagesDao
            from derisk.core.interface.message import _append_view_messages

            msg_dao = GptsMessagesDao()

            # conv_id 格式: uuid_数字 (如 b63fbb0e-38d8-11f1-8578-b5920cfbee2e_2)
            # conv_session_id 格式: 纯 uuid (如 b63fbb0e-38d8-11f1-8578-b5920cfbee2e)
            # 前端传入的 conv_uid 可能是 conv_id (带 _数字 后缀)，需要提取 conv_session_id

            # 判断是否是 conv_id 格式（带 _数字 后缀）
            is_conv_id_format = "_" in conv_uid and conv_uid.split("_")[-1].isdigit()

            # 提取 conv_session_id（去掉 _数字 后缀）
            if is_conv_id_format:
                # conv_id 格式，提取 conv_session_id
                conv_session_id = conv_uid.rsplit("_", 1)[0]
                _step_start = time.time()
                # 先尝试用 conv_session_id 查询（获取整个会话的所有消息）
                gpts_messages = msg_dao.get_by_conv_session_id(conv_session_id)
                logger.info(
                    f"[MESSAGES_HISTORY][PERF] 查询gpts_messages(conv_session_id={conv_session_id})耗时: {(time.time() - _step_start) * 1000:.2f}ms, 消息数: {len(gpts_messages)}"
                )
                # 如果没有找到，再尝试用原始 conv_id 查询
                if not gpts_messages:
                    _step_start = time.time()
                    gpts_messages = msg_dao.get_by_conv_id_sync(conv_uid)
                    logger.info(
                        f"[MESSAGES_HISTORY][PERF] 回退查询gpts_messages(conv_id={conv_uid})耗时: {(time.time() - _step_start) * 1000:.2f}ms, 消息数: {len(gpts_messages)}"
                    )
            else:
                # conv_session_id 格式，直接查询
                _step_start = time.time()
                gpts_messages = msg_dao.get_by_conv_session_id(conv_uid)
                logger.info(
                    f"[MESSAGES_HISTORY][PERF] 查询gpts_messages(conv_session_id={conv_uid})耗时: {(time.time() - _step_start) * 1000:.2f}ms, 消息数: {len(gpts_messages)}"
                )

            if not gpts_messages:
                logger.info(
                    f"[MESSAGES_HISTORY][PERF] 总耗时: {(time.time() - _start) * 1000:.2f}ms (无消息)"
                )
                return []

            _step_start = time.time()
            base_messages = []
            for unified_msg in gpts_messages:
                base_msg = unified_msg.to_base_message()
                base_msg.round_index = unified_msg.rounds
                base_messages.append(base_msg)
            logger.info(
                f"[MESSAGES_HISTORY][PERF] 转换为BaseMessage耗时: {(time.time() - _step_start) * 1000:.2f}ms"
            )

            _step_start = time.time()
            messages_with_view = _append_view_messages(base_messages)
            logger.info(
                f"[MESSAGES_HISTORY][PERF] 添加ViewMessage耗时: {(time.time() - _step_start) * 1000:.2f}ms"
            )

            _step_start = time.time()
            result = []
            for msg in messages_with_view:
                result.append(
                    MessageVo(
                        role=msg.type,
                        context=msg.content,
                        order=msg.round_index,
                        model_name=None,
                        feedback={},
                    )
                )
            logger.info(
                f"[MESSAGES_HISTORY][PERF] 转换为MessageVo耗时: {(time.time() - _step_start) * 1000:.2f}ms"
            )

            logger.info(
                f"[MESSAGES_HISTORY][PERF] 总耗时: {(time.time() - _start) * 1000:.2f}ms, 返回消息数: {len(result)}"
            )
            return result

        except Exception as e:
            logger.warning(f"Failed to read from gpts_messages: {e}")
            logger.info(
                f"[MESSAGES_HISTORY][PERF] 异常总耗时: {(time.time() - _start) * 1000:.2f}ms"
            )
            return []
