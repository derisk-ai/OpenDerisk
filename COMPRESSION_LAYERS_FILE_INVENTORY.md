# Compression Layers - File Inventory

## Created Analysis Documents

1. **COMPRESSION_LAYERS_MAPPING.md** - Comprehensive architecture document
   - Detailed analysis of all three layers
   - Code structure and implementation patterns
   - Cross-layer integration
   - Message metadata tracking

2. **COMPRESSION_LAYERS_QUICK_REFERENCE.md** - Quick lookup guide
   - One-page reference for each layer
   - Configuration parameters
   - Logging patterns
   - Integration examples

---

## File Organization by Layer

### Layer 1: Truncation (Tool Output Truncation)

**Primary Implementation:**
```
packages/derisk-core/src/derisk/agent/expand/react_master_agent/truncation.py
- Main class: Truncator
- Features: AgentFileSystem integration, async/sync modes, legacy fallback
- Default limits: 50 lines, 5KB
- Storage: AFS (modern) or ~/.opencode/tool-output (legacy)
```

**Simplified Version (v2):**
```
packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_components/output_truncator.py
- Main class: OutputTruncator
- Features: Auto temp directory, simple file save/load
- Default limits: 2000 lines, 50KB
- Storage: Temp directory only
```

---

### Layer 2: Pruning (History Record Pruning)

**Primary Implementation:**
```
packages/derisk-core/src/derisk/agent/expand/react_master_agent/prune.py
- Main class: HistoryPruner
- Features: Message classification, metadata preservation, token-based strategy
- Threshold: 4000 tokens
- Keeps: 5-50 messages (configurable)
- Markers: context["compacted"], context["compacted_at"], context["original_summary"]
```

**Simplified Version (v2):**
```
packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_components/history_pruner.py
- Main class: HistoryPruner
- Features: Dict-based messages, logarithmic output spacing
- Threshold: max_tool_outputs count
- Storage: In-memory only
```

---

### Layer 3: Compaction (Session Compression + Archival)

**Primary Implementation - LLM-Based:**
```
packages/derisk-core/src/derisk/agent/expand/react_master_agent/session_compaction.py
- Main class: SessionCompaction
- Features: LLM-based summarization, token estimation, fallback summary
- Threshold: 128K context × 0.8 = 102.4K tokens
- Result: CompactionSummary message with context["is_compaction_summary"]
```

**Simplified Version (v2):**
```
packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_components/context_compactor.py
- Main class: ContextCompactor
- Features: Optional LLM, fallback to keeping last N messages
- Threshold: max_tokens × threshold_ratio
```

**Advanced - Chapter-Based:**
```
packages/derisk-core/src/derisk/agent/shared/hierarchical_context/hierarchical_compactor.py
- Main class: HierarchicalCompactor
- Features: Structured templates (Goal, Accomplished, Discoveries, Remaining, Files)
- Purpose: LLM-based chapter summarization
```

**Unified Pipeline (v1 + v2):**
```
packages/derisk-core/src/derisk/agent/core/memory/compaction_pipeline.py
- Main class: HistoryCompactionPipeline
- Purpose: Combines all three layers with message adapter
- Features: Content protection (code blocks, thinking chains), recovery tools
```

---

## Supporting Infrastructure

### Message Handling
```
packages/derisk-core/src/derisk/agent/core/memory/
├── message_adapter.py          # UnifiedMessageAdapter for v1/v2 compatibility
├── history_archive.py          # HistoryChapter, HistoryCatalog for archival
└── compaction_pipeline.py      # Unified pipeline implementation
```

### Hierarchical Context
```
packages/derisk-core/src/derisk/agent/shared/hierarchical_context/
├── hierarchical_context_index.py       # Chapter, Section, TaskPhase data structures
├── hierarchical_context_manager.py     # Context lifecycle management
├── compaction_config.py                # Configuration
├── content_prioritizer.py              # Priority-based selection
└── tests/test_hierarchical_context.py  # Test coverage
```

### ReActMasterAgent
```
packages/derisk-core/src/derisk/agent/expand/react_master_agent/
├── __init__.py                         # Public API
├── react_master_agent.py               # Unified agent (all features)
├── doom_loop_detector.py               # Bonus: infinite loop detection
├── truncation.py                       # Layer 1
├── prune.py                            # Layer 2
├── session_compaction.py               # Layer 3
└── README.md                           # Comprehensive documentation
```

### Core v2 Components
```
packages/derisk-core/src/derisk/agent/core_v2/
├── builtin_agents/react_components/
│   ├── output_truncator.py             # Layer 1 (simplified)
│   ├── history_pruner.py               # Layer 2 (simplified)
│   ├── context_compactor.py            # Layer 3 (simplified)
│   └── doom_loop_detector.py
├── memory_compaction.py                # Alternative compaction
├── improved_compaction.py              # Enhanced with protection
└── context_processor.py                # Message processing utilities
```

