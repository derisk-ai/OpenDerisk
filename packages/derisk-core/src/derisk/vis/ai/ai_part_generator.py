"""
AI辅助Part生成系统

使用AI模型智能生成Part内容
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from derisk.vis.parts import (
    CodePart,
    PartStatus,
    PartType,
    TextPart,
    ThinkingPart,
    ToolUsePart,
    PlanPart,
    VisPart,
)

logger = logging.getLogger(__name__)


class GenerationContext:
    """生成上下文"""
    
    def __init__(
        self,
        prompt: str,
        part_type: Optional[PartType] = None,
        style: Optional[str] = None,
        language: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.prompt = prompt
        self.part_type = part_type
        self.style = style
        self.language = language
        self.metadata = metadata or {}
        self.timestamp = datetime.now()


class AIPartGenerator(ABC):
    """AI Part生成器基类"""
    
    @abstractmethod
    async def generate(
        self,
        context: GenerationContext
    ) -> VisPart:
        """
        生成Part
        
        Args:
            context: 生成上下文
            
        Returns:
            生成的Part
        """
        pass
    
    @abstractmethod
    async def enhance(
        self,
        part: VisPart,
        enhancement: str
    ) -> VisPart:
        """
        增强现有Part
        
        Args:
            part: Part实例
            enhancement: 增强指令
            
        Returns:
            增强后的Part
        """
        pass


class MockAIPartGenerator(AIPartGenerator):
    """
    Mock AI生成器 (用于测试)
    
    实际使用时替换为真实LLM调用
    """
    
    async def generate(self, context: GenerationContext) -> VisPart:
        """生成Part (Mock实现)"""
        # 根据类型生成不同的Part
        if context.part_type == PartType.CODE:
            return CodePart.create(
                code=f"# Generated Code\n# Prompt: {context.prompt}\n\ndef generated_function():\n    pass",
                language=context.language or "python"
            )
        elif context.part_type == PartType.THINKING:
            return ThinkingPart.create(
                content=f"Thinking about: {context.prompt}"
            )
        elif context.part_type == PartType.PLAN:
            return PlanPart.create(
                title=f"Plan for: {context.prompt}",
                items=[
                    {"task": "Step 1: Analyze", "status": "pending"},
                    {"task": "Step 2: Plan", "status": "pending"},
                    {"task": "Step 3: Execute", "status": "pending"},
                ]
            )
        else:
            return TextPart.create(
                content=f"Generated content for: {context.prompt}",
                format=context.style or "markdown"
            )
    
    async def enhance(self, part: VisPart, enhancement: str) -> VisPart:
        """增强Part (Mock实现)"""
        if isinstance(part, TextPart):
            enhanced_content = f"{part.content}\n\n[Enhanced: {enhancement}]"
            return part.copy(update={"content": enhanced_content})
        elif isinstance(part, CodePart):
            enhanced_code = f"{part.content}\n\n# Enhanced: {enhancement}"
            return part.copy(update={"content": enhanced_code})
        else:
            return part


class LLMPartGenerator(AIPartGenerator):
    """
    基于LLM的Part生成器
    
    集成真实LLM进行Part生成
    """
    
    def __init__(self, llm_client: Any = None):
        """
        初始化
        
        Args:
            llm_client: LLM客户端 (如OpenAI, Claude等)
        """
        self.llm_client = llm_client
        self._prompts = self._load_prompts()
    
    def _load_prompts(self) -> Dict[str, str]:
        """加载提示模板"""
        return {
            "code": """Generate {language} code based on the following requirement:

{prompt}

Requirements:
- Clean and well-structured
- Include comments
- Follow best practices

Output only the code without explanations.""",
            
            "text": """Generate {style} content based on the following prompt:

{prompt}

Requirements:
- Clear and concise
- Well-formatted
- Engaging

Output the content directly.""",
            
            "plan": """Create an execution plan based on the following goal:

{prompt}

Output as JSON array with format:
[{{"task": "task description", "status": "pending"}}]""",
            
            "thinking": """Analyze and think about the following:

{prompt}

Provide a structured analysis.""",
        }
    
    async def generate(self, context: GenerationContext) -> VisPart:
        """使用LLM生成Part"""
        if not self.llm_client:
            logger.warning("[AIGen] LLM客户端未配置,使用Mock生成器")
            return await MockAIPartGenerator().generate(context)
        
        try:
            # 构建提示
            prompt = self._build_prompt(context)
            
            # 调用LLM (这里需要根据实际LLM客户端调整)
            # response = await self.llm_client.generate(prompt)
            # content = response.content
            
            # Mock响应
            content = f"LLM generated content for: {context.prompt}"
            
            # 根据类型创建Part
            if context.part_type == PartType.CODE:
                return CodePart.create(code=content, language=context.language or "python")
            elif context.part_type == PartType.THINKING:
                return ThinkingPart.create(content=content)
            else:
                return TextPart.create(content=content)
                
        except Exception as e:
            logger.error(f"[AIGen] 生成失败: {e}")
            raise
    
    async def enhance(self, part: VisPart, enhancement: str) -> VisPart:
        """使用LLM增强Part"""
        if not self.llm_client:
            logger.warning("[AIGen] LLM客户端未配置")
            return part
        
        try:
            # 构建增强提示
            prompt = f"""Enhance the following content:

