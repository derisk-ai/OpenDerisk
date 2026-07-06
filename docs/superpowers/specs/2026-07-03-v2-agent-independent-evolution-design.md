# V2 Agent 独立演进设计：双轨并存 + 简化VIS协议

- 日期：2026-07-03
- 状态：待用户审核
- 作者：yhjun1026 + Claude
- 前置设计：`docs/superpowers/specs/2026-06-30-agent-framework-evolution-design.md`（V2内核）、`docs/superpowers/specs/2026-07-02-v2-agent-framework-successor-design.md`（参考）
- 关联代码：`packages/derisk-core/src/derisk/agent/core/v2/`

---

## 1. 背景与目标

### 1.1 背景

2026-07-03决策关闭了V2生产入口（`agent_chat.py`的V2 dispatch分支删除），V2代码保留作参考设计。但V2内核（P0-P4）已完整实现，220个测试通过，框架价值值得保留。

现有问题：
1. **渲染层未对齐**：`sse_adapter.py`跳过V2内部事件（step_start/tool_call等），前端无对应VIS类型
2. **V2入口关闭**：无法在产品中验证V2能力
3. **BAIZE干扰风险**：直接修改BAIZE可能影响生产

### 1.2 目标

**双轨并存，V2独立演进，不干扰BAIZE**：

1. V2有独立运行入口和渲染机制
2. BAIZE继续生产运行，不受影响
3. 两套框架可并存对比，互不干扰
4. V2展示事件细粒度优势（step状态/tool执行过程/usage实时展示）

### 1.3 成功标准

| 维度 | 标准 |
|---|---|
| **最小可行** | 对话流式 + 多工具调用 + 权限ASK + 子Agent spawn 全链路跑通 |
| **渲染创新** | 简化VIS协议实现，前端能渲染V2专属组件（step状态指示器、tool执行过程、usage实时展示） |
| **BAIZE不受干扰** | BAIZE路径代码零改动，生产运行不受影响 |
| **并行开发可行** | 协议文档约定清晰，前端后端可并行开发 |

---

## 2. 架构总览

### 2.1 双轨并存

```
┌─────────────────────────────────────────────────────────────┐
│                    产品层                                    │
│  ┌──────────────────┐    ┌──────────────────┐              │
│  │ Agent编辑页面     │    │ runtime_version  │              │
│  │ 选择器：          │    │ "v1" (BAIZE)     │              │
│  │ BAIZE / V2       │    │ "v2" (V2)        │              │
│  └──────────────────┘    └──────────────────┘              │
└─────────────────────────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
┌──────────────────┐    ┌──────────────────────────────┐
│  BAIZE 框架      │    │  V2 框架（本设计）           │
│  （不动）        │    │  独立入口 + 简化VIS协议      │
│                  │    │                              │
│  SSE协议不变     │    │  新SSE协议 + 新前端解析器   │
│  VisParser不变   │    │  简化VIS解析器              │
└──────────────────┘    └──────────────────────────────┘
```

**关键原则**：
- BAIZE代码路径零改动
- V2有独立的SSE端点和协议
- 前端两套解析器并存，按`runtime_version`选择

### 2.2 分层协议架构

