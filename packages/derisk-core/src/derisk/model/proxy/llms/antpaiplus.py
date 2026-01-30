#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import os
import time
import uuid
from concurrent.futures import Executor
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Optional, Type, Dict, Any, List

import aiohttp
from aiohttp import ClientSession, TCPConnector, ClientTimeout

from derisk.core import (
    ModelRequestContext,
    ModelRequest,
    MessageConverter,
    ModelOutput,
    ModelMetadata
)
from derisk.core.interface.parameter import LLMDeployModelParameters

from derisk.model.proxy.base import (
    ProxyLLMClient,
    register_proxy_model_adapter,
    AsyncGenerateStreamFunction
)
from derisk.model.utils.parse_utils import parse_chat_message
from derisk.util.i18n_utils import _

# Constants
_DEFAULT_API_BASE = "https://paiplusinference.alipay.com/inference"
_DEFAULT_CONN_POOL_SIZE = 50
_DEFAULT_CONN_TIMEOUT = 600
_DEFAULT_KEEPALIVE_TIMEOUT = 120
_MAX_RETRIES = 2
_BACKOFF_FACTOR = 0.3
_BUFFER_FLUSH_INTERVAL = 0.02
_CONNECTION_HEALTH_CHECK_INTERVAL = 60

logger = logging.getLogger(__name__)


@dataclass
class PaiPlusDeployModelParameters(LLMDeployModelParameters):
    provider: str = "proxy/paiplus"

    api_base: Optional[str] = field(
        default=_DEFAULT_API_BASE,
        metadata={"help": "The base URL of the PaiPlus Inference API."},
    )

    api_key: Optional[str] = field(
        default="${env:PAIPLUS_API_KEY}",
        metadata={"help": "The API key for PaiPlus Inference API.", "tags": "privacy"},
    )

    conn_pool_size: Optional[int] = field(
        default=_DEFAULT_CONN_POOL_SIZE,
        metadata={"help": "Connection pool size for API requests."},
    )

    conn_timeout: Optional[int] = field(
        default=_DEFAULT_CONN_TIMEOUT,
        metadata={"help": "Connection timeout in seconds."},
    )

    keepalive_timeout: Optional[int] = field(
        default=_DEFAULT_KEEPALIVE_TIMEOUT,
        metadata={"help": "Keepalive timeout for idle connections in seconds."},
    )
    model_version: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "The model version."
            )
        },
    )

async def paiplus_generate_stream(model, tokenizer, params, device, content_len=2048):
    logger.debug(f"paiplus_generate_stream: model={model}, content_len={content_len}")
    client: PaiPlusProxyLLMClient = model.proxy_llm_client
    context = ModelRequestContext(stream=True, user_name=params.get("user_name"))

    request = ModelRequest.build_request(
        client.default_model,
        messages=params["messages"],
        temperature=params.get("temperature"),
        context=context,
        max_new_tokens=params.get("max_new_tokens"),
    )
    async for r in client.generate_stream(request):
        yield r


@dataclass
class ConnectionPoolState:
    created_at: datetime
    total_requests: int = 0
    last_used: datetime = field(default_factory=datetime.now)


