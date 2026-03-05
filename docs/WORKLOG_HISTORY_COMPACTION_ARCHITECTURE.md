# Agent Tool Work Log 框架设计方案 v3.0

> 统一 core (v1) 与 core_v2 架构下的工作日志记录、历史压缩与章节化归档系统

## 1. 概述与目标

### 1.1 问题背景

在长周期的 Agent 会话中，随着交互轮次的增加，历史消息（History）的长度会迅速增长。当历史消息超过大语言模型（LLM）的上下文窗口（Context Window）时，Agent 会丢失关键的上下文信息，导致：

- **决策失误**：Agent 忘记之前的发现和结论，重复执行已完成的操作
- **工具循环**：缺少之前的调用记录，反复调用相同工具
- **上下文溢出**：LLM API 返回错误或静默截断，导致行为不可预测

目前系统在历史压缩和工作日志记录方面存在**碎片化**问题：

| 能力 | Core v1 (ReActMasterAgent) | Core v2 (ReActReasoningAgent) |
|------|---------------------------|-------------------------------|
| 工具输出截断 | Truncator + AgentFileSystem | OutputTruncator（仅临时文件）|
| 历史剪枝 | HistoryPruner（token 预算）| HistoryPruner（类似）|
| 会话压缩 | SessionCompaction（简单 LLM 总结）| ImprovedSessionCompaction（成熟，带内容保护）|
| 工作日志 | WorkLogManager + WorkLogStorage | 无 |
| 文件存储 | AgentFileSystem V3 | 无集成 |
| 历史归档 | 无 | 无 |
| 历史回溯 | 无 | 无 |

### 1.2 设计目标

本方案旨在设计一套**统一的** Agent Tool Work Log 框架，实现以下目标：

1. **统一性**：同时支持 core v1 (`ReActMasterAgent`) 和 core_v2 (`ReActReasoningAgent`) 架构，共用同一套核心逻辑
2. **章节化归档**：引入基于章节（Chapter）的历史归档系统，将压缩后的历史持久化存储至 `AgentFileSystem`
3. **三层压缩管道**：建立从输出截断（Layer 1）、历史剪枝（Layer 2）到会话压缩+归档（Layer 3）的完整处理流程
4. **可回溯性**：提供 Agent 可调用的原生 tool_call 历史回溯工具，使其能够按需检索已归档的上下文
5. **WorkLog 统一**：将 v1 的 WorkLogManager 能力扩展至 v2，统一工具调用记录

### 1.3 核心约束

- 必须兼容现有的 `AgentFileSystem` V3 存储系统（`core/file_system/agent_file_system.py`）
- 必须保留 tool_call 的原子性，避免在压缩过程中拆分 `assistant(tool_calls)` 和 `tool(tool_call_id)` 消息对
- 采用适配器模式处理不同版本的 `AgentMessage` 数据结构，不修改现有基类
- 必须使用原生的 tool_call 机制进行交互（native function calling），而非基于文本解析
- 向后兼容：新系统可选启用，不影响现有功能

---

## 2. 现有架构分析

### 2.1 Core v1 架构 (ReActMasterAgent)

> 源文件：`packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py`

v1 架构拥有较为完善的存储集成，但压缩逻辑相对简单。

#### 2.1.1 数据模型

**AgentMessage** (`core/types.py`，dataclass):

```python
@dataclasses.dataclass
class AgentMessage:
    message_id: str
    content: str
    role: str                           # "user", "assistant", "system", "tool"
    tool_calls: Optional[List[Dict]]    # 原生 tool_call 列表
    context: Dict                       # 上下文信息，也存储 tool_call_id
    action_report: Optional[Dict]       # Action 执行报告
    thinking: Optional[str]             # 思考内容
    observation: Optional[str]          # 观察内容
    rounds: int                         # 轮次编号
    round_id: str                       # 轮次 ID
    metrics: Optional[Dict]             # Token 使用量等指标
    # ... 其他字段
```

关键特性：
- `tool_calls` 是顶层字段，直接存储 LLM 返回的原生工具调用列表
- `context` 字典中也可能包含 `tool_calls`（兼容处理）和 `tool_call_id`
- 包含丰富的元数据如 `rounds`, `round_id`, `metrics`

#### 2.1.2 核心组件

```text
ReActMasterAgent
├── DoomLoopDetector          # 末日循环检测
├── SessionCompaction         # 会话压缩（简单 LLM 总结）
├── HistoryPruner             # 历史剪枝（token 预算）
├── Truncator                 # 输出截断 + AgentFileSystem 存储
├── WorkLogManager            # 工作日志记录与压缩
├── PhaseManager              # 阶段管理
├── ReportGenerator           # 报告生成
├── KanbanManager             # 看板管理（可选）
└── AgentFileSystem           # 统一文件管理（懒加载）
```

#### 2.1.3 工具调用数据流

```text
LLM 返回 response (含 tool_calls)
    │
    ▼
FunctionCallOutputParser.parse_actions()
    │  解析 tool_calls → Action 列表
    ▼
ReActMasterAgent.act()
    │
    ├─ 每个 Action 并行执行 (asyncio.gather)
    │   │
    │   ▼
    │  _run_single_tool_with_protection()
    │   ├── _check_doom_loop(tool_name, args)     → 检测循环
    │   ├── execution_func(**kwargs)               → 实际执行工具
    │   └── _truncate_tool_output(content, tool)   → Layer 1 截断
    │
    ├─ _record_action_to_work_log(tool, args, result)  → WorkEntry
    │
    └─ 结果存入消息历史
```

#### 2.1.4 上下文管理流程

```text
load_thinking_messages(received_message, sender, ...)
    │
    ├── super().load_thinking_messages()  → 获取基础消息列表
    │
    ├── _prune_history(messages)          → Layer 2: 标记旧工具输出
    │   └── HistoryPruner.prune()
    │
    ├── _check_and_compact_context(messages)  → Layer 3: LLM 总结
    │   └── SessionCompaction.compact()
    │
    └── _ensure_agent_file_system()       → 确保 AFS 可用
```

#### 2.1.5 存储层

**WorkLogManager** (`expand/react_master_agent/work_log.py`):
- 记录每个工具调用为 `WorkEntry`
- 支持压缩生成 `WorkLogSummary`
- 优先使用 `WorkLogStorage` 接口，回退到 `AgentFileSystem`

**WorkLogStorage** (接口，`core/memory/gpts/file_base.py`):
```python
class WorkLogStorage(ABC):
    async def append_work_entry(self, conv_id, entry, save_db=True)
    async def get_work_log(self, conv_id) -> List[WorkEntry]
    async def get_work_log_summaries(self, conv_id) -> List[WorkLogSummary]
    async def append_work_log_summary(self, conv_id, summary, save_db=True)
    async def get_work_log_context(self, conv_id, max_entries, max_tokens) -> str
    async def clear_work_log(self, conv_id)
    async def get_work_log_stats(self, conv_id) -> Dict
```

**GptsMemory** (`core/memory/gpts/gpts_memory.py`): 实现了 `WorkLogStorage`，提供缓存+持久化。

**AgentFileSystem** V3 (`core/file_system/agent_file_system.py`):
- 统一文件管理，支持 `FileStorageClient`（本地/OSS/分布式）
- 元数据追踪：通过 `FileMetadataStorage` 记录 `AgentFileMetadata`
- 会话级文件隔离：`agent_storage/<conv_id>/`

### 2.2 Core v2 架构 (ReActReasoningAgent)

> 源文件：`packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_reasoning_agent.py`

v2 架构在压缩策略上更为成熟，但缺乏统一的存储集成。

#### 2.2.1 数据模型

**AgentMessage** (`core_v2/agent_base.py`，Pydantic BaseModel):

```python
class AgentMessage(BaseModel):
    role: str                    # "user", "assistant", "system", "tool"
    content: str                 # 消息内容
    metadata: Dict = {}          # 元数据字典
    timestamp: datetime          # 时间戳
```

关键特性：
- **没有** `tool_calls` 顶层字段，工具调用存储在 `metadata["tool_calls"]` 中
- `tool_call_id` 存储在 `metadata["tool_call_id"]` 中
- 结构更简洁但信息密度依赖 `metadata` 字典的约定

#### 2.2.2 核心组件

```text
ReActReasoningAgent
├── DoomLoopDetector          # 末日循环检测（react_components/）
├── OutputTruncator           # 输出截断（仅临时文件，无 AFS）
├── ContextCompactor          # 简单 token 压缩
├── HistoryPruner             # 历史剪枝
└── (无 WorkLogManager)
└── (无 AgentFileSystem)
```

#### 2.2.3 工具调用数据流

```text
think(message) 
    │  构建消息: self._messages[-20:]
    │  处理 tool 角色: metadata["tool_call_id"]
    │  处理 assistant: metadata["tool_calls"]
    │
    ▼
LLM.generate(messages, tools)
    │  返回 response (含 tool_calls)
    │
    ▼
decide(context)
    │  从 response.tool_calls 构建 Decision(TOOL_CALL)
    │
    ▼
act(decision)
    ├── DoomLoopDetector.record_call(tool_name, args)
    ├── DoomLoopDetector.check_doom_loop()
    ├── execute_tool(tool_name, tool_args)       → 实际执行
    ├── OutputTruncator.truncate(output)          → 截断（无归档）
    └── 结果存入 self._messages (AgentMessage with metadata)
```

#### 2.2.4 ImprovedSessionCompaction（最成熟实现）

> 源文件：`packages/derisk-core/src/derisk/agent/core_v2/improved_compaction.py` (928 行)

这是目前系统中最完善的压缩实现，特性包括：

**内容保护 (ContentProtector)**:
- 代码块保护 (`CODE_BLOCK_PROTECTION`)
- 思维链保护 (`THINKING_CHAIN_PROTECTION`)
- 文件路径保护 (`FILE_PATH_PROTECTION`)

