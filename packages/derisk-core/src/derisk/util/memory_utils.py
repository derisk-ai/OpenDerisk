from typing import Any
import json
from pympler import asizeof

MODEL_CONTEXT_LENGTH = {
    "DeepSeek-V3": 64000,
    "DeepSeek-R1": 64000,
    "QwQ-32B": 64000,
}


def _get_object_bytes(obj: Any) -> int:
    """Get the bytes of a object in memory

    Args:
        obj (Any): The object to return the bytes
    """
    return asizeof.asizeof(obj)


def get_agent_llm_context_length(model_list: str) -> int:
    default_length = 32000
    if not model_list:
        return default_length
    if isinstance(model_list, str):
        try:
            model_list = json.loads(model_list)
        except Exception:
            return default_length
    return MODEL_CONTEXT_LENGTH.get(model_list[0], default_length)