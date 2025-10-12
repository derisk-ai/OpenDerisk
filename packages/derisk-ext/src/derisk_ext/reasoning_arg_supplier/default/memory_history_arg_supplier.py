import dataclasses
import json
import logging
from typing import List, Optional, get_origin, get_args, Union
from datetime import datetime, timedelta

from derisk.agent import AgentMessage, AgentContext, ConversableAgent, AgentMemory, Agent
from derisk.agent.resource.memory import MemoryParameters
from derisk.util import pypantic_utils
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import (
    ReasoningAgent,
)
from derisk_ext.reasoning_arg_supplier.default.default_history_arg_supplier import \
    DefaultHistoryArgSupplier
from derisk.storage.vector_store.filters import MetadataFilter, MetadataFilters, FilterOperator

MEMORY_HISTORY_ARG_SUPPLIER_NAME = "MEMORY_HISTORY_ARG_SUPPLIER"
_NAME = MEMORY_HISTORY_ARG_SUPPLIER_NAME
_DESCRIPTION = "记忆参数引擎: memory"

MODEL_CONTEXT_LENGTH = {
    "deepseek-v3": 64000,
    "deepSeek-r1": 64000,
    "QwQ-32B": 64000,
}

logger = logging.getLogger(__name__)


class MemoryHistoryArgSupplier(DefaultHistoryArgSupplier):
    @property
    def name(self) -> str:
        return _NAME

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def arg_key(self) -> str:
        return "memory"

    @property
    def params(self) -> List[dict]:
        result = []
        for field in dataclasses.fields(MemoryParameters):
            if field.name == "name":
                continue
            if field.name == "message_condense_prompt":
                field_type = "textarea"
            elif field.name == "score_threshold":
                field_type = "slider"
            else:
                field_type = pypantic_utils.get_simple_type_name(field.type)
            field_info = {
                "name": field.name,
                "value": field.default if field.default is not dataclasses.MISSING else None,
                "type": field_type,
                "description": field.metadata.get("help", ""),
                "label": field.metadata.get("label", ""),
                "options": field.metadata.get("options", [])
            }
            if field_type == "slider":
                field_info["max"] = field.metadata.get("max", "1.0")
                field_info["min"] =  field.metadata.get("min", "0.0")
                field_info["step"] = field.metadata.get("step", "0.1")
            if field_info.get("options"):
                field_info["type"] = "array"
            result.append(field_info)
        return result

    async def supply(
        self,
        prompt_param: dict,
        agent: ConversableAgent,
        agent_context: Optional[AgentContext] = None,
        received_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> None:
        prompt_param["resources"] = []

        history = await self.search_memories(
            agent.memory,
            received_message,
            agent_context,
            agent.get_memory_parameters(),
            get_agent_llm_context_length(agent) - 8000,
            agent.agent_context.agent_app_code,
        )
        if history:
            prompt_param[self.arg_key] = history
        else:
            prompt_param[self.arg_key] = ""



    async def search_memories(
        self,
        memory: AgentMemory,
        received_message: AgentMessage,
        agent_context: AgentContext,
        memory_params: MemoryParameters,
        llm_token_limit: Optional[int] = None,
        agent_id: Optional[str] = None,
    ):
        """Search memories from AgentMemory

        Args:
            memory (AgentMemory): The agent's memory instance.
            received_message (AgentMessage): The message received by the agent.
            agent_context (AgentContext): Context of the agent.
            memory_params (MemoryParameters): Parameters for memory retrieval.
            llm_token_limit (Optional[int]): Token limit for LLM.
            agent_id (Optional[str]): agent_id.

        Returns:
            str: A string containing recent memory fragments formatted for the agent.
        """
        if not memory:
            return []

        preference_memory_read: bool = False
        if agent_context and agent_context.extra and agent_context.extra.__contains__("preference_memory_read"):
            preference_memory_read = agent_context.extra.get("preference_memory_read")

        if preference_memory_read:
            # 读取preference中的user_memory
            date = get_time_24h_ago()
            metadata_filter = MetadataFilter(key="create_time", operator=FilterOperator.GT, value=date)
            metadata_filters = MetadataFilters(filters=[metadata_filter])
            logger.info("coversation %s User Memory "
                        "search: %s, create_time >= %s", agent_context.conv_id, agent_context.user_id, date)
            memory_fragments = await memory.preference_memory.search(
                observation=received_message.current_goal,
                session_id=session_id_from_conv_id(agent_context.conv_id),
                # agent_id=agent_id,
                enable_global_session=memory_params.enable_global_session,
                # retrieve_strategy=memory_params.retrieve_strategy,
                retrieve_strategy="exact",
                # discard_strategy=memory_params.discard_strategy,
                discard_strategy="fifo",
                condense_prompt=memory_params.message_condense_prompt,
                condense_model=memory_params.message_condense_model,
                score_threshold=memory_params.score_threshold,
                top_k=memory_params.top_k,
                llm_token_limit=llm_token_limit,
                user_id=agent_context.user_id,#TODO 使用viewer
                metadata_filters=metadata_filters,
            )
        else:
            memory_fragments = await memory.search(
                observation=received_message.current_goal,
                session_id=session_id_from_conv_id(agent_context.conv_id),
                agent_id=agent_id,
                enable_global_session=memory_params.enable_global_session,
                retrieve_strategy=memory_params.retrieve_strategy,
                discard_strategy=memory_params.discard_strategy,
                condense_prompt=memory_params.message_condense_prompt,
                condense_model=memory_params.message_condense_model,
                score_threshold=memory_params.score_threshold,
                top_k=memory_params.top_k,
                llm_token_limit=llm_token_limit,
            )


        recent_messages = [
            f"\nRound:{m.rounds if m.rounds else m.metadata.get('rounds')}\n"
            f"Role:{m.role if m.role else m.metadata.get('role')}\n"
            f"{m.raw_observation}" for m in memory_fragments
        ]
        logger.info("coversation %s Session Memory "
                    "fragments found: %s", agent_context.conv_id, recent_messages)
        return "\n".join(recent_messages)


def get_agent_llm_context_length(agent: ConversableAgent) -> int:
        default_length = 32000
        if not agent:
            return default_length

        model_list = agent.llm_config.strategy_context
        if not model_list:
            return default_length
        if isinstance(model_list, str):
            try:
                model_list = json.loads(model_list)
            except Exception:
                return default_length

        return MODEL_CONTEXT_LENGTH.get(model_list[0], default_length)


def session_id_from_conv_id(conv_id: str) -> str:
        idx = conv_id.rfind("_")
        return conv_id[:idx] if idx else conv_id


def get_time_24h_ago() -> str:
    """
    返回当前时间往前推 24 小时后的时间字符串，格式为:
    "YYYY-MM-DD HH:MM:SS"
    """
    # 1. 取得当前本地时间（如果想要 UTC 可改为 datetime.utcnow()）
    now = datetime.now()
    # 2. 往前推 24 小时
    twenty_four_hours_ago = now - timedelta(hours=24)
    # 3. 按指定格式输出
    formatted = twenty_four_hours_ago.strftime("%Y-%m-%d %H:%M:%S")
    return formatted