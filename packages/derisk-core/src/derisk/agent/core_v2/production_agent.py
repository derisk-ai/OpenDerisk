"""
实现完整可运行的Agent

这是一个开箱即用的Agent实现，集成了：
- LLM调用
- 工具执行
- 记忆管理
- 目标管理
- 进度追踪
- 用户交互能力（主动提问、授权审批、方案选择、中断恢复）
"""

from typing import AsyncIterator, Dict, Any, Optional, List
import asyncio
import logging
import json

from .agent_base import AgentBase, AgentInfo, AgentContext
from .llm_adapter import LLMAdapter, LLMConfig, LLMMessage, LLMFactory
from .goal import GoalManager, Goal, GoalStatus, SuccessCriterion, CriterionType
from .interaction import InteractionManager
from .enhanced_interaction import EnhancedInteractionManager
from .tools_v2.tool_base import ToolRegistry, ToolResult
from .tools_v2.builtin_tools import register_builtin_tools
from .visualization.progress import ProgressBroadcaster

from ..interaction.interaction_gateway import get_interaction_gateway
from ..interaction.recovery_coordinator import get_recovery_coordinator
from ..interaction.interaction_protocol import NotifyLevel, TodoItem

logger = logging.getLogger(__name__)


class ProductionAgent(AgentBase):
    """
    生产可用的Agent实现
    
    特性:
    - 集成LLM调用
    - 自动工具执行
    - 思考-决策-行动循环
    - 目标追踪
    - 权限检查
    - 用户交互能力（主动提问、授权审批、方案选择）
    - 中断恢复能力
    
    示例:
        agent = ProductionAgent.create(openai_api_key="sk-xxx")
        agent.init_interaction()
        
        # 交互能力
        answer = await agent.ask_user("请提供数据库连接信息")
        plan = await agent.choose_plan([...])
        
        async for chunk in agent.run("帮我完成代码重构"):
            print(chunk, end="")
    """
    
    def __init__(
        self,
        info: AgentInfo,
        llm_adapter: LLMAdapter,
        tool_registry: Optional[ToolRegistry] = None,
        goal_manager: Optional[GoalManager] = None,
        interaction_manager: Optional[InteractionManager] = None,
        progress_broadcaster: Optional[ProgressBroadcaster] = None
    ):
        super().__init__(info)
        self.llm = llm_adapter
        self.tools = tool_registry or ToolRegistry()
        self.goals = goal_manager or GoalManager()
        self.interactions = interaction_manager or InteractionManager()
        self.progress = progress_broadcaster
        
        # 增强交互能力
        self._enhanced_interaction: Optional[EnhancedInteractionManager] = None
        self._session_id = "default_session"
        self._current_step = 0
        
        if len(self.tools.list_all()) == 0:
            register_builtin_tools(self.tools)
    
    def init_interaction(
        self,
        session_id: Optional[str] = None,
    ):
        """
        初始化交互能力
        
        Args:
            session_id: 会话ID，用于恢复和状态管理
        """
        self._session_id = session_id or f"session_{id(self)}"
        
        self._enhanced_interaction = EnhancedInteractionManager(
            session_id=self._session_id,
            agent_name=self.info.name,
            gateway=get_interaction_gateway(),
            recovery_coordinator=get_recovery_coordinator(),
        )
        
        logger.info(f"[ProductionAgent] Interaction initialized: {self._session_id}")
    
    @property
    def interaction(self) -> EnhancedInteractionManager:
        """获取增强交互管理器"""
        if self._enhanced_interaction is None:
            self.init_interaction()
        return self._enhanced_interaction
    
    # ==================== 用户交互能力 ====================
    
    async def ask_user(
        self,
        question: str,
        title: str = "需要您的输入",
        default: Optional[str] = None,
        options: Optional[List[str]] = None,
        timeout: int = 300,
    ) -> str:
        """
        主动向用户提问
        
        使用场景：
        - 缺少必要信息时请求用户提供
        - 需要澄清模糊指令
        - 需要用户指定参数
        """
        return await self.interaction.ask(
            question=question,
            title=title,
            default=default,
            options=options,
            timeout=timeout,
        )
    
    async def request_authorization(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> bool:
        """
        请求工具执行授权
        
        使用场景：
        - 危险命令执行
        - 敏感数据访问
        """
        return await self.interaction.request_authorization_smart(
            tool_name=tool_name,
            tool_args=tool_args,
            reason=reason,
        )
    
    async def choose_plan(
        self,
        plans: List[Dict[str, Any]],
        title: str = "请选择方案",
    ) -> str:
        """
        让用户选择执行方案
        
        使用场景：
        - 多种技术路线可选
        - 成本/时间权衡
        """
        return await self.interaction.choose_plan(plans=plans, title=title)
    
    async def confirm(
        self,
        message: str,
        title: str = "确认",
        default: bool = False,
    ) -> bool:
        """确认操作"""
        return await self.interaction.confirm(message=message, title=title, default=default)
    
    async def select(
        self,
        message: str,
        options: List[Dict[str, Any]],
        title: str = "请选择",
        default: Optional[str] = None,
    ) -> str:
        """让用户选择"""
        return await self.interaction.select(
            message=message,
            options=options,
            title=title,
            default=default,
        )
    
    # ==================== 通知能力 ====================
    
    async def notify(self, message: str, level: NotifyLevel = NotifyLevel.INFO, title: Optional[str] = None):
        """发送通知"""
        await self.interaction.notify(message=message, level=level, title=title)
    
    async def notify_progress(self, message: str, progress: float):
        """发送进度通知"""
        await self.interaction.notify(message=message, level=NotifyLevel.INFO, progress=progress)
    
    async def notify_success(self, message: str):
        """发送成功通知"""
        await self.interaction.notify_success(message)
    
    async def notify_error(self, message: str):
        """发送错误通知"""
        await self.interaction.notify_error(message)
    
    # ==================== Todo 管理 ====================
    
    async def create_todo(
        self,
        content: str,
        priority: int = 0,
        dependencies: Optional[List[str]] = None,
    ) -> str:
        """创建 Todo"""
        return await self.interaction.create_todo(
            content=content,
            priority=priority,
            dependencies=dependencies,
        )
    
    async def start_todo(self, todo_id: str):
        """开始执行 Todo"""
        await self.interaction.start_todo(todo_id)
    
    async def complete_todo(self, todo_id: str, result: Optional[str] = None):
        """完成 Todo"""
        await self.interaction.complete_todo(todo_id, result)
    
    async def fail_todo(self, todo_id: str, error: str):
        """Todo 失败"""
        await self.interaction.fail_todo(todo_id, error)
    
    def get_todos(self) -> List[TodoItem]:
        """获取 Todo 列表"""
        return self.interaction.get_todos()
    
    def get_next_todo(self) -> Optional[TodoItem]:
        """获取下一个 Todo"""
        return self.interaction.get_next_todo()
    
    def get_progress(self) -> tuple:
        """获取进度"""
        return self.interaction.get_progress()
    
    # ==================== 中断恢复 ====================
    
    async def create_checkpoint(self, phase: str = "executing"):
        """创建检查点"""
        recovery = get_recovery_coordinator()
        await recovery.create_checkpoint(
            session_id=self._session_id,
            execution_id=f"exec_{self._session_id}",
            step_index=self._current_step,
            phase=phase,
            context={},
            agent=self,
        )
    
    async def has_recovery_state(self) -> bool:
        """检查是否有恢复状态"""
        recovery = get_recovery_coordinator()
        return await recovery.has_recovery_state(self._session_id)
    
    async def recover(self, resume_mode: str = "continue"):
        """
        恢复执行
        
        Args:
            resume_mode: continue / skip / restart
        """
        recovery = get_recovery_coordinator()
        return await recovery.recover(
            session_id=self._session_id,
            resume_mode=resume_mode,
        )
    
    @classmethod
    def create(
        cls,
        name: str = "production-agent",
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        max_steps: int = 20,
        **kwargs
    ) -> "ProductionAgent":
        """便捷创建方法"""
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
        
        return cls(info, llm_adapter)
    
    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """思考阶段 - 分析问题"""
        thinking = f"[思考] 分析问题: {message[:100]}..."
        
        if self.progress:
            await self.progress.thinking(thinking)
        
        yield thinking
    
    async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
        """决策阶段 - 选择行动"""
        system_prompt = self._build_system_prompt()
        
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=message)
        ]
        
        tools = self.tools.get_openai_tools()
        
        try:
            response = await self.llm.generate(
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None
            )
            
            if response.tool_calls:
                tool_call = response.tool_calls[0]
                return {
                    "type": "tool_call",
                    "tool_name": tool_call["function"]["name"],
                    "tool_args": json.loads(tool_call["function"]["arguments"])
                }
            
            return {
                "type": "response",
                "content": response.content
            }
            
        except Exception as e:
            logger.error(f"[ProductionAgent] 决策失败: {e}")
            return {
                "type": "error",
                "error": str(e)
            }
    
    async def act(self, tool_name: str, tool_args: Dict[str, Any], **kwargs) -> Any:
        """行动阶段 - 执行工具"""
        if self.progress:
            await self.progress.tool_started(tool_name, tool_args)
        
        try:
            result = await self.execute_tool(tool_name, tool_args)
            
            if self.progress:
                await self.progress.tool_completed(tool_name, str(result)[:100])
            
            return result
            
        except Exception as e:
            if self.progress:
                await self.progress.tool_failed(tool_name, str(e))
            raise
    
    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> ToolResult:
        """执行工具"""
        tool = self.tools.get(tool_name)
        
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"工具不存在: {tool_name}"
            )
        
        if tool.metadata.requires_permission:
            authorized = await self.interactions.request_authorization(
                f"执行工具: {tool_name}",
                {"args": args}
            )
            
            if not authorized:
                return ToolResult(
                    success=False,
                    output="",
                    error="用户拒绝授权"
                )
        
        return await tool.execute(args)
    
    async def run(self, message: str, stream: bool = True) -> AsyncIterator[str]:
        """主运行循环"""
        self._state = "running"
        self._current_step = 0
        
        if self.progress:
            await self.progress.info(f"开始处理: {message[:100]}")
        
        while self._current_step < self.info.max_steps:
            self._current_step += 1
            
            async for chunk in self.think(message):
                yield chunk + "\n"
            
            decision = await self.decide(message)
            
            if decision.get("type") == "response":
                response = decision["content"]
                yield response
                break
            
            elif decision.get("type") == "tool_call":
                tool_name = decision["tool_name"]
                tool_args = decision.get("tool_args", {})
                
                yield f"\n[执行工具] {tool_name}\n"
                
                try:
                    result = await self.act(tool_name, tool_args)
                    
                    if result.success:
                        yield f"[结果] {str(result.output)[:500]}\n"
                        message = f"工具 {tool_name} 执行成功: {result.output}"
                    else:
                        yield f"[错误] {result.error}\n"
                        message = f"工具 {tool_name} 执行失败: {result.error}"
                        
                except Exception as e:
                    yield f"[异常] {e}\n"
                    message = f"工具执行异常: {e}"
            
            elif decision.get("type") == "error":
                yield f"\n[错误] {decision['error']}\n"
                break
        
        if self._current_step >= self.info.max_steps:
            yield f"\n[警告] 达到最大步骤限制({self.info.max_steps})"
        
        self._state = "idle"
        yield "\n[完成]"
    
    def _build_system_prompt(self) -> str:
        """构建系统Prompt"""
        tools_desc = "\n".join([
            f"- {t.metadata.name}: {t.metadata.description}"
            for t in self.tools.list_all()
        ])
        
        return f"""你是一个专业的AI Agent助手。

## 可用工具:
{tools_desc}

## 行为准则:
1. 分析问题，选择最合适的工具
2. 如果需要执行工具，使用tool_call格式
3. 如果可以直接回答，直接回复
4. 保持简洁精确

当前Agent: {self.info.name}
最大步骤: {self.info.max_steps}
"""


