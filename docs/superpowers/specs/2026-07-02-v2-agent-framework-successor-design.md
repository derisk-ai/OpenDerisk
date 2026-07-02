# V2 Agent 框架继任设计：从内核到完整框架

- 日期：2026-07-02
- 状态：v2 — 满配承接验证后修订（补 6 项 GAP，推翻决策 #4），待写入实施计划
- 作者：yhjun1026 + Claude
- 前置 spec：`docs/superpowers/specs/2026-06-30-agent-framework-evolution-design.md`（V2 内核，P2-P4 已完成）
- 关联文件：
  - V2 内核：`packages/derisk-core/src/derisk/agent/core/v2/`
  - BAIZE 主壳（待瘦身/删除）：`packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py`（3619 行）
  - BAIZE 主循环（待瘦身/删除）：`packages/derisk-core/src/derisk/agent/core/base_agent.py::generate_reply`（~430 行）
  - 子系统（原样复用）：
    - `packages/derisk-core/src/derisk/agent/expand/react_master_agent/context_engine/`（ContextEngine）
    - `packages/derisk-core/src/derisk/agent/core/memory/longterm_manager.py`（LongTermMemoryManager）
    - `packages/derisk-core/src/derisk/agent/core/memory/read_pipeline.py`（MemoryReadPipeline）
    - `packages/derisk-core/src/derisk/agent/tools/`（ToolBase/ToolResult/ToolRegistry）
    - `packages/derisk-core/src/derisk/agent/expand/react_master_agent/doom_loop_detector.py`
    - `packages/derisk-core/src/derisk/agent/expand/react_master_agent/truncation.py`
    - `packages/derisk-core/src/derisk/agent/expand/react_master_agent/work_log.py`
    - `packages/derisk-core/src/derisk/agent/expand/react_master_agent/cold_persistence.py`

---

## 1. 背景：V2 内核已就绪，但不是完整框架

### 1.1 P2-P4 已完成的工作

前置 spec（2026-06-30）定义并实现了 V2 runtime **内核**：
- `StepState` 枚举 + `VALID_TRANSITIONS` 状态机
- `StepEvent` + `StateStore`（SQLite event sourcing）+ `RecoveryCoordinatorV2`
- `PermissionGate`（5 级链：Mode / SessionCache / Ruleset / Tool hook / ASK 持久化）
- `SubAgentRuntime` + `agent_transcript` 表 + 崩溃重建
- `StreamEvent` + `step_event_to_stream_event` + `stream_to_sse`
- `BAIZESubsystemAdapter`（桥接 BAIZE 子系统事件）
- `usage_metric`（实时 token 可观测性）

151/151 测试通过。`scripts/v2_demo.py` 验证全链路（run_step → SSE → resume → subagent）跑通。

### 1.2 V2 内核的真实定位

V2 内核只覆盖了 BAIZE 的"管道层"（状态机 / 恢复 / 权限 / 子 agent / SSE）。BAIZE 真正的 agent 能力（多轮 loop / 上下文管理 / 记忆 / 工具 / retry / doom-loop）V2 一项都没有。

**审计对比（基于 `Agent` 调研报告）：**

| 维度 | BAIZE | V2 内核 | 差距 |
|---|---|---|---|
| 状态机 | 散落 bool flag | `StepState` + 矩阵 | V2 赢 |
| 崩溃恢复 | 子系统各自 load | event sourcing + resume_step + lease + checkpoint | V2 赢 |
| 权限 | 单层 Ruleset | 5 级链 + 持久化 ASK | V2 赢 |
| 子 agent | AsyncTaskManager，无崩溃恢复 | SubAgentRuntime + transcript 重建 | V2 赢 |
| 多轮 loop | `generate_reply` while 循环 | **缺失** | BAIZE 赢 |
| 上下文管理 | ContextEngine + CompactionPipeline + Truncator | **缺失** | BAIZE 赢 |
| 记忆 | LongTermMemoryManager + MemoryReadPipeline | **缺失** | BAIZE 赢 |
| 工具系统 | ToolBase + 四路查找 + ToolAction 编排 | dict acting_fn | BAIZE 赢 |
| retry / doom-loop | _tool_failure_counts + DoomLoopDetector + MAX_ATTEMPTS | **缺失** | BAIZE 赢 |
| Hook 系统 | HookManager（共享） | 复用 HookManager | 平 |
| Vis/SSE | VisProtocolConverter | 复用 + typed StreamEvent | 平 |
| 可观测性 | tracer spans + stats | usage_metric 事件 | 互补 |

**结论：V2 停在内核层 = 不值得做。** 用户的质疑成立："搞一个 V2 啥功能都没有，一直说架构优秀，没看出优秀在哪。"

### 1.3 本 spec 的目标

把 V2 从"内核"升级为"完整的 agent 构建框架"，作为 BAIZE 框架的**继任者**：
- 把 BAIZE 的子系统（ContextEngine / Memory / Tools / DoomLoop / Retry）原样搬进 V2
- 新写 `run_loop`（多轮循环，瘦身版的 BAIZE `generate_reply`）
- 提供默认的 `default_acting_fn` / `default_thinking_fn`，让 agent 实例开箱即用
- 产品层加 `runtime_version` 字段，过渡期 BAIZE / V2 并存对比测试
- 验证通过后删除 BAIZE 主壳（`react_master_agent.py` / `generate_reply`），V2 成为唯一框架

---

## 2. 设计原则（约束）

本设计受两个硬约束：

### 2.1 不要过渡设计

V2 是 BAIZE 的继任者，不是并列第二套：
- 验证完直接删 BAIZE，不留 adapter / bridge / 兼容层
- 子系统**原样搬**，不重新设计抽象
- 不做"runtime 可插拔"（就一个 V2 runtime）
- 不做"模板系统"（agent 实例就是配置，不是模板）
- V2 内核 dict 接口**不改**（不原生化 ToolCall/ToolResult）—— 翻译在 default_acting_fn 里，避免改 P2-P4 测试

### 2.2 必须是完整产品能力

不能是脚本测试代码：
- 在 Agent 编辑页面能新增 V2 agent 实例
- 能在产品里跑（聊天、工具、权限 ASK、子 agent、崩溃恢复）
- 过渡期能和 BAIZE agent 并存做对比测试
- 前端 SSE 协议复用，无前端改动

### 2.3 V2 是框架，不是具体 agent

V2 是 agent 构建框架（继任 BAIZE 框架），不是某一个具体 agent：
- 框架提供 `run_loop` + 子系统默认集成，所有 agent 实例共用
- Agent 实例通过**配置**差异化：system prompt / tools / permissions / memory_space
- 基于 V2 框架可以构建：V2 Agent（对比测试用）、Code Agent、数据分析 Agent 等
- 配置维度对齐 BAIZE 的 `agent_info`，让迁移成本 = 改 `runtime_version` 字段

---

## 3. 范围

### 3.1 本 spec 覆盖（11 项，v2 修订）

1. **`run_loop`**：多轮循环，包 `run_step`，带 retry/termination/turn 边界
2. **`default_acting_fn`**：默认工具执行实现（resolve → gate → doom → hook → tracker → execute → truncate）
3. **`default_thinking_fn`**：默认 LLM thinking 实现（ContextEngine + Memory 注入 + scrubber + MAX_ATTEMPTS 装饰器）
4. **子系统搬运**：ContextEngine / Memory / Tools / DoomLoop / Retry 原样集成，无 adapter
5. **产品入口**：`runtime_version` 字段 + 后端分发 + Agent 编辑页面支持
6. **V2 内核原生化 ToolCall/ToolResult/ToolContext**（v2 新增）：acting_fn 签名从 dict 改为原生类型，让 BAIZE 语义干净映射；改 P2-P4 测试
7. **ToolContext 完整 schema**（v2 新增）：加 `scene/scenario_id/language`；明确 `set_resource/get_resource` 注入契约；承载沙箱活句柄
8. **`tool_context_factory` 规范**（v2 新增）：从 `resource_map` 派发 DBResource / RetrieverResource / SandboxManager.client 到 ToolContext
9. **资源→工具自动注入机制**（v2 新增）：等价 BAIZE `_inject_resource_based_tools` + `sandbox_tool_injection` + `_inject_async_task_tools`
10. **HookManager 集成**（v2 新增，推翻原决策 #4）：pre/post_tool_use + turn/conversation_complete hook；memory tier1/2/3 挂回 hook
11. **子 Agent shared_conv 模式**（v2 新增）：SubAgentRuntime 支持"共享父 conv_id"选项，等价 BAIZE AgentStart 语义

### 3.2 本 spec 不覆盖（明确排除）

