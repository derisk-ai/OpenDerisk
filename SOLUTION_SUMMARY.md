# Solution Summary for ReActMasterV2 Issues

## Executive Summary

Three critical issues identified and analyzed:

1. ✅ **Issue #1: Skill Loading** - RESOLVED
2. ⚠️ **Issue #2: Frontend Rendering** - Root cause identified, fix required
3. ⚠️ **Issue #3: Tool Call Truncation** - Likely caused by Issue #1, needs testing

---

## Issue #1: Skill Not Loaded Into Prompt ✅ RESOLVED

### Problem
- App configuration referenced skill with code `open-rca-diagnosis`
- Database had skill with code `open-rca-diagnosis-2-0-derisk-c5b0e208`
- Mismatch caused skill loading to fail

### Solution Applied
✅ App configuration updated with correct skill_code

### Verification
```bash
python3 diagnose_reactmaster.py
```

**Result**: All checks passed ✓

### Impact
- Skill metadata now loads into agent prompt
- Agent has access to domain knowledge
- Tool availability restored

### Next Steps
1. **Restart the server** to apply changes
2. Monitor agent initialization logs for:
   ```
   [ReActReasoningAgent] 资源预加载完成: tools_count=X, resource_prompt_len=Y
   ```
   Y should be > 0 (previously was 0)

---

## Issue #2: Frontend Running Window Not Displaying Tasks ⚠️

### Problem Identified

**Backend Data Structure** (`WorkSpaceContent`):
```python
{
  "uid": "session_id",
  "type": "INCR",
  "running_agents": ["AgentName"],
  "items": [
    FolderNode(  # ⬅️ FLAT LIST of task items
      uid="task_1",
      title="Search for logs",
      task_type="tool",
      markdown="...",
      ...
    ),
    FolderNode(
      uid="task_2",
      title="Read file",
      task_type="tool",
      ...
    )
  ],
  "explorer": "..."
}
```

**Frontend Expected Structure** (`VisRunningWindow`):
```typescript
{
  items: [  // ⬅️ NESTED by agent
    {
      agent_name: "AgentName",
      avatar: "...",
      items: [  // ⬅️ ACTUAL task items
        { uid: "task_1", title: "Search", ... },
        { uid: "task_2", title: "Read", ... }
      ]
    }
  ],
  running_agent: "AgentName"
}
```

### Root Cause

**Data Structure Mismatch**:

1. Backend sends **flat list** of all task items
2. Frontend expects **nested structure** grouped by agent
3. Frontend tries to group by `agent_name`:
   ```typescript
   const runningAgents = keyBy(dataItems, 'agent_name');
   ```
   But `FolderNode` doesn't have `agent_name` field!

### Solution Options

#### Option A: Fix Frontend (Recommended)
Update `VisRunningWindow` to handle flat task list:

```typescript
// Current (Wrong):
const runningAgents = keyBy(dataItems, 'agent_name');
// runningAgents = {} because dataItems don't have agent_name

// Fixed:
const runningAgents = useMemo(() => {
  // Treat the entire items array as belonging to current agent
  const agentName = Array.isArray(data.running_agent) 
    ? data.running_agent[0] 
    : data.running_agent;
  
  return {
    [agentName]: {
      agent_name: agentName,
      items: dataItems,  // Use items directly
      avatar: dataItems[0]?.avatar
    }
  };
}, [dataItems, data.running_agent]);
```

#### Option B: Fix Backend
Group task items by agent before sending:

```python
# In derisk_vis_window3_converter.py

async def _running_vis_build(...):
    # Group items by agent
    agent_items_map = {}
    for item in work_items:
        agent_name = item.agent_name or main_agent_name
        if agent_name not in agent_items_map:
            agent_items_map[agent_name] = {
                "agent_name": agent_name,
                "avatar": item.avatar,
                "items": []
            }
        agent_items_map[agent_name]["items"].append(item)
    
    work_space_content = WorkSpaceContent(
        uid=conv_session_id,
        type=UpdateType.INCR.value,
        running_agents=running_agents,
        items=list(agent_items_map.values()),  # ⬅️ Grouped by agent
        explorer=...
    )
```

### Recommended Fix
**Option A (Frontend)** is better because:
1. Simpler change
2. Maintains current backend architecture
3. Frontend already has all the data it needs

### Implementation (Frontend Fix)

File: `web/src/components/chat/chat-content-components/VisComponents/VisRunningWindow/index.tsx`

```typescript
// Replace line 48:
const runningAgents = useMemo(() => {
  // Handle flat task list from backend
  const currentAgentName = Array.isArray(data.running_agent) 
    ? data.running_agent[0] 
    : data.running_agent;
  
  if (!currentAgentName || !dataItems) {
    return {};
  }
  
  // Group all items under the current running agent
  return {
    [currentAgentName]: {
      agent_name: currentAgentName,
      items: dataItems,
      avatar: dataItems[0]?.avatar,
      description: dataItems[0]?.description
    }
  };
}, [dataItems, data.running_agent]);
```

---

## Issue #3: Agent Generating Pure Text Without Tool Calls ⚠️

