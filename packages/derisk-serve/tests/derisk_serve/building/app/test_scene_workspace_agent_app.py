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
