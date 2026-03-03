# Core_v2 Agent Prompt 显示问题修复说明

## 问题描述

在应用编辑的 Prompt Tab 中看不到 Core_v2 架构 Agent 的 prompt 模板。

## 问题原因

1. **Core_v2 Agent 未注册到 AgentManager**
   - `AgentManager` 管理的是传统 v1 Agent
   - Core_v2 Agent 使用新的架构，没有注册到 AgentManager

2. **Prompt 初始化依赖 AgentManager**
   - `sync_app_detail()` 方法通过 `get_agent_manager().get(agent_name)` 获取 Agent 实例
   - 当 `ag` 为 None 时，无法调用 `ag.prompt_template()` 获取 prompt 模板
   - 导致 `system_prompt_template` 和 `user_prompt_template` 为空

3. **前端 API 也依赖 AgentManager**
   - `/api/v1/agent/{agent_name}/prompt` API 同样依赖 AgentManager
   - 当 Agent 不存在时返回错误，导致前端无法获取默认 prompt

## 修复方案

### 1. 后端 Prompt 初始化修复 (`service.py`)

**文件**: `packages/derisk-serve/src/derisk_serve/building/app/service/service.py`

#### 1.1 添加 Core_v2 Agent 默认 Prompt 函数

```python
def _get_v2_agent_system_prompt(app_config) -> str:
    """获取 Core_v2 Agent 的默认 System Prompt"""
    base_prompt = """You are an AI assistant powered by Core_v2 architecture.

## Your Capabilities
- Execute multi-step tasks with planning and reasoning
- Use available tools and resources effectively
- Maintain context across conversation turns
- Provide clear and actionable responses

## Available Resources
{% if knowledge_resources %}
### Knowledge Bases
{% for kb in knowledge_resources %}
- **{{ kb.name }}**: {{ kb.description or 'Knowledge base for information retrieval' }}
{% endfor %}
{% endif %}

{% if skills %}
### Skills
{% for skill in skills %}
- **{{ skill.name }}**: {{ skill.description or 'Specialized skill for task execution' }}
{% endfor %}
{% endif %}

## Response Guidelines
1. Break down complex tasks into clear steps
2. Use tools when necessary to accomplish tasks
3. Provide explanations for your reasoning
4. Ask for clarification when needed

Always respond in a helpful, professional manner."""
    
    return base_prompt


def _get_v2_agent_user_prompt(app_config) -> str:
    """获取 Core_v2 Agent 的默认 User Prompt"""
    user_prompt = """User request: {{user_input}}

{% if context %}
Context: {{context}}
{% endif %}

Please process this request using available tools and resources."""
    
    return user_prompt
```

#### 1.2 修改 `sync_app_detail` 方法

```python
ag_mg = get_agent_manager()
ag = ag_mg.get(app_resp.agent)

agent_version = getattr(app_config, 'agent_version', 'v1') or 'v1'
is_v2_agent = agent_version == 'v2'

# System Prompt 初始化
if not app_config.system_prompt_template and building_mode:
    if app_resp.is_reasoning_engine_agent:
        # 推理引擎 Agent
        ...
    elif is_v2_agent:
        # Core_v2 Agent
        logger.info("构建模式初始化Core_v2 Agent system_prompt模版！")
        app_resp.system_prompt_template = _get_v2_agent_system_prompt(app_config)
    elif ag:
        # 传统 v1 Agent
        prompt_template, template_format = ag.prompt_template("system", app_resp.language)
        app_resp.system_prompt_template = prompt_template
    else:
        # Agent 未注册，使用默认 prompt
        app_resp.system_prompt_template = _get_default_system_prompt()
```

### 2. API 端点修复 (`controller.py`)

**文件**: `packages/derisk-serve/src/derisk_serve/agent/app/controller.py`

修改 `/api/v1/agent/{agent_name}/prompt` API：

