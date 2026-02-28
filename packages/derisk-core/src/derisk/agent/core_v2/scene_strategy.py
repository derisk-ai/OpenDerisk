"""
SceneStrategy - 场景策略扩展体系

实现场景特定的：
1. Prompt内容模板 - 场景特定的System Prompt
2. 钩子系统 - Agent生命周期各阶段的扩展点
3. 扩展重载 - 代码级别的场景自定义

设计原则：
- 策略可组合：多个策略可以组合使用
- 扩展点明确：Agent各环节都有扩展点
- 代码可注入：支持Python代码级别的扩展
"""

from typing import Dict, Any, List, Optional, Callable, Union, Awaitable
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod
from enum import Enum
from datetime import datetime
import copy
import logging
import asyncio

logger = logging.getLogger(__name__)


class AgentPhase(str, Enum):
    """Agent执行阶段"""
    INIT = "init"
    SYSTEM_PROMPT_BUILD = "system_prompt_build"
    BEFORE_THINK = "before_think"
    THINK = "think"
    AFTER_THINK = "after_think"
    BEFORE_ACT = "before_act"
    ACT = "act"
    AFTER_ACT = "after_act"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    POST_TOOL_CALL = "post_tool_call"
    CONTEXT_BUILD = "context_build"
    MESSAGE_PROCESS = "message_process"
    OUTPUT_RENDER = "output_render"
    ERROR = "error"
    COMPLETE = "complete"


class HookPriority(int, Enum):
    """钩子优先级"""
    LOWEST = 0
    LOW = 25
    NORMAL = 50
    HIGH = 75
    HIGHEST = 100


class HookResult(BaseModel):
    """钩子执行结果"""
    proceed: bool = True
    modified_data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error: Optional[str] = None


class HookContext(BaseModel):
    """钩子上下文"""
    phase: AgentPhase
    agent: Optional[Any] = None
    scene_profile: Optional[Any] = None
    step: int = 0
    max_steps: int = 20
    
    original_input: Optional[str] = None
    current_input: Optional[str] = None
    
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[Any] = None
    
    thinking: Optional[str] = None
    action: Optional[str] = None
    output: Optional[str] = None
    
    error: Optional[Exception] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        arbitrary_types_allowed = True


class SceneHook(ABC):
    """
    场景钩子基类
    
    子类可以重写任意阶段的处理方法
    
    示例:
        class MyHook(SceneHook):
            async def on_before_think(self, ctx: HookContext) -> HookResult:
                # 在思考前注入额外上下文
                ctx.current_input = f"{ctx.current_input}\n\n注意：请仔细思考"
                return HookResult(proceed=True, modified_data={"current_input": ctx.current_input})
    """
    
    name: str = "base_hook"
    priority: HookPriority = HookPriority.NORMAL
    phases: List[AgentPhase] = []  # 留空表示监听所有阶段
    
    async def execute(self, ctx: HookContext) -> HookResult:
        """执行钩子"""
        method_map = {
            AgentPhase.INIT: self.on_init,
            AgentPhase.BEFORE_THINK: self.on_before_think,
            AgentPhase.THINK: self.on_think,
            AgentPhase.AFTER_THINK: self.on_after_think,
            AgentPhase.BEFORE_ACT: self.on_before_act,
            AgentPhase.ACT: self.on_act,
            AgentPhase.AFTER_ACT: self.on_after_act,
            AgentPhase.BEFORE_TOOL: self.on_before_tool,
            AgentPhase.AFTER_TOOL: self.on_after_tool,
            AgentPhase.CONTEXT_BUILD: self.on_context_build,
            AgentPhase.MESSAGE_PROCESS: self.on_message_process,
            AgentPhase.OUTPUT_RENDER: self.on_output_render,
            AgentPhase.ERROR: self.on_error,
            AgentPhase.COMPLETE: self.on_complete,
        }
        
        method = method_map.get(ctx.phase)
        if method:
            return await method(ctx)
        
        return await self.on_any_phase(ctx)
    
    async def on_init(self, ctx: HookContext) -> HookResult:
        """初始化阶段"""
        return HookResult(proceed=True)
    
    async def on_before_think(self, ctx: HookContext) -> HookResult:
        """思考前"""
        return HookResult(proceed=True)
    
    async def on_think(self, ctx: HookContext) -> HookResult:
        """思考阶段"""
        return HookResult(proceed=True)
    
    async def on_after_think(self, ctx: HookContext) -> HookResult:
        """思考后"""
        return HookResult(proceed=True)
    
    async def on_before_act(self, ctx: HookContext) -> HookResult:
        """行动前"""
        return HookResult(proceed=True)
    
    async def on_act(self, ctx: HookContext) -> HookResult:
        """行动阶段"""
        return HookResult(proceed=True)
    
    async def on_after_act(self, ctx: HookContext) -> HookResult:
        """行动后"""
        return HookResult(proceed=True)
    
    async def on_before_tool(self, ctx: HookContext) -> HookResult:
        """工具调用前"""
        return HookResult(proceed=True)
    
    async def on_after_tool(self, ctx: HookContext) -> HookResult:
        """工具调用后"""
        return HookResult(proceed=True)
    
    async def on_context_build(self, ctx: HookContext) -> HookResult:
        """上下文构建"""
        return HookResult(proceed=True)
    
    async def on_message_process(self, ctx: HookContext) -> HookResult:
        """消息处理"""
        return HookResult(proceed=True)
    
    async def on_output_render(self, ctx: HookContext) -> HookResult:
        """输出渲染"""
        return HookResult(proceed=True)
    
    async def on_error(self, ctx: HookContext) -> HookResult:
        """错误处理"""
        return HookResult(proceed=True)
    
    async def on_complete(self, ctx: HookContext) -> HookResult:
        """完成阶段"""
        return HookResult(proceed=True)
    
    async def on_any_phase(self, ctx: HookContext) -> HookResult:
        """任意阶段（当没有特定方法时调用）"""
        return HookResult(proceed=True)


