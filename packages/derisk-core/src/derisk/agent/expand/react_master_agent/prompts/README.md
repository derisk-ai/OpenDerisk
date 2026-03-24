# ReActMasterAgent Prompt 模板

本目录包含 ReActMasterAgent 的分层 Prompt 模板，支持中英文双语。

## 目录结构

```
prompts/
├── identity/                      # 身份层
│   ├── default.md                 # 默认身份（中文）
│   └── default_en.md              # 默认身份（英文）
├── workflow/                      # 工作流层
│   ├── v3.md                      # V3 工作流（中文）
│   └── v3_en.md                   # V3 工作流（英文）
├── exceptions/                    # 异常处理层
│   ├── main.md                    # 异常处理（中文）
│   └── main_en.md                 # 异常处理（英文）
├── delivery/                      # 交付规范层
│   ├── main.md                    # 交付规范（中文）
│   └── main_en.md                 # 交付规范（英文）
├── resources/                     # 资源注入层（Jinja2）
│   ├── sandbox.md.j2              # 沙箱环境
│   ├── agents.md.j2               # 子 Agent
│   ├── knowledge.md.j2            # 知识库
│   ├── skills.md.j2               # 技能
│   └── other_resources.md.j2      # 其他资源
├── user/                          # 用户提示层（Jinja2）
│   ├── session_history.md.j2      # 历史对话回顾
│   ├── memories.md.j2              # 最近记忆
│   ├── question.md.j2              # 当前任务
│   └── natural_message.md.j2       # 自然消息
└── README.md
```

## 分层组装结构

### System Prompt 分层

```
┌─────────────────────────────────────────────────────────────────┐
│                         System Prompt                            │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: 身份层 (identity/)                                     │
│  ├── 用户 system_prompt_template（如果提供）                      │
│  └── 或默认 identity/default.md                                  │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: 资源层 (resources/) - 动态注入                           │
│  ├── sandbox.md.j2    (沙箱环境)                                 │
│  ├── agents.md.j2     (子 Agent)                                 │
│  ├── knowledge.md.j2  (知识库)                                   │
│  └── skills.md.j2     (技能)                                     │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: 控制层                                                 │
│  ├── workflow/v3.md         (核心工作流)                          │
│  ├── exceptions/main.md     (异常处理)                            │
│  └── delivery/main.md       (交付规范)                            │
└─────────────────────────────────────────────────────────────────┘
```

### User Prompt 分层

```
┌─────────────────────────────────────────────────────────────────┐
│                          User Prompt                              │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: 历史上下文层（二选一）                                    │
│  ├── session_history.md.j2   (会话历史，优先)                     │
│  └── memories.md.j2          (最近记忆)                          │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: 当前任务层（二选一）                                      │
│  ├── natural_message.md.j2   (自然消息，优先)                     │
│  └── question.md.j2          (当前任务)                          │
└─────────────────────────────────────────────────────────────────┘
```

## 模板变量

### identity 模板变量
- `{{ role }}` - Agent 角色
- `{{ name }}` - Agent 名称

### resources 模板变量
- `sandbox_enable` - 是否启用沙箱
- `work_dir` - 工作目录
- `agent_skill_dir` - 技能目录
- `use_agent_skill` - 是否使用技能

### user 模板变量
- `session_history` - 会话历史
- `most_recent_memories` - 最近记忆
- `question` - 用户问题
- `natural_message` - 自然消息

## 模板优先级

1. **Agent 模板** (`react_master_agent/prompts/`)
2. **共享模板** (`shared/prompt_assembly/prompts/`)

Agent 模板会覆盖共享模板。