```
┌─────────────────────────────────────────────────────────────┐
│                    V2 协议分层                               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  事件流层（V2 SSE Event Protocol）                   │  │
│  │  - 纯时序事件，无UID索引                             │  │
│  │  - seq序列号保证顺序                                 │  │
│  │  - event类型：step_start/llm_token/tool_call/...    │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                   │
│                         │ 触发                              │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  内容渲染层（简化VIS Protocol）                      │  │
│  │  - 单一组件，无嵌套                                  │  │
│  │  - UID定位，原子操作                                 │  │
│  │  - type: incr/replace/delete                         │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**分层原因**：
- 事件流层：表达状态变迁（时间维度）
- 内容渲染层：表达组件更新（空间维度）
- 分离后各自简单，不强行混合

---

## 3. 事件流层设计

### 3.1 事件格式

```typescript
interface V2Event {
  event: string;        // 事件类型
  seq: number;          // 序列号（单调递增）
  ts: number;           // 时间戳（毫秒）
  payload: object;      // 事件数据
}
```

**SSE输出格式**：
```
data:{"event":"step_start","seq":1,"ts":123456,"payload":{"step_id":"xxx","state":"THINKING"}}
data:{"event":"llm_token","seq":2,"ts":123457,"payload":{"token":"你好"}}
data:{"event":"tool_call","seq":3,"ts":123458,"payload":{"tool":"echo","args":{...}}}
```

### 3.2 事件类型定义

| event | payload | 触发时机 |
|---|---|---|
| `step_start` | `{step_id, state, agent_id}` | step初始化，state=INIT |
| `llm_token` | `{token, usage?}` | LLM流式输出每个token |
| `tool_call` | `{tool, args, tool_call_id}` | LLM决定调用工具 |
| `tool_result` | `{tool_call_id, result, success}` | 工具执行完成 |
| `interaction_request` | `{type, options, request_id}` | 权限ASK/用户确认 |
| `usage_metric` | `{step_id, cumulative, ratio}` | LLM调用结束，累计token |
| `sub_agent_start` | `{sub_agent_id, task, conv_id}` | 子Agent spawn |
| `sub_agent_result` | `{sub_agent_id, result}` | 子Agent完成 |
| `step_end` | `{step_id, state, had_tool_calls}` | step完成，state=DONE |
| `vis_update` | `{type, uid, tag, content, meta?}` | 触发简化VIS更新 |
| `error` | `{message, code?}` | 错误发生 |
| `done` | `{}` | 对话结束 |

### 3.3 事件流示例

**单工具调用流程**：
```
seq=1  event=step_start     payload={step_id:"s1",state:"INIT"}
seq=2  event=llm_token      payload={token:"我"}
seq=3  event=llm_token      payload={token:"来"}
seq=4  event=llm_token      payload={token:"帮"}
seq=5  event=llm_token      payload={token:"你"}
seq=6  event=tool_call      payload={tool:"echo",args:{msg:"hello"}}
seq=7  event=step_status    payload={step_id:"s1",state:"ACTING"}
seq=8  event=tool_result    payload={tool_call_id:"tc1",result:"hello",success:true}
seq=9  event=step_status    payload={step_id:"s1",state:"OBSERVING"}
seq=10 event=llm_token      payload={token:"工具"}
seq=11 event=llm_token      payload={token:"执行"}
seq=12 event=llm_token      payload={token:"完成"}
seq=13 event=usage_metric   payload={cumulative:{total:150},ratio:0.001}
seq=14 event=step_end       payload={step_id:"s1",state:"DONE"}
seq=15 event=done           payload={}
```

---

## 4. 内容渲染层设计（简化VIS Protocol）

### 4.1 核心模型

**简化原则**：
- 单一组件，无嵌套markdown/items
- UID定位，原子操作
- meta字段扩展元数据

```typescript
interface SimplifiedVisComponent {
  type: "incr" | "replace" | "delete";  // 操作类型
  uid: string;                           // 组件唯一标识
  tag: string;                           // 组件类型标签
  content: string;                       // markdown内容（扁平）
  meta?: object;                         // 元数据（可选）
}
```

### 4.2 操作语义

| type | 语义 | 前端行为 |
|---|---|---|
| `incr` | 增量追加 | `component.content += new_content` |
| `replace` | 全量替换 | `component.content = new_content` |
| `delete` | 删除组件 | 移除该UID的DOM节点 |

### 4.3 组件类型定义（tag）

| tag | 用途 | meta字段 |
|---|---|---|
| `message` | LLM输出的消息 | `{role:"assistant"}` |
| `thinking` | LLM思考块 | `{state:"streaming"}` |
| `tool_result` | 工具执行结果 | `{tool:"echo",success:true}` |
| `step_status` | step状态指示器 | `{state:"THINKING",step_id:"s1"}` |
| `usage_display` | token用量展示 | `{total:150,ratio:0.001}` |
| `sub_agent_panel` | 子Agent面板 | `{agent_name:"BAIZE",task:"..."}` |
| `interaction_prompt` | 用户交互提示 | `{type:"confirm",options:[...]}` |
| `error_block` | 错误展示 | `{code:"E001"}` |

### 4.4 UID命名约定

**UID结构**：`{step_id}-{component_type}-{index}`

示例：
```
s1-thinking-0        // step s1的thinking块
s1-tool-echo-0       // step s1的echo工具结果
s1-usage-0           // step s1的用量展示
s2-thinking-0        // step s2的thinking块
```

**聚合约定**：前端按`{step_id}-*`前缀聚合，渲染成step面板。

### 4.5 VIS更新事件格式

VIS更新通过`vis_update`事件触发：

```
data:{"event":"vis_update","seq":16,"ts":123470,"payload":{"type":"incr","uid":"s1-thinking-0","tag":"thinking","content":"分析中..."}}
data:{"event":"vis_update","seq":17,"ts":123471,"payload":{"type":"replace","uid":"s1-step_status-0","tag":"step_status","content":"","meta":{"state":"ACTING"}}}
data:{"event":"vis_update","seq":18,"ts":123472,"payload":{"type":"incr","uid":"s1-tool-echo-0","tag":"tool_result","content":"执行结果：hello"}}
```

---

## 5. 前端渲染机制

### 5.1 双协议解析器并存

```typescript
// 解析器选择
function createParser(runtimeVersion: "v1" | "v2") {
  if (runtimeVersion === "v1") {
    return new BaizeVisParser();  // 现有VisParser
  } else {
    return new V2SimplifiedVisParser();  // 新解析器
  }
}
```

### 5.2 V2前端解析器实现

```typescript
class V2SimplifiedVisParser {
  private components: Map<string, VisComponentState> = new Map();

