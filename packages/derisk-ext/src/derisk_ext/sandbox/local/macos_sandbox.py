"""
macOS Sandbox Exec Integration

Provides secure process isolation using macOS's sandbox-exec utility.
"""
import os
import tempfile
import json
import logging
from typing import List, Dict, Optional, Set
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SandboxProfileConfig:
    """Configuration for generating a macOS sandbox profile."""

    profile_name: str = "derisk_sandbox"
    read_only_paths: List[str] = field(default_factory=list)
    read_write_paths: List[str] = field(default_factory=list)
    deny_paths: List[str] = field(default_factory=list)
    allow_network: bool = True
    deny_network: bool = False
    allow_network_domains: List[str] = field(default_factory=list)
    deny_network_domains: List[str] = field(default_factory=list)
    allow_process_launch: bool = True
    allowed_parent_apps: List[str] = field(default_factory=list)
    max_files: Optional[int] = None
    max_memory: Optional[int] = None


class MacOSSandboxProfile:
    """Generates and manages macOS sandbox-exec profiles."""

    # System default directories that should be allowed in most sandboxes
    DEFAULT_READ_WRITE_PATHS = [
        "/tmp",
        "/var/folders",  # macOS temp storage
    ]

    DEFAULT_READ_ONLY_PATHS = [
        "/System/Library",
        "/usr/lib",
        "/usr/bin",
        "/usr/local/bin",
        "/opt",
        "/Library/Python",
        "/Applications",
        # Add common Python paths
    ]

    DENY_PATHS = [
        "/Users",
        "/private/var/root",
        "/etc",
        "/Applications/.",
    ]

    @staticmethod
    def generate_profile_template(config: SandboxProfileConfig) -> str:
        """
        Generate a sandbox-exec profile SBPL (Sandbox Profile Language) template.

        Reference: https://developer.apple.com/library/archive/documentation/Security/Conceptual/AppSandboxDesignGuide/AboutAppSandbox/AboutAppSandbox.html
        """
        # Start with version and profile name
        lines = [
            '(version 1)',
            f'(import "com.apple.security.cs.sbpl")',
            f'(import "system.sb")',
            '',
            f'(define profile "{config.profile_name}"',
            '    (deny default)',
            '',
        ]

        # Allow basic infrastructure
        lines.extend([
            '    (allow process-exec',
            '        (literal "/bin/sh")',
            '        (literal "/bin/zsh")',
            '        (literal "/bin/bash")',
            '        (literal "/usr/bin/python3")',
            '        (literal "/usr/local/bin/python3")',
            '        (literal "/Library/Frameworks/Python.framework/*/bin/python3")',
            '    )',
            '',
        ])

        # File system rules
        lines.append('    ;; File System Rules')
        lines.append('    (deny file-write*)')
        lines.append('    (deny file-read*)')

        # Allow specific read-only paths
        if config.read_only_paths or MacOSSandboxProfile.DEFAULT_READ_ONLY_PATHS:
            lines.append('    (allow file-read*')
            for path in MacOSSandboxProfile.DEFAULT_READ_ONLY_PATHS:
                lines.append(f'        (literal "{path}")')
            for path in config.read_only_paths:
                path_str = MacOSSandboxProfile._escape_path(path)
                lines.append(f'        (literal "{path_str}")')
            lines.append('    )')
            lines.append('')

        # Allow specific read-write paths
        if config.read_write_paths or MacOSSandboxProfile.DEFAULT_READ_WRITE_PATHS:
            lines.append('    (allow file-write* file-read*')
            for path in MacOSSandboxProfile.DEFAULT_READ_WRITE_PATHS:
                lines.append(f'        (literal "{path}")')
            for path in config.read_write_paths:
                path_str = MacOSSandboxProfile._escape_path(path)
                lines.append(f'        (literal "{path_str}")')
            lines.append('    )')
            lines.append('')

        # Explicitly deny paths
        if config.deny_paths or MacOSSandboxProfile.DENY_PATHS:
            lines.append('    (deny file-write* file-read*')
            for path in MacOSSandboxProfile.DENY_PATHS:
                lines.append(f'        (literal "{path}")')
            for path in config.deny_paths:
                path_str = MacOSSandboxProfile._escape_path(path)
                lines.append(f'        (literal "{path_str}")')
            lines.append('    )')
            lines.append('')

        # Network rules
        lines.append('    ;; Network Rules')
        if config.allow_network and not config.deny_network:
            lines.append('    (allow network*)')
            if config.deny_network_domains:
                lines.append('    (deny network*')
                for domain in config.deny_network_domains:
                    lines.append(f'        (literal "{domain}")')
                lines.append('    )')
        elif config.allow_network_domains:
            lines.append('    (deny network*)')
            lines.append('    (allow network*')
            for domain in config.allow_network_domains:
                lines.append(f'        (literal "{domain}")')
            lines.append('    )')
        else:
            lines.append('    (deny network*)')
        lines.append('')

        # Process launch rules
        if config.allow_process_launch:
            lines.append('    (allow process-fork)')
            lines.append('    (allow process-exec (require-all (regex #".*")))')
        else:
            lines.append('    (deny process-fork)')
            lines.append('    (deny process-exec (require-all (regex #".*")))')

        # Resource limits
        if config.max_files:
            lines.append(f'    (allow file-read* (limit "open-file-count" {config.max_files}))')
        if config.max_memory:
            # Memory limit in sandbox is not directly supported, but can be hinted
            lines.append(f'    ;; Memory limit: {config.max_memory} bytes (soft limit)')

        lines.append(')')
        lines.append('')

        # Apply the profile
        lines.append(f'(apply "{config.profile_name}")')

        return '\n'.join(lines)

    @staticmethod
    def _escape_path(path: str) -> str:
        """Escape special characters in path for SBPL."""
        # SBPL uses double quotes for literals, escape them
        return path.replace('\\', '\\\\').replace('"', '\\"')

    @staticmethod
    def create_profile_file(config: SandboxProfileConfig) -> str:
        """
        Create a temporary sandbox profile file and return its path.

        Args:
            config: SandboxProfileConfig to generate the profile from

        Returns:
            Path to the created profile file
        """
        profile_content = MacOSSandboxProfile.generate_profile_template(config)

        # Use a predictable name for easier cleanup
        profile_dir = Path(tempfile.gettempdir()) / "derisk_sandbox_profiles"
        profile_dir.mkdir(parents=True, exist_ok=True)

        profile_path = profile_dir / f"{config.profile_name}.sbpl"

        with open(profile_path, 'w') as f:
            f.write(profile_content)

        logger.info(f"Created sandbox profile: {profile_path}")
        return str(profile_path)

    @staticmethod
    def cleanup_profile(profile_name: Optional[str] = None):
        """
        Clean up sandbox profile files.

        Args:
            profile_name: Specific profile name to clean, or None to clean all
        """
        profile_dir = Path(tempfile.gettempdir()) / "derisk_sandbox_profiles"
        if not profile_dir.exists():
            return

        if profile_name:
            profile_path = profile_dir / f"{profile_name}.sbpl"
            if profile_path.exists():
                try:
                    profile_path.unlink()
                    logger.info(f"Removed sandbox profile: {profile_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove profile {profile_path}: {e}")
        else:
            # Clean all profiles
            for profile_path in profile_dir.glob("*.sbpl"):
                try:
                    profile_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to remove profile {profile_path}: {e}")
            try:
                profile_dir.rmdir()
            except Exception:
                pass


