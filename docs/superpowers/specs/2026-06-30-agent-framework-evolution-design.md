# Agent 框架演进设计：V2 Runtime

- 日期：2026-06-30
- 状态：设计已与用户逐节确认，待写入实施计划
- 作者：yhjun1026 + Claude
- 相关分支：feat/scenario-workspace-p0
- 关联文件：
  - `packages/derisk-core/src/derisk/agent/core/base_agent.py`（ConversableAgent 主循环）
  - `packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py`（BAIZE）
  - `packages/derisk-core/src/derisk/agent/expand/actions/agent_action.py`（AgentStart）
  - `packages/derisk-core/src/derisk/agent/core/memory/gpts/gpts_memory.py`（push_message / vis_messages）
  - `packages/derisk-core/src/derisk/agent/core/interaction_adapter.py`（InteractionAdapter）
  - `packages/derisk-core/src/derisk/agent/interaction/recovery_coordinator.py`（RecoveryCoordinator）
  - `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`（SSE 端点）

---

## 1. 背景与问题

当前 derisk-core 的 Agent 框架以 `ConversableAgent`（`base_agent.py:121`）为基类、以 BAIZE（`react_master_agent.py:118`，`ReActMasterAgent`）为主 Agent。调研发现架构"功能完整但机制割裂"，三个用户痛点不是缺能力，而是缺三件东西：**统一状态机、统一事件流、统一子 Agent 隔离模型**。

### 1.1 三个明确痛点

1. **对话任意点中断恢复**：现状只有 turn 级软中断（`base_agent.py:1258/1295` break step 循环）+ `RecoveryCoordinator`（`recovery_coordinator.py:34`）骨架，但 `StateStore` 默认 `MemoryStateStore`（纯 dict，进程重启即丢），且**没有 step 级中间状态保存**。
2. **同/异步 sub_agent 能力**：现状双轨割裂——同步 `AgentStart`（`agent_action.py:194`）共享 conv_id 和 gpts_memory、`sync` 参数声明但未读取（L225-231 vs L61）；异步走另一套 `AsyncTaskManager + CoreV1SubagentAdapter`（`react_master_agent.py:308-392`）。
3. **用户交互机制缺乏状态管控**：现状双轨——老 `ActionOutput.ask_user`（break 循环）+ 新 `InteractionAdapter`（`interaction_adapter.py:38`）。`check_tool_permission`（`base_agent.py:585`）是**声明式静态规则，没有自动串入 `act()` 流程**，各 Action 需自行集成。

### 1.2 割裂的具体证据

- **状态散落**：`Status` 枚举（`core/schema.py:29`）+ `received_message_state` dict（`base_agent.py:155`）+ `RuntimeContext.recovering`（L115）三处。
- **三套事件管道并存**：`push_context_event` → Operator 注册表（`base_agent.py:2867`）、`push_message` → per-conv `asyncio.Queue`（`gpts_memory.py:237`）、`HookManager.trigger`（`core/hook/manager.py:98`）。
- **子 Agent 双轨**：同步 `AgentStart` 共享上下文 + 异步 `AsyncTaskManager` 独立任务，两套 API。
- **中断恢复有骨架但不闭环**：`RecoveryCoordinator.create_checkpoint`（L57）快照很全但默认内存存储，无 step 级保存。
- **用户交互双轨且未串入**：老 `ActionOutput.ask_user` + 新 `InteractionAdapter`，`permission` 未自动串入 `act()`。

---

## 2. 横向对比

基于对 `/Users/tuyang/GitHub/hermes-agent` 和 `/Users/tuyang/GitHub/claude-code-open` 的调研：

| 维度 | derisk-core（现状） | Hermes | claude-code |
|---|---|---|---|
| 主循环 | `while` + `Status` 枚举隐式 | `while` + `IterationBudget` | `AsyncGenerator` `while(true)` |
| 显式状态机 | 否（散落三处） | 否 | 否（messages 数组承载） |
| Sub-agent | 同步共享上下文 + 异步 AsyncTaskManager（双轨割裂） | 同步阻塞 + 独立上下文，无异步 | 同步/异步二选一 + 独立上下文 + 可 resume |
| 中断恢复 | turn 级软中断 + RecoveryCoordinator（默认内存） | interrupt + `/resume` 重放 SessionDB | AbortController + JSONL append + `--resume` 重放 |
| 用户交互 | Action ask_user（老）+ InteractionAdapter（新，未串入 act） | callback 阻塞 + 静态规则 | `permission behavior=ask` + Promise 阻塞 + PermissionMode 状态机 |
| 事件流 | Operator 注册表 + per-conv Queue + HookManager 三管道 | 多 callback 分发 | AsyncGenerator 单一消费点 |

**结论**：claude-code 的"单一 AsyncGenerator + messages 承载状态 + Tool.checkPermissions + JSONL append + `--resume` 重放"模型最干净。derisk-core 不照搬 TS 实现，但借鉴其"统一抽象"理念。

---

## 3. 设计目标与演进姿态

### 3.1 目标

| 维度 | 目标 |
|---|---|
| 中断恢复 | 全场景：ask_user/工具授权等待期持久化 + 用户主动暂停续接 + 进程崩溃自动恢复 + 异步子 agent detach/resume |
| 子 Agent | 独立上下文 + 同/异步统一入口 + 异步可 detach/resume + 嵌套允许但受限 |
| 用户交互 | 完全统一：ask_user 和工具授权走同一套机制 + permission 自动串入 act() + 多 PermissionMode |

