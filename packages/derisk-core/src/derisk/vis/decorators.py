"""
VIS工具函数和装饰器
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Optional, Type

from derisk.vis.base import Vis
from derisk.vis.parts import PartType, VisPart

logger = logging.getLogger(__name__)


def vis_component(tag: str):
    """
    VIS组件注册装饰器
    
    简化VIS组件的注册流程
    
    示例:
        @vis_component("d-custom-plan")
        class CustomPlanVis(Vis):
            def sync_generate_param(self, **kwargs):
                return kwargs["content"]
    
    Args:
        tag: VIS标签名
    """
    def decorator(cls: Type[Vis]) -> Type[Vis]:
        # 添加vis_tag类方法
        @classmethod
        def vis_tag(cls) -> str:
            return tag
        
        cls.vis_tag = vis_tag
        cls._vis_tag = tag
        
        # 自动注册
        try:
            instance = cls()
            Vis.register(tag, instance)
            logger.info(f"[VIS] 已注册组件: {tag} -> {cls.__name__}")
        except Exception as e:
            logger.warning(f"[VIS] 注册组件失败 {tag}: {e}")
        
        return cls
    
    return decorator


def part_converter(part_type: PartType):
    """
    Part转换器装饰器
    
    为函数添加Part转换能力
    
    示例:
        @part_converter(PartType.TEXT)
        def text_to_part(text: str) -> Dict[str, Any]:
            return {"content": text}
    
    Args:
        part_type: Part类型
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> VisPart:
            result = func(*args, **kwargs)
            
            # 创建Part
            if isinstance(result, VisPart):
                return result
            elif isinstance(result, dict):
                # 从字典创建Part
                part_class = _get_part_class(part_type)
                if part_class:
                    return part_class(**result)
            
            # 默认创建文本Part
            from derisk.vis.parts import TextPart
            return TextPart.create(content=str(result))
        
        wrapper._part_type = part_type
        return wrapper
    
    return decorator


def _get_part_class(part_type: PartType) -> Optional[Type[VisPart]]:
    """根据Part类型获取对应的Part类"""
    from derisk.vis.parts import (
        TextPart,
        CodePart,
        ToolUsePart,
        ThinkingPart,
        PlanPart,
        ImagePart,
        FilePart,
        InteractionPart,
        ErrorPart,
    )
    
    part_map = {
        PartType.TEXT: TextPart,
        PartType.CODE: CodePart,
        PartType.TOOL_USE: ToolUsePart,
        PartType.THINKING: ThinkingPart,
        PartType.PLAN: PlanPart,
        PartType.IMAGE: ImagePart,
        PartType.FILE: FilePart,
        PartType.INTERACTION: InteractionPart,
        PartType.ERROR: ErrorPart,
    }
    
    return part_map.get(part_type)


def streaming_part(part_type: PartType = PartType.TEXT):
    """
    流式Part装饰器
    
    自动处理流式Part的创建和更新
    
    示例:
        @streaming_part(PartType.THINKING)
        async def generate_thinking(prompt: str):
            for chunk in llm_stream(prompt):
                yield chunk
    
    Args:
        part_type: Part类型
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取统一转换器
            from derisk.vis.unified_converter import UnifiedVisManager
            
            converter = UnifiedVisManager.get_converter()
            
            # 创建流式Part
            part_class = _get_part_class(part_type)
            if not part_class:
                from derisk.vis.parts import TextPart
                part_class = TextPart
            
            part = part_class.create(content="", streaming=True)
            converter.add_part_manually(part)
            
            try:
                # 流式处理
                async for chunk in func(*args, **kwargs):
                    if hasattr(part, 'append'):
                        part = part.append(str(chunk))
                        converter.add_part_manually(part)
                    yield chunk
                
                # 完成
                if hasattr(part, 'complete'):
                    part = part.complete()
                    converter.add_part_manually(part)
            
            except Exception as e:
                if hasattr(part, 'mark_error'):
                    part = part.mark_error(str(e))
                    converter.add_part_manually(part)
                raise
        
        return wrapper
    
    return decorator


def auto_vis_output(part_type: PartType = PartType.TEXT):
    """
    自动VIS输出装饰器
    
    自动将函数返回值转换为Part并添加到VIS
    
    示例:
        @auto_vis_output(PartType.CODE)
        def generate_code(requirement: str) -> str:
            return "def hello(): pass"
    
    Args:
        part_type: Part类型
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            _auto_add_part(part_type, result)
            return result
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            _auto_add_part(part_type, result)
            return result
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def _auto_add_part(part_type: PartType, content: Any):
    """自动添加Part到VIS"""
    from derisk.vis.unified_converter import UnifiedVisManager
    
    converter = UnifiedVisManager.get_converter()
    part_class = _get_part_class(part_type)
    
    if not part_class:
        from derisk.vis.parts import TextPart
        part_class = TextPart
    
    if isinstance(content, VisPart):
        converter.add_part_manually(content)
    elif isinstance(content, dict):
        part = part_class.create(**content)
        converter.add_part_manually(part)
    else:
        part = part_class.create(content=str(content))
        converter.add_part_manually(part)