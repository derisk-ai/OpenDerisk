# 产品层集成指南

本文档说明如何在当前产品层直接使用新增强的能力模块。

## 一、快速接入方式

### 1.1 直接使用核心模块

```python
# 在任何地方直接导入使用
from derisk_core import (
    # 权限控制
    PermissionChecker,
    PRIMARY_PERMISSION,
    READONLY_PERMISSION,
    
    # 沙箱执行
    DockerSandbox,
    LocalSandbox,
    SandboxFactory,
    
    # 工具系统
    tool_registry,
    register_builtin_tools,
    BashTool,
    ReadTool,
    WriteTool,
    
    # 工具组合
    BatchExecutor,
    TaskExecutor,
    WorkflowBuilder,
    
    # 配置管理
    ConfigManager,
    AppConfig,
)

# 初始化
register_builtin_tools()
config = ConfigManager.init("configs/derisk-proxy-aliyun.toml")
```

### 1.2 通过 API 调用

```python
import requests

# 获取配置
response = requests.get("http://localhost:7777/api/v1/config/current")
config = response.json()["data"]

# 执行工具
response = requests.post("http://localhost:7777/api/v1/tools/execute", json={
    "tool_name": "read",
    "args": {"file_path": "/path/to/file.py"}
})

# 批量执行
response = requests.post("http://localhost:7777/api/v1/tools/batch", json={
    "calls": [
        {"tool": "read", "args": {"file_path": "/a.py"}},
        {"tool": "read", "args": {"file_path": "/b.py"}},
    ]
})
```

---

## 二、在 Agent 中的集成

### 2.1 现有 Agent 集成权限控制

```python
# packages/derisk-serve/src/derisk_serve/agent/your_agent.py

from derisk_core import PermissionChecker, PRIMARY_PERMISSION

class YourAgent:
    def __init__(self):
        self.permission_checker = PermissionChecker(PRIMARY_PERMISSION)
        
        # 设置用户确认处理器（可选）
        self.permission_checker.set_ask_handler(self._ask_user)
    
    async def _ask_user(self, tool_name: str, args: dict) -> bool:
        """当权限为 ASK 时调用"""
        # 可以通过 WebSocket 推送到前端让用户确认
        return await self.send_to_user_and_wait_confirm(
            f"是否允许执行工具 {tool_name}?"
        )
    
    async def execute_tool(self, tool_name: str, args: dict):
        # 1. 权限检查
        result = await self.permission_checker.check(tool_name, args)
        if not result.allowed:
            return {"error": f"权限拒绝: {result.message}"}
        
        # 2. 执行工具
        tool = tool_registry.get(tool_name)
        return await tool.execute(args)
```

### 2.2 使用沙箱执行危险命令

```python
from derisk_core import DockerSandbox, SandboxFactory

class SafeAgent:
    async def execute_bash(self, command: str, use_sandbox: bool = True):
        if use_sandbox:
            # 使用 Docker 沙箱
            sandbox = await SandboxFactory.create(prefer_docker=True)
            result = await sandbox.execute(command, timeout=60)
            return result.stdout
        else:
            # 本地执行
            from derisk_core import BashTool
            tool = BashTool()
            result = await tool.execute({"command": command})
            return result.output
```

### 2.3 使用工具组合模式

```python
from derisk_core import BatchExecutor, WorkflowBuilder

class EfficientAgent:
    async def analyze_project(self, project_path: str):
        # 并行读取多个文件
        batch = BatchExecutor()
        result = await batch.execute([
            {"tool": "glob", "args": {"pattern": "**/*.py", "path": project_path}},
            {"tool": "glob", "args": {"pattern": "**/*.md", "path": project_path}},
            {"tool": "glob", "args": {"pattern": "**/requirements*.txt", "path": project_path}},
        ])
        
        files = {}
        for call_id, tool_result in result.results.items():
            if tool_result.success:
                files[call_id] = tool_result.output.split('\n')
        
        return files
    
    async def build_workflow(self):
        # 构建工作流
        workflow = (WorkflowBuilder()
            .step("read", {"file_path": "/config.json"}, name="config")
            .step("bash", {"command": "npm install"}, name="install")
            .step("bash", {"command": "npm run build"}, name="build")
            .parallel([
                {"tool": "bash", "args": {"command": "npm run test"}},
                {"tool": "bash", "args": {"command": "npm run lint"}},
            ])
        )
        
        results = await workflow.run()
        return results
```