### 3.2 演进姿态：结构性重构 + 外围兼容

- **内核**（状态机/事件流/StateStore/子Agent/permission）按 claude-code 模型**一次性统一重构**
- **外围**（ConversableAgent 外壳/BAIZE 子系统/前端 SSE/App JSON 配置）通过适配层**保持兼容**
- 不是"新旧并存"——只有一个运行时内核，外围只是适配层

### 3.3 否决的方案

- **Big Bang 全量重构**：风险过高，会动 BAIZE `bind().build()` 链路 + 前端 SSE + App JSON。否决。
- **Strangler Fig 旁路新运行时**：双轨期长，迁移边界模糊，重蹈"老 ask_user + 新 InteractionAdapter"双轨覆辙。否决。

---

## 4. 方案选型：内核先行 + 外围适配

**实现路径**：内核（状态机 + 事件流 + StateStore + 子Agent + permission）一次性统一重构，`ConversableAgent` 外壳保留，`generate_reply` 内部改为调用新内核。BAIZE 的 `bind().build()` 链路保留，子系统通过适配层接入。老 Action 通过统一 permission 适配层接入，老 `ActionOutput.ask_user` 废弃。

**理由**：
- 内核统一根治割裂
- 外围兼容控制爆炸半径（BAIZE/前端/App 配置不动）
- 不是新旧并存——只有一个运行时内核，外围只是适配层
- 适配层是单向依赖：外围依赖内核，内核不依赖外围

---

## 5. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    外围（兼容层，保留现有）                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Conversable- │  │ BAIZE 子系统 │  │  前端 SSE    │      │
│  │ Agent 外壳   │  │ ContextEngine│  │  App JSON    │      │
│  │ (generate_   │  │ Kanban/WorkLog│ │  配置        │      │
│  │  reply)      │  │ Phase/SysEvt │  │              │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │ 适配层           │ 适配层           │ 适配层       │
└─────────┼─────────────────┼─────────────────┼──────────────┘
          │                 │                 │
┌─────────▼─────────────────▼─────────────────▼──────────────┐
│                    内核（V2 Runtime，新建）                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ StepState    │  │ EventStream  │  │ StateStore   │      │
│  │ Machine      │─▶│ (AsyncGen +  │─▶│ (Persistent  │      │
│  │              │  │  EventSourc.)│  │  DB/Redis)   │      │
│  └──────┬───────┘  └──────────────┘  └──────────────┘      │
│         │                                                   │
│  ┌──────▼───────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ SubAgent     │  │ Permission   │  │ Recovery     │      │
│  │ Runtime      │  │ Gate         │  │ Coordinator  │      │
│  │ (统一入口)   │  │ (PermissionMode)│ │(重放+崩溃检测)│     │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### 5.1 内核六件套

| 模块 | 职责 | 替代的现状 |
|---|---|---|
| **StepState Machine** | 显式状态枚举 `thinking/acting/observing/awaiting_user/awaiting_tool_permission/awaiting_sub_agent/done/failed`，每 step 有 state 字段，转换受状态机约束 | 替代散落的 `Status` + `received_message_state` + `RuntimeContext.recovering` |
| **EventStream** | `AsyncGenerator[StreamEvent]`，append-only，每 step 的 input + output 都进事件流（event sourcing） | 替代 Operator 注册表 + per-conv Queue + HookManager 三管道 |
| **StateStore** | 持久化（DB/Redis），存 step state + 上下文快照 + 子 agent transcript + interaction checkpoint | 替代默认 `MemoryStateStore` |
| **SubAgent Runtime** | 统一入口（合并 `agent_start` + `AsyncTaskManager`），独立 conv_id/messages/memory，`run_in_background` 字段，detach + resume | 替代双轨 |
| **Permission Gate** | 自动串入 `act()`，`PermissionMode` 状态机，统一 `InteractionRequest` | 替代双轨（老 `ActionOutput.ask_user` + 静态 `permission_ruleset`） |
| **Recovery Coordinator** | 崩溃检测（心跳/lease）+ 重放恢复 | 扩展 `RecoveryCoordinator` |

### 5.2 外围三件套

1. **ConversableAgent 外壳**：`bind().build()` 链路保留，`generate_reply` 内部改为调用 V2 Runtime
2. **BAIZE 子系统**：ContextEngine/Kanban/WorkLog/Phase/SystemEventManager 通过 `BAIZESubsystemAdapter` 接入
3. **前端 SSE + App JSON**：协议兼容，适配层把新 `StreamEvent` 转成老 SSE 格式；App JSON 配置不动

### 5.3 关键边界原则

- 内核**不知道** BAIZE 的存在——只提供六个抽象
- 外围**通过适配层**接入内核
- 适配层是**单向依赖**：外围依赖内核，内核不依赖外围

---

## 6. 数据/配置/渲染变化范围

### 6.1 数据结构：新增 + 聚合保留（不破坏老的）

| 类型 | 变化 | 说明 |
|---|---|---|
| `AgentMessage` | 保留，变为聚合视图 | 老的 AgentMessage 仍在，变成"由多个 StepEvent 聚合而成"的高层视图 |
| `StepEvent`（新） | 新增 | event sourcing 最小单元：`step_id/agent_id/state/input/output/seq/timestamp` |
| `StepState` 枚举（新） | 新增 | `thinking/acting/observing/awaiting_user/awaiting_tool_permission/awaiting_sub_agent/done/failed` |
| `AgentTranscript`（新） | 新增 | 子 agent 独立消息序列，用于 detach + resume |
| `InteractionRequest/Response/Status` | 保留扩展 | 协议不动，补充 `step_id` 关联 |
| `received_message_state` dict | 废弃 | 被 StepState 取代 |
| `Status` 枚举 | 部分废弃 | `INTERRUPTED` 被细化成 `awaiting_*` 状态 |
| `GptsMessageMemory` | 保留 | 持久化层不动，但增加 StepEvent 表 |

