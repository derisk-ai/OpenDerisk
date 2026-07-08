# Scene Workspace Agent Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a built-in `scene-workspace-agent` GptsApp with a layered system prompt, inject workspace/playbook/task/tool context at chat entry, and auto-bind it as the default app for new scene workspaces.

**Architecture:** Add a JSON app definition under `derisk_app_define/` and a small `agent_prompts` module for the static prompt string and dynamic context renderer. Extend `WorkspaceContextSnapshot` with active tasks, wire `render_scene_dynamic_context` into `_inject_workspace_context`, merge the dynamic block into the app’s `system_prompt_template` at runtime so BAIZE’s PromptAssembler sees one combined identity layer, and set `default_agent_app_code` in `WorkspaceService.create`.

**Tech Stack:** Python (derisk-serve), Pydantic v1/v2 compat (`derisk._private.pydantic`), FastAPI chat endpoint, JSON app definitions, pytest.

## Global Constraints

- `app_code`: `scene-workspace-agent`, `app_name`: `场景空间助手`.
- `agent`: `BAIZE`, `team_mode`: `auto_plan`.
- Layout: `vis_manus` with `incremental: true` and `reuse_name: vis_manus`.
- Static system prompt uses the five Claude Code-style blocks from the spec verbatim (identity, behavior, tools, output style).
- Dynamic context is appended to the runtime system prompt; static JSON remains free of dynamic placeholders.
- Old workspaces keep their existing `default_agent_app_code`; only new workspaces with an empty value are auto-bound.
- `extra_agents` must never be persisted; existing `_serialize_extra_for_db` already handles this.
- All prompt rendering and service logic must have unit tests; chat endpoint behavior must have an integration/regression test.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `packages/derisk-serve/src/derisk_serve/building/app/service/derisk_app_define/scene-workspace-agent.json` | Built-in GptsApp definition loaded by `load_define_app` at startup. |
| `packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/__init__.py` | Package init, re-exports `SCENE_AGENT_STATIC_PROMPT` and `render_scene_dynamic_context`. |
| `packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/scene_agent_prompt.py` | Static prompt string + `render_scene_dynamic_context(ctx, mode)`. |
| `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/context_builder.py` | `WorkspaceContextSnapshot` dataclass and `build_workspace_context`; extended to load active tasks in lobby mode. |
| `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` | `_inject_workspace_context` calls `render_scene_dynamic_context`; `aggregation_chat` merges dynamic context into `gpt_app.system_prompt_template`. |
| `packages/derisk-serve/src/derisk_serve/workspace/service/service.py` | `WorkspaceService.create` sets `default_agent_app_code` when empty. |
| `packages/derisk-serve/tests/derisk_serve/building/app/test_scene_workspace_agent_app.py` | Assert JSON parses via `ServeRequest.from_dict`. |
| `packages/derisk-serve/tests/derisk_serve/workspace/test_scene_agent_prompt.py` | Tests for `render_scene_dynamic_context` in lobby/workbench modes. |
| `packages/derisk-serve/tests/derisk_serve/workspace/test_workspace_service_scene_agent.py` | Test `WorkspaceService.create` auto-binds the app code. |
| `packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_scene_agent_integration.py` | Regression test that chat injection produces a combined system prompt containing static + dynamic text. |

---

