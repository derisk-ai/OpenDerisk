"""
统一的 TeamContext 定义 - 支持 Core 和 Core_v2 架构

架构说明:
=========

1. agent_version 决定使用的架构:
   - "v1": 传统 Core 架构, 从 AgentManager 获取 Agent
   - "v2": Core_v2 架构, 动态创建 Agent

2. team_mode 决定工作模式:
   - "single_agent": 单Agent模式
   - "multi_agent": 多Agent协作模式

3. agent_name 的来源:
   - v1: 从 AgentManager 获取预注册的 Agent
   - v2: 动态创建, agent_name 可以是:
     - 预定义的 V2 Agent 模板 (simple_chat, planner, etc.)
     - 数据库中其他应用的 app_code (作为子Agent)

使用示例:
=========

# V1 架构 - 单Agent
{
    "agent_version": "v1",
    "team_mode": "single_agent",
    "agent_name": "AssistantAgent",  # 从 AgentManager 获取
}

# V2 架构 - 单Agent (简单对话)
{
    "agent_version": "v2",
    "team_mode": "single_agent", 
    "agent_name": "simple_chat",  # V2 预定义模板
}

# V2 架构 - 多Agent协作
{
    "agent_version": "v2",
    "team_mode": "multi_agent",
    "agent_name": "planner",  # 主Agent
    "sub_agents": [  # 子Agent列表
        {"agent_name": "code_assistant", "role": "coder"},
        {"agent_name": "data_analyst", "role": "analyst"}
    ]
}
"""

from enum import Enum
from typing import Optional, List, Dict, Any, Union
from derisk._private.pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_to_dict,
    model_validator,
)


class AgentVersion(str, Enum):
    """Agent 架构版本"""
    V1 = "v1"  # 传统 Core 架构
    V2 = "v2"  # Core_v2 架构


class WorkMode(str, Enum):
    """工作模式"""
    SINGLE_AGENT = "single_agent"  # 单Agent模式
    MULTI_AGENT = "multi_agent"    # 多Agent协作模式


class SubAgentConfig(BaseModel):
    """子Agent配置 - 用于多Agent协作模式"""
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    agent_name: str = Field(
        ...,
        description="子Agent名称或模板名称"
    )
    role: Optional[str] = Field(
        None,
        description="子Agent在团队中的角色"
    )
    description: Optional[str] = Field(
        None,
        description="子Agent职责描述"
    )
    tools: Optional[List[str]] = Field(
        None,
        description="子Agent可用的工具列表"
    )
    resources: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="子Agent的资源配置"
    )

    def to_dict(self) -> Dict[str, Any]:
        return model_to_dict(self)


