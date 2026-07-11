"""playbook_command 入口与 scene_agent_workspace render_name 测试。"""
import sys
from unittest.mock import MagicMock

import pytest

# The task package __init__ eagerly imports endpoints -> runtime -> agent
# controller, which requires derisk_app.config. Provide a lightweight stub so
# unit tests can import chat modules without the full derisk_app package
# installed.
if "derisk_app.config" not in sys.modules:
    sys.modules["derisk_app"] = MagicMock()
    sys.modules["derisk_app.config"] = MagicMock()

from derisk_serve.agent.agents.chat.agent_chat import AgentChat
from derisk_serve.agent.agents.chat.agent_chat_simple import SimpleAgentChat
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