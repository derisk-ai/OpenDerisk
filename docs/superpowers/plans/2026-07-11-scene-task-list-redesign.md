# 场景空间任务列表重做 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让场景空间左侧任务栏有过滤分类与丰富卡片信息,并修复"选剧本发起的任务没真正用 Agent 跑"的后端缺陷。

**Architecture:** 后端在 `create_task_from_tool` 创建任务后用 `asyncio.create_task` detached 跑 `task_service.start` + `playbook_runtime.run_task`(复用现有真能跑的路),并行起一个 detached LLM 标题总结协程;前端重做 `scene-task-rail`(Tab 过滤 + 方向 B 分层呼吸卡),用 shell 已 fetch 的 playbooks 本地查剧本名,以 4s 运行时轮询替代无法走事件流的后台任务状态刷新。

**Tech Stack:** Python 3 / asyncio / SQLAlchemy(后端 derisk-serve),React + Next.js + Ant Design + ahooks + TypeScript(前端 web/),pytest(asyncio_mode=auto)。

## Global Constraints

- 状态枚举固定(应用层 `VALID_TRANSITIONS` 约束):`draft / pending_trigger / running / awaiting_human / blocked / delivered / closed / archived / failed`。**无 `completed`(用 `delivered`)、无"待介入"(用 `awaiting_human`)**。
- 视觉用现有 design token(`--ws-*`,映射 `--mcp-*`):accent `#0069fe`、attention `#f59e0b`、success `#10b981`、danger `#ef4444`、surface `#fff`、border `#e5e7eb`、radius `12px`。不引入新色板。
- 后端 detached 协程必须最外层 `try/except` 记日志,绝不影响已返回的 SSE 和对方协程。
- 不改 `TaskResponse` schema、`TaskEntity` 列、workspace 事件架构、`playbook_runtime.run_task` 调度逻辑。
- 不抽共享 `Task` TS 类型 —— 只在 `scene-task-rail.tsx` 内定义最小类型。
- 标题总结单次失败保留占位、不重试。
- 前端分支:`feat/scene-agent-workspace-input`。提交信息按现有风格 `feat(web): ...` / `feat(task): ...`,末尾 `Co-Authored-By: Claude <noreply@anthropic.com>`。

## File Structure

**后端(2 文件)**:
- `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/_task_creator.py` —— 扩 `create_task_from_tool`:签名加 `model_name`;创建后 detached 跑 `start`+`run_task`;新增 `_summarize_task_title` helper + detached 标题协程。
- `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` —— `aggregation_chat` 的 `playbook_command` 分支:从 `chat_in_params` 抽 `model` 透传;`_user_text` 为空时拒绝创建。

**前端(4 文件)**:
- `web/src/app/workspaces/detail/scene-task-rail.tsx` —— 重写:Tab 过滤、方向 B 卡片、人话状态、已耗时定时器、空态、最小 `Task` 类型、接收 `playbooks` props。
- `web/src/app/workspaces/detail/scene-workspace-shell.tsx` —— 透传 `playbooks` 给 rail;新增 4s 运行时轮询 `useEffect`。
- `web/src/app/workspaces/detail/scene-workspace.css` —— 方向 B 卡片样式(用 `--ws-*`)。
- `web/src/app/workspaces/detail/agent-workspace-input.tsx` —— 选剧本空文本时禁用发送 + 提示。

**测试**:
- `packages/derisk-serve/tests/derisk_serve/workspace/agent_tools/test_task_creator.py` —— 新建,`create_task_from_tool` 单元测试。
- 扩 `packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py` —— 加 `_extract_model` 测试。
- `web/src/app/workspaces/detail/agent-workspace-input.test.ts` —— 新建,`canSendSceneTask` 纯函数测试。
- `web/src/app/workspaces/detail/scene-task-rail.test.ts` —— 新建,`statusToTab`/`statusLabel` 纯函数测试。

---

### Task 1: 后端 — `create_task_from_tool` 接上真实运行 + 标题总结

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/_task_creator.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/agent_tools/test_task_creator.py` (Create)

**Interfaces:**
- Consumes: `task_service.start(task_id) -> TaskResponse`(`task/service/service.py:138`);`task_service.update(TaskRequest) -> TaskResponse`(`task/service/service.py:83`);`task_service.get_by_id(task_id) -> Optional[TaskResponse]`(`task/service/service.py:99`);`playbook_runtime.run_task(system_app, task_id, user_code=None, sys_code=None) -> Dict`(`playbook/runtime.py:34`,async);`AIWrapper` + `ModelConfigCache`(`derisk.agent.util.llm.*`)。
- Produces: `create_task_from_tool(system_app, workspace_id, user_id, playbook_id, title, description, model_name) -> Dict`。新签名加 `model_name: Optional[str] = None`。返回 dict 不变。

- [ ] **Step 1: 写失败测试**

创建 `packages/derisk-serve/tests/derisk_serve/workspace/agent_tools/test_task_creator.py`:

```python
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
        if name == "task_service":
            return task_service
        if name == "playbook_service":
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
    system_app, task_service = _make_system_app(entity, playbook=MagicMock(name="营收分析"))

    created coronas = []

    def fake_create_task(coro):
        created coronas.append(coro)
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
    assert len(created coronas) >= 1
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
```

> ⚠️ 注意:`created coronas` 是占位笔误,实现时写 `created_tasks = []`、`created_tasks.append(coro)`、`assert len(created_tasks) >= 1`。(此处的中文笔误用来让测试在写代码前 RED,真正落盘时改成 `created_tasks`。)

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/agent_tools/test_task_creator.py -v`
Expected: FAIL —— `_task_creator` 无 `asyncio` / `playbook_runtime` 模块属性,或 `_summarize_task_title` 未定义。

