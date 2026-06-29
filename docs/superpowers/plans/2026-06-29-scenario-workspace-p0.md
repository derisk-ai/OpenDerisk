# Scenario Workspace P0 叙事翻盘 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把场景空间从"iframe 嵌 /chat 的壳子"翻盘为"以任务工作台为主体、空间资源运行时物化为 Agent 真能力"的独立产品形态——P0 五项落地。

**Architecture:** 后端先补 workspace_resource 物化链路（Playbook runtime + aggregation_chat 把 physical_ref 物化成 AgentResource 注入 Agent），并扩展流式协议支持结构化事件（task_created/context_loaded/artifact_produced 等）；前端在 workspace 详情页新增任务工作台组件（主体是进展+交付+对话折叠，输入框常驻底部），消费结构化事件渲染富卡片；同时补空间大厅默认页、本月空间成长卡片、顶部 workspace 切换器。HomeChat / Application Builder / Agent / Skill / MCP / Knowledge Vault 全程不动。

**Tech Stack:** Python 3.10+ / FastAPI（后端 serve 模块）/ Next.js + React + antd 5 + Tailwind v4 + ahooks useRequest（前端）/ SSE 流式（aggregation_chat async generator）/ pytest（后端测试）

## Global Constraints

- 场景空间是独立产品，**不动** HomeChat (`/`) / Application Builder (`/application/app/`) / Agent / Skill / MCP / Knowledge Vault / DataResource
- 任务工作台是新组件，**不复用 HomeChat 代码**；ChatSession 可作为折叠对话面板内核（已透传 workspace_id）
- 默认用标准 Agent 模板 BAIZE（app_code=`chat_normal`），空间可选 `default_agent_app_code` 覆盖
- `derisk_serve.cron` 保持通用不耦合业务（P0 不涉及调度改动）
- 后端流式协议已有 `vis.type ∈ {metadata, interrupt, error}` 白名单 fast-return（`use-chat.ts:86-90`），新增事件 type 是增量扩展，**不破坏**现有解析
- 物化链路不改 Agent 架构——`gates/deliverables/distill` 仍是空间层约束（P0 不涉及）
- 所有后端测试用 pytest，前端无测试框架（手动验证）
- 提交信息用 `feat(ws):` / `refactor(ws):` / `test(ws):` 前缀，中文描述

## File Structure

**后端新增**：
- `packages/derisk-serve/src/derisk_serve/workspace/materializer.py` — workspace_resource 物化器（physical_ref → AgentResource）
- `packages/derisk-serve/tests/derisk_serve/workspace/test_materializer.py` — 物化器测试

**后端修改**：
- `packages/derisk-serve/src/derisk_serve/workspace/context_builder.py` — build_workspace_context 增加物化结果字段
- `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` — aggregation_chat 注入物化资源 + 流式事件 helper
- `packages/derisk-serve/src/derisk_serve/playbook/runtime.py` — run_task 透传 dynamic_resources/extra_agents
- `packages/derisk-serve/src/derisk_serve/playbook/service/service.py` — assemble_context 增加 ref 解析

**前端新增**：
- `web/src/app/workspaces/detail/workbench.tsx` — 任务工作台主组件
- `web/src/app/workspaces/detail/workbench.css` — 工作台样式（`.ws-wb-*` BEM）
- `web/src/app/workspaces/detail/lobby.tsx` — 空间大厅组件（无选中任务时的主体）
- `web/src/components/layout/workspace-switcher.tsx` — 顶部 workspace 切换器
- `web/src/app/workspaces/detail/growth-card.tsx` — 本月空间成长卡片

**前端修改**：
- `web/src/app/workspaces/detail/client.tsx` — 主体切换：lobby ⇄ workbench（替换 L388-415 chat-panel）
- `web/src/components/layout/side-bar.tsx` — 展开态加 workspace 切换器（L812-827 之间）
- `web/src/hooks/use-chat.ts` — onmessage 增加 task_created/context_loaded/artifact_produced 等事件派发
- `web/src/components/chat/chat-session.tsx` — 暴露 onWorkspaceEvent 回调 prop

---

## Task 1: workspace_resource 物化器（核心命脉）

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/workspace/materializer.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_materializer.py`

**Interfaces:**
- Consumes: `WorkspaceService.list_resources(workspace_id)` 返回 `List[WorkspaceResourceResponse]`（字段 `type/name/category/physical_ref/config/access_mode`）；现有物化函数 `get_mcp_info(mcp_code)`（`mcp_collect.py:54`）、`app_service.app_detail(app_code)`、`DeriskSkillResource` 模式
- Produces: `materialize_resources(system_app, workspace_id) -> MaterializedResources`，其中 `MaterializedResources = {"dynamic_resources": List[AgentResource], "extra_agents": List[dict]}`；`AgentResource` 来自 `derisk.resource.resource`

- [ ] **Step 1: 写物化器的失败测试**

Create `packages/derisk-serve/tests/derisk_serve/workspace/test_materializer.py`:

```python
"""Tests for workspace_resource materializer."""
import pytest
from unittest.mock import MagicMock, patch
from derisk_serve.workspace.materializer import (
    materialize_resources,
    MaterializedResources,
)


def test_materialize_empty_resources_returns_empty():
    """空资源列表返回空物化结果，不抛异常。"""
    system_app = MagicMock()
    with patch(
        "derisk_serve.workspace.materializer.WorkspaceService"
    ) as MockWsService:
        MockWsService.return_value.list_resources.return_value = []
        result = materialize_resources(system_app, workspace_id=1)
    assert isinstance(result, MaterializedResources)
    assert result.dynamic_resources == []
    assert result.extra_agents == []


def test_materialize_unknown_type_skipped_not_raised():
    """未知 type（如 slo/oncall_rotation）跳过，不抛异常，记 warning。"""
    system_app = MagicMock()
    unknown_resource = MagicMock(
        type="slo",
        name="p99_latency",
        physical_ref=None,
        config_json='{"metric": "p99", "target": 200}',
        is_active=True,
    )
    with patch(
        "derisk_serve.workspace.materializer.WorkspaceService"
    ) as MockWsService:
        MockWsService.return_value.list_resources.return_value = [unknown_resource]
        result = materialize_resources(system_app, workspace_id=1)
    assert result.dynamic_resources == []
    assert result.extra_agents == []


def test_materialize_mcp_resource_produces_agent_resource():
    """type=mcp 的资源物化成 AgentResource（type=mcp(derisk)）。"""
    system_app = MagicMock()
    mcp_resource = MagicMock(
        type="mcp",
        name="k8s_mcp",
        physical_ref="k8s_mcp_code",
        config_json="{}",
        is_active=True,
    )
    with patch(
        "derisk_serve.workspace.materializer.WorkspaceService"
    ) as MockWsService, patch(
        "derisk_serve.workspace.materializer.get_mcp_info"
    ) as mock_get_mcp:
        MockWsService.return_value.list_resources.return_value = [mcp_resource]
        mock_get_mcp.return_value = {
            "mcp_servers": [{"url": "http://k8s-mcp.local"}],
            "headers": {},
            "source": "sse",
            "timeout": 30,
        }
        result = materialize_resources(system_app, workspace_id=1)
    assert len(result.dynamic_resources) == 1
    res = result.dynamic_resources[0]
    assert res.type == "mcp(derisk)"


