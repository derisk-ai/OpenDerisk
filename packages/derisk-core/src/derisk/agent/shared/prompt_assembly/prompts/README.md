# Prompt 模板目录

本目录包含分层 Prompt 模板，支持 core_v1 和 core_v2 两种架构。

## 分层组装

系统默认使用分层组装模式，将 Prompt 分为三层：

### ReActMasterAgent (core_v1)

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent
from derisk.agent import ProfileConfig

agent = ReActMasterAgent(
    profile=ProfileConfig(
        name="MyAgent",
        role="AI助手",
        system_prompt_template="""# 角色定义

你是一个专业的 {{role}}，专注于帮助用户解决问题。

## 核心能力
- 数据分析
- 代码开发
- 文档处理
""",  # 仅身份内容
    )
)
```

### ReActReasoningAgent (core_v2)

```python
from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent
from derisk.agent.core_v2.agent_info import AgentInfo

agent = ReActReasoningAgent(
    info=AgentInfo(
        name="ReActAgent",
        max_steps=20,
    )
)
```

## 目录结构

```
prompts/
├── identity/                      # 身份模板
│   ├── default.md                 # 默认身份模板（中文）
│   └── default_en.md              # 默认身份模板（英文）
├── workflow/                      # 工作流模板
│   ├── v3.md                      # V3 版本工作流（中文）
│   └── v3_en.md                   # V3 版本工作流（英文）
├── exceptions/                    # 异常处理模板
│   ├── main.md                    # 主异常处理模板（中文）
│   └── main_en.md                 # 主异常处理模板（英文）
├── delivery/                      # 交付规范模板
│   ├── main.md                    # 主交付规范（中文）
│   └── main_en.md                 # 主交付规范（英文）
└── resources/                     # 资源注入模板（Jinja2）
    ├── sandbox.md.j2              # 沙箱环境模板
    ├── agents.md.j2               # 子Agent模板
    ├── knowledge.md.j2            # 知识库模板
    ├── skills.md.j2               # 技能模板
    ├── tools.md.j2                # 工具模板
    ├── database.md.j2             # 数据库模板
    ├── internet.md.j2             # 互联网搜索模板
    ├── workflow.md.j2             # 工作流模板
    └── other.md.j2                # 其他资源模板
```

## 分层组装结构

```
┌─────────────────────────────────────────────────────────────────┐
│                         最终 System Prompt                        │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: 身份层 (Identity)                                      │
│  ├── 用户 system_prompt_template（如果提供）                      │
│  └── 或默认 identity/default.md                                  │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: 源层 (Resources) - 动态注入                           │
│  ├── sandbox.md.j2    (如果有 sandbox_manager)                   │
│  ├── agents.md.j2     (如果有 AppResource)                       │
│  ├── knowledge.md.j2  (如果有 RetrieverResource)                 │
│  ├── skills.md.j2     (如果有 AgentSkillResource)                │
│  ├── tools.md.j2      (如果有工具)                                │
│  └── database.md.j2   (如果有 DBResource)                        │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: 控制层 (Control)                                       │
│  ├── workflow/v3.md         (核心工作流)                          │
│  ├── exceptions/main.md     (异常处理)                            │
│  └── delivery/main.md       (交付规范)                            │
└─────────────────────────────────────────────────────────────────┘
```

## 前端集成

前端应用编辑页面 → `system_prompt_template` 字段

```
前端输入:
┌────────────────────────────┐
│ # 角色定义                 │
│ 你是一个专业的数据分析助手  │
└────────────────────────────┘
        │
        ▼ API 保存
┌────────────────────────────┐
│ gpts_app_config 表          │
│ system_prompt_template = "..."│
└────────────────────────────┘
        │
        ▼ AgentChat 加载
┌────────────────────────────┐
│ Profile.system_prompt_template│
└────────────────────────────┘
        │
        ▼ PromptAssembler 组装
┌────────────────────────────┐
│ 身份层 + 资源层 + 控制层     │
└────────────────────────────┘
```