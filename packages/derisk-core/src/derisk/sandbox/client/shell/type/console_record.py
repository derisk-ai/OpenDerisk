from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class ConsoleRecord:
    """
    Shell command console record model
    """
    command: str  # 无默认值字段在前
    ps1: Optional[str] = field(default=None)
    output: Optional[str] = field(default=None)


    def to_dict(self):
        # 手动处理字段别名输出
        data = asdict(self)
        return data