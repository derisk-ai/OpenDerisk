import asyncio
import logging
import os
import json
import uuid
from concurrent.futures import Executor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, Optional, Type, Union

import aiohttp

from derisk.util.error_types import LLMChatError
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
from derisk.util.limited_queue import LimitedQueue
from .chatgpt import OpenAICompatibleDeployModelParameters

_DEFAULT_MODEL = "modelops/QwQ-32B"
_DEFAULT_API_BASE = "https://codebot.alipay.com/v1/chat/completions"

logger = logging.getLogger(__name__)


@auto_register_resource(
    label=_("ModelOps Proxy LLM"),
    category=ResourceCategory.LLM_CLIENT,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("ModelOps proxy LLM configuration."),
    documentation_url="https://yuque.antfin.com/stw5mf/kg7h1z/bg6hekmdev2ppenm",
    show_in_ui=False,
)
@dataclass
class ModelOpsDeployModelParameters(OpenAICompatibleDeployModelParameters):
    """Deploy model parameters for ModelOps."""

    provider: str = "proxy/modelops"

    api_base: Optional[str] = field(
        default=_DEFAULT_API_BASE,
        metadata={
            "help": _("The base url of the ModelOps API."),
        },
    )

    api_key: Optional[str] = field(
        default="${env:MODELOPS_API_KEY}",
        metadata={
            "help": _("The API key of the ModelOps API."),
            "tags": "privacy",
        },
    )


async def modelops_generate_stream(
    model: ProxyModel, tokenizer, params, device, content_len=2048
):
    client: ModelOpsProxyClient = model.proxy_llm_client
    request = parse_model_request(params, client.default_model, stream=True)
    async for r in client.sync_generate_stream(request):
        yield r


class ModelOpsProxyClient(ProxyLLMClient):
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = _DEFAULT_MODEL,
        context_length: Optional[int] = 65536,
        executor: Optional[Executor] = None,
    ):
        self.api_base = api_base or os.getenv("MODELOPS_API_BASE") or _DEFAULT_API_BASE
        self.api_key = api_key or os.getenv("MODELOPS_API_KEY")
        self.model = model
        super().__init__(
            model_names=[model], context_length=context_length, executor=executor
        )

    @classmethod
    def new_client(
        cls,
        model_params: LLMDeployModelParameters,
        default_executor: Executor | None = None,
    ) -> "ModelOpsProxyClient":
        return cls(
            model=model_params.real_provider_model_name,
            api_key=model_params.api_key,
            api_base=model_params.api_base,
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
    def param_class(cls) -> Type[ModelOpsDeployModelParameters]:
        """Get the deploy model parameters class."""
        return ModelOpsDeployModelParameters

    @classmethod
    def generate_stream_function(
        cls,
    ) -> Optional[Union[GenerateStreamFunction, AsyncGenerateStreamFunction]]:
        """Get the generate stream function."""
        return modelops_generate_stream

    async def _modelops_stream_chat_v2(
        self,
        url,
        request: ModelRequest,
        model_name: str,
        model_version: Optional[str] = None,
    ):
        logger.info(f"_modelops_stream_chat:{url}")

        try:
            trace_id = (
                request.context.trace_id
                if request and request.context and request.context.trace_id
                else uuid.uuid4().hex
            )
            payload = {
                "model": model_name,
                "messages": request.to_common_messages(),
                "stream": True,
                "temperature": request.temperature,
                "stop": request.stop,
                "max_tokens": 16 * 1024,  # request.max_new_tokens
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
                "SOFA-RpcId": "0.1",
                "SOFA-TraceId": trace_id,
            }

            reasoning_content = ""
            text = ""
            logger.info(
                f"Send request to {url} with real model {model_name}, model trace {trace_id}"
            )
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json=payload, ssl=False
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        yield ModelOutput.build(
                            text=f"Server Error: {response.status},{error_text}",
                            error_code=1,
                        )
                        return

                    last_line = None
                    last_chunks = LimitedQueue(5)
                    try:
                        async for line in response.content:
                            try:
                                line_str = line.decode("utf-8") if line else ""
                                last_chunks.put(
                                    {"time": datetime.now(), "line": line_str}
                                )
                                if not line:
                                    continue
                                # 这里是在异步读取每一行，这是非阻塞协程的实现
                                last_line = line

                                if line_str.startswith("data:"):
                                    json_str = line_str[len("data:") :]
                                    try:
                                        data = json.loads(json_str)
                                        if data == "DONE":
                                            break
                                        choices = data.get("choices", [])
                                        if choices and isinstance(choices, list):
                                            delta = choices[0].get("delta", {})
                                            reasoning_content += delta.get(
                                                "reasoning_content", ""
                                            )
                                            text += delta.get("content", "")

                                        else:
                                            raise ValueError("Error line content")
                                        yield ModelOutput.build(
                                            text=text,
                                            thinking=reasoning_content,
                                            error_code=0,
                                        )
                                    except json.JSONDecodeError:
                                        raise ValueError(
                                            "Failed to decode response from ModelOps API."
                                        )

                            except Exception as e:
                                logger.exception(f"Stream read exception！{str(e)}")
                                raise

                        if last_line:
                            logger.info(
                                f"_modelops_stream_chat_v2 last chunk:{last_line}"
                            )
                    except aiohttp.ClientPayloadError as e:
                        logger.warning(f"Stream closed prematurely: {e}")
                        yield ModelOutput.build(text="Stream interrupted", error_code=1)
                    except asyncio.CancelledError:
                        logger.info("Client cancelled the stream")
                        raise
                    except Exception as e:
                        logger.error(
                            "Unexpected error during stream reading", exc_info=e
                        )
                        yield ModelOutput.build(
                            text=f"LLM Response Error: {e}", error_code=1
                        )
                    finally:
                        logger.info(f"[{trace_id}]last_chunks: {last_chunks.get()}")
                        if last_line:
                            logger.info(f"Last chunk: {last_line}")

        except Exception as e:
            logger.warning("LLMServer Generate Error!", e)
            yield ModelOutput(
                text=f"**LLMServer Generate Error, Please CheckErrorInfo.**: {e}",
                error_code=1,
            )

    async def sync_generate_stream(
        self,
        request: ModelRequest,
        message_converter: Optional[MessageConverter] = None,
    ) -> Iterator[ModelOutput]:
        request = self.local_covert_message(request, message_converter)
        model = request.model or self.model

        try:
            logger.debug(
                f"Send request to modelops ai, model: {model}, request: {request}"
            )
            try:
                import requests
            except ImportError as e:
                raise ValueError(
                    "Could not import requests. Please install requests by running `pip install requests`."
                ) from e

            request_model = self.model
            if request_model.startswith("modelops"):
                request_model = request_model.split("/")[1]

            url = self.api_base
            logger.info("API BASE:{self.api_base}, request_model:{request_model}")

            async for output in self._modelops_stream_chat_v2(
                url, request, request_model
            ):
                yield output

        except Exception as e:
            logger.error(f"Failed to send request to modelops ai, error: {e}")
            raise e


register_proxy_model_adapter(
    ModelOpsProxyClient,
    supported_models=[
        ModelMetadata(
            model=[
                "modelops/QwQ-32B",
                "modelops/DeepSeek-R1",
                "modelops/DeepSeek-R1-Distill-Qwen-32B",
            ],
            context_length=64 * 1024,
            max_output_length=8 * 1024,
            description="ModelOps Supported Models",
            link="https://yuque.antfin.com/stw5mf/kg7h1z/bg6hekmdev2ppenm",
            function_calling=False,
        )
    ],
)
