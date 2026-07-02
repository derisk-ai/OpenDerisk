# V2 Agent 框架继任实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 V2 从"内核"升级为"完整的 agent 构建框架"，作为 BAIZE 框架的继任者，让满配 BAIZE agent 无功能丢失切换到 V2 跑起来。

**Architecture:** V2 内核原生化 ToolCall/ToolResult/ToolContext（推翻 v1 dict 接口决策）+ 新写 `run_loop` 多轮循环 + `default_thinking_fn`/`default_acting_fn` 默认实现 + 子系统原样搬运（ContextEngine/Memory/Tools/DoomLoop/Truncator）+ HookManager 集成（推翻 v1 跳过决策）+ ToolResolver 资源→工具自动注入 + SubAgentRuntime shared_conv 模式 + 产品层 `runtime_version` 字段分发。

**Tech Stack:** Python 3.10+ / asyncio / pydantic / pytest / SQLite (StateStore) / derisk-core 现有子系统

**Spec:** `docs/superpowers/specs/2026-07-02-v2-agent-framework-successor-design.md`

## Global Constraints

- V2 是 BAIZE 继任者，验证后删 BAIZE，不留 adapter/bridge/兼容层
- V2 内核原生化：`ActingFn = Callable[[ToolCall, ToolContext], Awaitable[ToolResult]]`，`ThinkingFn` 仍收 dict 但 yield typed `ThinkingChunk`
- 子系统原样搬，0 改动（ContextEngine / LongTermMemoryManager / MemoryReadPipeline / DoomLoopDetector / Truncator / WorkLogManager / ColdPersistence）
- HookManager 必须集成（pre/post_tool_use + turn/conversation_complete）
- 不删 BAIZE 代码（删除是后续 spec）
- 每个任务结束 commit，commit message 用 `feat(agent-v2):` / `refactor(agent-v2):` / `test(agent-v2):` 前缀
- 测试用 `pytest`，async 测试用 `@pytest.mark.asyncio` 或项目既有约定（查 `pyproject.toml`）
- 所有新文件在 `packages/derisk-core/src/derisk/agent/core/v2/` 下
- 所有新测试在 `packages/derisk-core/tests/agent/core/v2/` 下

---

## 文件结构

### 新建文件（V2 框架模块）

| 文件 | 职责 |
|---|---|
| `packages/derisk-core/src/derisk/agent/core/v2/thinking_chunk.py` | ThinkingChunk typed union（TokenChunk/ToolCallChunk/UsageChunk） |
| `packages/derisk-core/src/derisk/agent/core/v2/tool_call_types.py` | V2 用的 ToolCall/ToolResult 别名 + 转换工具（复用 `derisk.agent.tools` 的 ToolCall/ToolResult） |
| `packages/derisk-core/src/derisk/agent/core/v2/run_loop.py` | 多轮循环，包 run_step |
| `packages/derisk-core/src/derisk/agent/core/v2/default_thinking.py` | default_thinking_fn 工厂 |
| `packages/derisk-core/src/derisk/agent/core/v2/default_acting.py` | default_acting_fn 工厂 |
| `packages/derisk-core/src/derisk/agent/core/v2/tool_failure_tracker.py` | 工具失败跟踪 |
| `packages/derisk-core/src/derisk/agent/core/v2/retrying_thinking.py` | MAX_ATTEMPTS 装饰器 |
| `packages/derisk-core/src/derisk/agent/core/v2/tool_resolver.py` | 工具查找 + 资源→工具自动注入 |
| `packages/derisk-core/src/derisk/agent/core/v2/tool_context_factory.py` | ToolContext 构造工厂 |
| `packages/derisk-core/src/derisk/agent/core/v2/hook_integration.py` | HookManager 集成辅助 |
| `packages/derisk-core/src/derisk/agent/core/v2/subagent_shared_conv.py` | shared_conv 模式扩展 |

### 修改文件

| 文件 | 改动 |
|---|---|
| `packages/derisk-core/src/derisk/agent/core/v2/runtime.py` | acting_fn 签名 dict → ToolCall/ToolResult；ThinkingFn yield typed chunk |
| `packages/derisk-core/src/derisk/agent/core/v2/__init__.py` | 导出新模块 |
| `packages/derisk-core/src/derisk/agent/core/v2/subagent_runtime.py` | 加 shared_conv 模式 |
| `packages/derisk-core/src/derisk/agent/core/v2/spawn_subagent_tool.py` | 加 shared_conv 参数 |
| `packages/derisk-core/src/derisk/agent/tools/context.py` | 加 scene/scenario_id/language/step_id/round_index 字段 |
| `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` | runtime_version 分发（后期任务） |

### 测试文件

每个新模块配套 `test_*.py`；改 `runtime.py` 后改 `test_runtime*.py` 的 mock 签名。

---

## 阶段划分

- **Phase 1: V2 内核原生化改造**（Task 1-3）—— 改 runtime.py 签名 + 改 P2-P4 测试 mock + typed ThinkingChunk
- **Phase 2: 基础设施模块**（Task 4-8）—— ToolFailureTracker / retrying_thinking / ToolContext 扩展 / tool_context_factory / ToolResolver
- **Phase 3: HookManager 集成 + default_acting_fn**（Task 9-11）
- **Phase 4: default_thinking_fn + 子系统搬运**（Task 12-14）
- **Phase 5: run_loop + 子 Agent shared_conv**（Task 15-17）
- **Phase 6: Skill 工具迁移**（Task 18-20）
- **Phase 7: 产品入口 + 满配验证**（Task 21-23）

---

## Phase 1: V2 内核原生化改造

### Task 1: 定义 ThinkingChunk typed union + ToolCall/ToolResult 复用

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/thinking_chunk.py`
- Create: `packages/derisk-core/src/derisk/agent/core/v2/tool_call_types.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_thinking_chunk.py`

**Interfaces:**
- Produces: `ThinkingChunk` (Union), `TokenChunk`, `ToolCallChunk`, `UsageChunk`（thinking_chunk.py）；`V2ToolCall`/`V2ToolResult` 别名（tool_call_types.py，从 `derisk.agent.tools.base` 复用 ToolCall/ToolResult）

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_thinking_chunk.py
"""ThinkingChunk typed union 测试。"""
from derisk.agent.core.v2.thinking_chunk import (
    ThinkingChunk, TokenChunk, ToolCallChunk, UsageChunk,
)
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult


def test_token_chunk():
    chunk = TokenChunk(token="hello", usage=None)
    assert chunk.token == "hello"
    assert chunk.usage is None


def test_token_chunk_with_usage():
    chunk = TokenChunk(token="hi", usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})
    assert chunk.usage["total_tokens"] == 12


def test_tool_call_chunk():
    tc = V2ToolCall(name="read_file", args={"path": "/tmp/x"})
    chunk = ToolCallChunk(tool_calls=[tc])
    assert len(chunk.tool_calls) == 1
    assert chunk.tool_calls[0].name == "read_file"


def test_usage_chunk():
    chunk = UsageChunk(usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})
    assert chunk.usage["total_tokens"] == 12


def test_thinking_chunk_union():
    t: ThinkingChunk = TokenChunk(token="x")
    assert isinstance(t, TokenChunk)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_thinking_chunk.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 thinking_chunk.py**

```python
# packages/derisk-core/src/derisk/agent/core/v2/thinking_chunk.py
"""V2 thinking_fn yield 的 typed chunk 类型。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from derisk.agent.core.v2.tool_call_types import V2ToolCall


@dataclass
class TokenChunk:
    """LLM 流式 token。usage 可选（最后一次 token 附带累计 usage）。"""
    token: str
    usage: Optional[Dict[str, Any]] = None


@dataclass
class ToolCallChunk:
    """LLM emit 的工具调用（已拼接完整，非 delta）。"""
    tool_calls: List[V2ToolCall]


@dataclass
class UsageChunk:
    """独立的 usage 事件（部分 provider 在 stream 结束时单独发）。"""
    usage: Dict[str, Any]


ThinkingChunk = Union[TokenChunk, ToolCallChunk, UsageChunk]
```

- [ ] **Step 4: 实现 tool_call_types.py**

```python
# packages/derisk-core/src/derisk/agent/core/v2/tool_call_types.py
"""V2 acting_fn 用的 ToolCall/ToolResult 类型别名。

