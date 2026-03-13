"""File I/O Integration for Agent Architectures

This module provides integration helpers for using file I/O functionality
in both core and core_v2 agent architectures.

Usage for core (PDCA-style agents):
    from derisk.agent.core.file_io_integration import (
        get_file_storage_client,
        create_agent_file_system,
        process_user_files,
    )

Usage for core_v2 (React-style agents):
    from derisk.agent.core.file_io_integration import (
        FileIOContext,
        initialize_file_io_for_agent,
    )
"""

import logging
import os
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from derisk.component import SystemApp
    from derisk.sandbox.base import SandboxBase

logger = logging.getLogger(__name__)


def get_file_storage_client(system_app: Optional["SystemApp"] = None):
    """Get FileStorageClient from system app.

    Args:
        system_app: SystemApp instance

    Returns:
        FileStorageClient instance or None
    """
    if system_app is None:
        return None

    try:
        from derisk.core.interface.file import FileStorageClient

        client = FileStorageClient.get_instance(system_app, default_component=None)
        return client
    except Exception as e:
        logger.warning(f"Failed to get FileStorageClient: {e}")
        return None


def create_agent_file_system(
    conv_id: str,
    session_id: Optional[str] = None,
    goal_id: Optional[str] = None,
    sandbox: Optional["SandboxBase"] = None,
    system_app: Optional["SystemApp"] = None,
    base_working_dir: Optional[str] = None,
):
    """Create AgentFileSystem instance for core architecture.

    Args:
        conv_id: Conversation ID
        session_id: Session ID (defaults to conv_id)
        goal_id: Goal ID for task isolation
        sandbox: Sandbox instance
        system_app: SystemApp instance
        base_working_dir: Base working directory

    Returns:
        AgentFileSystem instance
    """
    try:
        from derisk.agent.core.file_system.agent_file_system import AgentFileSystem

        file_storage_client = get_file_storage_client(system_app)

        if base_working_dir is None:
            try:
                from derisk.configs.model_config import DATA_DIR

                base_working_dir = os.path.join(DATA_DIR, "agent_storage")
            except ImportError:
                base_working_dir = os.path.expanduser("~/.derisk/agent_storage")

        afs = AgentFileSystem(
            conv_id=conv_id,
            session_id=session_id or conv_id,
            goal_id=goal_id or "default",
            sandbox=sandbox,
            file_storage_client=file_storage_client,
            base_working_dir=base_working_dir,
        )

        return afs
    except Exception as e:
        logger.error(f"Failed to create AgentFileSystem: {e}")
        raise


