from typing import Union, Literal, Any

BashCommandStatus = Union[
    Literal["running", "completed", "no_change_timeout", "hard_timeout", "terminated"], Any
]
