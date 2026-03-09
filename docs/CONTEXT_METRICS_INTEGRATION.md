# 上下文压缩监控集成指南

## 概述

三层压缩机制的实时监控功能，支持：
- **后端**: 指标收集、日志记录、WebSocket 推送
- **前端**: 实时展示组件

## 三层压缩架构

| Layer | 名称 | 触发时机 | 监控指标 |
|-------|------|----------|----------|
| 1 | Truncation (截断) | 工具输出过大 | 截断次数、字节数、归档文件数 |
| 2 | Pruning (修剪) | 历史消息累积 | 修剪消息数、节省 tokens、触发原因 |
| 3 | Compaction (压缩) | 上下文接近限制 | 归档消息数、章节创建、摘要长度 |

## 后端集成

### 1. 在 Pipeline 中使用

```python
from derisk.agent.core.memory import UnifiedCompactionPipeline, ContextMetricsCollector

# 创建 pipeline 时自动初始化监控
pipeline = UnifiedCompactionPipeline(
    conv_id="conv_123",
    session_id="sess_456",
    agent_file_system=afs,
    config=config,
    notification_callback=your_push_callback,  # 用于推送通知
)

# 设置 WebSocket 推送回调
from derisk.vis.realtime import get_realtime_pusher

pusher = get_realtime_pusher()
if pusher:
    pipeline._metrics_collector.set_push_callback(pusher.push_event)

# 获取指标
metrics = pipeline.get_context_metrics()
print(f"当前使用率: {metrics.usage_ratio:.1%}")
print(f"当前 tokens: {metrics.current_tokens}/{metrics.context_window}")
```

### 2. 更新上下文状态

```python
# 在每次消息处理后更新状态
pipeline.update_metrics_context_state(
    tokens=current_token_count,
    message_count=len(messages),
    round_counter=round_counter,
)
```

### 3. 获取指标数据

```python
# 获取 ContextMetrics 对象
metrics = pipeline.get_context_metrics()

# 获取字典 (用于序列化)
metrics_dict = pipeline.get_context_metrics_dict()

# 获取摘要字符串
summary = metrics.to_summary()
# 输出: [Context Metrics] Tokens: 50000/128000 (39.1%), Messages: 30, Rounds: 10 | L1(Truncate): 2x, L2(Prune): 1x (5 msgs), L3(Compact): 0x (0 chapters)
```

## 前端集成

### 1. 在 Layout 中添加 Provider

```tsx
// src/app/layout.tsx 或对话页面
import { ContextMetricsProvider } from '@/contexts';

export default function ChatLayout({ children }) {
  return (
    <ContextMetricsProvider conv_id={convId}>
      {children}
    </ContextMetricsProvider>
  );
}
```

### 2. 在对话页面使用组件

```tsx
import { ContextMetricsDisplay, useContextMetrics } from '@/components/chat/chat-content-components/ContextMetricsDisplay';

function ChatHeader() {
  const { metrics } = useContextMetrics();
  
  return (
    <div className="flex items-center justify-between">
      <h1>对话</h1>
      <ContextMetricsDisplay metrics={metrics} compact={true} />
    </div>
  );
}
```

### 3. 监听 WebSocket 推送

组件会自动监听 WebSocket 推送的 `context_metrics_update` 事件：

```typescript
// WebSocket 消息格式
{
  "type": "event",
  "event_type": "context_metrics_update",
  "conv_id": "conv_123",
  "timestamp": "2026-03-07T12:00:00",
  "data": {
    "current_tokens": 50000,
    "context_window": 128000,
    "usage_ratio": 0.391,
    "message_count": 30,
    "truncation": { ... },
    "pruning": { ... },
    "compaction": { ... }
  }
}
```

## 日志输出示例

### 后端日志

```
[Layer 1 - Truncation] 工具 'read' 输出截断: 50000B -> 5000B (压缩率 10.0%), file_key=tool_output_read_xxx
[Layer 2 - Pruning] 历史修剪完成: 10 条消息, 节省 2000 tokens, 触发原因: high_usage_75.0%, 使用率: 75.0%
[Layer 3 - Compaction] 会话压缩完成: 归档 50 条消息至章节 1, 节省 10000 tokens, 摘要长度: 500
```

### 前端显示

- **紧凑模式**: 显示使用率进度条、token 数、截断/压缩次数徽章
- **详细模式 (点击展开)**: 
  - 当前状态: 使用率、token 数、消息数、轮次、章节数
  - Layer 1: 截断次数、归档文件数、字节数、最近操作
  - Layer 2: 修剪次数、消息数、节省 tokens、触发原因
  - Layer 3: 压缩次数、归档消息数、章节列表

## 配置项

```python
# 在 UnifiedCompactionConfig 中
config = UnifiedCompactionConfig(
    # Layer 1
    max_output_lines=2000,
    max_output_bytes=50 * 1024,
    
    # Layer 2
    prune_protect_tokens=10000,
    enable_adaptive_pruning=True,
    
    # Layer 3
    context_window=128000,
    compaction_threshold_ratio=0.8,
    recent_messages_keep=5,
)
```

## API 参考

### ContextMetricsCollector

```python
class ContextMetricsCollector:
    def __init__(
        self,
        conv_id: str,
        session_id: str,
        context_window: int = 128000,
        config: Optional[Dict[str, Any]] = None,
        enable_logging: bool = True,
        push_callback: Optional[Callable] = None,
    ): ...
    
    def set_push_callback(self, callback: Callable) -> None: ...
    def update_context_state(self, tokens: int, message_count: int, round_counter: Optional[int] = None) -> None: ...
    def record_truncation(self, tool_name: str, original_bytes: int, truncated_bytes: int, ...) -> None: ...
    def record_pruning(self, messages_pruned: int, tokens_saved: int, trigger_reason: str, usage_ratio: float) -> None: ...
    def record_compaction(self, messages_archived: int, tokens_saved: int, chapter_index: int, ...) -> None: ...
    def get_metrics(self) -> ContextMetrics: ...
    def get_metrics_dict(self) -> Dict[str, Any]: ...
```

### UnifiedCompactionPipeline

```python
class UnifiedCompactionPipeline:
    def get_context_metrics(self) -> ContextMetrics: ...
    def get_context_metrics_dict(self) -> Dict[str, Any]: ...
    def update_metrics_context_state(self, tokens: int, message_count: int, round_counter: Optional[int] = None) -> None: ...
```

## 文件清单

### 后端
- `packages/derisk-core/src/derisk/agent/core/memory/context_metrics.py` - 指标收集器
- `packages/derisk-core/src/derisk/agent/core/memory/compaction_pipeline.py` - Pipeline 集成

### 前端
- `web/src/types/context-metrics.ts` - TypeScript 类型定义
- `web/src/components/chat/chat-content-components/ContextMetricsDisplay.tsx` - 展示组件
- `web/src/contexts/context-metrics-context.tsx` - Context Provider