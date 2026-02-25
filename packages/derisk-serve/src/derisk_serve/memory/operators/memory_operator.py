"""Operator to write preference memory for an agent."""

import json
from copy import copy
from typing import Dict, Optional, List

from derisk import SystemApp
from derisk.agent import (
    Memory,
    AgentMemory,
    MemoryFragment,
    AgentGenerateContext,
    AgentMessage,
)
from derisk.component import ComponentType
from derisk.core.awel import MapOperator
from derisk.core.awel.flow import ViewMetadata, OperatorCategory, Parameter, IOField
from derisk.core.awel.task.base import OUT
from derisk.storage.vector_store.filters import MetadataFilters, MetadataFilter
from derisk.util.executor_utils import ExecutorFactory


class PreferenceMemoryWriterOperator(MapOperator[AgentGenerateContext, OUT]):
    """Operator to write preference memory for an agent."""

    metadata = ViewMetadata(
        label="PreferenceMemoryWriterOperator",
        name="preference_memory_writer_operator",
        category=OperatorCategory.DATABASE,
        description="The PreferenceMemory Writer Operator.",
        parameters=[],
        inputs=[
            IOField.build_from(
                "Operator Request",
                "operator_request",
                AgentGenerateContext,
                "The Operator request.",
            )
        ],
        outputs=[
            IOField.build_from(
                "Operator Output",
                "operator_output",
                AgentGenerateContext,
                description="The Operator output.",
            )
        ],
    )

    def __init__(self, system_app: SystemApp, data_key: str = "memory", **kwargs):
        """Create a new PreferenceMemoryWriterOperator.

        Args:
            data_key (str): The key of the data_key.
            system_app (SystemApp): The system application instance.
            **kwargs: Additional keyword arguments.
        """
        self._system_app = system_app
        self._data_key = data_key
        # self._agent_memory = get_or_build_memory(
        #     system_app=system_app, agent_id=agent_id
        # )
        super().__init__(**kwargs)

    async def map(self, context: AgentGenerateContext) -> OUT:
        """Map the chunks to string."""
        from derisk_ext.agent.memory.preference import PreferenceMemoryFragment

        # Create a PreferenceMemoryFragment instance with the metadata
        agent_id = context.receiver.app_code
        agent_memory = get_or_build_memory(
            system_app=self._system_app, agent_id=agent_id
        )

        data_value = next(
            (
                item
                for item in [
                    # 从message的context中找
                    context.message.context[self._data_key]
                    if context.message
                    and context.message.context
                    and self._data_key in context.message.context
                    else None,
                    # 从dag_ctx变量中找
                    await self.current_dag_context.get_from_share_data(self._data_key),
                    # 直接取message
                    context.message.content,
                ]
                if item
            ),
            None,
        )

        if data_value:
            metadata = {self._data_key: data_value}
            if isinstance(data_value, dict):
                for key, value in data_value.items():
                    metadata[key] = value
            memory_fragment = PreferenceMemoryFragment(
                agent_id=agent_id,
                metadata=metadata,
            )
            await agent_memory.write(memory_fragment)

        result: AgentGenerateContext = copy(context)
        result.message = AgentMessage.init_new(rounds=context.message.rounds + 1)
        return result


class PreferenceMemorySearchOperator(MapOperator[AgentGenerateContext, OUT]):
    """Operator to search preference memory for an agent."""

    metadata = ViewMetadata(
        label="PreferenceMemorySearchOperator",
        name="preference_memory_search_operator",
        category=OperatorCategory.DATABASE,
        description="The PreferenceMemory Search Operator.",
        parameters=[],
        inputs=[
            IOField.build_from(
                "Operator Request",
                "operator_request",
                AgentGenerateContext,
                "The Operator request.",
            )
        ],
        outputs=[
            IOField.build_from(
                "Operator Output",
                "operator_output",
                AgentGenerateContext,
                description="The Operator output.",
            )
        ],
    )

    def __init__(self, system_app: SystemApp, data_key: str = "memory", **kwargs):
        """Create a new PreferenceMemoryWriterOperator.

        Args:
            agent_id (str): The ID of the agent.
            system_app (SystemApp): The system application instance.
            **kwargs: Additional keyword arguments.
        """
        self._system_app = system_app
        self._data_key = data_key
        super().__init__(**kwargs)

    async def map(
        self,
        context: AgentGenerateContext,
    ) -> OUT:
        """Map the metadata filters to memory fragments."""
        # metadata_filters = context.message or []
        # data_key = context.message.data_key
        metadata_filters = MetadataFilters(filters=[])
        agent_id = context.receiver.app_code
        agent_memory = get_or_build_memory(
            system_app=self._system_app, agent_id=agent_id
        )
        fragments: List[MemoryFragment] = await agent_memory.memory.search(
            agent_id=agent_id, metadata_filters=metadata_filters
        )
        memory: str = (
            fragments[-1].metadata.get(self._data_key, "")
            if (fragments and fragments[-1] and fragments[-1].metadata)
            else ""
        )
        result: AgentGenerateContext = copy(context)
        result.message = AgentMessage.init_new(
            content=memory, rounds=context.message.rounds + 1
        )
        return result


def get_or_build_memory(
    system_app: SystemApp,
    agent_id: str,
) -> Memory:
    """Get or build a Derisk memory instance for the given conversation ID.
    Args:
        system_app (SystemApp): The system application instance.
        agent_id:(str) app_code
    """
    from derisk.agent import ShortTermMemory

    storage_manager = StorageManager.get_instance(system_app)
    index_name = f"custom_{agent_id}"
    vector_store = storage_manager.create_vector_store(index_name=index_name)
    if vector_store is None:
        session_memory = ShortTermMemory(buffer_size=20)
        return AgentMemory(memory=session_memory)
    from derisk_ext.agent.memory.preference import PreferenceMemory

    executor = system_app.get_component(
        ComponentType.EXECUTOR_DEFAULT, ExecutorFactory
    ).create()
    preference_memory = PreferenceMemory(
        agent_id=agent_id,
        vector_store=vector_store,
        executor=executor,
    )
    agent_memory = AgentMemory(memory=preference_memory)
    return agent_memory
