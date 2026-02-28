"""
Context Assembler - 上下文组装器

将ContextLifecycle管理的内容组装成Prompt片段，注入到Agent输入中。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator import ContextLifecycleOrchestrator
    from .slot_manager import ContextSlot, SlotType

logger = logging.getLogger(__name__)


@dataclass
class PromptSection:
    """Prompt片段"""
    name: str
    content: str
    priority: int = 5
    slot_type: Optional[str] = None
    is_compressed: bool = False
    
    def to_string(self) -> str:
        return self.content


@dataclass  
class AssembledPrompt:
    """组装后的Prompt"""
    system_prompt: str = ""
    active_skills: List[PromptSection] = field(default_factory=list)
    dormant_skills: List[PromptSection] = field(default_factory=list)
    active_tools: List[PromptSection] = field(default_factory=list)
    resources: List[PromptSection] = field(default_factory=list)
    memories: List[PromptSection] = field(default_factory=list)
    
    total_tokens_estimate: int = 0
    sections_count: int = 0
    
    def get_full_prompt(self) -> str:
        """获取完整组装的Prompt"""
        parts = []
        
        if self.system_prompt:
            parts.append(self.system_prompt)
        
        # 活跃Skills（完整内容）
        if self.active_skills:
            parts.append("\n\n# Active Skills\n")
            for section in self.active_skills:
                parts.append(f"\n## {section.name}\n")
                parts.append(section.content)
        
        # 休眠Skills（摘要）
        if self.dormant_skills:
            parts.append("\n\n# Completed Skills (Summary)\n")
            for section in self.dormant_skills:
                parts.append(f"\n{section.content}\n")
        
        # 工具定义
        if self.active_tools:
            parts.append("\n\n# Available Tools\n")
            for section in self.active_tools:
                parts.append(f"\n{section.content}\n")
        
        # 资源
        if self.resources:
            parts.append("\n\n# Resources\n")
            for section in self.resources:
                parts.append(f"\n{section.content}\n")
        
        # 记忆
        if self.memories:
            parts.append("\n\n# Context Memory\n")
            for section in self.memories:
                parts.append(f"\n{section.content}\n")
        
        return "".join(parts)
    
    def get_token_estimate(self) -> int:
        """估算token数量"""
        return len(self.get_full_prompt()) // 4


class ContextAssembler:
    """
    上下文组装器
    
    将ContextLifecycle管理的槽位内容组装成可注入的Prompt
    """
    
    def __init__(
        self,
        orchestrator: "ContextLifecycleOrchestrator",
        system_prompt: str = "",
        max_tokens: int = 30000,
        skill_format_func: Optional[Callable] = None,
        tool_format_func: Optional[Callable] = None,
    ):
        self._orchestrator = orchestrator
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens
        self._skill_format_func = skill_format_func
        self._tool_format_func = tool_format_func
    
    def assemble(self) -> AssembledPrompt:
        """组装上下文为Prompt"""
        result = AssembledPrompt(system_prompt=self._system_prompt)
        
        slot_manager = self._orchestrator.get_slot_manager()
        skill_manager = self._orchestrator.get_skill_manager()
        tool_manager = self._orchestrator.get_tool_manager()
        
        # 1. 活跃Skills（完整内容，高优先级）
        for skill_name in skill_manager.get_active_skills():
            slot = slot_manager.get_slot_by_name(skill_name)
            if slot and slot.content:
                section = PromptSection(
                    name=skill_name,
                    content=slot.content,
                    priority=10,
                    slot_type="skill",
                    is_compressed=False,
                )
                result.active_skills.append(section)
        
        # 2. 休眠Skills（摘要形式）
        for skill_name in skill_manager.get_dormant_skills():
            slot = slot_manager.get_slot_by_name(skill_name)
            if slot and slot.content:
                section = PromptSection(
                    name=skill_name,
                    content=slot.content,
                    priority=3,
                    slot_type="skill",
                    is_compressed=True,
                )
                result.dormant_skills.append(section)
        
        # 3. 已加载的工具定义
        for tool_name in tool_manager.get_loaded_tools():
            slot = slot_manager.get_slot_by_name(tool_name)
            if slot and slot.content:
                section = PromptSection(
                    name=tool_name,
                    content=slot.content,
                    priority=5,
                    slot_type="tool",
                )
                result.active_tools.append(section)
        
        # 4. 按token预算排序和截断
        result = self._apply_token_budget(result)
        
        result.sections_count = (
            len(result.active_skills) + 
            len(result.dormant_skills) + 
            len(result.active_tools)
        )
        result.total_tokens_estimate = result.get_token_estimate()
        
        return result
    
    def _apply_token_budget(self, result: AssembledPrompt) -> AssembledPrompt:
        """应用token预算限制"""
        current_estimate = result.get_token_estimate()
        
        if current_estimate <= self._max_tokens:
            return result
        
        # 按优先级排序所有section
        all_sections = []
        for s in result.dormant_skills:
            all_sections.append(("dormant", s))
        
        # 从低优先级开始移除
        all_sections.sort(key=lambda x: x[1].priority)
        
        for section_type, section in all_sections:
            if result.get_token_estimate() <= self._max_tokens:
                break
            
            if section_type == "dormant":
                if section in result.dormant_skills:
                    result.dormant_skills.remove(section)
                    logger.debug(f"[Assembler] Removed dormant skill: {section.name}")
        
        return result
    
    def get_injection_messages(
        self,
        user_message: str,
        include_history: bool = True,
    ) -> List[Dict[str, str]]:
        """
        获取可注入到LLM的消息列表
        
        返回格式兼容OpenAI消息格式
        """
        assembled = self.assemble()
        messages = []
        
        # System消息
        system_content = assembled.system_prompt
        if assembled.dormant_skills:
            system_content += "\n\n" + "# Completed Tasks Summary\n"
            for section in assembled.dormant_skills:
                system_content += f"\n{section.content}\n"
        
        if system_content:
            messages.append({
                "role": "system",
                "content": system_content,
            })
        
        # 活跃Skills作为重要的上下文
        if assembled.active_skills:
            skills_content = "# Current Skill Instructions\n\n"
            for section in assembled.active_skills:
                skills_content += f"## {section.name}\n\n{section.content}\n\n"
            
            messages.append({
                "role": "system",
                "content": skills_content,
            })
        
        # 工具定义
        if assembled.active_tools:
            tools_content = "# Available Tools\n\n"
            for section in assembled.active_tools:
                tools_content += f"{section.content}\n"
            
            messages.append({
                "role": "system", 
                "content": tools_content,
            })
        
        # 用户消息
        messages.append({
            "role": "user",
            "content": user_message,
        })
        
        return messages
    
    def get_skill_context_for_prompt(self) -> str:
        """
        获取Skill上下文，用于插入到System Prompt
        
        这是一个简化方法，只返回Skill相关内容
        """
        assembled = self.assemble()
        parts = []
        
        if assembled.active_skills:
            parts.append("<active-skills>")
            for section in assembled.active_skills:
                parts.append(f"\n<skill name=\"{section.name}\">\n")
                parts.append(section.content)
                parts.append("\n</skill>")
            parts.append("\n</active-skills>")
        
        if assembled.dormant_skills:
            parts.append("\n<completed-skills>")
            for section in assembled.dormant_skills:
                parts.append(f"\n{section.content}")
            parts.append("\n</completed-skills>")
        
        return "".join(parts)
    
    def get_tools_context_for_prompt(self) -> str:
        """获取工具定义上下文"""
        assembled = self.assemble()
        
        if not assembled.active_tools:
            return ""
        
        parts = ["<tools>\n"]
        for section in assembled.active_tools:
            parts.append(section.content)
            parts.append("\n")
        parts.append("</tools>")
        
        return "".join(parts)
    
    def set_system_prompt(self, prompt: str) -> None:
        """设置系统提示"""
        self._system_prompt = prompt
    
    def set_max_tokens(self, max_tokens: int) -> None:
        """设置最大token数"""
        self._max_tokens = max_tokens


def create_context_assembler(
    orchestrator: "ContextLifecycleOrchestrator",
    system_prompt: str = "",
    max_tokens: int = 30000,
) -> ContextAssembler:
    """创建上下文组装器"""
    return ContextAssembler(
        orchestrator=orchestrator,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
    )