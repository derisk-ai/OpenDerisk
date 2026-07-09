"""Image URL rewriter for LLM providers.

Providers receive multimodal messages whose ``image_url.url`` may be a relative
file-API path (e.g. ``/api/v2/serve/file/files/<bucket>/<file_id>?conv_uid=...``)
that an external LLM endpoint cannot fetch. This module builds an idempotent
rewriter that converts such URLs into a form the model can consume:

* if the storage backend can produce a reachable absolute public URL (e.g. an
  OSS signed URL), use it;
* otherwise inline the image bytes as a ``data:<mime>;base64,...`` URI.

The rewriter is scoped to images only (non-image files keep their original url)
and never raises — any failure falls back to the original url so a broken image
never aborts an LLM call.
"""
import base64
import logging
import mimetypes
from typing import Callable, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Relative (or host-stripped) file-serving API path prefix.
_FILE_API_PREFIX = "/api/v2/serve/file/files/"


def build_image_url_rewriter(storage_client) -> Callable[[str], str]:
    """Build an idempotent image-URL rewriter closure.

    Args:
        storage_client: A :class:`FileStorageClient` used to resolve public URLs
            and read raw bytes. May be ``None``; in that case the rewriter is a
            no-op pass-through.

    Returns:
        ``Callable[[str], str]`` suitable for ``replace_url_func``.
    """

    def _rewrite(url) -> str:
        if not url:
            return url
        url = str(url)

        # Idempotent: already inlined.
        if url.startswith("data:"):
            return url

        parsed = urlparse(url)
        # Idempotent: absolute public URL that isn't our own file-API path
        # (OSS signed https URL, public CDN, ...). Relative file-API URLs and
        # absolute file-API URLs on a non-routable host fall through.
        if (
            parsed.scheme in ("http", "https")
            and parsed.netloc
            and not _is_our_file_api_path(parsed.path)
        ):
            return url

        # No storage client → cannot rewrite, pass through.
        if storage_client is None:
            return url

        bucket, file_id = _parse_bucket_file_id(url)
        if bucket is None:
            return url

        # Resolve metadata once; reused for both public-URL and base64 paths.
        try:
            metadata = storage_client.storage_system.get_file_metadata(
                bucket, file_id
            )
        except Exception:
            logger.warning(
                "get_file_metadata failed for %s/%s", bucket, file_id, exc_info=True
            )
            return url
        if metadata is None:
            return url

        # 1) Prefer a reachable public URL (OSS → signed aliyuncs URL).
        try:
            public_url = storage_client.get_public_url(metadata.uri)
            if public_url and _is_reachable_absolute(public_url):
                return public_url
        except Exception:
            logger.warning(
                "get_public_url failed for %s/%s", bucket, file_id, exc_info=True
            )

        # Images only: bail for non-image files to avoid inlining huge payloads.
        mime = _guess_image_mime(metadata.file_name, metadata.custom_metadata)
        if not mime:
            return url

        # 2) Fallback: read bytes → data:image/*;base64.
        try:
            stream, _ = storage_client.get_file_by_id(bucket, file_id)
            raw = stream.read()
            b64 = base64.b64encode(raw).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except Exception:
            logger.warning(
                "image base64 fallback failed for %s/%s; returning original url",
                bucket,
                file_id,
                exc_info=True,
            )
            return url

    return _rewrite


def _is_our_file_api_path(path: str) -> bool:
    return path.startswith(_FILE_API_PREFIX)


def _parse_bucket_file_id(url: str) -> Tuple[Optional[str], Optional[str]]:
    parsed = urlparse(url)
    path = parsed.path
    if path.startswith(_FILE_API_PREFIX):
        rest = path[len(_FILE_API_PREFIX):].strip("/")
        parts = rest.split("/")
        if len(parts) >= 2:
            # Query params (conv_uid/user_name) are auth/context hints only —
            # get_file_by_id needs just bucket + file_id.
            return parts[0], parts[1]
        return None, None
    if url.startswith("derisk-fs://"):
        try:
            from derisk.core.interface.file import FileStorageURI

            fs = FileStorageURI.parse(url)
            return fs.bucket, fs.file_id
        except Exception:
            return None, None
    return None, None


def _is_reachable_absolute(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    host = parsed.hostname or ""
    return not _is_non_routable_host(host)


def _is_non_routable_host(host: str) -> bool:
    """Loopback / link-local / unspecified hosts are not reachable externally.

    Mirrors ``derisk_serve.file.serve._is_public_host`` semantics without
    crossing the derisk-core → derisk-serve package boundary. Private RFC1918
    addresses are treated as reachable (intranet LLM providers may fetch them).
    """
    return (
        host in ("localhost", "0.0.0.0")
        or host.startswith("127.")
        or host.startswith("169.254.")
        or host == "::1"
    )


def _guess_image_mime(
    file_name: Optional[str],
    custom_metadata: Optional[dict] = None,
) -> Optional[str]:
    """Return an ``image/*`` mime when the file is recognizably an image.

    Returns ``None`` for unknown extensions so that non-image files (video,
    arbitrary documents) are NOT inlined as base64. Falls back to a mime hint
    stored in ``custom_metadata`` (keys ``mime``/``content_type``) when the
    file name has no recognizable image extension (e.g. screenshots).
    """
    if file_name:
        guess = mimetypes.guess_type(file_name)[0]
        if guess and guess.startswith("image/"):
            return guess
    if custom_metadata:
        for key in ("mime", "content_type", "media_type"):
            value = custom_metadata.get(key)
            if isinstance(value, str) and value.startswith("image/"):
                return value
    return None


def resolve_storage_client() -> Optional[object]:
    """Resolve the system ``FileStorageClient`` without importing derisk-serve.

    Returns ``None`` when no system app / registered client is available so
    callers can degrade to pass-through rewriting.
    """
    try:
        from derisk.component import SystemApp
        from derisk.core.interface.file import FileStorageClient

        system_app = SystemApp.get_instance()
        if system_app is None:
            return None
        return FileStorageClient.get_instance(system_app, default_component=None)
    except Exception:
        logger.debug(
            "FileStorageClient unavailable; image URL rewriting disabled",
            exc_info=True,
        )
        return None


def get_replace_url_func(provider) -> Callable[[str], str]:
    """Lazily build and cache the image-URL rewriter on a provider instance.

    Expects the provider to expose ``_storage_client`` and ``_replace_url_func``
    attributes. The storage client resolved at construction is preferred; on
    first call it falls back to :func:`resolve_storage_client`.
    """
    if provider._replace_url_func is None:
        storage_client = provider._storage_client or resolve_storage_client()
        provider._storage_client = storage_client
        provider._replace_url_func = build_image_url_rewriter(storage_client)
    return provider._replace_url_func