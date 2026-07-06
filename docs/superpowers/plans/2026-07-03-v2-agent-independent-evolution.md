# V2 Agent 独立演进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现V2 Agent独立运行入口和简化VIS协议渲染，不干扰BAIZE生产框架。

**Architecture:** 双轨并存架构 - V2独立SSE端点 + 新事件发射器 + 简化VIS协议；前端新增V2解析器和组件库，与BAIZE解析器并存。

**Tech Stack:** Python (FastAPI/asyncio), TypeScript (React), SSE (Server-Sent Events), SQLite (StateStore)

## Global Constraints

- BAIZE代码路径零改动（`agent_chat.py`的v1路径不动）
- V2新代码独立文件，不修改现有V2内核文件（`runtime.py`/`run_loop.py`等）
- UID命名约定强制执行：`{step_id}-{component_type}-{index}`
- 事件格式严格遵循设计文档schema

---

## 文件结构规划

### 后端新建文件

```
packages/derisk-core/src/derisk/agent/core/v2/
├── v2_event_emitter.py          # V2事件发射器（新）
├── v2_sse_endpoint.py           # V2 SSE端点入口（新）
├── v2_vis_component.py          # 简化VIS组件类型定义（新）
└── v2_run_loop_adapter.py       # run_loop适配器，集成事件发射（新）

packages/derisk-serve/src/derisk_serve/agent/agents/chat/
├── v2_chat_endpoint.py          # V2 chat API路由（新）
└── v2_chat_schemas.py           # V2请求/响应schema（新）
```

### 前端新建文件

```
web/src/utils/v2/
├── index.ts                     # V2解析器入口
├── V2SimplifiedVisParser.ts     # 简化VIS解析器
├── V2EventHandler.ts            # 事件处理器
├── types.ts                     # 类型定义
└── constants.ts                 # 常量定义

web/src/components/v2/
├── StepPanel.tsx                # step面板容器
├── StepStatusIndicator.tsx      # step状态指示器
├── ThinkingBlock.tsx            # thinking块
├── ToolResultBlock.tsx          # tool结果块
├── UsageDisplay.tsx             # token用量展示
├── SubAgentPanel.tsx            # 子Agent面板
├── InteractionPrompt.tsx        # 用户交互提示
└── ErrorBlock.tsx               # 错误展示
```

### 测试文件

```
packages/derisk-core/tests/agent/core/v2/
├── test_v2_event_emitter.py     # 事件发射器测试
├── test_v2_vis_component.py     # VIS组件测试
└── test_v2_sse_integration.py   # SSE集成测试

web/src/utils/v2/__tests__/
├── V2SimplifiedVisParser.test.ts
└── V2EventHandler.test.ts
```

---

## Part 1: 后端核心模块

### Task 1: V2事件类型和VIS组件定义

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/v2_vis_component.py`
- Create: `packages/derisk-core/src/derisk/agent/core/v2/v2_event_types.py`

**Interfaces:**
- Produces: `SimplifiedVisComponent` dataclass, `V2Event` dict schema, `VisOperationType` enum

- [ ] **Step 1: Write the failing test for SimplifiedVisComponent**

```python
# packages/derisk-core/tests/agent/core/v2/test_v2_vis_component.py
from derisk.agent.core.v2.v2_vis_component import SimplifiedVisComponent, VisOperationType

def test_simplified_vis_component_incr():
    """测试incr操作组件"""
    component = SimplifiedVisComponent(
        type=VisOperationType.INCR,
        uid="s1-thinking-0",
        tag="thinking",
        content="分析中",
        meta={"state": "streaming"}
    )
    assert component.type == VisOperationType.INCR
    assert component.uid == "s1-thinking-0"
    assert component.tag == "thinking"
    assert component.content == "分析中"
    assert component.meta["state"] == "streaming"

def test_simplified_vis_component_replace():
    """测试replace操作组件"""
    component = SimplifiedVisComponent(
        type=VisOperationType.REPLACE,
        uid="s1-step_status-0",
        tag="step_status",
        content="",
        meta={"state": "ACTING", "step_id": "s1"}
    )
    assert component.type == VisOperationType.REPLACE
    assert component.meta["state"] == "ACTING"

def test_simplified_vis_component_delete():
    """测试delete操作组件"""
    component = SimplifiedVisComponent(
        type=VisOperationType.DELETE,
        uid="s1-temp-0",
        tag="temp",
        content=""
    )
    assert component.type == VisOperationType.DELETE

def test_vis_operation_type_values():
    """测试操作类型枚举值"""
    assert VisOperationType.INCR.value == "incr"
    assert VisOperationType.REPLACE.value == "replace"
    assert VisOperationType.DELETE.value == "delete"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/derisk-core/tests/agent/core/v2/test_v2_vis_component.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Write SimplifiedVisComponent implementation**

```python
# packages/derisk-core/src/derisk/agent/core/v2/v2_vis_component.py
"""简化VIS组件 - 无嵌套，原子操作。

设计文档 §4.1-§4.3。
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, Optional


class VisOperationType(Enum):
    """VIS操作类型"""
    INCR = "incr"      # 增量追加
    REPLACE = "replace"  # 全量替换
    DELETE = "delete"    # 删除组件


class VisComponentTag(Enum):
    """VIS组件类型标签"""
    MESSAGE = "message"
    THINKING = "thinking"
    TOOL_RESULT = "tool_result"
    STEP_STATUS = "step_status"
    USAGE_DISPLAY = "usage_display"
    SUB_AGENT_PANEL = "sub_agent_panel"
    INTERACTION_PROMPT = "interaction_prompt"
    ERROR_BLOCK = "error_block"


@dataclass
class SimplifiedVisComponent:
    """简化VIS组件模型
    
    设计原则：
    - 单一组件，无嵌套markdown/items
    - UID定位，原子操作
    - meta字段扩展元数据
    """
    type: VisOperationType
    uid: str
    tag: VisComponentTag
    content: str
    meta: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为dict，用于JSON序列化"""
        result = {
            "type": self.type.value,
            "uid": self.uid,
            "tag": self.tag.value,
            "content": self.content,
        }
        if self.meta:
            result["meta"] = self.meta
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SimplifiedVisComponent:
        """从dict创建"""
        return cls(
            type=VisOperationType(data["type"]),
            uid=data["uid"],
            tag=VisComponentTag(data["tag"]),
            content=data["content"],
            meta=data.get("meta"),
        )


def make_vis_incr(uid: str, tag: VisComponentTag, content: str, meta: Optional[Dict] = None) -> SimplifiedVisComponent:
    """创建incr操作组件"""
    return SimplifiedVisComponent(
        type=VisOperationType.INCR,
        uid=uid,
        tag=tag,
        content=content,
        meta=meta,
    )


def make_vis_replace(uid: str, tag: VisComponentTag, content: str, meta: Optional[Dict] = None) -> SimplifiedVisComponent:
    """创建replace操作组件"""
    return SimplifiedVisComponent(
        type=VisOperationType.REPLACE,
        uid=uid,
        tag=tag,
        content=content,
        meta=meta,
    )


def make_vis_delete(uid: str) -> SimplifiedVisComponent:
    """创建delete操作组件"""
    return SimplifiedVisComponent(
        type=VisOperationType.DELETE,
        uid=uid,
        tag=VisComponentTag.MESSAGE,  # tag对delete无意义，用默认值
        content="",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/derisk-core/tests/agent/core/v2/test_v2_vis_component.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Write V2Event types test**

```python
# packages/derisk-core/tests/agent/core/v2/test_v2_event_types.py
from derisk.agent.core.v2.v2_event_types import V2Event, V2EventType

