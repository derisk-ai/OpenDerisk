"""
File System Tools - Unified Tool Authorization System

This module implements file system operations:
- read: Read file content
- write: Write content to file
- edit: Edit file with oldString/newString replacement
- glob: Search files by pattern
- grep: Search content in files

Version: 2.0
"""

import os
import glob as glob_module
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..decorators import file_read_tool, file_write_tool, tool
from ..base import ToolResult
from ..metadata import (
    ToolParameter,
    ToolCategory,
    AuthorizationRequirement,
    RiskLevel,
    RiskCategory,
)


@file_read_tool(
    name="read",
    description="Read content from a file. Returns file content with line numbers.",
    parameters=[
        ToolParameter(
            name="file_path",
            type="string",
            description="Absolute path to the file to read",
            required=True,
        ),
        ToolParameter(
            name="offset",
            type="integer",
            description="Line number to start from (1-indexed)",
            required=False,
            default=1,
            min_value=1,
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Maximum number of lines to read",
            required=False,
            default=2000,
            min_value=1,
            max_value=10000,
        ),
    ],
    tags=["file", "read", "content"],
)
async def read_file(
    file_path: str,
    offset: int = 1,
    limit: int = 2000,
    context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Read file content with optional offset and limit."""
    try:
        path = Path(file_path)
        
        if not path.exists():
            return ToolResult.error_result(f"File not found: {file_path}")
        
        if not path.is_file():
            return ToolResult.error_result(f"Path is not a file: {file_path}")
        
        # Read file with line numbers
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        
        # Apply offset and limit
        start_idx = max(0, offset - 1)  # Convert to 0-indexed
        end_idx = min(start_idx + limit, total_lines)
        
        # Format with line numbers
        output_lines = []
        for i in range(start_idx, end_idx):
            line_num = i + 1
            line_content = lines[i].rstrip('\n\r')
            # Truncate very long lines
            if len(line_content) > 2000:
                line_content = line_content[:2000] + "... (truncated)"
            output_lines.append(f"{line_num}: {line_content}")
        
        output = "\n".join(output_lines)
        
        return ToolResult.success_result(
            output,
            total_lines=total_lines,
            lines_returned=len(output_lines),
            offset=offset,
            limit=limit,
        )
        
    except PermissionError:
        return ToolResult.error_result(f"Permission denied: {file_path}")
    except Exception as e:
        return ToolResult.error_result(f"Error reading file: {str(e)}")


@file_write_tool(
    name="write",
    description="Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
    parameters=[
        ToolParameter(
            name="file_path",
            type="string",
            description="Absolute path to the file to write",
            required=True,
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Content to write to the file",
            required=True,
        ),
    ],
    tags=["file", "write", "create"],
)
async def write_file(
    file_path: str,
    content: str,
    context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Write content to a file."""
    try:
        path = Path(file_path)
        
        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Get file info
        stat = path.stat()
        
        return ToolResult.success_result(
            f"Successfully wrote {len(content)} bytes to {file_path}",
            file_path=str(path.absolute()),
            bytes_written=len(content),
            file_size=stat.st_size,
        )
        
    except PermissionError:
        return ToolResult.error_result(f"Permission denied: {file_path}")
    except Exception as e:
        return ToolResult.error_result(f"Error writing file: {str(e)}")


@file_write_tool(
    name="edit",
    description="Edit a file by replacing oldString with newString. The oldString must match exactly.",
    parameters=[
        ToolParameter(
            name="file_path",
            type="string",
            description="Absolute path to the file to edit",
            required=True,
        ),
        ToolParameter(
            name="old_string",
            type="string",
            description="The exact string to find and replace",
            required=True,
        ),
        ToolParameter(
            name="new_string",
            type="string",
            description="The string to replace with",
            required=True,
        ),
        ToolParameter(
            name="replace_all",
            type="boolean",
            description="Replace all occurrences (default: false, replace first only)",
            required=False,
            default=False,
        ),
    ],
    tags=["file", "edit", "replace"],
)
async def edit_file(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Edit a file by replacing exact string matches."""
    try:
        path = Path(file_path)
        
        if not path.exists():
            return ToolResult.error_result(f"File not found: {file_path}")
        
        if not path.is_file():
            return ToolResult.error_result(f"Path is not a file: {file_path}")
        
        # Read current content
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Check if old_string exists
        count = content.count(old_string)
        if count == 0:
            return ToolResult.error_result(
                f"oldString not found in content. Make sure to match the exact text including whitespace."
            )
        
        if count > 1 and not replace_all:
            return ToolResult.error_result(
                f"Found {count} matches for oldString. "
                f"Provide more surrounding context to identify the correct match, "
                f"or set replace_all=true to replace all occurrences."
            )
        
        # Perform replacement
        if replace_all:
            new_content = content.replace(old_string, new_string)
            replacements = count
        else:
            new_content = content.replace(old_string, new_string, 1)
            replacements = 1
        
        # Write back
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        return ToolResult.success_result(
            f"Successfully edited {file_path}. Made {replacements} replacement(s).",
            file_path=str(path.absolute()),
            replacements=replacements,
        )
        
    except PermissionError:
        return ToolResult.error_result(f"Permission denied: {file_path}")
    except Exception as e:
        return ToolResult.error_result(f"Error editing file: {str(e)}")


@file_read_tool(
    name="glob",
    description="Search for files matching a glob pattern. Returns file paths sorted by modification time.",
    parameters=[
        ToolParameter(
            name="pattern",
            type="string",
            description="Glob pattern (e.g., '**/*.py', 'src/**/*.ts')",
            required=True,
        ),
        ToolParameter(
            name="path",
            type="string",
            description="Base directory path (defaults to current working directory)",
            required=False,
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Maximum number of results to return",
            required=False,
            default=100,
            max_value=1000,
        ),
    ],
    tags=["file", "search", "glob", "pattern"],
)
async def glob_search(
    pattern: str,
    path: Optional[str] = None,
    limit: int = 100,
    context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Search for files matching a glob pattern."""
    try:
        # Determine base path
        if path:
            base_path = Path(path)
        elif context and "workspace" in context:
            base_path = Path(context["workspace"])
        else:
            base_path = Path.cwd()
        
        if not base_path.exists():
            return ToolResult.error_result(f"Path not found: {base_path}")
        
        # Search for files
        full_pattern = str(base_path / pattern)
        matches = glob_module.glob(full_pattern, recursive=True)
        
        # Sort by modification time (newest first)
        matches_with_mtime = []
        for match in matches:
            try:
                mtime = os.path.getmtime(match)
                matches_with_mtime.append((match, mtime))
            except (OSError, PermissionError):
                matches_with_mtime.append((match, 0))
        
        matches_with_mtime.sort(key=lambda x: x[1], reverse=True)
        
        # Apply limit
        limited_matches = matches_with_mtime[:limit]
        
        # Format output
        if not limited_matches:
            return ToolResult.success_result(
                f"No files found matching pattern: {pattern}",
                matches=[],
                total=0,
            )
        
        output_lines = [m[0] for m in limited_matches]
        output = "\n".join(output_lines)
        
        return ToolResult.success_result(
            output,
            matches=output_lines,
            total=len(matches),
            returned=len(limited_matches),
        )
        
    except Exception as e:
        return ToolResult.error_result(f"Error searching files: {str(e)}")


@file_read_tool(
    name="grep",
    description="Search file contents using a regular expression pattern. Returns matching lines with context.",
    parameters=[
        ToolParameter(
            name="pattern",
            type="string",
            description="Regular expression pattern to search for",
            required=True,
        ),
        ToolParameter(
            name="path",
            type="string",
            description="Directory or file path to search in",
            required=False,
        ),
        ToolParameter(
            name="include",
            type="string",
            description="File pattern to include (e.g., '*.py', '*.{ts,tsx}')",
            required=False,
        ),
        ToolParameter(
            name="context_lines",
            type="integer",
            description="Number of context lines before and after match",
            required=False,
            default=0,
            max_value=10,
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Maximum number of matches to return",
            required=False,
            default=100,
            max_value=1000,
        ),
    ],
    tags=["file", "search", "grep", "regex", "content"],
)
async def grep_search(
    pattern: str,
    path: Optional[str] = None,
    include: Optional[str] = None,
    context_lines: int = 0,
    limit: int = 100,
    context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Search file contents using regex pattern."""
    try:
        # Compile regex
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ToolResult.error_result(f"Invalid regex pattern: {e}")
        
        # Determine base path
        if path:
            base_path = Path(path)
        elif context and "workspace" in context:
            base_path = Path(context["workspace"])
        else:
            base_path = Path.cwd()
        
        if not base_path.exists():
            return ToolResult.error_result(f"Path not found: {base_path}")
        
        # Collect files to search
        files_to_search: List[Path] = []
        
        if base_path.is_file():
            files_to_search = [base_path]
        else:
            # Use include pattern if provided
            if include:
                # Handle patterns like *.{ts,tsx}
                if "{" in include:
                    # Expand brace patterns
                    match = re.match(r"\*\.{([^}]+)}", include)
                    if match:
                        extensions = match.group(1).split(",")
                        for ext in extensions:
                            files_to_search.extend(base_path.rglob(f"*.{ext.strip()}"))
                    else:
                        files_to_search.extend(base_path.rglob(include))
                else:
                    files_to_search.extend(base_path.rglob(include))
            else:
                # Search all text files
                files_to_search = list(base_path.rglob("*"))
                files_to_search = [f for f in files_to_search if f.is_file()]
        
        # Search files
        matches = []
        files_matched = set()
        
        for file_path in files_to_search:
            if len(matches) >= limit:
                break
            
            if not file_path.is_file():
                continue
            
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                
                for i, line in enumerate(lines):
                    if len(matches) >= limit:
                        break
                    
                    if regex.search(line):
                        files_matched.add(str(file_path))
                        
                        # Build match with context
                        result_lines = []
                        
                        # Context before
                        for j in range(max(0, i - context_lines), i):
                            result_lines.append(f"  {j + 1}: {lines[j].rstrip()}")
                        
                        # Match line
                        result_lines.append(f"> {i + 1}: {line.rstrip()}")
                        
                        # Context after
                        for j in range(i + 1, min(len(lines), i + 1 + context_lines)):
                            result_lines.append(f"  {j + 1}: {lines[j].rstrip()}")
                        
                        matches.append({
                            "file": str(file_path),
                            "line": i + 1,
                            "content": "\n".join(result_lines),
                        })
                        
            except (PermissionError, UnicodeDecodeError, IsADirectoryError):
                continue
        
        # Format output
        if not matches:
            return ToolResult.success_result(
                f"No matches found for pattern: {pattern}",
                matches=[],
                files_matched=0,
            )
        
        output_lines = []
        current_file = None
        for match in matches:
            if match["file"] != current_file:
                current_file = match["file"]
                output_lines.append(f"\n{current_file}")
            output_lines.append(match["content"])
        
        output = "\n".join(output_lines)
        
        return ToolResult.success_result(
            output,
            matches_count=len(matches),
            files_matched=len(files_matched),
        )
        
    except Exception as e:
        return ToolResult.error_result(f"Error searching content: {str(e)}")


# Export all tools for registration
__all__ = [
    "read_file",
    "write_file",
    "edit_file",
    "glob_search",
    "grep_search",
]