- ~~adapter / bridge 抽象层~~ —— 子系统直接调
- ~~模板系统 / agent 工厂~~ —— agent 实例就是配置
- ~~runtime 可插拔~~ —— 就一个 V2 runtime
- ~~`UnifiedCompactionPipeline` L2/L3/L4~~ —— ContextEngine 已覆盖，只保留 L1（truncate_output）

### 3.3 v2 修订说明（相对 v1）

v1 spec（已提交）的决策 #4"跳过 HookDispatcher，直接调 manager 方法"在满配 BAIZE agent 承接验证下被推翻。满配 agent 的 `pre_tool_use`/`post_tool_use`/审计/合规/非 memory turn hook 在 v1 决策下全部丢失。

v2 修订基于"满配 BAIZE agent 无丢失承接"验证（见附录 B），补 6 项 GAP：
- G2: Skill 工具签名迁移到 ToolContext
- G3: 资源→工具自动注入机制
- G4: ToolContext.set_resource/get_resource 注入点
- G5: 子 Agent shared_conv 模式
- G7: 沙箱活句柄注入路径
- G8/G9: HookManager 集成（推翻决策 #4）

### 3.4 后续 spec 覆盖（验证通过后）

- 删除 `react_master_agent.py`（3619 行）
- 删除 `base_agent.generate_reply` if/else 主循环
- 删除旧 `AgentMemory` / `LongTermMemory`（`long_term.py`，已 stub）
- 删除 `UnifiedCompactionPipeline` L2/L3/L4
- 把现有 BAIZE agent 实例配置迁移到 V2

---

## 4. 架构总览

### 4.1 分层

```
┌─────────────────────────────────────────────────────────┐
│  产品层：Agent 编辑页面 / SSE 端点 / AgentChat          │
│  runtime_version: "v1" (BAIZE) | "v2" (V2)              │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
┌──────────────────┐    ┌──────────────────────────────┐
│  BAIZE 框架      │    │  V2 框架（本 spec）          │
│  ReActMasterAgent│    │  run_loop                    │
│  generate_reply  │    │  default_thinking_fn         │
│  （过渡期保留）  │    │  default_acting_fn           │
│                  │    │  + 子系统原样集成            │
└──────────────────┘    └──────────────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ V2 内核  │  │ Context  │  │ Memory   │
        │ (P2-P4)  │  │ Engine   │  │ Manager  │
        │ run_step │  │ (搬)     │  │ (搬)     │
        └──────────┘  └──────────┘  └──────────┘
                ┌─────────────┬─────────────┐
                ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ Tools    │  │ DoomLoop │  │ Truncate │
        │ (搬)     │  │ (搬)     │  │ (搬)     │
        └──────────┘  └──────────┘  └──────────┘
```

### 4.2 V2 框架的组成

V2 框架 = V2 内核（已有，需原生化改造）+ 11 个新模块：

| 模块 | 位置 | 职责 | v2 状态 |
|---|---|---|---|
| `run_loop` | `v2/run_loop.py`（新） | 多轮循环，调 `run_step` 直到终止 | v1 已设计 |
| `default_thinking_fn` | `v2/default_thinking.py`（新） | LLM 调用 + ContextEngine + Memory 注入 + scrubber + MAX_ATTEMPTS | v1 已设计 |
| `default_acting_fn` | `v2/default_acting.py`（新） | 工具解析 → gate → doom → **hook** → tracker → execute → truncate | v2 加 hook |
| `tool_failure_tracker` | `v2/tool_failure_tracker.py`（新） | 从 BAIZE `_tool_failure_counts` 抽出 | v1 已设计 |
| `retrying_thinking` | `v2/retrying_thinking.py`（新） | MAX_ATTEMPTS 装饰器 | v1 已设计 |
| `tool_resolver` | `v2/tool_resolver.py`（新） | 四路查找 + Resource pack 递归 + 资源→工具自动注入 | v2 扩展 |
| `tool_context_factory` | `v2/tool_context_factory.py`（新） | 从 resource_map 构造 ToolContext，注入活资源句柄 | **v2 新增** |
| `hook_integration` | `v2/hook_integration.py`（新） | 集成 HookManager：pre/post_tool_use + turn/conversation_complete | **v2 新增** |
| `subagent_shared_conv` | `v2/subagent_shared_conv.py`（新） | SubAgentRuntime 加 shared_conv 模式，等价 AgentStart 语义 | **v2 新增** |
| `ToolCall` / `ToolResult` / `ToolContext` 原生化 | `v2/runtime.py` 改签名 | acting_fn 原生收 ToolCall 返 ToolResult | **v2 新增** |
| `skill_migration` | 工具改造（非新模块） | Skill / skill-aware 工具从 kwargs 迁到 ToolContext | **v2 新增** |

### 4.3 数据流（单 turn）

```
用户消息
  ↓
run_loop（外层）
  │
  ├─ 初始化：load MemoryReadPipeline / static_block
  │
  ├─ loop step（多次，直到 LLM 不再 emit tool_calls 或 terminate）:
  │    │
  │    ├─ run_step（V2 内核）
  │    │    │
  │    │    ├─ INIT → THINKING
  │    │    │    ├─ default_thinking_fn
  │    │    │    │    ├─ consume_prefetch（上一轮预取）
  │    │    │    │    │   或 sync retrieve_relevant_memories
  │    │    │    │    ├─ build_memory_context_block
  │    │    │    │    ├─ ContextEngine.build_messages
  │    │    │    │    ├─ LLM stream（MAX_ATTEMPTS=3 + 模型降级）
  │    │    │    │    ├─ StreamingContextScrubber 清洗
  │    │    │    │    └─ yield token / tool_calls / usage
  │    │    │    │
  │    │    ├─ ACTING（若有 tool_calls）
  │    │    │    ├─ PermissionGate.check（5 级链）
  │    │    │    ├─ DoomLoopDetector.check
  │    │    │    ├─ ToolFailureTracker.is_blocked
  │    │    │    ├─ ToolResolver.resolve → ToolBase.execute
  │    │    │    ├─ Truncator.truncate（L1，超阈值归档到 AFS）
  │    │    │    ├─ ToolFailureTracker.record（成功 reset / 失败 +1）
  │    │    │    └─ emit tool_result → OBSERVING
  │    │    │
  │    │    └─ DONE
  │    │
  │    └─ 判断是否继续 loop（LLM 无 tool_calls / terminate / 失败）
  │
  ├─ turn 结束：
  │    ├─ fire-and-forget prefetch（下一轮 memory）
  │    ├─ manager.write_turn_lightweight（Tier 1）
  │    └─ 若 round % N == 0 → manager.reflect_on_last_n_turns（Tier 2）
  │
  └─ conversation 结束（用户主动 / terminate）：
       └─ manager.curate_session（Tier 3）
```

---

## 5. 详细设计

### 5.1 `run_loop`

**位置：** `packages/derisk-core/src/derisk/agent/core/v2/run_loop.py`（新文件）

**职责：** 多轮循环，调 `run_step` 直到终止条件。

**签名：**
```python
async def run_loop(
    agent_id: str,
    conv_id: str,
    input_: dict,  # {"prompt": str, "session_id": str, "system_prompt": str, "scene": str, ...}
    state_store: StateStore,
    thinking_fn: ThinkingFn,  # 通常用 default_thinking_fn
    acting_fn: Optional[ActingFn] = None,  # 通常用 default_acting_fn
    *,
    parent_step_id: Optional[str] = None,
    permission_gate: Optional[PermissionGate] = None,
    subagent_runtime: Optional[SubAgentRuntime] = None,
    hook_manager: Optional[HookManager] = None,  # v2 新增：替代 on_turn_complete 回调
    max_steps: int = 20,  # 防止无限循环
) -> AsyncGenerator[StepEvent, None]:
```

**主循环逻辑（瘦身版的 BAIZE `generate_reply`）：**
```python
step_count = 0
turn_context = TurnContext(round=0, user_prompt=input_["prompt"], ...)

async for step_event in run_step(...):
    yield step_event
    if step_event.state == StepState.DONE:
        step_count += 1
        if step_event.event_type == "step_done":
            had_tool_calls = step_event.output.get("had_tool_calls", False)
            terminated = step_event.output.get("terminate", False)
            if not had_tool_calls or terminated or step_count >= max_steps:
                # turn 结束 — v2 改：触发 HookManager，不直接调 memory
                turn_context.final_answer = step_event.output.get("answer")
                turn_context.round += 1
                if hook_manager:
                    await hook_manager.trigger(
                        "turn_complete", turn_context.to_dict())
                break
    elif step_event.state == StepState.FAILED:
        if hook_manager:
            await hook_manager.trigger("error_occurred", {...})
        break
    elif step_event.state in (StepState.AWAITING_USER, StepState.AWAITING_TOOL_PERMISSION):
        # 暂停，等用户/权限响应；turn_context.interrupted = True
        turn_context.interrupted = True
        return

# conversation 结束（run_loop 调用方触发，或 terminate）
async def on_conversation_complete():
    if hook_manager:
        await hook_manager.trigger("conversation_complete", {...})
```