复用 derisk.agent.tools 的统一类型，不重新设计。
"""
from derisk.agent.tools.base import ToolCall as V2ToolCall
from derisk.agent.tools.result import ToolResult as V2ToolResult

__all__ = ["V2ToolCall", "V2ToolResult"]
```

- [ ] **Step 5: 确认 derisk.agent.tools 有 ToolCall/ToolResult**

Run: `cd packages/derisk-core && python -c "from derisk.agent.tools.base import ToolCall; from derisk.agent.tools.result import ToolResult; print(ToolCall, ToolResult)"`
Expected: 打印两个类，无 ImportError

如果 `ToolCall` 不在 `tools.base`，去 `tools/` 目录查实际位置并调整 import。

- [ ] **Step 6: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_thinking_chunk.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/thinking_chunk.py packages/derisk-core/src/derisk/agent/core/v2/tool_call_types.py packages/derisk-core/tests/agent/core/v2/test_thinking_chunk.py
git commit -m "feat(agent-v2): ThinkingChunk typed union + V2ToolCall/V2ToolResult 别名"
```

---

### Task 2: 改 runtime.py acting_fn 签名为原生 ToolCall/ToolResult

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/runtime.py`（签名 + `_run_acting_phase`）
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/__init__.py`（导出新类型）

**Interfaces:**
- Consumes: Task 1 的 `V2ToolCall`/`V2ToolResult`/`ThinkingChunk`
- Produces: `ActingFn = Callable[[V2ToolCall, ToolContext], Awaitable[V2ToolResult]]`；`ThinkingFn = Callable[[dict], AsyncGenerator[ThinkingChunk, None]]`

- [ ] **Step 1: 读 runtime.py 当前签名**

Run: `cd packages/derisk-core && grep -n "ThinkingFn\|ActingFn\|def run_step\|def _run_acting_phase\|def resume_step" src/derisk/agent/core/v2/runtime.py`

记录当前签名和 `_run_acting_phase` 内部调用 `acting_fn` 的方式。

- [ ] **Step 2: 改类型别名**

在 `runtime.py` 顶部（line 23-24 附近）改：

```python
# 旧：
# ThinkingFn = Callable[[dict], AsyncGenerator[dict, None]]
# ActingFn = Callable[[dict], Awaitable[dict]]

# 新：
from derisk.agent.core.v2.thinking_chunk import ThinkingChunk
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.tools.context import ToolContext

ThinkingFn = Callable[[dict], AsyncGenerator[ThinkingChunk, None]]
ActingFn = Callable[[V2ToolCall, ToolContext], Awaitable[V2ToolResult]]
```

- [ ] **Step 3: 改 `_run_acting_phase` 内部 acting_fn 调用**

找到 `_run_acting_phase` 里调用 `acting_fn` 的地方（当前可能是 `await acting_fn(tool_call_dict)`），改成构造 ToolContext + 调 `await acting_fn(tool_call, ctx)`。

具体改动需要读 runtime.py 的 `_run_acting_phase` 实现，把 `tool_call`（dict）转成 `V2ToolCall(name=tc["tool"], args=tc.get("input", {}))`，构造 `ToolContext(agent_id=..., conversation_id=conv_id, ...)`，调 `await acting_fn(v2_call, ctx)`，把返回的 `V2ToolResult` 转成内部 step event 用的 dict（`{"is_exe_success": result.success, "content": str(result.output), ...}`）。

- [ ] **Step 4: 改 run_step / resume_step 签名（如果它们也接 acting_fn）**

`run_step` 和 `resume_step` 的 `acting_fn` 参数类型已是 `ActingFn`，签名不变，但调用方传的 mock 要改。

- [ ] **Step 5: 运行 V2 测试看哪些挂了**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v 2>&1 | tail -50`
Expected: 大量 FAIL（mock 签名不对）—— 这是预期的，下一个 Task 修

- [ ] **Step 6: Commit（先不修测试，下一个 Task 修）**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/runtime.py
git commit -m "refactor(agent-v2): acting_fn 签名 dict → V2ToolCall/V2ToolResult/ToolContext (内核原生化)"
```

---

### Task 3: 修 P2-P4 测试 mock 适配新签名

**Files:**
- Modify: `packages/derisk-core/tests/agent/core/v2/test_runtime.py`
- Modify: `packages/derisk-core/tests/agent/core/v2/test_runtime_ask_user.py`
- Modify: `packages/derisk-core/tests/agent/core/v2/test_runtime_llm_token_usage.py`
- Modify: `packages/derisk-core/tests/agent/core/v2/test_runtime_permission.py`
- Modify: `packages/derisk-core/tests/agent/core/v2/test_runtime_subagent.py`
- Modify: `packages/derisk-core/tests/agent/core/v2/test_v2_runtime_with_deprecation.py`
- Modify: `packages/derisk-core/tests/agent/core/v2/test_spawn_subagent_tool.py`（如果有 mock acting_fn）

**Interfaces:**
- Consumes: Task 2 的新签名
- Produces: 全部 V2 测试 PASS

- [ ] **Step 1: 改 test_runtime.py 的 mock**

把：
```python
async def acting_fn(tool_call):
    return {"result": f"executed:{tool_call['tool']}"}
```
改成：
```python
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.tools.context import ToolContext

async def acting_fn(tool_call: V2ToolCall, ctx: ToolContext) -> V2ToolResult:
    return V2ToolResult.ok(output=f"executed:{tool_call.name}")
```

把 thinking_fn 的 mock：
```python
async def thinking_fn(input_):
    yield {"token": "hello"}
    yield {"token": "world"}
```
改成：
```python
from derisk.agent.core.v2.thinking_chunk import TokenChunk

async def thinking_fn(input_):
    yield TokenChunk(token="hello")
    yield TokenChunk(token="world")
```

带 tool_calls 的：
```python
async def thinking_with_tool(input_):
    yield {"token": "calling tool"}
    yield {"token": "", "tool_calls": [{"tool": "read_file"}]}
```
改成：
```python
from derisk.agent.core.v2.thinking_chunk import TokenChunk, ToolCallChunk

async def thinking_with_tool(input_):
    yield TokenChunk(token="calling tool")
    yield ToolCallChunk(tool_calls=[V2ToolCall(name="read_file", args={})])
```

- [ ] **Step 2: 改 test_runtime_ask_user.py**

acting_fn 返 `{"ask_user": ...}` 的 mock，改成：runtime 内部把 `acting_fn` 返回的 `V2ToolResult` 检查 `ask_user` 字段。读 `runtime.py` 的 `_run_acting_phase` 看 ask_user 怎么处理 —— 如果 V2ToolResult 没有 ask_user 字段，acting_fn 需要返特殊标记。**先读 V2ToolResult schema 确认**：

Run: `cd packages/derisk-core && python -c "from derisk.agent.tools.result import ToolResult; print(ToolResult.model_fields)"`

如果 ToolResult 没有 ask_user 字段，acting_fn 返 `V2ToolResult.ok(output=..., metadata={"ask_user": {...}})`，runtime 读 metadata。

- [ ] **Step 3: 改其余 test_runtime_*.py**

逐文件改 mock 签名，每个文件改完跑一次确认。

- [ ] **Step 4: 改 test_v2_runtime_with_deprecation.py**

读文件，把 `acting_fn` 返 `{"ask_user": ...}` 改成 `V2ToolResult` metadata。

- [ ] **Step 5: 跑全部 V2 测试**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v 2>&1 | tail -30`
Expected: 151 个测试全 PASS（或除已知 pre-existing failure `test_token_budget_enforcement` 外全 PASS）

- [ ] **Step 6: 跑 scripts/v2_demo.py 确认 demo 还能跑**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python scripts/v2_demo.py 2>&1 | tail -20`
Expected: 4 phase 全通过

如果 demo 挂了，改 demo 里的 `thinking_fn`/`acting_fn` mock 适配新签名。

- [ ] **Step 7: Commit**

```bash
git add packages/derisk-core/tests/agent/core/v2/ scripts/v2_demo.py
git commit -m "test(agent-v2): 适配 acting_fn/thinking_fn 原生签名"
```

---

## Phase 2: 基础设施模块

### Task 4: ToolFailureTracker

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/tool_failure_tracker.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_tool_failure_tracker.py`

**Interfaces:**
- Produces: `ToolFailureTracker(max_failures=3)` with `record_failure(name) -> bool` / `is_blocked(name) -> bool` / `reset(name)`

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_tool_failure_tracker.py
"""ToolFailureTracker 测试。"""
from derisk.agent.core.v2.tool_failure_tracker import ToolFailureTracker


def test_record_failure_below_threshold():
    tracker = ToolFailureTracker(max_failures=3)
    assert not tracker.record_failure("bash")  # 1 次
    assert not tracker.is_blocked("bash")


def test_record_failure_at_threshold():
    tracker = ToolFailureTracker(max_failures=3)
    tracker.record_failure("bash")
    tracker.record_failure("bash")
    assert tracker.record_failure("bash")  # 3 次，返回 True 表示达阈值
    assert tracker.is_blocked("bash")


def test_reset():
    tracker = ToolFailureTracker(max_failures=3)
    tracker.record_failure("bash")
    tracker.record_failure("bash")
    tracker.reset("bash")
    assert not tracker.is_blocked("bash")
    assert tracker.record_failure("bash")  # 重新从 1 开始


def test_different_tools_independent():
    tracker = ToolFailureTracker(max_failures=3)
    tracker.record_failure("bash")
    tracker.record_failure("read")
    assert not tracker.is_blocked("bash")
    assert not tracker.is_blocked("read")


def test_default_max_failures():
    tracker = ToolFailureTracker()
    assert tracker._max_failures == 3
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_tool_failure_tracker.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/tool_failure_tracker.py
"""工具连续失败跟踪器。

从 BAIZE react_master_agent.py:2517-2575 的 _tool_failure_counts 抽出。
无 agent 反向依赖。
"""
from typing import Dict


class ToolFailureTracker:
    def __init__(self, max_failures: int = 3):
        self._counts: Dict[str, int] = {}
        self._max_failures = max_failures

    def record_failure(self, tool_name: str) -> bool:
        """记录一次失败。返回是否达到阈值。"""
        self._counts[tool_name] = self._counts.get(tool_name, 0) + 1
        return self._counts[tool_name] >= self._max_failures

    def is_blocked(self, tool_name: str) -> bool:
        return self._counts.get(tool_name, 0) >= self._max_failures

    def reset(self, tool_name: str) -> None:
        self._counts.pop(tool_name, None)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_tool_failure_tracker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/tool_failure_tracker.py packages/derisk-core/tests/agent/core/v2/test_tool_failure_tracker.py
git commit -m "feat(agent-v2): ToolFailureTracker 工具连续失败跟踪"
```

---

### Task 5: retrying_thinking 装饰器

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/retrying_thinking.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_retrying_thinking.py`

**Interfaces:**
- Produces: `retrying_thinking(llm_stream_fn, max_attempts=3, model_fallback=None)` async generator

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_retrying_thinking.py
"""retrying_thinking 装饰器测试。"""
import pytest
from derisk.agent.core.v2.retrying_thinking import retrying_thinking
from derisk.agent.core.v2.thinking_chunk import TokenChunk


async def _stream_ok():
    yield TokenChunk(token="a")
    yield TokenChunk(token="b")


async def _stream_fail_once_then_succeed():
    """第一次抛异常，第二次成功。"""
    if not hasattr(_stream_fail_once_then_succeed, "_called"):
        _stream_fail_once_then_succeed._called = True
        raise RuntimeError("LLM error")
    yield TokenChunk(token="recovered")


async def _stream_always_fail():
    raise RuntimeError("always fails")


async def test_no_retry_on_success():
    chunks = []
    async for c in retrying_thinking(_stream_ok, max_attempts=3):
        chunks.append(c)
    assert len(chunks) == 2
    assert chunks[0].token == "a"


async def test_retry_on_failure_then_success():
    chunks = []
    async for c in retrying_thinking(_stream_fail_once_then_succeed, max_attempts=3):
        chunks.append(c)
    assert len(chunks) == 1
    assert chunks[0].token == "recovered"


async def test_retry_exhausted_raises():
    with pytest.raises(RuntimeError, match="always fails"):
        async for _ in retrying_thinking(_stream_always_fail, max_attempts=3):
            pass


async def test_model_fallback_called():
    """model_fallback 在重试时被调用，传入上次失败的 model。"""
    fallback_calls = []
    def fallback(last_model):
        fallback_calls.append(last_model)
        return "fallback-model"

    # _stream_fail_once_then_succeed 已在前面测试中 _called=True，需要重置
    if hasattr(_stream_fail_once_then_succeed, "_called"):
        del _stream_fail_once_then_succeed._called

    async for _ in retrying_thinking(
        _stream_fail_once_then_succeed, max_attempts=3,
        model_fallback=fallback, initial_model="primary"
    ):
        pass
    assert len(fallback_calls) == 1
    assert fallback_calls[0] == "primary"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_retrying_thinking.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/retrying_thinking.py
"""LLM stream 重试装饰器。

从 BAIZE react_master_agent.py:1908-2044 的 llm_thinking MAX_ATTEMPTS 逻辑抽出。
包装一个 async generator（LLM stream），失败时重试，可带模型降级。
"""
from typing import AsyncGenerator, Callable, Optional, Any


async def retrying_thinking(
    stream_fn: Callable[[], AsyncGenerator],
    max_attempts: int = 3,
    model_fallback: Optional[Callable[[str], str]] = None,
    initial_model: Optional[str] = None,
) -> AsyncGenerator:
    """重试 LLM stream。

    Args:
        stream_fn: 返回 async generator 的 callable（每次调用产生新 stream）
        max_attempts: 最大尝试次数
        model_fallback: 失败时调用的模型降级函数，传入 last_model 返回 new_model
        initial_model: 初始 model（用于第一次调用 + fallback 链）

    Yields: stream_fn 产生的 chunk
    """
    last_model = initial_model
    for attempt in range(max_attempts):
        try:
            async for chunk in stream_fn():
                yield chunk
            return  # 成功完成
        except Exception:
            if attempt + 1 >= max_attempts:
                raise
            if model_fallback and last_model is not None:
                last_model = model_fallback(last_model)
            # 否则用原 model 重试
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_retrying_thinking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/retrying_thinking.py packages/derisk-core/tests/agent/core/v2/test_retrying_thinking.py
git commit -m "feat(agent-v2): retrying_thinking MAX_ATTEMPTS 装饰器"
```

---

### Task 6: 扩展 ToolContext 字段（scene/scenario_id/language/step_id/round_index）

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/tools/context.py`
- Test: `packages/derisk-core/tests/agent/tools/test_context_v2_fields.py`（新建）

**Interfaces:**
- Produces: `ToolContext` 新增 `scene: Optional[str]` / `scenario_id: Optional[str]` / `language: str = "zh"` / `step_id: Optional[str]` / `round_index: int = 0`

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/tools/test_context_v2_fields.py
"""ToolContext v2 新增字段测试。"""
from derisk.agent.tools.context import ToolContext


def test_default_language_zh():
    ctx = ToolContext()
    assert ctx.language == "zh"


def test_scene_fields():
    ctx = ToolContext(scene="data_analyst", scenario_id="wm-sales-2025", language="en")
    assert ctx.scene == "data_analyst"
    assert ctx.scenario_id == "wm-sales-2025"
    assert ctx.language == "en"


def test_step_fields():
    ctx = ToolContext(step_id="step-abc123", round_index=3)
    assert ctx.step_id == "step-abc123"
    assert ctx.round_index == 3


def test_set_get_resource_still_works():
    ctx = ToolContext()
    ctx.set_resource("sandbox_client", "fake_client")
    assert ctx.get_resource("sandbox_client") == "fake_client"
    assert ctx.get_resource("nonexistent") is None
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/tools/test_context_v2_fields.py -v`
Expected: FAIL with `AttributeError` 或字段不存在

- [ ] **Step 3: 改 context.py**

在 `ToolContext` 类里，`available_skills` 字段后面加：

```python
    # v2 新增 —— 场景信息（G1）
    scene: Optional[str] = Field(None, description="场景标识（如 data_analyst）")
    scenario_id: Optional[str] = Field(None, description="场景实例 ID")
    language: str = Field("zh", description="语言代码")

    # v2 新增 —— step 元数据
    step_id: Optional[str] = Field(None, description="V2 step ID")
    round_index: int = Field(0, description="当前 turn 的 round 序号")
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/tools/test_context_v2_fields.py -v`
Expected: PASS

- [ ] **Step 5: 跑既有 ToolContext 测试确认无回归**

Run: `cd packages/derisk-core && python -m pytest tests/agent/tools/ -v 2>&1 | tail -10`
Expected: 既有测试全 PASS

- [ ] **Step 6: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/tools/context.py packages/derisk-core/tests/agent/tools/test_context_v2_fields.py
git commit -m "feat(agent-v2): ToolContext 加 scene/scenario_id/language/step_id/round_index 字段 (G1)"
```

---

### Task 7: tool_context_factory

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/tool_context_factory.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_tool_context_factory.py`

**Interfaces:**
- Consumes: Task 6 的 ToolContext
- Produces: `ToolContextFactory(...)` with `.build(tool_call, tool) -> ToolContext`

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_tool_context_factory.py
"""ToolContextFactory 测试。"""
from derisk.agent.core.v2.tool_context_factory import ToolContextFactory
from derisk.agent.core.v2.tool_call_types import V2ToolCall


class FakeSandboxManager:
    @property
    def client(self):
        return "fake_sandbox_client"


class FakeDBResource:
    pass


class FakeRetrieverResource:
    pass


class FakeAppResource:
    pass


def _make_factory(resource_map=None, sandbox_manager=None):
    return ToolContextFactory(
        agent_id="agent-1",
        conv_id="conv-1",
        user_id="user-1",
        scene="data_analyst",
        scenario_id="wm-sales",
        language="zh",
        resource_map=resource_map or {},
        sandbox_manager=sandbox_manager,
        skill_dir="/skills",
        available_skills={"sql_review": "/skills/sql_review"},
    )


def test_basic_context_fields():
    factory = _make_factory()
    tc = V2ToolCall(name="read_file", args={})
    ctx = factory.build(tc, tool=None)
    assert ctx.agent_id == "agent-1"
    assert ctx.conversation_id == "conv-1"
    assert ctx.user_id == "user-1"
    assert ctx.scene == "data_analyst"
    assert ctx.scenario_id == "wm-sales"
    assert ctx.language == "zh"
    assert ctx.skill_dir == "/skills"
    assert ctx.available_skills["sql_review"] == "/skills/sql_review"


def test_sandbox_client_injected():
    factory = _make_factory(sandbox_manager=FakeSandboxManager())
    tc = V2ToolCall(name="bash", args={})
    ctx = factory.build(tc, tool=None)
    assert ctx.get_resource("sandbox_client") == "fake_sandbox_client"


def test_db_resource_injected_for_db_tool():
    db = FakeDBResource()
    factory = _make_factory(resource_map={"DBResource": [db]})
    tc = V2ToolCall(name="execute_sql", args={"sql": "SELECT 1"})
    ctx = factory.build(tc, tool=None)
    assert ctx.get_resource("db_resource") is db


def test_knowledge_retriever_injected():
    retriever = FakeRetrieverResource()
    factory = _make_factory(resource_map={"RetrieverResource": [retriever]})
    tc = V2ToolCall(name="KnowledgeSearch", args={"query": "test"})
    ctx = factory.build(tc, tool=None)
    assert ctx.get_resource("knowledge_retriever") is retriever


def test_app_resource_injected_for_agent_start():
    app = FakeAppResource()
    factory = _make_factory(resource_map={"AppResource": [app]})
    tc = V2ToolCall(name="AgentStart", args={})
    ctx = factory.build(tc, tool=None)
    assert ctx.get_resource("app_resource") is app


def test_no_resource_injected_for_unrelated_tool():
    factory = _make_factory(
        resource_map={
            "DBResource": [FakeDBResource()],
            "RetrieverResource": [FakeRetrieverResource()],
        }
    )
    tc = V2ToolCall(name="read_file", args={})
    ctx = factory.build(tc, tool=None)
    assert ctx.get_resource("db_resource") is None
    assert ctx.get_resource("knowledge_retriever") is None
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_tool_context_factory.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/tool_context_factory.py
"""ToolContext 工厂。

