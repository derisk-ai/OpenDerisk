"""
工具授权中间件使用指南

为 bash 工具提供基于执行目录的授权检查。

## 快速开始

### 1. Core 架构集成

```python
from derisk.agent.tools import (
    AgentToolAdapter,
    create_tool_adapter_for_agent,
)

# 创建适配器（带 InteractionGateway）
adapter = create_tool_adapter_for_agent(
    agent=core_agent,
    interaction_gateway=interaction_gateway,  # 用于用户授权交互
)

# 获取 Core 适配器
core_adapter = adapter.adapt_for_core()

# 执行工具（会自动进行 cwd 授权检查）
result = await core_adapter.execute_for_core(
    action_input={
        "tool_name": "bash",
        "args": {"command": "ls -la", "cwd": "/etc"},
    },
    agent_context=core_agent.agent_context,
)
```

### 2. CoreV2 架构集成

```python
from derisk.agent.tools import (
    AgentToolAdapter,
    create_tool_adapter_for_agent,
)

# 在 Agent 初始化时创建适配器
class MyAgent(BaseBuiltinAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 创建工具适配器
        self._tool_adapter = create_tool_adapter_for_agent(
            agent=self,
            interaction_gateway=kwargs.get("interaction_gateway"),
        )
        self._core_v2_adapter = self._tool_adapter.adapt_for_core_v2()
    
    async def execute_tool(self, tool_name, tool_args, **kwargs):
        # 使用适配器执行工具（带授权检查）
        result = await self._core_v2_adapter.execute_for_core_v2(
            tool_call={
                "name": tool_name,
                "args": tool_args,
            },
            execution_context=self.context,
        )
        
        return ToolResult(
            success=result["success"],
            output=result["content"],
            metadata=result["metadata"],
        )
```

### 3. 在 Runtime 中设置 InteractionGateway

```python
from derisk.agent.core_v2.integration import AgentRuntime

runtime = AgentRuntime(
    agent=agent,
    interaction_gateway=gateway,
)

# 这会调用 agent.set_interaction_gateway(gateway)
# 如果 agent 有 tool_adapter，也会自动设置
if hasattr(agent, "_tool_adapter"):
    agent._tool_adapter.set_interaction_gateway(gateway)
```

## 授权流程

### 场景 1: cwd 在 sandbox 内
```
User: 执行 bash 命令 "ls -la"，cwd="/workspace"
Agent: 检测到 cwd /workspace 在 sandbox 内，直接执行
Result: 无需授权，直接返回结果
```

### 场景 2: cwd 在 sandbox 外
```
User: 执行 bash 命令 "cat /etc/passwd"，cwd="/etc"
Agent: 检测到 cwd /etc 在 sandbox /workspace 外
Agent: 通过 InteractionGateway 发送授权请求
User: 在前端看到授权弹窗
User: 点击"Allow Once"或"Allow for Session"
Agent: 收到授权响应，执行命令
Result: 返回执行结果
```

### 场景 3: 无 sandbox（本地模式）
```
User: 执行 bash 命令 "rm -rf /tmp/*"
Agent: 检测到无 sandbox，本地执行
Agent: 需要用户授权
User: 在前端确认授权
Agent: 执行命令
```

## 前端展示

前端会收到 `InteractionType.AUTHORIZATION` 类型的交互请求：

```json
{
  "type": "interaction_request",
  "data": {
    "type": "authorization",
    "title": "Authorization: bash",
    "message": "**Tool Authorization Required**\n\n**Tool:** `bash`\n**Command:** `cat /etc/passwd`\n**Working Directory:** `/etc`\n\n**Reason:** Execution directory '/etc' is outside sandbox working directory '/workspace'\n\nDo you want to allow this command to execute outside the sandbox?",
    "options": [
      {"label": "Allow Once", "value": "allow_once"},
      {"label": "Allow for Session", "value": "allow_session"},
      {"label": "Deny", "value": "deny"}
    ]
  }
}
```

前端可以使用 VisConfirmCard 或专门的授权组件来展示。

## 配置选项

### 通过工具配置关闭 CWD 授权检查

你可以在工具定义中通过 `authorization_config` 关闭 cwd 授权检查：

```python
from derisk.agent.tools import ToolMetadata, ToolCategory, ToolRiskLevel

class MyBashTool(ToolBase):
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="bash",
            display_name="Execute Bash",
            description="Execute bash commands",
            category=ToolCategory.SHELL,
            risk_level=ToolRiskLevel.HIGH,
            requires_permission=True,
            # 关闭 cwd 授权检查
            authorization_config={
                "disable_cwd_check": True
            },
        )
```

当 `disable_cwd_check` 设置为 `True` 时：
- bash 工具执行时不再检查 cwd 是否在 sandbox 内
- 但仍会检查 `requires_permission`（如果为 True，仍会弹出授权确认）
- 适用于完全信任的环境或特定的沙箱配置

### 全局配置关闭

你也可以在全局配置中禁用特定工具的 cwd 检查：

```python
from derisk.agent.tools import tool_registry

# 获取工具并修改配置
bash_tool = tool_registry.get("bash")
if bash_tool:
    bash_tool.metadata.authorization_config["disable_cwd_check"] = True
```

### 自定义授权检查器

```python
from derisk.agent.tools import (
    ToolAuthorizationMiddleware,
    ToolSpecificAuthorizer,
    AuthorizationContext,
    AuthorizationCheckResult,
    AuthorizationDecision,
)

class MyCustomAuthorizer(ToolSpecificAuthorizer):
    def can_handle(self, tool_name: str) -> bool:
        return tool_name == "my_tool"
    
    async def check(self, context: AuthorizationContext) -> AuthorizationCheckResult:
        # 自定义授权逻辑
        if should_allow(context.tool_args):
            return AuthorizationCheckResult(
                decision=AuthorizationDecision.ALLOW,
                reason="Custom check passed",
            )
        else:
            return AuthorizationCheckResult(
                decision=AuthorizationDecision.ASK_USER,
                reason="Custom check failed",
            )

# 注册自定义检查器
middleware = ToolAuthorizationMiddleware()
middleware.register_authorizer("my_tool", MyCustomAuthorizer())
```

### 跳过授权检查

```python
# 对于内部调用，可以跳过授权
result = await adapter.execute_tool(
    tool_name="bash",
    args={"command": "ls"},
    context=context,
    skip_authorization=True,  # 跳过授权检查
)
```

## 工作原理

1. **工具执行前**: `AgentToolAdapter.execute_tool` 调用 `_auth_middleware.execute_with_auth`
2. **授权检查**: `ToolAuthorizationMiddleware` 检查工具是否需要授权
   - 对于 bash 工具：检查 cwd 是否在 sandbox work_dir 内
   - 对于其他工具：检查 metadata.requires_permission
3. **用户交互**: 如果需要授权，通过 InteractionGateway 发送请求并等待响应
4. **执行工具**: 授权通过后，执行工具并返回结果

## 注意事项

1. **sandbox_client 注入**: 确保 context 中包含 sandbox_client，否则 cwd 检查会失败
2. **InteractionGateway**: 设置后才能进行用户交互式授权
3. **会话缓存**: 用户选择"Allow for Session"后会话内无需再次授权
4. **错误处理**: 授权失败会返回 `ToolResult` 而不是抛出异常

## 测试

```python
# 测试 cwd 检查
from derisk.agent.tools.authorization_middleware import BashCwdAuthorizer

authorizer = BashCwdAuthorizer()
result = await authorizer.check(AuthorizationContext(
    tool_name="bash",
    tool_args={"command": "ls", "cwd": "/etc"},
    sandbox_work_dir="/workspace",
))

assert result.decision == AuthorizationDecision.ASK_USER
```
