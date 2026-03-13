import asyncio
import datetime
import json
import logging
import os
import time
import uuid
from concurrent.futures import Executor
from typing import List, Optional, cast

import pandas as pd
from fastapi import APIRouter, Body, Depends, File, Query, UploadFile, BackgroundTasks
from fastapi.responses import StreamingResponse

from derisk._private.config import Config
from derisk.component import ComponentType
from derisk.configs import TAG_KEY_KNOWLEDGE_CHAT_DOMAIN_TYPE
from derisk.core import ModelOutput, HumanMessage
from derisk.core.awel import BaseOperator, CommonLLMHttpRequestBody
from derisk.core.awel.dag.dag_manager import DAGManager
from derisk.core.awel.util.chat_util import safe_chat_stream_with_dag_task
from derisk.core.interface.file import FileStorageClient
from derisk.core.schema.api import (
    ChatCompletionResponseChoice,
    ChatMessage,
    UsageInfo,
    ChatCompletionResponse,
)
from derisk.model.base import FlatSupportedModel
from derisk.model.cluster import (
    BaseModelController,
    WorkerManager,
    WorkerManagerFactory,
)
from derisk.util.data_util import first
from derisk.util.executor_utils import (
    DefaultExecutorFactory,
    ExecutorFactory,
)
from derisk.util.file_client import FileClient
from derisk.util.tracer import SpanType, root_tracer
from derisk_app.knowledge.request.request import KnowledgeSpaceRequest
from derisk_app.knowledge.service import KnowledgeService
from derisk_app.openapi.api_view_model import (
    ChatCompletionResponseStreamChoice,
    ChatCompletionStreamResponse,
    ChatSceneVo,
    ConversationVo,
    DeltaMessage,
    MessageVo,
    Result,
    WorkMode,
)
from derisk_serve.agent.agents.controller import multi_agents
from derisk_serve.agent.db.gpts_app import UserRecentAppsDao
from derisk_serve.agent.team.base import TeamMode
from derisk_serve.core import blocking_func_to_async
from derisk_serve.datasource.manages.db_conn_info import DBConfig, DbTypeInfo
from derisk_serve.flow.service.service import Service as FlowService
from derisk_serve.utils.auth import UserRequest, get_user_from_headers

router = APIRouter()
CFG = Config()
logger = logging.getLogger(__name__)
knowledge_service = KnowledgeService()

model_semaphore = None
global_counter = 0

user_recent_app_dao = UserRecentAppsDao()


def __get_conv_user_message(conversations: dict):
    messages = conversations["messages"]
    for item in messages:
        if item["type"] == "human":
            return item["data"]["content"]
    return ""


def __new_conversation(team_mode, user_name: str, sys_code: str) -> ConversationVo:
    unique_id = uuid.uuid1()
    return ConversationVo(
        conv_uid=str(unique_id),
        team_mode=team_mode,
        user_name=user_name,
        sys_code=sys_code,
    )


def get_db_list(user_id: str = None):
    dbs = CFG.local_db_manager.get_db_list(user_id=user_id)
    db_params = []
    for item in dbs:
        params: dict = {}
        params.update({"param": item["db_name"]})
        params.update({"type": item["db_type"]})
        db_params.append(params)
    return db_params


def plugins_select_info():
    plugins_infos: dict = {}
    for plugin in CFG.plugins:
        plugins_infos.update(
            {f"【{plugin._name}】=>{plugin._description}": plugin._name}
        )
    return plugins_infos


def get_db_list_info(user_id: str = None):
    dbs = CFG.local_db_manager.get_db_list(user_id=user_id)
    params: dict = {}
    for item in dbs:
        comment = item["comment"]
        if comment is not None and len(comment) > 0:
            params.update({item["db_name"]: comment})
    return params


def knowledge_list_info():
    """return knowledge space list"""
    params: dict = {}
    request = KnowledgeSpaceRequest()
    spaces = knowledge_service.get_knowledge_space(request)
    for space in spaces:
        params.update({space.name: space.desc})
    return params


