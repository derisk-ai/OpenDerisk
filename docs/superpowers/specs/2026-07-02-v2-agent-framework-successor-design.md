# V2 Agent 框架继任设计：从内核到完整框架

- 日期：2026-07-02
- 状态：设计已与用户逐节确认，待写入实施计划
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

### 3.1 本 spec 覆盖（5 项）

1. **`run_loop`**：多轮循环，包 `run_step`，带 retry/termination/turn 边界
2. **`default_acting_fn`**：默认工具执行实现（resolve → gate → doom → tracker → execute → truncate）
3. **`default_thinking_fn`**：默认 LLM thinking 实现（ContextEngine + Memory 注入 + scrubber + MAX_ATTEMPTS 装饰器）
4. **子系统搬运**：ContextEngine / Memory / Tools / DoomLoop / Retry 原样集成，无 adapter
5. **产品入口**：`runtime_version` 字段 + 后端分发 + Agent 编辑页面支持

### 3.2 本 spec 不覆盖（明确排除）

- ~~V2 内核改 ToolCall/ToolResult 原生~~ —— dict 接口不动
- ~~adapter / bridge 抽象层~~ —— 子系统直接调
- ~~模板系统 / agent 工厂~~ —— agent 实例就是配置
- ~~runtime 可插拔~~ —— 就一个 V2 runtime
- ~~HookManager 集成~~ —— 跳过 HookDispatcher，直接调 manager 方法
- ~~`UnifiedCompactionPipeline` L2/L3/L4~~ —— ContextEngine 已覆盖，只保留 L1（truncate_output）

### 3.3 后续 spec 覆盖（验证通过后）

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

V2 框架 = V2 内核（已有）+ 5 个新模块：

| 模块 | 位置 | 职责 |
|---|---|---|
| `run_loop` | `v2/run_loop.py`（新） | 多轮循环，调 `run_step` 直到终止 |
| `default_thinking_fn` | `v2/default_thinking.py`（新） | LLM 调用 + ContextEngine + Memory 注入 + scrubber + MAX_ATTEMPTS |
| `default_acting_fn` | `v2/default_acting.py`（新） | 工具解析 → gate → doom → tracker → execute → truncate |
| `tool_failure_tracker` | `v2/tool_failure_tracker.py`（新） | 从 BAIZE `_tool_failure_counts` 抽出 |
| `retrying_thinking` | `v2/retrying_thinking.py`（新） | MAX_ATTEMPTS 装饰器 |

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
    input_: dict,  # {"prompt": str, "session_id": str, ...}
    state_store: StateStore,
    thinking_fn: ThinkingFn,  # 通常用 default_thinking_fn
    acting_fn: Optional[ActingFn] = None,  # 通常用 default_acting_fn
    *,
    parent_step_id: Optional[str] = None,
    permission_gate: Optional[PermissionGate] = None,
    subagent_runtime: Optional[SubAgentRuntime] = None,
    max_steps: int = 20,  # 防止无限循环
    on_turn_complete: Optional[Callable] = None,  # memory tier1/2 钩子
    on_conversation_complete: Optional[Callable] = None,  # memory tier3 钩子
) -> AsyncGenerator[StepEvent, None]:
```

**主循环逻辑（瘦身版的 BAIZE `generate_reply`）：**
```python
step_count = 0
async for step_event in run_step(...):
    yield step_event
    if step_event.state == StepState.DONE:
        step_count += 1
        # 判断是否继续
        if step_event.event_type == "step_done":
            # 检查 LLM 是否 emit tool_calls
            had_tool_calls = step_event.output.get("had_tool_calls", False)
            terminated = step_event.output.get("terminate", False)
            if not had_tool_calls or terminated or step_count >= max_steps:
                # turn 结束
                if on_turn_complete:
                    await on_turn_complete(step_event)
                break
    elif step_event.state == StepState.FAILED:
        break
    elif step_event.state in (StepState.AWAITING_USER, StepState.AWAITING_TOOL_PERMISSION):
        # 暂停，等用户/权限响应
        return
