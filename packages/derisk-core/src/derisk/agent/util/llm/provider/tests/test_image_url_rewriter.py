"""Tests for the image-URL rewriter used by LLM providers."""
import base64
from io import BytesIO

from derisk.agent.util.llm.provider._image_url_rewriter import (
    build_image_url_rewriter,
)
from derisk.core.interface.file import FileMetadata


class _FakeMetadata:
    """Minimal stand-in for FileMetadata used by the rewriter."""

    def __init__(self, uri: str, file_name: str, custom_metadata=None):
        self.uri = uri
        self.file_name = file_name
        self.custom_metadata = custom_metadata or {}


class _FakeStorageClient:
    def __init__(
        self,
        *,
        public_url=None,
        public_url_reachable=False,
        file_bytes=b"",
        file_name="a.png",
    ):
        self._public_url = public_url
        self._public_url_reachable = public_url_reachable
        self._file_bytes = file_bytes
        self._file_name = file_name
        self.storage_system = self

    def get_file_metadata(self, bucket, file_id):
        return _FakeMetadata(
            uri=f"derisk-fs://_/{bucket}/{file_id}",
            file_name=self._file_name,
        )

    def get_public_url(self, uri):
        return self._public_url

    def get_file_by_id(self, bucket, file_id):
        return (
            BytesIO(self._file_bytes),
            _FakeMetadata(uri=f"derisk-fs://_/{bucket}/{file_id}",
                          file_name=self._file_name),
        )


REL_URL = "/api/v2/serve/file/files/derisk_app_file/abc-123?conv_uid=x&user_name=admin"


def test_relative_url_falls_back_to_base64_when_no_public_url():
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00"
    sc = _FakeStorageClient(
        public_url="/api/v2/serve/file/files/derisk_app_file/abc-123",  # relative → not reachable
        public_url_reachable=False,
        file_bytes=png_bytes,
        file_name="screenshot.png",
    )
    rewrite = build_image_url_rewriter(sc)
    result = rewrite(REL_URL)
    assert result.startswith("data:image/png;base64,")
    decoded = base64.b64decode(result.split("base64,", 1)[1])
    assert decoded == png_bytes


def test_reachable_oss_public_url_is_passed_through():
    sc = _FakeStorageClient(
        public_url="https://openderisk.oss-cn-beijing.aliyuncs.com/obj/abc?Signature=xx",
        public_url_reachable=True,
    )
    rewrite = build_image_url_rewriter(sc)
    # Relative URL is resolved to the OSS public URL (reachable) → returned.
    assert rewrite(REL_URL) == sc._public_url


def test_already_data_uri_is_idempotent():
    sc = _FakeStorageClient()
    rewrite = build_image_url_rewriter(sc)
    data_uri = "data:image/jpeg;base64,/9j/4AAQ"
    assert rewrite(data_uri) == data_uri


def test_absolute_https_url_not_our_file_api_is_passed_through():
    sc = _FakeStorageClient()
    rewrite = build_image_url_rewriter(sc)
    external = "https://cdn.example.com/img.png"
    assert rewrite(external) == external


def test_non_image_file_not_inlined_as_base64():
    sc = _FakeStorageClient(file_name="clip.mp4", file_bytes=b"fakevideo")
    rewrite = build_image_url_rewriter(sc)
    # No reachable public URL + non-image file → original url returned, not base64.
    assert rewrite(REL_URL) == REL_URL


def test_storage_client_none_is_pass_through():
    rewrite = build_image_url_rewriter(None)
    assert rewrite(REL_URL) == REL_URL


def test_storage_failure_returns_original_url_not_raise():
    class _Boom(_FakeStorageClient):
        def get_file_metadata(self, bucket, file_id):
            raise RuntimeError("db down")

    rewrite = build_image_url_rewriter(_Boom(file_name="a.png"))
    assert rewrite(REL_URL) == REL_URL  # never raises


def test_get_replace_url_func_caches_on_provider():
    from derisk.agent.util.llm.provider._image_url_rewriter import (
        get_replace_url_func,
    )

    class _Provider:
        def __init__(self):
            self._storage_client = None
            self._replace_url_func = None

    p = _Provider()
    f1 = get_replace_url_func(p)
    f2 = get_replace_url_func(p)
    assert f1 is f2  # cached