class MacOSSandboxWrapper:
    """Wrapper for sandbox-exec with proper process management."""

    def __init__(self, profile_name: str, config: SandboxProfileConfig):
        self.profile_name = profile_name
        self.config = config
        self.profile_path: Optional[str] = None
        self._check_sandbox_available()

    @staticmethod
    def _check_sandbox_available() -> bool:
        """Check if sandbox-exec is available on the system."""
        try:
            result = os.system("which sandbox-exec > /dev/null 2>&1")
            return result == 0
        except Exception:
            return False

    def __enter__(self):
        """Create profile when entering context."""
        self.profile_path = MacOSSandboxProfile.create_profile_file(self.config)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up profile when exiting context."""
        if self.profile_path:
            try:
                if os.path.exists(self.profile_path):
                    os.remove(self.profile_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup profile {self.profile_path}: {e}")

    @property
    def is_available(self) -> bool:
        """Check if sandbox-exec is available."""
        return self._check_sandbox_available()

    def get_executable_command(self, command: List[str]) -> List[str]:
        """
        Wrap a command to run under sandbox-exec.

        Args:
            command: Command and arguments to wrap

        Returns:
            Modified command list with sandbox-exec prefix
        """
        if not self.is_available:
            logger.warning("sandbox-exec not available, running without isolation")
            return command

        if not self.profile_path:
            raise RuntimeError("Profile not created. Use context manager or call create_profile first.")

        return [
            "sandbox-exec",
            "-p",
            self._get_profile_command(),
            *command
        ]

    def _get_profile_command(self) -> str:
        """
        Get the profile content as a shell command.

        Instead of loading from file, we can pass the profile directly.
        """
        if self.profile_path:
            # Read from file to embed in command
            with open(self.profile_path, 'r') as f:
                profile = f.read()
            return profile
        return MacOSSandboxProfile.generate_profile_template(self.config)


def create_sandbox_wrapper(
    session_id: str,
    work_dir: str,
    allow_network: bool = True,
    max_memory: Optional[int] = None,
) -> MacOSSandboxWrapper:
    """
    Create a configured MacOSSandboxWrapper for a session.

    Args:
        session_id: Unique session identifier
        work_dir: Working directory to allow read-write access
        allow_network: Whether to allow network access
        max_memory: Optional memory limit in bytes

    Returns:
        MacOSSandboxWrapper instance
    """
    config = SandboxProfileConfig(
        profile_name=f"derisk_{session_id}",
        read_write_paths=[work_dir],
        allow_network=allow_network,
        max_memory=max_memory,
    )

    return MacOSSandboxWrapper(config.profile_name, config)


# Predefined profile templates

STRICT_PROFILE = SandboxProfileConfig(
    profile_name="strict",
    allow_network=False,
    allow_process_launch=False,
)

NETWORK_ONLY_PROFILE = SandboxProfileConfig(
    profile_name="network_only",
    allow_network=True,
    allow_process_launch=False,
)

DEVELOPMENT_PROFILE = SandboxProfileConfig(
    profile_name="development",
    allow_network=True,
    allow_process_launch=True,
    read_write_paths=["/tmp"],
)