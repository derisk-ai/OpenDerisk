# Compression Layers Architecture - Complete Mapping

## Overview
The codebase implements **three-layer context compression** to manage LLM token usage in long-running agent sessions. Each layer operates at a different granularity level.

---

## Layer 1: Truncation (Tool Output Truncation)

**Purpose:** Immediately truncate large tool outputs before sending to LLM to prevent single-call context overflow.

### Core Implementation Files

#### 1. **`packages/derisk-core/src/derisk/agent/expand/react_master_agent/truncation.py`**
- **Main Class:** `Truncator`
- **Key Methods:**
  - `truncate(content, tool_name, max_lines, max_bytes)` - Synchronous truncation
  - `truncate_async(content, tool_name, max_lines, max_bytes)` - Asynchronous truncation
  - `read_truncated_content(file_key)` - Retrieve full truncated content
  - `_save_via_agent_file_system()` - Save to AgentFileSystem (AFS)
  - `_save_to_legacy_temp_file()` - Save to local temp directory

- **Data Class:** `TruncationResult`
  ```python
  - content: str (truncated output)
  - is_truncated: bool
  - original_lines: int
  - truncated_lines: int
  - original_bytes: int
  - truncated_bytes: int
  - temp_file_path: Optional[str]
  - file_key: Optional[str]  # AFS file identifier
  - suggestion: Optional[str] # Hint for agent
  ```

- **Configuration:** `TruncationConfig`
  ```python
  - DEFAULT_MAX_LINES = 50
  - DEFAULT_MAX_BYTES = 5 * 1024  # 50KB
  - TRUNCATION_SUGGESTION_TEMPLATE (with AFS file_key)
  - TRUNCATION_SUGGESTION_TEMPLATE_NO_AFS (legacy with file_path)
  ```

- **File Management Strategy:**
  - **AgentFileSystem (Modern):** Uses `file_key` for unified file management across agents
  - **Legacy Mode:** Saves to `~/.opencode/tool-output` directory
  - Generates unique `file_key` format: `tool_output_{tool_name}_{hash}_{counter}`

- **Logging:** Comprehensive logging at INFO level for truncation events

#### 2. **`packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_components/output_truncator.py`**
- **Main Class:** `OutputTruncator` (Simplified v2 version)
- **Key Methods:**
  - `truncate(content, tool_name)` - Simple synchronous truncation
  - `_save_full_output()` - Save to temp directory
  - `_generate_suggestion()` - Generate agent hint
  - `cleanup()` - Clean up temporary files

- **Features:**
  - Simpler than expand/react_master_agent version
  - Auto-cleanup of temp directory
  - No AgentFileSystem integration (v2 simplification)
  - Logging with `[Truncator]` prefix

- **Configuration:**
  ```python
  - max_lines: int = 2000
  - max_bytes: int = 50000
  - enable_save: bool = True
  ```

### Logging Points (Truncation)
```
Level: INFO
"Truncating output for {tool_name}: {original_lines} lines, {original_bytes} bytes -> max {max_lines} lines, {max_bytes} bytes"
"[AFS] Saved truncated output via AgentFileSystem: key={file_key}, path={file_metadata.local_path}"
"[Truncator] 截断输出: {original_lines}行 -> {truncated_lines_count}行, {original_bytes}字节 -> {truncated_bytes}字节"
"[Truncator] 保存完整输出: {file_path}"
"[Truncator] 清理输出目录: {self._output_dir}"

Level: ERROR
"Failed to save truncated output: {e}"
"[Truncator] 保存失败: {e}"
"[Truncator] 清理失败: {e}"
```

---

## Layer 2: Pruning (History Record Pruning)

**Purpose:** Clean up old/obsolete tool outputs from message history by marking them as "compacted" with placeholder content.

### Core Implementation Files

