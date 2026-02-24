from typing import Any
from dataclasses import dataclass, field, asdict

@dataclass
class Response:
    """
    Generic response model for API interface return results
    """

    success: bool | None = field(default=None)
    """
    Whether the operation was successful
    """

    message: str | None = field(default=None)
    """
    Operation result message
    """

    data: Any | None = field(default=None)
    """
    Data returned from the operation
    """

    def to_dict(self):
        return asdict(self)