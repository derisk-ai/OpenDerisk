from enum import Enum
from typing import Any, Dict, List, Optional, Set
import logging
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


class MediaType(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class ModelCapability(str, Enum):
    TEXT = "text"
    IMAGE_INPUT = "image_input"
    IMAGE_OUTPUT = "image_output"
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"
    VIDEO_INPUT = "video_input"
    DOCUMENT_INPUT = "document_input"
    FUNCTION_CALL = "function_call"
    STREAMING = "streaming"


@dataclass
class ModelInfo:
    model_name: str
    capabilities: Set[ModelCapability]
    context_length: int = 4096
    max_output_tokens: int = 4096
    priority: int = 0
    provider: str = "unknown"
    metadata: Dict = field(default_factory=dict)

    def supports_capability(self, capability: ModelCapability) -> bool:
        return capability in self.capabilities

    def supports_media_type(self, media_type: MediaType) -> bool:
        capability_map = {
            MediaType.IMAGE: ModelCapability.IMAGE_INPUT,
            MediaType.AUDIO: ModelCapability.AUDIO_INPUT,
            MediaType.VIDEO: ModelCapability.VIDEO_INPUT,
            MediaType.DOCUMENT: ModelCapability.DOCUMENT_INPUT,
            MediaType.UNKNOWN: None,
        }
        required_capability = capability_map.get(media_type)
        if required_capability:
            return self.supports_capability(required_capability)
        return False


MULTIMODAL_MODEL_REGISTRY: Dict[str, ModelInfo] = {
    "gpt-4o": ModelInfo(
        model_name="gpt-4o",
        capabilities={
            ModelCapability.TEXT,
            ModelCapability.IMAGE_INPUT,
            ModelCapability.AUDIO_INPUT,
            ModelCapability.FUNCTION_CALL,
            ModelCapability.STREAMING,
        },
        context_length=128000,
        max_output_tokens=16384,
        priority=100,
        provider="openai",
    ),
    "gpt-4o-mini": ModelInfo(
        model_name="gpt-4o-mini",
        capabilities={
            ModelCapability.TEXT,
            ModelCapability.IMAGE_INPUT,
            ModelCapability.FUNCTION_CALL,
            ModelCapability.STREAMING,
        },
        context_length=128000,
        max_output_tokens=16384,
        priority=90,
        provider="openai",
    ),
    "gpt-4-turbo": ModelInfo(
        model_name="gpt-4-turbo",
        capabilities={
            ModelCapability.TEXT,
            ModelCapability.IMAGE_INPUT,
            ModelCapability.FUNCTION_CALL,
            ModelCapability.STREAMING,
        },
        context_length=128000,
        max_output_tokens=4096,
        priority=80,
        provider="openai",
    ),
    "claude-3-opus": ModelInfo(
        model_name="claude-3-opus",
        capabilities={
            ModelCapability.TEXT,
            ModelCapability.IMAGE_INPUT,
            ModelCapability.DOCUMENT_INPUT,
            ModelCapability.STREAMING,
        },
        context_length=200000,
        max_output_tokens=4096,
        priority=95,
        provider="anthropic",
    ),
    "claude-3-sonnet": ModelInfo(
        model_name="claude-3-sonnet",
        capabilities={
            ModelCapability.TEXT,
            ModelCapability.IMAGE_INPUT,
            ModelCapability.DOCUMENT_INPUT,
            ModelCapability.STREAMING,
        },
        context_length=200000,
        max_output_tokens=4096,
        priority=85,
        provider="anthropic",
    ),
    "qwen-vl-max": ModelInfo(
        model_name="qwen-vl-max",
        capabilities={
            ModelCapability.TEXT,
            ModelCapability.IMAGE_INPUT,
            ModelCapability.VIDEO_INPUT,
            ModelCapability.STREAMING,
        },
        context_length=32000,
        max_output_tokens=2000,
        priority=85,
        provider="alibaba",
    ),
    "qwen-audio-turbo": ModelInfo(
        model_name="qwen-audio-turbo",
        capabilities={
            ModelCapability.TEXT,
            ModelCapability.AUDIO_INPUT,
            ModelCapability.STREAMING,
        },
        context_length=8000,
        max_output_tokens=2000,
        priority=80,
        provider="alibaba",
    ),
    "gemini-1.5-pro": ModelInfo(
        model_name="gemini-1.5-pro",
        capabilities={
            ModelCapability.TEXT,
            ModelCapability.IMAGE_INPUT,
            ModelCapability.AUDIO_INPUT,
            ModelCapability.VIDEO_INPUT,
            ModelCapability.DOCUMENT_INPUT,
            ModelCapability.STREAMING,
        },
        context_length=1000000,
        max_output_tokens=8192,
        priority=95,
        provider="google",
    ),
    "glm-4v": ModelInfo(
        model_name="glm-4v",
        capabilities={
            ModelCapability.TEXT,
            ModelCapability.IMAGE_INPUT,
            ModelCapability.STREAMING,
        },
        context_length=8192,
        max_output_tokens=1024,
        priority=75,
        provider="zhipu",
    ),
}


class MultimodalModelMatcher:

    def __init__(
        self,
        model_registry: Optional[Dict[str, ModelInfo]] = None,
        default_text_model: str = "gpt-4o-mini",
        default_image_model: str = "gpt-4o",
        default_audio_model: str = "qwen-audio-turbo",
        default_video_model: str = "qwen-vl-max",
    ):
        self.model_registry = model_registry or MULTIMODAL_MODEL_REGISTRY.copy()
        self.default_text_model = default_text_model
        self.default_image_model = default_image_model
        self.default_audio_model = default_audio_model
        self.default_video_model = default_video_model

    def register_model(self, model_info: ModelInfo) -> None:
        self.model_registry[model_info.model_name] = model_info

    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        return self.model_registry.get(model_name)

    def match_model_for_media_type(
        self,
        media_type: MediaType,
        preferred_provider: Optional[str] = None,
        require_streaming: bool = False,
    ) -> Optional[ModelInfo]:
        candidates = []

        for model_info in self.model_registry.values():
            if not model_info.supports_media_type(media_type):
                continue

            if require_streaming and not model_info.supports_capability(
                ModelCapability.STREAMING
            ):
                continue

            if preferred_provider and model_info.provider != preferred_provider:
                continue

            candidates.append(model_info)

        if not candidates:
            return None

        candidates.sort(key=lambda m: m.priority, reverse=True)
        return candidates[0]

    def match_model_for_media_types(
        self,
        media_types: List[MediaType],
        preferred_provider: Optional[str] = None,
        require_streaming: bool = False,
    ) -> Optional[ModelInfo]:
        if not media_types:
            return self.model_registry.get(self.default_text_model)

        unique_types = set(media_types)
        if unique_types == {MediaType.UNKNOWN} or unique_types == set():
            return self.model_registry.get(self.default_text_model)

        candidates = []

        for model_info in self.model_registry.values():
            supports_all = all(
                model_info.supports_media_type(mt)
                for mt in unique_types
                if mt != MediaType.UNKNOWN
            )

            if not supports_all:
                continue

            if require_streaming and not model_info.supports_capability(
                ModelCapability.STREAMING
            ):
                continue

            if preferred_provider and model_info.provider != preferred_provider:
                continue

            candidates.append(model_info)

        if not candidates:
            logger.warning(
                f"No model found that supports all media types: {unique_types}. "
                f"Falling back to separate processing."
            )
            non_unknown = [mt for mt in unique_types if mt != MediaType.UNKNOWN]
            if non_unknown:
                return self.match_model_for_media_type(
                    non_unknown[0], preferred_provider, require_streaming
                )
            return None

        candidates.sort(key=lambda m: m.priority, reverse=True)
        return candidates[0]

    def get_default_model_for_media_type(self, media_type: MediaType) -> str:
        default_map = {
            MediaType.IMAGE: self.default_image_model,
            MediaType.AUDIO: self.default_audio_model,
            MediaType.VIDEO: self.default_video_model,
            MediaType.DOCUMENT: self.default_text_model,
            MediaType.UNKNOWN: self.default_text_model,
        }
        return default_map.get(media_type, self.default_text_model)

    def list_models_for_capability(
        self, capability: ModelCapability, provider: Optional[str] = None
    ) -> List[ModelInfo]:
        models = []
        for model_info in self.model_registry.values():
            if model_info.supports_capability(capability):
                if provider is None or model_info.provider == provider:
                    models.append(model_info)
        return sorted(models, key=lambda m: m.priority, reverse=True)