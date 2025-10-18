import asyncio
import logging
import os
import httpx
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional, Type, Union

from derisk.core import ModelMetadata
from derisk.core.awel.flow import (
    TAGS_ORDER_HIGH,
    ResourceCategory,
    auto_register_resource,
)
from derisk.model.proxy.base import (
    AsyncGenerateStreamFunction,
    GenerateStreamFunction,
    register_proxy_model_adapter, ProxyLLMClient,
)
from derisk.model.proxy.llms.proxy_model import ProxyModel
from derisk.util.i18n_utils import _

if TYPE_CHECKING:
    from httpx._types import ProxiesTypes

logger = logging.getLogger(__name__)

_DEFAULT_API_BASE = "https://dashscope.aliyuncs.com/api/v1"
_DEFAULT_MODEL = "wan2.5-i2i-preview"


@auto_register_resource(
    label=_("Tongyi Proxy LLM"),
    category=ResourceCategory.LLM_CLIENT,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("Tongyi proxy LLM configuration."),
    documentation_url="https://help.aliyun.com/zh/model-studio/getting-started/first-api-call-to-qwen",
    show_in_ui=False,
)
@dataclass
class TongyiWanDeployModelParameters:
    """Deploy model parameters for Tongyi Image Generation."""

    provider: str = "proxy/wanxiang"

    api_base: Optional[str] = field(
        default=_DEFAULT_API_BASE,
        metadata={
            "help": _("The base url of the tongyi API."),
        },
    )

    api_key: Optional[str] = field(
        default="${env:DASHSCOPE_API_KEY}",
        metadata={
            "help": _("The API key of the tongyi API."),
            "tags": "privacy",
        },
    )

    model: Optional[str] = field(
        default=_DEFAULT_MODEL,
        metadata={
            "help": _("The model name for image generation."),
        }
    )

    timeout: Optional[int] = field(
        default=300,
        metadata={
            "help": _("Timeout for API requests in seconds."),
        }
    )


async def tongyi_generate_stream(
    model: ProxyModel, tokenizer, params, device, context_len=2048
):
    client: TongyiWanLLMClient = model.proxy_llm_client
    request_data = {
        "model": client.model,
        "input": {
            "prompt": params["prompt"],
            "images": params["images"]
        },
        "parameters": {
            "size": params.get("size", "1280*1280"),
            "n": params.get("n", 1)
        }
    }

    async with httpx.AsyncClient(base_url=client.api_base, proxies=client.proxies,
                                 timeout=client.timeout) as http_client:
        # Submit async task
        headers = {
            "Authorization": f"Bearer {client.api_key}",
            "X-DashScope-Async": "enable",
            "Content-Type": "application/json"
        }

        try:
            submit_response = await http_client.post(
                "/services/aigc/image2image/image-synthesis",
                headers=headers,
                json=request_data
            )
            submit_response.raise_for_status()
            task_id = submit_response.json()["output"]["task_id"]

            # Poll task status
            while True:
                await asyncio.sleep(2)  # Polling interval
                task_response = await http_client.get(
                    f"/tasks/{task_id}",
                    headers=headers
                )
                task_data = task_response.json()
                status = task_data["output"]["task_status"]

                if status == "SUCCEEDED":
                    results = task_data["output"]["results"]
                    for result in results:
                        yield result["url"]
                    break
                elif status in ["FAILED", "CANCELED"]:
                    error_msg = task_data.get("message", "Image generation failed")
                    raise RuntimeError(f"API request failed: {error_msg}")
                # Continue polling if status is PENDING or RUNNING

        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"API request failed: {e.response.text}") from e


class TongyiWanLLMClient(ProxyLLMClient):
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = _DEFAULT_MODEL,
        proxies: Optional["ProxiesTypes"] = None,
        timeout: Optional[int] = 300,

        **kwargs,
    ):
        self.api_base = api_base or os.getenv("DASHSCOPE_API_BASE") or _DEFAULT_API_BASE
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.model = model or _DEFAULT_MODEL
        self.proxies = proxies
        self.timeout = timeout


        super().__init__(model_names=[model])


    @property
    def default_model(self) -> str:
        return self.model

    @classmethod
    def param_class(cls) -> Type[TongyiWanDeployModelParameters]:
        return TongyiWanDeployModelParameters

    @classmethod
    def generate_stream_function(
        cls,
    ) -> Optional[Union[GenerateStreamFunction, AsyncGenerateStreamFunction]]:
        return tongyi_generate_stream


register_proxy_model_adapter(
    TongyiWanLLMClient,
    supported_models=[
        ModelMetadata(
            model=["wan2.5-i2i-preview"],
            description="Wan2.5 Image-to-Image Model",
            link="https://help.aliyun.com/zh/dashscope/developer-reference/overview-13",
            function_calling=False,
        ),
        ModelMetadata(
            model="wanx-v1",
            description="WanX Image Generation Model",
            link="https://help.aliyun.com/zh/dashscope/developer-reference/overview-13",
            function_calling=False,
        ),
    ],
)