---

## Key Classes & Methods

### Truncation
```python
# expand/react_master_agent/truncation.py
Truncator:
  - truncate(content, tool_name, max_lines, max_bytes) → TruncationResult
  - truncate_async(...) → TruncationResult (async)
  - read_truncated_content(file_key) → str
  - _save_via_agent_file_system(...) → (file_key, local_path)
  
TruncationResult:
  - content: str (truncated)
  - is_truncated: bool
  - file_key: str (AFS identifier)
  - suggestion: str (agent hint)

# core_v2/builtin_agents/react_components/output_truncator.py
OutputTruncator:
  - truncate(content, tool_name) → TruncationResult
  - _save_full_output(content, tool_name) → str (file_path)
```

### Pruning
```python
# expand/react_master_agent/prune.py
HistoryPruner:
  - prune(messages) → PruneResult
  - prune_action_outputs(outputs, max_length) → List[ActionOutput]
  - _get_prunable_indices(messages, metrics) → List[int]
  - _mark_compacted(message) → AgentMessage (modified)

MessageClassifier:
  - classify(message) → MessageType
  - is_essential(message) → bool

PruneResult:
  - removed_count: int
  - tokens_saved: int
  - pruned_message_ids: List[str]

# core_v2/builtin_agents/react_components/history_pruner.py
HistoryPruner:
  - prune(messages) → PruneResult
  - needs_prune(messages) → bool
```

### Compaction
```python
# expand/react_master_agent/session_compaction.py
SessionCompaction:
  - is_overflow(messages, estimated_output_tokens) → (bool, TokenEstimate)
  - compact(messages, force=False) → CompactionResult
  - _generate_summary(messages) → str
  - _generate_simple_summary(messages) → str (fallback)

CompactionResult:
  - success: bool
  - summary_content: str
  - tokens_saved: int
  - messages_removed: int

# core_v2/builtin_agents/react_components/context_compactor.py
ContextCompactor:
  - needs_compaction(messages) → bool
  - compact(messages, llm_adapter) → CompactionResult
  - _generate_summary(messages, llm_adapter) → str
```

---

## Data Flow

```
User Input
    ↓
Tool Execution
    ↓
Large Output (e.g., 100KB, 5000 lines)
    ↓
┌─────────────────────────────────────┐
│ LAYER 1: Truncation                 │
│ - Check: size > threshold?          │
│ - Action: Truncate + Save to AFS    │
│ - Result: Small output + file_key   │
└─────────────────────────────────────┘
    ↓
Send Truncated Output to LLM
    ↓
Message History Accumulates
    ├─ User message
    ├─ Truncated tool output
    ├─ Assistant response
    └─ (repeat N times)
    ↓
(Periodic check every N rounds)
    ↓
┌─────────────────────────────────────┐
│ LAYER 2: Pruning                    │
│ - Check: cumulative tokens > 4000?  │
│ - Action: Mark old outputs as [压缩]│
│ - Result: Lighter history in RAM    │
└─────────────────────────────────────┘
    ↓
Continue Conversation
    ├─ User message
    ├─ Compressed tool output (placeholder)
    ├─ Assistant response
    └─ (repeat many times)
    ↓
(When needed)
    ↓
┌─────────────────────────────────────┐
│ LAYER 3: Compaction                 │
│ - Check: total tokens > 80% window? │
│ - Action: Summarize + Archive       │
│ - Result: Fresh context window      │
└─────────────────────────────────────┘
    ↓
[Compaction Summary Message] + Recent Messages
    ↓
Fresh context for next LLM call
```

---

## Logging Locations

### Layer 1 - Truncation
```
truncation.py:
  Line ~237-241: logger.info() - "Truncating output for {tool_name}..."
  Line ~138-141: logger.info() - "[AFS] Saved truncated output..."
  Line ~175: logger.error() - "Failed to save truncated output..."
  
output_truncator.py:
  Line ~59: logger.info() - "[Truncator] 输出目录: {dir}"
  Line ~130-133: logger.info() - "[Truncator] 截断输出: {lines}行 -> {count}行"
  Line ~159: logger.info() - "[Truncator] 保存完整输出: {path}"
  Line ~163: logger.error() - "[Truncator] 保存失败: {e}"
  Line ~187: logger.info() - "[Truncator] 清理输出目录: {dir}"
```

