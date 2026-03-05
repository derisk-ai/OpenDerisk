"""
BaseBuiltinAgent - 内置Agent基类

为所有内置Agent提供通用功能：
- 工具管理（统一到ToolRegistry）
- 配置加载
- 默认行为
- 资源注入（参考core架构的ConversableAgent）
- 沙箱环境支持

工具分层：
1. 内置工具（_setup_default_tools）：bash, read, write, grep, glob, think 等
2. 交互工具（_setup_default_tools）：question, confirm, notify 等
3. 资源工具（preload_resource）：根据绑定的资源动态注入
   - AppResource -> Agent调用工具
   - RetrieverResource -> 知识检索工具
   - AgentSkillResource -> Skill工具
   - SandboxManager -> 沙箱工具
"""

from typing import AsyncIterator, Dict, Any, Optional, List, Type
from collections import defaultdict
import logging
import json
import asyncio

from ..agent_base import AgentBase, AgentInfo, AgentContext
from ..tools_v2 import (
    ToolRegistry,
    ToolResult,
    register_builtin_tools,
    register_interaction_tools,
)
from ..llm_adapter import LLMAdapter, LLMConfig, LLMFactory
from ..production_agent import ProductionAgent
from ..sandbox_docker import SandboxManager

logger = logging.getLogger(__name__)