  // 处理事件流
  handleEvent(event: V2Event) {
    switch (event.event) {
      case "step_start":
        this.emitVisUpdate({
          type: "replace",
          uid: `${event.payload.step_id}-step_status-0`,
          tag: "step_status",
          content: "",
          meta: { state: event.payload.state },
        });
        break;

      case "llm_token":
        // 自动追加到当前thinking组件
        const thinkingUid = `${currentStepId}-thinking-0`;
        this.emitVisUpdate({
          type: "incr",
          uid: thinkingUid,
          tag: "thinking",
          content: event.payload.token,
        });
        break;

      case "vis_update":
        // 直接处理
        this.handleVisUpdate(event.payload);
        break;

      // ... 其他事件类型
    }
  }

  // 处理VIS更新
  handleVisUpdate(component: SimplifiedVisComponent) {
    switch (component.type) {
      case "incr":
        const existing = this.components.get(component.uid);
        if (existing) {
          existing.content += component.content;
          if (component.meta) {
            existing.meta = { ...existing.meta, ...component.meta };
          }
        } else {
          this.components.set(component.uid, component);
        }
        break;

      case "replace":
        this.components.set(component.uid, component);
        break;

      case "delete":
        this.components.delete(component.uid);
        break;
    }

    // 触发渲染
    this.render();
  }

  // 渲染
  render() {
    // 按UID前缀聚合成step面板
    const stepGroups = this.groupByStep();
    // 渲染每个step面板
    for (const [stepId, components] of stepGroups) {
      renderStepPanel(stepId, components);
    }
  }

  groupByStep(): Map<string, VisComponentState[]> {
    const groups = new Map();
    for (const [uid, component] of this.components) {
      const stepId = uid.split("-")[0];
      if (!groups.has(stepId)) {
        groups.set(stepId, []);
      }
      groups.get(stepId).push(component);
    }
    return groups;
  }
}
```

### 5.3 step面板渲染示例

```tsx
function renderStepPanel(stepId: string, components: VisComponentState[]) {
  return (
    <div className="step-panel" key={stepId}>
      {/* step状态指示器 */}
      <StepStatusIndicator component={components.find(c => c.tag === "step_status")} />

      {/* thinking块 */}
      {components.filter(c => c.tag === "thinking").map(c => (
        <ThinkingBlock key={c.uid} content={c.content} />
      ))}

      {/* tool结果块 */}
      {components.filter(c => c.tag === "tool_result").map(c => (
        <ToolResultBlock key={c.uid} tool={c.meta?.tool} content={c.content} />
      ))}

      {/* 用量展示 */}
      <UsageDisplay component={components.find(c => c.tag === "usage_display")} />
    </div>
  );
}
```

---

## 6. 后端事件发射机制

### 6.1 V2 SSE端点

**新增端点**：`/api/v2/chat`（独立于BAIZE的`/api/v1/chat/completions`）

```python
# agent_chat.py 新增
@router.post("/api/v2/chat")
async def v2_chat(request: V2ChatRequest):
    agent_info = await get_agent_info(request.agent_id)

    if agent_info.runtime_version != "v2":
        raise ValueError("Agent not configured for V2")

    async def event_stream():
        async for event in run_v2_agent(agent_info, request):
            yield f"data:{json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )
```

### 6.2 事件发射器

```python
# v2/event_emitter.py（新文件）
class V2EventEmitter:
    def __init__(self, step_id: str, agent_id: str, conv_id: str):
        self.step_id = step_id
        self.agent_id = agent_id
        self.conv_id = conv_id
        self.seq = 0

    async def emit(self, event: str, payload: dict) -> V2Event:
        self.seq += 1
        return {
            "event": event,
            "seq": self.seq,
            "ts": int(time.time() * 1000),
            "payload": payload,
        }

    async def emit_vis_update(self, component: SimplifiedVisComponent) -> V2Event:
        return await self.emit("vis_update", component)
