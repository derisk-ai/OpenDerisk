# Derisk Agent 架构文档索引

> 最后更新: 2026-03-03

## 文档列表

### 核心架构文档

| 文档 | 描述 | 路径 |
|------|------|------|
| **Core V1 架构** | Core V1 Agent 的完整架构文档，包含分层模块定义、执行流程、关键逻辑细节 | [CORE_V1_ARCHITECTURE.md](./CORE_V1_ARCHITECTURE.md) |
| **Core V2 架构** | Core V2 Agent 的完整架构文档，包含新增模块（项目记忆、上下文隔离等） | [CORE_V2_ARCHITECTURE.md](./CORE_V2_ARCHITECTURE.md) |
| **前后端交互链路** | 前端与 Agent 的完整交互链路分析，包含 SSE 流式输出、VIS 协议 | [FRONTEND_BACKEND_INTERACTION.md](./FRONTEND_BACKEND_INTERACTION.md) |

### 详细专题文档

| 文档 | 描述 | 路径 |
|------|------|------|
| **上下文与记忆详解** | Core V2 上下文管理、压缩机制、记忆系统的完整实现细节 | [CORE_V2_CONTEXT_MEMORY_DETAIL.md](./CORE_V2_CONTEXT_MEMORY_DETAIL.md) |
| **工具与可视化详解** | Core V2 工具架构、文件系统集成、VIS 可视化机制的完整实现 | [CORE_V2_TOOLS_VIS_DETAIL.md](./CORE_V2_TOOLS_VIS_DETAIL.md) |

## 架构对比概览

### Core V1 vs Core V2

| 方面 | Core V1 | Core V2 |
|------|---------|---------|
| **执行模型** | generate_reply 单循环 | Think/Decide/Act 三阶段 |
| **消息模型** | send/receive 显式消息传递 | run() 主循环隐式处理 |
| **状态管理** | 隐式状态 | 明确状态机 (AgentState) |
| **子Agent** | 通过消息路由 | SubagentManager 显式委派 |
| **记忆系统** | GptsMemory (单一) | UnifiedMemory + ProjectMemory (分层) |
| **上下文隔离** | 无 | ISOLATED/SHARED/FORK 三种模式 |
| **扩展机制** | 继承重写 | SceneStrategy 钩子系统 |
| **推理策略** | 硬编码 | 可插拔 ReasoningStrategy |

### V2 新增模块

1. **ProjectMemory**: CLAUDE.md 风格的多层级记忆管理
2. **ContextIsolation**: 三种隔离模式的上下文管理
3. **SubagentManager**: 显式的子 Agent 委派系统
4. **UnifiedMemory**: 统一的记忆接口抽象
5. **SceneStrategy**: 基于钩子的场景扩展系统
6. **ReasoningStrategy**: 可插拔的推理策略
7. **Filesystem**: CLAUDE.md 兼容层和自动记忆钩子

## 快速导航

### 按角色

**前端开发者**:
- [前后端交互链路](./FRONTEND_BACKEND_INTERACTION.md) - 了解 API 端点和数据格式
- [VIS 协议](./CORE_V2_TOOLS_VIS_DETAIL.md#九可视化机制) - 消息渲染格式
- [VIS 标签格式](./CORE_V2_TOOLS_VIS_DETAIL.md#93-vis-标签格式) - 标签语法规范

**后端开发者**:
- [Core V2 架构](./CORE_V2_ARCHITECTURE.md) - 了解 V2 Agent 设计
- [Runtime 层](./CORE_V2_ARCHITECTURE.md#22-runtime-层-运行时层) - 会话管理
- [工具注册流程](./CORE_V2_TOOLS_VIS_DETAIL.md#八工具注册流程) - 工具系统

**架构师**:
- [Core V1 架构](./CORE_V1_ARCHITECTURE.md) - 了解原有设计
- [V1 vs V2 对比](./CORE_V2_ARCHITECTURE.md#42-与-v1-的关键差异) - 迁移指南
- [上下文压缩机制](./CORE_V2_CONTEXT_MEMORY_DETAIL.md#二上下文压缩机制) - 系统优化

### 按主题

**上下文管理**:
- [上下文管理架构](./CORE_V2_CONTEXT_MEMORY_DETAIL.md#一上下文管理架构) - 整体设计
- [压缩触发策略](./CORE_V2_CONTEXT_MEMORY_DETAIL.md#21-压缩触发策略) - 触发条件
- [内容保护器](./CORE_V2_CONTEXT_MEMORY_DETAIL.md#24-内容保护器实现) - 保护重要内容
- [上下文隔离机制](./CORE_V2_CONTEXT_MEMORY_DETAIL.md#五上下文隔离机制) - 子Agent隔离

**记忆系统**:
- [统一记忆接口](./CORE_V2_CONTEXT_MEMORY_DETAIL.md#31-统一记忆接口) - 接口定义
- [项目记忆系统](./CORE_V2_CONTEXT_MEMORY_DETAIL.md#四项目记忆系统) - .derisk目录
- [@import 指令](./CORE_V2_CONTEXT_MEMORY_DETAIL.md#44-import-指令机制) - 模块导入
- [GptsMemory 适配器](./CORE_V2_CONTEXT_MEMORY_DETAIL.md#34-gptsmemory-适配器) - V1兼容

**工具系统**:
- [工具基础架构](./CORE_V2_TOOLS_VIS_DETAIL.md#二工具基础架构) - ToolBase, ToolRegistry
- [内置工具详解](./CORE_V2_TOOLS_VIS_DETAIL.md#三内置工具详解) - bash, read, write等
- [Action 迁移适配器](./CORE_V2_TOOLS_VIS_DETAIL.md#五action-迁移适配器) - V1迁移
- [MCP 协议适配](./CORE_V2_TOOLS_VIS_DETAIL.md#六mcp-协议工具适配器) - 外部工具集成

**可视化机制**:
- [VIS 协议架构](./CORE_V2_TOOLS_VIS_DETAIL.md#91-vis-协议架构) - 双窗口设计
- [VIS 标签格式](./CORE_V2_TOOLS_VIS_DETAIL.md#93-vis-标签格式) - 标签语法
- [VIS 转换器](./CORE_V2_TOOLS_VIS_DETAIL.md#94-corev2viswindow3converter-实现) - 数据转换
- [前后端交互流程](./CORE_V2_TOOLS_VIS_DETAIL.md#96-前后端交互流程) - 数据传输

**文件系统集成**:
- [文件系统架构](./CORE_V2_TOOLS_VIS_DETAIL.md#101-文件系统架构) - 整体设计
- [CLAUDE.md 兼容层](./CORE_V2_TOOLS_VIS_DETAIL.md#102-claudemd-兼容层) - Claude Code兼容
- [自动记忆钩子](./CORE_V2_TOOLS_VIS_DETAIL.md#103-自动记忆钩子系统) - 自动记忆写入

## 目录结构

```
docs/architecture/
├── README.md                        # 本文件 (索引)
├── CORE_V1_ARCHITECTURE.md          # Core V1 架构文档
├── CORE_V2_ARCHITECTURE.md          # Core V2 架构文档
└── FRONTEND_BACKEND_INTERACTION.md  # 前后端交互链路文档
```