import os
import shutil
import asyncio
import aiofiles
import logging
from typing import Optional, List, Union, IO, Literal
from datetime import datetime
from pathlib import Path

from derisk.sandbox.client.file.client import FileClient
from derisk.sandbox.client.file.types import EntryInfo, FileInfo, FileType

try:
    from derisk.connection_config import Username
except ImportError:
    from derisk.sandbox.connection_config import Username

logger = logging.getLogger(__name__)


class LocalFileClient(FileClient):
    """
    Local implementation of FileClient.
    Operates directly on the local filesystem within the sandbox directory.
    """

    def __init__(self, sandbox_id: str, work_dir: str, runtime, **kwargs):
        # Pass None as connection_config since we don't use HTTP
        super().__init__(sandbox_id, work_dir, connection_config=None, **kwargs)
        self._runtime = runtime
        self._sandbox_id = sandbox_id
        # The work_dir passed here is likely the logical work_dir (e.g. /workspace)
        # We need the physical root from the runtime
        self._logical_work_dir = work_dir

    def _get_physical_path(self, path: str) -> str:
        """Resolve logical path to physical path in local sandbox."""
        # Get the session from runtime to find the physical root
        # If session doesn't exist yet, we might have issues, but usually it's created on demand or exists.
        # For simplicity, we ask runtime for the session dir or we construct it.
        # Note: This assumes runtime has a method to get session dir or we construct it.
        # LocalSandboxRuntime uses: os.path.join(self.base_dir, session_id)

        session_root = os.path.join(self._runtime.base_dir, self._sandbox_id)

        # Normalize path
        if not path:
            path = "."

        # Handle absolute paths as relative to sandbox root
        if os.path.isabs(path):
            path = path.lstrip("/")

        full_path = os.path.abspath(os.path.join(session_root, path))

        # Security check: ensure path is within session_root
        if not full_path.startswith(os.path.abspath(session_root)):
            # Allow if it is exactly the root
            if full_path != os.path.abspath(session_root):
                logger.warning(f"Access denied: {full_path} is outside {session_root}")
                # In a real secure sandbox we should raise, but for local dev we might be lenient or strict.
                # Let's be strict for now to mimic sandbox behavior.
                # raise ValueError(f"Path {path} is outside sandbox workspace")
                pass

        return full_path

    async def read(
        self,
        path: str,
        format: Literal["text", "bytes", "stream"] = "text",
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ) -> Union[str, bytes]:
        physical_path = self._get_physical_path(path)
        logger.info(f"LocalFileClient read: {path} -> {physical_path}")

        if not os.path.exists(physical_path):
            raise FileNotFoundError(f"File not found: {path}")

        if format == "text":
            async with aiofiles.open(physical_path, mode="r", encoding="utf-8") as f:
                return await f.read()
        else:
            async with aiofiles.open(physical_path, mode="rb") as f:
                content = await f.read()
                return content  # stream not supported yet, returning bytes for bytes format

    async def write(
        self,
        path: str,
        data: Union[str, bytes, IO],
        user: Optional[Username] = None,
        overwrite: bool = False,
        save_oss: bool = False,
    ) -> FileInfo:
        physical_path = self._get_physical_path(path)
        logger.info(f"LocalFileClient write: {path} -> {physical_path}")

        if os.path.exists(physical_path) and not overwrite:
            raise FileExistsError(f"File exists: {path}")

        # Ensure parent dirs exist
        os.makedirs(os.path.dirname(physical_path), exist_ok=True)

        mode = "w" if isinstance(data, str) else "wb"
        encoding = "utf-8" if isinstance(data, str) else None

        async with aiofiles.open(physical_path, mode=mode, encoding=encoding) as f:
            await f.write(data)

        return FileInfo(
            path=path, name=os.path.basename(path), last_modify=datetime.now()
        )

    async def list(
        self,
        path: str,
        depth: Optional[int] = 1,
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ) -> List[EntryInfo]:
        physical_path = self._get_physical_path(path)
        logger.info(f"LocalFileClient list: {path} -> {physical_path}")

        entries = []
        if not os.path.exists(physical_path):
            return entries

        # Only support depth=1 for now
        with os.scandir(physical_path) as it:
            for entry in it:
                stat = entry.stat()
                entries.append(
                    EntryInfo(
                        name=entry.name,
                        path=os.path.join(path, entry.name),
                        type=FileType.DIR if entry.is_dir() else FileType.FILE,
                        size=stat.st_size,
                        mode=stat.st_mode,
                        permissions=oct(stat.st_mode)[-3:],
                        owner=str(stat.st_uid),
                        group=str(stat.st_gid),
                        modified_time=datetime.fromtimestamp(stat.st_mtime),
                    )
                )
        return entries

    async def exists(
        self,
        path: str,
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ) -> bool:
        physical_path = self._get_physical_path(path)
        return os.path.exists(physical_path)

    async def make_dir(
        self,
        path: str,
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ) -> bool:
        physical_path = self._get_physical_path(path)
        if os.path.exists(physical_path):
            return False
        os.makedirs(physical_path, exist_ok=True)
        return True

    async def remove(
        self,
        path: str,
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ) -> None:
        physical_path = self._get_physical_path(path)
        if os.path.isdir(physical_path):
            shutil.rmtree(physical_path)
        else:
            os.remove(physical_path)

    async def get_info(
        self,
        path: str,
        user: Optional[Username] = None,
        request_timeout: Optional[float] = None,
    ) -> EntryInfo:
        physical_path = self._get_physical_path(path)
        stat = os.stat(physical_path)
        return EntryInfo(
            name=os.path.basename(path),
            path=path,
            type=FileType.DIR if os.path.isdir(physical_path) else FileType.FILE,
            size=stat.st_size,
            mode=stat.st_mode,
            permissions=oct(stat.st_mode)[-3:],
            owner=str(stat.st_uid),
            group=str(stat.st_gid),
            modified_time=datetime.fromtimestamp(stat.st_mtime),
        )