async def process_user_files(
    user_inputs: List[Dict[str, Any]],
    sandbox: Optional["SandboxBase"] = None,
    conv_id: Optional[str] = None,
    system_app: Optional["SystemApp"] = None,
) -> Dict[str, Any]:
    """Process user uploaded files.

    This function handles file routing between model direct consumption
    and sandbox tool processing.

    Args:
        user_inputs: List of user input files
        sandbox: Sandbox instance
        conv_id: Conversation ID
        system_app: SystemApp instance

    Returns:
        Dictionary with multimodal_contents, sandbox_file_refs, and errors
    """
    try:
        from derisk_serve.agent.file_io import (
            process_chat_input_files,
            FileProcessResult,
        )

        local_upload_dir = None
        if sandbox is None and system_app:
            try:
                from derisk.configs.model_config import DATA_DIR

                local_upload_dir = os.path.join(
                    DATA_DIR, "uploads", conv_id or "default"
                )
            except ImportError:
                local_upload_dir = os.path.expanduser(
                    f"~/.derisk/uploads/{conv_id or 'default'}"
                )

        result = await process_chat_input_files(
            user_inputs=user_inputs,
            sandbox=sandbox,
            conv_id=conv_id,
            local_upload_dir=local_upload_dir,
        )

        return {
            "multimodal_contents": result.multimodal_contents,
            "sandbox_file_refs": [ref.to_dict() for ref in result.sandbox_file_refs],
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


class FileIOContext:
    """Context manager for file I/O operations in core_v2 agents.

    This class provides a unified interface for file operations
    that works with both local and remote sandbox environments.

    Example:
        async with FileIOContext(
            conv_id="conv_123",
            sandbox=sandbox,
            system_app=system_app,
        ) as file_ctx:
            # Process uploaded files
            await file_ctx.process_user_files(user_inputs)

            # Deliver a file
            result = await file_ctx.deliver_file("/workspace/report.md")

            # Get delivery list
            deliveries = file_ctx.get_deliveries()
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
        self.work_dir = work_dir

        self._afs = None
        self._deliveries: List[Dict[str, Any]] = []
        self._sandbox_file_refs: List[Any] = []

    async def __aenter__(self):
        """Initialize file I/O context."""
        self._afs = create_agent_file_system(
            conv_id=self.conv_id,
            sandbox=self.sandbox,
            system_app=self.system_app,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup file I/O context."""
        pass

    async def process_user_files(
        self,
        user_inputs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Process user uploaded files."""
        result = await process_user_files(
            user_inputs=user_inputs,
            sandbox=self.sandbox,
            conv_id=self.conv_id,
            system_app=self.system_app,
        )

        if result.get("sandbox_file_refs"):
            self._sandbox_file_refs.extend(result["sandbox_file_refs"])

        return result

    async def deliver_file(
        self,
        path: str,
        description: str = "",
        file_type: str = "deliverable",
    ) -> Dict[str, Any]:
        """Deliver a file from sandbox.

        Args:
            path: File path in sandbox
            description: File description
            file_type: File type classification

        Returns:
            Delivery result with file URL and d-attach content
        """
        import os as os_module

        result = {
            "success": False,
            "file_name": os_module.basename(path),
            "path": path,
            "url": None,
            "dattach": None,
            "error": None,
        }

        try:
            file_name = os_module.basename(path)

            if self.sandbox and self.sandbox.file:
                file_info = await self.sandbox.file.read(path)
                if file_info and file_info.content:
                    from derisk.agent.core.memory.gpts import FileType as AfsFileType

                    if self._afs:
                        metadata = await self._afs.save_file(
                            file_key=file_name,
                            data=file_info.content,
                            file_type=AfsFileType.DELIVERABLE,
                            metadata={
                                "is_deliverable": True,
                                "description": description,
                                "file_category": file_type,
                            },
                        )

                        result["success"] = True
                        result["url"] = metadata.download_url or metadata.preview_url

                        self._deliveries.append(
                            {
                                "file_name": file_name,
                                "path": path,
                                "url": result["url"],
                                "file_type": file_type,
                                "description": description,
                            }
                        )

            if not result["success"]:
                result["error"] = "Failed to deliver file"

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Failed to deliver file {path}: {e}")

        return result

    def get_deliveries(self) -> List[Dict[str, Any]]:
        """Get list of delivered files."""
        return self._deliveries.copy()

    def get_sandbox_file_refs(self) -> List[Any]:
        """Get list of sandbox file references."""
        return self._sandbox_file_refs.copy()

    def render_deliveries(self, title: str = "Delivered Files") -> str:
        """Render all delivered files as d-attach list."""
        try:
            from derisk_serve.agent.file_io import render_dattach_list

            files = [
                {
                    "file_name": d["file_name"],
                    "file_url": d["url"],
                    "file_type": d.get("file_type", "deliverable"),
                    "description": d.get("description", ""),
                }
                for d in self._deliveries
            ]

            return render_dattach_list(files=files, title=title)
        except ImportError:
            return "\n".join(
                f"- {d['file_name']}: {d['url']}" for d in self._deliveries
            )


def initialize_file_io_for_agent(
    conv_id: str,
    sandbox: Optional["SandboxBase"] = None,
    system_app: Optional["SystemApp"] = None,
) -> FileIOContext:
    """Initialize file I/O context for an agent.

    This is a convenience function for creating a FileIOContext.

    Args:
        conv_id: Conversation ID
        sandbox: Sandbox instance
        system_app: SystemApp instance

    Returns:
        FileIOContext instance
    """
    return FileIOContext(
        conv_id=conv_id,
        sandbox=sandbox,
        system_app=system_app,
    )


__all__ = [
    "get_file_storage_client",
    "create_agent_file_system",
    "process_user_files",
    "FileIOContext",
    "initialize_file_io_for_agent",
]