class PromptTemplate(BaseModel):
    """
    Prompt模板
    
    支持变量替换和动态内容生成
    """
    template: str
    variables: Dict[str, Any] = Field(default_factory=dict)
    sections: Dict[str, str] = Field(default_factory=dict)
    
    def render(self, context: Optional[Dict[str, Any]] = None) -> str:
        """
        渲染Prompt模板
        
        Args:
            context: 渲染上下文
            
        Returns:
            str: 渲染后的Prompt
        """
        context = context or {}
        all_vars = {**self.variables, **context}
        
        result = self.template
        
        for key, value in all_vars.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        
        for section_name, section_content in self.sections.items():
            section_placeholder = f"[[{section_name}]]"
            if section_placeholder in result:
                rendered_section = self._render_section(section_content, all_vars)
                result = result.replace(section_placeholder, rendered_section)
        
        return result
    
    def _render_section(self, content: str, variables: Dict[str, Any]) -> str:
        """渲染段落"""
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in content:
                content = content.replace(placeholder, str(value))
        return content
    
    def with_variable(self, key: str, value: Any) -> "PromptTemplate":
        """添加变量"""
        new_template = self.copy()
        new_template.variables[key] = value
        return new_template
    
    def with_section(self, name: str, content: str) -> "PromptTemplate":
        """添加段落"""
        new_template = self.copy()
        new_template.sections[name] = content
        return new_template


class SystemPromptTemplate(BaseModel):
    """
    System Prompt模板配置
    
    场景特定的System Prompt内容
    """
    base_template: str = ""
    
    role_definition: str = ""
    capabilities: str = ""
    constraints: str = ""
    guidelines: str = ""
    examples: str = ""
    
    sections_order: List[str] = Field(default_factory=lambda: [
        "role", "capabilities", "constraints", "guidelines", "examples"
    ])
    
    def build(self, variables: Optional[Dict[str, Any]] = None) -> str:
        """
        构建完整的System Prompt
        
        Args:
            variables: 模板变量
            
        Returns:
            str: 完整的System Prompt
        """
        variables = variables or {}
        
        parts = []
        
        for section in self.sections_order:
            content = self._get_section_content(section)
            if content:
                rendered = self._render_content(content, variables)
                parts.append(rendered)
        
        if self.base_template:
            base = self._render_content(self.base_template, variables)
            main_content = "\n\n".join(parts)
            return base.replace("[[MAIN_CONTENT]]", main_content)
        
        return "\n\n".join(parts)
    
    def _get_section_content(self, section: str) -> str:
        """获取段落内容"""
        section_map = {
            "role": self.role_definition,
            "capabilities": self.capabilities,
            "constraints": self.constraints,
            "guidelines": self.guidelines,
            "examples": self.examples,
        }
        return section_map.get(section, "")
    
    def _render_content(self, content: str, variables: Dict[str, Any]) -> str:
        """渲染内容"""
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in content:
                content = content.replace(placeholder, str(value))
        return content


