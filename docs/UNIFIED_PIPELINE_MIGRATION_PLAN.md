# Unified Pipeline 迁移方案

> **目标**: 将 core 和 core_v2 所有 agent 统一切换到 Unified Pipeline 作为底层统一基础方案

## 1. 当前状况分析

### 1.1 核心发现

**好消息**: 两个架构都已经部分集成了 Unified Pipeline！

| 架构 | Unified Pipeline 基础设施 | Layer 集成状况 | 差距 |
|------|--------------------------|---------------|------|
| **Core v1 (ReActMasterAgent)** | ✅ 已初始化 `_compaction_pipeline` | ✅ Layer 2 (Pruning)<br>✅ Layer 3 (Compaction)<br>❌ Layer 1 (Truncation) 未统一 | Layer 1 仍使用独立的 Truncator |
| **Core v2 (ReActReasoningAgent)** | ✅ 已初始化参数和懒加载 | ⚠️ 基础设施存在<br>❌ 未真正使用 Pipeline | 未在 think/act 中调用 Pipeline 方法 |

### 1.2 当前架构问题

**Core v1 问题**:
```python
# 现状：双重架构并存
组件:
  ├── _truncator (Truncator)                # Layer 1 独立实现
  ├── _history_pruner (HistoryPruner)       # Layer 2 独立实现  
  ├── _session_compaction (SessionCompaction) # Layer 3 独立实现
  └── _compaction_pipeline (UnifiedPipeline) # 新的统一方案（未完全使用）

问题:
  - Layer 1 (Truncation) 未使用 Pipeline
  - 冗余组件并存，造成混乱
  - 降级逻辑中仍使用旧组件 (line 834-836)
```

**Core v2 问题**:
```python
# 现状：基础设施存在但未使用
组件:
  ├── _output_truncator (OutputTruncator)   # 独立实现
  ├── _history_pruner (HistoryPruner)       # 独立实现
  ├── _context_compactor (ContextCompactor) # 独立实现
  └── _compaction_pipeline (属性存在)       # 未真正使用

问题:
  - 未在 think() 中调用 Pipeline
  - 未在 act() 中调用 Pipeline
  - 未使用 Layer 1 截断功能
```

---

## 2. 统一方案设计

### 2.1 目标架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    ReAct Agent (v1 & v2)                        │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │            UnifiedCompactionPipeline (统一底层)             │ │
│  │                                                              │ │
│  │  Layer 1: truncate_output()                                 │ │
│  │    - 截断大型工具输出                                        │ │
│  │    - 归档到 AgentFileSystem                                 │ │
│  │                                                              │ │
│  │  Layer 2: prune_history()                                   │ │
│  │    - 剪枝旧的工具输出                                        │ │
│  │    - 保护关键消息                                            │ │
│  │                                                              │ │
│  │  Layer 3: compact_if_needed()                               │ │
│  │    - 压缩旧消息                                              │ │
│  │    - 创建 HistoryChapter                                     │ │
│  │    - 提供 read_history_chapter() 等回溯工具                 │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  移除的冗余组件:                                                 │
│    ✗ SessionCompaction (core v1)                               │
│    ✗ HistoryPruner (both)                                      │
│    ✗ Truncator / OutputTruncator (both)                       │
│    ✗ ContextCompactor (core v2)                                │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 迁移原则

1. **渐进式迁移**: 先完成集成，再移除冗余
2. **向后兼容**: 保留降级路径
3. **统一配置**: 使用 `HistoryCompactionConfig`
4. **消除重复**: 移除所有冗余组件

---

## 3. 详细迁移步骤

### 3.1 Phase 1: 完善 Pipeline 集成

#### Step 1.1: Core v1 (ReActMasterAgent) - 统一 Layer 1

**文件**: `packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py`

**修改点**:

1. **修改 `_truncate_tool_output()` 方法**，使用 Pipeline:
```python
# 当前代码 (line ~1100)
async def _truncate_tool_output(self, content: str, tool_name: str, ...) -> str:
    if not self._truncator:
        return content
    
    result = self._truncator.truncate(content, tool_name)
    # ... 处理结果

# 目标代码
async def _truncate_tool_output(self, content: str, tool_name: str, ...) -> str:
    pipeline = await self._ensure_compaction_pipeline()
    if pipeline:
        try:
            result = await pipeline.truncate_output(content, tool_name, tool_args)
            if result.is_truncated:
                logger.info(f"Pipeline truncation: {result.original_size} -> {result.truncated_size} bytes")
            return result.content
        except Exception as e:
            logger.warning(f"Pipeline truncation failed, fallback to legacy: {e}")
    
    # Fallback to legacy truncator (临时保留，Phase 2 移除)
    if self._truncator:
        result = self._truncator.truncate(content, tool_name)
        return result.content
    
    return content
```

