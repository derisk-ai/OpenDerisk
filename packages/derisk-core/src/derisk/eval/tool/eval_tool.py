from abc import ABC
from typing import Optional, Any, Dict

from derisk.agent.resource import BaseTool
from derisk._private.pydantic import BaseModel



class EvalToolOutput(BaseModel):
    content: Optional[Any] = None
    is_exe_success: bool = True
    snapshot_params : Optional[Any] = None
    error_msg: Optional[str] = None
    reason: Optional[str] = None


    def debug_view(self) -> dict[str, Any]:
        """输出工具执行过程信息"""
        return {
            "match_snapshot_params": self.snapshot_params,
            "reason": self.reason,
            "error_msg": self.error_msg
        }


class EvalToolExecutor(ABC):

    def __init__(self, tool_info: BaseTool, **kwargs):
        self.tool_info = tool_info

    async def run_tool(self, args:Dict[str, Any], case_id: Optional[str], **kwargs) -> EvalToolOutput:
        raise NotImplementedError()