**关键设计：**
- **无 if/else 地狱**：用 `StepState` 驱动，状态机已经定义好
- **max_steps 防失控**：默认 20，可配置
- **turn / conversation 生命周期走 HookManager**（v2 修订）：memory tier1/2/3 + 审计 + 日志 + 自定义 hook 都挂 HookManager，run_loop 只触发 `turn_complete` / `conversation_complete` / `error_occurred` 事件
- **TurnContext 严格对齐 BAIZE**（G6）：字段 `round / interrupted / user_prompt / final_answer / user_id / conv_id / agent_id / step_count`，对齐 `base_agent.py:1327-1355`，否则 memory tier2 的 `every_n_turns` 逻辑失效
- **崩溃恢复**：`run_loop` 本身无状态，所有状态在 `StateStore`，崩溃后 `resume_step` 续上

### 5.2 `default_thinking_fn`

**位置：** `packages/derisk-core/src/derisk/agent/core/v2/default_thinking.py`（新文件）

**职责：** LLM 调用 + 上下文构建 + 记忆注入 + scrubber + retry。

**工厂签名：**
```python
def make_default_thinking_fn(
    *,
    llm_client,  # derisk_llm 客户端
    model_alias: str,  # 如 "baize-ui"，复用 BAIZE 模型配置
    context_engine: ContextEngine,  # 注入
    memory_bundle: Optional[MemoryIntegrationBundle] = None,  # 注入
    max_attempts: int = 3,  # MAX_ATTEMPTS
    model_fallback: Optional[Callable[[str], str]] = None,  # 模型降级
) -> ThinkingFn:
    async def thinking_fn(input_: dict) -> AsyncGenerator[dict, None]:
        ...
    return thinking_fn
```

**`thinking_fn` 内部流程：**
```python
async def thinking_fn(input_: dict):
    user_prompt = input_["prompt"]
    conv_id = input_["conv_id"]
    session_id = input_["session_id"]

    # 1. Memory 注入（dynamic）
    memory_context = ""
    if memory_bundle:
        pipeline = memory_bundle.pipeline
        result = await pipeline.consume_prefetch(timeout=0.0)
        if result is None:
            # sync fallback
            result = await memory_bundle.manager.retrieve_relevant_memories(
                query=user_prompt, exclude_rooms=STATIC_ROOMS)
        memory_context = build_memory_context_block(result)

    # 2. ContextEngine 构建 messages
    messages = await gpts_memory.get_session_messages(session_id)
    work_logs_by_conv = {conv_id: await gpts_memory.get_work_log(conv_id)}
    context_window = await get_agent_llm_context_length(model_alias)
    build_out = await context_engine.build_messages(
        messages, work_logs_by_conv, conv_id, session_id, context_window)

    # 3. 拼最终 LLM messages（system + memory + build_out.messages + user_prompt）
    llm_messages = assemble_llm_messages(
        system_prompt=input_.get("system_prompt"),
        memory_context=memory_context,
        history=build_out.messages,
        user_prompt=user_prompt,
    )

    # 4. LLM 流式调用（带 MAX_ATTEMPTS + 模型降级）
    async for chunk in retrying_thinking(
        llm_client, llm_messages, model_alias,
        max_attempts=max_attempts, model_fallback=model_fallback,
    ):
        # chunk = {"token": ..., "usage": ..., "tool_calls": ...}
        # 5. Scrubber 清洗 token
        if "token" in chunk and chunk["token"] and memory_bundle:
            chunk["token"] = memory_bundle.pipeline.scrub_stream_delta(chunk["token"])
        yield chunk
```

**关键设计：**
- **ContextEngine 直接调** —— 无 adapter，30 行胶水
- **Memory 直接调** —— `consume_prefetch` / `retrieve_relevant_memories` / `scrub_stream_delta`，跳过 HookDispatcher
- **MAX_ATTEMPTS 装饰器** —— `retrying_thinking` 包装 LLM stream，3 次失败 + 模型降级
- **dict chunk 输出** —— 保持 V2 内核 dict 接口不变，thinking_fn 内部把 LLM delta 转成 `{"token": ..., "usage": ..., "tool_calls": [...]}`

### 5.3 `default_acting_fn`（v2 原生化 + HookManager 集成）

**位置：** `packages/derisk-core/src/derisk/agent/core/v2/default_acting.py`（新文件）

**职责：** 工具解析 → doom → 失败跟踪 → pre_tool_use hook → 执行 → post_tool_use hook → 截断。

**v2 修订：acting_fn 签名原生化（G4 + G8）**
```python
# v1: async def acting_fn(tool_call: dict) -> dict
# v2:
async def acting_fn(tool_call: ToolCall, context: ToolContext) -> ToolResult:
    ...
```

V2 内核 `runtime.py` 的 `_run_acting_phase` 同步改签名（P2-P4 测试相应改）。

**工厂签名：**
```python
def make_default_acting_fn(
    *,
    tool_resolver: ToolResolver,
    doom_loop_detector: DoomLoopDetector,
    failure_tracker: ToolFailureTracker,
    truncator: Truncator,
    hook_manager: Optional[HookManager] = None,  # v2 新增
    # 注意：permission_gate 不在工厂里，run_step 内核在 ACTING 前调
) -> ActingFn:
    async def acting_fn(tool_call: ToolCall, context: ToolContext) -> ToolResult:
        ...
    return acting_fn
```

**`acting_fn` 内部流程（v2）：**
```python
async def acting_fn(tool_call: ToolCall, context: ToolContext) -> ToolResult:
    tool_name = tool_call.name
    tool_input = tool_call.args

    # 1. DoomLoop 检测
    if not await doom_loop_detector.check(tool_name, tool_input):
        return ToolResult.fail(error="doom loop detected, blocked")

    # 2. 失败跟踪
    if failure_tracker.is_blocked(tool_name):
        return ToolResult.fail(error=f"工具 {tool_name} 连续失败超过阈值，已阻止")

    # 3. 解析工具（ToolResolver 四路查找 + Resource pack 递归）
    tool = tool_resolver.resolve(tool_name)
    if tool is None:
        return ToolResult.fail(error=f"工具 {tool_name} 未注册")

    # 4. pre_tool_use hook（v2 新增，G8）
    #    blocking：HookDecision 可能 MODIFY/DENY/ABORT
    if hook_manager:
        decision = await hook_manager.trigger_blocking(
            "pre_tool_use",
            {"tool_name": tool_name, "args": tool_input, "context": context})
        if decision.action == "DENY":
            return ToolResult.fail(error=f"hook denied: {decision.reason}")
        if decision.action == "MODIFY":
            tool_input = decision.modified_args
        if decision.action == "ABORT":
            return ToolResult.fail(error="hook aborted")

    # 5. 执行
    try:
        result: ToolResult = await tool.execute(tool_input, context=context)
    except Exception as e:
        failure_tracker.record_failure(tool_name)
        if hook_manager:
            await hook_manager.trigger("post_tool_use",
                {"tool_name": tool_name, "args": tool_input, "result": None,
                 "error": str(e), "context": context})
        return ToolResult.fail(error=f"执行异常: {e}")

    if not result.success:
        failure_tracker.record_failure(tool_name)
    else:
        failure_tracker.reset(tool_name)

    # 6. post_tool_use hook（v2 新增，G9，fire-and-forget）
    if hook_manager:
        await hook_manager.trigger("post_tool_use",
            {"tool_name": tool_name, "args": tool_input, "result": result,
             "context": context})

    # 7. 截断（L1，超阈值归档到 AFS）
    output_content = str(result.output)
    trunc_result = await truncator.truncate(output_content, tool_name, tool_input)
    if trunc_result.truncated:
        result.output = trunc_result.truncated_content  # 含 dattach tag

    return result
```

**关键设计：**
- **原生 ToolCall/ToolResult/ToolContext**（v2 修订）—— acting_fn 签名从 dict 改为原生类型，BAIZE 语义干净映射；P2-P4 测试相应改
- **HookManager 集成**（v2 修订，推翻决策 #4）—— pre_tool_use 在 execute 前调（blocking，可 MODIFY/DENY/ABORT），post_tool_use 在 execute 后调（fire-and-forget）
- **ToolResolver 收敛四路查找 + Resource pack 递归** —— 见 §5.6
- **Truncator 直接调** —— BAIZE 的 `truncation.py` 原样复用，写 AFS + dattach tag
- **失败跟踪 + doom loop 独立模块** —— 不耦合在 agent 类里

