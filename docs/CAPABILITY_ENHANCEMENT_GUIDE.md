# OpenDeRisk 能力增强指南

本文档介绍 OpenDeRisk 新增的核心能力模块，帮助开发者快速理解和使用这些功能。

## 目录

1. [权限控制系统](#权限控制系统)
2. [沙箱隔离系统](#沙箱隔离系统)
3. [代码操作工具](#代码操作工具)
4. [网络请求工具](#网络请求工具)
5. [工具组合模式](#工具组合模式)
6. [统一配置系统](#统一配置系统)

---

## 权限控制系统

参考 OpenCode 的 Permission Ruleset 设计，提供精细化的工具权限控制。

### 核心概念

```python
from derisk_core import PermissionRuleset, PermissionRule, PermissionAction

# 创建权限规则集
ruleset = PermissionRuleset(
    rules={
        "*": PermissionRule(tool_pattern="*", action=PermissionAction.ALLOW),
        "*.env": PermissionRule(tool_pattern="*.env", action=PermissionAction.ASK),
        "bash:rm": PermissionRule(tool_pattern="bash:rm", action=PermissionAction.DENY),
    },
    default_action=PermissionAction.ASK
)

# 检查权限
action = ruleset.check("read")      # -> ALLOW
action = ruleset.check(".env")      # -> ASK
action = ruleset.check("bash:rm")   # -> DENY
```

### 预设权限配置

```python
from derisk_core import PRIMARY_PERMISSION, READONLY_PERMISSION, EXPLORE_PERMISSION, SANDBOX_PERMISSION

# 主Agent权限 - 完整权限，敏感文件需要确认
PRIMARY_PERMISSION.check("bash")      # ALLOW
PRIMARY_PERMISSION.check(".env")      # ASK

# 只读Agent权限 - 只允许读取操作
READONLY_PERMISSION.check("read")     # ALLOW
READONLY_PERMISSION.check("write")    # DENY
READONLY_PERMISSION.check("bash")     # ASK

# 探索Agent权限 - 只允许查找和搜索
EXPLORE_PERMISSION.check("glob")      # ALLOW
EXPLORE_PERMISSION.check("grep")      # ALLOW
EXPLORE_PERMISSION.check("bash")      # DENY

# 沙箱权限 - 受限执行环境
SANDBOX_PERMISSION.check("bash")      # ALLOW
SANDBOX_PERMISSION.check(".env")      # DENY
```

### 权限检查器

```python
from derisk_core import PermissionChecker

checker = PermissionChecker(ruleset)

async def ask_user_handler(tool_name: str, args: dict) -> bool:
    """自定义询问处理器"""
    return input(f"允许执行 {tool_name}? [y/N]: ").lower() == 'y'

checker.set_ask_handler(ask_user_handler)

# 异步检查权限
result = await checker.check("bash", {"command": "rm -rf /"})
print(result.allowed)  # False
print(result.message)  # "删除操作需要确认"
```

---

## 沙箱隔离系统

参考 OpenClaw 的 Docker Sandbox 设计，提供安全的命令执行环境。

### Docker 沙箱

```python
from derisk_core import DockerSandbox, SandboxConfig

# 创建配置
config = SandboxConfig(
    image="python:3.11-slim",
    timeout=300,
    memory_limit="512m",
    cpu_limit=1.0,
    network_enabled=False,  # 禁用网络
)

# 创建沙箱
sandbox = DockerSandbox(config)

# 一次性执行（不保持容器）
result = await sandbox.execute("python -c 'print(1+1)'")
print(result.success)    # True
print(result.stdout)     # "2\n"

# 带工作目录执行
result = await sandbox.execute(
    "pytest tests/",
    cwd="/home/user/project"
)
```

### 沙箱工厂

```python
from derisk_core import SandboxFactory

# 自动选择最佳沙箱（优先Docker）
sandbox = await SandboxFactory.create(prefer_docker=True)

# 强制使用Docker
docker_sandbox = SandboxFactory.create_docker()

# 强制使用本地沙箱
local_sandbox = SandboxFactory.create_local()
```

### 本地沙箱（降级方案）

```python
from derisk_core import LocalSandbox

local = LocalSandbox()
result = await local.execute("ls -la", cwd="/tmp")

# 本地沙箱会阻止危险命令
result = await local.execute("rm -rf /")
print(result.success)  # False
print(result.error)    # "禁止执行的危险命令"
```

---

## 代码操作工具

参考 OpenCode 的代码操作能力，提供完整的文件和代码操作工具。

### 文件读取

```python
from derisk_core import ReadTool

tool = ReadTool()
result = await tool.execute({
    "file_path": "/path/to/file.py",
    "offset": 1,       # 起始行号
    "limit": 100       # 读取行数
})

print(result.output)  # 带行号的文件内容
# 1: def hello():
# 2:     print("world")
```

### 文件写入

```python
from derisk_core import WriteTool

tool = WriteTool()

# 创建新文件
result = await tool.execute({
    "file_path": "/path/to/new.py",
    "content": "print('hello')"
})

# 追加内容
result = await tool.execute({
    "file_path": "/path/to/new.py",
    "content": "\nprint('world')",
    "mode": "append"
})
```

### 文件编辑（精确替换）

```python
from derisk_core import EditTool

tool = EditTool()

# 精确替换
result = await tool.execute({
    "file_path": "/path/to/file.py",
    "old_string": "print('old')",
    "new_string": "print('new')"
})

# 替换所有匹配
result = await tool.execute({
    "file_path": "/path/to/file.py",
    "old_string": "old_var",
    "new_string": "new_var",
    "replace_all": True
})
```

### 文件搜索

```python
from derisk_core import GlobTool, GrepTool

# 通配符搜索
glob = GlobTool()
result = await glob.execute({
    "pattern": "**/*.py",
    "path": "/project/src"
})

# 内容搜索（正则）
grep = GrepTool()
result = await grep.execute({
    "pattern": r"def\s+\w+\(",
    "path": "/project/src",
    "include": "*.py"
})
```

### Bash 命令执行

```python
from derisk_core import BashTool

tool = BashTool(sandbox_mode="auto")

# 本地执行
result = await tool.execute({
    "command": "pytest tests/",
    "timeout": 60
})

# Docker 沙箱执行
result = await tool.execute({
    "command": "pip install pytest",
    "sandbox": "docker"
})
```

---

## 网络请求工具

### 网页获取

```python
from derisk_core import WebFetchTool

tool = WebFetchTool()

# 获取网页（Markdown格式）
result = await tool.execute({
    "url": "https://example.com",
    "format": "markdown"
})

# 获取JSON API
result = await tool.execute({
    "url": "https://api.github.com/repos/python/cpython",
    "format": "json"
})

# 自定义请求头
result = await tool.execute({
    "url": "https://api.example.com/data",
    "headers": {"Authorization": "Bearer token"}
})
```

### 网络搜索

```python
from derisk_core import WebSearchTool

tool = WebSearchTool()
result = await tool.execute({
    "query": "Python async best practices",
    "num_results": 5
})

print(result.output)
# **Title 1**
# https://example.com/article1
# Article snippet...
```

---

## 工具组合模式

参考 OpenCode 的 Batch 和 Task 模式，支持高级工具组合。

### 并行执行（Batch）

```python
from derisk_core import BatchExecutor

executor = BatchExecutor()

# 并行执行多个工具调用
result = await executor.execute([
    {"tool": "read", "args": {"file_path": "/a.py"}},
    {"tool": "read", "args": {"file_path": "/b.py"}},
    {"tool": "glob", "args": {"pattern": "**/*.md"}},
])

print(result.success_count)   # 成功数量
print(result.failure_count)   # 失败数量
print(result.results)         # 结果字典
```

### 子任务委派（Task）

```python
from derisk_core import TaskExecutor

executor = TaskExecutor()

# 生成子任务
result = await executor.spawn({
    "tool": "bash",
    "args": {"command": "pytest tests/"}
})

print(result.task_id)   # "task_1"
print(result.success)   # True/False
```

### 工作流构建

```python
from derisk_core import WorkflowBuilder

# 链式构建工作流
workflow = (WorkflowBuilder()
    .step("read", {"file_path": "/config.json"}, name="load_config")
    .step("bash", {"command": "npm install"}, name="install_deps")
    .step("bash", {"command": "npm run build"}, name="build")
    .parallel([
        {"tool": "bash", "args": {"command": "npm run test"}},
        {"tool": "bash", "args": {"command": "npm run lint"}},
    ])
)

# 执行工作流
results = await workflow.run()

# 引用前一步骤的结果
workflow2 = (WorkflowBuilder()
    .step("read", {"file_path": "/config.json"}, name="config")
    .step("write", {
        "file_path": "/output.txt",
        "content": "${config}"  # 引用config步骤的输出
    })
)
```

---

## 统一配置系统

简化的配置体验，支持 JSON 配置和环境变量。

### 配置文件 (derisk.json)

```json
{
  "name": "MyProject",
  "default_model": {
    "provider": "openai",
    "model_id": "gpt-4",
    "api_key": "${OPENAI_API_KEY}"
  },
  "agents": {
    "primary": {
      "name": "primary",
      "description": "主Agent",
      "max_steps": 20
    },
    "readonly": {
      "name": "readonly",
      "description": "只读Agent",
      "permission": {
        "default_action": "deny",
        "rules": {
          "read": "allow",
          "glob": "allow"
        }
      }
    }
  },
  "sandbox": {
    "enabled": false,
    "image": "python:3.11-slim"
  },
  "workspace": "~/.derisk/workspace"
}
```

### 配置加载

```python
from derisk_core import ConfigLoader, ConfigManager

# 自动加载配置（查找当前目录和 ~/.derisk/）
config = ConfigLoader.load()

# 从指定路径加载
config = ConfigLoader.load("/path/to/config.json")

# 全局配置管理
ConfigManager.init("/path/to/config.json")
config = ConfigManager.get()

# 重新加载配置
ConfigManager.reload()

# 验证配置
from derisk_core import ConfigValidator
warnings = ConfigValidator.validate(config)
for level, msg in warnings:
    print(f"[{level}] {msg}")
```

### 生成默认配置

```python
# Python方式
ConfigLoader.generate_default("derisk.json")

# 或使用CLI
# python -m derisk_core.config init -o derisk.json
```

---

## 快速开始

### 安装依赖

```bash
# 基础安装
uv sync --extra "base"

# 网络请求支持
uv sync --extra "proxy_openai"

# RAG支持
uv sync --extra "rag"
```

### 完整示例

```python
import asyncio
from derisk_core import (
    ConfigManager,
    PRIMARY_PERMISSION,
    PermissionChecker,
    DockerSandbox,
    tool_registry,
    register_builtin_tools,
    BatchExecutor,
)

async def main():
    # 1. 加载配置
    config = ConfigManager.init("derisk.json")
    
    # 2. 注册工具
    register_builtin_tools()
    
    # 3. 设置权限检查
    checker = PermissionChecker(PRIMARY_PERMISSION)
    
    # 4. 检查并执行
    result = await checker.check("bash", {"command": "ls"})
    if result.allowed:
        tool = tool_registry.get("bash")
        exec_result = await tool.execute({"command": "ls -la"})
        print(exec_result.output)
    
    # 5. 并行执行
    batch = BatchExecutor()
    batch_result = await batch.execute([
        {"tool": "glob", "args": {"pattern": "**/*.py"}},
        {"tool": "glob", "args": {"pattern": "**/*.md"}},
    ])
    print(f"找到 {batch_result.success_count} 个匹配")

asyncio.run(main())
```

---

## 与 OpenCode/OpenClaw 能力对比

| 能力 | OpenDeRisk | OpenCode | OpenClaw |
|------|------------|----------|----------|
| 权限控制 | ✅ Permission Ruleset | ✅ Permission Ruleset | ⚠️ Session Sandbox |
| 沙箱隔离 | ✅ Docker + Local | ❌ 无 | ✅ Docker Sandbox |
| 代码操作 | ✅ 完整工具集 | ✅ + LSP | ✅ 基础工具 |
| 网络请求 | ✅ WebFetch + Search | ✅ WebFetch | ✅ Browser |
| 工具组合 | ✅ Batch + Task + Workflow | ✅ Batch + Task | ❌ 无 |
| 配置系统 | ✅ JSON + 环境变量 | ✅ JSON | ✅ JSON |

---

## 下一步

1. 阅读详细API文档：`packages/derisk-core/src/derisk_core/`
2. 查看测试用例：`tests/`
3. 集成到现有Agent：参考 `packages/derisk-serve/`