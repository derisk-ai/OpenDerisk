# Prompt Assembly Module - 通用 Prompt 组装模块

提供分层 Prompt 组装能力，兼容 core_v1 和 core_v2 两种架构。

## 目录结构

```
prompt_assembly/
├── __init__.py                     # 模块入口
├── prompt_registry.py              # 模板注册表
├── resource_injector.py            # 资源注入器
├── prompt_assembler.py             # 分层组装器
└── prompts/                        # 模板文件目录
    ├── identity/                   # 身份模板
    ├── workflow/                   # 工作流模板
    ├── exceptions/                 # 异常处理模板
    ├── delivery/                   # 交付规范模板
    └── resources/                  # 资源注入模板
        ├── sandbox.md.j2           # 沙箱环境
        ├── agents.md.j2            # 子 Agent
        ├── knowledge.md.j2         # 知识库
        ├── skills.md.j2            # 技能
        ├── tools.md.j2             # 工具
        ├── database.md.j2          # 数据库
        ├── internet.md.j2          # 互联网搜索
        ├── workflow.md.j2          # 工作流
        └── other.md.j2             # 其他资源
```

## 核心组件

### 1. PromptRegistry - 模板注册表

```python
from derisk.agent.shared.prompt_assembly import get_registry

registry = get_registry()

# 获取模板
template = registry.get("identity", "default")

# 渲染模板
content = template.render(role="AI助手", name="Assistant")

# 注册自定义模板
registry.register_content(
    category="identity",
    name="custom_assistant",
    content="# 角色定义\n你是一个 {{role}}..."
)
```

### 2. ResourceInjector - 资源注入器

```python
from derisk.agent.shared.prompt_assembly import (
    ResourceInjector,
    ResourceContext,
)

# 创建资源上下文
ctx = ResourceContext.from_v1_agent(agent)  # core_v1
# 或
ctx = ResourceContext.from_v2_agent(agent)  # core_v2

# 注入资源
injector = ResourceInjector()
all_resources = await injector.inject_all(ctx)
```

### 3. PromptAssembler - 分层组装器

```python
from derisk.agent.shared.prompt_assembly import create_prompt_assembler

# core_v1 架构
assembler = create_prompt_assembler(architecture="v1", language="zh")
system_prompt = await assembler.assemble_system_prompt(
    user_system_prompt="你是一个专家...",
    resource_context=ctx,
    role="AI助手",
    name="Assistant",
)

# core_v2 架构
assembler = create_prompt_assembler(architecture="v2", language="zh")
system_prompt = await assembler.assemble_system_prompt(
    resource_context=ctx,
    agent_name="ReActAgent",
)
```

## 架构集成

### core_v1 (ReActMasterAgent)

**集成位置**: `load_thinking_messages()` 方法

```python
# packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py

from ...shared.prompt_assembly import (
    PromptAssembler,
    ResourceContext,
)

class ReActMasterAgent(ConversableAgent):
    _prompt_assembler: Optional[PromptAssembler] = PrivateAttr(default=None)

    def _get_prompt_assembler(self) -> PromptAssembler:
        if self._prompt_assembler is None:
            config = PromptAssemblyConfig(architecture="v1")
            self._prompt_assembler = PromptAssembler(config)
        return self._prompt_assembler

    async def load_thinking_messages(self, ...):
        # ... 现有逻辑 ...

        # 使用 PromptAssembler 分层组装
        assembler = self._get_prompt_assembler()
        resource_ctx = ResourceContext.from_v1_agent(self)

        user_system_prompt = getattr(self.profile, "system_prompt_template", None)
        system_prompt = await assembler.assemble_system_prompt(
            user_system_prompt=user_system_prompt,
            resource_context=resource_ctx,
            role=self.profile.role,
            name=self.profile.name,
        )
```

### core_v2 (ReActReasoningAgent)

**集成位置**: `_build_system_prompt_with_assembler()` 方法

