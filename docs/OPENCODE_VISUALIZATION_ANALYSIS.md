# OpenCode 项目可视化实现方案深度分析报告

## 一、架构概述

### 1.1 整体架构

OpenCode 采用 **三层架构** 实现可视化:

```
┌─────────────────────────────────────────────────────────────┐
│                   终端UI层 (TUI)                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   SolidJS + OpenTUI 渲染引擎                          │   │
│  │   - 组件化渲染 (Message, Tool, Prompt)                 │   │
│  │   - 响应式状态管理 (Signals)                           │   │
│  │   - 流式更新机制 (实时渲染)                            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          ▲ SSE/WebSocket
                          │
┌─────────────────────────────────────────────────────────────┐
│                   服务端层 (Server)                           │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │   Hono Server  │  │  BusEvent      │  │  Session     │  │
│  │   - REST API   │  │  - 事件广播    │  │  - 消息存储  │  │
│  │   - SSE Stream │  │  - 实时推送    │  │  - 状态管理  │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          ▲
                          │
┌─────────────────────────────────────────────────────────────┐
│                   Agent层 (LLM Integration)                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   AI SDK + Provider System                            │   │
│  │   - streamText() 流式生成                             │   │
│  │   - Tool Execution (动态工具调用)                      │   │
│  │   - Message Parts (细粒度消息组件)                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 二、核心组件分析

### 2.1 终端UI层 (TUI)

**技术栈**: SolidJS + OpenTUI (自定义终端渲染引擎)

**核心文件**: `packages/opencode/src/cli/cmd/tui/app.tsx`

#### 2.1.1 渲染架构

```typescript
// app.tsx:102-180
export function tui(input: {
  url: string
  args: Args
  directory?: string
  fetch?: typeof fetch
  events?: EventSource
  onExit?: () => Promise<void>
}) {
  return new Promise<void>(async (resolve) => {
    const mode = await getTerminalBackgroundColor()
    const onExit = async () => {
      await input.onExit?.()
      resolve()
    }

    render(
      () => {
        return (
          <ErrorBoundary fallback={(error, reset) => <ErrorComponent ... />}>
            <ArgsProvider {...input.args}>
              <ExitProvider onExit={onExit}>
                <KVProvider>
                  <ToastProvider>
                    <RouteProvider>
                      <SDKProvider url={input.url} ...>
                        <SyncProvider>
                          <ThemeProvider mode={mode}>
                            <LocalProvider>
                              <KeybindProvider>
                                <App />
                              </KeybindProvider>
                            </LocalProvider>
                          </ThemeProvider>
                        </SyncProvider>
                      </SDKProvider>
                    </RouteProvider>
                  </ToastProvider>
                </KVProvider>
              </ExitProvider>
            </ArgsProvider>
          </ErrorBoundary>
        )
      },
      {
        targetFps: 60,  // 60 FPS 渲染目标
        exitOnCtrlC: false,
        useKittyKeyboard: {},
      },
    )
  })
}
```

**关键设计**:
- **Provider 模式**: 多层 Context Provider 注入依赖
- **60 FPS 渲染**: 使用 OpenTUI 实现高性能终端渲染
- **响应式架构**: 基于 SolidJS 的细粒度响应式系统

#### 2.1.2 消息渲染系统

**核心文件**: `packages/opencode/src/cli/cmd/tui/routes/session/index.tsx`

```typescript
// session/index.tsx:1218-1294
function AssistantMessage(props: { message: AssistantMessage; parts: Part[]; last: boolean }) {
  const local = useLocal()
  const { theme } = useTheme()
  const sync = useSync()
  const messages = createMemo(() => sync.data.message[props.message.sessionID] ?? [])

  const final = createMemo(() => {
    return props.message.finish && !["tool-calls", "unknown"].includes(props.message.finish)
  })

  const duration = createMemo(() => {
    if (!final()) return 0
    if (!props.message.time.completed) return 0
    const user = messages().find((x) => x.role === "user" && x.id === props.message.parentID)
    if (!user || !user.time) return 0
    return props.message.time.completed - user.time.created
  })

  return (
    <>
      <For each={props.parts}>
        {(part, index) => {
          const component = createMemo(() => PART_MAPPING[part.type as keyof typeof PART_MAPPING])
          return (
            <Show when={component()}>
              <Dynamic
                last={index() === props.parts.length - 1}
                component={component()}
                part={part as any}
                message={props.message}
              />
            </Show>
          )
        }}
      </For>
      {/* 错误处理 */}
      <Show when={props.message.error && props.message.error.name !== "MessageAbortedError"}>
        <box border={["left"]} paddingTop={1} paddingBottom={1} paddingLeft={2} marginTop={1}
             backgroundColor={theme.backgroundPanel} borderColor={theme.error}>
          <text fg={theme.textMuted}>{props.message.error?.data.message}</text>
        </box>
      </Show>
      {/* 状态元数据 */}
      <Switch>
        <Match when={props.last || final() || props.message.error?.name === "MessageAbortedError"}>
          <box paddingLeft={3}>
            <text marginTop={1}>
              <span style={{ fg: local.agent.color(props.message.agent) }}>▣ </span>
              <span style={{ fg: theme.text }}>{Locale.titlecase(props.message.mode)}</span>
              <span style={{ fg: theme.textMuted }}> · {props.message.modelID}</span>
              <Show when={duration()}>
                <span style={{ fg: theme.textMuted }}> · {Locale.duration(duration())}</span>
              </Show>
            </text>
          </box>
        </Match>
      </Switch>
    </>
  )
}