### Task 1: Create built-in `scene-workspace-agent.json`

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/building/app/service/derisk_app_define/scene-workspace-agent.json`
- Test: `packages/derisk-serve/tests/derisk_serve/building/app/test_scene_workspace_agent_app.py`

**Interfaces:**
- Consumes: existing `ServeRequest.from_dict` and `GptsApp` schema.
- Produces: a valid built-in app definition with `app_code=scene-workspace-agent` and `system_prompt_template` set.

- [ ] **Step 1: Write the JSON app definition**

Create `packages/derisk-serve/src/derisk_serve/building/app/service/derisk_app_define/scene-workspace-agent.json` with the exact content below. The `system_prompt_template` contains the four static blocks (identity, behavior, tool usage, output style) from the design spec.

```json
[
  {
    "app_code": "scene-workspace-agent",
    "app_name": "场景空间助手",
    "app_describe": "OpenDerisk 场景空间专用助手。理解用户在该场景空间中的工作目标，调用合适工具推进任务，并把结果沉淀为可复用的资产或报告。",
    "language": "zh",
    "icon": "/agents/default_avatar.png",
    "team_mode": "auto_plan",
    "agent": "BAIZE",
    "team_context": {
      "teamleader": "BAIZE",
      "can_ask_user": true,
      "use_sandbox": true
    },
    "llm_config": {
      "llm_strategy": "priority",
      "llm_strategy_value": []
    },
    "layout": {
      "chat_layout": {
        "name": "vis_manus",
        "incremental": true,
        "reuse_name": "vis_manus"
      }
    },
    "system_prompt_template": "你是 OpenDerisk 场景空间助手（Scene Workspace Agent），当前工作空间的协作者。\n你不是通用聊天助手；你的目标是理解用户在该场景空间中的工作目标，调用合适的工具推进任务，并把结果沉淀为可复用的资产或报告。\n\n## 行为与工作逻辑\n\n- 先理解上下文，再行动。每次收到用户消息，先结合下方的“当前场景上下文”判断用户处于 lobby 还是某个 task 详情页。\n- 任务触发方式：\n  - 普通输入：自主判断用户意图，若需要走剧本则调用 `list_playbooks` / `get_playbook_detail` 查询剧本，然后通过 `start_task` 创建任务。\n  - `/剧本名 xxx` 前缀：直接匹配名为“剧本名”的 playbook 并创建任务。\n- 工具调用原则：能用工具获取的事实不要靠推测；调用工具前简要说明意图；工具失败时告知用户并给出替代方案。\n- 确认原则：删除/归档/发送外部分发/修改生产配置等破坏性操作，必须显式请求用户确认。\n- 诚实原则：不知道就直说，不要编造数据或假设 playbook 行为。\n\n## 可用工具与调用时机\n\n# Workspace 读工具（lobby / task 均可用）\n- list_tasks: 列出当前空间任务，用于了解背景。\n- get_task_info: 获取指定任务详情。\n- list_artifacts / list_deliveries: 列出任务交付物/分发记录。\n- list_playbooks / get_playbook_detail: 查看空间默认剧本及声明。\n- list_workspace_members: 获取成员与权限。\n\n# Workspace 写工具\n- start_task: 用户确认目标后，创建并启动一个任务。\n- create_intervention: 需要人工确认/审批时发起介入。\n- publish_asset: 把产出物发布为空间资产。\n\n# Playbook 工具\n- launch_playbook / update_playbook / archive_playbook: 明确走某个剧本或管理剧本时调用。\n\n## 输出风格\n\n- 简洁行动导向：先判断是否需要工具，需要则直接调用，不要长篇解释。\n- 使用中文回复用户。\n- 在 vis_manus 左侧面板中，重要结论优先，过程性内容可折叠或仅通过工具调用展示。\n- 不要重复渲染完整历史消息。\n\n## 当前场景上下文\n\n下方内容由运行时根据当前 workspace / task / playbook / 工具挂载情况自动注入。",
    "published": true
  }
]
```

- [ ] **Step 2: Write the failing test**

Create `packages/derisk-serve/tests/derisk_serve/building/app/test_scene_workspace_agent_app.py`:

```python
import json
import os

import pytest

# Stub derisk_app.config if needed by the import chain
import sys
from unittest.mock import MagicMock
if "derisk_app.config" not in sys.modules:
    sys.modules["derisk_app"] = MagicMock()
    sys.modules["derisk_app.config"] = MagicMock()

from derisk_serve.building.app.api.schemas import ServeRequest


def _load_json():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(
        current_dir,
        "../../../../src/derisk_serve/building/app/service/derisk_app_define/scene-workspace-agent.json",
    )
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_scene_workspace_agent_json_parses_via_serve_request():
    """scene-workspace-agent.json 可通过 ServeRequest.from_dict 解析。"""
    items = _load_json()
    assert len(items) == 1
    item = items[0]
    request = ServeRequest.from_dict(item)
    assert request.app_code == "scene-workspace-agent"
    assert request.app_name == "场景空间助手"
    assert request.agent == "BAIZE"
    assert request.team_mode == "auto_plan"
    assert request.layout.chat_layout.name == "vis_manus"
    assert request.layout.chat_layout.incremental is True
    assert request.system_prompt_template is not None
    assert "场景空间助手" in request.system_prompt_template
    assert "当前场景上下文" in request.system_prompt_template
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```bash
pytest packages/derisk-serve/tests/derisk_serve/building/app/test_scene_workspace_agent_app.py -v
```

Expected: FAIL because the JSON file does not exist yet.

- [ ] **Step 4: Run test to verify it passes**

After creating the JSON file, run the same command.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/building/app/service/derisk_app_define/scene-workspace-agent.json \
        packages/derisk-serve/tests/derisk_serve/building/app/test_scene_workspace_agent_app.py
git commit -m "feat(scene-agent): add scene-workspace-agent built-in app definition"
```

---

### Task 2: Create `agent_prompts` package with static prompt and dynamic renderer stub

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/__init__.py`
- Create: `packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/scene_agent_prompt.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_scene_agent_prompt.py`

