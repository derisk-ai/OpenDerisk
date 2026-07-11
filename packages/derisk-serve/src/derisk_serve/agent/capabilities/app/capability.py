"""AppCapability —— 子 Agent 自管理资源能力(RFC-006 Stage 4)。

App 是首个落地的自管理 Capability,用于验证 config→Capability→declare→prepare 全链。
特性:
- **无构造 I/O**:GptAppResource.__init__ 只存属性;AppCapability.prepare no-op。
- **declare 纯函数**:渲染 app 描述进 SYSTEM(复用 _APP_TEMPLATE_ZH / _render_app_desc)。
- **execute 不接管**:agent_start(子 agent 调度)是多轮对话而非单工具调用,
  形状对不上 Capability.execute —— 保持 AgentAction 走 sender.send(recipient) 团队
  派发。故 AppCapability.execute 抛 NotImplementedError(agent_start 不经 Route B)。

AppCapability 同时修复了旧 AppCapabilityResource.declare 桩返回 []、真实渲染在
declare_app 未被 facade 调用的问题:新 declare 直接渲染。

双轨:register_wrappers(旧 Resource 实例→AppCapabilityResource 桩)与
register_capability(config→AppCapability factory)并存,Stage 9 删前者。
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
from derisk.core.interface.resource.capability import Capability
from derisk.core.interface.resource.executor import (
    ExecutorCall,
    ExecutorStatus,
    ReleaseReason,
)

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


class AppCapability(Capability):
    """子 Agent 自管理能力:持有 app 元数据,declare 渲染描述。

    capability_id="app";executor_id="app:{app_code}"(多 app 唯一,避免 provider key
    冲突)。execute 不接管 agent_start(保持 AgentAction)。
    """

    capability_id = "app"

    def __init__(
        self,
        app_name: Optional[str] = None,
        app_code: Optional[str] = None,
        description: Optional[str] = None,
    ):
        self._app_name = app_name or ""
        self._app_code = app_code or ""
        self._description = description or ""
        self._status = ExecutorStatus.UNINITIALIZED

    @classmethod
    def from_config(cls, value: dict, system_app: Any = None) -> "AppCapability":
        """从 AgentResource.value dict 构造(无 I/O)。

        value 形如 {"app_code":..., "app_name":..., "app_desc":...}。
        """
        value = value or {}
        return cls(
            app_name=value.get("app_name") or value.get("name") or "",
            app_code=value.get("app_code") or "",
            description=value.get("app_desc") or value.get("description") or "",
        )

    @classmethod
    def from_legacy(cls, legacy_instance: Any) -> "AppCapability":
        """从旧 GptAppResource/AppResource 实例构造(过渡期,Stage 4.5)。

        读旧实例属性(app_name/app_code/app_desc)产 AppCapability,使 facade 遍历时
        翻成自管理 Capability(修复旧 wrapper declare 空桩)。无 I/O。
        Stage 9 旧类退役后改用 from_config。
        """
        name = (
            getattr(legacy_instance, "app_name", None)
            or getattr(legacy_instance, "name", None)
            or ""
        )
        code = getattr(legacy_instance, "app_code", "") or ""
        desc = (
            getattr(legacy_instance, "app_desc", "")
            or getattr(legacy_instance, "description", "")
            or ""
        )
        return cls(app_name=name, app_code=code, description=desc)

    @property
    def executor_id(self) -> str:
        # 与 capability_id 解耦:多 app 唯一,避免 executor_provider key 冲突。
        return f"app:{self._app_code}" if self._app_code else "app"

    # ----------------------------- 输入投影(纯) -------------------------- #
    def declare(self, config: Any = None) -> List[Contribution]:
        """渲染 app 描述进 SYSTEM。无 I/O。

        agent_start 工具不在此贡献(由 react_master 系统注入路径提供,builtin executor)。
        """
        if not self._app_name:
            return []
        try:
            text = _render_app_desc(
                self._app_name, self._app_code, self._description
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[app-capability] render app desc failed: {e}")
            text = f"{self._app_name}: {self._description}"
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.SYSTEM,
                content=text,
                lifetime=Lifetime.CONFIG_STATIC,
                cache_scope=CacheScope.USER,
                order=30,
            )
        ]

    def requires(self, config: Any = None) -> List[str]:
        # app 无 live 实例 / 不依赖共享 executor(不调 execute)。
        return []

    # ----------------------------- 生命周期(无 I/O) ----------------------- #
    async def prepare(self) -> None:
        self._status = ExecutorStatus.READY

    async def execute(self, call: ExecutorCall) -> Any:
        # agent_start 保持 AgentAction 团队派发,不经 Capability.execute。
        raise NotImplementedError(
            "AppCapability.execute 不接管 agent_start —— 保持 AgentAction 路由"
        )

    async def release(self, reason: ReleaseReason) -> None:
        self._status = ExecutorStatus.RELEASED