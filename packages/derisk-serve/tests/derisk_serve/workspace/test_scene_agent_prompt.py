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