### 5.4 `ToolFailureTracker`

**位置：** `packages/derisk-core/src/derisk/agent/core/v2/tool_failure_tracker.py`（新文件）

**职责：** 从 BAIZE `_tool_failure_counts` 抽出，无 agent 反向依赖。

```python
class ToolFailureTracker:
    def __init__(self, max_failures: int = 3):
        self._counts: Dict[str, int] = {}
        self._max_failures = max_failures

    def record_failure(self, tool_name: str) -> bool:
        """返回是否达到阈值"""
        self._counts[tool_name] = self._counts.get(tool_name, 0) + 1
        return self._counts[tool_name] >= self._max_failures

    def is_blocked(self, tool_name: str) -> bool:
        return self._counts.get(tool_name, 0) >= self._max_failures

    def reset(self, tool_name: str):
        self._counts.pop(tool_name, None)
```

**来源：** `react_master_agent.py:2517-2575` 的 `_tool_failure_counts` / `_check_and_record_tool_failure` / `_is_tool_blocked` / `_reset_tool_failure_count`，5 分钟抽出。

### 5.5 `retrying_thinking`

**位置：** `packages/derisk-core/src/derisk/agent/core/v2/retrying_thinking.py`（新文件）

**职责：** 包装 LLM stream，MAX_ATTEMPTS=3 + 模型降级。

```python
async def retrying_thinking(
    llm_client,
    messages: List[dict],
    model: str,
    max_attempts: int = 3,
    model_fallback: Optional[Callable[[str], str]] = None,
) -> AsyncGenerator[dict, None]:
    last_model = model
    for attempt in range(max_attempts):
        try:
            async for chunk in llm_client.generate_stream(last_model, messages):
                yield chunk
            return  # 成功完成
        except Exception as e:
            if attempt + 1 >= max_attempts:
                raise
            if model_fallback:
                last_model = model_fallback(last_model)
            # 否则用原 model 重试
```

**来源：** `react_master_agent.py:1908-2044` 的 `llm_thinking` 内 MAX_ATTEMPTS 逻辑，抽出成独立 async generator。

### 5.6 `ToolResolver`（v2 加资源→工具自动注入）

**位置：** `packages/derisk-core/src/derisk/agent/core/v2/tool_resolver.py`（新文件）

**职责：**
1. 收敛 BAIZE 四路工具查找为单一 `resolve(name)`
2. **资源→工具自动注入**（v2 新增，G3）：根据 `resource_map` 类型自动注入对应工具，等价 BAIZE `_inject_resource_based_tools` + `sandbox_tool_injection` + `_inject_async_task_tools`

```python
class ToolResolver:
    def __init__(
        self,
        *,
        sandbox_tools: Dict[str, BaseTool] = None,  # sandbox_tool_dict
        system_tools: Dict[str, BaseTool] = None,   # system_tool_dict
        unified_registry=None,                       # tool_registry
        resource_pack=None,                          # agent.resource（MCP 工具）
        resource_map: Dict[str, List[Resource]] = None,  # v2 新增
        sandbox_manager=None,                        # v2 新增
        enable_async_subagent: bool = False,         # v2 新增
    ):
        self._tools: Dict[str, BaseTool] = {}
        self._assemble()

    def _assemble(self):
        """组装工具集，等价 BAIZE preload_resource 的工具注入逻辑"""
        # 1. 系统工具（system_tool_dict）
        if self._system_tools:
            self._tools.update(self._system_tools)

        # 2. 沙箱工具（仅当 sandbox_manager 存在，等价 sandbox_tool_injection）
        if self._sandbox_manager and self._sandbox_tools:
            self._tools.update(self._sandbox_tools)

        # 3. 统一注册表
        if self._unified_registry:
            for name in self._unified_registry.list_names():
                self._tools.setdefault(name, self._unified_registry.get(name))

        # 4. 资源→工具自动注入（等价 _inject_resource_based_tools）
        if self._resource_map:
            self._inject_resource_based_tools()

        # 5. 异步子 agent 工具（等价 _inject_async_task_tools）
        if self._enable_async_subagent:
            self._inject_async_subagent_tools()

    def _inject_resource_based_tools(self):
        """根据 resource_map 类型注入对应工具（G3）"""
        for resource_type, resources in self._resource_map.items():
            if resource_type == "AppResource":
                # 注入 AgentStart（或 V2 SubAgentRuntime shared_conv 模式）
                self._tools["AgentStart"] = make_agent_start_tool(resources)
            elif resource_type == "RetrieverResource":
                # 注入 KnowledgeSearch，绑定 RetrieverResource 引用
                self._tools["KnowledgeSearch"] = make_knowledge_search_tool(resources)
            elif resource_type == "DBResource":
                # 注入 execute_sql / list_tables / get_table_spec
                self._tools.update(make_db_tools(resources))

    def resolve(self, name: str) -> Optional[BaseTool]:
        # 优先从已组装工具集查
        if name in self._tools:
            return self._tools[name]
        # 兜底：递归查 Resource pack（MCP 工具）
        if self._resource_pack:
            return self._lookup_resource_pack(name)
        return None

    def list_tools_for_llm(self) -> List[dict]:
        """生成 LLM tool list，等价 BAIZE function_calling_params"""
        return [t.to_openai_tool() for t in self._tools.values()]
```

**关键设计：**
- **来源**：`tool_action.py:344-362` 四路查找 + `base_agent.py:837-889` `_inject_resource_based_tools` + `react_master_agent.py:283-399` `_inject_async_task_tools`
- **不改 BAIZE 的工具注册机制**，只是查找 + 注入收敛
- **资源→工具自动注入在 ToolResolver 构造时一次性完成**，run_loop 期间 ToolResolver 不变

### 5.7 `ToolContext` 完整 schema（v2 新增，G1 + G4 + G7）

**位置：** 复用 `packages/derisk-core/src/derisk/agent/tools/context.py`，扩展字段

**v2 扩展字段：**
```python
class ToolContext(BaseModel):
    # 身份（已有）
    agent_id: str
    agent_name: str
    conversation_id: str
    message_id: str

    # 用户（已有）
    user_id: str
    user_name: str
    user_permissions: List[str]

    # 执行环境（已有）
    working_directory: str
    environment_variables: Dict
    sandbox_config: Optional[SandboxConfig]

    # 追踪（已有）
    trace_id: str
    span_id: str
    parent_span_id: str

    # 配置（已有）
    config: Dict
    max_output_bytes: int = 50 * 1024
    max_output_lines: int = 50

    # Skill（已有）
    skill_dir: Optional[str]
    available_skills: Dict[str, str]

    # v2 新增 —— 场景信息（G1）
    scene: Optional[str] = None
    scenario_id: Optional[str] = None
    language: str = "zh"

    # v2 新增 —— step 元数据
    step_id: Optional[str] = None
    round_index: int = 0

    # 动态资源（已有，但 v2 明确注入契约）
    # 通过 set_resource(name, value) / get_resource(name) 访问
    # 私有属性存储：_{name}

    # v2 新增 —— 沙箱活句柄（G7）
    # 通过 set_resource("sandbox_client", client) 注入
    # 工具通过 get_resource("sandbox_client") 取

    # v2 新增 —— agent 引用（G4）
    # 通过 set_resource("agent", agent) 注入（仅工具需要反查 agent 时用）
    # 通过 set_resource("agent_file_system", afs) 注入
```

**`set_resource` / `get_resource` 注入契约（v2 明确，G4）：**
```python
def set_resource(self, name: str, value: Any) -> None:
    setattr(self, f"_{name}", value)

def get_resource(self, name: str) -> Optional[Any]:
    return getattr(self, f"_{name}", None)
```

**注入点：** `tool_context_factory` 构造 ToolContext 时，根据 `tool` 元数据决定注入哪些 resource（见 §5.8）。

### 5.8 `tool_context_factory`（v2 新增，G4 + G7）

**位置：** `packages/derisk-core/src/derisk/agent/core/v2/tool_context_factory.py`（新文件）

**职责：** 根据 `tool_call` + `resource_map` + `sandbox_manager` 构造 ToolContext，注入活资源句柄。

