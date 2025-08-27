import json
import re
import time
import uuid
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.responses import JSONResponse, StreamingResponse

from derisk._private.pydantic import model_to_dict, model_to_json
from derisk.component import SystemApp, logger
from derisk.core.awel import CommonLLMHttpRequestBody
from derisk.core.schema.api import (
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatCompletionResponseStreamChoice,
    ChatCompletionStreamResponse,
    ChatMessage,
    DeltaMessage,
    ErrorResponse,
    UsageInfo,
)
from derisk.model.cluster.apiserver.api import APISettings
from derisk.util.executor_utils import blocking_func_to_async
from derisk.util.tracer import SpanType, root_tracer
from derisk_app.openapi.api_v1.api_v1 import (
    __new_conversation,
    get_chat_flow,
    get_executor,
    stream_generator,
)
from derisk_client.schema import ChatCompletionRequestBody, ChatMode
from derisk_serve.agent.agents.controller import multi_agents
from derisk_serve.flow.api.endpoints import get_service

router = APIRouter()
api_settings = APISettings()
get_bearer_token = HTTPBearer(auto_error=False)


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    service=Depends(get_service),
) -> Optional[str]:
    """Check the api key
    Args:
        auth (Optional[HTTPAuthorizationCredentials]): The bearer token.
        service (Service): The flow service.
    """
    if service.config.api_keys:
        api_keys = [key.strip() for key in service.config.api_keys.split(",")]
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "message": "",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_api_key",
                    }
                },
            )
        return token
    else:
        return None


@router.post("/v2/chat/completions", dependencies=[Depends(check_api_key)])
async def chat_completions(
    request: ChatCompletionRequestBody = Body(),
    service=Depends(get_service),
):
    """Chat V2 completions
    Args:
        request (ChatCompletionRequestBody): The chat request.
        flow_service (FlowService): The flow service.
    Raises:
        HTTPException: If the request is invalid.
    """
    logger.info(
        f"chat_completions:{request.chat_mode},{request.chat_param},{request.model}"
    )
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Transfer-Encoding": "chunked",
    }
    # check chat request
    check_chat_request(request)
    if request.conv_uid is None:
        request.conv_uid = str(uuid.uuid4())
    request.trace_id = request.trace_id or uuid.uuid4().hex
    request.rpc_id = request.rpc_id or "0.1"
    if request.chat_mode == ChatMode.CHAT_APP.value:
        if request.stream is False:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "message": "chat app now not support no stream",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_request_error",
                    }
                },
            )
        return StreamingResponse(
            chat_app_stream_wrapper(
                request=request,
            ),
            headers=headers,
            media_type="text/event-stream",
        )
    elif request.chat_mode == ChatMode.CHAT_AWEL_FLOW.value:
        if not request.stream:
            return await chat_flow_wrapper(request)
        else:
            return StreamingResponse(
                chat_flow_stream_wrapper(request),
                headers=headers,
                media_type="text/event-stream",
            )
    else:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "chat mode now only support chat_normal, chat_app, "
                    "chat_flow, chat_knowledge, chat_data",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_chat_mode",
                }
            },
        )
async def chat_app_stream_wrapper(request: ChatCompletionRequestBody = None):
    """chat app stream
    Args:
        request (OpenAPIChatCompletionRequest): request
        token (APIToken): token
    """
    async for output, agent_conv_id in multi_agents.app_chat(
        conv_uid=request.conv_uid,
        gpts_name=request.chat_param,
        user_query=request.messages,
        user_code=request.user_name,
        sys_code=request.sys_code,
        trace_id=request.trace_id,
        rpc_id=request.rpc_id,
    ):
        match = re.search(r"data:\s*({.*})", output)
        if match:
            json_str = match.group(1)
            vis = json.loads(json_str)
            vis_content = vis.get("vis", None)
            if vis_content != "[DONE]":
                choice_data = ChatCompletionResponseStreamChoice(
                    index=0,
                    delta=DeltaMessage(role="assistant", content=vis.get("vis", None)),
                )
                chunk = ChatCompletionStreamResponse(
                    id=request.conv_uid,
                    choices=[choice_data],
                    model=request.model,
                    created=int(time.time()),
                )
                json_content = model_to_json(
                    chunk, exclude_unset=True, ensure_ascii=False
                )
                content = f"data: {json_content}\n\n"
                yield content
    yield "data: [DONE]\n\n"


async def chat_flow_wrapper(request: ChatCompletionRequestBody):
    flow_service = get_chat_flow()
    flow_req = CommonLLMHttpRequestBody(**model_to_dict(request))
    flow_uid = request.chat_param
    output = await flow_service.safe_chat_flow(flow_uid, flow_req)
    if not output.success:
        return JSONResponse(
            model_to_dict(ErrorResponse(message=output.text, code=output.error_code)),
            status_code=400,
        )
    else:
        choice_data = ChatCompletionResponseChoice(
            index=0,
            message=ChatMessage(role="assistant", content=output.text),
        )
        if output.usage:
            usage = UsageInfo(**output.usage)
        else:
            usage = UsageInfo()
        return ChatCompletionResponse(
            id=request.conv_uid, choices=[choice_data], model=request.model, usage=usage
        )


async def chat_flow_stream_wrapper(
    request: ChatCompletionRequestBody,
) -> AsyncIterator[str]:
    """chat app stream
    Args:
        request (OpenAPIChatCompletionRequest): request
    """
    flow_service = get_chat_flow()
    flow_req = CommonLLMHttpRequestBody(**model_to_dict(request))
    flow_uid = request.chat_param

    async for output in flow_service.chat_stream_openai(flow_uid, flow_req):
        yield output


def check_chat_request(request: ChatCompletionRequestBody = Body()):
    """
    Check the chat request
    Args:
        request (ChatCompletionRequestBody): The chat request.
    Raises:
        HTTPException: If the request is invalid.
    """
    if request.chat_param is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "chart param is None",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_chat_param",
                }
            },
        )
    if request.model is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "model is None",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_model",
                }
            },
        )
    if request.messages is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "messages is None",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_messages",
                }
            },
        )
