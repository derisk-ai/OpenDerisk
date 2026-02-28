"""
分层上下文压缩配置

让用户可以在Agent配置中自定义：
1. 压缩策略
2. Prompt模板
3. 压缩阈值
4. 保护规则
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class CompactionStrategy(str, Enum):
    """压缩策略"""
    LLM_SUMMARY = "llm_summary"       # LLM生成摘要
    TRUNCATE = "truncate"             # 简单截断
    HYBRID = "hybrid"                 # 混合策略
    KEYWORD_EXTRACT = "keyword"       # 关键词提取


class CompactionTrigger(str, Enum):
    """压缩触发条件"""
    TOKEN_THRESHOLD = "token_threshold"     # Token阈值
    PHASE_TRANSITION = "phase_transition"   # 阶段转换
    PERIODIC = "periodic"                   # 周期性
    MANUAL = "manual"                       # 手动触发


@dataclass
class CompactionPromptConfig:
    """
    压缩Prompt配置
    
    用户可以自定义各种场景的Prompt模板
    """
    
    # 章节摘要模板
    chapter_summary_template: str = """请为以下任务阶段生成一个结构化的摘要。

## 阶段信息
- 阶段名称: {title}
- 阶段类型: {phase}
- 执行步骤数: {section_count}

## 执行步骤概览
{sections_overview}

## 请按以下格式生成摘要:

### 目标 (Goal)
[这个阶段要达成什么目标？]

### 完成事项 (Accomplished)
[已完成的主要工作和结果]

### 关键发现 (Discoveries)
[在执行过程中的重要发现和洞察]

### 待处理 (Remaining)
[还有什么需要后续跟进的事项？]

### 相关文件 (Relevant Files)
[涉及的文件和资源列表]
"""
    
    # 节压缩模板
    section_compact_template: str = """请压缩以下执行步骤的内容，保留关键信息。

步骤名称: {step_name}
优先级: {priority}
原始内容:
{content}

请生成简洁的摘要（保留关键决策、结果和下一步行动）:
"""
    
    # 批量压缩模板
    batch_compact_template: str = """请将以下多个相关执行步骤压缩为一个简洁的摘要。

步骤列表:
{sections_content}