```python
class ToolContextFactory:
    def __init__(
        self,
        *,
        agent_id: str,
        conv_id: str,
        user_id: str,
        scene: Optional[str],
        scenario_id: Optional[str],
        language: str,
        resource_map: Dict[str, List[Resource]],
        sandbox_manager: Optional[SandboxManager],
        skill_dir: Optional[str],
        available_skills: Dict[str, str],
        agent_file_system=None,
        agent=None,  # 仅工具需要反查 agent 时用
    ):
        ...

    def build(self, tool_call: ToolCall, tool: BaseTool) -> ToolContext:
        ctx = ToolContext(
            agent_id=self._agent_id,
            conversation_id=self._conv_id,
            user_id=self._user_id,
            scene=self._scene,
            scenario_id=self._scenario_id,
            language=self._language,
            skill_dir=self._skill_dir,
            available_skills=self._available_skills,
            ...
        )

        # 注入沙箱活句柄（G7）
        if self._sandbox_manager:
            ctx.set_resource("sandbox_client", self._sandbox_manager.client)

        # 注入 agent_file_system（G4）
        if self._agent_file_system:
            ctx.set_resource("agent_file_system", self._agent_file_system)

        # 注入 agent 引用（G4，仅工具需要时）
        if self._agent:
            ctx.set_resource("agent", self._agent)

        # 按 tool 类型注入对应资源（G4）
        tool_name = tool_call.name
        if tool_name in ("execute_sql", "list_tables", "get_table_spec"):
            # DB 工具 → 注入 DBResource
            if "DBResource" in self._resource_map:
                ctx.set_resource("db_resource", self._resource_map["DBResource"][0])
        elif tool_name == "KnowledgeSearch":
            if "RetrieverResource" in self._resource_map:
                ctx.set_resource("knowledge_retriever", self._resource_map["RetrieverResource"][0])
        elif tool_name == "AgentStart":
            if "AppResource" in self._resource_map:
                ctx.set_resource("app_resource", self._resource_map["AppResource"])

        return ctx
```

**关键设计：**
- **来源**：`tool_action.py:993-1059` + `agent_adapter.py:240-320` 的组装逻辑
- **按 tool 类型派发资源** —— 工具从 `ctx.get_resource(name)` 拿活句柄，不通过 kwargs 铺平
- **沙箱活句柄通过 `set_resource("sandbox_client", client)`** —— 不通过 `init_params` 铺平（旧路径）也不通过 `ToolContext.config` dict（新路径），统一走 `set_resource`

### 5.9 HookManager 集成（v2 新增，G8 + G9，推翻决策 #4）

**位置：** `packages/derisk-core/src/derisk/agent/core/v2/hook_integration.py`（新文件）

**职责：** V2 集成 BAIZE 的 HookManager，触发 `pre_tool_use` / `post_tool_use` / `turn_complete` / `conversation_complete` / `error_occurred` 事件。

**集成点：**

| 触发点 | V2 模块 | Hook 事件 | blocking |
|---|---|---|---|
| 工具执行前 | `default_acting_fn` | `pre_tool_use` | blocking（CONTINUE/DENY/ABORT/MODIFY） |
| 工具执行后 | `default_acting_fn` | `post_tool_use` | fire-and-forget |
| turn 结束 | `run_loop` | `turn_complete` | fire-and-forget |
| conversation 结束 | `run_loop` 调用方 | `conversation_complete` | fire-and-forget |
| step 失败 | `run_loop` | `error_occurred` | fire-and-forget |

**Hook context 字段对齐 BAIZE（G6）：**

`pre_tool_use` context（对齐 `tool_action.py:1334-1341`）：
```python
{
    "tool_name": str,
    "args": dict,
    "context": ToolContext,
    "conv_id": str,
    "agent_id": str,
}
```

`turn_complete` context（对齐 `base_agent.py:1327-1355`）：
```python
{
    "round": int,            # 第几个 turn
    "interrupted": bool,     # 是否被中断（AWAITING_USER 等）
    "user_prompt": str,
    "final_answer": str,
    "user_id": str,
    "conv_id": str,
    "agent_id": str,
    "step_count": int,
}
```

**Memory tier1/2/3 挂回 HookManager（推翻 v1 决策 #4）：**

v1 spec 决策 #4 "跳过 HookDispatcher，直接调 manager 方法" → v2 推翻，理由：满配 BAIZE agent 的审计/合规 hook + 非 memory turn hook 会丢失。

v2 做法：复用 BAIZE 的 `default_memory_hooks(config)`（`memory/hook_dispatcher.py:122-182`），把 memory tier1/2/3 挂到 HookManager：
- Tier 1（`memory_tier1_turn`）：`turn_complete` hook，priority=200
- Tier 2（`memory_tier2_reflect`）：`turn_complete` hook，priority=210，every N turns
- Tier 3（`memory_tier3_curate`）：`conversation_complete` hook，priority=220
- Tier 0（`memory_tier0_prefetch`）：`turn_complete` hook，priority=190

`run_loop` 只触发 `turn_complete` 事件，HookManager 按 priority 顺序 dispatch（包括 memory + 审计 + 日志 + 自定义）。

**用户自定义 hook 配置（满配 agent 的 hook_config）：**

agent_info 里 `team_context.hook_config.hooks` 列表，通过 `build_hook_manager(team_context)`（`hook/manager.py:192-208`）构造 HookManager，注入 `run_loop(hook_manager=...)`。

### 5.10 子 Agent shared_conv 模式（v2 新增，G5）

**位置：** `packages/derisk-core/src/derisk/agent/core/v2/subagent_shared_conv.py`（新文件）

**背景：** BAIZE `AgentStart` 共享父 conv_id / gpts_memory / AFS（父能看子的 WorkLog）；V2 `SubAgentRuntime` 独立 sub_conv_id（隔离）。这是设计层面的不同，**满配 agent 依赖共享 conv_id 时不能丢失**。

**v2 方案：SubAgentRuntime 加 `shared_conv` 模式**

```python
class SubAgentSpawnSpec(BaseModel):
    # ... 原有字段 ...
    shared_conv: bool = False  # v2 新增，默认 False（独立 conv_id，原 V2 语义）
```

`SubAgentRuntime.spawn(spec)` 行为：
- `shared_conv=False`（默认）：独立 sub_conv_id，子事件写子 conv 的 StateStore，通过 transcript 桥接结果（原 V2 语义）
- `shared_conv=True`：**共享父 conv_id**，子事件直接写父 conv 的 StateStore（事件 seq 接父的 seq），子 agent 用父的 gpts_memory / AFS / resource_map，等价 BAIZE AgentStart 语义

**shared_conv 模式的实现要点：**
- 子 step 的 `parent_step_id = 父 step_id`，`conv_id = 父 conv_id`（不新建）
- 子 step 的 seq 由父 conv 的 EventStream 分配（接父最后 seq + 1）
- 子 agent 的 thinking_fn / acting_fn 复用父的（同一 LLM 配置 / 同一工具集 / 同一记忆空间）
- 不创建 transcript（共享 conv 不需要桥接）
- depth 限制仍生效（防无限嵌套）

**何时用 shared_conv：**
- BAIZE `AgentStart`（同步，共享 conv_id）→ `shared_conv=True`
- BAIZE `spawn_agent_task`（异步，独立任务）→ `shared_conv=False`（原 V2 语义）

**产品层：** ToolResolver 的 `_inject_resource_based_tools` 注入 `AgentStart` 工具时，内部用 `shared_conv=True` 调 `SubAgentRuntime.spawn`。

### 5.11 Skill 工具签名迁移指南（v2 新增，G2）

**背景：** BAIZE 的 Skill / skill-aware 工具通过 `Action.run(**kwargs)` 接收 `skill_dir / available_skills / sandbox_client` 等参数；V2 原生化后，这些参数要从 `ToolContext` 读。

**需迁移的工具清单（基于 `tool_action.py:983-1059`）：**

| 工具 | 原参数（kwargs） | v2 迁移后（从 ToolContext 读） |
|---|---|---|
| `Skill` / `skill_exec` / `skill_list` | `skill_dir`, `available_skills`, `sandbox_client` | `ctx.skill_dir`, `ctx.available_skills`, `ctx.get_resource("sandbox_client")` |
| 沙箱工具（`Bash`, `Read`, `Write`, `Edit` 等） | `client` (init_params), `context.sandbox_manager` | `ctx.get_resource("sandbox_client")` |
| `todowrite` / `todoread` | `agent` | `ctx.get_resource("agent")` |
| `deliver_file` | `agent_file_system` | `ctx.get_resource("agent_file_system")` |
| `execute_sql` / `list_tables` / `get_table_spec` | `agent.resource_map[DBResource]` | `ctx.get_resource("db_resource")` |
| `KnowledgeSearch` | `agent.resource_map[RetrieverResource]` | `ctx.get_resource("knowledge_retriever")` |
| `AgentStart` | `agent.resource_map[AppResource]` | `ctx.get_resource("app_resource")` |

