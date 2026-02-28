"""
分层上下文 Memory Prompt 配置

将历史记忆压缩的prompt作为可配置的memory prompt，
允许用户在Agent配置中自定义编辑。

使用方式：
1. 作为Agent的memory_prompt_template字段
2. 支持用户自定义模板变量
3. 与Agent的系统提示集成
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class MemoryPromptVariables:
    """
    Memory Prompt 变量
    
    在模板中可用的变量
    """
    
    # 章节相关
    chapter_title: str = ""
    chapter_phase: str = ""
    chapter_summary: str = ""
    section_count: int = 0
    sections_overview: str = ""
    
    # 节相关
    step_name: str = ""
    step_priority: str = ""
    step_content: str = ""
    
    # 批量压缩相关
    batch_content: str = ""
    
    # 统计信息
    total_chapters: int = 0
    total_sections: int = 0
    total_tokens: int = 0
    current_phase: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_title": self.chapter_title,
            "chapter_phase": self.chapter_phase,
            "chapter_summary": self.chapter_summary,
            "section_count": self.section_count,
            "sections_overview": self.sections_overview,
            "step_name": self.step_name,
            "step_priority": self.step_priority,
            "step_content": self.step_content,
            "batch_content": self.batch_content,
            "total_chapters": self.total_chapters,
            "total_sections": self.total_sections,
            "total_tokens": self.total_tokens,
            "current_phase": self.current_phase,
        }


@dataclass
class MemoryPromptConfig:
    """
    Memory Prompt 完整配置
    
    用户可以在Agent配置中自定义这些模板。
    这些模板会在压缩和生成上下文时使用。
    
    使用示例：
        class MyAgent(ConversableAgent):
            memory_prompt_config: MemoryPromptConfig = Field(
                default_factory=lambda: MemoryPromptConfig(
                    chapter_summary_prompt="自定义模板...",
                )
            )
    """
    
    # ========== 章节压缩相关 ==========
    
    # 章节摘要生成Prompt（用于LLM压缩）
    chapter_summary_prompt: str = """请为以下任务阶段生成一个结构化的摘要。

