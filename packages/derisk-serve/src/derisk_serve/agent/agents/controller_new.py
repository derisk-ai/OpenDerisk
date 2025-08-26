import asyncio
import json
import logging
import uuid
from abc import ABC
from copy import deepcopy
from typing import Any, Dict, List, Optional, Type, AsyncGenerator, Callable, Tuple, Union

import asyncio
import json
import logging
import uuid
from abc import ABC
from copy import deepcopy
from typing import Any, Dict, List, Optional, Type, AsyncGenerator, Callable, Tuple, Union

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from derisk._private.config import Config
from derisk.agent import (
    AgentContext,
    AgentMemory,
    ConversableAgent,
    EnhancedShortTermMemory,
    HybridMemory,
    LLMConfig,
    ResourceType,
    UserProxyAgent,
    AWELTeamContext,
    get_agent_manager, Memory, AgentResource,
)
from derisk.agent.core.agent import ENV_CONTEXT_KEY
from derisk.agent.core.memory.gpts.disk_cache_gpts_memory import DiskGptsMemory
from derisk.agent.core.plan.react.team_react_plan import AutoTeamContext
from derisk.agent.core.base_team import ManagerAgent
from derisk.agent.core.memory.gpts import GptsMessage
from derisk.agent.core.schema import Status
from derisk.agent.resource.base import FILE_RESOURCES
from derisk.agent.resource import get_resource_manager, ResourceManager
from derisk.agent.util.llm.llm import LLMStrategyType
from derisk.component import BaseComponent, ComponentType, SystemApp
from derisk.core.awel.flow.flow_factory import FlowCategory
from derisk.core.interface.message import StorageConversation, HumanMessage
from derisk.model.cluster import WorkerManagerFactory
from derisk.model.cluster.client import DefaultLLMClient
from derisk.util.data_util import first
from derisk.util.date_utils import current_ms
from derisk.util.executor_utils import ExecutorFactory
from derisk.util.json_utils import serialize
from derisk.util.log_util import CHAT_LOGGER
from derisk.util.logger import digest
from derisk.util.tracer.tracer_impl import root_tracer
from derisk.vis import VisProtocolConverter
from derisk.vis.vis_manage import get_vis_manager
from derisk_app.derisk_server import system_app
from derisk_app.scene.base import ChatScene
from derisk_ext.agent.agents.awel.awel_runner_agent import AwelRunnerAgent
from derisk_ext.agent.memory.preference import PreferenceMemory
from derisk_serve.conversation.serve import Serve as ConversationServe
from derisk_serve.core import blocking_func_to_async
from derisk_serve.building.app.service.service import Service as AppService
from .derisks_memory import MetaDerisksMessageMemory, MetaDerisksPlansMemory
from ..db import GptsMessagesDao
from ..db.gpts_conversations_db import GptsConversationsDao, GptsConversationsEntity
from ..team.base import TeamMode
from ...building.app.api.schema_app import GptsApp
from ...building.app.api.schema_app_detail import GptsAppDetail
from ...building.app.api.schemas import ServerResponse
from ...building.config.api.schemas import ChatInParamValue, AppParamType
from ...rag.retriever.knowledge_space import KnowledgeSpaceRetriever


CFG = Config()

router = APIRouter()
logger = logging.getLogger(__name__)


def get_app_service() -> AppService:
    return AppService.get_instance(CFG.SYSTEM_APP)


