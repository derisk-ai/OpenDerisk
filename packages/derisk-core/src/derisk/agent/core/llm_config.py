from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, Field


class AgentLLMConfig(BaseModel):
    """Configuration for Agent's LLM model."""
    model: str
    provider: str  # e.g., "openai", "claude", "proxy"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_type: Optional[str] = None # azure, etc
    api_version: Optional[str] = None
    
    temperature: float = 0.5
    max_new_tokens: int = 2048
    top_p: Optional[float] = None
    stop: Optional[List[str]] = None
    
    # Extra parameters for specific providers
    extra_kwargs: Dict[str, Any] = Field(default_factory=dict)
    
    # Proxy specific config
    proxy_server_url: Optional[str] = None
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "AgentLLMConfig":
        return cls(**{k: v for k, v in config.items() if k in cls.model_fields})