def knowledge_list(user_id: str = None):
    """return knowledge space list"""
    request = KnowledgeSpaceRequest(user_id=user_id)
    spaces = knowledge_service.get_knowledge_space(request)
    space_list = []
    for space in spaces:
        params: dict = {}
        params.update({"param": space.name})
        params.update({"type": "space"})
        params.update({"space_id": space.id})
        space_list.append(params)
    return space_list


def get_model_controller() -> BaseModelController:
    controller = CFG.SYSTEM_APP.get_component(
        ComponentType.MODEL_CONTROLLER, BaseModelController
    )
    return controller


def get_worker_manager() -> WorkerManager:
    worker_manager = CFG.SYSTEM_APP.get_component(
        ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
    ).create()
    return worker_manager


def get_fs() -> FileStorageClient:
    return FileStorageClient.get_instance(CFG.SYSTEM_APP)


def get_dag_manager() -> DAGManager:
    """Get the global default DAGManager"""
    return DAGManager.get_instance(CFG.SYSTEM_APP)


def get_chat_flow() -> FlowService:
    """Get Chat Flow Service."""
    return FlowService.get_instance(CFG.SYSTEM_APP)


def get_executor() -> Executor:
    """Get the global default executor"""
    return CFG.SYSTEM_APP.get_component(
        ComponentType.EXECUTOR_DEFAULT,
        ExecutorFactory,
        or_register_component=DefaultExecutorFactory,
    ).create()


@router.post("/v1/resource/params/list", response_model=Result[List[dict]])
async def resource_params_list(
    resource_type: str,
    user_token: UserRequest = Depends(get_user_from_headers),
):
    if resource_type == "database":
        result = get_db_list()
    elif resource_type == "knowledge":
        result = knowledge_list()
    elif resource_type == "tool":
        result = plugins_select_info()
    else:
        return Result.succ()
    return Result.succ(result)


@router.post("/v1/resource/file/upload")
async def file_upload(
    chat_mode: str,
    conv_uid: str,
    temperature: Optional[float] = None,
    max_new_tokens: Optional[int] = None,
    sys_code: Optional[str] = None,
    model_name: Optional[str] = None,
    doc_files: List[UploadFile] = File(...),
    user_token: UserRequest = Depends(get_user_from_headers),
    fs: FileStorageClient = Depends(get_fs),
):
    logger.info(
        f"file_upload:{conv_uid}, files:{[file.filename for file in doc_files]}"
    )

    bucket = "derisk_app_file"
    file_params = []

    for doc_file in doc_files:
        file_name = doc_file.filename
        custom_metadata = {
            "user_name": user_token.user_id,
            "sys_code": sys_code,
            "conv_uid": conv_uid,
        }

        file_uri = await blocking_func_to_async(
            CFG.SYSTEM_APP,
            fs.save_file,
            bucket,
            file_name,
            doc_file.file,
            custom_metadata=custom_metadata,
        )

        _, file_extension = os.path.splitext(file_name)
        file_param = {
            "is_oss": True,
            "file_path": file_uri,
            "file_name": file_name,
            "file_learning": False,
            "bucket": bucket,
        }
        file_params.append(file_param)

    # If only one file was uploaded, return the single file_param directly
    # Otherwise return the array of file_params
    result = file_params[0] if len(file_params) == 1 else file_params
    return Result.succ(result)


@router.post("/v1/resource/file/delete")
async def file_delete(
    conv_uid: str,
    file_key: str,
    user_name: Optional[str] = None,
    sys_code: Optional[str] = None,
    user_token: UserRequest = Depends(get_user_from_headers),
):
    logger.info(f"file_delete:{conv_uid},{file_key}")
    oss_file_client = FileClient()

    return Result.succ(
        await oss_file_client.delete_file(conv_uid=conv_uid, file_key=file_key)
    )


