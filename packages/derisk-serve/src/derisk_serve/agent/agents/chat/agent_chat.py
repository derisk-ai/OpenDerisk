import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Union, Optional, List, Dict, Any, Type, Tuple, Callable, Awaitable

import orjson
from fastapi import BackgroundTasks

from derisk import BaseComponent
from derisk._private.config import Config
from derisk.agent import (
    AgentMemory,
    ConversableAgent,
    get_agent_manager,
    AgentContext,
    UserProxyAgent,
    LLMStrategyType,
    GptsMemory,
    LLMConfig,
    ResourceType,
    ShortTermMemory,
)
from derisk.agent.core.base_team import ManagerAgent
from derisk.agent.core.memory.gpts import GptsMessage
from derisk.agent.core.plan.react.team_react_plan import AutoTeamContext
from derisk.agent.core.sandbox_manager import SandboxManager
from derisk.agent.core.schema import Status
from derisk.agent.resource import get_resource_manager, ResourceManager
from derisk.agent.resource.agent_skills import AgentSkillResource
from derisk.agent.resource.base import FILE_RESOURCES, AgentResource
from derisk.agent.util.ext_config import ExtConfigHolder
from derisk.component import ComponentType, SystemApp
from derisk.sandbox import AutoSandbox
from derisk_app.config import SandboxConfigParameters
from derisk_serve.agent.resource import DeriskSkillResource
from derisk_serve.schedule.local_scheduler import LocalScheduler
from derisk.core.interface.scheduler import Scheduler
from derisk.core import HumanMessage, StorageConversation
from derisk.model import DefaultLLMClient
from derisk.model.cluster import WorkerManagerFactory
from derisk.util.data_util import first
from derisk.util.date_utils import current_ms
from derisk.util.executor_utils import ExecutorFactory, execute_no_wait, run_async_tasks
from derisk.util.json_utils import serialize
from derisk.util.log_util import CHAT_LOGGER
from derisk.util.logger import digest
from derisk.util.tracer.tracer_impl import root_tracer, trace
from derisk.vis import VisProtocolConverter
from derisk.vis.vis_manage import get_vis_manager
from derisk_serve.agent.agents.derisks_memory import (
    MetaDerisksPlansMemory,
    MetaDerisksMessageMemory,
    MetaAgentSystemMessageMemory,
    MetaDerisksWorkLogStorage,
    MetaDerisksKanbanStorage,
    MetaDerisksTodoStorage,
    MetaDerisksFileMetadataStorage,
)
from derisk_serve.agent.db import (
    GptsConversationsEntity,
    GptsConversationsDao,
    GptsMessagesDao,
)
from derisk_serve.agent.db.gpts_tool import GptsToolDao
from derisk_serve.agent.team.base import TeamMode
from derisk_serve.building.app.api.schema_app import GptsApp, GptsAppDetail
from derisk_serve.building.app.api.schemas import ServerResponse
from derisk_serve.building.app.service.service import Service as AppService
from derisk_serve.building.config.api.schemas import ChatInParamValue, AppParamType
from derisk_serve.conversation.serve import Serve as ConversationServe

logger = logging.getLogger(__name__)

CFG = Config()


def get_app_service() -> AppService:
    return AppService.get_instance(CFG.SYSTEM_APP)


def _format_vis_msg(msg: str):
    content = json.dumps({"vis": msg}, default=serialize, ensure_ascii=False)
    return f"data:{content} \n"


async def _build_conversation(
    conv_id: str,
    select_param: Union[str, Dict[str, Any]],
    model_name: str,
    summary: str,
    app_code: str,
    conv_serve: ConversationServe,
    user_name: Optional[str] = "",
    sys_code: Optional[str] = "",
) -> StorageConversation:
    return await StorageConversation(
        conv_uid=conv_id,
        chat_mode="chat_agent",
        user_name=user_name,
        sys_code=sys_code,
        model_name=model_name,
        summary=summary,
        param_type="derisks",
        param_value=select_param,
        app_code=app_code,
        conv_storage=conv_serve.conv_storage,
        message_storage=conv_serve.message_storage,
        async_load=True,
    ).async_load()


# 使用类型别名简化复杂类型注解
AgentContextType = Union[str, AutoTeamContext]


class GlobalSandboxManagerCache:
    """全局沙箱管理器缓存，用于同一会话内共享 sandbox_manager"""

    _repository: Dict[str, SandboxManager] = {}
    _lock: Optional[asyncio.Lock] = None

    @classmethod
    def get_lock(cls) -> asyncio.Lock:
        """获取锁，延迟初始化"""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    def get(cls, key: str) -> Optional[SandboxManager]:
        """获取沙箱管理器"""
        return cls._repository.get(key)

    @classmethod
    async def get_or_create(
        cls, key: str, creator: Callable[[], Awaitable[SandboxManager]]
    ) -> SandboxManager:
        """获取或创建沙箱管理器"""
        async with cls.get_lock():
            if key in cls._repository:
                return cls._repository[key]
            sandbox_manager = await creator()
            cls._repository[key] = sandbox_manager
            logger.info(
                f"[Sandbox]创建新sandbox，key={key}, 当前运行中沙箱数量={len(cls._repository)}"
            )
            return sandbox_manager

    @classmethod
    def remove(cls, key: str):
        """移除沙箱管理器"""
        cls._repository.pop(key, None)
        logger.info(
            f"[Sandbox]移除sandbox，key={key}, 当前运行中沙箱数量={len(cls._repository)}"
        )

    @classmethod
    async def cleanup_and_remove(cls, key: str):
        """清理并移除沙箱管理器，包括 kill 沙箱客户端"""
        sandbox_manager = cls._repository.pop(key, None)
        if sandbox_manager and sandbox_manager.client:
            try:
                await sandbox_manager.client.kill()
                logger.info(
                    f"[Sandbox]清理sandbox_manager并kill，key={key}, 杀死后运行中沙箱数量={len(cls._repository)}"
                )
            except Exception as e:
                logger.exception(
                    f"[Sandbox]清理sandbox_manager失败，key={key}, error={str(e)}"
                )
        else:
            logger.info(
                f"[Sandbox]清理sandbox_manager（无client），key={key}, 当前运行中沙箱数量={len(cls._repository)}"
            )