**关键信息提取 (KeyInfoExtractor)**:
- 自动提取关键信息并评估重要性分数
- 在压缩总结中优先保留高重要性信息

**工具调用原子组保护** (`_select_messages_to_compact()`):
```python
# 核心逻辑：避免在 assistant(tool_calls) + tool(tool_call_id) 组内拆分
while split_idx > 0:
    msg = messages[split_idx]
    role = msg.role or ""
    is_tool_msg = role == "tool"
    is_tool_assistant = (
        role == "assistant"
        and hasattr(msg, 'tool_calls') and msg.tool_calls
    )
    if not is_tool_assistant:
        ctx = getattr(msg, 'context', None)
        if isinstance(ctx, dict) and ctx.get('tool_calls'):
            is_tool_assistant = True
    if is_tool_msg or is_tool_assistant:
        split_idx -= 1
    else:
        break
```

**消息格式化** (`_format_messages_for_summary()`):
- 将 tool_calls 展平为可读文本用于总结
- 同时兼容 `msg.tool_calls` 和 `msg.context.get('tool_calls')` 两种格式

**自适应触发**:
- 基于增长速率的自适应检测 (`should_compact_adaptive()`)
- 当 token 增长率超过阈值时提前触发压缩

**共享记忆重载**:
- 支持 Claude Code 风格的共享记忆重载机制
- 压缩后可从外部加载额外上下文

### 2.3 共享存储层

#### FileType 枚举 (`core/memory/gpts/file_base.py`)

```python
class FileType(enum.Enum):
    TOOL_OUTPUT = "tool_output"           # 工具结果临时文件
    WRITE_FILE = "write_file"             # write 工具写入
    SANDBOX_FILE = "sandbox_file"         # 沙箱文件
    CONCLUSION = "conclusion"             # 结论文件
    KANBAN = "kanban"                     # 看板文件
    DELIVERABLE = "deliverable"           # 交付物
    TRUNCATED_OUTPUT = "truncated_output" # 截断输出
    WORKFLOW = "workflow"                 # 工作流
    KNOWLEDGE = "knowledge"              # 知识库
    TEMP = "temp"                        # 临时文件
    WORK_LOG = "work_log"                # 工作日志
    WORK_LOG_SUMMARY = "work_log_summary"# 工作日志摘要
    TODO = "todo"                        # 任务列表
```

#### WorkEntry 与 WorkLogSummary (`core/memory/gpts/file_base.py`)

```python
@dataclass
class WorkEntry:
    timestamp: float
    tool: str
    args: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    result: Optional[str] = None
    full_result_archive: Optional[str] = None   # AFS file_key
    archives: Optional[List[str]] = None        # 归档文件列表
    success: bool = True
    tags: List[str] = field(default_factory=list)
    tokens: int = 0
    status: str = WorkLogStatus.ACTIVE.value    # active/compressed/archived
    step_index: int = 0

@dataclass
class WorkLogSummary:
    compressed_entries_count: int
    time_range: Tuple[float, float]
    summary_content: str
    key_tools: List[str]
    archive_file: Optional[str] = None          # AFS file_key
    created_at: float
```

### 2.4 差异对比总结

| 维度 | Core v1 | Core v2 | 统一方案策略 |
|------|---------|---------|-------------|
| AgentMessage 类型 | dataclass | Pydantic BaseModel | UnifiedMessageAdapter 适配 |
| tool_calls 位置 | `msg.tool_calls` 或 `msg.context["tool_calls"]` | `msg.metadata["tool_calls"]` | 适配器统一提取 |
| tool_call_id 位置 | `msg.context["tool_call_id"]` | `msg.metadata["tool_call_id"]` | 适配器统一提取 |
| 截断 + 存储 | Truncator + AgentFileSystem | OutputTruncator + 临时文件 | 统一使用 AFS |
| 压缩质量 | 简单 LLM 总结 | 带内容保护的成熟总结 | 采用 v2 的 ImprovedSessionCompaction |
| WorkLog | WorkLogManager + WorkLogStorage | 无 | 统一引入 WorkLogManager |
| 文件管理 | AgentFileSystem V3 | 无 | 统一引入 AFS |
| 历史归档 | 无 | 无 | 新增章节化归档 |
| 历史回溯 | 无 | 无 | 新增回溯工具 |

---

## 3. 统一设计方案

### 3.1 统一消息适配层 (UnifiedMessageAdapter)

> 建议文件位置：`packages/derisk-core/src/derisk/agent/core/memory/message_adapter.py`

为消除 v1 和 v2 在消息结构上的差异，设计一个静态适配器类。该适配器不修改任何现有的 `AgentMessage` 类，仅提供统一的读取接口。

```python
from typing import Any, Dict, List, Optional
from datetime import datetime


class UnifiedMessageAdapter:
    """
    适配 v1 和 v2 的 AgentMessage 到统一读取接口。
    
    v1 AgentMessage (dataclass):
        - tool_calls: Optional[List[Dict]]          # 顶层字段
        - context: Dict                              # 含 tool_call_id, tool_calls
        - role, content, message_id, rounds, ...
    
    v2 AgentMessage (Pydantic BaseModel):
        - metadata: Dict                             # 含 tool_calls, tool_call_id
        - role, content, timestamp
    """
    
    @staticmethod
    def get_tool_calls(msg: Any) -> Optional[List[Dict]]:
        """从 v1 或 v2 消息中提取 tool_calls"""
        # v1 直接字段
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            return msg.tool_calls
        # v2 metadata
        if hasattr(msg, "metadata") and isinstance(msg.metadata, dict):
            tc = msg.metadata.get("tool_calls")
            if tc:
                return tc
        # v1 context 兼容
        if hasattr(msg, "context") and isinstance(msg.context, dict):
            tc = msg.context.get("tool_calls")
            if tc:
                return tc
        return None

    @staticmethod
    def get_tool_call_id(msg: Any) -> Optional[str]:
        """提取 tool_call_id"""
        # v2 metadata
        if hasattr(msg, "metadata") and isinstance(msg.metadata, dict):
            tcid = msg.metadata.get("tool_call_id")
            if tcid:
                return tcid
        # v1 context
        if hasattr(msg, "context") and isinstance(msg.context, dict):
            tcid = msg.context.get("tool_call_id")
            if tcid:
                return tcid
        # 直接属性
        return getattr(msg, "tool_call_id", None)

    @staticmethod
    def get_role(msg: Any) -> str:
        return getattr(msg, "role", "") or "unknown"

    @staticmethod
    def get_content(msg: Any) -> str:
        return getattr(msg, "content", "") or ""

    @staticmethod
    def get_timestamp(msg: Any) -> float:
        """获取时间戳（统一为 float epoch）"""
        # v2: datetime
        ts = getattr(msg, "timestamp", None)
        if isinstance(ts, datetime):
            return ts.timestamp()
        if isinstance(ts, (int, float)):
            return float(ts)
        # v1: gmt_create
        gmt = getattr(msg, "gmt_create", None)
        if isinstance(gmt, datetime):
            return gmt.timestamp()
        return 0.0

    @staticmethod
    def get_message_id(msg: Any) -> Optional[str]:
        """获取消息 ID"""
        return getattr(msg, "message_id", None)

    @staticmethod
    def get_round_id(msg: Any) -> Optional[str]:
        """获取轮次 ID（v1 专有，v2 返回 None）"""
        return getattr(msg, "round_id", None)

    @staticmethod
    def is_tool_call_message(msg: Any) -> bool:
        """判断是否是包含 tool_calls 的 assistant 消息"""
        role = UnifiedMessageAdapter.get_role(msg)
        if role != "assistant":
            return False
        return UnifiedMessageAdapter.get_tool_calls(msg) is not None

    @staticmethod
    def is_tool_result_message(msg: Any) -> bool:
        """判断是否是 tool 结果消息"""
        role = UnifiedMessageAdapter.get_role(msg)
        return role == "tool"

    @staticmethod
    def is_in_tool_call_group(msg: Any) -> bool:
        """判断消息是否属于工具调用原子组"""
        return (
            UnifiedMessageAdapter.is_tool_call_message(msg) 
            or UnifiedMessageAdapter.is_tool_result_message(msg)
        )

    @staticmethod
    def get_token_estimate(msg: Any) -> int:
        """估算消息的 token 数"""
        content = UnifiedMessageAdapter.get_content(msg)
        tool_calls = UnifiedMessageAdapter.get_tool_calls(msg)
        tokens = len(content) // 4
        if tool_calls:
            import json
            tokens += len(json.dumps(tool_calls, ensure_ascii=False)) // 4
        return tokens

    @staticmethod
    def serialize_message(msg: Any) -> Dict:
        """将消息序列化为可存储的字典格式"""
        return {
            "role": UnifiedMessageAdapter.get_role(msg),
            "content": UnifiedMessageAdapter.get_content(msg),
            "tool_calls": UnifiedMessageAdapter.get_tool_calls(msg),
            "tool_call_id": UnifiedMessageAdapter.get_tool_call_id(msg),
            "timestamp": UnifiedMessageAdapter.get_timestamp(msg),
            "message_id": UnifiedMessageAdapter.get_message_id(msg),
            "round_id": UnifiedMessageAdapter.get_round_id(msg),
        }
```

### 3.2 章节化历史归档系统 (Chapter-Based History Archival)

> 建议文件位置：`packages/derisk-core/src/derisk/agent/core/memory/history_archive.py`

引入章节概念，将长期的历史划分为多个可检索的片段。每个章节是一次完整的归档操作产出。

#### 3.2.1 新增 FileType 枚举

在 `core/memory/gpts/file_base.py` 的 `FileType` 中新增：

```python
class FileType(enum.Enum):
    # ... 现有类型 ...
    HISTORY_CHAPTER = "history_chapter"       # 章节原始消息归档
    HISTORY_CATALOG = "history_catalog"       # 会话章节索引目录
    HISTORY_SUMMARY = "history_summary"       # 章节总结文件
```

#### 3.2.2 数据模型