@router.post("/v1/resource/file/read")
async def file_read(
    conv_uid: str,
    file_key: str,
    user_name: Optional[str] = None,
    sys_code: Optional[str] = None,
    user_token: UserRequest = Depends(get_user_from_headers),
):
    logger.info(f"file_read:{conv_uid},{file_key}")
    file_client = FileClient()
    res = await file_client.read_file(conv_uid=conv_uid, file_key=file_key)
    df = pd.read_excel(res, index_col=False)
    return Result.succ(df.to_json(orient="records", date_format="iso", date_unit="s"))


async def get_hist_messages(conv_uid: str, user_name: str = None):
    from derisk_serve.conversation.service.service import Service as ConversationService

    instance: ConversationService = ConversationService.get_instance(CFG.SYSTEM_APP)
    return await instance.get_history_messages(
        {"conv_uid": conv_uid, "user_name": user_name}
    )


@router.post("/v1/chat/stop")
async def chat_stop(
    conv_session_id: str,
    user_token: UserRequest = Depends(get_user_from_headers),
):
    logger.info(f"chat_stop:{conv_session_id}")
    try:
        await multi_agents.stop_chat(
            conv_session_id, user_token.user_id if user_token else None
        )
    except Exception as e:
        logger.exception("停止对话异常！")
        return Result.failed(msg=f"停止对话失败！{str(e)}")


@router.get("/v1/chat/query")
async def chat_query(
    conv_id: str,
    vis_render: Optional[str] = Query(default=None, description="可视化协议名称"),
    user_token: UserRequest = Depends(get_user_from_headers),
):
    """查询会话状态和最终结论

    Args:
        conv_id: Agent会话ID (agent_conv_id)
        vis_render: 可视化协议名称
    """
    logger.info(f"chat_query: {conv_id}")
    try:
        result = await multi_agents.query_chat(conv_id=conv_id, vis_render=vis_render)
        if result is None:
            return Result.failed(code="E0103", msg=f"会话 {conv_id} 不存在")

        vis_final, user_answer, current_vis_render, is_final, state = result
        return Result.succ(
            {
                "conv_id": conv_id,
                "state": state,
                "is_final": is_final,
                "vis_final": vis_final,
                "user_answer": user_answer,
                "vis_render": current_vis_render,
            }
        )
    except Exception as e:
        logger.exception("查询会话异常!")
        return Result.failed(code="E0104", msg=f"查询会话失败: {str(e)}")


