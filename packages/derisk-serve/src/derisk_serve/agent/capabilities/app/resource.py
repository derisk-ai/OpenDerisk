"""AppResource —— 子 Agent capability 输入投影(RFC-005 Step B)。

App 资源是纯声明类:get_prompt 纯模板渲染 app 描述,无 I/O。
declare 产 app 描述 SYSTEM + agent_start ToolEntry(executor_id=builtin,
执行体=子 agent runtime,本轮选B 复用 builtin,SubAgentExecutor 留后续)。

双轨迁移:AppResource 包装旧 AppResource/GptAppResource 实例(由 build_resource
构建进 ResourcePack),declare 委托旧实例属性(app_name/app_code/app_desc)渲染。
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.tool_entry import (
    BUILTIN_EXECUTOR_ID,
    ToolEntry,
)
from derisk.core.interface.resource.protocol import ResourceProtocol

logger = logging.getLogger(__name__)

_APP_TEMPLATE_ZH = (
    "{{app_name}}：{% if app_code %}(app_code: {{app_code}}){% endif %}"
    "调用此资源与应用 {{app_name}} 进行交互。"
    "应用 {{app_name}} 有什么用？{{description}}"
)


def _render_app_desc(app_name: str, app_code: str, description: str) -> str:
    from derisk.util.template_utils import render
    return render(
        _APP_TEMPLATE_ZH,
        {"app_name": app_name, "app_code": app_code, "description": description},
    )


class AppCapabilityResource(ResourceProtocol):
    """子 Agent capability:declare app 描述 + agent_start 工具。

    双轨:由旧 AppResource/GptAppResource 实例包装构造,declare 委托其属性。
    capability_id="app"。
    """

    capability_id = "app"
    protocol_version = 1

    def __init__(
        self,
        legacy_instance: Any = None,
        app_name: Optional[str] = None,
        app_code: Optional[str] = None,
        description: Optional[str] = None,
        agent_start_tool: Any = None,
    ):
        self._legacy = legacy_instance
        self._app_name = app_name
        self._app_code = app_code
        self._description = description
        self._agent_start_tool = agent_start_tool

    @classmethod
    def declare(cls, config: Any) -> List[Contribution]:
        return []

    def declare_app(self) -> List[Contribution]:
        """实例方法:产 app 描述 SYSTEM + agent_start TOOLS Contribution。"""
        contribs: List[Contribution] = []
        name, code, desc = self._resolve_app()
        if not name:
            return contribs
        try:
            text = _render_app_desc(name, code, desc)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[app] render app desc failed: {e}")
            text = f"{name}: {desc}"
        contribs.append(
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.SYSTEM,
                content=text,
                lifetime=Lifetime.CONFIG_STATIC,
                cache_scope=CacheScope.USER,
                order=30,
            )
        )
        # agent_start 工具(若提供),executor_id=builtin(选B,执行体在子agent runtime)
        tool = self._resolve_agent_start_tool()
        if tool is not None:
            contribs.append(
                Contribution(
                    capability_id=self.capability_id,
                    slot=Slot.TOOLS,
                    content=tool,
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.NONE,
                    order=30,
                )
            )
        return contribs

    def _resolve_app(self):
        if self._app_name is not None:
            return self._app_name, self._app_code or "", self._description or ""
        if self._legacy is None:
            return None, None, None
        name = getattr(self._legacy, "app_name", None) or getattr(self._legacy, "name", None)
        code = getattr(self._legacy, "app_code", "") or ""
        desc = getattr(self._legacy, "app_desc", "") or getattr(self._legacy, "description", "") or ""
        return name, code, desc

    def _resolve_agent_start_tool(self):
        if self._agent_start_tool is not None:
            return self._agent_start_tool
        return None  # 工具由 react_master_agent 系统注入路径提供,此处暂不冗余注入

    def requires(self, config: Any = None) -> List[str]:
        return []