### Layer 2 - Pruning
```
prune.py:
  Line ~328-330: logger.info() - "Pruning history: {count} messages..."
  Line ~337: logger.info() - "No messages eligible for pruning"
  Line ~376-378: logger.info() - "Pruning completed: marked {count} messages..."
  
history_pruner.py:
  Line ~85-88: logger.info() - "[Pruner] 修剪历史: {count}条 -> {count}条"
```

### Layer 3 - Compaction
```
session_compaction.py:
  Line ~248-250: logger.info() - "Context overflow detected: {tokens} tokens"
  Line ~406: logger.info() - "Starting session compaction for {count} messages"
  Line ~412: logger.info() - "No messages to compact"
  Line ~472-475: logger.info() - "Compaction completed: removed {count}..."
  Line ~333: logger.error() - "Failed to generate summary: {e}"
  
context_compactor.py:
  Line ~96-99: logger.info() - "[Compactor] 压缩上下文: {count}条 -> {count}条"
  Line ~139: logger.error() - "[Compactor] 生成摘要失败: {e}"
```

---

## Configuration Hierarchy

```
HistoryCompactionConfig (core/memory/compaction_pipeline.py)
  ├─ TruncationConfig (expand/react_master_agent/)
  ├─ PruneConfig (expand/react_master_agent/)
  ├─ CompactionConfig (expand/react_master_agent/)
  └─ Hierarchical templates (shared/hierarchical_context/)

Individual component configs:
  - OutputTruncator.__init__(max_lines, max_bytes)
  - HistoryPruner.__init__(prune_protect, min_messages_keep)
  - ContextCompactor.__init__(max_tokens, threshold_ratio)
```

---

## Testing

```
Test Files:
- packages/derisk-core/tests/agent/test_history_compaction.py
- packages/derisk-core/tests/agent/core_v2/test_complete_refactor.py
- packages/derisk-core/src/derisk/agent/shared/hierarchical_context/tests/test_hierarchical_context.py

Run tests:
  python -m pytest packages/derisk-core/tests/agent/ -v
  python -m pytest packages/derisk-core/src/derisk/agent/shared/hierarchical_context/tests/ -v
```

---

## Integration Paths

### Path 1: Using ReActMasterAgent (All-in-One)
```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

agent = ReActMasterAgent(
    enable_output_truncation=True,
    enable_history_pruning=True,
    enable_session_compaction=True,
)
# All three layers automatically applied
```

### Path 2: Using Core v2 Components (Pick & Choose)
```python
from derisk.agent.core_v2.builtin_agents.react_components import (
    OutputTruncator,
    HistoryPruner,
    ContextCompactor,
)

truncator = OutputTruncator(max_lines=2000)
pruner = HistoryPruner(max_tool_outputs=20)
compactor = ContextCompactor(max_tokens=128000)
```

### Path 3: Using Unified Pipeline (v1 + v2)
```python
from derisk.agent.core.memory.compaction_pipeline import (
    HistoryCompactionPipeline,
    HistoryCompactionConfig,
)

config = HistoryCompactionConfig()
pipeline = HistoryCompactionPipeline(config)
```

### Path 4: Using Hierarchical Compaction
```python
from derisk.agent.shared.hierarchical_context import HierarchicalCompactor

compactor = HierarchicalCompactor()
# Chapter-based compression with structured templates
```

---

## Summary Statistics

- **Total Layer 1 files:** 2 (expand + v2)
- **Total Layer 2 files:** 2 (expand + v2)
- **Total Layer 3 files:** 4 (expand + v2 + hierarchical + unified)
- **Supporting infrastructure:** ~10 files
- **Total compression-related files:** ~20
- **Lines of code:** ~3000+ lines

---

## Next Steps

1. ✅ Map all compression layer files (DONE)
2. ✅ Document architecture (DONE)
3. ✅ Create quick reference (DONE)
4. ⬜ Add logging instrumentation points
5. ⬜ Create monitoring dashboard
6. ⬜ Add recovery/debugging tools
7. ⬜ Performance benchmarking
8. ⬜ Integration tests for long conversations

---

## Quick Commands for Navigation

```bash
# Find all truncation-related files
grep -r "class Truncator" packages/derisk-core/src/

# Find all pruning-related files
grep -r "class.*Pruner" packages/derisk-core/src/

# Find all compaction-related files
grep -r "class.*Compaction" packages/derisk-core/src/

# Find logging statements
grep -r "logger.info" packages/derisk-core/src/derisk/agent/ | grep -E "(Truncat|Prun|Compact)"

# Check all config classes
grep -r "@dataclass" packages/derisk-core/src/derisk/agent/expand/react_master_agent/ | grep -i config

# Run compression tests
python -m pytest packages/derisk-core/tests/agent/test_history_compaction.py -v
```