```python
import dataclasses
from typing import Dict, List, Optional, Tuple, Any


@dataclasses.dataclass
class HistoryChapter:
    """
    历史章节 — 一次归档操作的产物。
    
    包含该章节的元信息和指向 AgentFileSystem 中原始消息文件的引用。
    """
    chapter_id: str                          # 唯一标识
    chapter_index: int                       # 顺序索引（从 0 开始）
    time_range: Tuple[float, float]          # (start_timestamp, end_timestamp)
    message_count: int                       # 归档的消息数量
    tool_call_count: int                     # 包含的工具调用次数
    summary: str                             # LLM 生成的章节总结
    key_tools: List[str]                     # 关键工具列表
    key_decisions: List[str]                 # 关键决策/发现列表
    file_key: str                            # AgentFileSystem 中的归档文件 key
    token_estimate: int                      # 原始消息的估算 token 数
    created_at: float                        # 归档时间戳

    # 可选：WorkLog 关联
    work_log_summary_id: Optional[str] = None  # 关联的 WorkLogSummary
    
    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "HistoryChapter":
        return cls(**data)

    def to_catalog_entry(self) -> str:
        """生成用于目录展示的简要描述"""
        import time
        start = time.strftime("%H:%M:%S", time.localtime(self.time_range[0]))
        end = time.strftime("%H:%M:%S", time.localtime(self.time_range[1]))
        tools_str = ", ".join(self.key_tools[:5])
        return (
            f"Chapter {self.chapter_index}: [{start} - {end}] "
            f"{self.message_count} msgs, {self.tool_call_count} tool calls | "
            f"Tools: {tools_str}\n"
            f"Summary: {self.summary[:200]}"
        )


@dataclasses.dataclass
class HistoryCatalog:
    """
    历史目录 — 管理一个会话中所有章节的索引。
    
    持久化存储在 AgentFileSystem 中，类型为 HISTORY_CATALOG。
    """
    conv_id: str
    session_id: str
    chapters: List[HistoryChapter] = dataclasses.field(default_factory=list)
    total_messages: int = 0
    total_tool_calls: int = 0
    current_chapter_index: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0

    def add_chapter(self, chapter: HistoryChapter) -> None:
        """添加新章节"""
        self.chapters.append(chapter)
        self.total_messages += chapter.message_count
        self.total_tool_calls += chapter.tool_call_count
        self.current_chapter_index = chapter.chapter_index + 1
        self.updated_at = chapter.created_at

    def get_chapter(self, index: int) -> Optional[HistoryChapter]:
        """按索引获取章节"""
        for ch in self.chapters:
            if ch.chapter_index == index:
                return ch
        return None

    def get_overview(self) -> str:
        """生成目录概览文本"""
        lines = [
            f"=== History Catalog ===",
            f"Session: {self.session_id}",
            f"Total: {self.total_messages} messages, "
            f"{self.total_tool_calls} tool calls, "
            f"{len(self.chapters)} chapters",
            f"",
        ]
        for ch in self.chapters:
            lines.append(ch.to_catalog_entry())
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conv_id": self.conv_id,
            "session_id": self.session_id,
            "chapters": [ch.to_dict() for ch in self.chapters],
            "total_messages": self.total_messages,
            "total_tool_calls": self.total_tool_calls,
            "current_chapter_index": self.current_chapter_index,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "HistoryCatalog":
        chapters_data = data.pop("chapters", [])
        catalog = cls(**data)
        catalog.chapters = [HistoryChapter.from_dict(ch) for ch in chapters_data]
        return catalog
```

### 3.3 三层压缩管道 (Three-Layer Compression Pipeline)

> 建议文件位置：`packages/derisk-core/src/derisk/agent/core/memory/compaction_pipeline.py`

#### 3.3.1 整体架构

```text
┌─────────────────────────────────────────────────────────────────────┐
│                   UnifiedCompactionPipeline                         │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Layer 1: TruncationLayer (每次工具调用后触发)                  │  │
│  │  - 检查 output 大小 > max_output_bytes / max_output_lines    │  │
│  │  - 截断并将全文保存至 AgentFileSystem                         │  │
│  │  - 返回截断后的文本 + file_key 引用                           │  │
│  │  - 同时创建 WorkEntry 记录                                    │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                           │                                         │
│                           ▼                                         │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Layer 2: PruningLayer (每 N 轮检查一次)                       │  │
│  │  - 扫描历史消息，标记旧的 tool output 为 [已压缩]             │  │
│  │  - 保护最近 M 条消息和所有 tool-call 原子组                   │  │
│  │  - 对被标记的消息创建简短摘要替代原始内容                     │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                           │                                         │
│                           ▼                                         │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Layer 3: CompactionLayer (Token 接近上限时触发)               │  │
│  │  - 基于 ImprovedSessionCompaction 核心逻辑                    │  │
│  │  - 选择待压缩消息范围（尊重原子组边界）                       │  │
│  │  - 调用 LLM 生成章节总结（带内容保护和关键信息提取）         │  │
│  │  - 将原始消息序列化 → AgentFileSystem (HISTORY_CHAPTER)       │  │
│  │  - 创建 HistoryChapter → 更新 HistoryCatalog                  │  │
│  │  - 在内存中用总结消息替换原始消息                             │  │
│  │  - 创建 WorkLogSummary 记录                                   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  依赖：UnifiedMessageAdapter, AgentFileSystem, WorkLogStorage       │
└─────────────────────────────────────────────────────────────────────┘
```

#### 3.3.2 Pipeline 核心接口

```python
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class TruncationResult:
    """Layer 1 输出"""
    content: str                              # 截断后的内容
    is_truncated: bool = False                # 是否进行了截断
    original_size: int = 0                    # 原始大小（字节）
    truncated_size: int = 0                   # 截断后大小
    file_key: Optional[str] = None            # AFS 中的全文引用
    suggestion: Optional[str] = None          # 给 Agent 的建议


@dataclass
class PruningResult:
    """Layer 2 输出"""
    messages: List[Any]                       # 处理后的消息列表
    pruned_count: int = 0                     # 被剪枝的消息数
    tokens_saved: int = 0                     # 节省的 token 估算


@dataclass
class CompactionResult:
    """Layer 3 输出"""
    messages: List[Any]                       # 处理后的消息列表（已压缩）
    chapter: Optional["HistoryChapter"] = None  # 新创建的章节
    summary_content: Optional[str] = None     # 生成的总结
    messages_archived: int = 0                # 归档的消息数
    tokens_saved: int = 0                     # 节省的 token 估算
    compaction_triggered: bool = False        # 是否触发了压缩


class UnifiedCompactionPipeline:
    """
    统一三层压缩管道。
    
    在 v1 和 v2 架构中共用同一套核心逻辑，
    通过 UnifiedMessageAdapter 抹平消息结构差异。
    """
    
    def __init__(
        self,
        conv_id: str,
        session_id: str,
        agent_file_system: "AgentFileSystem",
        work_log_storage: Optional["WorkLogStorage"] = None,
        llm_client: Optional[Any] = None,
        config: Optional["HistoryCompactionConfig"] = None,
    ):
        self.conv_id = conv_id
        self.session_id = session_id
        self.afs = agent_file_system
        self.work_log_storage = work_log_storage
        self.llm_client = llm_client
        self.config = config or HistoryCompactionConfig()
        
        # 内部状态
        self._catalog: Optional[HistoryCatalog] = None
        self._round_counter: int = 0
        self._adapter = UnifiedMessageAdapter
    
    # ==================== Layer 1: Truncation ====================
    
    async def truncate_output(
        self,
        output: str,
        tool_name: str,
        tool_args: Optional[Dict] = None,
    ) -> TruncationResult:
        """
        Layer 1: 截断大型工具输出。
        
        每次工具执行后调用。如果输出超过阈值，
        截断并将全文存入 AgentFileSystem。
        
        Args:
            output: 工具原始输出
            tool_name: 工具名称
            tool_args: 工具参数（用于 WorkEntry 记录）
        
        Returns:
            TruncationResult 包含截断后的内容和 AFS 引用
        """
        ...
    
    # ==================== Layer 2: Pruning ====================
    
    async def prune_history(
        self,
        messages: List[Any],
    ) -> PruningResult:
        """
        Layer 2: 剪枝历史中旧的工具输出。
        
        每 N 轮（config.prune_interval_rounds）检查一次。
        从后向前扫描，保护最近的消息和工具调用原子组，
        将超出 token 预算的旧工具输出替换为简短摘要。
        
        Args:
            messages: 当前消息列表（v1 或 v2 格式）
        
        Returns:
            PruningResult 包含处理后的消息列表
        """
        ...
    
    # ==================== Layer 3: Compaction & Archival ====================
    
    async def compact_if_needed(
        self,
        messages: List[Any],
        force: bool = False,
    ) -> CompactionResult:
        """
        Layer 3: 检查是否需要压缩，如需要则执行章节归档。
        
        当估算 token 超过 context_window * threshold_ratio 时触发。
        
        流程：
        1. 估算当前消息总 token
        2. 如未超过阈值且 force=False，直接返回
        3. 使用 _select_messages_to_compact() 划分压缩范围
        4. 调用 LLM 生成章节总结（带内容保护）
        5. 将原始消息序列化并存入 AgentFileSystem
        6. 创建 HistoryChapter 并更新 HistoryCatalog
        7. 在消息列表中用总结消息替换被压缩的部分
        8. 如有 WorkLogStorage，创建 WorkLogSummary
        
        Args:
            messages: 当前消息列表
            force: 是否强制压缩（忽略阈值）
        
        Returns:
            CompactionResult
        """
        ...
    
    # ==================== Catalog Management ====================
    
    async def get_catalog(self) -> HistoryCatalog:
        """获取当前会话的历史目录（从 AFS 加载或创建新的）"""
        ...
    
    async def save_catalog(self) -> None:
        """将历史目录持久化到 AgentFileSystem"""
        ...
    
    # ==================== Chapter Recovery ====================
    
    async def read_chapter(self, chapter_index: int) -> Optional[str]:
        """
        读取指定章节的完整归档内容。
        
        从 AgentFileSystem 加载原始消息文件，
        格式化为可阅读的文本返回给 Agent。
        """
        ...
    
    async def search_chapters(
        self, 
        query: str, 
        max_results: int = 10,
    ) -> str:
        """
        在所有章节总结和关键信息中搜索。
        
        搜索范围包括：
        - 各章节的 summary
        - 各章节的 key_decisions
        - 各章节的 key_tools
        """
        ...
    
    # ==================== Internal Methods ====================
    
    def _estimate_tokens(self, messages: List[Any]) -> int:
        """估算消息列表的总 token 数"""
        ...
    
    def _select_messages_to_compact(
        self,
        messages: List[Any],
    ) -> Tuple[List[Any], List[Any]]:
        """
        选择待压缩的消息范围。
        
        核心逻辑继承自 ImprovedSessionCompaction._select_messages_to_compact()：
        - 保留最近 recent_messages_keep 条消息
        - 从分割点向前回退，确保不拆分 tool-call 原子组
        
        Returns:
            (to_compact, to_keep) 两个消息列表
        """
        ...
    
    async def _generate_chapter_summary(
        self,
        messages: List[Any],
    ) -> Tuple[str, List[str], List[str]]:
        """
        生成章节总结。
        
        继承 ImprovedSessionCompaction._generate_summary() 的内容保护逻辑，
        额外提取 key_tools 和 key_decisions。
        
        Returns:
            (summary, key_tools, key_decisions)
        """
        ...
    
    async def _archive_messages_to_chapter(
        self,
        messages: List[Any],
        summary: str,
        key_tools: List[str],
        key_decisions: List[str],
    ) -> HistoryChapter:
        """
        将消息归档为章节文件。
        
        1. 序列化消息为 JSON
        2. 存入 AgentFileSystem（file_type=HISTORY_CHAPTER）
        3. 创建 HistoryChapter 记录
        4. 更新 HistoryCatalog
        """
        ...
    
    def _create_summary_message(
        self,
        summary: str,
        chapter: HistoryChapter,
    ) -> Dict:
        """
        创建替换原始消息的总结消息。
        
        返回一个字典，调用方根据架构版本转换为对应的 AgentMessage。
        包含章节引用信息，便于 Agent 理解上下文来源。
        """
        ...
```