### 6.2 Agent 配置模型：基本不动

| 类型 | 变化 | 说明 |
|---|---|---|
| `GptsApp` JSON | 不动 | `main_orchestrator/manus/rca_openraca` 等配置文件零修改 |
| `ReactMasterAgent.bind().build()` 链路 | 保留 | BAIZE 子系统通过适配层接入新内核 |
| `AgentResource` / `resource_map` | 保留 | 资源声明模型不动 |
| `LongTermMemoryConfig` | 保留 | 长期记忆配置不动 |
| `V2RuntimeConfig`（新） | 新增 | 作为 `agent_context` 的一部分，含 StepState/EventStream/StateStore/SubAgent/Permission/Recovery 配置 |
| `PermissionMode` 字段（新） | 新增 | 在 `agent_context` 或 `ExtConfigHolder` 里，枚举 `default/plan/auto/bypass` |

### 6.3 渲染机制：后端统一，前端兼容

| 层 | 变化 | 说明 |
|---|---|---|
| 后端事件管道 | 统一 | 废弃 Operator 注册表 + per-conv `asyncio.Queue` 双管道，统一到 `EventStream`（AsyncGenerator yield） |
| `push_context_event` | 废弃 | 被 EventStream 取代 |
| `push_message` + `vis_messages()` | 废弃 | 被 EventStream 取代 |
| `HookManager` | 保留 | 长期记忆的 `turn_complete` hook 仍走 HookManager（数据层，不是渲染层） |
| 前端 SSE | 兼容 + 增量迁移 | SSE 适配层把新 `StreamEvent` 转成老 SSE 格式——前端零修改继续用；要更细粒度可增量迁移 |
| `agent_chat._chat_messages` SSE 端点 | 保留外壳 | 端点签名不动，内部从 `queue_iterator` 改为消费 `EventStream` |

### 6.4 前端不重构的验证

老渲染链路的输出由 `VisProtocolConverter` 决定（`GptVisConverter`/`DeriskVisConverter`/`DeriskIncrVisWindowConverter`/`DeriskIncrVisWindow3Converter`），这些 converter 是**独立的可复用组件**，不绑定 `push_message`/`vis_messages()`。新 EventStream 可以直接调用这些 converter 产出 VIS markdown。

老 SSE 协议共 10 种事件格式（`use-chat.ts:94-137` 判定路径）：`metadata` / `interrupt` / `error` / `workspace`×6（task_created/context_loaded/intervention_triggered/artifact_produced/delivery_sent/asset_referenced）/ `content` VIS markdown / `[DONE]` / raw error。新 EventStream 的 StreamEvent 适配层只要能产出这 10 种格式，前端零修改。

---

## 7. Step State Machine + Event Sourcing

### 7.1 StepState 状态机

```
INIT → THINKING → ACTING → OBSERVING ──┐
                                       │
                  ┌────────────────────┘
                  │
                  ├─ AWAITING_USER               (ask_user 挂起)
                  ├─ AWAITING_TOOL_PERMISSION    (工具授权挂起)
                  ├─ AWAITING_SUB_AGENT          (子 agent 挂起)
                  │
                  └─ DONE / FAILED
```

**关键**：每个 `AWAITING_*` 状态都是**可持久化挂起**的——进程重启后能从 StateStore 恢复到这个状态，等待外部输入续接。这是"任意点中断恢复"的语义基础。

### 7.2 StepEvent 数据结构

```python
@dataclass
class StepEvent:
    event_id: str               # UUID
    step_id: str                # 所属 step
    conv_id: str                # 会话
    agent_id: str               # 产出 agent
    parent_step_id: str | None  # 子 agent 场景的父 step
    state: StepState            # 当前状态
    event_type: str             # llm_token / tool_call / tool_result /
                                # interaction_request / interaction_response /
                                # sub_agent_start / sub_agent_result / ...
    input: dict                 # 事件输入
    output: dict                # 事件输出
    seq: int                    # 单调递增序列号（event sourcing 顺序）
    timestamp: float
```

**append-only**：一旦写入不可修改。一个 step 产出多个 StepEvent（thinking 阶段多个 `llm_token`，acting 阶段 `tool_call` + `tool_result`）。

### 7.3 EventStream（AsyncGenerator）

```python
async def run_step(agent, input_) -> AsyncGenerator[StepEvent, None]:
    step_id = uuid4()
    yield StepEvent(step_id=step_id, state=StepState.INIT, ...)

    # THINKING
    async for token in llm_stream(input_):
        yield StepEvent(step_id=step_id, state=StepState.THINKING,
                        event_type="llm_token", output={"token": token}, ...)

    # ACTING（permission gate 自动串入）
    for tool_call in tool_calls:
        permission = await permission_gate.check(tool_call)  # 自动拦截
        if permission.behavior == "ask":
            yield StepEvent(state=StepState.AWAITING_TOOL_PERMISSION, ...)
            response = await interaction_gateway.send_and_wait(...)  # 持久化挂起
            if response.action == "deny":
                yield StepEvent(state=StepState.FAILED, ...); return

        yield StepEvent(state=StepState.ACTING, event_type="tool_call", input=tool_call, ...)
        result = await execute_tool(tool_call)
        yield StepEvent(state=StepState.OBSERVING, event_type="tool_result", output=result, ...)

    yield StepEvent(state=StepState.DONE, ...)
```