```python
@router.get("/v1/agent/{agent_name}/prompt")
async def get_agent_default_prompt(
    agent_name: str,
    language: str = "en",
    user_info: UserRequest = Depends(get_user_from_headers),
):
    try:
        agent_manager = get_agent_manager()
        agent = agent_manager.get_agent(agent_name)

        if agent is None:
            # Agent 不在 AgentManager 中
            from derisk_serve.building.app.service.service import (
                _get_v2_agent_system_prompt,
                _get_v2_agent_user_prompt,
                _get_default_system_prompt,
                _get_default_user_prompt,
            )
            
            # 判断是否为 Core_v2 Agent
            if agent_name and ('v2' in agent_name.lower() or 'core_v2' in agent_name.lower()):
                logger.info(f"Agent '{agent_name}' not found in AgentManager, returning Core_v2 default prompts")
                result = {
                    "system_prompt_template": _get_v2_agent_system_prompt(None),
                    "user_prompt_template": _get_v2_agent_user_prompt(None),
                }
            else:
                # 使用通用默认 prompt
                result = {
                    "system_prompt_template": _get_default_system_prompt(),
                    "user_prompt_template": _get_default_user_prompt(),
                }
            
            return Result.succ(result)

        # Agent 存在，使用其 prompt
        result = {
            "system_prompt_template": _get_prompt_template(
                agent.profile.system_prompt_template, language
            ),
            "user_prompt_template": _get_prompt_template(
                agent.profile.user_prompt_template, language
            ),
        }

        return Result.succ(result)
    except Exception as e:
        logger.exception(f"Get agent default prompt error: {e}")
        return Result.failed(code="E000X", msg=f"get agent default prompt error: {e}")
```

## 核心改进

### 1. 智能识别 Agent 类型
- 通过 `agent_version` 字段识别 Core_v2 Agent
- 通过 agent 名称中的 'v2' 或 'core_v2' 关键字识别

### 2. 分层 Prompt 生成策略
```
优先级：
1. 推理引擎 Agent → 使用推理引擎的 prompt
2. Core_v2 Agent → 使用 Core_v2 专用 prompt
3. 传统 v1 Agent → 使用 AgentManager 中的 prompt
4. 未注册 Agent → 使用通用默认 prompt
```

### 3. 优雅降级
- 当 Agent 不在 AgentManager 中时，不再返回错误
- 根据 Agent 类型返回合适的默认 prompt
- 保证前端始终能获取到 prompt 内容

## 效果验证

### 1. 应用编辑页面
- ✅ 创建 Core_v2 Agent 应用时，Prompt Tab 显示默认 prompt
- ✅ 可以编辑和保存自定义 prompt
- ✅ 点击"重置"按钮可恢复默认 prompt

### 2. Prompt 内容
- ✅ System Prompt 包含 Core_v2 架构说明和能力描述
- ✅ User Prompt 包含标准的请求处理模板
- ✅ 支持资源（Knowledge、Skills）的动态注入

### 3. 向后兼容
- ✅ 传统 v1 Agent 正常工作
- ✅ 推理引擎 Agent 正常工作
- ✅ 未注册 Agent 也能显示默认 prompt

## 相关文件修改

1. **后端服务层**
   - `packages/derisk-serve/src/derisk_serve/building/app/service/service.py`
     - 添加 `_get_v2_agent_system_prompt()` 函数
     - 添加 `_get_v2_agent_user_prompt()` 函数
     - 添加 `_get_default_system_prompt()` 函数
     - 添加 `_get_default_user_prompt()` 函数
     - 修改 `sync_app_detail()` 方法
     - 修改 `sync_old_app_detail()` 方法

2. **后端 API 层**
   - `packages/derisk-serve/src/derisk_serve/agent/app/controller.py`
     - 修改 `get_agent_default_prompt()` API

3. **前端**（无需修改）
   - `web/src/app/application/app/components/tab-prompts.tsx` 已正确使用 API

## 后续优化建议

1. **Prompt 模板管理**
   - 将 Core_v2 prompt 模板移到配置文件或数据库
   - 支持用户自定义 prompt 模板

2. **Agent 注册机制**
   - 考虑将 Core_v2 Agent 注册到 AgentManager
   - 或者创建新的 V2AgentManager

3. **Prompt 变量支持**
   - 增强 prompt 模板的变量系统
   - 支持动态资源注入和上下文管理

## 总结

通过这次修复，Core_v2 Agent 在应用编辑时能够正确显示和使用 prompt 模板。修复采用了智能识别和优雅降级策略，确保了系统的稳定性和向后兼容性。