// Part 类型映射
const PART_MAPPING = {
  text: TextPart,
  tool: ToolPart,
  reasoning: ReasoningPart,
}
```

**关键设计**:
- **Part 组件化**: 每个消息由多个 Part 组成，独立渲染
- **动态组件映射**: `PART_MAPPING` + `Dynamic` 实现类型驱动的渲染
- **响应式更新**: 使用 `createMemo` 实现细粒度依赖追踪
- **实时状态**: 显示 Agent、Model、Duration 等元数据

#### 2.1.3 工具调用可视化

```typescript
// session/index.tsx:1370-1455
function ToolPart(props: { last: boolean; part: ToolPart; message: AssistantMessage }) {
  const ctx = use()
  const sync = useSync()

  // 根据配置决定是否显示完成的工具
  const shouldHide = createMemo(() => {
    if (ctx.showDetails()) return false
    if (props.part.state.status !== "completed") return false
    return true
  })

  const toolprops = {
    get metadata() {
      return props.part.state.status === "pending" ? {} : (props.part.state.metadata ?? {})
    },
    get input() {
      return props.part.state.input ?? {}
    },
    get output() {
      return props.part.state.status === "completed" ? props.part.state.output : undefined
    },
    get permission() {
      const permissions = sync.data.permission[props.message.sessionID] ?? []
      const permissionIndex = permissions.findIndex((x) => x.tool?.callID === props.part.callID)
      return permissions[permissionIndex]
    },
    get tool() {
      return props.part.tool
    },
    get part() {
      return props.part
    },
  }

  return (
    <Show when={!shouldHide()}>
      <Switch>
        <Match when={props.part.tool === "bash"}>
          <Bash {...toolprops} />
        </Match>
        <Match when={props.part.tool === "glob"}>
          <Glob {...toolprops} />
        </Match>
        <Match when={props.part.tool === "read"}>
          <Read {...toolprops} />
        </Match>
        {/* ... 其他工具 */}
        <Match when={true}>
          <GenericTool {...toolprops} />
        </Match>
      </Switch>
    </Show>
  )
}

// Bash 工具示例 - BlockTool 模式
function Bash(props: ToolProps<typeof BashTool>) {
  const { theme } = useTheme()
  const sync = useSync()
  const output = createMemo(() => stripAnsi(props.metadata.output?.trim() ?? ""))
  const [expanded, setExpanded] = createSignal(false)
  const lines = createMemo(() => output().split("\n"))
  const overflow = createMemo(() => lines().length > 10)
  const limited = createMemo(() => {
    if (expanded() || !overflow()) return output()
    return [...lines().slice(0, 10), "…"].join("\n")
  })

  return (
    <Switch>
      <Match when={props.metadata.output !== undefined}>
        <BlockTool
          title={title()}
          part={props.part}
          onClick={overflow() ? () => setExpanded((prev) => !prev) : undefined}
        >
          <box gap={1}>
            <text fg={theme.text}>$ {props.input.command}</text>
            <text fg={theme.text}>{limited()}</text>
            <Show when={overflow()}>
              <text fg={theme.textMuted}>{expanded() ? "Click to collapse" : "Click to expand"}</text>
            </Show>
          </box>
        </BlockTool>
      </Match>
      <Match when={true}>
        <InlineTool icon="$" pending="Writing command..." complete={props.input.command} part={props.part}>
          {props.input.command}
        </InlineTool>
      </Match>
    </Switch>
  )
}
```

**关键设计**:
- **双模式渲染**: `InlineTool` (行内) vs `BlockTool` (块级)
- **状态驱动**: `pending` vs `completed` 状态切换渲染模式
- **交互式**: 支持 expand/collapse、click 等交互
- **输出截断**: 自动处理长输出，提供展开功能

### 2.2 服务端层 (Server)

**核心文件**: `packages/opencode/src/server/server.ts`

#### 2.2.1 事件流架构

```typescript
// server/server.ts:1-200
import { streamSSE } from "hono/streaming"

