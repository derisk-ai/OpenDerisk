# AsyncTaskManager - 异步任务执行体系

## 1. 概述

AsyncTaskManager 为 OpenDerisk Agent 框架提供类似 Claude Code Agent Tool 的异步任务能力。主 Agent 可以在 ReAct 循环中通过标准 Tool 调用启动多个后台子 Agent 任务，继续自身工作，随时查询或等待结果，已完成的结果会自动注入到下一轮 LLM 推理上下文中。

### 核心能力

| 能力 | 描述 |
|------|------|
| 异步提交 | `spawn_agent_task` 提交后台任务，立即返回 task_id |
| 状态查询 | `check_tasks` 随时查看任务状态，不阻塞 |
| 等待结果 | `wait_tasks` 阻塞等待指定或任意任务完成 |
| 取消任务 | `cancel_task` 取消进行中的任务 |
| DAG 依赖 | `depend_on` 参数支持任务间依赖编排 |
| 自动通知 | 完成的任务结果在下一轮 think() 前自动注入 |

### 设计原则

1. **Tool 驱动** — LLM 通过标准 Tool 自主决定何时异步，不在框架层硬编码
2. **复用架构** — 底层复用 `SubagentManager.delegate()` 进行实际执行
3. **自动注入** — 完成结果以通知形式自然流入 LLM 推理上下文
4. **asyncio 原生** — 使用 Python asyncio Semaphore/Future/Event 实现
5. **渐进增强** — 对现有 Agent 架构零破坏，通过资源注入可选启用

## 2. 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Agent (ReAct Loop)                    │
│                                                               │
│  think() ──► decide() ──► act() ──► [结果注入] ──► think()   │
│                              │              ▲                  │
│              ┌───────────────┼───────────────┤                 │
│              ▼               ▼               ▼                 │
│     ┌──────────────┐ ┌────────────┐ ┌──────────────┐         │
│     │ spawn_agent  │ │ check_tasks│ │ wait_tasks   │         │
│     │   _task      │ │   (Tool)   │ │   (Tool)     │         │
│     └──────┬───────┘ └─────┬──────┘ └──────┬───────┘         │
│            │               │                │                  │
└────────────┼───────────────┼────────────────┼──────────────────┘
             │               │                │
    ┌────────▼───────────────▼────────────────▼────────┐
    │              AsyncTaskManager                     │
    │  ┌─────────┐  ┌─────────┐  ┌─────────┐          │
    │  │ Task A  │  │ Task B  │  │ Task C  │  ...     │
    │  │ RUNNING │  │ DONE    │  │ PENDING │          │
    │  └────┬────┘  └─────────┘  └─────────┘          │
    │       │                                           │
    │  ┌────▼────────────────────────────────┐         │
    │  │  SubagentManager.delegate()         │         │
    │  │  + asyncio.Semaphore 并发控制        │         │
    │  │  + asyncio.Future 完成通知           │         │
    │  └─────────────────────────────────────┘         │
    └──────────────────────────────────────────────────┘
```

### 组件关系

```
AsyncTaskManager
    ├── 复用 SubagentManager.delegate()  (实际执行)
    ├── asyncio.Semaphore                (并发限制)
    ├── asyncio.Future per task          (完成信号)
    ├── asyncio.Event                    (wait_any 通知)
    │
    └── 被以下 Tool 引用:
        ├── SpawnAgentTaskTool
        ├── CheckTasksTool
        ├── WaitTasksTool
        └── CancelTaskTool
```

## 3. 核心组件

### 3.1 数据模型

#### AsyncTaskSpec — 任务规格

```python
from derisk.agent.core_v2.async_task_manager import AsyncTaskSpec

spec = AsyncTaskSpec(
    # task_id 自动生成，格式: "atask_{8位hex}"
    agent_name="code_reviewer",         # 目标子 Agent 名称
    task_description="Review auth.py",  # 任务描述
    context={"file": "auth.py"},        # 上下文（可选）
    timeout=300,                         # 超时秒数（默认300）
    depend_on=["atask_abc12345"],        # 依赖任务列表（可选）
)
```

#### AsyncTaskStatus — 任务状态

```
PENDING ──► RUNNING ──► COMPLETED
                    ├──► FAILED
                    ├──► TIMEOUT
                    └──► CANCELLED