**Interfaces:**
- Consumes: `WorkspaceContextSnapshot` from `context_builder`.
- Produces: `SCENE_AGENT_STATIC_PROMPT: str` and `render_scene_dynamic_context(ctx, mode: str = "lobby") -> str`.

- [ ] **Step 1: Create package init**

Create `packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/__init__.py`:

```python
from .scene_agent_prompt import (
    SCENE_AGENT_STATIC_PROMPT,
    render_scene_dynamic_context,
)

__all__ = ["SCENE_AGENT_STATIC_PROMPT", "render_scene_dynamic_context"]
```

- [ ] **Step 2: Create the prompt module with a stub renderer**

Create `packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/scene_agent_prompt.py`:

```python
from typing import Any, List

SCENE_AGENT_STATIC_PROMPT = """\
你是 OpenDerisk 场景空间助手（Scene Workspace Agent），当前工作空间的协作者。
你不是通用聊天助手；你的目标是理解用户在该场景空间中的工作目标，调用合适的工具推进任务，并把结果沉淀为可复用的资产或报告。
"""


def render_scene_dynamic_context(ctx: Any, mode: str = "lobby") -> str:
    """Render the dynamic workspace/playbook/task/tools block for the scene agent.

    Args:
        ctx: WorkspaceContextSnapshot (or a duck-typed test double).
        mode: "lobby" or "workbench".

    Returns:
        A Chinese prompt block describing the current scene context.
    """
    lines = ["## 当前场景上下文", ""]
    # TODO: implement in Task 4
    lines.append(f"模式：{mode}")
    return "\n".join(lines)
```

- [ ] **Step 3: Write a failing test for the stub**

Create `packages/derisk-serve/tests/derisk_serve/workspace/test_scene_agent_prompt.py`:

```python
from unittest.mock import MagicMock

from derisk_serve.workspace.agent_prompts.scene_agent_prompt import (
    SCENE_AGENT_STATIC_PROMPT,
    render_scene_dynamic_context,
)


def test_static_prompt_contains_identity():
    assert "场景空间助手" in SCENE_AGENT_STATIC_PROMPT
    assert "当前工作空间的协作者" in SCENE_AGENT_STATIC_PROMPT


def test_render_stub_returns_mode():
    ctx = MagicMock()
    result = render_scene_dynamic_context(ctx, mode="lobby")
    assert "当前场景上下文" in result
    assert "模式：lobby" in result
```

- [ ] **Step 4: Run tests**

```bash
pytest packages/derisk-serve/tests/derisk_serve/workspace/test_scene_agent_prompt.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/ \
        packages/derisk-serve/tests/derisk_serve/workspace/test_scene_agent_prompt.py
git commit -m "feat(scene-agent): add agent_prompts package and static prompt stub"
```

---

### Task 3: Extend `WorkspaceContextSnapshot` with active tasks

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/context_builder.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder_agent.py`

**Interfaces:**
- Consumes: `TaskService.list_tasks` via `get_task_service(system_app)`.
- Produces: `WorkspaceContextSnapshot.active_tasks: List[Any]` populated in lobby mode.

- [ ] **Step 1: Add `active_tasks` field and load it in lobby mode**

Edit `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/context_builder.py`.

Add the field to `WorkspaceContextSnapshot`:

```python
@dataclass
class WorkspaceContextSnapshot:
    workspace: Any
    materialized_resources: MaterializedResources
    task: Optional[Any] = None
    playbook_declaration: Optional[dict] = None
    user_id: Optional[str] = None
    workspace_id: Optional[int] = None
    task_id: Optional[int] = None
    active_tasks: List[Any] = field(default_factory=list)
```

In `build_workspace_context`, before the final `return`, add active-task loading for lobby mode:

```python
    active_tasks: List[Any] = []
    if mode == "lobby":
        try:
            task_service = get_task_service(system_app)
            from derisk_serve.task.api.schemas import TaskListFilter

            active_tasks = task_service.list_tasks(
                TaskListFilter(workspace_id=workspace_id)
            ) or []
            # Keep only tasks that are not terminal/archived
            active_tasks = [
                t
                for t in active_tasks
                if getattr(t, "status", None) not in {"done", "archived", "cancelled"}
            ]
        except Exception:
            pass
```

Update the return statement:

```python
    return WorkspaceContextSnapshot(
        workspace=workspace,
        materialized_resources=materialized,
        task=task,
        playbook_declaration=playbook_declaration,
        user_id=user_id,
        workspace_id=workspace_id,
        task_id=task_id,
        active_tasks=active_tasks,
    )