- [ ] **Step 3: 写最小实现**

整体替换 `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/_task_creator.py`:

```python
"""Helper to create a real Task from tool invocation (non-intervention path).

创建任务后:(1) detached 启动 run_task 让 Agent 真正跑起来;
(2) detached 调 LLM 把原始输入总结为 ≤16 字短标题并写回 task.title。
两个后台协程互不影响,且不影响已返回的 SSE 流。
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
    """detached 跑 start + run_task,任何异常只记日志。"""
    try:
        from derisk_serve.task.service.service import (
            TASK_SERVICE_COMPONENT_NAME,
            TaskService,
        )
        from derisk_serve.playbook import runtime as playbook_runtime

        task_service: TaskService = system_app.get_component(
            TASK_SERVICE_COMPONENT_NAME, TaskService
        )
        task_service.start(task_id)
        await playbook_runtime.run_task(system_app, task_id, user_code=user_code)
    except Exception as e:  # noqa: BLE001
        logger.exception("detached run_task for task %s failed: %s", task_id, e)


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
    asyncio.create_task(_run_task_detached(system_app, entity.id, user_id))
    # detached 启动标题总结(独立于 run_task,互不影响)
    if title:
        asyncio.create_task(
            _summarize_title_detached(
                system_app, entity.id, title, playbook.name if playbook else None, model_name
            )
        )

    return {
        "task_id": entity.id,
        "title": entity.title,
        "status": entity.status,
        "playbook_id": entity.playbook_id,
        "playbook_name": playbook.name if playbook else None,
        "triggered_by": entity.triggered_by,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/agent_tools/test_task_creator.py -v`
Expected: PASS(2 个测试通过)。落地前把测试里的 `created coronas` 笔误改成 `created_tasks`。

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/agent_tools/_task_creator.py packages/derisk-serve/tests/derisk_serve/workspace/agent_tools/test_task_creator.py
git commit -m "feat(task): real agent run + LLM title summary on chat-initiated task

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 后端 — `aggregation_chat` 透传 model + 拒绝空文本发起

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py:991-1140`
- Test: `packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py`

**Interfaces:**
- Consumes: Task 1 的 `create_task_from_tool(..., model_name=...)`;`ChatInParamValue`(`building/config/api/schemas.py`)。
- Produces: 新静态方法 `AgentChat._extract_model(chat_in_params) -> Optional[str]`;playbook_command 分支在 `_user_text` 为空时 `yield` 一个错误 vis 提示并 `return`(不创建任务)。

- [ ] **Step 1: 写失败测试**

追加到 `packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py` 末尾:

```python
def test_extract_model_returns_model_name():
    """chat_in_params 含 model 参数时能抽到 param_value。"""
    chat = SimpleAgentChat.__new__(SimpleAgentChat)
    params = [
        _make_param("resource", "[]", "common_file"),
        _make_param("model", "test-provider/test-model"),
    ]
    assert chat._extract_model(params) == "test-provider/test-model"  # type: ignore[attr-defined]


def test_extract_model_returns_none_when_absent():
    chat = SimpleAgentChat.__new__(SimpleAgentChat)
    assert chat._extract_model(None) is None  # type: ignore[attr-defined]
    assert chat._extract_model([_make_param("resource", "[]")]) is None  # type: ignore[attr-defined]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py::test_extract_model_returns_model_name -v`
Expected: FAIL —— `SimpleAgentChat` 无 `_extract_model`。

- [ ] **Step 3: 写最小实现**

在 `agent_chat.py` 的 `_extract_playbook_command` 静态方法之后(约 line 1001 后)加一个静态方法:

```python
    @staticmethod
    def _extract_model(chat_in_params):
        """从 chat_in_params 抽取 model 参数,返回 model 名字符串或 None。"""
        if not chat_in_params:
            return None
        for p in chat_in_params:
            if getattr(p, "param_type", None) == "model":
                return getattr(p, "param_value", None)
        return None
```

然后修改 `aggregation_chat` 的 playbook_command 分支。定位现有代码(约 line 1095-1140),把:

```python
            result = create_task_from_tool(
                system_app=self.system_app,
                workspace_id=int(ext_info["workspace_id"]),
                user_id=user_code,
                playbook_id=playbook_command.get("playbook_id"),
                title=_user_text or playbook_command.get("playbook_name"),
                description=None,
            )
            # 发 task_created workspace event 后直接结束流 ...
            yield (
                None,
                format_workspace_event(
                    "task_created",
                    {
                        "task_id": result["task_id"],
                        ...
                        "workspace_id": int(ext_info["workspace_id"]),
                    },
                ),
                agent_conv_id,
            )
            yield None, _format_vis_msg("[DONE]"), agent_conv_id
            return
```

