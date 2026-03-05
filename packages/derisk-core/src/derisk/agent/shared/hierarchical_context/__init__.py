"""
分层上下文索引系统 (Hierarchical Context Index System)

将任务执行历史按章节结构组织，实现分层压缩和智能回溯。

核心特性：
1. 章节式索引：按任务阶段（探索期/开发期/调试期/优化期/收尾期）组织历史
2. 优先级压缩：基于内容重要性差异化压缩
3. LLM智能压缩：使用大模型生成结构化摘要
4. 主动回溯：Agent可通过工具主动回顾历史
5. 文件系统集成：压缩内容持久化存储

设计理念：
- 类比长篇小说的章节结构
- 第1轮和第100轮保持相同效果
- 确保上下文注意力稳定
- 用户可自定义压缩策略和Prompt模板
"""

from .hierarchical_context_index import (
    TaskPhase,
    ContentPriority,
    Section,
    Chapter,
    HierarchicalContextConfig,
)
from .chapter_indexer import ChapterIndexer
from .content_prioritizer import ContentPrioritizer
from .recall_tool import (
    RecallSectionTool,
    RecallChapterTool,
    SearchHistoryTool,
    RecallToolManager,
    create_recall_tools,
)
from .phase_transition_detector import (
    PhaseTransitionDetector,
    PhaseAwareCompactor,
)
from .hierarchical_context_manager import (
    HierarchicalContextManager,
    create_hierarchical_context_manager,
)
from .hierarchical_compactor import (
    HierarchicalCompactor,
    CompactionScheduler,
    CompactionResult,
    CompactionTemplate,
    create_hierarchical_compactor,
)
from .compaction_config import (
    CompactionStrategy,
    CompactionTrigger,
    CompactionPromptConfig,
    CompactionRuleConfig,
    HierarchicalCompactionConfig,
    PREDEFINED_PROMPT_TEMPLATES,
    get_prompt_template,
)
from .memory_prompt_config import (
    MemoryPromptConfig,
    MemoryPromptVariables,
    MEMORY_PROMPT_PRESETS,
    get_memory_prompt_preset,
    create_memory_prompt_config,
)
from .async_manager import (
    AsyncHierarchicalContextManager,
    AsyncLockManager,
    AsyncBatchProcessor,
    get_global_manager,
    create_async_manager,
)
from .integration_v1 import (
    HierarchicalContextMixin,
    HierarchicalContextIntegration,
    integrate_hierarchical_context,
)
from .integration_v2 import (
    HierarchicalContextV2Integration,
    HierarchicalContextCheckpoint,
    extend_agent_harness_with_hierarchical_context,
)

from .prompt_integration import (
    HierarchicalContextPromptConfig,
    integrate_hierarchical_context_to_prompt,
    DEFAULT_HIERARCHICAL_PROMPT_CONFIG,
    CONCISE_HIERARCHICAL_PROMPT_CONFIG,
    DETAILED_HIERARCHICAL_PROMPT_CONFIG,
)

__all__ = [
    # 核心数据结构
    "TaskPhase",
    "ContentPriority",
    "Section",
    "Chapter",
    "HierarchicalContextConfig",
    # 章节索引器
    "ChapterIndexer",
    # 优先级分类器
    "ContentPrioritizer",
    # 回溯工具
    "RecallSectionTool",
    "RecallChapterTool",
    "SearchHistoryTool",
    "RecallToolManager",
    "create_recall_tools",
    # 阶段检测器
    "PhaseTransitionDetector",
    "PhaseAwareCompactor",
    # 管理器
    "HierarchicalContextManager",
    "create_hierarchical_context_manager",
    # 压缩器
    "HierarchicalCompactor",
    "CompactionScheduler",
    "CompactionResult",
    "CompactionTemplate",
    "create_hierarchical_compactor",
    # 压缩配置
    "CompactionStrategy",
    "CompactionTrigger",
    "CompactionPromptConfig",
    "CompactionRuleConfig",
    "HierarchicalCompactionConfig",
    "PREDEFINED_PROMPT_TEMPLATES",
    "get_prompt_template",
    # Memory Prompt配置
    "MemoryPromptConfig",
    "MemoryPromptVariables",
    "MEMORY_PROMPT_PRESETS",
    "get_memory_prompt_preset",
    "create_memory_prompt_config",
    # Prompt集成
    "HierarchicalContextPromptConfig",
    "integrate_hierarchical_context_to_prompt",
    "DEFAULT_HIERARCHICAL_PROMPT_CONFIG",
    "CONCISE_HIERARCHICAL_PROMPT_CONFIG",
    "DETAILED_HIERARCHICAL_PROMPT_CONFIG",
    # 异步管理器
    "AsyncHierarchicalContextManager",
    "AsyncLockManager",
    "AsyncBatchProcessor",
    "get_global_manager",
    "create_async_manager",
    # Core V1 集成
    "HierarchicalContextMixin",
    "HierarchicalContextIntegration",
    "integrate_hierarchical_context",
    # Core V2 集成
    "HierarchicalContextV2Integration",
    "HierarchicalContextCheckpoint",
    "extend_agent_harness_with_hierarchical_context",
]