2. **移除降级路径中的旧组件调用**：
```python
# 当前代码 (line 834-836)
else:
    messages = await self._prune_history(messages)  # 旧方法
    messages = await self._check_and_compact_context(messages)  # 旧方法

# 目标代码
else:
    # Pipeline 不可用时，直接返回（不做处理）
    logger.warning("Compaction pipeline not available, skipping context management")
```

#### Step 1.2: Core v2 (ReActReasoningAgent) - 完整集成

**文件**: `packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_reasoning_agent.py`

**修改点**:

1. **修改 `think()` 方法**，在构建消息后调用 Pipeline：
```python
async def think(self, message: Optional[str] = None) -> Decision:
    # ... 现有构建消息逻辑
    
    # 新增：使用 Pipeline 进行 Layer 2 + Layer 3
    pipeline = await self._ensure_compaction_pipeline()
    if pipeline:
        # Layer 2: Prune
        prune_result = await pipeline.prune_history(self._messages)
        self._messages = prune_result.messages
        
        # Layer 3: Compact
        compact_result = await pipeline.compact_if_needed(self._messages)
        self._messages = compact_result.messages
        
        if compact_result.compaction_triggered and pipeline.has_compacted:
            await self._inject_history_tools_if_needed()
    
    # ... 继续现有 LLM 调用逻辑
```

2. **修改 `act()` 方法**，使用 Pipeline 的 Layer 1：
```python
async def act(self, decision: Decision) -> ToolResult:
    # ... 现有执行逻辑
    
    result = await self.execute_tool(decision.tool_name, decision.tool_args)
    
    # 新增：Layer 1 截断
    pipeline = await self._ensure_compaction_pipeline()
    if pipeline and result.output:
        trunc_result = await pipeline.truncate_output(
            result.output, 
            decision.tool_name,
            decision.tool_args
        )
        result.output = trunc_result.content
        
        if trunc_result.is_truncated:
            logger.info(f"Output truncated: saved to {trunc_result.file_key}")
    
    return result
```

### 3.2 Phase 2: 清理冗余代码

#### Step 2.1: Core v1 清理

**移除组件**:
- 删除 `_session_compaction` 属性和初始化
- 删除 `_history_pruner` 属性和初始化  
- 保留 `_truncator` 作为降级选项（仅当 Pipeline 不可用时）
- 删除 `_check_and_compact_context()` 方法
- 删除 `_prune_history()` 方法

**修改配置参数**:
```python
# 移除独立参数
# enable_session_compaction: bool = True        # ❌ 删除
# context_window: int = 128000                  # ❌ 删除
# compaction_threshold_ratio: float = 0.8       # ❌ 删除
# enable_history_pruning: bool = True           # ❌ 删除
# prune_protect_tokens: int = 4000              # ❌ 删除
# enable_output_truncation: bool = True         # ❌ 删除

# 新增统一参数
compaction_config: Optional[HistoryCompactionConfig] = None  # ✅ 新增
enable_unified_pipeline: bool = True                         # ✅ 新增
```

#### Step 2.2: Core v2 清理

**移除组件**:
- 删除 `_output_truncator` 属性和初始化
- 删除 `_history_pruner` 属性和初始化
- 删除 `_context_compactor` 属性和初始化

**修改配置参数**:
```python
# 移除独立参数
# enable_output_truncation: bool = True         # ❌ 删除
# max_output_lines: int = 2000                  # ❌ 删除
# max_output_bytes: int = 50000                 # ❌ 删除
# enable_context_compaction: bool = True        # ❌ 删除
# enable_history_pruning: bool = True           # ❌ 删除
# context_window: int = 128000                  # ❌ 删除

# 新增统一参数
compaction_config: Optional[HistoryCompactionConfig] = None  # ✅ 已存在
enable_unified_pipeline: bool = True                         # ✅ 重命名自 enable_compaction_pipeline
```

### 3.3 Phase 3: 统一配置和测试

#### Step 3.1: 创建配置工具函数

**新文件**: `packages/derisk-core/src/derisk/agent/core/memory/compaction_config.py`

```python
def create_default_compaction_config(
    context_window: int = 128000,
    max_output_lines: int = 2000,
    max_output_bytes: int = 50 * 1024,
    **kwargs
) -> HistoryCompactionConfig:
    """创建默认的压缩配置"""
    return HistoryCompactionConfig(
        context_window=context_window,
        max_output_lines=max_output_lines,
        max_output_bytes=max_output_bytes,
        **kwargs
    )
```