替换为:

```python
            # 选了剧本必须有任务目标:剧本只指定资源/能力,目标由用户输入。
            if not _user_text.strip():
                yield (
                    None,
                    _format_vis_msg(
                        "选择剧本后请输入本次任务目标(剧本只指定资源与能力,目标由你定义)。"
                    ),
                    agent_conv_id,
                )
                yield None, _format_vis_msg("[DONE]"), agent_conv_id
                return
            _model_name = self._extract_model(chat_in_params)
            result = create_task_from_tool(
                system_app=self.system_app,
                workspace_id=int(ext_info["workspace_id"]),
                user_id=user_code,
                playbook_id=playbook_command.get("playbook_id"),
                title=_user_text,
                description=None,
                model_name=_model_name,
            )
            # 发 task_created workspace event 后直接结束流(与 aggregation_chat 其余
            # yield 一致的 (task, sse_chunk, agent_conv_id) 三元组形态)
            yield (
                None,
                format_workspace_event(
                    "task_created",
                    {
                        "task_id": result["task_id"],
                        "title": result["title"],
                        "status": result["status"],
                        "playbook_id": result["playbook_id"],
                        "playbook_name": result["playbook_name"],
                        "triggered_by": result["triggered_by"],
                        "workspace_id": int(ext_info["workspace_id"]),
                    },
                ),
                agent_conv_id,
            )
            yield None, _format_vis_msg("[DONE]"), agent_conv_id
            return
```

> 注意:`format_workspace_event("task_created", {...})` 的 payload 内容保持与原来完全一致(只是放在替换块里完整写出)。`_user_text` 抽取逻辑(含 list content 拼接)在原代码里就在这段之前,不动。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py -v`
Expected: PASS(原有 4 个 + 新增 2 个全过)。

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py
git commit -m "feat(agent-chat): pass model to task creator, reject empty-text playbook launch

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 前端 — `AgentWorkspaceInput` 选剧本空文本禁用发送

**Files:**
- Modify: `web/src/app/workspaces/detail/agent-workspace-input.tsx`
- Test: `web/src/app/workspaces/detail/agent-workspace-input.test.ts` (Create)

**Interfaces:**
- Consumes: 现有 `playbookCommand`、`text`、`resources` state。
- Produces: 导出纯函数 `canSendSceneTask(text, hasResources, playbookCommand) -> boolean`。选了 `playbookCommand` 但 `text.trim()` 为空时,发送按钮禁用 + 输入框下提示文案。

- [ ] **Step 1: 写失败测试**

创建 `web/src/app/workspaces/detail/agent-workspace-input.test.ts`:

```ts
import { canSendSceneTask } from './agent-workspace-input';

const pb = { playbook_id: 1, playbook_name: '容量巡检' };