### Root Cause Analysis

**Symptom**: Agent outputs text instead of calling tools

**Root Causes**:
1. **Primary**: Skill not loaded (Issue #1) ❌
   - Agent lacks domain knowledge
   - Missing resource prompt guidance
   - Doesn't know available tools

2. **Secondary**: System prompt may not be compelling enough

3. **Potential**: LLM model (DeepSeek-V3) function calling behavior

### Expected Fix Impact

After resolving Issue #1 (skill loading), the agent should:
1. ✅ Have skill metadata in system prompt
2. ✅ Know available tools and when to use them
3. ✅ Generate tool calls instead of pure text

### Testing After Restart

**Test 1: Check Agent Initialization**
```bash
# Look for these log lines:
[ReActReasoningAgent] 检测到Skill资源，注入skill工具
[ReActReasoningAgent] 资源预加载完成: tools_count=X, resource_prompt_len=Y
```
Expected: Y > 0 (resource prompt should contain skill metadata)

**Test 2: Check Tool Definitions**
```bash
# Look for:
[ReActReasoningAgent] 调用 LLM: 消息数=X, 工具数=Y
```
Expected: Y > 6 (base tools + skill tools)

**Test 3: Check Tool Calls**
```bash
# Look for:
[ReActReasoningAgent] 工具调用: {tool_name}
```
Expected: See tool calls instead of "LLM 返回纯文本回答"

### Additional Fixes (If Still Failing)

If tool calls still not generated after Issue #1 is resolved:

**Fix A: Strengthen System Prompt**

File: `packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_reasoning_agent.py`

```python
REACT_REASONING_SYSTEM_PROMPT = """你是一个遵循 ReAct (推理+行动) 范式的智能 AI 助手，用于解决复杂任务。

## 核心原则

⚠️ **强制要求**：每轮必须调用工具！
- 禁止直接返回纯文本回答
- 禁止在未调用工具的情况下结束
- 必须使用工具来执行任务

## 工作流程

1. 分析任务需求
2. **立即调用工具**执行
3. 分析工具结果
4. 继续调用工具直到完成

... (rest of prompt)
"""
```

**Fix B: Verify LLM Model Supports Function Calling**

Check if DeepSeek-V3 supports function calling:
- If not, switch to a model that does (e.g., GPT-4, Claude)
- Or implement fallback to text-based tool invocation

---

## Action Plan

### Immediate (Now)
1. ✅ Issue #1 resolved - configuration updated
2. 🔄 Restart server to apply skill loading fix
3. ⏱️ Test agent behavior (Issue #3 should resolve)

### Short Term (Today)
4. 📝 Implement frontend fix for Issue #2
5. 🧪 Test running window display
6. 📊 Monitor agent tool call patterns

### Verification Checklist

```bash
# 1. Restart server
pkill -f "python.*derisk_server"
uv run python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/derisk-proxy-aliyun.toml

# 2. Check initialization logs
# Look for skill loading success

# 3. Test agent conversation
curl -X POST http://localhost:7777/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"user_input":"分析一个故障","conv_uid":"test-123","app_code":"rca-openrca"}'

# 4. Check frontend
# Open http://localhost:7777
# Navigate to RCA(OpenRCA) app
# Send a message
# Verify running window shows task items
```

---

## Expected Results

After implementing all fixes:

1. ✅ **Skill Loading**: Agent has domain knowledge and tools
2. ✅ **Frontend Rendering**: Running window displays task list correctly
3. ✅ **Tool Calls**: Agent generates tool calls instead of pure text

---

## Files Modified

1. ✅ `packages/derisk-serve/src/derisk_serve/building/app/service/derisk_app_define/rca_openrca_app.json`
   - Updated skill_code to match database

2. ⏱️ `web/src/components/chat/chat-content-components/VisComponents/VisRunningWindow/index.tsx`
   - Needs frontend data structure fix (Issue #2)

---

## Monitoring Points

After restart, monitor these logs:

```bash
# Skill loading
grep "检测到Skill资源" logs/derisk.log
grep "资源预加载完成" logs/derisk.log

# Tool calling
grep "调用 LLM" logs/derisk.log
grep "工具调用" logs/derisk.log

# Errors
grep -i "error\|exception\|failed" logs/derisk.log
```

---

## Rollback Plan

If issues persist:

1. **Rollback Skill Config**:
   ```json
   // Revert to original skill_code if needed
   "skillCode": "open-rca-diagnosis"
   ```

2. **Check Database**:
   ```sql
   -- Verify skill exists
   SELECT * FROM server_app_skill WHERE name='open_rca_diagnosis';
   ```

3. **Check Skill Files**:
   ```bash
   ls -la pilot/data/skill/open_rca_diagnosis/
   ```

---

## Support

If issues persist after implementing fixes:

1. Check server logs for errors
2. Verify skill files exist and are readable
3. Test with a simpler app to isolate issues
4. Review agent initialization logs in detail

**Debug Mode**: Enable verbose logging
```python
# In derisk_server.py
import logging
logging.basicConfig(level=logging.DEBUG)
```