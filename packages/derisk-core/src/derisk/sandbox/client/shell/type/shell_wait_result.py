from dataclasses import dataclass, asdict
from typing import Dict, Any

from .bash_command_status import BashCommandStatus


@dataclass
class ShellWaitResult:
    """
    Process wait result model
    """

    status: BashCommandStatus
    """Process status"""

    def to_dict(self) -> Dict[str, Any]:
        """将对象转换为字典（递归转换嵌套对象）"""
        return asdict(self)