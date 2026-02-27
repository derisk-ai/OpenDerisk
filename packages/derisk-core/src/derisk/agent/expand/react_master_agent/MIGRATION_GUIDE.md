# Agent 合并迁移指南

## 背景

为了简化架构、提高可维护性，我们将三个 Agent（`ReActAgent`、`ReActMasterAgent`、`PDCAAgent`）合并为一个统一的 `ReActMasterAgent`。

## 合并决策

| Agent | 状态 | 替代方案 |
|-------|------|----------|
| `ReActAgent` | **已弃用** | 使用 `ReActMasterAgent` |
| `PDCAAgent` | **已弃用** | 使用 `ReActMasterAgent(enable_kanban=True)` |
| `ReActMasterAgent` | **保留**，作为主Agent | - |

## 迁移指南

### 1. 从 ReActAgent 迁移

**旧代码：**
```python
from derisk.agent.expand.react_agent import ReActAgent

agent = ReActAgent()
```

**新代码：**
```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

agent = ReActMasterAgent(
    enable_doom_loop_detection=True,
    enable_session_compaction=True,
    enable_history_pruning=True,
    enable_output_truncation=True,
)
```

### 2. 从 PDCAAgent 迁移

**旧代码：**
```python
from derisk.agent.expand.pdca_agent import PDCAAgent

agent = PDCAAgent()
```

**新代码：**
```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

agent = ReActMasterAgent(
    enable_kanban=True,
    kanban_exploration_limit=2,
)
```

#### Kanban API 兼容性

旧的 PDCAAgent Kanban API 在 ReActMasterAgent 中完全兼容：

```python
# 创建看板
result = await agent.create_kanban(
    mission="分析系统性能问题",
    stages=[
        {
            "stage_id": "s1_data_collection",
            "description": "收集系统监控数据",
            "deliverable_type": "monitoring_data",
            "deliverable_schema": {
                "type": "object",
                "required": ["cpu_usage", "memory_usage"],
                "properties": {
                    "cpu_usage": {"type": "number"},
                    "memory_usage": {"type": "number"}
                }
            }
        },
        {
            "stage_id": "s2_analysis",
            "description": "分析性能瓶颈",
            "deliverable_type": "analysis_report",
            "depends_on": ["s1_data_collection"]
        }
    ]
)

# 提交交付物
result = await agent.submit_deliverable(
    stage_id="s1_data_collection",
    deliverable={"cpu_usage": 75.5, "memory_usage": 82.3},
    reflection="数据收集完成，发现CPU使用率较高"
)

# 读取交付物
result = await agent.read_deliverable("s1_data_collection")

# 获取看板状态
status = await agent.get_kanban_status()
```

## ReActMasterAgent 完整功能

### 核心配置

```python
agent = ReActMasterAgent(
    # 基础配置
    max_retry_count=25,
    
    # Doom Loop 检测
    enable_doom_loop_detection=True,
    doom_loop_threshold=3,
    
    # 上下文压缩
    enable_session_compaction=True,
    context_window=128000,
    compaction_threshold_ratio=0.8,
    
    # 输出截断
    enable_output_truncation=True,
    
    # 历史修剪
    enable_history_pruning=True,
    prune_protect_tokens=4000,
    
    # WorkLog 管理
    enable_work_log=True,
    work_log_context_window=128000,
    work_log_compression_ratio=0.7,
    
    # 阶段管理
    enable_phase_management=True,
    phase_auto_detection=True,
    phase_enable_prompts=True,
    
    # 报告生成
    enable_auto_report=True,
    report_auto_generate=False,
    report_default_type="detailed",
    report_default_format="markdown",
    
    # Kanban（从 PDCA 合并）
    enable_kanban=False,
    kanban_exploration_limit=2,
    kanban_auto_stage_transition=True,
)
```

### 新增功能对比

| 功能 | ReActAgent | PDCAAgent | ReActMasterAgent |
|------|:----------:|:---------:|:----------------:|
| Doom Loop 检测 | ❌ | ❌ | ✅ |
| 上下文压缩 | ❌ | ❌ | ✅ |
| 历史修剪 | ❌ | ❌ | ✅ |
| 输出截断 | ❌ | ❌ | ✅ |
| WorkLog 管理 | ❌ | ✅ 简单版 | ✅ 增强版 |
| 阶段管理 | ❌ | ❌ | ✅ Phase |
| Kanban | ❌ | ✅ | ✅ 可选 |
| Schema 验证 | ❌ | ✅ | ✅ |
| 探索限制 | ❌ | ✅ | ✅ |
| 报告生成 | ❌ | ❌ | ✅ |
| Todo 工具 | ❌ | ❌ | ✅ |
| 文件系统 | ❌ | ✅ | ✅ AgentFileSystem |

## 弃用时间表

| 版本 | 状态 |
|------|------|
| v2.2.0 | 添加弃用警告 |
| v2.3.0 | 默认不导出 ReActAgent 和 PDCAAgent |
| v3.0.0 | 完全移除 ReActAgent 和 PDCAAgent |

## 常见问题

### Q: 为什么合并？

A: 三个 Agent 存在大量功能重叠，维护成本高。合并后：
- 统一架构，减少代码重复
- 能力不减反增（继承所有优点）
- 维护成本显著降低

### Q: PDCAAgent 的核心功能会丢失吗？

A: 不会。Kanban 功能已完整迁移到 ReActMasterAgent 作为可选模块：
- `enable_kanban=True` 启用
- 完全兼容的 API
- Schema 验证、探索限制等特性全部保留

### Q: 迁移成本如何？

A: 迁移成本较低：
- ReActAgent → ReActMasterAgent：几乎零成本，API 兼容
- PDCAAgent → ReActMasterAgent：只需添加 `enable_kanban=True`

### Q: 如果我需要旧版功能怎么办？

A: 
1. 短期：继续使用，但会有弃用警告
2. 中期：迁移到 ReActMasterAgent
3. 长期：旧 Agent 将被移除，请尽快迁移

## 技术支持

如有问题，请联系开发团队或在 GitHub 提交 Issue。