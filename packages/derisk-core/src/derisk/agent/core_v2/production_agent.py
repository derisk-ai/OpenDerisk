"""
Production Agent Module - 生产环境Agent模块

提供生产环境下可直接使用的Agent实现和构建器。
"""

from typing import Optional, Dict, Any, List
from .enhanced_agent import ProductionAgent as _ProductionAgent
from .agent_info import AgentInfo, AgentMode


class AgentBuilder:
    """Agent构建器 - 提供流畅的API来构建Agent实例"""

    def __init__(self):
        self._name: str = "default_agent"
        self._description: str = ""
        self._mode: AgentMode = AgentMode.AUTO
        self._llm_client: Optional[Any] = None
        self._api_key: Optional[str] = None
        self._model: Optional[str] = None
        self._tools: List[Any] = []
        self._resources: Dict[str, Any] = {}
        self._max_iterations: int = (
            50  # Increased from 10 to support long-running tasks
        )
        self._timeout: int = 300

    def with_name(self, name: str) -> "AgentBuilder":
        """设置Agent名称"""
        self._name = name
        return self

    def with_description(self, description: str) -> "AgentBuilder":
        """设置Agent描述"""
        self._description = description
        return self

    def with_mode(self, mode: AgentMode) -> "AgentBuilder":
        """设置Agent模式"""
        self._mode = mode
        return self

    def with_llm_client(self, llm_client: Any) -> "AgentBuilder":
        """���置LLM客户端"""
        self._llm_client = llm_client
        return self

    def with_api_key(self, api_key: str) -> "AgentBuilder":
        """设置API密钥"""
        self._api_key = api_key
        return self

    def with_model(self, model: str) -> "AgentBuilder":
        """设置模型名称"""
        self._model = model
        return self

    def with_tools(self, tools: List[Any]) -> "AgentBuilder":
        """设置工具列表"""
        self._tools = tools
        return self

    def add_tool(self, tool: Any) -> "AgentBuilder":
        """添加单个工具"""
        self._tools.append(tool)
        return self

    def with_resources(self, resources: Dict[str, Any]) -> "AgentBuilder":
        """设置资源绑定"""
        self._resources = resources
        return self

    def with_max_iterations(self, max_iterations: int) -> "AgentBuilder":
        """设置最大迭代次数"""
        self._max_iterations = max_iterations
        return self

    def with_timeout(self, timeout: int) -> "AgentBuilder":
        """设置超时时间（秒）"""
        self._timeout = timeout
        return self

    def build(self) -> _ProductionAgent:
        """构建ProductionAgent实例"""
        info = AgentInfo(
            name=self._name,
            description=self._description,
            mode=self._mode,
        )

        agent = _ProductionAgent(
            info=info,
            llm_client=self._llm_client,
            api_key=self._api_key,
            model=self._model,
            tools=self._tools,
            resources=self._resources,
            max_iterations=self._max_iterations,
            timeout=self._timeout,
        )

        return agent


# Re-export ProductionAgent from enhanced_agent for backward compatibility
ProductionAgent = _ProductionAgent

__all__ = [
    "ProductionAgent",
    "AgentBuilder",
]
