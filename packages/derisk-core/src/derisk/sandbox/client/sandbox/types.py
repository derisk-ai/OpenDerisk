from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

from .tool_types import ToolSpec, ToolCategory


@dataclass
class SystemEnv:
    os: str
    os_version: str
    arch: str
    user: str
    home_dir: str
    timezone: str
    occupied_ports: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuntimeEnv:
    """
    version, path, etc. (python3, python3.11, python3.12, pip3, pip, uv, jupyter)
    """
    python: List[ToolSpec]
    nodejs: List[ToolSpec]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SandboxDetail:
    """
    system environment info
    """
    system: SystemEnv
    runtime: RuntimeEnv
    utils: List[ToolCategory]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SandboxResponse:
    instance_id: str
    name: Optional[str] = None
    success: Optional[bool] = None
    message: Optional[str] = None
    data: Optional[Any] = None
    home_dir: Optional[str] = None
    version: Optional[str] = None
    detail: Optional[SandboxDetail] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
