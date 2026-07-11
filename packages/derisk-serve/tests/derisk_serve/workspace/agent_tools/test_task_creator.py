"""create_task_from_tool 单元测试:验证创建后 detached 启动 run_task,以及 LLM 标题总结。"""
import asyncio
from unittest.mock import MagicMock

import pytest


def _make_system_app(task_entity, playbook=None):
    """构造 mock system_app,get_component 按名字返回 mock service。"""
    task_service = MagicMock()
    task_service.create.return_value = task_entity
    task_service.start.return_value = MagicMock(id=task_entity.id, status="running")
    task_service.get_by_id.return_value = task_entity
    playbook_service = MagicMock()
    playbook_service.get_by_id.return_value = playbook
    system_app = MagicMock()

    def get_component(name, cls=None):
        if name == "serve_task_service":
            return task_service
        if name == "serve_playbook_service":
            return playbook_service
        return MagicMock()

    system_app.get_component.side_effect = get_component
    return system_app, task_service


def _make_task_entity(eid=1, title="raw text", playbook_id=7):
    entity = MagicMock()
    entity.id = eid
    entity.title = title
    entity.status = "draft"
    entity.playbook_id = playbook_id
    entity.triggered_by = "manual"
    # update() 需要的字段
    for f in ("workspace_id", "parent_task_id", "type", "description", "status",
              "priority", "triggered_by", "trigger_ref", "playbook_id",
              "playbook_version_id", "conv_session_id", "created_by_user_id",
              "assigned_agents", "context", "due_at"):
        setattr(entity, f, None)
    return entity


def test_create_task_from_tool_starts_run_task_detached(monkeypatch):
    """创建任务后,必须 detached 启动 task_service.start + playbook_runtime.run_task。"""
    from derisk_serve.workspace.agent_tools import _task_creator

    entity = _make_task_entity()
    playbook = MagicMock()
    playbook.name = "营收分析"
    system_app, task_service = _make_system_app(entity, playbook=playbook)

    created_tasks = []

    def fake_create_task(coro):
        created_tasks.append(coro)
        return asyncio.ensure_future(coro)

    monkeypatch.setattr(_task_creator.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(_task_creator.playbook_runtime, "run_task", MagicMock())

    result = _task_creator.create_task_from_tool(
        system_app=system_app,
        workspace_id=10,
        user_id="123",
        playbook_id=7,
        title="本周营收分析",
        description=None,
        model_name="test-provider/test-model",
    )

    assert result["task_id"] == 1
    assert result["playbook_name"] == "营收分析"
    assert len(created_tasks) >= 1
    task_service.create.assert_called_once()


def test_summarize_task_title_calls_llm_and_returns_text(monkeypatch):
    """_summarize_task_title 利用 AIWrapper 调一次 LLM 并返回 trim 后的文本。"""
    from derisk_serve.workspace.agent_tools import _task_creator

    async def fake_awrapper_create(self, **kwargs):
        class _R:
            content = "本周营收分析报告"
        yield _R()

    monkeypatch.setattr(
        "derisk.agent.util.llm.llm_client.AIWrapper.create",
        fake_awrapper_create,
    )
    monkeypatch.setattr(
        "derisk.agent.util.llm.model_config_cache.ModelConfigCache.get_all_models",
        classmethod(lambda cls: ["test-provider/test-model"]),
    )
    monkeypatch.setattr(
        "derisk.agent.util.llm.model_config_cache.ModelConfigCache.get_config",
        classmethod(lambda cls, key: None),
    )

    out = asyncio.get_event_loop().run_until_complete(
        _task_creator._summarize_task_title("生成营收周报", "营收分析", "test-provider/test-model")
    )
    assert "营收分析报告" in out