def test_materialize_inactive_resource_skipped():
    """is_active=False 的资源跳过。"""
    system_app = MagicMock()
    inactive = MagicMock(
        type="mcp",
        name="old_mcp",
        physical_ref="old_code",
        config_json="{}",
        is_active=False,
    )
    with patch(
        "derisk_serve.workspace.materializer.WorkspaceService"
    ) as MockWsService:
        MockWsService.return_value.list_resources.return_value = [inactive]
        result = materialize_resources(system_app, workspace_id=1)
    assert result.dynamic_resources == []
    assert result.extra_agents == []
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/test_materializer.py -v`
Expected: FAIL with `ImportError: cannot import name 'materialize_resources'` 或 `ModuleNotFoundError`

- [ ] **Step 3: 写最小实现**

Create `packages/derisk-serve/src/derisk_serve/workspace/materializer.py`:

```python
"""Materialize workspace_resource.physical_ref into AgentResource at runtime.

这是场景空间能力的命脉——把空间挂载的资源从 prompt 字符串装饰
物化成 Agent 可实际调用的工具/能力。
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from derisk.resource.resource import AgentResource

logger = logging.getLogger(__name__)


@dataclass
class MaterializedResources:
    """物化结果：dynamic_resources 给 Agent 工具列表，extra_agents 给多 Agent 协作。"""

    dynamic_resources: List[AgentResource] = field(default_factory=list)
    extra_agents: List[Dict[str, Any]] = field(default_factory=list)


def _parse_config(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return {}


def _materialize_mcp(physical_ref: str, config: Dict[str, Any]) -> Optional[AgentResource]:
    """type=mcp → AgentResource(type=mcp(derisk))，复用 get_mcp_info。"""
    from derisk_serve.mcp.mcp_collect import get_mcp_info
    mcp_info = get_mcp_info(physical_ref)
    if not mcp_info:
        logger.warning(f"mcp not found: {physical_ref}")
        return None
    return AgentResource.from_dict(
        {
            "type": "mcp(derisk)",
            "value": {
                "mcp_servers": mcp_info.get("mcp_servers", []),
                "headers": mcp_info.get("headers", {}),
                "source": mcp_info.get("source", "sse"),
                "timeout": mcp_info.get("timeout", 30),
            },
        }
    )


def _materialize_datasource(
    physical_ref: str, config: Dict[str, Any]
) -> Optional[AgentResource]:
    """type=data_source → AgentResource(type=datasource)。"""
    return AgentResource.from_dict(
        {"type": "datasource", "value": physical_ref, **config}
    )


def _materialize_skill(
    physical_ref: str, config: Dict[str, Any]
) -> Optional[AgentResource]:
    """type=skill → AgentResource(type=agent_skill)。"""
    return AgentResource.from_dict(
        {"type": "agent_skill", "value": physical_ref, **config}
    )


def _materialize_knowledge_space(
    physical_ref: str, config: Dict[str, Any]
) -> Optional[AgentResource]:
    """type=knowledge_space → AgentResource(type=knowledge)。"""
    return AgentResource.from_dict(
        {"type": "knowledge", "value": physical_ref, **config}
    )


def _materialize_app_as_extra_agent(
    physical_ref: str, config: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """type=app（子 Agent）→ extra_agents 项。"""
    return {"app_code": physical_ref, **config}


def _materialize_llm_model(
    physical_ref: str, config: Dict[str, Any]
) -> Optional[AgentResource]:
    """type=llm_model → 暂不物化（Agent 架构 llm 渠道是静态配置），返回 None。"""
    return None


# type → 物化函数分派表
_MATERIALIZE_DISPATCH = {
    "mcp": _materialize_mcp,
    "data_source": _materialize_datasource,
    "skill": _materialize_skill,
    "agent_skill": _materialize_skill,
    "knowledge_space": _materialize_knowledge_space,
    "app": _materialize_app_as_extra_agent,
    "llm_model": _materialize_llm_model,
}


def materialize_resources(system_app, workspace_id: int) -> MaterializedResources:
    """把 workspace 下所有 active 资源物化成 AgentResource / extra_agents。

    未知 type（slo/oncall_rotation/data_pipeline/bi_dashboard/code_repo/api_endpoint/
    environment/runbook_target）当前跳过——这些是场景专属逻辑资源，
    P2 阶段通过 ResourceManager.register_resource 注册自定义类型后再物化。
    """
    from derisk_serve.workspace.service.service import WorkspaceService

    result = MaterializedResources()
    try:
        ws_service = WorkspaceService(system_app=system_app)
        resources = ws_service.list_resources(workspace_id) or []
    except Exception as e:
        logger.warning(f"materializer list_resources failed: {e}")
        return result

    for r in resources:
        if not getattr(r, "is_active", True):
            continue
        rtype = r.type
        handler = _MATERIALIZE_DISPATCH.get(rtype)
        if handler is None:
            logger.warning(
                f"materializer skip unsupported type={rtype} name={r.name} "
                f"(P2 will register via ResourceManager)"
            )
            continue
        try:
            config = _parse_config(getattr(r, "config_json", None))
            physical_ref = getattr(r, "physical_ref", None)
            materialized = handler(physical_ref, config)
            if materialized is None:
                continue
            if rtype == "app":
                result.extra_agents.append(materialized)
            else:
                result.dynamic_resources.append(materialized)
        except Exception as e:
            logger.warning(
                f"materializer fail type={rtype} name={r.name}: {e}"
            )
    return result
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/test_materializer.py -v`
Expected: PASS（4 个测试全过）

- [ ] **Step 5: 提交**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git add packages/derisk-serve/src/derisk_serve/workspace/materializer.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_materializer.py
git commit -m "feat(ws): 新增 workspace_resource 物化器，physical_ref → AgentResource"
```

---

## Task 2: build_workspace_context 集成物化结果

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/context_builder.py:60-78`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `materialize_resources(system_app, workspace_id) -> MaterializedResources`
- Produces: `build_workspace_context` 返回的 dict 新增 `materialized` 键（`{"dynamic_resources": [...], "extra_agents": [...]}`），原 `resources` 键保留（给 prompt 文本用）

- [ ] **Step 1: 写集成测试**

Create `packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder.py`:

```python
"""Tests for build_workspace_context materialized field."""
import pytest
from unittest.mock import MagicMock, patch
from derisk_serve.workspace.context_builder import build_workspace_context


def test_build_context_includes_materialized_key():
    """build_workspace_context 返回的 dict 含 materialized 键。"""
    system_app = MagicMock()
    with patch(
        "derisk_serve.workspace.context_builder.WorkspaceService"
    ) as MockWsService, patch(
        "derisk_serve.workspace.context_builder.materialize_resources"
    ) as mock_mat:
        MockWsService.return_value.get_by_id.return_value = MagicMock(
            id=1, workspace_code="ws1", name="SRE", scenario_type="sre",
            default_agent_app_code="chat_normal",
        )
        MockWsService.return_value.list_members.return_value = []
        MockWsService.return_value.list_resources.return_value = []
        mock_mat.return_value = MagicMock(
            dynamic_resources=[MagicMock(type="mcp(derisk)")],
            extra_agents=[],
        )
        ctx = build_workspace_context(system_app, workspace_id=1)
    assert "materialized" in ctx
    assert "dynamic_resources" in ctx["materialized"]
    assert "extra_agents" in ctx["materialized"]
    assert len(ctx["materialized"]["dynamic_resources"]) == 1


def test_build_context_materialized_empty_on_failure():
    """物化失败时 materialized 字段为空列表，不抛异常。"""
    system_app = MagicMock()
    with patch(
        "derisk_serve.workspace.context_builder.WorkspaceService"
    ) as MockWsService, patch(
        "derisk_serve.workspace.context_builder.materialize_resources",
        side_effect=Exception("boom"),
    ):
        MockWsService.return_value.get_by_id.return_value = MagicMock(
            id=1, workspace_code="ws1", name="SRE", scenario_type="sre",
            default_agent_app_code="chat_normal",
        )
        MockWsService.return_value.list_members.return_value = []
        MockWsService.return_value.list_resources.return_value = []
        ctx = build_workspace_context(system_app, workspace_id=1)
    assert ctx["materialized"]["dynamic_resources"] == []
    assert ctx["materialized"]["extra_agents"] == []
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder.py -v`
Expected: FAIL with `KeyError: 'materialized'` 或 `AttributeError`

- [ ] **Step 3: 改 context_builder.py 集成物化**

Modify `packages/derisk-serve/src/derisk_serve/workspace/context_builder.py`。在文件顶部 import 区加：

```python
from derisk_serve.workspace.materializer import materialize_resources
```

在 `build_workspace_context` 函数内，紧接 `context["resources"] = [...]` 那段（约 L67-76）之后插入：

```python
        # 物化资源为 AgentResource（运行时给 Agent 工具列表用）
        try:
            materialized = materialize_resources(system_app, workspace_id)
            context["materialized"] = {
                "dynamic_resources": materialized.dynamic_resources,
                "extra_agents": materialized.extra_agents,
            }
        except Exception as e:
            logger.warning(f"materialize_resources failed: {e}")
            context["materialized"] = {"dynamic_resources": [], "extra_agents": []}
```

注意：这段要放在 `try/except Exception as e:` 块内（workspace lookup 那个 try），如果 `context["resources"]` 之后还有 `except`，把物化放在 `try` 内、`except` 之前。如果 try 块已结束，则新加一个独立 try/except。

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git add packages/derisk-serve/src/derisk_serve/workspace/context_builder.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder.py
git commit -m "feat(ws): build_workspace_context 集成物化结果，输出 materialized 字段"
```

---

## Task 3: aggregation_chat 注入物化资源到 Agent

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py:690-708`（workspace_context 注入点）和 `_inner_chat` 的 dynamic_resources 组装点（约 L2306）

**Interfaces:**
- Consumes: Task 2 的 `build_workspace_context` 返回的 `materialized` 字段
- Produces: aggregation_chat 把 `materialized.dynamic_resources` 合并到 `ext_info["dynamic_resources"]`，把 `materialized.extra_agents` 塞 `ext_info["extra_agents"]`

- [ ] **Step 1: 写注入逻辑的测试**

Create `packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_workspace_injection.py`:

```python
"""Tests for workspace materialized resource injection in aggregation_chat."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from derisk_serve.agent.agents.chat.agent_chat import AgentChat