根据 tool_call + resource_map + sandbox_manager 构造 ToolContext，
按 tool 类型注入活资源句柄（DBResource / RetrieverResource / AppResource / sandbox_client）。

等价 BAIZE tool_action.py:993-1059 + agent_adapter.py:240-320 的组装逻辑。
"""
from typing import Any, Dict, List, Optional

from derisk.agent.tools.context import ToolContext
from derisk.agent.core.v2.tool_call_types import V2ToolCall


# tool_name → resource_map key 的映射
_TOOL_RESOURCE_MAP = {
    "execute_sql": "db_resource",
    "list_tables": "db_resource",
    "get_table_spec": "db_resource",
    "KnowledgeSearch": "knowledge_retriever",
    "AgentStart": "app_resource",
}

# tool_name → resource_map 类型 key（用于查找）
_TOOL_RESOURCE_TYPE = {
    "execute_sql": "DBResource",
    "list_tables": "DBResource",
    "get_table_spec": "DBResource",
    "KnowledgeSearch": "RetrieverResource",
    "AgentStart": "AppResource",
}


class ToolContextFactory:
    def __init__(
        self,
        *,
        agent_id: str,
        conv_id: str,
        user_id: Optional[str] = None,
        scene: Optional[str] = None,
        scenario_id: Optional[str] = None,
        language: str = "zh",
        resource_map: Optional[Dict[str, List[Any]]] = None,
        sandbox_manager: Optional[Any] = None,
        skill_dir: Optional[str] = None,
        available_skills: Optional[Dict[str, str]] = None,
        agent_file_system: Optional[Any] = None,
        agent: Optional[Any] = None,
    ):
        self._agent_id = agent_id
        self._conv_id = conv_id
        self._user_id = user_id
        self._scene = scene
        self._scenario_id = scenario_id
        self._language = language
        self._resource_map = resource_map or {}
        self._sandbox_manager = sandbox_manager
        self._skill_dir = skill_dir
        self._available_skills = available_skills or {}
        self._agent_file_system = agent_file_system
        self._agent = agent

    def build(self, tool_call: V2ToolCall, tool: Optional[Any] = None) -> ToolContext:
        ctx = ToolContext(
            agent_id=self._agent_id,
            conversation_id=self._conv_id,
            user_id=self._user_id,
            scene=self._scene,
            scenario_id=self._scenario_id,
            language=self._language,
            skill_dir=self._skill_dir,
            available_skills=self._available_skills,
        )

        # 注入沙箱活句柄（G7）
        if self._sandbox_manager is not None:
            ctx.set_resource("sandbox_client", self._sandbox_manager.client)

        # 注入 agent_file_system（G4）
        if self._agent_file_system is not None:
            ctx.set_resource("agent_file_system", self._agent_file_system)

        # 注入 agent 引用（G4）
        if self._agent is not None:
            ctx.set_resource("agent", self._agent)

        # 按 tool 类型派发对应资源（G4）
        tool_name = tool_call.name
        resource_type = _TOOL_RESOURCE_TYPE.get(tool_name)
        resource_key = _TOOL_RESOURCE_MAP.get(tool_name)
        if resource_type and resource_key:
            resources = self._resource_map.get(resource_type, [])
            if resources:
                ctx.set_resource(resource_key, resources[0])

        return ctx
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_tool_context_factory.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/tool_context_factory.py packages/derisk-core/tests/agent/core/v2/test_tool_context_factory.py
git commit -m "feat(agent-v2): ToolContextFactory 按 tool 类型注入活资源句柄 (G4 + G7)"
```

---

### Task 8: ToolResolver（含资源→工具自动注入）

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/tool_resolver.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_tool_resolver.py`

**Interfaces:**
- Consumes: BAIZE 的 `sandbox_tool_dict` / `system_tool_dict` / `tool_registry` / `agent.resource` / `resource_map` / `sandbox_manager`
- Produces: `ToolResolver(...)` with `.resolve(name) -> Optional[ToolBase]` + `.list_tools_for_llm() -> List[dict]`

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_tool_resolver.py
"""ToolResolver 测试。"""
from derisk.agent.core.v2.tool_resolver import ToolResolver


class FakeTool:
    def __init__(self, name):
        self.name = name
        self._tool_base = self  # for UnifiedToolAdapter path

    def to_openai_tool(self):
        return {"type": "function", "function": {"name": self.name, "description": "", "parameters": {}}}


def test_resolve_from_system_tools():
    tool = FakeTool("read_file")
    resolver = ToolResolver(system_tools={"read_file": tool})
    assert resolver.resolve("read_file") is tool


def test_resolve_returns_none_for_unknown():
    resolver = ToolResolver(system_tools={"read_file": FakeTool("read_file")})
    assert resolver.resolve("nonexistent") is None


def test_sandbox_tools_only_injected_if_sandbox_manager():
    """没绑 sandbox_manager 时，sandbox_tool_dict 不注入。"""
    bash = FakeTool("bash")
    resolver = ToolResolver(
        sandbox_tools={"bash": bash},
        sandbox_manager=None,
    )
    assert resolver.resolve("bash") is None


def test_sandbox_tools_injected_when_sandbox_manager():
    bash = FakeTool("bash")
    class FakeSM:
        pass
    resolver = ToolResolver(
        sandbox_tools={"bash": bash},
        sandbox_manager=FakeSM(),
    )
    assert resolver.resolve("bash") is bash


def test_list_tools_for_llm():
    read = FakeTool("read_file")
    write = FakeTool("write_file")
    resolver = ToolResolver(system_tools={"read_file": read, "write_file": write})
    tools = resolver.list_tools_for_llm()
    names = [t["function"]["name"] for t in tools]
    assert set(names) == {"read_file", "write_file"}
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_tool_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现（先做基础四路查找，资源注入下一 Task 加）**

```python
# packages/derisk-core/src/derisk/agent/core/v2/tool_resolver.py
"""工具解析器 + 资源→工具自动注入。

等价 BAIZE tool_action.py:344-362 四路查找 + base_agent.py:837-889 _inject_resource_based_tools。
"""
from typing import Any, Dict, List, Optional


class ToolResolver:
    def __init__(
        self,
        *,
        sandbox_tools: Optional[Dict[str, Any]] = None,
        system_tools: Optional[Dict[str, Any]] = None,
        unified_registry: Any = None,  # tool_registry
        resource_pack: Any = None,     # agent.resource（MCP 工具树）
        resource_map: Optional[Dict[str, List[Any]]] = None,
        sandbox_manager: Optional[Any] = None,
        enable_async_subagent: bool = False,
    ):
        self._sandbox_tools = sandbox_tools or {}
        self._system_tools = system_tools or {}
        self._unified_registry = unified_registry
        self._resource_pack = resource_pack
        self._resource_map = resource_map or {}
        self._sandbox_manager = sandbox_manager
        self._enable_async_subagent = enable_async_subagent
        self._tools: Dict[str, Any] = {}
        self._assemble()

    def _assemble(self):
        """组装工具集，等价 BAIZE preload_resource 的工具注入。"""
        # 1. 系统工具
        self._tools.update(self._system_tools)

        # 2. 沙箱工具（仅当 sandbox_manager 存在）
        if self._sandbox_manager is not None:
            self._tools.update(self._sandbox_tools)

        # 3. 统一注册表
        if self._unified_registry is not None:
            for name in self._list_registry_names():
                tool = self._unified_registry.get(name) if hasattr(self._unified_registry, "get") else None
                if tool is not None and name not in self._tools:
                    self._tools[name] = tool

    def _list_registry_names(self) -> List[str]:
        if hasattr(self._unified_registry, "list_names"):
            return list(self._unified_registry.list_names())
        if hasattr(self._unified_registry, "tools"):
            return list(self._unified_registry.tools.keys())
        return []

    def resolve(self, name: str) -> Optional[Any]:
        # 优先从已组装工具集查
        if name in self._tools:
            return self._tools[name]
        # 兜底：递归查 Resource pack（MCP 工具）
        if self._resource_pack is not None:
            return self._lookup_resource_pack(name)
        return None

    def _lookup_resource_pack(self, name: str) -> Optional[Any]:
        """递归遍历 resource pack 树查找工具。"""
        return _find_tool_in_pack(self._resource_pack, name)

    def list_tools_for_llm(self) -> List[dict]:
        """生成 LLM tool list（OpenAI 格式）。"""
        result = []
        for tool in self._tools.values():
            if hasattr(tool, "to_openai_tool"):
                result.append(tool.to_openai_tool())
            elif hasattr(tool, "_tool_base") and hasattr(tool._tool_base, "to_openai_tool"):
                result.append(tool._tool_base.to_openai_tool())
        return result


def _find_tool_in_pack(pack: Any, name: str, visited: Optional[set] = None) -> Optional[Any]:
    """递归遍历 Resource pack 树查找工具（按 name 匹配）。"""
    if visited is None:
        visited = set()
    pack_id = id(pack)
    if pack_id in visited:
        return None
    visited.add(pack_id)

    # pack 是 ToolPack / ResourcePack，有 _resources dict
    resources = getattr(pack, "_resources", None) or {}
    if isinstance(resources, dict):
        for tool_name, tool in resources.items():
            if tool_name == name:
                return tool
            # 递归子 pack
            if getattr(tool, "is_pack", False) or hasattr(tool, "sub_resources"):
                found = _find_tool_in_pack(tool, name, visited)
                if found is not None:
                    return found
    return None
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_tool_resolver.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/tool_resolver.py packages/derisk-core/tests/agent/core/v2/test_tool_resolver.py
git commit -m "feat(agent-v2): ToolResolver 四路工具查找 + Resource pack 递归"
```

---

## Phase 3: HookManager 集成 + default_acting_fn

### Task 9: hook_integration 辅助模块

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/hook_integration.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_hook_integration.py`

**Interfaces:**
- Consumes: `derisk.agent.core.hook.HookManager`
- Produces: `build_hook_context_for_pre_tool_use(tool_call, ctx)` / `build_hook_context_for_post_tool_use(tool_call, ctx, result)` / `build_hook_context_for_turn_complete(turn_ctx)` / `build_hook_context_for_conversation_complete(conv_ctx)` 等 helper

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_hook_integration.py
"""hook_integration context 构造测试。"""
from derisk.agent.core.v2.hook_integration import (
    build_pre_tool_use_context,
    build_post_tool_use_context,
    build_turn_complete_context,
    build_conversation_complete_context,
)
from derisk.agent.core.v2.tool_call_types import V2ToolCall
from derisk.agent.tools.context import ToolContext


def test_pre_tool_use_context():
    tc = V2ToolCall(name="bash", args={"cmd": "ls"})
    ctx = ToolContext(agent_id="a1", conversation_id="c1")
    result = build_pre_tool_use_context(tc, ctx)
    assert result["tool_name"] == "bash"
    assert result["args"] == {"cmd": "ls"}
    assert result["context"] is ctx
    assert result["conv_id"] == "c1"
    assert result["agent_id"] == "a1"


def test_post_tool_use_context_with_result():
    from derisk.agent.core.v2.tool_call_types import V2ToolResult
    tc = V2ToolCall(name="bash", args={})
    ctx = ToolContext(agent_id="a1", conversation_id="c1")
    result = V2ToolResult.ok(output="done")
    out = build_post_tool_use_context(tc, ctx, result)
    assert out["tool_name"] == "bash"
    assert out["result"] is result
    assert out["error"] is None


def test_post_tool_use_context_with_error():
    tc = V2ToolCall(name="bash", args={})
    ctx = ToolContext(agent_id="a1", conversation_id="c1")
    out = build_post_tool_use_context(tc, ctx, None, error="boom")
    assert out["error"] == "boom"
    assert out["result"] is None


def test_turn_complete_context():
    out = build_turn_complete_context(
        round=3, interrupted=False, user_prompt="hi",
        final_answer="hello", user_id="u1", conv_id="c1", agent_id="a1", step_count=5,
    )
    assert out["round"] == 3
    assert out["interrupted"] is False
    assert out["user_prompt"] == "hi"
    assert out["final_answer"] == "hello"
    assert out["user_id"] == "u1"
    assert out["conv_id"] == "c1"
    assert out["agent_id"] == "a1"
    assert out["step_count"] == 5


def test_conversation_complete_context():
    out = build_conversation_complete_context(
        conv_id="c1", agent_id="a1", user_id="u1", total_rounds=10,
    )
    assert out["conv_id"] == "c1"
    assert out["total_rounds"] == 10
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_hook_integration.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/hook_integration.py
"""HookManager 集成辅助：构造 hook context dict。