**迁移工作量：** ~10-15 个工具，每个改 execute 签名 + 参数读取，约 1-2 天。

**迁移策略：** 工具基类 `ToolBase` 提供 `execute(args, context)` 的默认实现，子类 override `_execute(args, context)`；迁移期间保留旧 `async_execute(**kwargs)` 兼容路径，但标记 deprecated。

### 5.12 子系统集成（搬运清单）

| 子系统 | 来源 | V2 集成方式 | 改动 |
|---|---|---|---|
| **ContextEngine** | `expand/react_master_agent/context_engine/` | `default_thinking_fn` 直接调 `build_messages` | 0 改动 |
| **ColdPersistence** | `expand/react_master_agent/cold_persistence.py` | ContextEngine 内部用，V2 不直接调 | 0 改动 |
| **WorkLogManager** | `expand/react_master_agent/work_log.py` | `default_thinking_fn` 调 `get_work_log`，工具执行后调 `record` | 0 改动 |
| **Truncator** | `expand/react_master_agent/truncation.py` | `default_acting_fn` 调 `truncate` | 0 改动 |
| **LongTermMemoryManager** | `core/memory/longterm_manager.py` | `default_thinking_fn` 调 `retrieve_relevant_memories`；run_loop 调 `write_turn_lightweight` / `reflect_on_last_n_turns` / `curate_session` | 0 改动 |
| **MemoryReadPipeline** | `core/memory/read_pipeline.py` | `default_thinking_fn` 调 `consume_prefetch` / `scrub_stream_delta` / `load_static_block` | 0 改动 |
| **DoomLoopDetector** | `expand/react_master_agent/doom_loop_detector.py` | `default_acting_fn` 调 `check`，`permission_callback` 接 V2 PermissionGate | 0 改动（已是独立类） |
| **ToolBase / ToolResult / ToolRegistry** | `agent/tools/` | `default_acting_fn` 调 `tool.execute` | 0 改动 |
| **PermissionRuleset** | `core/agent_info.py` | V2 PermissionGate 已复用（P2-P4） | 0 改动 |
| **VisProtocolConverter** | `vis/vis_converter.py` | `stream_to_sse` 已复用（P2-P4） | 0 改动 |

**关键：所有子系统 0 改动。** V2 只是新的"调用方"，不是新的"抽象层"。

### 5.13 V2 内核原生化改造（v2 新增）

**位置：** `packages/derisk-core/src/derisk/agent/core/v2/runtime.py` 改签名

**改动：**
```python
# v1（dict 接口）：
ThinkingFn = Callable[[dict], AsyncGenerator[dict, None]]
ActingFn = Callable[[dict], Awaitable[dict]]

# v2（原生接口）：
ThinkingFn = Callable[[dict], AsyncGenerator[ThinkingChunk, None]]  # input 仍 dict（含 prompt/scene/conv_id 等）
ActingFn = Callable[[ToolCall, ToolContext], Awaitable[ToolResult]]
```

`ThinkingChunk` typed union：
```python
ThinkingChunk = Union[
    TokenChunk,      # {token: str, usage: Optional[UsageDict]}
    ToolCallChunk,   # {tool_calls: List[ToolCall]}  # 增量拼接
    UsageChunk,      # {usage: UsageDict}  # 单独 usage 事件
]
```

**P2-P4 测试改动：**
- 151 个测试中 ~80 个涉及 acting_fn 签名，需改 mock：从 `async def mock_acting(tool_call: dict) -> dict` 改为 `async def mock_acting(tool_call: ToolCall, ctx: ToolContext) -> ToolResult`
- thinking_fn mock 同理改 yield 类型
- run_step 内核的 `_run_acting_phase` 改签名：从 `await acting_fn(tool_call_dict)` 改为 `await acting_fn(tool_call, ctx)`
- run_step 在 ACTING 前构造 ToolContext（从 input_ + agent_view 派生）

**工作量：** ~3 天（改内核 + 改测试 + 改 v2_demo.py）

### 5.14 产品入口

#### 5.14.1 Agent 类型字段

在 `agent_info`（或等价配置）加字段：
```python
runtime_version: Literal["v1", "v2"] = "v1"  # 默认 v1（BAIZE），过渡期
```

#### 5.14.2 后端分发

在 `agent_chat.py`（SSE 端点）根据 `runtime_version` 分发：
```python
if agent_info.runtime_version == "v2":
    # 走 V2 run_loop
    thinking_fn = make_default_thinking_fn(...)
    acting_fn = make_default_acting_fn(...)
    tool_resolver = ToolResolver(resource_map=..., sandbox_manager=..., ...)
    hook_manager = build_hook_manager(team_context)
    async for event in run_loop(
        ..., thinking_fn=thinking_fn, acting_fn=acting_fn,
        hook_manager=hook_manager,
    ):
        sse_line = step_event_to_stream_event(event)
        yield stream_to_sse(sse_line)
else:
    # 走 BAIZE 原路径
    async for sse in baize_generate_reply(...):
        yield sse
```

#### 5.14.3 前端

- **Agent 编辑页面**：加 `runtime_version` 选择器（v1 / v2）
- **聊天页面**：SSE 协议一致，无前端改动
- **usage_metric**：V2 路径已支持（P3 Task 10/11 的 `TokenStatusBar` / `MessageTokenBadge` 在 V2 路径下挂载）

#### 5.14.4 Agent 实例配置

V2 agent 实例配置维度（对齐 BAIZE `agent_info`，满配支持）：
- `runtime_version`: "v2"
- `system_prompt`: str
- `user_prompt_template`: str
- `context_config`: { scene, scenario_id, language }（G1）
- `resource_tool`: List[tool_id]（工具绑定，DB `ServeEntity.resource_tool`）
- `resource_knowledge`: List[RetrieverResource]
- `resource_agent`: List[AppResource]（子 agent，G5）
- `resource_memory`: LongTermMemoryConfig（记忆空间绑定，G7）
- `resources`: List[AgentResource]（DBResource / AgentSkillResource 等）
- `sandbox`: SandboxConfig（沙箱配置，G7）
- `team_context.hook_config`: hook 配置（G8/G9）
- `llm_config`: { model_alias, fallback }
- `runtime_config`: { max_steps, doom_loop_threshold, ... }
- `permissions`: PermissionRuleset

---

## 6. 兼容性与删除清单

### 6.1 过渡期（本 spec 实施后）

- BAIZE 框架保留，可继续创建 BAIZE agent
- V2 框架可用，可创建 V2 agent
- 两套共享：LLM 配置 / 工具注册表 / 权限规则 / 前端 / 知识库 / Memory space
- 两套不共享：runtime（run_loop vs generate_reply）

### 6.2 验证通过后删除（后续 spec）

| 删除项 | 行数 | 替代物 |
|---|---|---|
| `react_master_agent.py` | 3619 | V2 `run_loop` + `default_thinking_fn` + `default_acting_fn` |
| `base_agent.generate_reply` if/else 主循环 | ~430 | V2 `run_loop` |
| `base_agent._tool_failure_counts` 等 | ~60 | `ToolFailureTracker` |
| `base_agent._doom_loop_detector` 初始化 | ~30 | `default_acting_fn` 内 |
| `core/memory/agent_memory.py`（旧 AgentMemory） | ~750 | 已废弃，LongTermMemoryManager 替代 |
| `core/memory/long_term.py`（旧 LongTermMemory） | ~300 | 已废弃，LongTermMemoryManager 替代 |
| `core/memory/compaction_pipeline.py` L2/L3/L4 | ~800 | ContextEngine 已覆盖 |
| `tool_action.py`（ToolAction 编排） | ~700 | `default_acting_fn` |

**预计删除：~6000+ 行**

### 6.3 不删除（保留复用）

- `ContextEngine` / `ColdPersistence` / `WorkLogManager` / `Truncator`
- `LongTermMemoryManager` / `MemoryReadPipeline`
- `DoomLoopDetector`
- `ToolBase` / `ToolResult` / `ToolRegistry`
- `PermissionRuleset`
- `VisProtocolConverter`
- `HookManager`（V2 暂不集成，但保留给其他用途）

---

## 7. 风险与缓解（v2 修订）

### 7.1 V2 内核原生化改造的测试成本（v2 修订）

**风险：** acting_fn 签名从 dict 改为 ToolCall/ToolResult/ToolContext，P2-P4 的 151 个测试要改 ~80 个。

**缓解：** 测试改动是机械工作（mock 签名替换），不是设计工作。一次改完，长期受益（default_acting_fn 轻薄，无需 dict 翻译层）。改造期间用 v1 测试作参考，确保行为一致。

### 7.2 HookManager 集成的 hook context 对齐（v2 修订）