**关键设计**：
- 每个 yield 的 StepEvent **同时被 StateStore 持久化**（append-only）
- `AWAITING_*` 状态的 yield 触发"持久化挂起"——EventStream 暂停，进程可重启，续接时从 StateStore 恢复
- Permission gate 在工具执行前**自动拦截**（第 9 节细化）

### 7.4 StateStore 持久化策略

```python
class StateStore(Protocol):
    # event sourcing
    async def append_event(self, event: StepEvent) -> None: ...
    async def get_events(self, conv_id: str, since_seq: int = 0) -> list[StepEvent]: ...
    # step state
    async def get_step_state(self, step_id: str) -> StepState | None: ...
    async def set_step_state(self, step_id: str, state: StepState, snapshot: dict) -> None: ...
    # lease（崩溃检测）
    async def acquire_lease(self, conv_id: str, ttl: int) -> bool: ...
    async def renew_lease(self, conv_id: str, ttl: int) -> bool: ...
    async def scan_expired_leases(self) -> list[str]: ...
```

| 实现 | 选型 | 适用场景 |
|---|---|---|
| **DbStateStore** | 纯 DB（PostgreSQL/MySQL/SQLite），lease 用 `lease_expires_at` 字段 + 定时 scan，缓存降级为进程内 dict | 单机开发、无 Redis 部署 |
| **RedisStateStore** | 纯 Redis（StepEvent 用 Redis Stream，lease 用 TTL） | 短期会话、可接受少量丢失 |
| **HybridStateStore** | DB 持久化 + Redis lease/缓存 | 生产推荐 |

**配置**：

```yaml
state_store:
  backend: "db"  # "db" | "redis" | "hybrid"，默认 "db"
  db:
    url: "postgresql://..."
  redis:
    url: "redis://..."  # 仅 backend=hybrid 时必填
  lease:
    ttl_seconds: 30
    renew_interval_seconds: 10
```

**Redis 不强制引入**——`backend: "db"` 是默认值，单机开发零外部依赖。生产按需开启 `hybrid`。无 Redis 时 lease 用 DB 字段 + 定时 scan，缓存降级为进程内 dict，功能完整只是性能差一点。

### 7.5 崩溃检测 + 重放恢复

**崩溃检测**：
- 每个 agent 运行时持有一个 lease（Redis TTL 30s 或 DB `lease_expires_at`）
- 每 10s 续期一次
- 进程崩溃 → lease 过期 → 其他进程可接管

**重放恢复流程**：
1. 进程启动，扫描 `agent_lease` 过期的 conv_id
2. 对每个 conv_id，读 `step_event` 表重放重建状态
3. 找到最后一个 step 的 state：
   - `AWAITING_*`：恢复到等待状态，等外部输入
   - `THINKING/ACTING/OBSERVING`：该 step 未完成，**从该 step 的输入重新执行**（已完成的 step 从事件流读结果，不重做）
   - `DONE`：继续下一个 step
4. 重新启动 EventStream，从恢复点继续

**关键原则**：**已完成的 step 从事件流读结果，不重做**——避免重复执行副作用（已发的邮件不重发）。**未完成的 step 重新执行**——LLM 调用重新发（非确定性，但输入相同，结果大概率一致）。

---

## 8. SubAgent Runtime

### 8.1 统一入口：`spawn_subagent` 工具

```python
class SpawnSubagentTool(FunctionTool):
    name = "spawn_subagent"

    args = {
        "agent_name": str,           # 子 agent 类型（如 "BAIZE"）
        "task": str,                 # 子 agent 的任务
        "run_in_background": bool,   # False=同步阻塞; True=异步 detach
        "context": dict | None,      # 传给子 agent 的上下文
    }
    # max_depth 由 runtime 全局配置，不在 args 里暴露给 LLM
```

合并 `agent_start` + `AsyncTaskManager` 双轨为单一入口。`spawn_agent_task`/`check_tasks`/`wait_tasks`/`cancel_task` 保留为 SubAgent Runtime 的**查询接口**。

### 8.2 独立上下文（每次 spawn 必建）

```
父 agent (conv_id=A, step_id=S1)
  └─ spawn_subagent(agent_name="BAIZE", task="...", run_in_background=?)
      │
      ├─ 新建 sub_conv_id=B（独立于 A）
      ├─ 独立 messages 序列
      ├─ 独立 agent_memory（继承父 resource_map 子集）
      ├─ 独立 EventStream（子 agent 的 StepEvent 流，写入同一 step_event 表）
      └─ parent_step_id=S1（关联到父 agent 当前 step）
```

### 8.3 同步/异步二选一

**同步（`run_in_background=False`）**：
- 父 agent EventStream 进入 `AWAITING_SUB_AGENT` 状态挂起
- 子 agent 跑完，结果作为 `tool_result` 回父 agent 下一个 step

**异步（`run_in_background=True`）**：
- `spawn_subagent` 立即返回 `task_handle`
- 父 agent 继续做别的
- 子 agent 后台跑，transcript 持久化到 `agent_transcript` 表
- 子 agent 完成后，通过**通知注入**机制把一条 user message 注入父 agent 下一个 turn（类似 claude-code 的 `enqueueAgentNotification`）
- 父 agent 也可主动 `check_subagent_status(task_handle)` 查询