@router.post("/v1/chat/completions")
async def chat_completions(
    background_tasks: BackgroundTasks,
    dialogue: ConversationVo = Body(),
    user_token: UserRequest = Depends(get_user_from_headers),
):
    logger.info(
        f"chat_completions:{dialogue.team_mode},{dialogue.select_param},"
        f"{dialogue.model_name}, work_mode={dialogue.work_mode}, timestamp={int(time.time() * 1000)}"
    )
    if not dialogue.conv_uid:
        dialogue.conv_uid = uuid.uuid1().hex

    # Adapt OpenAI messages format to user_input
    if not dialogue.user_input and dialogue.messages:
        try:
            last_message = next(
                (
                    msg
                    for msg in reversed(dialogue.messages)
                    if msg.get("role") == "user"
                ),
                None,
            )
            if last_message:
                dialogue.user_input = last_message.get("content", "")
                logger.info(
                    f"Extracted user_input from messages: {dialogue.user_input}"
                )
        except Exception as e:
            logger.warning(f"Failed to extract user_input from messages: {e}")

    dialogue.user_name = user_token.user_id if user_token else dialogue.user_name
    dialogue.ext_info.update(
        {
            "trace_id": first(
                root_tracer.get_context_trace_id(), default=uuid.uuid4().hex
            )
        }
    )
    dialogue.ext_info.update({"rpc_id": "0.1"})

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Transfer-Encoding": "chunked",
    }
    try:
        dialogue.ext_info.update({"model_name": dialogue.model_name})
        dialogue.ext_info.update({"incremental": dialogue.incremental})
        dialogue.ext_info.update({"temperature": dialogue.temperature})
        dialogue.ext_info.update({"max_new_tokens": dialogue.max_new_tokens})

        in_message = HumanMessage.parse_chat_completion_message(
            dialogue.user_input, ignore_unknown_media=True
        )

        # 处理文件输入：提取文件引用并增强消息
        sandbox_file_refs = []
        if in_message.has_media:
            try:
                from derisk_serve.agent.file_io import (
                    process_chat_input_files,
                    build_enhanced_query_with_files,
                    SandboxFileRef,
                )

                user_inputs = []
                if isinstance(in_message.content, list):
                    for media in in_message.content:
                        if hasattr(media, "type") and hasattr(media, "object"):
                            if media.type == "image" and media.object.format.startswith(
                                "url"
                            ):
                                user_inputs.append(
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": str(media.object.data)},
                                    }
                                )
                            elif (
                                media.type == "file"
                                and media.object.format.startswith("url")
                            ):
                                user_inputs.append(
                                    {
                                        "type": "file_url",
                                        "file_url": {"url": str(media.object.data)},
                                    }
                                )

                if user_inputs:
                    result = await process_chat_input_files(
                        user_inputs=user_inputs,
                        sandbox=None,
                        conv_id=dialogue.conv_uid,
                    )
                    sandbox_file_refs = result.sandbox_file_refs
                    logger.info(
                        f"[v1/chat] Processed {len(sandbox_file_refs)} files from user input"
                    )

                    if sandbox_file_refs and not result.multimodal_contents:
                        text_content = (
                            in_message.last_text
                            if hasattr(in_message, "last_text")
                            else str(in_message.content)
                        )
                        enhanced_text = build_enhanced_query_with_files(
                            text_content, sandbox_file_refs
                        )
                        in_message = HumanMessage(content=enhanced_text)
                        logger.info("[v1/chat] Enhanced message with file references")

            except ImportError:
                logger.warning("[v1/chat] file_io module not available")
            except Exception as e:
                logger.warning(f"[v1/chat] Failed to process files: {e}")

        # 将 sandbox_file_refs 传递到 ext_info
        if sandbox_file_refs:
            dialogue.ext_info["sandbox_file_refs"] = [
                ref.to_dict() if hasattr(ref, "to_dict") else ref
                for ref in sandbox_file_refs
            ]

        work_mode = dialogue.work_mode or WorkMode.ASYNC

        if work_mode == WorkMode.QUICK:

            async def chat_wrapper():
                async for chunk, agent_conv_id in multi_agents.quick_app_chat(
                    conv_session_id=dialogue.conv_uid,
                    user_query=in_message,
                    chat_in_params=dialogue.chat_in_params,
                    app_code=dialogue.app_code,
                    user_code=dialogue.user_name,
                    sys_code=dialogue.sys_code,
                    **dialogue.ext_info,
                ):
                    yield chunk

            return StreamingResponse(
                chat_wrapper(),
                headers=headers,
                media_type="text/event-stream",
            )
        elif work_mode == WorkMode.BACKGROUND:

            async def chat_wrapper():
                async for chunk, agent_conv_id in multi_agents.app_chat_v2(
                    conv_uid=dialogue.conv_uid,
                    background_tasks=background_tasks,
                    gpts_name=dialogue.app_code,
                    specify_config_code=dialogue.app_config_code,
                    user_query=in_message,
                    user_code=dialogue.user_name,
                    sys_code=dialogue.sys_code,
                    chat_in_params=dialogue.chat_in_params,
                    **dialogue.ext_info,
                ):
                    yield chunk

            return StreamingResponse(
                chat_wrapper(),
                headers=headers,
                media_type="text/event-stream",
            )
        elif work_mode == WorkMode.ASYNC:
            result = await multi_agents.app_chat_v3(
                conv_uid=dialogue.conv_uid,
                background_tasks=background_tasks,
                gpts_name=dialogue.app_code,
                specify_config_code=dialogue.app_config_code,
                user_query=in_message,
                user_code=dialogue.user_name,
                sys_code=dialogue.sys_code,
                chat_in_params=dialogue.chat_in_params,
                **dialogue.ext_info,
            )
            agent_conv_id = result[1] if result else None
            return Result.succ(data={"conv_id": agent_conv_id})
        else:

            async def chat_wrapper():
                async for chunk, agent_conv_id in multi_agents.app_chat(
                    conv_uid=dialogue.conv_uid,
                    gpts_name=dialogue.app_code,
                    specify_config_code=dialogue.app_config_code,
                    user_query=in_message,
                    user_code=dialogue.user_name,
                    sys_code=dialogue.sys_code,
                    chat_in_params=dialogue.chat_in_params,
                    **dialogue.ext_info,
                ):
                    yield chunk

            return StreamingResponse(
                chat_wrapper(),
                headers=headers,
                media_type="text/event-stream",
            )

    except Exception as e:
        logger.exception(f"Chat Exception!{dialogue}", e)

        async def error_text(err_msg):
            yield f"data:{err_msg}\n\n"

        return StreamingResponse(
            error_text(str(e)),
            headers=headers,
            media_type="text/plain",
        )
    finally:
        if dialogue.user_name is not None and dialogue.app_code is not None:
            user_recent_app_dao.upsert(
                user_code=dialogue.user_name,
                sys_code=dialogue.sys_code,
                app_code=dialogue.app_code,
            )