class AgentBuilder:
    """
    Agent构建器
    
    示例:
        agent = (
            AgentBuilder()
            .with_model("gpt-4")
            .with_api_key("sk-xxx")
            .with_tools(["bash", "read", "write"])
            .with_max_steps(30)
            .build()
        )
    """
    
    def __init__(self):
        self._name = "agent"
        self._model = "gpt-4"
        self._api_key = None
        self._max_steps = 20
        self._tools: List[str] = []
        self._system_prompt = None
        self._config: Dict[str, Any] = {}
    
    def with_name(self, name: str) -> "AgentBuilder":
        self._name = name
        return self
    
    def with_model(self, model: str) -> "AgentBuilder":
        self._model = model
        return self
    
    def with_api_key(self, api_key: str) -> "AgentBuilder":
        self._api_key = api_key
        return self
    
    def with_max_steps(self, max_steps: int) -> "AgentBuilder":
        self._max_steps = max_steps
        return self
    
    def with_tools(self, tools: List[str]) -> "AgentBuilder":
        self._tools = tools
        return self
    
    def with_system_prompt(self, prompt: str) -> "AgentBuilder":
        self._system_prompt = prompt
        return self
    
    def with_config(self, config: Dict[str, Any]) -> "AgentBuilder":
        self._config.update(config)
        return self
    
    def build(self) -> ProductionAgent:
        """构建Agent"""
        import os
        
        api_key = self._api_key or os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise ValueError("需要提供API Key")
        
        info = AgentInfo(
            name=self._name,
            max_steps=self._max_steps,
            **self._config
        )
        
        llm_config = LLMConfig(
            model=self._model,
            api_key=api_key
        )
        
        llm_adapter = LLMFactory.create(llm_config)
        
        tool_registry = ToolRegistry()
        register_builtin_tools(tool_registry)
        
        return ProductionAgent(
            info=info,
            llm_adapter=llm_adapter,
            tool_registry=tool_registry
        )