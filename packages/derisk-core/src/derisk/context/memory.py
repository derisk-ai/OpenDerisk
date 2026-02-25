def get_or_build_memory(
    agent_id: str,
) -> Optional["PreferenceMemory"]:
    """上下文Memory
    Args:
        agent_id:(str) app_code
    Returns:
        PreferenceMemory or None if vector store is not configured
    """
    from typing import Optional
    from derisk_serve.rag.storage_manager import StorageManager
    from derisk_ext.agent.memory.preference import PreferenceMemory
    from derisk_ext.agent.memory.session import (
        _METADATA_SESSION_ID,
        _METADATA_AGENT_ID,
        _MESSAGE_ID,
    )
    from derisk.component import ComponentType
    from derisk.util.executor_utils import ExecutorFactory
    from derisk._private.config import Config
    from derisk.util.executor_utils import DefaultExecutorFactory

    CFG = Config()
    try:
        executor = CFG.SYSTEM_APP.get_component(
            ComponentType.EXECUTOR_DEFAULT, ExecutorFactory
        ).create()
    except Exception:
        executor = DefaultExecutorFactory().create()
    storage_manager = StorageManager.get_instance(CFG.SYSTEM_APP)
    index_name = f"context_{agent_id}"
    vector_store = storage_manager.create_vector_store(
        index_name=index_name,
        extra_indexes=[_METADATA_SESSION_ID, _METADATA_AGENT_ID, _MESSAGE_ID],
    )
    if vector_store is None:
        return None
    preference_memory = PreferenceMemory(
        agent_id=agent_id,
        vector_store=vector_store,
        executor=executor,
    )
    return preference_memory
