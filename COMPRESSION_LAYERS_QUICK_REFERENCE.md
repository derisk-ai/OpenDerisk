# Compression Layers - Quick Reference

## Three-Layer Architecture

### Layer 1: Truncation (🔪 Immediate)
**When:** Large single tool output
**Action:** Cut output, save full content elsewhere
**Files:**
- `packages/derisk-core/src/derisk/agent/expand/react_master_agent/truncation.py` (Main, AFS-aware)
- `packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_components/output_truncator.py` (Simplified)

**Key Classes:**
- `Truncator` → `truncate()`
- `OutputTruncator` → `truncate()`
- `TruncationResult`: content, is_truncated, file_key, suggestion

**Default Limits:**
- expand: 50 lines, 5KB
- v2: 2000 lines, 50KB

**Output Storage:**
- AgentFileSystem (preferred, file_key-based)
- Local temp dir (fallback, path-based)

---

### Layer 2: Pruning (✂️ Periodic)
**When:** Message history accumulates
**Action:** Mark old tool outputs with placeholder, keep summary
**Files:**
- `packages/derisk-core/src/derisk/agent/expand/react_master_agent/prune.py` (Main, rich classification)
- `packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_components/history_pruner.py` (Simplified)

**Key Classes:**
- `HistoryPruner` → `prune(messages)`
- `PruneResult`: removed_count, tokens_saved, pruned_message_ids
- `MessageClassifier`: Classify msg type, determine if essential

**Pruning Decision:**
1. From newest to oldest
2. Keep latest 5-10 messages (essential)
3. When cumulative tokens > 4000: mark older outputs as `[内容已压缩]`
4. Preserve in context: `compacted=True`, `original_summary`, `compacted_at`

**Protected Messages:**
- System messages
- User/human messages
- Recent messages
- Messages marked as critical/summary

---

### Layer 3: Compaction (📦 On Demand)
**When:** Context window near limit
**Action:** Summarize old messages + archive chapters
**Files:**
- `packages/derisk-core/src/derisk/agent/expand/react_master_agent/session_compaction.py` (Main, LLM-based)
- `packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_components/context_compactor.py` (Simplified)
- `packages/derisk-core/src/derisk/agent/shared/hierarchical_context/hierarchical_compactor.py` (Advanced, chapter-based)
- `packages/derisk-core/src/derisk/agent/core/memory/compaction_pipeline.py` (Unified v1+v2)

**Key Classes:**
- `SessionCompaction` → `is_overflow()`, `compact(messages)`
- `ContextCompactor` → `compact(messages)`
- `HierarchicalCompactor` → Chapter-based compression
- `CompactionResult`: success, summary_content, tokens_saved, messages_removed
- `CompactionSummary` → Converts to AgentMessage with `context["is_compaction_summary"]=True`

**Compression Logic:**
1. Check: `total_tokens > context_window * threshold_ratio` (80% default)
2. Keep recent 3-5 messages
3. Compress older messages via LLM → Summary text
4. Build new list: [system msgs] + [CompactionSummary] + [recent msgs]
5. Track: tokens_saved, messages_removed

**Thresholds:**
- Context window: 128K tokens
- Trigger ratio: 80% (102K tokens)
- Keep recent: 3-5 messages
- Estimated token: len(text) / 4

---

## Message Metadata Flags

### Truncation Metadata
```python
TruncationResult:
  file_key: "tool_output_read_xyz123_1"     # For AFS retrieval
  suggestion: "[输出已截断]\n原始输出包含 5000 行..."  # Hint for agent
```

### Pruning Metadata
```python
message.context:
  "compacted": True                           # Marked for compression
  "compacted_at": "2025-01-15T10:30:00"      # When compressed
  "original_summary": "First 100 chars..."   # Brief summary
  
message.content: "[内容已压缩: tool_output] First 100 chars..."  # Placeholder
```

### Compaction Metadata
```python
message.context:
  "is_compaction_summary": True               # Summary message flag
  "compacted_roles": ["assistant", "tool"]   # Original roles compressed
  "compaction_timestamp": 1705318400.0       # When compressed

message.role: "system"                        # Always system role
message.content: "[Session Summary - Previous 42 messages compacted]\n{summary}"
```

---