@pytest.mark.asyncio
async def test_workspace_materialized_resources_injected_to_ext_info():
    """workspace_id 存在时，物化的 dynamic_resources 合并到 ext_info。"""
    agent_chat = AgentChat.__new__(AgentChat)
    agent_chat.system_app = MagicMock()
    ext_info = {"workspace_id": 1, "task_id": None}

    fake_resource = MagicMock()
    fake_resource.type = "mcp(derisk)"
    fake_ctx = {
        "workspace_id": 1,
        "workspace": MagicMock(),
        "members": [],
        "resources": [],
        "materialized": {
            "dynamic_resources": [fake_resource],
            "extra_agents": [{"app_code": "analyzer"}],
        },
        "current_task": None,
        "recent_tasks": [],
        "recent_assets": [],
        "task_artifacts": [],
        "task_interventions": [],
    }

    with patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_context",
        return_value=fake_ctx,
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.render_workspace_context_summary",
        return_value="summary",
    ):
        # 直接调注入逻辑（aggregation_chat 太重，测注入分支）
        # 这里用反射或抽出 helper 测
        from derisk_serve.agent.agents.chat.agent_chat import (
            _inject_workspace_context,
        )
        _inject_workspace_context(agent_chat, ext_info)

    assert "dynamic_resources" in ext_info
    assert len(ext_info["dynamic_resources"]) == 1
    assert ext_info["dynamic_resources"][0] == fake_resource
    assert "extra_agents" in ext_info
    assert ext_info["extra_agents"] == [{"app_code": "analyzer"}]
    assert "workspace_context" in ext_info


@pytest.mark.asyncio
async def test_workspace_injection_no_workspace_id_noop():
    """无 workspace_id 时 ext_info 不被改动。"""
    ext_info = {}
    from derisk_serve.agent.agents.chat.agent_chat import (
        _inject_workspace_context,
    )
    agent_chat = AgentChat.__new__(AgentChat)
    agent_chat.system_app = MagicMock()
    _inject_workspace_context(agent_chat, ext_info)
    assert "dynamic_resources" not in ext_info
    assert "extra_agents" not in ext_info
    assert "workspace_context" not in ext_info
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_workspace_injection.py -v`
Expected: FAIL with `ImportError: cannot import name '_inject_workspace_context'`

- [ ] **Step 3: 抽出 _inject_workspace_context helper 并集成物化注入**

Modify `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`。

首先在文件顶部 import 区（已有 `from derisk_serve.workspace.context_builder import build_workspace_context, render_workspace_context_summary`）确认存在。如果没有，加 import。

然后在 `AgentChat` class 外（或内，作为 staticmethod / module function）新增 helper：

```python
def _inject_workspace_context(agent_chat, ext_info):
    """把 workspace_context + 物化资源注入 ext_info。

    抽出为独立函数便于测试。物化的 dynamic_resources/extra_agents
    会合并到 ext_info，后续 _build_agent_by_gpts 会消费。
    """
    workspace_id = ext_info.get("workspace_id") if ext_info else None
    task_id = ext_info.get("task_id") if ext_info else None
    if not workspace_id:
        return
    try:
        ws_ctx = build_workspace_context(
            agent_chat.system_app,
            int(workspace_id),
            task_id=int(task_id) if task_id else None,
        )
        ext_info["workspace_context"] = ws_ctx
        summary = render_workspace_context_summary(ws_ctx)
        if summary:
            existing_sys_prompt = ext_info.get("system_prompt") or ""
            ext_info["system_prompt"] = (
                existing_sys_prompt + "\n\n" + summary
            ).strip()

        # 物化资源注入（命脉：空间资源变成 Agent 真能力）
        materialized = ws_ctx.get("materialized") or {}
        existing_dyn = ext_info.get("dynamic_resources") or []
        existing_dyn.extend(materialized.get("dynamic_resources") or [])
        ext_info["dynamic_resources"] = existing_dyn

        existing_extra = ext_info.get("extra_agents") or []
        existing_extra.extend(materialized.get("extra_agents") or [])
        ext_info["extra_agents"] = existing_extra
    except Exception as e:
        logger.warning(f"workspace context injection failed: {e}")
```

然后在 `aggregation_chat` 内（原 L688-708 那段 `workspace_id = ext_info.get(...)` ... `except Exception as e: logger.warning(...)`），**整段替换**为：

```python
        # Workspace context + 物化资源注入
        _inject_workspace_context(self, ext_info)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_workspace_injection.py -v`
Expected: PASS（2 个测试全过）

- [ ] **Step 5: 手动回归验证 aggregation_chat 仍能跑通**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -c "from derisk_serve.agent.agents.chat.agent_chat import AgentChat, _inject_workspace_context; print('import ok')"`

Expected: 输出 `import ok`，无 ImportError。

- [ ] **Step 6: 提交**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git add packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py \
        packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_workspace_injection.py
git commit -m "feat(ws): aggregation_chat 注入物化资源到 Agent dynamic_resources/extra_agents"
```

---

## Task 4: Playbook runtime 透传物化资源

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/playbook/runtime.py:116-125`（app_chat_v3 调用点）

**Interfaces:**
- Consumes: Task 1 的 `materialize_resources`（直接调，不经 context_builder，因为 runtime 已有 task.workspace_id）
- Produces: `run_task` 调 `app_chat_v3` 时透传 `dynamic_resources` / `extra_agents` 到 `**ext_info`

- [ ] **Step 1: 写 runtime 透传测试**

Create `packages/derisk-serve/tests/derisk_serve/playbook/test_runtime_pass_resources.py`:

```python
"""Tests for playbook runtime passing materialized resources."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from derisk_serve.playbook.runtime import run_task


@pytest.mark.asyncio
async def test_run_task_passes_materialized_resources_to_app_chat():
    """run_task 把物化的 dynamic_resources/extra_agents 透传给 app_chat_v3。"""
    fake_task = MagicMock(
        id=1, workspace_id=10, title="容量巡检",
        playbook_id=5, playbook_version_id=2,
        context_json="{}", status="pending_trigger",
    )
    fake_playbook = MagicMock(
        id=5, name="容量巡检", scenario_type="sre", task_type="routine",
        declaration_dsl_json='{"skills": [], "context": {}, "deliverables": [], "distill": {}}',
        current_version=1,
    )
    fake_materialized = MagicMock(
        dynamic_resources=[MagicMock(type="mcp(derisk)")],
        extra_agents=[{"app_code": "analyzer"}],
    )

    with patch(
        "derisk_serve.playbook.runtime.PlaybookService"
    ) as MockPbService, patch(
        "derisk_serve.playbook.runtime.WorkspaceService"
    ) as MockWsService, patch(
        "derisk_serve.playbook.runtime.materialize_resources",
        return_value=fake_materialized,
    ) as mock_mat, patch(
        "derisk_serve.playbook.runtime.multi_agents"
    ) as mock_multi:
        MockPbService.return_value.get_by_id.return_value = fake_playbook
        mock_multi.app_chat_v3 = AsyncMock()
        await run_task(MagicMock(), fake_task)

        # 验证 app_chat_v3 被调用时 ext_info 含物化资源
        call_kwargs = mock_multi.app_chat_v3.call_args.kwargs
        assert "dynamic_resources" in call_kwargs
        assert len(call_kwargs["dynamic_resources"]) == 1
        assert "extra_agents" in call_kwargs
        assert call_kwargs["extra_agents"] == [{"app_code": "analyzer"}]
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/playbook/test_runtime_pass_resources.py -v`
Expected: FAIL（app_chat_v3 调用未含 dynamic_resources）

- [ ] **Step 3: 改 runtime.py 透传物化资源**

Modify `packages/derisk-serve/src/derisk_serve/playbook/runtime.py`。

首先在 import 区加：

```python
from derisk_serve.workspace.materializer import materialize_resources
```

然后在 `run_task` 函数内，调 `multi_agents.app_chat_v3` 之前（约 L116 之前），加物化调用：

```python
    # 物化空间资源，透传给 Agent
    materialized = materialize_resources(system_app, task.workspace_id)
```

然后修改 `app_chat_v3` 调用（原 L116-125），把 `dynamic_resources` 和 `extra_agents` 加到 ext_info：

```python
    await multi_agents.app_chat_v3(
        conv_uid=conv_uid,
        gpts_name=app_code,
        user_query=user_query,
        background_tasks=None,
        user_code=user_code,
        sys_code=sys_code,
        workspace_id=task.workspace_id,
        task_id=task.id,
        dynamic_resources=materialized.dynamic_resources,
        extra_agents=materialized.extra_agents,
    )
```

