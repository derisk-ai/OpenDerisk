"""
Shell Tools - Unified Tool Authorization System

This module implements shell command execution:
- bash: Execute shell commands with danger detection

Version: 2.0
"""

import asyncio
import shlex
import os
import re
from typing import Dict, Any, Optional, List
from pathlib import Path

from ..decorators import shell_tool
from ..base import ToolResult
from ..metadata import (
    ToolParameter,
    ToolCategory,
    AuthorizationRequirement,
    RiskLevel,
    RiskCategory,
)


# Dangerous command patterns that require extra caution
DANGEROUS_PATTERNS = [
    # Destructive file operations
    r"\brm\s+(-[rf]+\s+)*(/|~|\$HOME)",  # rm -rf /
    r"\brm\s+-[rf]*\s+\*",  # rm -rf *
    r"\bmkfs\b",  # Format filesystem
    r"\bdd\s+.*of=/dev/",  # dd to device
    r">\s*/dev/sd[a-z]",  # Write to disk device
    
    # System modification
    r"\bchmod\s+777\b",  # Overly permissive chmod
    r"\bchown\s+.*:.*\s+/",  # chown system files
    r"\bsudo\s+",  # sudo commands
    r"\bsu\s+",  # su commands
    
    # Network dangers
    r"\bcurl\s+.*\|\s*(ba)?sh",  # Pipe to shell
    r"\bwget\s+.*\|\s*(ba)?sh",  # Pipe to shell
    
    # Git dangers
    r"\bgit\s+push\s+.*--force",  # Force push
    r"\bgit\s+reset\s+--hard",  # Hard reset
    r"\bgit\s+clean\s+-fd",  # Clean untracked files
    
    # Database dangers
    r"\bDROP\s+DATABASE\b",  # Drop database
    r"\bDROP\s+TABLE\b",  # Drop table
    r"\bTRUNCATE\s+",  # Truncate table
    
    # Container dangers
    r"\bdocker\s+rm\s+-f",  # Force remove container
    r"\bdocker\s+system\s+prune",  # Prune everything
    r"\bkubectl\s+delete\s+",  # Delete k8s resources
]

# Commands that should never be executed
FORBIDDEN_COMMANDS = [
    r":(){ :|:& };:",  # Fork bomb
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"\binit\s+0\b",
    r"\bpoweroff\b",
]


def detect_dangerous_command(command: str) -> List[str]:
    """
    Detect potentially dangerous patterns in a command.
    
    Args:
        command: The shell command to analyze
        
    Returns:
        List of detected danger reasons
    """
    dangers = []
    command_lower = command.lower()
    
    # Check forbidden commands
    for pattern in FORBIDDEN_COMMANDS:
        if re.search(pattern, command, re.IGNORECASE):
            dangers.append(f"Forbidden command pattern detected: {pattern}")
    
    # Check dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            dangers.append(f"Dangerous pattern detected: {pattern}")
    
    # Check for pipe to shell
    if "|" in command and any(sh in command for sh in ["sh", "bash", "zsh"]):
        if "curl" in command_lower or "wget" in command_lower:
            dangers.append("Piping downloaded content to shell is dangerous")
    
    return dangers


@shell_tool(
    name="bash",
    description="Execute a bash command. Returns stdout, stderr, and exit code.",
    dangerous=True,  # This sets HIGH risk level
    parameters=[
        ToolParameter(
            name="command",
            type="string",
            description="The bash command to execute",
            required=True,
        ),
        ToolParameter(
            name="workdir",
            type="string",
            description="Working directory for command execution",
            required=False,
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Command timeout in seconds (default: 120)",
            required=False,
            default=120,
            min_value=1,
            max_value=3600,
        ),
        ToolParameter(
            name="env",
            type="object",
            description="Environment variables to set",
            required=False,
        ),
    ],
    tags=["shell", "bash", "execute", "command"],
    timeout=300,  # 5 minute max for the tool itself
)
async def bash_execute(
    command: str,
    workdir: Optional[str] = None,
    timeout: int = 120,
    env: Optional[Dict[str, str]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Execute a bash command."""
    try:
        # Check for forbidden commands
        forbidden_reasons = [
            r for r in detect_dangerous_command(command)
            if "Forbidden" in r
        ]
        if forbidden_reasons:
            return ToolResult.error_result(
                f"Command rejected: {'; '.join(forbidden_reasons)}",
                command=command,
                rejected=True,
            )
        
        # Detect dangerous patterns for metadata
        dangers = detect_dangerous_command(command)
        
        # Determine working directory
        cwd = workdir
        if not cwd and context and "workspace" in context:
            cwd = context["workspace"]
        if not cwd:
            cwd = os.getcwd()
        
        # Validate working directory
        if not os.path.isdir(cwd):
            return ToolResult.error_result(f"Working directory not found: {cwd}")
        
        # Prepare environment
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        if context and "env" in context:
            process_env.update(context["env"])
        
        # Execute command
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=process_env,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return ToolResult.error_result(
                f"Command timed out after {timeout} seconds",
                command=command,
                timeout=True,
            )
        
        # Decode output
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        
        # Truncate very long output
        max_output = 50000
        if len(stdout_str) > max_output:
            stdout_str = stdout_str[:max_output] + "\n... (output truncated)"
        if len(stderr_str) > max_output:
            stderr_str = stderr_str[:max_output] + "\n... (stderr truncated)"
        
        # Build output
        exit_code = process.returncode
        
        output_parts = []
        if stdout_str.strip():
            output_parts.append(stdout_str)
        if stderr_str.strip():
            output_parts.append(f"[stderr]\n{stderr_str}")
        
        output = "\n".join(output_parts) if output_parts else "(no output)"
        
        if exit_code == 0:
            return ToolResult.success_result(
                output,
                exit_code=exit_code,
                cwd=cwd,
                dangers_detected=dangers if dangers else None,
            )
        else:
            return ToolResult.error_result(
                f"Command failed with exit code {exit_code}",
                output=output,
                exit_code=exit_code,
                cwd=cwd,
            )
            
    except PermissionError:
        return ToolResult.error_result(f"Permission denied executing command")
    except Exception as e:
        return ToolResult.error_result(f"Error executing command: {str(e)}")


# Export all tools for registration
__all__ = [
    "bash_execute",
    "detect_dangerous_command",
    "DANGEROUS_PATTERNS",
    "FORBIDDEN_COMMANDS",
]