**风险：** HookManager 的 `turn_complete` / `pre_tool_use` context 字段如果不严格对齐 BAIZE，memory tier2 的 `every_n_turns` 逻辑 + 用户自定义 hook 会失效。

**缓解：** §5.9 明确 context 字段 schema，对齐 `base_agent.py:1327-1355` + `tool_action.py:1334-1341`。集成测试覆盖"满配 hook_config agent"端到端跑通。

### 7.3 子 Agent shared_conv 模式的语义风险（v2 新增）

**风险：** shared_conv=True 时子 agent 共享父 conv_id / gpts_memory / AFS，子事件写父 conv 的 StateStore —— 可能导致父 conv 的事件流被子 agent 污染，崩溃恢复时分不清父子 step。

**缓解：**
- 子 step 的 `parent_step_id = 父 step_id`，事件 metadata 标记 `is_subagent: True` + `subagent_depth: N`
- 崩溃恢复时 `RecoveryCoordinatorV2` 根据 `parent_step_id` 区分父子 step
- shared_conv 模式默认禁用异步（同步阻塞父 step），减少并发污染
- 文档明确：shared_conv 仅用于 AgentStart 语义（同步、共享上下文），异步场景用独立 conv_id

### 7.4 Skill 工具迁移的兼容性（v2 新增）

**风险：** Skill / skill-aware 工具从 kwargs 迁到 ToolContext，迁移期间新旧签名并存可能导致工具调用失败。

**缓解：**
- 工具基类 `ToolBase` 提供 `execute(args, context)` 默认实现，子类 override `_execute(args, context)`
- 保留旧 `async_execute(**kwargs)` 兼容路径，标记 deprecated
- 迁移清单（§5.11）逐工具迁移 + 测试覆盖
- 迁移完成验证：所有 skill-aware 工具在新 V2 agent 下能跑通

### 7.5 过渡期 BAIZE / V2 子系统状态同步（v1 保留）

**风险：** 过渡期同一 conv 如果先用 BAIZE 跑、再用 V2 跑，子系统状态（WorkLog / Memory / ColdPersistence）能否互通？

**缓解：** V2 直接复用 BAIZE 子系统的存储（gpts_memory / KnowledgeVault / AFS），状态天然互通。ContextEngine / MemoryReadPipeline 都是无状态读取，不冲突。

---

## 8. 验证标准（v2 修订）

V2 框架实施完成的验证清单：

### 8.1 功能验证（基础）

- [ ] V2 agent 实例可在 Agent 编辑页面创建
- [ ] V2 agent 可在聊天页面端到端对话
- [ ] 流式 token 输出正常
- [ ] 工具调用全链路（LLM emit tool_call → resolve → gate → hook → execute → result → LLM 再思考）
- [ ] 多轮 loop（LLM 看到 tool_result 后继续 thinking，直到不再 emit tool_calls）
- [ ] 权限 ASK（写操作触发 AWAITING_TOOL_PERMISSION，用户允许后继续）
- [ ] 子 agent spawn（独立 conv_id 模式）
- [ ] 崩溃恢复（kill 进程后重启，从最后 step 续上）
- [ ] 上下文压缩（长对话触发 ContextEngine cold handoff）
- [ ] 记忆写入（turn 结束后 write_turn_lightweight，通过 HookManager 触发）
- [ ] 记忆检索（thinking 前 retrieve_relevant_memories 注入 prompt）
- [ ] DoomLoop 检测（连续 3 次相同 tool_call 被阻止）
- [ ] 工具失败跟踪（同工具失败 3 次后 block）
- [ ] usage_metric 实时显示（TokenStatusBar）
- [ ] Truncator（长输出归档到 AFS + dattach tag）

### 8.2 满配承接验证（v2 新增，关键）

满配 BAIZE agent（prompt + 场景 + skill + DB + MCP + 知识库 + 子agent + 记忆 + 沙箱 + hook）切换到 V2 后无丢失：

- [ ] **system prompt + 场景信息**：scene/scenario_id 正确注入 system prompt
- [ ] **skill 绑定**：skill_dir / available_skills 通过 ToolContext 注入，Skill 工具能执行
- [ ] **DB 资源**：绑 DBResource 后 execute_sql / list_tables / get_table_spec 自动可用，DB 连接通过 ToolContext 传递
- [ ] **MCP 资源**：绑 MCPToolPack 后 MCP 工具自动可用，partial 闭包连接正常
- [ ] **知识库资源**：绑 RetrieverResource 后 KnowledgeSearch 自动可用，retriever 通过 ToolContext 传递
- [ ] **子 Agent（同步 shared_conv）**：AgentStart 共享父 conv_id，子 agent 消息写入父 gpts_memory，父能看子 WorkLog
- [ ] **子 Agent（异步独立 conv）**：spawn_agent_task 独立 sub_conv_id，transcript 桥接结果
- [ ] **记忆系统**：memory_space 绑定，static_block + dynamic prefetch + scrubber 全链路跑通；tier1/2/3 通过 HookManager 触发
- [ ] **沙箱**：SandboxManager 绑定，沙箱工具通过 ToolContext.get_resource("sandbox_client") 拿活句柄
- [ ] **HOOK 配置**：pre_tool_use（blocking，可 DENY/MODIFY/ABORT）+ post_tool_use（fire-and-forget）+ turn_complete（memory + 审计 + 日志）+ conversation_complete（memory curate）全跑通

### 8.3 对比验证

- [ ] 同一满配 agent 在 BAIZE / V2 跑，行为一致（工具调用 / 回答质量 / token 消耗 / hook 副作用）
- [ ] V2 SSE 协议与 BAIZE 兼容（前端无感知切换）

### 8.4 测试

- [ ] V2 内核 P2-P4 测试 151/151 通过（acting_fn 签名改后，~80 个测试改 mock）
- [ ] V2 框架新模块测试（run_loop / default_thinking_fn / default_acting_fn / ToolFailureTracker / retrying_thinking / ToolResolver / tool_context_factory / hook_integration / subagent_shared_conv）90%+ 覆盖
- [ ] Skill 工具迁移测试：所有 skill-aware 工具在新 ToolContext 签名下跑通
- [ ] 集成测试：满配 V2 agent 端到端跑通所有 8.2 项

---

## 9. 工作量估算（v2 修订）

| 阶段 | 工作量 | 内容 |
|---|---|---|
| Week 1 | 5 天 | V2 内核原生化改造（runtime.py 签名 + P2-P4 测试改 mock）+ `run_loop` + `ToolFailureTracker` + `retrying_thinking` |
| Week 2 | 5 天 | `ToolResolver`（含资源→工具自动注入）+ `tool_context_factory` + `ToolContext` schema 扩展 + `default_acting_fn`（含 HookManager 集成） |
| Week 3 | 5 天 | `default_thinking_fn`（ContextEngine + Memory 集成）+ `hook_integration`（HookManager 触发点 + memory tier 挂载）+ `subagent_shared_conv` |
| Week 4 | 4 天 | Skill 工具签名迁移（~10-15 个工具）+ 兼容路径 |
| Week 5 | 4 天 | 产品入口（runtime_version 字段 + 后端分发 + Agent 编辑页面）+ 集成测试 |
| Week 6 | 3 天 | 满配承接验证 + 对比测试 + 修 bug + 文档 |

**总计：~5-6 周**（v1 是 3-4 周，v2 增加 2 周用于 6 项 GAP 补齐）

---

## 10. 决策记录（v2 修订）

| # | 决策 | 理由 | v2 状态 |
|---|---|---|---|
| 1 | V2 是 BAIZE 框架的继任者，不是并列第二套 | 用户明确：验证完直接删 BAIZE，只维护一套 | 不变 |
| 2 | ~~V2 内核 dict 接口不改~~ → V2 内核原生化 ToolCall/ToolResult/ToolContext | 满配承接验证发现 dict 接口需 700 行 adapter，违反"不过渡设计"；原生化后 default_acting_fn 轻薄 | **v2 推翻** |
| 3 | 子系统原样搬，无 adapter | 不要过渡设计；子系统已是干净抽象 | 不变 |
| 4 | ~~跳过 HookDispatcher，直接调 manager 方法~~ → 集成 HookManager | 满配 agent 的 pre/post_tool_use + 审计 + 合规 + 非 memory turn hook 会丢失；用户明确"做就做完整" | **v2 推翻** |
| 5 | 删除 `UnifiedCompactionPipeline` L2/L3/L4 | ContextEngine 已覆盖，重复调用会打架；保留 L1（truncate_output） | 不变 |
| 6 | `run_loop` 用 `StepState` 驱动，无 if/else 地狱 | V2 内核状态机已就绪，利用它 | 不变 |
| 7 | Agent 实例配置对齐 BAIZE `agent_info`（满配维度） | 迁移成本 = 改 `runtime_version` 字段；满配维度全支持 | v2 扩展 |
| 8 | 过渡期 BAIZE / V2 共享子系统存储 | 状态互通，对比测试可行 | 不变 |
| 9 | ToolContext 扩展 scene/scenario_id/language + set_resource 注入契约 | G1 + G4 + G7：场景信息 + 活资源句柄 + 沙箱活句柄 | **v2 新增** |
| 10 | ToolResolver 加资源→工具自动注入 | G3：等价 BAIZE `_inject_resource_based_tools`，配置驱动体验不丢 | **v2 新增** |
| 11 | SubAgentRuntime 加 shared_conv 模式 | G5：等价 BAIZE AgentStart 共享 conv_id 语义，迁移不丢 | **v2 新增** |
| 12 | Skill 工具签名迁移到 ToolContext | G2：Skill / skill-aware 工具从 kwargs 迁到 ctx，统一参数传递 | **v2 新增** |

