from dataclasses import dataclass, asdict

from .bash_command_status import BashCommandStatus


@dataclass
class ShellKillResult:
    """
    Process termination result model
    """
    status: BashCommandStatus
    """Process status"""

    returncode: int
    """Process return code"""

    def to_dict(self):
        """Converts the dataclass instance to a dictionary"""
        return asdict(self)