```

#### AsyncTaskState — 运行状态

```python
state = manager.get_status(task_id)

state.spec           # AsyncTaskSpec
state.status         # AsyncTaskStatus
state.created_at     # 创建时间
state.started_at     # 开始时间
state.completed_at   # 完成时间
state.result         # 成功结果文本
state.error          # 错误信息
state.artifacts      # 产出物字典
state.consumed       # 是否已被主Agent消费
state.is_terminal()  # 是否为终态
state.elapsed_seconds()  # 已用时间
```

### 3.2 AsyncTaskManager

```python
from derisk.agent.core_v2.async_task_manager import AsyncTaskManager

manager = AsyncTaskManager(
    subagent_manager=subagent_mgr,  # 复用现有 SubagentManager
    max_concurrent=5,                # 最大并发数
    parent_session_id="session_123", # 父会话 ID
    on_task_complete=callback,       # 完成回调（可选）
    on_task_failed=callback,         # 失败回调（可选）
)
```

**核心方法:**

| 方法 | 说明 | 异步 |
|------|------|------|
| `spawn(spec)` | 提交任务，返回 task_id | Yes |
| `get_status(task_id)` | 查单个任务状态 | No |
| `get_all_status()` | 查所有任务摘要 | No |
| `get_completed_results(consume)` | 获取未消费的完成结果 | No |
| `wait_any(timeout)` | 等待任意任务完成 | Yes |
| `wait_all(task_ids, timeout)` | 等待指定任务全部完成 | Yes |
| `cancel(task_id)` | 取消任务 | Yes |
| `has_pending_tasks()` | 是否有未完成任务 | No |
| `format_status_table()` | 格式化状态表格 | No |
| `format_results(states)` | 格式化详细结果 | No |
| `format_notifications(states)` | 格式化通知文本 | No |
| `get_statistics()` | 获取统计信息 | No |

## 4. Tool 使用手册

### 4.1 spawn_agent_task — 启动后台任务

**参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| agent_name | string | Yes | 目标子 Agent 名称 |
| task | string | Yes | 任务描述 |
| context | object | No | 上下文信息 |
| timeout | integer | No | 超时秒数（默认300） |
| depend_on | string[] | No | 依赖的 task_id 列表 |

**返回示例:**
```
任务已提交到后台执行。
- Task ID: atask_a1b2c3d4
- Agent: code_reviewer
- 描述: Review the authentication module
- 超时: 300s

你可以继续其他工作，稍后用 check_tasks 查看状态或 wait_tasks 获取结果。
```

### 4.2 check_tasks — 查看状态

**参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_ids | string[] | No | 指定查询的 task_id，为空查全部 |

**返回示例:**
```
共 3 个任务:

  [✓] atask_a1b2c3d4 (code_reviewer): completed  [12.3s]
      任务: Review the authentication module
      结果: Found 2 security issues...
  [⟳] atask_e5f6g7h8 (security_scanner): running  [5.1s]
      任务: Scan for vulnerabilities
  [○] atask_i9j0k1l2 (report_writer): pending
      任务: Generate security report
```

### 4.3 wait_tasks — 等待完成

**参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_ids | string[] | No | 等待的 task_id，为空则等任意完成 |
| timeout | integer | No | 最大等待秒数（默认60） |

**返回示例:**
```
## Task: atask_a1b2c3d4
- Agent: code_reviewer
- 状态: completed
- 耗时: 12.3s
- 结果:
Found 2 security issues in auth.py:
1. SQL injection vulnerability at line 45
2. Missing input validation at line 78
```

### 4.4 cancel_task — 取消任务

**参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | string | Yes | 要取消的 task_id |

## 5. 集成方式

### 5.1 自动集成（推荐）

当 Agent 绑定了 `AppResource`（多 Agent 场景）且有 `SubagentManager` 时，`BaseBuiltinAgent` 会自动注入异步任务工具：

```python
# base_builtin_agent.py 中的自动注入逻辑
async def _inject_async_task_tools(self):
    # 条件: AppResource + SubagentManager
    # 自动创建 AsyncTaskManager 并注册 4 个 Tool
```

无需额外配置，只要满足条件即可在 LLM 工具列表中看到异步任务相关工具。

### 5.2 手动集成

```python
from derisk.agent.core_v2.async_task_manager import AsyncTaskManager
from derisk.agent.tools.builtin.async_task import register_async_task_tools

