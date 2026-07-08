"""Tests for workspace agent context builder."""
from unittest.mock import MagicMock, patch

import pytest


def test_build_workspace_context_lobby():
    from derisk_serve.workspace.agent_tools.context_builder import (
        build_workspace_context,
    )

    fake_system_app = MagicMock()
    fake_workspace = MagicMock(
        name="ws", id=1, default_agent_app_code="chat_normal"
    )
    fake_materialized = MagicMock(dynamic_resources=[], extra_agents=[])
    with patch(
        "derisk_serve.workspace.agent_tools.context_builder.get_workspace_service"
    ) as gs, patch(
        "derisk_serve.workspace.agent_tools.context_builder.materialize_resources"
    ) as mr:
        gs.return_value.get_by_id.return_value = fake_workspace
        mr.return_value = fake_materialized
        ctx = build_workspace_context(
            system_app=fake_system_app,
            workspace_id=1,
            user_id="u1",
            task_id=None,
            mode="lobby",
        )
    assert ctx.workspace is fake_workspace
    assert ctx.materialized_resources is fake_materialized
    assert ctx.task is None
    assert ctx.playbook_declaration is None
    assert ctx.user_id == "u1"
    assert ctx.workspace_id == 1
    assert ctx.task_id is None


def test_build_workspace_context_missing_workspace():
    from derisk_serve.workspace.agent_tools.context_builder import (
        build_workspace_context,
    )

    fake_system_app = MagicMock()
    fake_materialized = MagicMock(dynamic_resources=[], extra_agents=[])
    with patch(
        "derisk_serve.workspace.agent_tools.context_builder.get_workspace_service"
    ) as gs, patch(
        "derisk_serve.workspace.agent_tools.context_builder.materialize_resources"
    ) as mr:
        gs.return_value.get_by_id.return_value = None
        mr.return_value = fake_materialized
        ctx = build_workspace_context(
            system_app=fake_system_app,
            workspace_id=99,
            user_id="u1",
            task_id=None,
            mode="lobby",
        )
    assert ctx.workspace is None
    assert ctx.workspace_id == 99
    assert ctx.materialized_resources is fake_materialized


def test_build_workspace_context_with_task_and_playbook():
    from derisk_serve.workspace.agent_tools.context_builder import (
        build_workspace_context,
    )

    fake_system_app = MagicMock()
    fake_workspace = MagicMock(name="ws", id=1)
    fake_materialized = MagicMock(dynamic_resources=[], extra_agents=[])
    fake_task = MagicMock(id=2, title="task-title", playbook_id=10)
    fake_playbook = MagicMock(
        id=10, declaration={"skills": [{"name": "skill1"}]}
    )
    with patch(
        "derisk_serve.workspace.agent_tools.context_builder.get_workspace_service"
    ) as gs, patch(
        "derisk_serve.workspace.agent_tools.context_builder.materialize_resources"
    ) as mr, patch(
        "derisk_serve.workspace.agent_tools.context_builder.get_task_service"
    ) as gts, patch(
        "derisk_serve.workspace.agent_tools.context_builder.get_playbook_service"
    ) as gps:
        gs.return_value.get_by_id.return_value = fake_workspace
        mr.return_value = fake_materialized
        gts.return_value.get_by_id.return_value = fake_task
        gps.return_value.get_by_id.return_value = fake_playbook
        ctx = build_workspace_context(
            system_app=fake_system_app,
            workspace_id=1,
            user_id="u1",
            task_id=2,
            mode="workbench",
        )
    assert ctx.task is fake_task
    assert ctx.playbook_declaration == {"skills": [{"name": "skill1"}]}
    assert ctx.task_id == 2


def test_render_summary_lobby_contains_workspace_name():
    from derisk_serve.workspace.agent_tools.context_builder import (
        build_workspace_context,
        render_workspace_context_summary,
    )

    fake_system_app = MagicMock()
    fake_workspace = MagicMock(id=1)
    fake_workspace.name = "SRE空间"
    fake_materialized = MagicMock(dynamic_resources=[], extra_agents=[])
    with patch(
        "derisk_serve.workspace.agent_tools.context_builder.get_workspace_service"
    ) as gs, patch(
        "derisk_serve.workspace.agent_tools.context_builder.materialize_resources"
    ) as mr:
        gs.return_value.get_by_id.return_value = fake_workspace
        mr.return_value = fake_materialized
        ctx = build_workspace_context(
            system_app=fake_system_app,
            workspace_id=1,
            user_id="u1",
            mode="lobby",
        )
    summary = render_workspace_context_summary(ctx, mode="lobby")
    assert "空间" in summary or "workspace" in summary.lower()
    assert "SRE空间" in summary


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


def test_render_summary_workbench_with_task_and_skills():
    from derisk_serve.workspace.agent_tools.context_builder import (
        WorkspaceContextSnapshot,
        render_workspace_context_summary,
    )

    fake_workspace = MagicMock(id=1)
    fake_workspace.name = "Ops空间"
    fake_task = MagicMock(id=5)
    fake_task.title = "Fix bug"
    ctx = WorkspaceContextSnapshot(
        workspace=fake_workspace,
        materialized_resources=MagicMock(dynamic_resources=[], extra_agents=[]),
        task=fake_task,
        playbook_declaration={"skills": [{"name": "analyze"}, {"name": "fix"}]},
        user_id="u1",
        workspace_id=1,
        task_id=5,
    )
    summary = render_workspace_context_summary(ctx, mode="workbench")
    assert "Ops空间" in summary
    assert "Fix bug" in summary
    assert "analyze" in summary
    assert "fix" in summary


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
    fake_playbook = MagicMock(id=7, scenario_type="report")
    fake_playbook.name = "报告生成"
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
