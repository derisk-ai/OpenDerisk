# V1 Agent 架构与设计

> **版本**：v1.0
> **日期**：2026-07-06
> **状态**：当前主链路（V2 已归档为参考实现）

---

## 1. 总览

V2 框架已归档为参考实现（`packages/derisk-core/src/derisk/agent/core/v2/`，151/151 测试保留但生产入口关闭）。V1 通过 8 个 PR + Tier 3 + 5 个 gap 修复，纯加法地把 V2 的全部优势移植到现有主链路：

| 改造 | 内容 |
|------|------|
| PR 1 | 状态机形式化（`step_state_guard.py`） |
| PR 2 | 统一 sub_agent 工具（sync/async + 深度守卫 + 自模板 + SubAgentHandle） |
| PR 3 | step-level resume（复用 `gpts_message` + `gpts_work_log`） |
| PR 4 + Tier 3.2 | 心跳 + Lease + 自动恢复 |
| PR 5 | 权限 5 级链（Mode → Cache → Ruleset → Hook → CheckpointStore） |
| PR 6 | Hook context builders 抽取 |
| PR 7 | ToolFailureTracker（工具熔断） |
| PR 8 | Usage metric 聚合 |
| Tier 3.1 | Event sourcing 审计日志（`gpts_events` 表） |
| Tier 3.4 | 状态机模型检查（随机游走 + BFS 可达性 + 死锁检测） |

V2 spec 自己的对比表承认 V2 在 11 项里只赢 4 项、输 5 项、平 2 项。V2 赢的几项经核实都能在 V1 上纯加法实现，因此 V2 不再有独立生产价值。

---

## 2. 分层架构

```
┌──────────────────────────────────────────────────────────────┐
│  API 层 (FastAPI)                                            │
│  packages/derisk-serve/src/derisk_serve/agent/agents/chat/   │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  AgentChat (会话编排)                                        │
│  agent_chat.py                                               │
│  - 入口：aggregation_chat / _inner_chat                      │
│  - lease acquire/release (并发安全)                          │
│  - turn 结束决策 (pending_subagents → WAITING)               │
│  - RecoveryDaemon 启动钩子                                   │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  ConversableAgent / ReActMasterAgent (主循环)                │
│  base_agent.py / react_master_agent.py                       │
│  - generate_reply: think → act → think ... while loop        │
│  - emit_think_start/end + emit_act_start/end (事件埋点)      │
│  - touch_heartbeat (loop 自然进度点 inline)                  │
│  - step-level resume (recovering 模式查 work_log)            │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  Action 层                                                   │
│  actions/tool_action.py    - 工具调用 (5 级权限链)           │
│  actions/agent_action.py   - SubAgent (sync/async + 深度)    │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  横切关注点                                                   │
│  ├─ step_state_guard.py        状态机守卫                     │
│  ├─ heartbeat.py + lease       心跳 + 租约                    │
│  ├─ permission_mode.py         Mode → Cache → Ruleset → Hook │
│  ├─ permission_checkpoint_store.py  ASK 决策持久化            │
│  ├─ tool_failure_tracker.py    工具熔断                       │
│  ├─ hook_context_builders.py   Hook 上下文统一构造            │
│  ├─ event_log.py + gpts_events 表  事件审计                   │
│  ├─ usage_metric.py + model_pricing.py  Token/cost 聚合      │
│  └─ subagent_handle.py + subagent_coordinator.py  子 Agent   │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  持久化                                                       │
│  gpts_conversations  + gpts_messages + gpts_work_log         │
│  + gpts_events (新) + last_heartbeat + worker_id/lease       │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 核心抽象

### 3.1 AgentContext (`packages/derisk-core/src/derisk/agent/core/agent.py:223`)

会话级上下文，关键字段：

- `conv_id` / `conv_session_id`：会话标识
- `gpts_app_code` / `agent_app_code`：当前应用编码
- `extra["subagent_depth"]`：子 agent 嵌套深度（0=主，每 spawn +1，超过 `MAX_SUBAGENT_DEPTH=5` 抛 `SubagentDepthExceededError`）
- `extra["permission_mode"]`：权限模式（auto/plan/manual）
- `max_chat_round` / `max_retry_round` / `max_new_tokens` / `temperature`

### 3.2 SubAgentHandle (`packages/derisk-core/src/derisk/agent/core/subagent_handle.py`)

子 agent 状态封装，序列化到 `gpts_conversations.extra.pending_subagents`：

```python
@dataclass
class SubAgentHandle:
    sub_conv_id: str
    main_conv_id: str
    mode: SubAgentMode       # SYNC | ASYNC
    status: SubAgentStatus   # PENDING | RUNNING | DONE | FAILED
    result: Optional[str]
    error: Optional[str]
    started_at: Optional[float]
    finished_at: Optional[float]

    def is_terminal() -> bool  # status in (DONE, FAILED)
    def to_dict() / from_dict()  # 序列化
