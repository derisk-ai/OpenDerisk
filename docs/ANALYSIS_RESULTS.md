# OpenDerisk ReActMasterV2 Issues Analysis

## Executive Summary

Three critical issues identified in the ReActMasterV2 + vis_window3 system:

1. **Skill Loading Failure**: Skill metadata not loaded into agent prompt
2. **Frontend Rendering Issue**: Running window not displaying task lists
3. **Tool Call Truncation**: Agent generating pure text without function calls

---

## Issue #1: Skill Not Loaded Into Prompt 🔴 CRITICAL

### Root Cause
**Skill Code Mismatch**

**Configuration** (`rca_openrca_app.json`):
```json
{
  "type": "skill(derisk)",
  "value": "{\"skill_name\":\"open_rca_diagnosis\",\"skillCode\":\"open-rca-diagnosis\"}"
}
```

**Database Reality** (`server_app_skill` table):
```sql
skill_code: "open-rca-diagnosis-2-0-derisk-c5b0e208"
name: "open_rca_diagnosis"
```

### Impact
- AgentSkillResource not initialized properly
- Skill metadata not added to system prompt
- Agent lacks domain knowledge and tools from skill

### Evidence Chain

1. **App Config** references `skill_name: "open_rca_diagnosis"`
2. **Database Query** by `skill_code = "open-rca-diagnosis"` returns empty
3. **Skill Loading** fails silently in `AgentSkillResource.__init__`
4. **Prompt Generation** returns "No Skills provided"

### Fix Required

**Option A: Update App Configuration** (Recommended)
```json
{
  "type": "skill(derisk)",
  "value": "{\"skill_name\":\"open_rca_diagnosis\",\"skillCode\":\"open-rca-diagnosis-2-0-derisk-c5b0e208\"}"
}
```

**Option B: Update Database**
```sql
UPDATE server_app_skill 
SET skill_code = 'open-rca-diagnosis' 
WHERE name = 'open_rca_diagnosis';
```

**Option C: Fix Skill Loader to Use `name` instead of `skill_code`**

---

## Issue #2: Frontend Running Window Not Displaying Tasks 🔴 CRITICAL

### Symptom
- Running window area shows no task lists
- Cannot see model tasks, tool task lists
- Task content not rendered

### Root Cause Analysis

#### Backend Data Flow
1. **vis_window3 Converter** (`derisk_vis_window3_converter.py`)
   - Generates `running_window` data with `WorkSpace` component
   - `WorkSpaceContent` structure:
     ```python
     {
       "uid": conv_session_id,
       "type": "INCR",
       "running_agents": [...],
       "items": [FolderNode...],  # Task items
       "explorer": "..."  # Agent folder tree
     }
     ```

2. **Data Generation** (`gen_work_item()`)
   - Creates `FolderNode` for each action/LLM call
   - Task types: `llm`, `tool`, `code`, `report`, `knowledge`
   - Each item has: `uid`, `title`, `description`, `status`, `markdown`

#### Frontend Rendering Logic

**VisRunningWindow Component** (`index.tsx`):
```typescript
interface RunningAgent {
  items?: any[];  // Task items
  agent_name?: string;
  markdown?: string;
}

// Data structure expected:
data = {
  items: RunningAgent[],  // Array of agent tasks
  running_agent: string | string[]
}
```

**Key Rendering Logic**:
```typescript
const runningAgents = keyBy(dataItems, 'agent_name');
// dataItems = data.items
// Each item should have: agent_name, items array

const hasItems = Array.isArray(items) && items.length > 0;

// If hasItems, render CoderWindow with tabs
// Otherwise render markdown directly
```

### Hypothesis

**Problem**: Backend sends `WorkSpaceContent.items` as `FolderNode[]`, but frontend expects `RunningAgent[]`

**Mismatch**:
- Backend sends: `{ items: [FolderNode{uid, title, task_type, markdown}] }`
- Frontend expects: `{ items: [RunningAgent{agent_name, items: [...]}] }`

### Investigation Needed

1. Check actual API response structure
2. Verify frontend parse-vis.ts transformation
3. Check if vis_window3 converter is using wrong data format

### Potential Fix