class UnifiedTeamContext(BaseModel):
    """
    统一的团队上下文 - 支持 Core 和 Core_v2 架构
    
    核心字段:
    - agent_version: 架构版本 ("v1" | "v2")
    - team_mode: 工作模式 ("single_agent" | "multi_agent")
    - agent_name: 主Agent名称
    - sub_agents: 子Agent列表 (多Agent模式时使用)
    """
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    agent_version: str = Field(
        default="v1",
        description="Agent架构版本: v1(Core) 或 v2(Core_v2)"
    )
    
    team_mode: str = Field(
        default="single_agent",
        description="工作模式: single_agent(单Agent) 或 multi_agent(多Agent协作)"
    )
    
    agent_name: str = Field(
        default="default",
        description=(
            "主Agent名称。"
            "v1架构: 从AgentManager获取的预注册Agent名称。"
            "v2架构: V2预定义模板名称(simple_chat/planner/等)或其他应用app_code"
        )
    )
    
    sub_agents: Optional[List[SubAgentConfig]] = Field(
        default=None,
        description="子Agent列表，仅在multi_agent模式下使用"
    )
    
    # ========== 以下为通用配置 ==========
    
    llm_strategy: Optional[str] = Field(
        None,
        description="LLM策略"
    )
    
    llm_strategy_value: Union[Optional[str], Optional[List[Any]]] = Field(
        None,
        description="LLM策略配置值"
    )
    
    system_prompt_template: Optional[str] = Field(
        None,
        description="系统提示词模板"
    )
    
    user_prompt_template: Optional[str] = Field(
        None,
        description="用户提示词模板"
    )
    
    prologue: Optional[str] = Field(
        None,
        description="开场白"
    )
    
    tools: Optional[List[str]] = Field(
        None,
        description="可用工具列表"
    )
    
    can_ask_user: bool = Field(
        default=True,
        description="是否可以向用户提问"
    )
    
    use_sandbox: bool = Field(
        default=False,
        description="是否使用沙箱环境"
    )
    
    ext_config: Optional[Dict[str, Any]] = Field(
        None,
        description="扩展配置"
    )
    
    def is_v2(self) -> bool:
        """是否使用 Core_v2 架构"""
        return self.agent_version == "v2"
    
    def is_multi_agent(self) -> bool:
        """是否为多Agent模式"""
        return self.team_mode == "multi_agent"
    
    def get_main_agent_name(self) -> str:
        """获取主Agent名称"""
        return self.agent_name
    
    def get_sub_agent_names(self) -> List[str]:
        """获取子Agent名称列表"""
        if not self.sub_agents:
            return []
        return [sub.agent_name for sub in self.sub_agents]
    
    def to_dict(self) -> Dict[str, Any]:
        return model_to_dict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedTeamContext":
        """从字典创建实例"""
        if "sub_agents" in data and isinstance(data["sub_agents"], list):
            data["sub_agents"] = [
                SubAgentConfig(**sub) if isinstance(sub, dict) else sub
                for sub in data["sub_agents"]
            ]
        return cls(**data)

    @classmethod
    def from_legacy_single_agent(
        cls, 
        context: Any,
        agent_version: str = "v1"
    ) -> "UnifiedTeamContext":
        """
        从旧的 SingleAgentContext 转换
        
        Args:
            context: SingleAgentContext 实例或字典
            agent_version: Agent版本
        """
        if isinstance(context, dict):
            return cls(
                agent_version=agent_version,
                team_mode="single_agent",
                agent_name=context.get("agent_name", "default"),
                llm_strategy=context.get("llm_strategy"),
                llm_strategy_value=context.get("llm_strategy_value"),
                system_prompt_template=context.get("prompt_template"),
                user_prompt_template=context.get("user_prompt_template"),
                prologue=context.get("prologue"),
                can_ask_user=context.get("can_ask_user", True),
                use_sandbox=context.get("use_sandbox", False),
            )
        
        return cls(
            agent_version=agent_version,
            team_mode="single_agent",
            agent_name=getattr(context, "agent_name", "default"),
            llm_strategy=getattr(context, "llm_strategy", None),
            llm_strategy_value=getattr(context, "llm_strategy_value", None),
            system_prompt_template=getattr(context, "prompt_template", None),
            user_prompt_template=getattr(context, "user_prompt_template", None),
            prologue=getattr(context, "prologue", None),
            can_ask_user=getattr(context, "can_ask_user", True),
            use_sandbox=getattr(context, "use_sandbox", False),
        )

    @classmethod
    def from_legacy_auto_team(
        cls, 
        context: Any,
        agent_version: str = "v1"
    ) -> "UnifiedTeamContext":
        """
        从旧的 AutoTeamContext 转换
        
        Args:
            context: AutoTeamContext 实例或字典
            agent_version: Agent版本
        """
        if isinstance(context, dict):
            teamleader = context.get("teamleader", "default")
            return cls(
                agent_version=agent_version,
                team_mode="multi_agent",
                agent_name=teamleader,
                llm_strategy=context.get("llm_strategy"),
                llm_strategy_value=context.get("llm_strategy_value"),
                system_prompt_template=context.get("prompt_template"),
                user_prompt_template=getattr(context, "user_prompt_template", None),
                prologue=context.get("prologue"),
                can_ask_user=context.get("can_ask_user", True),
                use_sandbox=context.get("use_sandbox", False),
            )
        
        return cls(
            agent_version=agent_version,
            team_mode="multi_agent",
            agent_name=getattr(context, "teamleader", "default"),
            llm_strategy=getattr(context, "llm_strategy", None),
            llm_strategy_value=getattr(context, "llm_strategy_value", None),
            system_prompt_template=getattr(context, "prompt_template", None),
            user_prompt_template=getattr(context, "user_prompt_template", None),
            prologue=getattr(context, "prologue", None),
            can_ask_user=getattr(context, "can_ask_user", True),
            use_sandbox=getattr(context, "use_sandbox", False),
        )