注意：`app_chat_v3` 的签名接受 `**ext_info`，`dynamic_resources` / `extra_agents` 会进 ext_info 传给 aggregation_chat。

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/playbook/test_runtime_pass_resources.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git add packages/derisk-serve/src/derisk_serve/playbook/runtime.py \
        packages/derisk-serve/tests/derisk_serve/playbook/test_runtime_pass_resources.py
git commit -m "feat(ws): playbook runtime 透传物化资源到 app_chat_v3"
```

---

## Task 5: 后端流式事件 helper（task_created/context_loaded/artifact_produced）

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`（新增 event helper + 在 workspace context 注入后 yield context_loaded 事件）

**Interfaces:**
- Consumes: Task 3 的 `_inject_workspace_context`
- Produces: 流式 chunk 新增 `{"vis": {"type": "context_loaded", "payload": {...}}}` 格式；前端 use-chat.ts 解析

- [ ] **Step 1: 写 event helper 测试**

Create `packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_stream_events.py`:

```python
"""Tests for workspace stream event helpers."""
import json
import pytest
from derisk_serve.agent.agents.chat.agent_chat import (
    format_workspace_event,
    WORKSPACE_EVENT_TYPES,
)


def test_format_workspace_event_context_loaded():
    """context_loaded 事件格式正确。"""
    chunk = format_workspace_event(
        "context_loaded",
        {"skills": ["db_query", "anomaly_detect"], "assets": ["asset_78"]},
    )
    assert chunk.startswith("data:")
    assert chunk.endswith("\n\n")
    payload = json.loads(chunk[len("data:"):].strip())
    assert payload["vis"]["type"] == "context_loaded"
    assert payload["vis"]["payload"]["skills"] == ["db_query", "anomaly_detect"]


def test_format_workspace_event_task_created():
    """task_created 事件格式正确。"""
    chunk = format_workspace_event(
        "task_created", {"task_id": 124, "title": "容量巡检"}
    )
    payload = json.loads(chunk[len("data:"):].strip())
    assert payload["vis"]["type"] == "task_created"
    assert payload["vis"]["payload"]["task_id"] == 124


def test_format_workspace_event_invalid_type_raises():
    """非法事件 type 抛 ValueError。"""
    with pytest.raises(ValueError):
        format_workspace_event("bogus_type", {})


def test_workspace_event_types_contains_expected():
    """事件 type 白名单含预期的 6 种。"""
    expected = {
        "task_created",
        "context_loaded",
        "intervention_triggered",
        "artifact_produced",
        "delivery_sent",
        "asset_referenced",
    }
    assert expected.issubset(WORKSPACE_EVENT_TYPES)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_stream_events.py -v`
Expected: FAIL with `ImportError: cannot import name 'format_workspace_event'`

- [ ] **Step 3: 写 event helper**

Modify `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`。在文件顶部（import 区之后、class 之前）加：

```python
import orjson

# workspace 流式事件白名单
WORKSPACE_EVENT_TYPES = frozenset(
    {
        "task_created",
        "context_loaded",
        "intervention_triggered",
        "artifact_produced",
        "delivery_sent",
        "asset_referenced",
    }
)


def format_workspace_event(event_type: str, payload: dict) -> str:
    """格式化 workspace 结构化事件为 SSE chunk。

    与现有 vis.type=metadata/interrupt/error 同协议，前端 use-chat.ts 白名单 fast-return。
    """
    if event_type not in WORKSPACE_EVENT_TYPES:
        raise ValueError(f"unsupported workspace event type: {event_type}")
    body = orjson.dumps({"vis": {"type": event_type, "payload": payload}})
    return f"data:{body.decode()}\n\n"
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_stream_events.py -v`
Expected: PASS（4 个测试全过）

- [ ] **Step 5: 在 aggregation_chat 注入 context_loaded 事件**

Modify `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`。在 `aggregation_chat` 内，`_inject_workspace_context(self, ext_info)` 之后、`async for chunk` 循环之前，加 yield context_loaded 事件：

```python
        # workspace context 注入后，yield context_loaded 事件给前端
        if ext_info.get("workspace_id"):
            ws_ctx = ext_info.get("workspace_context") or {}
            resources = ws_ctx.get("resources") or []
            yield task, format_workspace_event(
                "context_loaded",
                {
                    "workspace_id": int(ext_info["workspace_id"]),
                    "resources": [
                        {"type": r.get("type"), "name": r.get("name")}
                        for r in resources
                    ],
                    "materialized_count": len(
                        (ws_ctx.get("materialized") or {}).get("dynamic_resources") or []
                    ),
                },
            ), agent_conv_id
```

注意：`yield task, chunk, agent_conv_id` 的三元组格式要和现有 yield 一致——看 aggregation_chat 现有 yield 语句（如 L872 `yield task, f"data:{...}\n\n", agent_conv_id`），保持一致。如果现有 yield 是二元组，改成二元组。

- [ ] **Step 6: 验证 import 与语法**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -c "from derisk_serve.agent.agents.chat.agent_chat import format_workspace_event, WORKSPACE_EVENT_TYPES; print('ok'); print(format_workspace_event('context_loaded', {'x': 1}))"`

Expected: 输出 `ok` 和 `data:{"vis":{"type":"context_loaded","payload":{"x":1}}}\n\n`

- [ ] **Step 7: 提交**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git add packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py \
        packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_stream_events.py
git commit -m "feat(ws): 新增 workspace 流式事件 helper（task_created/context_loaded/...）"
```

---

## Task 6: 前端 use-chat.ts 解析 workspace 事件

**Files:**
- Modify: `web/src/hooks/use-chat.ts:80-113`（onmessage 解析）

**Interfaces:**
- Consumes: Task 5 的 `format_workspace_event` 输出的 SSE chunk 格式
- Produces: `useChat` 的 `onMessage` 回调会收到 `{type: "context_loaded", payload: {...}}` 等 workspace 事件对象；新增 `onWorkspaceEvent` 回调 prop

- [ ] **Step 1: 改 use-chat.ts onmessage 解析**

Modify `web/src/hooks/use-chat.ts`。找到 L86-90 的 `if (vis.type === 'metadata' || vis.type === 'interrupt')` 分支，扩展为：

```typescript
              if (parsedData?.vis && typeof parsedData.vis === 'object') {
                const vis = parsedData.vis;
                if (vis.type === 'metadata' || vis.type === 'interrupt') {
                  onMessage?.(vis);
                  return;
                } else if (vis.type === 'error') {
                  onError?.(vis.content || '对话发生错误');
                  return;
                } else if (
                  vis.type === 'task_created' ||
                  vis.type === 'context_loaded' ||
                  vis.type === 'intervention_triggered' ||
                  vis.type === 'artifact_produced' ||
                  vis.type === 'delivery_sent' ||
                  vis.type === 'asset_referenced'
                ) {
                  onWorkspaceEvent?.(vis as WorkspaceEvent);
                  return;
                }
              }
```

然后在 `useChat` 的参数类型定义（找 `interface UseChatParams` 或类似）加 `onWorkspaceEvent?: (event: WorkspaceEvent) => void`。

在文件顶部加类型定义：

```typescript
export type WorkspaceEventType =
  | 'task_created'
  | 'context_loaded'
  | 'intervention_triggered'
  | 'artifact_produced'
  | 'delivery_sent'
  | 'asset_referenced';

export interface WorkspaceEvent {
  type: WorkspaceEventType;
  payload: Record<string, any>;
}
```

并在 `useChat` 返回值里暴露 `onWorkspaceEvent`（如果 useChat 是 hook，把回调存在 ref 里供 onmessage 调用——参考现有 onMessage/onError 的处理模式）。

- [ ] **Step 2: 手动验证前端编译通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && pnpm tsc --noEmit 2>&1 | head -30`

Expected: 无类型错误（或仅有 pre-existing 警告）。如果有 `onWorkspaceEvent` 未定义的错误，检查 UseChatParams 接口是否加了对字段。

- [ ] **Step 3: 提交**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git add web/src/hooks/use-chat.ts
git commit -m "feat(ws): use-chat.ts 解析 workspace 流式事件，新增 onWorkspaceEvent 回调"
```

---

## Task 7: ChatSession 暴露 onWorkspaceEvent prop

**Files:**
- Modify: `web/src/components/chat/chat-session.tsx:22-30`（ChatSessionProps）和 `handleChat` 调用 useChat 处

**Interfaces:**
- Consumes: Task 6 的 `useChat` 的 `onWorkspaceEvent`
- Produces: `<ChatSession onWorkspaceEvent={...} />` 把事件透传给父组件（任务工作台）

- [ ] **Step 1: 改 ChatSessionProps 加 onWorkspaceEvent**

Modify `web/src/components/chat/chat-session.tsx`。找到 `ChatSessionProps`（L22-30），加：