```

**关键设计：**
- **无 if/else 地狱**：用 `StepState` 驱动，状态机已经定义好
- **max_steps 防失控**：默认 20，可配置
- **turn / conversation 生命周期**：通过 `on_turn_complete` / `on_conversation_complete` 回调挂载 memory 钩子，不耦合到 run_loop 内部
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

### 5.3 `default_acting_fn`

**位置：** `packages/derisk-core/src/derisk/agent/core/v2/default_acting.py`（新文件）

**职责：** 工具解析 → 权限 → doom → 失败跟踪 → 执行 → 截断。

**工厂签名：**
```python
def make_default_acting_fn(
    *,
    tool_resolver: ToolResolver,  # 统一工具查找
    permission_gate: PermissionGate,
    doom_loop_detector: DoomLoopDetector,
    failure_tracker: ToolFailureTracker,
    truncator: Truncator,  # BAIZE 的 Truncator
    tool_context_factory: Callable[[dict], ToolContext],  # 构造 ToolContext
) -> ActingFn:
    async def acting_fn(tool_call: dict) -> dict:
        ...
    return acting_fn
```

**`acting_fn` 内部流程：**
```python
async def acting_fn(tool_call: dict) -> dict:
    tool_name = tool_call["tool"]
    tool_input = tool_call.get("input", {})

    # 1. DoomLoop 检测
    if not await doom_loop_detector.check(tool_name, tool_input):
        return {"is_exe_success": False, "content": "doom loop detected, blocked"}

    # 2. 失败跟踪
    if failure_tracker.is_blocked(tool_name):
        return {"is_exe_success": False, "content": f"工具 {tool_name} 连续失败超过阈值，已阻止"}

    # 3. PermissionGate.check（5 级链，可能 emit AWAITING_TOOL_PERMISSION）
    #    注意：gate.check 是 async generator，run_step 内核已经处理
    #    acting_fn 这里假设已经通过权限检查（run_step 在 ACTING 前调 gate）

    # 4. 解析工具
    tool = tool_resolver.resolve(tool_name)
    if tool is None:
        return {"is_exe_success": False, "content": f"工具 {tool_name} 未注册"}

    # 5. 构造 ToolContext
    ctx = tool_context_factory(tool_call)  # agent_id / conv_id / step_id / user_id / ...

    # 6. 执行
    try:
        result: ToolResult = await tool.execute(tool_input, context=ctx)
    except Exception as e:
        failure_tracker.record_failure(tool_name)
        return {"is_exe_success": False, "content": f"执行异常: {e}"}

    if not result.success:
        failure_tracker.record_failure(tool_name)
    else:
        failure_tracker.reset(tool_name)

    # 7. 截断（L1，超阈值归档到 AFS）
    output_content = str(result.output)
    trunc_result = await truncator.truncate(output_content, tool_name, tool_input)
    if trunc_result.truncated:
        output_content = trunc_result.truncated_content  # 含 dattach tag

    return {
        "is_exe_success": result.success,
        "content": output_content,
        "tool_name": tool_name,
        "artifacts": [a.dict() for a in result.artifacts] if result.artifacts else [],
    }
```

**关键设计：**
- **dict 接口** —— 进 dict 出 dict，V2 内核签名不动
- **ToolResolver 收敛四路查找** —— BAIZE 现在是 `sandbox_tool_dict + system_tool_dict + tool_registry + resource pack` 四路 if/elif，V2 收敛到一个 `ToolResolver.resolve(name)`，内部仍查这四路但封装一次
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

### 5.6 `ToolResolver`

**位置：** `packages/derisk-core/src/derisk/agent/core/v2/tool_resolver.py`（新文件）

**职责：** 收敛 BAIZE 四路工具查找为单一 `resolve(name)`。

```python
class ToolResolver:
    def __init__(
        self,
        sandbox_tools: Dict[str, BaseTool] = None,  # sandbox_tool_dict
        system_tools: Dict[str, BaseTool] = None,  # system_tool_dict
        unified_registry=None,  # tool_registry
        resource_pack=None,  # agent.resource（MCP 工具）
    ):
        ...

    def resolve(self, name: str) -> Optional[BaseTool]:
        if name in self._sandbox_tools:
            return self._sandbox_tools[name]
        if name in self._system_tools:
            return self._system_tools[name]
        if self._unified_registry:
            tool = self._unified_registry.get(name)
            if tool:
                return tool
        if self._resource_pack:
            return self._lookup_resource_pack(name)
        return None
