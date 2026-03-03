"""
AgentBase - Agent基类实现

参考OpenCode和OpenClaw的Agent设计
简化接口,配置驱动,集成Permission系统
支持子Agent委派 (Subagent Delegation)
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, Optional, List, TYPE_CHECKING
from pydantic import BaseModel, Field
from enum import Enum
import asyncio
from datetime import datetime

from .agent_info import AgentInfo, PermissionAction
from .permission import PermissionChecker, PermissionResponse, PermissionDeniedError
from .memory_factory import create_agent_memory
from .unified_memory.base import UnifiedMemoryInterface, MemoryType

# Import GptsMemory for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
    from .project_memory import ProjectMemoryManager
    from .context_isolation import SubagentContextConfig

if TYPE_CHECKING:
    from .subagent_manager import SubagentManager, SubagentResult


class AgentState(str, Enum):
    """Agent状态枚举"""

    IDLE = "idle"  # 空闲状态
    THINKING = "thinking"  # 思考中
    ACTING = "acting"  # 执行动作中
    WAITING_INPUT = "waiting_input"  # 等待用户输入
    ERROR = "error"  # 错误状态
    TERMINATED = "terminated"  # 已终止


class AgentContext(BaseModel):
    """Agent运行时上下文"""

    session_id: str  # 会话ID
    conversation_id: Optional[str] = None  # 对话ID
    user_id: Optional[str] = None  # 用户ID
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 元数据

    # 工具相关
    available_tools: List[str] = Field(default_factory=list)  # 可用工具列表
    tool_context: Dict[str, Any] = Field(default_factory=dict)  # 工具上下文

    # 执行统计
    total_tokens: int = 0  # 总token数
    total_steps: int = 0  # 总步骤数
    start_time: Optional[datetime] = None  # 开始时间

    class Config:
        arbitrary_types_allowed = True


class AgentMessage(BaseModel):
    """Agent消息"""

    role: str  # 角色: user/assistant/system
    content: str  # 内容
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 元数据
    timestamp: datetime = Field(default_factory=datetime.now)  # 时间戳

    class Config:
        arbitrary_types_allowed = True


class AgentExecutionResult(BaseModel):
    """Agent执行结果"""

    success: bool  # 是否成功
    response: Optional[str] = None  # 响应内容
    error: Optional[str] = None  # 错误信息
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 元数据

    # 统计信息
    tokens_used: int = 0  # 使用的token数
    steps_taken: int = 0  # 执行的步骤数
    execution_time: float = 0.0  # 执行时间(秒)


class AgentBase(ABC):
    """
    Agent基类 - 简化接口,配置驱动

    设计原则:
    1. 配置驱动 - 通过AgentInfo配置,而非复杂的继承
    2. 权限集成 - 内置Permission系统
    3. 流式输出 - 支持流式响应
    4. 状态管理 - 明确的状态机
    5. 异步优先 - 全异步设计

    示例:
        class MyAgent(AgentBase):
            async def think(self, message: str) -> AsyncIterator[str]:
                # 实现思考逻辑
                yield "思考中..."

            async def act(self, tool_name: str, args: Dict) -> Any:
                # 实现动作执行
                return await self.execute_tool(tool_name, args)
    """

    def __init__(
        self,
        info: AgentInfo,
        memory: Optional[UnifiedMemoryInterface] = None,
        use_persistent_memory: bool = False,
        gpts_memory: Optional["GptsMemory"] = None,
        conv_id: Optional[str] = None,
        # 新增参数 - 项目记忆和上下文隔离
        project_memory: Optional["ProjectMemoryManager"] = None,
        context_isolation_config: Optional["SubagentContextConfig"] = None,
    ):
        """
        初始化 Agent

        Args:
            info: Agent 配置信息
            memory: 统一记忆接口实例 (可选，如果提供则优先使用)
            use_persistent_memory: 是否使用持久化记忆
            gpts_memory: GptsMemory 实例 (Core V1 的记忆管理器，用于统一后端)
            conv_id: 会话 ID (用于 GptsMemory 后端)
            project_memory: 项目记忆管理器 (用于 CLAUDE.md 风格的多层级记忆)
            context_isolation_config: 子代理上下文隔离配置
        """
        self.info = info
        self._state = AgentState.IDLE
        self._context: Optional[AgentContext] = None
        self._messages: List[AgentMessage] = []
        self._permission_checker = PermissionChecker(info.permission)
        self._current_step = 0
        self._subagent_manager: Optional["SubagentManager"] = None
        self._session_id: Optional[str] = None

        # 存储 GptsMemory 引用以便后续使用
        self._gpts_memory = gpts_memory
        self._conv_id = conv_id

        # 项目记忆管理器 (CLAUDE.md 风格)
        self._project_memory = project_memory
        self._isolation_config = context_isolation_config

        # 初始化统一记忆
        if memory is not None:
            # 使用传入的 memory 实例
            self._memory = memory
        elif gpts_memory is not None:
            # 使用 GptsMemory 后端创建适配器
            from .memory_factory import MemoryFactory
            self._memory = MemoryFactory.create_with_gpts(
                gpts_memory=gpts_memory,
                conv_id=conv_id or self._session_id or "",
                session_id=self._session_id,
            )
        else:
            # 延迟创建，等待 session_id 设置
            self._memory = None

        self._use_persistent_memory = use_persistent_memory
        self._memory_initialized = False

    @property
    def state(self) -> AgentState:
        """获取当前状态"""
        return self._state

    @property
    def context(self) -> Optional[AgentContext]:
        """获取上下文"""
        return self._context

    @property
    def messages(self) -> List[AgentMessage]:
        """获取消息历史"""
        return self._messages.copy()
    
    @property
    def memory(self) -> UnifiedMemoryInterface:
        """获取统一记忆管理器"""
        if self._memory is None:
            # 如果设置了 GptsMemory，使用适配器
            if self._gpts_memory is not None:
                from .memory_factory import MemoryFactory
                self._memory = MemoryFactory.create_with_gpts(
                    gpts_memory=self._gpts_memory,
                    conv_id=self._conv_id or self._session_id or "",
                    session_id=self._session_id,
                )
            else:
                # 否则创建新的记忆管理器
                self._memory = create_agent_memory(
                    agent_name=self.info.name,
                    session_id=self._session_id,
                    use_persistent=self._use_persistent_memory,
                )
        return self._memory

    @property
    def project_memory(self) -> Optional["ProjectMemoryManager"]:
        """获取项目记忆管理器"""
        return self._project_memory

    @property
    def isolation_config(self) -> Optional["SubagentContextConfig"]:
        """获取上下文隔离配置"""
        return self._isolation_config

    async def build_system_prompt(self) -> str:
        """
        构建 System Prompt（包含项目记忆）

        将 agent 的基础 system prompt 与项目记忆上下文合并，
        参考 Claude Code 的 CLAUDE.md 机制。

        Returns:
            完整的 system prompt 字符串
        """
        base_prompt = self.info.system_prompt or ""

        # 如果有项目记忆，添加项目上下文
        if self._project_memory:
            try:
                memory_context = await self._project_memory.build_context(
                    agent_name=self.info.name,
                    session_id=self._session_id,
                )

                if memory_context:
                    return f"{base_prompt}\n\n# Project Context\n\n{memory_context}"
            except Exception as e:
                # 如果获取项目记忆失败，只返回基础 prompt
                import logging
                logging.getLogger(__name__).warning(f"Failed to build project memory context: {e}")

        return base_prompt

    def set_project_memory(
        self,
        project_memory: "ProjectMemoryManager",
    ) -> "AgentBase":
        """
        设置项目记忆管理器

        Args:
            project_memory: ProjectMemoryManager 实例

        Returns:
            self: 支持链式调用
        """
        self._project_memory = project_memory
        return self

    def set_context_isolation_config(
        self,
        config: "SubagentContextConfig",
    ) -> "AgentBase":
        """
        设置上下文隔离配置

        Args:
            config: SubagentContextConfig 实例

        Returns:
            self: 支持链式调用
        """
        self._isolation_config = config
        return self

    def set_state(self, state: AgentState):
        """设置状态"""
        self._state = state

    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        """添加消息到历史"""
        self._messages.append(
            AgentMessage(role=role, content=content, metadata=metadata or {})
        )
    
    async def save_memory(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.WORKING,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        保存记忆到统一记忆管理器
        
        Args:
            content: 记忆内容
            memory_type: 记忆类型
            metadata: 元数据
            
        Returns:
            记忆ID
        """
        return await self.memory.write(
            content=content,
            memory_type=memory_type,
            metadata=metadata,
        )
    
    async def load_memory(
        self,
        query: str = "",
        memory_types: Optional[List[MemoryType]] = None,
        top_k: int = 10,
    ) -> List[AgentMessage]:
        """
        从统一记忆管理器加载记忆
        
        Args:
            query: 查询字符串
            memory_types: 记忆类型列表
            top_k: 返回数量
            
        Returns:
            消息列表
        """
        from .unified_memory.base import SearchOptions
        
        options = SearchOptions(
            top_k=top_k,
            memory_types=memory_types,
        )
        
        items = await self.memory.read(query, options)
        
        messages = []
        for item in items:
            messages.append(AgentMessage(
                role="assistant",
                content=item.content,
                metadata={
                    "memory_id": item.id,
                    "memory_type": item.memory_type.value,
                    "importance": item.importance,
                    "created_at": item.created_at.isoformat(),
                    **item.metadata,
                },
            ))
        
        return messages
    
    async def get_conversation_history(self, max_messages: int = 50) -> List[AgentMessage]:
        """
        获取对话历史（包含持久化记忆）
        
        Args:
            max_messages: 最大消息数
            
        Returns:
            对话历史
        """
        messages = list(self._messages)
        
        memory_messages = await self.load_memory(
            query="",
            memory_types=[MemoryType.WORKING, MemoryType.EPISODIC],
            top_k=max_messages - len(messages),
        )
        
        messages.extend(memory_messages)
        
        messages.sort(key=lambda m: m.metadata.get("created_at", ""))
        
        return messages[:max_messages]

    async def initialize(self, context: AgentContext):
        """
        初始化Agent

        Args:
            context: 运行时上下文
        """
        self._context = context
        self._context.start_time = datetime.now()
        self._current_step = 0
        self.set_state(AgentState.IDLE)
        
        if not self._memory_initialized:
            if hasattr(self.memory, 'initialize'):
                await self.memory.initialize()
            self._memory_initialized = True

    # ========== 核心抽象方法 ==========

    @abstractmethod
    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """
        思考阶段 - 生成思考过程

        Args:
            message: 输入消息
            **kwargs: 额外参数

        Yields:
            str: 思考过程的文本片段
        """
        pass

    @abstractmethod
    async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
        """
        决策阶段 - 决定下一步动作

        Args:
            message: 输入消息
            **kwargs: 额外参数

        Returns:
            Dict: 决策结果,包含:
                - type: "response" | "tool_call" | "subagent" | "terminate"
                - content: 响应内容(如果type=response)
                - tool_name: 工具名称(如果type=tool_call)
                - tool_args: 工具参数(如果type=tool_call)
                - subagent: 子Agent名称(如果type=subagent)
                - task: 任务内容(如果type=subagent)
        """
        pass

    @abstractmethod
    async def act(self, tool_name: str, tool_args: Dict[str, Any], **kwargs) -> Any:
        """
        执行动作阶段

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            **kwargs: 额外参数

        Returns:
            Any: 执行结果
        """
        pass

    # ========== 权限相关 ==========

    async def check_permission(
        self, tool_name: str, tool_args: Dict[str, Any] = None, ask_user: bool = True
    ) -> PermissionResponse:
        """
        检查工具执行权限

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            ask_user: 是否询问用户(对于ASK权限)

        Returns:
            PermissionResponse: 权限响应
        """
        return await self._permission_checker.check_async(
            tool_name,
            tool_args,
            self._context.dict() if self._context else {},
            reason=f"Agent '{self.info.name}' 请求执行工具 '{tool_name}'",
        )

    def can_execute(self, tool_name: str) -> bool:
        """
        同步检查是否可以执行工具(不询问用户)

        Args:
            tool_name: 工具名称

        Returns:
            bool: 是否有权限
        """
        action = self.info.permission.check(tool_name)
        return action == PermissionAction.ALLOW

    # ========== 工具执行 ==========

    async def execute_tool(
        self, tool_name: str, tool_args: Dict[str, Any], **kwargs
    ) -> Any:
        """
        执行工具(带权限检查)

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            **kwargs: 额外参数

        Returns:
            Any: 工具执行结果

        Raises:
            PermissionDeniedError: 权限被拒绝
        """
        # 1. 检查权限
        permission_response = await self.check_permission(tool_name, tool_args)

        if not permission_response.granted:
            raise PermissionDeniedError(permission_response.reason, tool_name)

        # 2. 检查是否超过步数限制
        if self._current_step >= self.info.max_steps:
            raise RuntimeError(f"超过最大步数限制({self.info.max_steps})")

        # 3. 执行工具
        self.set_state(AgentState.ACTING)
        self._current_step += 1

        try:
            result = await self.act(tool_name, tool_args, **kwargs)
            self.set_state(AgentState.IDLE)
            return result
        except Exception as e:
            self.set_state(AgentState.ERROR)
            raise

    def set_subagent_manager(self, manager: "SubagentManager") -> "AgentBase":
        """
        设置子Agent管理器
        
        Args:
            manager: SubagentManager实例
            
        Returns:
            self: 支持链式调用
        """
        self._subagent_manager = manager
        return self
    
    def set_session_id(self, session_id: str) -> "AgentBase":
        """
        设置会话ID

        Args:
            session_id: 会话ID

        Returns:
            self: 支持链式调用
        """
        self._session_id = session_id

        # 如果使用 GptsMemory 且没有 conv_id，使用 session_id 作为 conv_id
        if self._gpts_memory is not None and not self._conv_id:
            self._conv_id = session_id

        return self

    def set_gpts_memory(
        self,
        gpts_memory: "GptsMemory",
        conv_id: Optional[str] = None,
    ) -> "AgentBase":
        """
        设置 GptsMemory 后端

        Args:
            gpts_memory: GptsMemory 实例
            conv_id: 会话 ID

        Returns:
            self: 支持链式调用
        """
        self._gpts_memory = gpts_memory
        self._conv_id = conv_id or self._session_id

        # 重新创建记忆适配器
        if self._gpts_memory is not None:
            from .memory_factory import MemoryFactory
            self._memory = MemoryFactory.create_with_gpts(
                gpts_memory=self._gpts_memory,
                conv_id=self._conv_id or "",
                session_id=self._session_id,
            )
            self._memory_initialized = False

        return self
    
    async def delegate_to_subagent(
        self,
        subagent_name: str,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> "SubagentResult":
        """
        委派任务给子Agent
        
        这是子Agent调用的核心方法，参考 OpenCode 的 Task 工具设计。
        
        Args:
            subagent_name: 子Agent名称
            task: 任务内容
            context: 额外上下文
            timeout: 超时时间(秒)
            
        Returns:
            SubagentResult: 执行结果
            
        Raises:
            RuntimeError: 如果未配置SubagentManager
        """
        if not self._subagent_manager:
            raise RuntimeError(
                "SubagentManager 未配置。请调用 set_subagent_manager() 进行配置。"
            )
        
        session_id = self._session_id or "default"
        
        result = await self._subagent_manager.delegate(
            subagent_name=subagent_name,
            task=task,
            parent_session_id=session_id,
            context=context,
            timeout=timeout,
            sync=True,
        )
        
        return result
    
    def get_available_subagents(self) -> List[str]:
        """
        获取可用的子Agent列表
        
        Returns:
            List[str]: 子Agent名称列表
        """
        if not self._subagent_manager:
            return []
        
        return [a.name for a in self._subagent_manager.get_available_subagents()]

    # ========== 主执行循环 ==========

    async def run(
        self, message: str, stream: bool = True, **kwargs
    ) -> AsyncIterator[str]:
        """
        执行主循环

        Args:
            message: 用户消息
            stream: 是否流式输出
            **kwargs: 额外参数

        Yields:
            str: 响应片段
        """
        self.add_message("user", message)
        
        await self.save_memory(
            content=f"User: {message}",
            memory_type=MemoryType.WORKING,
            metadata={"role": "user"},
        )

        self._current_step = 0

        while self._current_step < self.info.max_steps:
            try:
                self.set_state(AgentState.THINKING)

                if stream:
                    async for chunk in self.think(message, **kwargs):
                        yield f"[THINKING] {chunk}"

                decision = await self.decide(message, **kwargs)

                decision_type = decision.get("type")

                if decision_type == "response":
                    content = decision.get("content", "")
                    self.add_message("assistant", content)
                    
                    await self.save_memory(
                        content=f"Assistant: {content}",
                        memory_type=MemoryType.WORKING,
                        metadata={"role": "assistant"},
                    )
                    
                    yield content
                    break

                elif decision_type == "tool_call":
                    tool_name = decision.get("tool_name")
                    tool_args = decision.get("tool_args", {})

                    try:
                        result = await self.execute_tool(tool_name, tool_args)
                        message = self._format_tool_result(tool_name, result)
                    except PermissionDeniedError as e:
                        message = f"工具执行被拒绝: {e.message}"
                        yield f"[ERROR] {message}"

                elif decision_type == "subagent":
                    subagent = decision.get("subagent")
                    task = decision.get("task")
                    
                    try:
                        result = await self.delegate_to_subagent(
                            subagent_name=subagent,
                            task=task,
                        )
                        message = result.to_llm_message()
                        self.add_message("assistant", f"[子Agent {subagent}] {result.output}")
                    except Exception as e:
                        message = f"子Agent执行失败: {str(e)}"
                        yield f"[ERROR] {message}"

                elif decision_type == "terminate":
                    yield "[TERMINATE] 执行已完成"
                    break

                else:
                    yield f"[ERROR] 未知的决策类型: {decision_type}"
                    break

            except Exception as e:
                self.set_state(AgentState.ERROR)
                yield f"[ERROR] 执行出错: {str(e)}"
                break

        if self._current_step >= self.info.max_steps:
            yield f"[WARNING] 达到最大步数限制({self.info.max_steps})"

    def _format_tool_result(self, tool_name: str, result: Any) -> str:
        """格式化工具结果"""
        if isinstance(result, str):
            return f"工具 {tool_name} 执行结果:\n{result}"
        else:
            return f"工具 {tool_name} 执行结果: {result}"

    # ========== 辅助方法 ==========

    def get_statistics(self) -> Dict[str, Any]:
        """获取执行统计"""
        execution_time = 0.0
        if self._context and self._context.start_time:
            execution_time = (datetime.now() - self._context.start_time).total_seconds()

        return {
            "agent_name": self.info.name,
            "state": self.state.value,
            "current_step": self._current_step,
            "max_steps": self.info.max_steps,
            "messages_count": len(self._messages),
            "execution_time": execution_time,
        }

    async def reset(self):
        """重置Agent状态"""
        self._state = AgentState.IDLE
        self._messages.clear()
        self._current_step = 0
        if self._context:
            self._context.total_tokens = 0
            self._context.total_steps = 0
            self._context.start_time = None


class SimpleAgent(AgentBase):
    """
    简单Agent实现 - 用于测试和演示

    示例:
        agent = SimpleAgent(AgentInfo(name="simple"))
        async for chunk in agent.run("你好"):
            print(chunk)
    """

    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """思考阶段"""
        yield f"正在思考: {message[:50]}..."

    async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
        """决策阶段"""
        # 简单实现: 所有消息都直接返回
        return {"type": "response", "content": f"收到消息: {message}"}

    async def act(self, tool_name: str, tool_args: Dict[str, Any], **kwargs) -> Any:
        """执行动作"""
        return f"执行了工具 {tool_name}"