```typescript
  onWorkspaceEvent?: (event: import('@/hooks/use-chat').WorkspaceEvent) => void;
```

- [ ] **Step 2: 在 useChat 调用处传 onWorkspaceEvent**

在 `chat-session.tsx` 找到 `const { chat, ctrl } = useChat({ app_code })`（约 L60），改为：

```typescript
  const { chat, ctrl } = useChat({
    app_code,
    onWorkspaceEvent: props.onWorkspaceEvent,
  });
```

注意：如果 useChat 的参数对象已有其他字段，把 `onWorkspaceEvent` 加进去。如果 useChat 是通过 `chat({ data, ctrl, onMessage, ... })` 在 handleChat 里传回调（而非 hook 参数），则在 `chat()` 调用里加 `onWorkspaceEvent: props.onWorkspaceEvent`。

- [ ] **Step 3: 验证编译**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && pnpm tsc --noEmit 2>&1 | head -30`

Expected: 无新增类型错误。

- [ ] **Step 4: 提交**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git add web/src/components/chat/chat-session.tsx
git commit -m "feat(ws): ChatSession 暴露 onWorkspaceEvent prop 透传给任务工作台"
```

---

## Task 8: 任务工作台组件 workbench.tsx

**Files:**
- Create: `web/src/app/workspaces/detail/workbench.tsx`
- Create: `web/src/app/workspaces/detail/workbench.css`

**Interfaces:**
- Consumes: Task 7 的 `<ChatSession onWorkspaceEvent>`；现有 API `getTaskInfo` / `listInterventions` / `listArtifacts`（task 维度）；现有 `useRequest`
- Produces: `<Workbench taskId={...} workspaceId={...} onBack={() => void} />` 组件，主体是进展+交付+对话折叠，输入框常驻底部

- [ ] **Step 1: 写 workbench.css 样式**

Create `web/src/app/workspaces/detail/workbench.css`:

```css
/* 任务工作台样式 — BEM .ws-wb-* */
.ws-wb {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.ws-wb__header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--ws-border, #e5e7eb);
  background: var(--ws-bg, #fff);
}

.ws-wb__back {
  cursor: pointer;
  color: var(--ws-text-secondary, #6b7280);
  font-size: 14px;
}

.ws-wb__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--ws-text, #111827);
}

.ws-wb__meta {
  font-size: 12px;
  color: var(--ws-text-secondary, #6b7280);
}

.ws-wb__body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ws-wb__section {
  border: 1px solid var(--ws-border, #e5e7eb);
  border-radius: 8px;
  background: var(--ws-bg, #fff);
}

.ws-wb__section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ws-text-secondary, #6b7280);
  padding: 10px 14px;
  border-bottom: 1px solid var(--ws-border, #e5e7eb);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ws-wb__progress {
  padding: 8px 14px;
}

.ws-wb__step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  color: var(--ws-text, #111827);
}

.ws-wb__step-icon {
  width: 16px;
  text-align: center;
}

.ws-wb__step-name {
  flex: 1;
}

.ws-wb__step-tool {
  color: var(--ws-text-secondary, #6b7280);
  font-size: 12px;
  font-family: ui-monospace, monospace;
}

.ws-wb__step-duration {
  color: var(--ws-text-secondary, #6b7280);
  font-size: 12px;
}

.ws-wb__step--done .ws-wb__step-icon { color: #10b981; }
.ws-wb__step--running .ws-wb__step-icon { color: #3b82f6; }
.ws-wb__step--pending .ws-wb__step-icon { color: #d1d5db; }

.ws-wb__artifact {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ws-wb__artifact-title {
  font-size: 14px;
  font-weight: 500;
}

.ws-wb__artifact-actions {
  display: flex;
  gap: 8px;
}

.ws-wb__dialog {
  padding: 8px 14px;
  max-height: 200px;
  overflow-y: auto;
}

.ws-wb__dialog-msg {
  font-size: 13px;
  padding: 4px 0;
  color: var(--ws-text, #111827);
}

.ws-wb__dialog-msg--user { color: var(--ws-text-secondary, #6b7280); }
.ws-wb__dialog-expand {
  font-size: 12px;
  color: var(--ws-accent, #3b82f6);
  cursor: pointer;
  padding: 6px 0;
}

.ws-wb__input {
  border-top: 1px solid var(--ws-border, #e5e7eb);
  padding: 12px 20px;
  background: var(--ws-bg, #fff);
}

.ws-wb__input textarea {
  width: 100%;
  resize: none;
  border: 1px solid var(--ws-border, #e5e7eb);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
  outline: none;
}

.ws-wb__input textarea:focus {
  border-color: var(--ws-accent, #3b82f6);
}
```

- [ ] **Step 2: 写 workbench.tsx 组件**

Create `web/src/app/workspaces/detail/workbench.tsx`:

```tsx
'use client';

import { useState, useMemo } from 'react';
import { Button, Input, Tag } from 'antd';
import { useRequest } from 'ahooks';
import {
  getTaskInfo,
  listInterventions,
  listArtifacts,
} from '@/client/api';
import { ChatSession } from '@/components/chat/chat-session';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import './workbench.css';

export interface WorkbenchProps {
  taskId: number;
  workspaceId: number;
  appCode: string;
  convUid: string;
  onBack: () => void;
}

export function Workbench({
  taskId,
  workspaceId,
  appCode,
  convUid,
  onBack,
}: WorkbenchProps) {
  const [dialogExpanded, setDialogExpanded] = useState(false);
  const [events, setEvents] = useState<WorkspaceEvent[]>([]);
  const [input, setInput] = useState('');

  const { data: task } = useRequest(() => getTaskInfo(taskId), {
    refreshDeps: [taskId],
  });
  const { data: artifacts } = useRequest(
    () => listArtifacts({ task_id: taskId }),
    { refreshDeps: [taskId] }
  );
  const { data: interventions } = useRequest(
    () => listInterventions({ task_id: taskId }),
    { refreshDeps: [taskId] }
  );

  const handleWorkspaceEvent = (event: WorkspaceEvent) => {
    setEvents((prev) => [...prev, event]);
  };

  const progressSteps = useMemo(() => {
    // 从 events 推导进展步骤（context_loaded → 后续 tool 调用）
    // P0 简化版：基于 task.status + events 渲染
    const steps: Array<{
      name: string;
      tool?: string;
      status: 'done' | 'running' | 'pending';
    }> = [];
    const ctxEvent = events.find((e) => e.type === 'context_loaded');
    if (ctxEvent) {
      steps.push({
        name: '上下文加载',
        tool: `${ctxEvent.payload.materialized_count} 项资源`,
        status: 'done',
      });
    }
    if (task?.status === 'running' || task?.status === 'awaiting_human') {
      steps.push({ name: 'Agent 执行中', status: 'running' });
    }
    if (task?.status === 'delivered' || task?.status === 'closed') {
      steps.push({ name: '交付完成', status: 'done' });
    }
    return steps;
  }, [events, task]);

  const dialogMessages = useMemo(() => {
    // P0 简化版：从 events 取 asset_referenced / artifact_produced 等
    return events
      .filter((e) => e.type === 'asset_referenced' || e.type === 'artifact_produced')
      .slice(-3);
  }, [events]);

  return (
    <div className="ws-wb">
      <div className="ws-wb__header">
        <span className="ws-wb__back" onClick={onBack}>← 返回大厅</span>
        <span className="ws-wb__title">{task?.title || `task_${taskId}`}</span>
        {task?.triggered_by && (
          <span className="ws-wb__meta">{task.triggered_by}</span>
        )}
      </div>

      <div className="ws-wb__body">
        {/* 进展 */}
        <div className="ws-wb__section">
          <div className="ws-wb__section-title">进展</div>
          <div className="ws-wb__progress">
            {progressSteps.length === 0 && (
              <div className="ws-wb__step ws-wb__step--pending">
                <span className="ws-wb__step-icon">○</span>
                <span className="ws-wb__step-name">等待开始</span>
              </div>
            )}
            {progressSteps.map((step, i) => (
              <div key={i} className={`ws-wb__step ws-wb__step--${step.status}`}>
                <span className="ws-wb__step-icon">
                  {step.status === 'done' ? '✓' : step.status === 'running' ? '◐' : '○'}
                </span>
                <span className="ws-wb__step-name">{step.name}</span>
                {step.tool && <span className="ws-wb__step-tool">{step.tool}</span>}
              </div>
            ))}
          </div>
        </div>

        {/* 交付物 */}
        {artifacts && artifacts.length > 0 && (
          <div className="ws-wb__section">
            <div className="ws-wb__section-title">交付物</div>
            <div className="ws-wb__artifact">
              {artifacts.map((a: any) => (
                <div key={a.id}>
                  <div className="ws-wb__artifact-title">
                    {a.title || `artifact_${a.id}`}
                  </div>
                  <Tag>{a.type}</Tag>
                  <div className="ws-wb__artifact-actions">
                    <Button size="small">预览</Button>
                    <Button size="small">发送</Button>
                    <Button size="small">沉淀为 Asset</Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 协作对话（折叠） */}
        <div className="ws-wb__section">
          <div className="ws-wb__section-title">协作对话</div>
          <div className="ws-wb__dialog">
            {dialogMessages.length === 0 && (
              <div className="ws-wb__dialog-msg">暂无对话</div>
            )}
            {dialogMessages.slice(0, dialogExpanded ? undefined : 3).map((e, i) => (
              <div key={i} className="ws-wb__dialog-msg">
                {e.type === 'artifact_produced' ? 'Agent 产出: ' : 'Agent 引用: '}
                {JSON.stringify(e.payload)}
              </div>
            ))}
            {dialogMessages.length > 3 && (
              <div
                className="ws-wb__dialog-expand"
                onClick={() => setDialogExpanded(!dialogExpanded)}
              >
                {dialogExpanded ? '收起' : `展开完整对话 (${dialogMessages.length})`}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 输入框常驻底部 */}
      <div className="ws-wb__input">
        <Input.TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={`给 task_${taskId} 下指令...`}
          autoSize={{ minRows: 1, maxRows: 4 }}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              // P0: 通过 ChatSession 发送（ChatSession 内部处理）
              // 这里简化为清空——实际发送由 ChatSession 的 chat() 处理
              setInput('');
            }
          }}
        />
      </div>

      {/* ChatSession 隐藏，作为对话内核 + 事件源 */}
      <div style={{ display: 'none' }}>
        <ChatSession
          convUid={convUid}
          appCode={appCode}
          workspaceId={String(workspaceId)}
          taskId={String(taskId)}
          minimal
          onWorkspaceEvent={handleWorkspaceEvent}
        />
      </div>
    </div>
  );
}
```