## 阶段信息
- 阶段名称: {chapter_title}
- 阶段类型: {chapter_phase}
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
    
    # ========== 节压缩相关 ==========
    
    # 节内容压缩Prompt
    section_compact_prompt: str = """请压缩以下执行步骤的内容，保留关键信息。

步骤名称: {step_name}
优先级: {step_priority}
原始内容:
{step_content}

请生成简洁的摘要（保留关键决策、结果和下一步行动）:
"""
    
    # 批量压缩Prompt
    batch_compact_prompt: str = """请将以下多个相关执行步骤压缩为一个简洁的摘要。

步骤列表:
{batch_content}

请生成：
1. 这些步骤的共同目标
2. 主要执行结果
3. 关键决策和发现
4. 需要注意的事项
"""
    
    # ========== 上下文生成相关 ==========
    
    # 分层上下文输出模板（用于生成给LLM看的上下文）
    hierarchical_context_template: str = """# 任务执行历史

## 执行统计
- 总章节: {total_chapters}
- 总步骤: {total_sections}
- 当前阶段: {current_phase}

{chapters_content}
"""
    
    # 完整章节展示模板
    chapter_full_template: str = """## {chapter_title} ({chapter_phase})
{chapter_summary}

### 执行步骤:
{sections_content}
"""
    
    # 章节索引展示模板（二级索引）
    chapter_index_template: str = """## {chapter_title} ({chapter_phase})
摘要: {chapter_summary}

### 步骤索引:
{sections_index}
"""
    
    # 章节总结展示模板（一级索引）
    chapter_summary_only_template: str = """[{chapter_id}] {chapter_title} ({chapter_phase}): {chapter_summary}
"""
    
    # 节内容展示模板
    section_content_template: str = """#### {step_name}
{step_content}
"""
    
    # 节索引模板
    section_index_template: str = """- [{section_id}] {step_name} ({step_priority}): {step_content_preview}...
"""
    
    # ========== 系统提示相关 ==========
    
    # LLM调用时的系统提示
    llm_system_prompt: str = "You are a helpful assistant specialized in summarizing task execution history. Focus on key decisions, results, and next steps."
    
    # 压缩内容的系统提示（注入到Agent的系统提示中）
    memory_context_system_prompt: str = """## 任务历史记忆

以下是任务执行的历史记录，按阶段组织。你可以使用 `recall_history` 工具回顾早期步骤的详细内容。

{hierarchical_context}

---
*提示: 使用 recall_section(section_id) 查看具体步骤详情*
"""
    
    # ========== 回溯工具相关 ==========
    
    # 回溯结果的展示模板
    recall_section_template: str = """### 步骤详情: {step_name}

**ID**: {section_id}
**优先级**: {step_priority}
**阶段**: {chapter_phase}

#### 内容:
{step_content}

---
*这是归档的历史步骤，可通过 section_id 引用*
"""
    
    recall_chapter_template: str = """## 阶段详情: {chapter_title}

**阶段**: {chapter_phase}
**步骤数**: {section_count}

### 摘要:
{chapter_summary}

### 步骤列表:
{sections_list}
"""
    
    # ========== 配置选项 ==========
    
    # 是否在系统提示中注入历史记忆
    inject_memory_to_system: bool = True
    
    # 历史记忆注入的位置（"before" 或 "after" 系统提示）
    memory_injection_position: str = "after"
    
    # 最大上下文长度（字符）
    max_context_length: int = 10000
    
    # 是否显示步骤ID（用于回溯）
    show_section_ids: bool = True
    
    def format_chapter_summary(
        self,
        chapter_title: str,
        chapter_phase: str,
        section_count: int,
        sections_overview: str,
    ) -> str:
        """格式化章节摘要Prompt"""
        return self.chapter_summary_prompt.format(
            chapter_title=chapter_title,
            chapter_phase=chapter_phase,
            section_count=section_count,
            sections_overview=sections_overview,
        )
    
    def format_section_compact(
        self,
        step_name: str,
        step_priority: str,
        step_content: str,
    ) -> str:
        """格式化节压缩Prompt"""
        return self.section_compact_prompt.format(
            step_name=step_name,
            step_priority=step_priority,
            step_content=step_content[:2000],  # 限制长度
        )
    
    def format_hierarchical_context(
        self,
        total_chapters: int,
        total_sections: int,
        current_phase: str,
        chapters_content: str,
    ) -> str:
        """格式化分层上下文"""
        return self.hierarchical_context_template.format(
            total_chapters=total_chapters,
            total_sections=total_sections,
            current_phase=current_phase,
            chapters_content=chapters_content,
        )
    
    def format_memory_system_prompt(
        self,
        hierarchical_context: str,
    ) -> str:
        """格式化记忆系统提示"""
        return self.memory_context_system_prompt.format(
            hierarchical_context=hierarchical_context,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "chapter_summary_prompt": self.chapter_summary_prompt,
            "section_compact_prompt": self.section_compact_prompt,
            "batch_compact_prompt": self.batch_compact_prompt,
            "hierarchical_context_template": self.hierarchical_context_template,
            "chapter_full_template": self.chapter_full_template,
            "chapter_index_template": self.chapter_index_template,
            "chapter_summary_only_template": self.chapter_summary_only_template,
            "section_content_template": self.section_content_template,
            "section_index_template": self.section_index_template,
            "llm_system_prompt": self.llm_system_prompt,
            "memory_context_system_prompt": self.memory_context_system_prompt,
            "recall_section_template": self.recall_section_template,
            "recall_chapter_template": self.recall_chapter_template,
            "inject_memory_to_system": self.inject_memory_to_system,
            "memory_injection_position": self.memory_injection_position,
            "max_context_length": self.max_context_length,
            "show_section_ids": self.show_section_ids,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryPromptConfig":
        """从字典反序列化"""
        return cls(
            chapter_summary_prompt=data.get("chapter_summary_prompt", cls.chapter_summary_prompt),
            section_compact_prompt=data.get("section_compact_prompt", cls.section_compact_prompt),
            batch_compact_prompt=data.get("batch_compact_prompt", cls.batch_compact_prompt),
            hierarchical_context_template=data.get("hierarchical_context_template", cls.hierarchical_context_template),
            chapter_full_template=data.get("chapter_full_template", cls.chapter_full_template),
            chapter_index_template=data.get("chapter_index_template", cls.chapter_index_template),
            chapter_summary_only_template=data.get("chapter_summary_only_template", cls.chapter_summary_only_template),
            section_content_template=data.get("section_content_template", cls.section_content_template),
            section_index_template=data.get("section_index_template", cls.section_index_template),
            llm_system_prompt=data.get("llm_system_prompt", cls.llm_system_prompt),
            memory_context_system_prompt=data.get("memory_context_system_prompt", cls.memory_context_system_prompt),
            recall_section_template=data.get("recall_section_template", cls.recall_section_template),
            recall_chapter_template=data.get("recall_chapter_template", cls.recall_chapter_template),
            inject_memory_to_system=data.get("inject_memory_to_system", True),
            memory_injection_position=data.get("memory_injection_position", "after"),
            max_context_length=data.get("max_context_length", 10000),
            show_section_ids=data.get("show_section_ids", True),
        )


# 预定义的Memory Prompt模板
MEMORY_PROMPT_PRESETS = {
    # OpenCode风格
    "opencode": MemoryPromptConfig(
        chapter_summary_prompt="""Provide a detailed summary for the task phase above.

Focus on information that would be helpful for continuing the conversation.

---
## Goal
[What goal(s) is the user trying to accomplish?]

## Instructions
- [What important instructions did the user give you]

## Discoveries
[What notable things were learned]

## Accomplished
[What work has been completed, in progress, and left?]

## Relevant files
[List of relevant files]
---
""",
        memory_context_system_prompt="""## Task History

{hierarchical_context}

Use `recall_history` tool to view detailed content of early steps.
""",
    ),
    
    # 简洁风格
    "concise": MemoryPromptConfig(
        chapter_summary_prompt="""阶段: {chapter_title}
步骤: {section_count}

{sections_overview}

摘要:""",
        hierarchical_context_template="""# 历史
章节: {total_chapters} | 步骤: {total_sections} | 当前: {current_phase}

{chapters_content}
""",
        memory_context_system_prompt="""## 历史

{hierarchical_context}
""",
    ),
    
    # 详细报告风格
    "detailed": MemoryPromptConfig(
        chapter_summary_prompt="""# 任务阶段报告

## 基本信息
- 阶段: {chapter_title} ({chapter_phase})
- 步骤数: {section_count}

## 执行详情
{sections_overview}

## 分析总结

### 目标
[主要目标]

### 完成情况
[详细描述]

### 发现
[重要发现]

### 风险
[问题和风险]

### 下一步
[计划和建议]
""",
        memory_context_system_prompt="""## 任务执行历史报告

{hierarchical_context}

---
*使用 recall_section(section_id) 查看详情*
""",
    ),
    
    # 中文优化风格
    "chinese": MemoryPromptConfig(
        chapter_summary_prompt="""请为以下任务阶段生成摘要：

## 阶段信息
- 名称: {chapter_title}
- 类型: {chapter_phase}
- 步骤数: {section_count}

## 步骤概览
{sections_overview}

## 请按以下格式输出：

### 目标
[本阶段要达成的目标]

### 完成事项
[已完成的主要工作]

### 关键发现
[重要发现和洞察]

### 后续跟进
[待处理事项]

### 相关资源
[涉及的文件和资源]
""",
        llm_system_prompt="你是一个专业的任务执行历史总结助手。请用中文生成简洁、结构化的摘要。",
        memory_context_system_prompt="""## 任务历史记录

{hierarchical_context}

---
*使用 recall_history 工具可查看早期步骤详情*
""",
    ),
}


def get_memory_prompt_preset(preset_name: str) -> Optional[MemoryPromptConfig]:
    """
    获取预定义的Memory Prompt模板
    
    Args:
        preset_name: 预设名称 ("opencode", "concise", "detailed", "chinese")
        
    Returns:
        MemoryPromptConfig 配置
    """
    return MEMORY_PROMPT_PRESETS.get(preset_name)


def create_memory_prompt_config(
    preset: Optional[str] = None,
    **customizations,
) -> MemoryPromptConfig:
    """
    创建Memory Prompt配置
    
    Args:
        preset: 预设模板名称
        **customizations: 自定义覆盖
        
    Returns:
        配置好的 MemoryPromptConfig
    """
    if preset and preset in MEMORY_PROMPT_PRESETS:
        base_config = MEMORY_PROMPT_PRESETS[preset]
        config_dict = base_config.to_dict()
        config_dict.update(customizations)
        return MemoryPromptConfig.from_dict(config_dict)
    
    return MemoryPromptConfig(**customizations)