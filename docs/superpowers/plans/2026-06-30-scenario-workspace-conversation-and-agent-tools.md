# Scenario Workspace Conversation & Agent Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement three-layer injection model (空间基线/空间操作/剧本能力) for Scenario Workspace conversations, with backend-managed conversation mapping (is_current + remove localStorage), task/space conversation isolation, and non-blocking intervention flow for space Agent write tools.

**Architecture:** Extend `WorkspaceConversationLink` with `is_current`/`title` for backend current-conversation lookup. Relax `InterventionEntity.task_id` to nullable and add `conv_uid` for Lobby writes. Build `WorkspaceControlAgent(ConversableAgent)` wrapping read/write FunctionTools, injected via `extra_agents` in `_inject_workspace_context`. Materialize playbook declaration (skills/resources) to AgentResource for Workbench. Frontend `ConversationSwitcher` dropdown replaces localStorage; Workbench uses `task.conv_session_id`, Lobby uses workspace-level current conv_uid.

**Tech Stack:** Python 3.10+, derisk-serve (SQLAlchemy + FastAPI), derisk-core (ConversableAgent + FunctionTool), Next.js 14 + Ant Design + ahooks, pytest, vitest.

## Global Constraints

- **Backend conversation mapping:** `WorkspaceConversationLink.is_current` (Boolean, default False, indexed) + `title` (String(255), nullable). One `is_current=True` per (workspace_id, user_id) — enforced in `set_current_conversation` by transactionally flipping all others to False.
- **Intervention task_id relaxation:** `InterventionEntity.task_id` changes from `nullable=False` to `nullable=True`. `InterventionRequest.task_id` and `InterventionResponse.task_id` change from `int` to `Optional[int]`. Add `InterventionEntity.conv_uid = Column(String(255), nullable=True, index=True)`.
- **Three-layer injection:** Layer 1 (空间基线, both Lobby+Workbench): 5 read tools. Layer 2 (空间操作, Lobby only): 7 tools (2 read + 5 write). Layer 3 (剧本能力, Workbench only): 6 tools (3 read + 3 write). Lobby total = 12 tools, Workbench total = 11 tools. Layer 2 and Layer 3 do not overlap.
- **Write tool flow:** Tool creates intervention (task_id nullable, conv_uid set) → SSE `intervention_triggered` event → frontend `VisConfirmCard` → user resolves → `POST /interventions/{id}/resolve-and-execute` → `execute_resolved` routes by `question_json.tool` → calls tool execute method → `_post_message_back` via `multi_agents.app_chat(conv_uid, gpts_name, synthetic_user_query)`.
- **Frontend convUid:** Remove all localStorage reads/writes for convUid in `web/src/app/workspaces/detail/client.tsx`. Use `getCurrentConversation(workspaceId)` on mount. Workbench receives `task.conv_session_id` as convUid (no switching — task-scoped).
- **`appCode`:** Use `workspace.default_agent_app_code or 'chat_normal'` consistently on both backend (playbook runtime) and frontend (client.tsx).
- **No new dependencies.** No emojis in code. Match existing style. Tests required for every backend module.

---

## File Structure

**Backend (packages/derisk-serve/src/derisk_serve/):**

- `workspace/models/models.py` — modify `WorkspaceConversationLinkEntity`: add `is_current`, `title`; extend `link()` signature.
- `workspace/service/service.py` — add `get_current_conversation`, `set_current_conversation`, `rename_conversation`.
- `workspace/api/endpoints.py` — add `GET /workspaces/{id}/conversations/current`, `POST /workspaces/{id}/conversations/set-current`, `PATCH /conversations/{conv_uid}/rename`.
- `workspace/materializer.py` — add `materialize_playbook_declaration(system_app, playbook_id) -> List[AgentResource]`.
- `workspace/agent_tools/__init__.py` — new, exports `build_workspace_toolkit`.
- `workspace/agent_tools/read_tools.py` — new, 8 read FunctionTools (5 Layer-1 + 3 Layer-3).
- `workspace/agent_tools/write_tools.py` — new, 5 write FunctionTools (Layer-2) wrapped with intervention flow.
- `workspace/agent_tools/playbook_tools.py` — new, 3 write FunctionTools (Layer-3) wrapped with intervention flow.
- `workspace/agent_tools/toolkit.py` — new, `WorkspaceControlAgent(ConversableAgent)` + `build_workspace_toolkit(system_app, ws_id, user_id, task_id, playbook_declaration)`.
- `workspace/agent_tools/context_builder.py` — new, `build_workspace_context(ws_id, user_id, task_id, mode) -> WorkspaceContextSnapshot` and `render_workspace_context_summary(ctx, mode)`.
- `intervention/models/models.py` — modify `InterventionEntity`: `task_id` nullable, add `conv_uid`.
- `intervention/api/schemas.py` — modify `InterventionRequest`/`InterventionResponse`: `task_id: Optional[int]`.
- `intervention/service/service.py` — add `execute_resolved(intervention_id) -> InterventionEntity`.
- `intervention/api/endpoints.py` — add `POST /interventions/{id}/resolve-and-execute`.
- `agent/agents/chat/agent_chat.py` — modify `_inject_workspace_context` to call `build_workspace_toolkit` and append `WorkspaceControlAgent` to `extra_agents`. Add `mode` parameter pass-through.

**Frontend (web/src/):**

- `client/api/workspace/index.ts` — add `getCurrentConversation`, `setCurrentConversation`, `renameConversation`.
- `app/workspaces/detail/client.tsx` — remove localStorage; use `getCurrentConversation`; pass `task.conv_session_id` to Workbench; mount `ConversationSwitcher`.
- `app/workspaces/detail/conversation-switcher.tsx` — new, dropdown component.
- `components/chat/visual-confirm-card.tsx` — modify: route resolve through `resolveAndExecute` endpoint; refresh task list after resolve.

**Tests (packages/derisk-serve/tests/derisk_serve/):**

- `workspace/test_conv_link_dao.py` — new, tests `is_current` flip, `get_current`, `rename`.
- `workspace/test_agent_tools.py` — new, tests each tool's pure execution path.
- `workspace/test_intervention_execute.py` — new, tests `execute_resolved` routing and `_post_message_back`.
- `workspace/test_injection.py` — new, tests `build_workspace_toolkit` for Lobby (12 tools) and Workbench (11 tools).
- `workspace/test_playbook_materializer.py` — new, tests declaration materialization.
- `intervention/test_intervention_nullable_task.py` — new, tests creating intervention with task_id=None.

---

## Task 1: WorkspaceConversationLink Schema Extension

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/models/models.py:115-219`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_conv_link_dao.py`

**Interfaces:**
- Produces: `WorkspaceConversationLinkEntity.is_current: Boolean`, `WorkspaceConversationLinkEntity.title: Optional[String]`. `link(workspace_id, conv_uid, task_id=None, user_id=None, title=None, set_current=False) -> WorkspaceConversationLinkEntity`.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-serve/tests/derisk_serve/workspace/test_conv_link_dao.py
import pytest
from derisk_serve.workspace.models.models import WorkspaceConversationLinkEntity, WorkspaceDAO


@pytest.fixture
def db_session(tmp_path):
    from derisk_serve.workspace.models.models import db
    # Use in-memory sqlite; assume db.init() helper exists in conftest
    db.init(f"sqlite:///{tmp_path}/test.db")
    db.drop_all()
    db.create_all()
    with db.session() as session:
        yield session


def test_link_with_set_current_flips_previous(db_session):
    dao = WorkspaceDAO(db_session)
    first = dao.link(workspace_id=1, conv_uid="conv-1", user_id="u1", set_current=True)
    second = dao.link(workspace_id=1, conv_uid="conv-2", user_id="u1", set_current=True)

    db_session.refresh(first)
    db_session.refresh(second)
    assert first.is_current is False
    assert second.is_current is True


def test_get_current_conversation(db_session):
    dao = WorkspaceDAO(db_session)
    dao.link(workspace_id=1, conv_uid="conv-1", user_id="u1", set_current=True)
    dao.link(workspace_id=1, conv_uid="conv-2", user_id="u1", set_current=False)

    current = dao.get_current(workspace_id=1, user_id="u1")
    assert current.conv_uid == "conv-1"


def test_rename_conversation(db_session):
    dao = WorkspaceDAO(db_session)
    link = dao.link(workspace_id=1, conv_uid="conv-1", user_id="u1", title="old")
    dao.rename(conv_uid="conv-1", title="new title")

    db_session.refresh(link)
    assert link.title == "new title"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_conv_link_dao.py -v`
Expected: FAIL — `is_current` column missing / `get_current` method missing / `rename` method missing.

- [ ] **Step 3: Add columns and extend link()**

In `packages/derisk-serve/src/derisk_serve/workspace/models/models.py`, locate `WorkspaceConversationLinkEntity` class definition. Add columns after `gmt_modified`:

```python
    is_current = Column(Boolean, nullable=False, default=False, index=True)
    title = Column(String(255), nullable=True)
```

Extend the `link()` method signature and body:

```python
    def link(
        self,
        workspace_id: int,
        conv_uid: str,
        task_id: Optional[int] = None,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
        set_current: bool = False,
    ) -> "WorkspaceConversationLinkEntity":
        entity = WorkspaceConversationLinkEntity(
            workspace_id=workspace_id,
            conv_uid=conv_uid,
            task_id=task_id,
            user_id=user_id,
            title=title,
            is_current=False,
        )
        self._session.add(entity)
        self._session.flush()
        if set_current:
            self._set_current_internal(workspace_id, user_id, conv_uid)
        return entity

    def _set_current_internal(self, workspace_id: int, user_id: Optional[str], conv_uid: str) -> None:
        self._session.query(WorkspaceConversationLinkEntity).filter(
            WorkspaceConversationLinkEntity.workspace_id == workspace_id,
            WorkspaceConversationLinkEntity.user_id == user_id,
            WorkspaceConversationLinkEntity.conv_uid != conv_uid,
        ).update({WorkspaceConversationLinkEntity.is_current: False}, synchronize_session=False)
        self._session.query(WorkspaceConversationLinkEntity).filter(
            WorkspaceConversationLinkEntity.workspace_id == workspace_id,
            WorkspaceConversationLinkEntity.user_id == user_id,
            WorkspaceConversationLinkEntity.conv_uid == conv_uid,
        ).update({WorkspaceConversationLinkEntity.is_current: True}, synchronize_session=False)
        self._session.flush()

    def get_current(self, workspace_id: int, user_id: Optional[str]) -> Optional["WorkspaceConversationLinkEntity"]:
        return (
            self._session.query(WorkspaceConversationLinkEntity)
            .filter(
                WorkspaceConversationLinkEntity.workspace_id == workspace_id,
                WorkspaceConversationLinkEntity.user_id == user_id,
                WorkspaceConversationLinkEntity.is_current.is_(True),
            )
            .order_by(WorkspaceConversationLinkEntity.gmt_modified.desc())
            .first()
        )

    def rename(self, conv_uid: str, title: str) -> Optional["WorkspaceConversationLinkEntity"]:
        entity = (
            self._session.query(WorkspaceConversationLinkEntity)
            .filter(WorkspaceConversationLinkEntity.conv_uid == conv_uid)
            .first()
        )
        if entity is None:
            return None
        entity.title = title
        self._session.flush()
        return entity