```

### 3.3 ConversationCache (`packages/derisk-core/src/derisk/agent/core/memory/gpts/gpts_memory.py:214`)

会话级内存缓存，承载：

- `messages: Dict[str, GptsMessage]` + `message_ids: List[str]`
- `plans: Dict[str, GptsPlan]`
- `work_logs: List[WorkEntry]` + `work_entries_by_message: Dict[str, List[WorkEntry]]`
- `events: List[GptsEventEntity]`（Tier 3.1 加载，用于审计/重放）
- `actions / system_messages / context_windows / files / kanban / todos`
- `last_access` / `lock: asyncio.Lock`

`load_persistent_memory(conv_id, replay_events=False)`：懒加载 messages + plans + work_logs；`replay_events=True` 时同时加载 `gpts_events`。

---

## 4. 关键流程

### 4.1 主循环（think → act）

```
agent_chat._inner_chat
  ├─ acquire_lease(conv_uid)            # 并发安全：原子条件 UPDATE
  ├─ touch_heartbeat(conv_uid)          # 入口心跳
  ├─ generate_reply (while retry):
  │     ├─ touch_heartbeat              # 每轮 think 前
  │     ├─ emit_think_start             # 事件埋点
  │     ├─ llm_client.create(...)       # LLM 调用（流式）
  │     ├─ emit_think_end               # 事件埋点
  │     ├─ emit_usage_metric            # token 聚合
  │     └─ act(message):
  │           ├─ touch_heartbeat        # 工具前
  │           ├─ emit_act_start         # 每个工具一次
  │           ├─ asyncio.gather(...)    # 并行执行
  │           ├─ emit_act_end           # 每个工具一次
  │           ├─ touch_heartbeat        # 工具后
  │           └─ tracker.record_success/failure  # 熔断追踪
  └─ release_lease / state transition (COMPLETE/WAITING/FAILED)
```

### 4.2 子 Agent（sync vs async）

```
SubAgent.run (agent_action.py:440)
  ├─ 读 parent_depth = agent_context.extra["subagent_depth"]
  ├─ if depth >= MAX_SUBAGENT_DEPTH(5): raise SubagentDepthExceededError
  │
  ├─ if mode == "sync":
  │     ├─ 调 super().run (走 recipient.generate_reply)
  │     └─ recipient.agent_context.extra["subagent_depth"] = parent_depth + 1
  │
  └─ if mode == "async":
        ├─ coordinator.register_subagent → 写 gpts_conversations.extra
        ├─ asyncio.create_task(_run_subagent_background)
        │     └─ _start_app(parent_depth=parent_depth)
        │           └─ child AgentContext.extra["subagent_depth"] = parent_depth + 1
        └─ 返回 sub_conv_id，主 loop 看到 observation 后可继续 spawn 或结束当前轮

# turn 结束决策（agent_chat.py:3208）
if pending_subagents and not all_done: state = WAITING
else: state = COMPLETE / WAITING(user_input)