describe('canSendSceneTask', () => {
  it('allows send with text and no playbook', () => {
    expect(canSendSceneTask('hello', false, null)).toBe(true);
  });
  it('allows send with resources only and no playbook', () => {
    expect(canSendSceneTask('', true, null)).toBe(true);
  });
  it('blocks send with empty text and no resources and no playbook', () => {
    expect(canSendSceneTask('   ', false, null)).toBe(false);
  });
  it('blocks send when playbook chosen but text empty', () => {
    expect(canSendSceneTask('', false, pb)).toBe(false);
    expect(canSendSceneTask('   ', true, pb)).toBe(false);
  });
  it('allows send when playbook chosen and text present', () => {
    expect(canSendSceneTask('生成本周巡检', false, pb)).toBe(true);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

web 是 Next.js,优先用现有测试 runner。先探:

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && cat package.json | grep -E '"(test|jest|vitest)"' && npx tsc --noEmit -p tsconfig.json 2>&1 | head`

Expected: tsc 报错 `Module '"./agent-workspace-input"' has no exported member 'canSendSceneTask'`(因 Step 3 还没做)。若无 jest/vitest,以 tsc 报错作为 RED 信号。

- [ ] **Step 3: 写最小实现**

在 `agent-workspace-input.tsx` 顶部 import 之后加纯函数:

```tsx
/** 选了剧本时必须输入任务目标;没选剧本按原逻辑(有文本或有资源即可)。 */
export function canSendSceneTask(
  text: string,
  hasResources: boolean,
  playbookCommand: { playbook_id: number; playbook_name: string } | null,
): boolean {
  const trimmed = text.trim();
  if (playbookCommand) return trimmed.length > 0;
  return trimmed.length > 0 || hasResources;
}
```

把 `handleSend`(line 124-139)替换为:

```tsx
    const canSend = canSendSceneTask(text, resources.length > 0, playbookCommand);

    const handleSend = () => {
      if (!canSend) return;
      const trimmed = text.trim();
      onSend({
        text: trimmed,
        resources: resources.length ? resources : undefined,
        model: selectedModel || undefined,
        playbookCommand: playbookCommand ?? undefined,
      });
      setText('');
      setResources([]);
      setPlaybookCommand(null);
      setShowPlaybook(false);
    };
```

> `canSend` 声明要放在 `handleSend` 之前、组件函数体内能访问到 `text/resources/playbookCommand` 的位置(即现有 `handleSend` 所在那层作用域)。

然后给发送按钮加 `disabled`,并在输入框容器底部加提示。定位发送按钮(圆形发送按钮,在文件后部)。在它所在的 flex 容器内、按钮元素之前插入提示:

```tsx
        {playbookCommand && !text.trim() && (
          <div className="text-[11px] text-amber-600 px-1 pb-1">
            选了剧本要写本次任务目标 — 剧本只指定资源/能力,目标由你定。
          </div>
        )}
```

并在发送按钮上把现有 `disabled` 改为追加 `|| !canSend`(例如原 `disabled={loading || disabled}` → `disabled={loading || disabled || !canSend}`)。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && npx tsc --noEmit -p tsconfig.json`
Expected: tsc 通过。若有 jest/vitest,跑 `canSendSceneTask` 的 5 个 case 全过。

- [ ] **Step 5: 提交**

```bash
git add web/src/app/workspaces/detail/agent-workspace-input.tsx web/src/app/workspaces/detail/agent-workspace-input.test.ts
git commit -m "feat(web): block empty-text send when playbook chosen in AgentWorkspaceInput

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 前端 — `scene-task-rail` 重做(Tab 过滤 + 方向 B 卡片)

**Files:**
- Modify: `web/src/app/workspaces/detail/scene-task-rail.tsx`(整体重写)
- Test: `web/src/app/workspaces/detail/scene-task-rail.test.ts` (Create)

**Interfaces:**
- Consumes: 新增 props `playbooks?: { playbook_id: number; playbook_name: string }[]`。其余 props(`tasks`, `interventions`, `activeTaskId`, `disabled`, `onPreview`, `onEnterConversation`)不变。
- Produces: 导出纯函数 `statusToTab(status) -> TaskTabKey`、`statusLabel(status) -> string`、类型 `TaskTabKey`。纯展示组件,无对外新接口。

- [ ] **Step 1: 写失败测试**

创建 `web/src/app/workspaces/detail/scene-task-rail.test.ts`:

```ts
import { statusToTab, statusLabel } from './scene-task-rail';

describe('statusToTab', () => {
  it('maps running variants to running tab', () => {
    expect(statusToTab('running')).toBe('running');
    expect(statusToTab('draft')).toBe('running');
    expect(statusToTab('pending_trigger')).toBe('running');
    expect(statusToTab('blocked')).toBe('running');
  });
  it('maps awaiting_human to awaiting tab', () => {
    expect(statusToTab('awaiting_human')).toBe('awaiting');
  });
  it('maps delivered/closed to done tab', () => {
    expect(statusToTab('delivered')).toBe('done');
    expect(statusToTab('closed')).toBe('done');
  });
  it('maps failed to failed tab', () => {
    expect(statusToTab('failed')).toBe('failed');
  });
  it('falls back to all', () => {
    expect(statusToTab('whatever')).toBe('all');
    expect(statusToTab(undefined)).toBe('all');
  });
});

describe('statusLabel', () => {
  it('returns 人话文案', () => {
    expect(statusLabel('running')).toBe('运行中');
    expect(statusLabel('awaiting_human')).toBe('待你介入');
    expect(statusLabel('delivered')).toBe('已交付');
    expect(statusLabel('failed')).toBe('失败');
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && npx tsc --noEmit -p tsconfig.json`
Expected: tsc 报错 `scene-task-rail` 未导出 `statusToTab` / `statusLabel`。

- [ ] **Step 3: 写最小实现 — 重写 `scene-task-rail.tsx`**

整体替换 `web/src/app/workspaces/detail/scene-task-rail.tsx`:

```tsx
'use client';

import { useEffect, useMemo, useState } from 'react';
import { Input } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

export type TaskTabKey = 'all' | 'running' | 'awaiting' | 'done' | 'failed';

export function statusToTab(status: string | undefined): TaskTabKey {
  switch (status) {
    case 'running':
    case 'pending_trigger':
    case 'blocked':
    case 'draft':
      return 'running';
    case 'awaiting_human':
      return 'awaiting';
    case 'delivered':
    case 'closed':
      return 'done';
    case 'failed':
      return 'failed';
    default:
      return 'all';
  }
}

export function statusLabel(status: string | undefined): string {
  switch (status) {
    case 'running': return '运行中';
    case 'pending_trigger': return '等待触发';
    case 'blocked': return '阻塞';
    case 'draft': return '准备中';
    case 'awaiting_human': return '待你介入';
    case 'delivered': return '已交付';
    case 'closed': return '已关闭';
    case 'failed': return '失败';
    default: return status || '未知';
  }
}

const TAB_LABEL: Record<TaskTabKey, string> = {
  all: '全部',
  running: '运行中',
  awaiting: '待介入',
  done: '已完成',
  failed: '失败',
};

const TAB_CLASS: Record<TaskTabKey, string> = {
  all: 'ws-rail-tab--all',
  running: 'ws-rail-tab--running',
  awaiting: 'ws-rail-tab--awaiting',
  done: 'ws-rail-tab--done',
  failed: 'ws-rail-tab--failed',
};

function ElapsedTimer({ task }: { task: any }) {
  const [, force] = useState(0);
  useEffect(() => {
    if (!task?.started_at || task.status !== 'running') return;
    const t = setInterval(() => force((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [task?.started_at, task?.status]);
  if (!task?.started_at || task.status !== 'running') return <></>;
  const secs = Math.max(0, Math.floor((Date.now() - dayjs(task.started_at).valueOf()) / 1000));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return <span className="ws-rail-elapsed">{`已耗时 ${m}m${String(s).padStart(2, '0')}s`}</span>;
}

export interface SceneTaskRailProps {
  tasks: any[];
  interventions: any[];
  activeTaskId?: number | null;
  disabled?: boolean;
  playbooks?: { playbook_id: number; playbook_name: string }[];
  onPreview: (item: any, kind: 'task' | 'intervention') => void;
  onEnterConversation: (taskId: number) => void;
}

export function SceneTaskRail({
  tasks,
  interventions,
  activeTaskId,
  disabled,
  playbooks,
  onPreview,
  onEnterConversation,
}: SceneTaskRailProps) {
  const [filter, setFilter] = useState('');
  const [tab, setTab] = useState<TaskTabKey>('all');

  const pbNameById = useMemo(() => {
    const m = new Map<number, string>();
    (playbooks || []).forEach((p) => m.set(p.playbook_id, p.playbook_name));
    return m;
  }, [playbooks]);

  const taskItems = useMemo(
    () => (tasks || []).map((t) => ({
      kind: 'task' as const,
      raw: t,
      updatedAt: t.gmt_modified || t.gmt_created || t.updated_at || new Date().toISOString(),
    })),
    [tasks],
  );
  const intItems = useMemo(
    () => (interventions || []).map((i) => ({
      kind: 'intervention' as const,
      raw: i,
      updatedAt: i.updated_at || i.created_at || new Date().toISOString(),
    })),
    [interventions],
  );
  const merged = useMemo(
    () => [...taskItems, ...intItems].sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
    ),
    [taskItems, intItems],
  );

  const counts = useMemo(() => {
    const c: Record<TaskTabKey, number> = { all: merged.length, running: 0, awaiting: 0, done: 0, failed: 0 };
    merged.forEach((it) => {
      if (it.kind === 'task') {
        if (statusToTab(it.raw.status) !== 'all') c[statusToTab(it.raw.status)] += 1;
      } else {
        c.awaiting += 1;
      }
    });
    return c;
  }, [merged]);

  const activeCount = counts.running + counts.awaiting;

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return merged.filter((it) => {
      if (it.kind === 'task') {
        if (tab !== 'all' && statusToTab(it.raw.status) !== tab) return false;
      } else {
        if (tab !== 'all' && tab !== 'awaiting') return false;
      }
      if (!q) return true;
      const t = (it.kind === 'task' ? it.raw.title : it.raw.question?.title) || `it_${it.raw.id}`;
      return t.toLowerCase().includes(q) || String(it.raw.id).includes(q);
    });
  }, [merged, tab, filter]);

  return (
    <div className="ws-scene-task-rail">
      <div className="ws-scene-task-rail__header">
        <div className="ws-rail-h-top">
          <span className="ws-rail-title">任务与介入</span>
          <span className="ws-rail-count">{`${counts.all}${activeCount ? ` · 运行中 ${activeCount}` : ''}`}</span>
        </div>
        <div className="ws-rail-tabs">
          {(Object.keys(TAB_LABEL) as TaskTabKey[]).map((k) => (
            <div
              key={k}
              className={`ws-rail-tab ${TAB_CLASS[k]}${tab === k ? ' ws-rail-tab--on' : ''}`}
              role="button"
              tabIndex={0}
              onClick={() => setTab(k)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTab(k); } }}
            >
              {TAB_LABEL[k]}
              <span className={`ws-rail-bd${counts[k] === 0 ? ' ws-rail-bd--zero' : ''}`}>{counts[k]}</span>
            </div>
          ))}
        </div>
      </div>
      <Input
        prefix={<SearchOutlined />}
        placeholder="搜索任务、介入"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="ws-scene-task-rail__search"
      />
      <div className="ws-scene-task-rail__list">
        {filtered.length === 0 && (
          <div className="ws-rail-empty">
            <div className="ws-rail-empty-t">
              {tab === 'failed' ? '没有失败的任务' : tab === 'done' ? '还没有已完成的任务' : tab === 'awaiting' ? '当前没有待介入' : '暂无任务'}
            </div>
            <div className="ws-rail-empty-h">在右侧输入发起任务,选剧本 + 写目标,Agent 会跑起来。</div>
          </div>
        )}
        {filtered.map((it) => {
          const isTask = it.kind === 'task';
          const t = it.raw;
          const pbName = isTask && t.playbook_id ? pbNameById.get(t.playbook_id) : null;
          const isActive = isTask && activeTaskId === t.id;
          return (
            <div
              key={`${it.kind}-${t.id}`}
              className={`ws-rail-card${isActive ? ' ws-rail-card--active' : ''}${!isTask ? ' ws-rail-card--int' : ''}`}
              role={disabled ? undefined : 'button'}
              tabIndex={disabled ? -1 : 0}
              aria-disabled={disabled}
              onClick={() => !disabled && onPreview(t, it.kind)}
              onKeyDown={(e) => { if (!disabled && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onPreview(t, it.kind); } }}
            >
              <div className="ws-rail-card-head">
                <span className={`ws-rail-status ws-rail-status--${t.status || (isTask ? 'draft' : 'requested')}`}>
                  <span className="ws-rail-dot" />
                  {isTask ? statusLabel(t.status) : '待响应'}
                </span>
                {pbName && <span className="ws-rail-pb">📖 {pbName}</span>}
                {isTask && <ElapsedTimer task={t} />}
              </div>
              <div className="ws-rail-ttl">{isTask ? (t.title || `task_${t.id}`) : (t.question?.title || `intervention_${t.id}`)}</div>
              <div className="ws-rail-foot">
                <span className="ws-rail-src">{isTask ? `${t.triggered_by || '手动'} · ${t.type || 'adhoc'}` : '人工 · 介入'}</span>
                <span className="ws-rail-tm">{dayjs(it.updatedAt).format('MM-DD HH:mm')}</span>
                {isTask && (
                  <span
                    className="ws-rail-enter"
                    role="button"
                    tabIndex={disabled ? -1 : 0}
                    onClick={(e) => { e.stopPropagation(); if (!disabled) onEnterConversation(t.id); }}
                    onKeyDown={(e) => { if (!disabled && e.key === 'Enter') { e.preventDefault(); onEnterConversation(t.id); } }}
                  >
                    进入对话 →
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && npx tsc --noEmit -p tsconfig.json`
Expected: tsc 通过。`statusToTab`/`statusLabel` 的纯函数 case 全过。

- [ ] **Step 5: 追加方向 B 卡片样式到 `scene-workspace.css`**

在 `scene-workspace.css` 末尾追加(Task 5 会改 shell 与轮询,这里先把卡片样式备好):

```css
/* === scene-task-rail: 方向 B 分层呼吸卡 === */
.ws-scene-task-rail__header { padding: 12px 14px 10px; border-bottom: 1px solid var(--ws-border); }
.ws-rail-h-top { display: flex; align-items: baseline; justify-content: space-between; }
.ws-rail-title { font-size: 13.5px; font-weight: 700; color: var(--ws-ink); }
.ws-rail-count { font-size: 11px; color: var(--ws-ink-3); font-family: var(--ws-mono); }

.ws-rail-tabs { display: flex; gap: 4px; margin-top: 10px; overflow-x: auto; padding-bottom: 2px; }
.ws-rail-tab {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11.5px; font-weight: 500; color: var(--ws-ink-2);
  padding: 4px 9px; border-radius: 999px; white-space: nowrap; cursor: pointer;
  border: 1px solid transparent; transition: all .15s; flex-shrink: 0;
}
.ws-rail-tab:hover { background: var(--ws-bg); color: var(--ws-ink); }
.ws-rail-tab--on { background: var(--ws-accent-light); color: var(--ws-accent); border-color: rgba(var(--ws-accent-rgb), .22); font-weight: 600; }
.ws-rail-bd {
  font-size: 10px; font-weight: 600; min-width: 16px; text-align: center;
  padding: 0 5px; border-radius: 999px; background: rgba(100,116,139,.14); color: var(--ws-ink-2);
}
.ws-rail-tab--on .ws-rail-bd { background: var(--ws-accent); color: #fff; }
.ws-rail-bd--zero { opacity: .45; }

.ws-scene-task-rail__search { margin: 10px 12px 8px; }
.ws-scene-task-rail__list { flex: 1; overflow-y: auto; padding: 0 12px 12px; }
.ws-scene-task-rail__list::-webkit-scrollbar { width: 5px; }
.ws-scene-task-rail__list::-webkit-scrollbar-thumb { background: var(--ws-border); border-radius: 4px; }

.ws-rail-empty { padding: 40px 16px; text-align: center; color: var(--ws-ink-3); }
.ws-rail-empty-t { font-size: 12.5px; font-weight: 600; color: var(--ws-ink-2); margin-bottom: 3px; }
.ws-rail-empty-h { font-size: 11px; color: var(--ws-ink-3); line-height: 1.5; }

.ws-rail-card {
  background: var(--ws-surface); border: 1px solid var(--ws-border);
  border-radius: 10px; margin-bottom: 8px; cursor: pointer; transition: all .18s;
}
.ws-rail-card:hover { border-color: var(--ws-accent); box-shadow: 0 3px 10px rgba(var(--ws-accent-rgb), .1); }
.ws-rail-card--active { border-color: var(--ws-accent); box-shadow: 0 0 0 2px rgba(var(--ws-accent-rgb), .2); }
.ws-rail-card--int { background: var(--ws-attention-light); border-color: rgba(var(--ws-attention-rgb), .3); }

.ws-rail-card-head { display: flex; align-items: center; gap: 7px; padding: 9px 12px 0; }
.ws-rail-status { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600; }
.ws-rail-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; flex-shrink: 0; background: var(--ws-ink-3); }
.ws-rail-status--running { color: var(--ws-accent); }
.ws-rail-status--running .ws-rail-dot { background: var(--ws-accent); box-shadow: 0 0 0 3px rgba(var(--ws-accent-rgb), .14); animation: ws-rail-pulse 1.6s ease-in-out infinite; }
@keyframes ws-rail-pulse { 50% { box-shadow: 0 0 0 5px rgba(var(--ws-accent-rgb), .05); } }
.ws-rail-status--awaiting_human, .ws-rail-status--pending_trigger { color: var(--ws-attention); }
.ws-rail-status--awaiting_human .ws-rail-dot, .ws-rail-status--pending_trigger .ws-rail-dot { background: var(--ws-attention); box-shadow: 0 0 0 3px rgba(var(--ws-attention-rgb), .14); }
.ws-rail-status--delivered, .ws-rail-status--closed { color: var(--ws-success); }
.ws-rail-status--delivered .ws-rail-dot, .ws-rail-status--closed .ws-rail-dot { background: var(--ws-success); }
.ws-rail-status--failed, .ws-rail-status--blocked { color: var(--ws-danger); }
.ws-rail-status--failed .ws-rail-dot, .ws-rail-status--blocked .ws-rail-dot { background: var(--ws-danger); }
.ws-rail-status--draft { color: var(--ws-ink-3); }

.ws-rail-pb {
  display: inline-flex; align-items: center; font-size: 10px; font-weight: 500;
  color: var(--ws-accent); background: var(--ws-accent-light);
  border: 1px solid rgba(var(--ws-accent-rgb), .2);
  padding: 2px 7px; border-radius: 999px; max-width: 120px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ws-rail-elapsed { margin-left: auto; font-size: 10px; color: var(--ws-ink-3); font-family: var(--ws-mono); white-space: nowrap; flex-shrink: 0; }

.ws-rail-ttl { font-size: 13px; font-weight: 600; color: var(--ws-ink); padding: 6px 12px 0; line-height: 1.38; }
.ws-rail-foot {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px 9px; margin-top: 7px;
  border-top: 1px solid var(--ws-border-subtle); font-size: 10px; color: var(--ws-ink-2);
}
.ws-rail-src { color: var(--ws-ink-2); }
.ws-rail-tm { color: var(--ws-ink-3); font-family: var(--ws-mono); font-size: 9.5px; }
.ws-rail-enter { margin-left: auto; color: var(--ws-accent); font-weight: 600; font-size: 10.5px; cursor: pointer; }
.ws-rail-card:hover .ws-rail-enter { text-decoration: underline; }
```

- [ ] **Step 6: 提交**

```bash
git add web/src/app/workspaces/detail/scene-task-rail.tsx web/src/app/workspaces/detail/scene-task-rail.test.ts web/src/app/workspaces/detail/scene-workspace.css
git commit -m "feat(web): redesign scene-task-rail — tab filter + layered info card

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 前端 — `scene-workspace-shell` 透传 playbooks + 4s 运行时轮询

**Files:**
- Modify: `web/src/app/workspaces/detail/scene-workspace-shell.tsx`

**Interfaces:**
- Consumes: Task 4 的 `SceneTaskRail` 新 props `playbooks`;现有 `tasks` state、`onRefreshLists` props。
- Produces: shell 把已 fetch 的 `playbooks` 传给 `SceneTaskRail`;新增 `useEffect` 在有活跃任务时 4s 轮询 `onRefreshLists`。

- [ ] **Step 1: 写失败测试**

shell 是组合组件、依赖 ahooks/derisk-app API,纯单测成本高。本任务的逻辑核心是"有活跃任务时起轮询、无则停",抽成一个纯函数测试。

在 `scene-workspace-shell.tsx` 顶部 import 之后加导出:

```ts
/** 判断当前任务列表里是否有活跃任务(running 等会变化的状态),决定是否开轮询。 */
export function hasActiveTask(tasks: any[]): boolean {
  const active = new Set(['running', 'pending_trigger', 'blocked', 'awaiting_human', 'draft']);
  return (tasks || []).some((t) => active.has(t?.status));
}
```

创建 `web/src/app/workspaces/detail/scene-workspace-shell.test.ts`:

```ts
import { hasActiveTask } from './scene-workspace-shell';

describe('hasActiveTask', () => {
  it('returns true when any task is running/awaiting/draft/etc', () => {
    expect(hasActiveTask([{ status: 'running' }])).toBe(true);
    expect(hasActiveTask([{ status: 'awaiting_human' }])).toBe(true);
    expect(hasActiveTask([{ status: 'draft' }])).toBe(true);
    expect(hasActiveTask([{ status: 'delivered' }, { status: 'running' }])).toBe(true);
  });
  it('returns false when all tasks are terminal', () => {
    expect(hasActiveTask([{ status: 'delivered' }])).toBe(false);
    expect(hasActiveTask([{ status: 'closed' }, { status: 'failed' }])).toBe(false);
  });
  it('returns false on empty', () => {
    expect(hasActiveTask([])).toBe(false);
    expect(hasActiveTask(null as any)).toBe(false);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && npx tsc --noEmit -p tsconfig.json`
Expected: tsc 报错 `scene-workspace-shell` 未导出 `hasActiveTask`。

- [ ] **Step 3: 写最小实现**

在 `scene-workspace-shell.tsx` 顶部加 `hasActiveTask` 函数(见 Step 1)。

然后在组件内(现有 `useRequest` 拉取 playbooks 的 hook 下方,`useEffect` 群里)加轮询 `useEffect`:

```tsx
  // 运行时轮询:有活跃任务时每 4s 刷新任务/介入列表,无活跃任务时停。
  // 后台 run_task 的状态变更无法走 workspace 事件流(fire-and-forget,无 SSE 连接),
  // 用轮询替代;task_created 事件触发的 onRefreshLists 仍保留。
  useEffect(() => {
    if (!hasActiveTask(tasks) || !onRefreshLists) return;
    const timer = setInterval(onRefreshLists, 4000);
    return () => clearInterval(timer);
  }, [tasks, onRefreshLists]);
```

然后把 `playbooks` 透传给 `SceneTaskRail`。定位 `<SceneTaskRail ... />`(约 line 161-168),加一行 prop:

```tsx
        <SceneTaskRail
          tasks={tasks}
          interventions={interventions}
          activeTaskId={activeTaskId}
          disabled={switchingTask}
          playbooks={playbooks}
          onPreview={handlePreview}
          onEnterConversation={handleEnterConversation}
        />
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && npx tsc --noEmit -p tsconfig.json`
Expected: tsc 通过。`hasActiveTask` 的纯函数 case 全过。

- [ ] **Step 5: 提交**

```bash
git add web/src/app/workspaces/detail/scene-workspace-shell.tsx web/src/app/workspaces/detail/scene-workspace-shell.test.ts
git commit -m "feat(web): pass playbooks to task rail + 4s active-task polling

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: 验证 — 全链路冒烟

**Files:** 无代码改动,仅运行验证。

- [ ] **Step 1: 后端测试全过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/agent_tools/test_task_creator.py packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py -v`
Expected: PASS(全部)。

- [ ] **Step 2: 前端类型检查全过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && npx tsc --noEmit -p tsconfig.json`
Expected: 无错误。

- [ ] **Step 3: 手动冒烟(需起服务,由用户或 run skill 执行)**

启动 derisk 后端 + web 前端,在场景空间:
1. 不选剧本,直接发文本 → 大厅对话,任务栏不新增任务。
2. 打 `/` 选剧本,不输入文本 → 发送按钮禁用,提示"选了剧本要写本次任务目标"。
3. 打 `/` 选剧本 + 输入"生成本周容量巡检报告" → 发送 → 任务栏立即出现任务(状态准备中/运行中) → ~4s 内状态变 running、显示已耗时、Agent 真的在右侧对话里跑 vis → 跑完状态变 delivered/awaiting_human/failed → 无活跃任务后轮询停。
4. 标题几秒后从"生成本周容量巡检报告"变成 LLM 总结的短标题。
5. 切换 Tab(运行中/待介入/已完成/失败)过滤生效,空 Tab 显示空态。

> 若无法本地起服务,至少完成 Step 1+2,并在 PR 描述里标注 Step 3 待用户验证。

- [ ] **Step 4: 确认改动文件清单**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && git diff --stat main...HEAD -- packages/derisk-serve/src/derisk_serve/workspace/agent_tools/_task_creator.py packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py web/src/app/workspaces/detail/scene-task-rail.tsx web/src/app/workspaces/detail/scene-workspace-shell.tsx web/src/app/workspaces/detail/scene-workspace.css web/src/app/workspaces/detail/agent-workspace-input.tsx`
Expected: 6 文件被改动,无意外文件。

---

## Self-Review

**1. Spec coverage:**
- §3.1 后端真实运行 → Task 1(`create_task_from_tool` detached start+run_task)+ Task 2(透传 model、空文本拒绝)。
- §3.2 LLM 标题总结 → Task 1(`_summarize_task_title` + `_summarize_title_detached`)。
- §3.3 后端数据现实(不改) → 无任务,Global Constraints 已明列不做。
- §3.4 任务栏重做 → Task 4(Tab + 卡片 + 空态 + 剧本本地查名)+ Task 5(透传 playbooks)。
- §3.5 发起校验 → Task 3(前端禁用)+ Task 2(后端拒绝)。
- §3.6 轮询刷新 → Task 5(`hasActiveTask` + 4s `useEffect`)。
覆盖完整。

**2. Placeholder scan:** 无 TBD/TODO。Task 1 测试里的 `created coronas` 已显式标注为笔误、落地改 `created_tasks`,非占位。所有代码块完整。

**3. Type consistency:**
- `create_task_from_tool` 签名加 `model_name` —— Task 2 调用处用 `model_name=_model_name` 一致。
- `statusToTab`/`statusLabel` —— Task 4 定义、Task 4 测试引用,一致。
- `hasActiveTask` —— Task 5 定义、测试引用,一致。
- `TaskTabKey` —— Task 4 定义,内部 `TAB_LABEL`/`TAB_CLASS` 用,一致。
- `canSendSceneTask` —— Task 3 定义、测试引用,一致。
- `_extract_model` —— Task 2 定义、Task 2 测试引用,一致。

无不一致。