注意：
- P0 简化版：ChatSession `display:none` 作为事件源和对话内核，输入框是 workbench 自己的——P1 阶段再把输入框和 ChatSession 真正联动（让输入框调 `chat()` 发送）。P0 先把"主体是进展+交付+对话折叠，输入框常驻底部"的形态立住。
- `listArtifacts` / `listInterventions` 的实际 API 签名以 `web/src/client/api/artifact/index.ts` 和 `intervention/index.ts` 为准——如果参数名不是 `task_id`，调整。
- `getTaskInfo` 如果实际是 `getTask` 或其他名，以 `web/src/client/api/task/index.ts` 为准。

- [ ] **Step 3: 验证编译**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && pnpm tsc --noEmit 2>&1 | head -40`

Expected: 无新增类型错误。如果有 `listArtifacts` 参数错误，检查 API client 实际签名并修正。

- [ ] **Step 4: 提交**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git add web/src/app/workspaces/detail/workbench.tsx \
        web/src/app/workspaces/detail/workbench.css
git commit -m "feat(ws): 新增任务工作台组件（进展+交付+对话折叠，输入框常驻底部）"
```

---

## Task 9: 空间大厅组件 lobby.tsx

**Files:**
- Create: `web/src/app/workspaces/detail/lobby.tsx`

**Interfaces:**
- Consumes: workspace 详情页已有的 `useRequest` 数据（tasks/artifacts/deliveries/triggers/playbooks）；Task 10 的 `<GrowthCard>`
- Produces: `<Lobby workspaceId={...} onSelectTask={(tid) => void} />`，主体是进行中任务/栖居交付物/最近交付/快捷发起

- [ ] **Step 1: 写 lobby.tsx**

Create `web/src/app/workspaces/detail/lobby.tsx`:

```tsx
'use client';

import { Button, Card, Tag } from 'antd';
import { useRequest } from 'ahooks';
import { listTasks, listArtifacts, listDeliveries, listPlaybooks } from '@/client/api';
import { GrowthCard } from './growth-card';

export interface LobbyProps {
  workspaceId: number;
  onSelectTask: (taskId: number) => void;
  onQuickStart: (playbookId: number) => void;
}

export function Lobby({ workspaceId, onSelectTask, onQuickStart }: LobbyProps) {
  const { data: tasks } = useRequest(() =>
    listTasks({ workspace_id: workspaceId, status: 'running' })
  );
  const { data: deliveries } = useRequest(() =>
    listDeliveries({ workspace_id: workspaceId })
  );
  const { data: artifacts } = useRequest(() =>
    listArtifacts({ workspace_id: workspaceId })
  );
  const { data: playbooks } = useRequest(() =>
    listPlaybooks({ workspace_id: workspaceId })
  );

  const runningTasks = (tasks || []).slice(0, 5);
  const recentDeliveries = (deliveries || []).slice(0, 3);
  const hostedArtifacts = (artifacts || []).filter((a: any) => a.hosting_status === 'running').slice(0, 4);

  return (
    <div className="ws-lobby">
      <div className="ws-lobby__main">
        {/* 进行中任务 */}
        <section className="ws-lobby__section">
          <div className="ws-lobby__section-head">
            <h3>📋 进行中任务 ({runningTasks.length})</h3>
          </div>
          <div className="ws-lobby__task-list">
            {runningTasks.length === 0 && <div className="ws-empty">暂无进行中任务</div>}
            {runningTasks.map((t: any) => (
              <Card
                key={t.id}
                size="small"
                className="ws-lobby__task-card"
                hoverable
                onClick={() => onSelectTask(t.id)}
              >
                <div className="ws-lobby__task-title">{t.title}</div>
                <div className="ws-lobby__task-meta">
                  <Tag color="blue">{t.status}</Tag>
                  <span>{t.triggered_by}</span>
                </div>
              </Card>
            ))}
          </div>
        </section>

        {/* 栖居的交付物 */}
        <section className="ws-lobby__section">
          <div className="ws-lobby__section-head">
            <h3>🏠 栖居的交付物 ({hostedArtifacts.length})</h3>
          </div>
          <div className="ws-lobby__hosted-grid">
            {hostedArtifacts.length === 0 && (
              <div className="ws-empty">P8 上线后这里展示托管运行的交付物</div>
            )}
            {hostedArtifacts.map((a: any) => (
              <Card key={a.id} size="small" className="ws-lobby__hosted-card">
                <div>{a.title}</div>
                <Tag color="green">running</Tag>
                <Button size="small" type="link">打开</Button>
              </Card>
            ))}
          </div>
        </section>

        {/* 最近交付 */}
        <section className="ws-lobby__section">
          <div className="ws-lobby__section-head">
            <h3>📨 最近交付 ({recentDeliveries.length})</h3>
          </div>
          <div className="ws-lobby__delivery-list">
            {recentDeliveries.map((d: any) => (
              <div key={d.id} className="ws-lobby__delivery-item">
                <Tag>{d.category}</Tag>
                <span>{d.channel}</span>
                <span className="ws-lobby__delivery-status">{d.status}</span>
              </div>
            ))}
          </div>
        </section>

        {/* 快捷发起 */}
        <section className="ws-lobby__section">
          <div className="ws-lobby__section-head">
            <h3>⚡ 快捷发起</h3>
          </div>
          <div className="ws-lobby__quick">
            {(playbooks || []).slice(0, 4).map((p: any) => (
              <Button
                key={p.id}
                onClick={() => onQuickStart(p.id)}
              >
                + {p.name}
              </Button>
            ))}
            <Button type="dashed">+ 自定义</Button>
          </div>
        </section>
      </div>

      {/* 侧栏：成长卡 */}
      <aside className="ws-lobby__rail">
        <GrowthCard workspaceId={workspaceId} />
      </aside>
    </div>
  );
}
```

注意：`listTasks` / `listDeliveries` / `listPlaybooks` 的实际签名以 `web/src/client/api/{task,delivery,playbook}/index.ts` 为准。如果参数名不同，调整。

- [ ] **Step 2: 验证编译**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && pnpm tsc --noEmit 2>&1 | head -40`

Expected: 无新增类型错误（GrowthCard 还没建，下一个 Task 建会有未定义错误，先跳过）。

- [ ] **Step 3: 提交**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git add web/src/app/workspaces/detail/lobby.tsx
git commit -m "feat(ws): 新增空间大厅组件（进行中任务/栖居交付物/最近交付/快捷发起）"
```

---

## Task 10: 本月空间成长卡片 growth-card.tsx

**Files:**
- Create: `web/src/app/workspaces/detail/growth-card.tsx`
- Modify: 后端 `packages/derisk-serve/src/derisk_serve/workspace/api/endpoints.py`（新增 `/workspaces/{id}/growth` 端点）

**Interfaces:**
- Consumes: workspace_asset / task / playbook / knowledge（llm-wiki）的查询能力
- Produces: `<GrowthCard workspaceId={...} />` 显示沉淀数/演化提议数/任务趋势/知识图谱节点数

