# V2 Skill 工具迁移清单

Task 17 调研输出。记录所有 skill-aware 工具的当前签名、依赖字段和 V2 迁移目标签名。

## 背景

V2 `ToolContext` 已扩展以下字段：
- `skill_dir: Optional[str]` — 直接字段（不再需要 `context.config["skill_dir"]`）
- `available_skills: Dict[str, str]` — 直接字段（不再需要 `context.config["available_skills"]`）
- `sandbox_client` — 通过 `context.get_resource("sandbox_client")` 注入（ToolContextFactory 已在 `build()` 中注入）
- `agent_file_system` — 通过 `context.get_resource("agent_file_system")` 注入
- `agent` — 通过 `context.get_resource("agent")` 注入

当前多数工具通过 `context.config["skill_dir"]` / `context.config["available_skills"]` / `context.config["sandbox_client"]` 读取，迁移后需改为直接字段或 `get_resource()`。

---

## 1. Skill 工具

### 1.1 ReadSkillTool (`skill/read_skill.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `context.config["available_skills"]` — skill name -> path 映射
- `context.config["skill_dir"]` — skill 基础目录
- `sandbox_client` — 通过 `_get_sandbox_client(context)` (从 `context.config["sandbox_client"]` 或 `context.get_resource("sandbox_client")` 获取)

**迁移后签名 (不变):**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**迁移要点:**
- `context.config["available_skills"]` → `context.available_skills` (已是 ToolContext 直接字段)
- `context.config["skill_dir"]` → `context.skill_dir` (已是 ToolContext 直接字段)
- `sandbox_client` 获取路径已兼容 `context.get_resource("sandbox_client")`，无需修改

---

### 1.2 ListSkillsTool (`skill/list_skills.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `context.config["available_skills"]` — 预计算 skill 映射
- `context.config["skill_dir"]` — skill 基础目录
- `sandbox_client` — 通过 `_get_sandbox_client(context)`

**迁移后签名 (不变):**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**迁移要点:**
- `context.config["available_skills"]` → `context.available_skills`
- `context.config["skill_dir"]` → `context.skill_dir`

---

### 1.3 ExecuteSkillScriptTool (`skill/execute_skill.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `context.config["available_skills"]` — skill name -> path 映射
- `context.config["skill_dir"]` — skill 基础目录
- `sandbox_client` — 通过 `_get_sandbox_client(context)`

**迁移后签名 (不变):**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**迁移要点:**
- `context.config["available_skills"]` → `context.available_skills`
- `context.config["skill_dir"]` → `context.skill_dir`

---

## 2. Sandbox 工具

### 2.1 SandboxToolBase (`sandbox/base.py`) — 基类

**`_get_sandbox_client` 方法:**
当前已支持从 `context.get_resource("sandbox_client")` 获取 sandbox_client，V2 兼容。无需修改。

**迁移要点:**
- 路径 `context.config["sandbox_client"]` 已能被 V2 的 `set_resource("sandbox_client", ...)` 覆盖，但 `context.config.get("sandbox_client")` 不会命中。需要考虑是否在 `build()` 中同时写 `config["sandbox_client"]` 或修改 `_get_sandbox_client` 的查找顺序。
- `_get_sandbox_client` 当前已查 `context.get_resource("sandbox_client")`（第 72 行），V2 可直接命中，无需修改。

### 2.2 ShellExecTool (`sandbox/shell_exec.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `sandbox_client` — 通过 `_get_sandbox_client(context)`

**迁移后签名 (不变):**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**迁移要点:** 无变化，`_get_sandbox_client` 已兼容 V2。

### 2.3 DeliverFileTool (`sandbox/deliver_file.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `sandbox_client` — 通过 `_get_sandbox_client(context)`

**迁移要点:** 无变化。

### 2.4 EditFileTool (`sandbox/edit_file.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `sandbox_client` — 通过 `_get_sandbox_client(context)`

**迁移要点:** 无变化。

### 2.5 CreateFileTool (`sandbox/create_file.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `sandbox_client` — 通过 `_get_sandbox_client(context)`

**迁移要点:** 无变化。

### 2.6 ViewTool (`sandbox/view.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `sandbox_client` — 通过 `_get_sandbox_client(context)`

**迁移要点:** 无变化。

### 2.7 DownloadFileTool (`sandbox/download_file.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `sandbox_client` — 通过 `_get_sandbox_client(context)`

**迁移要点:** 无变化。

### 2.8 Browser 工具 (`sandbox/browser.py`) — 12 个工具

所有浏览器工具均继承 `SandboxToolBase`，execute 签名统一为:
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

依赖 `sandbox_client` — 通过 `_get_sandbox_client(context)`。

**迁移要点:** 无变化。

---

## 3. File System 工具

### 3.1 ReadTool (`file_system/read.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `sandbox_client` — 通过 `_get_sandbox_client(context)`（仅沙箱模式下使用）
- `context.working_directory` — 本地模式下使用

**迁移要点:** 无变化。

