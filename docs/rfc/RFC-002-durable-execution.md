# RFC-002 · 持久化执行与检查点机制

| 字段 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-06-18 |

---

## 1. 背景与问题

长任务（数据分析、代码生成、多轮诊断）跑到一半进程崩溃 / 被 kill / OOM 重启时，当前没有跨进程恢复能力——必须从头跑。这对：

- **生产稳定性**：主机重启 / Pod 漂移会丢任务；
- **交互连续性**：用户在第 8 步被打断，回来时只能从第 1 步重来；
- **成本控制**：长任务平均 10-30 次 LLM 调用，重跑 = 直接浪费几美元到几十美元；

是真实痛点。

## 2. v1 已有的恢复底座

`agent/interaction/` 路径下已经有一套**正在跑**的 checkpoint 机制：

```python
# agent/interaction/interaction_protocol.py
class InterruptPoint(BaseModel)         # 中断点
class RecoveryState(BaseModel)          # 恢复状态
class ResumeResult(BaseModel)           # 恢复结果

# agent/interaction/interaction_gateway.py
class StateStore(ABC)                   # 状态存储抽象
class MemoryStateStore(StateStore)      # 内存实现

# agent/interaction/recovery_coordinator.py
class RecoveryCoordinator:
    async def create_checkpoint(session_id, execution_id, step_index, phase, context, agent)
    async def recover(session_id, resume_mode)

# react_master_agent/interaction_extension.py（已接入 ReAct 路径）
async def request_tool_authorization():
    await self._create_checkpoint_if_needed()    # 工具授权前 checkpoint
async def ask():
    await self._create_checkpoint_if_needed()    # 用户提问前 checkpoint
async def choose_plan():
    await self._create_checkpoint_if_needed()    # 多方案选择前 checkpoint
```

抽象层完整（`StateStore` + `RecoveryCoordinator` + `RecoveryState`），并已在**交互打断点**上自动打 checkpoint。**唯一缺的是"崩溃恢复"**——目前 checkpoint 只在用户主动交互（`ask` / `request_tool_authorization` / `choose_plan`）时打，没有覆盖：

1. **每 N 步自动 checkpoint**（防止崩溃丢进度）；
2. **进程启动时检测 unfinished session 并提示恢复**；
3. **`StateStore` 默认实现是内存版**（`MemoryStateStore`），重启即丢——需要持久化后端。

## 3. 设计目标与原则

| 原则 | 含义 |
|---|---|
| **复用 RecoveryCoordinator** | 不引入 `AgentHarness` / `CheckpointManager` 新类；现有抽象足够 |
| **分级触发** | 交互打断点（已有）+ 步级自动 + 时间兜底，三种独立的 checkpoint 触发条件 |
| **覆盖式优于链式** | 每 session 只保留最近 N 个 checkpoint，不做链式压缩——直到出现真实诉求 |
| **失败安全** | checkpoint 写盘失败不阻塞主流程，记 WARN 日志即可——主进程继续，下一次 checkpoint 再尝试 |

## 4. 核心机制

### 4.1 持久化 StateStore

```python
class FileStateStore(StateStore):
    """文件后端，按 session_id 落盘到 ${DERISK_HOME}/recovery/{session_id}.json
    
    每个 session 维护一个 JSON 文件，包含最近 N 个 checkpoint 的环形缓冲。
    写入采用 atomic write（写 .tmp + rename），避免半写文件。
    """
    
    def __init__(self, base_dir: str, max_checkpoints_per_session: int = 5):
        ...
```

或更稳的 `DbStateStore`（写 `gpts_recovery_state` 表）。生产默认 `FileStateStore`，开发默认 `MemoryStateStore`。

### 4.2 步级自动 checkpoint

在 ReAct 循环关键节点补打点：

```python
# react_master_agent.py 的 _run_thinking_loop
async for step in thinking_loop:
    await self._maybe_checkpoint(step_index=step.idx, phase="thinking_done")
    # ... LLM call ...
    await self._maybe_checkpoint(step_index=step.idx, phase="action_dispatched")
    # ... tool execute ...
    await self._maybe_checkpoint(step_index=step.idx, phase="action_complete")
```

`_maybe_checkpoint` 内部按 **步数 + 时间双门控** 触发：

```python
async def _maybe_checkpoint(self, step_index: int, phase: str):
    now = time.monotonic()
    by_step  = step_index - self._last_checkpoint_step >= self.config.checkpoint_step_interval
    by_time  = now - self._last_checkpoint_at >= self.config.checkpoint_max_seconds
    if not (by_step or by_time):
        return
    try:
        await self.recovery.create_checkpoint(...)
        self._last_checkpoint_step = step_index
        self._last_checkpoint_at = now
    except Exception as e:
        logger.warning(f"checkpoint failed at step={step_index} phase={phase}: {e}")
```

默认配置：`step_interval=5`、`max_seconds=60`。

### 4.3 启动时 unfinished session 检测

