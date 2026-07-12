"""Helper to create a real Task from tool invocation (non-intervention path).

创建任务后:(1) detached 启动 run_task 让 Agent 真正跑起来;
(2) detached 调 LLM 把原始输入总结为 ≤16 字短标题并写回 task.title。
两个后台协程互不影响,且不影响已返回的 SSE 流。
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# hold refs to detached asyncio tasks so CPython doesn't GC them mid-flight (CPython/asyncio caveat)
_pending_detached_tasks: set = set()


def __getattr__(name):
    """惰性暴露 playbook_runtime 模块,避免 module-level import 触发循环导入
    (runtime -> agent.agents.controller -> ... -> toolkit -> _task_creator)。
    测试通过 monkeypatch.setattr(_task_creator.playbook_runtime, "run_task", ...) 访问。
    """
    if name == "playbook_runtime":
        from derisk_serve.playbook import runtime as playbook_runtime
        globals()["playbook_runtime"] = playbook_runtime
        return playbook_runtime
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def _summarize_task_title(
    user_text: str,
    playbook_name: Optional[str],
    model: Optional[str],
) -> str:
    """单次 LLM 调用,把任务发起文本压缩成 ≤16 字短标题。失败返回 ""。"""
    try:
        from derisk.agent.util.llm.llm_client import AIWrapper
        from derisk.agent.util.llm.model_config_cache import ModelConfigCache
        from derisk.agent.core.llm_config import AgentLLMConfig
    except ImportError as e:
        logger.warning("LLM stack not available for title summarization: %s", e)
        return ""

    if not model:
        all_models = ModelConfigCache.get_all_models()
        if not all_models:
            return ""
        model = all_models[0]

    model_config = ModelConfigCache.get_config(model)
    agent_llm_config = None
    if model_config:
        try:
            agent_llm_config = AgentLLMConfig.from_dict(model_config)
        except Exception as e:  # noqa: BLE001
            logger.warning("Parse model config for %s failed: %s", model, e)

    ai_wrapper = AIWrapper(llm_config=agent_llm_config)
    prompt = (
        "把下面这条任务发起文本压缩成 ≤16 字的简短中文标题,"
        "只输出标题本身,不要引号、不要解释、不要标点结尾:\n"
        f"用户输入:{user_text}\n"
        f"剧本:{playbook_name or '无'}"
    )
    messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]

    result_text = ""
    try:
        async for result in ai_wrapper.create(
            messages=messages, llm_model=model, stream_out=False
        ):
            if result and result.content:
                result_text += result.content
    except Exception as e:  # noqa: BLE001
        logger.warning("summarize task title LLM call failed: %s", e)
        return ""
    return result_text.strip()


async def _run_task_detached(system_app, task_id: int, user_code: Optional[str]) -> None:
    """detached 跑 start + run_task，任何异常只记日志并把任务转成 failed。"""
    task_service = None
    try:
        from derisk_serve.task.service.service import (
            TASK_SERVICE_COMPONENT_NAME,
            TaskService,
        )
        from derisk_serve.playbook import runtime as playbook_runtime

        task_service = system_app.get_component(TASK_SERVICE_COMPONENT_NAME, TaskService)
        task_service.start(task_id)
        await playbook_runtime.run_task(system_app, task_id, user_code=user_code)
    except Exception as e:  # noqa: BLE001
        logger.exception("detached run_task for task %s failed: %s", task_id, e)
        # best-effort: 标记为 failed，避免任务永久停在 running。
        # transition 对非法转换会 raise ValueError（task 可能已被 run_task 内部转成终态），
        # 这里用嵌套 try 全吞，保证 _run_task_detached 永不再次抛出。
        if task_service is not None:
            try:
                task_service.transition(task_id, "failed")
            except Exception:  # noqa: BLE001
                logger.warning(
                    "best-effort transition(failed) for task %s raised; leaving status as-is",
                    task_id,
                    exc_info=True,
                )


async def _summarize_title_detached(
    system_app, task_id: int, user_text: str, playbook_name: Optional[str], model: Optional[str]
) -> None:
    """detached 跑 LLM 标题总结并写回。任何异常只记日志,保留占位标题。"""
    try:
        new_title = await _summarize_task_title(user_text, playbook_name, model)
        if not new_title:
            return
        from derisk_serve.task.api.schemas import TaskRequest
        from derisk_serve.task.service.service import (
            TASK_SERVICE_COMPONENT_NAME,
            TaskService,
        )

        task_service: TaskService = system_app.get_component(
            TASK_SERVICE_COMPONENT_NAME, TaskService
        )
        existing = task_service.get_by_id(task_id)
        if not existing:
            return
        task_service.update(
            TaskRequest(
                id=existing.id,
                workspace_id=existing.workspace_id,
                parent_task_id=existing.parent_task_id,
                type=existing.type,
                title=new_title,
                description=existing.description or "",
                status=existing.status,
                priority=existing.priority,
                triggered_by=existing.triggered_by,
                trigger_ref=existing.trigger_ref,
                playbook_id=existing.playbook_id,
                playbook_version_id=existing.playbook_version_id,
                conv_session_id=existing.conv_session_id,
                created_by_user_id=existing.created_by_user_id,
                assigned_agents=existing.assigned_agents,
                context=existing.context,
                due_at=existing.due_at,
            )
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("detached title summarization for task %s failed: %s", task_id, e)


def create_task_from_tool(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    playbook_id: Optional[int] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a real Task via TaskService, return task metadata.

    创建后:(1) detached 启动 run_task 让 Agent 真跑;(2) detached 总结短标题写回。
    """
    from derisk_serve.task.api.schemas import TaskRequest
    from derisk_serve.task.service.service import (
        TASK_SERVICE_COMPONENT_NAME,
        TaskService,
    )
    from derisk_serve.playbook.service.service import (
        PLAYBOOK_SERVICE_COMPONENT_NAME,
        PlaybookService,
    )
    from derisk_serve.playbook import runtime as playbook_runtime  # noqa: F401  供测试 monkeypatch

    task_service: TaskService = system_app.get_component(
        TASK_SERVICE_COMPONENT_NAME, TaskService
    )
    playbook_service: PlaybookService = system_app.get_component(
        PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService
    )

    playbook = None
    if playbook_id:
        playbook = playbook_service.get_by_id(playbook_id)

    request = TaskRequest(
        workspace_id=workspace_id,
        playbook_id=playbook_id,
        title=title or (playbook.name if playbook else "手动创建任务"),
        description=description or "",
        type="adhoc",
        triggered_by="manual",
        created_by_user_id=int(user_id) if user_id and user_id.isdigit() else None,
    )
    entity = task_service.create(request)

    # detached 启动真实运行(不阻塞当前 SSE 流)
    run_t = asyncio.create_task(_run_task_detached(system_app, entity.id, user_id))
    _pending_detached_tasks.add(run_t)
    run_t.add_done_callback(_pending_detached_tasks.discard)
    # detached 启动标题总结(独立于 run_task,互不影响)
    if title:
        title_t = asyncio.create_task(
            _summarize_title_detached(
                system_app, entity.id, title, playbook.name if playbook else None, model_name
            )
        )
        _pending_detached_tasks.add(title_t)
        title_t.add_done_callback(_pending_detached_tasks.discard)

    return {
        "task_id": entity.id,
        "title": entity.title,
        "status": entity.status,
        "playbook_id": entity.playbook_id,
        "playbook_name": playbook.name if playbook else None,
        "triggered_by": entity.triggered_by,
    }