#### 3.3.3 Layer 1 详细设计

**触发时机**：每次工具调用完成后立即执行。

**处理逻辑**：
```text
输入: output (str), tool_name (str)
    │
    ├── 计算 output 大小 (行数 + 字节数)
    │
    ├── 如果 未超过阈值:
    │   └── 返回原始 output, is_truncated=False
    │
    ├── 如果 超过阈值:
    │   ├── 将完整 output 存入 AgentFileSystem
    │   │   file_type = FileType.TRUNCATED_OUTPUT
    │   │   返回 file_key
    │   │
    │   ├── 截断 output 至 max_lines / max_bytes
    │   │
    │   ├── 在截断处附加建议:
    │   │   "[输出已截断] 原始 {lines} 行 ({bytes} 字节)
    │   │    完整输出已归档: file_key={file_key}
    │   │    使用 read_history_chapter 或 read_file 获取完整内容"
    │   │
    │   └── 返回 TruncationResult
    │
    └── 创建 WorkEntry (如有 WorkLogStorage):
        tool=tool_name, args=tool_args
        result=truncated_content
        full_result_archive=file_key (如果截断)
```

**v1 集成点**：替换 `ReActMasterAgent._truncate_tool_output()` 中的逻辑，已有 AFS 支持。

**v2 集成点**：替换 `ReActReasoningAgent.act()` 中的 `OutputTruncator.truncate()` 逻辑，新增 AFS 支持。

#### 3.3.4 Layer 2 详细设计

**触发时机**：每 `config.prune_interval_rounds` 轮检查一次，在构建 LLM 请求消息前执行。

**处理逻辑**：
```text
输入: messages (List[AgentMessage])
    │
    ├── 从后向前遍历消息
    │
    ├── 累计 token 预算: 当 cumulative_tokens > prune_protect_tokens 时
    │   开始标记更早的工具输出消息
    │
    ├── 对于每条被标记的工具输出消息:
    │   ├── 检查是否属于 tool-call 原子组
    │   │   ├── 是: 保留完整原子组（assistant + 所有 tool response）
    │   │   └── 否: 可以安全剪枝
    │   │
    │   ├── 将消息内容替换为简短摘要:
    │   │   "[工具输出已剪枝] {tool_name}: {first_100_chars}..."
    │   │
    │   └── 如果原始内容已有 AFS 引用, 保留引用
    │
    └── 返回 PruningResult
```

**关键约束**：
- 永远不剪枝 `system` 和 `user` 消息
- 保护最近 `recent_messages_keep` 条消息
- 保护完整的 tool-call 原子组（使用 `UnifiedMessageAdapter.is_in_tool_call_group()`）

#### 3.3.5 Layer 3 详细设计

**触发时机**：Layer 2 之后，当估算 token > `context_window * compaction_threshold_ratio` 时触发。

**处理逻辑**：
```text
输入: messages (List[AgentMessage])
    │
    ├── _estimate_tokens(messages) → total_tokens
    │
    ├── 如果 total_tokens < threshold 且 force=False:
    │   └── 返回原始 messages, compaction_triggered=False
    │
    ├── _select_messages_to_compact(messages) 
    │   → (to_compact, to_keep)
    │   注意: 尊重 tool-call 原子组边界
    │
    ├── _generate_chapter_summary(to_compact)
    │   → (summary, key_tools, key_decisions)
    │   使用 ImprovedSessionCompaction 的核心逻辑:
    │   - ContentProtector 保护代码块、思维链、文件路径
    │   - KeyInfoExtractor 提取关键信息
    │   - 通过 LLM 生成结构化总结
    │
    ├── _archive_messages_to_chapter(to_compact, summary, ...)
    │   ├── 序列化 to_compact → JSON
    │   ├── AgentFileSystem.save_file(
    │   │     content=json, file_type=HISTORY_CHAPTER,
    │   │     file_name=f"chapter_{index}.json"
    │   │   )
    │   ├── 创建 HistoryChapter 记录
    │   ├── HistoryCatalog.add_chapter(chapter)
    │   └── save_catalog() → 持久化目录
    │
    ├── _create_summary_message(summary, chapter)
    │   → summary_msg (Dict)
    │   内容格式:
    │   "[History Compaction] Chapter {index} archived.
    │    {summary}
    │    Archived {msg_count} messages ({tool_count} tool calls).
    │    Use get_history_overview() or read_history_chapter({index})
    │    to access archived content."
    │
    ├── 构建新消息列表: [summary_msg] + to_keep
    │
    ├── 如有 WorkLogStorage:
    │   创建 WorkLogSummary 记录
    │
    └── 返回 CompactionResult
```

### 3.4 历史回溯工具 (History Recovery Tools)

> 建议文件位置：`packages/derisk-core/src/derisk/agent/core/tools/history_tools.py`

为 Agent 提供原生的 tool_call 工具，使其能主动检索已归档的历史。

#### 3.4.1 工具定义

```python
from derisk.agent.resource import FunctionTool


def create_history_tools(pipeline: "UnifiedCompactionPipeline") -> Dict[str, FunctionTool]:
    """创建历史回溯工具集合"""
    
    async def read_history_chapter(chapter_index: int) -> str:
        """
        读取指定历史章节的完整归档内容。
        
        当你需要回顾之前的操作细节或找回之前的发现时使用此工具。
        章节索引从 0 开始，可通过 get_history_overview 获取所有章节列表。
        
        Args:
            chapter_index: 章节索引号 (从 0 开始)
        
        Returns:
            章节的完整归档内容，包括所有消息和工具调用结果
        """
        return await pipeline.read_chapter(chapter_index)
    
    async def search_history(query: str, max_results: int = 10) -> str:
        """
        在所有已归档的历史章节中搜索信息。
        
        搜索范围包括章节总结、关键决策和工具调用记录。
        当你需要查找之前讨论过的特定主题或做出的决定时使用此工具。
        
        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
        
        Returns:
            匹配的历史记录，包含章节引用
        """
        return await pipeline.search_chapters(query, max_results)
    
    async def get_tool_call_history(
        tool_name: str = "", 
        limit: int = 20,
    ) -> str:
        """
        获取工具调用历史记录。
        
        从 WorkLog 中检索工具调用记录。可按工具名称过滤。
        
        Args:
            tool_name: 工具名称过滤（空字符串表示所有工具）
            limit: 返回的最大记录数
        
        Returns:
            工具调用历史的格式化文本
        """
        if not pipeline.work_log_storage:
            return "WorkLog 未配置"
        entries = await pipeline.work_log_storage.get_work_log(pipeline.conv_id)
        if tool_name:
            entries = [e for e in entries if e.tool == tool_name]
        entries = entries[-limit:]
        # 格式化输出
        ...
    
    async def get_history_overview() -> str:
        """
        获取历史章节目录概览。
        
        返回所有已归档章节的列表，包括每个章节的时间范围、
        消息数、工具调用数和摘要。可以根据概览信息决定
        是否需要 read_history_chapter 读取特定章节的详情。
        
        Returns:
            历史章节目录的格式化文本
        """
        catalog = await pipeline.get_catalog()
        return catalog.get_overview()

    return {
        "read_history_chapter": FunctionTool.from_function(read_history_chapter),
        "search_history": FunctionTool.from_function(search_history),
        "get_tool_call_history": FunctionTool.from_function(get_tool_call_history),
        "get_history_overview": FunctionTool.from_function(get_history_overview),
    }
```

#### 3.4.2 工具注册

