"""
自定义Part开发SDK

提供便捷的自定义Part开发工具和模板
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type, Union

from derisk._private.pydantic import BaseModel, Field
from derisk.vis.parts import PartStatus, PartType, VisPart

logger = logging.getLogger(__name__)


@dataclass
class PartTemplate:
    """Part模板"""
    name: str
    description: str
    part_type: PartType
    default_fields: Dict[str, Any] = field(default_factory=dict)
    required_fields: List[str] = field(default_factory=list)
    field_validators: Dict[str, Callable[[Any], bool]] = field(default_factory=dict)
    example_data: Optional[Dict[str, Any]] = None
    
    def create_part(self, **kwargs) -> VisPart:
        """
        根据模板创建Part
        
        Args:
            **kwargs: Part字段
            
        Returns:
            Part实例
        """
        # 合并默认字段
        data = {**self.default_fields, **kwargs}
        
        # 验证必需字段
        for field_name in self.required_fields:
            if field_name not in data or data[field_name] is None:
                raise ValueError(f"缺少必需字段: {field_name}")
        
        # 验证字段
        for field_name, validator in self.field_validators.items():
            if field_name in data and not validator(data[field_name]):
                raise ValueError(f"字段验证失败: {field_name}")
        
        # 创建Part (简化版本,实际应根据part_type创建具体类型)
        part = VisPart(
            type=self.part_type,
            content=data.get("content", ""),
            metadata=data.get("metadata", {}),
            **{k: v for k, v in data.items() if k not in ["content", "metadata"]}
        )
        
        return part


class PartBuilder:
    """
    Part构建器
    
    流式API构建自定义Part
    """
    
    def __init__(self, part_type: PartType):
        self._type = part_type
        self._content = ""
        self._status = PartStatus.PENDING
        self._metadata: Dict[str, Any] = {}
        self._uid: Optional[str] = None
    
    def with_content(self, content: str) -> "PartBuilder":
        """设置内容"""
        self._content = content
        return self
    
    def with_status(self, status: PartStatus) -> "PartBuilder":
        """设置状态"""
        self._status = status
        return self
    
    def with_metadata(self, **kwargs) -> "PartBuilder":
        """设置元数据"""
        self._metadata.update(kwargs)
        return self
    
    def with_uid(self, uid: str) -> "PartBuilder":
        """设置UID"""
        self._uid = uid
        return self
    
    def build(self) -> VisPart:
        """构建Part"""
        return VisPart(
            type=self._type,
            content=self._content,
            status=self._status,
            metadata=self._metadata,
            uid=self._uid,
        )


class CustomPartRegistry:
    """
    自定义Part注册表
    
    管理所有自定义Part模板
    """
    
    def __init__(self):
        self._templates: Dict[str, PartTemplate] = {}
        self._factories: Dict[str, Callable[..., VisPart]] = {}
    
    def register_template(self, template: PartTemplate):
        """
        注册模板
        
        Args:
            template: Part模板
        """
        self._templates[template.name] = template
        logger.info(f"[PartSDK] 注册模板: {template.name}")
    
    def register_factory(
        self,
        name: str,
        factory: Callable[..., VisPart]
    ):
        """
        注册工厂函数
        
        Args:
            name: 名称
            factory: 工厂函数
        """
        self._factories[name] = factory
        logger.info(f"[PartSDK] 注册工厂: {name}")
    
    def create(self, name: str, **kwargs) -> VisPart:
        """
        创建Part
        
        Args:
            name: 模板或工厂名称
            **kwargs: 参数
            
        Returns:
            Part实例
        """
        # 尝试从模板创建
        if name in self._templates:
            return self._templates[name].create_part(**kwargs)
        
        # 尝试从工厂创建
        if name in self._factories:
            return self._factories[name](**kwargs)
        
        raise ValueError(f"未找到模板或工厂: {name}")
    
    def list_templates(self) -> List[str]:
        """列出所有模板"""
        return list(self._templates.keys())
    
    def get_template_info(self, name: str) -> Optional[Dict[str, Any]]:
        """获取模板信息"""
        if name not in self._templates:
            return None
        
        template = self._templates[name]
        return {
            "name": template.name,
            "description": template.description,
            "part_type": template.part_type.value,
            "default_fields": template.default_fields,
            "required_fields": template.required_fields,
            "example_data": template.example_data,
        }


# 预定义模板

TEMPLATES = {
    "markdown_text": PartTemplate(
        name="markdown_text",
        description="Markdown格式文本Part",
        part_type=PartType.TEXT,
        default_fields={"format": "markdown"},
        required_fields=["content"],
        example_data={"content": "# Title\n\nContent here..."},
    ),
    
    "python_code": PartTemplate(
        name="python_code",
        description="Python代码Part",
        part_type=PartType.CODE,
        default_fields={"language": "python", "line_numbers": True},
        required_fields=["content"],
        example_data={"content": "def hello():\n    print('Hello')"},
    ),
    
    "bash_tool": PartTemplate(
        name="bash_tool",
        description="Bash工具执行Part",
        part_type=PartType.TOOL_USE,
        default_fields={"tool_name": "bash"},
        required_fields=["tool_args"],
        field_validators={
            "tool_args": lambda x: isinstance(x, dict) and "command" in x
        },
        example_data={"tool_args": {"command": "ls -la"}},
    ),
    
    "ai_thinking": PartTemplate(
        name="ai_thinking",
        description="AI思考过程Part",
        part_type=PartType.THINKING,
        default_fields={"expand": False},
        required_fields=["content"],
        example_data={"content": "让我分析一下这个问题..."},
    ),
}


# Part DSL (领域特定语言)

class PartDSL:
    """
    Part DSL
    
    提供声明式Part定义语法
    """
    
    @staticmethod
    def text(content: str, **kwargs) -> VisPart:
        """创建文本Part"""
        return PartBuilder(PartType.TEXT).with_content(content).with_metadata(**kwargs).build()
    
    @staticmethod
    def code(content: str, language: str = "python", **kwargs) -> VisPart:
        """创建代码Part"""
        return (
            PartBuilder(PartType.CODE)
            .with_content(content)
            .with_metadata(language=language, **kwargs)
            .build()
        )
    
    @staticmethod
    def tool(name: str, args: Dict[str, Any], **kwargs) -> VisPart:
        """创建工具Part"""
        return (
            PartBuilder(PartType.TOOL_USE)
            .with_metadata(tool_name=name, tool_args=args, **kwargs)
            .build()
        )
    
    @staticmethod
    def thinking(content: str, expand: bool = False, **kwargs) -> VisPart:
        """创建思考Part"""
        return (
            PartBuilder(PartType.THINKING)
            .with_content(content)
            .with_metadata(expand=expand, **kwargs)
            .build()
        )


# 装饰器: 自动创建Part

def auto_part(part_type: PartType = PartType.TEXT, **default_fields):
    """
    自动创建Part装饰器
    
    Args:
        part_type: Part类型
        **default_fields: 默认字段
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            # 执行原函数
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            # 自动创建Part
            if isinstance(result, VisPart):
                return result
            elif isinstance(result, str):
                return PartBuilder(part_type).with_content(result).with_metadata(**default_fields).build()
            elif isinstance(result, dict):
                return PartBuilder(part_type).with_metadata(**result, **default_fields).build()
            else:
                return PartBuilder(part_type).with_content(str(result)).with_metadata(**default_fields).build()
        
        return wrapper
    
    return decorator


import asyncio


# 全局注册表
_registry: Optional[CustomPartRegistry] = None


def get_part_registry() -> CustomPartRegistry:
    """获取全局Part注册表"""
    global _registry
    if _registry is None:
        _registry = CustomPartRegistry()
        
        # 注册预定义模板
        for template in TEMPLATES.values():
            _registry.register_template(template)
    
    return _registry


# 便捷函数

def create_part(name: str, **kwargs) -> VisPart:
    """
    创建Part
    
    Args:
        name: 模板名称
        **kwargs: 参数
        
    Returns:
        Part实例
    """
    return get_part_registry().create(name, **kwargs)