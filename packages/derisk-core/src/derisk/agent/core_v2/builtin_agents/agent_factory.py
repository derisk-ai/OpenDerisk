"""
Agent工厂 - 创建和管理Agent实例

支持：
1. 从代码创建Agent
2. 从配置文件创建Agent
3. 工具自动加载
"""

from typing import Dict, Any, Optional, Type
import logging
import os
import yaml
import json

from .react_reasoning_agent import ReActReasoningAgent
from .file_explorer_agent import FileExplorerAgent
from .coding_agent import CodingAgent
from ..agent_info import AgentInfo
from ..llm_adapter import LLMConfig, LLMFactory

logger = logging.getLogger(__name__)


class AgentFactory:
    """
    Agent工厂类
    
    支持创建三种内置Agent：
    - ReActReasoningAgent
    - FileExplorerAgent
    - CodingAgent
    """
    
    AGENT_TYPES = {
        "react_reasoning": ReActReasoningAgent,
        "file_explorer": FileExplorerAgent,
        "coding": CodingAgent,
    }
    
    @classmethod
    def create(
        cls,
        agent_type: str,
        name: Optional[str] = None,
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        **kwargs
    ):
        """
        创建Agent实例
        
        Args:
            agent_type: Agent类型
            name: Agent名称
            model: 模型名称
            api_key: API密钥
            **kwargs: 其他参数
            
        Returns:
            Agent实例
        """
        if agent_type not in cls.AGENT_TYPES:
            raise ValueError(
                f"未知的Agent类型: {agent_type}. "
                f"可用类型: {list(cls.AGENT_TYPES.keys())}"
            )
        
        agent_class = cls.AGENT_TYPES[agent_type]
        name = name or f"{agent_type}-agent"
        
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("需要提供OpenAI API Key")
        
        info = AgentInfo(name=name, **kwargs)
        
        llm_config = LLMConfig(model=model, api_key=api_key)
        llm_adapter = LLMFactory.create(llm_config)
        
        return agent_class(info=info, llm_adapter=llm_adapter, **kwargs)
    
    @classmethod
    def create_from_config(cls, config_path: str):
        """
        从配置文件创建Agent
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            Agent实例
        """
        config = cls._load_config(config_path)
        
        return cls.create(
            agent_type=config.get("type"),
            name=config.get("name"),
            model=config.get("model", "gpt-4"),
            api_key=config.get("api_key"),
            **config.get("options", {})
        )
    
    @classmethod
    def _load_config(cls, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            if config_path.endswith(".yaml") or config_path.endswith(".yml"):
                return yaml.safe_load(f)
            elif config_path.endswith(".json"):
                return json.load(f)
            else:
                raise ValueError(f"不支持的配置格式: {config_path}")


def create_agent(
    agent_type: str,
    name: Optional[str] = None,
    model: str = "gpt-4",
    api_key: Optional[str] = None,
    **kwargs
):
    """
    便捷函数：创建Agent
    
    Args:
        agent_type: Agent类型 (react_reasoning/file_explorer/coding)
        name: Agent名称
        model: 模型名称
        api_key: API密钥
        **kwargs: 其他参数
        
    Returns:
        Agent实例
        
    Example:
        agent = create_agent("react_reasoning", name="my-agent")
    """
    return AgentFactory.create(
        agent_type=agent_type,
        name=name,
        model=model,
        api_key=api_key,
        **kwargs
    )


def create_agent_from_config(config_path: str):
    """
    便捷函数：从配置文件创建Agent
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        Agent实例
        
    Example:
        agent = create_agent_from_config("config.yaml")
    """
    return AgentFactory.create_from_config(config_path)