```

### 6.3 run_step集成

```python
# v2/runtime.py 改造
async def run_step(...) -> AsyncGenerator[V2Event, None]:
    emitter = V2EventEmitter(step_id, agent_id, conv_id)

    # INIT
    yield await emitter.emit("step_start", {"step_id": step_id, "state": "INIT", "agent_id": agent_id})

    # THINKING
    yield await emitter.emit("step_status", {"step_id": step_id, "state": "THINKING"})
    async for chunk in thinking_fn(input_):
        if chunk.token:
            yield await emitter.emit("llm_token", {"token": chunk.token})
            # 同时触发VIS更新
            yield await emitter.emit_vis_update({
                "type": "incr",
                "uid": f"{step_id}-thinking-0",
                "tag": "thinking",
                "content": chunk.token,
            })
        if chunk.tool_calls:
            for tc in chunk.tool_calls:
                yield await emitter.emit("tool_call", {"tool": tc.name, "args": tc.args, "tool_call_id": tc.id})

    # ACTING
    yield await emitter.emit("step_status", {"step_id": step_id, "state": "ACTING"})
    for tc in tool_calls:
        result = await acting_fn(tc, context)
        yield await emitter.emit("tool_result", {"tool_call_id": tc.id, "result": result.output, "success": result.success})
        yield await emitter.emit_vis_update({
            "type": "incr",
            "uid": f"{step_id}-tool-{tc.name}-0",
            "tag": "tool_result",
            "content": str(result.output),
            "meta": {"tool": tc.name, "success": result.success},
        })

    # DONE
    yield await emitter.emit("step_end", {"step_id": step_id, "state": "DONE", "had_tool_calls": len(tool_calls) > 0})
```

---

## 7. 实现计划

### 7.1 工作分解

| 模块 | 工作量 | 依赖 |
|---|---|---|
| **协议文档** | 1天 | 无 |
| **后端事件发射器** | 2天 | 协议文档 |
| **后端V2 SSE端点** | 1天 | 事件发射器 |
| **run_step集成** | 2天 | 事件发射器 |
| **前端V2解析器** | 3天 | 协议文档 |
| **前端V2组件库** | 3天 | V2解析器 |
| **产品入口** | 1天 | 后端+前端 |
| **集成测试** | 2天 | 全部 |

**总计：约2周**

### 7.2 并行开发路径

```
Week 1:
  后端：协议文档 → 事件发射器 → V2 SSE端点
  前端：协议文档 → V2解析器 → V2组件库（基础）

Week 2:
  后端：run_step集成 → 产品入口
  前端：V2组件库（完成） → 集成测试
```

---

## 8. 验证标准

### 8.1 功能验证

| 场景 | 验证点 |
|---|---|
| **对话流式** | token增量追加渲染，thinking块展示 |
| **单工具调用** | tool_call事件 → tool_result渲染 |
| **多工具调用** | 多个tool_result块按UID区分 |
| **权限ASK** | interaction_request → interaction_prompt组件 → 用户响应 |
| **子Agent spawn** | sub_agent_start → sub_agent_panel组件 → sub_agent_result |
| **用量展示** | usage_metric → usage_display组件实时更新 |
| **step状态指示** | step_status组件随状态变化更新 |

### 8.2 BAIZE不受干扰验证

| 验证点 | 方法 |
|---|---|
| BAIZE SSE协议不变 | 对比git diff，无改动 |
| BAIZE VisParser不变 | 对比git diff，无改动 |
| BAIZE agent实例正常运行 | 创建BAIZE agent，对话测试 |

### 8.3 性能验证

| 指标 | 标准 |
|---|---|
| 事件解析延迟 | < 5ms/事件 |
| VIS更新延迟 | < 10ms/组件 |
| 前端渲染流畅度 | 无卡顿，token追加实时展示 |

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 协议设计遗漏字段 | 协议文档预留`meta`扩展空间 |
| 前端组件渲染不一致 | 组件schema严格定义，前端按schema渲染 |
| UID命名冲突 | UID命名约定强制执行，后端验证 |
| 事件顺序错乱 | `seq`序列号保证顺序，前端按seq排序 |
| BAIZE误改动 | 代码review检查，V2代码独立目录 |

---

## 10. 决策记录

| # | 决策 | 理由 |
|---|---|---|
| 1 | 双轨并存，不替换BAIZE | 不干扰生产，保留实验空间 |
| 2 | 分层协议：事件流层 + 内容渲染层 | 事件是时间维度，组件是空间维度，分离更清晰 |
| 3 | 简化VIS：去掉嵌套，保留UID+原子操作 | 嵌套是复杂根源，去掉后解析器从700行→50行 |
| 4 | UID前缀聚合替代嵌套 | 组合通过约定而非强制，前端灵活 |
| 5 | 前端双解析器并存 | 按runtime_version选择，互不干扰 |
| 6 | meta字段预留扩展 | 未来支持动画/交互/布局，不影响协议核心 |