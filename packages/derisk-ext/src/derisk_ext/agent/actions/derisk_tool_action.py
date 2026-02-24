import logging
from typing import Optional, Any, List
from derisk.agent.expand.actions.tool_action import ToolAction
from derisk.agent.resource import BaseTool, ToolPack
from derisk.vis import SystemVisTag
from .browser_action import BrowserAction
from .monitor_action import MonitorAction
from derisk_ext.vis.common.tags.derisk_monitor import MonitorSpace
from derisk_serve.agent.resource.tool.mcp import MCPToolPack

logger = logging.getLogger(__name__)
MONITOR_MCPS: List[str] = []
_MONITOR_TOOLS: List[str] = []


class DeriskToolAction(MonitorAction, BrowserAction):
    """Tool action class."""
    name = "AntTool"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def is_monitor_tool(self, tool_info: BaseTool, tool_pack: Optional[ToolPack]=None):

        if tool_pack and isinstance(tool_pack, MCPToolPack) and (tool_pack.name in MONITOR_MCPS):
            return True
        if tool_info.name in _MONITOR_TOOLS:
            return True
        return False

    async def is_browser_tool(self, tool_result:  Optional[Any] = None):
        """Is browser tool.

        :param tool_result: tool result
        :type tool_result: Optional[Any]
        :rtype: bool
        """
        from derisk.agent.core.sandbox.tools.browser_tool import BrowserResult
        if tool_result and isinstance(tool_result, BrowserResult):
            return True
        return False

    async def gen_view(self, message_id, tool_call_id,  tool_info: BaseTool, status,
                       tool_pack: Optional[ToolPack] =None,
                       args: Optional[Any] = None,
                       out_type: Optional[str] = "json",
                       tool_result: Optional[Any] = None, err_msg: Optional[str] = None, tool_cost: float = 0,
                       start_time: Optional[Any] = None, **kwargs):
        is_monitor_tool = await self.is_monitor_tool( tool_info,tool_pack)
        is_browser_tool = await self.is_browser_tool(tool_result)
        if is_monitor_tool:
            self.action_view_tag: str = MonitorSpace.vis_tag()
            return await MonitorAction.gen_view(self, message_id=message_id, tool_call_id=tool_call_id,
                                                   tool_pack=tool_pack, tool_info=tool_info, status=status, args=args,
                                                   out_type=out_type, tool_result=tool_result, err_msg=err_msg,
                                                   tool_cost=tool_cost, start_time=start_time, **kwargs)
        elif is_browser_tool:
            return await BrowserAction.gen_view(self, message_id=message_id, tool_call_id=tool_call_id,
                                             tool_pack=tool_pack, tool_info=tool_info, status=status, args=args,
                                             out_type=out_type, tool_result=tool_result, err_msg=err_msg,
                                             tool_cost=tool_cost, start_time=start_time, **kwargs)
        else:
            self.action_view_tag: str = SystemVisTag.VisTool.value
            return await ToolAction.gen_view(self, message_id=message_id, tool_call_id=tool_call_id,
                                             tool_pack=tool_pack, tool_info=tool_info, status=status, args=args,
                                             out_type=out_type, tool_result=tool_result, err_msg=err_msg,
                                             tool_cost=tool_cost, start_time=start_time, **kwargs)

    async def gen_content(self, tool_result: Any) -> Any:
        is_browser_tool = await self.is_browser_tool(tool_result.get("content"))
        if is_browser_tool:
            return await BrowserAction.gen_content(self, tool_result=tool_result)
        return tool_result["content"]

