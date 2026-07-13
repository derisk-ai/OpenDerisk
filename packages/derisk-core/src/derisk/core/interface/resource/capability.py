"""Capability —— 自管理资源对象协议(RFC-006)。

一个 Capability 对象**同时**承担输入投影(declare/consume)与执行投影
(prepare/execute/release/fetch),自己持有 live 实例、管生命周期、管使用。
这把 RFC-005 当初拆成 `ResourceProtocol`(declare)与 `Executor`(execute)两个
对象的"双轨"收成一轨:一种资源 = 一个对象,可被读完一个类即理解其全貌。

设计取舍:
- **不继承** `ResourceProtocol`/`Executor`。二者对 `declare`/`requires` 用了
  classmethod 形态(纯函数、可缓存),而 Capability 需要 `self`(持有实例)。
  直接继承会冲突。故 Capability 是独立 ABC,由 facade 的适配器(pacade.py
  `_CapabilityDeclareAdapter`/`_CapabilityExecutorAdapter`)鸭子类型接入现有
  `_declare_one`/`_prepare_executors`/`_resolve_data_requirements` 编排骨架,
  不重写编排。

- **executor_id 默认 = capability_id**。资源能力 1:1 自管理。例外:跨能力共享
  底座(sandbox)是独立 `Executor`(非 Capability),经 `requires()` 引用——
  见 `sandbox/executor.py`。

- **declare 保持纯函数**:需 I/O 的数据(schema 表列表等)走 `DataRequirement`
  占位 + `fetch` 回填,保证 config_hash 静态快照缓存不被 prepare 击穿。

- **prepare 时序在 declare 之前**:facade 先拓扑 `prepare`(建 live 实例),
  再 `declare`(读实例 / 发占位),再 `fetch`(用实例取数据)。`requires` 描述
  对共享 executor 的依赖,供拓扑排序。

生命周期:Agent 级引用计数(一会话一份连接/连接池被多轮复用;首个 requires
者触发 prepare,引用归零 release)。见 `InMemoryExecutorRegistry.acquire/release`。

新增一种资源 = 新建一个类实现本 ABC + 在 capability 目录 `register_capability`
注册,零改框架。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from derisk.core.interface.resource.bundle import Contribution
from derisk.core.interface.resource.data_requirement import DataRequirement
from derisk.core.interface.resource.executor import (
    ExecutorCall,
    ExecutorStatus,
    ReleaseReason,
)


class Capability(ABC):
    """自管理资源能力:输入投影 + 生命周期 + 执行投影 合一。

    子类需实现:`capability_id`、`declare`、`prepare`、`execute`、`release`。
    可选覆盖:`executor_id`(默认同 capability_id)、`requires`(默认
    `[self.executor_id]`)、`fetch`(默认 NotImplementedError)、`consume`(默认 `[]`)。
    """

    capability_id: str
    protocol_version: int = 1

    @property
    def executor_id(self) -> str:
        """执行投影身份,默认同 capability_id。

        仅共享底座(如 sandbox)或一能力多实例时需覆盖。资源能力保持 1:1。
        """
        return self.capability_id

    # ----------------------------- 输入投影(纯函数) ---------------------- #
    @abstractmethod
    def declare(self, config: Any = None) -> List[Contribution]:
        """声明面【纯函数,无 I/O】。

        产配置态文本(库/skill/app 元数据)+ SYSTEM/TOOLS 槽 Contribution。
        需外部数据(如 DB 表列表)时,Contribution.content 带 DataRequirement
        占位,由 `fetch` 回填。禁止在此直接调 I/O(会击穿 config_hash 快照缓存)。
        """

    def requires(self, config: Any = None) -> List[str]:
        """依赖哪些 executor_id(共享底座,如 sandbox)。默认自身。

        资源能力默认自管理,返回自身 executor_id;需共享底座时追加,如
        `["sandbox"]`(并覆盖 `executor_id` 不冲突时)。facade 据此拓扑 sort prepare。
        """
        return [self.executor_id]

    async def consume(self, call_result: Any) -> List[Contribution]:
        """【可选】消费面:工具执行后反改输入(RAG 回注/多模态等)。默认空。"""
        return []

    # ----------------------------- 生命周期(I/O) ------------------------- #
    @abstractmethod
    async def prepare(self) -> None:
        """建 live 实例(连接/service/沙箱就绪)。幂等:重复调不重建。

        这是旧 `Resource.__init__` 里建连接/service 的活迁来之处。facade 在
        `declare` 之前先拓扑 `prepare`。实例 Agent 级引用计数复用。
        """

    @abstractmethod
    async def execute(self, call: ExecutorCall) -> Any:
        """执行工具调用,用 `self` 持有的 live 实例。前置 status==READY。

        `call.tool_name` 标识本能力暴露的哪个工具(如 execute_sql /
        knowledge_search / read_skill),按之分派到具体执行体。返回值交 facade
        侧统一 normalize(via ToolDispatcher Route B → ToolAction._execute_tool)。
        """

    @abstractmethod
    async def release(self, reason: ReleaseReason) -> None:
        """拆 live 实例/还连接。幂等。引用计数归零时由 registry 触发。"""

    async def fetch(self, requirement: DataRequirement) -> Any:
        """【可选】填 `declare` 产的 DataRequirement 占位,用 live 实例取数据。

        返回 str(文本)或可 str() 的数据,facade 用其重建 Contribution.content
        替换占位。无 I/O 需求的能力不实现(默认 NotImplementedError)。
        """
        raise NotImplementedError(
            f"capability {self.capability_id} does not support fetch"
        )

    # ----------------------------- 自描述(辅助) -------------------------- #
    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<Capability {self.capability_id}>"


class CapabilityPack:
    """自管理 Capability 的容器(供 facade._iter_sub_resources 遍历)。

    与旧 ``ResourcePack`` 同形状(``is_pack``/``sub_resources``),使 facade
    ``_iter_sub_resources`` 无需区分新旧 pack。sub_resources 是一批已构造好的
    ``Capability`` 对象——它们由构造期(agent_chat)用 factory map 从 AgentResource
    config 产出,绑给 agent;Agent 只持有对象,不再持有 config。

    过渡期:agent 可同时持有旧 ``ResourcePack``(self.resource,供 Stage 8 前的
    resource_map 消费)与新 ``CapabilityPack``(优先供 facade.assemble 消费)。
    """

    def __init__(self, capabilities: List["Capability"] | None = None):
        self._capabilities: List["Capability"] = list(capabilities or [])

    @property
    def is_pack(self) -> bool:
        return True

    @property
    def sub_resources(self) -> List["Capability"]:
        return self._capabilities

    def add(self, capability: "Capability") -> None:
        self._capabilities.append(capability)

    async def preload_resource(self) -> None:
        """eager load:遍历 sub Capability 调 prepare(agent init 期,对齐旧
        ResourcePack.preload_resource 时机)。MCP 等连外部 server 的能力在此建连接,
        而非延后到 facade.assemble。prepare 需幂等(已 READY 则跳过)。
        """
        import asyncio

        async def _prep(cap):
            try:
                await cap.prepare()
            except Exception as e:  # noqa: BLE001
                # 单能力 prepare 失败不阻塞其它(对齐旧 ResourcePack 容错)
                import logging

                logging.getLogger(__name__).warning(
                    f"[CapabilityPack] prepare {getattr(cap, 'capability_id', '?')} failed: {e}"
                )

        await asyncio.gather(*[_prep(c) for c in self._capabilities], return_exceptions=False)

    def get(self, capability_id_prefix: str) -> Optional["Capability"]:
        """按 capability_id 前缀查首个 Capability(供 _check_have_resource 等消费者取实例)。"""
        for c in self._capabilities:
            cid = getattr(c, "capability_id", "")
            if cid and cid.startswith(capability_id_prefix):
                return c
        return None

    def get_all(self, capability_id_prefix: str) -> List["Capability"]:
        """按 capability_id 前缀查全部 Capability(多实例,如多 DB/Knowledge)。"""
        return [
            c
            for c in self._capabilities
            if getattr(c, "capability_id", "").startswith(capability_id_prefix)
        ]


__all__ = [
    "Capability",
    "CapabilityPack",
    "ExecutorCall",
    "ExecutorStatus",
    "ReleaseReason",
    "DataRequirement",
    "Contribution",
]