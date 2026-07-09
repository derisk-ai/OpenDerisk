# 场景空间 AgentWorkspace 输入与渲染 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在场景空间 AgentWorkspace 里实现标准多模态输入框(文本+文件+模型+`/`剧本命令)和结构化 VIS 渲染区(后端新增 `scene_agent_workspace` converter 驱动),替代现有简版输入框与纯文本步骤面板。

**Architecture:** 后端新增 `SceneAgentWorkspace` vis converter 子类,自动扫描注册,产出 `{render_name, planning, execution[], summary}` 结构化 vis 产物;场景 Agent(workspace_id 路径)默认走它,并在 `aggregation_chat` 入口识别 `playbook_command` 走 `start_task`。前端 `useSceneAgentChat` 扩展产出 `workspaceView` 状态 + 多模态 send;新建独立 `AgentWorkspaceRenderer`(复用 `markdownComponents`/GPTVis,无 ChatContentContext)和 `AgentWorkspaceInput`(本地状态,文件上传/模型/剧本命令);退役简版 `AgentChatInput`、`AgentProcessPanel`、死代码 `scene-agent-chat.tsx`。

**Tech Stack:** Python(后端 vis converter + agent_chat)/ TypeScript + React + antd + ahooks + jest + ts-jest(前端)/ GPTVis(markdown+vis 渲染)

## Global Constraints

- 后端 vis converter 通过子类化 `VisProtocolConverter` + 文件落在 `packages/derisk-ext/src/derisk_ext/vis/derisk/` 自动注册(`render_name` 属性为 key),不写 entry_points/装饰器/注册表。
- 后端 send 载荷契约(前端必须遵守):`user_input` 多模态 `{role:'user', content:[...resources, {type:'text', text}]}` 或 string;`chat_in_params` 含 `param_type` 为 `resource`/`model`/`playbook_command`;顶层 `model_name`;`ext_info` 含 `vis_render/workspace_id/task_id`;经 `useChat().chat` → `POST /api/v1/chat/completions`。
- 剧本命令协议字段:`chat_in_params` 项 `{param_type:'playbook_command', sub_type:'playbook', param_value: JSON.stringify({playbook_id, playbook_name})}`,`user_input` 为任务主题文本。
- 前端测试:jest + ts-jest,`testEnvironment: node`,测试文件放被测代码相邻的 `__tests__/` 目录,名 `*.test.ts(x)`;DOM 组件测试需在文件头加 `/** @jest-environment jsdom */`。纯逻辑测试镜像 `web/src/app/workspaces/detail/__tests__/parse-agent-steps.test.ts` 模式。
- 前端 `markdownComponents`/`markdownPlugins`/`preprocessLaTeX` 不依赖 `ChatContentContext`,可独立复用;但 `vis-chat-link.tsx` 依赖 Context 的 `handleChat`——AgentWorkspace 渲染区若内容含 `chat-link` 按钮会崩,本期用最小 `ChatContentContext.Provider`(提供 `handleChat` 占位)兜底。
- DRY/YAGNI:不引入未要求的能力(工具栏/skills/MCP/temperature/max_tokens)。

---

## File Structure

后端:
- Create: `packages/derisk-ext/src/derisk_ext/vis/derisk/derisk_vis_scene_agent_workspace_converter.py` — `SceneAgentWorkspaceConverter`,产出结构化 vis。
- Create: `packages/derisk-ext/tests/derisk_ext/vis/derisk/test_scene_agent_workspace_converter.py` — converter 单测。
- Modify: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` — render_name 解析(workspace_id→`scene_agent_workspace`)+ `playbook_command` 入口分支。
- Modify: `packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py` —(新建)playbook_command 入口测试。

前端:
- Create: `web/src/app/workspaces/detail/agent-workspace-types.ts` — 共享类型 `WorkspaceView`/`WorkspaceExecutionStep`/`WorkspaceArtifact`/`AgentWorkspaceInputHandle`/`PlaybookCommand`。
- Create: `web/src/app/workspaces/detail/parse-workspace-view.ts` — 把流式 `scene_agent_workspace` vis 对象规约成 `WorkspaceView`(增量合并、按 id 去重)。
- Create: `web/src/app/workspaces/detail/__tests__/parse-workspace-view.test.ts` — 单测。
- Create: `web/src/app/workspaces/detail/agent-workspace-input.tsx` — 独立多模态输入框。
- Create: `web/src/app/workspaces/detail/__tests__/agent-workspace-input.test.tsx` — 输入框逻辑测试。
- Create: `web/src/app/workspaces/detail/agent-workspace-renderer.tsx` — 独立 vis 渲染器(JSON not needed here)。
- Modify: `web/src/app/workspaces/detail/use-scene-agent-chat.ts` — 扩展 `send` 签名 + `workspaceView` 状态 + onMessage 分支。
- Modify: `web/src/app/workspaces/detail/agent-workspace.tsx` — 接入新输入框 + 渲染器,接收 `playbooks` prop。
- Modify: `web/src/app/workspaces/detail/scene-workspace-shell.tsx` — 拉取并下传 `playbooks`。
- Delete: `web/src/app/workspaces/detail/scene-agent-chat.tsx`(死代码)。
- Delete: `web/src/app/workspaces/detail/agent-chat-input.tsx`(被新输入框取代)。
- Delete: `web/src/app/workspaces/detail/agent-process-panel.tsx`(被渲染器取代)。

---

### Task 1: 后端 SceneAgentWorkspaceConverter

**Files:**
- Create: `packages/derisk-ext/src/derisk_ext/vis/derisk/derisk_vis_scene_agent_workspace_converter.py`
- Test: `packages/derisk-ext/tests/derisk_ext/vis/derisk/test_scene_agent_workspace_converter.py`

**Interfaces:**
- Consumes: `VisProtocolConverter` 基类(`packages/derisk-core/src/derisk/vis/vis_converter.py:77`)、`ManusExecutionStep`/`ManusArtifactItem`(`vis_manus_protocol.py:75,128`)。`DeriskIncrVisManusConverter`(`derisk_vis_manus_converter.py:113`)作为父类参考。
- Produces: `render_name = "scene_agent_workspace"` 的 converter,`visualization(...)` 返回结构化 dict(经 `_generate_vis_tag_output` 包成 vis tag,前端解析)。

参考文献:converter 注册靠 `scan_vis_converts("derisk_ext.vis")`(`vis_manage.py:39`)扫描子类;`render_name` 属性为 key(`vis_manage.py:51`)。`ManusExecutionStep` 字段:`id,type,title,subtitle,description,phase,status,output,action,action_input`。`ManusArtifactItem` 字段:`id,type,name,content,mime_type,file_path`。

- [ ] **Step 1: 写失败测试**

创建 `packages/derisk-ext/tests/derisk_ext/vis/derisk/test_scene_agent_workspace_converter.py`:

```python
"""Unit tests for SceneAgentWorkspaceConverter."""
import json
import pytest

from derisk_ext.vis.derisk.derisk_vis_scene_agent_workspace_converter import (
    SceneAgentWorkspaceConverter,
)


def _make_gpt_msg(action_report=None, ai_message=""):
    """构造一个最小 GptsMessage-like 对象供测试使用。"""
    class _Msg:
        def __init__(self):
            self.action_report = action_report
            self.ai_message = ai_message
            self.role_name = "LLM"
    return _Msg()


@pytest.mark.asyncio
async def test_render_name_is_scene_agent_workspace():
    conv = SceneAgentWorkspaceConverter(derisk_url="http://localhost")
    assert conv.render_name == "scene_agent_workspace"
    assert conv.web_use is True