export namespace Server {
  const app = new Hono()
  
  export const App: () => Hono = lazy(
    () => app
      .onError((err, c) => {
        log.error("failed", { error: err })
        if (err instanceof NamedError) {
          return c.json(err.toObject(), { status: 500 })
        }
        return c.json(new NamedError.Unknown({ message: err.toString() }).toObject(), {
          status: 500,
        })
      })
      .use(cors({ origin: corsHandler }))
      .route("/global", GlobalRoutes())
      .route("/session", SessionRoutes())
      // ... 其他路由
  )
}
```

#### 2.2.2 事件广播系统

**核心文件**: `packages/opencode/src/bus/bus-event.ts`

```typescript
// bus/bus-event.ts
export namespace BusEvent {
  const registry = new Map<string, Definition>()

  export function define<Type extends string, Properties extends ZodType>(
    type: Type, 
    properties: Properties
  ) {
    const result = { type, properties }
    registry.set(type, result)
    return result
  }

  export function payloads() {
    return z.discriminatedUnion(
      "type",
      registry.entries().map(([type, def]) => {
        return z.object({
          type: z.literal(type),
          properties: def.properties,
        })
      }).toArray()
    )
  }
}
```

**关键设计**:
- **类型安全**: 使用 Zod 定义事件 schema
- **事件注册**: 全局 registry 管理所有事件类型
- **Payload 联合类型**: 自动生成 discriminated union

### 2.3 Agent层 (LLM Integration)

**核心文件**: `packages/opencode/src/session/llm.ts`

#### 2.3.1 流式生成架构

```typescript
// session/llm.ts:28-275
export namespace LLM {
  export type StreamInput = {
    user: MessageV2.User
    sessionID: string
    model: Provider.Model
    agent: Agent.Info
    system: string[]
    abort: AbortSignal
    messages: ModelMessage[]
    tools: Record<string, Tool>
  }

  export type StreamOutput = StreamTextResult<ToolSet, unknown>

  export async function stream(input: StreamInput) {
    const [language, cfg, provider, auth] = await Promise.all([
      Provider.getLanguage(input.model),
      Config.get(),
      Provider.getProvider(input.model.providerID),
      Auth.get(input.model.providerID),
    ])

    // 系统提示词处理
    const system = []
    system.push([
      ...(input.agent.prompt ? [input.agent.prompt] : SystemPrompt.provider(input.model)),
      ...input.system,
      ...(input.user.system ? [input.user.system] : []),
    ].filter((x) => x).join("\n"))

    // 工具解析
    const tools = await resolveTools(input)

    // 使用 AI SDK 的 streamText
    return streamText({
      onError(error) {
        log.error("stream error", { error })
      },
      async experimental_repairToolCall(failed) {
        const lower = failed.toolCall.toolName.toLowerCase()
        if (lower !== failed.toolCall.toolName && tools[lower]) {
          return { ...failed.toolCall, toolName: lower }
        }
        return {
          ...failed.toolCall,
          input: JSON.stringify({
            tool: failed.toolCall.toolName,
            error: failed.error.message,
          }),
          toolName: "invalid",
        }
      },
      temperature: params.temperature,
      topP: params.topP,
      providerOptions: ProviderTransform.providerOptions(input.model, params.options),
      activeTools: Object.keys(tools).filter((x) => x !== "invalid"),
      tools,
      abortSignal: input.abort,
      messages: [
        ...system.map((x): ModelMessage => ({ role: "system", content: x })),
        ...input.messages,
      ],
      model: wrapLanguageModel({
        model: language,
        middleware: [
          extractReasoningMiddleware({ tagName: "think", startWithReasoning: false }),
        ],
      }),
    })
  }
}
```

**关键设计**:
- **AI SDK 集成**: 使用 Vercel AI SDK 的 `streamText`
- **Middleware 架构**: 支持 reasoning 提取、参数转换等中间件
- **Tool 修复**: 自动修复工具名称大小写问题
- **Abort 支持**: 支持中断流式生成

#### 2.3.2 Message Part 系统

**核心文件**: `packages/opencode/src/session/message-v2.ts`

```typescript
// message-v2.ts:39-200
export namespace MessageV2 {
  const PartBase = z.object({
    id: z.string(),
    sessionID: z.string(),
    messageID: z.string(),
  })

