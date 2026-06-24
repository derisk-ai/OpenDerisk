"""Proxy-based embedding / rerank implementations.

These replace the old cluster-backed ``RemoteEmbeddings`` / ``RemoteRerankEmbeddings``
which routed requests through ``WorkerManager``. The proxy implementations call
the provider HTTP API directly, reading all parameters from
``EmbeddingModelConfig`` (name / provider / api_key / api_url / backend / extra).

Supported providers:

* ``proxy/openai`` — any OpenAI-compatible ``/v1/embeddings`` endpoint.
* ``proxy/tongyi`` — DashScope text-embedding (native or compatible-mode).
* ``proxy/ollama`` — Ollama ``/api/embeddings``.

Rerank:

* ``proxy/tongyi`` — DashScope ``/services/rerank/text-rerank/text-rerank``.
* ``proxy/jina`` — Jina rerank API.
* ``proxy/openai`` — OpenAI-compatible rerank (e.g. Cohere via OpenAI gateway).

Adding a new provider only requires extending ``_PROVIDER_BUILDERS`` /
``_RERANK_PROVIDERS`` below.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

import requests

from derisk.core import Embeddings, RerankEmbeddings

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60


def _resolve_api_key(api_key: Optional[str], provider: str) -> Optional[str]:
    """Resolve an API key from config, env, or system secrets."""
    if api_key and not api_key.startswith("${"):
        return api_key
    # Try env by provider
    env_map = {
        "proxy/openai": "OPENAI_API_KEY",
        "proxy/tongyi": "DASHSCOPE_API_KEY",
        "proxy/ollama": "OLLAMA_API_KEY",
        "proxy/jina": "JINA_API_KEY",
    }
    env_name = env_map.get(provider)
    if env_name:
        import os

        return os.getenv(env_name)
    return api_key


def _openai_embedding_call(
    config: "EmbeddingModelConfigLike", texts: List[str]
) -> List[List[float]]:
    """Call an OpenAI-compatible /v1/embeddings endpoint."""
    api_url = config.api_url or "https://api.openai.com/v1"
    api_url = api_url.rstrip("/")
    if not api_url.endswith("/embeddings"):
        # Append /embeddings if api_url is just the base.
        api_url = f"{api_url}/embeddings"
    model_name = config.backend or config.name
    api_key = _resolve_api_key(config.api_key, config.provider)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: Dict[str, Any] = {"model": model_name, "input": texts}
    payload.update(config.extra or {})
    resp = requests.post(api_url, json=payload, headers=headers, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    # OpenAI format: {"data": [{"embedding": [...], "index": 0}, ...]}
    items = sorted(data["data"], key=lambda x: x.get("index", 0))
    return [item["embedding"] for item in items]


def _tongyi_embedding_call(
    config: "EmbeddingModelConfigLike", texts: List[str]
) -> List[List[float]]:
    """Call DashScope text-embedding.

    If ``api_url`` ends with ``compatible-mode`` (or compatible-mode/v1), defer
    to the OpenAI-compatible path. Otherwise use the native DashScope API.
    """
    api_url = (config.api_url or "").lower()
    if "compatible-mode" in api_url:
        return _openai_embedding_call(config, texts)

    endpoint = config.api_url or "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
    model_name = config.backend or config.name
    api_key = _resolve_api_key(config.api_key, config.provider)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload: Dict[str, Any] = {
        "model": model_name,
        "input": {"texts": texts},
    }
    payload.update(config.extra or {})
    resp = requests.post(endpoint, json=payload, headers=headers, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    # DashScope format: {"output": {"embeddings": [{"embedding": [...], "text_index": 0}, ...]}}
    items = sorted(
        data.get("output", {}).get("embeddings", []),
        key=lambda x: x.get("text_index", 0),
    )
    return [item["embedding"] for item in items]


def _ollama_embedding_call(
    config: "EmbeddingModelConfigLike", texts: List[str]
) -> List[List[float]]:
    """Call Ollama /api/embeddings (one text per call)."""
    api_url = config.api_url or "http://localhost:11434/api/embeddings"
    model_name = config.backend or config.name
    results: List[List[float]] = []
    for text in texts:
        payload = {"model": model_name, "prompt": text}
        payload.update(config.extra or {})
        resp = requests.post(api_url, json=payload, timeout=_DEFAULT_TIMEOUT)
        resp.raise_for_status()
        results.append(resp.json()["embedding"])
    return results


_PROVIDER_BUILDERS: Dict[str, Callable[["EmbeddingModelConfigLike", List[str]], List[List[float]]]] = {
    "proxy/openai": _openai_embedding_call,
    "proxy/tongyi": _tongyi_embedding_call,
    "proxy/ollama": _ollama_embedding_call,
}


def _tongyi_rerank_call(
    config: "EmbeddingModelConfigLike", query: str, candidates: List[str]
) -> List[float]:
    endpoint = config.api_url or "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    model_name = config.backend or config.name
    api_key = _resolve_api_key(config.api_key, config.provider)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload: Dict[str, Any] = {
        "model": model_name,
        "input": {"query": query, "documents": candidates},
    }
    payload.update(config.extra or {})
    resp = requests.post(endpoint, json=payload, headers=headers, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    # DashScope format: {"output": {"results": [{"relevance_score": 0.9, "index": 0}, ...]}}
    results = data.get("output", {}).get("results", [])
    scores = [0.0] * len(candidates)
    for item in results:
        idx = item.get("index", 0)
        if 0 <= idx < len(candidates):
            scores[idx] = float(item.get("relevance_score", 0.0))
    return scores


def _jina_rerank_call(
    config: "EmbeddingModelConfigLike", query: str, candidates: List[str]
) -> List[float]:
    endpoint = config.api_url or "https://api.jina.ai/v1/rerank"
    model_name = config.backend or config.name
    api_key = _resolve_api_key(config.api_key, config.provider)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload: Dict[str, Any] = {
        "model": model_name,
        "query": query,
        "documents": candidates,
    }
    payload.update(config.extra or {})
    resp = requests.post(endpoint, json=payload, headers=headers, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    # Jina format: {"results": [{"relevance_score": 0.9, "index": 0}, ...]}
    results = data.get("results", [])
    scores = [0.0] * len(candidates)
    for item in results:
        idx = item.get("index", 0)
        if 0 <= idx < len(candidates):
            scores[idx] = float(item.get("relevance_score", 0.0))
    return scores


def _openai_rerank_call(
    config: "EmbeddingModelConfigLike", query: str, candidates: List[str]
) -> List[float]:
    """OpenAI-compatible rerank (e.g. Cohere via gateway)."""
    api_url = (config.api_url or "https://api.openai.com/v1").rstrip("/")
    if not api_url.endswith("/rerank"):
        api_url = f"{api_url}/rerank"
    model_name = config.backend or config.name
    api_key = _resolve_api_key(config.api_key, config.provider)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: Dict[str, Any] = {
        "model": model_name,
        "query": query,
        "documents": candidates,
    }
    payload.update(config.extra or {})
    resp = requests.post(api_url, json=payload, headers=headers, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    scores = [0.0] * len(candidates)
    for item in results:
        idx = item.get("index", 0)
        if 0 <= idx < len(candidates):
            scores[idx] = float(item.get("relevance_score", item.get("score", 0.0)))
    return scores


_RERANK_PROVIDERS: Dict[str, Callable[["EmbeddingModelConfigLike", str, List[str]], List[float]]] = {
    "proxy/tongyi": _tongyi_rerank_call,
    "proxy/jina": _jina_rerank_call,
    "proxy/openai": _openai_rerank_call,
}


class EmbeddingModelConfigLike:
    """Minimal structural type matching ``derisk_core.config.schema.EmbeddingModelConfig``.

    Defined as a duck-typed protocol so callers can pass either the pydantic
    config object or a simple dataclass / namedtuple with the same fields.
    """

    name: str
    provider: str
    api_key: Optional[str]
    api_url: Optional[str]
    backend: Optional[str]
    extra: Dict[str, Any]


class ProxyEmbeddings(Embeddings):
    """Embeddings client that calls the provider HTTP API directly.

    No worker process, no controller, no cluster. The model instance is
    fully described by ``EmbeddingModelConfig``.
    """

    def __init__(self, config: EmbeddingModelConfigLike) -> None:
        self._config = config
        self._builder = _PROVIDERS_GET(config.provider)
        if self._builder is None:
            # Default to OpenAI-compatible for unknown providers.
            logger.warning(
                f"Unknown embedding provider '{config.provider}', falling back to "
                f"OpenAI-compatible /v1/embeddings call."
            )
            self._builder = _openai_embedding_call

    @property
    def config(self) -> EmbeddingModelConfigLike:
        return self._config

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return self._builder(self._config, texts)

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> List[float]:
        return self.embed_query(text)


def _PROVIDERS_GET(provider: str):
    return _PROVIDER_BUILDERS.get(provider)


class ProxyRerankEmbeddings(RerankEmbeddings):
    """Rerank client that calls the provider HTTP API directly."""

    def __init__(self, config: EmbeddingModelConfigLike) -> None:
        self._config = config
        self._caller = _RERANK_PROVIDERS.get(config.provider)
        if self._caller is None:
            logger.warning(
                f"Unknown rerank provider '{config.provider}', falling back to "
                f"OpenAI-compatible /v1/rerank call."
            )
            self._caller = _openai_rerank_call

    def predict(self, query: str, candidates: List[str]) -> List[float]:
        if not candidates:
            return []
        return self._caller(self._config, query, candidates)

    async def apredict(self, query: str, candidates: List[str]) -> List[float]:
        return self.predict(query, candidates)
