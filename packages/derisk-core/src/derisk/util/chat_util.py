import json
from dataclasses import asdict, is_dataclass
from typing import Union

from derisk._private.pydantic import BaseModel, model_to_json

SSE_DATA_TYPE = Union[str, BaseModel, dict]


def transform_to_sse(data: SSE_DATA_TYPE) -> str:
    """Transform data to Server-Sent Events format.

    Args:
        data: Data to transform to SSE format

    Returns:
        str: Data in SSE format

    Raises:
        ValueError: If data type is not supported
    """
    if isinstance(data, BaseModel):
        return (
            f"data: {model_to_json(data, exclude_unset=True, ensure_ascii=False)}\n\n"
        )
    elif isinstance(data, dict):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    elif isinstance(data, str):
        return f"data: {data}\n\n"
    elif is_dataclass(data):
        return f"data: {json.dumps(asdict(data), ensure_ascii=False)}\n\n"
    else:
        raise ValueError(f"Unsupported data type: {type(data)}")