请生成：
1. 这些步骤的共同目标
2. 主要执行结果
3. 关键决策和发现
4. 需要注意的事项
"""
    
    # 自定义模板（用户可扩展）
    custom_templates: Dict[str, str] = field(default_factory=dict)
    
    # 系统提示
    system_prompt: str = "You are a helpful assistant specialized in summarizing task execution history."
    
    # 输出格式要求
    output_format_hints: str = "Use markdown format with clear sections."
    
    def get_template(self, template_name: str) -> Optional[str]:
        """获取模板"""
        templates = {
            "chapter_summary": self.chapter_summary_template,
            "section_compact": self.section_compact_template,
            "batch_compact": self.batch_compact_template,
        }
        
        # 先检查自定义模板
        if template_name in self.custom_templates:
            return self.custom_templates[template_name]
        
        return templates.get(template_name)
    
    def set_custom_template(self, name: str, template: str) -> None:
        """设置自定义模板"""
        self.custom_templates[name] = template
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_summary_template": self.chapter_summary_template,
            "section_compact_template": self.section_compact_template,
            "batch_compact_template": self.batch_compact_template,
            "custom_templates": self.custom_templates,
            "system_prompt": self.system_prompt,
            "output_format_hints": self.output_format_hints,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompactionPromptConfig":
        return cls(
            chapter_summary_template=data.get("chapter_summary_template", cls.chapter_summary_template),
            section_compact_template=data.get("section_compact_template", cls.section_compact_template),
            batch_compact_template=data.get("batch_compact_template", cls.batch_compact_template),
            custom_templates=data.get("custom_templates", {}),
            system_prompt=data.get("system_prompt", cls.system_prompt),
            output_format_hints=data.get("output_format_hints", cls.output_format_hints),
        )


@dataclass
class CompactionRuleConfig:
    """
    压缩规则配置
    
    定义不同优先级内容的压缩策略
    """
    
    # CRITICAL内容规则
    critical_rules: Dict[str, Any] = field(default_factory=lambda: {
        "preserve": True,           # 是否保护不压缩
        "max_length": None,         # 最大长度（None表示不限制）
        "compaction_strategy": CompactionStrategy.LLM_SUMMARY.value,
    })
    
    # HIGH内容规则
    high_rules: Dict[str, Any] = field(default_factory=lambda: {
        "preserve": False,
        "max_length": 500,
        "compaction_strategy": CompactionStrategy.LLM_SUMMARY.value,
        "keep_recent": 3,           # 保留最近N个
    })
    
    # MEDIUM内容规则
    medium_rules: Dict[str, Any] = field(default_factory=lambda: {
        "preserve": False,
        "max_length": 200,
        "compaction_strategy": CompactionStrategy.HYBRID.value,
        "keep_recent": 5,
    })
    
    # LOW内容规则
    low_rules: Dict[str, Any] = field(default_factory=lambda: {
        "preserve": False,
        "max_length": 100,
        "compaction_strategy": CompactionStrategy.TRUNCATE.value,
        "keep_recent": 10,
    })
    
    def get_rules_for_priority(self, priority: str) -> Dict[str, Any]:
        """获取指定优先级的规则"""
        rules_map = {
            "critical": self.critical_rules,
            "high": self.high_rules,
            "medium": self.medium_rules,
            "low": self.low_rules,
        }
        return rules_map.get(priority.lower(), self.medium_rules)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "critical_rules": self.critical_rules,
            "high_rules": self.high_rules,
            "medium_rules": self.medium_rules,
            "low_rules": self.low_rules,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompactionRuleConfig":
        return cls(
            critical_rules=data.get("critical_rules", cls.critical_rules),
            high_rules=data.get("high_rules", cls.high_rules),
            medium_rules=data.get("medium_rules", cls.medium_rules),
            low_rules=data.get("low_rules", cls.low_rules),
        )


@dataclass
class HierarchicalCompactionConfig:
    """
    分层上下文压缩完整配置
    
    可在Agent配置中使用，允许用户完全自定义压缩行为。
    
    使用示例:
        # 在Agent配置中
        class MyAgent(ConversableAgent):
            hierarchical_compaction_config: HierarchicalCompactionConfig = Field(
                default_factory=lambda: HierarchicalCompactionConfig(
                    strategy=CompactionStrategy.LLM_SUMMARY,
                    token_threshold=50000,
                    prompts=CompactionPromptConfig(
                        chapter_summary_template="自定义模板...",
                    ),
                )
            )
    """
    
    # 基础配置
    enabled: bool = True
    strategy: CompactionStrategy = CompactionStrategy.LLM_SUMMARY
    
    # 触发配置
    trigger: CompactionTrigger = CompactionTrigger.TOKEN_THRESHOLD
    token_threshold: int = 50000           # Token阈值触发
    check_interval: int = 10               # 周期性检查间隔（步数）
    
    # LLM配置
    llm_max_tokens: int = 500              # LLM输出最大token
    llm_temperature: float = 0.3           # LLM温度
    
    # 压缩配置
    prompts: CompactionPromptConfig = field(default_factory=CompactionPromptConfig)
    rules: CompactionRuleConfig = field(default_factory=CompactionRuleConfig)
    
    # 保护配置
    protect_recent_chapters: int = 2       # 保护最近N章
    protect_recent_tokens: int = 20000     # 保护最近N tokens
    
    # 存储配置
    archive_enabled: bool = True           # 是否归档压缩内容
    archive_to_filesystem: bool = True     # 归档到文件系统
    
    # 监控配置
    log_compactions: bool = True
    track_statistics: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "strategy": self.strategy.value,
            "trigger": self.trigger.value,
            "token_threshold": self.token_threshold,
            "check_interval": self.check_interval,
            "llm_max_tokens": self.llm_max_tokens,
            "llm_temperature": self.llm_temperature,
            "prompts": self.prompts.to_dict(),
            "rules": self.rules.to_dict(),
            "protect_recent_chapters": self.protect_recent_chapters,
            "protect_recent_tokens": self.protect_recent_tokens,
            "archive_enabled": self.archive_enabled,
            "archive_to_filesystem": self.archive_to_filesystem,
            "log_compactions": self.log_compactions,
            "track_statistics": self.track_statistics,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HierarchicalCompactionConfig":
        prompts_data = data.get("prompts", {})
        rules_data = data.get("rules", {})
        
        return cls(
            enabled=data.get("enabled", True),
            strategy=CompactionStrategy(data.get("strategy", "llm_summary")),
            trigger=CompactionTrigger(data.get("trigger", "token_threshold")),
            token_threshold=data.get("token_threshold", 50000),
            check_interval=data.get("check_interval", 10),
            llm_max_tokens=data.get("llm_max_tokens", 500),
            llm_temperature=data.get("llm_temperature", 0.3),
            prompts=CompactionPromptConfig.from_dict(prompts_data),
            rules=CompactionRuleConfig.from_dict(rules_data),
            protect_recent_chapters=data.get("protect_recent_chapters", 2),
            protect_recent_tokens=data.get("protect_recent_tokens", 20000),
            archive_enabled=data.get("archive_enabled", True),
            archive_to_filesystem=data.get("archive_to_filesystem", True),
            log_compactions=data.get("log_compactions", True),
            track_statistics=data.get("track_statistics", True),
        )
    
    @classmethod
    def default(cls) -> "HierarchicalCompactionConfig":
        """创建默认配置"""
        return cls()
    
    @classmethod
    def minimal(cls) -> "HierarchicalCompactionConfig":
        """创建最小配置（仅截断，不使用LLM）"""
        return cls(
            enabled=True,
            strategy=CompactionStrategy.TRUNCATE,
            token_threshold=30000,
        )
    
    @classmethod
    def aggressive(cls) -> "HierarchicalCompactionConfig":
        """创建激进配置（更频繁压缩）"""
        return cls(
            enabled=True,
            strategy=CompactionStrategy.LLM_SUMMARY,
            token_threshold=30000,
            check_interval=5,
            protect_recent_chapters=1,
            protect_recent_tokens=10000,
        )


# 预定义的Prompt模板集合
PREDEFINED_PROMPT_TEMPLATES = {
    # OpenCode风格的结构化摘要
    "opencode_style": CompactionPromptConfig(
        chapter_summary_template="""Provide a detailed summary for the task phase above.

