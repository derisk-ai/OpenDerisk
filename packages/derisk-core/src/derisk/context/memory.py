def get_or_build_memory(
    agent_id: str,
) -> "PreferenceMemory":
    """ 上下文Memory
    Args:
        agent_id:(str) app_code
    """
    from derisk_serve.rag.storage_manager import StorageManager
    from derisk_ext.agent.memory.preference import PreferenceMemory
    from derisk.component import ComponentType
    from derisk.util.executor_utils import ExecutorFactory
    from derisk._private.config import Config
    CFG = Config()
    executor = CFG.SYSTEM_APP.get_component(ComponentType.EXECUTOR_DEFAULT, ExecutorFactory).create()
    storage_manager = StorageManager.get_instance(CFG.SYSTEM_APP)
    index_name = f"context_{agent_id}"
    vector_store = storage_manager.create_vector_store(index_name=index_name)
    preference_memory = PreferenceMemory(
        agent_id=agent_id,
        vector_store=vector_store,
        executor=executor,
    )
    return preference_memory