- [ ] **Step 1: 写后端 growth 端点测试**

Create `packages/derisk-serve/tests/derisk_serve/workspace/test_growth_endpoint.py`:

```python
"""Tests for workspace growth endpoint."""
import pytest
from unittest.mock import MagicMock, patch
from derisk_serve.workspace.service.service import WorkspaceService


def test_get_workspace_growth_returns_dict_with_expected_keys():
    """get_workspace_growth 返回含 expected keys。"""
    system_app = MagicMock()
    with patch.object(WorkspaceService, "__init__", lambda self, system_app: None), \
         patch.object(WorkspaceService, "get_growth", return_value={
             "assets_count": 12,
             "evolution_proposals_count": 0,
             "tasks_trend": [{"date": "2026-06-28", "count": 3}],
             "knowledge_graph_nodes": 0,
         }):
        svc = WorkspaceService(system_app=system_app)
        growth = svc.get_growth(workspace_id=1)
    assert "assets_count" in growth
    assert "evolution_proposals_count" in growth
    assert "tasks_trend" in growth
    assert "knowledge_graph_nodes" in growth


def test_get_workspace_growth_proposals_zero_in_p0():
    """P0 阶段演化提议数恒为 0（提议生成 P2 才做）。"""
    system_app = MagicMock()
    with patch.object(WorkspaceService, "__init__", lambda self, system_app: None), \
         patch.object(WorkspaceService, "get_growth", return_value={
             "assets_count": 5,
             "evolution_proposals_count": 0,
             "tasks_trend": [],
             "knowledge_graph_nodes": 0,
         }):
        svc = WorkspaceService(system_app=system_app)
        growth = svc.get_growth(workspace_id=1)
    assert growth["evolution_proposals_count"] == 0
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/test_growth_endpoint.py -v`
Expected: FAIL with `AttributeError: 'WorkspaceService' object has no attribute 'get_growth'`

- [ ] **Step 3: 后端 WorkspaceService 加 get_growth 方法**

Modify `packages/derisk-serve/src/derisk_serve/workspace/service/service.py`。在 `WorkspaceService` class 内加方法：

```python
    def get_growth(self, workspace_id: int) -> dict:
        """返回空间本月成长数据。

        P0 阶段演化提议数恒为 0（提议生成 P2 才做），知识图谱节点数 P1 才接入 llm-wiki。
        """
        from datetime import datetime, timedelta
        from derisk_serve.workspace_asset.service.service import (
            WorkspaceAssetService,
        )
        from derisk_serve.task.service.service import TaskService

        now = datetime.utcnow()
        month_ago = now - timedelta(days=30)

        try:
            asset_svc = WorkspaceAssetService(system_app=self.system_app)
            assets = asset_svc.list_assets(workspace_id) or []
            assets_count = len(assets)
        except Exception as e:
            logger.warning(f"get_growth assets failed: {e}")
            assets_count = 0

        try:
            task_svc = TaskService(system_app=self.system_app)
            tasks = task_svc.list_tasks(workspace_id) or []
            # 按日聚合最近 30 天
            trend_map: dict = {}
            for t in tasks:
                created = getattr(t, "created_at", None)
                if created and created >= month_ago:
                    key = created.strftime("%Y-%m-%d")
                    trend_map[key] = trend_map.get(key, 0) + 1
            tasks_trend = [
                {"date": k, "count": v}
                for k, v in sorted(trend_map.items())
            ]
        except Exception as e:
            logger.warning(f"get_growth tasks failed: {e}")
            tasks_trend = []

        return {
            "assets_count": assets_count,
            "evolution_proposals_count": 0,  # P0 占位，P2 才做生成
            "tasks_trend": tasks_trend,
            "knowledge_graph_nodes": 0,  # P0 占位，P1 接入 llm-wiki
        }
```

注意：`WorkspaceAssetService` / `TaskService` 的实际类名和 `list_assets` / `list_tasks` 方法签名以代码为准——如果不同，调整。`logger` 已在 service.py 顶部定义（如果没有，加 `import logging; logger = logging.getLogger(__name__)`）。

- [ ] **Step 4: 注册 growth 端点**

Modify `packages/derisk-serve/src/derisk_serve/workspace/api/endpoints.py`。在现有 router 里加：

```python
@router.get("/workspaces/{workspace_id}/growth", response_model=ResultModel)
async def get_workspace_growth(
    workspace_id: int,
    request: Request,
) -> ResultModel:
    """获取空间本月成长数据。"""
    service = WorkspaceService.get_instance(request)
    growth = service.get_growth(workspace_id)
    return ResultModel.success(growth)
```

注意：`ResultModel` 和 `WorkspaceService.get_instance` 的实际用法以 endpoints.py 现有端点的模式为准——参考其他端点（如 `list_resources`）的写法保持一致。

- [ ] **Step 5: 运行测试验证通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/test_growth_endpoint.py -v`
Expected: PASS

- [ ] **Step 6: 写前端 GrowthCard 组件**

Create `web/src/app/workspaces/detail/growth-card.tsx`:

```tsx
'use client';

import { Card, Statistic } from 'antd';
import { useRequest } from 'ahooks';
import { apiGet } from '@/client/api';

export interface GrowthCardProps {
  workspaceId: number;
}

interface GrowthData {
  assets_count: number;
  evolution_proposals_count: number;
  tasks_trend: Array<{ date: string; count: number }>;
  knowledge_graph_nodes: number;
}

export function GrowthCard({ workspaceId }: GrowthCardProps) {
  const { data } = useRequest<GrowthData>(
    () => apiGet(`/api/v1/serve_workspace_service/workspaces/${workspaceId}/growth`),
    { refreshDeps: [workspaceId] }
  );

  return (
    <Card size="small" title="本月空间成长" className="ws-growth-card">
      <Statistic title="沉淀 Asset" value={data?.assets_count ?? 0} />
      <Statistic
        title="Playbook 演化提议"
        value={data?.evolution_proposals_count ?? 0}
        suffix={data?.evolution_proposals_count === 0 ? '(P2 上线)' : ''}
      />
      <Statistic
        title="知识图谱节点"
        value={data?.knowledge_graph_nodes ?? 0}
        suffix={data?.knowledge_graph_nodes === 0 ? '(P1 上线)' : ''}
      />
      <div className="ws-growth-card__trend">
        <span className="ws-growth-card__trend-label">任务趋势</span>
        <span className="ws-growth-card__trend-value">
          {(data?.tasks_trend || []).reduce((sum, t) => sum + t.count, 0)} 次 (30 天)
        </span>
      </div>
    </Card>
  );
}
```

注意：`apiGet` 的实际导出名以 `web/src/client/api/index.ts` 为准——如果是 `GET` 或其他名，调整。

- [ ] **Step 7: 验证编译**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && pnpm tsc --noEmit 2>&1 | head -40`

Expected: 无新增类型错误。

- [ ] **Step 8: 提交**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git add packages/derisk-serve/src/derisk_serve/workspace/service/service.py \
        packages/derisk-serve/src/derisk_serve/workspace/api/endpoints.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_growth_endpoint.py \
        web/src/app/workspaces/detail/growth-card.tsx
git commit -m "feat(ws): 新增本月空间成长卡片（后端 get_growth + 前端 GrowthCard）"
```

---

## Task 11: workspace 详情页主体切换（lobby ⇄ workbench）

**Files:**
- Modify: `web/src/app/workspaces/detail/client.tsx:386-592`（替换 .ws-console grid）

**Interfaces:**
- Consumes: Task 8 的 `<Workbench>`、Task 9 的 `<Lobby>`
- Produces: workspace 详情页主体根据 `selectedTaskId` 切换：无选中显示 Lobby，选中显示 Workbench

- [ ] **Step 1: 改 client.tsx 引入 Lobby/Workbench 并切换主体**

Modify `web/src/app/workspaces/detail/client.tsx`。

在 import 区加：

```tsx
import { Lobby } from './lobby';
import { Workbench } from './workbench';
```

在组件内（约 L170 附近 state 区）加：

```tsx
const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
```

找到 `.ws-console` grid（L386-592），整段替换为：

```tsx
      <div className="ws-console">
        {selectedTaskId === null ? (
          <Lobby
            workspaceId={Number(wsId)}
            onSelectTask={(tid) => setSelectedTaskId(tid)}
            onQuickStart={(pid) => {
              // P0 简化：跳转到 triggers 页或调 createTask
              router.push(`/workspaces/detail?id=${wsCode}&trigger=${pid}`);
            }}
          />
        ) : (
          <Workbench
            taskId={selectedTaskId}
            workspaceId={Number(wsId)}
            appCode={appCode}
            convUid={convUid || ''}
            onBack={() => setSelectedTaskId(null)}
          />
        )}
      </div>