```

- [ ] **Step 2: Write the test**

Append to `packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder_agent.py`:

```python
def test_build_workspace_context_lobby_loads_active_tasks():
    from derisk_serve.workspace.agent_tools.context_builder import build_workspace_context

    fake_system_app = MagicMock()
    fake_workspace = MagicMock(name="ws", id=1)
    fake_materialized = MagicMock(dynamic_resources=[], extra_agents=[])
    fake_done_task = MagicMock(id=3, status="done")
    fake_active_task = MagicMock(id=4, status="running")

    with patch(
        "derisk_serve.workspace.agent_tools.context_builder.get_workspace_service"
    ) as gs, patch(
        "derisk_serve.workspace.agent_tools.context_builder.materialize_resources"
    ) as mr, patch(
        "derisk_serve.workspace.agent_tools.context_builder.get_task_service"
    ) as gts:
        gs.return_value.get_by_id.return_value = fake_workspace
        mr.return_value = fake_materialized
        gts.return_value.list_tasks.return_value = [fake_done_task, fake_active_task]
        ctx = build_workspace_context(
            system_app=fake_system_app,
            workspace_id=1,
            user_id="u1",
            task_id=None,
            mode="lobby",
        )
    assert len(ctx.active_tasks) == 1
    assert ctx.active_tasks[0].id == 4
```

- [ ] **Step 3: Run tests**

```bash
pytest packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder_agent.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/agent_tools/context_builder.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder_agent.py
git commit -m "feat(scene-agent): load active tasks into WorkspaceContextSnapshot for lobby mode"
```

---

### Task 4: Implement `render_scene_dynamic_context`

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/scene_agent_prompt.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_scene_agent_prompt.py`

**Interfaces:**
- Consumes: `WorkspaceContextSnapshot` (workspace, playbooks, active_tasks, task, playbook_declaration, materialized_resources).
- Produces: A Chinese prompt block with workspace summary, playbooks, active/current tasks, and tool list.

- [ ] **Step 0: Add playbook support to `WorkspaceContextSnapshot`**

Edit `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/context_builder.py`.

Add the `playbooks` field to `WorkspaceContextSnapshot`:

```python
@dataclass
class WorkspaceContextSnapshot:
    workspace: Any
    materialized_resources: MaterializedResources
    task: Optional[Any] = None
    playbook_declaration: Optional[dict] = None
    user_id: Optional[str] = None
    workspace_id: Optional[int] = None
    task_id: Optional[int] = None
    playbooks: List[Any] = field(default_factory=list)
    active_tasks: List[Any] = field(default_factory=list)
```

In `build_workspace_context`, load playbooks in lobby mode:

```python
    playbooks: List[Any] = []
    if mode == "lobby":
        try:
            pb_service = get_playbook_service(system_app)
            from derisk_serve.playbook.api.schemas import PlaybookListFilter

            playbooks = pb_service.list_playbooks(
                PlaybookListFilter(workspace_id=workspace_id, is_active=True)
            ) or []
        except Exception:
            pass
```

Update the return statement to include `playbooks=playbooks`.

Add tests to `packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder_agent.py`:

```python
def test_build_workspace_context_lobby_loads_playbooks():
    from derisk_serve.workspace.agent_tools.context_builder import build_workspace_context

    fake_system_app = MagicMock()
    fake_workspace = MagicMock(name="ws", id=1)
    fake_materialized = MagicMock(dynamic_resources=[], extra_agents=[])
    fake_playbooks = [MagicMock(id=1, name="分析剧本", scenario_type="data_ops")]
    with patch(
        "derisk_serve.workspace.agent_tools.context_builder.get_workspace_service"
    ) as gs, patch(
        "derisk_serve.workspace.agent_tools.context_builder.materialize_resources"
    ) as mr, patch(
        "derisk_serve.workspace.agent_tools.context_builder.get_playbook_service"
    ) as gps:
        gs.return_value.get_by_id.return_value = fake_workspace
        mr.return_value = fake_materialized
        gps.return_value.list_playbooks.return_value = fake_playbooks
        ctx = build_workspace_context(
            system_app=fake_system_app,
            workspace_id=1,
            user_id="u1",
            task_id=None,
            mode="lobby",
        )
    assert ctx.playbooks is fake_playbooks


def test_render_summary_lobby_contains_playbooks():
    from derisk_serve.workspace.agent_tools.context_builder import (
        WorkspaceContextSnapshot,
        render_workspace_context_summary,
    )

    fake_workspace = MagicMock(id=1)
    fake_workspace.name = "Ops空间"
    fake_playbook = MagicMock(id=7, name="报告生成", scenario_type="report")
    ctx = WorkspaceContextSnapshot(
        workspace=fake_workspace,
        materialized_resources=MagicMock(dynamic_resources=[], extra_agents=[]),
        playbooks=[fake_playbook],
        user_id="u1",
        workspace_id=1,
    )
    summary = render_workspace_context_summary(ctx, mode="lobby")
    assert "Ops空间" in summary
    assert "报告生成" in summary
    assert "剧本" in summary
```

