# OpenDerisk 记忆体系完整架构

> 三层记忆架构：处理层 → 管理层 → 存储层

## 概述

基于对 Claude-Code、Hermes-Agent、OpenClaw 三个主流 Agent 记忆系统的深度对比分析，
OpenDerisk 构建了完整的三层记忆体系，融合了三个框架的核心优势：

| 借鉴来源 | 特性 | 实现位置 |
|---------|------|---------|
| **OpenClaw** | 混合检索、时间衰减、MMR、Recall Tracking、三阶段 Dreaming | HybridSearchEngine, RecallTracker, MemoryPromotionEngine |
| **Hermes** | 生命周期 hooks、Provider 插件架构 | MemoryLifecycleHooks, LettaAdapter |
| **Claude-Code** | Frozen Snapshot Pattern | FrozenSnapshotManager |

## 三层架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                     OpenDerisk Memory Architecture v3                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Layer 1: Memory Processing Layer - 记忆处理层                │   │
│  │                                                              │   │
│  │  MemoryProcessor(ABC) │ MemorySpaceStrategy │ LLMMemoryProcessor │   │
│  │  RecallTracker        │ HybridSearchEngine │ KGExtractor       │   │
│  │  PromotionEngine      │ TemporalDecay      │ MMR Re-ranking    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                │                                    │
│                                ▼                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Layer 2: Memory Manager Layer - 记忆管理层                   │   │
│  │                                                              │   │
│  │  LongTermMemoryManager │ MemoryIntegrationBundle             │   │
│  │  MemoryPipeline        │ MemoryStoreAdapter                  │   │
│  │  LifecycleHooks        │ FrozenSnapshotManager               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                │                                    │
│                                ▼                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Layer 3: Storage Provider Layer - 存储层                     │   │
│  │                                                              │   │
│  │  MemPalaceMemoryStore (vector + KG)                          │   │
│  │  LettaMemoryStore     (core + archival)                      │   │
│  │  MemoryStoreBase      (17 个抽象方法，可扩展)                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

## 文件清单

### 处理层（7 个文件）

| 文件 | 路径 | 描述 |
|------|------|------|
| processor.py | derisk-core/storage/memory/ | MemoryProcessor ABC 接口 |
| strategy.py | derisk-core/storage/memory/ | MemorySpaceStrategy 空间策略配置 |
| recall_tracker.py | derisk-core/storage/memory/ | RecallTracker 检索历史追踪（OpenClaw） |
| hybrid_search.py | derisk-core/storage/memory/ | 混合检索+时间衰减+MMR（OpenClaw） |
| lifecycle.py | derisk-core/storage/memory/ | 生命周期 hooks（Hermes） |
| snapshot.py | derisk-core/storage/memory/ | Frozen Snapshot（Claude-Code） |
| promotion.py | derisk-core/storage/memory/ | 三阶段晋升引擎 Light→REM→Deep（OpenClaw） |
| llm_processor.py | derisk-ext/memory/ | LLM MemoryProcessor 实现 |

### 管理层（3 个新增文件 + 1 个增强文件）

| 文件 | 路径 | 描述 |
|------|------|------|
| longterm_manager.py | derisk-core/.../unified_memory/ | 增强：添加 Processor/Strategy/RecallTracker/HybridSearch |
| store_adapter.py | derisk-core/.../unified_memory/ | NEW: MemoryStoreBase → UnifiedMemoryInterface 桥接 |
| pipeline.py | derisk-core/.../unified_memory/ | NEW: MemoryPipeline 执行管线 |

### 存储层（1 个新增文件 + 1 个已有文件）

| 文件 | 路径 | 描述 |
|------|------|------|
| mempalace_store.py | derisk-ext/storage/memory/ | MemPalace 存储（已有，vector + KG） |
| letta_adapter.py | derisk-ext/storage/memory/ | NEW: Letta Provider 适配器（Hermes） |

### 集成层（2 个增强文件 + 1 个前端文件）

| 文件 | 路径 | 描述 |
|------|------|------|
| core_v2_adapter.py | derisk-serve/agent/ | 增强：_build_memory_from_app() |
| app_to_v2_converter.py | derisk-serve/agent/ | 增强：返回 MemoryIntegrationBundle |
| tab-memory.tsx | web/src/.../components/ | 前端记忆配置 UI（已有） |

## BAIZE Agent 记忆全链路

### 产品配置流程