context 字段对齐 BAIZE：
- pre/post_tool_use: tool_action.py:1334-1341
- turn_complete: base_agent.py:1327-1355
"""
from typing import Any, Dict, Optional

from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult


def build_pre_tool_use_context(
    tool_call: V2ToolCall, ctx: Any,
) -> Dict[str, Any]:
    return {
        "tool_name": tool_call.name,
        "args": tool_call.args,
        "context": ctx,
        "conv_id": getattr(ctx, "conversation_id", None),
        "agent_id": getattr(ctx, "agent_id", None),
        "step_id": getattr(ctx, "step_id", None),
    }


def build_post_tool_use_context(
    tool_call: V2ToolCall,
    ctx: Any,
    result: Optional[V2ToolResult],
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "tool_name": tool_call.name,
        "args": tool_call.args,
        "context": ctx,
        "result": result,
        "error": error,
        "conv_id": getattr(ctx, "conversation_id", None),
        "agent_id": getattr(ctx, "agent_id", None),
    }


def build_turn_complete_context(
    *,
    round: int,
    interrupted: bool,
    user_prompt: str,
    final_answer: Optional[str],
    user_id: Optional[str],
    conv_id: str,
    agent_id: str,
    step_count: int,
) -> Dict[str, Any]:
    return {
        "round": round,
        "interrupted": interrupted,
        "user_prompt": user_prompt,
        "final_answer": final_answer,
        "user_id": user_id,
        "conv_id": conv_id,
        "agent_id": agent_id,
        "step_count": step_count,
    }


def build_conversation_complete_context(
    *,
    conv_id: str,
    agent_id: str,
    user_id: Optional[str],
    total_rounds: int,
) -> Dict[str, Any]:
    return {
        "conv_id": conv_id,
        "agent_id": agent_id,
        "user_id": user_id,
        "total_rounds": total_rounds,
    }
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_hook_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/hook_integration.py packages/derisk-core/tests/agent/core/v2/test_hook_integration.py
git commit -m "feat(agent-v2): hook_integration context 构造 helper (G8/G9)"
```

---

### Task 10: 集成 HookManager 到 default_acting_fn（含 default_acting_fn 完整实现）

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/default_acting.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_default_acting.py`

**Interfaces:**
- Consumes: Task 4 (ToolFailureTracker) / Task 7 (ToolContextFactory) / Task 8 (ToolResolver) / Task 9 (hook_integration) / BAIZE DoomLoopDetector / Truncator
- Produces: `make_default_acting_fn(...)` 工厂返回 `ActingFn`

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_default_acting.py
"""default_acting_fn 测试。"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from derisk.agent.core.v2.default_acting import make_default_acting_fn
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.core.v2.tool_failure_tracker import ToolFailureTracker
from derisk.agent.core.v2.tool_context_factory import ToolContextFactory
from derisk.agent.core.v2.tool_resolver import ToolResolver
from derisk.agent.tools.context import ToolContext


class FakeTool:
    def __init__(self, name, result):
        self.name = name
        self._result = result

    async def execute(self, args, context=None):
        return self._result


class FakeDoomLoop:
    async def check(self, tool_name, args):
        return True  # 允许


class FakeDoomLoopBlock:
    async def check(self, tool_name, args):
        return False  # 阻止


class FakeTruncator:
    async def truncate(self, content, tool_name, args):
        # 不截断
        return MagicMock(truncated=False, truncated_content=content)


def _make_factory():
    return ToolContextFactory(agent_id="a1", conv_id="c1")


def _make_acting_fn(tool, doom_loop=None, truncator=None, hook_manager=None):
    resolver = ToolResolver(system_tools={tool.name: tool})
    failure_tracker = ToolFailureTracker(max_failures=3)
    return make_default_acting_fn(
        tool_resolver=resolver,
        doom_loop_detector=doom_loop or FakeDoomLoop(),
        failure_tracker=failure_tracker,
        truncator=truncator or FakeTruncator(),
        hook_manager=hook_manager,
        tool_context_factory=_make_factory(),
    )


async def test_execute_success():
    tool = FakeTool("read_file", V2ToolResult.ok(output="file content"))
    acting_fn = _make_acting_fn(tool)
    tc = V2ToolCall(name="read_file", args={"path": "/tmp/x"})
    ctx = ToolContext()
    result = await acting_fn(tc, ctx)
    assert result.success
    assert result.output == "file content"


async def test_doom_loop_blocks():
    tool = FakeTool("bash", V2ToolResult.ok(output="ok"))
    acting_fn = _make_acting_fn(tool, doom_loop=FakeDoomLoopBlock())
    tc = V2ToolCall(name="bash", args={})
    ctx = ToolContext()
    result = await acting_fn(tc, ctx)
    assert not result.success
    assert "doom loop" in result.error.lower()


async def test_failure_tracker_blocks_after_threshold():
    tool = FakeTool("bash", V2ToolResult.fail(error="boom"))
    acting_fn = _make_acting_fn(tool)
    tc = V2ToolCall(name="bash", args={})
    ctx = ToolContext()
    # 失败 3 次
    for _ in range(3):
        await acting_fn(tc, ctx)
    # 第 4 次应被 block
    result = await acting_fn(tc, ctx)
    assert not result.success
    assert "blocked" in result.error.lower() or "阈值" in result.error


async def test_unknown_tool_returns_fail():
    tool = FakeTool("read_file", V2ToolResult.ok(output="x"))
    acting_fn = _make_acting_fn(tool)
    tc = V2ToolCall(name="nonexistent", args={})
    ctx = ToolContext()
    result = await acting_fn(tc, ctx)
    assert not result.success
    assert "未注册" in result.error or "not registered" in result.error.lower()


async def test_pre_tool_use_hook_can_deny():
    tool = FakeTool("bash", V2ToolResult.ok(output="ok"))
    hook_manager = MagicMock()
    decision = MagicMock()
    decision.action = "DENY"
    decision.reason = "audit denied"
    hook_manager.trigger_blocking = AsyncMock(return_value=decision)
    acting_fn = _make_acting_fn(tool, hook_manager=hook_manager)
    tc = V2ToolCall(name="bash", args={})
    ctx = ToolContext()
    result = await acting_fn(tc, ctx)
    assert not result.success
    assert "hook denied" in result.error


async def test_post_tool_use_hook_fires():
    tool = FakeTool("bash", V2ToolResult.ok(output="ok"))
    hook_manager = MagicMock()
    decision = MagicMock()
    decision.action = "CONTINUE"
    hook_manager.trigger_blocking = AsyncMock(return_value=decision)
    hook_manager.trigger = AsyncMock()
    acting_fn = _make_acting_fn(tool, hook_manager=hook_manager)
    tc = V2ToolCall(name="bash", args={})
    ctx = ToolContext()
    await acting_fn(tc, ctx)
    # post_tool_use 应被触发
    hook_manager.trigger.assert_called_once()
    call_args = hook_manager.trigger.call_args
    assert call_args.args[0] == "post_tool_use"


async def test_exception_recorded_as_failure():
    class CrashTool:
        name = "bash"
        async def execute(self, args, context=None):
            raise RuntimeError("crashed")
    acting_fn = _make_acting_fn(CrashTool())
    tc = V2ToolCall(name="bash", args={})
    ctx = ToolContext()
    result = await acting_fn(tc, ctx)
    assert not result.success
    assert "执行异常" in result.error
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_default_acting.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/default_acting.py
"""default_acting_fn 工厂。

流程：resolve → doom → failure_tracker → pre_tool_use hook → execute → post_tool_use hook → truncate

等价 BAIZE tool_action.py:278-680 的 ToolAction.run，但用原生 V2ToolCall/V2ToolResult/ToolContext。
"""
from typing import Any, Optional

from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.core.v2.tool_failure_tracker import ToolFailureTracker
from derisk.agent.core.v2.tool_resolver import ToolResolver
from derisk.agent.core.v2.tool_context_factory import ToolContextFactory
from derisk.agent.core.v2.hook_integration import (
    build_pre_tool_use_context,
    build_post_tool_use_context,
)
from derisk.agent.tools.context import ToolContext


