from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RunModel(str, Enum):
    """运行模式常量定义"""
    
    NORMAL: str = "normal"
    SNAPSHOT: str = "snapshot"


class ToolRunConfig(BaseModel):
    """工具运行配置"""
    
    tool_name: Optional[str] = Field(
        default=None,
        alias="toolName"
    )
    
    run_model: str = Field(
        default=RunModel.NORMAL,
        alias="runMode"
    )


class ToolRunModel(BaseModel):
    """工具运行配置模型"""
    
    tool_run_configs: Optional[List[ToolRunConfig]] = Field(
        default=None,
        alias="toolRunConfigs"
    )
    
    default_mode: str = Field(
        default=RunModel.NORMAL,
        alias="defaultMode"
    )

if __name__ == "__main__":
    # 测试从 JSON 字符串解析
    # java_style_json = '{"toolRunConfigs":[{"toolId":"test_tool","runModel":"normal"}],"defaultMode":"normal"}'
    java_style_json = '{"defaultMode":"normal"}'
    import json
    
    # 方法1: 使用 json.loads + 构造对象
    data = json.loads(java_style_json)
    config = ToolRunModel(**data)
    print("解析结果:", config)
