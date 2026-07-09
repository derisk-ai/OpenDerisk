"""Executor — 能力的执行投影(RFC-005 §3.4)。

本模块只定义:
1. ``ReleaseReason`` / ``ExecutorStatus`` 数据契约。
2. ``Executor`` 抽象(prepare / execute / release)。
3. ``topological_prepare`` 确定性算法——按 requires 拓扑并行就绪 executor。
4. ``ExecutorRegistry`` 引用计数接口(供实现层落地 Agent 级 lifecycle)。

本模块不依赖 v1/v2 任一架构,不碰 ``Resource`` 基类。具体 executor 实现
(DB 连接器包装、沙箱运行时包装)与 registry 实现下沉到 agent/ 层。
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from derisk.util.annotations import PublicAPI

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 释放原因 / 状态
# --------------------------------------------------------------------------- #
@PublicAPI(stability="beta")
class ReleaseReason(str, Enum):
    """Executor 释放原因。决定 release 实现的清理力度(如 ERROR 可能更激进)。"""

    SESSION_END = "session_end"        # 对话完成,确定性释放
    AGENT_END = "agent_end"            # Agent 卸载
    CONFIG_CHANGED = "config_changed"  # 资源配置变更,需重建
    ERROR = "error"                    # 异常退出,可能伴随重起
    EXPLICIT = "explicit"              # 用户/管理面显式释放


@PublicAPI(stability="beta")
class ExecutorStatus(str, Enum):
    """Executor 就绪状态机。"""

    UNINITIALIZED = "uninitialized"  # 尚未 prepare
    PREPARING = "preparing"          # prepare 进行中
    READY = "ready"                  # 已就绪,可 execute
    RELEASING = "releasing"          # release 进行中
    RELEASED = "released"            # 已释放
    FAILED = "failed"                # prepare 失败


# --------------------------------------------------------------------------- #
# ToolCall 传递契约(执行投影的输入)
# --------------------------------------------------------------------------- #
@PublicAPI(stability="beta")
@dataclass(frozen=True)
class ExecutorCall:
    """一次执行调用。executor 据 capability_id 路由到具体执行体。

    作为协议层薄契约,不绑定具体 ToolCall 类型;实现层可包装现有 ToolCall。
    """

    executor_id: str          # 目标 executor
    capability_id: str        # 触发的能力(绑定输入投影↔执行投影)
    tool_name: str
    args: Dict[str, Any] = field(default_factory=dict)
    call_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# Executor 抽象
# --------------------------------------------------------------------------- #
@PublicAPI(stability="beta")
class Executor(ABC):
    """能力的执行投影(RFC-005 §3.4)。

    一个 executor 是一个可执行工具调用的底座:
    - DB 连接器(跑 execute_sql)、沙箱运行时(跑 run_python)、
      子 Agent 运行时(跑 sub_agent)、检索后端(跑 search)。

    沙箱是「通用」executor——可被多 capability 的 tool 共享指向;DB 连接器等
    是「专用」executor,绑死在单 capability。两者同走本抽象,无特例分支。

    生命周期(建议 Agent 级引用计数,见 ExecutorRegistry):
        UNINITIALIZED →(prepare）→ PREPARING → READY →（release）→ RELEASING → RELEASED
    """

    @property
    @abstractmethod
    def executor_id(self) -> str:
        """稳定身份。用于 requires() 引用、缓存键、跨投影握手。"""

    @abstractmethod
    async def prepare(self) -> None:
        """就绪。默认语义 no-op(由子类覆盖)。

        DB连接器→建连接池;沙箱→起实例;子Agent→起运行时。
        Agent 级一次,会话内复用(详见 RFC-005 §3.4 生命周期)。
        幂等:重复调用不应重建已就绪资源。
        """

    @abstractmethod
    async def execute(self, call: ExecutorCall) -> Any:
        """执行一次工具调用。前提:status == READY(否则由调用方 lazy 阻塞)。"""

    @abstractmethod
    async def release(self, reason: ReleaseReason) -> None:
        """释放。默认语义 no-op(由子类覆盖)。

        reason 决定清理力度;ERROR 时可能需更激进清理(如 kill 沙箱进程)。
        幂等:已释放再调不应报错。
        """


# --------------------------------------------------------------------------- #
# 拓扑并行就绪(确定性算法,纯函数式)
# --------------------------------------------------------------------------- #
@PublicAPI(stability="beta")
async def topological_prepare(
    executors: Iterable[Executor],
    requires_map: Optional[Dict[str, List[str]]] = None,
) -> Tuple[Dict[str, Exception], List[str]]:
    """按 requires 拓扑并行 prepare 所有 executor(RFC-005 §3.4)。

    沙箱等被依赖的 executor 先 prepare;依赖它们的在其就绪后才 prepare。
    同一深度的 executor 并行 prepare。

    Args:
        executors: 需要就绪的 executor 集合(以 executor_id 标识)。
        requires_map: {executor_id: [依赖的 executor_id...]}。被依赖项若不在
            ``executors`` 集合中视为外部已就绪,不阻塞。默认空(无依赖)。

    Returns:
        (errors, order):errors = {executor_id: 异常}(prepare 失败者);
        order = 实际 prepare 完成的 executor_id 序列(拓扑序)。
        失败的 executor 不阻塞不依赖它的其它 executor。

    语义对应 RFC-005 §3.4:沙箱先于依赖它的工具就绪,拓扑而非特例判断。
    """
    requires_map = requires_map or {}
    by_id: Dict[str, Executor] = {ex.executor_id: ex for ex in executors}
    ids = set(by_id.keys())

    # 仅保留集合内 + 存在的依赖(外部依赖视为已就绪,不进图)
    deps: Dict[str, Set[str]] = {
        eid: {d for d in requires_map.get(eid, []) if d in ids}
        for eid in ids
    }

    errors: Dict[str, Exception] = {}
    prepared: Set[str] = set()
    order: List[str] = []

    # 检测循环依赖(避免死循环)
    _detect_cycle(deps)

    while len(prepared) + len(errors) < len(ids):
        # 本轮可 prepare:依赖已全部就绪(prepared)且自身未处理
        ready_now = [
            eid for eid in ids
            if eid not in prepared
            and eid not in errors
            and all(d in prepared for d in deps[eid])
        ]
        if not ready_now:
            # 剩余均因依赖失败而阻塞 → 标记为因依赖缺失失败
            blocked = [
                eid for eid in ids
                if eid not in prepared and eid not in errors
            ]
            for eid in blocked:
                errors[eid] = RuntimeError(
                    f"executor {eid} blocked by failed/missing dependency"
                )
            break

        # 并行 prepare 本轮
        async def _prepare_one(eid: str) -> Tuple[str, Optional[Exception]]:
            try:
                await by_id[eid].prepare()
                return eid, None
            except Exception as e:  # noqa: BLE001
                logger.warning(f"executor {eid} prepare failed: {e}")
                return eid, e

        results = await asyncio.gather(*[_prepare_one(eid) for eid in ready_now])
        for eid, err in results:
            if err is None:
                prepared.add(eid)
                order.append(eid)
            else:
                errors[eid] = err

    return errors, order


def _detect_cycle(deps: Dict[str, Set[str]]) -> None:
    """检测依赖图循环,有环抛 ValueError(否则 topological_prepare 会死循环)。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {n: WHITE for n in deps}

    def visit(n: str, path: List[str]) -> None:
        color[n] = GRAY
        for d in deps[n]:
            if color[d] == GRAY:
                raise ValueError(
                    f"executor dependency cycle detected: {' -> '.join(path + [n, d])}"
                )
            if color[d] == WHITE:
                visit(d, path + [n])
        color[n] = BLACK

    for n in deps:
        if color[n] == WHITE:
            visit(n, [])


# --------------------------------------------------------------------------- #
# 引用计数 Registry 接口(Agent 级 lifecycle 契约)
# --------------------------------------------------------------------------- #
@PublicAPI(stability="beta")
class ExecutorRegistry(ABC):
    """Executor 引用计数与生命周期 registry 契约(RFC-005 §3.4)。

    Agent 级 lifecycle:一个会话一份 executor(如沙箱/连接池)被多 capability
    共享,首个 requires 者触发 prepare,引用计数归零时 release。

    本类是契约;具体实现(进程内 registry、跨会话池等)下沉到 agent/ 层。
    """

    @abstractmethod
    async def acquire(self, conv_id: str, executor: Executor) -> Executor:
        """为某会话 acquire 一个 executor。首次则 prepare;后续返回已就绪实例。

        引用计数 +1。返回的 executor 保证 status==READY(否则抛异常)。
        """

    @abstractmethod
    async def release_session(self, conv_id: str, reason: ReleaseReason) -> None:
        """释放某会话持有的所有 executor 引用(SESSION_END 时调用)。

        引用计数 -1,归零者 release(reason)。幂等。
        """

    @abstractmethod
    async def release(
        self, conv_id: str, executor_id: str, reason: ReleaseReason
    ) -> None:
        """释放某会话对单个 executor 的一次引用(逐 capability 释放)。

        计数 -1,归零才 release。共享 executor 不被单个 capability 释放连累。
        幂等:未 acquire 的 (conv_id, executor_id) 不报错。
        """

    @abstractmethod
    def get(self, conv_id: str, executor_id: str) -> Optional[Executor]:
        """获取某会话已 acquire 的 executor(不增计数)。未 acquire 返回 None。"""


# --------------------------------------------------------------------------- #
# 默认内存实现(供落地与测试;生产可替换为带池的实现)
# --------------------------------------------------------------------------- #
class InMemoryExecutorRegistry(ExecutorRegistry):
    """进程内引用计数 registry。

    key: (conv_id, executor_id) → (executor, refcount)。
    不跨进程;会话级隔离。满足 RFC-005 §3.4「Agent 级 lifecycle」默认形态。
    """

    def __init__(self) -> None:
        self._store: Dict[Tuple[str, str], Tuple[Executor, int]] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, conv_id: str, executor: Executor) -> Executor:
        async with self._lock:
            key = (conv_id, executor.executor_id)
            entry = self._store.get(key)
            if entry is not None:
                ex, count = entry
                self._store[key] = (ex, count + 1)
                return ex
            # 首次:prepare 并登记
            await executor.prepare()
            self._store[key] = (executor, 1)
            return executor

    async def release(
        self, conv_id: str, executor_id: str, reason: ReleaseReason
    ) -> None:
        """逐 capability 释放单条引用(计数 -1,归零才 release)。"""
        to_release: Optional[Executor] = None
        async with self._lock:
            key = (conv_id, executor_id)
            entry = self._store.get(key)
            if entry is None:
                return  # 幂等:未 acquire
            ex, count = entry
            new_count = count - 1
            if new_count <= 0:
                self._store.pop(key, None)
                to_release = ex
            else:
                self._store[key] = (ex, new_count)
        if to_release is not None:
            try:
                await to_release.release(reason)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"executor {executor_id} release failed: {e}")

    async def release_session(self, conv_id: str, reason: ReleaseReason) -> None:
        """释放某会话持有的【所有】 executor 引用(会话终结,全部归零)。

        与 ``release`` 的区别:``release`` 逐 capability 减 1(单条 acquire→单条 release);
        ``release_session`` 在会话终结时把该会话每个 executor 的引用全部清零并 release——
        因为会话消失后,持有引用的 capability 也不复存在。
        """
        to_release: List[Executor] = []
        async with self._lock:
            for key in list(self._store.keys()):
                if key[0] != conv_id:
                    continue
                ex, _count = self._store.pop(key)
                to_release.append(ex)
        # 锁外 release(避免长 I/O 持锁)
        for ex in to_release:
            try:
                await ex.release(reason)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"executor {ex.executor_id} release failed: {e}")

    def get(self, conv_id: str, executor_id: str) -> Optional[Executor]:
        entry = self._store.get((conv_id, executor_id))
        return entry[0] if entry else None