## Configuration Reference

### Truncation Config
```python
TruncationConfig:
  DEFAULT_MAX_LINES = 50          # expand version
  DEFAULT_MAX_BYTES = 5 * 1024    # 5KB
  
OutputTruncator (v2):
  max_lines = 2000
  max_bytes = 50000
```

### Pruning Config
```python
PruneConfig:
  DEFAULT_PRUNE_PROTECT = 4000             # Token threshold
  TOOL_OUTPUT_THRESHOLD_RATIO = 0.6        # Tool output ratio
  MESSAGE_EXPIRY_SECONDS = 1800            # 30 minutes
  MIN_MESSAGES_KEEP = 5                    # Minimum to preserve
  MAX_MESSAGES_KEEP = 50                   # Maximum allowed
  PRUNE_STRATEGY = "token_based"
```

### Compaction Config
```python
CompactionConfig:
  DEFAULT_CONTEXT_WINDOW = 128000          # Tokens
  DEFAULT_THRESHOLD_RATIO = 0.8            # 80% trigger
  SUMMARY_MESSAGES_TO_KEEP = 5
  RECENT_MESSAGES_KEEP = 3
  CHARS_PER_TOKEN = 4                      # Token estimation
```

### Unified Pipeline Config (core/memory)
```python
HistoryCompactionConfig:
  # Layer 1
  max_output_lines = 2000
  max_output_bytes = 50 * 1024
  
  # Layer 2
  prune_protect_tokens = 4000
  prune_interval_rounds = 5
  min_messages_keep = 10
  prune_protected_tools = ("skill",)
  
  # Layer 3
  context_window = 128000
  compaction_threshold_ratio = 0.8
  recent_messages_keep = 5
  
  # Archival
  chapter_max_messages = 100
  chapter_summary_max_tokens = 2000
  max_chapters_in_memory = 3
  
  # Protection
  code_block_protection = True
  thinking_chain_protection = True
  file_path_protection = True
```

---

## Logging Quick Map

### Truncation Logs
```
✓ INFO: "Truncating output for {tool_name}: {lines} lines → {max_lines}"
✓ INFO: "[AFS] Saved truncated output via AgentFileSystem: key={file_key}"
✓ INFO: "[Truncator] 截断输出: {original}行 → {truncated}行"
✗ ERROR: "Failed to save truncated output: {e}"
```

### Pruning Logs
```
✓ INFO: "Pruning history: {count} messages, ~{tokens} tokens"
✓ INFO: "Pruning completed: marked {removed} messages as compacted, saved {saved} tokens"
ℹ INFO: "No messages eligible for pruning"
```

### Compaction Logs
```
✓ INFO: "Starting session compaction for {count} messages"
✓ INFO: "Compaction completed: removed {removed} messages, saved {saved} tokens"
ℹ INFO: "Context overflow detected: {tokens} tokens (threshold: {limit})"
✗ ERROR: "Failed to generate summary: {e}"
```

---

## Message Type Classification (Layer 2)

```python
MessageType (Enum):
  SYSTEM         # System messages → Always keep
  USER           # User/human → Always keep
  ASSISTANT      # Model response → Prune if old
  TOOL_OUTPUT    # Tool results → Prune candidate
  THINKING       # Reasoning steps → Prune candidate
  SUMMARY        # Compaction summary → Always keep
  OBSOLETE       # Already marked compacted → Skip
```

**Pruning Priority (highest to lowest):**
1. System messages (never prune)
2. Recent messages (protect_recent)
3. User messages (essential)
4. Summary messages (is_compaction_summary=True)
5. Thinking messages (medium priority)
6. Tool outputs (first to prune)
7. Obsolete messages (skip)

---

## File Storage Strategy

### AgentFileSystem Mode (expand/truncation.py)
```
Format: file_key = "tool_output_{tool_name}_{content_hash}_{counter}"
Example: "tool_output_read_abc12345_1"
Usage: read_truncated_content(file_key="tool_output_read_abc12345_1")
Storage: agent_storage/<conv_id>/ (local) or OSS (remote)
```

### Legacy Mode (both versions)
```
Format: file_path = "~/.opencode/tool-output/{tool_name}_{hash}_{counter}.txt"
Example: "~/.opencode/tool-output/read_abc12345_1.txt"
Usage: Full file path
Storage: Local filesystem only
```