# 子 agent 完成 → coordinator.on_subagent_done
#   → 全 done → _trigger_main_resume
#       （注入 subagent_results 到 user message, is_retry_chat=True）
```

### 4.3 崩溃恢复

```
进程启动
  └─ RecoveryDaemon.scan_and_recover()
        ├─ SELECT * FROM gpts_conversations WHERE state='RUNNING'
        └─ for each conv:
              ├─ if heartbeat fresh AND lease valid: skip (其他进程在跑)
              ├─ if acquire_lease(conv_id) == False: skip (被抢)
              ├─ validate_session_transition(RUNNING → RETRYING)  # 状态机守卫
              ├─ UPDATE state='RETRYING'
              ├─ if has pending_subagents:
              │     └─ coordinator.recover_main:
              │           - 子 DONE → 收集 result
              │           - 子 RUNNING + lease 过期 → 标记 FAILED
              │           - 子 RUNNING + lease 新鲜 → 注册监听
              │           - 全 done → _trigger_main_resume
              └─ else: _trigger_main_retry (aggregation_chat is_retry_chat=True)
                    └─ step-level resume:
                          - _recovery_message 跳过 LLM (复用上次 assistant 消息)
                          - act 时查 cache.work_logs，命中 success → 跳过工具
```

### 4.4 权限 5 级链

```
ToolAction.run (tool_action.py)
  Level 1: PermissionMode (AUTO/PLAN/MANUAL)
           MANUAL → 直接 ASK
           PLAN + 写工具 → ASK
           AUTO → 放行
  Level 2: SessionCache (conv_id:tool_name:hash(args) → 复用决策)
  Level 3: Ruleset (base_agent.check_tool_permission)
  Level 4: Tool hook (_invoke_pre_tool_hook)
  Level 5: ASK → permission_checkpoint_store 落 DB → resume 时 replay