# 1. 创建 AsyncTaskManager
async_manager = AsyncTaskManager(
    subagent_manager=my_subagent_manager,
    max_concurrent=5,
    parent_session_id="session_abc",
)

# 2. 注册 Tool 到 Agent 的 ToolRegistry
register_async_task_tools(
    registry=agent.tools,
    async_task_manager=async_manager,
)

# 3. 保存引用（用于自动通知注入）
agent._async_task_manager = async_manager
```

### 5.3 自动通知注入

在 `ReActReasoningAgent.think()` 中，每轮 LLM 调用前会自动检查并注入已完成的异步任务结果：

```python
# react_reasoning_agent.py 中的注入逻辑
async def _collect_async_task_notifications(self) -> str:
    # 获取 _async_task_manager
    # 调用 get_completed_results(consume=True)
    # 格式化为 "[异步任务完成通知]" 文本
    # 注入为 user message
```

LLM 会看到类似这样的通知：
```
[异步任务完成通知]
以下后台任务已完成，请根据结果继续工作：

### Task atask_a1b2c3d4 (code_reviewer)
状态: completed
结果:
Code review complete. Found 2 issues...
```

## 6. 完整执行流程示例

```
用户: "帮我同时分析这3个代码仓库的安全漏洞并生成报告"

Main Agent ReAct Loop:

Round 1: think()
  LLM: "需要分析3个仓库，应该并行执行"
  决策: 调用 spawn_agent_task x 3

Round 1: act()
  -> spawn_agent_task(agent="security_analyzer", task="分析仓库A") -> task_001
  -> spawn_agent_task(agent="security_analyzer", task="分析仓库B") -> task_002
  -> spawn_agent_task(agent="security_analyzer", task="分析仓库C") -> task_003

Round 2: think()
  LLM: "3个任务已提交，我先准备报告模板"
  决策: 调用 create_file

Round 2: act()
  -> create_file("security_report_template.md", ...)

  [后台: task_001 完成]

Round 3: _collect_async_task_notifications() 注入:
  "[异步任务完成通知] Task task_001 完成: 发现3个高危漏洞..."

Round 3: think()
  LLM: "仓库A分析完毕，先写入报告，然后等待剩余任务"
  决策: edit_file + wait_tasks

Round 3: act()
  -> edit_file("security_report.md", "## 仓库A\n...")
  -> wait_tasks(task_ids=["task_002", "task_003"], timeout=120)
     [阻塞等待...]
     返回: task_002=completed, task_003=completed

Round 4: think()
  LLM: "全部完成，整合最终报告"
```

## 7. DAG 依赖编排

通过 `depend_on` 参数构建任务依赖图：

```
任务提交:
  spawn_agent_task(agent="collector", task="收集数据")       -> task_001
  spawn_agent_task(agent="scanner",  task="扫描环境")       -> task_002
  spawn_agent_task(agent="analyzer", task="分析",
                   depend_on=["task_001", "task_002"])      -> task_003
  spawn_agent_task(agent="reporter", task="生成报告",
                   depend_on=["task_003"])                  -> task_004

执行图:
  task_001 (数据收集) ──┐
                         ├──► task_003 (分析) ──► task_004 (报告)
  task_002 (环境扫描) ──┘
```

**规则:**
- `depend_on` 中的所有任务必须成功完成，当前任务才会开始
- 如果任何依赖失败/超时/取消，当前任务也会失败
- 循环依赖不会被检测，会导致死锁（由超时机制兜底）

## 8. 安全与资源控制

### 并发控制

```python
AsyncTaskManager(max_concurrent=5)  # 最多同时运行 5 个任务
```

超出并发数的任务会排队等待（通过 `asyncio.Semaphore`）。

### 超时控制

- 每个任务有独立超时（`spec.timeout`，默认 300 秒）
- `wait_tasks` 有等待超时（`timeout` 参数）
- 超时的任务状态变为 `TIMEOUT`

### 资源隔离

每个子 Agent 任务通过 `SubagentManager` 执行，继承其上下文隔离机制：
- `SubagentSession` 独立会话
- 可配合 `ContextIsolationMode` 使用

## 9. API Reference

### 文件路径

| 文件 | 说明 |
|------|------|
| `core_v2/async_task_manager.py` | AsyncTaskManager + 数据模型 |
| `tools/builtin/async_task/async_task_tools.py` | 4 个 Tool 实现 |
| `tools/builtin/async_task/__init__.py` | 模块注册入口 |
| `core_v2/builtin_agents/base_builtin_agent.py` | Core V2 自动注入逻辑 |
| `core_v2/builtin_agents/react_reasoning_agent.py` | Core V2 通知注入逻辑 |
| `expand/react_master_agent/react_master_agent.py` | Core V1 集成（工具注入 + 通知注入） |

### Import 路径

```python
# 核心管理器
from derisk.agent.core_v2.async_task_manager import (
    AsyncTaskManager,
    AsyncTaskSpec,
    AsyncTaskState,
    AsyncTaskStatus,
)

