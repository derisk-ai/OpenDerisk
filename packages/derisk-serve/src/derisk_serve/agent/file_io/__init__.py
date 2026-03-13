"""File Input/Output Module for OpenDeRisk

This module provides comprehensive file handling capabilities for OpenDeRisk:

1. File Type Configuration (file_type_config.py)
   - Determines how files should be processed (MODEL_DIRECT vs SANDBOX_TOOL)
   - Supports dynamic configuration via environment variables, YAML files, or defaults

2. Sandbox File Reference (sandbox_file_ref.py)
   - Handles file routing between model direct consumption and sandbox tool processing
   - Supports downloading files from URLs and initializing them in sandbox

3. D-Attach Utilities (dattach_utils.py)
   - Provides utilities for creating d-attach components for frontend display
   - Supports single file and multi-file list rendering

Usage:
    from derisk_serve.agent.file_io import (
        FileProcessMode,
        get_file_process_mode,
        SandboxFileRef,
        process_user_input_file,
        render_dattach,
        DAttachBuilder,
    )

    # Check file processing mode
    mode = get_file_process_mode("report.pdf")  # Returns FileProcessMode.SANDBOX_TOOL

    # Create d-attach component
    output = render_dattach("report.md", "https://example.com/report.md")
"""

from .file_type_config import (
    FileProcessMode,
    FileTypeConfig,
    FileTypeConfigManager,
    FileTypeRule,
    DEFAULT_CONFIG,
    get_file_process_mode,
    is_model_direct_file,
    is_sandbox_tool_file,
)

from .sandbox_file_ref import (
    SANDBOX_UPLOAD_DIR,
    FileProcessResult,
    SandboxFileRef,
    UserInputType,
    build_enhanced_query_with_files,
    detect_file_type,
    detect_mime_type,
    download_file_from_url,
    initialize_files_in_sandbox,
    is_image_file,
    process_chat_input_files,
    process_user_input_file,
)

from .dattach_utils import (
    DAttachBuilder,
    attach,
    attach_list,
    create_dattach_content,
    create_dattach_list_content,
    get_mime_type,
    render_dattach,
    render_dattach_list,
)

__all__ = [
    # File Type Config
    "FileProcessMode",
    "FileTypeConfig",
    "FileTypeConfigManager",
    "FileTypeRule",
    "DEFAULT_CONFIG",
    "get_file_process_mode",
    "is_model_direct_file",
    "is_sandbox_tool_file",
    # Sandbox File Ref
    "SANDBOX_UPLOAD_DIR",
    "FileProcessResult",
    "SandboxFileRef",
    "UserInputType",
    "build_enhanced_query_with_files",
    "detect_file_type",
    "detect_mime_type",
    "download_file_from_url",
    "initialize_files_in_sandbox",
    "is_image_file",
    "process_chat_input_files",
    "process_user_input_file",
    # D-Attach Utils
    "DAttachBuilder",
    "attach",
    "attach_list",
    "create_dattach_content",
    "create_dattach_list_content",
    "get_mime_type",
    "render_dattach",
    "render_dattach_list",
]
