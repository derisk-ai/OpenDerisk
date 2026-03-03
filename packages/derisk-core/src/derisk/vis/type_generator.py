"""
TypeScript类型自动生成脚本

从Python Pydantic模型生成TypeScript类型定义
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Type, get_type_hints

logger = logging.getLogger(__name__)


class TypeScriptTypeGenerator:
    """
    TypeScript类型生成器
    
    从Python类型生成TypeScript类型定义
    """
    
    # Python类型到TypeScript类型的映射
    TYPE_MAP = {
        'str': 'string',
        'int': 'number',
        'float': 'number',
        'bool': 'boolean',
        'dict': 'Record<string, any>',
        'list': 'any[]',
        'Any': 'any',
        'None': 'null',
        'Optional': ' | null',
    }
    
    def __init__(self, output_path: str):
        """
        初始化生成器
        
        Args:
            output_path: TypeScript输出文件路径
        """
        self.output_path = Path(output_path)
        self._generated_enums: Set[str] = set()
        self._generated_interfaces: Set[str] = set()
    
    def generate_from_pydantic_model(self, model_class: Type) -> str:
        """
        从Pydantic模型生成TypeScript接口
        
        Args:
            model_class: Pydantic模型类
            
        Returns:
            TypeScript接口定义
        """
        # 获取模型名称
        model_name = model_class.__name__
        
        # 获取字段
        fields = model_class.model_fields if hasattr(model_class, 'model_fields') else {}
        
        # 生成接口字段
        ts_fields = []
        for field_name, field_info in fields.items():
            ts_type = self._python_type_to_typescript(field_info.annotation)
            optional = not field_info.is_required()
            
            field_str = f"  {field_name}{'?' if optional else ''}: {ts_type};"
            ts_fields.append(field_str)
        
        # 生成接口
        interface = f"export interface {model_name} {{\n"
        interface += "\n".join(ts_fields)
        interface += "\n}"
        
        return interface
    
    def _python_type_to_typescript(self, python_type: Any) -> str:
        """
        将Python类型转换为TypeScript类型
        
        Args:
            python_type: Python类型
            
        Returns:
            TypeScript类型字符串
        """
        # 处理字符串形式的类型
        type_str = str(python_type)
        
        # 基本类型映射
        for py_type, ts_type in self.TYPE_MAP.items():
            if py_type in type_str:
                if py_type == 'Optional':
                    # Optional[X] -> X | null
                    inner_type = type_str.replace('Optional[', '').replace(']', '')
                    inner_ts = self._python_type_to_typescript(inner_type)
                    return f"{inner_ts} | null"
                elif py_type == 'List':
                    # List[X] -> X[]
                    inner_type = type_str.replace('List[', '').replace(']', '')
                    inner_ts = self._python_type_to_typescript(inner_type)
                    return f"{inner_ts}[]"
                elif py_type == 'Dict':
                    # Dict[K, V] -> Record<K, V>
                    return 'Record<string, any>'
                else:
                    return ts_type
        
        # 默认返回any
        return 'any'
    
    def generate_from_enum(self, enum_class: Type) -> str:
        """
        从Python Enum生成TypeScript枚举
        
        Args:
            enum_class: Python Enum类
            
        Returns:
            TypeScript枚举定义
        """
        enum_name = enum_class.__name__
        
        # 生成枚举值
        enum_values = []
        for member in enum_class:
            value = member.value
            if isinstance(value, str):
                enum_values.append(f"  {member.name} = '{value}'")
            else:
                enum_values.append(f"  {member.name} = {value}")
        
        # 生成枚举
        enum_def = f"export enum {enum_name} {{\n"
        enum_def += ",\n".join(enum_values)
        enum_def += "\n}"
        
        return enum_def
    
    def generate_full_typescript(self, models: List[Type], enums: List[Type]) -> str:
        """
        生成完整的TypeScript文件内容
        
        Args:
            models: Pydantic模型列表
            enums: Enum列表
            
        Returns:
            完整的TypeScript文件内容
        """
        lines = [
            "/**",
            " * 自动生成的TypeScript类型定义",
            " * ",
            " * 由TypeScriptTypeGenerator从Python模型生成",
            " * 不要手动修改此文件!",
            " */",
            "",
        ]
        
        # 生成枚举
        for enum_class in enums:
            enum_def = self.generate_from_enum(enum_class)
            lines.append(enum_def)
            lines.append("")
        
        # 生成接口
        for model_class in models:
            interface_def = self.generate_from_pydantic_model(model_class)
            lines.append(interface_def)
            lines.append("")
        
        return "\n".join(lines)
    
    def write_to_file(self, content: str):
        """写入文件"""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(content, encoding='utf-8')
        logger.info(f"[TypeScript] 已生成类型定义: {self.output_path}")


def generate_vis_types():
    """
    生成VIS相关的TypeScript类型
    
    从vis.parts模块生成
    """
    from derisk.vis.parts import (
        VisPart,
        PartStatus,
        PartType,
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
    
    # 输出路径
    output_path = Path(__file__).parent / "frontend" / "types.generated.ts"
    
    generator = TypeScriptTypeGenerator(str(output_path))
    
    # 枚举列表
    enums = [PartStatus, PartType]
    
    # 模型列表
    models = [
        VisPart,
        TextPart,
        CodePart,
        ToolUsePart,
        ThinkingPart,
        PlanPart,
        ImagePart,
        FilePart,
        InteractionPart,
        ErrorPart,
    ]
    
    # 生成
    content = generator.generate_full_typescript(models, enums)
    generator.write_to_file(content)
    
    return output_path


if __name__ == "__main__":
    generate_vis_types()