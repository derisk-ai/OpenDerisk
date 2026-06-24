"""Embedder factory — resolve embedding models via the Agent LLM provider registry.

Per RFC 004 §6, embedding models are configured the same way as LLM models:
through `agent.llm.provider` (TOML) and surfaced via `ModelConfigCache`.
This avoids a separate `AppConfig.embeddings` registration and lets users
pick any provider's embedding model from the same model management UI.

This factory:
1. Looks up `model_name` in `ModelConfigCache` (same cache the Agent uses).
2. Builds an `AgentLLMConfig` from the cached dict.
3. Calls the provider's OpenAI-compatible `/embeddings` endpoint directly
   (all registered providers — openai/azure/tongyi-compatible/ollama/theta —
   expose `/embeddings` or a compatible route).
4. Wraps the result in an `Embeddings` ABC adapter so callers can use
   `embed_query` / `embed_documents` interchangeably with other code.

The cache key is `model_name`; the orchestrator owns one `EmbedderCache`
per system_app.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from derisk.core.interface.embeddings import Embeddings

logger = logging.getLogger(__name__)


class ProviderEmbeddings(Embeddings):
    """`Embeddings` ABC adapter that calls a provider's `/embeddings` endpoint.

    Constructed from a `ModelConfigCache` entry. Uses `requests` (sync) to
    match the existing `proxy_embedding.py` pattern — embedding calls are
    short and the ABC's `embed_query` is sync anyway.
    """

    def __init__(self, model_config: Dict[str, Any]):
        self._config = model_config
        self._model_name = (
            model_config.get("model")
            or model_config.get("name")
            or model_config.get("backend")
        )
        self._provider = (model_config.get("provider") or "openai").lower()
        self._api_key = self._resolve_api_key(model_config)
        self._api_url = self._resolve_embeddings_url(model_config)

    def _resolve_api_key(self, config: Dict[str, Any]) -> Optional[str]:
        api_key = config.get("api_key")
        if api_key and not api_key.startswith("${"):
            return api_key
        # Fall back to env by provider
        import os

        env_map = {
            "openai": "OPENAI_API_KEY",
            "azure": "AZURE_OPENAI_API_KEY",
            "tongyi": "DASHSCOPE_API_KEY",
            "ollama": "OLLAMA_API_KEY",
            "theta": "THETA_API_KEY",
        }
        env_name = env_map.get(self._provider)
        if env_name:
            return os.getenv(env_name)
        return api_key

    def _resolve_embeddings_url(self, config: Dict[str, Any]) -> str:
        """Build the `/embeddings` URL from the config's base_url / api_url."""
        base = (
            config.get("base_url")
            or config.get("api_base")
            or config.get("api_url")
            or "https://api.openai.com/v1"
        )
        base = base.rstrip("/")
        # Tongyi native endpoint (non-compatible-mode) — leave as-is if the
        # user explicitly set an embeddings endpoint.
        if "dashscope.aliyuncs.com" in base and "compatible-mode" not in base:
            return base.rstrip("/text-embedding/text-embedding").rstrip(
                "/text-embedding"
            ) + "/text-embedding/text-embedding"
        if base.endswith("/embeddings"):
            return base
        return f"{base}/embeddings"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        import requests

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload: Dict[str, Any] = {"model": self._model_name, "input": texts}
        # Pass through any extra params the user set (e.g. dimensions,
        # encoding_format).
        extra = self._config.get("extra") or {}
        payload.update(extra)
        resp = requests.post(
            self._api_url, json=payload, headers=headers, timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        items = sorted(data["data"], key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in items]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]

    # Keep repr useful for logs
    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"ProviderEmbeddings(model={self._model_name!r}, provider={self._provider!r})"


def get_embedder(model_name: str, system_app: Any = None) -> Embeddings:
    """Resolve `model_name` via `ModelConfigCache` and return an `Embeddings`.

    `system_app` is accepted for API symmetry with other factories but not
    required: `ModelConfigCache` is a global singleton populated at app
    startup by the Agent's `_register_model_configs`.
    """
    from derisk.agent.util.llm.model_config_cache import ModelConfigCache

    config = ModelConfigCache.get_config(model_name)
    if config is None:
        raise ValueError(
            f"Embedding model '{model_name}' is not registered in agent.llm.provider. "
            "Add it to the model management module (same place as LLM models)."
        )
    return ProviderEmbeddings(config)


class EmbedderCache:
    """Per-system_app embedder cache. The orchestrator owns one instance."""

    def __init__(self, system_app: Any = None):
        self._system_app = system_app
        self._cache: Dict[str, Embeddings] = {}

    def get(self, model_name: str) -> Embeddings:
        if model_name not in self._cache:
            self._cache[model_name] = get_embedder(model_name, self._system_app)
        return self._cache[model_name]

    def clear(self) -> None:
        self._cache.clear()


__all__ = ["get_embedder", "EmbedderCache", "ProviderEmbeddings"]