#### 1. **`packages/derisk-core/src/derisk/agent/expand/react_master_agent/prune.py`**
- **Main Class:** `HistoryPruner`
- **Key Methods:**
  - `prune(messages)` - Main pruning operation
  - `prune_action_outputs(action_outputs, max_total_length)` - Prune ActionOutput lists
  - `_get_prunable_indices()` - Identify which messages can be pruned
  - `_mark_compacted()` - Mark message as compacted with placeholder
  - `get_stats()` - Return pruning statistics

- **Data Classes:**
  ```python
  PruneConfig:
    - DEFAULT_PRUNE_PROTECT = 4000 tokens
    - TOOL_OUTPUT_THRESHOLD_RATIO = 0.6
    - MESSAGE_EXPIRY_SECONDS = 1800 (30 minutes)
    - MIN_MESSAGES_KEEP = 5
    - MAX_MESSAGES_KEEP = 50
    - PRUNE_STRATEGY = "token_based"

  PruneResult:
    - success: bool
    - original_messages: List[AgentMessage]
    - pruned_messages: List[AgentMessage]
    - removed_count: int
    - tokens_before: int
    - tokens_after: int
    - tokens_saved: int
    - pruned_message_ids: List[str]

  MessageMetrics:
    - message_id: str
    - token_count: int
    - message_type: MessageType (SYSTEM, USER, ASSISTANT, TOOL_OUTPUT, etc.)
    - timestamp: float
    - is_essential: bool
    - is_compacted: bool

  MessageType (Enum):
    - SYSTEM, USER, ASSISTANT, TOOL_OUTPUT, THINKING, SUMMARY, OBSOLETE
  ```

- **Pruning Strategy:**
  1. From back to front: traverse from newest to oldest
  2. Keep latest `MIN_MESSAGES_KEEP` messages
  3. When cumulative tokens exceed `PRUNE_PROTECT`:
     - Mark tool outputs as "compacted"
     - Replace content with placeholder: `[内容已压缩: {type}] {summary}...`
     - Preserve original summary in context
  4. Mark with metadata:
     ```python
     message.context["compacted"] = True
     message.context["compacted_at"] = timestamp
     message.context["original_summary"] = summary
     ```

- **Message Classification:**
  - **Essential messages** (never pruned):
    - System, user, human messages
    - Messages with `is_critical` flag
    - Compaction summary messages
  - **Prunable messages:**
    - Tool outputs (TOOL_OUTPUT)
    - Thinking/reasoning messages (THINKING)
    - Older assistant messages (if exceeding limits)

#### 2. **`packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_components/history_pruner.py`**
- **Main Class:** `HistoryPruner` (Simplified v2 version)
- **Key Methods:**
  - `needs_prune()` - Check if pruning needed
  - `prune()` - Execute pruning
  - `_do_prune()` - Internal pruning logic
  - `_select_tool_outputs_to_keep()` - Select which outputs to preserve
  - `get_statistics()` - Return stats

- **Features:**
  - Works with dict-based messages (simpler than expand version)
  - Tool output detection by content string matching
  - Logarithmic spacing of preserved outputs
  - Logging with `[Pruner]` prefix

- **Configuration:**
  ```python
  - max_tool_outputs: int = 20
  - protect_recent: int = 10
  - protect_system: bool = True
  ```

### Logging Points (Pruning)
```
Level: INFO
"Pruning history: {len(messages)} messages, ~{total_tokens} tokens, threshold {self.prune_protect}"
"No messages eligible for pruning"
"Pruning completed: marked {result.removed_count} messages as compacted, saved ~{result.tokens_saved} tokens"
"[Pruner] 修剪历史: {original_count}条 -> {len(pruned_messages)}条, 移除 {messages_removed}条, 节省 {tokens_saved} tokens"
```

---

## Layer 3: Compaction & Archival (Session Compression)

**Purpose:** When context window is near limit, compress entire session history into summarized chapters and archive old chapters.

### Core Implementation Files

