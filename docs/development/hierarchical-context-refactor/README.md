# 历史上下文管理重构项目

## 项目概览

本项目旨在通过集成现有的 HierarchicalContext 系统，重构历史上下文管理机制，解决当前对话历史丢失、WorkLog 无法追溯等核心问题。

## 核心问题

| 问题 | 影响 | 解决方案 |
|------|------|---------|
| 会话连续追问上下文丢失 | 第100轮对话无法回溯前99轮历史 | 完整历史加载 + 智能压缩 |
| 历史对话只取首尾消息 | 中间工作过程丢失 | 使用 HierarchicalContext 完整保留历史 |
| WorkLog 不在历史上下文中 | 无法追溯工作过程 | WorkLog → Section 转换机制 |
| Core 和 Core V2 记忆系统混乱 | 三套记忆系统未协同，代码混乱 | 统一上下文中间件 + 统一记忆架构 |
| 宝藏系统完全未使用 | 技术债务 | 激活 HierarchicalContext 系统 |

## 核心目标

### 1. 解决会话连续追问上下文丢失问题
- 第1轮到第100轮对话保持相同的上下文质量
- 完整保留工作过程（WorkLog），支持历史回溯
- 智能压缩管理，优化上下文窗口利用率

### 2. 统一 Core 和 Core V2 记忆和文件系统架构
- 整合三套记忆系统（GptsMemory, UnifiedMemoryManager, AgentBase._messages）
- 统一文件系统持久化机制（AgentFileSystem）
- 建立 Core 和 Core V2 共享的记忆管理层

### 3. 激活沉睡的 HierarchicalContext 系统
- 利用已实现的 80% 功能，快速上线
- 建立统一的上下文管理标准

## 核心方案

**方案架构**：集成现有 HierarchicalContext 系统（80% 功能已实现）

```
应用层 (agent_chat.py, runtime.py)
         ↓
统一上下文中间件 (UnifiedContextMiddleware) ← 新增组件
         ↓
HierarchicalContext 核心系统 (已有，无需改动)
         ↓
持久化层 (GptsMemory + AgentFileSystem)
```

**关键优势**：
- 利用现有实现，开发周期短（2-3天完成核心功能）
- 智能压缩管理（3种策略：LLM/Rules/Hybrid）
- 支持历史回溯（Agent可主动查看历史）
- 向下兼容（保持现有接口不变）

## 文档导航

### 核心文档

1. **[开发方案](./01-development-plan.md)**
   - 问题背景与目标
   - 技术方案设计
   - 核心实现设计
   - 配置与灰度方案
   - 质量保证

2. **[任务拆分计划](./02-task-breakdown.md)**
   - 26个详细任务分解
   - 任务依赖关系图
   - 每个任务的实现步骤
   - 验收标准
   - 风险管理

### 任务概览

| 阶段 | 任务数 | 说明 |
|------|--------|------|
| Phase 1: 核心开发 | 8个 | UnifiedContextMiddleware + WorkLog转换 |
| Phase 2: 集成改造 | 6个 | agent_chat.py + runtime.py 改造 |
| Phase 3: 测试验证 | 5个 | 单元/集成/E2E测试 |
| Phase 4: 配置与灰度 | 4个 | 配置加载 + 灰度控制 + 监控 |
| Phase 5: 文档与发布 | 3个 | 文档编写 + 审查 + 发布 |

### 任务依赖关系

```
Phase 1 (核心开发)
    ↓
Phase 2 (集成改造)
    ↓
Phase 3 (测试验证)
    ↓
Phase 4 (配置与灰度)
    ↓
Phase 5 (文档与发布)
```

## 快速开始

### 1. 阅读文档

建议阅读顺序：
1. 本文档（概览）
2. [开发方案](./01-development-plan.md) - 理解架构设计
3. [任务拆分计划](./02-task-breakdown.md) - 了解具体任务

### 2. 开发流程

```bash
# 1. 创建项目结构（T1.1）
mkdir -p derisk/context
mkdir -p tests/test_unified_context

# 2. 从 Phase 1 开始开发
# 按照 02-task-breakdown.md 中的步骤逐个完成任务

# 3. 每完成一个任务，运行单元测试
pytest tests/test_unified_context/ -v

# 4. 确保测试覆盖率 > 80%
pytest tests/test_unified_context/ --cov=derisk/context --cov-report=html
```

### 3. 核心文件

**新增文件**：
- `derisk/context/unified_context_middleware.py` - 核心中间件
- `derisk/context/gray_release_controller.py` - 灰度控制器
- `derisk/context/config_loader.py` - 配置加载器
- `configs/hierarchical_context_config.yaml` - 配置文件