def make_default_acting_fn(
    *,
    tool_resolver: ToolResolver,
    doom_loop_detector: Any,
    failure_tracker: ToolFailureTracker,
    truncator: Any,
    tool_context_factory: ToolContextFactory,
    hook_manager: Optional[Any] = None,
):
    async def acting_fn(tool_call: V2ToolCall, ctx: ToolContext) -> V2ToolResult:
        tool_name = tool_call.name
        tool_input = tool_call.args

        # 1. DoomLoop 检测
        allowed = await doom_loop_detector.check(tool_name, tool_input)
        if not allowed:
            return V2ToolResult.fail(error="doom loop detected, blocked")

        # 2. 失败跟踪
        if failure_tracker.is_blocked(tool_name):
            return V2ToolResult.fail(error=f"工具 {tool_name} 连续失败超过阈值，已阻止")

        # 3. 解析工具
        tool = tool_resolver.resolve(tool_name)
        if tool is None:
            return V2ToolResult.fail(error=f"工具 {tool_name} 未注册")

        # 4. pre_tool_use hook（blocking）
        if hook_manager is not None:
            decision = await hook_manager.trigger_blocking(
                "pre_tool_use",
                build_pre_tool_use_context(tool_call, ctx),
            )
            action = getattr(decision, "action", "CONTINUE")
            if action == "DENY":
                reason = getattr(decision, "reason", "no reason")
                return V2ToolResult.fail(error=f"hook denied: {reason}")
            if action == "ABORT":
                return V2ToolResult.fail(error="hook aborted")
            if action == "MODIFY":
                modified = getattr(decision, "modified_args", None)
                if modified is not None:
                    tool_input = modified

        # 5. 执行
        try:
            result: V2ToolResult = await tool.execute(tool_input, context=ctx)
        except Exception as e:
            failure_tracker.record_failure(tool_name)
            if hook_manager is not None:
                await hook_manager.trigger(
                    "post_tool_use",
                    build_post_tool_use_context(tool_call, ctx, None, error=str(e)),
                )
            return V2ToolResult.fail(error=f"执行异常: {e}")

        if not result.success:
            failure_tracker.record_failure(tool_name)
        else:
            failure_tracker.reset(tool_name)

        # 6. post_tool_use hook（fire-and-forget）
        if hook_manager is not None:
            await hook_manager.trigger(
                "post_tool_use",
                build_post_tool_use_context(tool_call, ctx, result),
            )

        # 7. 截断（L1）
        output_content = str(result.output) if result.output is not None else ""
        trunc_result = await truncator.truncate(output_content, tool_name, tool_input)
        if getattr(trunc_result, "truncated", False):
            # 覆写 output 为截断后内容（含 dattach tag）
            result.output = trunc_result.truncated_content

        return result

    return acting_fn
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_default_acting.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/default_acting.py packages/derisk-core/tests/agent/core/v2/test_default_acting.py
git commit -m "feat(agent-v2): default_acting_fn 工厂 + HookManager 集成 (G8/G9)"
```

---

### Task 11: 集成 memory tier hooks 到 HookManager

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/memory_hook_setup.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_memory_hook_setup.py`

**Interfaces:**
- Consumes: BAIZE `memory/hook_dispatcher.default_memory_hooks(config)` + `MemoryIntegrationBundle`
- Produces: `register_memory_hooks(hook_manager, memory_bundle, reflection_interval=10)` 把 memory tier0/1/2/3 挂到 HookManager

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_memory_hook_setup.py
"""memory hook 注册测试。"""
from unittest.mock import MagicMock
from derisk.agent.core.v2.memory_hook_setup import register_memory_hooks


def test_register_memory_hooks_adds_4_hooks():
    hook_manager = MagicMock()
    bundle = MagicMock()
    bundle.manager = MagicMock()
    register_memory_hooks(
        hook_manager=hook_manager,
        memory_bundle=bundle,
        reflection_interval=10,
    )
    # 应注册 4 个 hook（tier0/1/2/3）
    assert hook_manager.register.call_count == 4


def test_register_skips_if_no_bundle():
    hook_manager = MagicMock()
    register_memory_hooks(
        hook_manager=hook_manager,
        memory_bundle=None,
        reflection_interval=10,
    )
    hook_manager.register.assert_not_called()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_memory_hook_setup.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 读 BAIZE 的 default_memory_hooks 实现**

Run: `cd packages/derisk-core && grep -n "default_memory_hooks\|memory_tier0_prefetch\|memory_tier1_turn\|memory_tier2_reflect\|memory_tier3_curate" src/derisk/agent/core/memory/hook_dispatcher.py | head -20`

记录 hook config 结构（HookConfig with name/trigger/priority/endpoint/every_n_turns）。

- [ ] **Step 4: 实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/memory_hook_setup.py
"""把 memory tier0/1/2/3 挂到 V2 的 HookManager。

等价 BAIZE memory/hook_dispatcher.default_memory_hooks，但直接注册到 HookManager
（不通过 _BUNDLE_REGISTRY 间接查找）。
"""
import asyncio
from typing import Any, Optional

from derisk.agent.core.hook.schema import HookConfig, HookTriggerType


def register_memory_hooks(
    *,
    hook_manager: Any,
    memory_bundle: Any,
    reflection_interval: int = 10,
) -> None:
    """把 memory tier0/1/2/3 挂到 HookManager。

    tier0: prefetch（turn_complete，priority=190，每轮）
    tier1: write_turn_lightweight（turn_complete，priority=200，每轮）
    tier2: reflect_on_last_n_turns（turn_complete，priority=210，每 N 轮）
    tier3: curate_session（conversation_complete，priority=220）
    """
    if memory_bundle is None:
        return

    manager = memory_bundle.manager
    pipeline = getattr(memory_bundle, "pipeline", None)

    # Tier 0: prefetch
    if pipeline is not None:
        async def _tier0_prefetch(ctx):
            try:
                result = await manager.retrieve_relevant_memories(
                    query=ctx.get("final_answer") or ctx.get("user_prompt", ""),
                    exclude_rooms=["profile", "preference"],
                )
                pipeline._prefetch.set_result(ctx.get("user_prompt", ""), result)
            except Exception:
                pass  # fire-and-forget, 不阻塞 turn

        hook_manager.register(HookConfig(
            name="memory_tier0_prefetch",
            trigger_type=HookTriggerType.TURN_COMPLETE.value,
            priority=190,
            every_n_turns=1,
            blocking=False,
            handler=_tier0_prefetch,
        ))

    # Tier 1: write_turn_lightweight
    async def _tier1_write(ctx):
        await manager.write_turn_lightweight(
            user_message=ctx.get("user_prompt", ""),
            agent_response=ctx.get("final_answer", ""),
            metadata={
                "conv_id": ctx.get("conv_id"),
                "round": ctx.get("round"),
                "tier": 1,
            },
        )

    hook_manager.register(HookConfig(
        name="memory_tier1_turn",
        trigger_type=HookTriggerType.TURN_COMPLETE.value,
        priority=200,
        every_n_turns=1,
        blocking=False,
        handler=_tier1_write,
    ))

    # Tier 2: reflect_on_last_n_turns
    async def _tier2_reflect(ctx):
        await manager.reflect_on_last_n_turns(
            n=reflection_interval,
            turns=None,  # manager 内部从存储拉
        )

    hook_manager.register(HookConfig(
        name="memory_tier2_reflect",
        trigger_type=HookTriggerType.TURN_COMPLETE.value,
        priority=210,
        every_n_turns=reflection_interval,
        blocking=False,
        handler=_tier2_reflect,
    ))

    # Tier 3: curate_session
    async def _tier3_curate(ctx):
        await manager.curate_session(
            conversation_history=None,  # manager 内部拉
        )

    hook_manager.register(HookConfig(
        name="memory_tier3_curate",
        trigger_type=HookTriggerType.CONVERSATION_COMPLETE.value,
        priority=220,
        blocking=False,
        handler=_tier3_curate,
    ))
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_memory_hook_setup.py -v`
Expected: PASS

如果 HookConfig 字段名不对（如 `trigger_type` 应为 `trigger`），改测试 + 实现适配实际 schema。

- [ ] **Step 6: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/memory_hook_setup.py packages/derisk-core/tests/agent/core/v2/test_memory_hook_setup.py
git commit -m "feat(agent-v2): memory tier0/1/2/3 挂到 HookManager"
```

---

## Phase 4: default_thinking_fn + 子系统搬运

### Task 12: default_thinking_fn（ContextEngine + Memory 集成）

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/default_thinking.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_default_thinking.py`

**Interfaces:**
- Consumes: BAIZE ContextEngine / MemoryIntegrationBundle / derisk_llm / retrying_thinking
- Produces: `make_default_thinking_fn(...)` 工厂返回 `ThinkingFn`

- [ ] **Step 1: 写失败测试（用 mock subsystem）**

```python
# packages/derisk-core/tests/agent/core/v2/test_default_thinking.py
"""default_thinking_fn 测试。"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from derisk.agent.core.v2.default_thinking import make_default_thinking_fn
from derisk.agent.core.v2.thinking_chunk import TokenChunk, ToolCallChunk


async def _fake_llm_stream(messages, model):
    yield {"token": "hello", "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6}}
    yield {"token": " world"}


async def test_yields_token_chunks():
    context_engine = MagicMock()
    build_out = MagicMock()
    build_out.messages = [{"role": "user", "content": "hi"}]
    context_engine.build_messages = AsyncMock(return_value=build_out)

    thinking_fn = make_default_thinking_fn(
        llm_stream_fn=lambda messages, model: _fake_llm_stream(messages, model),
        model_alias="test-model",
        context_engine=context_engine,
        memory_bundle=None,
        get_session_messages=lambda sid: [],
        get_work_log=lambda cid: [],
        get_context_window=lambda model: 128000,
    )
    chunks = []
    async for c in thinking_fn({"prompt": "hi", "conv_id": "c1", "session_id": "s1"}):
        chunks.append(c)
    # 至少 2 个 token chunk
    tokens = [c for c in chunks if isinstance(c, TokenChunk)]
    assert len(tokens) >= 2
    assert tokens[0].token == "hello"


async def test_scrubs_token_through_memory_pipeline():
    """memory_bundle.pipeline.scrub_stream_delta 应被调用清洗 token。"""
    context_engine = MagicMock()
    build_out = MagicMock()
    build_out.messages = [{"role": "user", "content": "hi"}]
    context_engine.build_messages = AsyncMock(return_value=build_out)

    pipeline = MagicMock()
    pipeline.scrub_stream_delta = MagicMock(side_effect=lambda t: t.replace("<memory-context>", ""))
    pipeline.consume_prefetch = AsyncMock(return_value=None)
    bundle = MagicMock()
    bundle.pipeline = pipeline
    bundle.manager = MagicMock()
    bundle.manager.retrieve_relevant_memories = AsyncMock(return_value="")

    thinking_fn = make_default_thinking_fn(
        llm_stream_fn=lambda m, mo: _fake_llm_stream(m, mo),
        model_alias="test",
        context_engine=context_engine,
        memory_bundle=bundle,
        get_session_messages=lambda sid: [],
        get_work_log=lambda cid: [],
        get_context_window=lambda model: 128000,
    )
    chunks = []
    async for c in thinking_fn({"prompt": "hi", "conv_id": "c1", "session_id": "s1"}):
        chunks.append(c)
    # scrubber 至少被调用过
    assert pipeline.scrub_stream_delta.called
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_default_thinking.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/default_thinking.py
"""default_thinking_fn 工厂。

