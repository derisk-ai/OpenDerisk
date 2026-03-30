import logging
from typing import Dict, Any, Optional, List, Tuple
from copy import deepcopy

logger = logging.getLogger(__name__)


class ModelConfigCache:
    """全局模型配置缓存

    支持两种格式存储：
    - provider/model: 完整格式，如 "openai/DeepSeek-V3"
    - model: 简单格式，用于查找默认 provider
    """

    _instance = None
    _model_configs: Dict[str, Dict[str, Any]] = {}  # key: "provider/model"
    _model_providers: Dict[
        str, List[str]
    ] = {}  # key: model_name, value: list of provider keys

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register_configs(cls, configs: Dict[str, Dict[str, Any]]):
        """注册模型配置

        Args:
            configs: key 为 "provider/model" 格式，value 为配置
        """
        for key, config in configs.items():
            cls._model_configs[key] = config

            # 提取模型名，建立模型到 provider 的映射
            model_name = config.get("model") or key.split("/")[-1]
            if model_name not in cls._model_providers:
                cls._model_providers[model_name] = []
            if key not in cls._model_providers[model_name]:
                cls._model_providers[model_name].append(key)

        logger.info(f"ModelConfigCache: registered {len(configs)} models")
        for model, providers in cls._model_providers.items():
            logger.info(f"  {model}: {providers}")

    @classmethod
    def get_config(cls, model_key: str) -> Optional[Dict[str, Any]]:
        """获取模型配置

        Args:
            model_key: 可以是 "provider/model" 格式，或纯模型名

        Returns:
            模型配置，如果没找到返回 None
        """
        # 先尝试完整 key
        if model_key in cls._model_configs:
            return cls._model_configs[model_key]

        # 如果是纯模型名，返回第一个 provider 的配置
        if model_key in cls._model_providers:
            providers = cls._model_providers[model_key]
            if providers:
                return cls._model_configs[providers[0]]

        return None

    @classmethod
    def has_model(cls, model_key: str) -> bool:
        """检查模型是否存在"""
        if model_key in cls._model_configs:
            return True
        if model_key in cls._model_providers:
            return True
        return False

    @classmethod
    def get_all_models(cls) -> List[str]:
        """获取所有模型名（去重）"""
        return list(cls._model_providers.keys())

    @classmethod
    def get_all_model_keys(cls) -> List[str]:
        """获取所有模型 key（provider/model 格式）"""
        return list(cls._model_configs.keys())

    @classmethod
    def clear(cls):
        """清空缓存"""
        cls._model_configs = {}
        cls._model_providers = {}

    @classmethod
    def is_multimodal(cls, model_key: str) -> bool:
        """检查模型是否支持多模态（图片输入）

        Args:
            model_key: 可以是 "provider/model" 格式，或纯模型名

        Returns:
            是否支持多模态，如果没找到配置返回 False
        """
        config = cls.get_config(model_key)
        if config:
            return config.get("is_multimodal", False)
        return False

    @classmethod
    def get_multimodal_models(cls) -> List[str]:
        """获取所有支持多模态的模型名

        Returns:
            支持图片输入的模型列表
        """
        multimodal_models = []
        for model_name in cls._model_providers.keys():
            if cls.is_multimodal(model_name):
                multimodal_models.append(model_name)
        return multimodal_models


def parse_provider_configs(
    global_agent_conf: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """解析 [[agent.llm.provider]] 配置

    Args:
        global_agent_conf: agent.llm 配置

    Returns:
        key 为 "provider/model" 格式的配置映射，包含 is_multimodal 字段标识是否支持图片输入
    """
    model_configs = {}

    if not global_agent_conf:
        return model_configs

    providers_list = global_agent_conf.get("provider")

    if not isinstance(providers_list, list):
        return model_configs

    for provider_conf in providers_list:
        if not isinstance(provider_conf, dict):
            continue

        provider_name = provider_conf.get("provider", "default")
        p_defaults = {
            k: v for k, v in provider_conf.items() if k not in ["model", "provider"]
        }
        p_defaults["provider"] = provider_name

        if "api_base" in p_defaults and "base_url" not in p_defaults:
            p_defaults["base_url"] = p_defaults["api_base"]

        p_models = provider_conf.get("model", [])
        if isinstance(p_models, list):
            for m_conf in p_models:
                if not isinstance(m_conf, dict):
                    continue

                model_name = m_conf.get("name") or m_conf.get("model")
                if not model_name:
                    continue

                final_conf_dict = deepcopy(p_defaults)
                final_conf_dict.update(m_conf)
                if "api_base" in final_conf_dict and "base_url" not in final_conf_dict:
                    final_conf_dict["base_url"] = final_conf_dict["api_base"]
                if "name" in final_conf_dict and "model" not in final_conf_dict:
                    final_conf_dict["model"] = model_name

                is_multimodal = m_conf.get(
                    "is_multimodal", m_conf.get("supports_vision", False)
                )
                final_conf_dict["is_multimodal"] = bool(is_multimodal)

                api_key_ref = final_conf_dict.get("api_key_ref", "")
                if api_key_ref and not final_conf_dict.get("api_key"):
                    try:
                        from derisk_core.config.encryption import (
                            ConfigReferenceResolver,
                        )

                        resolved_value = ConfigReferenceResolver.resolve(api_key_ref)
                        if resolved_value and isinstance(resolved_value, str):
                            final_conf_dict["api_key"] = resolved_value
                            logger.debug(
                                f"Resolved api_key_ref for {provider_name}/{model_name}: "
                                f"{resolved_value[:8]}...{resolved_value[-4:] if len(resolved_value) > 12 else ''}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to resolve api_key_ref for {provider_name}/{model_name}: {e}"
                        )

                config_key = f"{provider_name}/{model_name}"
                model_configs[config_key] = final_conf_dict

    return model_configs
