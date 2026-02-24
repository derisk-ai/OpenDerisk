from dataclasses import dataclass, field, asdict
from typing import Optional
import datetime as dt

@dataclass
class ShellSessionInfo:
    """
    Shell session information
    """
    status: str = field(metadata={"description": "Session status"})
    working_dir: Optional[str] = field(
        default=None,
        metadata={"description": "Working directory"}
    )
    created_at: Optional[dt.datetime] = field(
        default=None,
        metadata={"description": "Creation timestamp"}
    )
    last_used_at: Optional[dt.datetime] = field(
        default=None,
        metadata={"description": "Last used timestamp"}
    )
    age_seconds: Optional[int] = field(
        default=None,
        metadata={"description": "Age of session in seconds"}
    )
    current_command: Optional[str] = field(
        default=None,
        metadata={"description": "Currently executing command"}
    )

    def to_dict(self):
        return asdict(self)