Focus on information that would be helpful for continuing the conversation, including:
- What we did
- What we're doing
- Which files we're working on
- What we're going to do next

---
## Goal

[What goal(s) is the user trying to accomplish?]

## Instructions

- [What important instructions did the user give you that are relevant]
- [If there is a plan or spec, include information about it]

## Discoveries

[What notable things were learned during this conversation]

## Accomplished

[What work has been completed, what work is still in progress, and what work is left?]

## Relevant files / directories

[Construct a structured list of relevant files that have been read, edited, or created]
---
""",
        section_compact_template="""Summarize this step concisely:

Step: {step_name}
Priority: {priority}
Content: {content}

Summary:""",
    ),
    
    # 简洁风格
    "concise": CompactionPromptConfig(
        chapter_summary_template="""阶段: {title} ({phase})
步骤数: {section_count}

摘要:
{sections_overview}
""",
        section_compact_template="""{step_name}: {content}

压缩为:""",
    ),
    
    # 详细风格
    "detailed": CompactionPromptConfig(
        chapter_summary_template="""# 任务阶段报告

## 基本信息
- **阶段名称**: {title}
- **阶段类型**: {phase}
- **执行步骤数**: {section_count}

## 执行详情
{sections_overview}

## 分析总结

### 主要目标
[请描述这个阶段的主要目标]

### 完成情况
[请详细描述已完成的工作和结果]

### 重要发现
[请列出在执行过程中的重要发现]

### 问题与风险
[请指出遇到的问题和潜在风险]

### 下一步计划
[请描述下一步的计划和建议]

## 相关资源
[请列出涉及的文件、资源和依赖]
""",
        section_compact_template="""请为以下执行步骤生成详细摘要：

**步骤名称**: {step_name}
**优先级**: {priority}

**执行内容**:
{content}

**摘要要求**:
1. 主要执行内容
2. 关键决策和原因
3. 执行结果和影响
4. 需要注意的事项

**摘要**:
""",
    ),
}


def get_prompt_template(style: str) -> Optional[CompactionPromptConfig]:
    """
    获取预定义的Prompt模板
    
    Args:
        style: 模板风格 ("opencode_style", "concise", "detailed")
        
    Returns:
        Prompt配置，如果不存在返回None
    """
    return PREDEFINED_PROMPT_TEMPLATES.get(style)