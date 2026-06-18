"""text_utils 测试。"""

from derisk.agent.expand.react_master_agent.context_engine.text_utils import (
    DEFAULT_CHARS_PER_TOKEN,
    build_user_content,
    estimate_message_tokens,
    estimate_tokens_text,
    extract_text_content,
)

from .conftest import FakeMsg


def test_extract_text_from_str():
    assert extract_text_content("hello") == "hello"


def test_extract_text_from_none():
    assert extract_text_content(None) == ""


def test_extract_text_from_list_of_str():
    assert extract_text_content(["a", "b"]) == "a\nb"


def test_extract_text_from_list_of_dict_objects():
    content = [{"object": {"data": "x"}}, {"object": {"data": "y"}}]
    assert extract_text_content(content) == "x\ny"


def test_build_user_content_plain_text():
    msg = FakeMsg("c1", "human", "m1", content="问题")
    assert build_user_content(msg) == "问题"


def test_build_user_content_legacy_multimodal():
    msg = FakeMsg(
        "c1",
        "human",
        "m1",
        content="看图",
        content_types=["image_url"],
        context={"image_url": "http://x/a.png"},
    )
    result = build_user_content(msg)
    assert isinstance(result, list)
    # 含 text 部分 + image_url 部分
    types = {p.get("type") for p in result}
    assert "text" in types
    assert "image_url" in types


def test_build_user_content_multimodal_multiple_urls():
    msg = FakeMsg(
        "c1",
        "human",
        "m1",
        content="",
        content_types=["image_url"],
        context={"image_url": ["http://x/a.png", "http://x/b.png"]},
    )
    result = build_user_content(msg)
    imgs = [p for p in result if p.get("type") == "image_url"]
    assert len(imgs) == 2


def test_estimate_tokens_matches_chars_per_token():
    text = "x" * 40
    assert estimate_tokens_text(text) == 40 // DEFAULT_CHARS_PER_TOKEN


def test_estimate_tokens_min_one():
    assert estimate_tokens_text("") == 1


def test_estimate_message_tokens_includes_tool_calls():
    msg = {
        "role": "ai",
        "content": "x" * 8,
        "tool_calls": [{"id": "t1", "function": {"name": "f", "arguments": "{}"}}],
    }
    # content 8 chars + tool_calls json > content alone
    only_content = estimate_message_tokens({"role": "ai", "content": "x" * 8})
    assert estimate_message_tokens(msg) > only_content