# 从 core_v2 顶层导入
from derisk.agent.core_v2 import (
    AsyncTaskManager,
    AsyncTaskSpec,
    AsyncTaskState,
    AsyncTaskStatus,
)

# Tool 注册
from derisk.agent.tools.builtin.async_task import register_async_task_tools

# 单独导入 Tool
from derisk.agent.tools.builtin.async_task.async_task_tools import (
    SpawnAgentTaskTool,
    CheckTasksTool,
    WaitTasksTool,
    CancelTaskTool,
)
```

## 10. Core V1 集成（ReActMasterAgent）

异步任务能力同时集成到 Core V1 架构的 `ReActMasterAgent` 中。

### 集成方式

Core V1 使用 `FunctionTool` + `AgentAction` 模式，与 Core V2 的 `ToolBase` 不同。集成通过以下方式实现：

1. **CoreV1SubagentAdapter**：将 Core V1 的 `send()/receive()` 通信模式适配为 `SubagentManager.delegate()` 接口
2. **4 个 FunctionTool 包装函数**：`_spawn_agent_task`、`_check_tasks`、`_wait_tasks`、`_cancel_task`
3. **通知注入**：在 `thinking()` 方法中，通过 `tool_messages` 注入已完成任务的通知

### 与 Core V2 的差异

| 特性 | Core V2 | Core V1 |
|------|---------|---------|
| 工具类型 | `ToolBase` 子类 | `FunctionTool` 包装 |
| 工具注册 | `ToolRegistry` | `available_system_tools` dict |
| 通知注入位置 | `think()` → messages list | `thinking()` → tool_messages |
| `depend_on` 参数 | JSON 数组 | 逗号分隔字符串 |
| `task_ids` 参数 | JSON 数组 | 逗号分隔字符串 |
| 自动注入条件 | AppResource + SubagentManager | available_agents 非空 |

### Core V1 注意事项

- Core V1 的 `FunctionTool` 不支持数组参数，因此 `depend_on` 和 `task_ids` 使用逗号分隔的字符串格式（如 `"task_001,task_002"`）
- 工具在 `preload_resource()` 阶段注入，条件是检测到多 Agent 场景（`available_agents` 非空）
- 通知注入在每轮 `thinking()` 调用时自动执行

## 11. 与 Claude Code Agent Tool 对比

| 能力 | Claude Code | OpenDerisk AsyncTask |
|------|-------------|---------------------|
| 启动子 Agent | `Agent` tool | `spawn_agent_task` tool |
| 同步等待 | 默认前台执行 | `wait_tasks` 显式等待 |
| 后台运行 | `run_in_background: true` | 默认异步 |
| 结果通知 | 自动通知 | `_collect_async_task_notifications` 自动注入 |
| 多任务并行 | 多个 Agent tool 并行调用 | 多次 `spawn_agent_task` |
| 任务依赖 | 无 | `depend_on` DAG 编排 |
| 隔离 | `isolation: "worktree"` | `SubagentContextConfig` |
| 取消 | `TaskStop` | `cancel_task` |
| 状态查询 | `TaskOutput` | `check_tasks` |

### 优势

1. **DAG 依赖编排** — Claude Code 不支持任务间依赖
2. **自动结果注入** — 无需手动轮询，完成结果自然流入推理上下文
3. **统一并发控制** — Semaphore 确保资源不被过度占用
4. **与现有架构无缝集成** — 复用 SubagentManager，不重复造轮子
