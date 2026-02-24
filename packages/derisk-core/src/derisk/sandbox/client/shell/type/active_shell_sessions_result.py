from dataclasses import dataclass, field, asdict
from typing import Dict

from .shell_session_info import ShellSessionInfo


# 假设 ShellSessionInfo 已在其他地方定义（也应是 dataclass 或基本类型）
@dataclass
class ActiveShellSessionsResult:
    """
    Active shell sessions result
    """
    sessions: Dict[str, ShellSessionInfo] = field(default_factory=dict)
    """
    Map of session ID to session info
    """

    def to_dict(self):
        return asdict(self)