```

---

## 5. 横切关注点

### 5.1 状态机守卫 (`step_state_guard.py`)

- `SESSION_VALID_TRANSITIONS`: 8 个 Status 的合法转换表（RUNNING/WAITING/RETRYING/INTERRUPTED/BLOCKED/COMPLETE/FAILED + None→RUNNING）
- `MESSAGE_VALID_TRANSITIONS`: 消息级状态（TODO/RUNNING/COMPLETE/FAILED）
- `WARN_ONLY=True` 灰度（先 log warning 不抛错，观察一周后切 False）
- 守卫插入点：`agent_chat.py` 6 处 + `base_agent.py` 3 处
- Tier 3.4 模型检查（`test_state_machine_model_checking.py`）：
  - 静态结构检查（终态无 outgoing、非终态有 outgoing、无自环）
  - 随机游走 20 次 × 50 步，每次转换必须合法
  - BFS 终态可达性（每个非终态都能到达 COMPLETE/FAILED）
  - 死锁检测（无 outgoing 的非终态）

### 5.2 心跳 + Lease

| 机制 | 实现 | 阈值 |
|------|------|------|
| 心跳 | `touch_heartbeat(conv_id)` fire-and-forget，inline 在 loop 自然进度点（think 前/act 前后） | — |
| Lease | `worker_id + lease_expires_at`，原子条件 UPDATE（`worker_id IS NULL OR lease_expires_at < now`） | TTL=90s |
| 陈旧判断 | `is_stale(last_heartbeat, threshold=90s)` | 90s |
| 防御性退化 | 列不存在时 `acquire_lease` 返回 False，回退心跳判断 | — |

设计原则：心跳不是独立 task，而是 inline 在 agent loop 自然进度点。这样：
- loop 正常跑 → 心跳自然新鲜
- 进程崩溃 / kill -9 → 心跳停止更新 → 重启时检测到陈旧 → 恢复

### 5.3 事件日志（Tier 3.1）

- 表：`gpts_events(id, conv_id, message_id, sequence, event_type, event_data, gmt_create)`
- 事件类型常量（`event_log.py`）：
  - `EVENT_THINK_START` / `EVENT_THINK_END`
  - `EVENT_ACT_START` / `EVENT_ACT_END`
  - `EVENT_TURN_START` / `EVENT_TURN_END`
  - `EVENT_CONVERSATION_START` / `EVENT_CONVERSATION_END`
- `emit_event(conv_id, event_type, ...)` fire-and-forget，无 event loop 时静默跳过
- `EventLogDao.append_event` 自动分配 sequence = max + 1
- 公开查询接口：`GptsMemory.load_event_log(conv_id, since_sequence=0)`

### 5.4 Hook 分层 (`hook_context_builders.py`)

4 个统一构造函数：

- `build_pre_tool_use_context(tool_name, tool_input, conv_id, agent_id, user_code)`
- `build_post_tool_use_context(tool_name, tool_input, tool_output, tool_success, conv_id, agent_id)`
- `build_turn_complete_context(conv_id, agent_id, turn_index, final_message)`
- `build_conversation_complete_context(conv_id, agent_id, total_turns, total_tokens)`

`tool_action.py` 和 `base_agent.py` 调用这些函数构造 hook 上下文，统一字段，提升一致性 + 可测性。

### 5.5 ToolFailureTracker (`tool_failure_tracker.py`)

- 每个会话独立 `ToolFailureTracker` 实例（在 `ConversationCache`）
- `record_failure(tool_name, error)` → 连续失败 +1
- `record_success(tool_name)` → 失败计数清零
- `is_disabled(tool_name)` → 检查是否在 cooldown 期内
- 默认配置：`max_consecutive_failures=5`，`cooldown_seconds=300`

集成点（`react_master_agent.act`）：工具执行前 `is_disabled` → 跳过并返回错误；执行后 `record_success/failure`。

### 5.6 Usage Metric (`usage_metric.py` + `model_pricing.py`)

- `emit_usage_metric(conv_id, model_name, prompt_tokens, completion_tokens, role)` 写入 in-memory buffer + `gpts_messages.metrics`
- `aggregate_usage(conv_id) -> ConversationUsage` 聚合：
  - `total_prompt_tokens / total_completion_tokens / total_tokens`
  - `total_cost_usd`（按 `model_pricing` 表估算）
  - `by_model: Dict[str, int]` / `by_role: Dict[str, int]`（main/subagent）
- 集成点：`base_agent.generate_reply` 在 LLM 流式结束后调用

---

## 6. 数据持久化

| 表 | 用途 | 关键字段 |
|----|------|---------|
| `gpts_conversations` | 会话 | `state` + `last_heartbeat` + `worker_id` + `lease_expires_at` + `extra`(JSON, 含 `pending_subagents`) |
| `gpts_messages` | 每轮 LLM 输入输出 | `rounds/content/thinking/tool_calls/observation/action_report/metrics` |
| `gpts_work_log` | 每个工具调用 | `tool/args/result/success/status/tool_call_id/message_id` |
| `gpts_events` (新) | 事件审计日志 | `conv_id/message_id/sequence/event_type/event_data` |
| `permission_checkpoints` (新) | ASK 决策持久化 | `conv_id/tool_name/input_hash/decision/reason/timestamp` |

迁移 SQL：`assets/schema/upgrade_v1_governance.sql`（幂等，包含 `last_heartbeat` / `worker_id` / `lease_expires_at` 列 + `gpts_events` 表）。

---

## 7. 部署形态

### 单进程
- 心跳 + 子 agent async 都在主进程跑
- RecoveryDaemon 启动时扫描 RUNNING 会话

### 多进程
- Lease 机制确保同一会话同一时刻只有一个 worker 在跑
- 其他 worker 检测到 lease 新鲜 → 跳过（不重复拉起）
- 心跳新鲜但 lease 过期（边缘 case）→ 尝试 takeover

### 分布式子 Agent（未来）
- `SubagentCoordinator` 设计成可插拔 backend
- 当前实现 `LocalSubagentBackend`（单进程 `asyncio.create_task`）
- 未来加 `DistributedSubagentBackend` 通过 RPC 队列派发到其他机器
- 调用方代码不变，未来切 backend 只改注入

---

## 8. 关键文件清单

### 新增代码（src）

| 文件 | 用途 |
|------|------|
| `derisk-core/src/derisk/agent/core/step_state_guard.py` | 状态机守卫 + IllegalTransitionError |
| `derisk-core/src/derisk/agent/core/subagent_handle.py` | SubAgentHandle / SubAgentMode / SubAgentStatus |
| `derisk-core/src/derisk/agent/core/resource_utils.py` | extract_resource_map |
| `derisk-core/src/derisk/agent/core/event_log.py` | emit_event + 便捷函数 |
| `derisk-core/src/derisk/agent/core/heartbeat_hook.py` | touch_heartbeat (core 层) |
| `derisk-core/src/derisk/agent/core/hook_context_builders.py` | 4 个 build_*_context |
| `derisk-core/src/derisk/agent/core/permission_mode.py` | PermissionMode 枚举 |
| `derisk-core/src/derisk/agent/core/permission_checkpoint_store.py` | ASK 决策持久化 |
| `derisk-core/src/derisk/agent/core/tool_failure_tracker.py` | 工具熔断追踪 |
| `derisk-core/src/derisk/agent/core/usage_metric.py` | ConversationUsage + emit/aggregate |
| `derisk-core/src/derisk/agent/core/model_pricing.py` | 模型定价表 |
| `derisk-serve/src/derisk_serve/agent/heartbeat.py` | lease (acquire/renew/release) |
| `derisk-serve/src/derisk_serve/agent/recovery_daemon.py` | RecoveryDaemon |
| `derisk-serve/src/derisk_serve/agent/subagent_coordinator.py` | SubagentCoordinator |
| `derisk-serve/src/derisk_serve/agent/db/gpts_events_db.py` | EventLogDao + GptsEventEntity |
| `assets/schema/upgrade_v1_governance.sql` | DB migration |

### 修改的主链路

| 文件 | 改动 |
|------|------|
| `agent_chat.py` | V2 入口关闭 + lease acquire/release + WAITING 决策（pending_subagents）+ RecoveryDaemon 注册 |
| `base_agent.py` | 状态守卫（3 处）+ 心跳（generate_reply while 顶部 + act 前后）+ 事件埋点（think_start/end + act_start/end）+ step resume（recovering 标记）+ tracker（record_success/failure）+ usage emit |
| `react_master_agent.py` | act 事件埋点 + 心跳 + step-level resume（查 work_log 短路） |
| `actions/agent_action.py` | SubAgent 重命名 + sync/async 模式 + 深度守卫 + 自模板（agent_id 可选）+ extract_resource_map 复用 |
| `actions/tool_action.py` | 5 级权限链 + hook builders + tracker is_disabled 检查 |
| `resource/app.py` | `_start_app` 接 `parent_depth` 参数 |
| `memory/gpts/gpts_memory.py` | `load_persistent_memory` 加 work_log + `load_event_log` + `replay_events` 选项 |

### 测试（tests）

| 文件 | 覆盖 |
|------|------|
| `test_step_state_guard.py` | 合法/非法转换 + WARN_ONLY 行为 |
| `test_state_machine_model_checking.py` | 随机游走 + BFS 可达性 + 死锁检测 |
| `test_event_log.py` | emit_event fire-and-forget + EventLogDao |
| `test_act_think_event_hooks.py` | act/think 事件埋点 + import 路径 |
| `test_event_log_replay.py` | load_event_log + replay_events 选项 |
| `test_step_level_resume.py` | retry 时复用 work_log |
| `test_sub_agent_tool.py` | sync/async + 深度守卫 + 自模板 |
| `test_subagent_coordinator.py` | register/done/failed + recover_main |
| `test_lease.py` | acquire/renew/release + 防御性退化 |
| `test_heartbeat_recovery.py` | 心跳陈旧判断 + RecoveryDaemon |
| `test_start_app_depth.py` | parent_depth → child AgentContext.extra |
| `test_v1_governance_e2e.py` | 完整 async 子 agent 流程 + 完整崩溃恢复流程 |
| `test_hook_context_builders.py` | 4 个 builder 字段校验 |
| `test_permission_5_level_chain.py` | 5 级链完整流程 |
| `test_tool_failure_tracker.py` | 连续失败熔断 + cooldown |
| `test_usage_metric.py` | emit/aggregate + cost 估算 |

V1 governance 测试总计：**234 passed**

---

## 9. 已知边界 / 未来工作

- **WARN_ONLY 灰度**：状态机守卫目前 `WARN_ONLY=True`，观察一周日志无误报后切 `False`
- **MAX_SUBAGENT_DEPTH=5**：先灰度，确认无正常场景触发，再考虑收紧
- **分布式子 Agent**：接口已预留（`SubagentCoordinator` 可插拔 backend），未来加 `DistributedSubagentBackend` 通过 RPC 队列派发到其他机器。本次只实现 `LocalSubagentBackend`
- **LLM 流式 token 级 resume**：未做（成本一次 LLM 调用，不值得为这个持久化 partial stream）
- **V2 框架**：代码 + 测试保留作参考，不演进、不修 SSE bug、不补 vis_protocol、不补 workspace 事件
- **预存失败**：`test_history_compaction`、`test_sandbox_tool_v2` 等 160 个 baseline 失败是历史问题，与 V1 治理无关

---

## 10. 验证手段

### 单元测试
```bash
python -m pytest packages/derisk-core/tests/agent/core/test_step_state_guard.py
python -m pytest packages/derisk-core/tests/agent/core/test_state_machine_model_checking.py
python -m pytest packages/derisk-core/tests/agent/core/test_event_log.py
python -m pytest packages/derisk-core/tests/agent/core/test_act_think_event_hooks.py
python -m pytest packages/derisk-core/tests/agent/core/memory/test_event_log_replay.py
python -m pytest packages/derisk-core/tests/agent/core/memory/test_step_level_resume.py
python -m pytest packages/derisk-core/tests/agent/expand/actions/test_sub_agent_tool.py
python -m pytest packages/derisk-serve/tests/derisk_serve/agent/test_lease.py
python -m pytest packages/derisk-serve/tests/derisk_serve/agent/test_heartbeat_recovery.py
python -m pytest packages/derisk-serve/tests/derisk_serve/agent/test_subagent_coordinator.py
python -m pytest packages/derisk-serve/tests/derisk_serve/agent/test_start_app_depth.py
python -m pytest packages/derisk-serve/tests/derisk_serve/agent/test_v1_governance_e2e.py
```

### 回归
```bash
python -m pytest packages/derisk-core/tests/agent/ packages/derisk-serve/tests/derisk_serve/agent/ --no-header -q
```

### 端到端手动验证
1. **状态机**：构造 COMPLETE → RUNNING，确认 `IllegalTransitionError`（或 WARN_ONLY 下的 warning）
2. **子 Agent**：
   - 主 agent 调 2 个 `sub_agent(mode="sync")` → 同步等结果
   - 主 agent 调 2 个 `sub_agent(mode="async")` → 主 WAITING → 子后台跑完 → 主自动 resume
   - 主 agent 调 `sub_agent(agent_id=None)` → 用当前 agent 模板 spawn
   - 递归 `sub_agent` → depth=5 时抛 `SubagentDepthExceededError`
3. **step resume**：3 轮工具对话，第 2 轮后模拟崩溃，重启 retry，前 2 轮工具跳过、第 3 轮正常跑
4. **崩溃恢复**：
   - 主 agent 中途 kill -9，重启进程，自动恢复
   - 主 + 2 个 async 子 agent，子中途 kill -9，重启确认子 FAILED + 主 resume with error
   - 双进程跑同一 conv_id，第二个检测到 lease 新鲜、不重复拉起
5. **权限**：配 `permission_mode=MANUAL` 每次工具调用都 ASK；配 `AUTO` 全放行
6. **熔断**：配 `max_consecutive_failures=3`，工具连失 3 次后第 4 次被熔断；等 cooldown 过期解除
7. **Usage**：跑 2 轮对话，`aggregate_usage(conv_id)` 返回 total_tokens = 两次 LLM 调用之和

---

## 11. V2 处置

- **关生产入口**：`agent_chat.py:2628-2629` 的 `if gpts_app.agent_version == "v2":` 分支已删除
- **保留代码**：`packages/derisk-core/src/derisk/agent/core/v2/` 不删，151/151 测试保留
- **不主动演进**：不修 SSE bug，不补 vis_protocol，不补 workspace 事件
- **设计文档归档**：`docs/superpowers/specs/2026-07-02-v2-agent-framework-successor-design.md` 标"参考设计"
- **V2 价值评估**：经核实，V2 的所有优势（状态机 / 崩溃恢复 / 权限 / 子 Agent / Hook 分层）都能在 V1 上纯加法实现。V2 不再有独立生产价值，保留作设计参考和测试资产

---

## 变更历史

| 日期 | 版本 | 内容 |
|------|------|------|
| 2026-07-06 | v1.0 | 首版：V1 治理 8 PR + Tier 3 + 5 gap 修复全部完成，234 测试通过 |