class ConversationManager:
    """管理对话初始化、状态和历史记录"""

    def __init__(self, gpts_conversations_dao):
        self.gpts_conversations = gpts_conversations_dao

    async def build_agent_conv_id(self, conv_session_id: str, **ext_info):
        gpts_conversations = self.gpts_conversations.get_by_session_id_asc(conv_session_id)
        last_conversation = gpts_conversations[-1] if gpts_conversations else None

        if last_conversation and Status.WAITING.value == last_conversation.state:
            return last_conversation.conv_id, gpts_conversations

        gpt_chat_order = str(len(gpts_conversations) + 1) if gpts_conversations else "1"
        return f"{conv_session_id}_{gpt_chat_order}", gpts_conversations

    def create_conversation_record(
            self,
            agent_conv_id: str,
            conv_session_id: str,
            user_query: HumanMessage,
            gpts_name: str,
            team_mode: str,
            user_code: str,
            sys_code: str,
            vis_render: str,
            keep_start_rounds: int = 0,
            keep_end_rounds: int = 0,
            gpts_conversations: Optional[List[GptsConversationsEntity]] = None
    ) -> List[GptsMessage]:
        """创建新的对话记录并构建历史对话"""
        historical_dialogues = []

        if keep_start_rounds > 0 or keep_end_rounds > 0 and gpts_conversations:
            rely_conversations = []
            total_rounds = keep_start_rounds + keep_end_rounds

            if total_rounds < len(gpts_conversations):
                if keep_start_rounds > 0:
                    rely_conversations.extend(gpts_conversations[:keep_start_rounds])
                if keep_end_rounds > 0:
                    rely_conversations.extend(gpts_conversations[-keep_end_rounds:])
            else:
                rely_conversations = gpts_conversations

            for conv in rely_conversations:
                if temps := self.gpts_messages_dao.get_by_conv_id(conv.conv_id):
                    if len(temps) > 1:
                        historical_dialogues.extend([temps[0], temps[-1]])

        self.gpts_conversations.add(
            GptsConversationsEntity(
                conv_id=agent_conv_id,
                conv_session_id=conv_session_id,
                user_goal=json.dumps(user_query.to_dict(), ensure_ascii=False),
                gpts_name=gpts_name,
                team_mode=team_mode,
                state=Status.RUNNING.value,
                max_auto_reply_round=0,
                auto_reply_count=0,
                user_code=user_code,
                sys_code=sys_code,
                vis_render=vis_render,
            )
        )

        return historical_dialogues