---

## 三、在前端中的集成

### 3.1 使用配置管理服务

```typescript
// 在 React 组件中使用
import { configService, toolsService } from '@/services/config';

// 获取配置
const config = await configService.getConfig();

// 更新模型配置
await configService.updateModelConfig({
  temperature: 0.8,
  max_tokens: 8192,
});

// 创建 Agent
await configService.createAgent({
  name: 'my-agent',
  description: '自定义 Agent',
  max_steps: 30,
});
```

### 3.2 执行工具

```typescript
// 执行单个工具
const result = await toolsService.executeTool('read', {
  file_path: '/path/to/file.py',
});

// 批量执行
const batchResult = await toolsService.batchExecute([
  { tool: 'glob', args: { pattern: '**/*.py' } },
  { tool: 'grep', args: { pattern: 'def\\s+\\w+' } },
]);

// 检查权限
const permission = await toolsService.checkPermission('bash', {
  command: 'rm -rf /',
});
if (!permission.allowed) {
  alert(permission.message);
}
```

---

## 四、API 端点列表

### 配置管理 API (`/api/v1/config`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/current` | GET | 获取当前完整配置 |
| `/schema` | GET | 获取配置 Schema |
| `/model` | GET/POST | 获取/更新模型配置 |
| `/agents` | GET | 列出所有 Agent |
| `/agents/{name}` | GET/PUT/DELETE | Agent CRUD |
| `/sandbox` | GET/POST | 获取/更新沙箱配置 |
| `/validate` | POST | 验证配置 |
| `/reload` | POST | 重新加载配置 |
| `/export` | GET | 导出配置为 JSON |
| `/import` | POST | 导入配置 |

### 工具执行 API (`/api/v1/tools`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/list` | GET | 列出所有可用工具 |
| `/schemas` | GET | 获取所有工具 Schema |
| `/{name}/schema` | GET | 获取单个工具 Schema |
| `/execute` | POST | 执行单个工具 |
| `/batch` | POST | 批量并行执行工具 |
| `/permission/check` | POST | 检查工具权限 |
| `/permission/presets` | GET | 获取预设权限配置 |
| `/sandbox/status` | GET | 获取沙箱状态 |

---

## 五、完整集成示例

### 5.1 创建自定义 Agent

```python
# packages/derisk-ext/src/derisk_ext/agent/custom_agent.py

from derisk_core import (
    AgentConfig,
    PermissionConfig,
    PermissionChecker,
    PRIMARY_PERMISSION,
    DockerSandbox,
    tool_registry,
    register_builtin_tools,
    BatchExecutor,
)
from derisk_serve.agent import AgentBase  # 现有基类

class CodeAnalysisAgent(AgentBase):
    """代码分析 Agent - 使用新能力"""
    
    def __init__(self):
        super().__init__()
        
        # 初始化工具
        register_builtin_tools()
        
        # 配置权限（只读）
        self.permission_checker = PermissionChecker(
            PRIMARY_PERMISSION.merge(READONLY_PERMISSION)
        )
        
        # 配置沙箱
        self.sandbox = DockerSandbox()
    
    async def analyze_file(self, file_path: str) -> dict:
        """分析单个文件"""
        # 权限检查
        perm = await self.permission_checker.check("read", {"file_path": file_path})
        if not perm.allowed:
            return {"error": perm.message}
        
        # 读取文件
        read_tool = tool_registry.get("read")
        result = await read_tool.execute({"file_path": file_path})
        
        if not result.success:
            return {"error": result.error}
        
        # 分析代码
        content = result.output
        analysis = await self._analyze_content(content)
        
        return analysis
    
    async def analyze_project(self, project_path: str) -> dict:
        """并行分析整个项目"""
        batch = BatchExecutor()
        
        # 并行执行多个分析
        result = await batch.execute([
            {"tool": "glob", "args": {"pattern": "**/*.py", "path": project_path}, "id": "py_files"},
            {"tool": "glob", "args": {"pattern": "**/*.js", "path": project_path}, "id": "js_files"},
            {"tool": "grep", "args": {"pattern": r"TODO|FIXME|XXX", "path": project_path}, "id": "todos"},
            {"tool": "grep", "args": {"pattern": r"def\s+\w+\(", "path": project_path, "include": "*.py"}, "id": "functions"},
        ])
        
        return {
            "py_files": result.results["py_files"].output if result.results.get("py_files") else "",
            "js_files": result.results["js_files"].output if result.results.get("js_files") else "",
            "todos": result.results["todos"].output if result.results.get("todos") else "",
            "functions": result.results["functions"].output if result.results.get("functions") else "",
        }
    
    async def execute_in_sandbox(self, command: str) -> str:
        """在沙箱中安全执行"""
        result = await self.sandbox.execute(command)
        if not result.success:
            raise Exception(result.error)
        return result.stdout
```