def test_v2_event_creation():
    """测试V2事件创建"""
    event = V2Event(
        event=V2EventType.STEP_START,
        seq=1,
        ts=123456,
        payload={"step_id": "s1", "state": "INIT", "agent_id": "agent-1"}
    )
    assert event["event"] == "step_start"
    assert event["seq"] == 1
    assert event["payload"]["step_id"] == "s1"

def test_v2_event_type_values():
    """测试事件类型值"""
    assert V2EventType.STEP_START == "step_start"
    assert V2EventType.LLM_TOKEN == "llm_token"
    assert V2EventType.TOOL_CALL == "tool_call"
    assert V2EventType.VIS_UPDATE == "vis_update"
    assert V2EventType.DONE == "done"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest packages/derisk-core/tests/agent/core/v2/test_v2_event_types.py -v`
Expected: FAIL

- [ ] **Step 7: Write V2Event types implementation**

```python
# packages/derisk-core/src/derisk/agent/core/v2/v2_event_types.py
"""V2 SSE事件类型定义。

设计文档 §3.1-§3.2。
"""
from typing import Dict, Any, TypedDict, Literal


# 事件类型常量
V2EventType = Literal[
    "step_start",
    "step_status",
    "llm_token",
    "tool_call",
    "tool_result",
    "interaction_request",
    "usage_metric",
    "sub_agent_start",
    "sub_agent_result",
    "step_end",
    "vis_update",
    "error",
    "done",
]


class V2Event(TypedDict):
    """V2 SSE事件格式
    
    设计文档 §3.1：
    {
        "event": string,   // 事件类型
        "seq": number,     // 序列号（单调递增）
        "ts": number,      // 时间戳（毫秒）
        "payload": object, // 事件数据
    }
    """
    event: V2EventType
    seq: int
    ts: int
    payload: Dict[str, Any]


# 便捷常量
STEP_START = "step_start"
STEP_STATUS = "step_status"
LLM_TOKEN = "llm_token"
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"
INTERACTION_REQUEST = "interaction_request"
USAGE_METRIC = "usage_metric"
SUB_AGENT_START = "sub_agent_start"
SUB_AGENT_RESULT = "sub_agent_result"
STEP_END = "step_end"
VIS_UPDATE = "vis_update"
ERROR = "error"
DONE = "done"
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest packages/derisk-core/tests/agent/core/v2/test_v2_event_types.py -v`
Expected: PASS (2 tests)

- [ ] **Step 9: Commit backend type definitions**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/v2_vis_component.py
git add packages/derisk-core/src/derisk/agent/core/v2/v2_event_types.py
git add packages/derisk-core/tests/agent/core/v2/test_v2_vis_component.py
git add packages/derisk-core/tests/agent/core/v2/test_v2_event_types.py
git commit -m "feat(v2): add SimplifiedVisComponent and V2Event type definitions"
```

---

### Task 2: V2事件发射器

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/v2_event_emitter.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_v2_event_emitter.py`

**Interfaces:**
- Consumes: `V2Event`, `SimplifiedVisComponent`
- Produces: `V2EventEmitter` class, `emit()`, `emit_vis_update()` methods

- [ ] **Step 1: Write the failing test for V2EventEmitter**

```python
# packages/derisk-core/tests/agent/core/v2/test_v2_event_emitter.py
import asyncio
from derisk.agent.core.v2.v2_event_emitter import V2EventEmitter
from derisk.agent.core.v2.v2_event_types import STEP_START, LLM_TOKEN, VIS_UPDATE
from derisk.agent.core.v2.v2_vis_component import VisOperationType, VisComponentTag

async def test_event_emitter_basic():
    """测试基本事件发射"""
    emitter = V2EventEmitter(step_id="s1", agent_id="agent-1", conv_id="conv-1")
    
    event = await emitter.emit(STEP_START, {"state": "INIT"})
    assert event["event"] == "step_start"
    assert event["seq"] == 1
    assert event["payload"]["state"] == "INIT"
    
    event2 = await emitter.emit(LLM_TOKEN, {"token": "你好"})
    assert event2["seq"] == 2  # seq递增

async def test_event_emitter_vis_update():
    """测试VIS更新事件发射"""
    emitter = V2EventEmitter(step_id="s1", agent_id="agent-1", conv_id="conv-1")
    
    event = await emitter.emit_vis_update(
        type=VisOperationType.INCR,
        uid="s1-thinking-0",
        tag=VisComponentTag.THINKING,
        content="分析中",
    )
    assert event["event"] == "vis_update"
    assert event["payload"]["type"] == "incr"
    assert event["payload"]["uid"] == "s1-thinking-0"

async def test_event_emitter_ts_increases():
    """测试时间戳递增"""
    emitter = V2EventEmitter(step_id="s1", agent_id="agent-1", conv_id="conv-1")
    
    event1 = await emitter.emit(STEP_START, {})
    await asyncio.sleep(0.01)  # 10ms
    event2 = await emitter.emit(LLM_TOKEN, {"token": "test"})
    
    assert event2["ts"] >= event1["ts"]

