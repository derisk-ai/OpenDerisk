def find_default_model(config: AppConfig) -> Optional[Dict[str, Any]]:
    """从配置中查找默认模型

    Args:
        config: 应用配置

    Returns:
        默认模型配置字典，包含 provider, model_name, temperature, max_new_tokens 等
        如果没有找到返回 None
    """
    try:
        agent_llm = getattr(config, "agent_llm", None)
        if not agent_llm or not hasattr(agent_llm, "providers"):
            return None

        providers = agent_llm.providers or []

        # 查找第一个标记为 is_default 的模型
        for provider_config in providers:
            if not hasattr(provider_config, "models"):
                continue

            models = provider_config.models or []
            for model_config in models:
                if getattr(model_config, "is_default", False):
                    return {
                        "provider": provider_config.provider,
                        "model_name": model_config.name,
                        "temperature": model_config.temperature or 0.7,
                        "max_new_tokens": model_config.max_new_tokens or 4096,
                        "is_multimodal": getattr(model_config, "is_multimodal", False),
                        "api_base": provider_config.api_base,
                        "api_key_ref": provider_config.api_key_ref,
                    }

        # 如果没有找到 is_default，返回第一个 provider 的第一个模型
        if providers and hasattr(providers[0], "models") and providers[0].models:
            first_provider = providers[0]
            first_model = first_provider.models[0]
            return {
                "provider": first_provider.provider,
                "model_name": first_model.name,
                "temperature": first_model.temperature or 0.7,
                "max_new_tokens": first_model.max_new_tokens or 4096,
                "is_multimodal": getattr(first_model, "is_multimodal", False),
                "api_base": first_provider.api_base,
                "api_key_ref": first_provider.api_key_ref,
            }

        return None
    except Exception as e:
        logger.warning(f"Failed to find default model: {e}")
        return None


def get_all_models_from_config(config: AppConfig) -> List[str]:
    """从配置中获取所有模型名称

    Args:
        config: 应用配置

    Returns:
        模型名称列表
    """
    models = []
    try:
        agent_llm = getattr(config, "agent_llm", None)
        if not agent_llm or not hasattr(agent_llm, "providers"):
            return models

        providers = agent_llm.providers or []
        for provider_config in providers:
            if not hasattr(provider_config, "models"):
                continue

            for model_config in provider_config.models or []:
                if hasattr(model_config, "name") and model_config.name:
                    models.append(model_config.name)

        return models
    except Exception as e:
        logger.warning(f"Failed to get all models from config: {e}")
        return models