### 8.4 detach + resume（跨进程）

异步子 agent 跑到一半，父 agent 可以：
- **detach**：不等了，做别的（默认行为，无需显式调用）
- **resume**：后续调用 `resume_subagent(task_handle)` 接回
  - 从 `agent_transcript` 表读子 agent 最新状态
  - 子 agent 已完成 → 直接拿结果
  - 子 agent 还在跑 → 父 agent 可 `wait_subagent` 或继续 detach

**跨进程 resume**：transcript 持久化在 DB，父 agent 进程崩溃重启后也能 resume 之前的异步子 agent（和第 7 节的崩溃恢复闭环）。

### 8.5 嵌套递归深度限制

子 agent 可 spawn 子子 agent，但 `max_depth` 全局限制（默认 5，可配置）。每 spawn 一层 depth+1，超限则 spawn 失败。类似 Hermes 的 `max_spawn_depth`。

### 8.6 子 agent 的 ask_user / permission 处理（策略 C）

| 策略 | 行为 | 优缺点 |
|---|---|---|
| A. 自动 deny（headless） | 子 agent 的 ask_user/授权请求自动 deny | 子 agent 可能因 deny 失败 |
| B. 全部冒泡到父 agent | 子 agent 的请求冒泡，父 agent 决定是否问用户 | 异步子 agent 会打断父 agent |
| **C. 同步冒泡 + 异步自动 deny（推荐）** | 同步子 agent：ask_user/授权冒泡到父 agent（父 agent 在 `AWAITING_SUB_AGENT` 状态收到子 agent 的 `interaction_request`）；异步子 agent：自动 deny | 和 claude-code 一致，同步保用户体验，异步保非阻塞 |

**策略 C 实现**：父 agent spawn 时把自己的 `PermissionContext` 透传给子 agent。子 agent 的 `interaction_gateway` 在同步模式下委托父 agent，在异步模式下走 `autoDenyForBackgroundAgents`。

```python
class SubAgentInteractionGateway(InteractionGateway):
    def __init__(self, parent_agent, sync: bool):
        self.parent = parent_agent
        self.sync = sync

    async def send_and_wait(self, request) -> InteractionResponse:
        if self.sync:
            return await self.parent.delegate_interaction(request)
        else:
            return InteractionResponse(action="deny", reason="auto-deny for background agent")
```

### 8.7 父 agent 接收异步子 agent 结果的两种机制

| 机制 | 触发 | 类比 |
|---|---|---|
| **通知注入**（被动） | 子 agent 完成后自动注入一条 user message 到父 agent 下一个 turn | claude-code `enqueueAgentNotification` |
| **主动查询**（主动） | 父 agent 调用 `check_subagent_status(task_handle)` | claude-code `AppState.tasks[taskId]` |

---

## 9. 用户交互 + Permission Gate

### 9.1 统一 InteractionRequest + 持久化

现状已有 `InteractionAdapter`（`interaction_adapter.py:38`）+ `interaction_protocol.py`（`InteractionType/Status`），保留扩展：

```python
# InteractionType（已有，保留）
ASK / CONFIRM / SELECT / AUTHORIZE / CHOOSE_PLAN / NOTIFY

# InteractionStatus（已有，保留）
PENDING / RESPONSSED / TIMEOUT / CANCELLED / DEFERRED

# InteractionRequest 扩展字段
@dataclass
class InteractionRequest:
    request_id: str
    step_id: str          # 新增：关联 event sourcing
    conv_id: str
    type: InteractionType
    # ... 其余字段保留
```

`InteractionRequest` 持久化到 StateStore 的 `interaction_checkpoint` 表——`AWAITING_USER`/`AWAITING_TOOL_PERMISSION` 状态的 step 进程崩溃后能从 checkpoint 恢复。

### 9.2 PermissionMode 状态机（新增，类似 claude-code）

| Mode | 行为 | 场景 |
|---|---|---|
| `default` | 每个工具调用按规则检查，`ask` 则问用户 | 默认 |
| `plan` | 只规划不执行（有副作用的工具自动 deny，只允许只读工具） | 规划模式 |
| `auto` | 自动允许所有工具（YOLO） | 谨慎用，需显式开启 |
| `bypass` | 跳过 PermissionGate（仅内部用，不暴露给 LLM/用户） | 系统级操作 |

`PermissionMode` 是 agent 级配置，存在 `agent_context` 里。可运行时切换（类似 claude-code 的 `/permissions`）。

### 9.3 PermissionGate：自动串入 act()（关键缺陷修复）

```python
class PermissionGate:
    async def check(self, tool_call, agent) -> PermissionResult:
        # 1. PermissionMode 短路
        mode = agent.context.permission_mode
        if mode == "bypass" or mode == "auto":
            return PermissionResult(behavior="allow")
        if mode == "plan" and tool_call.has_side_effects:
            return PermissionResult(behavior="deny", reason="plan mode")

        # 2. session cache（同会话已授权过）
        if agent.session_cache.is_allowed(tool_call.tool_name, tool_call.input_hash):
            return PermissionResult(behavior="allow")

        # 3. permission_ruleset（静态规则）
        action = agent.permission_ruleset.check(tool_call)
        if action == PermissionAction.ALLOW: return allow
        if action == PermissionAction.DENY:  return deny

        # 4. Tool.check_permissions（工具自带规则，类似 claude-code）
        result = await tool.check_permissions(tool_call.input, agent.context)
        if result.behavior != "ask": return result

        # 5. behavior=ask → 发 InteractionRequest 持久化挂起
        interaction = InteractionRequest(
            type=InteractionType.AUTHORIZE, step_id=agent.current_step_id,
            options=[
                {"label": "Allow once",        "action": "allow_once"},
                {"label": "Allow for session", "action": "allow_session"},
                {"label": "Deny",              "action": "deny"},
            ])
        # EventStream yield AWAITING_TOOL_PERMISSION，进程崩溃不丢
        response = await agent.interaction_gateway.send_and_wait(interaction)

        # 6. 处理响应
        if response.action == "allow_session":
            agent.session_cache.allow(tool_call.tool_name, tool_call.input_hash)
        return {"allow_once": allow, "allow_session": allow, "deny": deny}[response.action]
```

