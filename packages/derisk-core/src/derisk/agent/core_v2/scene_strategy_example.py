"""
Custom Scene Strategy Extension Example - 自定义场景策略扩展示例

展示如何通过代码扩展创建自定义场景：
1. 自定义Prompt模板
2. 自定义钩子处理器
3. 组合使用现有钩子
4. 新增扩展组件
"""

from typing import Dict, Any, List
import asyncio

from derisk.agent.core_v2.scene_strategy import (
    SceneHook,
    HookContext,
    HookResult,
    HookPriority,
    AgentPhase,
    SystemPromptTemplate,
    SceneStrategy,
    ContextProcessorExtension,
    ToolSelectorExtension,
    OutputRendererExtension,
    SceneStrategyRegistry,
    SceneStrategyExecutor,
    scene_hook,
)
from derisk.agent.core_v2.scene_strategies_builtin import (
    CodeBlockProtectionHook,
    ErrorRecoveryHook,
)


MY_CUSTOM_PROMPT = SystemPromptTemplate(
    base_template="""You are {{agent_name}}, a specialized AI assistant for {{domain}} tasks.

[[MAIN_CONTENT]]

Always prioritize {{priority_value}} in your responses.""",
    
    role_definition="""## Your Specialized Role

You are an expert in {{domain}} with deep knowledge in:
- {{feature_1}}
- {{feature_2}}
- {{feature_3}}

Your expertise helps users accomplish tasks efficiently and correctly.""",
    
    capabilities="""## Your Capabilities

1. **Primary Skills**: {{primary_skills}}
2. **Secondary Skills**: {{secondary_skills}}
3. **Tools Available**: {{tools_available}}

Use these capabilities to provide comprehensive assistance.""",
    
    constraints="""## Operating Constraints

- Always verify critical information
- Follow domain best practices
- Be explicit about assumptions
- Provide citations when appropriate
- Handle edge cases gracefully""",
    
    guidelines="""## Response Guidelines

1. Start with a brief summary when appropriate
2. Provide step-by-step explanations
3. Include examples for complex concepts
4. End with actionable recommendations
5. Ask clarifying questions when needed""",
    
    sections_order=["role", "capabilities", "constraints", "guidelines"]
)


class CustomPreProcessorHook(SceneHook):
    """
    自定义预处理钩子示例
    
    在Agent思考前进行预处理
    """
    name = "custom_pre_processor"
    priority = HookPriority.HIGH
    phases = [AgentPhase.BEFORE_THINK]
    
    async def on_before_think(self, ctx: HookContext) -> HookResult:
        """在思考前注入自定义上下文"""
        custom_context = ctx.metadata.get("custom_context", {})
        
        if custom_context.get("task_type"):
            task_type = custom_context["task_type"]
            injection = f"\n\n<Task Type: {task_type}>\nPlease approach this task appropriately."
            
            if ctx.current_input:
                ctx.current_input += injection
        
        return HookResult(
            proceed=True,
            modified_data={"current_input": ctx.current_input}
        )


class CustomPostProcessorHook(SceneHook):
    """
    自定义后处理钩子示例
    
    在输出前进行后处理
    """
    name = "custom_post_processor"
    priority = HookPriority.LOW
    phases = [AgentPhase.OUTPUT_RENDER]
    
    async def on_output_render(self, ctx: HookContext) -> HookResult:
        """处理最终输出"""
        if ctx.output:
            custom_context = ctx.metadata.get("custom_context", {})
            
            if custom_context.get("add_signature"):
                ctx.output += f"\n\n---\nProcessed by: {custom_context.get('signature', 'Custom Agent')}"
            
            if custom_context.get("quality_check"):
                quality_score = self._calculate_quality_score(ctx.output)
                ctx.metadata["quality_score"] = quality_score
        
        return HookResult(proceed=True)
    
    def _calculate_quality_score(self, text: str) -> float:
        """简单的质量评分"""
        score = 0.5
        
        if len(text) > 100:
            score += 0.1
        if "```" in text:
            score += 0.1
        if any(word in text.lower() for word in ["example", "示例", "step"]):
            score += 0.1
        if "error" not in text.lower():
            score += 0.1
        
        return min(1.0, score)


class CustomToolFilterHook(SceneHook):
    """
    自定义工具过滤钩子
    
    根据任务类型自动过滤可用工具
    """
    name = "custom_tool_filter"
    priority = HookPriority.NORMAL
    phases = [AgentPhase.BEFORE_ACT]
    
    def __init__(self, filter_rules: Dict[str, List[str]] = None):
        self.filter_rules = filter_rules or {
            "read_only": ["read", "grep", "glob", "webfetch"],
            "write_only": ["write", "edit"],
            "safe": ["read", "grep", "glob", "write", "edit"],
        }
    
    async def on_before_act(self, ctx: HookContext) -> HookResult:
        """根据上下文过滤工具"""
        custom_context = ctx.metadata.get("custom_context", {})
        mode = custom_context.get("tool_mode", "safe")
        
        if mode in self.filter_rules:
            allowed_tools = self.filter_rules[mode]
            filtered_tools = [
                t for t in ctx.tools
                if t.get("name") in allowed_tools or t.get("function", {}).get("name") in allowed_tools
            ]
            
            if filtered_tools:
                ctx.metadata["filtered_tools"] = filtered_tools
                ctx.metadata["filter_mode"] = mode
        
        return HookResult(proceed=True)