**v1 (ReActMasterAgent)**:
在 `preload_resource()` 中注册到 `available_system_tools`:
```python
# react_master_agent.py 中
async def preload_resource(self):
    await super().preload_resource()
    # ... 现有工具注入 ...
    
    # 注入历史回溯工具
    if self._compaction_pipeline:
        from derisk.agent.core.tools.history_tools import create_history_tools
        history_tools = create_history_tools(self._compaction_pipeline)
        for tool_name, tool in history_tools.items():
            self.available_system_tools[tool_name] = tool
```

**v2 (ReActReasoningAgent)**:
在 `__init__()` 或 `preload_resource()` 中注册到 `ToolRegistry`:
```python
# react_reasoning_agent.py 中
async def preload_resource(self):
    await super().preload_resource()
    # ... 现有工具注入 ...
    
    # 注入历史回溯工具
    if self._compaction_pipeline:
        from derisk.agent.core.tools.history_tools import create_history_tools
        history_tools = create_history_tools(self._compaction_pipeline)
        for tool_name, tool_func in history_tools.items():
            self.tools.register(tool_name, tool_func)
```

### 3.5 WorkLog 统一集成

#### 3.5.1 v1 现状与扩展

v1 已有完整的 WorkLog 支持链路：

```text
ReActMasterAgent._record_action_to_work_log()
    └── WorkLogManager.add_entry()
        └── WorkLogStorage.append_work_entry()  (via GptsMemory)
```

**扩展**：在 Layer 3 归档时，通过 WorkLogStorage 创建 WorkLogSummary：
```python
# 在 _archive_messages_to_chapter() 中
if self.work_log_storage:
    summary = WorkLogSummary(
        compressed_entries_count=chapter.message_count,
        time_range=chapter.time_range,
        summary_content=chapter.summary,
        key_tools=chapter.key_tools,
        archive_file=chapter.file_key,
    )
    await self.work_log_storage.append_work_log_summary(
        self.conv_id, summary
    )
```

#### 3.5.2 v2 新增 WorkLog 支持

v2 当前没有 WorkLog 集成。需要：

1. 在 `ReActReasoningAgent.__init__()` 中初始化 `WorkLogManager`
2. 在 `act()` 方法中，每次工具执行后创建 `WorkEntry`
3. 使用 `SimpleWorkLogStorage` 作为轻量级实现（或通过依赖注入使用 `GptsMemory`）

```python
# react_reasoning_agent.py 扩展
class ReActReasoningAgent(BaseBuiltinAgent):
    def __init__(self, ..., work_log_storage=None, ...):
        # ... 现有初始化 ...
        
        # 新增: WorkLog 支持
        self._work_log_storage = work_log_storage or SimpleWorkLogStorage()
        self._work_log_manager = WorkLogManager(
            agent_id=info.name,
            session_id=getattr(info, 'session_id', 'default'),
            work_log_storage=self._work_log_storage,
        )
    
    async def act(self, decision, **kwargs):
        result = await super_act(decision, **kwargs)  # 原有逻辑
        
        # 新增: 记录到 WorkLog
        entry = WorkEntry(
            timestamp=time.time(),
            tool=decision.tool_name,
            args=decision.tool_args,
            result=result.output[:500] if result.output else None,
            success=result.success,
            step_index=self._current_step,
        )
        await self._work_log_manager.add_entry(entry)
        
        return result
```

#### 3.5.3 WorkLogStorage 接口扩展

在现有 `WorkLogStorage` 接口中新增章节管理方法：

```python
class WorkLogStorage(ABC):
    # ... 现有方法 ...
    
    # 新增: 章节目录管理
    async def get_history_catalog(
        self, conv_id: str
    ) -> Optional[Dict]:
        """获取历史章节目录（可选实现，默认返回 None）"""
        return None
    
    async def save_history_catalog(
        self, conv_id: str, catalog: Dict
    ) -> None:
        """保存历史章节目录（可选实现）"""
        pass
```

---

## 4. 集成架构图

### 4.1 总体系统架构

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                         Agent Layer                                      │
│                                                                          │
│  ┌──────────────────────────┐    ┌──────────────────────────┐           │
│  │   ReActMasterAgent (v1)  │    │ ReActReasoningAgent (v2)  │           │
│  │                          │    │                            │           │
│  │  load_thinking_messages  │    │  think() / decide()        │           │
│  │  act()                   │    │  act()                     │           │
│  │  preload_resource()      │    │  preload_resource()        │           │
│  └───────────┬──────────────┘    └──────────────┬─────────────┘           │
│              │                                   │                        │
│              └──────────┬────────────────────────┘                        │
│                         │                                                │
│                         ▼                                                │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                   UnifiedMessageAdapter                          │   │
│  │   get_tool_calls() | get_tool_call_id() | is_tool_call_group()  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                         │                                                │
│                         ▼                                                │
├──────────────────────────────────────────────────────────────────────────┤
│                      Processing Layer                                    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                UnifiedCompactionPipeline                          │   │
│  │                                                                    │   │
│  │  ┌────────────────────────────────────────────────────────────┐  │   │
│  │  │ Layer 1: TruncationLayer                                   │  │   │
│  │  │   truncate_output(output, tool_name) → TruncationResult    │  │   │
│  │  └────────────────────────────────────────────────────────────┘  │   │
│  │  ┌────────────────────────────────────────────────────────────┐  │   │
│  │  │ Layer 2: PruningLayer                                      │  │   │
│  │  │   prune_history(messages) → PruningResult                  │  │   │
│  │  └────────────────────────────────────────────────────────────┘  │   │
│  │  ┌────────────────────────────────────────────────────────────┐  │   │
│  │  │ Layer 3: CompactionLayer                                   │  │   │
│  │  │   compact_if_needed(messages) → CompactionResult           │  │   │
│  │  │   ┌─ ContentProtector (from ImprovedSessionCompaction)     │  │   │
│  │  │   ├─ KeyInfoExtractor                                      │  │   │
│  │  │   └─ ChapterArchiver                                       │  │   │
│  │  └────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                         │                                                │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              History Recovery Tools (System Tools)                │   │
│  │  read_history_chapter | search_history | get_tool_call_history   │   │
│  │  get_history_overview                                            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                         │                                                │
├──────────────────────────────────────────────────────────────────────────┤
│                       Storage Layer                                      │
│                                                                          │
│  ┌─────────────────────┐    ┌──────────────────────────────────────┐    │
│  │   WorkLogManager    │    │        AgentFileSystem V3            │    │
│  │                     │    │                                      │    │
│  │  add_entry()        │    │  save_file() / read_file()           │    │
│  │  compress()         │    │  FileType: HISTORY_CHAPTER           │    │
│  │  get_context()      │    │           HISTORY_CATALOG            │    │
│  └─────────┬───────────┘    │           TRUNCATED_OUTPUT           │    │
│            │                └──────────────────┬───────────────────┘    │
│            ▼                                   │                        │
│  ┌─────────────────────┐                       ▼                        │
│  │  WorkLogStorage     │    ┌──────────────────────────────────────┐    │
│  │  (GptsMemory /      │    │     FileMetadataStorage              │    │
│  │   SimpleStorage)    │    │     (AgentFileMetadata CRUD)         │    │
│  └─────────────────────┘    └──────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              Backend: Local Disk / OSS / Distributed             │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.2 工具调用完整数据流

```text
[1] LLM 返回 response (含 tool_calls)
     │
     ▼
[2] Agent 解析 tool_calls
     │  v1: FunctionCallOutputParser.parse_actions()
     │  v2: decide() → Decision(TOOL_CALL, tool_name, tool_args)
     │
     ▼
[3] Agent 执行工具
     │  v1: _run_single_tool_with_protection() → execution_func()
     │  v2: act() → execute_tool(tool_name, tool_args)
     │
     ▼
[4] Pipeline Layer 1: 截断检查
     │  pipeline.truncate_output(output, tool_name, tool_args)
     │  ├── 未超阈值: 原样返回
     │  └── 超过阈值:
     │      ├── AFS.save_file(full_output, TRUNCATED_OUTPUT) → file_key
     │      ├── 截断 output + 附加建议
     │      └── 返回 TruncationResult
     │
     ▼
[5] WorkLog 记录
     │  WorkLogManager.add_entry(WorkEntry{tool, args, result, file_key})
     │
     ▼
[6] 结果存入消息历史
     │  v1: AgentMessage(role="tool", content=truncated, context={tool_call_id})
     │  v2: AgentMessage(role="tool", content=truncated, metadata={tool_call_id})
     │
     ▼
[7] 下一轮思考前: Pipeline Layer 2 + Layer 3
     │  v1: load_thinking_messages() 中
     │  v2: think() 构建消息前
     │
     ├── Layer 2: pipeline.prune_history(messages) → PruningResult
     │   └── 标记旧工具输出为摘要
     │
     └── Layer 3: pipeline.compact_if_needed(messages) → CompactionResult
         ├── Token 未超: 返回原消息
         └── Token 超限:
             ├── 选择消息范围 → (to_compact, to_keep)
             ├── LLM 生成总结 → summary
             ├── AFS 归档 → chapter_file_key
             ├── 创建 HistoryChapter
             ├── 更新 HistoryCatalog
             ├── WorkLogSummary 记录
             └── 返回 [summary_msg] + to_keep
```

### 4.3 章节归档与回溯流程

