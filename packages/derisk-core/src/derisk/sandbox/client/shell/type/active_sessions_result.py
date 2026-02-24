
from dataclasses import dataclass, field, asdict
from typing import Dict

from .session_info import SessionInfo


@dataclass
class ActiveSessionsResult:
    """
    Active sessions result
    """
    sessions: Dict[str, SessionInfo] = field(default_factory=dict)
    """
    Map of session ID to session info
    """

    def to_dict(self):
        return asdict(self)