---

## Integration Points

### With ReActMasterAgent
```python
# All three layers built-in
agent = ReActMasterAgent(
    enable_doom_loop_detection=True,
    enable_output_truncation=True,
    enable_history_pruning=True,
    enable_session_compaction=True,
)
```

### With Core v2
```python
# Component-based usage
truncator = OutputTruncator(max_lines=2000)
pruner = HistoryPruner(max_tool_outputs=20)
compactor = ContextCompactor(max_tokens=128000)
```

### With Unified Pipeline
```python
# All in one
pipeline = HistoryCompactionPipeline(config)
layer1_result = await pipeline.truncate(output, tool_name)
layer2_result = await pipeline.prune(messages)
layer3_result = await pipeline.compact(messages)
```

---

## Token Estimation

### Formula
```
estimated_tokens ≈ len(text_in_characters) / 4
```

### Components
- **Input tokens:** User messages + system prompts
- **Output tokens:** Estimated 500-1000 per response
- **Cached tokens:** Previous context (optional)
- **Total:** input + output + cached

### Thresholds
- **Prune trigger:** cumulative > 4000 tokens
- **Compact trigger:** total > 128000 * 0.8 = 102400 tokens

---

## Typical Flow Example

```
User Input: "Analyze this large file"
    ↓
Tool Call: read(path="/var/log/huge.log")
    ↓ 
[LAYER 1] Output = 100K bytes, 5000 lines
    → Truncate to 50 lines, 5KB
    → Save full content to AFS
    → Append suggestion: "Use file_key=tool_output_read_xyz123_1"
    ↓
LLM Response: "Based on the first 50 lines..."
    ↓
Message History: [user, read_truncated, assistant] = ~3K tokens
    ↓
User: "Do more analysis"
    ↓
Message History After 5 turns: ~15K tokens, 30 messages
    ↓
[LAYER 2] Prune Check (every 5 rounds)
    → Cumulative tool outputs = 6K tokens > 4K threshold
    → Mark turns 1-3 tool outputs as [内容已压缩]
    ↓
Message History: [user, summary, assistant] × 5 = ~8K tokens, 15 messages
    ↓
User: "Analyze 10 more files"
    ↓
Message History After 20 turns: ~110K tokens, 50 messages
    ↓
[LAYER 3] Compact Check
    → Total tokens = 110K > 102K threshold (80%)
    → Summarize turns 1-15
    → Create CompactionSummary message
    ↓
Message History: [system, summary, recent 5 turns] = ~50K tokens, 8 messages
    ↓
Next LLM Call: Fresh context window available
```

---

## Debugging Tips

1. **Check if truncation occurred:**
   ```python
   result = truncator.truncate(large_output, "my_tool")
   if result.is_truncated:
       print(f"Truncated: {result.file_key} has full content")
   ```

2. **Check if pruning marked messages:**
   ```python
   pruned = messages[i]
   if pruned.context.get("compacted"):
       print(f"Message was compressed at {pruned.context['compacted_at']}")
   ```

3. **Check if compaction happened:**
   ```python
   result = await compactor.compact(messages)
   if result.summary_content:
       print(f"Saved {result.tokens_saved} tokens")
   ```

4. **Enable debug logging:**
   ```python
   logging.basicConfig(level=logging.DEBUG)
   logger = logging.getLogger("derisk.agent")
   ```

---

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| File not found | Using old file_path | Use file_key with AFS |
| Too many messages | Pruning not triggered | Check prune_protect threshold |
| Compaction failed | LLM unavailable | Use fallback simple summary |
| Lost content | Output not saved | Enable AFS storage |
| Memory growing | Layer 1 not enabled | Enable truncation |

---

## Key Takeaways

✓ **Layer 1 (Truncation):** Immediate, per-tool-call compression  
✓ **Layer 2 (Pruning):** Periodic, message-level cleanup  
✓ **Layer 3 (Compaction):** On-demand, session-level summarization  
✓ **Three-layer approach:** Progressive compression = token savings without losing context  
✓ **AgentFileSystem:** Modern, unified file management with file_key references  
✓ **Message metadata:** Tracks what's compressed and how to retrieve it