```text
=== 归档流程 ===

Messages: [m1, m2, m3, ..., m50, m51, ..., m60]
                                 ▲
                                 │ split point (保留最近 10 条)
                                 
to_compact = [m1 ... m50]    to_keep = [m51 ... m60]
     │
     ├── serialize(to_compact) → JSON
     ├── AFS.save_file(json, HISTORY_CHAPTER, "chapter_0.json") → file_key_0
     ├── LLM.summarize(to_compact) → summary_0
     ├── HistoryChapter(index=0, file_key=file_key_0, summary=summary_0)
     ├── HistoryCatalog.add_chapter(chapter_0)
     └── AFS.save_file(catalog.to_json(), HISTORY_CATALOG)
     
最终消息: [summary_msg_0, m51, ..., m60]

... 继续运行 ...

Messages: [summary_msg_0, m51, ..., m60, m61, ..., m120]
                                              ▲
                                              │ 再次触发
to_compact = [summary_msg_0, m51 ... m110]
to_keep = [m111 ... m120]
     │
     ├── AFS.save_file(..., "chapter_1.json") → file_key_1
     ├── HistoryChapter(index=1, ...)
     └── HistoryCatalog.add_chapter(chapter_1)

最终消息: [summary_msg_1, m111, ..., m120]


=== 回溯流程 ===

Agent: "我需要查看之前分析过的日志内容..."
     │
     ▼
Agent 调用 get_history_overview()
     │  返回:
     │  Chapter 0: [10:00 - 10:30] 50 msgs, 20 tool calls
     │    Summary: 初始分析阶段，读取了 /var/log/syslog...
     │  Chapter 1: [10:30 - 11:15] 60 msgs, 35 tool calls
     │    Summary: 深入分析异常日志，执行了根因定位...
     │
     ▼
Agent 调用 read_history_chapter(chapter_index=0)
     │  Pipeline.read_chapter(0)
     │  ├── catalog.get_chapter(0) → chapter_0
     │  ├── AFS.read_file(chapter_0.file_key) → JSON
     │  ├── deserialize → messages
     │  └── format_for_display → 格式化文本
     │
     ▼
Agent 获得完整的归档内容，继续推理
```

---

## 5. 两套架构的详细集成点

### 5.1 v1 (ReActMasterAgent) 集成点

> 源文件：`packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py`

#### 5.1.1 初始化 Pipeline

在 `_initialize_components()` 中（约 L267）新增:

```python
def _initialize_components(self):
    # ... 现有组件初始化 (1-9) ...
    
    # 10. 初始化统一压缩管道（延迟初始化，需要 conv_id）
    self._compaction_pipeline = None
    self._pipeline_initialized = False

async def _ensure_compaction_pipeline(self) -> Optional["UnifiedCompactionPipeline"]:
    """确保压缩管道已初始化"""
    if self._pipeline_initialized:
        return self._compaction_pipeline
    
    afs = await self._ensure_agent_file_system()
    if not afs:
        return None
    
    ctx = self.not_null_agent_context
    self._compaction_pipeline = UnifiedCompactionPipeline(
        conv_id=ctx.conv_id,
        session_id=ctx.conv_session_id,
        agent_file_system=afs,
        work_log_storage=self.memory.gpts_memory if self.memory else None,
        llm_client=self._get_llm_client(),
        config=HistoryCompactionConfig(
            context_window=self.context_window,
            compaction_threshold_ratio=self.compaction_threshold_ratio,
            max_output_lines=...,
            max_output_bytes=...,
            prune_protect_tokens=self.prune_protect_tokens,
        ),
    )
    self._pipeline_initialized = True
    return self._compaction_pipeline
```

#### 5.1.2 集成 Layer 1 (截断)

在 `_run_single_tool_with_protection()` 中（约 L637-688），替换截断逻辑:

```python
# 现有: 
# result.content = self._truncate_tool_output(result.content, tool_name)
# 改为:
pipeline = await self._ensure_compaction_pipeline()
if pipeline and result.content:
    tr = await pipeline.truncate_output(result.content, tool_name, args)
    result.content = tr.content
```

#### 5.1.3 集成 Layer 2 + Layer 3 (剪枝 + 压缩)

在 `load_thinking_messages()` 中（约 L690-725），替换现有的 prune 和 compact 逻辑:

```python
async def load_thinking_messages(self, ...):
    messages, context, system_prompt, user_prompt = await super().load_thinking_messages(...)
    
    pipeline = await self._ensure_compaction_pipeline()
    if pipeline and messages:
        # Layer 2: 剪枝（替换现有 _prune_history）
        prune_result = await pipeline.prune_history(messages)
        messages = prune_result.messages
        
        # Layer 3: 压缩+归档（替换现有 _check_and_compact_context）
        compact_result = await pipeline.compact_if_needed(messages)
        messages = compact_result.messages
    else:
        # 回退到现有逻辑
        messages = await self._prune_history(messages)
        messages = await self._check_and_compact_context(messages)
    
    await self._ensure_agent_file_system()
    return messages, context, system_prompt, user_prompt
```

#### 5.1.4 注册历史回溯工具

在 `preload_resource()` 中（约 L186-206）:

```python
async def preload_resource(self):
    await super().preload_resource()
    await self.system_tool_injection()
    await self.sandbox_tool_injection()
    # ... 现有工具注入 ...
    
    # 注入历史回溯工具
    pipeline = await self._ensure_compaction_pipeline()
    if pipeline and self.config.enable_recovery_tools:
        from derisk.agent.core.tools.history_tools import create_history_tools
        for name, tool in create_history_tools(pipeline).items():
            self.available_system_tools[name] = tool
            logger.info(f"History tool '{name}' injected")
```

### 5.2 v2 (ReActReasoningAgent) 集成点

> 源文件：`packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_reasoning_agent.py`

#### 5.2.1 初始化 Pipeline + WorkLog

在 `__init__()` 中（约 L116-150）新增参数和初始化:

```python
class ReActReasoningAgent(BaseBuiltinAgent):
    def __init__(
        self,
        ...,  # 现有参数
        # 新增参数
        enable_work_log: bool = True,
        enable_compaction_pipeline: bool = True,
        agent_file_system: Optional["AgentFileSystem"] = None,
        work_log_storage: Optional["WorkLogStorage"] = None,
        compaction_config: Optional["HistoryCompactionConfig"] = None,
    ):
        super().__init__(...)
        # ... 现有初始化 ...
        
        # 新增: 文件系统
        self._agent_file_system = agent_file_system
        
        # 新增: WorkLog
        self._work_log_storage = work_log_storage
        if enable_work_log:
            from ...core.memory.gpts.file_base import SimpleWorkLogStorage
            if not self._work_log_storage:
                self._work_log_storage = SimpleWorkLogStorage()
        
        # 新增: 统一压缩管道（延迟初始化）
        self._compaction_pipeline = None
        self._compaction_config = compaction_config
        self._enable_compaction_pipeline = enable_compaction_pipeline
```

#### 5.2.2 集成 Layer 1 (截断)

在 `act()` 中（约 L607-661），替换截断逻辑:

```python
async def act(self, decision, **kwargs):
    # ... 执行工具 ...
    result = await self.execute_tool(tool_name, tool_args)
    
    # 替换原有 OutputTruncator 逻辑
    pipeline = self._get_compaction_pipeline()
    if pipeline and result.output:
        tr = await pipeline.truncate_output(result.output, tool_name, tool_args)
        result.output = tr.content
        if tr.is_truncated:
            result.metadata["truncated"] = True
            result.metadata["file_key"] = tr.file_key
    elif self._output_truncator and result.output:
        # 回退到原有逻辑
        truncation_result = self._output_truncator.truncate(result.output, tool_name)
        ...
    
    # 新增: 记录到 WorkLog
    if self._work_log_storage:
        entry = WorkEntry(
            timestamp=time.time(),
            tool=tool_name,
            args=tool_args,
            result=result.output[:500] if result.output else None,
            full_result_archive=tr.file_key if tr and tr.is_truncated else None,
            success=result.success,
            step_index=self._current_step,
        )
        await self._work_log_storage.append_work_entry(
            self._get_session_id(), entry
        )
    
    return ActionResult(...)
```

#### 5.2.3 集成 Layer 2 + Layer 3

在 `think()` 中（约 L465-536），在构建消息列表前执行压缩:

```python
async def think(self, message, **kwargs):
    # ... 前置逻辑 ...
    
    # 新增: 在构建消息前执行压缩管道
    pipeline = self._get_compaction_pipeline()
    if pipeline:
        prune_result = await pipeline.prune_history(self._messages)
        self._messages = prune_result.messages
        
        compact_result = await pipeline.compact_if_needed(self._messages)
        self._messages = compact_result.messages
    
    # 构建消息列表（原有逻辑）
    for msg in self._messages[-20:]:
        ...
```

#### 5.2.4 新增 AgentFileSystem 支持

v2 当前不使用 `AgentFileSystem`，需要引入:

```python
async def _ensure_agent_file_system(self) -> Optional["AgentFileSystem"]:
    """确保 AgentFileSystem 已初始化"""
    if self._agent_file_system:
        return self._agent_file_system
    
    try:
        from ...core.file_system.agent_file_system import AgentFileSystem
        session_id = self._get_session_id()
        self._agent_file_system = AgentFileSystem(
            conv_id=session_id,
            session_id=session_id,
        )
        await self._agent_file_system.sync_workspace()
        return self._agent_file_system
    except Exception as e:
        logger.warning(f"Failed to initialize AgentFileSystem: {e}")
        return None
```

#### 5.2.5 注册历史回溯工具

在 `_get_default_tools()` 或 `preload_resource()` 中:

```python
async def preload_resource(self):
    await super().preload_resource()
    # ... 现有资源加载 ...
    
    # 注入历史回溯工具
    pipeline = self._get_compaction_pipeline()
    if pipeline:
        from ...core.tools.history_tools import create_history_tools
        for name, tool in create_history_tools(pipeline).items():
            self.tools.register(name, tool)
```

---

## 6. 新增 FileType 和数据模型

### 6.1 FileType 扩展

在 `packages/derisk-core/src/derisk/agent/core/memory/gpts/file_base.py` 中新增:

```python
class FileType(enum.Enum):
    # ... 现有类型 ...
    HISTORY_CHAPTER = "history_chapter"       # 章节原始消息归档（JSON）
    HISTORY_CATALOG = "history_catalog"       # 会话章节索引目录（JSON）
    HISTORY_SUMMARY = "history_summary"       # 章节总结文件（Markdown）
```

### 6.2 WorkLogStatus 扩展

