# RFC-001 · Agent 生命周期 Hook 系统

| 字段 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-06-18 |

---

## 1. 背景与问题

`ReActMasterAgent` 单体 2800+ 行，把 ReAct 思考-行动循环、工具调用前后处理、压缩前后逻辑、错误降级都耦合在主类里。新增"诊断场景在思考前注入历史故障"或"性能场景在工具执行后采集指标"这类能力时，只能改主类——这是继承树过重的核心痛点。

需要一种**外部代码可以订阅 Agent 生命周期、并在受控点修改主流程**的机制。

## 2. v1 已有的事件底座

`agent/core/memory/gpts/system_event.py` 已有一套**正在生产运行**的事件系统：

```python
class SystemEventType(Enum):
    AGENT_BUILD_START / AGENT_BUILD_COMPLETE
    SANDBOX_INIT_START / SANDBOX_INIT_DONE / SANDBOX_INIT_FAILED
    RESOURCE_LOADING / RESOURCE_LOADED / RESOURCE_FAILED
    SUB_AGENT_BUILD_START / SUB_AGENT_BUILD_DONE
    LLM_THINKING
    ACTION_COMPLETE / ACTION_FAILED
    # 共 30+ 事件类型，覆盖 Preparation / Execution / Compression 三阶段

class SystemEventManager:
    def add_event(event_type, ...)        # 发射事件
    def set_event_callback(callback)      # 注册单回调
    def get_events_by_phase(phase)        # 按阶段查询
    def start_event / end_event           # 计时打点
```

`ReActMasterAgent` 已在 ≥ 6 处调用点接入：构建（:3123）、思考（:1774, :1855）、行动完成（:2226-2232）等。

**这是合适的承载者，不需要新建 HookExecutor/HookManager 类**。差距只在两点：

1. **多订阅者**：当前只有单 `event_callback`，不够灵活。
2. **可拦截**：当前回调返回值不被消费、不能影响主流程；缺少"思考前修改 prompt / 工具执行前 veto"这类能力。

## 3. 设计目标与原则

| 原则 | 含义 |
|---|---|
| **复用 SystemEventManager** | 不引入新 hook 框架；现有的事件系统已是合适抽象 |
| **白名单可拦截** | 仅在明确标记的事件上启用 veto/mutate，避免任意 listener 改主流程 |
| **错误隔离** | listener 抛异常不影响主流程；记日志、跳过 |
| **顺序确定** | 多 listener 串行执行，按订阅顺序，结果可复现 |

## 4. 核心机制

### 4.1 多监听器订阅（取代单 callback）

```python
class SystemEventManager:
    _listeners: Dict[SystemEventType, List[EventListener]]

    def subscribe(event_type: SystemEventType, listener: EventListener) -> Unsubscribe
    def subscribe_all(listener: EventListener) -> Unsubscribe
```

- `EventListener = Callable[[SystemEvent], Awaitable[Optional[ListenerResult]]]`
- 默认返回 `None` 表示放行，与现有 `event_callback` 兼容。
- 现有 `set_event_callback` 保留，作为"单 listener 快捷方式"。

### 4.2 可拦截事件（白名单）

```python
class ListenerResult(BaseModel):
    veto: bool = False               # 拦截：终止后续处理
    mutated_payload: Optional[Dict]  # 修改 payload 后传给下一 listener
```

- 仅在标记 `interceptable=True` 的事件上消费 `veto` 与 `mutated_payload`。
- 默认拦截白名单：`LLM_BEFORE_THINKING` / `ACTION_BEFORE_EXECUTE`。
- 其他事件保持纯通知语义——listener 即使返回 `veto=True` 也只记 WARN 日志、不影响主流程。

### 4.3 补全 BEFORE/AFTER 事件类型

现有事件多为 `*_START / *_COMPLETE / *_FAILED`，缺少在动作执行前的可拦截点。新增：

