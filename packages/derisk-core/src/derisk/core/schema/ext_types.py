"""Extended types for the OpenAI API."""

from typing_extensions import Literal, Required, TypedDict

class FileURL(TypedDict, total=False):
    url: Required[str]
    """URL of the file."""

class ImageURL(FileURL):
    detail: Literal["auto", "low", "high"]
    """Specifies the detail level of the image.

    Learn more in the
    [Vision guide](https://platform.openai.com/docs/guides/vision#low-or-high-fidelity-image-understanding).
    """


class ExtAudioURL(FileURL):

    detail: Required[Literal["wav", "mp3"]]
    """The format of the encoded audio data."""


class ExtChatCompletionContentPartInputAudioParam(TypedDict, total=False):
    audio_url: Required[ExtAudioURL]

    type: Required[Literal["audio_url"]]
    """The type of the content part. Always `audio_url`."""


class ExtVideoURL(FileURL):

    detail: Required[Literal["mp4", "avi"]]
    """The format of the encoded video data."""


class ExtChatCompletionContentPartInputVideoParam(TypedDict, total=False):
    video_url: Required[ExtVideoURL]

    type: Required[Literal["video_url"]]
    """The type of the content part. Always `video_url`."""



class ExtChatCompletionContentPartInputFileParam(TypedDict, total=False):
    file_url: Required[FileURL]
    type: Required[Literal["file_url"]]
    """The type of the content part. Always `file_url`."""
