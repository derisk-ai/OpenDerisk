from dataclasses import dataclass, field
from typing import Optional

from derisk.util.i18n_utils import _
from derisk_serve.core import BaseServeConfig

APP_NAME = "multimodal"
SERVE_APP_NAME = "derisk_serve_multimodal"
SERVE_APP_NAME_HUMP = "derisk_serve_Multimodal"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.multimodal."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"


@dataclass
class ServeConfig(BaseServeConfig):
    """Configuration for multimodal serve module."""

    __type__ = APP_NAME

    default_bucket: Optional[str] = field(
        default="multimodal_files",
        metadata={"help": _("Default bucket for multimodal file storage")},
    )
    max_file_size: Optional[int] = field(
        default=100 * 1024 * 1024,
        metadata={"help": _("Maximum file size in bytes (default 100MB)")},
    )
    default_text_model: Optional[str] = field(
        default="gpt-4o-mini",
        metadata={"help": _("Default model for text processing")},
    )
    default_image_model: Optional[str] = field(
        default="gpt-4o",
        metadata={"help": _("Default model for image processing")},
    )
    default_audio_model: Optional[str] = field(
        default="qwen-audio-turbo",
        metadata={"help": _("Default model for audio processing")},
    )
    default_video_model: Optional[str] = field(
        default="qwen-vl-max",
        metadata={"help": _("Default model for video processing")},
    )