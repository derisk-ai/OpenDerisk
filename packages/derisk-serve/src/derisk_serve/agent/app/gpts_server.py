from derisk._private.config import Config
from derisk.component import ComponentType
from derisk.model.cluster import BaseModelController
from derisk_serve.agent.db.gpts_app import GptsAppDao

CFG = Config()

gpts_dao = GptsAppDao()


async def available_llms(worker_type: str = "llm"):
    controller = CFG.SYSTEM_APP.get_component(
        ComponentType.MODEL_CONTROLLER, BaseModelController
    )
    types = set()
    models = await controller.get_all_instances(healthy_only=True)
    for model in models:
        worker_name, wt = model.model_name.split("@")
        if wt == worker_type:
            types.add(worker_name)
    
    # Also fetch models from global SystemApp config (including proxy models)
    if CFG.SYSTEM_APP and CFG.SYSTEM_APP.config:
        agent_llm_conf = CFG.SYSTEM_APP.config.get("agent.llm")
        if not agent_llm_conf:
            agent_conf = CFG.SYSTEM_APP.config.get("agent")
            if isinstance(agent_conf, dict):
                agent_llm_conf = agent_conf.get("llm")
        
        if agent_llm_conf and isinstance(agent_llm_conf.get("provider"), list):
             for p_conf in agent_llm_conf.get("provider"):
                 if isinstance(p_conf, dict) and "model" in p_conf:
                    p_models = p_conf.get("model")
                    if isinstance(p_models, list):
                        for m in p_models:
                            if isinstance(m, dict) and "name" in m:
                                types.add(m.get("name"))

        if agent_llm_conf and isinstance(agent_llm_conf.get("models"), list):
            for m in agent_llm_conf.get("models"):
                if isinstance(m, dict) and "model" in m:
                    types.add(m.get("model"))
        elif agent_llm_conf and agent_llm_conf.get("model"):
            types.add(agent_llm_conf.get("model"))
            
    return list(types)