**关键设计**：
- **PermissionGate 是 act() 的前置拦截器**——所有工具调用前自动检查，**不需要各 Action 自行集成**（修复现状的关键缺陷）
- 5 级检查链：PermissionMode → session cache → permission_ruleset → Tool.check_permissions → InteractionRequest
- `InteractionRequest` 持久化挂起（`AWAITING_TOOL_PERMISSION`），进程崩溃不丢
- session cache 支持 `allow_once` / `allow_session` / `deny`

### 9.4 老 `ActionOutput.ask_user` 废弃 + 迁移

| 阶段 | 动作 |
|---|---|
| **废弃** | `ActionOutput.ask_user` 字段（`base_agent.py:1258/1295` 的 break 循环逻辑） |
| **迁移** | 所有 Action 改用 `agent.interaction_adapter.ask()` / `.confirm()` / `.select()` 主动发起 InteractionRequest |
| **兼容期** | 保留 `ActionOutput.ask_user` 字段一个版本，适配层自动转成 `InteractionRequest`，让老 Action 逐步迁移 |

### 9.5 前端交互 UI 对接

| 现有 | 新架构下 |
|---|---|
| `/api/v1/interaction/respond`（`interaction_api.py:73`） | 保留，前端提交响应的协议不动 |
| `interaction_gateway.deliver_response`（L251） | 保留，解除挂起 |
| 前端 SSE `vis.type=intervention_triggered` | 复用，作为 `InteractionRequest` 的前端事件载体 |
| 前端交互 UI（ask/confirm/select/authorize） | 新建，但走现有 SSE + HTTP 协议，不引入新通道 |

**关键**：前端交互 UI 通过现有 SSE（`intervention_triggered` 事件）+ 现有 HTTP（`/respond`）对接，**不引入新协议通道**。前端需要新增的只是渲染交互组件本身（如果还没有的话）。

---

## 10. 事件流统一 + 前端 SSE 适配

### 10.1 单一 EventStream

```python
async def agent_event_stream(agent, input_) -> AsyncGenerator[StreamEvent, None]:
    """Agent 对外统一事件流。SSE 适配层、内部消费者、BAIZE 子系统适配层都从这里读。"""
    async for step_event in run_step(agent, input_):
        yield step_event_to_stream_event(step_event)
```

### 10.2 StreamEvent 类型

```python
@dataclass
class StreamEvent:
    type: str
    payload: dict
    seq: int
    timestamp: float

EVENT_TYPES = {
    # === 老 SSE 兼容（前端零修改） ===
    "metadata",            # 老 SSE #1
    "interrupt",           # 老 SSE #2
    "error",               # 老 SSE #3
    "workspace",           # 老 SSE #4-9 (task_created/context_loaded/intervention_triggered/...)
    "content",             # 老 SSE #10 (VIS markdown 字符串)
    "done",                # 老 SSE #11 ([DONE])

    # === 新增细粒度（前端可选消费，增量迁移） ===
    "step_start", "step_end",
    "llm_token",           # thinking 增量 token
    "tool_call", "tool_result",
    "interaction_request", # ask_user / 工具授权
    "sub_agent_start", "sub_agent_result",
}
```

### 10.3 SSE 适配层

```python
async def stream_to_sse(event_stream) -> AsyncGenerator[str, None]:
    """把新 StreamEvent 转成老 SSE 格式，前端零修改。"""
    yield 'data:{"vis":{"type":"metadata","conv_session_id":"...","conv_uid":"..."}}\n\n'

    async for event in event_stream:
        if event.type == "content":
            # 复用老 VisProtocolConverter 产出 VIS markdown
            vis_md = agent.vis_converter.visualization(event.payload)
            yield f'data:{{"vis":"{vis_md}"}}\n\n'
        elif event.type == "workspace":
            yield f'data:{{"vis":{{"type":"{event.payload["event_type"]}","payload":{...}}}}}\n\n'
        elif event.type == "interaction_request":
            yield f'data:{{"vis":{{"type":"intervention_triggered","payload":{...}}}}}\n\n'
        elif event.type == "error":
            yield f'data:{{"vis":{{"type":"error","content":"{event.payload["message"]}"}}}}\n\n'
        elif event.type == "done":
            yield 'data:{"vis":"[DONE]"} \n'
```

**关键**：SSE 适配层**直接调用老 `VisProtocolConverter`**（`GptVisConverter`/`DeriskVisConverter`/`DeriskIncrVisWindowConverter` 等）产出 VIS markdown，不重新实现渲染逻辑。前端 `use-chat.ts:94-137` 的判定路径完全不动。

### 10.4 三管道归并