```python
class SystemEventType:
    LLM_BEFORE_THINKING   = "llm_before_thinking"   # interceptable
    LLM_AFTER_THINKING    = "llm_after_thinking"
    ACTION_BEFORE_EXECUTE = "action_before_execute" # interceptable
    ACTION_AFTER_EXECUTE  = "action_after_execute"
```

ReAct 循环在原有 `LLM_THINKING` 打点附近补 4 个新事件。

### 4.4 串行执行与异常隔离

```python
async def _dispatch(event):
    payload = event.payload
    for listener in self._listeners[event.type]:
        try:
            result = await listener(event.with_payload(payload))
            if event.interceptable and result:
                if result.veto:
                    return DispatchResult(vetoed=True, by=listener.__name__)
                if result.mutated_payload:
                    payload = result.mutated_payload
        except Exception as e:
            logger.error(f"listener {listener} raised {e}, skipped")
            continue
    return DispatchResult(payload=payload)
```

## 5. 演进路径

| 步骤 | 改动 | 代码量 | 风险 |
|---|---|---|---|
| **S1** | `SystemEventManager` 增 `subscribe / unsubscribe / subscribe_all`；保留现有 `set_event_callback` 兼容 | ~80 行 | 低 |
| **S2** | 新增 4 个 `BEFORE_*` / `AFTER_*` 事件类型 + ReAct 循环打点 | ~50 行 | 低 |
| **S3** | 引入 `ListenerResult` + 在 2 个 `BEFORE_*` 事件实现 veto/mutate 语义 | ~120 行 | 中（影响主流程，需测试） |
| **S4** | 把现有 `_log_compression` / `_inject_*` 等内联代码改成 listener 形式（演示场景） | ~100 行 | 低 |

**总计**：~350 行新增 + 4 处插桩。不超过 `system_event.py` 当前规模的 30%。

## 6. 不做什么

- **不引入 `HookExecutor` / `HookManager` / `HookRegistry` 新类**——`SystemEventManager` 已是合适的承载者，再造一层只是改名换姓。
- **不做"yaml hook 配置 / 可视化 hook 注册 UI"**——配置驱动是 RFC-004 的事，本 RFC 只造代码层机制。
- **不让所有事件可拦截**——只白名单事件能 veto/mutate。任意事件可改主流程会导致控制流不可预测。
- **不做 listener 优先级排序**——按订阅顺序就够；如果出现需要再补，避免预先复杂化。
- **不做跨进程消息总线**——进程内 listener 即可；分布式 hook 是另一 RFC。
- **不做"链式 hook 转换"**（一个 listener 输出作为下一个的输入）——除了 `mutated_payload`，其他副作用通过 listener 自己访问外部状态来达成。

## 7. 验收标准

| 编号 | 项 | 判定 |
|---|---|---|
| AC-1 | 新增 listener 订阅不破坏现有 `event_callback` 行为 | 现有 callback 测试 100% 通过 |
| AC-2 | 在 `LLM_BEFORE_THINKING` 注册返回 `veto=True` 的 listener，能阻止本次 LLM 调用 | 集成测试 |
| AC-3 | 在 `ACTION_BEFORE_EXECUTE` 注册 listener，能修改 tool args 传给下一 listener | 单测 |
| AC-4 | 多个 listener 注册到同事件，按订阅顺序串行执行 | 单测 |
| AC-5 | listener 抛异常不影响主流程（错误隔离） | 单测 + 日志验证 |
| AC-6 | 在非 `interceptable` 事件返回 `veto=True`，主流程不受影响、记 WARN | 单测 |

## 8. 开放问题

1. listener 是否需要支持优先级 / 排序？建议：v1 不做，按订阅顺序就够；未来出现需要再补。
2. `subscribe_all` 是否会拖慢热路径？评估：每事件 list 长度通常 < 5，O(n) 串行调用可接受；若出现热点再用 typed dispatch 优化。
3. 是否提供"一次性 listener"（fire-once）语法糖？建议：不做内置；listener 内部自取消即可。