```python
class WorkLogStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPRESSED = "compressed"
    ARCHIVED = "archived"           # 已有
    CHAPTER_ARCHIVED = "chapter_archived"  # 新增: 已归档到章节
```

### 6.3 WorkLogStorage 接口扩展

```python
class WorkLogStorage(ABC):
    # ... 现有 7 个抽象方法 ...
    
    # 新增（可选实现，提供默认空实现）
    async def get_history_catalog(self, conv_id: str) -> Optional[Dict]:
        """获取历史章节目录"""
        return None
    
    async def save_history_catalog(self, conv_id: str, catalog: Dict) -> None:
        """保存历史章节目录"""
        pass
```

### 6.4 AgentFileMetadata 扩展考虑

现有 `AgentFileMetadata` 已包含足够的字段支持章节存储:
- `file_type`: 使用新的 `HISTORY_CHAPTER` / `HISTORY_CATALOG`
- `metadata`: 字典字段，可存储 `chapter_index`, `time_range` 等
- `message_id`: 可关联最后一条被归档的消息 ID
- `tool_name`: 对于 `HISTORY_CHAPTER` 可设为 `"compaction_pipeline"`

无需修改 `AgentFileMetadata` 的结构定义。

---

## 7. 配置设计

> 建议文件位置：放在 `compaction_pipeline.py` 同文件内

```python
@dataclasses.dataclass
class HistoryCompactionConfig:
    """统一压缩管道配置"""
    
    # ==================== Layer 1: 截断配置 ====================
    max_output_lines: int = 2000          # 单次输出最大行数
    max_output_bytes: int = 50 * 1024     # 单次输出最大字节数 (50KB)
    
    # ==================== Layer 2: 剪枝配置 ====================
    prune_protect_tokens: int = 4000      # 保护最近 N tokens 的消息不被剪枝
    prune_interval_rounds: int = 5        # 每 N 轮检查一次
    min_messages_keep: int = 10           # 最少保留消息数
    
    # ==================== Layer 3: 压缩+归档配置 ====================
    context_window: int = 128000          # LLM 上下文窗口大小
    compaction_threshold_ratio: float = 0.8  # 触发压缩的阈值比例
    recent_messages_keep: int = 5         # 压缩时保留的最近消息数
    chars_per_token: int = 4              # Token 估算比例
    
    # 章节归档
    chapter_max_messages: int = 100       # 单章节最大消息数
    chapter_summary_max_tokens: int = 2000  # 章节总结最大 token
    max_chapters_in_memory: int = 3       # 内存中缓存的章节数
    
    # 内容保护（继承自 ImprovedSessionCompaction）
    code_block_protection: bool = True    # 保护代码块
    thinking_chain_protection: bool = True  # 保护思维链
    file_path_protection: bool = True     # 保护文件路径
    max_protected_blocks: int = 10        # 最大保护块数
    
    # 共享记忆
    reload_shared_memory: bool = True     # 压缩后重载共享记忆
    
    # 自适应触发
    adaptive_check_interval: int = 5      # 自适应检查间隔（消息数）
    adaptive_growth_threshold: float = 0.3  # 增长率触发阈值
    
    # ==================== 回溯工具配置 ====================
    enable_recovery_tools: bool = True    # 是否启用历史回溯工具
    max_search_results: int = 10          # 搜索最大返回数
    
    # ==================== 兼容配置 ====================
    fallback_to_legacy: bool = True       # Pipeline 不可用时回退到现有逻辑
```

---

## 8. 迁移策略

### 阶段规划

| 阶段 | 内容 | 影响范围 | 风险 |
|------|------|---------|------|
| Phase 1 | UnifiedMessageAdapter | 新增文件，无改动 | 极低 |
| Phase 2 | 数据模型 (HistoryChapter, HistoryCatalog, FileType) | file_base.py 新增枚举 | 低 |
| Phase 3 | UnifiedCompactionPipeline 实现 | 新增文件，核心逻辑 | 中 |
| Phase 4 | v1 ReActMasterAgent 集成 | 修改现有文件 | 中 |
| Phase 5 | v2 ReActReasoningAgent 集成 | 修改现有文件 | 中 |
| Phase 6 | History Recovery Tools | 新增文件 + 注册 | 低 |
| Phase 7 | 测试与验证 | 全链路 | - |

### Phase 1: UnifiedMessageAdapter (无破坏性改动)

**目标**: 实现统一消息读取层。

**新增文件**:
- `packages/derisk-core/src/derisk/agent/core/memory/message_adapter.py`

**验证**:
- 单元测试：分别传入 v1 和 v2 的 AgentMessage，验证所有 get_* 方法返回一致
- 确保 `is_tool_call_message()` 和 `is_tool_result_message()` 对两种格式都正确

### Phase 2: 数据模型扩展

**目标**: 定义章节归档相关的数据结构。

**修改文件**:
- `core/memory/gpts/file_base.py`: 新增 FileType 枚举值

**新增文件**:
- `core/memory/history_archive.py`: HistoryChapter, HistoryCatalog

**验证**:
- 序列化/反序列化测试 (`to_dict()` / `from_dict()`)
- 确保新的 FileType 不与现有值冲突

### Phase 3: UnifiedCompactionPipeline

**目标**: 实现三层压缩管道核心逻辑。

**新增文件**:
- `core/memory/compaction_pipeline.py`: UnifiedCompactionPipeline

**关键实现决策**:
- Layer 3 的总结生成逻辑直接移植自 `ImprovedSessionCompaction._generate_summary()`
- 消息选择逻辑移植自 `ImprovedSessionCompaction._select_messages_to_compact()`
- 新增：章节归档到 AgentFileSystem 和 HistoryCatalog 管理

**验证**:
- 单独测试每个 Layer
- 集成测试：模拟 100+ 轮对话，验证压缩触发和章节创建
- 验证 tool-call 原子组不被拆分

### Phase 4: v1 ReActMasterAgent 集成

**目标**: 将 Pipeline 集成到 v1 架构。

**修改文件**:
- `expand/react_master_agent/react_master_agent.py`:
  - `_initialize_components()`: 新增 pipeline 初始化
  - `load_thinking_messages()`: Layer 2 + 3 集成
  - `_run_single_tool_with_protection()`: Layer 1 集成
  - `preload_resource()`: 工具注册

**兼容策略**:
- 新增 `enable_compaction_pipeline: bool = False` 配置项（默认关闭）
- `fallback_to_legacy=True` 确保 pipeline 失败时回退到现有逻辑
- 渐进式切换：先在测试环境验证，再开启

### Phase 5: v2 ReActReasoningAgent 集成

**目标**: 将 Pipeline + WorkLog + AgentFileSystem 引入 v2。

**修改文件**:
- `core_v2/builtin_agents/react_reasoning_agent.py`:
  - `__init__()`: 新增参数和初始化
  - `think()`: Layer 2 + 3 集成
  - `act()`: Layer 1 + WorkLog 集成
  - `preload_resource()`: 工具注册
  - 新增 `_ensure_agent_file_system()`

**兼容策略**:
- 所有新参数都有默认值，不影响现有使用方式
- `enable_compaction_pipeline=False` 默认关闭
- v2 可选择不使用 AgentFileSystem（回退到原有 OutputTruncator）

### Phase 6: History Recovery Tools

**目标**: 实现并注册历史回溯工具。

**新增文件**:
- `core/tools/history_tools.py`: 工具函数定义 + `create_history_tools()`

**验证**:
- 工具函数单元测试
- 在两个架构中分别测试工具注册和调用
- 验证 LLM 能正确调用这些工具（function calling schema 生成正确）

### Phase 7: 测试与验证

**测试类型**:

1. **单元测试**: 每个组件独立测试
   - UnifiedMessageAdapter
   - HistoryChapter / HistoryCatalog 序列化
   - Pipeline 各 Layer 独立测试

2. **集成测试**: 完整链路测试
   - 模拟 200+ 轮长对话
   - 验证多次压缩 → 多章节生成
   - 验证章节回溯工具返回正确内容

3. **压力测试**: Token 控制验证
   - 验证消息总量始终在 context_window * threshold_ratio 以内
   - 验证大型工具输出（>1MB）的截断和归档

4. **兼容性测试**: 回退验证
   - Pipeline 禁用时，v1 和 v2 行为与现有完全一致
   - Pipeline 初始化失败时，自动回退到现有逻辑

---

## 9. 设计决策记录

### 9.1 为什么选择 ImprovedSessionCompaction 作为 Layer 3 基础？

v2 的 `ImprovedSessionCompaction`（928 行）是目前系统中最成熟的压缩实现：

- **内容保护**: ContentProtector 可以识别并保护代码块、思维链、文件路径等关键内容
- **原子组感知**: `_select_messages_to_compact()` 已经实现了 tool-call 原子组保护逻辑
- **关键信息提取**: KeyInfoExtractor 能自动识别重要性高的信息并优先保留
- **自适应触发**: 基于 token 增长率的自适应触发策略比简单阈值更智能
- **兼容两种消息格式**: 已同时处理 `msg.tool_calls` 和 `msg.context.get("tool_calls")`

相比之下，v1 的 `SessionCompaction`（503 行）功能更简单，缺少内容保护和关键信息提取。

### 9.2 为什么采用章节化归档而非仅保留总结？

仅保留总结（lossy compression）会导致细节不可逆丢失。在 SRE/RCA 场景中，Agent 经常需要回顾之前读取的日志片段、配置文件内容、执行结果等。

章节化归档的优势：
- **可逆性**: 原始消息完整保存在 AgentFileSystem 中，Agent 可随时加载回来
- **按需加载**: 仅在需要时通过工具加载，不占用常驻上下文
- **可搜索**: 通过章节总结和关键词可快速定位相关信息
- **空间效率**: 利用已有的 AgentFileSystem 存储体系，支持 OSS 等远程存储

### 9.3 为什么使用适配器模式而非修改 AgentMessage？