  // 文本 Part
  export const TextPart = PartBase.extend({
    type: z.literal("text"),
    text: z.string(),
    synthetic: z.boolean().optional(),
    ignored: z.boolean().optional(),
    time: z.object({
      start: z.number(),
      end: z.number().optional(),
    }).optional(),
    metadata: z.record(z.string(), z.any()).optional(),
  })

  // Reasoning Part (思维链)
  export const ReasoningPart = PartBase.extend({
    type: z.literal("reasoning"),
    text: z.string(),
    metadata: z.record(z.string(), z.any()).optional(),
    time: z.object({
      start: z.number(),
      end: z.number().optional(),
    }),
  })

  // 工具调用 Part
  export const ToolPart = PartBase.extend({
    type: z.literal("tool"),
    tool: z.string(),
    callID: z.string(),
    state: z.discriminatedUnion("status", [
      z.object({
        status: z.literal("pending"),
        input: z.any(),
      }),
      z.object({
        status: z.literal("completed"),
        input: z.any(),
        output: z.any(),
        metadata: z.record(z.string(), z.any()).optional(),
      }),
      z.object({
        status: z.literal("error"),
        input: z.any(),
        error: z.string(),
      }),
    ]),
  })

  // 文件 Part
  export const FilePart = PartBase.extend({
    type: z.literal("file"),
    mime: z.string(),
    filename: z.string().optional(),
    url: z.string(),
    source: FilePartSource.optional(),
  })

  // 消息结构
  export const Message = z.discriminatedUnion("role", [
    UserMessage,
    AssistantMessage,
  ])
}
```

**关键设计**:
- **细粒度 Part**: 每个消息由多个 Part 组成
- **状态机**: Tool Part 支持 pending → completed/error 状态转换
- **时间追踪**: 每个 Part 记录开始和结束时间
- **元数据**: 支持自定义 metadata 字段

### 2.4 Worker 层 (进程间通信)

**核心文件**: `packages/opencode/src/cli/cmd/tui/worker.ts`

```typescript
// worker.ts:1-152
import { createOpencodeClient, type Event } from "@opencode-ai/sdk/v2"
import { Rpc } from "@/util/rpc"

const eventStream = {
  abort: undefined as AbortController | undefined,
}

const startEventStream = (directory: string) => {
  const abort = new AbortController()
  eventStream.abort = abort
  const signal = abort.signal

  const sdk = createOpencodeClient({
    baseUrl: "http://opencode.internal",
    directory,
    fetch: fetchFn,
    signal,
  })

  ;(async () => {
    while (!signal.aborted) {
      const events = await Promise.resolve(
        sdk.event.subscribe({}, { signal })
      ).catch(() => undefined)

      if (!events) {
        await Bun.sleep(250)
        continue
      }

      // 流式处理事件
      for await (const event of events.stream) {
        Rpc.emit("event", event as Event)
      }

      if (!signal.aborted) {
        await Bun.sleep(250)
      }
    }
  })().catch((error) => {
    Log.Default.error("event stream error", { error })
  })
}

export const rpc = {
  async fetch(input: { url: string; method: string; headers: Record<string, string>; body?: string }) {
    const response = await Server.App().fetch(request)
    const body = await response.text()
    return {
      status: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      body,
    }
  },
  async server(input: { port: number; hostname: string }) {
    if (server) await server.stop(true)
    server = Server.listen(input)
    return { url: server.url.toString() }
  },
  async shutdown() {
    if (eventStream.abort) eventStream.abort.abort()
    await Instance.disposeAll()
    if (server) server.stop(true)
  },
}

