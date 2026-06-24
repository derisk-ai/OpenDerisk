"""S3 / object-store file backend for DistributedVaultFS.

Wraps `derisk.core.interface.file.FileStorageClient`, which already
supports S3 / OSS / MinIO / local-file via the `[[serves.backends]]`
TOML config. We use deterministic `file_id`s derived from the wiki
path or verbat id so reads/writes/deletes address the same object
across calls without maintaining a separate path→URI index.

All FileStorageClient methods are sync — we wrap them in
`asyncio.to_thread` so the async event loop isn't blocked.

Key layout (deterministic file_id, namespaced by space_id):
- raw verbat: `ksraw-{space_id}-{extract_mode}-{verbat_id}`
- wiki doc:   `kswiki-{space_id}-{slug(wiki_path)}`
- schema.md:  `ksschema-{space_id}`
- purpose.md: `kspurpose-{space_id}`
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


_SAFE_RE = re.compile(r"[^a-zA-Z0-9._-]")


def _slugify(s: str, max_len: int = 128) -> str:
    """Make a string safe to embed in a file_id (S3 key constraint)."""
    return _SAFE_RE.sub("_", s)[:max_len]


class S3FileStore:
    """File backend for DistributedVaultFS using FileStorageClient.

    The client is resolved lazily so the store can be constructed
    before the system_app is initialized.
    """

    def __init__(
        self,
        bucket: str,
        space_id: str,
        storage_type: Optional[str] = None,
        client: Optional[object] = None,
        system_app: Optional[object] = None,
    ):
        self._bucket = bucket
        self._space_id = space_id
        self._storage_type = storage_type
        self._client = client
        self._system_app = system_app

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def storage_type(self) -> Optional[str]:
        return self._storage_type

    # ------------------------------------------------------------------
    # Client resolution (lazy)
    # ------------------------------------------------------------------
    def _get_client(self):
        if self._client is not None:
            return self._client
        from derisk.core.interface.file import FileStorageClient

        if self._system_app is not None:
            try:
                self._client = FileStorageClient.get_instance(self._system_app)
                return self._client
            except Exception as e:
                logger.debug(
                    "FileStorageClient.get_instance failed (%s); "
                    "falling back to default client",
                    e,
                )

        # Fallback: default client (local file storage if no S3 configured)
        self._client = FileStorageClient()
        if self._storage_type:
            self._client.default_storage_type = self._storage_type
        return self._client

    def _resolve_storage_type(self) -> str:
        client = self._get_client()
        if self._storage_type:
            return self._storage_type
        if client.default_storage_type:
            return client.default_storage_type
        # Final fallback: derive from bucket name (S3 common case)
        return "s3"

    # ------------------------------------------------------------------
    # file_id helpers (deterministic)
    # ------------------------------------------------------------------
    def _file_id_for_raw(self, extract_mode: str, verbat_id: str) -> str:
        return f"ksraw-{_slugify(self._space_id)}-{extract_mode}-{_slugify(verbat_id)}"

    def _file_id_for_wiki(self, norm_path: str) -> str:
        return f"kswiki-{_slugify(self._space_id)}-{_slugify(norm_path)}"

    def _file_id_for_schema(self) -> str:
        return f"ksschema-{_slugify(self._space_id)}"

    def _file_id_for_purpose(self) -> str:
        return f"kspurpose-{_slugify(self._space_id)}"

    def _file_id_for_root(self, name: str) -> str:
        return f"ksroot-{_slugify(self._space_id)}-{_slugify(name)}"

    # ------------------------------------------------------------------
    # Core ops (sync internally, async wrapper)
    # ------------------------------------------------------------------
    def _save_text_sync(self, file_id: str, content: str, file_name: str) -> str:
        client = self._get_client()
        storage_type = self._resolve_storage_type()
        data = io.BytesIO(content.encode("utf-8"))
        return client.save_file(
            bucket=self._bucket,
            file_name=file_name,
            file_data=data,
            storage_type=storage_type,
            file_id=file_id,
        )

    def _read_text_sync(self, file_id: str) -> Optional[str]:
        client = self._get_client()
        # Check existence via metadata first to avoid FileNotFoundError
        meta = client.storage_system.get_file_metadata(self._bucket, file_id)
        if not meta:
            return None
        data, _ = client.get_file(meta.uri)
        try:
            return data.read().decode("utf-8")
        finally:
            try:
                data.close()
            except Exception:
                pass

    def _delete_sync(self, file_id: str) -> None:
        client = self._get_client()
        meta = client.storage_system.get_file_metadata(self._bucket, file_id)
        if not meta:
            return
        client.delete_file(meta.uri)

    def _exists_sync(self, file_id: str) -> bool:
        client = self._get_client()
        return client.storage_system.get_file_metadata(self._bucket, file_id) is not None

    # ------------------------------------------------------------------
    # Async API (called by DistributedVaultFS)
    # ------------------------------------------------------------------
    async def write_raw(self, extract_mode: str, verbat_id: str, content: str) -> None:
        file_id = self._file_id_for_raw(extract_mode, verbat_id)
        await asyncio.to_thread(
            self._save_text_sync, file_id, content, f"{verbat_id}.txt"
        )

    async def read_raw(self, extract_mode: str, verbat_id: str) -> str:
        file_id = self._file_id_for_raw(extract_mode, verbat_id)
        return await asyncio.to_thread(self._read_text_sync, file_id) or ""

    async def delete_raw(self, extract_mode: str, verbat_id: str) -> None:
        file_id = self._file_id_for_raw(extract_mode, verbat_id)
        await asyncio.to_thread(self._delete_sync, file_id)

    async def write_wiki(self, norm_path: str, content: str) -> None:
        file_id = self._file_id_for_wiki(norm_path)
        file_name = norm_path.rsplit("/", 1)[-1] or "file.md"
        await asyncio.to_thread(
            self._save_text_sync, file_id, content, file_name
        )

    async def read_wiki(self, norm_path: str) -> str:
        file_id = self._file_id_for_wiki(norm_path)
        return await asyncio.to_thread(self._read_text_sync, file_id) or ""

    async def delete_wiki(self, norm_path: str) -> None:
        file_id = self._file_id_for_wiki(norm_path)
        await asyncio.to_thread(self._delete_sync, file_id)

    async def write_schema(self, content: str) -> None:
        file_id = self._file_id_for_schema()
        await asyncio.to_thread(
            self._save_text_sync, file_id, content, "schema.md"
        )

    async def read_schema(self) -> str:
        file_id = self._file_id_for_schema()
        return await asyncio.to_thread(self._read_text_sync, file_id) or ""

    async def write_purpose(self, content: str) -> None:
        file_id = self._file_id_for_purpose()
        await asyncio.to_thread(
            self._save_text_sync, file_id, content, "purpose.md"
        )

    async def read_purpose(self) -> str:
        file_id = self._file_id_for_purpose()
        return await asyncio.to_thread(self._read_text_sync, file_id) or ""

    async def exists_wiki(self, norm_path: str) -> bool:
        file_id = self._file_id_for_wiki(norm_path)
        return await asyncio.to_thread(self._exists_sync, file_id)

    async def seed_protected_files_if_missing(
        self, schema_md: str, protected: dict[str, str]
    ) -> None:
        """Write schema.md + protected wiki files if not already present.

        `protected` maps wiki path → default content (e.g.
        {"index.md": "# Index\n\n", "log.md": "# Operation Log\n\n", ...}).
        Schema and purpose.md are at the root, not under wiki/.
        """
        if not await asyncio.to_thread(self._exists_sync, self._file_id_for_schema()):
            await self.write_schema(schema_md)
        if not await asyncio.to_thread(self._exists_sync, self._file_id_for_purpose()):
            await self.write_purpose("# Purpose\n\n")
        for path, default in protected.items():
            file_id = self._file_id_for_wiki(path)
            if not await asyncio.to_thread(self._exists_sync, file_id):
                await self.write_wiki(path, default)
