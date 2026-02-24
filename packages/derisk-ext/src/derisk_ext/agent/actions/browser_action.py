import base64
import json
import logging
import re
import uuid
from io import BytesIO
from typing import Optional, Any

from derisk._private.config import Config
from derisk.agent import ConversableAgent, AgentContext, Resource
from derisk.agent.core.action.base import ToolCall
from derisk.agent.core.sandbox.tools.browser_tool import BROWSER_TOOLS
from derisk.agent.expand.actions.sandbox_action import SandboxAction
from derisk.agent.expand.actions.tool_action import  ToolInput
from derisk.agent.resource import BaseTool, ToolPack
from derisk.core.interface.file import FileStorageClient
from derisk_ext.vis.derisk.tags.drsk_browser import DrskBrowser

logger = logging.getLogger(__name__)
CFG = Config()
ONE_YEAR_SECONDS = 365 * 24 * 3600


class BrowserAction(SandboxAction):
    """Browser action class."""
    name = "Browser"

    def __init__(self, **kwargs):
        self.vis: DrskBrowser = DrskBrowser()
        super().__init__(**kwargs)

    async def gen_view(
            self,
            message_id,
            tool_call_id,
            tool_info: BaseTool,
            status,
            tool_pack: Optional[ToolPack] = None,
            args: Optional[Any] = None,
            out_type: Optional[str] = "json",
            tool_result: Optional[Any] = None,
            err_msg: Optional[str] = None,
            tool_cost: float = 0,
            start_time: Optional[Any] = None,
            **kwargs
    ):
        # view = None
        try:
            # memory = kwargs.get("memory")
            # agent_context = kwargs.get("agent_context")
            # messages = await memory.gpts_memory.get_session_messages(
            #     agent_context.conv_session_id)
            browser_outputs = []
            history_items = []
            # for message in messages:
            #     action_out = message.action_report
            #     if action_out:
            #         browser_outputs = [out for out in action_out if "browser_" in
            #                            out.action]
            # for browser_output in browser_outputs:
            #     history_items = parse_browser_step(browser_output.view)
            #     if history_items:
            #         for i, history_item in enumerate(history_items):
            #             history_item["index"] = i
            if tool_result.success:
                if tool_result.screenshot is not None or tool_result.screenshot != "":
                    fs_client = FileStorageClient.get_instance(CFG.SYSTEM_APP)
                    image_data = base64.b64decode(tool_result.screenshot)
                    file_data = BytesIO(image_data)
                    image_params = {
                        'response-content-type': 'image/jpeg',
                    }
                    file_name = f"{uuid.uuid4().hex[:16]}.png"
                    oss_backend = fs_client.storage_system.storage_backends.get("oss")
                    if oss_backend and hasattr(oss_backend, "save_public_image"):
                        image_url = oss_backend.save_public_image(
                            "derisk_knowledge_file",
                            file_name,
                            file_data=file_data
                        )
                    else:
                        file_str = fs_client.save_file(
                            "derisk_knowledge_file",
                            file_name,
                            file_data=file_data,
                            storage_type="oss",
                            custom_metadata=image_params,
                        )
                        image_url = fs_client.get_public_url(
                            file_str,
                            expire=ONE_YEAR_SECONDS,
                            params=image_params
                        )

                    tool_result.image_url = image_url
                else:
                    image_url = tool_result.image_url
                item = {
                    "url": tool_result.url,
                    "description": "Derisk正在使用浏览器-" + tool_result.title,
                    "web_image": image_url,
                    "index": len(history_items),
                    "action": f"{tool_info.description}"
                }
                history_items.extend([item])
                param = {
                    "content": tool_result.elements,
                    "message_id": message_id,
                    "items": history_items,
                    "current_index": len(history_items) if history_items else 0,
                    "url": tool_result.url
                }
            else:
                param = {
                    "content": tool_result.error,
                    "message_id": message_id,
                    "items": history_items,
                    "current_index": len(history_items) if history_items else 0,
                    "url": tool_result.url
                }
            view = await self.vis.display(
                **param
            )
            return view
        except Exception as e:
            logger.exception("Browser Tool Result View Failed!")
            return f"Browser Tool Result View Failed!{str(e)}"

    async def gen_content(self, tool_result: Any) -> Any:
        from derisk.agent.core.sandbox.tools.browser_tool import BrowserResult
        browser_result: BrowserResult = tool_result.get("content")
        if browser_result.success:
            content_dict = {
                "elements": browser_result.elements,
                "image_url": browser_result.image_url,
            }
            content = json.dumps(content_dict, ensure_ascii=False)
        else:
            content = browser_result.error
        # tool_result["content"] = content
        return content

    @classmethod
    def parse_action(
        cls,
        tool_call: ToolCall,
        default_action: Optional["Action"] = None,
        resource: Optional[Resource] = None,
        **kwargs,
    ) -> Optional["Action"]:
        """Parse the action from the message.

        If you want skip the action, return None.
        """
        if tool_call.name in BROWSER_TOOLS:
            agent: ConversableAgent = kwargs.get('agent')
            agent_context: AgentContext = kwargs.get('agent_context')
            if not agent.sandbox_manager or not agent.sandbox_manager.client:
                raise ValueError("没有可用的沙箱环境,无法使用沙箱环境工具！")
            sandbox_client = agent.sandbox_manager.client
            return cls(action_uid=tool_call.tool_call_id,
                       action_input=ToolInput(tool_name=tool_call.name,
                                              tool_call_id=tool_call.tool_call_id,
                                              thought=tool_call.thought,
                                              args=tool_call.args),
                       init_params={
                           "client": sandbox_client,
                           "conversation_id": agent_context.conv_id,
                       })
        else:
            return None


def parse_browser_step(text):
    if not isinstance(text, str):
        logger.error(
            f"Browser Tool parse_browser_step View Failed! {text}"
        )
        return []
    pattern = r'drsk-browser\s*\n\s*(\{.*?\})\s*\n```'
    match = re.search(pattern, text, re.DOTALL)

    if match:
        json_str = match.group(1)
        json_str = json_str.replace(r'\"', '"')
        data = json.loads(json_str)
        return data.get("items")
    return None