@scene_hook("decorator_hook_example", priority=HookPriority.NORMAL)
async def simple_decorator_hook(ctx: HookContext) -> HookResult:
    """
    使用装饰器创建简单钩子示例
    
    这个钩子会在所有阶段执行
    """
    ctx.metadata["decorator_hook_called"] = True
    return HookResult(proceed=True)


def create_custom_strategy(
    name: str,
    domain: str,
    features: List[str],
    base_strategy: str = "general"
) -> SceneStrategy:
    """
    工厂函数：创建自定义场景策略
    
    Args:
        name: 策略名称
        domain: 领域
        features: 特性列表
        base_strategy: 基础策略名称
        
    Returns:
        SceneStrategy: 完整的场景策略
    """
    prompt = SystemPromptTemplate(
        base_template=f"You are an expert assistant specialized in {domain}.\n\n[[MAIN_CONTENT]]",
        role_definition=f"## {domain} Expert\n\nYou have deep expertise in:\n" + 
                       "\n".join(f"- {f}" for f in features),
        capabilities="## Capabilities\n\nAvailable tools and resources for " + domain,
        constraints="## Constraints\n\nFollow best practices in " + domain,
        guidelines="## Guidelines\n\nBe thorough and accurate",
        sections_order=["role", "capabilities", "constraints", "guidelines"]
    )
    
    hooks = []
    base = SceneStrategyRegistry.get_strategy(base_strategy)
    if base:
        hooks.extend(base.hooks)
    
    hooks.extend(["custom_pre_processor", "custom_post_processor"])
    
    return SceneStrategy(
        name=name,
        description=f"Custom strategy for {domain}",
        system_prompt=prompt,
        hooks=hooks,
        context_processor_extension=ContextProcessorExtension(
            custom_importance_rules=[
                {"pattern": "domain_keyword", "importance": 0.9},
            ]
        )
    )


def register_custom_hooks():
    """注册自定义钩子"""
    SceneStrategyRegistry.register_hook(CustomPreProcessorHook())
    SceneStrategyRegistry.register_hook(CustomPostProcessorHook())
    SceneStrategyRegistry.register_hook(CustomToolFilterHook())


class CustomStrategyExample:
    """
    完整的自定义场景策略示例
    
    展示如何组合使用所有组件
    """
    
    def __init__(self, agent):
        self.agent = agent
        self.strategy = None
        self.executor = None
    
    def setup(self):
        """设置自定义策略"""
        register_custom_hooks()
        
        self.strategy = create_custom_strategy(
            name="my_custom_strategy",
            domain="Data Analysis",
            features=["Statistical Analysis", "Data Visualization", "Report Generation"],
            base_strategy="general"
        )
        
        SceneStrategyRegistry.register_strategy(self.strategy)
        
        self.executor = SceneStrategyExecutor("my_custom_strategy", self.agent)
    
    async def run_with_hooks(self, user_input: str) -> str:
        """使用钩子系统运行"""
        ctx = HookContext(
            phase=AgentPhase.INIT,
            agent=self.agent,
            original_input=user_input,
            current_input=user_input,
            metadata={
                "custom_context": {
                    "task_type": "analysis",
                    "add_signature": True,
                    "signature": "Data Analyst Agent",
                    "quality_check": True,
                }
            }
        )
        
        ctx = await self.executor.execute_phase(AgentPhase.INIT, ctx)
        
        ctx = await self.executor.execute_phase(AgentPhase.CONTEXT_BUILD, ctx)
        
        ctx = await self.executor.execute_phase(AgentPhase.BEFORE_THINK, ctx)
        
        ctx = await self.executor.execute_phase(AgentPhase.AFTER_THINK, ctx)
        
        ctx.output = f"Analysis result for: {user_input}"
        
        ctx = await self.executor.execute_phase(AgentPhase.OUTPUT_RENDER, ctx)
        
        return ctx.output
    
    def build_prompt(self) -> str:
        """构建System Prompt"""
        return self.executor.build_system_prompt({
            "agent_name": "Data Analyst",
            "domain": "Data Analysis",
            "feature_1": "Statistical Analysis",
            "feature_2": "Data Visualization",
            "feature_3": "Report Generation",
            "priority_value": "accuracy",
            "primary_skills": "Python, SQL, Statistics",
            "secondary_skills": "Visualization, Reporting",
            "tools_available": "read, grep, bash",
        })


if __name__ == "__main__":
    print("=== Custom Scene Strategy Example ===\n")
    
    register_custom_hooks()
    
    strategy = create_custom_strategy(
        name="demo_strategy",
        domain="Code Review",
        features=["Bug Detection", "Code Quality Analysis", "Best Practices"],
    )
    
    SceneStrategyRegistry.register_strategy(strategy)
    
    executor = SceneStrategyExecutor("demo_strategy")
    
    prompt = executor.build_system_prompt({
        "agent_name": "Code Reviewer",
        "domain": "Code Review",
        "feature_1": "Bug Detection",
        "feature_2": "Code Quality",
        "feature_3": "Best Practices",
        "priority_value": "code quality",
        "primary_skills": "Code Analysis, Pattern Recognition",
        "secondary_skills": "Refactoring, Documentation",
        "tools_available": "read, grep, glob",
    })
    
    print("Generated System Prompt:")
    print("-" * 50)
    print(prompt[:1000] + "...")
    print()
    
    print("Available Hooks:")
    for hook in SceneStrategyRegistry.get_hooks_for_scene("demo_strategy"):
        print(f"  - {hook.name} (priority: {hook.priority})")