class BaseBuiltinAgent(ProductionAgent):
    """
    内置Agent基类
    
    继承ProductionAgent，提供：
    1. 默认工具集管理（统一到ToolRegistry）
    2. 配置驱动的工具加载
    3. 原生Function Call支持
    4. 场景特定的默认行为
    5. 资源注入能力（参考core架构）
    6. 沙箱环境支持
    
    工具管理策略：
    - 所有工具统一注册到 self.tools (ToolRegistry)
    - _setup_default_tools(): 注册基础工具和交互工具
    - preload_resource(): 根据资源绑定动态注入工具
    
    子类需要实现：
    - _get_default_tools(): 返回默认工具列表
    - _build_system_prompt(): 构建系统提示词
    """
    
    def __init__(
        self,
        info: AgentInfo,
        llm_adapter: LLMAdapter,
        tool_registry: Optional[ToolRegistry] = None,
        default_tools: Optional[List[str]] = None,
        resource: Optional[Any] = None,
        resource_map: Optional[Dict[str, List[Any]]] = None,
        sandbox_manager: Optional[SandboxManager] = None,
        memory: Optional[Any] = None,
        use_persistent_memory: bool = False,
        **kwargs
    ):
        super().__init__(
            info=info,
            llm_adapter=llm_adapter,
            tool_registry=tool_registry,
            memory=memory,
            use_persistent_memory=use_persistent_memory,
            **kwargs
        )
        
        self.resource = resource
        self.resource_map = resource_map or defaultdict(list)
        self.sandbox_manager = sandbox_manager
        
        self.default_tools = default_tools or self._get_default_tools()
        self._setup_default_tools()
    
    def _get_default_tools(self) -> List[str]:
        """获取默认工具列表 - 子类实现"""
        return ["bash", "read", "write", "think"]
    
    def _setup_default_tools(self):
        """设置默认工具"""
        if len(self.tools.list_all()) == 0:
            register_builtin_tools(self.tools)
            register_interaction_tools(self.tools)
            
            logger.info(
                f"[{self.__class__.__name__}] 已注册默认工具: {len(self.tools.list_names())} 个"
            )
    
    def _build_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        构建工具定义（Function Call格式）

        Returns:
            List[Dict]: OpenAI Function Calling格式的工具定义
        """
        tools = []

        # 获取所有注册的工具名称
        all_tool_names = self.tools.list_names()

        for tool_name in all_tool_names:
            tool = self.tools.get(tool_name)
            if tool:
                tools.append(self._tool_to_function(tool))

        # 记录日志：工具数量和名称列表
        tool_names_in_defs = [t.get('function', {}).get('name', 'unknown') for t in tools]
        logger.info(f"[{self.__class__.__name__}] 构建工具定义: 数量={len(tools)}, 工具列表={tool_names_in_defs}")

        return tools
    
    def _tool_to_function(self, tool: Any) -> Dict[str, Any]:
        """
        将工具转换为Function Call格式
        
        Args:
            tool: 工具实例
            
        Returns:
            Dict: Function定义
        """
        metadata = tool.metadata
        
        return {
            "type": "function",
            "function": {
                "name": metadata.name,
                "description": metadata.description,
                "parameters": metadata.parameters
            }
        }
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词 - 子类实现"""
        return f"你是一个专业的AI助手。当前Agent: {self.info.name}"
    
    def _check_have_resource(self, resource_type: Type) -> bool:
        """
        检查是否有某种类型的资源
        
        Args:
            resource_type: 资源类型
            
        Returns:
            bool: 是否有该类型资源
        """
        for resources in self.resource_map.values():
            if not resources:
                continue
            first = resources[0]
            if isinstance(first, resource_type):
                if len(resources) == 1 and getattr(first, "is_empty", False):
                    return False
                else:
                    return True
        return False
    
    async def preload_resource(self) -> None:
        """
        预加载资源并注入工具
        
        参考core架构的ConversableAgent.preload_resource实现
        
        根据绑定的资源动态注入工具到 ToolRegistry：
        1. AppResource -> Agent调用工具
        2. RetrieverResource -> 知识检索工具  
        3. AgentSkillResource -> Skill工具
        4. SandboxManager -> 沙箱工具
        """
        await self._inject_resource_tools()
        logger.info(f"[{self.__class__.__name__}] 资源预加载完成，工具数量: {len(self.tools.list_names())}")
    
    async def _inject_resource_tools(self) -> None:
        """
        根据绑定的资源注入工具到 ToolRegistry
        """
        await self._inject_knowledge_tools()
        await self._inject_agent_tools()
        await self._inject_sandbox_tools()
    
    async def _inject_knowledge_tools(self) -> None:
        """注入知识检索工具"""
        try:
            from ...resource import RetrieverResource
            
            if self._check_have_resource(RetrieverResource):
                logger.info(f"[{self.__class__.__name__}] 检测到知识资源，注入检索工具")
                try:
                    from ...expand.actions.knowledge_action import KnowledgeSearch
                    self._register_action_as_tool(KnowledgeSearch)
                except ImportError:
                    logger.debug("KnowledgeSearch action未找到")
                    
        except ImportError:
            logger.debug("RetrieverResource模块未找到")
    
    async def _inject_agent_tools(self) -> None:
        """注入Agent调用工具"""
        try:
            from ...resource.app import AppResource
            
            if self._check_have_resource(AppResource):
                logger.info(f"[{self.__class__.__name__}] 检测到Agent资源，注入Agent调用工具")
                try:
                    from ...expand.actions.agent_action import AgentStart
                    self._register_action_as_tool(AgentStart)
                except ImportError:
                    logger.debug("AgentStart action未找到")
                    
        except ImportError:
            logger.debug("AppResource模块未找到")
    
    async def _inject_sandbox_tools(self) -> None:
        """注入沙箱工具"""
        if self.sandbox_manager:
            logger.info(f"[{self.__class__.__name__}] 检测到沙箱环境，注入沙箱工具")
            try:
                from ...core.sandbox.sandbox_tool_registry import sandbox_tool_dict
                count = 0
                for tool_name, tool in sandbox_tool_dict.items():
                    tool_adapter = self._adapt_core_function_tool(tool)
                    if tool_adapter:
                        self.tools.register(tool_adapter)
                        count += 1
                logger.info(f"[{self.__class__.__name__}] 已注入 {count} 个沙箱工具")
            except ImportError:
                logger.debug("沙箱工具注册表未找到")
    
    def _adapt_core_function_tool(self, core_tool: Any) -> Optional[Any]:
        """
        将 core 架构的 FunctionTool 适配为 core_v2 的 ToolBase
        
        Args:
            core_tool: core架构的FunctionTool实例
            
        Returns:
            ToolBase适配后的工具实例，失败返回None
        """
        try:
            from ..tools_v2 import ToolBase, ToolMetadata, ToolResult
            
            class CoreFunctionToolAdapter(ToolBase):
                """Core FunctionTool 适配器"""
                
                def __init__(self, func_tool: Any):
                    self._func_tool = func_tool
                    super().__init__()
                
                def _define_metadata(self) -> ToolMetadata:
                    return ToolMetadata(
                        name=getattr(self._func_tool, 'name', 'unknown'),
                        description=getattr(self._func_tool, 'description', '') or f"工具: {getattr(self._func_tool, 'name', 'unknown')}",
                        parameters=getattr(self._func_tool, 'args', {}) or {},
                        requires_permission=getattr(self._func_tool, 'ask_user', False),
                        dangerous=False,
                        category="sandbox",
                        version="1.0.0"
                    )
                
                async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
                    try:
                        if hasattr(self._func_tool, 'async_execute'):
                            result = await self._func_tool.async_execute(**args)
                        elif hasattr(self._func_tool, 'execute'):
                            result = self._func_tool.execute(**args)
                            if asyncio.iscoroutine(result):
                                result = await result
                        else:
                            return ToolResult(
                                success=False,
                                output="",
                                error=f"Tool {self.metadata.name} has no execute method"
                            )
                        
                        if isinstance(result, ToolResult):
                            return result
                        
                        return ToolResult(
                            success=True,
                            output=str(result) if result else "",
                            metadata={"raw_result": result}
                        )
                    except Exception as e:
                        logger.warning(f"沙箱工具执行失败 {self.metadata.name}: {e}")
                        return ToolResult(
                            success=False,
                            output="",
                            error=str(e)
                        )
            
            return CoreFunctionToolAdapter(core_tool)
            
        except Exception as e:
            logger.warning(f"适配core工具失败: {e}")
            return None
    
    def _register_action_as_tool(self, action_cls: Type) -> None:
        """
        将 Action 转换并注册为工具
        
        Args:
            action_cls: Action类
        """
        try:
            from ..tools_v2 import ActionToolAdapter
            tool = ActionToolAdapter(action_cls())
            self.tools.register(tool)
            logger.info(f"[{self.__class__.__name__}] 已注册工具: {tool.metadata.name}")
        except Exception as e:
            logger.warning(f"注册工具失败 {action_cls.__name__}: {e}")

    async def execute_tool(self, tool_name: str, tool_args: Dict[str, Any], **kwargs) -> "ToolResult":
        """
        执行工具

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            **kwargs: 其他参数

        Returns:
            ToolResult: 工具执行结果
        """
        from ..tools_v2 import ToolResult

        tool = self.tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"工具不存在: {tool_name}"
            )

        try:
            # 使用 ToolRegistry 的 execute 方法
            result = await self.tools.execute(tool_name, tool_args, kwargs)
            return result
        except Exception as e:
            logger.exception(f"[{self.__class__.__name__}] 工具执行异常: {tool_name}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )

    @classmethod
    def create(
        cls,
        name: str = "builtin-agent",
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        max_steps: int = 20,
        **kwargs
    ) -> "BaseBuiltinAgent":
        """
        便捷创建方法
        
        Args:
            name: Agent名称
            model: 模型名称
            api_key: API密钥
            max_steps: 最大步数
            **kwargs: 其他参数
            
        Returns:
            BaseBuiltinAgent: Agent实例
        """
        import os
        
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise ValueError("需要提供OpenAI API Key")
        
        info = AgentInfo(
            name=name,
            max_steps=max_steps,
            **kwargs
        )
        
        llm_config = LLMConfig(
            model=model,
            api_key=api_key
        )
        
        llm_adapter = LLMFactory.create(llm_config)
        
        return cls(info, llm_adapter, **kwargs)