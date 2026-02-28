# OpenDeRisk 能力增强完成报告

## 执行摘要

基于对 OpenCode (112k stars) 和 OpenClaw (234k stars) 两大顶级开源项目的深度对比分析，已成功补齐 OpenDeRisk 在代码操作、网络请求、沙箱隔离、权限控制等方面的能力短板，并优化了维护配置便捷度。

## 一、已完成能力模块

### 1. 权限控制系统 ✅

**实现路径**: `packages/derisk-core/src/derisk_core/permission/`

**核心文件**:
- `ruleset.py` - 权限规则集实现
- `checker.py` - 权限检查器
- `presets.py` - 预设权限配置

**能力对比**:
| 功能 | OpenDeRisk | OpenCode | OpenClaw |
|------|------------|----------|----------|
| 规则集定义 | ✅ Pydantic | ✅ Zod | ⚠️ 配置 |
| 通配符匹配 | ✅ fnmatch | ✅ glob | ❌ |
| 预设权限 | ✅ 4种 | ✅ 2种 | ❌ |
| 异步检查 | ✅ | ✅ | ⚠️ |

**改进幅度**: 从基础权限到精细 Ruleset 控制，达到 OpenCode 同等水平。

---

### 2. 沙箱隔离系统 ✅

**实现路径**: `packages/derisk-core/src/derisk_core/sandbox/`

**核心文件**:
- `docker_sandbox.py` - Docker沙箱实现
- `local_sandbox.py` - 本地沙箱（降级方案）
- `factory.py` - 沙箱工厂

**能力对比**:
| 功能 | OpenDeRisk | OpenCode | OpenClaw |
|------|------------|----------|----------|
| Docker隔离 | ✅ | ❌ | ✅ |
| 资源限制 | ✅ CPU/内存 | ❌ | ✅ |
| 网络隔离 | ✅ | ❌ | ✅ |
| 自动降级 | ✅ | N/A | ⚠️ |

**改进幅度**: 从无沙箱到完整 Docker 隔离，达到 OpenClaw 同等水平。

---

### 3. 代码操作工具 ✅

**实现路径**: `packages/derisk-core/src/derisk_core/tools/code_tools.py`

**工具列表**:
| 工具 | 功能 | 风险等级 |
|------|------|----------|
| ReadTool | 读取文件内容 | LOW |
| WriteTool | 创建/覆盖文件 | MEDIUM |
| EditTool | 精确字符串替换 | MEDIUM |
| GlobTool | 通配符文件搜索 | LOW |
| GrepTool | 正则内容搜索 | LOW |

**能力对比**:
| 功能 | OpenDeRisk | OpenCode | OpenClaw |
|------|------------|----------|----------|
| 文件读写 | ✅ | ✅ | ✅ |
| 精确编辑 | ✅ | ✅ | ⚠️ |
| 搜索工具 | ✅ | ✅ | ✅ |
| LSP集成 | ❌ | ✅ | ❌ |

**改进幅度**: 从基础文件操作到完整工具集，接近 OpenCode 水平（LSP集成待后续）。

---

### 4. 网络请求工具 ✅

**实现路径**: `packages/derisk-core/src/derisk_core/tools/network_tools.py`

**工具列表**:
| 工具 | 功能 | 输出格式 |
|------|------|----------|
| WebFetchTool | 获取网页内容 | text/markdown/json/html |
| WebSearchTool | 网络搜索 | 结构化结果 |

**能力对比**:
| 功能 | OpenDeRisk | OpenCode | OpenClaw |
|------|------------|----------|----------|
| 网页获取 | ✅ | ✅ | ✅ |
| 格式转换 | ✅ Markdown | ✅ | ⚠️ |
| 网络搜索 | ✅ DuckDuckGo | ❌ | ❌ |
| 浏览器控制 | ❌ | ❌ | ✅ |

**改进幅度**: 从基础请求到完整网络工具集，新增搜索能力。

---

### 5. 工具组合模式 ✅

**实现路径**: `packages/derisk-core/src/derisk_core/tools/composition.py`

**核心组件**:
| 组件 | 功能 | 参考来源 |
|------|------|----------|
| BatchExecutor | 并行执行多个工具 | OpenCode |
| TaskExecutor | 子任务委派 | OpenCode |
| WorkflowBuilder | 链式工作流构建 | 新增 |

**能力对比**:
| 功能 | OpenDeRisk | OpenCode | OpenClaw |
|------|------------|----------|----------|
| 并行执行 | ✅ | ✅ | ❌ |
| 任务委派 | ✅ | ✅ | ❌ |
| 工作流 | ✅ | ❌ | ❌ |
| 条件分支 | ✅ | ❌ | ❌ |

**改进幅度**: 新增高级工具组合能力，超越 OpenCode/OpenClaw。

---

### 6. 统一配置系统 ✅

**实现路径**: `packages/derisk-core/src/derisk_core/config/`

**核心文件**:
- `schema.py` - 配置Schema定义
- `loader.py` - 配置加载器
- `validator.py` - 配置验证器

**能力对比**:
| 功能 | OpenDeRisk | OpenCode | OpenClaw |
|------|------------|----------|----------|
| 配置格式 | ✅ JSON | ✅ JSON | ✅ JSON |
| 环境变量 | ✅ ${VAR} | ⚠️ | ✅ |
| 自动发现 | ✅ | ✅ | ✅ |
| 配置验证 | ✅ | ⚠️ | ✅ |
| CLI工具 | ✅ | ❌ | ✅ doctor |

