
from dataclasses import dataclass, asdict


@dataclass
class SessionInfo:
    """
    Active session information
    """
    kernel_name: str
    """Kernel name"""

    last_used: float
    """Last used timestamp"""

    age_seconds: int
    """Age of session in seconds"""

    def to_dict(self):
        return asdict(self)