v1 和 v2 的 `AgentMessage` 在整个系统中被深度使用：

- v1 `AgentMessage` (dataclass) 被 `ConversableAgent`, `Agent`, `ActionOutput`, `GptsMemory` 等数十个类引用
- v2 `AgentMessage` (Pydantic BaseModel) 被 `AgentBase`, `BaseBuiltinAgent`, `EnhancedAgent` 等使用

直接修改基类会导致：
- 大量已有代码需要适配
- 序列化/反序列化格式变化的兼容性风险
- 两个版本之间的依赖混乱

适配器模式的优势：
- 零侵入：不修改任何现有类
- 单点维护：格式差异集中在适配器中处理
- 安全：任何错误只影响新功能，不影响现有逻辑

### 9.4 为什么坚持使用 AgentFileSystem V3 作为存储后端？

`AgentFileSystem` V3 已经在 v1 架构中得到充分验证：

- **统一接口**: 一套 API 支持本地存储和 OSS 远程存储
- **元数据追踪**: 通过 `FileMetadataStorage` 记录每个文件的完整元数据
- **会话隔离**: 按 `conv_id` 隔离文件，避免跨会话污染
- **文件恢复**: 支持通过 `sync_workspace()` 从远程恢复文件
- **已有集成**: v1 的 Truncator, WorkLogManager 已经使用它

将同一套存储体系引入 v2 可以：
- 共享文件管理基础设施
- 实现跨架构的文件互通
- 避免重复造轮子

### 9.5 为什么设计三层而非两层或一层？

三层压缩对应三种不同粒度的内存管理需求：

| 层 | 粒度 | 触发频率 | 作用 |
|---|---|---|---|
| Layer 1 截断 | 单次工具输出 | 每次工具调用 | 防止单次输出撑爆上下文 |
| Layer 2 剪枝 | 消息级别 | 每 N 轮 | 渐进式释放旧内容空间 |
| Layer 3 归档 | 会话级别 | Token 接近上限 | 大规模压缩 + 持久化 |

如果只有 Layer 3，在长对话中会出现：
- 前期：大量冗余的旧工具输出占据上下文
- 触发压缩时：需要一次性压缩大量消息，延迟高
- 压缩后：丢失大量中间细节

三层设计的渐进式策略确保上下文始终保持健康状态。

---

## 附录 A: 关键源文件索引

| 文件 | 说明 |
|------|------|
| `core/types.py` | v1 AgentMessage (dataclass) |
| `core_v2/agent_base.py` | v2 AgentMessage (Pydantic) |
| `core/memory/gpts/file_base.py` | WorkEntry, WorkLogSummary, WorkLogStorage, FileType, AgentFileMetadata |
| `core/memory/gpts/gpts_memory.py` | GptsMemory (实现 WorkLogStorage) |
| `core/file_system/agent_file_system.py` | AgentFileSystem V3 |
| `expand/react_master_agent/react_master_agent.py` | ReActMasterAgent (v1, 1852 行) |
| `expand/react_master_agent/session_compaction.py` | v1 SessionCompaction (503 行) |
| `expand/react_master_agent/prune.py` | v1 HistoryPruner |
| `expand/react_master_agent/truncation.py` | v1 Truncator |
| `expand/react_master_agent/work_log.py` | WorkLogManager (645 行) |
| `core_v2/builtin_agents/react_reasoning_agent.py` | ReActReasoningAgent (v2, 774 行) |
| `core_v2/improved_compaction.py` | ImprovedSessionCompaction (928 行, 最成熟) |
| `core_v2/memory_compaction.py` | MemoryCompactor (708 行) |
| `core_v2/builtin_agents/react_components/` | v2 的 OutputTruncator, HistoryPruner, ContextCompactor, DoomLoopDetector |

## 附录 B: 新增文件清单

| 文件（建议路径） | 说明 |
|------|------|
| `core/memory/message_adapter.py` | UnifiedMessageAdapter |
| `core/memory/history_archive.py` | HistoryChapter, HistoryCatalog |
| `core/memory/compaction_pipeline.py` | UnifiedCompactionPipeline, HistoryCompactionConfig |
| `core/tools/history_tools.py` | 历史回溯工具 (read_history_chapter, search_history, etc.) |

---

## 附录 C: 实现进展记录

> 最后更新: 2026-03-03

### 总体状态: ✅ 全部完成

所有 7 个阶段已完成代码开发，122 个单元测试全部通过。

### 各阶段完成状态

| 阶段 | 状态 | 完成文件 |
|------|------|---------|
| Phase 1: UnifiedMessageAdapter | ✅ 完成 | `core/memory/message_adapter.py` (241 行) |
| Phase 2: 数据模型扩展 | ✅ 完成 | `core/memory/history_archive.py` (107 行) + `file_base.py` 新增枚举 |
| Phase 3: UnifiedCompactionPipeline | ✅ 完成 | `core/memory/compaction_pipeline.py` (1001 行) |
| Phase 4: History Recovery Tools | ✅ 完成 | `core/tools/history_tools.py` (175 行) |
| Phase 5: v1 ReActMasterAgent 集成 | ✅ 完成 | `react_master_agent.py` — 6 处集成点 |
| Phase 6: v2 ReActReasoningAgent 集成 | ✅ 完成 | `react_reasoning_agent.py` — 7 处集成点 |
| Phase 7: 测试与验证 | ✅ 完成 | `tests/agent/test_history_compaction.py` (~900 行, 122 tests) |

### 关键实现决策记录

1. **历史回溯工具延迟注入**: 历史回溯工具（read_history_chapter, search_history, get_tool_call_history, get_history_overview）仅在首次 compaction 发生后才动态注入到 Agent 的工具集中。通过 `pipeline.has_compacted` 属性控制。这避免了在短会话中暴露无意义的空工具。

2. **v1 Core `all_tool_message` 修正**: v1 架构的 `thinking()` 方法已重写，确保传递给 LLM 的 `tool_messages`（即 kwargs 中的 `all_tool_message`）来自压缩后的记忆（经过 Layer 2 剪枝 + Layer 3 压缩），而非原始未压缩的消息列表。

3. **FunctionTool 构造方式**: 使用 `FunctionTool(name=..., func=..., description=...)` 直接构造，而非 `FunctionTool.from_function()`。内部函数引用通过 `_func` 属性访问。

4. **v2 工具注册方式**: v2 使用 `ToolRegistry.register_function(name, description, func, parameters)` 注册历史工具，该方法内部创建兼容的 `ToolBase` 包装器。

5. **适配器模式**: `UnifiedMessageAdapter` 通过静态方法统一读取 v1 (dataclass)、v2 (Pydantic) 和 plain dict 三种消息格式，不修改任何现有 AgentMessage 类。角色名通过 `_ROLE_ALIASES` 归一化（ai→assistant, human→user）。

7. **Skill 保护机制**: 在 Layer 2 (Prune) 阶段，通过 `prune_protected_tools=("skill",)` 配置项，保护 skill 工具输出不被剪枝。在 Layer 3 (Compaction) 阶段，skill 输出被提取到 `chapter.skill_outputs` 并在摘要消息中重新注入，确保 compaction 后 Agent 仍能访问完整的 skill 指令。

8. **向后兼容**: 所有新参数默认关闭 (`enable_compaction_pipeline=False`)，`fallback_to_legacy=True` 确保 pipeline 异常时自动回退到现有逻辑。

### 测试覆盖

- **UnifiedMessageAdapter**: 35+ 测试 — role/content/tool_calls/tool_call_id/timestamp 读取、消息分类、序列化、格式化
- **HistoryChapter & HistoryCatalog**: 序列化/反序列化往返、目录管理、章节检索
- **HistoryCompactionConfig**: 默认值与自定义值
- **内容保护**: importance 计算、代码块/思维链/文件路径提取、保护内容格式化
- **关键信息提取**: decision/constraint/preference 提取、去重、格式化
- **Pipeline Layer 1 (截断)**: 5 测试 — 无截断/按行/按字节/AFS 归档/无 AFS 回退
- **Pipeline Layer 2 (剪枝)**: 5 测试 — 间隔控制/跳过用户消息/跳过短消息/最小消息保护
- **Pipeline Layer 3 (压缩)**: 8 测试 — 阈值控制/强制触发/AFS 归档/系统消息保护/近期消息保留/空消息/tool_call 原子组/has_compacted 标志
- **目录管理**: 3 测试 — 新建/从存储加载/保存
- **章节恢复**: 5 测试 — 未找到/无 AFS/成功读取/搜索无结果/搜索匹配
- **历史工具**: 9 测试 — 工具创建/类型验证/描述/各工具功能调用
- **数据模型枚举**: FileType 新值/WorkLogStatus 新值
- **SimpleWorkLogStorage**: 目录的空读取/保存读取往返/按需创建存储
- **Pipeline 内部辅助**: 5 测试 — token 估算/消息选择/tool_call 组保护/摘要消息创建
- **Skill 保护**: 5 测试 — 工具名查找/skill 跳过剪枝/skill 输出提取/摘要重新注入
- **端到端**: 2 测试 — 完整三层流程/多轮压缩循环

### 新增/修改文件汇总

**新增文件 (5)**:
- `packages/derisk-core/src/derisk/agent/core/memory/message_adapter.py`
- `packages/derisk-core/src/derisk/agent/core/memory/history_archive.py`
- `packages/derisk-core/src/derisk/agent/core/memory/compaction_pipeline.py`
- `packages/derisk-core/src/derisk/agent/core/tools/history_tools.py`
- `packages/derisk-core/tests/agent/test_history_compaction.py`

**修改文件 (3)**:
- `packages/derisk-core/src/derisk/agent/core/memory/gpts/file_base.py` — 新增 FileType 枚举值、WorkLogStatus 枚举值、WorkLogStorage 目录方法
- `packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py` — Pipeline 集成 (6 处)
- `packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_reasoning_agent.py` — Pipeline 集成 (7 处)