class PaiPlusProxyLLMClient(ProxyLLMClient):
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        model_version: Optional[str] = None,
        context_length: Optional[int] = 4096,
        executor: Optional[Executor] = None,
        conn_pool_size: int = _DEFAULT_CONN_POOL_SIZE,
        conn_timeout: int = _DEFAULT_CONN_TIMEOUT,
        keepalive_timeout: int = _DEFAULT_KEEPALIVE_TIMEOUT,
    ):
        self.api_base = api_base or os.getenv("PAIPLUS_API_BASE") or _DEFAULT_API_BASE
        self.api_key = api_key or os.getenv("PAIPLUS_API_KEY")
        self.model = model
        self.model_version = model_version or "v1"
        self.conn_pool_size = conn_pool_size
        self.conn_timeout = conn_timeout
        self.keepalive_timeout = keepalive_timeout

        self._connector: Optional[TCPConnector] = None
        self._session: Optional[ClientSession] = None
        self._pool_state: Optional[ConnectionPoolState] = None
        self._closed = False
        self._health_check_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        super().__init__(
            model_names=[model] if model else [],
            context_length=context_length,
            executor=executor,
        )

    @classmethod
    def new_client(
        cls,
        model_params: LLMDeployModelParameters,
        default_executor: Optional[Executor] = None,
    ) -> "PaiPlusProxyLLMClient":
        return cls(
            model=model_params.real_provider_model_name,
            api_base=model_params.api_base,
            api_key=model_params.api_key,
            model_version=model_params.model_version,
            context_length=model_params.context_length,
            executor=default_executor,
            conn_pool_size=model_params.conn_pool_size,
            conn_timeout=model_params.conn_timeout,
            keepalive_timeout=model_params.keepalive_timeout,
        )

    async def _ensure_session(self) -> ClientSession:
        """Lazy initialize and return session."""
        async with self._lock:
            if self._closed:
                raise RuntimeError("Client is closed")

            if self._session is None or self._session.closed:
                logger.debug("Initializing new PaiPlus session...")
                self._connector = TCPConnector(
                    limit=self.conn_pool_size,
                    keepalive_timeout=self.keepalive_timeout,
                    enable_cleanup_closed=True,
                )
                self._session = ClientSession(
                    connector=self._connector,
                    timeout=ClientTimeout(total=self.conn_timeout),
                    trust_env=True,
                )
                self._pool_state = ConnectionPoolState(created_at=datetime.now())

                if self._health_check_task is None or self._health_check_task.done():
                    self._health_check_task = asyncio.create_task(self._connection_health_check())

                logger.info(
                    f"PaiPlus session initialized | Pool={self.conn_pool_size}, "
                    f"Keepalive={self.keepalive_timeout}s, Timeout={self.conn_timeout}s"
                )

            if self._pool_state:
                self._pool_state.last_used = datetime.now()
                self._pool_state.total_requests += 1
            return self._session

    async def _connection_health_check(self):
        """Periodically recycle idle connection pool."""
        try:
            while not self._closed:
                await asyncio.sleep(_CONNECTION_HEALTH_CHECK_INTERVAL)
                async with self._lock:
                    if self._closed:
                        return
                    if self._pool_state:
                        idle_sec = (datetime.now() - self._pool_state.last_used).total_seconds()
                        if idle_sec > 300:  # 5 minutes
                            logger.info(f"Recycling idle connection pool (idle {idle_sec:.1f}s)")
                            await self._recycle_pool()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Health check error: {e}")

    async def _recycle_pool(self):
        if self._session:
            await self._session.close()
        if self._connector:
            await self._connector.close()
        self._session = None
        self._connector = None
        self._pool_state = None

    async def close(self):
        async with self._lock:
            if self._closed:
                return
            self._closed = True

            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass

            await self._recycle_pool()

            lifetime = (
                datetime.now() - self._pool_state.created_at
            ).total_seconds() if self._pool_state else 0
            total_reqs = self._pool_state.total_requests if self._pool_state else 0
            logger.info(f"PaiPlus client closed | Lifetime={lifetime:.2f}s, Requests={total_reqs}")

    @property
    def default_model(self) -> str:
        return self.model or "default_model"

    @classmethod
    def param_class(cls) -> Type[PaiPlusDeployModelParameters]:
        return PaiPlusDeployModelParameters

    @classmethod
    def generate_stream_function(cls) -> Optional[AsyncGenerateStreamFunction]:
        return paiplus_generate_stream

    def _get_full_url(self, model_name: str, version: str = "v1") -> str:
        return f"{self.api_base.rstrip('/')}/{model_name}/{version}"

    def _convert_to_paiplus_payload(self, request: ModelRequest) -> Dict[str, Any]:
        """Convert ModelRequest to PaiPlus API payload format."""
        # Extract system and user messages
        messages = request.to_common_messages()
        last_usr_message = ""
        system_messages = []
        for message in messages:
            if message["role"] == "user":
                if isinstance(message["content"], list):
                    last_usr_message = message["content"][0]['text']
                elif isinstance(message["content"], dict):
                    last_usr_message = message["content"]['text']
                else:
                    last_usr_message = message["content"]
            elif message["role"] == "system":
                system_messages.append(message["content"])
        system_message_str = " ".join(system_messages)
        query = (
            f"{system_message_str} {last_usr_message}\n"
        )

        return {"query": query, "sync": True}

    async def _paiplus_stream_chat(
        self,
        request: ModelRequest,
        model_name: str,
        model_version: Optional[str] ="v1",
    ) -> AsyncIterator[ModelOutput]:
        trace_id = (request.context.trace_id if request.context else None) or uuid.uuid4().hex
        # use_key = (request.context.extra.get(
        #     "api_key") if request.context and request.context.extra else None) or self.api_key
        #
        # if not use_key:
        #     yield ModelOutput.build(text="Missing API key for PaiPlus", error_code=401)
        #     return

        headers = {
            "Content-Type": "application/json",
            'MPS-app-name': 'test',
            "MPS-http-version": "1.0",
            "MPS-trace-id": trace_id,
        }

        # Build PaiPlus specific payload
        payload_data = self._convert_to_paiplus_payload(request)

        payload = {
            "features": {},
            "tensorFeatures": {
                "data": {
                    "shapes": [1],
                    "stringValues": [json.dumps(payload_data, ensure_ascii=False)]
                }
            }
        }

        logger.debug(f"Request START | Trace: {trace_id} | Model: {model_name} | URL: {self._get_full_url(model_name, model_version)}")

        retry_count = 0

        while retry_count <= _MAX_RETRIES:
            try:
                session = await self._ensure_session()

                logger.info(f"Request URL: {self._get_full_url(model_name, model_version)}")
                logger.info(f"Request headers: {headers}")
                logger.info(f"Request payload (abbreviated): {json.dumps(payload, ensure_ascii=False)[:1000]}")

                async with session.post(
                    self._get_full_url(model_name, model_version),
                    headers=headers,
                    json=payload,
                    ssl=False,
                    timeout=ClientTimeout(total=self.conn_timeout)
                ) as resp:

                    response_text = await resp.text()  # ←←← 关键：一次性读取全部响应

                    if resp.status == 200:
                        try:
                            outer_json = json.loads(response_text)
                        except json.JSONDecodeError as e:
                            yield ModelOutput.build(text=f"Invalid JSON response: {e}", error_code=500)
                            return

                        # 检查 success 和 resultMap
                        if not outer_json.get("success", True):
                            error_msg = f"Backend error: {outer_json.get('resultCode')} - {outer_json.get('errorMessage')}"
                            yield ModelOutput.build(text=error_msg, error_code=500)
                            return

                        result_map = outer_json.get("resultMap")
                        if not result_map or "result" not in result_map:
                            yield ModelOutput.build(text="Missing 'result' in response", error_code=500)
                            return

                        inner_result_str = result_map["result"]
                        try:
                            inner_json = json.loads(inner_result_str)
                        except json.JSONDecodeError as e:
                            yield ModelOutput.build(
                                text=f"Failed to parse inner result JSON: {e} | Raw: {inner_result_str[:200]}",
                                error_code=500)
                            return

                        final_text = inner_json.get("text", "")
                        thinking = inner_json.get("reasoning_content", "")  # 如果有 reasoning 字段

                        yield ModelOutput(
                            text=final_text,
                            thinking=thinking,
                            error_code=0
                        )
                        return

                    else:
                        error_text = response_text
                        if 500 <= resp.status < 600 and retry_count < _MAX_RETRIES:
                            retry_count += 1
                            backoff = _BACKOFF_FACTOR * (2 ** retry_count)
                            logger.warning(
                                f"[Trace:{trace_id}] Retry {retry_count}/{_MAX_RETRIES} after {backoff:.2f}s for status {resp.status}")
                            await asyncio.sleep(backoff)
                            continue
                        else:
                            yield ModelOutput.build(
                                text=f"HTTP {resp.status}: {error_text}",
                                error_code=resp.status,
                            )
                            return

            except (aiohttp.ClientPayloadError, asyncio.TimeoutError, aiohttp.ServerDisconnectedError) as e:
                retry_count += 1
                if retry_count > _MAX_RETRIES:
                    error_msg = f"Max retries exceeded: {str(e)}"
                    logger.error(f"[Trace:{trace_id}] {error_msg}")
                    yield ModelOutput.build(text=error_msg, error_code=500)
                    return
                backoff = _BACKOFF_FACTOR * (2 ** retry_count)
                logger.warning(
                    f"[Trace:{trace_id}] Network error, retry {retry_count}/{_MAX_RETRIES} after {backoff:.2f}s: {e}")
                await asyncio.sleep(backoff)

            except Exception as e:
                logger.exception(f"[Trace:{trace_id}] Unexpected error during request: {e}")
                yield ModelOutput.build(text=f"Request error: {str(e)}", error_code=500)
                return

    async def generate_stream(
        self,
        request: ModelRequest,
        message_converter: Optional[MessageConverter] = None,
    ) -> AsyncIterator[ModelOutput]:
        request = self.local_covert_message(request, message_converter)
        model_name = request.model or self.default_model
        logger.debug(f"Sending request to PaiPlus, model: {model_name}")
        try:
            async for output in self._paiplus_stream_chat(request, model_name, model_version=self.model_version):
                yield output
        except Exception as e:
            logger.exception(f"Top-level error in generate_stream: {e}")
            yield ModelOutput.build(text=f"Critical error: {str(e)}", error_code=500)


# Register the adapter
register_proxy_model_adapter(
    PaiPlusProxyLLMClient,
    supported_models=[
        ModelMetadata(
            model=[
                "odc_odps_sql_fix",
                "ODPS_SQL_GEN",
                "ODC_ODPS_SQL_GEN",
            ],
            context_length=4096,
            max_output_length=4096,
            description="PaiPlus supported model",
            link="https://paiplusinference.alipay.com",
            function_calling=False,
        ),
    ],
)