```sql
SELECT session_id FROM gpts_recovery_state
WHERE status IN ('running', 'paused')
  AND updated_at < NOW() - INTERVAL 1 MINUTE   -- 心跳超时视为崩溃
```

对每个 unfinished session：
- 进程启动时**只记 WARN 日志，不主动恢复**（避免雪崩）；
- 在 `ReActMasterAgent` 创建时，若发现入参 `session_id` 命中 unfinished，触发 `recover()` 恢复链路。

### 4.4 心跳更新

`_maybe_checkpoint` 调用时一并更新 `gpts_recovery_state.updated_at`——这样"心跳超时"的判定与 checkpoint 节奏自然对齐，无需独立心跳任务。

## 5. 演进路径

| 步骤 | 改动 | 代码量 | 风险 |
|---|---|---|---|
| **S1** | 在 `agent/interaction/interaction_gateway.py` 新增 `FileStateStore`（按 session_id 落盘 + atomic write + 环形缓冲 N=5） | ~120 行 | 低 |
| **S2** | `RecoveryCoordinator` 默认 store 由配置切换（dev: memory, prod: file） | ~30 行 | 低 |
| **S3** | `InteractionExtension` 增 `_maybe_checkpoint`（步数 + 时间双门控） | ~60 行 | 低 |
| **S4** | `ReActMasterAgent._run_thinking_loop` 关键 3 处调用 `_maybe_checkpoint` | ~30 行 | 中 |
| **S5** | 新增 `gpts_recovery_state` 表（如选 DB 后端）+ unfinished session 启动扫描 | ~150 行 | 中 |
| **S6** | CLI 工具 `derisk recover-session <session_id>`：手动恢复 | ~50 行 | 低 |

**总计**：~440 行新增 + 部分主路径插桩。全部叠加在已有 `interaction/` 抽象上，不新增框架。

## 6. 不做什么

- **不引入 `AgentHarness` 类**——`ConversableAgent` + `RecoveryCoordinator` 组合已是合适的承载者。
- **不做 `CircuitBreaker` 熔断 / `WorkerPool` / `DistributedExecution`**——这些是 SRE 层关注，不是 agent 框架基础能力。
- **不引入"5 层 ExecutionContext"**（system / task / tool / memory / temporary）——上下文分层是上下文管理 RFC 范畴，不是 checkpoint 的事。
- **不做"链式压缩 checkpoint"**（每 checkpoint 引用父 checkpoint）——直接覆盖最近 N 个，未来出现长 session 内存压力再考虑。
- **不做"6 种 checkpoint type"**（manual/automatic/task_start/task_end/error/milestone）——实际只需要 `auto / manual / interaction` 三种，多余类型可未来按需加。
- **不解决跨进程沙箱状态恢复**——本 RFC 只恢复 agent 的执行状态（消息、step、todo）；沙箱内文件 IO 副作用可能丢失，**用户需明确知晓**。沙箱快照是 SandboxManager 范畴。
- **不做 checkpoint 加密**——除非部署环境明确要求；多数场景 checkpoint 与 `gpts_messages` 同等敏感级别，沿用现有数据保护即可。

## 7. 验收标准

| 编号 | 项 | 判定 |
|---|---|---|
| AC-1 | 长任务进程崩溃后重启，能从最近 checkpoint 恢复 | e2e：跑 10 步任务，第 5 步 `kill -9`，重启后 `recover()` 从第 5 步继续 |
| AC-2 | `FileStateStore` 默认落盘到 `${DERISK_HOME}/recovery/`，重启后可见 | 集成测试 |
| AC-3 | 步级自动 checkpoint 不显著增加单步耗时（< 5%） | benchmark：开/关 checkpoint 对比 LLM step 耗时 |
| AC-4 | 进程启动时若有 unfinished session（心跳超时 1 分钟），记 WARN 日志 | 启动日志验证 |
| AC-5 | 现有交互打断点（ask/authorize/choose_plan）的 checkpoint 行为不退化 | 现有测试 100% 通过 |
| AC-6 | checkpoint 写盘失败不阻塞主流程，仅记 WARN | 故障注入测试（mock 磁盘满） |

## 8. 开放问题

1. `FileStateStore` 是否够用，还是直接落 DB（`gpts_recovery_state`）？建议：先 File（实现简单、零基础设施依赖）；跨 Pod / 多实例场景再加 DB。
2. `checkpoint_interval` 默认值（步数 / 时间双门控的具体阈值）需要根据线上 LLM 平均耗时调整——上线后看实际 checkpoint 频率再调。
3. checkpoint 数据中包含用户问题与工具结果（敏感信息），落盘时是否需要加密？取决于部署环境，可作为 `FileStateStore` 的可选能力（`FileStateStore(encrypt=True, key=...)`）。
4. 心跳超时阈值（默认 1 分钟）能否处理"用户长时间未回复 ask"的场景？这种 session 不是崩溃而是阻塞——建议用 `RecoveryState.status` 的 `paused` 与 `running` 区分，启动扫描只针对 `running` 且超时的，不误报阻塞会话。