Current Content:
{part.content}

Enhancement Request:
{enhancement}

Output the enhanced content."""
            
            # 调用LLM
            # response = await self.llm_client.generate(prompt)
            # enhanced_content = response.content
            
            # Mock响应
            enhanced_content = f"{part.content}\n\n[Enhanced: {enhancement}]"
            
            return part.copy(update={"content": enhanced_content})
            
        except Exception as e:
            logger.error(f"[AIGen] 增强失败: {e}")
            return part
    
    def _build_prompt(self, context: GenerationContext) -> str:
        """构建提示"""
        part_type = context.part_type or PartType.TEXT
        template_key = part_type.value if hasattr(part_type, 'value') else str(part_type)
        
        template = self._prompts.get(template_key, self._prompts["text"])
        
        return template.format(
            prompt=context.prompt,
            language=context.language or "python",
            style=context.style or "markdown"
        )


class SmartPartSuggester:
    """
    智能Part建议器
    
    根据上下文建议合适的Part类型和内容
    """
    
    def __init__(self, generator: AIPartGenerator):
        self.generator = generator
        self._suggestions_cache: Dict[str, List[Dict[str, Any]]] = {}
    
    async def suggest(
        self,
        context: str,
        max_suggestions: int = 3
    ) -> List[Dict[str, Any]]:
        """
        根据上下文建议Part
        
        Args:
            context: 上下文描述
            max_suggestions: 最大建议数量
            
        Returns:
            建议列表
        """
        suggestions = []
        
        # 简单的规则匹配 (实际可使用ML模型)
        if "code" in context.lower() or "function" in context.lower():
            suggestions.append({
                "part_type": PartType.CODE,
                "confidence": 0.9,
                "reason": "检测到代码相关关键词"
            })
        
        if "think" in context.lower() or "analyze" in context.lower():
            suggestions.append({
                "part_type": PartType.THINKING,
                "confidence": 0.85,
                "reason": "检测到思考分析关键词"
            })
        
        if "plan" in context.lower() or "step" in context.lower():
            suggestions.append({
                "part_type": PartType.PLAN,
                "confidence": 0.8,
                "reason": "检测到规划步骤关键词"
            })
        
        if "execute" in context.lower() or "tool" in context.lower():
            suggestions.append({
                "part_type": PartType.TOOL_USE,
                "confidence": 0.75,
                "reason": "检测到工具执行关键词"
            })
        
        # 默认文本建议
        if not suggestions:
            suggestions.append({
                "part_type": PartType.TEXT,
                "confidence": 0.5,
                "reason": "默认文本类型"
            })
        
        return suggestions[:max_suggestions]
    
    async def auto_generate(
        self,
        context: str
    ) -> VisPart:
        """
        自动选择并生成Part
        
        Args:
            context: 上下文描述
            
        Returns:
            生成的Part
        """
        suggestions = await self.suggest(context)
        
        if suggestions:
            best = suggestions[0]
            gen_context = GenerationContext(
                prompt=context,
                part_type=best["part_type"]
            )
            return await self.generator.generate(gen_context)
        
        # 默认生成文本Part
        return await self.generator.generate(GenerationContext(prompt=context))


# 装饰器: AI生成Part

def ai_generated(
    part_type: PartType = PartType.TEXT,
    language: Optional[str] = None,
    style: Optional[str] = None
):
    """
    AI生成装饰器
    
    Args:
        part_type: Part类型
        language: 语言
        style: 风格
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            # 执行原函数获取prompt
            prompt = await func(*args, **kwargs) if hasattr(func, '__call__') else str(func(*args, **kwargs))
            
            # 创建生成上下文
            context = GenerationContext(
                prompt=prompt,
                part_type=part_type,
                language=language,
                style=style
            )
            
            # 生成Part
            generator = get_ai_generator()
            return await generator.generate(context)
        
        return wrapper
    
    return decorator


# 全局生成器
_ai_generator: Optional[AIPartGenerator] = None


def get_ai_generator() -> AIPartGenerator:
    """获取全局AI生成器"""
    global _ai_generator
    if _ai_generator is None:
        _ai_generator = MockAIPartGenerator()
    return _ai_generator


def set_ai_generator(generator: AIPartGenerator):
    """设置全局AI生成器"""
    global _ai_generator
    _ai_generator = generator