"""
完整API路由实现

扩展API层支持所有新功能:
- 进度追踪
- 检查点管理
- 目标管理
- 执行历史
- 多模态消息支持
- 动态资源选择
- 模型选择
"""

from typing import Dict, Any, List, Optional, Union
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
import logging
import json
import asyncio
import uuid
import time

from ..agent_harness import (
    Checkpoint, CheckpointType, ExecutionSnapshot, ExecutionState,
    AgentHarness, StateStore
)
from ..goal import Goal, GoalStatus, GoalPriority, SuccessCriterion
from ..long_task_executor import LongRunningTaskExecutor, LongTaskConfig, ProgressReport
from ..production_agent import ProductionAgent, AgentBuilder
from ..llm_adapter import LLMConfig

logger = logging.getLogger(__name__)

router = APIRouter()

# ========== 全局实例 ==========

_executor: Optional[LongRunningTaskExecutor] = None
_harness: Optional[AgentHarness] = None


def get_executor() -> LongRunningTaskExecutor:
    """获取执行器"""
    global _executor
    if _executor is None:
        raise HTTPException(status_code=500, detail="Executor not initialized")
    return _executor


def init_executor(api_key: str, model: str = "gpt-4"):
    """初始化执行器"""
    global _executor
    
    agent = AgentBuilder().with_api_key(api_key).with_model(model).build()
    
    config = LongTaskConfig(
        max_steps=1000,
        checkpoint_interval=50,
        storage_backend="file",
        storage_path=".agent_state"
    )
    
    _executor = LongRunningTaskExecutor(agent=agent, config=config)


# ========== 请求/响应模型 ==========

class WorkMode:
    SIMPLE = "simple"
    QUICK = "quick"
    BACKGROUND = "background"
    ASYNC = "async"


class ChatInParamValue(BaseModel):
    param_type: str = Field(
        ...,
        description="The param type of app chat in.",
    )
    sub_type: Optional[str] = Field(
        None,
        description="The sub type of chat in param.",
    )
    param_value: str = Field(
        ...,
        description="The chat in param value"
    )


class CreateSessionRequest(BaseModel):
    user_id: Optional[str] = None
    agent_name: str = "default"
    metadata: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    conv_uid: str = Field(default="", description="conversation uid")
    app_code: Optional[str] = Field(None, description="app code")
    app_config_code: Optional[str] = Field(None, description="app config code")
    user_input: Union[str, Dict[str, Any], List[Any]] = Field(
        default="", description="User input messages, supports multimodal content."
    )
    messages: Optional[List[Dict[str, Any]]] = Field(
        None, description="OpenAI compatible messages list"
    )
    user_name: Optional[str] = Field(None, description="user name")
    team_mode: Optional[str] = Field(default="", description="team mode")
    chat_in_params: Optional[List[ChatInParamValue]] = Field(
        None, description="chat in param values for dynamic resources"
    )
    select_param: Optional[Any] = Field(
        None, description="chat scene select param for dynamic resources"
    )
    model_name: Optional[str] = Field(None, description="llm model name")
    temperature: Optional[float] = Field(default=0.5, description="temperature")
    max_new_tokens: Optional[int] = Field(default=640000, description="max new tokens")
    incremental: bool = Field(default=False, description="incremental output")
    sys_code: Optional[str] = Field(None, description="System code")
    prompt_code: Optional[str] = Field(None, description="prompt code")
    ext_info: Dict[str, Any] = Field(default_factory=dict, description="extra info")
    work_mode: Optional[str] = Field(
        default=WorkMode.SIMPLE, description="Work mode: simple, quick, background, async"
    )
    stream: bool = Field(default=True, description="Whether return stream")
    session_id: Optional[str] = Field(None, description="session id (for v2 compatibility)")


class CreateGoalRequest(BaseModel):
    name: str
    description: str
    priority: str = "medium"
    criteria: Optional[List[Dict[str, Any]]] = None


class CreateCheckpointRequest(BaseModel):
    checkpoint_type: str = "manual"
    message: Optional[str] = None


class SubmitUserInputRequest(BaseModel):
    session_id: str
    content: str
    input_type: str = "text"
    metadata: Optional[Dict[str, Any]] = None


class UserInputResponse(BaseModel):
    success: bool
    message: str
    queue_length: int


# ========== 会话管理 ==========