### 3.2 WriteTool (`file_system/write.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `sandbox_client` — 通过 `_get_sandbox_client(context)`
- `context.working_directory` — 本地模式下使用

**迁移要点:** 无变化。

### 3.3 EditTool (`file_system/edit.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `sandbox_client` — 通过 `_get_sandbox_client(context)`
- `context.working_directory` — 本地模式下使用

**迁移要点:** 无变化。

---

## 4. Shell 工具

### 4.1 BashTool (`shell/bash.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `sandbox_client` — 通过 `_get_sandbox_client(context)`
- `context.working_directory` — 本地模式下使用

**迁移要点:** 无变化。

---

## 5. Media Gen 工具

### 5.1 GenerateImageTool (`media_gen/media_gen_tools.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**依赖的 ToolContext 字段:**
- `sandbox_client` — 通过 `_get_agent_file_system(context)` 内的查找路径访问 `context.config["sandbox_client"]`
- `agent_file_system` — 通过 `_get_agent_file_system(context)` 获取

**迁移要点:**
- `_get_agent_file_system` 函数中有对 `context.config["sandbox_client"]` 的访问，用于从 sandbox_client 上取 `agent_file_system`。V2 下 `agent_file_system` 已通过 `context.get_resource("agent_file_system")` 注入，应优先使用该路径。

### 5.2 GenerateVideoTool (`media_gen/media_gen_tools.py`)

**当前 execute 签名:**
```python
async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult
```

**迁移要点:** 同 GenerateImageTool。

---

## 6. Expand Actions（旧框架动作层）

### 6.1 SandboxAction (`expand/actions/sandbox_action.py`)

**当前 parse_action 签名:**
```python
@classmethod
def parse_action(cls, tool_call: ToolCall, default_action=None, resource=None, **kwargs) -> Optional["Action"]
```

**依赖:**
- `agent.sandbox_manager.client` — 从 ConversableAgent 获取沙箱客户端
- `agent_context.conv_id` — 会话 ID

**迁移要点:**
- SandboxAction 是旧框架（BAIZE）的动作层，V2 不需要此文件。V2 的 acting_fn 直接调用工具，无需经过 parse_action。

### 6.2 ToolAction (`expand/actions/tool_action.py`)

**当前 run 签名:**
```python
async def run(self, ai_message=None, resource=None, rely_action_out=None, need_vis_render=True, skip_init_push=False, **kwargs) -> ActionOutput
```

**依赖:**
- `agent.sandbox_manager` — 获取 sandbox_client
- `agent.agent_context` — 获取 conv_id, conv_session_id
- `agent.agent_file_system` — 文件系统
- `kwargs.get("agent_file_system")` — 系统工具文件系统

**迁移要点:**
- ToolAction 是旧框架（BAIZE）的动作层。V2 的 acting_fn 已替代此逻辑，ToolAction 通过 `UnifiedToolAdapter` 桥接新框架工具。
- 在 V2 中，`_execute_tool` 构建 `tool_context` dict 传给工具，迁移后应直接使用 `ToolContextFactory.build()` 构造的 `ToolContext`。

---

## 7. 辅助模块

### 7.1 `_skill_path_utils.py` (`skill/_skill_path_utils.py`)

纯函数模块，无 execute 方法，无 context 依赖。提供 `normalize_skill_name()` 和 `resolve_local_skill_dir()` 辅助函数。

**迁移要点:** 无需迁移，V2 继续使用。

---

## 汇总

| 类别 | 工具数 | 需要迁移的工具 | 不需要迁移 |
|------|--------|----------------|-----------|
| Skill 工具 | 3 | ReadSkillTool, ListSkillsTool, ExecuteSkillScriptTool | - |
| Sandbox 工具 | 9+12 | ShellExecTool, DeliverFileTool, EditFileTool, CreateFileTool, ViewTool, DownloadFileTool, 12 Browser tools | - |
| File System 工具 | 3 | ReadTool, WriteTool, EditTool | - |
| Shell 工具 | 1 | BashTool | - |
| Media Gen 工具 | 2 | GenerateImageTool, GenerateVideoTool | - |
| Expand Actions | 2 | SandboxAction, ToolAction | - |
| 辅助模块 | 1 | - | _skill_path_utils.py |

**总计: 19 个源文件（不含 __pycache__），涉及 32+ 个工具类。**

### 迁移优先级

1. **P0 — Skill 工具 (Task 18):** 3 个工具，需修改 `context.config["skill_dir"]` → `context.skill_dir` 和 `context.config["available_skills"]` → `context.available_skills`。
2. **P1 — Sandbox/File System/Shell 工具 (Task 19):** 大部分无需修改（`_get_sandbox_client` 已兼容 V2），但需确认 ToolContextFactory 在 `build()` 中注入 `sandbox_client` 后 `_get_sandbox_client` 的查找路径能命中。
3. **P2 — Media Gen/Expand Actions (Task 20):** Media Gen 的 `_get_agent_file_system` 需优先使用 `context.get_resource("agent_file_system")`；Expand Actions 在 V2 中不再使用。