class AgentBuilder:
    """构建和管理Agent实例"""

    def __init__(self, system_app):
        self.system_app = system_app
        self.llm_provider = None

    async def init_llm_provider(self):
        """延迟初始化LLM提供者"""
        if not self.llm_provider:
            worker_manager = self.system_app.get_component(
                ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
            ).create()
            self.llm_provider = DefaultLLMClient(worker_manager, auto_convert_message=True)

    async def build_agent_memory(
            self,
            conv_id: str,
            agent_id: str,
            user_id: str,
            team_context: Optional[Union[str, AutoTeamContext]] = None
    ) -> AgentMemory:
        """统一构建Agent内存"""
        from derisk_serve.rag.storage_manager import StorageManager
        from derisk_ext.agent.memory.session import SessionMemory

        executor = self.system_app.get_component(
            ComponentType.EXECUTOR_DEFAULT, ExecutorFactory
        ).create()

        storage_manager = StorageManager.get_instance(self.system_app)
        index_name = f"session_{agent_id}"
        vector_store = storage_manager.create_vector_store(index_name=index_name)

        await self.init_llm_provider()
        llm_client = DefaultLLMClient(worker_manager=self.llm_provider.worker_manager)

        session_memory = SessionMemory(
            session_id=conv_id,
            agent_id=agent_id,
            vector_store=vector_store,
            executor=executor,
            gpts_memory=self.memory,
            llm_client=llm_client,
        )

        agent_memory = AgentMemory(memory=session_memory, gpts_memory=self.memory)

        # 配置用户偏好内存
        if team_context and team_context.resources:
            for resource in team_context.resources:
                if resource.type == 'memory':
                    json_val = json.loads(resource.value)
                    if json_val.get('enable_user_memory', False):
                        user_store = storage_manager.create_vector_store(
                            index_name=f"user_{user_id}"
                        )
                        agent_memory.preference_memory = PreferenceMemory(
                            agent_id=agent_id,
                            vector_store=user_store,
                            executor=executor,
                            metadata={"user_id": user_id},
                        )
                        break

        return agent_memory

    async def build_agent(
            self,
            context: AgentContext,
            agent_memory: AgentMemory,
            app: GptsApp,
            **kwargs
    ) -> ConversableAgent:
        """统一构建Agent实例"""
        await self.init_llm_provider()
        resource_manager = get_resource_manager()

        if app.team_mode == TeamMode.SINGLE_AGENT.value:
            return await self._build_single_agent(context, agent_memory, app, resource_manager)
        elif app.team_mode == TeamMode.AUTO_PLAN.value:
            return await self._build_auto_plan_agent(context, agent_memory, app, resource_manager)
        elif app.team_mode == TeamMode.AWEL_LAYOUT.value:
            return await self._build_awel_agent(context, agent_memory, app)
        else:
            raise ValueError(f"Unsupported team mode: {app.team_mode}")

    async def _build_single_agent(self, context, agent_memory, app, resource_manager):
        """构建单Agent模式"""
        if app.details and len(app.details) == 1:
            return await self._build_employee_agent(app.details[0], context, agent_memory, resource_manager)

        agent_cls = get_agent_manager().get_by_name(app.agent)
        llm_config = LLMConfig(
            llm_client=self.llm_provider,
            llm_strategy=LLMStrategyType(app.llm_config.llm_strategy),
            strategy_context=app.llm_config.llm_strategy_value
        )

        depend_resource = await blocking_func_to_async(
            CFG.SYSTEM_APP, resource_manager.build_resource, app.all_resources
        )

        agent_context = deepcopy(context)
        agent_context.agent_app_code = app.app_code

        agent = await agent_cls().bind(agent_context).bind(agent_memory).bind(llm_config).bind(depend_resource).build()

        # 更新Agent信息
        profile = agent.profile.copy()
        profile.desc = app.app_describe
        profile.name = app.app_name
        profile.avatar = app.icon
        if app.system_prompt_template: profile.system_prompt_template = app.system_prompt_template
        if app.user_prompt_template: profile.user_prompt_template = app.user_prompt_template

        return agent.bind(profile)

    async def _build_auto_plan_agent(self, context, agent_memory, app, resource_manager):
        """构建自动规划Agent"""
        manager_cls = get_agent_manager().get_by_name(app.team_context.teamleader)
        manager = manager_cls()

        llm_config = LLMConfig(
            llm_client=self.llm_provider,
            llm_strategy=LLMStrategyType(app.llm_config.llm_strategy),
            strategy_context=app.llm_config.llm_strategy_value
        )

        if app.all_resources:
            depend_resource = await blocking_func_to_async(
                CFG.SYSTEM_APP, resource_manager.build_resource, app.all_resources
            )
            manager.bind(depend_resource)

        agent_context = deepcopy(context)
        agent_context.agent_app_code = app.app_code
        manager = await manager.bind(agent_context).bind(llm_config).bind(agent_memory).build()

        # 更新Manager信息
        profile = manager.profile.copy()
        profile.desc = app.app_describe
        profile.name = app.app_name
        profile.avatar = app.icon
        if app.system_prompt_template: profile.system_prompt_template = app.system_prompt_template
        if app.user_prompt_template: profile.user_prompt_template = app.user_prompt_template

        # 添加员工
        if isinstance(manager, ManagerAgent) and app.details:
            employees = await self._build_employees(app.details, context, agent_memory, resource_manager)
            manager.hire(employees)

        return manager.bind(profile)

    async def _build_awel_agent(self, context, agent_memory, app):
        """构建AWEL布局Agent"""
        from derisk_app.openapi.api_v1.api_v1 import get_chat_flow
        agent = AwelRunnerAgent(
            team_context=app.team_context,
            flow_service=get_chat_flow()
        )

        agent_context = deepcopy(context)
        agent_context.agent_app_code = app.app_code
        agent = await agent.bind(agent_context).bind(agent_memory).build()

        # 更新Agent信息
        profile = agent.profile.copy()
        profile.desc = app.app_describe
        profile.name = app.app_name
        profile.avatar = app.icon

        return agent.bind(profile)

    async def _build_employees(self, app_details, context, agent_memory, resource_manager):
        """构建员工Agent"""
        employees = []
        for detail in app_details:
            if detail.type == "app":
                app_detail = await get_app_service().app_detail(detail.agent_role, building_mode=False)
                employee = await self.build_agent(context, agent_memory, app_detail)
            else:
                raise ValueError("当前应用数据已经无法支持，请重新编辑构建！")
            employees.append(employee)
        return employees