#### 1. **`packages/derisk-core/src/derisk/agent/expand/react_master_agent/session_compaction.py`**
- **Main Class:** `SessionCompaction`
- **Key Methods:**
  - `is_overflow(messages, estimated_output_tokens)` - Check if context exceeding threshold
  - `compact(messages, force=False)` - Perform session compression
  - `_select_messages_to_compact()` - Select which messages to compress
  - `_generate_summary()` - Use LLM to generate summary
  - `_generate_simple_summary()` - Fallback summary without LLM
  - `_format_messages_for_summary()` - Format messages for LLM
  - `get_stats()` - Return compaction statistics

- **Data Classes:**
  ```python
  CompactionConfig:
    - DEFAULT_CONTEXT_WINDOW = 128000
    - DEFAULT_THRESHOLD_RATIO = 0.8
    - SUMMARY_MESSAGES_TO_KEEP = 5
    - RECENT_MESSAGES_KEEP = 3
    - CHARS_PER_TOKEN = 4

  CompactionStrategy (Enum):
    - SUMMARIZE = "summarize"
    - TRUNCATE_OLD = "truncate_old"
    - HYBRID = "hybrid"

  TokenEstimate:
    - input_tokens: int
    - cached_tokens: int
    - output_tokens: int
    - total_tokens: int
    - usable_context: int

  CompactionResult:
    - success: bool
    - original_messages: List[AgentMessage]
    - compacted_messages: List[AgentMessage]
    - summary_content: Optional[str]
    - tokens_saved: int
    - messages_removed: int
    - error_message: Optional[str]

  CompactionSummary:
    - content: str
    - original_message_count: int
    - timestamp: float
    - metadata: Dict[str, Any]
    - to_message() -> AgentMessage (with context["is_compaction_summary"] flag)
  ```

- **Compression Workflow:**
  1. Check if `total_tokens > usable_context` (80% of window by default)
  2. Select messages to compress: keep recent N messages, compress the rest
  3. Format old messages for LLM
  4. Generate summary using LLM (or simple fallback)
  5. Create `CompactionSummary` message with:
     ```python
     content = "[Session Summary - Previous {N} messages compacted]\n{summary}"
     context["is_compaction_summary"] = True
     role = "system"
     ```
  6. Build new message list: [system messages] + [summary] + [recent messages]
  7. Track metrics: `tokens_saved`, `messages_removed`

- **Token Estimation:**
  - Simple estimation: `tokens ≈ len(text) / 4` (chars_per_token)
  - Estimates input, cached, and output tokens separately

#### 2. **`packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_components/context_compactor.py`**
- **Main Class:** `ContextCompactor` (Simplified v2 version)
- **Key Methods:**
  - `needs_compaction()` - Check if compression needed
  - `compact()` - Execute compression
  - `_generate_summary()` - LLM-based summarization
  - `_simple_summary()` - Fallback summary
  - `_build_compacted_messages()` - Build new message list
  - `_simple_compact()` - Simple compression (keep last N)
  - `get_statistics()` - Return stats

- **Features:**
  - Works with dict-based messages
  - Optional LLM integration for summaries
  - Fallback to simple compaction (last 10 messages)
  - Logging with `[Compactor]` prefix

- **Configuration:**
  ```python
  - max_tokens: int = 128000
  - threshold_ratio: float = 0.8
  - enable_summary: bool = True
  ```

#### 3. **`packages/derisk-core/src/derisk/agent/shared/hierarchical_context/hierarchical_compactor.py`**
- **Main Class:** `HierarchicalCompactor`
- **Purpose:** Chapter-based compression with structured templates
- **Key Features:**
  - Chapter-level summarization
  - Section-level compression
  - Multi-section compaction
  - Structured templates (Goal, Accomplished, Discoveries, Remaining, Relevant Files)

- **Data Class:**
  ```python
  CompactionTemplate:
    - CHAPTER_SUMMARY_TEMPLATE
    - SECTION_COMPACT_TEMPLATE
    - MULTI_SECTION_COMPACT_TEMPLATE

  CompactionResult:
    - success: bool
    - original_tokens: int
    - compacted_tokens: int
    - summary: Optional[str]
    - error: Optional[str]
  ```

