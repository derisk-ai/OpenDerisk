"""
Agent Prompt 集成配置

定义如何将分层上下文和回溯工具信息注入到 Agent 的 Prompt 中。
需要与主要产品层 Agent 的 Prompt 模板配合调整。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class HierarchicalContextPromptConfig:
    """
    分层上下文 Prompt 配置
    
    这些模板需要与 Agent 的系统提示模板配合使用。
    用户可以在 Agent 配置中自定义这些模板。
    
    使用方式：
    1. 在 Agent 初始化时，将 memory_prompt_config 传入
    2. 在生成系统提示时，调用 format_system_prompt() 注入历史记忆
    3. 回溯工具信息会自动包含在上下文中
    """
    
    # ========== 历史记忆注入模板 ==========
    # 这是注入到 Agent 系统提示中的主模板
    
    memory_injection_template: str = """
## 任务执行历史记忆

以下是任务执行的历史记录，按阶段组织。每个步骤都有唯一ID。

{hierarchical_context}

### 可用工具：
- `recall_section(section_id)` - 查看指定步骤的详细内容
- `recall_chapter(chapter_id)` - 查看指定阶段的所有步骤
- `search_history(query)` - 搜索历史记录

**使用提示**：
- 上下文中 `[ID: section_xxx]` 标记的就是可回溯的步骤ID
- 标有 `[已归档]` 的步骤可以调用 recall_section 查看完整内容
- 回溯工具可以帮助你回顾早期的决策和结果

---
"""
    
    # ========== 工具使用指南 ==========
    
    tool_usage_guide: str = """
### 回溯工具使用指南

当你需要回顾历史步骤时：

1. **查看上下文中的步骤ID**
   - 每个步骤都有 `[ID: section_xxx]` 标记
   - 例如：`[ID: section_15_1735765234]`

2. **调用回溯工具**
   ```
   recall_section("section_15_1735765234")
   ```

3. **搜索历史**
   ```
   search_history("关键词")
   ```

4. **查看整个阶段**
   ```
   recall_chapter("chapter_2_1735765200")
   ```
"""
    
    # ========== 压缩后的内容格式 ==========
    # 当步骤被压缩时，显示给 Agent 的格式
    
    archived_section_hint: str = "[已归档，可使用 recall_section(\"{section_id}\") 查看详情]"
    
    # ========== 注入位置 ==========
    # 控制历史记忆注入到系统提示的哪个位置
    
    injection_position: str = "before_tools"  # before_tools, after_tools, before_system, after_system
    
    # ========== 是否启用 ==========
    
    enable_memory_injection: bool = True
    enable_tool_guide: bool = True
    
    def format_memory_injection(
        self,
        hierarchical_context: str,
        include_tool_guide: bool = True,
    ) -> str:
        """
        格式化注入到系统提示的历史记忆
        
        Args:
            hierarchical_context: 分层上下文内容
            include_tool_guide: 是否包含工具使用指南
            
        Returns:
            格式化后的内容
        """
        content = self.memory_injection_template.format(
            hierarchical_context=hierarchical_context,
        )
        
        if include_tool_guide and self.enable_tool_guide:
            content += self.tool_usage_guide
        
        return content
    
    def format_archived_hint(self, section_id: str) -> str:
        """格式化归档提示"""
        return self.archived_section_hint.format(section_id=section_id)


# ============================================================
# Agent Prompt 模板调整示例
# ============================================================

# 原始 Agent 系统提示模板（示例）
ORIGINAL_SYSTEM_PROMPT = """你是一个智能助手，帮助用户完成任务。

## 你的能力
- 分析问题
- 使用工具
- 解决任务

## 注意事项
- 保持专注
- 高效执行
"""

# 调整后的 Agent 系统提示模板（集成分层上下文）
ADJUSTED_SYSTEM_PROMPT_TEMPLATE = """你是一个智能助手，帮助用户完成任务。

## 你的能力
- 分析问题
- 使用工具
- 解决任务
- **回顾历史**：你可以使用 recall_section、recall_chapter、search_history 工具回顾之前的执行记录

