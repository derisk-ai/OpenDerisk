"""SandboxExecutor —— 共享沙箱运行时执行投影(RFC-006 Stage 2)。

Sandbox 是跨能力共享底座(平台基础设施),**不是** Capability:
- DB/Knowledge/Skill 等 capability 经 `requires=["sandbox"]` 引用本 executor;
- 它本身不是某种资源(无 AgentResource 配置),由 react_master 在构造 facade 时
  直接注入 `executor_provider["sandbox"]`。

prepare 校验 sandbox client 就绪(release 置 RELEASED)。工具执行暂留 Route A
(builtin 回调,见 SandboxResource 注释"选B 方案")——Route B 收编沙箱工具执行
是后续决策,本阶段只打通生命周期 + provider 接线,让 capability 的 `requires`
不再被空 provider 静默跳过。
"""

from __future__ import annotations

import logging
from typing import Any

from derisk.core.interface.resource.executor import (
    Executor,
    ExecutorStatus,
    ReleaseReason,
)

logger = logging.getLogger(__name__)

SANDBOX_EXECUTOR_ID = "sandbox"


class SandboxExecutor(Executor):
    """共享沙箱运行时 lifecycle 执行器(非 Capability)。

    持有 sandbox_manager 引用;prepare 校验其 client 就绪。多 capability 共享
    同一 SandboxExecutor 实例(facade 注入一份,registry 引用计数复用)。
    """

    def __init__(self, sandbox_manager: Any = None):
        self._sandbox_manager = sandbox_manager
        self._status = ExecutorStatus.UNINITIALIZED

    @property
    def executor_id(self) -> str:
        return SANDBOX_EXECUTOR_ID

    @property
    def status(self) -> ExecutorStatus:
        return self._status

    def _client_available(self) -> bool:
        mgr = self._sandbox_manager
        return bool(mgr is not None and getattr(mgr, "client", None) is not None)

    async def prepare(self) -> None:
        """校验 sandbox client 已就绪(client 由 sandbox_manager 在 agent init 建好)。"""
        if self._client_available():
            self._status = ExecutorStatus.READY
        else:
            # 无 client 不视为致命:部分场景(纯协议/测试)无沙箱,后续 acquire 执行
            # 会自然失败。保持 UNINITIALIZED 让 _prepare_executors 视情况处理。
            raise RuntimeError("SandboxExecutor: sandbox client not available")

    async def execute(self, call: Any) -> Any:
        """沙箱工具执行暂走 Route A(builtin 回调,自处理沙箱/本地切换)。

        Route B 收编沙箱工具执行体是后续独立决策;本阶段 executor 仅承担 lifecycle。
        """
        raise NotImplementedError(
            "SandboxExecutor.execute 未实现 —— 沙箱工具暂走 Route A(builtin)"
        )

    async def release(self, reason: ReleaseReason) -> None:
        """置 RELEASED。sandbox_manager 的 client 生命周期由 agent_chat 独立管(已有清理路径)。"""
        self._status = ExecutorStatus.RELEASED