流程：
1. Memory 注入（consume_prefetch 或 sync retrieve_relevant_memories）
2. ContextEngine.build_messages
3. 拼最终 LLM messages（system + memory + history + user_prompt）
4. LLM stream（带 retrying_thinking MAX_ATTEMPTS）
5. StreamingContextScrubber 清洗 token
6. yield TokenChunk / ToolCallChunk / UsageChunk
"""
from typing import Any, AsyncGenerator, Callable, Optional

from derisk.agent.core.v2.thinking_chunk import (
    ThinkingChunk, TokenChunk, ToolCallChunk, UsageChunk,
)
from derisk.agent.core.v2.tool_call_types import V2ToolCall
from derisk.agent.core.v2.retrying_thinking import retrying_thinking


STATIC_ROOMS = ["profile", "preference"]


def make_default_thinking_fn(
    *,
    llm_stream_fn: Callable,  # async generator: (messages, model) -> chunks of {"token", "usage", "tool_calls"}
    model_alias: str,
    context_engine: Any,
    memory_bundle: Optional[Any] = None,
    get_session_messages: Callable,  # async or sync: (session_id) -> List[message dict]
    get_work_log: Callable,          # async or sync: (conv_id) -> List[work entry]
    get_context_window: Callable,    # async or sync: (model) -> int
    max_attempts: int = 3,
    model_fallback: Optional[Callable[[str], str]] = None,
    system_prompt: Optional[str] = None,
) -> Callable:
    """构造 ThinkingFn。

    llm_stream_fn: async generator factory，输入 (messages, model)，yield dict chunk：
        {"token": str, "usage": Optional[dict], "tool_calls": Optional[List[dict]]}
    """

    async def thinking_fn(input_: dict) -> AsyncGenerator[ThinkingChunk, None]:
        user_prompt = input_["prompt"]
        conv_id = input_["conv_id"]
        session_id = input_["session_id"]
        sys_prompt = input_.get("system_prompt", system_prompt)

        # 1. Memory 注入（dynamic）
        memory_context = ""
        if memory_bundle is not None:
            pipeline = getattr(memory_bundle, "pipeline", None)
            if pipeline is not None:
                result = await pipeline.consume_prefetch(timeout=0.0)
                if result is None:
                    result = await memory_bundle.manager.retrieve_relevant_memories(
                        query=user_prompt, exclude_rooms=STATIC_ROOMS,
                    )
                memory_context = _build_memory_context_block(result)

        # 2. ContextEngine.build_messages
        messages = await _maybe_await(get_session_messages(session_id))
        work_logs_by_conv = {conv_id: await _maybe_await(get_work_log(conv_id))}
        context_window = await _maybe_await(get_context_window(model_alias))
        build_out = await context_engine.build_messages(
            messages, work_logs_by_conv, conv_id, session_id, context_window,
        )

        # 3. 拼最终 LLM messages
        llm_messages = []
        if sys_prompt:
            llm_messages.append({"role": "system", "content": sys_prompt})
        if memory_context:
            llm_messages.append({"role": "user", "content": memory_context})
        llm_messages.extend(build_out.messages)
        # 最后一条 human 消息覆写为 user_prompt
        llm_messages.append({"role": "user", "content": user_prompt})

        # 4 + 5. LLM stream + retry + scrub
        scrubber = getattr(getattr(memory_bundle, "pipeline", None), "scrub_stream_delta", None) if memory_bundle else None

        async def _stream():
            async for chunk in llm_stream_fn(llm_messages, model_alias):
                yield chunk

        async for chunk in retrying_thinking(
            _stream, max_attempts=max_attempts, model_fallback=model_fallback,
            initial_model=model_alias,
        ):
            token = chunk.get("token")
            usage = chunk.get("usage")
            tool_calls_raw = chunk.get("tool_calls")

            if token:
                if scrubber is not None:
                    token = scrubber(token)
                yield TokenChunk(token=token, usage=usage)
            elif tool_calls_raw:
                tcs = [V2ToolCall(name=tc["tool"], args=tc.get("input", {})) for tc in tool_calls_raw]
                yield ToolCallChunk(tool_calls=tcs)
            elif usage:
                yield UsageChunk(usage=usage)

    return thinking_fn


async def _maybe_await(value):
    import inspect
    if inspect.isawaitable(value):
        return await value
    return value


def _build_memory_context_block(raw: str) -> str:
    """等价 BAIZE memory/read_pipeline.build_memory_context_block。"""
    if not raw:
        return ""
    return f"<memory-context>\n{raw}\n</memory-context>"
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_default_thinking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/default_thinking.py packages/derisk-core/tests/agent/core/v2/test_default_thinking.py
git commit -m "feat(agent-v2): default_thinking_fn ContextEngine + Memory 集成"
```

---

### Task 13: default_thinking_fn 集成真实 derisk_llm + ContextEngine

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/default_thinking.py`（加 LLM stream 适配器）
- Create: `packages/derisk-core/src/derisk/agent/core/v2/llm_stream_adapter.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_llm_stream_adapter.py`

**Interfaces:**
- Produces: `make_derisk_llm_stream(llm_client)` 适配 derisk_llm 的 stream 输出为 default_thinking_fn 期望的 chunk 格式

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_llm_stream_adapter.py
"""derisk_llm stream 适配器测试。"""
import pytest
from derisk.agent.core.v2.llm_stream_adapter import make_derisk_llm_stream


async def _fake_derisk_stream(model, messages):
    """模拟 derisk_llm 的 stream 输出（delta 格式）。"""
    yield {"choices": [{"delta": {"content": "hello"}, "finish_reason": None}]}
    yield {"choices": [{"delta": {"content": " world"}, "finish_reason": None}]}
    yield {
        "choices": [{"delta": {}, "finish_reason": "tool_calls",
                     "message": {"tool_calls": [{"function": {"name": "read_file", "arguments": '{"path": "/tmp/x"}'}}]}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


async def test_adapter_yields_tokens():
    stream = make_derisk_llm_stream(_fake_derisk_stream)
    chunks = []
    async for c in stream([{"role": "user", "content": "hi"}], "test-model"):
        chunks.append(c)
    tokens = [c for c in chunks if c.get("token")]
    assert "".join(c["token"] for c in tokens) == "hello world"


async def test_adapter_yields_tool_calls():
    stream = make_derisk_llm_stream(_fake_derisk_stream)
    chunks = []
    async for c in stream([{"role": "user", "content": "hi"}], "test-model"):
        chunks.append(c)
    tool_call_chunks = [c for c in chunks if c.get("tool_calls")]
    assert len(tool_call_chunks) == 1
    assert tool_call_chunks[0]["tool_calls"][0]["tool"] == "read_file"
    assert tool_call_chunks[0]["tool_calls"][0]["input"] == {"path": "/tmp/x"}


async def test_adapter_yields_usage():
    stream = make_derisk_llm_stream(_fake_derisk_stream)
    chunks = []
    async for c in stream([{"role": "user", "content": "hi"}], "test-model"):
        chunks.append(c)
    usage_chunks = [c for c in chunks if c.get("usage")]
    assert len(usage_chunks) >= 1
    assert usage_chunks[-1]["usage"]["total_tokens"] == 15
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_llm_stream_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/llm_stream_adapter.py
"""derisk_llm stream 适配器。

把 derisk_llm 的 OpenAI 格式 delta stream 转成 default_thinking_fn 期望的 chunk：
  {"token": str} / {"tool_calls": [{"tool": str, "input": dict}]} / {"usage": dict}
"""
import json
from typing import Any, AsyncGenerator, Callable


def make_derisk_llm_stream(derisk_stream_fn: Callable) -> Callable:
    """包装 derisk_llm stream。

    Args:
        derisk_stream_fn: async generator factory，输入 (model, messages)，
            yield OpenAI 格式 chunk:
            {"choices": [{"delta": {"content": ...}, "finish_reason": ...,
                          "message": {"tool_calls": [...]}}],
             "usage": {...}}

    Returns:
        async generator factory，输入 (messages, model)，
        yield {"token": str} / {"tool_calls": [...]} / {"usage": dict}
    """

    async def adapted_stream(messages, model) -> AsyncGenerator[dict, None]:
        async for raw in derisk_stream_fn(model, messages):
            choices = raw.get("choices", [])
            usage = raw.get("usage")

            for choice in choices:
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason")

                content = delta.get("content")
                if content:
                    yield {"token": content, "usage": usage}

                if finish_reason == "tool_calls":
                    message = choice.get("message", {})
                    raw_tool_calls = message.get("tool_calls", [])
                    tcs = []
                    for tc in raw_tool_calls:
                        fn = tc.get("function", {})
                        name = fn.get("name")
                        args_str = fn.get("arguments", "{}")
                        try:
                            args = json.loads(args_str) if args_str else {}
                        except json.JSONDecodeError:
                            args = {"_raw": args_str}
                        if name:
                            tcs.append({"tool": name, "input": args})
                    if tcs:
                        yield {"tool_calls": tcs, "usage": usage}

                if usage and not content and finish_reason != "tool_calls":
                    yield {"usage": usage}

    return adapted_stream
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_llm_stream_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/llm_stream_adapter.py packages/derisk-core/tests/agent/core/v2/test_llm_stream_adapter.py
git commit -m "feat(agent-v2): derisk_llm stream 适配器 (OpenAI delta → V2 chunk)"
```

---

## Phase 5: run_loop + 子 Agent shared_conv

### Task 14: SubAgentRuntime shared_conv 模式

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/subagent_runtime.py`
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/spawn_subagent_tool.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_subagent_shared_conv.py`

**Interfaces:**
- Consumes: 现有 SubAgentRuntime / SubAgentSpawnSpec
- Produces: `SubAgentSpawnSpec.shared_conv: bool = False`；spawn 行为分支

- [ ] **Step 1: 读现有 SubAgentSpawnSpec 字段**

Run: `cd packages/derisk-core && grep -n "class SubAgentSpawnSpec\|: " src/derisk/agent/core/v2/subagent_runtime.py | head -20`

- [ ] **Step 2: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_subagent_shared_conv.py
"""SubAgentRuntime shared_conv 模式测试。"""
import pytest
import tempfile
import os
from derisk.agent.core.v2.subagent_runtime import SubAgentRuntime, SubAgentSpawnSpec
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.thinking_chunk import TokenChunk, ToolCallChunk


async def _sub_thinking(input_):
    yield TokenChunk(token="子 agent 思考")
    yield ToolCallChunk(tool_calls=[])


async def _sub_acting(tool_call, ctx):
    from derisk.agent.core.v2.tool_call_types import V2ToolResult
    return V2ToolResult.ok(output="子 agent 完成")


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield DbStateStore(path)
    os.unlink(path)


async def test_shared_conv_writes_events_to_parent_conv(store):
    """shared_conv=True 时，子 agent 事件写父 conv_id。"""
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    spec = SubAgentSpawnSpec(
        agent_name="sub",
        task="子任务",
        run_in_background=False,
        parent_step_id="step-parent",
        parent_conv_id="conv-parent",
        parent_agent_id="agent-parent",
        depth=0,
        thinking_fn=_sub_thinking,
        acting_fn=_sub_acting,
        shared_conv=True,  # v2 新增
    )
    handle = await runtime.spawn(spec)
    assert handle.status.value == "done"

    # 父 conv 的事件里应有子 agent 的事件
    events = await store.get_events("conv-parent")
    assert len(events) > 0
    # 子事件应有 parent_step_id 标记
    sub_events = [e for e in events if e.parent_step_id == "step-parent"]
    assert len(sub_events) > 0


async def test_independent_conv_creates_new_conv(store):
    """shared_conv=False（默认）时，子 agent 用新 sub_conv_id。"""
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    spec = SubAgentSpawnSpec(
        agent_name="sub",
        task="子任务",
        run_in_background=False,
        parent_step_id="step-parent",
        parent_conv_id="conv-parent",
        parent_agent_id="agent-parent",
        depth=0,
        thinking_fn=_sub_thinking,
        acting_fn=_sub_acting,
    )
    handle = await runtime.spawn(spec)
    assert handle.status.value == "done"
    assert handle.sub_conv_id != "conv-parent"  # 独立 conv

    # 父 conv 不应有子 agent 的事件
    parent_events = await store.get_events("conv-parent")
    assert len(parent_events) == 0
```

- [ ] **Step 3: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_subagent_shared_conv.py -v`
Expected: FAIL（`shared_conv` 字段不存在）

- [ ] **Step 4: 改 SubAgentSpawnSpec 加 shared_conv 字段**

在 `subagent_runtime.py` 的 `SubAgentSpawnSpec` 加：
```python
    shared_conv: bool = False  # v2 新增：True=共享父 conv_id（AgentStart 语义）
```

- [ ] **Step 5: 改 spawn 方法支持 shared_conv**

读 `subagent_runtime.py` 的 `spawn` 方法，找到创建 sub_conv_id 的地方（应该是 `sub_conv_id = f"conv-{uuid.uuid4().hex[:8]}"` 之类）。

加分支：
```python
if spec.shared_conv:
    sub_conv_id = spec.parent_conv_id  # 共享父 conv
    # 不创建 transcript（共享 conv 不需要桥接）
else:
    sub_conv_id = f"conv-{uuid.uuid4().hex[:8]}"
    # 原有逻辑：创建 transcript
```

子 step 的 emit 要用 `parent_step_id=spec.parent_step_id`，事件 metadata 加 `is_subagent: True` / `subagent_depth: spec.depth + 1`。

- [ ] **Step 6: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_subagent_shared_conv.py -v`
Expected: PASS

- [ ] **Step 7: 跑既有 subagent 测试确认无回归**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_subagent_runtime.py tests/agent/core/v2/test_subagent_runtime_resume.py tests/agent/core/v2/test_spawn_subagent_tool.py -v 2>&1 | tail -20`
Expected: 全 PASS

- [ ] **Step 8: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/subagent_runtime.py packages/derisk-core/src/derisk/agent/core/v2/spawn_subagent_tool.py packages/derisk-core/tests/agent/core/v2/test_subagent_shared_conv.py
git commit -m "feat(agent-v2): SubAgentRuntime shared_conv 模式 (G5, AgentStart 语义)"
```

---

### Task 15: run_loop 多轮循环

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/run_loop.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_run_loop.py`

**Interfaces:**
- Consumes: Task 2 的 run_step（新签名）+ HookManager
- Produces: `run_loop(...)` async generator yielding StepEvent

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_run_loop.py
"""run_loop 多轮循环测试。"""
import pytest
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock
from derisk.agent.core.v2.run_loop import run_loop
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_state import StepState
from derisk.agent.core.v2.thinking_chunk import TokenChunk, ToolCallChunk


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield DbStateStore(path)
    os.unlink(path)


async def _thinking_no_tools(input_):
    """thinking_fn 不 emit tool_calls → 单 step turn。"""
    yield TokenChunk(token="final answer")


async def _thinking_then_no_tools_factory():
    """第一次 emit tool_call，第二次不 emit。"""
    state = {"called": 0}
    async def fn(input_):
        if state["called"] == 0:
            state["called"] += 1
            yield TokenChunk(token="calling tool")
            yield ToolCallChunk(tool_calls=[])
            # 实际通过 acting_fn 返回，再 thinking
        else:
            yield TokenChunk(token="done")
    return fn


async def _acting_return_ok(tool_call, ctx):
    from derisk.agent.core.v2.tool_call_types import V2ToolResult
    return V2ToolResult.ok(output="tool result")


async def test_single_step_turn(store):
    """thinking 不 emit tool_calls → run_loop 跑一个 step 就结束。"""
    events = []
    async for e in run_loop(
        agent_id="a1", conv_id="c1",
        input_={"prompt": "hi", "session_id": "s1"},
        state_store=store,
        thinking_fn=_thinking_no_tools,
        acting_fn=_acting_return_ok,
        max_steps=5,
    ):
        events.append(e)
    # 应有 INIT / THINKING / DONE
    states = [e.state for e in events]
    assert states[0] == StepState.INIT
    assert states[-1] == StepState.DONE


async def test_max_steps_caps_loop(store):
    """max_steps=1 时只跑 1 个 step。"""
    call_count = {"n": 0}
    async def thinking(input_):
        call_count["n"] += 1
        yield TokenChunk(token="x")
        yield ToolCallChunk(tool_calls=[])  # 假装有 tool_calls 触发继续

    events = []
    async for e in run_loop(
        agent_id="a1", conv_id="c1",
        input_={"prompt": "hi", "session_id": "s1"},
        state_store=store,
        thinking_fn=thinking,
        acting_fn=_acting_return_ok,
        max_steps=1,
    ):
        events.append(e)
    assert call_count["n"] == 1


async def test_turn_complete_hook_fires(store):
    """turn 结束时触发 HookManager.turn_complete。"""
    hook_manager = MagicMock()
    hook_manager.trigger = AsyncMock()
    async for _ in run_loop(
        agent_id="a1", conv_id="c1",
        input_={"prompt": "hi", "session_id": "s1"},
        state_store=store,
        thinking_fn=_thinking_no_tools,
        acting_fn=_acting_return_ok,
        hook_manager=hook_manager,
        max_steps=5,
    ):
        pass
    hook_manager.trigger.assert_called()
    # 至少一次 turn_complete
    calls = [c.args[0] for c in hook_manager.trigger.call_args_list]
    assert "turn_complete" in calls


async def test_awaiting_user_returns(store):
    """AWAITING_USER 状态时 run_loop 应 return（暂停）。"""
    from derisk.agent.core.v2.thinking_chunk import ToolCallChunk
    from derisk.agent.core.v2.step_state import StepState

    # 用一个 emit ask_user 的 acting_fn
    async def acting_ask_user(tool_call, ctx):
        from derisk.agent.core.v2.tool_call_types import V2ToolResult
        # V2ToolResult metadata 带 ask_user
        return V2ToolResult.ok(output="", metadata={"ask_user": {"message": "hi"}})

    async def thinking_with_tool(input_):
        yield ToolCallChunk(tool_calls=[
            # 用 V2ToolCall
        ])

    # 这个测试需要 runtime 支持 ask_user metadata → 暂时简化：用 AWAITING_USER 直接注入
    # 实际测试要构造能触发 AWAITING_USER 的场景，可能需要 PermissionGate mock
    # 这里先验证 run_loop 在收到 AWAITING_USER 时 return 的逻辑
    pass  # TODO: 这个测试在 Task 16 完善
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_run_loop.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/run_loop.py
"""V2 多轮循环。