**改造文件**：
- `derisk_serve/agent/agents/chat/agent_chat.py` - 集成中间件
- `derisk/agent/core_v2/integration/runtime.py` - Core V2集成

**测试文件**：
- `tests/test_unified_context/test_middleware.py` - 中间件测试
- `tests/test_unified_context/test_worklog_conversion.py` - 转换测试
- `tests/test_unified_context/test_integration.py` - 集成测试
- `tests/test_unified_context/test_e2e.py` - E2E测试

## 核心技术点

### 1. WorkLog → Section 转换

将 WorkEntry 按任务阶段分组：
- 探索期（EXPLORATION）：read, glob, grep, search
- 开发期（DEVELOPMENT）：write, edit, bash, execute
- 调试期（DEBUGGING）：失败的操作
- 优化期（REFINEMENT）：refactor, optimize
- 收尾期（DELIVERY）：summary, document

### 2. 优先级判断

根据工具类型和执行结果自动判断优先级：
- CRITICAL：关键决策（critical/decision标签）
- HIGH：关键工具成功执行（write/bash/edit）
- MEDIUM：普通成功调用
- LOW：失败或低价值操作

### 3. 智能压缩

三种压缩策略：
- LLM_SUMMARY：使用LLM生成结构化摘要
- RULE_BASED：基于规则压缩
- HYBRID：混合策略（推荐）

### 4. 历史回溯

Agent可通过工具主动查看历史：
- `recall_section(section_id)`：查看具体步骤详情
- `recall_chapter(chapter_id)`：查看任务阶段摘要
- `search_history(keywords)`：搜索历史记录

## 配置示例

```yaml
hierarchical_context:
  enabled: true
  
chapter:
  max_chapter_tokens: 10000
  max_section_tokens: 2000
  recent_chapters_full: 2
  middle_chapters_index: 3
  early_chapters_summary: 5

compaction:
  enabled: true
  strategy: "llm_summary"
  trigger:
    token_threshold: 40000

worklog_conversion:
  enabled: true
  phase_detection:
    exploration_tools: ["read", "glob", "grep", "search", "think"]
    development_tools: ["write", "edit", "bash", "execute", "run"]

gray_release:
  enabled: false
  gray_percentage: 0
  user_whitelist: []
  app_whitelist: []
```

## 验收标准

### 功能标准
- ✅ 第100轮对话包含前99轮的关键信息
- ✅ 历史加载包含 WorkLog 内容
- ✅ Agent 可调用回溯工具查看历史
- ✅ 超过阈值自动触发压缩

### 性能标准
- 历史加载延迟 (P95) < 500ms
- 步骤记录延迟 (P95) < 50ms
- 内存增量 < 100MB/1000会话
- 压缩效率 > 50%

### 质量标准
- 单元测试覆盖率 > 80%
- 集成测试通过率 = 100%
- 代码审查问题数 = 0 critical

## 相关资源

### 相关代码
- [HierarchicalContext 系统](/derisk/agent/shared/hierarchical_context/)
- [GptsMemory](/derisk/agent/core/memory/gpts/)
- [AgentChat](/derisk_serve/agent/agents/chat/agent_chat.py)
- [Runtime](/derisk/agent/core_v2/integration/runtime.py)

### 参考文档
- HierarchicalContext 使用示例：`derisk/agent/shared/hierarchical_context/examples/usage_examples.py`
- 配置预设：`derisk/agent/shared/hierarchical_context/compaction_config.py`

## 常见问题

### Q1: 为什么选择集成 HierarchicalContext 而不是重新实现？

A: HierarchicalContext 系统 80% 的功能已经实现完善，包括章节索引、智能压缩、回溯工具等。重新实现需要 2-3周，而集成只需 2-3天，且质量有保障。

### Q2: 是否向下兼容？

A: 是的。所有改造都保持向下兼容，通过配置开关可以快速回滚到旧逻辑。

### Q3: 性能会有影响吗？

A: 通过缓存机制和异步加载，性能影响可控。目标是历史加载延迟 < 500ms。

### Q4: 如何灰度发布？

A: 支持多维度灰度：
- 白名单（用户/应用/会话）
- 流量百分比灰度
- 黑名单控制

### Q5: 如何监控和排查问题？

A: 完整的监控指标体系：
- 加载延迟和成功率
- 压缩效率
- 回溯工具使用频率
- 内存使用情况

## 联系方式

- 技术负责人：[待填写]
- 产品负责人：[待填写]
- 测试负责人：[待填写]

## 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|---------|------|
| v1.0 | 2025-03-02 | 初始版本，创建开发方案和任务拆分文档 | 开发团队 |