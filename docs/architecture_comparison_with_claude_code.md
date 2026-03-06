# Claude Code vs Derisk 架构深度对比分析报告

## 目录
1. [执行摘要](#执行摘要)
2. [Agent架构对比](#agent架构对比)
3. [上下文管理策略对比](#上下文管理策略对比)
4. [记忆机制对比](#记忆机制对比)
5. [核心工具系统对比](#核心工具系统对比)
6. [核心Prompt对比](#核心prompt对比)
7. [多Agent机制对比](#多agent机制对比)
8. [架构优劣势分析](#架构优劣势分析)
9. [改进建议](#改进建议)

---

## 执行摘要

| 维度 | Claude Code | Derisk |
|------|-------------|--------|
| **定位** | 终端AI编程助手 | 企业级SRE多智能体框架 |
| **架构风格** | 单体+子代理委托 | 分层资源驱动架构 |
| **核心模式** | ReAct + 工具调用 | ReAct + PDCA双模式 |
| **上下文管理** | 分层配置+自动压缩 | 会话缓存+向量存储 |
| **记忆系统** | 文件系统+CLAUDE.md | 感官/短期/长期三层记忆 |
| **工具系统** | 内置+MCP扩展 | Resource抽象+插件注册 |
| **多Agent** | 子代理+Agent Teams | 层级委托+Team管理 |
| **成熟度** | 生产级（71.7k stars） | 企业级（生产就绪） |

---

## 1. Agent架构对比

### 1.1 Claude Code 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Main Agent (Claude)                      │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Permission System                        │    │
│  │  default | acceptEdits | dontAsk | bypassPermissions │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                  │
│  ┌───────────┬───────────┼───────────┬───────────┐         │
│  │           │           │           │           │         │
│  ▼           ▼           ▼           ▼           ▼         │
│ Explore    Plan     General     Bash     StatusLine        │
│ (Haiku)   (Main)    (Main)    (Main)     (Sonnet)          │
│                                                           │
│ Tools: Read-only  Read-only   All      Bash       All      │
└─────────────────────────────────────────────────────────────┘
```

**特点：**
- 主代理统一入口，子代理按需委托
- 子代理通过Markdown+YAML frontmatter定义
- 权限模式可配置，支持自动批准/拒绝
- 模型选择灵活（Haiku快速探索，Sonnet复杂任务）

### 1.2 Derisk 架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent Interface                         │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              ConversableAgent (Base)                 │    │
│  │  ┌─────────────┬─────────────┬─────────────────┐   │    │
│  │  │ ManagerAgent │ ReActAgent  │   PDCAAgent     │   │    │
│  │  │ (Orchestrator)│(Reasoning) │(Plan-Do-Check-Act)│  │    │
│  │  └─────────────┴─────────────┴─────────────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                  │
│  ┌────────────────────────┼────────────────────────────┐   │
│  │                    Resource Layer                     │   │
│  │  LLMConfig │ Memory │ Tools │ Knowledge │ Apps      │   │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                  │
│  ┌────────────────────────┼────────────────────────────┐   │
│  │                   Permission System                    │   │
│  │          ALLOW │ DENY │ ASK (User Approval)           │   │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**特点：**
- 抽象接口+基类实现+特化代理三层结构
- 资源驱动设计，通过bind()动态绑定
- 支持ReAct推理循环和PDCA计划执行双模式
- 内置沙箱隔离执行环境

### 1.3 架构对比表

| 维度 | Claude Code | Derisk |
|------|-------------|--------|
| **继承层次** | 扁平（主代理+子代理） | 深层（接口→基类→特化） |
| **代理定义** | Markdown+YAML | Python类+装饰器 |
| **配置方式** | frontmatter属性 | 数据类字段 |
| **权限粒度** | 模式级别 | 工具+命令级别 |
| **执行环境** | 本地Shell | 可配置沙箱 |
| **状态管理** | 会话隔离 | ContextHelper并发安全 |

---

## 2. 上下文管理策略对比

### 2.1 Claude Code 上下文管理

**分层配置加载：**
```
优先级（从高到低）：
1. Managed Policy     ← 组织级策略
2. Command Line Args  ← 会话级覆盖
3. Local Settings     ← .claude/settings.local.json
4. Project Settings    ← .claude/settings.json
5. User Settings       ← ~/.claude/settings.json
```

**上下文窗口管理：**
```python
# Claude Code策略
- 触发阈值: ~95% 容量时自动压缩
- 子代理隔离: 每个子代理独立上下文窗口
- 上下文分叉: Skills可使用 context: fork 创建新上下文
- 预算缩放: Skill描述占上下文2%（最小16000字符）
```

**工具输出限制：**
```
- MCP工具输出警告阈值: 10,000 tokens
- 可配置最大值: MAX_MCP_OUTPUT_TOKENS
- 默认最大: 25,000 tokens
```

### 2.2 Derisk 上下文管理

**会话缓存架构：**
```python
class ConversationCache:
    """TTL缓存，3小时过期，最多200会话"""
    messages: List[Dict]           # 消息历史
    actions: List[ActionOutput]   # 动作历史
    plans: List[Plan]             # 计划列表
    task_tree: TaskTreeManager    # 任务树
    file_metadata: Dict           # 文件元数据
    work_logs: List[WorkLog]     # 工作日志
    kanban: Kanban               # 看板状态
    todos: List[Todo]            # 待办事项
```

**上下文窗口管理：**
```python
class ContextWindow:
    """管理上下文token限制和压缩"""
    def create(self) -> ContextTokenAlloc
    def add_message(self, message) -> TokenUsage
    def compact(self) -> CompactedContext  # 超限时触发压缩
```

**动态变量注入：**
```python
# ReAct Agent动态提示词变量
@self._vm.register("available_agents", "可用Agents资源")
async def var_available_agents(instance):
    # 运行时动态生成代理列表
    ...

@self._vm.register("available_tools", "可用工具列表")
async def var_available_tools(instance):
    # 根据权限动态过滤工具
    ...
```

### 2.3 上下文管理对比表

| 维度 | Claude Code | Derisk |
|------|-------------|--------|
| **配置层级** | 5层（策略→命令行→本地→项目→用户） | 3层（系统→项目→用户） |
| **压缩策略** | 95%阈值自动压缩 | 显式compact()调用 |
| **隔离机制** | 子代理独立上下文 | 会话级TTL缓存 |
| **动态注入** | !`command`预处理 | Jinja2模板+注册变量 |
| **持久化** | 文件系统 | 数据库+向量存储 |

---

## 3. 记忆机制对比

### 3.1 Claude Code 记忆系统

**记忆类型：**
```
┌─────────────────────────────────────────────────────────┐
│                     Memory Hierarchy                     │
├─────────────────┬───────────────────────────────────────┤
│ Managed Policy  │ 组织级共享指令（系统目录）              │
├─────────────────┼───────────────────────────────────────┤
│ Project Memory  │ ./CLAUDE.md（团队共享，git追踪）        │
├─────────────────┼───────────────────────────────────────┤
│ Project Rules   │ ./.claude/rules/*.md（模块化规则）     │
├─────────────────┼───────────────────────────────────────┤
│ User Memory     │ ~/.claude/CLAUDE.md（个人偏好）        │
├─────────────────┼───────────────────────────────────────┤
│ Project Local   │ ./CLAUDE.local.md（个人项目特定）      │
├─────────────────┼───────────────────────────────────────┤
│ Auto Memory     │ ~/.claude/projects/<project>/memory/  │
│                 │ Claude自动学习的笔记                   │
└─────────────────┴───────────────────────────────────────┘
```

**Auto Memory结构：**
```
~/.claude/projects/<project>/memory/
├── MEMORY.md          # 简洁索引（前200行自动加载）
├── debugging.md       # 详细调试笔记
└── api-conventions.md # 主题文件
```

**CLAUDE.md导入机制：**
```markdown
# 支持相对路径和绝对路径导入
See @README for project overview.

# 附加指令
- git workflow @docs/git-instructions.md
```

### 3.2 Derisk 记忆系统

**认知模型架构：**
```
┌─────────────────────────────────────────────────────────┐
│                Human Cognitive Memory Model              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────┐                                   │
│  │ SensoryMemory   │ ← 感知输入（瞬时）                 │
│  │ (Perceptual)    │                                   │
│  └────────┬────────┘                                   │
│           │ 注意力筛选                                  │
│           ▼                                             │
│  ┌─────────────────┐                                   │
│  │ ShortTermMemory │ ← 工作记忆（临时、内存）           │
│  │ (Working)       │   容量有限，快速访问               │
│  └────────┬────────┘                                   │
│           │ 巩固化                                      │
│           ▼                                             │
│  ┌─────────────────┐                                   │
│  │ LongTermMemory  │ ← 长期记忆（持久、向量存储）       │
│  │ (Persistent)    │   语义搜索，重要性排序             │
│  └─────────────────┘                                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**MemoryFragment核心结构：**
```python
@dataclass
class MemoryFragment:
    id: int                    # Snowflake ID
    raw_observation: str       # 原始数据
    embeddings: List[float]    # 向量表示
    importance: float           # 相关性分数（0-1）
    is_insight: bool           # 是否为高层次洞察
    last_accessed_time: datetime
    
    # 记忆巩固相关
    consolidation_count: int   # 巩固次数
    decay_rate: float          # 衰减率
```

**GptsMemory会话管理：**
```python
class GptsMemory:
    """会话级记忆管理"""
    
    # TTL缓存
    _cache: TTLCache = TTLCache(maxsize=200, ttl=10800)  # 3小时
    
    # 持久化层
    message_memory: GptsMessageMemory
    plans_memory: GptsPlansMemory
    file_memory: AgentFileMemory
    
    # 流式支持
    message_channel: Queue[MessageStorage]
    
    async def write_memories(
        self,
        conversation_id: str,
        messages: List[AgentMessage]
    ) -> List[MemoryFragment]:
        """从对话中提取并存储记忆"""
        ...
```

**AgentMemory检索策略：**
```python
def read(
    self,
    query: str,
    limit: int = 100,
    token_limit: int = 4000
) -> List[MemoryFragment]:
    """
    检索策略：
    1. 语义相似度（embeddings）
    2. 时近性（last_accessed_time）
    3. 重要性（importance）
    4. token预算约束
    """
    ...
```

### 3.3 记忆机制对比表

| 维度 | Claude Code | Derisk |
|------|-------------|--------|
| **记忆层次** | 2层（用户定义+自动记忆） | 3层（感官→短期→长期） |
| **存储方式** | 文件系统（Markdown） | 向量数据库+关系数据库 |
| **语义搜索** | 无原生支持 | 支持embedding检索 |
| **记忆巩固** | 无自动机制 | 重要性衰减+巩固计数 |
| **共享机制** | Git共享CLAUDE.md | 按会话隔离 |
| **容量管理** | 前200行+导入深度限制 | token预算+重要性过滤 |

---

## 4. 核心工具系统对比

### 4.1 Claude Code 工具系统

**内置工具：**
| 工具 | 描述 | 关键参数 |
|------|------|----------|
| **Read** | 读取文件内容 | `file_path`, `offset`, `limit` |
| **Write** | 创建/覆盖文件 | `file_path`, `content` |
| **Edit** | 编辑文件 | `file_path`, `old_string`, `new_string`, `replace_all` |
| **Glob** | 模式匹配查找文件 | `pattern`, `path` |
| **Grep** | 搜索文件内容 | `pattern`, `path`, `glob`, `output_mode` |
| **Bash** | 执行Shell命令 | `command`, `description`, `timeout` |
| **Task** | 启动子代理 | `agent_type`, `prompt`, `thoroughness` |
| **WebFetch** | 获取网页内容 | `url`, `format`, `timeout` |
| **WebSearch** | 网络搜索 | `query` |
| **Skill** | 调用技能 | `name`, `arguments` |

**MCP工具扩展：**
```
命名规范: mcp__<server>__<tool>

示例:
- mcp__memory__create_entities
- mcp__filesystem__read_file
- mcp__github__search_repositories
```

**权限规则：**
```json
{
  "permissions": {
    "allow": [
      "Bash(npm run lint)",
      "Bash(npm run test *)"
    ],
    "deny": [
      "Bash(curl *)",
      "Read(./.env)",
      "Read(./secrets/**)"
    ]
  }
}
```

**沙箱配置：**
```json
{
  "sandbox": {
    "enabled": true,
    "autoAllowBashIfSandboxed": true,
    "excludedCommands": ["git", "docker"],
    "filesystem": {
      "allowWrite": ["//tmp/build"],
      "denyRead": ["~/.aws/credentials"]
    },
    "network": {
      "allowedDomains": ["github.com", "*.npmjs.org"],
      "allowUnixSockets": ["/var/run/docker.sock"]
    }
  }
}
```

### 4.2 Derisk 工具系统

**Resource抽象架构：**
```python
class ResourceType(str, Enum):
    DB = "database"
    Knowledge = "knowledge"
    Tool = "tool"
    AgentSkill = "agent_skill"
    App = "app"
    Memory = "memory"
    Workflow = "workflow"
    Pack = "pack"  # 资源容器
```

**工具基类：**
```python
class BaseTool(Resource):
    name: str
    description: str
    args: Dict[str, ToolParameter]
    
    async def get_prompt(self) -> Tuple[str, Dict]
    
    # 执行模式
    execute()              # 同步执行
    async_execute()        # 异步执行
    execute_stream()       # 生成器执行
    async_execute_stream() # 异步生成器
```

**FunctionTool装饰器：**
```python
@tool(description="Search the web for information")
async def web_search(
    query: str,
    max_results: int = 5
) -> str:
    """Search the web for information."""
    ...
```

**内置工具：**
| 工具 | 用途 | 位置 |
|------|------|------|
| Terminate | 结束对话 | `expand/actions/terminate_action.py` |
| KnowledgeSearch | 搜索知识库 | `expand/actions/knowledge_action.py` |
| AgentStart | 委托子代理 | `expand/actions/agent_action.py` |
| ToolAction | 通用工具执行器 | `expand/actions/tool_action.py` |
| SandboxAction | 沙箱执行 | `expand/actions/sandbox_action.py` |
| KanbanAction | 看板管理 | `expand/actions/kanban_action.py` |

**工具参数定义：**
```python
class ToolParameter(BaseModel):
    name: str
    title: str
    type: str          # string, integer, boolean等
    description: str
    enum: Optional[List[str]]
    required: bool
    default: Optional[Any]
```

**权限系统：**
```python
class PermissionAction(Enum):
    ALLOW = "allow"   # 直接执行
    DENY = "deny"     # 阻止执行
    ASK = "ask"       # 要求用户确认

def check_tool_permission(
    tool_name: str,
    command: str
) -> PermissionAction:
    """检查工具权限"""
    ...
```

**沙箱工具：**
```python
sandbox_tool_dict = {
    "view": list_directory,
    "read_file": read_file_content,
    "create_file": create_new_file,
    "edit_file": edit_file,
    "shell_exec": execute_shell_command,
    "browser_navigate": web_browser_automation
}
```

### 4.3 工具系统对比表

| 维度 | Claude Code | Derisk |
|------|-------------|--------|
| **扩展机制** | MCP协议 | Resource抽象+插件注册 |
| **定义方式** | 工具描述+JSON Schema | Python函数+装饰器 |
| **权限粒度** | 工具级+模式级 | 工具级+命令级+用户确认 |
| **沙箱支持** | 配置式 | 可插拔沙箱实现 |
| **工具组合** | Skills封装 | ResourcePack容器 |
| **流式执行** | 部分支持 | 完整流式API |

---

## 5. 核心Prompt对比

### 5.1 Claude Code Prompt模式

**系统Prompt定制：**
```bash
--system-prompt          # 完全替换默认prompt
--system-prompt-file     # 从文件加载替换
--append-system-prompt   # 追加到默认prompt
--append-system-prompt-file  # 从文件追加
```

**Skill Prompt结构：**
```yaml
---
name: code-reviewer
description: Reviews code for quality
tools: Read, Glob, Grep
model: sonnet
permissionMode: default
maxTurns: 10
skills:
  - api-conventions
mcpServers:
  - slack
memory: user
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate.sh"
---

# Code Review Instructions
When reviewing code...
```

**动态上下文注入：**
```yaml
---
name: pr-summary
description: Summarize pull request changes
context: fork
agent: Explore
---

## PR Context
- PR diff: !`gh pr diff`
- PR comments: !`gh pr view --comments`
```

**调用控制：**
| Frontmatter | 用户可调用 | Claude可调用 |
|-------------|-----------|-------------|
| (默认) | ✓ | ✓ |
| `disable-model-invocation: true` | ✓ | ✗ |
| `user-invocable: false` | ✗ | ✓ |

**变量替换：**
| 变量 | 描述 |
|------|------|
| `$ARGUMENTS` | 所有参数 |
| `$ARGUMENTS[N]` | 第N个参数 |
| `$N` | `$ARGUMENTS[N]`简写 |
| `${CLAUDE_SESSION_ID}` | 会话ID |

### 5.2 Derisk Prompt模式

**Profile配置：**
```python
class ProfileConfig(BaseModel):
    name: str
    role: str
    goal: str
    constraints: List[str]
    
    system_prompt_template: str   # Jinja2模板
    user_prompt_template: str
    write_memory_template: str
```

**ReAct System Prompt结构：**
```jinja2
## 角色与使命
你是 `{{ role }}`，一个成果驱动的编排主脑

## 黄金原则
### 原则1：技能优先
- 优先使用已定义的Skill，避免重复造轮子

### 原则2：专家输入优先
- 委托给专业Agent前，先收集必要的上下文

### 原则3：工作流状态隔离
- 不同阶段的状态互不干扰

## 资源空间
<available_agents>
{{ available_agents }}
</available_agents>

<available_knowledges>
{{ available_knowledges }}
</available_knowledges>

<available_skills>
{{ available_skills }}
</available_skills>

## 工具列表
<tools>
{{ system_tools }}
{{ custom_tools }}
</tools>

## 响应格式
<scratch_pad>
[推理过程]
</scratch_pad>

<tool_calls>
[
  {"name": "tool_name", "args": {...}}
]
</tool_calls>
```

**PDCA Prompt（版本8）：**
```jinja2
## 阶段管理
{% if is_planning_phase %}
### 规划阶段
- 探索限制: 最多2次探索步骤
- 必须调用: create_kanban
- 禁止: 执行性工具

{% else %}
### 执行阶段
- 聚焦当前阶段
- 提交交付物
- 工具规则: 独占工具 vs 并行工具

{% endif %}

## 清单
{% for item in checklist %}
- {{ item }}
{% endfor %}
```

**动态变量注册：**
```python
class ReActAgent:
    def register_variables(self):
        @self._vm.register("available_agents", "可用Agents资源")
        async def var_available_agents(instance):
            agents = instance.resource.get_resource_by_type(ResourceType.Agent)
            return self._format_agents(agents)
        
        @self._vm.register("available_tools", "可用工具列表")
        async def var_available_tools(instance):
            tools = instance.resource.get_resource_by_type(ResourceType.Tool)
            return self._format_tools(tools)
        
        @self._vm.register("available_skills", "可用技能列表")
        async def var_available_skills(instance):
            skills = instance.resource.get_resource_by_type(ResourceType.AgentSkill)
            return self._format_skills(skills)
```

### 5.3 Prompt对比表

| 维度 | Claude Code | Derisk |
|------|-------------|--------|
| **模板引擎** | 无/简单替换 | Jinja2 |
| **配置方式** | Markdown+YAML frontmatter | Python数据类 |
| **动态注入** | !`command`预处理 | 注册变量+异步函数 |
| **阶段管理** | 无原生支持 | PDCA阶段切换 |
| **条件逻辑** | 无 | Jinja2条件块 |
| **复用机制** | Skills导入 | Profile继承 |

---

## 6. 多Agent机制对比

### 6.1 Claude Code 多Agent机制

**子代理 vs Agent Teams：**

| 特性 | 子代理 | Agent Teams |
|------|--------|-------------|
| **上下文** | 独立窗口，结果返回主代理 | 完全独立实例 |
| **通信** | 仅向主代理报告 | 对等直接通信 |
| **协调** | 主代理管理 | 共享任务列表 |
| **适用场景** | 聚焦任务 | 复杂协作 |
| **Token成本** | 较低（摘要返回） | 较高（独立实例） |

**Agent Teams架构：**
```
┌─────────────────────────────────────────────────────────┐
│                    Team Lead (主会话)                     │
│                           │                               │
│         ┌─────────────────┼─────────────────┐           │
│         │                 │                 │           │
│         ▼                 ▼                 ▼           │
│   ┌───────────┐    ┌───────────┐    ┌───────────┐      │
│   │ Teammate 1│    │ Teammate 2│    │ Teammate 3│      │
│   │(独立实例) │    │(独立实例) │    │(独立实例) │      │
│   └───────────┘    └───────────┘    └───────────┘      │
│         │                 │                 │           │
│         └─────────────────┼─────────────────┘           │
│                           │                               │
│                    ┌──────┴──────┐                       │
│                    │ 共享任务列表  │                       │
│                    │ 邮箱通信     │                       │
│                    └─────────────┘                       │
└─────────────────────────────────────────────────────────┘
```

**Team协调特性：**
- **共享任务列表**：队友认领和完成任务
- **任务依赖**：依赖完成时自动解除阻塞
- **直接消息**：队友间直接通信
- **计划审批**：实施前需Lead审批
- **质量门控**：TeammateIdle和TaskCompleted钩子

**显示模式：**
| 模式 | 描述 | 要求 |
|------|------|------|
| `in-process` | 全部在主终端 | 任意终端 |
| `tmux` | 分屏显示 | tmux或iTerm2+it2 CLI |

**启用Agent Teams：**
```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

### 6.2 Derisk 多Agent机制

**层级委托架构：**
```
┌─────────────────────────────────────────────────────────┐
│                   ManagerAgent (协调器)                   │
│                           │                               │
│         ┌─────────────────┼─────────────────┐           │
│         │                 │                 │           │
│         ▼                 ▼                 ▼           │
│   ┌───────────┐    ┌───────────┐    ┌───────────┐      │
│   │ Agent A   │    │ Agent B   │    │ Agent C   │      │
│   │(数据分析师)│    │(SRE专家)  │    │(子代理)   │      │
│   └───────────┘    └───────────┘    └───────────┘      │
│         │                 │                 │           │
│         ▼                 ▼                 ▼           │
│   ┌───────────┐    ┌───────────┐                    │
│   │Tools      │    │Tools      │                    │
│   │- query_db │    │- metrics  │                    │
│   │- report   │    │- Agent C  │                    │
│   └───────────┘    └───────────┘                    │
└─────────────────────────────────────────────────────────┘
```

**AgentStart Action：**
```python
class AgentAction(Action):
    async def run(self, ...):
        # 找到目标代理
        recipient = next(
            agent for agent in sender.agents 
            if agent.name == action_input.agent_name
        )
        
        # 创建委托消息
        message = AgentMessage.init_new(
            content=action_input.content,
            context=action_input.extra_info,
            goal_id=current_message.message_id
        )
        
        # 发送给子代理
        answer = await sender.send(message, recipient)
        return answer
```

**Team管理：**
```python
class Team(BaseModel):
    agents: List[ConversableAgent]
    messages: List[Dict]
    max_round: int = 100
    
    def hire(self, agents: List[Agent]):
        """添加代理到团队"""
        ...
    
    async def select_speaker(
        self,
        last_speaker: Agent,
        selector: Agent
    ) -> Agent:
        """选择下一个发言者"""
        ...
```

**Agent Manager（注册中心）：**
```python
class AgentManager(BaseComponent):
    _agents: Dict[str, Tuple[Type[ConversableAgent], ConversableAgent]]
    
    def register_agent(cls: Type[ConversableAgent]):
        """注册代理类"""
        ...
    
    def get_agent(name: str) -> ConversableAgent:
        """获取代理实例"""
        ...
    
    def list_agents() -> List[Dict]:
        """列出所有代理"""
        ...
    
    def after_start():
        """启动后自动扫描"""
        scan_agents("derisk.agent.expand")
        scan_agents("derisk_ext.agent.agents")
```

**消息流：**
```
User -> UserProxyAgent -> ManagerAgent
                              │
                              ▼
                        generate_reply()
                              │
                              ├── thinking() [LLM推理]
                              ├── act() [执行动作]
                              └── verify() [验证结果]
                              │
                              ▼
                        AgentMessage (回复)
                              │
                              ├── send() 给子代理
                              └── 或返回给用户
```

### 6.3 多Agent机制对比表

| 维度 | Claude Code | Derisk |
|------|-------------|--------|
| **委托模式** | 子代理委托 | 层级委托 |
| **通信方式** | 主代理中转 | 直接消息+主代理中转 |
| **协调机制** | 主代理管理/任务列表 | ManagerAgent+Team |
| **代理发现** | Markdown配置 | 注册中心+自动扫描 |
| **任务跟踪** | 共享任务列表 | TaskTree+Kanban |
| **实例隔离** | 子代理独立上下文 | 会话级隔离 |
| **显示模式** | tmux分屏 | 终端流式输出 |

---

## 7. 架构优劣势分析

### 7.1 Claude Code 优势

| 维度 | 优势说明 |
|------|----------|
| **易用性** | Markdown+YAML定义代理，学习曲线低 |
| **配置简洁** | Frontmatter配置直观，无需编程 |
| **上下文管理** | 自动压缩+分层配置，开箱即用 |
| **工具扩展** | MCP协议标准化，生态丰富 |
| **记忆共享** | Git友好的CLAUDE.md，团队协作方便 |
| **权限控制** | 模式级别权限，简化管理 |
| **Agent Teams** | 实验性对等协作，适合复杂场景 |
| **社区规模** | 71.7k stars，活跃社区 |

### 7.2 Claude Code 劣势

| 维度 | 劣势说明 |
|------|----------|
| **可编程性** | 限于YAML配置，复杂逻辑受限 |
| **状态管理** | 无复杂状态机支持 |
| **语义记忆** | 无向量存储，语义搜索缺失 |
| **执行环境** | 本地Shell为主，沙箱支持有限 |
| **企业特性** | 缺少审计日志、权限继承等 |
| **代理类型** | 固定几种子代理，扩展受限 |

### 7.3 Derisk 优势

| 维度 | 优势说明 |
|------|----------|
| **可编程性** | Python类定义，完全可编程 |
| **资源抽象** | 统一Resource接口，高度解耦 |
| **记忆系统** | 三层记忆+向量存储+语义搜索 |
| **代理模式** | ReAct+PDCA双模式，适应不同场景 |
| **权限系统** | 工具级+命令级+用户确认，细粒度 |
| **沙箱隔离** | 可插拔沙箱实现，安全性高 |
| **企业特性** | 分布式追踪、审计日志、会话管理 |
| **任务管理** | TaskTree+Kanban，复杂任务编排 |

### 7.4 Derisk 劣势

| 维度 | 劣势说明 |
|------|----------|
| **学习曲线** | Python框架，需要编程经验 |
| **配置复杂** | 数据类配置，不如YAML直观 |
| **社区规模** | 相对较小，生态有限 |
| **标准化** | 无MCP等标准协议支持 |
| **记忆共享** | 会话隔离，团队共享不便 |
| **Agent协作** | 层级委托为主，对等协作弱 |

---

## 8. 改进建议

### 8.1 对Derisk的建议

#### 1. 引入CLAUDE.md风格的记忆共享
```python
# 建议添加
class SharedMemory:
    """团队共享记忆，Git友好"""
    
    path: str  # .derisk/TEAM_MEMORY.md
    
    def load_from_project(self) -> List[MemoryFragment]:
        """从项目目录加载共享记忆"""
        ...
    
    def sync_to_git(self):
        """同步到Git仓库"""
        ...
```

#### 2. 简化代理定义
```python
# 当前方式
class MyAgent(ConversableAgent):
    name: str = "my_agent"
    role: str = "..."
    ...

# 建议支持装饰器简化
@agent(
    name="my_agent",
    role="Data Analyst",
    tools=["query_db", "generate_report"],
    model="sonnet"
)
async def my_agent_handler(message: AgentMessage) -> AgentMessage:
    ...
```

#### 3. 添加MCP协议支持
```python
class MCPToolAdapter(BaseTool):
    """MCP工具适配器"""
    
    server_name: str
    tool_name: str
    
    async def async_execute(self, **kwargs):
        # 调用MCP服务器
        ...
```

#### 4. 实现自动上下文压缩
```python
class ContextWindow:
    AUTO_COMPACT_THRESHOLD = 0.95  # 95%时自动压缩
    
    def should_compact(self) -> bool:
        return self.usage_ratio > self.AUTO_COMPACT_THRESHOLD
    
    async def auto_compact(self):
        if self.should_compact():
            await self.compact()
```

#### 5. 添加对等协作模式
```python
class PeerAgentTeam:
    """对等代理团队"""
    
    agents: List[ConversableAgent]
    shared_tasks: TaskList
    mailbox: Dict[str, Queue[AgentMessage]]
    
    async def broadcast(self, message: AgentMessage):
        """广播给所有队友"""
        ...
    
    async def direct_message(
        self,
        from_agent: str,
        to_agent: str,
        message: AgentMessage
    ):
        """直接消息"""
        ...
```

### 8.2 对Claude Code的建议（参考Derisk）

#### 1. 添加三层记忆系统
```yaml
# 建议支持
memory:
  sensory:
    enabled: true
    ttl: 60s
  short_term:
    enabled: true
    max_items: 100
  long_term:
    enabled: true
    vector_db: "chromadb"
    embedding_model: "text-embedding-3-small"
```

#### 2. 增强状态管理
```yaml
# 建议支持状态机
---
name: deployment-agent
states:
  - name: planning
    transitions: [execute, abort]
  - name: execute
    transitions: [verify, rollback]
  - name: verify
    transitions: [complete, rollback]
---
```

#### 3. 添加PDCA模式
```yaml
# 建议支持
---
name: pdca-agent
mode: pdca
phases:
  plan:
    tools: [read, grep, glob]  # 只读探索
    max_steps: 2
  do:
    tools: [all]  # 所有工具
  check:
    hooks:
      - type: verify
        command: "./scripts/verify.sh"
  act:
    hooks:
      - type: commit
        command: "git commit"
---
```

---

## 9. 总结

### 架构哲学对比

| 维度 | Claude Code | Derisk |
|------|-------------|--------|
| **设计哲学** | 约定优于配置 | 配置优于约定 |
| **目标用户** | 开发者（编程助手） | 企业（SRE自动化） |
| **扩展方式** | YAML+MCP | Python+Resource |
| **复杂度** | 低（开箱即用） | 高（企业级特性） |
| **灵活性** | 中（配置限制） | 高（完全可编程） |

### 适用场景

| 场景 | 推荐系统 |
|------|----------|
| 个人编程助手 | Claude Code |
| 代码审查自动化 | Claude Code |
| 企业SRE自动化 | Derisk |
| 复杂任务编排 | Derisk |
| 快速原型开发 | Claude Code |
| 生产级部署 | Derisk |

### 最终评价

**Claude Code** 代表了**开发者友好**的AI代理设计理念：
- 配置简洁，学习曲线低
- 社区活跃，生态丰富
- 适合个人开发者和小团队

**Derisk** 代表了**企业级**AI代理框架设计理念：
- 架构完善，功能全面
- 安全可控，生产就绪
- 适合企业级复杂场景

两者在AI代理领域各有优势，可以根据具体需求选择。对于需要快速上手的个人开发者，推荐Claude Code；对于需要企业级特性、复杂任务编排的场景，推荐Derisk。

---

*报告生成时间: 2026-03-01*
*Claude Code版本: 参考 https://github.com/anthropics/claude-code*
*Derisk版本: 基于当前代码库分析*