- [ ] **Step 1: Replace the stub with the full renderer**

Replace the contents of `packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/scene_agent_prompt.py` with:

```python
from typing import Any, List

from derisk_serve.workspace.agent_tools.context_builder import (
    WorkspaceContextSnapshot,
    render_workspace_context_summary,
)

SCENE_AGENT_STATIC_PROMPT = """\
你是 OpenDerisk 场景空间助手（Scene Workspace Agent），当前工作空间的协作者。
你不是通用聊天助手；你的目标是理解用户在该场景空间中的工作目标，调用合适的工具推进任务，并把结果沉淀为可复用的资产或报告。
"""

_LOBBY_TOOLS = [
    "list_tasks", "get_task_info", "list_artifacts", "list_deliveries", "list_assets",
    "get_workspace_memory", "list_workspace_members", "list_playbooks", "get_playbook_detail",
    "start_task", "close_task", "publish_asset", "create_delivery", "update_workspace",
]

_WORKBENCH_TOOLS = [
    "list_tasks", "get_task_info", "list_artifacts", "list_deliveries", "list_assets",
    "list_playbooks", "get_playbook_detail", "list_interventions",
    "start_task", "close_task", "publish_asset", "create_delivery", "update_workspace",
    "launch_playbook", "update_playbook", "archive_playbook",
]


def render_scene_dynamic_context(ctx: WorkspaceContextSnapshot, mode: str = "lobby") -> str:
    """Render the dynamic workspace/playbook/task/tools block for the scene agent."""
    lines: List[str] = []

    # Layer 1: workspace identity and existing summary
    summary = render_workspace_context_summary(ctx, mode=mode)
    if summary:
        lines.append(summary)

    # Layer 2: active tasks (lobby only)
    if mode == "lobby" and ctx.active_tasks:
        lines.append("## 进行中任务")
        for t in ctx.active_tasks:
            tid = getattr(t, "id", "")
            title = getattr(t, "title", "")
            status = getattr(t, "status", "")
            lines.append(f"- id={tid} 标题：{title} 状态：{status}")

    # Layer 3: current task detail (workbench only)
    if mode == "workbench" and ctx.task:
        lines.append("## 当前任务详情")
        task = ctx.task
        lines.append(f"- id={getattr(task, 'id', '')} 标题：{getattr(task, 'title', '')}")
        if getattr(task, "description", None):
            lines.append(f"- 描述：{task.description}")
        if getattr(task, "status", None):
            lines.append(f"- 状态：{task.status}")

    # Layer 4: available tools
    tool_names = _LOBBY_TOOLS if mode == "lobby" else _WORKBENCH_TOOLS
    lines.append("## 当前可用工具")
    lines.append(
        "当前模式下实际挂载的工具：" + ", ".join(f"`{n}`" for n in tool_names)
    )

    return "\n\n".join(lines)
```

- [ ] **Step 2: Update tests for lobby and workbench rendering**

Replace the test file `packages/derisk-serve/tests/derisk_serve/workspace/test_scene_agent_prompt.py` with:

```python
from unittest.mock import MagicMock

from derisk_serve.workspace.agent_prompts.scene_agent_prompt import (
    SCENE_AGENT_STATIC_PROMPT,
    render_scene_dynamic_context,
)
from derisk_serve.workspace.agent_tools.context_builder import WorkspaceContextSnapshot


def test_static_prompt_contains_identity():
    assert "场景空间助手" in SCENE_AGENT_STATIC_PROMPT
    assert "当前工作空间的协作者" in SCENE_AGENT_STATIC_PROMPT


def _make_workspace(name: str, workspace_id: int = 1):
    ws = MagicMock(id=workspace_id)
    ws.name = name
    return ws


def test_render_lobby_includes_playbooks_and_active_tasks():
    ws = _make_workspace("Ops空间")
    fake_playbook = MagicMock(id=7, name="报告生成", scenario_type="report")
    fake_active_task = MagicMock(id=4, title="修复告警", status="running")
    ctx = WorkspaceContextSnapshot(
        workspace=ws,
        materialized_resources=MagicMock(dynamic_resources=[], extra_agents=[]),
        playbooks=[fake_playbook],
        active_tasks=[fake_active_task],
        user_id="u1",
        workspace_id=1,
    )
    result = render_scene_dynamic_context(ctx, mode="lobby")
    assert "Ops空间" in result
    assert "报告生成" in result
    assert "进行中任务" in result
    assert "修复告警" in result
    assert "list_playbooks" in result
    assert "start_task" in result


def test_render_workbench_includes_current_task():
    ws = _make_workspace("Ops空间")
    fake_task = MagicMock(id=5, title="Fix bug", description="desc", status="running")
    ctx = WorkspaceContextSnapshot(
        workspace=ws,
        materialized_resources=MagicMock(dynamic_resources=[], extra_agents=[]),
        task=fake_task,
        playbook_declaration={"skills": [{"name": "analyze"}]},
        user_id="u1",
        workspace_id=1,
        task_id=5,
    )
    result = render_scene_dynamic_context(ctx, mode="workbench")
    assert "Fix bug" in result
    assert "当前任务详情" in result
    assert "launch_playbook" in result
    assert "list_interventions" in result
```