@router.post("/session")
async def create_session(req: CreateSessionRequest):
    """创建会话"""
    try:
        execution_id = await get_executor().execute(
            task="",
            metadata=req.metadata or {}
        )
        
        return {
            "success": True,
            "session_id": execution_id,
            "agent_name": req.agent_name
        }
    except Exception as e:
        logger.error(f"[API] 创建会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """获取会话信息"""
    snapshot = get_executor().get_snapshot(session_id)
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "success": True,
        "data": snapshot.dict()
    }


@router.delete("/session/{session_id}")
async def close_session(session_id: str):
    """关闭会话"""
    try:
        await get_executor().cancel(session_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 聊天 ==========

@router.post("/chat")
async def chat(
    background_tasks: BackgroundTasks,
    req: ChatRequest,
):
    """
    聊天接口 - 支持多模态、模型选择、动态资源
    
    功能:
    - 多模态消息: 通过 user_input 或 messages 传入图片、音频等内容
    - 模型选择: 通过 model_name 指定模型
    - 动态资源: 通过 select_param 和 chat_in_params 选择资源
    - 工作模式: simple/quick/background/async
    """
    logger.info(
        f"chat:{req.team_mode},{req.select_param},"
        f"{req.model_name}, work_mode={req.work_mode}, timestamp={int(time.time() * 1000)}"
    )
    
    if not req.conv_uid:
        req.conv_uid = uuid.uuid1().hex

    if not req.user_input and req.messages:
        try:
            last_message = next(
                (
                    msg
                    for msg in reversed(req.messages)
                    if msg.get("role") == "user"
                ),
                None,
            )
            if last_message:
                req.user_input = last_message.get("content", "")
                logger.info(f"Extracted user_input from messages: {req.user_input}")
        except Exception as e:
            logger.warning(f"Failed to extract user_input from messages: {e}")

    req.ext_info = req.ext_info or {}
    req.ext_info.update({"trace_id": req.ext_info.get("trace_id") or uuid.uuid4().hex})
    req.ext_info.update({"rpc_id": "0.1"})

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Transfer-Encoding": "chunked",
    }
    
    try:
        req.ext_info.update({"model_name": req.model_name})
        req.ext_info.update({"incremental": req.incremental})
        req.ext_info.update({"temperature": req.temperature})
        req.ext_info.update({"max_new_tokens": req.max_new_tokens})

        try:
            from derisk.core import HumanMessage
            from derisk.core.schema.types import ChatCompletionUserMessageParam
            user_msg = req.user_input
            if isinstance(user_msg, str):
                in_message = HumanMessage.parse_chat_completion_message(
                    user_msg, ignore_unknown_media=True
                )
            elif isinstance(user_msg, dict):
                user_msg.setdefault("role", "user")
                in_message = HumanMessage.parse_chat_completion_message(
                    ChatCompletionUserMessageParam(**user_msg), ignore_unknown_media=True
                )
            else:
                in_message = str(user_msg)
        except ImportError:
            in_message = req.user_input if isinstance(req.user_input, str) else str(req.user_input)

        work_mode = req.work_mode or WorkMode.SIMPLE

        if work_mode == WorkMode.QUICK:
            async def chat_wrapper_quick():
                try:
                    from derisk_serve.agent.agents.controller import multi_agents
                    async for chunk, agent_conv_id in multi_agents.quick_app_chat(
                        conv_session_id=req.conv_uid,
                        user_query=in_message,
                        chat_in_params=req.chat_in_params,
                        app_code=req.app_code,
                        user_code=req.user_name,
                        sys_code=req.sys_code,
                        **req.ext_info,
                    ):
                        yield chunk
                except Exception as e:
                    logger.error(f"[API] quick_app_chat error: {e}")
                    yield f"data:{{'error': '{str(e)}'}}\n\n"

            if req.stream:
                return StreamingResponse(
                    chat_wrapper_quick(),
                    headers=headers,
                    media_type="text/event-stream",
                )
            else:
                result_chunks = []
                async for chunk in chat_wrapper_quick():
                    result_chunks.append(chunk)
                return {"success": True, "content": "".join(result_chunks)}

        elif work_mode == WorkMode.BACKGROUND:
            async def chat_wrapper_background():
                try:
                    from derisk_serve.agent.agents.controller import multi_agents
                    async for chunk, agent_conv_id in multi_agents.app_chat_v2(
                        conv_uid=req.conv_uid,
                        background_tasks=background_tasks,
                        gpts_name=req.app_code,
                        specify_config_code=req.app_config_code,
                        user_query=in_message,
                        user_code=req.user_name,
                        sys_code=req.sys_code,
                        chat_in_params=req.chat_in_params,
                        **req.ext_info,
                    ):
                        yield chunk
                except Exception as e:
                    logger.error(f"[API] app_chat_v2 error: {e}")
                    yield f"data:{{'error': '{str(e)}'}}\n\n"

            return StreamingResponse(
                chat_wrapper_background(),
                headers=headers,
                media_type="text/event-stream",
            )

        elif work_mode == WorkMode.ASYNC:
            try:
                from derisk_serve.agent.agents.controller import multi_agents
                result = await multi_agents.app_chat_v3(
                    conv_uid=req.conv_uid,
                    background_tasks=background_tasks,
                    gpts_name=req.app_code,
                    specify_config_code=req.app_config_code,
                    user_query=in_message,
                    user_code=req.user_name,
                    sys_code=req.sys_code,
                    chat_in_params=req.chat_in_params,
                    **req.ext_info,
                )
                agent_conv_id = result[1] if result else None
                return {"success": True, "data": {"conv_id": agent_conv_id}}
            except Exception as e:
                logger.error(f"[API] app_chat_v3 error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        else:
            try:
                from derisk_serve.agent.agents.controller import multi_agents
                async def chat_wrapper_simple():
                    async for chunk, agent_conv_id in multi_agents.app_chat(
                        conv_uid=req.conv_uid,
                        gpts_name=req.app_code,
                        specify_config_code=req.app_config_code,
                        user_query=in_message,
                        user_code=req.user_name,
                        sys_code=req.sys_code,
                        chat_in_params=req.chat_in_params,
                        **req.ext_info,
                    ):
                        yield chunk

                if req.stream:
                    return StreamingResponse(
                        chat_wrapper_simple(),
                        headers=headers,
                        media_type="text/event-stream",
                    )
                else:
                    result_chunks = []
                    async for chunk in chat_wrapper_simple():
                        result_chunks.append(chunk)
                    return {"success": True, "content": "".join(result_chunks)}
            except Exception as e:
                logger.error(f"[API] multi_agents not available, using fallback: {e}")
                
                if req.stream:
                    async def fallback_wrapper():
                        execution_id = await get_executor().execute(
                            task=str(in_message),
                            metadata={"session_id": req.session_id, "conv_uid": req.conv_uid}
                        )
                        yield f"data:{{'execution_id': '{execution_id}'}}\n\n"
                    
                    return StreamingResponse(
                        fallback_wrapper(),
                        headers=headers,
                        media_type="text/event-stream",
                    )
                else:
                    execution_id = await get_executor().execute(
                        task=str(in_message),
                        metadata={"session_id": req.session_id, "conv_uid": req.conv_uid}
                    )
                    return {"success": True, "execution_id": execution_id}

    except Exception as e:
        logger.exception(f"Chat Exception! {e}")

        async def error_text(err_msg):
            yield f"data:{err_msg}\n\n"

        if req.stream:
            return StreamingResponse(
                error_text(str(e)),
                headers=headers,
                media_type="text/plain",
            )
        else:
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/input/submit", response_model=UserInputResponse)
async def submit_user_input(req: SubmitUserInputRequest):
    """
    提交用户主动输入（支持分布式部署）
    
    用户可以在Agent执行过程中主动输入内容
    系统会自动路由到执行该session的节点
    """
    try:
        from ..interaction.sse_stream_manager import get_sse_manager
        
        sse_manager = get_sse_manager()
        
        success = await sse_manager.submit_user_input(
            session_id=req.session_id,
            content=req.content,
            input_type=req.input_type,
            metadata=req.metadata,
        )
        
        if not success:
            return UserInputResponse(
                success=False,
                message="No active execution for this session",
                queue_length=0,
            )
        
        has_pending = await sse_manager.has_pending_user_input(req.session_id)
        
        logger.info(f"[API] User input submitted: {req.content[:50]}... for session {req.session_id}")
        
        return UserInputResponse(
            success=True,
            message="Input submitted and routed to execution node",
            queue_length=1 if has_pending else 0,
        )
    except Exception as e:
        logger.error(f"[API] 提交用户输入失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/input/queue/{session_id}")
async def get_input_queue(session_id: str):
    """获取用户输入队列状态"""
    try:
        from ..interaction.sse_stream_manager import get_sse_manager
        
        sse_manager = get_sse_manager()
        has_pending = await sse_manager.has_pending_user_input(session_id)
        node_id = await sse_manager.get_execution_node(session_id)
        
        return {
            "success": True,
            "session_id": session_id,
            "has_pending_input": has_pending,
            "execution_node": node_id,
            "is_local": await sse_manager.is_local_execution(session_id),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/input/queue/{session_id}")
async def clear_input_queue(session_id: str):
    """清空用户输入队列"""
    try:
        from ..interaction.sse_stream_manager import get_sse_manager
        
        sse_manager = get_sse_manager()
        await sse_manager.unregister_execution(session_id)
        
        return {"success": True, "message": "Queue cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/execution/node/{session_id}")
async def get_execution_node(session_id: str):
    """获取执行节点信息（用于调试）"""
    try:
        from ..interaction.sse_stream_manager import get_sse_manager
        
        sse_manager = get_sse_manager()
        node_id = await sse_manager.get_execution_node(session_id)
        is_local = await sse_manager.is_local_execution(session_id)
        
        return {
            "success": True,
            "session_id": session_id,
            "execution_node": node_id,
            "is_local": is_local,
            "current_node": sse_manager.node_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 进度追踪 ==========

@router.get("/execution/{execution_id}/progress")
async def get_progress(execution_id: str):
    """获取执行进度"""
    progress = get_executor().get_progress(execution_id)
    
    if not progress:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    return {
        "success": True,
        "data": {
            "phase": progress.phase.value,
            "current_step": progress.current_step,
            "total_steps": progress.total_steps,
            "progress_percent": progress.progress_percent,
            "status": progress.status.value,
            "elapsed_time": progress.elapsed_time,
            "estimated_remaining": progress.estimated_remaining
        }
    }


@router.post("/execution/{execution_id}/pause")
async def pause_execution(execution_id: str):
    """暂停执行"""
    try:
        await get_executor().pause(execution_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execution/{execution_id}/resume")
async def resume_execution(execution_id: str):
    """恢复执行"""
    try:
        await get_executor().resume(execution_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execution/{execution_id}/cancel")
async def cancel_execution(execution_id: str):
    """取消执行"""
    try:
        await get_executor().cancel(execution_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 检查点管理 ==========

@router.get("/execution/{execution_id}/checkpoints")
async def list_checkpoints(execution_id: str):
    """列出检查点"""
    try:
        harness = get_executor()._harness
        checkpoints = await harness.checkpoint_manager.list_checkpoints(execution_id)
        
        return {
            "success": True,
            "data": [
                {
                    "checkpoint_id": cp.checkpoint_id,
                    "checkpoint_type": cp.checkpoint_type.value,
                    "step_index": cp.step_index,
                    "timestamp": cp.timestamp.isoformat(),
                    "message": cp.message
                }
                for cp in checkpoints
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execution/{execution_id}/checkpoint")
async def create_checkpoint(execution_id: str, req: CreateCheckpointRequest):
    """创建检查点"""
    try:
        harness = get_executor()._harness
        snapshot = get_executor().get_snapshot(execution_id)
        
        if not snapshot:
            raise HTTPException(status_code=404, detail="Execution not found")
        
        checkpoint = await harness.checkpoint_manager.create_checkpoint(
            execution_id=execution_id,
            checkpoint_type=CheckpointType(req.checkpoint_type),
            state=snapshot.dict(),
            step_index=snapshot.current_step,
            message=req.message
        )
        
        return {
            "success": True,
            "checkpoint_id": checkpoint.checkpoint_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/checkpoint/{checkpoint_id}/restore")
async def restore_checkpoint(checkpoint_id: str):
    """恢复检查点"""
    try:
        execution_id = await get_executor().restore_from_checkpoint(checkpoint_id)
        
        if not execution_id:
            raise HTTPException(status_code=404, detail="Checkpoint not found")
        
        return {
            "success": True,
            "execution_id": execution_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 目标管理 ==========

@router.post("/execution/{execution_id}/goal")
async def create_goal(execution_id: str, req: CreateGoalRequest):
    """创建目标"""
    try:
        criteria = []
        if req.criteria:
            for c in req.criteria:
                criteria.append(SuccessCriterion(
                    description=c.get("description", ""),
                    type=c.get("type", "llm_eval"),
                    config=c.get("config", {})
                ))
        
        goal = await get_executor()._harness.goal_manager.create_goal(
            name=req.name,
            description=req.description,
            priority=GoalPriority(req.priority),
            criteria=criteria
        )
        
        return {
            "success": True,
            "goal_id": goal.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/execution/{execution_id}/goals")
async def list_goals(execution_id: str):
    """列出目标"""
    try:
        harness = get_executor()._harness
        goals = harness.goal_manager.get_all_goals()
        
        return {
            "success": True,
            "data": [
                {
                    "goal_id": g.id,
                    "name": g.name,
                    "status": g.status.value,
                    "priority": g.priority.value,
                    "created_at": g.created_at.isoformat()
                }
                for g in goals
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execution/{execution_id}/goal/{goal_id}/complete")
async def complete_goal(execution_id: str, goal_id: str):
    """完成目标"""
    try:
        harness = get_executor()._harness
        await harness.goal_manager.complete_goal(goal_id, "手动完成")
        
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 执行历史 ==========

@router.get("/executions")
async def list_executions():
    """列出所有执行"""
    try:
        executions = await get_executor().list_executions()
        
        return {
            "success": True,
            "data": executions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/execution/{execution_id}")
async def get_execution(execution_id: str):
    """获取执行详情"""
    snapshot = get_executor().get_snapshot(execution_id)
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    return {
        "success": True,
        "data": snapshot.dict()
    }


# ========== 统计信息 ==========

@router.get("/stats")
async def get_stats():
    """获取统计信息"""
    try:
        stats = get_executor().get_statistics()
        return {"success": True, "data": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 配置管理 ==========

@router.get("/config/{key}")
async def get_config(key: str):
    """获取配置"""
    from ..config_manager import get_config as _get_config
    value = _get_config(key)
    return {"success": True, "key": key, "value": value}


@router.post("/config")
async def set_config(data: Dict[str, Any]):
    """设置配置"""
    from ..config_manager import set_config as _set_config
    
    key = data.get("key")
    value = data.get("value")
    
    if not key:
        raise HTTPException(status_code=400, detail="Key is required")
    
    _set_config(key, value)
    return {"success": True}


# ========== 状态接口 ==========

@router.get("/status")
async def get_status():
    """获取系统状态"""
    try:
        executor = get_executor()
        return {
            "success": True,
            "data": {
                "running": True,
                "executor_stats": executor.get_statistics() if hasattr(executor, 'get_statistics') else {}
            }
        }
    except Exception:
        return {
            "success": True,
            "data": {
                "running": False,
                "message": "Executor not initialized, please set OPENAI_API_KEY"
            }
        }


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


# ========== WebSocket ==========

_active_websockets: Dict[str, List[WebSocket]] = {}


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket 流式消息端点"""
    await websocket.accept()
    
    if session_id not in _active_websockets:
        _active_websockets[session_id] = []
    _active_websockets[session_id].append(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue
            
            msg_type = message.get("type")
            
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            
            elif msg_type == "chat":
                content = message.get("content", "")
                
                try:
                    async for chunk in _stream_chat(session_id, content):
                        await websocket.send_json(chunk)
                except Exception as e:
                    await websocket.send_json({"type": "error", "content": str(e)})
            
            elif msg_type == "progress_subscribe":
                await websocket.send_json({"type": "subscribed", "session_id": session_id})
                
    except WebSocketDisconnect:
        pass
    finally:
        if session_id in _active_websockets:
            try:
                _active_websockets[session_id].remove(websocket)
            except ValueError:
                pass


async def _stream_chat(session_id: str, message: str):
    """流式聊天生成"""
    yield {"type": "thinking", "content": f"处理消息..."}
    
    try:
        executor = get_executor()
        
        execution_id = await executor.execute(
            task=message,
            metadata={"session_id": session_id}
        )
        
        yield {"type": "execution_started", "execution_id": execution_id}
        
        import asyncio
        for _ in range(10):
            await asyncio.sleep(0.1)
            progress = executor.get_progress(execution_id)
            if progress:
                yield {
                    "type": "progress",
                    "content": {
                        "phase": progress.phase.value,
                        "percent": progress.progress_percent,
                        "step": progress.current_step
                    }
                }
                
                if progress.status.value == "completed":
                    break
        
        snapshot = executor.get_snapshot(execution_id)
        if snapshot:
            yield {
                "type": "complete",
                "content": snapshot.result or "完成"
            }
        else:
            yield {"type": "complete", "content": "任务已提交"}
            
    except Exception as e:
        yield {"type": "error", "content": str(e)}


# ========== 创建应用 ==========

def create_app():
    """创建完整应用"""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    
    app = FastAPI(
        title="DeRisk Agent V2 API",
        description="完整Agent产品API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(router, prefix="/api/v2")
    
    @app.on_event("startup")
    async def startup_event():
        logger.info("[API] DeRisk Agent V2 API 启动")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("[API] DeRisk Agent V2 API 关闭")
    
    @app.get("/")
    async def root():
        return {
            "name": "DeRisk Agent V2",
            "version": "1.0.0",
            "docs": "/docs",
            "api": "/api/v2"
        }
    
    return app