## 任务历史记忆
{memory_context}

## 注意事项
- 保持专注
- 高效执行
- **善用历史**：遇到类似问题时，可以回顾之前的解决方案
"""


# ============================================================
# ReActMasterAgent Prompt 集成示例
# ============================================================

REACT_MASTER_FC_SYSTEM_TEMPLATE_WITH_HIERARCHICAL = """
你是一个遵循最佳实践的 ReAct 代理。

## 核心能力
1. **推理 (Reasoning)**：分析问题，制定计划
2. **行动 (Acting)**：使用工具执行操作
3. **回溯 (Recall)**：回顾历史决策和结果

{memory_context}

## 工具使用原则
1. 先思考，再行动
2. 使用 todo 工具管理任务
3. 使用 recall_* 工具回顾历史

## 输出格式
使用 JSON 格式输出思考和工具调用。
"""


# ============================================================
# 集成到 Agent 的方法
# ============================================================

def integrate_hierarchical_context_to_prompt(
    original_system_prompt: str,
    hierarchical_context: str,
    prompt_config: Optional[HierarchicalContextPromptConfig] = None,
) -> str:
    """
    将分层上下文集成到 Agent 的系统提示中
    
    Args:
        original_system_prompt: 原始系统提示
        hierarchical_context: 分层上下文内容
        prompt_config: Prompt配置
        
    Returns:
        集成后的系统提示
    """
    config = prompt_config or HierarchicalContextPromptConfig()
    
    if not config.enable_memory_injection:
        return original_system_prompt
    
    memory_content = config.format_memory_injection(
        hierarchical_context=hierarchical_context,
    )
    
    # 根据注入位置处理
    if config.injection_position == "before_system":
        return memory_content + "\n" + original_system_prompt
    elif config.injection_position == "after_system":
        return original_system_prompt + "\n" + memory_content
    elif config.injection_position == "before_tools":
        # 在工具说明之前插入
        if "## 工具" in original_system_prompt:
            return original_system_prompt.replace(
                "## 工具",
                memory_content + "\n\n## 工具"
            )
        return original_system_prompt + "\n" + memory_content
    elif config.injection_position == "after_tools":
        # 在工具说明之后插入
        if "## 注意" in original_system_prompt:
            return original_system_prompt.replace(
                "## 注意",
                memory_content + "\n\n## 注意"
            )
        return original_system_prompt + "\n" + memory_content
    
    return original_system_prompt + "\n" + memory_content


def get_section_id_injection_template() -> str:
    """
    获取 section_id 注入模板
    
    这是在生成上下文时，将 section_id 注入到每个步骤的格式
    """
    return """### {step_name}
[ID: {section_id}]{archived_hint}
{content}
"""


# ============================================================
# 配置导出
# ============================================================

# 默认配置
DEFAULT_HIERARCHICAL_PROMPT_CONFIG = HierarchicalContextPromptConfig()

# 简洁配置（少提示）
CONCISE_HIERARCHICAL_PROMPT_CONFIG = HierarchicalContextPromptConfig(
    memory_injection_template="""
## 历史记录
{hierarchical_context}

使用 recall_section(section_id) 查看详情。
""",
    enable_tool_guide=False,
)

# 详细配置（多提示）
DETAILED_HIERARCHICAL_PROMPT_CONFIG = HierarchicalContextPromptConfig(
    memory_injection_template="""
## 任务执行历史记忆

以下是按阶段组织的历史记录。每个步骤都有唯一ID，可用于回溯。

{hierarchical_context}

### 可用的回溯工具

| 工具 | 说明 | 示例 |
|------|------|------|
| recall_section(section_id) | 查看指定步骤详情 | recall_section("section_15_xxx") |
| recall_chapter(chapter_id) | 查看整个阶段 | recall_chapter("chapter_2_xxx") |
| search_history(query) | 搜索历史 | search_history("错误") |

**提示**：上下文中 `[ID: xxx]` 就是可回溯的步骤ID，标有 `[已归档]` 的步骤建议回溯查看完整内容。

---
""",
    tool_usage_guide="",
    enable_tool_guide=True,
)