import logging
import os
import json
from concurrent.futures import Executor
from dataclasses import dataclass, field
from typing import Iterator, Optional, Type, Union
from derisk.util.i18n_utils import _

from derisk.core import MessageConverter, ModelMetadata, ModelOutput, ModelRequest
from derisk.core.awel.flow import (
    TAGS_ORDER_HIGH,
    ResourceCategory,
    auto_register_resource,
)
from derisk.core.interface.parameter import LLMDeployModelParameters
from derisk.model.proxy.base import (
    AsyncGenerateStreamFunction,
    GenerateStreamFunction,
    ProxyLLMClient,
    register_proxy_model_adapter,
)
from derisk.model.proxy.llms.proxy_model import ProxyModel, parse_model_request
from .chatgpt import OpenAICompatibleDeployModelParameters

_DEFAULT_MODEL = "volc/deepseek-r1"
_DEFAULT_PLATFORM = "derisk"
_DEFAULT_API_BASE = "https://zdfmng.alipay.com/chat/completions"

logger = logging.getLogger(__name__)


@auto_register_resource(
    label=_("AntEngine Proxy LLM"),
    category=ResourceCategory.LLM_CLIENT,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("AntEngine proxy LLM configuration."),
    documentation_url="https://yuque.antfin.com/ntzgfe/kg7h1z/cx0cb0m2w3rui5k8#hJFXC",
    show_in_ui=False,
)
@dataclass
class AntEngineDeployModelParameters(OpenAICompatibleDeployModelParameters):
    """Deploy model parameters for AntEngine."""

    provider: str = "proxy/antengine"

    api_base: Optional[str] = field(
        default=_DEFAULT_API_BASE,
        metadata={
            "help": _("The base url of the AntEngine API."),
        },
    )

    api_key: Optional[str] = field(
        default="${env:ANTENGINE_API_KEY}",
        metadata={
            "help": _("The API key of the AntEngine API."),
            "tags": "privacy",
        },
    )


def antengine_generate_stream(
    model: ProxyModel, tokenizer, params, device, content_len=2048
):
    client: AntEngineLLMClient = model.proxy_llm_client
    request = parse_model_request(params, client.default_model, stream=True)
    for r in client.sync_generate_stream(request):
        yield r


class AntEngineLLMClient(ProxyLLMClient):
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = _DEFAULT_MODEL,
        context_length: Optional[int] = 131072,
        executor: Optional[Executor] = None,
    ):
        self.api_base = api_base or os.getenv("ANTENGINE_API_BASE") or _DEFAULT_API_BASE
        self.api_key = api_key or os.getenv("ANTENGINE_API_KEY")
        self.model = model
        super().__init__(
            model_names=[model],
            context_length=context_length,
            executor=executor,
        )

    @classmethod
    def new_client(
        cls,
        model_params: LLMDeployModelParameters,
        default_executor: Executor | None = None,
    ) -> "AntEngineLLMClient":
        return cls(
            model=model_params.real_provider_model_name,
            api_base=model_params.api_base,
            api_key=model_params.api_key,
            context_length=model_params.context_length,
            executor=default_executor,
        )

    @property
    def default_model(self) -> str:
        model = self.model
        if not model:
            model = _DEFAULT_MODEL
        return model

    @classmethod
    def param_class(cls) -> Type[AntEngineDeployModelParameters]:
        """Get the deploy model parameters class."""
        return AntEngineDeployModelParameters

    @classmethod
    def generate_stream_function(
        cls,
    ) -> Optional[Union[GenerateStreamFunction, AsyncGenerateStreamFunction]]:
        """Get the generate stream function."""
        return antengine_generate_stream

    def sync_generate_stream(
        self,
        request: ModelRequest,
        message_converter: Optional[MessageConverter] = None,
    ) -> Iterator[ModelOutput]:
        request = self.local_covert_message(request, message_converter)
        messages = request.to_common_messages(support_system_role=True)
        model = request.model or self.model
        try:
            logger.debug(
                f"Send request to antengine ai, model: {model}, request: {request}"
            )
            try:
                import requests
            except ImportError as e:
                raise ValueError(
                    "Could not import requests, please install it by `pip install requests`"
                ) from e

            request_model = self.model
            if request_model.startswith("volc"):
                request_model = request_model.replace("volc/", "volc-")
            elif request_model.startswith("aliyun"):
                request_model = request_model.split("/")[1]

            data = {
                "model": request_model,
                "messages": messages,
                "platform": _DEFAULT_PLATFORM,
                "stream": True,
                "temperature": request.temperature,
                "stop": request.stop,
                "max_tokens": request.max_new_tokens,
            }
            headers = {
                "Content-Type": "application/json",
                "X_ACCESS_KEY": self.api_key,
            }
            url = self.api_base

            response = requests.post(url, json=data, headers=headers, stream=True)
            response.encoding = "utf-8"
            reasoning_content = ""
            text = ""

            for line in response.iter_lines(decode_unicode=True):
                if line:
                    if line.startswith("data: "):
                        json_str = line[len("data: ") :]
                        try:
                            data = json.loads(json_str)
                            reasoning_content += data.get("reasoningContent", "")
                            text += data.get("completion", "")
                            if not text:
                                continue
                            if data == "[DONE]":
                                break
                        except json.JSONDecodeError:
                            print("Empty line")
                        yield ModelOutput.build(
                            text=text, thinking=reasoning_content, error_code=0
                        )
        except Exception as e:
            logger.error(f"Failed to send request to antengine ai: {e}")
            raise e


register_proxy_model_adapter(
    AntEngineLLMClient,
    supported_models=[
        ModelMetadata(
            model="上数/volc-deepseek-r1",
            context_length=64 * 1024,
            max_output_length=64 * 1024,
            description="Volc DeepSeek-R1 by AntEngine",
            link="https://yuque.antfin.com/ntzgfe/kg7h1z/cx0cb0m2w3rui5k8#hJFXC",
            function_calling=True,
        ),
        ModelMetadata(
            model="上数/volc-deepseek-v3",
            context_length=64 * 1024,
            max_output_length=64 * 1024,
            description="Volc DeepSeek-V3 by AntEngine",
            link="https://yuque.antfin.com/ntzgfe/kg7h1z/cx0cb0m2w3rui5k8#hJFXC",
            function_calling=True,
        ),
        ModelMetadata(
            model="上数/qwen-plus",
            context_length=64 * 1024,
            max_output_length=64 * 1024,
            description="qwen-plus by AntEngine",
            link="https://yuque.antfin.com/ntzgfe/kg7h1z/cx0cb0m2w3rui5k8#hJFXC",
            function_calling=True,
        ),
        ModelMetadata(
            model="上数/qwen-max",
            context_length=64 * 1024,
            max_output_length=64 * 1024,
            description="qwen-max by AntEngine",
            link="https://yuque.antfin.com/ntzgfe/kg7h1z/cx0cb0m2w3rui5k8#hJFXC",
            function_calling=True,
        ),
        ModelMetadata(
            model="上数/qwq-plus",
            context_length=64 * 1024,
            max_output_length=64 * 1024,
            description="qwq-plus by AntEngine",
            link="https://yuque.antfin.com/ntzgfe/kg7h1z/cx0cb0m2w3rui5k8#hJFXC",
            function_calling=True,
        ),
    ],
)