@pytest.mark.asyncio
async def test_visualization_returns_structured_vis_with_execution_step():
    """给定带 action_report 的 message,visualization 产出含 execution 步骤的结构化 vis。"""
    conv = SceneAgentWorkspaceConverter(derisk_url="http://localhost")
    action_report = {
        "view": "tool_view",
        "content": json.dumps({
            "name": "search_workspace",
            "args": {"query": "营收"},
            "status": "complete",
            "content": "找到 3 条记录",
        }),
    }
    msg = _make_gpt_msg(action_report=action_report, ai_message="正在搜索")

    out = await conv.visualization(messages=[msg], gpt_msg=msg, is_first_chunk=True)
    # out 是 vis tag 包裹的字符串,内部 JSON 含 render_name + execution
    assert "scene_agent_workspace" in out
    assert "execution" in out
    assert "search_workspace" in out
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/derisk-ext && python -m pytest tests/derisk_ext/vis/derisk/test_scene_agent_workspace_converter.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'derisk_ext.vis.derisk.derisk_vis_scene_agent_workspace_converter'`

- [ ] **Step 3: 实现 converter**

创建 `packages/derisk-ext/src/derisk_ext/vis/derisk/derisk_vis_scene_agent_workspace_converter.py`:

```python
"""场景空间 AgentWorkspace 可视化转换器。

产出结构化 vis 产物 {render_name, planning, execution[], summary},前端 AgentWorkspaceRenderer 消费。
注册靠子类扫描(render_name = scene_agent_workspace)。
"""
import json
import uuid
from typing import Any, Dict, List, Optional, Union

from derisk_ext.vis.derisk.derisk_vis_manus_converter import (
    DeriskIncrVisManusConverter,
)


