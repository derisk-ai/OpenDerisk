# Derisk Agent 架构文档索引

> 最后更新: 2026-03-03

## 文档列表

| 文档 | 描述 | 路径 |
|------|------|------|
| **Core V1 架构** | Core V1 Agent 的完整架构文档，包含分层模块定义、执行流程、关键逻辑细节 | [CORE_V1_ARCHITECTURE.md](./CORE_V1_ARCHITECTURE.md) |
| **Core V2 架构** | Core V2 Agent 的完整架构文档，包含新增模块（项目记忆、上下文隔离等） | [<br/>CORE_V2_ARCHITECTURE.md](./CORE_V2_ARCHITECTURE.md) |
| **前后端交互链路** | 前端与 Agent 的完整交互链路分析，包含 SSE 流式输出、VIS 协议 | [FRONTEND_BACKEND_INTERACTION.md](./FRONTEND_BACKEND_INTERACTION.md) |

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
- [VIS 协议](./FRONTEND_BACKEND_INTERACTION.md#五vis-可视化协议) - 消息渲染格式

**后端开发者**:
- [Core V2 架构](./CORE_V2_ARCHITECTURE.md) - 了解 V2 Agent 设计
- [Runtime 层](./CORE_V2_ARCHITECTURE.md#22-runtime-层-运行时层) - 会话管理
- [Memory 层](./CORE_V2_ARCHITECTURE.md#24-memory-层-记忆层-新增) - 记忆系统

**架构师**:
- [Core V1 架构](./CORE_V1_ARCHITECTURE.md) - 了解原有设计
- [V1 vs V2 对比](./CORE_V2_ARCHITECTURE.md#四与-v1-的关键差异) - 迁移指南

## 目录结构

```
docs/architecture/
├── README.md                        # 本文件 (索引)
├── CORE_V1_ARCHITECTURE.md          # Core V1 架构文档
├── CORE_V2_ARCHITECTURE.md          # Core V2 架构文档
└── FRONTEND_BACKEND_INTERACTION.md  # 前后端交互链路文档
```