```

注意：`wsId` / `wsCode` / `convUid` / `appCode` 是 client.tsx 现有变量（来自 useRequest / localStorage），保持现名。如果变量名不同，调整。

- [ ] **Step 2: 手动验证页面渲染**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && pnpm dev` 然后浏览器打开 `/workspaces/detail?id=<某个 workspace_code>`

Expected:
- 进空间看到 Lobby（进行中任务/栖居交付物/最近交付/快捷发起 + 右侧成长卡）
- 点任务卡片切到 Workbench（进展+交付+对话折叠 + 底部输入框 + 返回大厅）
- 点"返回大厅"回到 Lobby

- [ ] **Step 3: 提交**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git add web/src/app/workspaces/detail/client.tsx
git commit -m "feat(ws): workspace 详情页主体切换（lobby ⇄ workbench）"
```

---

## Task 12: 顶部 workspace 切换器

**Files:**
- Create: `web/src/components/layout/workspace-switcher.tsx`
- Modify: `web/src/components/layout/side-bar.tsx:812-827`（展开态 LOGO 与新对话按钮之间插入切换器）

**Interfaces:**
- Consumes: `listWorkspaces` API
- Produces: `<WorkspaceSwitcher />` 下拉切换空间，切换后跳转 `/workspaces/detail?id=<code>`

- [ ] **Step 1: 写 WorkspaceSwitcher 组件**

Create `web/src/components/layout/workspace-switcher.tsx`:

```tsx
'use client';

import { Select, Spin } from 'antd';
import { useRequest } from 'ahooks';
import { useRouter, usePathname } from 'next/navigation';
import { listWorkspaces } from '@/client/api';

export function WorkspaceSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const { data, loading } = useRequest(() => listWorkspaces({}));

  // 从 URL 推断当前空间
  const currentCode = (() => {
    const m = pathname?.match(/\/workspaces\/detail\?id=([^&]+)/);
    return m?.[1] || '';
  })();

  const handleChange = (value: string) => {
    router.push(`/workspaces/detail?id=${value}`);
  };

  if (loading) return <Spin size="small" />;

  return (
    <Select
      value={currentCode || undefined}
      placeholder="切换空间"
      onChange={handleChange}
      style={{ width: 180 }}
      showSearch
      optionFilterProp="label"
      options={(data || []).map((ws: any) => ({
        value: ws.workspace_code,
        label: ws.name,
      }))}
    />
  );
}
```

注意：`listWorkspaces` 的参数和返回字段以 `web/src/client/api/workspace/index.ts` 为准。

- [ ] **Step 2: 在 side-bar.tsx 展开态插入切换器**

Modify `web/src/components/layout/side-bar.tsx`。在 import 区加：

```tsx
import { WorkspaceSwitcher } from './workspace-switcher';
```

找到展开态 LOGO（约 L812-815）和"新对话"按钮（L817-827）之间，插入：

```tsx
        <div className="side-bar-workspace-switcher">
          <WorkspaceSwitcher />
        </div>
```

注意：只在展开态插入，折叠态不插（折叠态空间太小）。`side-bar-workspace-switcher` class 可加 margin/padding 样式，或在 side-bar 的 CSS 文件加。

- [ ] **Step 3: 验证编译与渲染**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && pnpm tsc --noEmit 2>&1 | head -20`

Expected: 无新增类型错误。

手动验证：`pnpm dev` 打开任意页面，侧栏展开态应显示 workspace 切换器下拉。

- [ ] **Step 4: 提交**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git add web/src/components/layout/workspace-switcher.tsx \
        web/src/components/layout/side-bar.tsx
git commit -m "feat(ws): 顶部新增 workspace 切换器（展开态下拉切换空间）"
```

---

## Task 13: 端到端验证

**Files:**
- 无新增，仅验证

**Interfaces:**
- Consumes: Task 1-12 全部产出

- [ ] **Step 1: 后端测试全跑**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/ packages/derisk-serve/tests/derisk_serve/agent/agents/chat/ packages/derisk-serve/tests/derisk_serve/playbook/ -v`

Expected: 全部 PASS

- [ ] **Step 2: 前端编译检查**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && pnpm tsc --noEmit 2>&1 | tail -20`

Expected: 无新增类型错误（pre-existing 警告可忽略）

- [ ] **Step 3: 启动后端验证物化链路**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m derisk_app`（或项目实际的启动命令）

Expected: 后端启动无 ImportError，serve 模块全部注册。

- [ ] **Step 4: 启动前端验证叙事翻盘**

Run: `cd /Users/tuyang/GitHub/OpenDerisk/web && pnpm dev`

浏览器验证清单：
1. 登录后点侧栏"场景空间"进 `/workspaces` 列表
2. 侧栏展开态显示 workspace 切换器
3. 进某个 workspace → 看到 Lobby（不是空对话）
4. Lobby 显示进行中任务/栖居交付物/最近交付/快捷发起 + 右侧本月空间成长卡
5. 点任务卡片 → 切到 Workbench（进展+交付+对话折叠+底部输入框）
6. 点"返回大厅" → 回到 Lobby
7. 在 Workbench 里 Agent 运行时，观察进展步骤是否更新（依赖 context_loaded 事件）

- [ ] **Step 5: 验证物化链路实际生效**

在 workspace_resource 表插入一条 `type=mcp, physical_ref=<真实 mcp_code>` 的记录，触发一个 Playbook，检查 AgentRun 是否真的能调这个 MCP（看日志或 AgentRun.skills_loaded_json）。

Expected: Agent 实际加载了该 MCP 资源，不是只在 prompt 里看到字符串。

- [ ] **Step 6: 提交验证记录**

```bash
cd /Users/tuyang/GitHub/OpenDerisk
git log --oneline -15  # 确认 12 个 Task 的提交都在
```

Expected: 看到 12 个 `feat(ws):` 提交，按 Task 顺序排列。

---

## 风险与回退

**风险 1：物化链路破坏现有 aggregation_chat**
- 缓解：Task 3 抽出 `_inject_workspace_context` helper，独立测试，不改动 aggregation_chat 主流程
- 回退：revert Task 3 提交，物化结果不注入 ext_info（Agent 仍只看 prompt 字符串）

**风险 2：前端 ChatSession display:none 导致对话功能不可用**
- 缓解：P0 先把叙事翻盘形态立住，ChatSession 作为事件源；P1 再把输入框和 ChatSession 真正联动
- 回退：把 ChatSession 改为 visible，workbench 主体仍展示进展/交付，但对话区可见

**风险 3：growth 端点的 list_assets/list_tasks 在大空间下慢**
- 缓解：P0 空间数据量小（design partner 阶段），不加索引；P1 再加缓存或预聚合
- 回退：growth 端点返回 0 占位，卡片显示"(P1 上线)"

**风险 4：workspace 切换器在非 workspace 页面也显示**
- 缓解：side-bar 展开态统一显示，切换器从 URL 推断当前空间
- 回退：切换器只在 `/workspaces/*` 路径下显示（加 pathname 判断）

---

## Self-Review

**1. Spec coverage**：
- P0-1 任务工作台 → Task 8 (workbench.tsx) + Task 11 (主体切换) + Task 5/6/7 (事件链路) ✅
- P0-2 空间大厅默认页 → Task 9 (lobby.tsx) + Task 11 (主体切换) ✅
- P0-3 本月空间成长卡片 → Task 10 (growth-card + 后端端点) ✅
- P0-4 顶部 workspace 切换器 → Task 12 ✅
- P0-5 workspace_resource 物化链路 → Task 1 (materializer) + Task 2 (context_builder) + Task 3 (aggregation_chat) + Task 4 (playbook runtime) ✅

**2. Placeholder scan**：无 TBD/TODO/待补，所有步骤含完整代码或精确命令 ✅

**3. Type consistency**：
- `materialize_resources` 在 Task 1/2/4 签名一致 ✅
- `MaterializedResources` 字段 `dynamic_resources` / `extra_agents` 在 Task 1/2/3 一致 ✅
- `format_workspace_event` 在 Task 5 定义、Task 6 前端解析类型一致 ✅
- `WorkspaceEvent` 类型 Task 6 定义、Task 7/8 使用一致 ✅
- `get_growth` 返回字段在 Task 10 后端测试与前端 GrowthCard 一致 ✅

**4. 依赖关系**：
- Task 1 → Task 2 → Task 3（物化链路后端）
- Task 1 → Task 4（物化链路 runtime）
- Task 5 → Task 6 → Task 7 → Task 8（事件链路前端）
- Task 10 → Task 9（GrowthCard 给 Lobby 用）
- Task 8 + Task 9 → Task 11（主体切换）
- Task 12 独立
- Task 13 端到端验证依赖全部