### 5.2 在 API 路由中使用

```python
# 添加到 packages/derisk-app/src/derisk_app/openapi/api_v1/

from fastapi import APIRouter
from derisk_core import tool_registry, register_builtin_tools, BatchExecutor

router = APIRouter(prefix="/custom", tags=["Custom"])

@router.post("/analyze")
async def analyze_code(request: dict):
    """代码分析接口"""
    register_builtin_tools()
    
    # 获取文件内容
    file_path = request.get("file_path")
    read_tool = tool_registry.get("read")
    result = await read_tool.execute({"file_path": file_path})
    
    if not result.success:
        return {"success": False, "error": result.error}
    
    # 分析...
    content = result.output
    
    return {"success": True, "content": content}

@router.post("/batch-analyze")
async def batch_analyze(request: dict):
    """批量分析"""
    files = request.get("files", [])
    
    batch = BatchExecutor()
    calls = [
        {"tool": "read", "args": {"file_path": f}, "id": f}
        for f in files
    ]
    
    result = await batch.execute(calls)
    
    return {
        "success": result.failure_count == 0,
        "results": {
            call_id: {
                "success": r.success,
                "content": r.output if r.success else r.error
            }
            for call_id, r in result.results.items()
        }
    }
```

---

## 六、配置页面使用

访问 `/settings/config` 可以：

1. **可视化配置** - 通过表单修改模型、Agent、沙箱配置
2. **JSON 编辑** - 直接编辑 JSON 配置文件
3. **工具管理** - 查看所有可用工具及其 Schema
4. **验证配置** - 检查配置是否正确
5. **导入导出** - 导出配置或导入新配置

---

## 七、迁移指南

### 从旧配置迁移

```python
# 旧方式
from derisk_app.config import Config

# 新方式 - 直接使用 ConfigManager
from derisk_core import ConfigManager

config = ConfigManager.get()
model = config.default_model.model_id
```

### 从旧工具迁移

```python
# 旧方式 - 各自实现的工具
from some_module import read_file, write_file

# 新方式 - 统一工具系统
from derisk_core import tool_registry, ReadTool, WriteTool

# 方式1：直接使用工具类
tool = ReadTool()
result = await tool.execute({"file_path": "/path/to/file"})

# 方式2：通过注册表
register_builtin_tools()
tool = tool_registry.get("read")
result = await tool.execute({"file_path": "/path/to/file"})
```

---

## 八、常见问题

### Q: 如何自定义权限规则？

```python
from derisk_core import PermissionRuleset, PermissionRule, PermissionAction

custom_permission = PermissionRuleset(
    rules={
        "read": PermissionRule(tool_pattern="read", action=PermissionAction.ALLOW),
        "write": PermissionRule(tool_pattern="write", action=PermissionAction.ASK),
        "bash": PermissionRule(tool_pattern="bash", action=PermissionAction.DENY),
    },
    default_action=PermissionAction.DENY
)
```

### Q: 如何添加自定义工具？

```python
from derisk_core import ToolBase, ToolMetadata, ToolResult, ToolCategory, ToolRisk

class MyCustomTool(ToolBase):
    def _define_metadata(self):
        return ToolMetadata(
            name="my_tool",
            description="我的自定义工具",
            category=ToolCategory.SYSTEM,
            risk=ToolRisk.MEDIUM,
        )
    
    def _define_parameters(self):
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string"}
            },
            "required": ["input"]
        }
    
    async def execute(self, args, context=None):
        # 实现你的逻辑
        return ToolResult(success=True, output="result")

# 注册
tool_registry.register(MyCustomTool())
```

### Q: Docker 不可用怎么办？

```python
from derisk_core import SandboxFactory

# 自动降级到本地沙箱
sandbox = await SandboxFactory.create(prefer_docker=True)
# 如果 Docker 不可用，会自动返回 LocalSandbox
```