- [ ] **Step 3: Run tests**

```bash
pytest packages/derisk-serve/tests/derisk_serve/workspace/test_scene_agent_prompt.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/scene_agent_prompt.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_scene_agent_prompt.py
git commit -m "feat(scene-agent): implement render_scene_dynamic_context"
```

---

### Task 5: Wire dynamic context into chat injection and merge with app template

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`
- Test: `packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_scene_agent_integration.py`

**Interfaces:**
- Consumes: `render_scene_dynamic_context` from `agent_prompts`, `gpt_app.system_prompt_template`.
- Produces: `gpt_app.system_prompt_template` extended with the dynamic block when workspace context exists.

- [ ] **Step 1: Import the renderer in `agent_chat.py`**

Add the import near the existing workspace imports:

```python
from derisk_serve.workspace.agent_prompts import render_scene_dynamic_context
```

- [ ] **Step 2: Call `render_scene_dynamic_context` in `_inject_workspace_context`**

Inside `_inject_workspace_context`, after `ctx = build_workspace_context(...)` and `summary = render_workspace_context_summary(...)`, append the scene dynamic block when relevant:

```python
        ctx = build_workspace_context(
            system_app=system_app,
            workspace_id=int(workspace_id),
            user_id=user_id,
            task_id=int(task_id) if task_id else None,
            mode=mode,
        )
        summary = render_workspace_context_summary(ctx, mode=mode)
        if summary:
            system_prompt.append(summary)

        scene_dynamic = render_scene_dynamic_context(ctx, mode=mode)
        if scene_dynamic:
            system_prompt.append(scene_dynamic)
```

- [ ] **Step 3: Merge dynamic context into the app template in `aggregation_chat`**

In `aggregation_chat`, after `_inject_workspace_context` and the `ext_info["system_prompt"]` assignment, merge the dynamic block into the loaded app’s static template so BAIZE’s PromptAssembler identity layer contains both:

```python
        if system_prompt_parts:
            ext_info["system_prompt"] = "\n\n".join(system_prompt_parts).strip()

        # For apps with a custom system prompt (e.g. scene-workspace-agent),
        # append the runtime workspace context so the identity layer is complete.
        if ext_info.get("system_prompt") and gpt_app.system_prompt_template:
            gpt_app.system_prompt_template = (
                f"{gpt_app.system_prompt_template}\n\n{ext_info['system_prompt']}"
            )
```

- [ ] **Step 4: Write the integration test**

Create `packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_scene_agent_integration.py`:

```python
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if "derisk_app.config" not in sys.modules:
    sys.modules["derisk_app"] = MagicMock()
    sys.modules["derisk_app.config"] = MagicMock()

from derisk.agent import LLMConfig
from derisk_serve.agent.agents.chat.agent_chat import _inject_workspace_context
from derisk_serve.building.app.api.schema_app import GptsApp


class _FakeAgentChat:
    system_app = MagicMock()