---

## 11. 后续 spec

- **删除 BAIZE 主壳**：验证通过后，删除 `react_master_agent.py` / `generate_reply` / 旧 memory / CompactionPipeline L2-L4 / `tool_action.py`，预计 ~6000 行
- **多 agent 编排**：group chat / next_speakers / peer routing（BAIZE 也没有，需新设计）
- **V2 内核原生化更深一步**（如果未来需要）：thinking_fn 也原生化（typed ThinkingChunk 替代 dict）

---

## 附录 A：BAIZE 子系统调研结论摘要

（详细调研见 brainstorming 对话记录，这里只摘录对设计有影响的结论）

### A.1 ContextEngine

- **无状态纯函数式**：`build_messages(messages, work_logs_by_conv, conv_id, session_id, context_window)` 直接调
- **依赖注入**：ColdPersistenceAdapter / SummarizeFn / EventEmitter 都是 Protocol
- **V2 直接复用，0 改动**

### A.2 LongTermMemoryManager + MemoryReadPipeline

- **纯 async API**：`retrieve_relevant_memories` / `write_turn_lightweight` / `reflect_on_last_n_turns` / `curate_session`
- **MemoryReadPipeline**：prefetch cache + scrubber + static_block
- **V2 直接复用，跳过 HookDispatcher**，直接调 manager 方法
- **旧栈废弃**：`AgentMemory` / `LongTermMemory`（long_term.py）已 stub，不碰

### A.3 工具系统

- **ToolBase / ToolResult / ToolRegistry 已是干净抽象**
- **BAIZE 四路查找**（sandbox_tool_dict + system_tool_dict + tool_registry + resource pack）→ V2 用 `ToolResolver` 收敛
- **ToolContext 字段缺失**（memory / agent_file_system / render_protocol）→ V2 用 `tool_context_factory` 构造 + `set_resource` 注入
- **have_retry / ask_user 双轨** → V2：have_retry 由 `ToolFailureTracker` 外部跟踪，ask_user 由 `AskUserAdapter` 转换（已有）

### A.4 DoomLoop + Retry

- **DoomLoopDetector 天然独立**，只依赖 `permission_callback`
- **`_tool_failure_counts` 是 5 行字典逻辑**，抽 `ToolFailureTracker`
- **MAX_ATTEMPTS=3 + 模型降级**，抽 `retrying_thinking` 装饰器

### A.5 删除清单（来自调研）

- `react_master_agent.py`：3619 行 → V2 `run_loop` + defaults 替代
- `base_agent.generate_reply` if/else：~430 行 → V2 `run_loop` 替代
- `core/memory/agent_memory.py`：~750 行（已废弃）
- `core/memory/long_term.py`：~300 行（已 stub）
- `core/memory/compaction_pipeline.py` L2/L3/L4：~800 行 → ContextEngine 替代
- `tool_action.py`：~700 行 → V2 `default_acting_fn` 替代

**预计删除：~6000+ 行**

---

## 附录 B：满配 BAIZE Agent 承接验证报告（v2 修订依据）

### B.1 验证目标

满配 BAIZE agent（prompt + 场景信息 + skill + DB + MCP + 知识库 + 子 Agent + 记忆 + 沙箱 + hook）能否无功能丢失切换到 V2 框架跑起来。

### B.2 验证方法

构造满配 agent_info（基于 `ServeEntity` schema + 真实配置维度），逐项验证 V2（方案 B：内核原生化）能否承接。

### B.3 9 项逐项验证结果

| # | 配置项 | V2 承接状态 | GAP |
|---|---|---|---|
| 1 | system prompt + 场景信息 | ⚠ 需补 | G1: ToolContext 加 scene/scenario_id/language |
| 2 | skill 绑定 | ⚠ 需迁 | G2: Skill 工具签名迁移到 ToolContext |
| 3 | DB 资源自动注入工具 | ⚠ 需补 | G3: 资源→工具自动注入机制 |
| 4 | MCP 资源 | ✔ 不丢失 | partial 闭包天然兼容 |
| 5 | 知识库资源 | ⚠ 需补 | G4: ToolContext.set_resource 注入点 |
| 6 | 子 Agent（AgentStart 同步共享 conv_id） | ⚠ 语义丢失 | G5: 需 shared_conv 模式 |
| 7 | 记忆系统 | ⚠ 部分风险 | G6: hook context 字段对齐 BAIZE |
| 8 | 沙箱 | ⚠ 需补 | G7: 沙箱活句柄注入路径 |
| 9 | HOOK 配置 | ✖ 大量丢失 | G8/G9: 必须集成 HookManager（推翻决策 #4） |

### B.4 GAP 清单与补法

| GAP | 描述 | 补法 | 工作量 |
|---|---|---|---|
| G1 | ToolContext 缺场景字段 | 加 scene/scenario_id/language | 30min |
| G2 | Skill 工具签名迁移 | 改 ~10-15 个工具的 execute 签名 | 1-2 天 |
| G3 | 资源→工具自动注入 | ToolResolver 加 `_inject_resource_based_tools` | 1 天 |
| G4 | ToolContext.set_resource 注入点 | tool_context_factory 按 tool 类型派发 | 1 天 |
| G5 | 子 Agent 共享 conv_id | SubAgentRuntime 加 shared_conv 模式 | 3 天 |
| G6 | hook context 字段对齐 | 严格按 base_agent.py:1327-1355 复现 | 2 天 |
| G7 | 沙箱活句柄注入 | tool_context_factory 注入 sandbox_client | 1 天 |
| G8 | pre/post_tool_use hook | default_acting_fn 集成 HookManager | 3 天 |
| G9 | turn/conversation hook | run_loop 集成 HookManager，memory 挂回 hook | 与 G8 合并 |

### B.5 最终结论

**V2 方案 B（内核原生化 + 补 6 项 GAP）能无功能丢失承接满配 BAIZE agent。**

- 技术上可行：所有 gap 都是补协议/补工厂/补 hook 集成点，没有根本性架构冲突（G5 是语义选择，shared_conv 模式解决）
- v1 spec 决策 #4"跳过 HookDispatcher"在满配场景下错误，v2 推翻
- v1 spec 决策 #2"dict 接口不改"在满配场景下导致 700 行 adapter，v2 推翻为原生化
- 工作量从 v1 的 3-4 周增至 v2 的 5-6 周，但保证满配无丢失承接，否则不能删 BAIZE

### B.6 满配 agent_info 示例

（见验证报告第一步 1.2，含 system_prompt / context_config / resource_tool / resource_knowledge / resource_agent / resource_memory / resources / runtime_config / sandbox / team_context.hook_config 全维度）

---

## 附录 C：v2 修订摘要

相对 v1 spec（已提交 commit `d72a305c`），v2 修订内容：

1. **范围扩展**：从 5 项增至 11 项（§3.1）
2. **决策 #2 推翻**：V2 内核原生化 ToolCall/ToolResult/ToolContext（§5.3 + §5.13）
3. **决策 #4 推翻**：集成 HookManager，不再跳过 HookDispatcher（§5.9）
4. **新增 4 个模块**：ToolContext schema 扩展（§5.7）+ tool_context_factory（§5.8）+ hook_integration（§5.9）+ subagent_shared_conv（§5.10）
5. **ToolResolver 扩展**：加资源→工具自动注入（§5.6）
6. **Skill 工具迁移指南**：~10-15 个工具签名迁移（§5.11）
7. **满配承接验证**：新增 §8.2 满配验证清单 + 附录 B 验证报告
8. **工作量调整**：3-4 周 → 5-6 周
9. **决策记录扩展**：8 项 → 12 项（§10）

