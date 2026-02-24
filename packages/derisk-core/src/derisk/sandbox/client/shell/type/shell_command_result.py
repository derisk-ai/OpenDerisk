from dataclasses import dataclass, field, asdict
from typing import Optional, List

from .bash_command_status import BashCommandStatus
from .console_record import ConsoleRecord


@dataclass
class ShellCommandResult:
    """
    Shell command execution result model
    """
    session_id: str
    """Shell session ID"""

    status: BashCommandStatus
    """Command execution status"""

    command: Optional[str] = field(default=None)
    """Executed command"""

    terminal_id: Optional[str] = field(
        default=None,
        metadata={"description": "Executed command Terminal ID."}
    )
    output: Optional[str] = field(default=None)
    """Command execution output, only has value when status is completed"""

    console: Optional[List[ConsoleRecord]] = field(default=None)
    """Console command records"""

    exit_code: Optional[int] = field(default=None)
    """Command execution exit code, only has value when status is completed"""

    def to_dict(self):
        return asdict(self)