@router.post("/v1/chat/topic/terminate")
async def terminate_topic(
    conv_id: str,
    round_index: int,
    user_token: UserRequest = Depends(get_user_from_headers),
):
    logger.info(f"terminate_topic:{conv_id},{round_index}")
    try:
        from derisk_serve.agent.agents.controller import multi_agents

        return Result.succ(await multi_agents.topic_terminate(conv_id))
    except Exception as e:
        logger.exception("Topic terminate error!")
        return Result.failed(code="E0102", msg=str(e))


@router.get("/v1/model/types")
async def model_types(controller: BaseModelController = Depends(get_model_controller)):
    logger.info("/controller/model/types")
    try:
        types = set()
        models = await controller.get_all_instances(healthy_only=True)
        for model in models:
            worker_name, worker_type = model.model_name.split("@")
            if worker_type == "llm" and worker_name not in [
                "codegpt_proxyllm",
                "text2sql_proxyllm",
            ]:
                types.add(worker_name)
        return Result.succ(list(types))

    except Exception as e:
        return Result.failed(code="E000X", msg=f"controller model types error {e}")


@router.get("/v1/test")
async def test():
    return "service status is UP"


@router.get(
    "/v1/model/supports",
    deprecated=True,
    description="This endpoint is deprecated. Please use "
    "`/api/v2/serve/model/model-types` instead. It will be removed in v0.8.0.",
)
async def model_supports(worker_manager: WorkerManager = Depends(get_worker_manager)):
    logger.warning(
        "The endpoint `/api/v1/model/supports` is deprecated. Please use "
        "`/api/v2/serve/model/model-types` instead. It will be removed in v0.8.0."
    )
    try:
        models = await worker_manager.supported_models()
        return Result.succ(FlatSupportedModel.from_supports(models))
    except Exception as e:
        return Result.failed(code="E000X", msg=f"Fetch supportd models error {e}")


async def flow_stream_generator(func, incremental: bool, model_name: str):
    stream_id = f"chatcmpl-{str(uuid.uuid1())}"
    previous_response = ""
    async for chunk in func:
        if chunk:
            msg = chunk.replace("\ufffd", "")
            if incremental:
                incremental_output = msg[len(previous_response) :]
                choice_data = ChatCompletionResponseStreamChoice(
                    index=0,
                    delta=DeltaMessage(role="assistant", content=incremental_output),
                )
                chunk = ChatCompletionStreamResponse(
                    id=stream_id, choices=[choice_data], model=model_name
                )
                _content = json.dumps(
                    chunk.dict(exclude_unset=True), ensure_ascii=False
                )
                yield f"data: {_content}\n\n"
            else:
                # TODO generate an openai-compatible streaming responses
                msg = msg.replace("\n", "\\n")
                yield f"data:{msg}\n\n"
            previous_response = msg
    if incremental:
        yield "data: [DONE]\n\n"