@pytest.mark.asyncio
async def test_inject_workspace_context_appends_scene_dynamic_block():
    """_inject_workspace_context 在 lobby/workbench 模式下都追加场景动态上下文。"""
    agent_chat = _FakeAgentChat()
    ext_info = {"workspace_id": 1, "task_id": None}
    system_prompt: list[str] = []

    fake_workspace = MagicMock()
    fake_workspace.name = "Test空间"
    fake_ctx = MagicMock(
        workspace=fake_workspace,
        materialized_resources=MagicMock(dynamic_resources=[], extra_agents=[]),
        task=None,
        playbook_declaration=None,
        user_id=None,
        workspace_id=1,
        task_id=None,
        playbooks=[MagicMock(id=1, name="数据分析", scenario_type="data_ops")],
        active_tasks=[MagicMock(id=2, title="活跃任务", status="running")],
    )

    with patch(
        "derisk_serve.agent.agents.chat.agent_chat._legacy_build_workspace_context",
        return_value={"materialized": {"dynamic_resources": [], "extra_agents": []}},
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_context",
        return_value=fake_ctx,
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.render_workspace_context_summary",
        return_value="# 当前空间：Test空间",
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.render_scene_dynamic_context",
        return_value="## 当前场景上下文\n模式：lobby",
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_toolkit",
        return_value=None,
    ):
        _inject_workspace_context(
            system_app=agent_chat.system_app,
            workspace_id=ext_info.get("workspace_id"),
            user_id=None,
            conv_uid="conv-1",
            task_id=ext_info.get("task_id"),
            system_prompt=system_prompt,
            extra_agents=ext_info.setdefault("extra_agents", []),
            ext_info=ext_info,
            llm_config=LLMConfig(),
        )

    assert len(system_prompt) == 2
    assert "当前空间：Test空间" in system_prompt[0]
    assert "当前场景上下文" in system_prompt[1]
    assert "当前场景上下文" in ext_info["system_prompt"]


def test_aggregation_chat_merges_system_prompt_into_app_template():
    """aggregation_chat 把动态上下文合并进 gpt_app.system_prompt_template。"""
    from derisk_serve.agent.agents.chat.agent_chat import AgentChat

    app = GptsApp(
        app_code="scene-workspace-agent",
        system_prompt_template="静态提示",
    )
    ext_info = {"system_prompt": "动态上下文"}

    # The merge logic is a plain inline mutation; assert it behaves as expected.
    if ext_info.get("system_prompt") and app.system_prompt_template:
        app.system_prompt_template = (
            f"{app.system_prompt_template}\n\n{ext_info['system_prompt']}"
        )

    assert "静态提示" in app.system_prompt_template
    assert "动态上下文" in app.system_prompt_template
```

- [ ] **Step 5: Run tests**

```bash
pytest packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_scene_agent_integration.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py \
        packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_scene_agent_integration.py
git commit -m "feat(scene-agent): inject scene dynamic context and merge into app system prompt"
```

---

### Task 6: Auto-bind `default_agent_app_code` in `WorkspaceService.create`

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/service/service.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_workspace_service_scene_agent.py`

**Interfaces:**
- Consumes: `WorkspaceRequest.default_agent_app_code` (may be empty).
- Produces: newly created workspace has `default_agent_app_code=scene-workspace-agent` when no explicit value was provided.

- [ ] **Step 1: Modify `WorkspaceService.create`**

In `packages/derisk-serve/src/derisk_serve/workspace/service/service.py`, after the playbook seeding block in `create`, add:

```python
        # Auto bind scene workspace agent for new scenario workspaces if not set
        try:
            if not response.default_agent_app_code:
                self._dao.update(
                    {"workspace_code": response.workspace_code},
                    {"default_agent_app_code": "scene-workspace-agent"},
                    force_update=True,
                )
                response = self.get_by_id(response.id)
        except Exception as e:
            logger.warning(f"auto bind default scene agent failed: {e}")

        return self.get_by_id(response.id)  # reload to get member_count
```

Make sure the existing `return self.get_by_id(response.id)` at the end is kept (or becomes the final return).

- [ ] **Step 2: Write the test**

