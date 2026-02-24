"""Application Resources for the agent."""

import uuid
from typing import List, Optional

from derisk._private.config import Config
from derisk.agent import AgentMessage, ConversableAgent
from derisk.agent.resource.app import AppInfo, AppResource
from derisk_serve.agent.agents.app_agent_manage import get_app_manager

CFG = Config()
class GptAppResource(AppResource):
    """AppResource resource class."""

    def __init__(self, name: str, app_code: str, **kwargs):
        """Initialize AppResource resource."""
        super().__init__(name, **kwargs)

        self._app_code = app_code
        self._app_name = kwargs.get("app_name")
        self._app_icon = kwargs.get("app_icon")
        self._app_desc = kwargs.get("app_desc")

    @property
    def app_code(self) -> str:
        """Return the app code."""
        return self._app_code

    @property
    def app_desc(self) -> str:
        """Return the app description."""
        return self._app_desc

    @property
    def app_name(self) -> str:
        """Return the app name."""
        return self._app_name

    @property
    def app_icon(self) -> str:
        """Return the app icon."""
        return self._app_icon

    @classmethod
    def _get_app_list(cls, **kwargs) -> List[AppInfo]:
        from derisk_serve.agent.agents.app_agent_manage import get_app_manager

        # Only call this function when the system app is initialized
        apps = get_app_manager().get_derisks(query=kwargs.get("query"), user_code=kwargs.get("user_code"), sys_code=kwargs.get("sys_code"))
        app_list = []
        for app in apps:
            app_list.append(
                AppInfo(name=app.app_name, icon=app.icon, code=app.app_code, desc=app.app_describe)
            )
        return app_list

    async def _start_app(
        self,
        user_input: str,
        sender: ConversableAgent,
        conv_uid: Optional[str] = None,
    ) -> AgentMessage:
        """Start App By AppResource."""
        conv_uid = str(uuid.uuid4()) if conv_uid is None else conv_uid
        gpts_app = get_app_manager().get_app(self._app_code)
        app_agent = await get_app_manager().create_agent_by_app_code(
            gpts_app, conv_uid=conv_uid
        )

        agent_message = AgentMessage(
            content=user_input,
            current_goal=user_input,
            context={
                "conv_uid": conv_uid,
            },
            rounds=0,
        )
        reply_message: AgentMessage = await app_agent.generate_reply(
            received_message=agent_message, sender=sender
        )

        return reply_message