| 现有管道 | 新架构下的去向 |
|---|---|
| `push_context_event` → Operator 注册表（`base_agent.py:2867`） | 废弃，被 EventStream 取代 |
| `push_message` → per-conv `asyncio.Queue`（`gpts_memory.py:1232`） | 废弃，被 EventStream 取代 |
| `HookManager.trigger`（`core/hook/manager.py:98`） | 保留，但事件来源从 `push_context_event` 改为 EventStream 的 `step_end` 事件 |

**关键**：HookManager 不废弃——它是**数据层**（长期记忆 tier0/1/2/3 的触发器），不是渲染层。只是它的触发源从 `push_context_event`（已废弃）改为 EventStream 的 `step_end` 事件。

### 10.5 前端 SSE 端点：保留外壳，内部改消费 EventStream

| 现有 | 新架构下 |
|---|---|
| `agent_chat.chat`（L673）SSE 端点签名 | 保留 |
| `_chat_messages`（L2753）`async for item in iterator` | 改为 `async for chunk in stream_to_sse(agent_event_stream(agent, input_))` |
| `queue_iterator`（`gpts_memory.py:851`） | 废弃 |
| 老 `VisProtocolConverter` 组件 | 保留并复用，被 SSE 适配层调用 |

### 10.6 BAIZE 子系统适配层

BAIZE 子系统目前通过 `push_context_event` 和 `push_message` 输出事件。新架构下通过适配层接入 EventStream：

```python
class BAIZESubsystemAdapter:
    """把 BAIZE 子系统的事件转成 StreamEvent。"""

    def __init__(self, event_stream: EventStream):
        self.event_stream = event_stream

    async def on_kanban_update(self, kanban_state):
        await self.event_stream.emit(StreamEvent(
            type="workspace",
            payload={"event_type": "task_created", "payload": kanban_state},
        ))

    async def on_phase_change(self, phase):
        await self.event_stream.emit(StreamEvent(
            type="workspace",
            payload={"event_type": "context_loaded", "payload": phase},
        ))
    # ... 其他子系统
```

**关键原则**：子系统内部实现不动，只改它们的"事件输出口"——从 `push_context_event`/`push_message` 改为调用 `BAIZESubsystemAdapter.emit()`。

---

## 11. BAIZE 子系统适配 + 测试 + 迁移路径

### 11.1 BAIZE 子系统适配层细化

| 子系统 | 现状接入方式 | 新架构下适配方式 |
|---|---|---|
| `ContextEngine` | 通过 `push_context_event` 接入压缩事件 | 通过 `BAIZESubsystemAdapter` 订阅 EventStream 的 `step_end` 事件做压缩，**不改其内部实现** |
| `KanbanManager` | 通过 `push_message` 输出任务规划 | 通过 `BAIZESubsystemAdapter` 输出 `workspace` 事件（`task_created`） |
| `WorkLogManager` | 通过 `push_context_event` 输出工作日志 | 通过 `BAIZESubsystemAdapter` 输出 `content` 事件 |
| `PhaseManager` | 通过 `push_context_event` 输出阶段变化 | 通过 `BAIZESubsystemAdapter` 输出 `workspace` 事件（`context_loaded`） |
| `SystemEventManager` | 通过 `push_context_event` 输出 VIS 渲染 | 通过 `BAIZESubsystemAdapter` 输出 `content`/`workspace` 事件 |

### 11.2 ReactMasterAgent.bind().build() 链路保留

现状链路（`react_master_agent.py:1296-1308`）：

```python
ReactMasterAgent.bind(agent_context).bind(agent_memory).bind(llm_config) \
    .bind(sandbox_manager).bind(resource).bind(context_config) \
    .bind(ExtConfigHolder).bind(scheduler).build()
```

新架构下：
- `bind()` 链路**完全保留**
- **新增** `bind(v2_runtime)` 绑定 V2 Runtime（六件套）
- `build()` 内部把 `ConversableAgent.generate_reply` 替换为调用 V2 Runtime
- 子系统通过 `BAIZESubsystemAdapter` 接入 V2 Runtime 的 EventStream
- App JSON 配置（main_orchestrator/manus/rca_openraca）**零修改**

### 11.3 测试策略

**单元测试**：
- StepState 状态机转换（合法转换通过、非法转换拒绝）
- StepEvent append-only + `seq` 单调递增
- PermissionGate 5 级检查链（每级短路、fallback）
- SubAgent Runtime（同步/异步、detach/resume、嵌套深度限制）
- StateStore 三实现 contract 测试（DbStateStore/RedisStateStore/HybridStateStore 接口一致性）

**集成测试**：
- 崩溃恢复：跑到 `AWAITING_USER` → kill 进程 → 重启 → 从 checkpoint 恢复 → 用户响应 → 续接
- 异步子 agent detach + resume：父启动异步子 agent → 父做别的 → 父 crash → 重启 → resume 子 agent → 拿到结果
- 工具授权跨进程：`AWAITING_TOOL_PERMISSION` → kill → 重启 → 用户授权 → 工具执行
- 长期记忆 hook：`step_end` 事件触发 tier0/1/2/3 钩子

**兼容测试**：
- BAIZE 现有行为不回归（main_orchestrator/manus/rca_openraca 三个 App JSON 跑通）
- 前端 SSE 协议兼容（老前端零修改消费新 EventStream）
- 老 `VisProtocolConverter` 输出格式不变
- App JSON 配置零修改

### 11.4 迁移路径（分阶段 P0-P4）