**改进幅度**: 从多TOML文件到单一JSON配置，大幅简化配置体验。

---

## 二、文件结构总览

```
packages/derisk-core/src/derisk_core/
├── __init__.py                    # 主入口，导出所有模块
├── permission/                    # 权限控制系统
│   ├── __init__.py
│   ├── ruleset.py                 # 权限规则集
│   ├── checker.py                 # 权限检查器
│   └── presets.py                 # 预设权限
├── sandbox/                       # 沙箱隔离系统
│   ├── __init__.py
│   ├── base.py                    # 沙箱基类
│   ├── docker_sandbox.py          # Docker沙箱
│   ├── local_sandbox.py           # 本地沙箱
│   └── factory.py                 # 沙箱工厂
├── tools/                         # 工具系统
│   ├── __init__.py
│   ├── base.py                    # 工具基类
│   ├── code_tools.py              # 代码操作工具
│   ├── bash_tool.py               # Bash工具
│   ├── network_tools.py           # 网络请求工具
│   ├── composition.py             # 工具组合模式
│   └── registry.py                # 工具注册表
└── config/                        # 配置系统
    ├── __init__.py
    ├── schema.py                  # 配置Schema
    ├── loader.py                  # 配置加载器
    └── validator.py               # 配置验证器

configs/
└── derisk.default.json            # 默认配置示例

docs/
└── CAPABILITY_ENHANCEMENT_GUIDE.md # 能力增强指南

tests/
└── test_new_capabilities.py       # 新能力测试用例

scripts/
└── derisk_config.py               # 配置管理CLI
```

---

## 三、能力差距修复状态

| 差距项 | 原状态 | 修复后状态 | 目标状态 |
|--------|--------|------------|----------|
| 代码操作 | ⚠️ 基础 | ✅ 完整 | ✅ 达成 |
| 网络请求 | ⚠️ 基础 | ✅ 完整 | ✅ 达成 |
| 沙箱隔离 | ❌ 无 | ✅ Docker | ✅ 达成 |
| 权限控制 | ⚠️ 基础 | ✅ Ruleset | ✅ 达成 |
| 工具组合 | ❌ 无 | ✅ Batch/Task/Workflow | ✅ 超越 |
| 配置便捷度 | ⚠️ 复杂 | ✅ 简化 | ✅ 达成 |

---

## 四、与 OpenCode/OpenClaw 能力对比总结

### 能力矩阵（修复后）

| 能力领域 | OpenDeRisk | OpenCode | OpenClaw | 评价 |
|----------|------------|----------|----------|------|
| **权限控制** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | 并列领先 |
| **沙箱隔离** | ⭐⭐⭐ | ⭐ | ⭐⭐⭐ | 并列领先 |
| **代码操作** | ⭐⭐⭐ | ⭐⭐⭐+LSP | ⭐⭐ | 接近领先 |
| **网络请求** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐+Browser | 并列领先 |
| **工具组合** | ⭐⭐⭐+Workflow | ⭐⭐⭐ | ⭐ | **领先** |
| **配置体验** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | 并列领先 |
| **多渠道** | ⭐ | ⭐ | ⭐⭐⭐ | 待改进 |
| **语音交互** | ⭐ | ⭐ | ⭐⭐⭐ | 待改进 |

---

## 五、使用示例

### 快速开始

```python
from derisk_core import (
    ConfigManager,
    PermissionChecker,
    PRIMARY_PERMISSION,
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
    
    # 3. 权限检查
    checker = PermissionChecker(PRIMARY_PERMISSION)
    result = await checker.check("bash", {"command": "ls"})
    
    # 4. 沙箱执行
    sandbox = DockerSandbox()
    exec_result = await sandbox.execute("pip install requests")
    
    # 5. 并行执行
    batch = BatchExecutor()
    batch_result = await batch.execute([
        {"tool": "glob", "args": {"pattern": "**/*.py"}},
        {"tool": "grep", "args": {"pattern": "def\\s+\\w+"}},
    ])
```

---

## 六、后续建议

### Phase 2 可选增强
1. **LSP集成** - 代码补全、重构能力
2. **多渠道接入** - 参考 OpenClaw Channel 层
3. **语音交互** - Voice Wake + TTS
4. **浏览器控制** - CDP 协议集成

### 维护建议
1. 持续同步上游 OpenCode/OpenClaw 改进
2. 增加集成测试覆盖
3. 建立性能基准测试

---

## 七、总结

本次能力增强工作成功补齐了 OpenDeRisk 与 OpenCode/OpenClaw 之间的主要能力差距：

- **权限控制**: 达到 OpenCode 同等水平
- **沙箱隔离**: 达到 OpenClaw 同等水平
- **代码操作**: 接近 OpenCode 水平（待LSP）
- **网络请求**: 达到 OpenClaw 同等水平
- **工具组合**: **超越**两大项目
- **配置体验**: 大幅简化，接近领先水平

核心竞争力方面，OpenDeRisk 在以下领域保持优势：
- RCA 根因分析能力
- 可视化证据链
- SRE 领域知识库
- 多 Agent 协作