```
Agent Builder 页面 → "记忆" Tab → 选择 Memory 类型知识空间 → 保存
    │
    ▼
写入 gpts_app_config.resource_memory 列（TEXT 类型）
    │
    ▼
格式: [{"type":"memory","name":"memory","value":"{\"memories\":[...],\"auto_memory\":true,\"enable_kg\":true,\"top_k\":5}"}]
```

### Agent 构建流程

```
CoreV2Component.dynamic_agent_factory()
    │
    ▼
_build_v2_agent_from_gpts_app()
    │
    └── _build_memory_from_app()
            │
            ├── 解析 resource_memory
            ├── 创建 MemoryToolPack（每个空间）
            ├── 注册记忆工具到 agent tools
            │
            └── create_memory_integration_bundle()
                    │
                    ├── MemoryStoreBase 实例
                    ├── MemoryProcessor（LLM-based）
                    ├── MemorySpaceStrategy（每空间）
                    ├── RecallTracker
                    ├── HybridSearchEngine
                    ├── MemoryLifecycleHooks
                    ├── FrozenSnapshotManager
                    └── MemoryPromotionEngine
```

### Agent 对话执行流程

```
1. MemoryPipeline.on_session_start(query)
   ├── HybridSearchEngine 检索（Vector + FTS + 时间衰减 + MMR）
   ├── 捕获 Frozen Snapshot
   └── 返回记忆文本 → 注入 system prompt

2. Agent 生成回复

3. MemoryPipeline.on_turn_end(user_message, assistant_response)
   └── MemoryProcessor.extract_key_content() → LLM 提取
   └── MemoryProcessor.consolidate_memories() → 融合
   └── store.awrite_memory() → 写入
   └── 如 enable_kg: extract_triples() → 写入 KG

4. MemoryPipeline.on_session_end()
   └── MemoryPromotionEngine.run_promotion_sweep()
       ├── Light: 从 RecallTracker 收集候选
       ├── REM: 概念标签模式识别
       └── Deep: 多组件评分 → 晋升写入
```

## 核心机制详解

### 混合检索（HybridSearchEngine）

```
1. Vector 搜索（ChromaDB/MemPalace）
2. 关键词搜索（FTS 或 fallback 文本匹配）
3. 合并：vector_weight * vec_score + keyword_weight * kw_score
4. 时间衰减：score *= exp(-λ * age_days)，λ = ln(2) / halflife
5. MMR 重排：λ * relevance - (1-λ) * max_similarity_to_selected
```

### 三阶段晋升（MemoryPromotionEngine）

```
Light Sleep:
  - 从 RecallTracker 获取检索历史
  - 过滤去重，计算置信度
  → 候选列表

REM Sleep:
  - 分析 concept tags patterns
  - 识别强模式（tags 出现在多个候选中）
  → 增强候选

Deep Sleep:
  - 多组件评分:
    frequency (0.24): log(recall_count)
    relevance (0.30): avg search score
    diversity (0.15): unique queries
    recency (0.15): exp(-lambda * age)
    consolidation (0.10): recall day span
    conceptual (0.06): concept tag count
  - 高于阈值的晋升写入
  → 晋升结果
```

### 生命周期 Hooks

```python
on_turn_start(turn, message)      # 预热检索
on_turn_end(turn, user, assistant) # 自动写入
on_session_end(history)           # 最终提取 + 晋升
on_session_switch(new_id, reset)  # 重置缓存
on_pre_compress(messages)         # 压缩前提取
```

## 与主流框架对比

| 维度 | OpenDerisk v3 | Hermes | OpenClaw | Claude-Code |
|------|--------------|--------|----------|-------------|
| 架构完整性 | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★☆ |
| LLM处理 | ★★★★★ | ★★★★☆ | ★★★★★ | ★★★☆☆ |
| 检索能力 | ★★★★★ | ★★★☆☆ | ★★★★★ | ★★☆☆☆ |
| 生命周期 | ★★★★★ | ★★★★★ | ★★★☆☆ | ★★☆☆☆ |
| 扩展性 | ★★★★★ | ★★★★★ | ★★★★☆ | ★★☆☆☆ |
| Cache优化 | ★★★★★ | ★★★★★ | ★★☆☆☆ | ★★★★★ |
| 记忆整合能力 | ★★★★★ | ★★★★☆ | ★★★★★ | ★★★☆☆ |