Rpc.listen(rpc)
```

**关键设计**:
- **RPC 通信**: 使用 RPC 实现进程间通信
- **Event Stream**: 持续订阅服务端事件
- **Abort 控制**: 支持优雅关闭
- **自动重连**: 失败后自动重试

## 三、与 derisk VIS 协议的对比分析

### 3.1 架构差异对比

| 维度 | OpenCode | derisk VIS |
|------|----------|------------|
| **渲染引擎** | OpenTUI (自定义终端渲染) | HTML/Canvas (Web渲染) |
| **组件模型** | Part 系统 (细粒度组件) | Block 系统 (块级组件) |
| **状态管理** | SolidJS Signals (响应式) | Python 对象 (手动管理) |
| **流式传输** | SSE + WebSocket | WebSocket |
| **事件系统** | BusEvent (类型安全) | ProgressBroadcaster (简单事件) |
| **存储** | Session + Part (结构化) | GptsMemory (对话存储) |

### 3.2 流式处理方式对比

#### OpenCode 流式处理

```typescript
// 1. Agent 层生成流
const stream = await streamText({
  model: language,
  messages: [...],
  tools: {...},
})

// 2. 自动 Part 分解
for await (const part of stream.fullStream) {
  if (part.type === "text-delta") {
    // 自动创建 TextPart
    emit("message.part.updated", {
      part: { type: "text", text: part.textDelta }
    })
  }
  if (part.type === "tool-call") {
    // 自动创建 ToolPart (pending 状态)
    emit("message.part.updated", {
      part: { 
        type: "tool", 
        tool: part.toolName,
        state: { status: "pending", input: part.args }
      }
    })
  }
}

// 3. 工具执行后更新 Part 状态
emit("message.part.updated", {
  part: {
    type: "tool",
    tool: "bash",
    state: { status: "completed", output: "..." }
  }
})

// 4. TUI 响应式渲染
createEffect(() => {
  const parts = sync.data.part[messageID]
  // 自动重新渲染
})
```

#### derisk VIS 流式处理

```python
# 1. 手动创建 Block
block_id = await canvas.add_thinking("分析中...")

# 2. 手动更新 Block
await canvas.update_thinking(block_id, thought="完成分析")

# 3. 手动推送 VIS 协议
vis_text = await vis_converter.convert(block)
await gpts_memory.push(vis_text)

# 4. 前端渲染
# 前端接收 VIS 文本并解析渲染
```

**关键差异**:
- **自动化程度**: OpenCode 自动分解 Part，derisk 手动创建 Block
- **状态同步**: OpenCode 响应式自动更新，derisk 手动推送
- **类型安全**: OpenCode 强类型 Part，derisk 弱类型 VIS 文本

### 3.3 可视化能力对比

#### OpenCode 工具可视化

```typescript
// InlineTool 模式 - 简洁行内显示
<InlineTool icon="$" pending="Writing command..." complete={props.input.command}>
  {props.input.command}
</InlineTool>

// BlockTool 模式 - 详细块级显示
<BlockTool title="# Bash" onClick={toggleExpand}>
  <text>$ {command}</text>
  <text>{output}</text>
  <text>Click to expand</text>
</BlockTool>

// 交互能力
- Expand/Collapse 长输出
- Click 跳转到详情
- Hover 高亮显示
- Selection 复制文本
```

#### derisk VIS 工具可视化

```python
# Block 模式 - 结构化块级显示
await canvas.add_tool_call(
    tool_name="bash",
    tool_args={"command": "ls -la"},
    status="running"
)

# VIS 协议输出
"""
## Tool Call

**Tool**: bash
**Command**: `ls -la`
**Status**: running

```bash
output here...
```
"""

# 交互能力
- Markdown 渲染
- 代码高亮
- 状态标记
```

**关键差异**:
- **交互性**: OpenCode 支持丰富的终端交互，derisk 依赖前端实现
- **渲染引擎**: OpenCode 自定义终端渲染，derisk 依赖 Web 技术
- **状态反馈**: OpenCode 实时状态更新，derisk 手动状态管理

### 3.4 可扩展性设计对比

#### OpenCode 扩展机制

```typescript
// 1. Part 类型扩展
export const CustomPart = PartBase.extend({
  type: z.literal("custom"),
  data: z.any(),
})

// 2. 渲染组件注册
const PART_MAPPING = {
  text: TextPart,
  tool: ToolPart,
  custom: CustomPart,  // 新增
}

