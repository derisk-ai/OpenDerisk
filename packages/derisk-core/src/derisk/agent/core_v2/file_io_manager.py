"""File I/O Integration for core_v2 Agent Architecture

This module provides file I/O capabilities specifically designed for the
core_v2 (React-style) agent architecture.

Features:
- Integration with core_v2's filesystem module
- Support for project memory based file storage
- Deliver file tool integration
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from derisk.component import SystemApp
    from derisk.sandbox.base import SandboxBase

logger = logging.getLogger(__name__)


@dataclass
class DeliverableFile:
    """Represents a file that has been delivered to the user."""

    file_id: str
    file_name: str
    file_path: str
    file_url: Optional[str] = None
    file_type: str = "deliverable"
    description: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    file_size: Optional[int] = None
    mime_type: Optional[str] = None


class CoreV2FileIOManager:
    """File I/O manager for core_v2 architecture.

    This class manages file input/output operations for React-style agents,
    including:
    - Processing user-uploaded files
    - Managing file storage
    - Creating file deliveries
    - Generating d-attach components

    Example:
        manager = CoreV2FileIOManager(
            conv_id="conv_123",
            sandbox=sandbox,
            system_app=system_app,
        )

        # Process user files
        await manager.process_user_files(user_inputs)

        # Deliver a file
        result = await manager.deliver_file("/workspace/report.md")

        # Get all deliveries
        deliveries = manager.get_all_deliveries()
    """

    def __init__(
        self,
        conv_id: str,
        sandbox: Optional["SandboxBase"] = None,
        system_app: Optional["SystemApp"] = None,
        work_dir: Optional[str] = None,
    ):
        self.conv_id = conv_id
        self.sandbox = sandbox
        self.system_app = system_app
        self.work_dir = work_dir or self._get_default_work_dir()

        self._deliveries: List[DeliverableFile] = []
        self._uploaded_files: List[Dict[str, Any]] = []
        self._file_storage_client = None

    def _get_default_work_dir(self) -> str:
        """Get default working directory."""
        try:
            from derisk.configs.model_config import DATA_DIR

            return os.path.join(DATA_DIR, "agent_storage", self.conv_id)
        except ImportError:
            return os.path.expanduser(f"~/.derisk/agent_storage/{self.conv_id}")

    def _get_file_storage_client(self):
        """Get FileStorageClient lazily."""
        if self._file_storage_client is None and self.system_app:
            try:
                from derisk.core.interface.file import FileStorageClient

                self._file_storage_client = FileStorageClient.get_instance(
                    self.system_app, default_component=None
                )
            except Exception as e:
                logger.warning(f"Failed to get FileStorageClient: {e}")
        return self._file_storage_client

    async def initialize(self) -> None:
        """Initialize the file I/O manager."""
        os.makedirs(self.work_dir, exist_ok=True)
        logger.info(f"CoreV2FileIOManager initialized for conv: {self.conv_id}")

    async def process_user_files(
        self,
        user_inputs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Process user-uploaded files.

        Args:
            user_inputs: List of user input files

        Returns:
            Processing result with file references
        """
        try:
            from derisk_serve.agent.file_io import (
                process_chat_input_files,
                initialize_files_in_sandbox,
                FileProcessResult,
            )

            local_upload_dir = os.path.join(self.work_dir, "uploads")
            os.makedirs(local_upload_dir, exist_ok=True)

            result = await process_chat_input_files(
                user_inputs=user_inputs,
                sandbox=self.sandbox,
                conv_id=self.conv_id,
                local_upload_dir=local_upload_dir,
            )

            self._uploaded_files.extend(result.sandbox_file_refs)

            if self.sandbox and result.sandbox_file_refs:
                init_result = await initialize_files_in_sandbox(
                    sandbox=self.sandbox,
                    sandbox_file_refs=result.sandbox_file_refs,
                    conv_id=self.conv_id,
                )
                logger.info(
                    f"Initialized {len(init_result.get('success', []))} files in sandbox"
                )

            return {
                "multimodal_contents": result.multimodal_contents,
                "sandbox_file_refs": [
                    ref.to_dict() for ref in result.sandbox_file_refs
                ],
                "errors": result.errors,
            }

        except ImportError:
            logger.warning("derisk_serve.agent.file_io not available")
            return {
                "multimodal_contents": [],
                "sandbox_file_refs": [],
                "errors": ["File I/O module not available"],
            }
        except Exception as e:
            logger.error(f"Failed to process user files: {e}")
            return {
                "multimodal_contents": [],
                "sandbox_file_refs": [],
                "errors": [str(e)],
            }

    async def deliver_file(
        self,
        file_path: str,
        description: str = "",
        file_type: str = "deliverable",
    ) -> DeliverableFile:
        """Deliver a file from the sandbox.

        Args:
            file_path: Path to the file in sandbox
            description: Description of the file
            file_type: Type classification (deliverable, report, data, etc.)

        Returns:
            DeliverableFile instance
        """
        import uuid
        import mimetypes

        file_name = os.path.basename(file_path)
        mime_type, _ = mimetypes.guess_type(file_name)
        file_id = str(uuid.uuid4())
        file_size = None
        file_url = None

        if self.sandbox and self.sandbox.file:
            try:
                file_info = await self.sandbox.file.read(file_path)
                if file_info and file_info.content:
                    content = file_info.content
                    file_size = len(
                        content.encode("utf-8") if isinstance(content, str) else content
                    )

                    oss_file = await self.sandbox.file.upload_to_oss(file_path)
                    if oss_file and oss_file.temp_url:
                        file_url = oss_file.temp_url

            except Exception as e:
                logger.warning(f"Failed to read/upload file {file_path}: {e}")

        if not file_url:
            file_url = f"local://{file_path}"

        delivery = DeliverableFile(
            file_id=file_id,
            file_name=file_name,
            file_path=file_path,
            file_url=file_url,
            file_type=file_type,
            description=description,
            file_size=file_size,
            mime_type=mime_type or "application/octet-stream",
        )

        self._deliveries.append(delivery)
        logger.info(f"Delivered file: {file_name} -> {file_url}")

        return delivery

    def get_all_deliveries(self) -> List[DeliverableFile]:
        """Get all delivered files."""
        return self._deliveries.copy()

    def get_uploaded_files(self) -> List[Dict[str, Any]]:
        """Get all uploaded file references."""
        return self._uploaded_files.copy()

    def render_deliveries(self, title: str = "Delivered Files") -> str:
        """Render all deliveries as d-attach list."""
        try:
            from derisk_serve.agent.file_io import render_dattach_list

            files = [
                {
                    "file_name": d.file_name,
                    "file_url": d.file_url,
                    "file_type": d.file_type,
                    "description": d.description,
                    "file_size": d.file_size,
                    "mime_type": d.mime_type,
                }
                for d in self._deliveries
            ]

            return render_dattach_list(files=files, title=title)

        except ImportError:
            lines = [f"## {title}", ""]
            for d in self._deliveries:
                lines.append(f"- **{d.file_name}**: {d.file_url}")
            return "\n".join(lines)

    def clear(self) -> None:
        """Clear all tracked files."""
        self._deliveries.clear()
        self._uploaded_files.clear()


def create_file_io_manager(
    conv_id: str,
    sandbox: Optional["SandboxBase"] = None,
    system_app: Optional["SystemApp"] = None,
    work_dir: Optional[str] = None,
) -> CoreV2FileIOManager:
    """Create a file I/O manager for core_v2 agents.

    Args:
        conv_id: Conversation ID
        sandbox: Sandbox instance
        system_app: SystemApp instance
        work_dir: Working directory

    Returns:
        CoreV2FileIOManager instance
    """
    return CoreV2FileIOManager(
        conv_id=conv_id,
        sandbox=sandbox,
        system_app=system_app,
        work_dir=work_dir,
    )


__all__ = [
    "DeliverableFile",
    "CoreV2FileIOManager",
    "create_file_io_manager",
]
