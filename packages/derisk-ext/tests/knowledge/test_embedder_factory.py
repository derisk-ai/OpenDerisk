"""Tests for the embedder factory (RFC 004 §6).

Validates that `ProviderEmbeddings` correctly:
- Builds the `/embeddings` URL from a provider's base_url
- Resolves api_key from config or env fallback
- Calls `requests.post` with the right payload
- Parses the OpenAI-compatible response shape
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from derisk_ext.knowledge.embedder_factory import (
    EmbedderCache,
    ProviderEmbeddings,
    get_embedder,
)


def _fake_response(payload: Dict[str, Any]):
    """Build a mock requests.Response-like object."""
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_provider_embeddings_builds_url_openai():
    emb = ProviderEmbeddings(
        {
            "model": "text-embedding-3-small",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
        }
    )
    assert emb._api_url == "https://api.openai.com/v1/embeddings"
    assert emb._api_key == "sk-test"
    assert emb._model_name == "text-embedding-3-small"


def test_provider_embeddings_resolves_env_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    emb = ProviderEmbeddings(
        {
            "model": "text-embedding-3-small",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "${OPENAI_API_KEY}",
        }
    )
    assert emb._api_key == "sk-from-env"


def test_provider_embeddings_tongyi_native_url():
    """Tongyi native endpoint gets normalized to text-embedding path."""
    emb = ProviderEmbeddings(
        {
            "model": "text-embedding-v3",
            "provider": "tongyi",
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "api_key": "sk-tongyi",
        }
    )
    assert "/text-embedding" in emb._api_url


def test_embed_documents_calls_requests_with_correct_payload():
    emb = ProviderEmbeddings(
        {
            "model": "text-embedding-3-small",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
        }
    )
    fake_resp = _fake_response(
        {
            "data": [
                {"index": 1, "embedding": [0.1, 0.2, 0.3]},
                {"index": 0, "embedding": [0.4, 0.5, 0.6]},
            ]
        }
    )
    with patch("requests.post", return_value=fake_resp) as mock_post:
        vecs: List[List[float]] = emb.embed_documents(["hello", "world"])

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.openai.com/v1/embeddings"
    payload = kwargs["json"]
    assert payload["model"] == "text-embedding-3-small"
    assert payload["input"] == ["hello", "world"]
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer sk-test"

    # Response must be sorted by index
    assert vecs == [[0.4, 0.5, 0.6], [0.1, 0.2, 0.3]]


def test_embed_query_returns_single_vector():
    emb = ProviderEmbeddings(
        {
            "model": "text-embedding-3-small",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
        }
    )
    fake_resp = _fake_response(
        {"data": [{"index": 0, "embedding": [0.7, 0.8]}]}
    )
    with patch("requests.post", return_value=fake_resp):
        vec = emb.embed_query("one")
    assert vec == [0.7, 0.8]


def test_get_embedder_raises_when_model_not_registered(monkeypatch):
    """If ModelConfigCache has no entry for the model, raise ValueError."""
    from derisk.agent.util.llm import model_config_cache as mcc_mod

    monkeypatch.setattr(mcc_mod.ModelConfigCache, "get_config", staticmethod(lambda name: None))
    with pytest.raises(ValueError, match="not registered"):
        get_embedder("nonexistent-model")


def test_get_embedder_returns_provider_embeddings_when_registered(monkeypatch):
    from derisk.agent.util.llm import model_config_cache as mcc_mod

    fake_config = {
        "model": "text-embedding-3-small",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-test",
    }
    monkeypatch.setattr(
        mcc_mod.ModelConfigCache, "get_config", staticmethod(lambda name: fake_config)
    )
    emb = get_embedder("text-embedding-3-small")
    assert isinstance(emb, ProviderEmbeddings)
    assert emb._model_name == "text-embedding-3-small"


def test_embedder_cache_returns_same_instance_for_same_model(monkeypatch):
    from derisk.agent.util.llm import model_config_cache as mcc_mod

    fake_config = {
        "model": "text-embedding-3-small",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-test",
    }
    monkeypatch.setattr(
        mcc_mod.ModelConfigCache, "get_config", staticmethod(lambda name: fake_config)
    )
    cache = EmbedderCache()
    a = cache.get("text-embedding-3-small")
    b = cache.get("text-embedding-3-small")
    assert a is b