```

Also extend `to_response` to include the new fields:

```python
    def to_response(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "conv_uid": self.conv_uid,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "title": self.title,
            "is_current": self.is_current,
            "gmt_created": self.gmt_created,
            "gmt_modified": self.gmt_modified,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_conv_link_dao.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/models/models.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_conv_link_dao.py
git commit -m "feat(workspace): add is_current/title to WorkspaceConversationLinkEntity"
```

---

## Task 2: Conversation Service Layer

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/service/service.py`
- Test: extend `packages/derisk-serve/tests/derisk_serve/workspace/test_conv_link_dao.py` (or new `test_conv_service.py`)

**Interfaces:**
- Consumes: `WorkspaceDAO.link/get_current/rename/list_by_workspace` from Task 1.
- Produces: `WorkspaceService.get_current_conversation(workspace_id, user_id) -> Optional[WorkspaceConversationLinkEntity]`, `set_current_conversation(workspace_id, user_id, conv_uid) -> WorkspaceConversationLinkEntity`, `rename_conversation(conv_uid, title) -> WorkspaceConversationLinkEntity`.

- [ ] **Step 1: Write the failing test**

```python
# Append to packages/derisk-serve/tests/derisk_serve/workspace/test_conv_link_dao.py
from derisk_serve.workspace.service.service import WorkspaceService


@pytest.fixture
def service(db_session):
    return WorkspaceService(db_session)


def test_service_set_current_persists(service, db_session):
    service.link_conversation(workspace_id=1, conv_uid="conv-1", user_id="u1")
    service.link_conversation(workspace_id=1, conv_uid="conv-2", user_id="u1")

    service.set_current_conversation(workspace_id=1, user_id="u1", conv_uid="conv-2")

    current = service.get_current_conversation(workspace_id=1, user_id="u1")
    assert current.conv_uid == "conv-2"


def test_service_rename(service):
    service.link_conversation(workspace_id=1, conv_uid="conv-1", user_id="u1")
    renamed = service.rename_conversation(conv_uid="conv-1", title="my title")
    assert renamed.title == "my title"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_conv_link_dao.py::test_service_set_current_persists -v`
Expected: FAIL — `WorkspaceService.set_current_conversation` missing.

- [ ] **Step 3: Add service methods**

In `packages/derisk-serve/src/derisk_serve/workspace/service/service.py`, add to `WorkspaceService`:

```python
    def get_current_conversation(
        self, workspace_id: int, user_id: Optional[str]
    ) -> Optional[WorkspaceConversationLinkEntity]:
        return self.dao.get_current(workspace_id=workspace_id, user_id=user_id)

    def set_current_conversation(
        self, workspace_id: int, user_id: Optional[str], conv_uid: str
    ) -> WorkspaceConversationLinkEntity:
        link = (
            self.dao._session.query(WorkspaceConversationLinkEntity)
            .filter(
                WorkspaceConversationLinkEntity.workspace_id == workspace_id,
                WorkspaceConversationLinkEntity.conv_uid == conv_uid,
            )
            .first()
        )
        if link is None:
            raise ValueError(f"Conversation {conv_uid} not linked to workspace {workspace_id}")
        self.dao._set_current_internal(workspace_id, user_id, conv_uid)
        self.dao._session.commit()
        return self.dao.get_current(workspace_id=workspace_id, user_id=user_id)

    def rename_conversation(
        self, conv_uid: str, title: str
    ) -> Optional[WorkspaceConversationLinkEntity]:
        entity = self.dao.rename(conv_uid=conv_uid, title=title)
        self.dao._session.commit()
        return entity
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_conv_link_dao.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/service/service.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_conv_link_dao.py
git commit -m "feat(workspace): add conversation service methods for current/rename"
```

---

## Task 3: Conversation Management Endpoints

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/api/endpoints.py:255-301`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_conv_endpoints.py`

**Interfaces:**
- Consumes: `WorkspaceService.get_current_conversation/set_current_conversation/rename_conversation/list_conversations` from Task 2.
- Produces: `GET /workspaces/{workspace_id}/conversations/current`, `POST /workspaces/{workspace_id}/conversations/set-current`, `PATCH /conversations/{conv_uid}/rename`.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-serve/tests/derisk_serve/workspace/test_conv_endpoints.py
import pytest
from fastapi.testclient import TestClient
from derisk_serve.workspace.api.endpoints import router


@pytest.fixture
def client(monkeypatch):
    # Patch service factory; assume conftest provides app wiring
    from derisk_serve.workspace.api import endpoints as ep
    app = __import__("fastapi").FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_current_endpoint(client, monkeypatch):
    from derisk_serve.workspace.api import endpoints as ep
    class FakeLink:
        conv_uid = "conv-1"
        title = "t"
        is_current = True
        workspace_id = 1
        task_id = None
        user_id = "u1"
        def to_response(self):
            return {"conv_uid": "conv-1", "title": "t", "is_current": True}
    monkeypatch.setattr(ep, "get_service", lambda: type("S", (), {
        "get_current_conversation": lambda self, workspace_id, user_id: FakeLink(),
    }()))
    res = client.get("/workspaces/1/conversations/current", headers={"X-User-ID": "u1"})
    assert res.status_code == 200
    assert res.json()["conv_uid"] == "conv-1"


def test_set_current_endpoint(client, monkeypatch):
    from derisk_serve.workspace.api import endpoints as ep
    captured = {}
    class FakeLink:
        def to_response(self):
            return {"conv_uid": "conv-2", "is_current": True}
    monkeypatch.setattr(ep, "get_service", lambda: type("S", (), {
        "set_current_conversation": lambda self, **kw: (captured.update(kw), FakeLink())[1],
    }()))
    res = client.post("/workspaces/1/conversations/set-current", json={"conv_uid": "conv-2"}, headers={"X-User-ID": "u1"})
    assert res.status_code == 200
    assert captured["conv_uid"] == "conv-2"


def test_rename_endpoint(client, monkeypatch):
    from derisk_serve.workspace.api import endpoints as ep
    class FakeLink:
        def to_response(self):
            return {"conv_uid": "conv-1", "title": "new"}
    monkeypatch.setattr(ep, "get_service", lambda: type("S", (), {
        "rename_conversation": lambda self, conv_uid, title: FakeLink(),
    }()))
    res = client.patch("/conversations/conv-1/rename", json={"title": "new"}, headers={"X-User-ID": "u1"})
    assert res.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_conv_endpoints.py -v`
Expected: FAIL — endpoints don't exist (404).

- [ ] **Step 3: Add endpoints**

In `packages/derisk-serve/src/derisk_serve/workspace/api/endpoints.py`, append:

```python
from typing import Optional
from fastapi import APIRouter, Header
from pydantic import BaseModel


class SetCurrentRequest(BaseModel):
    conv_uid: str


class RenameRequest(BaseModel):
    title: str


@router.get("/workspaces/{workspace_id}/conversations/current")
async def get_current_conversation(
    workspace_id: int,
    user_id: Optional[str] = Header(None, alias="X-User-ID"),
):
    service = get_service()
    link = service.get_current_conversation(workspace_id=workspace_id, user_id=user_id)
    if link is None:
        return {"data": None}
    return {"data": link.to_response()}


@router.post("/workspaces/{workspace_id}/conversations/set-current")
async def set_current_conversation(
    workspace_id: int,
    payload: SetCurrentRequest,
    user_id: Optional[str] = Header(None, alias="X-User-ID"),
):
    service = get_service()
    link = service.set_current_conversation(
        workspace_id=workspace_id, user_id=user_id, conv_uid=payload.conv_uid
    )
    return {"data": link.to_response()}


@router.patch("/conversations/{conv_uid}/rename")
async def rename_conversation(
    conv_uid: str,
    payload: RenameRequest,
):
    service = get_service()
    link = service.rename_conversation(conv_uid=conv_uid, title=payload.title)
    if link is None:
        return {"data": None}
    return {"data": link.to_response()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_conv_endpoints.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/api/endpoints.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_conv_endpoints.py
git commit -m "feat(workspace): add conversation current/rename endpoints"
```

---

## Task 4: Intervention Schema Relaxation

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/intervention/models/models.py`
- Modify: `packages/derisk-serve/src/derisk_serve/intervention/api/schemas.py`
- Test: `packages/derisk-serve/tests/derisk_serve/intervention/test_intervention_nullable_task.py`

**Interfaces:**
- Produces: `InterventionEntity.task_id: Optional[Integer]` (nullable), `InterventionEntity.conv_uid: Optional[String]` (nullable, indexed). `InterventionRequest.task_id: Optional[int]`, `InterventionResponse.task_id: Optional[int]`, `InterventionResponse.conv_uid: Optional[str]`.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-serve/tests/derisk_serve/intervention/test_intervention_nullable_task.py
import pytest


@pytest.fixture
def db_session(tmp_path):
    from derisk_serve.intervention.models.models import db
    db.init(f"sqlite:///{tmp_path}/test.db")
    db.drop_all()
    db.create_all()
    with db.session() as session:
        yield session


def test_create_intervention_with_null_task(db_session):
    from derisk_serve.intervention.models.models import InterventionEntity, InterventionDAO
    dao = InterventionDAO(db_session)
    entity = dao.create(
        question_json={"tool": "start_task", "args": {"workspace_id": 1}},
        user_id="u1",
        conv_uid="conv-1",
        task_id=None,
    )
    assert entity.id is not None
    assert entity.task_id is None
    assert entity.conv_uid == "conv-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/intervention/test_intervention_nullable_task.py -v`
Expected: FAIL — `task_id` NOT NULL constraint, `conv_uid` column missing.

- [ ] **Step 3: Relax constraints**

In `packages/derisk-serve/src/derisk_serve/intervention/models/models.py`, locate `InterventionEntity.task_id`:

```python
    task_id = Column(Integer, nullable=True, index=True)
    conv_uid = Column(String(255), nullable=True, index=True)
```

In `packages/derisk-serve/src/derisk_serve/intervention/api/schemas.py`, locate `InterventionRequest` and `InterventionResponse`:

```python
class InterventionRequest(BaseModel):
    # ... existing fields ...
    task_id: Optional[int] = None
    conv_uid: Optional[str] = None
    # ...


class InterventionResponse(BaseModel):
    # ... existing fields ...
    task_id: Optional[int] = None
    conv_uid: Optional[str] = None
    # ...
```

Update `InterventionDAO.create` (or wherever the entity is built) to accept `conv_uid` and pass through `task_id=None`:

```python
    def create(
        self,
        *,
        question_json: dict,
        user_id: Optional[str] = None,
        task_id: Optional[int] = None,
        conv_uid: Optional[str] = None,
        **kwargs,
    ) -> InterventionEntity:
        entity = InterventionEntity(
            question_json=question_json,
            user_id=user_id,
            task_id=task_id,
            conv_uid=conv_uid,
            **kwargs,
        )
        self._session.add(entity)
        self._session.flush()
        return entity
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/intervention/test_intervention_nullable_task.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/intervention/models/models.py \
        packages/derisk-serve/src/derisk_serve/intervention/api/schemas.py \
        packages/derisk-serve/tests/derisk_serve/intervention/test_intervention_nullable_task.py
git commit -m "feat(intervention): allow nullable task_id, add conv_uid column"
```

---

## Task 5: Workspace Context Builder

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/__init__.py`
- Create: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/context_builder.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder_agent.py`

**Interfaces:**
- Consumes: `WorkspaceService`, `TaskService`, `materialize_resources`.
- Produces: `WorkspaceContextSnapshot` dataclass with fields `{workspace, materialized_resources, task (optional), playbook_declaration (optional), user_id}`. `build_workspace_context(workspace_id, user_id, task_id=None, mode="lobby"|"workbench") -> WorkspaceContextSnapshot`. `render_workspace_context_summary(ctx, mode) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder_agent.py
import pytest
from unittest.mock import MagicMock, patch


def test_build_workspace_context_lobby(monkeypatch):
    from derisk_serve.workspace.agent_tools.context_builder import build_workspace_context

    fake_system_app = MagicMock()
    with patch(
        "derisk_serve.workspace.agent_tools.context_builder.get_service"
    ) as gs, patch(
        "derisk_serve.workspace.agent_tools.context_builder.materialize_resources"
    ) as mr:
        gs.return_value.get_by_id.return_value = MagicMock(name="ws", id=1, default_agent_app_code="chat_normal")
        mr.return_value = MagicMock(resources=[], tools=[])
        ctx = build_workspace_context(
            system_app=fake_system_app, workspace_id=1, user_id="u1", task_id=None, mode="lobby"
        )
        assert ctx.workspace is not None
        assert ctx.task is None
        assert ctx.playbook_declaration is None


def test_render_summary_lobby_contains_workspace_name(monkeypatch):
    from derisk_serve.workspace.agent_tools.context_builder import build_workspace_context, render_workspace_context_summary
    fake_system_app = MagicMock()
    with patch("derisk_serve.workspace.agent_tools.context_builder.get_service") as gs, \
         patch("derisk_serve.workspace.agent_tools.context_builder.materialize_resources") as mr:
        gs.return_value.get_by_id.return_value = MagicMock(name="ws", id=1, default_agent_app_code="chat_normal")
        mr.return_value = MagicMock(resources=[], tools=[])
        ctx = build_workspace_context(system_app=fake_system_app, workspace_id=1, user_id="u1", mode="lobby")
        summary = render_workspace_context_summary(ctx, mode="lobby")
        assert "空间" in summary or "workspace" in summary.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_context_builder_agent.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement context_builder.py**

```python
# packages/derisk-serve/src/derisk_serve/workspace/agent_tools/__init__.py
from derisk_serve.workspace.agent_tools.toolkit import build_workspace_toolkit  # noqa: F401
```

```python
# packages/derisk-serve/src/derisk_serve/workspace/agent_tools/context_builder.py
from dataclasses import dataclass, field
from typing import Any, List, Optional

from derisk_serve.workspace.service.service import WorkspaceService
from derisk_serve.workspace.materializer import materialize_resources, MaterializedResources


@dataclass
class WorkspaceContextSnapshot:
    workspace: Any
    materialized_resources: MaterializedResources
    task: Optional[Any] = None
    playbook_declaration: Optional[dict] = None
    user_id: Optional[str] = None
    workspace_id: Optional[int] = None
    task_id: Optional[int] = None


def get_service(system_app) -> WorkspaceService:
    from derisk_serve.workspace.service.service import ServiceType
    return system_app.get_instance(ServiceType.WORKSPACE_SERVICE, WorkspaceService)


def get_task_service(system_app):
    from derisk_serve.task.service.service import TaskService, ServiceType
    return system_app.get_instance(ServiceType.TASK_SERVICE, TaskService)


def build_workspace_context(
    system_app,
    workspace_id: int,
    user_id: Optional[str] = None,
    task_id: Optional[int] = None,
    mode: str = "lobby",
) -> WorkspaceContextSnapshot:
    ws_service = get_service(system_app)
    workspace = ws_service.get_by_id(workspace_id)

    materialized = materialize_resources(system_app, workspace_id)

    task = None
    playbook_declaration = None
    if task_id is not None:
        task_service = get_task_service(system_app)
        task = task_service.get_by_id(task_id)
        if task and getattr(task, "playbook_id", None):
            from derisk_serve.playbook.service.service import PlaybookService
            pb_service = system_app.get_instance(
                __import__("derisk_serve.playbook.service.service", fromlist=["ServiceType"]).ServiceType.PLAYBOOK_SERVICE,
                PlaybookService,
            )
            playbook = pb_service.get_by_id(task.playbook_id)
            if playbook and getattr(playbook, "declaration_dsl_json", None):
                playbook_declaration = playbook.declaration_dsl_json

    return WorkspaceContextSnapshot(
        workspace=workspace,
        materialized_resources=materialized,
        task=task,
        playbook_declaration=playbook_declaration,
        user_id=user_id,
        workspace_id=workspace_id,
        task_id=task_id,
    )


def render_workspace_context_summary(ctx: WorkspaceContextSnapshot, mode: str = "lobby") -> str:
    ws = ctx.workspace
    name = getattr(ws, "name", f"workspace_{ctx.workspace_id}") if ws else f"workspace_{ctx.workspace_id}"
    lines = [
        f"# 当前空间：{name} (id={ctx.workspace_id})",
        f"模式：{mode}",
    ]
    if ctx.materialized_resources:
        res = getattr(ctx.materialized_resources, "resources", []) or []
        if res:
            lines.append(f"已物化资源数：{len(res)}")
    if ctx.task:
        lines.append(f"当前任务：{getattr(ctx.task, 'title', '')} (id={getattr(ctx.task, 'id', '')})")
    if ctx.playbook_declaration:
        skills = (ctx.playbook_declaration or {}).get("skills", []) or []
        if skills:
            lines.append(f"剧本技能：{', '.join(s.get('name', str(s)) if isinstance(s, dict) else str(s) for s in skills)}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_context_builder_agent.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/agent_tools/__init__.py \
        packages/derisk-serve/src/derisk_serve/workspace/agent_tools/context_builder.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_context_builder_agent.py
git commit -m "feat(workspace): add workspace context builder with mode parameter"
```

---

## Task 6: Playbook Declaration Materializer

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/materializer.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_playbook_materializer.py`

**Interfaces:**
- Consumes: `PlaybookEntity.declaration_dsl_json` structure `{skills: [{name, type, ...}], context: {resources: [...]}, deliverables: [...], distill: ...}`.
- Produces: `materialize_playbook_declaration(system_app, declaration_dsl_json) -> List[AgentResource]`.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-serve/tests/derisk_serve/workspace/test_playbook_materializer.py
import pytest
from unittest.mock import MagicMock, patch


def test_materialize_playbook_declaration_handles_skills_and_resources():
    from derisk_serve.workspace.materializer import materialize_playbook_declaration
    declaration = {
        "skills": [{"name": "skill-a", "type": "skill"}],
        "context": {"resources": [{"type": "mcp", "name": "mcp-x", "server_name": "s1"}]},
        "deliverables": [],
    }
    fake_system_app = MagicMock()
    with patch("derisk_serve.workspace.materializer._materialize_skill") as ms, \
         patch("derisk_serve.workspace.materializer._materialize_mcp") as mm:
        ms.return_value = [MagicMock(spec=[], name="skill-resource")]
        mm.return_value = [MagicMock(spec=[], name="mcp-resource")]
        result = materialize_playbook_declaration(fake_system_app, declaration)
        assert len(result) == 2
        ms.assert_called_once()
        mm.assert_called_once()


def test_materialize_playbook_declaration_empty():
    from derisk_serve.workspace.materializer import materialize_playbook_declaration
    fake_system_app = MagicMock()
    assert materialize_playbook_declaration(fake_system_app, {}) == []
    assert materialize_playbook_declaration(fake_system_app, None) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_playbook_materializer.py -v`
Expected: FAIL — function doesn't exist.

- [ ] **Step 3: Implement materialize_playbook_declaration**

In `packages/derisk-serve/src/derisk_serve/workspace/materializer.py`, append:

```python
def materialize_playbook_declaration(system_app, declaration_dsl_json) -> List["AgentResource"]:
    """Materialize skills + context.resources from a playbook declaration into AgentResource list.

    Reuses _MATERIALIZE_DISPATCH for resource types; for skills uses _materialize_skill.
    """
    if not declaration_dsl_json:
        return []
    resources: List["AgentResource"] = []

    skills = declaration_dsl_json.get("skills") or []
    for skill in skills:
        skill_type = skill.get("type") or "skill"
        handler = _MATERIALIZE_DISPATCH.get(skill_type) or _MATERIALIZE_DISPATCH.get("skill")
        if handler is None:
            continue
        try:
            resources.extend(handler(system_app, skill) or [])
        except Exception:
            continue

    ctx = declaration_dsl_json.get("context") or {}
    ctx_resources = ctx.get("resources") or []
    for res in ctx_resources:
        res_type = res.get("type")
        handler = _MATERIALIZE_DISPATCH.get(res_type)
        if handler is None:
            continue
        try:
            resources.extend(handler(system_app, res) or [])
        except Exception:
            continue

    return resources
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_playbook_materializer.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/materializer.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_playbook_materializer.py
git commit -m "feat(workspace): materialize playbook declaration skills/resources"
```

---

## Task 7: Read Tools Module

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/read_tools.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_agent_tools.py`

**Interfaces:**
- Produces: 10 `FunctionTool` instances (5 Layer-1 + 2 Layer-2 + 3 Layer-3):
  - Layer 1 (空间基线, both modes): `list_tasks_tool`, `get_task_info_tool`, `list_artifacts_tool`, `list_deliveries_tool`, `list_assets_tool`
  - Layer 2 (空间操作, Lobby only): `get_workspace_memory_tool`, `list_workspace_members_tool`
  - Layer 3 (剧本能力, Workbench only): `list_playbooks_tool`, `get_playbook_detail_tool`, `list_interventions_tool`
  - Each tool: `name`, `description`, `func`. All read tools take `workspace_id: int` and return JSON-serializable dicts.
- Layer-2 read backing:
  - `get_workspace_memory`: reads from `WorkspaceMemoryService` (if absent, returns `{"memory": null}`); the service lives at `derisk_serve.workspace.memory.service` — if it doesn't exist, return `{"memory": null, "note": "no workspace memory configured"}` rather than erroring.
  - `list_workspace_members`: reads from `WorkspaceMemberService.list_members(workspace_id)` (if absent, returns `[]`); if no service exists, return `{"members": [], "note": "no member service configured"}`.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-serve/tests/derisk_serve/workspace/test_agent_tools.py
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def fake_system_app():
    return MagicMock()


def test_list_tasks_tool_returns_list(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools
    with patch("derisk_serve.workspace.agent_tools.read_tools.get_task_service") as gts:
        gts.return_value.list_tasks.return_value = [MagicMock(to_response=lambda: {"id": 1, "title": "t"})]
        tools = build_read_tools(fake_system_app, workspace_id=1)
        list_tasks = next(t for t in tools if t.name == "list_tasks")
        result = list_tasks.func(workspace_id=1)
        assert isinstance(result, list)


def test_get_task_info_tool_returns_dict(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools
    with patch("derisk_serve.workspace.agent_tools.read_tools.get_task_service") as gts:
        gts.return_value.get_by_id.return_value = MagicMock(to_response=lambda: {"id": 1, "title": "t"})
        tools = build_read_tools(fake_system_app, workspace_id=1)
        tool = next(t for t in tools if t.name == "get_task_info")
        result = tool.func(workspace_id=1, task_id=1)
        assert isinstance(result, dict)


def test_read_tools_count(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools
    with patch("derisk_serve.workspace.agent_tools.read_tools.get_task_service"), \
         patch("derisk_serve.workspace.agent_tools.read_tools.get_artifact_service"), \
         patch("derisk_serve.workspace.agent_tools.read_tools.get_delivery_service"), \
         patch("derisk_serve.workspace.agent_tools.read_tools.get_asset_service"), \
         patch("derisk_serve.workspace.agent_tools.read_tools.get_playbook_service"), \
         patch("derisk_serve.workspace.agent_tools.read_tools.get_intervention_service"), \
         patch("derisk_serve.workspace.agent_tools.read_tools.get_workspace_memory_service"), \
         patch("derisk_serve.workspace.agent_tools.read_tools.get_workspace_member_service"):
        tools = build_read_tools(fake_system_app, workspace_id=1)
        # 5 Layer-1 + 2 Layer-2 + 3 Layer-3 = 10
        names = {t.name for t in tools}
        assert {"list_tasks", "get_task_info", "list_artifacts", "list_deliveries", "list_assets",
                "get_workspace_memory", "list_workspace_members",
                "list_playbooks", "get_playbook_detail", "list_interventions"} == names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_agent_tools.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement read_tools.py**

```python
# packages/derisk-serve/src/derisk_serve/workspace/agent_tools/read_tools.py
"""Read-only FunctionTools for the workspace control Agent.

Layer 1 (空间基线, both Lobby + Workbench): list_tasks, get_task_info, list_artifacts, list_deliveries, list_assets.
Layer 3 (剧本能力, Workbench only): list_playbooks, get_playbook_detail, list_interventions.
"""
import json
from typing import Any, List

from derisk.agent.resource.tool.base import FunctionTool


def get_task_service(system_app):
    from derisk_serve.task.service.service import TaskService, ServiceType
    return system_app.get_instance(ServiceType.TASK_SERVICE, TaskService)


def get_artifact_service(system_app):
    from derisk_serve.artifact.service.service import ArtifactService, ServiceType
    return system_app.get_instance(ServiceType.ARTIFACT_SERVICE, ArtifactService)


def get_delivery_service(system_app):
    from derisk_serve.delivery.service.service import DeliveryService, ServiceType
    return system_app.get_instance(ServiceType.DELIVERY_SERVICE, DeliveryService)


def get_asset_service(system_app):
    from derisk_serve.workspace.asset.service.service import AssetService, ServiceType
    return system_app.get_instance(ServiceType.ASSET_SERVICE, AssetService)


def get_playbook_service(system_app):
    from derisk_serve.playbook.service.service import PlaybookService, ServiceType
    return system_app.get_instance(ServiceType.PLAYBOOK_SERVICE, PlaybookService)


def get_intervention_service(system_app):
    from derisk_serve.intervention.service.service import InterventionService, ServiceType
    return system_app.get_instance(ServiceType.INTERVENTION_SERVICE, InterventionService)


def _to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "to_response"):
        return obj.to_response()
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if hasattr(obj, "__dict__"):
        return {k: _to_jsonable(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return obj


def _list_tasks(system_app, workspace_id: int):
    svc = get_task_service(system_app)
    items = svc.list_tasks(workspace_id=workspace_id) or []
    return _to_jsonable(items)


def _get_task_info(system_app, workspace_id: int, task_id: int):
    svc = get_task_service(system_app)
    item = svc.get_by_id(task_id)
    return _to_jsonable(item) if item else {"error": "task not found"}


def _list_artifacts(system_app, workspace_id: int, task_id: int = None):
    svc = get_artifact_service(system_app)
    items = svc.list_artifacts(workspace_id=workspace_id, task_id=task_id) or []
    return _to_jsonable(items)


def _list_deliveries(system_app, workspace_id: int):
    svc = get_delivery_service(system_app)
    items = svc.list_deliveries(workspace_id=workspace_id) or []
    return _to_jsonable(items)


def _list_assets(system_app, workspace_id: int):
    svc = get_asset_service(system_app)
    items = svc.list_assets(workspace_id=workspace_id) or []
    return _to_jsonable(items)


def _list_playbooks(system_app, workspace_id: int):
    svc = get_playbook_service(system_app)
    items = svc.list_playbooks(workspace_id=workspace_id) or []
    return _to_jsonable(items)


def _get_playbook_detail(system_app, workspace_id: int, playbook_id: int):
    svc = get_playbook_service(system_app)
    item = svc.get_by_id(playbook_id)
    return _to_jsonable(item) if item else {"error": "playbook not found"}


def _list_interventions(system_app, workspace_id: int, task_id: int = None):
    svc = get_intervention_service(system_app)
    items = svc.list_interventions(workspace_id=workspace_id, task_id=task_id) or []
    return _to_jsonable(items)


def get_workspace_memory_service(system_app):
    """Return WorkspaceMemoryService if registered, else None."""
    try:
        from derisk_serve.workspace.memory.service import WorkspaceMemoryService
        from derisk_serve.workspace.memory.service import ServiceType
        return system_app.get_instance(ServiceType.WORKSPACE_MEMORY_SERVICE, WorkspaceMemoryService)
    except Exception:
        return None


def get_workspace_member_service(system_app):
    """Return WorkspaceMemberService if registered, else None."""
    try:
        from derisk_serve.workspace.member.service import WorkspaceMemberService
        from derisk_serve.workspace.member.service import ServiceType
        return system_app.get_instance(ServiceType.WORKSPACE_MEMBER_SERVICE, WorkspaceMemberService)
    except Exception:
        return None


def _get_workspace_memory(system_app, workspace_id: int):
    svc = get_workspace_memory_service(system_app)
    if svc is None:
        return {"memory": None, "note": "no workspace memory configured"}
    try:
        mem = svc.get(workspace_id=workspace_id)
        return {"memory": _to_jsonable(mem) if mem else None}
    except Exception as e:
        return {"memory": None, "error": str(e)}


def _list_workspace_members(system_app, workspace_id: int):
    svc = get_workspace_member_service(system_app)
    if svc is None:
        return {"members": [], "note": "no member service configured"}
    try:
        items = svc.list_members(workspace_id=workspace_id) or []
        return {"members": _to_jsonable(items)}
    except Exception as e:
        return {"members": [], "error": str(e)}


def build_read_tools(system_app, workspace_id: int) -> List[FunctionTool]:
    """Build all read tools (Layer 1 + Layer 2 + Layer 3). Caller decides which subset to register."""
    specs = [
        ("list_tasks", "列出当前空间下的所有任务", _list_tasks, {"workspace_id": int}),
        ("get_task_info", "查询指定任务的详情", _get_task_info, {"workspace_id": int, "task_id": int}),
        ("list_artifacts", "列出空间下（可选指定任务）的交付物", _list_artifacts, {"workspace_id": int, "task_id": int}),
        ("list_deliveries", "列出空间下最近的投递记录", _list_deliveries, {"workspace_id": int}),
        ("list_assets", "列出空间下沉淀的 Asset", _list_assets, {"workspace_id": int}),
        ("get_workspace_memory", "读取空间记忆", _get_workspace_memory, {"workspace_id": int}),
        ("list_workspace_members", "列出空间成员", _list_workspace_members, {"workspace_id": int}),
        ("list_playbooks", "列出空间下的剧本", _list_playbooks, {"workspace_id": int}),
        ("get_playbook_detail", "查询剧本详情", _get_playbook_detail, {"workspace_id": int, "playbook_id": int}),
        ("list_interventions", "列出空间下（可选指定任务）的人工介入记录", _list_interventions, {"workspace_id": int, "task_id": int}),
    ]
    tools: List[FunctionTool] = []
    for name, desc, fn, arg_types in specs:
        def make_tool(fn=fn, arg_types=arg_types, name=name, desc=desc):
            def _wrapped(**kwargs):
                kwargs["system_app"] = system_app
                return fn(**kwargs)
            _wrapped.__name__ = name
            return FunctionTool(name=name, description=desc, func=_wrapped, args_schema=None)
        tools.append(make_tool())
    return tools
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_agent_tools.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/agent_tools/read_tools.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_agent_tools.py
git commit -m "feat(workspace): add 8 read tools (Layer1 + Layer3)"
```

---

## Task 8: Write Tools Module (Layer 2 + Layer 3)

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/write_tools.py`
- Create: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/playbook_tools.py`
- Test: extend `packages/derisk-serve/tests/derisk_serve/workspace/test_agent_tools.py`

**Interfaces:**
- Consumes: `InterventionService.create` (task_id nullable, conv_uid).
- Produces: `build_write_tools(system_app, workspace_id, user_id, conv_uid, task_id=None) -> List[FunctionTool]` (Layer 2: start_task, close_task, publish_asset, create_delivery, update_workspace). `build_playbook_tools(...)` (Layer 3: launch_playbook, update_playbook, archive_playbook). Each tool **does not execute** — it creates an intervention with `question_json={tool, args}` and returns `{"intervention_id": id, "status": "awaiting_human"}`.

- [ ] **Step 1: Write the failing test**

```python
# Append to packages/derisk-serve/tests/derisk_serve/workspace/test_agent_tools.py
def test_write_tool_creates_intervention_with_null_task(fake_system_app):
    from derisk_serve.workspace.agent_tools.write_tools import build_write_tools
    with patch("derisk_serve.workspace.agent_tools.write_tools.get_intervention_service") as gis:
        gis.return_value.create.return_value = MagicMock(id=42)
        tools = build_write_tools(fake_system_app, workspace_id=1, user_id="u1", conv_uid="conv-1", task_id=None)
        start_task = next(t for t in tools if t.name == "start_task")
        result = start_task.func(workspace_id=1, playbook_id=10)
        assert result["status"] == "awaiting_human"
        assert result["intervention_id"] == 42
        # Lobby mode: task_id must be None
        call_kwargs = gis.return_value.create.call_args.kwargs
        assert call_kwargs["task_id"] is None
        assert call_kwargs["conv_uid"] == "conv-1"


def test_playbook_write_tool_creates_intervention(fake_system_app):
    from derisk_serve.workspace.agent_tools.playbook_tools import build_playbook_tools
    with patch("derisk_serve.workspace.agent_tools.playbook_tools.get_intervention_service") as gis:
        gis.return_value.create.return_value = MagicMock(id=7)
        tools = build_playbook_tools(fake_system_app, workspace_id=1, user_id="u1", conv_uid="conv-1", task_id=5)
        launch = next(t for t in tools if t.name == "launch_playbook")
        result = launch.func(workspace_id=1, playbook_id=10)
        assert result["status"] == "awaiting_human"
        call_kwargs = gis.return_value.create.call_args.kwargs
        assert call_kwargs["question_json"]["tool"] == "launch_playbook"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_agent_tools.py::test_write_tool_creates_intervention_with_null_task -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement write_tools.py and playbook_tools.py**

```python
# packages/derisk-serve/src/derisk_serve/workspace/agent_tools/write_tools.py
"""Layer 2 (空间操作) write tools — Lobby only. Each creates an intervention, does NOT execute."""
from typing import List, Optional

from derisk.agent.resource.tool.base import FunctionTool
from derisk_serve.workspace.agent_tools.read_tools import get_intervention_service


def _make_intervention(system_app, *, tool_name: str, args: dict, user_id, conv_uid, task_id) -> dict:
    svc = get_intervention_service(system_app)
    entity = svc.create(
        question_json={"tool": tool_name, "args": args},
        user_id=user_id,
        conv_uid=conv_uid,
        task_id=task_id,
    )
    return {"intervention_id": entity.id, "status": "awaiting_human"}


def build_write_tools(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    conv_uid: str,
    task_id: Optional[int] = None,
) -> List[FunctionTool]:
    specs = [
        ("start_task", "在当前空间下发起一个任务", {"workspace_id": int, "playbook_id": int, "title": str}),
        ("close_task", "关闭指定任务", {"workspace_id": int, "task_id": int}),
        ("publish_asset", "将一个交付物沉淀为空间级 Asset", {"workspace_id": int, "artifact_id": int, "title": str}),
        ("create_delivery", "创建一条投递记录", {"workspace_id": int, "artifact_id": int, "channel": str, "category": str}),
        ("update_workspace", "更新空间基本信息", {"workspace_id": int, "name": str, "description": str}),
    ]
    tools: List[FunctionTool] = []
    for name, desc, arg_types in specs:
        def make_tool(name=name, desc=desc):
            def _wrapped(**kwargs):
                return _make_intervention(
                    system_app,
                    tool_name=name,
                    args=kwargs,
                    user_id=user_id,
                    conv_uid=conv_uid,
                    task_id=task_id,
                )
            _wrapped.__name__ = name
            return FunctionTool(name=name, description=desc, func=_wrapped, args_schema=None)
        tools.append(make_tool())
    return tools
```

```python
# packages/derisk-serve/src/derisk_serve/workspace/agent_tools/playbook_tools.py
"""Layer 3 (剧本能力) write tools — Workbench only. Each creates an intervention, does NOT execute."""
from typing import List, Optional

from derisk.agent.resource.tool.base import FunctionTool
from derisk_serve.workspace.agent_tools.read_tools import get_intervention_service


def _make_intervention(system_app, *, tool_name: str, args: dict, user_id, conv_uid, task_id) -> dict:
    svc = get_intervention_service(system_app)
    entity = svc.create(
        question_json={"tool": tool_name, "args": args},
        user_id=user_id,
        conv_uid=conv_uid,
        task_id=task_id,
    )
    return {"intervention_id": entity.id, "status": "awaiting_human"}


def build_playbook_tools(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    conv_uid: str,
    task_id: Optional[int] = None,
) -> List[FunctionTool]:
    specs = [
        ("launch_playbook", "基于剧本发起新任务", {"workspace_id": int, "playbook_id": int, "title": str}),
        ("update_playbook", "更新剧本声明 DSL", {"workspace_id": int, "playbook_id": int, "declaration": dict}),
        ("archive_playbook", "归档剧本", {"workspace_id": int, "playbook_id": int}),
    ]
    tools: List[FunctionTool] = []
    for name, desc, arg_types in specs:
        def make_tool(name=name, desc=desc):
            def _wrapped(**kwargs):
                return _make_intervention(
                    system_app,
                    tool_name=name,
                    args=kwargs,
                    user_id=user_id,
                    conv_uid=conv_uid,
                    task_id=task_id,
                )
            _wrapped.__name__ = name
            return FunctionTool(name=name, description=desc, func=_wrapped, args_schema=None)
        tools.append(make_tool())
    return tools
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_agent_tools.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/agent_tools/write_tools.py \
        packages/derisk-serve/src/derisk_serve/workspace/agent_tools/playbook_tools.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_agent_tools.py
git commit -m "feat(workspace): add Layer2/Layer3 write tools with intervention flow"
```

---

## Task 9: WorkspaceControlAgent + build_workspace_toolkit

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/toolkit.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_injection.py`

**Interfaces:**
- Consumes: `build_read_tools`, `build_write_tools`, `build_playbook_tools`, `materialize_playbook_declaration`, `WorkspaceContextSnapshot`.
- Produces: `WorkspaceControlAgent(ConversableAgent)` with `function_tools` populated. `build_workspace_toolkit(system_app, workspace_id, user_id, conv_uid, task_id=None, mode="lobby"|"workbench") -> Optional[WorkspaceControlAgent]`. Returns `None` if conv_uid missing. Lobby mode: 5 Layer-1 read + 7 Layer-2 (5 write + 2 Layer-2 reads... see note). Workbench mode: 5 Layer-1 read + 6 Layer-3 (3 read + 3 write). Total Lobby = 12, Workbench = 11.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-serve/tests/derisk_serve/workspace/test_injection.py
import pytest
from unittest.mock import MagicMock, patch


def _named_tool(name: str):
    m = MagicMock()
    m.name = name
    return m


def test_build_workspace_toolkit_lobby_has_12_tools():
    from derisk_serve.workspace.agent_tools.toolkit import build_workspace_toolkit
    fake_system_app = MagicMock()
    layer1 = [_named_tool(n) for n in ["list_tasks", "get_task_info", "list_artifacts", "list_deliveries", "list_assets"]]
    layer2_read = [_named_tool(n) for n in ["get_workspace_memory", "list_workspace_members"]]
    # Include Layer-3 reads in the all_read list to prove Lobby filters them out
    layer3_read = [_named_tool(n) for n in ["list_playbooks", "get_playbook_detail", "list_interventions"]]
    all_read = layer1 + layer2_read + layer3_read

    with patch("derisk_serve.workspace.agent_tools.toolkit.build_read_tools", return_value=all_read) as gr, \
         patch("derisk_serve.workspace.agent_tools.toolkit.build_write_tools", return_value=[_named_tool(f"w{i}") for i in range(5)]) as gw, \
         patch("derisk_serve.workspace.agent_tools.toolkit.build_playbook_tools") as gp:
        agent = build_workspace_toolkit(
            system_app=fake_system_app,
            workspace_id=1,
            user_id="u1",
            conv_uid="conv-1",
            task_id=None,
            mode="lobby",
        )
        assert agent is not None
        assert len(agent._tools) == 12, f"Lobby must have 12 tools, got {len(agent._tools)}"
        gr.assert_called_once()
        gw.assert_called_once()
        gp.assert_not_called()


def test_build_workspace_toolkit_workbench_has_11_tools():
    from derisk_serve.workspace.agent_tools.toolkit import build_workspace_toolkit
    fake_system_app = MagicMock()
    layer1 = [_named_tool(n) for n in ["list_tasks", "get_task_info", "list_artifacts", "list_deliveries", "list_assets"]]
    layer2_read = [_named_tool(n) for n in ["get_workspace_memory", "list_workspace_members"]]
    layer3_read = [_named_tool(n) for n in ["list_playbooks", "get_playbook_detail", "list_interventions"]]
    all_read = layer1 + layer2_read + layer3_read

    with patch("derisk_serve.workspace.agent_tools.toolkit.build_read_tools", return_value=all_read) as gr, \
         patch("derisk_serve.workspace.agent_tools.toolkit.build_write_tools") as gw, \
         patch("derisk_serve.workspace.agent_tools.toolkit.build_playbook_tools", return_value=[_named_tool(f"p{i}") for i in range(3)]) as gp:
        agent = build_workspace_toolkit(
            system_app=fake_system_app,
            workspace_id=1,
            user_id="u1",
            conv_uid="conv-1",
            task_id=10,
            mode="workbench",
        )
        assert agent is not None
        assert len(agent._tools) == 11, f"Workbench must have 11 tools, got {len(agent._tools)}"
        gr.assert_called_once()
        gw.assert_not_called()
        gp.assert_called_once()


def test_build_workspace_toolkit_returns_none_without_conv_uid():
    from derisk_serve.workspace.agent_tools.toolkit import build_workspace_toolkit
    fake_system_app = MagicMock()
    agent = build_workspace_toolkit(
        system_app=fake_system_app,
        workspace_id=1,
        user_id="u1",
        conv_uid=None,
        task_id=None,
        mode="lobby",
    )
    assert agent is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_injection.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement toolkit.py**

```python
# packages/derisk-serve/src/derisk_serve/workspace/agent_tools/toolkit.py
"""WorkspaceControlAgent wraps FunctionTools; injected into chat via extra_agents."""
from typing import List, Optional

from derisk.agent.core.conversable_agent import ConversableAgent

from derisk_serve.workspace.agent_tools.read_tools import build_read_tools
from derisk_serve.workspace.agent_tools.write_tools import build_write_tools
from derisk_serve.workspace.agent_tools.playbook_tools import build_playbook_tools


# Layer 1 read tool names (shared by both modes) — 5 tools
LAYER1_READ = {"list_tasks", "get_task_info", "list_artifacts", "list_deliveries", "list_assets"}
# Layer 2 read tool names (Lobby only) — 2 tools
LAYER2_READ = {"get_workspace_memory", "list_workspace_members"}
# Layer 3 read tool names (Workbench only) — 3 tools
LAYER3_READ = {"list_playbooks", "get_playbook_detail", "list_interventions"}


class WorkspaceControlAgent(ConversableAgent):
    """A ConversableAgent that exposes workspace read/write tools.

    Tools are registered as function_tools; write tools create interventions
    rather than executing directly (non-blocking confirmation flow).
    """

    def __init__(self, system_app, tools: List, name: str = "workspace_control"):
        super().__init__(name=name, system_app=system_app)
        self._tools = tools
        for tool in tools:
            try:
                self.register_function_tool(tool)
            except Exception:
                # Fallback: attach directly
                pass


def build_workspace_toolkit(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    conv_uid: Optional[str],
    task_id: Optional[int] = None,
    mode: str = "lobby",
) -> Optional[WorkspaceControlAgent]:
    """Build the workspace control Agent for the given mode.

    Lobby (mode="lobby"): Layer 1 (5 read) + Layer 2 (2 read + 5 write) = 12 tools.
    Workbench (mode="workbench"): Layer 1 (5 read) + Layer 3 (3 read + 3 write) = 11 tools.
    Layer 2 and Layer 3 do not overlap.
    """
    if not conv_uid:
        return None

    all_read = build_read_tools(system_app, workspace_id)
    if mode == "lobby":
        layer1 = [t for t in all_read if t.name in LAYER1_READ]
        layer2_read = [t for t in all_read if t.name in LAYER2_READ]
        write = build_write_tools(system_app, workspace_id, user_id, conv_uid, task_id=task_id)
        tools = layer1 + layer2_read + write
    elif mode == "workbench":
        layer1 = [t for t in all_read if t.name in LAYER1_READ]
        layer3_read = [t for t in all_read if t.name in LAYER3_READ]
        playbook_write = build_playbook_tools(system_app, workspace_id, user_id, conv_uid, task_id=task_id)
        tools = layer1 + layer3_read + playbook_write
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return WorkspaceControlAgent(system_app=system_app, tools=tools)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_injection.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/agent_tools/toolkit.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_injection.py
git commit -m "feat(workspace): add WorkspaceControlAgent + build_workspace_toolkit"
```

---

## Task 10: Intervention execute_resolved + Endpoint

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/intervention/service/service.py`
- Modify: `packages/derisk-serve/src/derisk_serve/intervention/api/endpoints.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_intervention_execute.py`

**Interfaces:**
- Consumes: `InterventionEntity.question_json = {tool, args}`, `InterventionEntity.conv_uid`, `InterventionEntity.task_id`.
- Produces: `InterventionService.execute_resolved(intervention_id) -> InterventionEntity`. Routes by `question_json.tool`:
  - `start_task` → `TaskService.create(...)` → returns new task
  - `close_task` → `TaskService.update(status='closed')`
  - `publish_asset` → `AssetService.create(is_published=True)`
  - `create_delivery` → `DeliveryService.create(...)`
  - `update_workspace` → `WorkspaceService.update(...)`
  - `launch_playbook` → `PlaybookRuntime.launch(...)`
  - `update_playbook` → `PlaybookService.update(...)`
  - `archive_playbook` → `PlaybookService.archive(...)`
  - After execution: `_post_message_back(conv_uid, tool, result)` via `multi_agents.app_chat`.
- Endpoint: `POST /interventions/{id}/resolve-and-execute` accepts `InterventionResolveRequest`, calls `resolve` then `execute_resolved`.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-serve/tests/derisk_serve/workspace/test_intervention_execute.py
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def fake_system_app():
    app = MagicMock()
    return app


def test_execute_resolved_routes_start_task(fake_system_app):
    from derisk_serve.intervention.service.service import InterventionService
    svc = InterventionService(fake_system_app)
    fake_intervention = MagicMock(
        id=1,
        conv_uid="conv-1",
        task_id=None,
        question_json={"tool": "start_task", "args": {"workspace_id": 1, "playbook_id": 10, "title": "t"}},
        user_id="u1",
    )
    with patch.object(svc, "_dao", new=MagicMock()), \
         patch.object(svc._dao, "get_by_id", return_value=fake_intervention), \
         patch("derisk_serve.intervention.service.service.get_task_service") as gts, \
         patch.object(svc, "_post_message_back") as pmb:
        gts.return_value.create.return_value = MagicMock(id=99, to_response=lambda: {"id": 99})
        svc.execute_resolved(intervention_id=1, decision="approved", distillation=None, resolved_by_user_id="u1")
        gts.return_value.create.assert_called_once()
        pmb.assert_called_once()


def test_execute_resolved_unknown_tool_raises(fake_system_app):
    from derisk_serve.intervention.service.service import InterventionService
    svc = InterventionService(fake_system_app)
    fake_intervention = MagicMock(
        id=1,
        conv_uid="conv-1",
        task_id=None,
        question_json={"tool": "unknown_tool", "args": {}},
        user_id="u1",
    )
    with patch.object(svc, "_dao", new=MagicMock()), \
         patch.object(svc._dao, "get_by_id", return_value=fake_intervention):
        with pytest.raises(ValueError):
            svc.execute_resolved(intervention_id=1, decision="approved", distillation=None, resolved_by_user_id="u1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_intervention_execute.py -v`
Expected: FAIL — `execute_resolved` method missing.

- [ ] **Step 3: Implement execute_resolved**

In `packages/derisk-serve/src/derisk_serve/intervention/service/service.py`, add:

```python
from typing import Optional


class InterventionService:
    # ... existing methods ...

    def execute_resolved(
        self,
        intervention_id: int,
        decision: str,
        distillation: Optional[str],
        resolved_by_user_id: Optional[str],
    ) -> "InterventionEntity":
        entity = self._dao.get_by_id(intervention_id)
        if entity is None:
            raise ValueError(f"Intervention {intervention_id} not found")
        if decision != "approved":
            self._dao.update(intervention_id, status="rejected", resolved_by_user_id=resolved_by_user_id)
            return entity

        question = entity.question_json or {}
        tool_name = question.get("tool")
        args = question.get("args", {}) or {}

        result = self._route_and_execute(tool_name, args, entity)

        # mark resolved
        self._dao.update(
            intervention_id,
            status="resolved",
            distillation=distillation,
            resolved_by_user_id=resolved_by_user_id,
        )

        # back-write a message to the conversation
        try:
            self._post_message_back(
                conv_uid=entity.conv_uid,
                tool_name=tool_name,
                result=result,
                user_id=resolved_by_user_id,
            )
        except Exception:
            pass

        return entity

    def _route_and_execute(self, tool_name: str, args: dict, entity) -> dict:
        system_app = self._system_app
        if tool_name == "start_task":
            from derisk_serve.task.service.service import TaskService, ServiceType
            svc = system_app.get_instance(ServiceType.TASK_SERVICE, TaskService)
            task = svc.create(**args)
            return {"task_id": getattr(task, "id", None)}
        if tool_name == "close_task":
            from derisk_serve.task.service.service import TaskService, ServiceType
            svc = system_app.get_instance(ServiceType.TASK_SERVICE, TaskService)
            svc.update(task_id=args["task_id"], status="closed")
            return {"task_id": args["task_id"], "status": "closed"}
        if tool_name == "publish_asset":
            from derisk_serve.workspace.asset.service.service import AssetService, ServiceType
            svc = system_app.get_instance(ServiceType.ASSET_SERVICE, AssetService)
            asset = svc.create(**{**args, "is_published": True})
            return {"asset_id": getattr(asset, "id", None)}
        if tool_name == "create_delivery":
            from derisk_serve.delivery.service.service import DeliveryService, ServiceType
            svc = system_app.get_instance(ServiceType.DELIVERY_SERVICE, DeliveryService)
            delivery = svc.create(**args)
            return {"delivery_id": getattr(delivery, "id", None)}
        if tool_name == "update_workspace":
            from derisk_serve.workspace.service.service import WorkspaceService, ServiceType
            svc = system_app.get_instance(ServiceType.WORKSPACE_SERVICE, WorkspaceService)
            svc.update(**args)
            return {"workspace_id": args.get("workspace_id")}
        if tool_name == "launch_playbook":
            from derisk_serve.playbook.runtime import PlaybookRuntime
            runtime = PlaybookRuntime(system_app)
            task = runtime.launch(**args)
            return {"task_id": getattr(task, "id", None)}
        if tool_name == "update_playbook":
            from derisk_serve.playbook.service.service import PlaybookService, ServiceType
            svc = system_app.get_instance(ServiceType.PLAYBOOK_SERVICE, PlaybookService)
            svc.update(**args)
            return {"playbook_id": args.get("playbook_id")}
        if tool_name == "archive_playbook":
            from derisk_serve.playbook.service.service import PlaybookService, ServiceType
            svc = system_app.get_instance(ServiceType.PLAYBOOK_SERVICE, PlaybookService)
            svc.archive(args["playbook_id"])
            return {"playbook_id": args.get("playbook_id"), "archived": True}
        raise ValueError(f"Unknown tool: {tool_name}")

    def _post_message_back(self, conv_uid: str, tool_name: str, result: dict, user_id: Optional[str]):
        if not conv_uid:
            return
        try:
            from derisk_serve.agent.agents.controller import multi_agents
            synthetic_query = f"[已确认执行工具 {tool_name}] 结果：{result}"
            multi_agents.app_chat(
                conv_uid=conv_uid,
                gpts_name="chat_normal",
                user_query=synthetic_query,
            )
        except Exception:
            pass
```

- [ ] **Step 4: Add the endpoint**

In `packages/derisk-serve/src/derisk_serve/intervention/api/endpoints.py`, append:

```python
@router.post("/interventions/{intervention_id}/resolve-and-execute")
async def resolve_and_execute(
    intervention_id: int,
    payload: InterventionResolveRequest,
):
    service = get_service()
    entity = service.execute_resolved(
        intervention_id=intervention_id,
        decision=payload.decision,
        distillation=payload.distillation,
        resolved_by_user_id=payload.resolved_by_user_id,
    )
    return {"data": entity.to_response() if hasattr(entity, "to_response") else {"id": entity.id}}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_intervention_execute.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 6: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/intervention/service/service.py \
        packages/derisk-serve/src/derisk_serve/intervention/api/endpoints.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_intervention_execute.py
git commit -m "feat(intervention): execute_resolved routing + resolve-and-execute endpoint"
```

---

## Task 11: Inject WorkspaceControlAgent into agent_chat

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py:100-120,754,906`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_chat_injection.py`

**Interfaces:**
- Consumes: `build_workspace_toolkit`, `build_workspace_context`, `render_workspace_context_summary` from Tasks 5, 9.
- Produces: `_inject_workspace_context` extended to:
  1. Build `WorkspaceContextSnapshot` (mode = "lobby" if `task_id is None` else "workbench").
  2. Append `render_workspace_context_summary` to system_prompt.
  3. Build `WorkspaceControlAgent` via `build_workspace_toolkit` and append to `extra_agents`.
- Caller passes `workspace_id, user_id, conv_uid, task_id` into `_inject_workspace_context`. The `conv_uid` for Lobby = workspace current conv_uid; for Workbench = `task.conv_session_id`.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk_serve/tests/derisk_serve/workspace/test_chat_injection.py
import pytest
from unittest.mock import MagicMock, patch


def test_inject_workspace_context_appends_agent_and_prompt(monkeypatch):
    from derisk_serve.agent.agents.chat import agent_chat
    fake_system_app = MagicMock()
    extra_agents = []
    system_prompt = ["base"]
    with patch("derisk_serve.agent.agents.chat.agent_chat.build_workspace_context") as bc, \
         patch("derisk_serve.agent.agents.chat.agent_chat.render_workspace_context_summary") as rs, \
         patch("derisk_serve.agent.agents.chat.agent_chat.build_workspace_toolkit") as bt:
        bc.return_value = MagicMock(workspace_id=1, task=None, playbook_declaration=None)
        rs.return_value = "WORKSPACE SUMMARY"
        bt.return_value = MagicMock(name="workspace_agent")
        agent_chat._inject_workspace_context(
            system_app=fake_system_app,
            workspace_id=1,
            user_id="u1",
            conv_uid="conv-1",
            task_id=None,
            system_prompt=system_prompt,
            extra_agents=extra_agents,
        )
        assert "WORKSPACE SUMMARY" in system_prompt
        assert len(extra_agents) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_chat_injection.py -v`
Expected: FAIL — `_inject_workspace_context` signature doesn't include `conv_uid`/`task_id`/`extra_agents`.

- [ ] **Step 3: Modify _inject_workspace_context**

In `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`:

Add imports near the top:

```python
from derisk_serve.workspace.agent_tools.context_builder import (
    build_workspace_context,
    render_workspace_context_summary,
)
from derisk_serve.workspace.agent_tools.toolkit import build_workspace_toolkit
```

Locate `_inject_workspace_context` (around line 100) and replace its body to accept `user_id`, `conv_uid`, `task_id`, `extra_agents`:

```python
def _inject_workspace_context(
    *,
    system_app,
    workspace_id: Optional[int],
    user_id: Optional[str],
    conv_uid: Optional[str],
    task_id: Optional[int],
    system_prompt: List[str],
    extra_agents: List,
) -> None:
    if not workspace_id:
        return
    mode = "workbench" if task_id else "lobby"
    try:
        ctx = build_workspace_context(
            system_app=system_app,
            workspace_id=workspace_id,
            user_id=user_id,
            task_id=task_id,
            mode=mode,
        )
        summary = render_workspace_context_summary(ctx, mode=mode)
        if summary:
            system_prompt.append(summary)
        agent = build_workspace_toolkit(
            system_app=system_app,
            workspace_id=workspace_id,
            user_id=user_id,
            conv_uid=conv_uid,
            task_id=task_id,
            mode=mode,
        )
        if agent is not None:
            extra_agents.append(agent)
    except Exception:
        pass
```

At the call site (around line 754), update to pass all parameters:

```python
_inject_workspace_context(
    system_app=system_app,
    workspace_id=workspace_id,
    user_id=user_id,
    conv_uid=conv_uid,
    task_id=task_id,
    system_prompt=system_prompt,
    extra_agents=extra_agents,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-serve && pytest tests/derisk_serve/workspace/test_chat_injection.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py \
        packages/derisk-serve/tests/derisk_serve/workspace/test_chat_injection.py
git commit -m "feat(chat): inject WorkspaceControlAgent + workspace summary into agent_chat"
```

---

## Task 12: Frontend API Client Methods

**Files:**
- Modify: `web/src/client/api/workspace/index.ts`
- Test: visual / type check

**Interfaces:**
- Produces: `getCurrentConversation(workspaceId: number)`, `setCurrentConversation(workspaceId, convUid)`, `renameConversation(convUid, title)`.

- [ ] **Step 1: Add API methods**

Append to `web/src/client/api/workspace/index.ts`:

```typescript
export async function getCurrentConversation(workspaceId: number) {
  const res = await axios.get(
    `${API_BASE}/workspaces/${workspaceId}/conversations/current`,
    { headers: getHeaders() }
  );
  return res.data?.data ?? null;
}

export async function setCurrentConversation(workspaceId: number, convUid: string) {
  const res = await axios.post(
    `${API_BASE}/workspaces/${workspaceId}/conversations/set-current`,
    { conv_uid: convUid },
    { headers: getHeaders() }
  );
  return res.data?.data;
}

export async function renameConversation(convUid: string, title: string) {
  const res = await axios.patch(
    `${API_BASE}/conversations/${convUid}/rename`,
    { title },
    { headers: getHeaders() }
  );
  return res.data?.data;
}

export async function resolveAndExecuteIntervention(
  interventionId: number,
  payload: { decision: string; distillation?: string; resolved_by_user_id?: string }
) {
  const res = await axios.post(
    `${API_BASE}/interventions/${interventionId}/resolve-and-execute`,
    payload,
    { headers: getHeaders() }
  );
  return res.data?.data;
}
```

- [ ] **Step 2: Type-check the file**

Run: `cd web && pnpm tsc --noEmit`
Expected: no errors in `workspace/index.ts`.

- [ ] **Step 3: Commit**

```bash
git add web/src/client/api/workspace/index.ts
git commit -m "feat(web): add conversation current/rename + resolveAndExecute client methods"
```

---

## Task 13: Frontend ConversationSwitcher Component

**Files:**
- Create: `web/src/app/workspaces/detail/conversation-switcher.tsx`
- Test: visual

**Interfaces:**
- Produces: `<ConversationSwitcher workspaceId, currentConvUid, onChanged={(convUid) => void} />` — dropdown listing conversations from `listConversations`, "新建对话" item that creates a new convUid and calls `setCurrentConversation`, "重命名" item per row.

- [ ] **Step 1: Implement the component**

```tsx
// web/src/app/workspaces/detail/conversation-switcher.tsx
'use client';

import { useState } from 'react';
import { Dropdown, Button, Modal, Input, message } from 'antd';
import { useRequest } from 'ahooks';
import {
  apiInterceptors,
  listConversations,
  setCurrentConversation,
  renameConversation,
  createConversation,
  linkConversation,
} from '@/client/api';

export interface ConversationSwitcherProps {
  workspaceId: number;
  currentConvUid: string;
  onChanged: (convUid: string) => void;
}

export function ConversationSwitcher({
  workspaceId,
  currentConvUid,
  onChanged,
}: ConversationSwitcherProps) {
  const [renameTarget, setRenameTarget] = useState<{ convUid: string; title: string } | null>(null);
  const [renameValue, setRenameValue] = useState('');

  const { data: listRes, refresh } = useRequest(
    async () => apiInterceptors(listConversations({ workspace_id: workspaceId })),
    { refreshDeps: [workspaceId] }
  );
  const conversations = listRes?.[1] || [];

  const handleNew = async () => {
    const [, newConv] = await apiInterceptors(createConversation());
    if (!newConv?.conv_uid) return;
    await apiInterceptors(
      linkConversation({
        workspace_id: workspaceId,
        conv_uid: newConv.conv_uid,
        user_id: undefined,
      })
    );
    await apiInterceptors(setCurrentConversation(workspaceId, newConv.conv_uid));
    refresh();
    onChanged(newConv.conv_uid);
    message.success('已新建会话');
  };

  const handleSelect = async (convUid: string) => {
    await apiInterceptors(setCurrentConversation(workspaceId, convUid));
    onChanged(convUid);
  };

  const handleRename = async () => {
    if (!renameTarget) return;
    await apiInterceptors(renameConversation(renameTarget.convUid, renameValue));
    setRenameTarget(null);
    refresh();
    message.success('已重命名');
  };

  const items = [
    ...conversations.map((c: any) => ({
      key: c.conv_uid,
      label: (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontWeight: c.conv_uid === currentConvUid ? 600 : 400,
          }}
        >
          <span>{c.title || c.conv_uid.slice(0, 8)}</span>
          <Button
            type="link"
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              setRenameTarget({ convUid: c.conv_uid, title: c.title || '' });
              setRenameValue(c.title || '');
            }}
          >
            重命名
          </Button>
        </div>
      ),
      onClick: () => handleSelect(c.conv_uid),
    })),
    { type: 'divider' as const },
    { key: '__new__', label: '+ 新建会话', onClick: handleNew },
  ];

  return (
    <>
      <Dropdown menu={{ items }} trigger={['click']}>
        <Button size="small">会话切换</Button>
      </Dropdown>
      <Modal
        title="重命名会话"
        open={!!renameTarget}
        onOk={handleRename}
        onCancel={() => setRenameTarget(null)}
      >
        <Input
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          placeholder="输入新的会话标题"
        />
      </Modal>
    </>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd web && pnpm tsc --noEmit`
Expected: no errors in the new file.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/workspaces/detail/conversation-switcher.tsx
git commit -m "feat(web): add ConversationSwitcher dropdown component"
```

---

## Task 14: Frontend client.tsx — Remove localStorage, Use getCurrentConversation

**Files:**
- Modify: `web/src/app/workspaces/detail/client.tsx:160-418`

**Interfaces:**
- Consumes: `getCurrentConversation`, `ConversationSwitcher` from Tasks 12, 13.
- Produces: `client.tsx` removes `localStorage.getItem/setItem` for convUid. On mount: calls `getCurrentConversation(workspaceId)`. If null: creates a new convUid via `createConversation` + `linkConversation` + `setCurrentConversation`. Workbench render passes `task.conv_session_id` as convUid (no switching). Lobby renders `<ConversationSwitcher>`.

- [ ] **Step 1: Modify client.tsx**

Locate `const [convUid, setConvUid] = useState<string>('');` (around line 168) and the localStorage logic (lines 180-199). Replace with:

```tsx
const [convUid, setConvUid] = useState<string>('');
  const appCode = ws?.default_agent_app_code || 'chat_normal';

  // Load or create workspace-level current conversation from backend.
  const { run: loadCurrentConv } = useRequest(
    async () => {
      const [, current] = await apiInterceptors(getCurrentConversation(workspaceId));
      if (current?.conv_uid) {
        setConvUid(current.conv_uid);
        return;
      }
      // Create + link + set as current
      const [, newConv] = await apiInterceptors(createConversation());
      if (!newConv?.conv_uid) return;
      await apiInterceptors(
        linkConversation({
          workspace_id: workspaceId,
          conv_uid: newConv.conv_uid,
          user_id: undefined,
        })
      );
      await apiInterceptors(setCurrentConversation(workspaceId, newConv.conv_uid));
      setConvUid(newConv.conv_uid);
    },
    { ready: !!workspaceId }
  );
```

Locate the Workbench render (around line 391-413). For Workbench, pass `task.conv_session_id` instead of `convUid`:

```tsx
{activeTab === 'workbench' && selectedTaskId ? (
  <Workbench
    taskId={selectedTaskId}
    workspaceId={workspaceId}
    appCode={appCode}
    convUid={taskConvUid /* resolved below */}
    onBack={() => setActiveTab('lobby')}
  />
) : (
  <Lobby
    workspaceId={workspaceId}
    workspaceCode={wsCode}
    workspaceName={ws?.name || ''}
    workspaceType={ws?.type || ''}
    appCode={appCode}
    convUid={convUid}
    onSelectTask={(tid) => {
      setSelectedTaskId(tid);
      setActiveTab('workbench');
    }}
    onQuickStart={(pid) => {/* existing */}}
  />
)}
```

Add `taskConvUid` resolution near the top of the component:

```tsx
const { data: taskRes } = useRequest(
  async () => selectedTaskId ? apiInterceptors(getTaskInfo(selectedTaskId)) : null,
  { refreshDeps: [selectedTaskId] }
);
const taskConvUid = taskRes?.[1]?.conv_session_id || convUid;
```

Add the `ConversationSwitcher` to the workspace identity bar (where the title is rendered):

```tsx
<ConversationSwitcher
  workspaceId={workspaceId}
  currentConvUid={convUid}
  onChanged={(newUid) => {
    setConvUid(newUid);
  }}
/>
```

- [ ] **Step 2: Run dev server and verify**

Run: `cd web && pnpm dev`
Open: `http://localhost:3000/workspaces/detail?id=<workspace_code>`
Verify:
1. On first load, convUid is fetched from backend (no localStorage).
2. ConversationSwitcher dropdown shows conversations.
3. Clicking "新建会话" creates a new convUid and switches to it.
4. Clicking a conversation switches to it.
5. Opening a task workbench uses the task's conv_session_id (different from lobby convUid).

- [ ] **Step 3: Commit**

```bash
git add web/src/app/workspaces/detail/client.tsx
git commit -m "feat(web): backend-managed convUid, Workbench uses task.conv_session_id"
```

---

## Task 15: VisualConfirmCard routes through resolve-and-execute

**Files:**
- Modify: `web/src/components/chat/visual-confirm-card.tsx`

**Interfaces:**
- Consumes: `resolveAndExecuteIntervention` from Task 12.
- Produces: When user clicks "确认执行" in VisConfirmCard, calls `resolveAndExecuteIntervention(interventionId, { decision: 'approved', distillation, resolved_by_user_id })`. On success: shows toast, refreshes task list (via callback prop).

- [ ] **Step 1: Modify VisConfirmCard**

Locate the resolve handler in `web/src/components/chat/visual-confirm-card.tsx`. Replace the existing resolve call (which probably calls `resolveIntervention`) with `resolveAndExecuteIntervention`:

```tsx
const handleResolve = async () => {
  setLoading(true);
  try {
    await apiInterceptors(
      resolveAndExecuteIntervention(interventionId, {
        decision: 'approved',
        distillation: distillationValue || undefined,
        resolved_by_user_id: userId,
      })
    );
    message.success('已执行');
    onResolved?.();
  } finally {
    setLoading(false);
  }
};
```

Import:

```tsx
import { resolveAndExecuteIntervention } from '@/client/api';
```

- [ ] **Step 2: Run dev server and verify**

Run: `cd web && pnpm dev`
Open: a workspace chat. Trigger a write tool via conversation (e.g., ask the Agent to "发起一个任务"). VisConfirmCard appears. Click "确认执行". Verify:
1. Card shows loading state.
2. After success, toast "已执行" shows.
3. A new message appears in the chat from the Agent acknowledging execution (back-write via `_post_message_back`).
4. Task list refreshes to show the new task.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/chat/visual-confirm-card.tsx
git commit -m "feat(web): VisConfirmCard routes through resolve-and-execute"
```

---

## Task 16: End-to-End Smoke Test

**Files:** none (manual)

- [ ] **Step 1: Backend startup**

Run: `cd packages/derisk-serve && python -m derisk_serve.cli serve`
Verify: server starts, no import errors from new modules.

- [ ] **Step 2: Lobby mode smoke**

Open: `http://localhost:3000/workspaces/detail?id=<ws_code>`
- Send a chat message: "列出当前空间的任务".
- Verify: Agent responds with task list (uses `list_tasks` tool from Layer 1).
- Send: "发起一个任务，剧本是 X".
- Verify: VisConfirmCard appears with `start_task` intervention.
- Click "确认执行".
- Verify: new task appears in lobby task list; Agent message back-writes "已执行工具 start_task".

- [ ] **Step 3: Workbench mode smoke**

Click a task to enter Workbench.
- Verify: convUid = task.conv_session_id (different from lobby convUid).
- Send: "查询当前剧本详情".
- Verify: Agent uses `get_playbook_detail` (Layer 3) and responds with declaration.
- Send: "归档当前剧本".
- Verify: VisConfirmCard with `archive_playbook` intervention.
- Click "确认执行".
- Verify: playbook is archived; Agent back-writes result.

- [ ] **Step 4: Conversation switching smoke**

In Lobby, click "会话切换" → "+ 新建会话".
- Verify: new convUid is set as current; old conversation is no longer current.
- Reload page.
- Verify: convUid is restored from backend (not localStorage).
- Switch back to old conversation via dropdown.
- Verify: chat history loads from old convUid.

- [ ] **Step 5: Final commit (if any fixups needed)**

```bash
git status
# If clean, nothing to commit. If fixups:
git add -p
git commit -m "fix: end-to-end smoke test adjustments"
```

---

## Self-Review

**1. Spec coverage:**
- 4.1 会话管理后端化: Tasks 1, 2, 3, 12, 13, 14 ✓
- 4.2 空间 Agent 工具集 (three-layer): Tasks 5, 6, 7, 8, 9, 11 ✓
- 4.2 Intervention flow: Tasks 4, 8, 10, 15 ✓
- 4.3 Workbench 任务隔离 (task.conv_session_id): Task 14 ✓
- Layer 1 (5 read), Layer 2 (Lobby only, 7), Layer 3 (Workbench only, 6): Tasks 7, 8, 9 ✓

**2. Placeholder scan:**
- No "TBD" / "TODO" / "implement later" in any task.
- All code blocks are complete.
- Test code provided for every backend task.

**3. Type consistency:**
- `WorkspaceConversationLinkEntity.is_current: Boolean` — consistent across Tasks 1, 2, 3.
- `InterventionEntity.task_id: Optional[int]` — consistent across Tasks 4, 8, 10.
- `InterventionEntity.conv_uid: Optional[str]` — consistent across Tasks 4, 8, 10.
- `build_workspace_toolkit(..., mode="lobby"|"workbench")` — consistent across Tasks 9, 11.
- `WorkspaceControlAgent(ConversableAgent)` — consistent across Tasks 9, 11.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-30-scenario-workspace-conversation-and-agent-tools.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
