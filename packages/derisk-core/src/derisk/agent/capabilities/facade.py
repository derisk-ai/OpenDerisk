"""ResourceFacade —— 协议层编排,产出 AgentInputsSnapshot(RFC-005 §3.6 / S9)。

协议对外锚点。独立于 v1/v2,两套架构共同消费快照。编排:

    List[AgentResource](配置态)
      → ResourceManager.a_build_resource  --- 资源实例化(复用现有入口)
      → 遍历资源:旧 Resource 子类经 _legacy_wrappers 包成 ResourceProtocol,
        均走原生 declare(无 LegacyResourceAdapter 桥接,已移除)
      → 收集 requires + topological_prepare executor
      → 叠加会话/轮次运行态(SESSION/TURN)
      → freeze → AgentInputsSnapshot(不可变,可缓存/序列化/跨进程)
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    FrozenBundle,
    InputBundle,
    Lifetime,
    SCOPE_PRIORITY,
    Slot,
    SystemBlock,
)
from derisk.core.interface.resource.capability import Capability
from derisk.core.interface.resource.tool_entry import (
    BUILTIN_EXECUTOR_ID,
    ToolEntry,
)
from derisk.core.interface.resource.executor import (
    Executor,
    ExecutorRegistry,
    ExecutorStatus,
    InMemoryExecutorRegistry,
    ReleaseReason,
    topological_prepare,
)
from derisk.core.interface.resource.protocol import ResourceProtocol

# Executor工厂映射:executor_id → Executor 实例(由接入层提供)
ExecutorProvider = Dict[str, Executor]

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 配置哈希(缓存失效键)
# --------------------------------------------------------------------------- #
def compute_config_hash(agent_resources: List[Any]) -> str:
    """对配置态资源列表取稳定 hash(缓存失效键)。

    输入是 AgentResource(配置态),只看 type/value/name/version 等稳定字段。
    """
    if not agent_resources:
        return "empty"
    try:
        payload = [
            {
                "type": getattr(r, "type", None),
                "value": getattr(r, "value", None),
                "name": getattr(r, "name", None),
                "version": getattr(r, "version", None),
            }
            for r in agent_resources
        ]
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"compute_config_hash failed: {e}")
        return "fallback"


# --------------------------------------------------------------------------- #
# Facade
# --------------------------------------------------------------------------- #
class ResourceFacade:
    """协议层门面。组装 AgentInputsSnapshot,缓存静态部分,叠加运行态。

    用法::

        facade = ResourceFacade(registry=InMemoryExecutorRegistry())
        snapshot = await facade.assemble(
            agent_id="a1", conv_id="c1", agent_resources=cfg,
            resource_root=agent.resource, agent=agent,
        )
        # v1/v2 消费 snapshot:frozen.system / .tools / .user_parts
    """

    def __init__(
        self,
        registry: Optional[ExecutorRegistry] = None,
        snapshot_cache: Optional[Dict[Tuple[str, str], FrozenBundle]] = None,
        executor_provider: Optional[ExecutorProvider] = None,
    ):
        self.registry = registry or InMemoryExecutorRegistry()
        # 静态快照缓存:(agent_id, config_hash) → FrozenBundle
        self._snapshot_cache: Dict[Tuple[str, str], FrozenBundle] = (
            snapshot_cache if snapshot_cache is not None else {}
        )
        # 会话级运行态:(conv_id) → List[Contribution](SESSION lifetime)
        self._session_store: Dict[str, List[Contribution]] = {}
        # 每 config 的 required executor ids 缓存(供静态快照命中时复用)
        self._requires_cache: Dict[Tuple[str, str], List[str]] = {}
        # executor 工厂(executor_id → Executor),由接入层提供。沙箱/DB 连接器等
        # 在此注册。无则跳过 executor 链路(纯协议层、无执行投影时)。
        self.executor_provider: ExecutorProvider = executor_provider or {}
        # 双轨迁移:旧 Resource 子类 → capability 包装映射(Step B+ 机制)。
        # key=旧 Resource 类(or isinstance-able),value=wrapper 工厂(旧实例 → ResourceProtocol)。
        # capability 目录 register() 时注册,使 facade 遍历 ResourcePack 子资源时
        # 自动把旧 Resource 包成对应 capability 的 ResourceProtocol 走原生 declare。
        self._legacy_wrappers: Dict[Any, Any] = {}
        # RFC-006:自管理 Capability 工厂注册表。type_key(AgentResource.type)→
        # factory(value:dict, system_app) -> Capability。各 capability 目录
        # `register_capability(facade)` 时注册,使 facade 能直接从 AgentResource
        # 配置构造 Capability(不经旧 Resource 子类 + wrapper)。
        self._capability_factories: Dict[str, Callable[[dict, Any], Capability]] = {}
        # RFC-006 Stage 4.5:过渡期"旧 Resource 实例 → 自管理 Capability"工厂。
        # key=类 or 谓词(识别旧实例),value=factory(legacy_instance)→Capability。
        # _to_resource_protocol 优先于 _legacy_wrappers 匹配:旧实例仍由 ResourceManager
        # 构造(不动),但 facade 遍历时翻成真正的 Capability 对象(经适配器接入
        # declare/prepare/execute),修复旧 wrapper 的 declare 空桩问题。Stage 9 旧类
        # 退役后改用 _capability_factories 从 config 直接产,本表随之删除。
        self._legacy_capability_providers: Dict[Any, Callable[[Any], Capability]] = {}

    def register_capability_factory(
        self, type_key: str, factory: Callable[[dict, Any], Capability]
    ) -> None:
        """注册 type_key → Capability 工厂(RFC-006 自管理能力构造入口)。

        factory(value: dict, system_app) -> Capability。facade 遇此 type_key 的
        AgentResource 时直接调 factory 产 Capability,跳过旧 Resource 子类构造。
        与 `_legacy_wrappers` 并存(过渡期);新路径优先,无 factory 才回退 wrapper。
        """
        self._capability_factories[type_key] = factory

    def register_legacy_capability_provider(
        self, key: Any, factory: Callable[[Any], Capability]
    ) -> None:
        """注册旧 Resource 实例 → 自管理 Capability 工厂(过渡期,Stage 4.5)。

        key 同 register_legacy_wrapper:类(isinstance)或谓词 callable(sub)->bool。
        factory(legacy_instance) -> Capability。_to_resource_protocol 优先于此
        匹配(先于 _legacy_wrappers),使旧实例被翻成 Capability 而非旧 ResourceProtocol
        包装(declare 空桩)。Stage 9 旧类退役时删除,改走 _capability_factories(config)。
        """
        self._legacy_capability_providers[key] = factory

    def register_legacy_wrapper(self, key: Any, wrapper_factory: Any) -> None:
        """注册旧 Resource 子类 → capability 包装工厂(双轨迁移,纯 core)。

        key 可为:
        - 类(用 isinstance 判定):需 import 该类;serve 层用。
        - 谓词 callable(sub)->bool(纯属性判断):core 层用,不 import 上层类,
          避免分层倒置(core→serve 反向依赖)。
        wrapper_factory(legacy_instance) -> ResourceProtocol 实例。

        facade 遍历 ResourcePack 子资源时,命中 key 的旧实例调 factory 包成
        新 capability 走原生 declare,脱离 legacy 桥接。
        首个命中的 key 胜出(注册顺序即优先级)。
        """
        list(self._legacy_wrappers.keys())  # noqa: 触发惰性(确保存在)
        self._legacy_wrappers[key] = wrapper_factory

    def _to_resource_protocol(self, sub: Any) -> Optional[ResourceProtocol]:
        """把 ResourcePack 子资源转成 ResourceProtocol:本身是则直接返;
        Capability 则适配成 declare 面(并副作用注入 executor 面);
        否则查 _legacy_wrappers 找包装(类或谓词);都无返 None。"""
        if isinstance(sub, ResourceProtocol):
            return sub
        if isinstance(sub, Capability):
            # RFC-006:Capability 自管理 —— 注入执行面到 provider,返 declare 适配器。
            # 执行面(proto_id=cap.executor_id)供 _prepare_executors/_resolve_data_requirements
            # 经 executor_provider 查取;declare 面(适配为 ResourceProtocol)供 _declare_one 调用。
            if sub.executor_id not in self.executor_provider:
                self.executor_provider[sub.executor_id] = _CapabilityExecutorAdapter(sub)
            return _CapabilityDeclareAdapter(sub)
        # Stage 4.5:优先把旧 Resource 实例翻成自管理 Capability(经适配器接入 declare/
        # prepare/execute),修复旧 wrapper declare 空桩。匹配先于 _legacy_wrappers。
        for key, factory in self._legacy_capability_providers.items():
            if callable(key) and not isinstance(key, type):
                try:
                    if key(sub):
                        cap = factory(sub)
                        if isinstance(cap, Capability):
                            if cap.executor_id not in self.executor_provider:
                                self.executor_provider[cap.executor_id] = (
                                    _CapabilityExecutorAdapter(cap)
                                )
                            return _CapabilityDeclareAdapter(cap)
                except Exception:  # noqa: BLE001
                    continue
            else:
                try:
                    if isinstance(sub, key):
                        cap = factory(sub)
                        if isinstance(cap, Capability):
                            if cap.executor_id not in self.executor_provider:
                                self.executor_provider[cap.executor_id] = (
                                    _CapabilityExecutorAdapter(cap)
                                )
                            return _CapabilityDeclareAdapter(cap)
                except TypeError:
                    continue
        for key, factory in self._legacy_wrappers.items():
            if callable(key) and not isinstance(key, type):
                # 谓词:key(sub) -> bool,纯属性判断,不 import 上层类
                try:
                    if key(sub):
                        return factory(sub)
                except Exception:  # noqa: BLE001
                    continue
            else:
                # 类:isinstance 判定(serve 层注册的具体 Resource 类)
                try:
                    if isinstance(sub, key):
                        return factory(sub)
                except TypeError:
                    continue
        return None

    # ----------------------------- 主入口 ----------------------------------- #
    async def assemble(
        self,
        *,
        agent_id: str,
        conv_id: str,
        agent_resources: Optional[List[Any]] = None,
        resource_root: Optional[Any] = None,
        agent: Optional[Any] = None,
        turn_user_parts: Optional[List[Contribution]] = None,
        identity: Optional[str] = None,
        control_block: Optional[str] = None,
        memory_static_block: Optional[str] = None,
        builtin_tools: Optional[Dict[str, Any]] = None,
        extra_static_contribs: Optional[List[Contribution]] = None,
        extra_tools: Optional[List[ToolEntry]] = None,
    ) -> "AgentInputsSnapshot":
        """组装本轮输入快照。

        路线B:facade 产完整 system 快照(身份+控制层进静态快照;资源层 declare;
        静态记忆层会话级叠加)。

        Args:
            agent_id: Agent 标识(缓存键)。
            conv_id: 会话标识(SESSION 运行态键)。
            agent_resources: 配置态 List[AgentResource],用于决定 config_hash。
            resource_root: 已 build 的 Resource(Pack);None 则用 agent.resource。
            agent: v1 agent(构建 ResourceContext;桥接需要)。
            turn_user_parts: 本轮 user 输入(TURN 级 Contribution)。
            identity: 身份层渲染后文本(GLOBAL,跨用户通用)。
            control_block: 控制层渲染后文本(GLOBAL,workflow/exceptions/delivery)。
            memory_static_block: 静态记忆层文本(USER 会话级,profile/preference)。
            builtin_tools: Agent 自带工具 {name: tool},统一进快照 TOOLS 槽作
                ToolEntry(executor_id=agent:builtin)。可能动态(如历史回顾工具在
                首次压缩后注入),故不进静态快照缓存,作 snapshot 透传字段。
            extra_static_contribs: 非 ResourcePack 的 capability 资源(沙箱 env 等)
                的 SYSTEM Contribution,透传不进缓存。
            extra_tools: 运行时归某 capability 的 ToolEntry(如沙箱委托类工具)。

        Returns:
            AgentInputsSnapshot:含 frozen(静态 system:身份+控制+资源)+ 会话级记忆
                + user_parts + builtin_tools + extra。
        """
        config_hash = compute_config_hash(agent_resources or [])

        # 1. 静态快照(命中即复用),同时缓存 required executor ids
        #    身份/控制层随 agent 模板稳定 → 进静态快照缓存键的一部分。
        layer_hash = (config_hash, _hash_optional(identity), _hash_optional(control_block))
        cache_key = (agent_id, layer_hash)
        frozen = self._snapshot_cache.get(cache_key)
        if frozen is None:
            bundle, required_ids, built_ready = await self._build_static_bundle(
                agent=agent, resource_root=resource_root, agent_id=agent_id,
                conv_id=conv_id, identity=identity, control_block=control_block,
            )
            frozen = bundle.freeze(config_hash=config_hash)
            self._snapshot_cache[cache_key] = frozen
            self._requires_cache[cache_key] = required_ids
            executors_ready = built_ready
        else:
            required_ids = self._requires_cache.get(cache_key, [])
            executors_ready = await self._prepare_executors(
                conv_id=conv_id, required_ids=required_ids
            )

        # 2. 静态记忆层(会话级,USER,进 system 但不进缓存键)
        memory_block = None
        if memory_static_block and memory_static_block.strip():
            memory_block = memory_static_block.strip()

        # 3. 叠加 SESSION 运行态(本轮不写入快照,仅透传)
        session_contribs = list(self._session_store.get(conv_id, []))

        # 4. 本轮 TURN user_parts
        turn = list(turn_user_parts or [])

        # 5. builtin tools(Agent 自带,统一进 TOOLS 槽;动态故不进缓存,透传)
        builtin_entries: List[ToolEntry] = []
        for name, tool in (builtin_tools or {}).items():
            builtin_entries.append(
                ToolEntry(
                    tool_name=name,
                    tool=tool,
                    capability_id="agent:builtin",
                    executor_id=BUILTIN_EXECUTOR_ID,
                    description=getattr(tool, "description", "") or "",
                )
            )

        # 6. extra system contribs(沙箱 env 等非 ResourcePack 的 capability 资源,
        #    SESSION/USER-ENV 性质,透传不进缓存)
        extra_system = tuple(extra_static_contribs or [])

        # 7. extra tools(沙箱委托类工具等,运行时归 sandbox 能力的 ToolEntry)
        extra_tool_entries = tuple(extra_tools or [])

        return AgentInputsSnapshot(
            frozen=frozen,
            memory_static_block=memory_block,
            extra_system_contribs=extra_system,
            extra_tools=extra_tool_entries,
            session_user_parts=tuple(session_contribs),
            turn_user_parts=tuple(turn),
            builtin_tools=tuple(builtin_entries),
            config_hash=config_hash,
            executors_ready=executors_ready,
        )

    # ----------------------- 静态 bundle 构建 -------------------------------- #
    async def _build_static_bundle(
        self,
        *,
        agent: Optional[Any],
        resource_root: Optional[Any],
        agent_id: str,
        conv_id: str,
        identity: Optional[str] = None,
        control_block: Optional[str] = None,
    ) -> Tuple[InputBundle, List[str], bool]:
        """构建静态 InputBundle + 准备 executor。

        返回 (bundle, required_executor_ids, executors_ready)。
        """
        bundle = InputBundle()
        # RFC-006 Phase C:root 优先 agent.capability_pack(自管理 Capability 对象);
        # fallback 旧 agent.resource(双轨过渡,Phase D 旧类退役后 resource 消亡)。
        # resource_root 显式传入时最优先(测试/特殊场景)。
        if resource_root is not None:
            root = resource_root
        elif agent is not None:
            cap_pack = getattr(agent, "capability_pack", None)
            root = cap_pack if cap_pack is not None else getattr(agent, "resource", None)
        else:
            root = None

        # L1 身份层 + L3 控制层(GLOBAL,跨用户通用)
        if identity:
            bundle.add(
                Contribution(
                    capability_id=f"{agent_id}:identity",
                    slot=Slot.SYSTEM,
                    content=identity,
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.GLOBAL,
                    order=0,
                )
            )
        if control_block:
            bundle.add(
                Contribution(
                    capability_id=f"{agent_id}:control",
                    slot=Slot.SYSTEM,
                    content=control_block,
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.GLOBAL,
                    order=100,
                )
            )

        # L2 资源层(RFC-006 时序:适配 → requires → acquire(prepare) → declare → fetch)。
        #   prepare 先于 declare:使 Knowledge/MCP/Skill 这类 declare 依赖 prepare I/O
        #   产出(spaces/tools 元数据)的能力自管理——旧 __init__ 的 hydrate/preload I/O
        #   挪到 prepare,declare 读 prepared 实例。requires 是静态(capability_id/config
        #   派生)故前置收集。缓存语义不变:frozen 缓存 declare 产出(prepared 后 stable),
        #   命中时复用 frozen 不重跑 prepare/declare。
        required_executor_ids: list = []
        executors_ready = True
        if root is not None:
            subs: List[ResourceProtocol] = []
            for sub in _iter_sub_resources(root):
                wrapped = self._to_resource_protocol(sub)
                if wrapped is not None:
                    subs.append(wrapped)
            if subs:
                # 1) 前置收集 requires(静态,不需 prepare)。
                for s in subs:
                    try:
                        reqs = s.requires(getattr(s, "_config", None))
                        if inspect.isawaitable(reqs):
                            reqs = await reqs
                        required_executor_ids.extend(list(reqs))
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"resource requires() failed: {e}")
                # 2) acquire → prepare(实例就位)。
                executors_ready = await self._prepare_executors(
                    conv_id=conv_id, required_ids=required_executor_ids
                )
                # 3) declare(此时 Capability 实例已 prepared,declare 读 self._spaces 等)。
                results = await asyncio.gather(
                    *[
                        self._declare_one(s, getattr(s, "_config", None))
                        for s in subs
                    ],
                    return_exceptions=False,
                )
                for (contribs, _reqs) in results:
                    if contribs is None:
                        continue
                    bundle.extend(contribs)
        # 无子资源 / 全部 declare 为空 → 资源层即为空(无 LegacyResourceAdapter 桥接)。
        # WorkflowResource/ReasoningEngineResource 无 wrapper 但不出现在部署资源包中,
        # 普通无资源 agent 亦应得到空资源层而非旧桥接。

        # executor 链路已在上方 prepare(时序前置)。

        # 数据需求回填(Step A):扫描 declare 产出中 content 为 DataRequirement 的
        # Contribution,调对应 executor.fetch 预取,用结果重建 Contribution 替换占位。
        await self._resolve_data_requirements(bundle, conv_id=conv_id)

        return bundle, required_executor_ids, executors_ready

    async def _resolve_data_requirements(self, bundle: InputBundle, *, conv_id: str) -> None:
        """扫描 system/tools 槽中 content 为 DataRequirement 的 Contribution,
        并行调对应 executor.fetch 预取回填,用新 Contribution 替换(Contribution frozen,
        故重建)。失败则跳过(保留占位)。多 DataRequirement 并行 fetch,不串行阻塞。
        """
        from derisk.core.interface.resource.data_requirement import DataRequirement

        async def _resolve_slot(slot_name: str) -> None:
            src = getattr(bundle, slot_name)
            if not src:
                return
            # 收集需 fetch 的 (index, contribution) 并行单元
            fetch_tasks = []
            pending: List[Tuple[int, Contribution]] = []
            for idx, c in enumerate(src):
                if isinstance(c.content, DataRequirement):
                    ex = self.executor_provider.get(c.content.executor_id)
                    if ex is None:
                        continue  # 无 executor,保留占位
                    pending.append((idx, c))
                    fetch_tasks.append(self._fetch_one(ex, c.content))

            if not pending:
                return
            # 并行 fetch(不阻塞事件循环,各 executor 内部 I/O 应已异步化)
            results = await asyncio.gather(*fetch_tasks, return_exceptions=False)

            # 用结果重建 slot 列表(替换占位)
            new_list: List[Contribution] = list(src)
            for (idx, c), result in zip(pending, results):
                if result is None:
                    continue  # fetch 失败已记日志,保留占位
                rendered = result if isinstance(result, str) else str(result)
                new_list[idx] = Contribution(
                    capability_id=c.capability_id,
                    slot=c.slot,
                    content=rendered,
                    lifetime=c.lifetime,
                    cache_scope=c.cache_scope,
                    order=c.order,
                )
            setattr(bundle, slot_name, new_list)

        await asyncio.gather(_resolve_slot("system"), _resolve_slot("tools"))

    @staticmethod
    async def _fetch_one(executor: Any, requirement: Any) -> Any:
        """并行 fetch 单元:失败返 None(占位保留),成功返 fetch 结果。"""
        try:
            return await executor.fetch(requirement)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"fetch failed for {requirement.kind} "
                f"(executor={requirement.executor_id}): {e}"
            )
            return None

    async def _prepare_executors(
        self, *, conv_id: str, required_ids: List[str]
    ) -> bool:
        """准备 requires 声明的 executor(S5)。"""
        if not required_ids:
            return True
        ready = True
        for eid in dict.fromkeys(required_ids):  # 去重保序
            ex = self.executor_provider.get(eid)
            if ex is None:
                logger.debug(f"executor {eid} not in provider, skip prepare")
                continue
            try:
                await self.registry.acquire(conv_id, ex)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"executor {eid} acquire failed: {e}")
                ready = False
        return ready

    @staticmethod
    async def _declare_one(
        resource: ResourceProtocol, config: Any
    ) -> Tuple[Optional[List[Contribution]], List[str]]:
        """并行单元:声明一个资源,返回 (contributions, required_executor_ids)。

        失败返回 (None, []),不抛——已在 gather 调用方跳过。
        兼容同步 declare(返回 list)与异步 declare(返回 awaitable)。
        """
        cap = getattr(resource, "capability_id", resource)
        try:
            contribs = resource.declare(config)
            if inspect.isawaitable(contribs):
                contribs = await contribs
            reqs = resource.requires(config)
            if inspect.isawaitable(reqs):
                reqs = await reqs
            return list(contribs), list(reqs)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"resource {cap} declare failed, fallback to legacy: {e}"
            )
            return None, []

    # --------------------------- 运行态写入 --------------------------------- #
    def add_session_part(self, conv_id: str, contribution: Contribution) -> None:
        """写入会话级运行态(多模态加载等 SESSION Contribution)。"""
        if contribution.lifetime != Lifetime.SESSION:
            raise ValueError(
                f"add_session_part requires SESSION lifetime, got {contribution.lifetime}"
            )
        self._session_store.setdefault(conv_id, []).append(contribution)

    async def end_session(self, conv_id: str) -> None:
        """会话结束:清会话运行态 + release 该会话 executor 引用(SESSION_END)。"""
        self._session_store.pop(conv_id, None)
        await self.registry.release_session(conv_id, ReleaseReason.SESSION_END)

    def invalidate_config(self, agent_id: str, config_hash: Optional[str] = None) -> None:
        """配置变更:失效静态快照缓存。"""
        if config_hash is None:
            self._snapshot_cache = {
                k: v for k, v in self._snapshot_cache.items() if k[0] != agent_id
            }
            self._requires_cache = {
                k: v for k, v in self._requires_cache.items() if k[0] != agent_id
            }
            return
        to_drop = [
            k for k in self._snapshot_cache
            if k[0] == agent_id and k[1][0] == config_hash
        ]
        for k in to_drop:
            self._snapshot_cache.pop(k, None)
            self._requires_cache.pop(k, None)


# --------------------------------------------------------------------------- #
# AgentInputsSnapshot(协议对外锚点,§3.6)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AgentInputsSnapshot:
    """不可变输入快照。v1/v2 共同消费的纯数据契约。

    - frozen: 静态(system[身份+控制+资源] + 资源工具)+ 已 freeze,可缓存。
    - builtin_tools: Agent 自带工具(ToolEntry,动态透传不进缓存)。
    - extra_tools: 运行时归某 capability 的 ToolEntry(如沙箱委托类工具)。
    - memory_static_block: 静态记忆层(USER 会话级,透传不进缓存键)。
    - extra_system_contribs: 非 ResourcePack 资源的 SYSTEM Contribution(沙箱 env)。
    - session_user_parts: 会话级运行态(SESSION,如加载的图片)。
    - turn_user_parts: 本轮 user 输入(TURN,如 RAG inline)。
    """

    frozen: FrozenBundle
    builtin_tools: Tuple[ToolEntry, ...] = ()
    extra_tools: Tuple[ToolEntry, ...] = ()
    memory_static_block: Optional[str] = None
    extra_system_contribs: Tuple[Contribution, ...] = ()
    session_user_parts: Tuple[Contribution, ...] = ()
    turn_user_parts: Tuple[Contribution, ...] = ()
    config_hash: str = ""
    executors_ready: bool = False

    # --------------------------- 便利访问 ----------------------------------- #
    @property
    def system(self) -> FrozenBundle:
        """静态 system(身份+控制+资源),provider 消费。记忆层见 full_system_blocks。"""
        return self.frozen

    @property
    def tools(self) -> Tuple[Contribution, ...]:
        """【仅资源工具】frozen.tools。全部工具(含 builtin)见 all_tools()。"""
        return self.frozen.tools

    def all_tools(self) -> Tuple[Any, ...]:
        """全部工具,供:

        - function_calling_params 转 schema(provider 层)。
        - ToolDispatcher.dispatch 的 entries 参数(派发器兼容两种形态)。

        含:frozen.tools(资源工具)+ extra_tools(沙箱委托类,归 sandbox 能力)
        + builtin_tools(Agent 自带,如 spawn_agent/ask_user/Skill)。
        """
        return (
            tuple(self.frozen.tools)
            + tuple(self.extra_tools)
            + tuple(self.builtin_tools)
        )

    def sandbox_tools(self) -> Tuple[ToolEntry, ...]:
        """沙箱委托类工具(归 capability_id=sandbox)。"""
        return self.extra_tools

    def all_user_parts(self) -> Tuple[Contribution, ...]:
        """合并会话级 + 本轮 user 输出(供拼 user message)。"""
        return self.session_user_parts + self.turn_user_parts

    def full_system_blocks(
        self, *, with_memory: bool = True, with_extra: bool = True
    ) -> Tuple["SystemBlock", ...]:
        """完整 system 块列表(含记忆层 + extra env),按 cache_scope 优先级排序。

        顺序:GLOBAL(身份→控制)→ ENV(沙箱 env)→ USER(记忆→资源)。
        记忆/资源为 USER 块;沙箱 env 为 ENV 块(scope 优先级介于 GLOBAL 与 USER)。

        provider 用此列表组 Anthropic 数组式 system + cache_control(经
        to_anthropic_system),或降级合并 str(经 merge_to_str)。
        """
        blocks = list(self.frozen.system)

        if with_extra:
            for c in self.extra_system_contribs:
                blocks.append(
                    SystemBlock(
                        text=str(c.content) if not isinstance(c.content, str) else c.content,
                        cache_scope=c.cache_scope,
                    )
                )

        if with_memory and self.memory_static_block:
            memory_block = SystemBlock(
                text=self.memory_static_block, cache_scope=CacheScope.USER
            )
            first_user_idx = next(
                (i for i, b in enumerate(blocks) if b.cache_scope == CacheScope.USER),
                len(blocks),
            )
            blocks.insert(first_user_idx, memory_block)

        # 重排:GLOBAL → ENV → USER → NONE(scope 优先级稳定排序)
        blocks.sort(key=lambda b: SCOPE_PRIORITY[b.cache_scope])
        return tuple(blocks)


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #
def _iter_sub_resources(root: Any) -> List[Any]:
    """遍历 ResourcePack 的子资源(或单 Resource 自身)。"""
    if root is None:
        return []
    is_pack = getattr(root, "is_pack", False)
    if is_pack:
        try:
            return list(root.sub_resources)
        except Exception:  # noqa: BLE001
            return []
    return [root]


# --------------------------------------------------------------------------- #
# Capability 适配器(RFC-006)
# --------------------------------------------------------------------------- #
# Capability 不继承 ResourceProtocol/Executor(declare/requires 的 classmethod 形态
# 与需 self 的执行面冲突),故用这两个适配器鸭子类型介入 facade 现有编排:
#  - declare 面(_CapabilityDeclareAdapter)被 _declare_one 调用,产 Contribution + requires
#  - 执行面(_CapabilityExecutorAdapter)注入 executor_provider,被 _prepare_executors/
#    _resolve_data_requirements 取用(acquire/fetch),及 ToolDispatcher Route B 取用(execute)。
# 二者共享同一 Capability 实例(Capability 自己持有 live 实例)。

class _CapabilityDeclareAdapter(ResourceProtocol):
    """把 Capability 的 declare/requires/consume 适配成 ResourceProtocol(供 _declare_one)。"""

    def __init__(self, cap: Capability):
        self._cap = cap

    @property
    def capability_id(self) -> str:
        return self._cap.capability_id

    def declare(self, config: Any = None) -> List[Contribution]:
        return self._cap.declare(config)

    def requires(self, config: Any = None) -> List[str]:
        return self._cap.requires(config)

    async def consume(self, call_result: Any) -> List[Contribution]:
        return await self._cap.consume(call_result)


class _CapabilityExecutorAdapter(Executor):
    """把 Capability 的 prepare/execute/release/fetch 适配成 Executor(供 registry/provider)。"""

    def __init__(self, cap: Capability):
        self._cap = cap
        self._status = ExecutorStatus.UNINITIALIZED

    @property
    def executor_id(self) -> str:
        return self._cap.executor_id

    @property
    def status(self) -> ExecutorStatus:
        return self._status

    async def prepare(self) -> None:
        await self._cap.prepare()
        self._status = ExecutorStatus.READY

    async def execute(self, call: Any) -> Any:
        return await self._cap.execute(call)

    async def release(self, reason: ReleaseReason) -> None:
        await self._cap.release(reason)
        self._status = ExecutorStatus.RELEASED

    async def fetch(self, requirement: Any) -> Any:
        return await self._cap.fetch(requirement)


def _hash_optional(text: Optional[str]) -> str:
    """对可选文本取短 hash(用作缓存键的一部分)。None → 'none'。"""
    if not text:
        return "none"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]