**Backend needs to transform**:
```python
# Current (Wrong):
work_space_content = WorkSpaceContent(items=[FolderNode...])

# Should be (Correct):
work_space_content = WorkSpaceContent(
  items=[
    RunningAgent(
      agent_name=agent_name,
      avatar=agent_avatar,
      items=[FolderNode...]  # Actual tasks
    )
  ]
)
```

---

## Issue #3: Agent Generating Pure Text Without Tool Calls 🟡 HIGH

### Symptom
- Multiple pure text outputs without tool calls
- Agent not executing tools as expected
- Truncated responses

### Root Cause Analysis

#### ReActReasoningAgent Flow

1. **think()** - LLM generation with function calling
   ```python
   response = await self.llm_client.generate(
       messages=messages,
       tools=tools,  # Tool definitions
       tool_choice="auto"
   )
   ```

2. **decide()** - Check for tool calls
   ```python
   if response.tool_calls:
       return Decision(type=TOOL_CALL, ...)
   else:
       return Decision(type=RESPONSE, content=response.content)
   ```

### Possible Causes

#### A. System Prompt Issues
```python
REACT_REASONING_SYSTEM_PROMPT = """...
## 立即行动
现在请调用工具开始执行任务！不要只是思考或总结。
"""
```
- Prompt may not be compelling enough
- Missing resource/skill prompts

#### B. LLM Model Issues
- **Model**: `DeepSeek-V3` (from app config)
- May not support function calling properly
- May need explicit tool selection instructions

#### C. Tool Definition Issues
```python
def _build_tool_definitions(self):
    # Returns OpenAI-compatible tool schemas
    # Check if tools are properly defined
```

#### D. Missing Resource Prompts
```python
async def _build_resource_prompt(self):
    # Build prompt with:
    # - available_agents
    # - available_knowledges  
    # - available_skills ⬅️ THIS IS EMPTY due to Issue #1
    # - other_resources
```

**Key Issue**: Because skill is not loaded (Issue #1), the agent lacks:
- Domain knowledge
- Specialized tools
- Context for what tools to use

### Impact Chain

1. **Skill not loaded** → Empty resource prompt
2. **Agent doesn't know available tools** → Generates generic text
3. **No tool selection guidance** → Avoids calling tools
4. **Result**: Pure text responses

---

## Recommended Fix Priority

### Priority 1: Fix Skill Loading (Issue #1)
**Impact**: Fixes both #1 and potentially #3

**Steps**:
1. Update skill_code in app config or database
2. Verify AgentSkillResource initialization
3. Test skill prompt appears in system prompt

### Priority 2: Fix Frontend Data Format (Issue #2)
**Impact**: Restores task visibility

**Steps**:
1. Verify backend data structure matches frontend expectations
2. Check vis_window3 converter output
3. Update data transformation if needed

### Priority 3: Verify Tool Calling (Issue #3)
**Impact**: Agent behavior

**Steps**:
1. Verify LLM model supports function calling
2. Check tool definitions are correct
3. Ensure system prompt is clear about tool usage
4. Fix skill loading first (may resolve this)

---

## Testing Checklist

### Issue #1 Test
```bash
# 1. Check database skill
sqlite3 pilot/meta_data/derisk.db "SELECT skill_code, name FROM server_app_skill WHERE name='open_rca_diagnosis';"

# 2. Check app config
cat packages/derisk-serve/src/derisk_serve/building/app/service/derisk_app_define/rca_openrca_app.json | grep -A5 "skill_name"

# 3. Check agent initialization logs
# Look for: "[ReActReasoningAgent] 资源预加载完成: tools_count=X, resource_prompt_len=Y"
```

### Issue #2 Test
```bash
# 1. Start app and check running window data
curl http://localhost:7777/api/v1/chat/completions -X POST -d '{"user_input":"test","conv_uid":"test123"}'

# 2. Check frontend console for parse errors
# 3. Inspect vis_window3 API response structure
```

### Issue #3 Test
```python
# In agent logs, check:
# - "调用 LLM: 消息数=X, 工具数=Y"
# - "LLM 返回纯文本回答，任务可能已完成" (early termination warning)
# - "工具调用: {tool_name}" (should see this for each tool)
```

---

## Next Steps

1. **Immediate**: Fix skill_code mismatch in app config
2. **Verify**: Check if Issue #3 resolves after fixing Issue #1
3. **Debug**: Capture actual API response for Issue #2
4. **Monitor**: Check agent logs for tool call patterns