# ========== V2 预定义 Agent 模板 ==========

class V2AgentTemplate(str, Enum):
    """V2 架构预定义的 Agent 模板"""
    
    SIMPLE_CHAT = "simple_chat"
    PLANNER = "planner"
    CODE_ASSISTANT = "code_assistant"
    DATA_ANALYST = "data_analyst"
    RESEARCHER = "researcher"
    WRITER = "writer"
    # 新增三种内置Agent
    REACT_REASONING = "react_reasoning"
    FILE_EXPLORER = "file_explorer"
    CODING = "coding"


V2_AGENT_TEMPLATES = {
    V2AgentTemplate.SIMPLE_CHAT: {
        "name": "simple_chat",
        "display_name": "简单对话Agent",
        "description": "适用于基础对话场景，无工具调用能力",
        "mode": "primary",
        "tools": [],
    },
    V2AgentTemplate.PLANNER: {
        "name": "planner",
        "display_name": "规划执行Agent",
        "description": "适用于复杂任务，支持PDCA循环规划和工具调用",
        "mode": "planner",
        "tools": ["bash", "python", "file"],
    },
    V2AgentTemplate.CODE_ASSISTANT: {
        "name": "code_assistant",
        "display_name": "代码助手",
        "description": "专注于代码编写、审查和调试",
        "mode": "planner",
        "tools": ["bash", "python", "file", "code_search"],
    },
    V2AgentTemplate.DATA_ANALYST: {
        "name": "data_analyst",
        "display_name": "数据分析师",
        "description": "专注于数据分析和可视化",
        "mode": "planner",
        "tools": ["python", "chart", "database"],
    },
    V2AgentTemplate.RESEARCHER: {
        "name": "researcher",
        "display_name": "研究助手",
        "description": "专注于信息收集和研究分析",
        "mode": "planner",
        "tools": ["web_search", "knowledge"],
    },
    V2AgentTemplate.WRITER: {
        "name": "writer",
        "display_name": "写作助手", 
        "description": "专注于内容创作和文档编写",
        "mode": "primary",
        "tools": ["file"],
    },
    # 新增三种内置Agent模板
    V2AgentTemplate.REACT_REASONING: {
        "name": "react_reasoning",
        "display_name": "ReAct推理Agent（推荐）",
        "description": "长程任务推理Agent，支持末日循环检测、上下文压缩、输出截断、历史修剪，适用于复杂推理任务",
        "mode": "primary",
        "tools": ["bash", "read", "write", "grep", "glob", "think"],
        "capabilities": [
            "末日循环检测",
            "上下文压缩",
            "输出截断",
            "历史修剪",
            "原生FunctionCall"
        ],
        "recommended": True,
    },
    V2AgentTemplate.FILE_EXPLORER: {
        "name": "file_explorer",
        "display_name": "文件探索Agent",
        "description": "主动探索项目结构，自动识别项目类型，分析代码组织，适用于项目探索和文档生成",
        "mode": "primary",
        "tools": ["glob", "grep", "read", "bash", "think"],
        "capabilities": [
            "主动探索机制",
            "项目类型识别",
            "结构分析",
            "文档生成"
        ],
    },
    V2AgentTemplate.CODING: {
        "name": "coding",
        "display_name": "编程开发Agent",
        "description": "自主代码开发Agent，支持代码库探索、智能定位、质量检查，适用于功能开发和代码重构",
        "mode": "primary",
        "tools": ["read", "write", "bash", "grep", "glob", "think"],
        "capabilities": [
            "自主探索代码库",
            "智能代码定位",
            "功能开发",
            "代码质量检查"
        ],
    },
}


def get_v2_agent_templates() -> List[Dict[str, Any]]:
    """获取所有 V2 Agent 模板列表"""
    return [
        {
            "name": info["name"],
            "display_name": info["display_name"],
            "description": info["description"],
            "mode": info["mode"],
            "tools": info["tools"],
        }
        for info in V2_AGENT_TEMPLATES.values()
    ]


def get_v2_agent_template(name: str) -> Optional[Dict[str, Any]]:
    """获取指定的 V2 Agent 模板"""
    return V2_AGENT_TEMPLATES.get(V2AgentTemplate(name))