class ContextProcessorExtension(BaseModel):
    """上下文处理器扩展"""
    
    pre_processors: List[str] = Field(default_factory=list)
    post_processors: List[str] = Field(default_factory=list)
    
    custom_protect_patterns: List[str] = Field(default_factory=list)
    custom_importance_rules: List[Dict[str, Any]] = Field(default_factory=list)
    
    message_transformers: List[str] = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True


class ToolSelectorExtension(BaseModel):
    """工具选择器扩展"""
    
    filter_rules: List[Dict[str, Any]] = Field(default_factory=list)
    priority_adjustments: Dict[str, int] = Field(default_factory=dict)
    
    auto_suggest_tools: bool = False
    suggest_rules: List[str] = Field(default_factory=list)


class OutputRendererExtension(BaseModel):
    """输出渲染器扩展"""
    
    format_transformers: List[str] = Field(default_factory=list)
    post_processors: List[str] = Field(default_factory=list)
    
    code_block_renderer: Optional[str] = None
    markdown_renderer: Optional[str] = None


class SceneStrategy(BaseModel):
    """
    场景策略完整配置
    
    包含场景的所有可扩展部分：
    1. Prompt模板
    2. 钩子配置
    3. 各环节扩展
    """
    name: str
    description: str = ""
    
    system_prompt: Optional[SystemPromptTemplate] = None
    user_prompt_template: Optional[PromptTemplate] = None
    
    hooks: List[str] = Field(default_factory=list)
    hook_configs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    
    context_processor_extension: Optional[ContextProcessorExtension] = None
    tool_selector_extension: Optional[ToolSelectorExtension] = None
    output_renderer_extension: Optional[OutputRendererExtension] = None
    
    custom_components: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        arbitrary_types_allowed = True


class SceneStrategyRegistry:
    """
    场景策略注册中心
    
    管理场景的Prompt模板、钩子和扩展
    """
    
    _strategies: Dict[str, SceneStrategy] = {}
    _hooks: Dict[str, SceneHook] = {}
    _prompt_templates: Dict[str, SystemPromptTemplate] = {}
    
    @classmethod
    def register_strategy(cls, strategy: SceneStrategy) -> None:
        """注册场景策略"""
        cls._strategies[strategy.name] = strategy
        logger.info(f"[SceneStrategyRegistry] Registered strategy: {strategy.name}")
    
    @classmethod
    def get_strategy(cls, name: str) -> Optional[SceneStrategy]:
        """获取场景策略"""
        return cls._strategies.get(name)
    
    @classmethod
    def register_hook(cls, hook: SceneHook) -> None:
        """注册钩子"""
        cls._hooks[hook.name] = hook
        logger.info(f"[SceneStrategyRegistry] Registered hook: {hook.name}")
    
    @classmethod
    def get_hook(cls, name: str) -> Optional[SceneHook]:
        """获取钩子"""
        return cls._hooks.get(name)
    
    @classmethod
    def get_hooks_for_scene(cls, strategy_name: str) -> List[SceneHook]:
        """获取场景的所有钩子"""
        strategy = cls._strategies.get(strategy_name)
        if not strategy:
            return []
        
        hooks = []
        for hook_name in strategy.hooks:
            hook = cls._hooks.get(hook_name)
            if hook:
                hooks.append(hook)
        
        return sorted(hooks, key=lambda h: h.priority, reverse=True)
    
    @classmethod
    def register_prompt_template(cls, name: str, template: SystemPromptTemplate) -> None:
        """注册Prompt模板"""
        cls._prompt_templates[name] = template
        logger.info(f"[SceneStrategyRegistry] Registered prompt template: {name}")
    
    @classmethod
    def get_prompt_template(cls, name: str) -> Optional[SystemPromptTemplate]:
        """获取Prompt模板"""
        return cls._prompt_templates.get(name)