// 3. 工具扩展
function CustomTool(props: ToolProps<CustomToolInfo>) {
  return (
    <BlockTool title="# Custom Tool">
      <CustomRenderer {...props} />
    </BlockTool>
  )
}

// 4. 自动集成到消息流
<Switch>
  <Match when={props.part.tool === "custom"}>
    <CustomTool {...toolprops} />
  </Match>
</Switch>
```

#### derisk VIS 扩展机制

```python
# 1. Block 类型扩展
class CustomBlock(Block):
    block_type = "custom"
    data: Any

# 2. 注册到 Canvas
canvas.register_block_type("custom", CustomBlock)

# 3. VIS 协议扩展
class CustomVisConverter:
    def convert(self, block: CustomBlock) -> str:
        return f"## Custom Block\n{block.data}"

# 4. 前端渲染器扩展
# 前端需要新增对应的渲染逻辑
```

**关键差异**:
- **类型安全**: OpenCode 强类型 Part，derisk 弱类型 Block
- **渲染耦合**: OpenCode 组件化渲染，derisk 前后端分离
- **扩展复杂度**: OpenCode 端到端扩展，derisk 需要前后端协调

## 四、关键技术亮点

### 4.1 响应式渲染系统

OpenCode 使用 SolidJS 的细粒度响应式系统，实现高效的增量更新:

```typescript
// 自动依赖追踪
const output = createMemo(() => props.metadata.output?.trim() ?? "")

// 只有 output 变化时才重新渲染
<text fg={theme.text}>{output()}</text>

// 条件渲染
<Show when={overflow()}>
  <text>Click to expand</text>
</Show>
```

**优势**:
- **性能**: 只更新变化的部分，避免全量重渲染
- **简洁**: 自动依赖追踪，无需手动管理
- **可读**: 声明式代码，易于理解

### 4.2 Part 组件化架构

每个消息由多个 Part 组成，独立渲染和管理:

```
Message
├── TextPart (文本内容)
├── ReasoningPart (思维链)
├── ToolPart[] (工具调用)
│   ├── Bash (bash 命令)
│   ├── Read (文件读取)
│   ├── Write (文件写入)
│   └── Edit (代码编辑)
└── FilePart[] (文件附件)
```

**优势**:
- **模块化**: 每个 Part 独立开发、测试
- **可组合**: 灵活组合不同类型的 Part
- **可扩展**: 轻松添加新的 Part 类型

### 4.3 状态驱动的渲染模式

根据状态自动切换渲染模式:

```typescript
// pending 状态 → InlineTool (简洁)
<InlineTool icon="$" pending="Writing command...">
  {command}
</InlineTool>

// completed 状态 → BlockTool (详细)
<BlockTool title="# Bash">
  <text>{command}</text>
  <text>{output}</text>
</BlockTool>

// error 状态 → 错误显示
<text fg={theme.error}>{error}</text>
```

**优势**:
- **渐进式展示**: 先显示简洁信息，后展开详细内容
- **状态可视化**: 清晰展示工具执行状态
- **用户友好**: 避免信息过载

### 4.4 终端优化渲染

OpenTUI 针对终端环境优化:

```typescript
// 60 FPS 渲染
render(() => <App />, {
  targetFps: 60,
  useKittyKeyboard: {},  // Kitty 键盘协议
})

// ANSI 颜色处理
const output = createMemo(() => stripAnsi(props.metadata.output?.trim() ?? ""))

// 终端特性适配
const mode = await getTerminalBackgroundColor()  // 检测背景色
renderer.setTerminalTitle("OpenCode")  // 设置标题
renderer.disableStdoutInterception()  // 禁用 stdout 拦截
```

**优势**:
- **高性能**: 60 FPS 流畅渲染
- **兼容性**: 支持多种终端协议
- **原生体验**: 充分利用终端特性

## 五、derisk 可借鉴的设计

### 5.1 Part 组件化系统

**建议**: 引入细粒度的 Part 系统

```python
# 定义 Part 基类
from pydantic import BaseModel
from typing import Literal, Optional, Dict, Any

class PartBase(BaseModel):
    id: str
    session_id: str
    message_id: str
    type: str

class TextPart(PartBase):
    type: Literal["text"] = "text"
    text: str
    time: Optional[Dict[str, float]] = None

class ToolPart(PartBase):
    type: Literal["tool"] = "tool"
    tool: str
    call_id: str
    state: Dict[str, Any]  # pending/completed/error

