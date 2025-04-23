"""Some internal tools for the DERISK project."""

from typing_extensions import Annotated, Doc

from ...resource.tool.base import tool


@tool(description="List the supported models in DERISK project.")
def list_derisk_support_models(
    model_type: Annotated[
        str, Doc("The model type, LLM(Large Language Model) and EMBEDDING).")
    ] = "LLM",
) -> str:
    """List the supported models in derisk."""
    from derisk.configs.model_config import EMBEDDING_MODEL_CONFIG, LLM_MODEL_CONFIG

    if model_type.lower() == "llm":
        supports = list(LLM_MODEL_CONFIG.keys())
    elif model_type.lower() == "embedding":
        supports = list(EMBEDDING_MODEL_CONFIG.keys())
    else:
        raise ValueError(f"Unsupported model type: {model_type}")
    return "\n\n".join(supports)
