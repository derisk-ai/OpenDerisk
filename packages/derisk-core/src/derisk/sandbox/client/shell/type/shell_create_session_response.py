from dataclasses import dataclass, asdict


@dataclass
class ShellCreateSessionResponse:
    """
    Shell session creation response model
    """
    session_id: str
    """Unique identifier of the created shell session"""

    working_dir: str
    """Working directory of the created session"""

    def to_dict(self):
        """Converts the dataclass instance to a dictionary"""
        return asdict(self)