```python
# packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_reasoning_agent.py

from ...shared.prompt_assembly import (
    PromptAssembler,
    ResourceContext,
)

class ReActReasoningAgent(BaseBuiltinAgent):
    _prompt_assembler: Optional[PromptAssembler] = None
    
    def _get_prompt_assembler(self) -> PromptAssembler:
        if self._prompt_assembler is None:
            config = PromptAssemblyConfig(architecture="v2")
            self._prompt_assembler = PromptAssembler(config)
        return self._prompt_assembler
    
    async def _build_system_prompt_with_assembler(self) -> str:
        assembler = self._get_prompt_assembler()
        resource_ctx = ResourceContext.from_v2_agent(self)
        
        return await assembler.assemble_system_prompt(
            resource_context=resource_ctx,
            agent_name=self.info.name,
        )
    
    async def think(self, message: str, **kwargs):
        # 使用新方法
        system_prompt = await self._build_system_prompt_with_assembler()
        # ...
```

## 前端集成

### 数据流

```
┌─────────────────┐
│  前端应用编辑页面  │
├─────────────────┤
│ system_prompt   │  ← 用户输入（身份内容）
│ user_prompt     │  ← 用户输入（可选前缀）
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  API Request    │
│ ServeRequest {  │
│   system_prompt │
│   user_prompt   │
│   resources...  │
│ }               │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Database       │
│ gpts_app_config │
│ system_prompt   │
│ user_prompt     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  AgentChat      │
│ 构建 Agent      │
│ temp_profile    │
│ .system_prompt  │ ← 赋值给 Profile
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Agent          │
│ Profile         │
│ PromptAssembler │ ← 组装最终 Prompt
└─────────────────┘
```

### 前端字段说明

| 字段 | 数据库列 | 说明 |
|------|---------|------|
| `system_prompt_template` | `system_prompt_template` | 系统提示模板 |
| `user_prompt_template` | `user_prompt_template` | 用户提示模板 |

### API Schema

```python
# packages/derisk-serve/src/derisk_serve/building/config/api/schemas.py

class ServeRequest(BaseModel):
    system_prompt_template: Optional[str] = Field(None, description="system prompt模版")
    user_prompt_template: Optional[str] = Field(None, description="user prompt模版")
    # ... 其他字段
```

### AgentChat 集成

```python
# packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py

# 构建 Agent 时设置 Profile
temp_profile = recipient.profile.copy()
if app.system_prompt_template is not None:
    temp_profile.system_prompt_template = app.system_prompt_template
if app.user_prompt_template:
    temp_profile.user_prompt_template = app.user_prompt_template
recipient.bind(temp_profile)
```

## 资源类型

| 资源类型 | 模板文件 | 对应 ResourceType |
|---------|---------|------------------|
| 沙箱环境 | `sandbox.md.j2` | SANDBOX |
| 子 Agent | `agents.md.j2` | App |
| 知识库 | `knowledge.md.j2` | Knowledge |
| 技能 | `skills.md.j2` | AgentSkill |
| 工具 | `tools.md.j2` | Tool, Plugin |
| 数据库 | `database.md.j2` | DB |
| 互联网 | `internet.md.j2` | Internet |
| 工作流 | `workflow.md.j2` | Workflow |
| 其他 | `other.md.j2` | 其他类型 |

## 扩展资源模板

要添加新的资源类型支持：

1. 创建模板文件 `prompts/resources/new_type.md.j2`
2. 更新 `ResourceType` 枚举
3. 在 `ResourceContext` 添加资源提取逻辑
4. 在 `ResourceInjector` 添加注入方法

```python
# 1. 扩展 ResourceType
class ResourceType(str, Enum):
    NEW_TYPE = "new_type"

# 2. 添加资源提取
class ResourceContext:
    def _extract_new_type(self) -> List[ResourceInfo]:
        # 提取逻辑
        pass

# 3. 添加注入方法
class ResourceInjector:
    async def inject_new_type(self, ctx: ResourceContext) -> Optional[str]:
        resources = ctx.get_resources(ResourceType.NEW_TYPE)
        if not resources:
            return None
        template = self._get_template(ResourceType.NEW_TYPE)
        return template.render(new_types=[r.to_dict() for r in resources])
```