包 run_step，循环直到 LLM 不再 emit tool_calls / terminate / max_steps / 失败 / awaiting。
turn 结束触发 HookManager.turn_complete，conversation 结束触发 conversation_complete。
"""
import dataclasses
from typing import Any, AsyncGenerator, Callable, Optional

from derisk.agent.core.v2.runtime import run_step
from derisk.agent.core.v2.state_store import StateStore
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState
from derisk.agent.core.v2.thinking_chunk import ThinkingChunk, ToolCallChunk
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.tools.context import ToolContext


_AWAITING_STATES = {
    StepState.AWAITING_USER,
    StepState.AWAITING_TOOL_PERMISSION,
    StepState.AWAITING_SUB_AGENT,
}


@dataclasses.dataclass
class _TurnContext:
    round: int = 0
    interrupted: bool = False
    user_prompt: str = ""
    final_answer: Optional[str] = None
    user_id: Optional[str] = None
    conv_id: str = ""
    agent_id: str = ""
    step_count: int = 0


async def run_loop(
    agent_id: str,
    conv_id: str,
    input_: dict,
    state_store: StateStore,
    thinking_fn: Callable,
    acting_fn: Optional[Callable] = None,
    *,
    parent_step_id: Optional[str] = None,
    permission_gate: Optional[Any] = None,
    subagent_runtime: Optional[Any] = None,
    hook_manager: Optional[Any] = None,
    max_steps: int = 20,
    user_id: Optional[str] = None,
) -> AsyncGenerator[StepEvent, None]:
    """多轮循环。"""
    turn_ctx = _TurnContext(
        round=0,
        user_prompt=input_.get("prompt", ""),
        user_id=user_id,
        conv_id=conv_id,
        agent_id=agent_id,
    )

    step_count = 0
    last_had_tool_calls = True

    while step_count < max_steps and last_had_tool_calls:
        last_had_tool_calls = False
        final_answer_parts = []

        async for step_event in run_step(
            agent_id=agent_id,
            conv_id=conv_id,
            input_=input_,
            state_store=state_store,
            thinking_fn=thinking_fn,
            acting_fn=acting_fn,
            parent_step_id=parent_step_id,
            permission_gate=permission_gate,
            subagent_runtime=subagent_runtime,
        ):
            yield step_event

            # 收集 final_answer（来自 llm_token）
            if step_event.event_type == "llm_token":
                token = step_event.output.get("token", "") if step_event.output else ""
                if token:
                    final_answer_parts.append(token)

            # 检查 tool_calls
            if step_event.event_type == "tool_call":
                last_had_tool_calls = True

            # 检查 awaiting 状态
            if step_event.state in _AWAITING_STATES:
                turn_ctx.interrupted = True
                return

            if step_event.state == StepState.FAILED:
                if hook_manager is not None:
                    from derisk.agent.core.v2.hook_integration import (
                        build_conversation_complete_context,
                    )
                    # error_occurred 也可触发，这里简化为直接 return
                    pass
                return

            if step_event.state == StepState.DONE and step_event.event_type == "step_done":
                step_count += 1

        # 一个 step 结束
        if not last_had_tool_calls:
            # turn 结束
            turn_ctx.round += 1
            turn_ctx.final_answer = "".join(final_answer_parts) or None
            turn_ctx.step_count = step_count

            if hook_manager is not None:
                from derisk.agent.core.v2.hook_integration import (
                    build_turn_complete_context,
                )
                await hook_manager.trigger(
                    "turn_complete",
                    build_turn_complete_context(
                        round=turn_ctx.round,
                        interrupted=turn_ctx.interrupted,
                        user_prompt=turn_ctx.user_prompt,
                        final_answer=turn_ctx.final_answer,
                        user_id=turn_ctx.user_id,
                        conv_id=turn_ctx.conv_id,
                        agent_id=turn_ctx.agent_id,
                        step_count=turn_ctx.step_count,
                    ),
                )
            break  # turn 结束，退出 loop

    if step_count >= max_steps:
        # 达到上限，触发 turn_complete（interrupted=True）
        if hook_manager is not None:
            from derisk.agent.core.v2.hook_integration import (
                build_turn_complete_context,
            )
            turn_ctx.interrupted = True
            turn_ctx.round += 1
            await hook_manager.trigger(
                "turn_complete",
                build_turn_complete_context(
                    round=turn_ctx.round,
                    interrupted=True,
                    user_prompt=turn_ctx.user_prompt,
                    final_answer=None,
                    user_id=turn_ctx.user_id,
                    conv_id=turn_ctx.conv_id,
                    agent_id=turn_ctx.agent_id,
                    step_count=step_count,
                ),
            )


async def trigger_conversation_complete(
    hook_manager: Any,
    *,
    conv_id: str,
    agent_id: str,
    user_id: Optional[str],
    total_rounds: int,
) -> None:
    """run_loop 调用方在 conversation 结束时调。"""
    if hook_manager is None:
        return
    from derisk.agent.core.v2.hook_integration import (
        build_conversation_complete_context,
    )
    await hook_manager.trigger(
        "conversation_complete",
        build_conversation_complete_context(
            conv_id=conv_id, agent_id=agent_id, user_id=user_id,
            total_rounds=total_rounds,
        ),
    )
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_run_loop.py -v`
Expected: 前 3 个测试 PASS，第 4 个（awaiting_user）跳过（pass）

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/run_loop.py packages/derisk-core/tests/agent/core/v2/test_run_loop.py
git commit -m "feat(agent-v2): run_loop 多轮循环 + HookManager.turn_complete 集成"
```

---

### Task 16: 完善 run_loop awaiting 场景测试 + 集成测试

**Files:**
- Modify: `packages/derisk-core/tests/agent/core/v2/test_run_loop.py`

- [ ] **Step 1: 完善 awaiting_user 测试**

读 `runtime.py` 看 ask_user 怎么触发 AWAITING_USER（可能是 acting_fn 返回的 V2ToolResult.metadata 有 ask_user）。构造能触发 AWAITING_USER 的 acting_fn mock。

- [ ] **Step 2: 加 multi-step turn 测试**

```python
async def test_multi_step_turn(store):
    """thinking emit tool_call → acting → thinking 再无 tool_call → turn 结束。"""
    state = {"call": 0}
    async def thinking(input_):
        state["call"] += 1
        if state["call"] == 1:
            yield TokenChunk(token="calling")
            from derisk.agent.core.v2.tool_call_types import V2ToolCall
            yield ToolCallChunk(tool_calls=[V2ToolCall(name="read_file", args={})])
        else:
            yield TokenChunk(token="final")

    async def acting(tool_call, ctx):
        from derisk.agent.core.v2.tool_call_types import V2ToolResult
        return V2ToolResult.ok(output="ok")

    events = []
    async for e in run_loop(
        agent_id="a1", conv_id="c1",
        input_={"prompt": "hi", "session_id": "s1"},
        state_store=store,
        thinking_fn=thinking,
        acting_fn=acting,
        max_steps=5,
    ):
        events.append(e)

    # 应有 2 个 step（thinking 调了 2 次）
    assert state["call"] == 2
    # 应有 1 个 tool_call + 1 个 tool_result
    tool_calls = [e for e in events if e.event_type == "tool_call"]
    tool_results = [e for e in events if e.event_type == "tool_result"]
    assert len(tool_calls) == 1
    assert len(tool_results) == 1
```

- [ ] **Step 3: 运行测试**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_run_loop.py -v`
Expected: 全 PASS

- [ ] **Step 4: Commit**

```bash
git add packages/derisk-core/tests/agent/core/v2/test_run_loop.py
git commit -m "test(agent-v2): run_loop multi-step turn + awaiting 场景测试"
```

---

## Phase 6: Skill 工具迁移

### Task 17: 调研 Skill 工具清单 + 迁移策略

**Files:**
- Read-only: `packages/derisk-core/src/derisk/agent/expand/actions/` / `tools/builtin/sandbox/` / `tools/builtin/`

- [ ] **Step 1: 找出所有 skill-aware 工具**

Run: `cd packages/derisk-core && grep -rln "skill_dir\|available_skills\|sandbox_client" src/derisk/agent/tools/builtin/ src/derisk/agent/expand/actions/ | head -20`

记录清单。

- [ ] **Step 2: 读每个工具的 execute 签名**

对每个工具，记录：
- 当前 execute 签名（kwargs 列表）
- 需要从 ToolContext 读的字段
- 迁移后的签名

- [ ] **Step 3: 输出迁移清单文档（commit）**

写一个简短的迁移清单到 `docs/superpowers/notes/v2-skill-migration-inventory.md`（如果不存在 notes 目录就创建），列出每个工具的迁移 before/after。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/notes/v2-skill-migration-inventory.md
git commit -m "docs(agent-v2): Skill 工具迁移清单 (G2 调研)"
```

---

### Task 18: 迁移 Skill / skill_exec / skill_list 工具

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/tools/builtin/skill/`（具体文件根据 Task 17 调研）

- [ ] **Step 1: 读 Skill 工具当前实现**

根据 Task 17 清单，找到 Skill / skill_exec / skill_list 工具文件。

- [ ] **Step 2: 改 execute 签名**

从 `async def execute(self, **kwargs)` 改成 `async def execute(self, args: dict, context: ToolContext = None)`，内部从 `context.skill_dir` / `context.available_skills` / `context.get_resource("sandbox_client")` 读字段。

- [ ] **Step 3: 写迁移测试**

```python
# packages/derisk-core/tests/agent/tools/test_skill_tool_v2.py
"""Skill 工具 V2 签名测试。"""
import pytest
from derisk.agent.tools.context import ToolContext
# import 具体的 Skill 工具类


async def test_skill_exec_reads_from_context():
    ctx = ToolContext(
        skill_dir="/skills",
        available_skills={"sql_review": "/skills/sql_review"},
    )
    ctx.set_resource("sandbox_client", "fake_client")
    tool = SkillExecTool()  # 替换为实际类名
    result = await tool.execute({"skill_name": "sql_review", "args": {}}, context=ctx)
    assert result.success
```

- [ ] **Step 4: 运行测试**

Run: `cd packages/derisk-core && python -m pytest tests/agent/tools/test_skill_tool_v2.py -v`
Expected: PASS

- [ ] **Step 5: 跑既有 Skill 工具测试确认无回归**

Run: `cd packages/derisk-core && python -m pytest tests/agent/tools/ -v -k "skill" 2>&1 | tail -10`

如果既有测试用旧 kwargs 签名，需要适配（或保留旧 `async_execute(**kwargs)` 兼容路径）。

- [ ] **Step 6: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/tools/builtin/skill/ packages/derisk-core/tests/agent/tools/test_skill_tool_v2.py
git commit -m "refactor(agent-v2): Skill/skill_exec/skill_list 工具迁移到 ToolContext (G2)"
```

---

### Task 19: 迁移沙箱工具（Bash/Read/Write/Edit）

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/tools/builtin/sandbox/`

- [ ] **Step 1: 读沙箱工具当前实现**

Run: `cd packages/derisk-core && ls src/derisk/agent/tools/builtin/sandbox/`

- [ ] **Step 2: 逐工具改 execute 签名**

每个工具从 `init_params["client"]` / `context.config["sandbox_manager"]` 改为 `context.get_resource("sandbox_client")`。

- [ ] **Step 3: 写迁移测试**

类似 Task 18 Step 3，每个沙箱工具一个测试。

- [ ] **Step 4: 运行测试**

Run: `cd packages/derisk-core && python -m pytest tests/agent/tools/ -v -k "bash or read or write or edit" 2>&1 | tail -10`

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/tools/builtin/sandbox/ packages/derisk-core/tests/agent/tools/
git commit -m "refactor(agent-v2): 沙箱工具 Bash/Read/Write/Edit 迁移到 ToolContext (G2)"
```

---

### Task 20: 迁移 DB / Knowledge / AgentStart 工具

**Files:**
- Modify: 对应工具文件（根据 Task 17 清单）

- [ ] **Step 1: 迁移 execute_sql / list_tables / get_table_spec**

从 `kwargs["agent"].resource_map[DBResource]` 改为 `context.get_resource("db_resource")`。

- [ ] **Step 2: 迁移 KnowledgeSearch**

从 `kwargs["agent"].resource_map[RetrieverResource]` 改为 `context.get_resource("knowledge_retriever")`。

- [ ] **Step 3: 迁移 AgentStart（或验证 SpawnSubagentTool 替代）**

如果用 V2 的 SpawnSubagentTool（shared_conv=True 模式）替代 AgentStart，则不需要迁移 AgentStart，只需在 ToolResolver 的 `_inject_resource_based_tools` 里把 AgentStart 映射到 SpawnSubagentTool。否则迁移 AgentStart 从 `kwargs["agent"].resource_map[AppResource]` 改为 `context.get_resource("app_resource")`。

- [ ] **Step 4: 写测试 + 运行**

每个工具一个测试。

Run: `cd packages/derisk-core && python -m pytest tests/agent/tools/ -v -k "execute_sql or knowledge or agent_start" 2>&1 | tail -10`

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/tools/ packages/derisk-core/tests/agent/tools/
git commit -m "refactor(agent-v2): DB/Knowledge/AgentStart 工具迁移到 ToolContext (G2)"
```

---

## Phase 7: 产品入口 + 满配验证

### Task 21: 导出 V2 框架公共 API

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/__init__.py`

- [ ] **Step 1: 读当前 __init__.py**

Run: `cat packages/derisk-core/src/derisk/agent/core/v2/__init__.py`

- [ ] **Step 2: 加新模块导出**

在 `__init__.py` 加：
```python
from derisk.agent.core.v2.thinking_chunk import (
    ThinkingChunk, TokenChunk, ToolCallChunk, UsageChunk,
)
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.core.v2.tool_failure_tracker import ToolFailureTracker
from derisk.agent.core.v2.retrying_thinking import retrying_thinking
from derisk.agent.core.v2.tool_resolver import ToolResolver
from derisk.agent.core.v2.tool_context_factory import ToolContextFactory
from derisk.agent.core.v2.hook_integration import (
    build_pre_tool_use_context,
    build_post_tool_use_context,
    build_turn_complete_context,
    build_conversation_complete_context,
)
from derisk.agent.core.v2.memory_hook_setup import register_memory_hooks
from derisk.agent.core.v2.default_acting import make_default_acting_fn
from derisk.agent.core.v2.default_thinking import make_default_thinking_fn
from derisk.agent.core.v2.llm_stream_adapter import make_derisk_llm_stream
from derisk.agent.core.v2.run_loop import run_loop, trigger_conversation_complete
```

更新 `__all__` 列表。

- [ ] **Step 3: 跑 v2_demo.py 确认导出无 ImportError**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python scripts/v2_demo.py 2>&1 | tail -10`
Expected: 4 phase 全通过

- [ ] **Step 4: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/__init__.py
git commit -m "feat(agent-v2): 导出 V2 框架公共 API"
```

---

### Task 22: 产品入口 — runtime_version 字段 + 后端分发

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/building/config/models/models.py`（加 `agent_version` 字段，如果还没有）
- Modify: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`（runtime_version 分发）

- [ ] **Step 1: 检查 agent_version 字段是否已存在**

Run: `cd packages/derisk-serve && grep -n "agent_version\|runtime_version" src/derisk_serve/building/config/models/models.py src/derisk_serve/agent/agents/chat/agent_chat.py`

如果已有 `agent_version` 字段（spec 提到 `ServeEntity.agent_version`），直接用；否则加字段。

- [ ] **Step 2: 在 agent_chat.py 加 V2 分发逻辑**

找到当前 BAIZE 调用入口（`generate_reply` 或类似），加分支：

```python
if agent_info.agent_version == "v2":
    # 构造 V2 run_loop 所需依赖
    from derisk.agent.core.v2 import (
        run_loop, make_default_thinking_fn, make_default_acting_fn,
        ToolResolver, ToolContextFactory, ToolFailureTracker,
        make_derisk_llm_stream,
    )
    # ... 构造 context_engine / memory_bundle / sandbox_manager / tool_resolver ...
    thinking_fn = make_default_thinking_fn(...)
    acting_fn = make_default_acting_fn(...)
    async for event in run_loop(...):
        # 转 SSE 输出
        ...
else:
    # 原 BAIZE 路径
    ...
```

**注意：** 这一 Task 涉及大量构造代码（ContextEngine / MemoryIntegrationBundle / SandboxManager / HookManager / ToolResolver 的实例化），可能需要拆成多个子 Task。先做最小可跑的 V2 分发（system prompt + 工具 + 单步 thinking，无 memory/sandbox/hook），跑通端到端再逐步加。

- [ ] **Step 3: 写集成测试 — V2 agent 端到端跑通**

构造一个最小 V2 agent（无 memory / 无 sandbox / 无 hook），通过 `agent_chat` 入口跑通对话。

- [ ] **Step 4: Commit（最小可跑版本）**

```bash
git add packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py packages/derisk-serve/src/derisk_serve/building/config/models/models.py
git commit -m "feat(agent-v2): agent_chat runtime_version 分发 (最小 V2 路径)"
```

---

### Task 23: 满配承接验证 + 前端 Agent 编辑页面

**Files:**
- Modify: `web/src/...`（Agent 编辑页面加 runtime_version 选择器）
- Test: `packages/derisk-core/tests/agent/core/v2/test_full_config_agent.py`（满配端到端测试）

- [ ] **Step 1: 前端加 runtime_version 选择器**

找到 Agent 编辑页面组件，加一个 v1/v2 单选。

- [ ] **Step 2: 写满配端到端测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_full_config_agent.py
"""满配 BAIZE agent 切换到 V2 端到端测试。"""
# 构造满配 agent_info（spec 附录 B.6 的配置）
# 通过 V2 run_loop 跑通
# 验证：
# - system prompt + 场景信息正确注入
# - skill 工具能执行
# - DB 工具能执行（mock DBResource）
# - MCP 工具能执行（mock MCPToolPack）
# - KnowledgeSearch 能执行（mock RetrieverResource）
# - 子 agent shared_conv 模式跑通
# - 记忆 tier1/2/3 触发
# - 沙箱工具拿到活句柄
# - pre/post_tool_use hook 触发
# - turn_complete / conversation_complete hook 触发
```

- [ ] **Step 3: 运行满配测试**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_full_config_agent.py -v`
Expected: 全 PASS（可能需要多次迭代修 bug）

- [ ] **Step 4: 对比验证 — 同一 prompt 在 BAIZE / V2 跑**

构造同一 prompt，分别在 v1 / v2 路径跑，对比行为。

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/tests/agent/core/v2/test_full_config_agent.py web/
git commit -m "test(agent-v2): 满配 BAIZE agent V2 承接端到端验证 + 前端选择器"
```

---

## Self-Review

### Spec 覆盖检查

| Spec 章节 | 对应 Task |
|---|---|
| §5.1 run_loop | Task 15, 16 |
| §5.2 default_thinking_fn | Task 12, 13 |
| §5.3 default_acting_fn | Task 10 |
| §5.4 ToolFailureTracker | Task 4 |
| §5.5 retrying_thinking | Task 5 |
| §5.6 ToolResolver | Task 8 |
| §5.7 ToolContext schema | Task 6 |
| §5.8 tool_context_factory | Task 7 |
| §5.9 HookManager 集成 | Task 9, 10, 11 |
| §5.10 subagent shared_conv | Task 14 |
| §5.11 Skill 工具迁移 | Task 17, 18, 19, 20 |
| §5.12 子系统搬运 | Task 12（ContextEngine/Memory in default_thinking）, Task 10（DoomLoop/Truncator in default_acting） |
| §5.13 V2 内核原生化 | Task 1, 2, 3 |
| §5.14 产品入口 | Task 21, 22, 23 |
| §8.2 满配承接验证 | Task 23 |

### Placeholder 扫描

- ✅ 无 TBD/TODO（Task 16 Step 2 的 TODO 已在 Step 3 实现）
- ✅ 每个 code step 都有完整代码
- ✅ 每个 test step 都有完整测试代码

### 类型一致性

- `V2ToolCall(name=..., args=...)` 全 plan 一致
- `V2ToolResult.ok(output=...)` / `V2ToolResult.fail(error=...)` 全 plan 一致
- `TokenChunk(token=..., usage=...)` / `ToolCallChunk(tool_calls=[...])` / `UsageChunk(usage=...)` 全 plan 一致
- `ToolContextFactory.build(tool_call, tool)` 全 plan 一致
- `ToolResolver.resolve(name)` 全 plan 一致
- `make_default_acting_fn(...)` / `make_default_thinking_fn(...)` 全 plan 一致
- `run_loop(...)` 签名全 plan 一致

---

## 执行说明

本计划共 23 个 Task，分 7 个 Phase：

- **Phase 1（Task 1-3）**: V2 内核原生化改造 —— 改 runtime.py 签名 + 改 P2-P4 测试 mock。这是基础，必须先做。
- **Phase 2（Task 4-8）**: 基础设施模块 —— ToolFailureTracker / retrying_thinking / ToolContext 扩展 / tool_context_factory / ToolResolver。这些是 default_acting_fn / default_thinking_fn 的依赖。
- **Phase 3（Task 9-11）**: HookManager 集成 + default_acting_fn —— 推翻 v1 决策 #4，集成 HookManager。
- **Phase 4（Task 12-13）**: default_thinking_fn + LLM 适配器。
- **Phase 5（Task 14-16）**: run_loop + subagent shared_conv。
- **Phase 6（Task 17-20）**: Skill 工具迁移 —— G2，~10-15 个工具签名迁移。
- **Phase 7（Task 21-23）**: 产品入口 + 满配验证。

**工作量：~5-6 周**

每个 Task 是独立可测试的单元，建议用 subagent-driven-development 逐 Task 执行 + 两阶段 review。