```

**来源：** `tool_action.py:344-362` 的四路 if/elif，封装成一个类。**不改 BAIZE 的工具注册机制**，只是查找收敛。

### 5.7 子系统集成（搬运清单）

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

### 5.8 产品入口

#### 5.8.1 Agent 类型字段

在 `agent_info`（或等价配置）加字段：
```python
runtime_version: Literal["v1", "v2"] = "v1"  # 默认 v1（BAIZE），过渡期
```

#### 5.8.2 后端分发

在 `agent_chat.py`（SSE 端点）根据 `runtime_version` 分发：
```python
if agent_info.runtime_version == "v2":
    # 走 V2 run_loop
    thinking_fn = make_default_thinking_fn(...)
    acting_fn = make_default_acting_fn(...)
    async for event in run_loop(..., thinking_fn=thinking_fn, acting_fn=acting_fn):
        sse_line = step_event_to_stream_event(event)
        yield stream_to_sse(sse_line)
else:
    # 走 BAIZE 原路径
    async for sse in baize_generate_reply(...):
        yield sse
```

#### 5.8.3 前端

- **Agent 编辑页面**：加 `runtime_version` 选择器（v1 / v2）
- **聊天页面**：SSE 协议一致，无前端改动
- **usage_metric**：V2 路径已支持（P3 Task 10/11 的 `TokenStatusBar` / `MessageTokenBadge` 在 V2 路径下挂载）

#### 5.8.4 Agent 实例配置

V2 agent 实例配置维度（对齐 BAIZE `agent_info`）：
- `runtime_version`: "v2"
- `system_prompt`: str
- `tools`: List[str]（工具名列表）
- `permissions`: PermissionRuleset
- `memory_space`: str（记忆空间，对应 KnowledgeVault space_slug）
- `model_alias`: str（模型配置 alias，复用 BAIZE 的 `models.llm.json`）
- `max_steps`: int（run_loop 上限，默认 20）

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

## 7. 风险与缓解

### 7.1 V2 内核 dict 接口的翻译成本

**风险：** `default_acting_fn` 内 dict ↔ ToolCall/ToolResult 翻译，未来每个 V2 agent 都要付。

**缓解：** `default_acting_fn` 是框架默认提供，agent 实例不写代码就可用。只有需要自定义工具流程的 agent 才 override acting_fn，那是少数情况。如果未来发现翻译成本普遍痛，再提案 V2 内核原生化（不在这个 spec 范围）。

### 7.2 Memory 集成跳过 HookDispatcher

**风险：** BAIZE 的 memory tier1/2/3 通过 HookDispatcher 触发，V2 跳过 HookDispatcher 直接调 manager 方法，可能丢失 hook 链上的其他副作用（如审计、日志）。

**缓解：** V2 通过 `on_turn_complete` / `on_conversation_complete` 回调挂载 memory 钩子，回调内可以加审计/日志。如果未来需要完整 hook 链，再集成 HookManager（不在这个 spec 范围）。

### 7.3 ToolContext 字段缺失

**风险：** BAIZE 的 `ToolContext` 没有 `memory / agent_file_system / render_protocol`，这些通过 `Action.run(**kwargs)` 铺平传递。V2 的 `default_acting_fn` 要构造 ToolContext，需要补齐这些字段。

**缓解：** `tool_context_factory` 工厂负责构造 ToolContext + 通过 `set_resource` 注入 memory / agent_file_system。render_protocol 通过 EventStream 替代（V2 不依赖 render_protocol 推消息）。

### 7.4 过渡期 BAIZE / V2 子系统状态同步

**风险：** 过渡期同一 conv 如果先用 BAIZE 跑、再用 V2 跑，子系统状态（WorkLog / Memory / ColdPersistence）能否互通？

**缓解：** V2 直接复用 BAIZE 子系统的存储（gpts_memory / KnowledgeVault / AFS），状态天然互通。ContextEngine / MemoryReadPipeline 都是无状态读取，不冲突。

---

## 8. 验证标准

V2 框架实施完成的验证清单：

### 8.1 功能验证

- [ ] V2 agent 实例可在 Agent 编辑页面创建
- [ ] V2 agent 可在聊天页面端到端对话
- [ ] 流式 token 输出正常
- [ ] 工具调用全链路（LLM emit tool_call → resolve → gate → execute → result → LLM 再思考）
- [ ] 多轮 loop（LLM 看到 tool_result 后继续 thinking，直到不再 emit tool_calls）
- [ ] 权限 ASK（写操作触发 AWAITING_TOOL_PERMISSION，用户允许后继续）
- [ ] 子 agent spawn（SpawnSubagentTool 触发 AWAITING_SUB_AGENT，子 agent 完成后父续）
- [ ] 崩溃恢复（kill 进程后重启，从最后 step 续上）
- [ ] 上下文压缩（长对话触发 ContextEngine cold handoff）
- [ ] 记忆写入（turn 结束后 write_turn_lightweight）
- [ ] 记忆检索（thinking 前 retrieve_relevant_memories 注入 prompt）
- [ ] DoomLoop 检测（连续 3 次相同 tool_call 被阻止）
- [ ] 工具失败跟踪（同工具失败 3 次后 block）
- [ ] usage_metric 实时显示（TokenStatusBar）
- [ ] Truncator（长输出归档到 AFS + dattach tag）

### 8.2 对比验证

- [ ] 同一 prompt 在 BAIZE / V2 跑，行为一致（工具调用 / 回答质量 / token 消耗）
- [ ] V2 SSE 协议与 BAIZE 兼容（前端无感知切换）

### 8.3 测试

- [ ] V2 内核 P2-P4 测试 151/151 通过（不改内核）
- [ ] V2 框架新模块测试（run_loop / default_thinking_fn / default_acting_fn / ToolFailureTracker / retrying_thinking / ToolResolver）90%+ 覆盖
- [ ] 集成测试：V2 agent 端到端跑通所有 8.1 项

---

## 9. 工作量估算

| 阶段 | 工作量 | 内容 |
|---|---|---|
| Week 1 | 5 天 | `run_loop` + `ToolFailureTracker` + `retrying_thinking` + `ToolResolver` + 单测 |
| Week 2 | 5 天 | `default_thinking_fn`（ContextEngine + Memory 集成）+ `default_acting_fn`（DoomLoop + Truncator 集成）+ 单测 |
| Week 3 | 4 天 | 产品入口（runtime_version 字段 + 后端分发 + Agent 编辑页面）+ 集成测试 |
| Week 4 | 3 天 | 对比测试 + 修 bug + 文档 |

**总计：~3-4 周**

---

## 10. 决策记录

| # | 决策 | 理由 |
|---|---|---|
| 1 | V2 是 BAIZE 框架的继任者，不是并列第二套 | 用户明确：验证完直接删 BAIZE，只维护一套 |
| 2 | V2 内核 dict 接口不改 | 避免改 P2-P4 测试；翻译在 default_acting_fn 内，框架默认提供 |
| 3 | 子系统原样搬，无 adapter | 不要过渡设计；子系统已是干净抽象 |
| 4 | 跳过 HookDispatcher，直接调 manager 方法 | HookDispatcher 依赖 HookManager 抽象，V2 暂不集成；直接调减少耦合 |
| 5 | 删除 `UnifiedCompactionPipeline` L2/L3/L4 | ContextEngine 已覆盖，重复调用会打架；保留 L1（truncate_output） |
| 6 | `run_loop` 用 `StepState` 驱动，无 if/else 地狱 | V2 内核状态机已就绪，利用它 |
| 7 | Agent 实例配置对齐 BAIZE `agent_info` | 迁移成本 = 改 `runtime_version` 字段 |
| 8 | 过渡期 BAIZE / V2 共享子系统存储 | 状态互通，对比测试可行 |

---

## 11. 后续 spec

- **删除 BAIZE 主壳**：验证通过后，删除 `react_master_agent.py` / `generate_reply` / 旧 memory / CompactionPipeline L2-L4 / `tool_action.py`，预计 ~6000 行
- **V2 内核原生 ToolCall/ToolResult**（如果翻译成本痛）：让 acting_fn 原生收 ToolCall 返 ToolResult，改 P2-P4 测试
- **HookManager 集成**（如果需要完整 hook 链）：把 memory tier1/2/3 / 审计 / 日志挂回 HookManager
- **多 agent 编排**：group chat / next_speakers / peer routing（BAIZE 也没有，需新设计）

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