#### 4. **`packages/derisk-core/src/derisk/agent/core/memory/compaction_pipeline.py`** (Unified v1/v2)
- **Main Class:** `HistoryCompactionPipeline`
- **Purpose:** Unified three-layer pipeline for both v1 and v2 agents
- **Architecture:**
  - Layer 1: `TruncationResult` - Truncate large outputs
  - Layer 2: `PruningResult` - Prune old outputs
  - Layer 3: `CompactionResult` - Compress entire session

- **Key Configuration:**
  ```python
  HistoryCompactionConfig:
    # Layer 1: Truncation
    max_output_lines: int = 2000
    max_output_bytes: int = 50 * 1024

    # Layer 2: Pruning
    prune_protect_tokens: int = 4000
    prune_interval_rounds: int = 5
    min_messages_keep: int = 10
    prune_protected_tools: Tuple[str, ...] = ("skill",)

    # Layer 3: Compaction + Archival
    context_window: int = 128000
    compaction_threshold_ratio: float = 0.8
    recent_messages_keep: int = 5
    chapter_max_messages: int = 100
    chapter_summary_max_tokens: int = 2000
    max_chapters_in_memory: int = 3

    # Content Protection
    code_block_protection: bool = True
    thinking_chain_protection: bool = True
    file_path_protection: bool = True
  ```

- **Message Adapter:** `UnifiedMessageAdapter` - Works with v1/v2 messages
- **Archival:** `HistoryChapter`, `HistoryCatalog` - Archive compressed chapters

### Logging Points (Compaction)
```
Level: INFO
"Context overflow detected: {estimate.total_tokens} tokens (threshold: {self.usable_context})"
"Starting session compaction for {len(messages)} messages"
"No messages to compact"
"Compaction completed: removed {result.messages_removed} messages, saved ~{tokens_saved} tokens, current message count: {len(compacted_messages)}"
"[Compactor] 压缩上下文: {original_count}条 -> {len(new_messages)}条, 节省 {tokens_saved} tokens"

Level: ERROR
"Failed to generate summary: {e}"
```

---

## Cross-Layer Integration

### Message Flow
```
Tool Output
    ↓
[LAYER 1: Truncation]
  - Check: original_bytes > max_bytes OR original_lines > max_lines?
  - Action: Truncate + Save to AFS + Append suggestion
    ↓
LLM Call (with truncated output)
    ↓
Message History Accumulates
    ↓
[LAYER 2: Pruning] (Periodic, e.g., every 5 rounds)
  - Check: cumulative_tokens > prune_protect?
  - Action: Mark old outputs as "compacted" with placeholder
    ↓
Message History Continues
    ↓
[LAYER 3: Compaction] (When needed)
  - Check: total_tokens > context_window * threshold_ratio?
  - Action: Summarize history + Archive chapters + Keep recent
    ↓
Lighter Context for Next Call
```

### Metadata Tracking
```python
# Truncation
TruncationResult.file_key → Used to retrieve full content later
TruncationResult.suggestion → Hints for agent how to access full output

# Pruning
AgentMessage.context["compacted"] = True
AgentMessage.context["compacted_at"] = timestamp
AgentMessage.context["original_summary"] = brief_summary
AgentMessage.content = "[内容已压缩: {type}] {summary}..."

# Compaction
AgentMessage.context["is_compaction_summary"] = True
AgentMessage.context["compacted_roles"] = list of roles compressed
AgentMessage.context["compaction_timestamp"] = timestamp
AgentMessage.role = "system"
AgentMessage.content = "[Session Summary - Previous N messages compacted]\n{summary}"
```

---

## File Organization Summary

### ReActMasterAgent (expand/)
```
packages/derisk-core/src/derisk/agent/expand/react_master_agent/
├── truncation.py              # Layer 1: Tool output truncation (AFS-aware)
├── prune.py                   # Layer 2: History pruning (with message classification)
├── session_compaction.py      # Layer 3: Session compression (LLM-based)
├── doom_loop_detector.py      # Bonus: Detect infinite tool loops
├── react_master_agent.py      # Unified ReAct agent with all features
└── README.md                  # Comprehensive documentation
```