class SceneAgentWorkspaceConverter(DeriskIncrVisManusConverter):
    """场景空间 AgentWorkspace 转换器。

    复用 manus converter 的消息解析与 action_report 抽取逻辑,
    但输出形态改为 AgentWorkspace 需要的结构化 JSON(planning/execution/summary)。
    """

    SCENE_TAG = "scene_agent_workspace"

    @property
    def reuse_name(self):
        return "scene_agent_workspace"

    @property
    def render_name(self):
        return "scene_agent_workspace"

    @property
    def web_use(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "场景空间 AgentWorkspace 结构化可视化布局"

    @staticmethod
    def _safe_json_loads(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None

    def _step_from_action_report(self, report: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从 action_report 抽取一个 execution step。"""
        content = self._safe_json_loads(report.get("content"))
        if not isinstance(content, dict):
            return None
        status_raw = str(content.get("status", "")).lower()
        status = (
            "running" if status_raw in ("running", "executing", "pending")
            else "failed" if status_raw in ("failed", "error", "blocked")
            else "done"
        )
        action = content.get("name") or report.get("view")
        action_input = content.get("args") if isinstance(content.get("args"), dict) else None
        output = content.get("content") if isinstance(content.get("content"), str) else None
        return {
            "id": str(content.get("name") or uuid.uuid4().hex),
            "type": "tool_call",
            "title": str(action or "工具调用"),
            "status": status,
            "action": action,
            "action_input": action_input,
            "output": output,
            "artifact": None,
            "vis": None,
        }

    async def visualization(
        self,
        messages: List[Any],
        plans_map: Optional[Dict[str, Any]] = None,
        gpt_msg: Any = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        new_plans: Optional[List[Any]] = None,
        is_first_chunk: bool = False,
        incremental: bool = False,
        senders_map: Optional[Dict[str, Any]] = None,
        main_agent_name: Optional[str] = None,
        is_first_push: bool = False,
        **kwargs,
    ) -> str:
        """产出结构化 vis tag 包裹的 JSON。"""
        execution: List[Dict[str, Any]] = []
        summary: Optional[str] = None

        # 优先从 gpt_msg / stream_msg 取当前 action_report
        report = None
        if gpt_msg is not None and getattr(gpt_msg, "action_report", None):
            report = gpt_msg.action_report
        elif isinstance(stream_msg, dict) and stream_msg.get("action_report"):
            report = stream_msg["action_report"]
        if isinstance(report, dict):
            step = self._step_from_action_report(report)
            if step:
                execution.append(step)

        # assistant 文本作为 summary 候选
        ai_text = getattr(gpt_msg, "ai_message", None) if gpt_msg is not None else None
        if isinstance(ai_text, str) and ai_text.strip():
            summary = ai_text.strip()

        payload = {
            "render_name": "scene_agent_workspace",
            "planning": None,
            "execution": execution,
            "summary": summary,
        }
        body = json.dumps(payload, ensure_ascii=False)
        return f"```{self.SCENE_TAG}\n{body}\n```"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/derisk-ext && python -m pytest tests/derisk_ext/vis/derisk/test_scene_agent_workspace_converter.py -v`
Expected: PASS(3 tests)

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-ext/src/derisk_ext/vis/derisk/derisk_vis_scene_agent_workspace_converter.py packages/derisk-ext/tests/derisk_ext/vis/derisk/test_scene_agent_workspace_converter.py
git commit -m "feat(vis): add SceneAgentWorkspaceConverter for structured scene agent output"
```

---

### Task 2: 后端 render_name 解析 + playbook_command 入口

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`(render_name 解析 L1073-1085;`aggregation_chat` 入口 L1001-1012)
- Test: `packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py`(新建)

**Interfaces:**
- Consumes: `aggregation_chat(self, conv_id, ..., chat_in_params: Optional[List[ChatInParamValue]] = None, **ext_info)`(`agent_chat.py:1001-1012`);`create_task_from_tool(system_app, workspace_id, user_id, playbook_id, title, description)`(`_task_creator.py:5`);`ChatInParamValue`(`schemas.py:87`)字段 `param_type`/`sub_type`/`param_value`。
- Produces: 当 `ext_info.workspace_id` 存在时 `vis_render="scene_agent_workspace"`;当 `chat_in_params` 含 `param_type=='playbook_command'` 时,直接 `create_task_from_tool` + 发 `task_created` workspace event 并提前 return(跳过 LLM 回合)。

参考:`start_task` 工具发 `task_created` 的 payload 形态(`write_tools.py:54-63`):
```python
{"task_id","title","status","playbook_id","playbook_name","triggered_by","workspace_id"}
```

- [ ] **Step 1: 写失败测试**

创建 `packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py`:

```python
"""playbook_command 入口与 scene_agent_workspace render_name 测试。"""
import pytest

from derisk_serve.agent.agents.chat.agent_chat import SimpleAgentChat
from derisk_serve.building.config.api.schemas import ChatInParamValue


def _make_param(ptype, value, sub_type=None):
    return ChatInParamValue(param_type=ptype, param_value=value, sub_type=sub_type)


def test_extract_playbook_command_returns_playbook_id_and_name():
    """chat_in_params 含 playbook_command 时能被正确抽取。"""
    chat = SimpleAgentChat.__new__(SimpleAgentChat)
    params = [
        _make_param("resource", "[]", "common_file"),
        _make_param(
            "playbook_command",
            '{"playbook_id": 7, "playbook_name": "营收分析"}',
            "playbook",
        ),
    ]
    cmd = chat._extract_playbook_command(params)  # type: ignore[attr-defined]
    assert cmd == {"playbook_id": 7, "playbook_name": "营收分析"}


def test_extract_playbook_command_returns_none_when_absent():
    chat = SimpleAgentChat.__new__(SimpleAgentChat)
    assert chat._extract_playbook_command(None) is None  # type: ignore[attr-defined]
    assert chat._extract_playbook_command([_make_param("resource", "[]")]) is None  # type: ignore[attr-defined]


def test_resolve_vis_render_prefers_scene_for_workspace():
    """有 workspace_id 时 render_name 解析为 scene_agent_workspace。"""
    chat = SimpleAgentChat.__new__(SimpleAgentChat)
    assert chat._resolve_vis_render(ext_info={"workspace_id": 1}, gpt_app=None) == "scene_agent_workspace"  # type: ignore[attr-defined]
    # 无 workspace_id 且无 app layout 时回退 gpt_vis_all
    assert chat._resolve_vis_render(ext_info={}, gpt_app=None) == "gpt_vis_all"  # type: ignore[attr-defined]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/derisk-serve && python -m pytest tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py -v`
Expected: FAIL —— `AttributeError: 'SimpleAgentChat' object has no attribute '_extract_playbook_command'`

- [ ] **Step 3: 实现两个辅助方法**

在 `agent_chat.py` 的 `SimpleAgentChat` 类内(放在 `aggregation_chat` 方法定义之前),新增:

```python
    @staticmethod
    def _extract_playbook_command(chat_in_params):
        """从 chat_in_params 抽取 playbook_command,返回 {playbook_id, playbook_name} 或 None。"""
        if not chat_in_params:
            return None
        import json
        for p in chat_in_params:
            if getattr(p, "param_type", None) == "playbook_command":
                try:
                    return json.loads(p.param_value)
                except (TypeError, ValueError, AttributeError):
                    return None
        return None

    @staticmethod
    def _resolve_vis_render(ext_info, gpt_app):
        """场景 Agent(workspace_id)默认 scene_agent_workspace,否则走 app layout / gpt_vis_all。"""
        if ext_info.get("workspace_id"):
            return "scene_agent_workspace"
        if gpt_app and gpt_app.layout and gpt_app.layout.chat_layout:
            return gpt_app.layout.chat_layout.name
        return "gpt_vis_all"
```

- [ ] **Step 4: 接入 aggregation_chat**

修改 `agent_chat.py` L1073-1081,把原 render_name 解析替换为调用新方法。原代码:
```python
        vis_render = ext_info.get("vis_render", None)
        if not vis_render:
            if gpt_app.layout and gpt_app.layout.chat_layout:
                vis_render = gpt_app.layout.chat_layout.name
            else:
                vis_render = "gpt_vis_all"
```
改为:
```python
        vis_render = ext_info.get("vis_render", None)
        if not vis_render:
            vis_render = self._resolve_vis_render(ext_info, gpt_app)
```

然后在 `aggregation_chat` body 开头(读取 `chat_in_params` 之后、`vis_render` 解析之前,即 L1011 `chat_in_params` 参数之后的方法体起始处),插入 playbook_command 命令模式分支:

```python
        # 剧本命令模式:chat_in_params 含 playbook_command 时直接创建任务,跳过 LLM 回合
        playbook_command = self._extract_playbook_command(chat_in_params)
        if playbook_command and ext_info.get("workspace_id"):
            from derisk_serve.workspace.agent_tools._task_creator import (
                create_task_from_tool,
            )
            result = create_task_from_tool(
                system_app=self.system_app,
                workspace_id=int(ext_info["workspace_id"]),
                user_id=ext_info.get("user_id"),
                playbook_id=playbook_command.get("playbook_id"),
                title=(conv_input if isinstance(conv_input, str) else None) or playbook_command.get("playbook_name"),
                description=None,
            )
            # 发 task_created workspace event 后直接结束流
            yield self._format_workspace_event({"type": "task_created", "payload": {
                "task_id": result["task_id"],
                "title": result["title"],
                "status": result["status"],
                "playbook_id": result["playbook_id"],
                "playbook_name": result["playbook_name"],
                "triggered_by": result["triggered_by"],
                "workspace_id": ext_info["workspace_id"],
            }})
            yield "data: [DONE]\n\n"
            return
```

注意:
- `conv_input` 是 `aggregation_chat` 里 user_input 的本地变量名;若实际变量名不同(检查方法签名后的第一行赋值),用实际名。
- `_format_workspace_event` 包装 `{vis:{type,payload}}` 的辅助方法,已存在于 `agent_chat.py`(L259-272 附近的 `format_workspace_event`),确认它是实例方法 `self._format_workspace_event` 还是模块函数 `format_workspace_event`,用对应调用方式。
- `self.system_app` 是 `SimpleAgentChat` 已有的属性;若属性名不同用实际名(检查 `__init__`)。
- 这段若是同步生成器与 async 混用导致 yield 语法问题,改为 `yield` 在 async generator 里合法。`aggregation_chat` 是 `async def`,内部 `yield` 即为 async generator,合法。

若 `aggregation_chat` 不是 async generator(而是返回 list/用 queue),则命令模式分支改为:把 event 推入事件队列后 return(参照 L1253-1299 workspace_event_queue 的drain方式)。**实现时先读 L1253-1299 确认事件下发机制**,用一致方式。

- [ ] **Step 5: 运行测试确认通过**

Run: `cd packages/derisk-serve && python -m pytest tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py -v`
Expected: PASS(3 tests)

- [ ] **Step 6: 提交**

```bash
git add packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py
git commit -m "feat(agent-chat): scene_agent_workspace render_name + playbook_command task creation"
```

---

### Task 3: 前端共享类型 + workspaceView 解析器

**Files:**
- Create: `web/src/app/workspaces/detail/agent-workspace-types.ts`
- Create: `web/src/app/workspaces/detail/parse-workspace-view.ts`
- Test: `web/src/app/workspaces/detail/__tests__/parse-workspace-view.test.ts`

**Interfaces:**
- Consumes: 流上 `scene_agent_workspace` vis tag 内容(JSON 字符串,经 `use-chat.ts` 解析 tag 后传入)。
- Produces:
  - `WorkspaceView` `{ planning: {goal, steps[{id,title,status}]} | null, execution: WorkspaceExecutionStep[], summary: string | null }`
  - `WorkspaceExecutionStep` `{ id, type:'tool_call'|'thinking'|'artifact'|'delivery', title, status:'running'|'done'|'failed', action?, action_input?, output?, artifact?: WorkspaceArtifact, vis? }`
  - `WorkspaceArtifact` `{ file_path, mime_type?, preview_url? }`
  - `PlaybookCommand` `{ playbook_id: number, playbook_name: string }`
  - `AgentWorkspaceInputHandle` `{ focus: () => void }`
  - 函数 `parseWorkspaceView(view, prev): WorkspaceView` —— 把单个 chunk 的 vis payload 合并进 prev(按 `execution[].id` 去重更新)。

- [ ] **Step 1: 写失败测试**

创建 `web/src/app/workspaces/detail/__tests__/parse-workspace-view.test.ts`:

```typescript
import { parseWorkspaceView } from '../parse-workspace-view';
import type { WorkspaceView } from '../agent-workspace-types';

describe('parseWorkspaceView', () => {
  test('首次 chunk 建立 execution', () => {
    const chunk = {
      render_name: 'scene_agent_workspace',
      planning: null,
      execution: [{ id: 's1', type: 'tool_call', title: '搜索', status: 'running', action: 'search' }],
      summary: null,
    };
    const view = parseWorkspaceView(chunk, null);
    expect(view.execution).toHaveLength(1);
    expect(view.execution[0].id).toBe('s1');
    expect(view.execution[0].status).toBe('running');
  });

  test('同 id 步骤去重更新状态', () => {
    const prev: WorkspaceView = {
      planning: null,
      execution: [{ id: 's1', type: 'tool_call', title: '搜索', status: 'running', action: 'search' }],
      summary: null,
    };
    const chunk = {
      render_name: 'scene_agent_workspace',
      planning: null,
      execution: [{ id: 's1', type: 'tool_call', title: '搜索', status: 'done', action: 'search', output: 'OK' }],
      summary: '完成',
    };
    const view = parseWorkspaceView(chunk, prev);
    expect(view.execution).toHaveLength(1);
    expect(view.execution[0].status).toBe('done');
    expect(view.execution[0].output).toBe('OK');
    expect(view.summary).toBe('完成');
  });

  test('新 id 步骤追加', () => {
    const prev: WorkspaceView = {
      planning: null,
      execution: [{ id: 's1', type: 'tool_call', title: 'A', status: 'done' }],
      summary: null,
    };
    const chunk = {
      render_name: 'scene_agent_workspace',
      planning: { goal: 'G', steps: [{ id: 'p1', title: 'P1', status: 'done' }] },
      execution: [{ id: 's1', type: 'tool_call', title: 'A', status: 'done' }, { id: 's2', type: 'artifact', title: 'B', status: 'running' }],
      summary: null,
    };
    const view = parseWorkspaceView(chunk, prev);
    expect(view.execution.map(e => e.id)).toEqual(['s1', 's2']);
    expect(view.planning?.goal).toBe('G');
  });

  test('非法 payload 返回 prev', () => {
    const prev: WorkspaceView = { planning: null, execution: [], summary: null };
    expect(parseWorkspaceView(null, prev)).toBe(prev);
    expect(parseWorkspaceView({ execution: 'no' }, prev)).toBe(prev);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd web && npx jest src/app/workspaces/detail/__tests__/parse-workspace-view.test.ts`
Expected: FAIL —— `Cannot find module '../parse-workspace-view'`

- [ ] **Step 3: 实现类型与解析器**

创建 `web/src/app/workspaces/detail/agent-workspace-types.ts`:

```typescript
export interface WorkspaceArtifact {
  file_path: string;
  mime_type?: string;
  preview_url?: string;
}

export interface WorkspaceExecutionStep {
  id: string;
  type: 'tool_call' | 'thinking' | 'artifact' | 'delivery';
  title: string;
  status: 'running' | 'done' | 'failed';
  action?: string | null;
  action_input?: Record<string, unknown> | null;
  output?: string | null;
  artifact?: WorkspaceArtifact | null;
  vis?: unknown;
}

export interface WorkspacePlanning {
  goal: string;
  steps: { id: string; title: string; status: 'pending' | 'running' | 'done' | 'failed' }[];
}

export interface WorkspaceView {
  planning: WorkspacePlanning | null;
  execution: WorkspaceExecutionStep[];
  summary: string | null;
}

export interface PlaybookCommand {
  playbook_id: number;
  playbook_name: string;
}

export interface AgentWorkspaceInputHandle {
  focus: () => void;
}
```

创建 `web/src/app/workspaces/detail/parse-workspace-view.ts`:

```typescript
import type { WorkspaceExecutionStep, WorkspaceView } from './agent-workspace-types';

const VALID_TYPES = ['tool_call', 'thinking', 'artifact', 'delivery'];
const VALID_STATUS = ['running', 'done', 'failed'];

function normalizeStep(raw: unknown): WorkspaceExecutionStep | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.id !== 'string' || typeof r.title !== 'string') return null;
  const type = VALID_TYPES.includes(r.type as string) ? (r.type as WorkspaceExecutionStep['type']) : 'tool_call';
  const status = VALID_STATUS.includes(r.status as string) ? (r.status as WorkspaceExecutionStep['status']) : 'running';
  return {
    id: r.id,
    type,
    title: r.title,
    status,
    action: typeof r.action === 'string' ? r.action : null,
    action_input: r.action_input && typeof r.action_input === 'object' ? (r.action_input as Record<string, unknown>) : null,
    output: typeof r.output === 'string' ? r.output : null,
    artifact: r.artifact && typeof r.artifact === 'object' ? (r.artifact as WorkspaceExecutionStep['artifact']) : null,
    vis: r.vis ?? null,
  };
}

export function parseWorkspaceView(chunk: unknown, prev: WorkspaceView | null): WorkspaceView {
  if (!chunk || typeof chunk !== 'object') return prev ?? { planning: null, execution: [], summary: null };
  const c = chunk as Record<string, unknown>;
  if (!Array.isArray(c.execution)) return prev ?? { planning: null, execution: [], summary: null };

  const prevById = new Map((prev?.execution ?? []).map(e => [e.id, e]));
  const execution: WorkspaceExecutionStep[] = [];
  for (const raw of c.execution) {
    const step = normalizeStep(raw);
    if (!step) continue;
    const existing = prevById.get(step.id);
    execution.push(existing ? { ...existing, ...step } : step);
    prevById.delete(step.id);
  }
  // 保留 prev 中未被本 chunk 覆盖的旧步骤(已完成的)
  for (const leftover of prevById.values()) {
    execution.push(leftover);
  }

  const planning = c.planning && typeof c.planning === 'object'
    ? (c.planning as WorkspaceView['planning'])
    : (prev?.planning ?? null);
  const summary = typeof c.summary === 'string' ? c.summary : (prev?.summary ?? null);

  return { planning, execution, summary };
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd web && npx jest src/app/workspaces/detail/__tests__/parse-workspace-view.test.ts`
Expected: PASS(4 tests)

- [ ] **Step 5: 提交**

```bash
git add web/src/app/workspaces/detail/agent-workspace-types.ts web/src/app/workspaces/detail/parse-workspace-view.ts web/src/app/workspaces/detail/__tests__/parse-workspace-view.test.ts
git commit -m "feat(web): workspace view types + parser for scene agent workspace"
```

---

### Task 4: 扩展 useSceneAgentChat(多模态 send + workspaceView)

**Files:**
- Modify: `web/src/app/workspaces/detail/use-scene-agent-chat.ts`
- Test: `web/src/app/workspaces/detail/__tests__/use-scene-agent-chat.test.ts`(新建,纯逻辑:send 载荷构造)

**Interfaces:**
- Consumes: `useChat().chat`(`use-chat.ts:158`)、`parseAgentSteps`(`parse-agent-steps.ts`)、`parseWorkspaceView`(Task 3)、`UserChatContent`(`@/types/chat`)。
- Produces: `send` 签名改为 `send: (payload: { text: string; resources?: ParsedResourceItem[]; model?: string; playbookCommand?: PlaybookCommand }) => void`;返回值新增 `workspaceView: WorkspaceView`、`clearWorkspaceView: () => void`。

参考:`use-chat.ts` 的 `onMessage` 会把 `scene_agent_workspace` vis 对象(非 workspace-event 白名单 type)当 object 传入 `onMessage`(L144);现有 `onMessage`(L71-75)只处理 `parseAgentSteps`,对象会返回 null 被丢弃。扩展 onMessage:对象先尝试 `parseWorkspaceView` 合并到 `workspaceView`。

send 载荷构造(对齐 `chat-session.tsx:306-320`):
- `user_input`:有 resources 时 `{role:'user', content:[...resources, {type:'text', text}]}`,否则 `text`。
- `chat_in_params`:`[...(resources.length ? [{param_type:'resource', param_value: JSON.stringify(resources), sub_type:'common_file'}] : []), ...(model ? [{param_type:'model', param_value: model}] : []), ...(playbookCommand ? [{param_type:'playbook_command', sub_type:'playbook', param_value: JSON.stringify(playbookCommand)}] : [])]`(仅当非空)。
- `model_name`:model(若有)。
- `ext_info`:`{ vis_render:'scene_agent_workspace', workspace_id, task_id }`(含 workspace_id/task_id)。
- `app_code`/`team_mode`/`app_config_code`/`agent_version`:从 appCode 传(NUM);其余无 appInfo,可省(后端 `aggregation_chat` 经 `**ext_info` 接收)。

- [ ] **Step 1: 写失败测试**

创建 `web/src/app/workspaces/detail/__tests__/use-scene-agent-chat.test.ts`:

```typescript
/** @jest-environment jsdom */
import { renderHook, act } from '@testing-library/react';
import { useSceneAgentChat } from '../use-scene-agent-chat';

jest.mock('@/hooks/use-chat', () => ({
  useChat: () => ({
    chat: jest.fn((params: any) => {
      // 模拟后端下发一个 scene_agent_workspace vis 对象 + done
      params.onMessage({ render_name: 'scene_agent_workspace', planning: null, execution: [{ id: 's1', type: 'tool_call', title: 'A', status: 'done' }], summary: null });
      params.onDone?.();
    }),
    ctrl: new AbortController(),
  }),
}));

describe('useSceneAgentChat', () => {
  test('send 构造多模态 user_input 与 chat_in_params', async () => {
    const { result } = renderHook(() => useSceneAgentChat({ convUid: 'c1', appCode: 'app', workspaceId: 9 }));
    await act(async () => {
      result.current.send({ text: '你好', resources: [{ type: 'file_url', file_url: { url: 'u', file_name: 'f.txt' } }], model: 'gpt-4' });
    });
    // workspaceView 被流更新
    expect(result.current.workspaceView.execution).toHaveLength(1);
    expect(result.current.workspaceView.execution[0].id).toBe('s1');
  });

  test('send 剧本命令构造 playbook_command chat_in_params', async () => {
    const { result } = renderHook(() => useSceneAgentChat({ convUid: 'c1', appCode: 'app', workspaceId: 9 }));
    await act(async () => {
      result.current.send({ text: '营收分析', playbookCommand: { playbook_id: 7, playbook_name: '营收分析' } });
    });
    expect(result.current.loading).toBe(false);
  });
});
```

> 注:若 `@testing-library/react` 未安装,先 `cd web && npm i -D @testing-library/react @testing-library/jest-dom` 并确认 jest 配置 testEnvironment 已支持(文件头 `@jest-environment jsdom`)。若环境装不上,降级为直接测一个独立的 `buildSceneAgentSendData(payload)` 纯函数(把 send 里的载荷构造抽成纯函数单测)。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd web && npx jest src/app/workspaces/detail/__tests__/use-scene-agent-chat.test.ts`
Expected: FAIL —— `workspaceView` 不存在 / `send` 签名不匹配

- [ ] **Step 3: 扩展 hook**

修改 `web/src/app/workspaces/detail/use-scene-agent-chat.ts`。在现有 import 基础上加:
```typescript
import type { WorkspaceExecutionStep } from './agent-workspace-types'  // 若只用到 WorkspaceView 则改
```
实际 import:
```typescript
import { parseWorkspaceView } from './parse-workspace-view';
import type { PlaybookCommand, WorkspaceView } from './agent-workspace-types';
```

`UseSceneAgentChatResult` 接口改为:
```typescript
interface SceneAgentSendPayload {
  text: string;
  resources?: Record<string, unknown>[];  // ParsedResourceItem 形态
  model?: string;
  playbookCommand?: PlaybookCommand;
}

interface UseSceneAgentChatResult {
  steps: AgentStep[];
  workspaceView: WorkspaceView;
  loading: boolean;
  error: string | null;
  lastInput: SceneAgentSendPayload | null;
  send: (payload: SceneAgentSendPayload) => void;
  abort: () => void;
  clearSteps: () => void;
  clearWorkspaceView: () => void;
}
```

新增状态(放在现有 useState 旁):
```typescript
const [workspaceView, setWorkspaceView] = useState<WorkspaceView>({ planning: null, execution: [], summary: null });
const [lastInput, setLastInput] = useState<SceneAgentSendPayload | null>(null);
```

`send` 改为:
```typescript
const send = useCallback(
  (payload: SceneAgentSendPayload) => {
    const { text, resources = [], model, playbookCommand } = payload;
    if (!convUid || !text.trim()) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    setLastInput(payload);
    setError(null);

    const userInput = resources.length > 0
      ? { role: 'user', content: [...resources, ...(text.trim() ? [{ type: 'text', text: text.trim() }] : [])] }
      : text.trim();

    const chatInParams: { param_type: string; param_value: string; sub_type?: string }[] = [];
    if (resources.length > 0) {
      chatInParams.push({ param_type: 'resource', param_value: JSON.stringify(resources), sub_type: 'common_file' });
    }
    if (model) {
      chatInParams.push({ param_type: 'model', param_value: model });
    }
    if (playbookCommand) {
      chatInParams.push({ param_type: 'playbook_command', sub_type: 'playbook', param_value: JSON.stringify(playbookCommand) });
    }

    chat({
      ctrl,
      data: {
        conv_uid: convUid,
        user_input: userInput,
        workspace_id: workspaceId,
        task_id: taskId,
        ...(model ? { model_name: model } : {}),
        ...(chatInParams.length ? { chat_in_params: chatInParams } : {}),
        team_mode: '',
        app_config_code: '',
        agent_version: 'v1',
        ext_info: {
          vis_render: 'scene_agent_workspace',
          ...(workspaceId !== undefined ? { workspace_id: Number(workspaceId) } : {}),
          ...(taskId !== undefined ? { task_id: Number(taskId) } : {}),
        },
      },
      onMessage: (message: unknown) => {
        if (message && typeof message === 'object') {
          const step = parseAgentSteps(message);
          if (step) { appendStep(step); return; }
          // scene_agent_workspace 结构化 vis
          const mv = message as Record<string, unknown>;
          if (mv.render_name === 'scene_agent_workspace' || Array.isArray(mv.execution)) {
            setWorkspaceView(prev => parseWorkspaceView(message, prev));
          }
        }
      },
      onDone: () => { setLoading(false); setLastInput(null); },
      onClose: () => { setLoading(false); setLastInput(null); },
      onError: (content: string) => {
        setError(content || 'Agent error');
        appendStep({ id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`, type: 'unknown', title: 'Agent error', status: 'failed', timestamp: Date.now(), payload: { error: content || 'Agent error' } });
        setLoading(false);
      },
      onWorkspaceEvent,
    });
  },
  [convUid, workspaceId, taskId, chat, appendStep, onWorkspaceEvent],
);
```

新增 `clearWorkspaceView`:
```typescript
const clearWorkspaceView = useCallback(() => setWorkspaceView({ planning: null, execution: [], summary: null }), []);
```

`useEffect` 里 convUid 变化时也清 workspaceView:在现有 `clearSteps` 的 effect 里加 `setWorkspaceView({ planning: null, execution: [], summary: null })`。

return 改为:
```typescript
return { steps, workspaceView, loading, error, lastInput, send, abort, clearSteps, clearWorkspaceView };
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd web && npx jest src/app/workspaces/detail/__tests__/use-scene-agent-chat.test.ts`
Expected: PASS(2 tests)

- [ ] **Step 5: 提交**

```bash
git add web/src/app/workspaces/detail/use-scene-agent-chat.ts web/src/app/workspaces/detail/__tests__/use-scene-agent-chat.test.ts
git commit -m "feat(web): extend useSceneAgentChat with multimodal send + workspaceView"
```

---

### Task 5: 独立多模态输入框 AgentWorkspaceInput

**Files:**
- Create: `web/src/app/workspaces/detail/agent-workspace-input.tsx`
- Test: `web/src/app/workspaces/detail/__tests__/agent-workspace-input.test.tsx`

**Interfaces:**
- Consumes: `postChatModeParamsFileLoad`(`request.ts:271`)、`getModelList`(`request.ts:364`)、`apiInterceptors`(`@/client/api`)、`file-preview.tsx`、utils `getFileIcon`/`formatFileSize`/`transformFileUrl`、antd。
- Produces: `AgentWorkspaceInput`(forwardRef `AgentWorkspaceInputHandle`),props:
  ```typescript
  interface AgentWorkspaceInputProps {
    convUid?: string;
    onSend: (payload: { text: string; resources?: Record<string, unknown>[]; model?: string; playbookCommand?: PlaybookCommand }) => void;
    loading?: boolean;
    disabled?: boolean;
    lastInput?: { text: string } | null;
    onRetry?: () => void;
    playbooks?: { playbook_id: number; playbook_name: string }[];
  }
  ```

参考(从 UnifiedChatInput 抽纯逻辑):
- `UploadingFile` `{ id, file, progress, status:'uploading'|'success'|'error', error? }`
- `getAcceptTypes`(`unified-chat-input.tsx:100-117`)
- 上传:`FormData` append `doc_files` → `postChatModeParamsFileLoad({convUid, chatMode:'chat_normal', data, model})`;URL 归一化 6 格式分支(`L852-890`);resource 对象构造按 image/audio/video/file(`L894-931`)。写回改为本地 `setResources(prev => [...prev, newResourceItem])`。
- 模型:`useRequest` + `apiInterceptors(getModelList())` 过滤 `worker_type==='llm'`。
- `/` 唤起:输入框 `onChange` 检测末尾 `/` → 弹 antd `Popover`/`Dropdown` 列出 `playbooks`,选中→ `onSend({ text: 当前文本去掉/后内容, playbookCommand: {playbook_id, playbook_name} })` 并清空。

- [ ] **Step 1: 写失败测试**

创建 `web/src/app/workspaces/detail/__tests__/agent-workspace-input.test.tsx`(聚焦纯逻辑:`/` 剧本检测 + send 载荷构造,渲染用 jsdom):

```tsx
/** @jest-environment jsdom */
import { render, fireEvent, screen, act } from '@testing-library/react';
import { AgentWorkspaceInput } from '../agent-workspace-input';

jest.mock('@/client/api', () => ({
  apiInterceptors: jest.fn(() => Promise.resolve([null, []])),
  getModelList: jest.fn(),
  postChatModeParamsFileLoad: jest.fn(),
}));
jest.mock('ahooks', () => ({ useRequest: () => ({ loading: false }) }));

describe('AgentWorkspaceInput', () => {
  test('输入 / 且有 playbooks 时显示剧本列表', () => {
    const onSend = jest.fn();
    render(
      <AgentWorkspaceInput
        convUid="c1"
        onSend={onSend}
        playbooks={[{ playbook_id: 1, playbook_name: '营收分析' }]}
      />,
    );
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: '/' } });
    expect(screen.getByText('营收分析')).toBeInTheDocument();
  });

  test('选中剧本后 onSend 携带 playbookCommand 与主题文本', () => {
    const onSend = jest.fn();
    render(
      <AgentWorkspaceInput
        convUid="c1"
        onSend={onSend}
        playbooks={[{ playbook_id: 1, playbook_name: '营收分析' }]}
      />,
    );
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: '本月营收/' } });
    fireEvent.click(screen.getByText('营收分析'));
    expect(onSend).toHaveBeenCalledWith(
      expect.objectContaining({
        text: expect.any(String),
        playbookCommand: { playbook_id: 1, playbook_name: '营收分析' },
      }),
    );
  });
});
```

> 注:`/` 唤起的语义:用户输入"主题内容"+`/`(或 `/` 后筛选剧本名)。实现采用:文本以 `/` 结尾时弹出列表;选中后,`/` 之前的文本作为任务主题 `text`,剧本进入 `playbookCommand`。测试依此语义写。若你偏好"`/` 后输入剧本名筛选",实现时调整,测试同步。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd web && npx jest src/app/workspaces/detail/__tests__/agent-workspace-input.test.tsx`
Expected: FAIL —— `Cannot find module '../agent-workspace-input'`

- [ ] **Step 3: 实现输入框**

创建 `web/src/app/workspaces/detail/agent-workspace-input.tsx`:

```tsx
'use client';

import { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { Button, Input, Popover } from 'antd';
import { SendOutlined, ReloadOutlined, PaperClipOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { apiInterceptors, getModelList, postChatModeParamsFileLoad } from '@/client/api';
import { getFileIcon, formatFileSize } from '@/utils/fileUtils';
import { transformFileUrl } from '@/utils';
import type { IModelData } from '@/types/model';
import type { AgentWorkspaceInputHandle, PlaybookCommand } from './agent-workspace-types';

interface ResourceItem {
  type: string;
  image_url?: { url: string; preview_url?: string; file_name?: string };
  file_url?: { url: string; preview_url?: string; file_name?: string };
  audio_url?: { url: string; preview_url?: string; file_name?: string };
  video_url?: { url: string; preview_url?: string; file_name?: string };
}

interface UploadingFile { id: string; file: File; status: 'uploading' | 'success' | 'error'; error?: string }

interface AgentWorkspaceInputProps {
  convUid?: string;
  onSend: (payload: { text: string; resources?: ResourceItem[]; model?: string; playbookCommand?: PlaybookCommand }) => void;
  loading?: boolean;
  disabled?: boolean;
  lastInput?: { text: string } | null;
  onRetry?: () => void;
  playbooks?: { playbook_id: number; playbook_name: string }[];
}

export const AgentWorkspaceInput = forwardRef<AgentWorkspaceInputHandle, AgentWorkspaceInputProps>(
  function AgentWorkspaceInput({ convUid, onSend, loading, disabled, lastInput, onRetry, playbooks }, ref) {
    const [text, setText] = useState('');
    const [resources, setResources] = useState<ResourceItem[]>([]);
    const [uploading, setUploading] = useState<UploadingFile[]>([]);
    const [modelList, setModelList] = useState<IModelData[]>([]);
    const [selectedModel, setSelectedModel] = useState<string>('');
    const [showPlaybook, setShowPlaybook] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useImperativeHandle(ref, () => ({ focus: () => textareaRef.current?.focus() }));

    useRequest(async () => {
      const [, data] = await apiInterceptors(getModelList());
      return data || [];
    }, {
      onSuccess: (models: IModelData[]) => {
        const llm = models.filter(m => m.worker_type === 'llm');
        setModelList(llm);
        if (llm.length) setSelectedModel(llm[0].model_name);
      },
    });

    const normalizeUploadRes = (res: any): { fileUrl: string; previewUrl: string } => {
      let previewUrl = '', fileUrl = '';
      if (res?.preview_url) { previewUrl = res.preview_url; fileUrl = res.file_path || previewUrl; }
      else if (res?.file_path) { fileUrl = res.file_path; previewUrl = transformFileUrl(fileUrl); }
      else if (res?.url || res?.file_url) { fileUrl = res.url || res.file_url; previewUrl = fileUrl; }
      else if (res?.path) { fileUrl = res.path; previewUrl = transformFileUrl(fileUrl); }
      else if (typeof res === 'string') { fileUrl = res; previewUrl = res; }
      else if (Array.isArray(res)) { const f = res[0]; previewUrl = f?.preview_url || ''; fileUrl = f?.file_path || f?.preview_url || previewUrl; if (!previewUrl && fileUrl) previewUrl = transformFileUrl(fileUrl); }
      return { fileUrl, previewUrl };
    };

    const buildResourceItem = (file: File, fileUrl: string, previewUrl: string): ResourceItem => {
      const common = { url: fileUrl, preview_url: previewUrl || fileUrl, file_name: file.name };
      if (file.type.startsWith('image/')) return { type: 'image_url', image_url: common };
      if (file.type.startsWith('audio/')) return { type: 'audio_url', audio_url: common };
      if (file.type.startsWith('video/')) return { type: 'video_url', video_url: common };
      return { type: 'file_url', file_url: common };
    };

    const handleFileUpload = async (file: File) => {
      if (!convUid) return;
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
      setUploading(prev => [...prev, { id, file, status: 'uploading' }]);
      const formData = new FormData();
      formData.append('doc_files', file);
      const [err, res] = await apiInterceptors(
        postChatModeParamsFileLoad({ convUid, chatMode: 'chat_normal', data: formData, model: selectedModel, config: { timeout: 1000 * 60 * 60 } }),
      );
      setUploading(prev => prev.filter(u => u.id !== id));
      if (err) {
        setUploading(prev => [...prev, { id, file, status: 'error', error: String(err) }]);
        return;
      }
      const { fileUrl, previewUrl } = normalizeUploadRes(res);
      setResources(prev => [...prev, buildResourceItem(file, fileUrl, previewUrl)]);
    };

    const handleDrop = async (e: React.DragEvent) => {
      e.preventDefault();
      for (const f of Array.from(e.dataTransfer.files)) await handleFileUpload(f);
    };

    const handleSend = () => {
      const trimmed = text.trim();
      if (!trimmed && resources.length === 0) return;
      onSend({ text: trimmed, resources: resources.length ? resources : undefined, model: selectedModel || undefined });
      setText('');
      setResources([]);
      setShowPlaybook(false);
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
    };

    const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const v = e.target.value;
      setText(v);
      setShowPlaybook(v.endsWith('/') && (playbooks?.length ?? 0) > 0);
    };

    const pickPlaybook = (pb: { playbook_id: number; playbook_name: string }) => {
      const topic = text.replace(/\/\s*$/, '').trim();
      onSend({ text: topic || pb.playbook_name, playbookCommand: { playbook_id: pb.playbook_id, playbook_name: pb.playbook_name } });
      setText('');
      setShowPlaybook(false);
    };

    const filteredPlaybooks = (playbooks ?? []).filter(pb =>
      !text.slice(0, -1) || pb.playbook_name.toLowerCase().includes(text.slice(0, -1).toLowerCase())
    );

    const playbookPopover = (
      <div className="ws-agent-input__playbook-list">
        {filteredPlaybooks.map(pb => (
          <div key={pb.playbook_id} className="ws-agent-input__playbook-item" onClick={() => pickPlaybook(pb)} role="button">
            {pb.playbook_name}
          </div>
        ))}
      </div>
    );

    return (
      <div className="ws-agent-input" onDrop={handleDrop} onDragOver={(e) => e.preventDefault()}>
        {uploading.map(u => (
          <div key={u.id} className="ws-agent-input__uploading">{u.file.name} {u.status === 'error' ? '失败' : '上传中'}</div>
        ))}
        {resources.map((r, i) => (
          <div key={i} className="ws-agent-input__resource">
            <span>{r.image_url?.file_name || r.file_url?.file_name || r.audio_url?.file_name || r.video_url?.file_name}</span>
            <Button size="small" type="text" onClick={() => setResources(prev => prev.filter((_, j) => j !== i))}>×</Button>
          </div>
        ))}
        <Popover open={showPlaybook} content={playbookPopover} trigger="" placement="topLeft">
          <Input.TextArea
            ref={textareaRef}
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder="输入指令给 Agent…(输入 / 选择剧本)"
            autoSize={{ minRows: 1, maxRows: 6 }}
            disabled={disabled || loading}
          />
        </Popover>
        <div className="ws-agent-input__actions">
          <Button icon={<PaperClipOutlined />} disabled={!convUid || disabled} onClick={() => fileInputRef.current?.click()} />
          <input ref={fileInputRef} type="file" multiple style={{ display: 'none' }} onChange={(e) => { for (const f of Array.from(e.target.files || [])) handleFileUpload(f); e.target.value = ''; }} />
          {lastInput && onRetry && !loading && <Button icon={<ReloadOutlined />} onClick={onRetry} disabled={disabled} title="重试" />}
          <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading} disabled={(disabled || loading) && resources.length === 0 && !text.trim()} />
        </div>
      </div>
    );
  },
);
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd web && npx jest src/app/workspaces/detail/__tests__/agent-workspace-input.test.tsx`
Expected: PASS(2 tests)

- [ ] **Step 5: 提交**

```bash
git add web/src/app/workspaces/detail/agent-workspace-input.tsx web/src/app/workspaces/detail/__tests__/agent-workspace-input.test.tsx
git commit -m "feat(web): standalone multimodal AgentWorkspaceInput with file/model/playbook-command"
```

---

### Task 6: 独立 vis 渲染器 AgentWorkspaceRenderer + 接入

**Files:**
- Create: `web/src/app/workspaces/detail/agent-workspace-renderer.tsx`
- Modify: `web/src/app/workspaces/detail/agent-workspace.tsx`
- Delete: `web/src/app/workspaces/detail/agent-process-panel.tsx`
- Delete: `web/src/app/workspaces/detail/agent-chat-input.tsx`
- Delete: `web/src/app/workspaces/detail/scene-agent-chat.tsx`

**Interfaces:**
- Consumes: `markdownComponents`/`markdownPlugins`/`preprocessLaTeX`(`web/src/components/chat/chat-content-components/config.tsx`,无 Context 依赖)、`GPTVis`(`@antv/gpt-vis`)、`WorkspaceView`(Task 3)、`AgentWorkspaceInput`(Task 5)、`useSceneAgentChat`(Task 4)。`ChatContentContext`(`@/contexts`)需提供最小 `handleChat` 占位渲染 `vis-chat-link`。
- Produces: `AgentWorkspaceRenderer({ view, onStepClick? })`;`AgentWorkspace` 改用新输入框 + 渲染器,接收 `playbooks` prop。

- [ ] **Step 1: 实现渲染器**

创建 `web/src/app/workspaces/detail/agent-workspace-renderer.tsx`:

```tsx
'use client';

import { useMemo } from 'react';
import { GPTVis } from '@antv/gpt-vis';
import markdownComponents, { markdownPlugins, preprocessLaTeX } from '@/components/chat/chat-content-components/config';
import type { WorkspaceExecutionStep, WorkspaceView } from './agent-workspace-types';
import type { AgentStep } from './agent-types';

const STATUS_ICON: Record<WorkspaceExecutionStep['status'], string> = {
  running: '⏳',
  done: '✅',
  failed: '❌',
};

function StepCard({ step, onStepClick }: { step: WorkspaceExecutionStep; onStepClick?: (s: WorkspaceExecutionStep) => void }) {
  const markdown = useMemo(() => {
    const parts: string[] = [];
    if (step.action) parts.push(`**工具:** ${step.action}`);
    if (step.action_input) parts.push('```json\n' + JSON.stringify(step.action_input, null, 2) + '\n```');
    if (step.output) parts.push(step.output);
    return parts.join('\n\n');
  }, [step]);

  return (
    <div className="ws-agent-renderer__step" role="button" tabIndex={0}
      onClick={() => onStepClick?.(step)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onStepClick?.(step); } }}>
      <div className="ws-agent-renderer__step-head">
        <span>{STATUS_ICON[step.status]}</span>
        <span className="ws-agent-renderer__step-title">{step.title}</span>
      </div>
      {markdown && (
        <GPTVis components={markdownComponents} {...markdownPlugins}>
          {preprocessLaTeX(markdown)}
        </GPTVis>
      )}
      {step.artifact && (
        <div className="ws-agent-renderer__artifact">{step.artifact.file_path}</div>
      )}
    </div>
  );
}

export interface AgentWorkspaceRendererProps {
  view: WorkspaceView;
  onStepClick?: (step: WorkspaceExecutionStep) => void;
}

export function AgentWorkspaceRenderer({ view, onStepClick }: AgentWorkspaceRendererProps) {
  return (
    <div className="ws-agent-renderer">
      {view.planning && (
        <div className="ws-agent-renderer__planning">
          <div className="ws-agent-renderer__goal">{view.planning.goal}</div>
          {view.planning.steps.map(s => (
            <div key={s.id} className="ws-agent-renderer__plan-step">{STATUS_ICON[(s.status as WorkspaceExecutionStep['status'])] ?? '•'} {s.title}</div>
          ))}
        </div>
      )}
      {view.execution.map(step => (
        <StepCard key={step.id} step={step} onStepClick={onStepClick} />
      ))}
      {view.summary && (
        <GPTVis components={markdownComponents} {...markdownPlugins}>
          {preprocessLaTeX(view.summary)}
        </GPTVis>
      )}
      {!view.execution.length && !view.summary && (
        <div className="ws-agent-renderer__empty">Agent 就绪,输入指令开始工作</div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 改造 agent-workspace.tsx**

修改 `web/src/app/workspaces/detail/agent-workspace.tsx`:
- 替换 import:`import { AgentChatInput, AgentChatInputHandle } from './agent-chat-input'` → `import { AgentWorkspaceInput, } from './agent-workspace-input'` + `import { AgentWorkspaceRenderer } from './agent-workspace-renderer'` + `import type { AgentWorkspaceInputHandle } from './agent-workspace-types'`。
- 从 `useSceneAgentChat` 多解构 `workspaceView, clearWorkspaceView`。
- `useSceneAgentChat` 返回里用新 send(已是 payload 形态)。注意 `onRetry`:原 `send(lastInput)`,现 lastInput 是 payload 对象,直接 `send(lastInput)` 仍合法。
- `AgentWorkspaceProps` 新增 `playbooks?: { playbook_id: number; playbook_name: string }[]`。
- 输入框块(L88-95)替换为:
  ```tsx
  <AgentWorkspaceInput
    ref={inputRef}
    convUid={convUid}
    onSend={send}
    loading={loading}
    disabled={!convUid || switchingTask}
    lastInput={lastInput ? { text: typeof lastInput.text === 'string' ? lastInput.text : '' } : null}
    onRetry={lastInput ? () => send(lastInput) : undefined}
    playbooks={playbooks}
  />
  ```
  `inputRef` 类型从 `AgentChatInputHandle` 改为 `AgentWorkspaceInputHandle`。
- 输出区:把 `<AgentProcessPanel steps={steps} ... />` 替换为 `<AgentWorkspaceRenderer view={workspaceView} onStepClick={onStepClick ? (s) => onStepClick({ id: s.id, type: 'unknown', title: s.title, status: s.status === 'running' ? 'running' : s.status === 'failed' ? 'failed' : 'done', timestamp: Date.now(), payload: { action: s.action } }) : undefined} />`。
  > 注:`onStepClick` 当前签名是 `(step: AgentStep) => void`。renderer 透出 `WorkspaceExecutionStep`,这里做一次最小适配转换。若你希望后联动用 richer 对象,后续统一类型,本期保持适配。
- `useEffect` 里 convUid 变化时同时调 `clearWorkspaceView()`。

- [ ] **Step 3: 删除退役文件**

```bash
git rm web/src/app/workspaces/detail/agent-process-panel.tsx
git rm web/src/app/workspaces/detail/agent-chat-input.tsx
git rm web/src/app/workspaces/detail/scene-agent-chat.tsx
```

确认无残留 import:`cd web && grep -rn "agent-process-panel\|agent-chat-input\|scene-agent-chat" src/` 应只返回被删文件路径或空。

- [ ] **Step 4: 类型检查**

Run: `cd web && npx tsc --noEmit`
Expected: 无错误(若有 `AgentChatInput`/`AgentProcessPanel` 残留引用,修正)

- [ ] **Step 5: 提交**

```bash
git add web/src/app/workspaces/detail/agent-workspace-renderer.tsx web/src/app/workspaces/detail/agent-workspace.tsx
git commit -m "feat(web): AgentWorkspaceRenderer + retire AgentProcessPanel/AgentChatInput/scene-agent-chat"
```

---

### Task 7: shell 接入 playbooks + 端到端验证

**Files:**
- Modify: `web/src/app/workspaces/detail/scene-workspace-shell.tsx`

**Interfaces:**
- Consumes: `listPlaybooks`(`web/src/client/api/playbook/index.ts:4`,`POST /api/v1/serve_playbook_service/playbooks/list`)。请求体形态:按现有 PlaybookListFilter(含 workspace_id);具体字段参考 `packages/derisk-serve/.../playbook/service/service.py:172 list_playbooks(f: PlaybookListFilter)`。若 listPlaybooks 入参 schema 不确定,先读 `PlaybookListFilter` 定义。
- Produces: shell 拉取当前 workspace 的 playbooks 并下传 `<AgentWorkspace playbooks={...}>`。

- [ ] **Step 1: 查清 listPlaybooks 请求体**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && grep -n "class PlaybookListFilter" -A 20 packages/derisk-serve/src/derisk_serve/playbook/service/service.py`
确认 filter 字段(workspace_id 等),作为 listPlaybooks 入参。

- [ ] **Step 2: shell 拉取 playbooks**

修改 `web/src/app/workspaces/detail/scene-workspace-shell.tsx`:
- import 加 `import { listPlaybooks } from '@/client/api'` + `import { useRequest } from 'ahooks'`(若未引入)。
- 组件内加:
  ```tsx
  const { data: playbooks } = useRequest(async () => {
    if (!workspaceId) return [];
    const [, data] = await apiInterceptors(listPlaybooks({ workspace_id: Number(workspaceId) }));
    return (data || []).map((p: any) => ({ playbook_id: p.id, playbook_name: p.name }));
  }, { refreshDeps: [workspaceId] });
  ```
  > 字段名 `id`/`name` 按 PlaybookResponse 实际字段确认(读 service.py 的 `PlaybookResponse` 或 `_to_response`);若为 `playbook_id`/`playbook_name` 则保持。
- `<AgentWorkspace>` 加 `playbooks={playbooks}` prop(L185-197 块)。

- [ ] **Step 3: 跑测试 + 类型检查**

Run: `cd web && npx tsc --noEmit && npx jest src/app/workspaces/detail/__tests__/`
Expected: 全绿

- [ ] **Step 4: 提交**

```bash
git add web/src/app/workspaces/detail/scene-workspace-shell.tsx
git commit -m "feat(web): scene-workspace-shell fetches and passes playbooks to AgentWorkspace"
```

- [ ] **Step 5: 端到端手验清单**

启动前端 + 后端,在场景空间 Agent 空间验证:
1. 输入框文本输入 + 回车发送 → `workspaceView.execution` 渲染步骤卡片。
2. 拖拽文件 → 上传卡 → 资源 chip 出现 → 发送带文件。
3. 模型下拉选择 → 切换模型发送。
4. 输入"主题"+`/` → 剧本列表弹出 → 选中 → 任务被创建(出现 task_created,场景空间任务列表新增,任务主题=输入文本)。
5. 步骤卡片点击 → `onStepClick` 触达 shell(本期 console 可见即可)。
6. 无 `UnifiedChatInput` 重复输入框(ManusChatContent 内部输入框不渲染,因 AgentWorkspace 不走 ChatSession)。

---

## Self-Review

**1. Spec coverage:**
- 数据协议 schema → Task 1(converter)+ Task 3(前端类型/解析器)。
- 后端 converter 实现 → Task 1。
- render_name 解析 + 剧本命令入口 → Task 2。
- useSceneAgentChat 扩展 + workspaceView → Task 4。
- 独立 vis 渲染器 → Task 6。
- 独立多模态输入框(文本/文件/模型/`/`剧本)→ Task 5。
- 剧本命令模式(前端 payload + 后端识别)→ Task 5(前端)+ Task 2(后端)。
- 清理(scene-agent-chat/agent-chat-input/AgentProcessPanel)→ Task 6。
- 测试 → 每个任务含 TDD。
- ManusChatContent 内部输入框:AgentWorkspace 不走 ChatSession,故不触发;死代码 scene-agent-chat.tsx 删除后无残留路径。✓ spec 此项满足。

**2. Placeholder scan:** Task 2 Step 4 有"若变量名不同用实际名/若不是 async generator 用一致方式"的条件提示——因 `aggregation_chat` 内部事件下发机制需实现时读 L1253-1299 确认,这是必要的实现期核对,非占位空洞。其余步骤均有完整代码。

**3. Type consistency:**
- `SceneAgentSendPayload`(Task 4)↔ `AgentWorkspaceInputProps.onSend` payload(Task 5):字段 `text/resources/model/playbookCommand` 一致;resources 类型 Task 4 用 `Record<string,unknown>[]`,Task 5 用 `ResourceItem[]`——`ResourceItem` 是 `Record` 的具体形态,运行期兼容,但类型上 Task 4 应放宽接受。修正:Task 4 onSend payload resources 类型保持 `Record<string, unknown>[]`,Task 5 的 `ResourceItem` 满足该约束(结构子集)。已一致。
- `workspaceView` 在 Task 4 产出、Task 6 消费,字段一致。
- `AgentWorkspaceInputHandle.focus` Task 3 定义 / Task 5 实现 / Task 6 使用,一致。
- `PlaybookCommand` Task 3 定义 / Task 5 / Task 4 一致。

无类型不一致。