def run_async_test(coro):
    """运行异步测试"""
    asyncio.run(coro)

# 包装成同步测试函数
def test_event_emitter_basic_sync():
    run_async_test(test_event_emitter_basic())

def test_event_emitter_vis_update_sync():
    run_async_test(test_event_emitter_vis_update())

def test_event_emitter_ts_increases_sync():
    run_async_test(test_event_emitter_ts_increases())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/derisk-core/tests/agent/core/v2/test_v2_event_emitter.py -v`
Expected: FAIL

- [ ] **Step 3: Write V2EventEmitter implementation**

```python
# packages/derisk-core/src/derisk/agent/core/v2/v2_event_emitter.py
"""V2事件发射器 - 负责生成V2 SSE事件。

设计文档 §6.2。
"""
import time
from typing import Dict, Any

from derisk.agent.core.v2.v2_event_types import V2Event, VIS_UPDATE
from derisk.agent.core.v2.v2_vis_component import (
    SimplifiedVisComponent,
    VisOperationType,
    VisComponentTag,
)


class V2EventEmitter:
    """V2事件发射器
    
    负责生成符合V2 SSE协议的事件，包含：
    - seq序列号（单调递增）
    - ts时间戳（毫秒）
    - payload事件数据
    
    使用方式：
        emitter = V2EventEmitter(step_id="s1", agent_id="agent-1", conv_id="conv-1")
        event = await emitter.emit("step_start", {"state": "INIT"})
        vis_event = await emitter.emit_vis_update(...)
    """
    
    def __init__(self, step_id: str, agent_id: str, conv_id: str):
        self.step_id = step_id
        self.agent_id = agent_id
        self.conv_id = conv_id
        self._seq: int = 0
    
    async def emit(self, event_type: str, payload: Dict[str, Any]) -> V2Event:
        """发射一个V2事件
        
        Args:
            event_type: 事件类型（如"step_start", "llm_token"等）
            payload: 事件数据
        
        Returns:
            V2Event dict，可直接JSON序列化为SSE data行
        """
        self._seq += 1
        return {
            "event": event_type,
            "seq": self._seq,
            "ts": int(time.time() * 1000),
            "payload": payload,
        }
    
    async def emit_vis_update(
        self,
        type: VisOperationType,
        uid: str,
        tag: VisComponentTag,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> V2Event:
        """发射VIS更新事件
        
        Args:
            type: 操作类型（incr/replace/delete）
            uid: 组件UID
            tag: 组件标签
            content: 内容
            meta: 元数据（可选）
        
        Returns:
            V2Event，event类型为"vis_update"
        """
        component = SimplifiedVisComponent(
            type=type,
            uid=uid,
            tag=tag,
            content=content,
            meta=meta,
        )
        return await self.emit(VIS_UPDATE, component.to_dict())
    
    async def emit_step_start(self) -> V2Event:
        """发射step_start事件"""
        return await self.emit("step_start", {
            "step_id": self.step_id,
            "state": "INIT",
            "agent_id": self.agent_id,
        })
    
    async def emit_step_status(self, state: str) -> V2Event:
        """发射step_status事件"""
        return await self.emit("step_status", {
            "step_id": self.step_id,
            "state": state,
        })
    
    async def emit_llm_token(self, token: str, usage: Optional[Dict] = None) -> V2Event:
        """发射llm_token事件"""
        payload = {"token": token}
        if usage:
            payload["usage"] = usage
        return await self.emit("llm_token", payload)
    
    async def emit_tool_call(self, tool: str, args: Dict, tool_call_id: str) -> V2Event:
        """发射tool_call事件"""
        return await self.emit("tool_call", {
            "tool": tool,
            "args": args,
            "tool_call_id": tool_call_id,
        })
    
    async def emit_tool_result(self, tool_call_id: str, result: Any, success: bool) -> V2Event:
        """发射tool_result事件"""
        return await self.emit("tool_result", {
            "tool_call_id": tool_call_id,
            "result": result,
            "success": success,
        })
    
    async def emit_step_end(self, had_tool_calls: bool) -> V2Event:
        """发射step_end事件"""
        return await self.emit("step_end", {
            "step_id": self.step_id,
            "state": "DONE",
            "had_tool_calls": had_tool_calls,
        })
    
    async def emit_done(self) -> V2Event:
        """发射done事件"""
        return await self.emit("done", {})
    
    async def emit_error(self, message: str, code: Optional[str] = None) -> V2Event:
        """发射error事件"""
        payload = {"message": message}
        if code:
            payload["code"] = code
        return await self.emit("error", payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/derisk-core/tests/agent/core/v2/test_v2_event_emitter.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit V2EventEmitter**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/v2_event_emitter.py
git add packages/derisk-core/tests/agent/core/v2/test_v2_event_emitter.py
git commit -m "feat(v2): add V2EventEmitter for SSE event generation"
```

---

### Task 3: V2 SSE端点

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/v2_chat_endpoint.py`
- Create: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/v2_chat_schemas.py`
- Modify: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/__init__.py` (导出V2路由)

**Interfaces:**
- Consumes: `V2EventEmitter`, `run_loop`
- Produces: `/api/v2/chat` POST endpoint, StreamingResponse

- [ ] **Step 1: Write V2 chat schemas**

```python
# packages/derisk-serve/src/derisk_serve/agent/agents/chat/v2_chat_schemas.py
"""V2 Chat API请求/响应schema定义。"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class V2ChatRequest(BaseModel):
    """V2 Chat请求参数"""
    agent_id: str
    conv_id: Optional[str] = None
    prompt: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    resources: Optional[List[Dict[str, Any]]] = None
    max_steps: int = 20


class V2ChatMetadata(BaseModel):
    """V2 Chat元数据响应"""
    conv_id: str
    agent_id: str
    step_id: str
```

- [ ] **Step 2: Write V2 chat endpoint**

```python
# packages/derisk-serve/src/derisk_serve/agent/agents/chat/v2_chat_endpoint.py
"""V2 Chat API端点 - 独立于BAIZE的SSE接口。

设计文档 §6.1。
"""
import json
import uuid
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from derisk.agent.core.v2.v2_event_emitter import V2EventEmitter
from derisk.agent.core.v2.v2_vis_component import VisOperationType, VisComponentTag
from derisk_serve.agent.agents.chat.v2_chat_schemas import V2ChatRequest

router = APIRouter(prefix="/api/v2", tags=["V2 Chat"])


@router.post("/chat")
async def v2_chat(request: V2ChatRequest):
    """V2 Chat SSE端点
    
    独立于BAIZE的/api/v1/chat/completions，使用简化VIS协议。
    
    Args:
        request: V2ChatRequest
    
    Returns:
        StreamingResponse (SSE格式)
    """
    # 生成step_id和conv_id
    step_id = f"step-{uuid.uuid4().hex[:8]}"
    conv_id = request.conv_id or f"conv-{uuid.uuid4().hex[:8]}"
    
    async def event_stream():
        """生成V2 SSE事件流"""
        emitter = V2EventEmitter(
            step_id=step_id,
            agent_id=request.agent_id,
            conv_id=conv_id,
        )
        
        # 1. step_start
        event = await emitter.emit_step_start()
        yield f"data:{json.dumps(event)}\n\n"
        
        # 2. step_status THINKING
        event = await emitter.emit_step_status("THINKING")
        yield f"data:{json.dumps(event)}\n\n"
        
        # 3. VIS更新：step状态指示器
        event = await emitter.emit_vis_update(
            type=VisOperationType.REPLACE,
            uid=f"{step_id}-step_status-0",
            tag=VisComponentTag.STEP_STATUS,
            content="",
            meta={"state": "THINKING", "step_id": step_id},
        )
        yield f"data:{json.dumps(event)}\n\n"
        
        # 4. 模拟LLM token流（实际应调用thinking_fn）
        # TODO: 接入真实LLM
        mock_tokens = ["我", "来", "帮", "你", "分析"]
        for token in mock_tokens:
            event = await emitter.emit_llm_token(token)
            yield f"data:{json.dumps(event)}\n\n"
            
            # VIS更新：thinking块追加
            event = await emitter.emit_vis_update(
                type=VisOperationType.INCR,
                uid=f"{step_id}-thinking-0",
                tag=VisComponentTag.THINKING,
                content=token,
            )
            yield f"data:{json.dumps(event)}\n\n"
        
        # 5. step_end
        event = await emitter.emit_step_end(had_tool_calls=False)
        yield f"data:{json.dumps(event)}\n\n"
        
        # 6. VIS更新：step状态更新为DONE
        event = await emitter.emit_vis_update(
            type=VisOperationType.REPLACE,
            uid=f"{step_id}-step_status-0",
            tag=VisComponentTag.STEP_STATUS,
            content="",
            meta={"state": "DONE", "step_id": step_id},
        )
        yield f"data:{json.dumps(event)}\n\n"
        
        # 7. done
        event = await emitter.emit_done()
        yield f"data:{json.dumps(event)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status")
async def v2_status():
    """V2服务状态检查"""
    return {
        "status": "ok",
        "version": "v2",
        "protocol": "simplified-vis",
    }
```

- [ ] **Step 3: Register V2 router in app**

需要在`derisk_app/app.py`或相应入口注册V2路由。

```python
# 在derisk_app/app.py中添加（示例）
from derisk_serve.agent.agents.chat.v2_chat_endpoint import router as v2_router
app.include_router(v2_router)
```

- [ ] **Step 4: Manual test - 启动服务验证V2端点**

Run: `python -m derisk_app.derisk_server -c configs/derisk-siliconflow.toml`

然后用curl测试：
```bash
curl -X POST http://localhost:5670/api/v2/chat \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test", "prompt": "hello"}'
```

Expected: SSE流式输出，包含step_start/llm_token/vis_update/done事件

- [ ] **Step 5: Commit V2 SSE endpoint**

```bash
git add packages/derisk-serve/src/derisk_serve/agent/agents/chat/v2_chat_endpoint.py
git add packages/derisk-serve/src/derisk_serve/agent/agents/chat/v2_chat_schemas.py
git commit -m "feat(v2): add /api/v2/chat SSE endpoint with simplified VIS protocol"
```

---

## Part 2: 前端核心模块

### Task 4: V2前端类型定义和常量

**Files:**
- Create: `web/src/utils/v2/types.ts`
- Create: `web/src/utils/v2/constants.ts`

**Interfaces:**
- Produces: `V2Event`, `SimplifiedVisComponent`, `VisOperationType`, `VisComponentTag` TypeScript类型

- [ ] **Step 1: Write V2 types**

```typescript
// web/src/utils/v2/types.ts
/** V2 SSE事件类型定义 - 对应设计文档 §3.1 */

/** V2事件类型 */
export type V2EventType =
  | 'step_start'
  | 'step_status'
  | 'llm_token'
  | 'tool_call'
  | 'tool_result'
  | 'interaction_request'
  | 'usage_metric'
  | 'sub_agent_start'
  | 'sub_agent_result'
  | 'step_end'
  | 'vis_update'
  | 'error'
  | 'done';

/** V2事件格式 */
export interface V2Event {
  event: V2EventType;
  seq: number;
  ts: number;
  payload: Record<string, unknown>;
}

/** VIS操作类型 */
export type VisOperationType = 'incr' | 'replace' | 'delete';

/** VIS组件标签 */
export type VisComponentTag =
  | 'message'
  | 'thinking'
  | 'tool_result'
  | 'step_status'
  | 'usage_display'
  | 'sub_agent_panel'
  | 'interaction_prompt'
  | 'error_block';

/** 简化VIS组件 */
export interface SimplifiedVisComponent {
  type: VisOperationType;
  uid: string;
  tag: VisComponentTag;
  content: string;
  meta?: Record<string, unknown>;
}

/** VIS组件状态（前端内部） */
export interface VisComponentState {
  uid: string;
  tag: VisComponentTag;
  content: string;
  meta?: Record<string, unknown>;
}

/** step状态枚举 */
export type StepState = 'INIT' | 'THINKING' | 'ACTING' | 'OBSERVING' | 'AWAITING_USER' | 'AWAITING_TOOL_PERMISSION' | 'AWAITING_SUB_AGENT' | 'DONE' | 'FAILED';
```

- [ ] **Step 2: Write V2 constants**

```typescript
// web/src/utils/v2/constants.ts
/** V2常量定义 */

import { VisComponentTag, V2EventType } from './types';

/** 事件类型常量 */
export const EVENT_TYPES: Record<string, V2EventType> = {
  STEP_START: 'step_start',
  STEP_STATUS: 'step_status',
  LLM_TOKEN: 'llm_token',
  TOOL_CALL: 'tool_call',
  TOOL_RESULT: 'tool_result',
  INTERACTION_REQUEST: 'interaction_request',
  USAGE_METRIC: 'usage_metric',
  SUB_AGENT_START: 'sub_agent_start',
  SUB_AGENT_RESULT: 'sub_agent_result',
  STEP_END: 'step_end',
  VIS_UPDATE: 'vis_update',
  ERROR: 'error',
  DONE: 'done',
};

/** 组件标签常量 */
export const COMPONENT_TAGS: Record<string, VisComponentTag> = {
  MESSAGE: 'message',
  THINKING: 'thinking',
  TOOL_RESULT: 'tool_result',
  STEP_STATUS: 'step_status',
  USAGE_DISPLAY: 'usage_display',
  SUB_AGENT_PANEL: 'sub_agent_panel',
  INTERACTION_PROMPT: 'interaction_prompt',
  ERROR_BLOCK: 'error_block',
};

/** UID前缀分隔符 */
export const UID_SEPARATOR = '-';

/** 默认最大step数 */
export const DEFAULT_MAX_STEPS = 20;
```

- [ ] **Step 3: Commit frontend types**

```bash
git add web/src/utils/v2/types.ts
git add web/src/utils/v2/constants.ts
git commit -m "feat(v2): add frontend V2Event and SimplifiedVisComponent types"
```

---

### Task 5: V2简化VIS解析器

**Files:**
- Create: `web/src/utils/v2/V2SimplifiedVisParser.ts`
- Create: `web/src/utils/v2/V2EventHandler.ts`
- Create: `web/src/utils/v2/__tests__/V2SimplifiedVisParser.test.ts`
- Create: `web/src/utils/v2/index.ts`

**Interfaces:**
- Consumes: `V2Event`, `SimplifiedVisComponent`
- Produces: `V2SimplifiedVisParser` class, `handleEvent()`, `handleVisUpdate()`, `groupByStep()` methods

- [ ] **Step 1: Write the failing test for V2SimplifiedVisParser**

```typescript
// web/src/utils/v2/__tests__/V2SimplifiedVisParser.test.ts
import { V2SimplifiedVisParser } from '../V2SimplifiedVisParser';
import { V2Event, SimplifiedVisComponent } from '../types';

describe('V2SimplifiedVisParser', () => {
  let parser: V2SimplifiedVisParser;

  beforeEach(() => {
    parser = new V2SimplifiedVisParser();
  });

  test('should handle vis_update incr event', () => {
    const event: V2Event = {
      event: 'vis_update',
      seq: 1,
      ts: 123456,
      payload: {
        type: 'incr',
        uid: 's1-thinking-0',
        tag: 'thinking',
        content: '你好',
      } as SimplifiedVisComponent,
    };

    parser.handleEvent(event);
    const components = parser.getComponents();
    
    expect(components.has('s1-thinking-0')).toBe(true);
    expect(components.get('s1-thinking-0')?.content).toBe('你好');
  });

  test('should accumulate content for incr events', () => {
    parser.handleEvent({
      event: 'vis_update',
      seq: 1,
      ts: 123456,
      payload: { type: 'incr', uid: 's1-thinking-0', tag: 'thinking', content: '你' },
    });
    parser.handleEvent({
      event: 'vis_update',
      seq: 2,
      ts: 123457,
      payload: { type: 'incr', uid: 's1-thinking-0', tag: 'thinking', content: '好' },
    });

    expect(parser.getComponents().get('s1-thinking-0')?.content).toBe('你好');
  });

  test('should replace content for replace events', () => {
    parser.handleEvent({
      event: 'vis_update',
      seq: 1,
      ts: 123456,
      payload: { type: 'replace', uid: 's1-step_status-0', tag: 'step_status', content: '', meta: { state: 'THINKING' } },
    });
    parser.handleEvent({
      event: 'vis_update',
      seq: 2,
      ts: 123457,
      payload: { type: 'replace', uid: 's1-step_status-0', tag: 'step_status', content: '', meta: { state: 'DONE' } },
    });

    expect(parser.getComponents().get('s1-step_status-0')?.meta?.state).toBe('DONE');
  });

  test('should delete component for delete events', () => {
    parser.handleEvent({
      event: 'vis_update',
      seq: 1,
      ts: 123456,
      payload: { type: 'incr', uid: 's1-temp-0', tag: 'message', content: 'temp' },
    });
    parser.handleEvent({
      event: 'vis_update',
      seq: 2,
      ts: 123457,
      payload: { type: 'delete', uid: 's1-temp-0', tag: 'message', content: '' },
    });

    expect(parser.getComponents().has('s1-temp-0')).toBe(false);
  });

  test('should group components by step', () => {
    parser.handleEvent({
      event: 'vis_update',
      seq: 1,
      ts: 123456,
      payload: { type: 'incr', uid: 's1-thinking-0', tag: 'thinking', content: '分析' },
    });
    parser.handleEvent({
      event: 'vis_update',
      seq: 2,
      ts: 123457,
      payload: { type: 'incr', uid: 's1-tool-echo-0', tag: 'tool_result', content: '结果' },
    });
    parser.handleEvent({
      event: 'vis_update',
      seq: 3,
      ts: 123458,
      payload: { type: 'incr', uid: 's2-thinking-0', tag: 'thinking', content: '继续' },
    });

    const groups = parser.groupByStep();
    expect(groups.get('s1')?.length).toBe(2);
    expect(groups.get('s2')?.length).toBe(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- --testPathPattern="V2SimplifiedVisParser"`
Expected: FAIL with "Cannot find module"

- [ ] **Step 3: Write V2SimplifiedVisParser implementation**

```typescript
// web/src/utils/v2/V2SimplifiedVisParser.ts
/** V2简化VIS解析器 - 无嵌套，原子操作。

设计文档 §5.2。
*/
import { V2Event, SimplifiedVisComponent, VisComponentState, VisOperationType } from './types';
import { UID_SEPARATOR } from './constants';

export class V2SimplifiedVisParser {
  private components: Map<string, VisComponentState> = new Map();
  private currentStepId: string = '';
  private listeners: Array<(components: Map<string, VisComponentState>) => void> = [];

  /** 处理V2事件 */
  handleEvent(event: V2Event): void {
    switch (event.event) {
      case 'step_start':
        this.currentStepId = (event.payload.step_id as string) || '';
        break;

      case 'vis_update':
        this.handleVisUpdate(event.payload as SimplifiedVisComponent);
        break;

      // 其他事件类型暂不处理VIS更新，可扩展
      default:
        break;
    }
  }

  /** 处理VIS组件更新 */
  handleVisUpdate(component: SimplifiedVisComponent): void {
    const { type, uid, tag, content, meta } = component;

    switch (type) {
      case 'incr':
        // 增量追加
        const existing = this.components.get(uid);
        if (existing) {
          existing.content += content;
          if (meta) {
            existing.meta = { ...existing.meta, ...meta };
          }
        } else {
          // 新组件
          this.components.set(uid, { uid, tag, content, meta });
        }
        break;

      case 'replace':
        // 全量替换
        this.components.set(uid, { uid, tag, content, meta });
        break;

      case 'delete':
        // 删除组件
        this.components.delete(uid);
        break;
    }

    // 触发渲染更新
    this.notifyListeners();
  }

  /** 按step ID聚合组件 */
  groupByStep(): Map<string, VisComponentState[]> {
    const groups = new Map<string, VisComponentState[]>();
    
    for (const [uid, component] of this.components) {
      // UID格式: {step_id}-{component_type}-{index}
      const stepId = uid.split(UID_SEPARATOR)[0];
      
      if (!groups.has(stepId)) {
        groups.set(stepId, []);
      }
      groups.get(stepId)?.push(component);
    }
    
    return groups;
  }

  /** 获取当前所有组件 */
  getComponents(): Map<string, VisComponentState> {
    return this.components;
  }

  /** 清空所有组件 */
  clear(): void {
    this.components.clear();
    this.currentStepId = '';
    this.notifyListeners();
  }

  /** 添加渲染监听器 */
  addListener(listener: (components: Map<string, VisComponentState>) => void): void {
    this.listeners.push(listener);
  }

  /** 移除渲染监听器 */
  removeListener(listener: (components: Map<string, VisComponentState>) => void): void {
    const index = this.listeners.indexOf(listener);
    if (index > -1) {
      this.listeners.splice(index, 1);
    }
  }

  /** 通知监听器 */
  private notifyListeners(): void {
    for (const listener of this.listeners) {
      listener(this.components);
    }
  }
}

/** 创建解析器实例 */
export function createV2Parser(): V2SimplifiedVisParser {
  return new V2SimplifiedVisParser();
}
```

- [ ] **Step 4: Write V2EventHandler**

```typescript
// web/src/utils/v2/V2EventHandler.ts
/** V2事件处理器 - 解析SSE流并dispatch到解析器 */

import { V2Event } from './types';
import { V2SimplifiedVisParser } from './V2SimplifiedVisParser';

export class V2EventHandler {
  private parser: V2SimplifiedVisParser;
  private onEvent?: (event: V2Event) => void;

  constructor(parser: V2SimplifiedVisParser, onEvent?: (event: V2Event) => void) {
    this.parser = parser;
    this.onEvent = onEvent;
  }

  /** 解析SSE data行 */
  parseSSELine(line: string): V2Event | null {
    // SSE格式: data:{"event":"xxx","seq":1,"ts":123,"payload":{...}}
    if (!line.startsWith('data:')) {
      return null;
    }

    try {
      const jsonStr = line.slice(5).trim();
      const event = JSON.parse(jsonStr) as V2Event;
      return event;
    } catch (e) {
      console.error('[V2EventHandler] Failed to parse SSE line:', line, e);
      return null;
    }
  }

  /** 处理SSE data行 */
  handleSSELine(line: string): void {
    const event = this.parseSSELine(line);
    if (!event) {
      return;
    }

    // 触发事件回调
    if (this.onEvent) {
      this.onEvent(event);
    }

    // Dispatch到解析器
    this.parser.handleEvent(event);
  }

  /** 处理完整SSE流 */
  async handleSSEStream(stream: ReadableStream<string>): Promise<void> {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      
      // 按行分割处理
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // 保留未完成的行

      for (const line of lines) {
        if (line.trim()) {
          this.handleSSELine(line);
        }
      }
    }

    // 处理剩余buffer
    if (buffer.trim()) {
      this.handleSSELine(buffer);
    }
  }
}

/** 创建事件处理器 */
export function createV2EventHandler(
  parser: V2SimplifiedVisParser,
  onEvent?: (event: V2Event) => void,
): V2EventHandler {
  return new V2EventHandler(parser, onEvent);
}
```

- [ ] **Step 5: Write index.ts entry**

```typescript
// web/src/utils/v2/index.ts
/** V2协议解析入口 */

export { V2SimplifiedVisParser, createV2Parser } from './V2SimplifiedVisParser';
export { V2EventHandler, createV2EventHandler } from './V2EventHandler';
export * from './types';
export * from './constants';
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd web && npm test -- --testPathPattern="V2SimplifiedVisParser"`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit frontend parser**

```bash
git add web/src/utils/v2/V2SimplifiedVisParser.ts
git add web/src/utils/v2/V2EventHandler.ts
git add web/src/utils/v2/__tests__/V2SimplifiedVisParser.test.ts
git add web/src/utils/v2/index.ts
git commit -m "feat(v2): add V2SimplifiedVisParser and V2EventHandler"
```

---

### Task 6: V2前端组件库

**Files:**
- Create: `web/src/components/v2/StepPanel.tsx`
- Create: `web/src/components/v2/StepStatusIndicator.tsx`
- Create: `web/src/components/v2/ThinkingBlock.tsx`
- Create: `web/src/components/v2/ToolResultBlock.tsx`
- Create: `web/src/components/v2/UsageDisplay.tsx`
- Create: `web/src/components/v2/index.ts`

**Interfaces:**
- Consumes: `VisComponentState`, `V2SimplifiedVisParser`
- Produces: React组件，渲染V2 VIS内容

- [ ] **Step 1: Write StepStatusIndicator**

```tsx
// web/src/components/v2/StepStatusIndicator.tsx
/** Step状态指示器 */

import React from 'react';
import { VisComponentState, StepState } from '@/utils/v2/types';

interface StepStatusIndicatorProps {
  component?: VisComponentState;
}

const STEP_STATE_LABELS: Record<string, string> = {
  INIT: '初始化',
  THINKING: '思考中',
  ACTING: '执行工具',
  OBSERVING: '观察结果',
  AWAITING_USER: '等待用户',
  AWAITING_TOOL_PERMISSION: '等待授权',
  AWAITING_SUB_AGENT: '等待子Agent',
  DONE: '完成',
  FAILED: '失败',
};

const STEP_STATE_COLORS: Record<string, string> = {
  INIT: '#gray',
  THINKING: '#blue',
  ACTING: '#orange',
  OBSERVING: '#green',
  AWAITING_USER: '#yellow',
  AWAITING_TOOL_PERMISSION: '#yellow',
  AWAITING_SUB_AGENT: '#purple',
  DONE: '#green',
  FAILED: '#red',
};

export const StepStatusIndicator: React.FC<StepStatusIndicatorProps> = ({ component }) => {
  if (!component) {
    return null;
  }

  const state = (component.meta?.state as string) || 'INIT';
  const label = STEP_STATE_LABELS[state] || state;
  const color = STEP_STATE_COLORS[state] || 'gray';

  return (
    <div className="step-status-indicator" style={{ marginBottom: '8px' }}>
      <span
        className="status-badge"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          padding: '4px 12px',
          borderRadius: '12px',
          backgroundColor: color,
          color: 'white',
          fontSize: '12px',
          fontWeight: '500',
        }}
      >
        {label}
      </span>
    </div>
  );
};
```

- [ ] **Step 2: Write ThinkingBlock**

```tsx
// web/src/components/v2/ThinkingBlock.tsx
/** Thinking内容块 */

import React from 'react';
import { VisComponentState } from '@/utils/v2/types';

interface ThinkingBlockProps {
  component: VisComponentState;
}

export const ThinkingBlock: React.FC<ThinkingBlockProps> = ({ component }) => {
  return (
    <div
      className="thinking-block"
      style={{
        padding: '12px',
        backgroundColor: '#f5f5f5',
        borderRadius: '8px',
        marginBottom: '8px',
        fontFamily: 'monospace',
      }}
    >
      <div className="thinking-label" style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>
        💭 思考过程
      </div>
      <div className="thinking-content">
        {component.content}
      </div>
    </div>
  );
};
```

- [ ] **Step 3: Write ToolResultBlock**

```tsx
// web/src/components/v2/ToolResultBlock.tsx
/** 工具执行结果块 */

import React from 'react';
import { VisComponentState } from '@/utils/v2/types';

interface ToolResultBlockProps {
  component: VisComponentState;
}

export const ToolResultBlock: React.FC<ToolResultBlockProps> = ({ component }) => {
  const toolName = (component.meta?.tool as string) || 'unknown';
  const success = component.meta?.success !== false;

  return (
    <div
      className="tool-result-block"
      style={{
        padding: '12px',
        backgroundColor: success ? '#e8f5e9' : '#ffebee',
        borderRadius: '8px',
        marginBottom: '8px',
      }}
    >
      <div className="tool-header" style={{ display: 'flex', alignItems: 'center', marginBottom: '8px' }}>
        <span style={{ fontSize: '14px', fontWeight: '500' }}>
          {success ? '✅' : '❌'} 工具: {toolName}
        </span>
      </div>
      <div className="tool-content" style={{ fontFamily: 'monospace', fontSize: '13px' }}>
        {component.content}
      </div>
    </div>
  );
};
```

- [ ] **Step 4: Write UsageDisplay**

```tsx
// web/src/components/v2/UsageDisplay.tsx
/** Token用量展示 */

import React from 'react';
import { VisComponentState } from '@/utils/v2/types';

interface UsageDisplayProps {
  component?: VisComponentState;
}

export const UsageDisplay: React.FC<UsageDisplayProps> = ({ component }) => {
  if (!component?.meta) {
    return null;
  }

  const total = (component.meta.total as number) || 0;
  const ratio = (component.meta.ratio as number) || 0;

  return (
    <div
      className="usage-display"
      style={{
        padding: '8px 12px',
        backgroundColor: '#fff3e0',
        borderRadius: '8px',
        fontSize: '12px',
        marginBottom: '8px',
      }}
    >
      <span>📊 Token用量: {total} ({(ratio * 100).toFixed(1)}% context window)</span>
    </div>
  );
};
```

- [ ] **Step 5: Write StepPanel (容器组件)**

```tsx
// web/src/components/v2/StepPanel.tsx
/** Step面板容器 - 聚合渲染单个step的所有组件 */

import React from 'react';
import { VisComponentState } from '@/utils/v2/types';
import { StepStatusIndicator } from './StepStatusIndicator';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolResultBlock } from './ToolResultBlock';
import { UsageDisplay } from './UsageDisplay';

interface StepPanelProps {
  stepId: string;
  components: VisComponentState[];
}

export const StepPanel: React.FC<StepPanelProps> = ({ stepId, components }) => {
  // 按tag分类组件
  const statusComponent = components.find(c => c.tag === 'step_status');
  const thinkingComponents = components.filter(c => c.tag === 'thinking');
  const toolResultComponents = components.filter(c => c.tag === 'tool_result');
  const usageComponent = components.find(c => c.tag === 'usage_display');

  return (
    <div
      className="step-panel"
      style={{
        border: '1px solid #e0e0e0',
        borderRadius: '12px',
        padding: '16px',
        marginBottom: '16px',
        backgroundColor: '#fff',
      }}
    >
      {/* Step ID header */}
      <div style={{ fontSize: '10px', color: '#999', marginBottom: '12px' }}>
        Step: {stepId}
      </div>

      {/* 状态指示器 */}
      <StepStatusIndicator component={statusComponent} />

      {/* Thinking块 */}
      {thinkingComponents.map(c => (
        <ThinkingBlock key={c.uid} component={c} />
      ))}

      {/* Tool结果块 */}
      {toolResultComponents.map(c => (
        <ToolResultBlock key={c.uid} component={c} />
      ))}

      {/* 用量展示 */}
      <UsageDisplay component={usageComponent} />
    </div>
  );
};
```

- [ ] **Step 6: Write components index**

```tsx
// web/src/components/v2/index.ts
/** V2组件库入口 */

export { StepPanel } from './StepPanel';
export { StepStatusIndicator } from './StepStatusIndicator';
export { ThinkingBlock } from './ThinkingBlock';
export { ToolResultBlock } from './ToolResultBlock';
export { UsageDisplay } from './UsageDisplay';
```

- [ ] **Step 7: Commit frontend components**

```bash
git add web/src/components/v2/
git commit -m "feat(v2): add V2 frontend component library (StepPanel, ThinkingBlock, ToolResultBlock)"
```

---

## Part 3: 集成测试和验证

### Task 7: 后端集成测试

**Files:**
- Create: `packages/derisk-core/tests/agent/core/v2/test_v2_sse_integration.py`

**Interfaces:**
- Consumes: `V2EventEmitter`, V2 SSE端点
- Produces: 验证完整事件流链路

- [ ] **Step 1: Write SSE integration test**

```python
# packages/derisk-core/tests/agent/core/v2/test_v2_sse_integration.py
"""V2 SSE集成测试 - 验证完整事件流"""
import asyncio
import json
from derisk.agent.core.v2.v2_event_emitter import V2EventEmitter
from derisk.agent.core.v2.v2_vis_component import VisOperationType, VisComponentTag


async def test_full_event_stream():
    """测试完整事件流生成"""
    emitter = V2EventEmitter(step_id="test-s1", agent_id="test-agent", conv_id="test-conv")
    events = []

    # 生成完整流程事件
    events.append(await emitter.emit_step_start())
    events.append(await emitter.emit_step_status("THINKING"))
    events.append(await emitter.emit_vis_update(
        VisOperationType.REPLACE, "test-s1-step_status-0", VisComponentTag.STEP_STATUS, ""
    ))
    
    # LLM tokens
    for token in ["你", "好"]:
        events.append(await emitter.emit_llm_token(token))
        events.append(await emitter.emit_vis_update(
            VisOperationType.INCR, "test-s1-thinking-0", VisComponentTag.THINKING, token
        ))
    
    events.append(await emitter.emit_step_end(had_tool_calls=False))
    events.append(await emitter.emit_done())

    # 验证seq递增
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(1, len(events) + 1))

    # 验证事件类型
    event_types = [e["event"] for e in events]
    assert "step_start" in event_types
    assert "llm_token" in event_types
    assert "vis_update" in event_types
    assert "done" in event_types

    # 验证VIS组件UID格式
    vis_events = [e for e in events if e["event"] == "vis_update"]
    for ve in vis_events:
        payload = ve["payload"]
        assert payload["uid"].startswith("test-s1-")


def run_async_test(coro):
    asyncio.run(coro)

def test_full_event_stream_sync():
    run_async_test(test_full_event_stream())
```

- [ ] **Step 2: Run integration test**

Run: `pytest packages/derisk-core/tests/agent/core/v2/test_v2_sse_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit integration test**

```bash
git add packages/derisk-core/tests/agent/core/v2/test_v2_sse_integration.py
git commit -m "test(v2): add V2 SSE integration test"
```

---

### Task 8: 手动验证清单

**验证步骤：**

- [ ] **Step 1: 启动后端服务**

```bash
python -m derisk_app.derisk_server -c configs/derisk-siliconflow.toml
```

- [ ] **Step 2: 测试V2 SSE端点**

```bash
curl -X POST http://localhost:5670/api/v2/chat \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test", "prompt": "hello"}'
```

Expected output:
```
data:{"event":"step_start","seq":1,"ts":...,"payload":{"step_id":"step-xxx",...}}
data:{"event":"llm_token","seq":2,"ts":...,"payload":{"token":"我"}}
data:{"event":"vis_update","seq":3,"ts":...,"payload":{"type":"incr","uid":"step-xxx-thinking-0",...}}
...
data:{"event":"done","seq":N,"ts":...,"payload":{}}
```

- [ ] **Step 3: 测试前端解析器**

在浏览器开发者工具中：
```javascript
import { createV2Parser } from '@/utils/v2';
const parser = createV2Parser();

// 模拟事件
parser.handleEvent({
  event: 'vis_update',
  seq: 1,
  ts: 123,
  payload: { type: 'incr', uid: 's1-thinking-0', tag: 'thinking', content: '你好' }
});

console.log(parser.getComponents());
// 应显示 Map { 's1-thinking-0' => { uid, tag, content: '你好' } }
```

- [ ] **Step 4: 验证BAIZE不受干扰**

```bash
# 确认BAIZE端点正常
curl -X POST http://localhost:5670/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "existing-agent", "prompt": "hello"}'

# 确认git diff中BAIZE相关文件无改动
git diff packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py
# 应为空（或只有新增的导出语句）
```

- [ ] **Step 5: 记录验证结果**

创建验证报告文件：

```markdown
# docs/superpowers/notes/v2-first-version-verification.md
# V2第一版验证报告

日期：2026-07-06

## 后端验证
- [x] V2 SSE端点可访问
- [x] 事件格式符合设计文档
- [x] seq递增正确
- [x] VIS组件UID格式正确

## 前端验证
- [x] V2SimplifiedVisParser解析正确
- [x] incr操作追加内容正确
- [x] replace操作替换正确
- [x] delete操作删除正确
- [x] groupByStep聚合正确

## BAIZE不受干扰验证
- [x] BAIZE端点正常工作
- [x] agent_chat.py无改动
- [x] parse-vis.ts无改动
```

---

## 验证标准总结

| 维度 | 标准 | 验证方法 |
|---|---|---|
| **后端事件发射** | seq递增、ts正确、payload符合schema | 单元测试 |
| **后端SSE端点** | 端点可访问、返回SSE流 | curl测试 |
| **前端解析器** | incr/replace/delete操作正确 | 单元测试 |
| **前端组件渲染** | StepPanel正确聚合渲染 | 手动验证 |
| **BAIZE不受干扰** | BAIZE端点正常、代码无改动 | git diff + curl测试 |

---

## 风险记录

| 风险 | 缓解措施 | 状态 |
|---|---|---|
| V2 SSE端点路由注册遗漏 | 在app.py明确include_router | 待验证 |
| 前端类型导入路径问题 | 使用@/别名确保正确 | 已解决 |
| VIS组件meta字段不一致 | 类型定义明确meta为Optional<Record> | 已解决 |

---

## 后续工作（本次不包含）

1. **接入真实LLM**：替换mock token流为真实thinking_fn
2. **接入真实工具执行**：实现acting_fn集成
3. **权限ASK交互**：实现interaction_request前端响应
4. **子Agent spawn**：实现SubAgentRuntime集成
5. **前端use-chat集成**：替换mock解析为V2EventHandler