"""Proxy models."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from derisk.model.proxy.llms.chatgpt import OpenAILLMClient
    from derisk.model.proxy.llms.claude import ClaudeLLMClient
    from derisk.model.proxy.llms.deepseek import DeepseekLLMClient
    from derisk.model.proxy.llms.gemini import GeminiLLMClient
    from derisk.model.proxy.llms.gitee import GiteeLLMClient
    from derisk.model.proxy.llms.moonshot import MoonshotLLMClient
    from derisk.model.proxy.llms.ollama import OllamaLLMClient
    from derisk.model.proxy.llms.siliconflow import SiliconFlowLLMClient
    from derisk.model.proxy.llms.spark import SparkLLMClient
    from derisk.model.proxy.llms.tongyi import TongyiLLMClient
    from derisk.model.proxy.llms.wenxin import WenxinLLMClient
    from derisk.model.proxy.llms.yi import YiLLMClient
    from derisk.model.proxy.llms.zhipu import ZhipuLLMClient
    from derisk.model.proxy.llms.volcengine import VolcengineLLMClient

def __lazy_import(name):
    module_path = {
        "OpenAILLMClient": "derisk.model.proxy.llms.chatgpt",
        "ClaudeLLMClient": "derisk.model.proxy.llms.claude",
        "GeminiLLMClient": "derisk.model.proxy.llms.gemini",
        "SiliconFlowLLMClient": "derisk.model.proxy.llms.siliconflow",
        "SparkLLMClient": "derisk.model.proxy.llms.spark",
        "TongyiLLMClient": "derisk.model.proxy.llms.tongyi",
        "WenxinLLMClient": "derisk.model.proxy.llms.wenxin",
        "ZhipuLLMClient": "derisk.model.proxy.llms.zhipu",
        "YiLLMClient": "derisk.model.proxy.llms.yi",
        "MoonshotLLMClient": "derisk.model.proxy.llms.moonshot",
        "OllamaLLMClient": "derisk.model.proxy.llms.ollama",
        "DeepseekLLMClient": "derisk.model.proxy.llms.deepseek",
        "GiteeLLMClient": "derisk.model.proxy.llms.gitee",
        "VolcengineLLMClient": "derisk.model.proxy.llms.volcengine",
    }

    if name in module_path:
        module = __import__(module_path[name], fromlist=[name])
        return getattr(module, name)
    else:
        raise AttributeError(f"module {__name__} has no attribute {name}")


def __getattr__(name):
    return __lazy_import(name)


__all__ = [
    "OpenAILLMClient",
    "ClaudeLLMClient",
    "GeminiLLMClient",
    "TongyiLLMClient",
    "ZhipuLLMClient",
    "WenxinLLMClient",
    "SiliconFlowLLMClient",
    "SparkLLMClient",
    "YiLLMClient",
    "MoonshotLLMClient",
    "OllamaLLMClient",
    "DeepseekLLMClient",
    "GiteeLLMClient",
    "VolcengineLLMClient",
]