class ReasoningPart(PartBase):
    type: Literal["reasoning"] = "reasoning"
    text: str
    time: Dict[str, float]

# 消息包含多个 Part
class Message(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    parts: List[PartBase]  # 多态 Part 列表
```

### 5.2 响应式状态管理

**建议**: 引入响应式状态管理

```python
from typing import Callable, TypeVar, Generic
from dataclasses import dataclass
from watchgod import watch

T = TypeVar('T')

@dataclass
class Signal(Generic[T]):
    """简化的响应式 Signal"""
    _value: T
    _subscribers: list[Callable[[T], None]]
    
    def get(self) -> T:
        return self._value
    
    def set(self, value: T):
        if self._value != value:
            self._value = value
            for subscriber in self._subscribers:
                subscriber(value)
    
    def subscribe(self, callback: Callable[[T], None]):
        self._subscribers.append(callback)

# 使用示例
class SessionState:
    messages: Signal[list[Message]] = Signal([])
    parts: Signal[dict[str, list[Part]]] = Signal({})

# 自动更新
def render_messages(messages: list[Message]):
    for msg in messages:
        for part in msg.parts:
            render_part(part)

state.messages.subscribe(render_messages)
```

### 5.3 状态驱动的渲染模式

**建议**: 根据状态自动切换渲染模式

```python
class ToolRenderer:
    @staticmethod
    def render(part: ToolPart) -> str:
        if part.state["status"] == "pending":
            return ToolRenderer.render_inline(part)
        elif part.state["status"] == "completed":
            return ToolRenderer.render_block(part)
        else:  # error
            return ToolRenderer.render_error(part)
    
    @staticmethod
    def render_inline(part: ToolPart) -> str:
        return f"⏳ {part.tool}: {part.state.get('input', {})}"
    
    @staticmethod
    def render_block(part: ToolPart) -> str:
        return f"""
## {part.tool}

**Input**: `{part.state.get('input', {})}`

**Output**:
```
{part.state.get('output', '')}
```
"""
```

### 5.4 事件系统集成

**建议**: 引入类型安全的事件系统

```python
from typing import TypeVar, Generic, Callable
from dataclasses import dataclass
from pydantic import BaseModel

T = TypeVar('T')

@dataclass
class Event(Generic[T]):
    type: str
    properties: T

class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}
    
    def emit(self, event: Event):
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            handler(event.properties)
    
    def on(self, event_type: str, handler: Callable):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

# 使用示例
class MessagePartUpdated(BaseModel):
    part: PartBase
    session_id: str

bus = EventBus()

def on_part_updated(props: MessagePartUpdated):
    # 自动更新渲染
    render_part(props.part)

bus.on("message.part.updated", on_part_updated)

# 发送事件
bus.emit(Event(
    type="message.part.updated",
    properties=MessagePartUpdated(
        part=TextPart(...),
        session_id="..."
    )
))
```

## 六、总结与建议

### 6.1 OpenCode 的核心优势

1. **架构清晰**: 三层架构分离关注点，易于维护
2. **组件化**: Part 系统实现细粒度组件化
3. **响应式**: SolidJS 提供高效的增量更新
4. **类型安全**: TypeScript + Zod 提供端到端类型安全
5. **交互丰富**: 终端环境下的丰富交互能力

### 6.2 derisk 可改进的方向

1. **引入 Part 系统**: 替代现有的 Block 系统，实现细粒度组件化
2. **响应式状态**: 引入类似 Signal 的响应式状态管理
3. **状态驱动渲染**: 根据状态自动切换渲染模式
4. **类型安全事件**: 使用 Pydantic 定义事件 schema
5. **自动化流程**: 减少 manual 操作，提升自动化程度

### 6.3 实施建议

#### 短期 (1-2 周)
- 引入 Part 基类和核心 Part 类型
- 实现简单的响应式 Signal 机制
- 优化工具调用的可视化展示

#### 中期 (1-2 月)
- 完善 Part 系统，支持所有类型
- 实现状态驱动的渲染模式切换
- 引入类型安全的事件系统

#### 长期 (3-6 月)
- 重构 VIS 协议，基于 Part 系统
- 实现前端响应式渲染
- 提供丰富的交互能力

---

**报告生成时间**: 2026-02-28  
**分析代码版本**: OpenCode (latest)  
**对比项目**: derisk Core_v2