class AgentChat(BaseComponent, ABC):
    name = ComponentType.AGENT_CHAT

    def __init__(
        self,
        system_app: SystemApp,
        gpts_memory: Optional[GptsMemory] = None,
        llm_provider: Optional[DefaultLLMClient] = None,
    ):
        self.gpts_conversations = GptsConversationsDao()
        self.gpts_messages_dao = GptsMessagesDao()

        # 初始化数据库存储后端
        file_metadata_db_storage = MetaDerisksFileMetadataStorage()
        work_log_db_storage = MetaDerisksWorkLogStorage()
        kanban_db_storage = MetaDerisksKanbanStorage()
        todo_db_storage = MetaDerisksTodoStorage()

        self.memory = gpts_memory or GptsMemory(
            plans_memory=MetaDerisksPlansMemory(),
            message_memory=MetaDerisksMessageMemory(),
            message_system_memory=MetaAgentSystemMessageMemory(),
            file_metadata_db_storage=file_metadata_db_storage,
            work_log_db_storage=work_log_db_storage,
            kanban_db_storage=kanban_db_storage,
            todo_db_storage=todo_db_storage,
        )
        self.llm_provider = llm_provider
        self.agent_memory_map = {}

        super().__init__(system_app)
        self.system_app = system_app
        self.agent_manage = get_agent_manager(system_app)

    def init_app(self, system_app: SystemApp):
        self.system_app = system_app
        # 注册全局模型配置缓存
        self._register_model_configs()

    def _register_model_configs(self):
        """注册全局模型配置到缓存"""
        from derisk.agent.util.llm.model_config_cache import (
            ModelConfigCache,
            parse_provider_configs,
        )

        global_agent_conf = self.system_app.config.get("agent.llm")
        if not global_agent_conf:
            agent_conf = self.system_app.config.get("agent")
            if isinstance(agent_conf, dict):
                global_agent_conf = agent_conf.get("llm")

        if global_agent_conf:
            model_configs = parse_provider_configs(global_agent_conf)
            if model_configs:
                ModelConfigCache.register_configs(model_configs)
                logger.info(f"Registered {len(model_configs)} models to global cache")

    async def _get_or_create_sandbox_manager(
        self, context: AgentContext, app: GptsApp, need_sandbox: bool
    ) -> Optional[SandboxManager]:
        """获取或创建沙箱管理器，同一会话内共享

        Args:
            context: Agent 上下文
            app: 应用配置
            need_sandbox: 是否需要沙箱

        Returns:
            SandboxManager 实例或 None
        """
        # 检查是否需要沙箱
        # 处理 team_context 可能是字典或对象的情况
        use_sandbox_flag = False
        if app.team_context:
            if hasattr(app.team_context, "use_sandbox"):
                use_sandbox_flag = app.team_context.use_sandbox
            elif isinstance(app.team_context, dict):
                use_sandbox_flag = app.team_context.get("use_sandbox", False)

        if not (
            (need_sandbox and use_sandbox_flag)
            or await self._have_agent_skill(
                app, context.extra.get("dynamic_resources", [])
            )
        ):
            return None

        # 检查缓存中是否已有该会话的 sandbox_manager
        sandbox_key = f"{context.conv_id}_{context.staff_no}"
        cached_manager = GlobalSandboxManagerCache.get(sandbox_key)
        if cached_manager:
            return cached_manager

        # 缓存中没有，需要创建新的
        async def _create_sandbox_manager() -> SandboxManager:
            app_config = self.system_app.config.configs.get("app_config")
            sandbox_config: Optional[SandboxConfigParameters] = app_config.sandbox
            sandbox_client = await AutoSandbox.create(
                user_id=context.staff_no or sandbox_config.user_id,
                agent=sandbox_config.agent_name,
                type=sandbox_config.type,
                template=sandbox_config.template_id,
                work_dir=sandbox_config.work_dir,
                skill_dir=sandbox_config.skill_dir,
                oss_ak=sandbox_config.oss_ak,
                oss_sk=sandbox_config.oss_sk,
                oss_endpoint=sandbox_config.oss_endpoint,
                oss_bucket_name=sandbox_config.oss_bucket_name,
            )
            sandbox_manager = SandboxManager(sandbox_client=sandbox_client)
            # 后台启动和初始化沙箱服务
            sandbox_task = asyncio.create_task(sandbox_manager.acquire())
            sandbox_manager.set_init_task(sandbox_task)
            return sandbox_manager

        return await GlobalSandboxManagerCache.get_or_create(
            sandbox_key, _create_sandbox_manager
        )

    async def _cleanup_sandbox_manager(
        self, conv_id: str, staff_no: Optional[str] = None
    ):
        """清理会话的沙箱管理器

        Args:
            conv_id: 会话ID
            staff_no: 用户ID
        """
        if staff_no:
            sandbox_key = f"{conv_id}_{staff_no}"
            await GlobalSandboxManagerCache.cleanup_and_remove(sandbox_key)

    def after_start(self):
        if not self.llm_provider:
            worker_manager = CFG.SYSTEM_APP.get_component(
                ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
            ).create()
            self.llm_provider = DefaultLLMClient(
                worker_manager, auto_convert_message=True
            )

    async def save_conversation(
        self,
        conv_session_id: str,
        agent_conv_id: str,
        current_message: StorageConversation,
        final_message: Optional[str] = None,
        err_msg: Optional[str] = None,
        chat_call_back: Optional[Callable[..., Optional[Any]]] = None,
        first_chunk_ms: Optional[int] = None,
    ):
        """最终对话保存（按格式收集最终内容，回调，并销毁缓存空间）

        Args:
            conv_session_id:会话id
            agent_conv_id:对话id
        """
        logger.info(f"Agent chat end, save conversation {agent_conv_id}!")
        try:
            """统一保存对话结果的逻辑"""
            if not final_message:
                try:
                    final_message = await self.memory.vis_final(agent_conv_id)
                except Exception as e:
                    logger.exception(f"获取{agent_conv_id}最终消息异常: {str(e)}")
                    final_message = str(e)

            final_report = None
            if callable(chat_call_back):
                try:
                    final_report = await self.memory.user_answer(agent_conv_id)
                except Exception as e:
                    logger.exception(f"获取{conv_session_id}最终报告异常: {str(e)}")

                post_action_reports: list[dict] = []
                try:
                    messages = await self.memory.get_messages(agent_conv_id)
                    post_action_reports = [
                        post_action_report
                        for message in messages
                        if (
                            post_action_report := _get_post_action_report(
                                message.context
                            )
                        )
                    ]
                except Exception as e:
                    logger.exception(
                        f"获取{conv_session_id}post_action_reports: {str(e)}"
                    )

                await chat_call_back(
                    conv_session_id,
                    agent_conv_id,
                    final_message,
                    final_report,
                    err_msg,
                    first_chunk_ms,
                    post_action_reports=post_action_reports,
                )

            # Deliver to channel if configured (handles cron job message delivery)
            if not err_msg:
                content = final_report  # 只看final_report 不看final_message
                content = content.lstrip() if content else None
                if content:
                    await self._deliver_to_channel_if_configured(
                        conv_session_id, content
                    )

            # logger.info(f"获取{conv_session_id}最终消息: {final_message}, 异常信息:{err_msg}")
            if not final_message:
                final_message = ""
            if err_msg:
                current_message.add_view_message(final_message)
            else:
                current_message.add_view_message(final_message)
            current_message.end_current_round()
            current_message.save_to_storage()

        finally:
            await self.memory.clear(agent_conv_id)

    async def _deliver_to_channel_if_configured(
        self,
        conv_session_id: str,
        content: str,
    ) -> bool:
        """Deliver message to channel if configured in conversation extra.

        This method handles automatic message delivery to channels (e.g., DingTalk)
        when the conversation was initiated from a channel or when a cron job
        needs to deliver results to a channel.

        The channel info is stored in the conversation's extra field when
        the conversation is created from a channel message.

        Args:
            conv_session_id: The conversation session ID.
            content: The message content to deliver.

        Returns:
            True if delivered successfully, False otherwise.
        """
        if not conv_session_id:
            return False

        try:
            # Get channel info from conversation extra
            conversations = await self.gpts_conversations.get_by_session_id_asc(
                conv_session_id
            )

            if not conversations:
                logger.debug(f"No conversations found for session {conv_session_id}")
                return False

            # Get the most recent conversation to extract channel info
            first_conv = conversations[-1]
            if not first_conv.extra:
                logger.debug(f"No extra field in conversation {first_conv.conv_id}")
                return False

            # Parse extra field
            extra = orjson.loads(first_conv.extra)
            channel_info = extra.get("channel")

            if not channel_info:
                logger.debug(f"No channel info in conversation {first_conv.conv_id}")
                return False

            channel_id = channel_info.get("channel_id")
            receiver_id = channel_info.get("receiver_id")
            is_group = channel_info.get("is_group", False)

            if not channel_id or not receiver_id:
                logger.warning(
                    f"Incomplete channel info: channel_id={channel_id}, receiver_id={receiver_id}"
                )
                return False

            # Get the channel handler from registry
            from derisk.channel.registry import ChannelHandlerRegistry

            registry = ChannelHandlerRegistry.get_instance()
            handler = registry.get_handler(channel_id)

            if not handler:
                logger.warning(f"No active handler for channel {channel_id}")
                return False

            # Send the message
            result = await handler.send_message(
                receiver_id=receiver_id,
                content=content,
                content_type="text",
                is_group=is_group,
            )

            if result.success:
                logger.info(f"Delivered message to channel {channel_id}")
                return True
            else:
                logger.error(f"Failed to deliver: {result.error}")
                return False

        except Exception as e:
            logger.error(f"Error delivering to channel: {e}")
            return False

    @trace("agent.initialize_conversation", requires=["app_code", "conv_session_id"])
    async def _initialize_conversation(
        self,
        conv_session_id: str,
        app_code: str,
        user_query: Union[str, HumanMessage],
        user_code: Optional[str] = None,
    ) -> StorageConversation:
        """初始化会话"""
        conv_serve = ConversationServe.get_instance(CFG.SYSTEM_APP)
        current_message = await _build_conversation(
            conv_id=conv_session_id,
            select_param="",
            summary="",
            model_name="",
            app_code=app_code,
            conv_serve=conv_serve,
            user_name=user_code,
        )
        execute_no_wait(current_message.save_to_storage)
        # current_message.save_to_storage()
        current_message.start_new_round()
        current_message.add_user_message(
            user_query if isinstance(user_query, str) else user_query.content
        )
        return current_message

    @trace(
        "agent.initialize_agent_conversation", requires=["app_code", "conv_session_id"]
    )
    async def _initialize_agent_conversation(self, conv_session_id: str, **ext_info):
        gpts_conversations: List[
            GptsConversationsEntity
        ] = await self.gpts_conversations.get_by_session_id_asc(conv_session_id)

        logger.info(
            f"gpts_conversations count:{conv_session_id}, "
            f"{len(gpts_conversations) if gpts_conversations else 0}"
        )
        last_conversation = gpts_conversations[-1] if gpts_conversations else None
        if last_conversation and Status.WAITING.value == last_conversation.state:
            agent_conv_id = last_conversation.conv_id
            logger.info("收到用户动作授权, 恢复会话: " + agent_conv_id)
        else:
            gpt_chat_order = (
                "1" if not gpts_conversations else str(len(gpts_conversations) + 1)
            )
            agent_conv_id = conv_session_id + "_" + gpt_chat_order
        return agent_conv_id, gpts_conversations

    @abstractmethod
    async def chat(
        self,
        conv_uid: str,
        gpts_name: str,
        user_query: Union[str, HumanMessage],
        background_tasks: Optional[BackgroundTasks] = None,
        specify_config_code: Optional[str] = None,
        user_code: Optional[str] = None,
        sys_code: Optional[str] = None,
        stream: Optional[bool] = True,
        chat_call_back: Optional[Any] = None,
        chat_in_params: Optional[List[ChatInParamValue]] = None,
        **ext_info,
    ):
        """会话入口接口,根据需要分开实现. 对外服务
        Args:

        """
        raise NotImplementedError

    async def aggregation_chat(
        self,
        conv_id: str,
        agent_conv_id: str,
        gpts_name: str,
        user_query: Union[str, HumanMessage],
        user_code: str = None,
        sys_code: str = None,
        stream: Optional[bool] = True,
        gpts_conversations: Optional[List[GptsConversationsEntity]] = None,
        specify_config_code: Optional[str] = None,
        chat_in_params: Optional[List[ChatInParamValue]] = None,
        **ext_info,
    ):
        """具体agent(app)对话入口，构建对话记忆和对话目标等通用的Agent对话逻辑(需要外层基于会话封装一般不直接)

        Args:
            conv_id: 会话id
            agent_conv_id：当前对话id
            gpts_name：要对话的智能体(应用/agent/工作流等)
        """
        # logger.info(
        #     f"agent_chat conv_id:{conv_id}, agent_conv_id:{agent_conv_id},gpts_name:{gpts_name},user_query:"
        #     f"{user_query}"
        # )
        root_tracer.set_current_agent_id(gpts_name)  # 将当前agent app_code写入trace存储
        digest(
            CHAT_LOGGER,
            "CHAT_ENTRY",
            conv_id=conv_id,
            app_code=gpts_name,
            user_code=user_code,
        )
        start_ts = root_tracer.get_context_entrance_ms() or current_ms()
        succeed = False
        first_chunk_time = None
        if isinstance(user_query, str):
            user_query: HumanMessage = HumanMessage.parse_chat_completion_message(
                user_query, ignore_unknown_media=True
            )

        root_tracer.set_context_conv_id(agent_conv_id)
        message_round = 0
        history_message_count = 0
        is_retry_chat = False
        last_speaker_name = None
        history_messages = None

        ########################################################
        app_config = self.system_app.config.configs.get("app_config")
        web_config = app_config.service.web

        app_service = get_app_service()
        gpt_app: GptsApp = await app_service.app_detail(
            gpts_name, specify_config_code, building_mode=False
        )
        await self.dynamic_resource_adapter(gpt_app, ext_info)
        if not gpt_app:
            raise ValueError(f"Not found app {gpts_name}!")

        # init gpts  memory
        vis_render = ext_info.get("vis_render", None)
        # 如果接口指定使用接口传递，没有指定使用当前应用的布局配置
        if not vis_render:
            if gpt_app.layout and gpt_app.layout.chat_layout:
                vis_render = gpt_app.layout.chat_layout.name
            else:
                vis_render = "gpt_vis_all"

        vis_converter_mng = get_vis_manager()
        vis_protocol = vis_converter_mng.get_by_name(vis_render)(
            derisk_url=web_config.web_url
        )
        ext_info["incremental"] = vis_protocol.incremental

        await self.memory.init(
            agent_conv_id,
            app_code=gpts_name,
            history_messages=history_messages,
            start_round=history_message_count,
            vis_converter=vis_protocol,
        )
        #########################################################

        with root_tracer.start_span("agent.conversation.state_check"):
            # 检查最后一个对话记录是否完成，如果是等待状态，则要继续进行当前对话
            if gpts_conversations:
                last_gpts_conversation: GptsConversationsEntity = gpts_conversations[-1]
                logger.info(
                    f"last conversation status:{last_gpts_conversation.__dict__}"
                )
                if last_gpts_conversation.state == Status.WAITING.value:
                    is_retry_chat = True
                    agent_conv_id = last_gpts_conversation.conv_id

                    gpts_messages: List[
                        GptsMessage
                    ] = await self.gpts_messages_dao.get_by_conv_id(agent_conv_id)  # type:ignore

                    last_message = gpts_messages[-1]
                    message_round = last_message.rounds + 1
                    last_speaker_name = last_message.sender_name

                    # 恢复起来的会话，需要加载历史消息到记忆中
                    await self.memory.load_persistent_memory(agent_conv_id)

            historical_dialogues: List[GptsMessage] = []
            if not is_retry_chat:
                # Create a new gpts conversation record

                ## When creating a new gpts conversation record, determine whether to
                # include the history of previous topics according to the application
                # definition.
                if gpt_app.keep_start_rounds > 0 or gpt_app.keep_end_rounds > 0:
                    if gpts_conversations and len(gpts_conversations) > 0:
                        rely_conversations = []
                        if gpt_app.keep_start_rounds + gpt_app.keep_end_rounds < len(
                            gpts_conversations
                        ):
                            if gpt_app.keep_start_rounds > 0:
                                front = gpts_conversations[gpt_app.keep_start_rounds :]
                                rely_conversations.extend(front)
                            if gpt_app.keep_end_rounds > 0:
                                back = gpts_conversations[-gpt_app.keep_end_rounds :]
                                rely_conversations.extend(back)
                        else:
                            rely_conversations = gpts_conversations
                        for gpts_conversation in rely_conversations:
                            temps: List[GptsMessage] = await self.memory.get_messages(
                                gpts_conversation.conv_id
                            )
                            if temps and len(temps) > 1:
                                historical_dialogues.append(temps[0])
                                historical_dialogues.append(temps[-1])

                user_goal = json.dumps(user_query.to_dict(), ensure_ascii=False)
                user_goal = user_goal[: min(len(user_goal), 6500)] if user_goal else ""
                await self.gpts_conversations.a_add(
                    GptsConversationsEntity(
                        conv_id=agent_conv_id,
                        conv_session_id=conv_id,
                        user_goal=user_goal,
                        gpts_name=gpts_name,
                        team_mode=gpt_app.team_mode,
                        state=Status.RUNNING.value,
                        max_auto_reply_round=0,
                        auto_reply_count=0,
                        user_code=user_code,
                        sys_code=sys_code,
                        vis_render=vis_render,
                        extra=orjson.dumps(ext_info).decode(),
                    )
                )

        # init agent memory
        agent_memory = self.get_or_build_derisk_memory(
            conv_id, gpt_app.app_code, user_code, gpt_app.team_context
        )
        file_handle = None
        try:
            task = asyncio.create_task(
                self._inner_chat(
                    user_query=user_query,
                    conv_session_id=conv_id,
                    conv_uid=agent_conv_id,
                    gpts_app=gpt_app,
                    agent_memory=agent_memory,
                    is_retry_chat=is_retry_chat,
                    last_speaker_name=last_speaker_name,
                    init_message_rounds=message_round,
                    historical_dialogues=historical_dialogues,
                    user_code=user_code,
                    sys_code=sys_code,
                    stream=stream,
                    chat_in_params=chat_in_params,
                    **ext_info,
                )
            )
            ## TEST FILE WRITE
            WRITE_TO_FILE = True
            if WRITE_TO_FILE:
                from derisk.configs.model_config import DATA_DIR
                import os

                chat_chunk_file_path = os.path.join(DATA_DIR, "chat_chunk_file")
                os.makedirs(chat_chunk_file_path, exist_ok=True)
                filename = os.path.join(
                    chat_chunk_file_path, f"_chat_file_{agent_conv_id}.jsonl"
                )
                file_handle = open(filename, "w", encoding="utf-8")
            if stream == True:
                async for chunk in self._chat_messages(agent_conv_id):
                    if chunk and len(chunk) > 0:
                        try:
                            content = orjson.dumps({"vis": chunk}).decode("utf-8")
                            if WRITE_TO_FILE:
                                file_handle.write(content)
                                file_handle.write("\n")
                            resp = f"data:{content}\n\n"
                            first_chunk_time = first_chunk_time or current_ms()
                            yield task, resp, agent_conv_id
                        except Exception as e:
                            logger.exception(
                                f"get messages {gpts_name} Exception!" + str(e)
                            )
                            yield task, f"data: {str(e)}\n\n", agent_conv_id

                # 5. 最终处理
                if task.done() and task.exception():
                    # 如果任务有异常，返回错误
                    logger.exception(f"agent chat exception!{conv_id}")
                    raise task.exception()
                else:
                    # 正常结束
                    yield task, _format_vis_msg("[DONE]"), agent_conv_id
            else:
                logger.info("非流式消息输出!")
                last_chunk = None, None, None
                async for chunk in self._chat_messages(agent_conv_id):
                    if chunk and len(chunk) > 0:
                        if not first_chunk_time:
                            yield task, "", agent_conv_id
                        try:
                            content = json.dumps(
                                {"vis": chunk},
                                default=serialize,
                                ensure_ascii=False,
                            )
                            if WRITE_TO_FILE:
                                file_handle.write(content)
                                file_handle.write("\n")
                            resp = f"data:{content}\n\n"
                            first_chunk_time = first_chunk_time or current_ms()
                            last_chunk = task, resp, agent_conv_id
                        except Exception as e:
                            logger.exception(
                                f"get messages {gpts_name} Exception!" + str(e)
                            )
                            yield task, f"data: {str(e)}\n\n", agent_conv_id
                yield last_chunk
            succeed = True
        except asyncio.CancelledError:
            # 取消时不立即回调
            logger.info("Generator cancelled, delaying callback")
            raise
        except Exception as e:
            logger.exception(f"Agent chat have error!{str(e)}")
            raise e
            # yield task, str(e), agent_conv_id
        finally:
            digest(
                CHAT_LOGGER,
                "CHAT_DONE",
                conv_id=conv_id,
                app_code=gpts_name,
                user_code=user_code,
                succeed=succeed,
                cost_ms=current_ms() - start_ts,
                first_chunk_time=(first_chunk_time - start_ts)
                if first_chunk_time
                else 0,
            )
            # 确保文件句柄关闭
            if file_handle:
                file_handle.close()

    def get_or_build_agent_memory(self, conv_id: str, derisks_name: str) -> AgentMemory:
        session_memory = ShortTermMemory(buffer_size=10)
        agent_memory = AgentMemory(session_memory, gpts_memory=self.memory)
        return agent_memory

    @trace("agent.get_or_build_memory", requires=["conv_id", "agent_id"])
    def get_or_build_derisk_memory(
        self,
        conv_id: str,
        agent_id: str,
        user_id: str,
        team_context: Optional[AgentContextType] = None,
    ) -> AgentMemory:
        """Get or build a Derisk memory instance for the given conversation ID.

        Args:
            conv_id:(str) conversation ID
            agent_id:(str) app_code
        """
        session_memory = ShortTermMemory(buffer_size=20)
        agent_memory = AgentMemory(
            memory=session_memory,
            gpts_memory=self.memory,
        )
        return agent_memory

    async def build_agent_by_app_code(
        self,
        app_code: str,
        context: AgentContext,
        agent_memory: AgentMemory = None,
        **kwargs,
    ) -> ConversableAgent:
        app_service = get_app_service()
        gpts_app: ServerResponse = await app_service.app_detail(
            app_code, building_mode=False
        )
        agent_memory = agent_memory or self.get_or_build_agent_memory(
            context.conv_id, gpts_app.app_name
        )
        resource_manager: ResourceManager = get_resource_manager()
        return await self._build_agent_by_gpts(
            context=context,
            agent_memory=agent_memory,
            rm=resource_manager,
            app=gpts_app,
            **kwargs,
        )

    async def _have_agent_skill(
        self, app: GptsApp, dynamic_resources: Optional[List[AgentResource]] = None
    ):
        """检查应用是否包含 AgentSkill 资源"""
        if app.resource_tool and any(
            item.type in [AgentSkillResource.type(), DeriskSkillResource.type()]
            for item in app.resource_tool
        ):
            return True
        if app.all_resources and any(
            item.type in [AgentSkillResource.type(), DeriskSkillResource.type()]
            for item in app.all_resources
        ):
            return True
        if dynamic_resources and any(
            item.type in [AgentSkillResource.type(), DeriskSkillResource.type()]
            for item in dynamic_resources
        ):
            return True
        return False

    @trace("agent.build_agent_by_gpts")
    async def _build_agent_by_gpts(
        self,
        context: AgentContext,
        agent_memory: AgentMemory,
        rm: ResourceManager,
        app: GptsApp,
        scheduler: Optional[Scheduler],
        need_sandbox: bool = False,
        **kwargs,
    ) -> ConversableAgent:
        """Build a dialogue target agent through gpts configuration"""
        from datetime import datetime

        logger.info(
            f"_build_agent_by_gpts:{app.app_code},{app.app_name}, start:{datetime.now()}"
        )
        try:
            ## 检测动态资源
            real_all_resources = kwargs.get("dynamic_resources", [])

            # 使用全局缓存获取或创建 sandbox_manager，避免并行创建重复的沙箱
            sandbox_manager = await self._get_or_create_sandbox_manager(
                context, app, need_sandbox
            )

            # 初始化场景文件到沙箱（如果应用绑定了场景）
            # 注意：每个Agent有独立的场景文件目录，避免多Agent共享沙箱时的冲突
            if sandbox_manager and app.scenes and len(app.scenes) > 0:
                try:
                    from derisk.agent.core_v2.scene_sandbox_initializer import (
                        initialize_scenes_for_agent,
                    )

                    scene_init_result = await initialize_scenes_for_agent(
                        app_code=app.app_code,
                        agent_name=app.app_name or app.app_code or "default_agent",
                        scenes=app.scenes,
                        sandbox_manager=sandbox_manager,
                    )
                    if scene_init_result.get("success"):
                        logger.info(
                            f"[AgentChat] Scene files initialized for {app.app_code}: "
                            f"{len(scene_init_result.get('files', []))} files "
                            f"in {scene_init_result.get('scenes_dir', 'unknown')}"
                        )
                    else:
                        logger.warning(
                            f"[AgentChat] Failed to initialize scene files for {app.app_code}: "
                            f"{scene_init_result.get('message')}"
                        )
                except Exception as scene_init_error:
                    logger.warning(
                        f"[AgentChat] Error initializing scene files for {app.app_code}: "
                        f"{scene_init_error}"
                    )
                    # 场景初始化失败不影响主流程

            employees: List[ConversableAgent] = []
            if "extra_agents" in kwargs and kwargs.get("extra_agents"):
                # extra_agents 表示动态添加的子Agent
                employees = await self._build_extra_employees(
                    kwargs.get("extra_agents"), context, agent_memory, rm, scheduler
                )
                app.all_resources.extend(
                    [self.agent_to_resource(extra_agent) for extra_agent in employees]
                )
            elif app.details is not None and len(app.details) > 0:
                employees: List[ConversableAgent] = await self._build_employees(
                    context,
                    agent_memory,
                    rm,
                    [deepcopy(item) for item in app.details],
                    scheduler,
                )
            team_mode = TeamMode(app.team_mode)
            ## 模型服务
            if not self.llm_provider:
                worker_manager = CFG.SYSTEM_APP.get_component(
                    ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
                ).create()
                self.llm_provider = DefaultLLMClient(
                    worker_manager, auto_convert_message=True
                )

            llm_config = LLMConfig(
                llm_client=self.llm_provider,
                llm_strategy=LLMStrategyType(app.llm_config.llm_strategy),
                strategy_context=app.llm_config.llm_strategy_value,
                llm_param=app.llm_config.llm_param,
                mist_keys=app.llm_config.mist_keys,
            )

            real_all_resources.extend(app.all_resources)
            real_all_resources = await self.add_duplicate_allow_tools(
                real_all_resources
            )

            if team_mode == TeamMode.SINGLE_AGENT or TeamMode.NATIVE_APP == team_mode:
                if employees is not None and len(employees) == 1:
                    recipient = employees[0]
                else:
                    cls: Type[ConversableAgent] = self.agent_manage.get_by_name(
                        app.agent
                    )

                    ## 处理agent资源内容
                    # depend_resource = await blocking_func_to_async(
                    #     CFG.SYSTEM_APP, rm.build_resource, app.all_resources
                    # )
                    depend_resource = await rm.a_build_resource(real_all_resources)

                    agent_context = deepcopy(context)
                    agent_context.agent_app_code = app.app_code

                    recipient = (
                        await cls()
                        .bind(agent_context)
                        .bind(agent_memory)
                        .bind(llm_config)
                        .bind(sandbox_manager)
                        .bind(depend_resource)
                        # .bind(prompt_template)
                        .bind(app.context_config)
                        .bind(ExtConfigHolder(ext_config=app.ext_config))
                        .bind(scheduler)
                        .build()
                    )

                ## 处理Agent实例的基本信息
                temp_profile = recipient.profile.copy()
                temp_profile.desc = app.app_describe
                temp_profile.name = app.app_name
                temp_profile.avatar = app.icon
                if app.system_prompt_template is not None:
                    temp_profile.system_prompt_template = app.system_prompt_template
                if app.user_prompt_template:
                    temp_profile.user_prompt_template = app.user_prompt_template

                # 如果应用有场景，读取场景内容并注入到Agent的System Prompt
                if app.scenes and len(app.scenes) > 0 and sandbox_manager:
                    try:
                        scene_content = await self._load_and_inject_scenes(
                            agent_name=app.app_name or app.app_code or "default_agent",
                            scenes=app.scenes,
                            sandbox_manager=sandbox_manager,
                            agent_profile=temp_profile,
                        )
                        if scene_content:
                            logger.info(
                                f"[AgentChat] 场景内容已注入Agent: "
                                f"{len(scene_content)} 字符"
                            )
                    except Exception as e:
                        logger.warning(f"[AgentChat] 场景内容注入失败: {e}")
                        # 场景注入失败不影响主流程

                recipient.bind(temp_profile)

                return recipient
            elif TeamMode.AUTO_PLAN == team_mode:
                agent_manager = get_agent_manager()
                auto_team_ctx = app.team_context

                manager_cls: Type[ConversableAgent] = agent_manager.get_by_name(
                    auto_team_ctx.teamleader
                )
                manager = manager_cls()

                if real_all_resources:
                    # depend_resource = await blocking_func_to_async(
                    #     CFG.SYSTEM_APP, rm.build_resource, app.all_resources
                    # )
                    depend_resource = await rm.a_build_resource(real_all_resources)
                    manager.bind(depend_resource)

                agent_context = deepcopy(context)
                agent_context.agent_app_code = app.app_code

                manager = (
                    await manager.bind(agent_context)
                    .bind(llm_config)
                    .bind(agent_memory)
                    .bind(app.context_config)
                    .bind(sandbox_manager)
                    .bind(ExtConfigHolder(ext_config=app.ext_config))
                    .bind(scheduler)
                    .build()
                )

                ## 处理Agent实例的基本信息
                temp_profile = manager.profile.copy()
                temp_profile.desc = app.app_describe
                temp_profile.name = app.app_name
                temp_profile.avatar = app.icon
                if app.system_prompt_template is not None:
                    temp_profile.system_prompt_template = app.system_prompt_template
                if app.user_prompt_template:
                    temp_profile.user_prompt_template = app.user_prompt_template
                manager.bind(temp_profile)

                if isinstance(manager, ManagerAgent) and len(employees) > 0:
                    manager.hire(employees)
                logger.info(
                    f"_build_agent_by_gpts return:{manager.profile.name},{manager.profile.desc},{id(manager)}"
                )

                return manager
            else:
                raise ValueError(f"Unknown Agent Team Mode!{team_mode}")

        finally:
            logger.info(
                f"_build_agent_by_gpts:{app.app_code},{app.app_name}, end:{datetime.now()}"
            )

    @trace("agent.build_employees")
    async def _build_employees(
        self,
        context: AgentContext,
        agent_memory: AgentMemory,
        rm: ResourceManager,
        app_details: List[GptsAppDetail],
        scheduler: Optional[Scheduler],
    ) -> List[ConversableAgent]:
        """Constructing dialogue members through gpts-related Agent or gpts app information."""
        from datetime import datetime

        logger.info(
            f"_build_employees: details={[item.agent_role + ',' + item.agent_name for item in app_details] if app_details else ''},start:{datetime.now()}"
        )
        app_service = get_app_service()

        async def _build_employee_agent(record: GptsAppDetail):
            logger.info(
                f"_build_employees循环:{record.agent_role},{record.agent_name}, start:{datetime.now()}"
            )
            if record.type == "app":
                gpt_app: GptsApp = deepcopy(
                    await app_service.app_detail(record.agent_role, building_mode=False)
                )
                if not gpt_app:
                    raise ValueError(f"Not found app {record.agent_role}!")
                employee_agent = await self._build_agent_by_gpts(
                    context, agent_memory, rm, gpt_app, scheduler=scheduler
                )

                logger.info(
                    f"_build_employees循环:{employee_agent.profile.role},{employee_agent.profile.name},{employee_agent.profile.desc},{id(employee_agent)}, end:{datetime.now()}"
                )
                return employee_agent
            else:
                raise ValueError("当前应用数据已经无法支持，请重新编辑构建！")

        api_tasks = []
        for record in app_details:
            api_tasks.append(_build_employee_agent(record))

        employees = await run_async_tasks(tasks=api_tasks, concurrency_limit=10)
        logger.info(
            f"_build_employees return:{[item.profile.name if item.profile.name else '' + ',' + str(id(item)) for item in employees]},end:{datetime.now()}"
        )
        return employees

    @trace("agent.build_extra_agents")
    async def _build_extra_employees(
        self,
        extra_agents: List[Union[str, dict]],
        context: AgentContext,
        agent_memory: AgentMemory,
        rm: ResourceManager,
        scheduler: Optional[Scheduler],
        need_sandbox: bool = False,
    ) -> List[ConversableAgent]:
        logger.info(f"_build_extra_employees: need_sandbox={need_sandbox}")

        def _uniform(_extra_agent) -> dict:
            """将参数转为同样的格式"""
            if isinstance(_extra_agent, dict):
                return _extra_agent
            else:
                return {"app_code": _extra_agent}

        async def _build(_extra_agent) -> ConversableAgent:
            app = await app_service.app_detail(
                _extra_agent.get("app_code"),
                specify_config_code=_extra_agent.get("config_code", None),
                building_mode=False,
            )
            agent = await self._build_agent_by_gpts(
                context, agent_memory, rm, app, scheduler, need_sandbox=need_sandbox
            )
            return agent

        app_service = get_app_service()
        extra_agents = [_uniform(extra_agent) for extra_agent in extra_agents]
        tasks = [_build(extra_agent) for extra_agent in extra_agents]
        extra_employees = await asyncio.gather(*tasks)
        return list(extra_employees)

    async def _load_and_inject_scenes(
        self,
        agent_name: str,
        scenes: List[str],
        sandbox_manager: SandboxManager,
        agent_profile: Any,
    ) -> str:
        """
        从沙箱加载场景内容并注入到Agent的System Prompt

        Args:
            agent_name: Agent名称
            scenes: 场景ID列表
            sandbox_manager: 沙箱管理器
            agent_profile: Agent配置对象

        Returns:
            注入的场景内容
        """
        from derisk.agent.core_v2.scene_sandbox_initializer import get_scene_initializer

        initializer = get_scene_initializer(sandbox_manager)
        scene_contents = []

        # 读取每个场景文件
        for scene_id in scenes:
            try:
                content = await initializer.read_scene_file(agent_name, scene_id)
                if content:
                    # 解析YAML Front Matter，提取有效内容
                    parts = content.split("---\n")
                    if len(parts) >= 3:
                        # 有Front Matter，提取body部分
                        body = "---\n".join(parts[2:])
                        scene_contents.append(f"## 场景: {scene_id}\n\n{body}")
                    else:
                        # 没有Front Matter，使用全部内容
                        scene_contents.append(f"## 场景: {scene_id}\n\n{content}")

                    logger.debug(f"[AgentChat] 加载场景内容: {scene_id}")
            except Exception as e:
                logger.warning(f"[AgentChat] 加载场景 {scene_id} 失败: {e}")

        if not scene_contents:
            return ""

        # 构建场景提示词
        scene_separator = "\n\n---\n\n"
        scene_prompt = f"""# 场景定义

你是根据以下场景定义来协助用户的智能助手。请严格遵循场景定义中的角色设定、工作流程和工具使用规范。

{scene_separator.join(scene_contents)}

---

"""

        # 注入到Agent的System Prompt
        original_prompt = agent_profile.system_prompt_template or ""
        agent_profile.system_prompt_template = scene_prompt + original_prompt

        return scene_prompt

    def agent_to_resource(self, agent: ConversableAgent) -> AgentResource:
        return AgentResource.from_dict(
            {
                "type": ResourceType.App.value,
                "value": json.dumps(
                    {
                        "name": f"{agent.name}({agent.agent_context.agent_app_code})",
                        "app_code": agent.agent_context.agent_app_code,
                        "app_name": agent.name,
                        "app_describe": agent.desc,
                        "icon": agent.avatar,
                    },
                    ensure_ascii=False,
                ),
                "name": f"{agent.name}({agent.agent_context.agent_app_code})",
                "unique_id": uuid.uuid4().hex,
            }
        )

    async def add_duplicate_allow_tools(self, resources: List[AgentResource]):
        if not resources:
            return []
        gpts_tool_dao = GptsToolDao()
        for resource in resources:
            if resource.type not in [AgentSkillResource.type()]:
                continue
            value = json.loads(resource.value)
            tool_id = value.get("tool_id")
            if not tool_id:
                continue
            gpt_tool = gpts_tool_dao.get_tool_by_tool_id(tool_id)
            if not gpt_tool:
                continue
            config = json.loads(gpt_tool.config)
            release, debug = config.get("release", None), config.get("debug", None)
            if release:
                allow_tools = release.get("metadata", {}).get("allowed-tools")
            elif debug:
                allow_tools = debug.get("metadata", {}).get("allowed-tools")
            else:
                continue
            if allow_tools:
                skill_allow_tools = await self._get_skill_allow_tools_resources(
                    allow_tools
                )
                resources.extend(skill_allow_tools)
        seen_combinations = set()
        unique_resources = []
        for resource in resources:
            key = resource.unique_id
            if not key:
                unique_resources.append(resource)
                continue
            if key not in seen_combinations:
                seen_combinations.add(key)
                unique_resources.append(resource)
        return unique_resources

    async def chat_in_params_to_resource(
        self,
        chat_in_params: Optional[List[ChatInParamValue]],
        ext_info: Optional[dict] = None,
    ) -> Optional[List[AgentResource]]:
        dynamic_resources = []
        if chat_in_params:
            for chat_in_param in chat_in_params:
                if chat_in_param.param_type == "resource":
                    sub_type = chat_in_param.sub_type
                    param_value = chat_in_param.param_value

                    if sub_type == "mcp(derisk)":
                        try:
                            if isinstance(param_value, str):
                                value_data = json.loads(param_value)
                            else:
                                value_data = param_value

                            mcp_code = (
                                value_data.get("mcp_code")
                                if isinstance(value_data, dict)
                                else value_data
                            )
                            mcp_name = (
                                value_data.get("name")
                                if isinstance(value_data, dict)
                                else None
                            )

                            if mcp_code:
                                from derisk_serve.agent.resource.tool.mcp_collect import (
                                    get_mcp_info,
                                )

                                mcp_info = get_mcp_info(mcp_code)
                                if mcp_info:
                                    mcp_value = {
                                        "name": mcp_name or mcp_info.name or mcp_code,
                                        "mcp_code": mcp_code,
                                        "mcp_servers": mcp_info.server_url or "",
                                        "headers": mcp_info.headers or {},
                                        "source": mcp_info.source or "faas",
                                        "timeout": mcp_info.timeout or 120,
                                    }
                                    mcp_resource = AgentResource.from_dict(
                                        {
                                            "type": "mcp(derisk)",
                                            "name": mcp_name or f"MCP[{mcp_code}]",
                                            "value": json.dumps(
                                                mcp_value, ensure_ascii=False
                                            ),
                                        }
                                    )
                                    dynamic_resources.append(mcp_resource)
                                    logger.info(
                                        f"Added MCP resource from chat_in_params: {mcp_code}"
                                    )
                                else:
                                    logger.warning(
                                        f"MCP info not found for code: {mcp_code}"
                                    )
                        except Exception as e:
                            logger.warning(f"Failed to process MCP resource: {e}")
                    else:
                        dynamic_resources.append(
                            AgentResource.from_dict(
                                {
                                    "type": sub_type,
                                    "name": f"用户选择了[{sub_type}]资源",
                                    "value": param_value,
                                }
                            )
                        )

                    if chat_in_param.sub_type == DeriskSkillResource.type():
                        skill_param_value = chat_in_param.param_value
                        if isinstance(skill_param_value, str):
                            skill_config = json.loads(skill_param_value)
                        else:
                            skill_config = skill_param_value
                        config_str = skill_config.get("config")
                        if config_str:
                            metadata = (
                                json.loads(config_str)
                                .get("release", {})
                                .get("metadata", {})
                            )
                        else:
                            metadata = {}
                        allow_tools = metadata.get("allowed-tools")
                        allow_tools_resources = (
                            await self._get_skill_allow_tools_resources(allow_tools)
                        )
                        if allow_tools_resources:
                            dynamic_resources.extend(allow_tools_resources)
        if ext_info:
            ext_resources = await self._get_resource_from_ext_info(ext_info)
            dynamic_resources.extend(ext_resources)
        return dynamic_resources

    async def _get_skill_allow_tools_resources(
        self, allow_tools: Optional[Union[str, List[str]]]
    ):
        """根据 Skill 资源的 allow tools 参数获取对应的 Tool 资源列表"""
        try:
            if isinstance(allow_tools, str):
                allow_tools = [
                    tool.strip() for tool in allow_tools.split(",") if tool.strip()
                ]
            all_tool_names = []
            mcp_with_allow_tools = {}
            for tool_name in allow_tools:
                if tool_name.startswith("mcp."):
                    split_list = tool_name.split(".")
                    mcp_name = split_list[1] if len(split_list) > 1 else None
                    mcp_allow_tool = split_list[2] if len(split_list) > 2 else None
                    if mcp_allow_tool:
                        if mcp_name in mcp_with_allow_tools:
                            mcp_with_allow_tools[mcp_name].append(mcp_allow_tool)
                        else:
                            mcp_with_allow_tools[mcp_name] = [mcp_allow_tool]
                    all_tool_names.append(mcp_name)
                else:
                    all_tool_names.append(tool_name)

            tool_resources = []
            gpts_tool_dao = GptsToolDao()
            if all_tool_names:
                tools = await gpts_tool_dao.get_tools_by_names(all_tool_names)
                for tool in tools:
                    try:
                        tool_config = (
                            json.loads(tool.config)
                            if isinstance(tool.config, str)
                            else tool.config
                        )
                        value = {
                            "name": tool.tool_name,
                            "tool_id": tool.tool_id,
                            "description": tool_config.get("description", ""),
                        }
                        match tool.type:
                            case "MCP":
                                resource_type = "tool(mcp(sse))"
                                value["headers"] = tool_config.get("headers", {})
                                value["source"] = tool_config.get("source", "faas")
                                value["timeout"] = tool_config.get("timeout", 120)
                                value["mcp_servers"] = tool_config.get("url", "")
                                if tool.tool_name in mcp_with_allow_tools:
                                    value["allow_tools"] = mcp_with_allow_tools[
                                        tool.tool_name
                                    ]
                            case "HTTP" | "TR" | "LOCAL":
                                resource_type = f"tool({tool.type.lower()})"
                            case "SKILL":
                                resource_type = "agent_skill"
                                value["config"] = tool.config
                            case _:
                                logger.warning(f"Unknown tool type: {tool.type}")
                                continue
                        tool_resource = AgentResource.from_dict(
                            {
                                "type": resource_type,
                                "name": tool.tool_name,
                                "value": json.dumps(value, ensure_ascii=False),
                                "is_dynamic": True,
                                "context": None,
                            }
                        )
                        tool_resources.append(tool_resource)
                        logger.info(
                            f"Added tool resource from allow_tools [{resource_type}]: {tool.tool_name}"
                        )
                    except Exception as e:
                        logger.error(f"Skill Failed to load tool {tool.tool_name}: {e}")
            return tool_resources
        except Exception as e:
            logger.error(
                f"Failed to load allow_tools for skill {self.name}: {e}", exc_info=True
            )

    async def _get_resource_from_ext_info(self, ext_info: Optional[dict]):
        """Solve front chat in params."""
        dynamic_resources = []
        if not ext_info or "extraTools" not in ext_info:
            return dynamic_resources

        extra_tools = ext_info.get("extraTools")
        if not extra_tools or not isinstance(extra_tools, list):
            return dynamic_resources

        for tool in extra_tools:
            try:
                name, tool_id, id, type = (
                    tool.get("toolName"),
                    tool.get("toolId"),
                    tool.get("id", None),
                    tool.get("type"),
                )
                protocol, description, config = (
                    tool.get("protocol"),
                    tool.get("description"),
                    tool.get("config"),
                )
                value = {
                    "name": name,
                    "tool_id": tool_id,
                    "description": description,
                    "nex_tool_id": id,
                }
                if type == "LOCAL":
                    resource_type = "tool(local)"
                elif type == "API":
                    if protocol == "HTTP":
                        resource_type = "tool(http)"
                    elif protocol == "TR":
                        resource_type = "tool(tr)"
                    else:
                        resource_type = "tool(http)"
                elif type == "MCP":
                    resource_type = "tool(mcp(sse))"
                    if config:
                        config = json.loads(config)
                        value["headers"] = config.get("headers", {})
                        value["source"] = config.get("source", "faas")
                        value["timeout"] = config.get("timeout", 120)
                        value["mcp_servers"] = config.get("url", "")
                elif type == "SKILL":
                    resource_type = "agent_skill"
                    if config:
                        value["config"] = config
                        metadata = (
                            json.loads(config).get("release", {}).get("metadata", {})
                        )
                        allow_tools = metadata.get("allowed-tools")
                        if allow_tools:
                            allow_tool_resources = (
                                await self._get_skill_allow_tools_resources(allow_tools)
                            )
                            dynamic_resources.extend(allow_tool_resources)
                else:
                    logger.warning(f"Unknown tool type: {type}")
                    continue
                agent_resource = AgentResource(
                    type=resource_type,
                    name=name,
                    value=json.dumps(value, ensure_ascii=False),
                    unique_id=tool_id,
                    is_dynamic=True,
                )
                dynamic_resources.append(agent_resource)
                logger.info(f"Added dynamic tool resource: {name}")
            except Exception as e:
                logger.exception(f"Failed to load tool: {e}")
                continue

        seen_combinations = set()
        unique_resources = []
        for resource in dynamic_resources:
            key = (resource.name, resource.type)
            if key not in seen_combinations:
                seen_combinations.add(key)
                unique_resources.append(resource)
        return unique_resources

    def chat_in_params_to_context(
        self, chat_in_params: Optional[List[ChatInParamValue]], gpts_app: GptsApp
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """处理对话输出参数"""
        context = {}
        ## 输入层参数转Agent上下文参数
        ### 1.资源类型统一变成对话上下文参数
        ### 2.其他类型统一变成环境上下文参数
        llm_context = {}
        env_context = {}
        if chat_in_params:
            for param in chat_in_params:
                if AppParamType.Resource.value == param.param_type:
                    if param.sub_type not in FILE_RESOURCES:
                        try:
                            if isinstance(param.param_value, str):
                                value_obj = json.loads(param.param_value)
                                if isinstance(value_obj, list):
                                    r_value = value_obj[0]
                                else:
                                    r_value = value_obj
                            else:
                                r_value = param.param_value
                            logger.info("加载用户指定的资源")
                            chat_in_resource = AgentResource.from_dict(
                                {
                                    "type": param.sub_type,
                                    "name": f"对话选择[{param.sub_type}]资源",
                                    "value": r_value,
                                }
                            )
                            if not gpts_app.all_resources:
                                gpts_app.all_resources = []
                            gpts_app.all_resources.append(chat_in_resource)
                            llm_context[param.sub_type] = chat_in_resource
                        except Exception as e:
                            logger.warning(f"选择资源无法转换！{chat_in_params}", e)
                    else:
                        llm_context[param.sub_type] = param.param_value
                else:
                    llm_context[param.param_type] = param.param_value
                    if param.param_type == AppParamType.Model.value:
                        logger.info("用户指定了模型，优先使用")
                        gpts_app.llm_config.llm_strategy_value = [param.param_value]

                    elif param.param_type == AppParamType.Temperature.value:
                        temperature = param.param_value
                        logger.info("用户指定了模型Temperature，优先使用")

                    elif param.param_type == AppParamType.MaxNewTokens.value:
                        max_tokens = param.param_value
                        logger.info("用户指定了模型MaxTokens，优先使用")
        return llm_context, env_context

    async def _inner_chat(
        self,
        user_code: str,
        user_query: HumanMessage,
        conv_session_id: str,
        conv_uid: str,
        gpts_app: GptsApp,
        agent_memory: AgentMemory,
        is_retry_chat: bool = False,
        last_speaker_name: str = None,
        init_message_rounds: int = 0,
        historical_dialogues: Optional[List[GptsMessage]] = None,
        rely_messages: Optional[List[GptsMessage]] = None,
        stream: Optional[bool] = True,
        chat_in_params: Optional[List[ChatInParamValue]] = None,
        **ext_info,
    ):
        ### init chat param
        ## 检查应用是否配置完整
        if not gpts_app.agent:
            raise ValueError("当前应用还没配置Agent模版无法开启对话!")
        if not gpts_app.llm_config:
            raise ValueError("当前应用还没配置模型无法开始对话!")
        recipient: Optional[ConversableAgent] = None
        gpts_status = Status.COMPLETE.value
        staff_no = ext_info.get("staff_no") or gpts_app.user_code or "derisk"
        try:
            if isinstance(user_query.content, List):
                from derisk_serve.multimodal.service.service import MultimodalService
                from derisk.core.interface.media import MediaContent, MediaContentType

                multimodal_service = MultimodalService.get_instance(self.system_app)

                if multimodal_service:
                    new_content = MediaContent.replace_url(
                        user_query.content, multimodal_service.replace_uri
                    )
                    user_query.content = new_content

                    matched_model = multimodal_service.match_model_for_content(
                        user_query.content
                    )
                    if matched_model:
                        ext_info["multimodal_matched_model"] = matched_model
                        logger.info(f"[Multimodal] Auto matched model: {matched_model}")
                else:
                    from derisk_serve.file.serve import Serve as FileServe

                    file_serve = FileServe.get_instance(self.system_app)
                    new_content = MediaContent.replace_url(
                        user_query.content, file_serve.replace_uri
                    )
                    user_query.content = new_content

            if not self.agent_manage:
                self.agent_manage = get_agent_manager()

            from derisk.agent.core.types import ENV_CONTEXT_KEY
            from derisk.agent.core.types import LLM_CONTEXT_KEY

            ## 处理对话输入参数
            ### 环境参数穿透当前会话不落表，llm参数作为消息的扩展参数随消息落表，agent控制是否向下传递
            llm_context, env_context = self.chat_in_params_to_context(
                chat_in_params, gpts_app
            )
            ### 获取Agent对话资源
            dynamic_resources = await self.chat_in_params_to_resource(
                chat_in_params, ext_info
            )
            if dynamic_resources:
                ext_info["dynamic_resources"] = dynamic_resources

            if ext_info.get(ENV_CONTEXT_KEY):
                env_context.update(ext_info.get(ENV_CONTEXT_KEY))
            context: AgentContext = AgentContext(
                user_id=user_code,
                staff_no=staff_no,
                conv_id=conv_uid,
                conv_session_id=conv_session_id,
                trace_id=first(
                    ext_info.get("trace_id", None),
                    root_tracer.get_context_trace_id(),
                    uuid.uuid4().hex,
                ),
                rpc_id=ext_info.get("rpc_id", "0.1"),
                gpts_app_code=gpts_app.app_code,
                gpts_app_name=gpts_app.app_name,
                language=gpts_app.language,
                incremental=ext_info.get("incremental", False),
                env_context=env_context,
                stream=stream,
                extra=ext_info,
                mist_keys=gpts_app.llm_config.mist_keys,
            )

            cache = await self.memory.cache(conv_uid)
            scheduler: Scheduler = LocalScheduler(cache=cache)
            rm = get_resource_manager()
            recipient = await self._build_agent_by_gpts(
                context,
                agent_memory,
                rm,
                gpts_app,
                scheduler=scheduler,
                need_sandbox=True,
                **ext_info,
            )

            if is_retry_chat:
                # retry chat
                self.gpts_conversations.update(conv_uid, Status.RUNNING.value)

            user_proxy: UserProxyAgent = (
                await UserProxyAgent().bind(context).bind(agent_memory).build()
            )
            user_code = ext_info.get("user_code", None)
            if user_code:
                app_config = self.system_app.config.configs.get("app_config")
                web_config = app_config.service.web
                user_proxy.profile.avatar = (
                    f"{web_config.web_url}/user/avatar?loginName={user_code}"
                )
            await user_proxy.initiate_chat(
                recipient=recipient,
                message=user_query,
                is_retry_chat=is_retry_chat,
                last_speaker_name=last_speaker_name,
                message_rounds=init_message_rounds,
                historical_dialogues=user_proxy.convert_to_agent_message(
                    historical_dialogues
                ),
                rely_messages=rely_messages,
                approval_message_id=ext_info.get("approval_message_id"),
                **llm_context,
            )

            if await scheduler.running():
                await scheduler.schedule()

            # Check if the user has received a question.
            if user_proxy.have_ask_user():
                gpts_status = Status.WAITING.value

            self.gpts_conversations.update(conv_uid, gpts_status)
        except Exception as e:
            logger.error(f"chat abnormal termination！{conv_uid},{str(e)}")
            self.gpts_conversations.update(conv_uid, Status.FAILED.value)
            raise ValueError(f"The conversation is abnormal!{str(e)}")
        finally:
            logger.info(f"inner chat final!{conv_uid}")
            await self.memory.complete(conv_uid)
            # 清理全局缓存中的沙箱管理器记录
            await self._cleanup_sandbox_manager(conv_uid, staff_no)
        return conv_uid

    async def _chat_messages(self, conv_id: str):
        if not (iterator := await self.memory.queue_iterator(conv_id)):
            return

        async for item in iterator:
            # 可选：记录调试信息
            yield item
            await asyncio.sleep(0)

    async def stop_chat(self, conv_session_id: str, user_id: Optional[str] = None):
        """停止对话.

        Args:
            conv_session_id:会话id(当前会话的conversation_session_id)
            user_id:用户ID，用于清理沙箱
        """
        logger.info(f"stop_chat conv_session_id:{conv_session_id}")

        convs = await self.gpts_conversations.get_by_session_id_asc(conv_session_id)
        if convs:
            conv_id = convs[-1].conv_id
            await self.memory.stop(conv_id=conv_id)
            # 清理该会话的沙箱
            await self._cleanup_sandbox_manager(conv_id, user_id)
        else:
            raise ValueError(f"未找到会话[{conv_session_id}]")

    async def stop_chat_with_conv_id(self, conv_id: str, user_id: Optional[str] = None):
        """停止对话.

        Args:
            conv_id: 对话id(当前对话的agent_conv_id 非conversation_session_id)
            user_id: 用户ID，用于清理沙箱
        """
        logger.info(f"stop_chat conv_id:{conv_id}")
        await self.memory.stop(conv_id=conv_id)
        # 清理该会话的沙箱
        await self._cleanup_sandbox_manager(conv_id, user_id)

    async def retry_chat(self, conv_id: str):
        """重试对话, 对于运行中且最终消息超过5分钟的 可以基于已有对话记录继续运行

        Args:
            conv_id: 对话id(当前对话的agent_conv_id 非conversation_session_id)
        """
        pass

    async def query_chat(self, conv_id: str, vis_render: Optional[str] = None):
        """查询对话

        Args:
            conv_id: 对话id(当前对话的agent_conv_id 非conversation_session_id)
            vis_render: 可视化协议名称（决定返回数据的格式）
        """
        gpts_memory = GptsMemory(
            plans_memory=MetaDerisksPlansMemory(),
            message_memory=MetaDerisksMessageMemory(),
        )
        try:
            gpts_conversation: GptsConversationsEntity = (
                self.gpts_conversations.get_by_conv_id(conv_id)
            )
            if not gpts_conversation:
                return None
            is_final = False
            if gpts_conversation.state in [Status.COMPLETE.value, Status.FAILED.value]:
                is_final = True
            logger.info(
                f"query_chat gpts_conversation vis render:{vis_render},{gpts_conversation.vis_render}"
            )
            current_vis_render = (
                vis_render or gpts_conversation.vis_render or "nex_vis_window"
            )

            app_config = self.system_app.config.configs.get("app_config")
            web_config = app_config.service.web
            vis_manager = get_vis_manager()

            vis_convert: VisProtocolConverter = vis_manager.get_by_name(
                current_vis_render
            )(derisk_url=web_config.web_url)

            ## 重新初始化对话memory数据
            await gpts_memory.init(conv_id=conv_id, vis_converter=vis_convert)
            await gpts_memory.load_persistent_memory(conv_id)
            ## 构建Agent应用实例并挂载到memory，获取对应头像等信息
            # context: AgentContext = AgentContext(
            #     conv_id=conv_id,
            #     conv_session_id=gpts_conversation.conv_session_id,
            #     trace_id=uuid.uuid4().hex,
            #     rpc_id="",
            #     gpts_app_code=gpts_conversation.gpts_name,
            # )
            # try:
            #     await self.build_agent_by_app_code(gpts_conversation.gpts_name, context)
            # except Exception as e:
            #     logger.warning(f"查询会话时，恢复agent对象异常！{str(e)}")

            # 返回对应协议的最终消息内容
            return (
                await gpts_memory.vis_final(conv_id),
                await gpts_memory.user_answer(conv_id),
                current_vis_render,
                is_final,
                gpts_conversation.state,
            )
        finally:
            await gpts_memory.clear(conv_id)

    async def dynamic_resource_adapter(
        self, gpt_app: GptsApp, ext_info: Optional[dict] = None
    ) -> None:
        """Dynamic resource adapter."""
        pass


def _get_post_action_report(context: str | dict) -> Optional[dict]:
    if not context:
        return None

    try:
        if isinstance(context, str):
            context = json.loads(context)
        return context.get("post_action_report", None)
    except Exception as e:
        return None