| 阶段 | 目标 | 范围 | 验证 |
|---|---|---|---|
| **P0** | 内核骨架 | StepState + StepEvent + EventStream + StateStore（DbStateStore）+ 崩溃恢复 | 单元测试 + 简单 Agent 跑通 |
| **P1** | Permission Gate | PermissionGate 5 级检查 + InteractionRequest 持久化 + 老 `ActionOutput.ask_user` 适配层 | 集成测试：工具授权跨进程 |
| **P2** | SubAgent Runtime | `spawn_subagent` 统一入口 + 同步/异步 + detach/resume + 嵌套深度 | 集成测试：异步子 agent crash + resume |
| **P3** | 事件流统一 | StreamEvent + SSE 适配层 + 三管道归并 + BAIZESubsystemAdapter | 兼容测试：BAIZE 三 App 跑通 + 前端零修改 |
| **P4** | 清理 | 废弃 `push_context_event`/`push_message`/`queue_iterator`/`ActionOutput.ask_user`/`needs_tool_approval` | 兼容测试：无回归 |

**关键**：P3 之前老三管道和新 EventStream **并存**（适配层双向转换），P3 完成后才废弃老管道。这避免了"一刀切"的风险。

### 11.5 风险与回退

| 风险 | 缓解 |
|---|---|
| BAIZE 子系统适配层复杂度（ContextEngine 压缩逻辑可能深度耦合 `push_context_event`） | P3 先做最小适配，ContextEngine 订阅 `step_end` 触发压缩，不改其内部实现 |
| 老 Action 迁移到 `interaction_adapter` 工作量大 | 兼容期保留 `ActionOutput.ask_user` 字段，适配层自动转，老 Action 逐步迁移 |
| StateStore 持久化性能（StepEvent append 频率高） | HybridStateStore 用 Redis 做 write-ahead buffer，批量 flush 到 DB |
| 崩溃恢复的 LLM 非确定性（重启后重新调用 LLM 结果可能不同） | 已完成 step 从事件流读结果不重做；未完成 step 重新执行接受非确定性 |
| Redis 可选但生产推荐 → 开发环境无 Redis 时 lease 用 DB scan 性能 | 单机开发 conv_id 数量少，scan 性能够用；生产用 Hybrid |
| P3 双轨期事件一致性（老管道和新 EventStream 并存） | 适配层做双向转换，老管道的事件全部由新 EventStream 派生，保证单一真相源 |

---

## 12. 与现有代码的关系总览

| 现有 | 新架构下 |
|---|---|
| `ConversableAgent.generate_reply`（`base_agent.py:941`） | 保留外壳，内部改为调用 V2 Runtime |
| `Status` 枚举 + `received_message_state` + `RuntimeContext.recovering` | 废弃，被 StepState 状态机取代 |
| `push_context_event` + Operator 注册表 | 废弃，被 EventStream 取代 |
| `push_message` + per-conv Queue + `queue_iterator` | 废弃，被 EventStream + SSE 适配层取代 |
| `vis_messages` + `VisProtocolConverter` | 保留并复用 |
| `HookManager.trigger` | 保留，事件来源改为 EventStream |
| `RecoveryCoordinator` + `MemoryStateStore` | 扩展，StateStore 升级为 DB+Redis |
| `AgentStart` action + `AsyncTaskManager` | 合并为 SubAgent Runtime |
| `CoreV1SubagentAdapter` | 保留作为 SubAgent Runtime 的分布式调度适配层 |
| `check_tool_permission` + `needs_tool_approval` + `ActionOutput.ask_user` | 废弃，被 PermissionGate + InteractionAdapter 取代 |
| `InteractionAdapter` + `InteractionGateway` + `interaction_protocol.py` | 保留扩展 |
| `/api/v1/interaction/respond` | 保留，前端协议不动 |
| `ReactMasterAgent.bind().build()` 链路 | 保留，新增 `bind(v2_runtime)` |
| BAIZE 子系统（ContextEngine/Kanban/WorkLog/Phase/SystemEventManager） | 内部不动，通过 BAIZESubsystemAdapter 接入 |
| App JSON 配置 + 前端 SSE 协议 | 零修改 |

---

## 13. 附录：术语表

| 术语 | 定义 |
|---|---|
| **V2 Runtime** | 本设计提出的新 Agent 运行时内核，含六件套 |
| **StepState** | 显式状态枚举，替代散落的 Status + received_message_state + RuntimeContext.recovering |
| **StepEvent** | event sourcing 最小单元，append-only，含 step_id/state/input/output/seq |
| **EventStream** | AsyncGenerator[StreamEvent]，单一事件流，替代三管道 |
| **StreamEvent** | 对外级事件，覆盖老 SSE 10 种 + 新增细粒度 |
| **StateStore** | 持久化接口，三实现：DbStateStore/RedisStateStore/HybridStateStore |
| **SubAgent Runtime** | 统一子 Agent 入口，合并 agent_start + AsyncTaskManager |
| **PermissionGate** | 工具执行前自动拦截的 5 级检查链 |
| **PermissionMode** | default/plan/auto/bypass 四种模式 |
| **BAIZESubsystemAdapter** | BAIZE 子系统接入 EventStream 的适配层 |
| **SSE 适配层** | StreamEvent → 老 SSE 格式的转换层，复用老 VisConverter |
| **Lease** | agent 运行时心跳，用于崩溃检测（Redis TTL 或 DB lease_expires_at） |
| **Transcript** | 子 agent 独立消息序列，用于 detach + resume |