async def no_stream_generator(chat):
    with root_tracer.start_span("no_stream_generator"):
        msg = await chat.nostream_call()
        yield f"data: {msg}\n\n"


async def stream_generator(
    chat,
    incremental: bool,
    model_name: str,
    text_output: bool = True,
    openai_format: bool = False,
    conv_uid: str = None,
):
    """Generate streaming responses

    Our goal is to generate an openai-compatible streaming responses.
    Currently, the incremental response is compatible, and the full response will be
    transformed in the future.

    Args:
        chat (BaseChat): Chat instance.
        incremental (bool): Used to control whether the content is returned
            incrementally or in full each time.
        model_name (str): The model name

    Yields:
        _type_: streaming responses
    """
    span = root_tracer.start_span("stream_generator")
    msg = "[LLM_ERROR]: llm server has no output, maybe your prompt template is wrong."

    stream_id = conv_uid or f"chatcmpl-{str(uuid.uuid1())}"
    try:
        if incremental and not openai_format:
            raise ValueError("Incremental response must be openai-compatible format.")
        async for chunk in chat.stream_call(
            text_output=text_output, incremental=incremental
        ):
            if not chunk:
                await asyncio.sleep(0.02)
                continue

            if openai_format:
                # Must be ModelOutput
                output: ModelOutput = cast(ModelOutput, chunk)
                text = None
                think_text = None
                if output.has_text:
                    text = output.text
                if output.has_thinking:
                    think_text = output.thinking_text
                if incremental:
                    choice_data = ChatCompletionResponseStreamChoice(
                        index=0,
                        delta=DeltaMessage(
                            role="assistant", content=text, reasoning_content=think_text
                        ),
                    )
                    chunk = ChatCompletionStreamResponse(
                        id=stream_id, choices=[choice_data], model=model_name
                    )
                    _content = json.dumps(
                        chunk.dict(exclude_unset=True), ensure_ascii=False
                    )
                    yield f"data: {_content}\n\n"
                else:
                    choice_data = ChatCompletionResponseChoice(
                        index=0,
                        message=ChatMessage(
                            role="assistant",
                            content=output.text,
                            reasoning_content=output.thinking_text,
                        ),
                    )
                    if output.usage:
                        usage = UsageInfo(**output.usage)
                    else:
                        usage = UsageInfo()
                    _content = ChatCompletionResponse(
                        id=stream_id,
                        choices=[choice_data],
                        model=model_name,
                        usage=usage,
                    )
                    _content = json.dumps(
                        chunk.dict(exclude_unset=True), ensure_ascii=False
                    )
                    yield f"data: {_content}\n\n"
            else:
                msg = chunk.replace("\ufffd", "")
                msg = msg.replace("\n", "\\n")
                yield f"data:{msg}\n\n"
            await asyncio.sleep(0.02)
        if incremental:
            yield "data: [DONE]\n\n"
        span.end()
    except Exception as e:
        logger.exception("stream_generator error")
        yield f"data: [SERVER_ERROR]{str(e)}\n\n"
        if incremental:
            yield "data: [DONE]\n\n"


def message2Vo(message: dict, order, model_name) -> MessageVo:
    return MessageVo(
        role=message["type"],
        context=message["data"]["content"],
        order=order,
        model_name=model_name,
    )


from .config_api import router as config_router
from .tools_api import router as tools_router

router.include_router(config_router, prefix="/v1", tags=["Config"])
router.include_router(tools_router, prefix="/v1", tags=["Tools"])