#### Step 3.2: 添加测试用例

**新文件**: `packages/derisk-core/tests/agent/test_unified_pipeline_integration.py`

```python
import pytest
from derisk.agent.core.memory.compaction_pipeline import (
    UnifiedCompactionPipeline,
    HistoryCompactionConfig,
)

class TestUnifiedPipelineIntegration:
    """测试 Unified Pipeline 集成"""
    
    @pytest.mark.asyncio
    async def test_layer1_truncation(self):
        """测试 Layer 1 截断功能"""
        # ...
    
    @pytest.mark.asyncio
    async def test_layer2_pruning(self):
        """测试 Layer 2 剪枝功能"""
        # ...
    
    @pytest.mark.asyncio
    async def test_layer3_compaction(self):
        """测试 Layer 3 压缩功能"""
        # ...
    
    @pytest.mark.asyncio
    async def test_react_master_agent_integration(self):
        """测试 ReActMasterAgent 集成"""
        # ...
    
    @pytest.mark.asyncio
    async def test_react_reasoning_agent_integration(self):
        """测试 ReActReasoningAgent 集成"""
        # ...
```

---

## 4. 迁移验证清单

### 4.1 功能验证

- [ ] Layer 1 (Truncation) 正常工作
  - [ ] 大型工具输出被截断
  - [ ] 完整内容归档到 AgentFileSystem
  - [ ] 返回正确的 file_key
  
- [ ] Layer 2 (Pruning) 正常工作
  - [ ] 旧的工具输出被剪枝
  - [ ] 系统/用户消息被保护
  - [ ] Tool-call 原子组被保护

- [ ] Layer 3 (Compaction) 正常工作
  - [ ] Token 超过阈值时触发压缩
  - [ ] 生成 HistoryChapter
  - [ ] 历史回溯工具可用

- [ ] 向后兼容性
  - [ ] Pipeline 不可用时能降级
  - [ ] 旧配置参数仍能工作（映射到新配置）

### 4.2 性能验证

- [ ] 内存使用没有增加
- [ ] Token 消耗显著降低
- [ ] LLM 调用次数没有增加

### 4.3 代码质量

- [ ] 所有冗余代码已移除
- [ ] 无重复功能
- [ ] 配置参数统一
- [ ] 日志清晰完整

---

## 5. 风险和缓解措施

### 5.1 潜在风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Pipeline 初始化失败 | 上下文管理完全失效 | 保留降级路径，记录详细日志 |
| AgentFileSystem 不可用 | Layer 1 功能降级 | 降级到内存模式，仅截断不归档 |
| LLM 客户端不可用 | Layer 3 无法生成摘要 | 使用简单摘要算法降级 |
| 消息结构不兼容 | 功能异常 | UnifiedMessageAdapter 已处理 |

### 5.2 回滚计划

如果迁移失败:
1. 立即回滚到迁移前的代码版本
2. 启用 `enable_unified_pipeline=False` 参数
3. 使用旧版组件（临时保留）

---

## 6. 时间线和资源

### 6.1 时间估算

| 阶段 | 任务 | 预估时间 |
|------|------|---------|
| Phase 1 | 完善 Pipeline 集成 | 3-4 小时 |
| Phase 2 | 清理冗余代码 | 2-3 小时 |
| Phase 3 | 统一配置和测试 | 3-4 小时 |
| 验证 | 功能和性能测试 | 2-3 小时 |
| **总计** | | **10-14 小时** |

### 6.2 关键依赖

- AgentFileSystem 功能稳定
- UnifiedMessageAdapter 兼容性
- LLM 客户端可用性
- 测试环境准备完毕

---

## 7. 成功标准

迁移完成的标志:

✅ **功能完整**:
- 所有 agent 使用 Unified Pipeline
- 三层压缩机制完整实现
- 历史回溯工具可用

✅ **代码质量**:
- 无冗余组件
- 配置统一
- 日志清晰

✅ **性能提升**:
- Token 消耗降低 30%+
- 内存使用稳定
- 无功能退化

✅ **文档完善**:
- 迁移指南
- 使用文档
- API 文档更新

---

## 8. 后续优化

迁移完成后的可选优化:

1. **智能压缩策略**: 基于 message importance 动态调整压缩策略
2. **多级缓存**: 对已压缩的章节建立索引缓存
3. **压缩质量评估**: 评估压缩后信息的保留质量
4. **自适应参数**: 根据实际使用情况自动调整阈值
5. **性能监控**: 添加详细的性能指标收集和分析

---

**文档版本**: v1.0  
**创建日期**: 2026-03-06  
**最后更新**: 2026-03-06