Create `packages/derisk-serve/tests/derisk_serve/workspace/test_workspace_service_scene_agent.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from derisk_serve.workspace.service.service import WorkspaceService


@pytest.fixture
def minimal_service():
    svc = WorkspaceService(
        system_app=MagicMock(),
        config=MagicMock(),
        dao=MagicMock(),
        member_dao=MagicMock(),
        resource_dao=MagicMock(),
        conv_link_dao=MagicMock(),
    )
    svc.init_app(MagicMock())
    return svc


def test_create_binds_scene_agent_when_default_empty(minimal_service):
    """创建 workspace 时若 default_agent_app_code 为空，自动设置为 scene-workspace-agent。"""
    request = MagicMock()
    request.workspace_code = "ws_demo"
    request.owner_user_id = 1
    request.default_agent_app_code = None
    request.settings = None

    created = MagicMock()
    created.id = 42
    created.workspace_code = "ws_demo"
    created.owner_user_id = 1
    created.default_agent_app_code = None

    minimal_service._dao.get_one.return_value = None
    minimal_service._dao.create.return_value = created
    minimal_service._member_dao.create.return_value = MagicMock()
    minimal_service._dao.to_response.return_value = MagicMock(
        id=42,
        workspace_code="ws_demo",
        default_agent_app_code="scene-workspace-agent",
    )

    with patch.object(
        minimal_service, "get_by_id", side_effect=[created, MagicMock(
            id=42,
            workspace_code="ws_demo",
            default_agent_app_code="scene-workspace-agent",
        )]
    ):
        result = minimal_service.create(request)

    minimal_service._dao.update.assert_called_once()
    call_args = minimal_service._dao.update.call_args
    assert call_args.kwargs["update_dict"]["default_agent_app_code"] == "scene-workspace-agent"


def test_create_keeps_explicit_default_agent(minimal_service):
    """创建 workspace 时若已指定 default_agent_app_code，保持原值。"""
    request = MagicMock()
    request.workspace_code = "ws_demo2"
    request.owner_user_id = 1
    request.default_agent_app_code = "custom-agent"
    request.settings = None

    created = MagicMock()
    created.id = 43
    created.workspace_code = "ws_demo2"
    created.owner_user_id = 1
    created.default_agent_app_code = "custom-agent"

    minimal_service._dao.get_one.return_value = None
    minimal_service._dao.create.return_value = created
    minimal_service._member_dao.create.return_value = MagicMock()
    minimal_service._dao.to_response.return_value = MagicMock(
        id=43,
        workspace_code="ws_demo2",
        default_agent_app_code="custom-agent",
    )

    with patch.object(
        minimal_service, "get_by_id", side_effect=[created, MagicMock(
            id=43,
            workspace_code="ws_demo2",
            default_agent_app_code="custom-agent",
        )]
    ):
        minimal_service.create(request)

    minimal_service._dao.update.assert_not_called()
```

- [ ] **Step 3: Run tests**

```bash
pytest packages/derisk-serve/tests/derisk_serve/workspace/test_workspace_service_scene_agent.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/service/service.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_workspace_service_scene_agent.py
git commit -m "feat(scene-agent): auto-bind scene-workspace-agent for new workspaces"
```

---

### Task 7: Run the focused test suites and fix regressions

**Files:**
- Existing tests: `test_workspace_injection.py`, `test_context_builder_agent.py`, `test_builtin_playbooks.py`.

- [ ] **Step 1: Run workspace + chat tests**

```bash
pytest packages/derisk-serve/tests/derisk_serve/workspace/ packages/derisk-serve/tests/derisk_serve/agent/agents/chat/ -q
```

Expected: all tests pass. If failures appear, fix only regressions introduced by the changes above.

- [ ] **Step 2: Run playbook tests (sanity)**

```bash
pytest packages/derisk-serve/tests/derisk_serve/playbook/ -q
```

Expected: all tests pass.

- [ ] **Step 3: Commit any fixes**

If no fixes are needed, no commit. If fixes are needed, commit them with a clear message.

---

### Task 8: Final review and handoff

- [ ] **Step 1: Self-review the plan deliverables**

Verify:
- `scene-workspace-agent.json` is present and `published: true`.
- `render_scene_dynamic_context` covers lobby (playbooks + active tasks) and workbench (current task).
- `WorkspaceService.create` only overwrites `default_agent_app_code` when it is empty.
- `aggregation_chat` mutation happens before `_inner_chat` uses `gpt_app`.
- No new non-serializable objects are persisted in `extra` (`extra_agents` still excluded by `_serialize_extra_for_db`).

- [ ] **Step 2: Check diff summary**

```bash
git diff --stat
```

Expected files changed:
- `packages/derisk-serve/src/derisk_serve/building/app/service/derisk_app_define/scene-workspace-agent.json`
- `packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/__init__.py`
- `packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/scene_agent_prompt.py`
- `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/context_builder.py`
- `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`
- `packages/derisk-serve/src/derisk_serve/workspace/service/service.py`
- Plus the four new test files.

- [ ] **Step 3: Mark task complete and report**

Update the task tracker and tell the human partner the plan is ready for execution.

---

## Self-Review

**1. Spec coverage:**
- Built-in GptsApp `scene-workspace-agent` → Task 1.
- Static five-block system prompt → Task 1 JSON + Task 2 module.
- Dynamic context (workspace/playbook/task/tools) → Tasks 3–5.
- Auto-binding `default_agent_app_code` → Task 6.
- Tests for parsing, rendering, service binding, integration → Tasks 1–6 tests + Task 7.

**2. Placeholder scan:**
- No TODO/TBD.
- No vague “add error handling” steps.
- All code blocks are complete.

**3. Type consistency:**
- `WorkspaceContextSnapshot` fields match usage in `render_scene_dynamic_context`.
- `render_scene_dynamic_context(ctx, mode)` signature matches the spec.
- `gpt_app.system_prompt_template` is mutated in-place before `_inner_chat` consumes it.