### Core v2 (core_v2/)
```
packages/derisk-core/src/derisk/agent/core_v2/
├── builtin_agents/react_components/
│   ├── output_truncator.py      # Layer 1: Simplified truncation
│   ├── history_pruner.py        # Layer 2: Simplified pruning
│   ├── context_compactor.py     # Layer 3: Simplified compaction
│   └── doom_loop_detector.py
├── memory_compaction.py          # Alternative compaction implementation
└── improved_compaction.py        # Enhanced compaction with protection
```

### Hierarchical Context (shared/)
```
packages/derisk-core/src/derisk/agent/shared/hierarchical_context/
├── hierarchical_compactor.py      # Layer 3: Chapter-based compression
├── compaction_config.py           # Configuration for hierarchical compression
├── hierarchical_context_index.py  # Chapter/Section/Task structure
└── tests/
    └── test_hierarchical_context.py
```

### Unified Pipeline (core/)
```
packages/derisk-core/src/derisk/agent/core/
├── memory/
│   ├── compaction_pipeline.py     # Layer 1+2+3: Unified pipeline
│   ├── message_adapter.py         # UnifiedMessageAdapter for v1/v2
│   ├── history_archive.py         # Chapter archival system
│   └── compaction_pipeline.py
```

---

## Key Differences: expand vs core_v2

| Feature | expand/react_master_agent | core_v2 |
|---------|--------------------------|---------|
| Truncation | AgentFileSystem-aware with `file_key` | Simple temp file save |
| Pruning | MessageClassifier with MessageType enum | Simple string matching |
| Compaction | LLM-based + fallback simple summary | Optional LLM + simple compact |
| Message Format | AgentMessage with rich context | Dict-based messages |
| Complexity | High (production-ready) | Medium (simplified) |
| Async Support | Full async/sync modes | Limited async |
| Token Estimation | Detailed (input/cached/output) | Simple (total only) |

---

## Test Coverage

### Test Files Found
```
packages/derisk-core/tests/agent/test_history_compaction.py
packages/derisk-core/tests/agent/core_v2/test_complete_refactor.py
packages/derisk-core/src/derisk/agent/shared/hierarchical_context/tests/test_hierarchical_context.py
```

---

## Configuration Patterns

### Environment Variables / Config Files
- Truncation config: `max_lines`, `max_bytes`
- Pruning config: `prune_protect`, `min_messages_keep`, `max_messages_keep`
- Compaction config: `context_window`, `threshold_ratio`, `recent_messages_keep`
- All stored in respective `Config` dataclasses

### Default Values
- **Truncation:** 50 lines max, 5KB bytes max (expand) / 2000 lines, 50KB (v2)
- **Pruning:** 4000 tokens protect threshold, keep 5-50 messages
- **Compaction:** 128K context window, 80% threshold, keep 3-5 recent messages

---

## Logging Summary

All three layers use Python's `logging` module:
- **Logger name:** `derisk.agent.expand.react_master_agent` or `derisk.agent.core_v2...`
- **Log levels:**
  - `INFO`: Normal operations (truncation, pruning, compaction events)
  - `ERROR`: Failures (file save errors, LLM generation failures)
  - `WARNING`: Degradation (falling back to legacy mode, LLM unavailable)

Typical logging setup:
```python
import logging
logger = logging.getLogger(__name__)
logger.info(f"[ComponentName] Operation details")
logger.error(f"[ComponentName] Error details")
```

---

## Next Steps for Implementation

1. **Identify logging insertion points** in each layer
2. **Verify AgentFileSystem integration** in truncation layer
3. **Check message metadata handling** in pruning/compaction
4. **Test end-to-end flow** with long conversations
5. **Add monitoring/metrics** around compression effectiveness