class SceneStrategyExecutor:
    """
    场景策略执行器
    
    负责执行场景的钩子和扩展
    """
    
    def __init__(self, strategy_name: str, agent: Any = None):
        self.strategy_name = strategy_name
        self.agent = agent
        self.strategy = SceneStrategyRegistry.get_strategy(strategy_name)
        self._hook_results: List[Dict[str, Any]] = []
    
    async def execute_phase(
        self,
        phase: AgentPhase,
        context: Optional[HookContext] = None
    ) -> HookContext:
        """
        执行指定阶段的所有钩子
        
        Args:
            phase: 执行阶段
            context: 钩子上下文
            
        Returns:
            HookContext: 更新后的上下文
        """
        if context is None:
            context = HookContext(phase=phase, agent=self.agent)
        else:
            context.phase = phase
        
        hooks = SceneStrategyRegistry.get_hooks_for_scene(self.strategy_name)
        
        for hook in hooks:
            if hook.phases and phase not in hook.phases:
                continue
            
            try:
                result = await hook.execute(context)
                
                self._hook_results.append({
                    "hook": hook.name,
                    "phase": phase.value,
                    "result": result.dict(),
                    "timestamp": datetime.now().isoformat(),
                })
                
                if not result.proceed:
                    logger.warning(
                        f"[SceneStrategyExecutor] Hook {hook.name} blocked execution at {phase}"
                    )
                    break
                
                if result.modified_data:
                    for key, value in result.modified_data.items():
                        if hasattr(context, key):
                            setattr(context, key, value)
                        else:
                            context.metadata[key] = value
                            
            except Exception as e:
                logger.error(f"[SceneStrategyExecutor] Hook {hook.name} error: {e}")
                if phase == AgentPhase.ERROR:
                    raise
        
        return context
    
    def build_system_prompt(self, variables: Optional[Dict[str, Any]] = None) -> str:
        """
        构建System Prompt
        
        Args:
            variables: 模板变量
            
        Returns:
            str: 渲染后的System Prompt
        """
        if not self.strategy or not self.strategy.system_prompt:
            return ""
        
        return self.strategy.system_prompt.build(variables)
    
    def get_hook_results(self) -> List[Dict[str, Any]]:
        """获取所有钩子执行结果"""
        return self._hook_results.copy()
    
    def clear_results(self) -> None:
        """清空执行结果"""
        self._hook_results.clear()


def scene_hook(
    name: str,
    priority: HookPriority = HookPriority.NORMAL,
    phases: Optional[List[AgentPhase]] = None
):
    """
    装饰器：快速创建场景钩子
    
    示例:
        @scene_hook("my_hook", priority=HookPriority.HIGH)
        async def my_hook_handler(ctx: HookContext) -> HookResult:
            # 处理逻辑
            return HookResult(proceed=True)
    """
    def decorator(func: Callable[[HookContext], Awaitable[HookResult]]):
        class FunctionalHook(SceneHook):
            pass
        
        hook = FunctionalHook()
        hook.name = name
        hook.priority = priority
        hook.phases = phases or []
        
        async def on_any_phase(self, ctx: HookContext) -> HookResult:
            return await func(ctx)
        
        hook.on_any_phase = lambda ctx: on_any_phase(hook, ctx)
        
        SceneStrategyRegistry.register_hook(hook)
        return func
    
    return decorator


def create_simple_hook(
    name: str,
    handler: Callable[[HookContext], Awaitable[HookResult]],
    priority: HookPriority = HookPriority.NORMAL,
    phases: Optional[List[AgentPhase]] = None
) -> SceneHook:
    """
    创建简单钩子
    
    Args:
        name: 钩子名称
        handler: 处理函数
        priority: 优先级
        phases: 监听的阶段列表
        
    Returns:
        SceneHook: 钩子实例
    """
    class SimpleHook(SceneHook):
        pass
    
    hook = SimpleHook()
    hook.name = name
    hook.priority = priority
    hook.phases = phases or []
    
    async def on_any_phase(self, ctx: HookContext) -> HookResult:
        return await handler(ctx)
    
    hook.on_any_phase = lambda ctx: on_any_phase(hook, ctx)
    
    return hook