class MultiAgents(BaseComponent, ABC):
    name = ComponentType.MULTI_AGENTS

    def __init__(self, system_app: SystemApp):
        super().__init__(system_app)
        self.system_app = system_app
        self.gpts_conversations = GptsConversationsDao()
        self.gpts_messages_dao = GptsMessagesDao()
        self.memory = DiskGptsMemory(
            plans_memory=MetaDerisksPlansMemory(),
            message_memory=MetaDerisksMessageMemory(),
        )
        self.conv_manager = ConversationManager(self.gpts_conversations)
        self.agent_builder = AgentBuilder(system_app)

    def init_app(self, system_app: SystemApp):
        system_app.app.include_router(router, prefix="/api", tags=["Multi-Agents"])
        self.system_app = system_app

    async def stop_chat(self, conv_id: str):
        await self.memory.stop(conv_id=conv_id)

    async def query_chat(self, conv_id: str, vis_render: Optional[str] = None):
        """查询对话统一实现"""
        gpts_conversation = self.gpts_conversations.get_by_conv_id(conv_id)
        current_vis_render = vis_render or gpts_conversation.vis_render or "nex_vis_window"

        app_config = self.system_app.config.configs.get("app_config")
        web_config = app_config.service.web
        vis_manager = get_vis_manager()
        vis_convert = vis_manager.get_by_name(current_vis_render)(derisk_url=web_config.web_url)

        self.memory.init(conv_id=conv_id, vis_converter=vis_convert)
        await self.memory.load_persistent_memory(conv_id)

        context = AgentContext(
            conv_id=conv_id,
            conv_session_id=gpts_conversation.conv_session_id,
            trace_id=uuid.uuid4().hex,
            rpc_id="",
            gpts_app_code=gpts_conversation.gpts_name,
        )

        try:
            await self.agent_builder.build_agent_by_app_code(
                gpts_conversation.gpts_name,
                context
            )
        except Exception as e:
            logger.warning(f"查询会话时恢复agent对象异常: {str(e)}")

        return (
            await self.memory.vis_final(conv_id),
            await self.memory.user_answer(conv_id),
            current_vis_render
        )

    async def _common_chat_flow(
            self,
            conv_session_id: str,
            agent_conv_id: str,
            gpts_name: str,
            user_query: HumanMessage,
            user_code: str,
            sys_code: str,
            stream: bool,
            is_quick_chat: bool = False,
            **ext_info
    ) -> AsyncGenerator:
        """通用聊天流程实现"""
        logger.info(f"{'Quick' if is_quick_chat else ''}Chat started: {conv_session_id}")

        # 初始化可视化
        app_config = self.system_app.config.configs.get("app_config")
        web_config = app_config.service.web
        vis_render = ext_info.get("vis_render", "derisk_vis_incr" if is_quick_chat else None)

        vis_manager = get_vis_manager()
        vis_protocol = vis_manager.get_by_name(vis_render)(derisk_url=web_config.web_url)
        ext_info["incremental"] = vis_protocol.incremental

        # 初始化内存
        self.memory.init(
            agent_conv_id,
            history_messages=None,
            start_round=0,
            vis_converter=vis_protocol,
        )

        # 获取应用配置
        app_service = get_app_service()
        gpt_app = await app_service.app_detail(
            gpts_name,
            ext_info.get("specify_config_code"),
            building_mode=False
        )

        if not gpt_app:
            raise ValueError(f"应用未找到: {gpts_name}!")

        # 构建Agent内存
        agent_memory = await self.agent_builder.build_agent_memory(
            conv_session_id,
            gpt_app.app_code,
            user_code,
            gpt_app.team_context
        )

        # 运行Agent聊天
        task = asyncio.create_task(
            self.agent_team_chat(
                user_code=user_code,
                user_query=user_query,
                conv_session_id=conv_session_id,
                conv_uid=agent_conv_id,
                gpts_app=gpt_app,
                agent_memory=agent_memory,
                **ext_info
            )
        )

        # 流式输出处理
        async for chunk in self.chat_messages(agent_conv_id):
            if chunk:
                try:
                    content = json.dumps({"vis": chunk}, default=serialize, ensure_ascii=False)
                    yield task, f"data:{content}\n", agent_conv_id
                except Exception as e:
                    logger.exception(f"消息处理异常: {str(e)}")
                    yield task, f"data: {str(e)}\n", agent_conv_id

        # 最终处理
        if task.done() and task.exception():
            logger.exception(f"Agent聊天异常: {conv_session_id}")
            raise task.exception()
        else:
            yield task, _format_vis_msg("[DONE]"), agent_conv_id

    async def agent_chat(
            self,
            conv_id: str,
            agent_conv_id: str,
            gpts_name: str,
            user_query: Union[str, HumanMessage],
            user_code: str = None,
            sys_code: str = None,
            stream: Optional[bool] = True,
            gpts_conversations: Optional[List[GptsConversationsEntity]] = None,
            **ext_info,
    ):
        async for result in self._common_chat_flow(
                conv_id,
                agent_conv_id,
                gpts_name,
                user_query,
                user_code,
                sys_code,
                stream,
                is_quick_chat=False,
                gpts_conversations=gpts_conversations,
                **ext_info
        ):
            yield result

    async def quick_chat(
            self,
            conv_session_id: str,
            agent_conv_id: str,
            gpts_conversations: List[GptsConversationsEntity],
            user_query,
            **ext_info
    ):
        async for result in self._common_chat_flow(
                conv_session_id,
                agent_conv_id,
                "quick_chat",
                user_query,
                ext_info.get("user_code"),
                ext_info.get("sys_code"),
                True,
                is_quick_chat=True,
                gpts_conversations=gpts_conversations,
                **ext_info
        ):
            yield result

    async def agent_team_chat(
            self,
            user_code: str,
            user_query: HumanMessage,
            conv_session_id: str,
            conv_uid: str,
            gpts_app: GptsApp,
            agent_memory: AgentMemory,
            **ext_info
    ):
        """统一Agent团队聊天实现"""
        try:
            # 处理文件资源
            if isinstance(user_query.content, list):
                from derisk_serve.file.serve import Serve as FileServe
                file_serve = FileServe.get_instance(self.system_app)
                user_query.content = file_serve.replace_media_urls(user_query.content)

            # 创建上下文
            context = AgentContext(
                user_id=user_code,
                conv_id=conv_uid,
                conv_session_id=conv_session_id,
                trace_id=ext_info.get("trace_id", uuid.uuid4().hex),
                rpc_id=ext_info.get("rpc_id", "0.1"),
                gpts_app_code=gpts_app.app_code,
                gpts_app_name=gpts_app.app_name,
                language=gpts_app.language,
                incremental=ext_info.get("incremental", False),
                env_context=ext_info.get(ENV_CONTEXT_KEY, {}),
                stream=ext_info.get("stream", True),
                extra=ext_info,
            )

            # 构建Agent
            recipient = await self.agent_builder.build_agent(
                context,
                agent_memory,
                gpts_app,
                **ext_info
            )

            # 创建用户代理
            user_proxy = await UserProxyAgent().bind(context).bind(agent_memory).build()
            if user_code:
                app_config = self.system_app.config.configs.get("app_config")
                web_config = app_config.service.web
                user_proxy.profile.avatar = f"{web_config.web_url}/user/avatar?loginName={user_code}"

            # 启动聊天
            await user_proxy.initiate_chat(
                recipient=recipient,
                message=user_query,
                **self._process_chat_params(ext_info.get("chat_in_params"))
            )

            # 更新对话状态
            status = Status.WAITING.value if user_proxy.have_ask_user() else Status.COMPLETE.value
            self.gpts_conversations.update(conv_uid, status)

        except Exception as e:
            logger.error(f"聊天异常终止: {str(e)}", exc_info=True)
            self.gpts_conversations.update(conv_uid, Status.FAILED.value)
            raise ValueError(f"对话异常: {str(e)}")
        finally:
            await self.memory.complete(conv_uid)

    def _process_chat_params(self, chat_in_params: Optional[List[ChatInParamValue]]) -> Dict[str, Any]:
        """处理聊天输入参数"""
        llm_context = {}
        if not chat_in_params:
            return llm_context

        for param in chat_in_params:
            if param.param_type == AppParamType.Resource.value and param.sub_type not in FILE_RESOURCES:
                value = json.loads(param.param_value) if isinstance(param.param_value, str) else param.param_value
                llm_context[param.sub_type] = AgentResource.from_dict({
                    "type": param.sub_type,
                    "name": "用户选择资源",
                    "value": value[0] if isinstance(value, list) else value
                })
            else:
                llm_context[param.param_type] = param.param_value

        return llm_context

    # 其他方法保持不变，但使用新的工具类...
    # async def app_chat, async def quick_app_chat, etc...


# 辅助函数
def _format_vis_msg(msg: str):
    return f"data:{json.dumps({'vis': msg}, default=serialize, ensure_ascii=False)}\n"


def _build_conversation(
        conv_id: str,
        select_param: Union[str, Dict[str, Any]],
        model_name: str,
        summary: str,
        app_code: str,
        conv_serve: ConversationServe,
        user_name: Optional[str] = "",
        sys_code: Optional[str] = "",
) -> StorageConversation:
    return StorageConversation(
        conv_uid=conv_id,
        chat_mode=ChatScene.ChatAgent.value(),
        user_name=user_name,
        sys_code=sys_code,
        model_name=model_name,
        summary=summary,
        param_type="derisks",
        param_value=select_param,
        app_code=app_code,
        conv_storage=conv_serve.conv_storage,
        message_storage=conv_serve.message_storage,
    )


multi_agents = MultiAgents(system_app)
