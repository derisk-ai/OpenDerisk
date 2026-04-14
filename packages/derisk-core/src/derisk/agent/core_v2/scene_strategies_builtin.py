"""
Built-in Scene Strategies - 内置场景策略实现

实现通用模式和编码模式的完整策略：
1. System Prompt模板
2. 钩子处理器
3. 各环节扩展
"""

from typing import Dict, Any, List, Optional
import logging

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
    create_simple_hook,
)

logger = logging.getLogger(__name__)


GENERAL_SYSTEM_PROMPT = SystemPromptTemplate(
    base_template="""You are {{agent_name}}, an intelligent AI assistant designed to help users with a wide variety of tasks.

[[MAIN_CONTENT]]

Remember to be helpful, accurate, and thoughtful in your responses.""",
    
    role_definition="""## Your Role

You are a versatile assistant capable of:
- Answering questions and providing explanations
- Helping with analysis and research
- Assisting with writing and editing tasks
- Supporting problem-solving activities
- Providing recommendations and insights

Approach each task with clarity, accuracy, and a focus on being genuinely helpful.""",
    
    capabilities="""## Capabilities

You have access to the following capabilities:
- **File Operations**: Read, write, and edit files
- **Search**: Search for files and content using patterns
- **Command Execution**: Execute shell commands when needed
- **Web Access**: Fetch and analyze web content
- **Analysis**: Analyze code, data, and text

Use these capabilities wisely to accomplish user tasks effectively.""",
    
    constraints="""## Constraints & Guidelines

1. **Accuracy**: Provide accurate and verified information
2. **Safety**: Avoid harmful, illegal, or unethical actions
3. **Privacy**: Respect user privacy and confidential information
4. **Honesty**: Acknowledge limitations and uncertainties
5. **Efficiency**: Be thorough but focused on the task at hand

When uncertain, ask clarifying questions rather than making assumptions.""",
    
    guidelines="""## Response Guidelines

- Be concise yet comprehensive
- Structure your responses clearly
- Provide examples when helpful
- Break down complex tasks into steps
- Verify important information when possible
- Ask for clarification if the request is ambiguous""",
    
    examples="",
    
    sections_order=["role", "capabilities", "constraints", "guidelines"]
)


CODING_SYSTEM_PROMPT = SystemPromptTemplate(
    base_template="""You are {{agent_name}}, an expert software developer AI assistant specialized in writing high-quality code.

[[MAIN_CONTENT]]

## Current Context
- Working Directory: {{workspace_path}}
{{#git_info}}- Git Branch: {{git_branch}}{{/git_info}}
{{#project_type}}- Project Type: {{project_type}}{{/project_type}}

Always write clean, maintainable, and well-documented code.""",
    
    role_definition="""## Your Role as a Code Expert

You are a senior software engineer with deep expertise in:
- Writing production-quality code
- Code review and refactoring
- Debugging and troubleshooting
- Software architecture and design patterns
- Testing and quality assurance
- Documentation and code comments

You approach coding tasks with precision, following best practices and industry standards.""",
    
    capabilities="""## Coding Capabilities

### Code Generation
- Write clean, efficient, and well-structured code
- Follow language-specific conventions and idioms
- Generate appropriate error handling
- Include comprehensive documentation

### Code Analysis
- Analyze existing code for bugs and issues
- Identify performance bottlenecks
- Detect security vulnerabilities
- Suggest improvements and optimizations

### Code Modification
- Refactor code safely
- Implement new features
- Fix bugs with proper testing
- Maintain backward compatibility

### Development Tools
- Read and analyze project files
- Execute tests and commands
- Manage dependencies
- Work with version control""",
    
    constraints="""## Coding Constraints & Principles

### Code Quality
1. **Readability**: Code should be self-documenting
2. **Maintainability**: Follow DRY, SOLID, and YAGNI principles
3. **Testability**: Write testable code with proper separation
4. **Performance**: Consider efficiency and resource usage
5. **Security**: Follow secure coding practices

### Best Practices
- Use meaningful variable and function names
- Keep functions focused and small
- Handle errors gracefully
- Write unit tests for critical functionality
- Document public APIs and complex logic

### Safety Rules
- Always read existing code before modifying
- Backup or version control before major changes
- Test changes thoroughly
- Be cautious with destructive operations
- Ask before executing potentially dangerous commands""",
    
    guidelines="""## Coding Workflow

### Before Writing Code
1. Understand the requirements fully
2. Analyze existing codebase structure
3. Plan the implementation approach
4. Consider edge cases and error handling

### While Writing Code
1. Follow the project's coding standards
2. Write modular and reusable components
3. Include appropriate error handling
4. Add clear comments for complex logic
5. Write self-documenting code

### After Writing Code
1. Review your own code
2. Run existing tests
3. Test edge cases manually
4. Update documentation if needed
5. Check for potential improvements

### Code Style
{{#code_style_rules}}
- {{.}}
{{/code_style_rules}}

### Output Format
Always structure code outputs clearly:
```
[File: path/to/file.py]
```language
// code here
```

Include a brief explanation of changes when modifying files.""",
    
    examples="""## Code Examples

### Example 1: Adding a function
User: Add a function to calculate fibonacci numbers

Response:
I'll add a fibonacci function with proper documentation and error handling.

[File: math_utils.py]
```python
def fibonacci(n: int) -> list[int]:
    \"\"\"
    Generate a Fibonacci sequence up to n numbers.
    
    Args:
        n: Number of Fibonacci numbers to generate
        
    Returns:
        List of Fibonacci numbers
        
    Raises:
        ValueError: If n is negative
    \"\"\"
    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0:
        return []
    if n == 1:
        return [0]
    
    fib = [0, 1]
    for _ in range(2, n):
        fib.append(fib[-1] + fib[-2])
    return fib

# Usage:
# fibonacci(10) -> [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
```

This implementation:
- Uses proper type hints
- Includes comprehensive docstring
- Handles edge cases
- Is efficient with O(n) time complexity

### Example 2: Refactoring
User: Refactor this function to be more readable

I would:
1. First read the existing function
2. Identify areas for improvement
3. Refactor while maintaining functionality
4. Ensure tests still pass""",
    
    sections_order=["role", "capabilities", "constraints", "guidelines", "examples"]
)


class CodeBlockProtectionHook(SceneHook):
    """
    代码块保护钩子
    
    在上下文构建时保护代码块不被截断
    """
    name = "code_block_protection"
    priority = HookPriority.HIGH
    phases = [AgentPhase.CONTEXT_BUILD]
    
    async def on_context_build(self, ctx: HookContext) -> HookResult:
        """上下文构建时检测并保护代码块"""
        import re
        
        code_pattern = re.compile(r'```[\w]*\n[\s\S]*?```|`[^`]+`', re.MULTILINE)
        
        protected_messages = []
        for msg in ctx.messages:
            content = msg.get("content", "")
            if isinstance(content, str) and code_pattern.search(content):
                msg["has_code_block"] = True
                msg["protection_priority"] = "high"
            protected_messages.append(msg)
        
        return HookResult(
            proceed=True,
            modified_data={"messages": protected_messages}
        )


class FilePathPreservationHook(SceneHook):
    """
    文件路径保护钩子
    
    保护文件路径信息在上下文中完整保留
    """
    name = "file_path_preservation"
    priority = HookPriority.HIGH
    phases = [AgentPhase.MESSAGE_PROCESS]
    
    async def on_message_process(self, ctx: HookContext) -> HookResult:
        """处理消息时标记文件路径"""
        import re
        
        path_pattern = re.compile(
            r'(?:^|\s|[\'"])(/[a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+|[a-zA-Z]:\\[a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)',
            re.MULTILINE
        )
        
        preserved_paths = []
        for msg in ctx.messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                paths = path_pattern.findall(content)
                if paths:
                    msg["contains_file_paths"] = True
                    msg["file_paths"] = paths
                    preserved_paths.extend(paths)
        
        if preserved_paths:
            ctx.metadata["preserved_file_paths"] = list(set(preserved_paths))
        
        return HookResult(proceed=True)


class CodeStyleInjectionHook(SceneHook):
    """
    代码风格注入钩子
    
    在思考前注入代码风格指南
    """
    name = "code_style_injection"
    priority = HookPriority.NORMAL
    phases = [AgentPhase.BEFORE_THINK]
    
    def __init__(self, style_rules: List[str] = None):
        self.style_rules = style_rules or [
            "Use consistent indentation (4 spaces for Python)",
            "Follow PEP 8 for Python code",
            "Use meaningful variable and function names",
            "Add docstrings for public functions",
            "Keep functions under 50 lines",
            "Avoid deep nesting",
        ]
    
    async def on_before_think(self, ctx: HookContext) -> HookResult:
        """注入代码风格提示"""
        if ctx.scene_profile and hasattr(ctx.scene_profile, 'prompt_policy'):
            policy = ctx.scene_profile.prompt_policy
            if policy.code_style_rules:
                self.style_rules = policy.code_style_rules
        
        style_prompt = "\n".join(f"- {rule}" for rule in self.style_rules)
        
        context_addition = f"""

<code_style_guide>
Please follow these coding style guidelines:
{style_prompt}
</code_style_guide>"""
        
        if ctx.current_input and "<code_style_guide>" not in ctx.current_input:
            ctx.current_input = ctx.current_input + context_addition
        
        return HookResult(
            proceed=True,
            modified_data={"current_input": ctx.current_input}
        )


class ProjectContextInjectionHook(SceneHook):
    """
    项目上下文注入钩子
    
    注入项目结构和工作区信息
    """
    name = "project_context_injection"
    priority = HookPriority.NORMAL
    phases = [AgentPhase.CONTEXT_BUILD]
    
    async def on_context_build(self, ctx: HookContext) -> HookResult:
        """注入项目上下文"""
        context_info = []
        
        if ctx.metadata.get("workspace_path"):
            context_info.append(f"Working Directory: {ctx.metadata['workspace_path']}")
        
        if ctx.metadata.get("git_branch"):
            context_info.append(f"Current Branch: {ctx.metadata['git_branch']}")
        
        if ctx.metadata.get("project_type"):
            context_info.append(f"Project Type: {ctx.metadata['project_type']}")
        
        if context_info:
            for msg in ctx.messages:
                if msg.get("role") == "system":
                    existing = msg.get("content", "")
                    msg["content"] = existing + "\n\n" + "Project Context:\n" + "\n".join(context_info)
                    break
        
        return HookResult(proceed=True)


class ToolOutputFormatterHook(SceneHook):
    """
    工具输出格式化钩子
    
    格式化工具调用结果以更好的可读性
    """
    name = "tool_output_formatter"
    priority = HookPriority.LOW
    phases = [AgentPhase.AFTER_TOOL]
    
    async def on_after_tool(self, ctx: HookContext) -> HookResult:
        """格式化工具输出"""
        # 豁免特定工具的截断：
        # - skill_read/skill_list: Skill 内容不应截断，保持完整指令
        # - get_table_spec: 表 spec 是结构化数据，截断会破坏格式
        # - read/read_file/view: 这些工具已自行管理输出大小（分段读取）
        # - execute_sql: 已自行管理输出大小（分页+CSV导出）
        TRUNCATION_EXEMPT_TOOLS = {
            "skill_read", "skill_list", "get_table_spec",
            "read", "read_file", "view", "execute_sql",
        }

        if ctx.tool_result:
            result_str = str(ctx.tool_result)

            # 只对非豁免工具进行截断
            if ctx.tool_name and ctx.tool_name not in TRUNCATION_EXEMPT_TOOLS:
                if len(result_str) > 5000:
                    truncated = result_str[:5000]
                    ctx.tool_result = truncated + f"\n... [truncated, {len(result_str)} total characters]"
                    ctx.metadata["output_truncated"] = True

            if ctx.tool_name and "read" in ctx.tool_name:
                ctx.metadata["output_type"] = "file_content"

        return HookResult(proceed=True)


class ErrorRecoveryHook(SceneHook):
    """
    错误恢复钩子
    
    在执行错误时提供恢复建议
    """
    name = "error_recovery"
    priority = HookPriority.HIGH
    phases = [AgentPhase.ERROR]
    
    async def on_error(self, ctx: HookContext) -> HookResult:
        """处理错误并提供恢复建议"""
        if ctx.error:
            error_type = type(ctx.error).__name__
            error_msg = str(ctx.error)
            
            recovery_suggestions = []
            
            if "FileNotFound" in error_type or "No such file" in error_msg:
                recovery_suggestions.append("Check if the file path is correct")
                recovery_suggestions.append("Verify the file exists before reading")
            
            if "Permission" in error_type or "permission denied" in error_msg.lower():
                recovery_suggestions.append("Check file/directory permissions")
            
            if "SyntaxError" in error_type:
                recovery_suggestions.append("Review the code for syntax errors")
            
            ctx.metadata["error_type"] = error_type
            ctx.metadata["error_message"] = error_msg
            ctx.metadata["recovery_suggestions"] = recovery_suggestions
        
        return HookResult(proceed=True)


GENERAL_STRATEGY = SceneStrategy(
    name="general",
    description="通用场景策略 - 平衡的助手能力",
    
    system_prompt=GENERAL_SYSTEM_PROMPT,
    
    hooks=[
        "project_context_injection",
        "error_recovery",
    ],
    
    context_processor_extension=ContextProcessorExtension(
        custom_importance_rules=[
            {"pattern": "user_question", "importance": 0.9},
            {"pattern": "task_goal", "importance": 0.85},
        ]
    ),
)


CODING_STRATEGY = SceneStrategy(
    name="coding",
    description="编码场景策略 - 专业的代码开发支持，内置软件工程最佳实践",
    
    system_prompt=CODING_SYSTEM_PROMPT,
    
    hooks=[
        "software_engineering_injection",
        "code_block_protection",
        "file_path_preservation",
        "code_style_injection",
        "project_context_injection",
        "tool_output_formatter",
        "error_recovery",
        "software_engineering_check",
    ],
    
    context_processor_extension=ContextProcessorExtension(
        custom_protect_patterns=[
            r'```[\w]*\n[\s\S]*?```',
            r'def\s+\w+\s*\([^)]*\):',
            r'class\s+\w+.*:',
            r'from\s+\w+\s+import',
            r'import\s+\w+',
        ],
        custom_importance_rules=[
            {"pattern": "code_block", "importance": 0.95},
            {"pattern": "file_path", "importance": 0.9},
            {"pattern": "error_message", "importance": 0.85},
            {"pattern": "function_definition", "importance": 0.8},
        ]
    ),
    
    tool_selector_extension=ToolSelectorExtension(
        filter_rules=[
            {"action": "prefer", "tools": ["read", "edit", "write", "grep", "glob"]},
            {"action": "confirm", "tools": ["bash"]},
        ],
        auto_suggest_tools=True,
        suggest_rules=[
            "read for file exploration",
            "grep for content search",
            "edit for code modification",
        ]
    ),
    
    output_renderer_extension=OutputRendererExtension(
        code_block_renderer="syntax_highlight",
        markdown_renderer="full",
    ),
)


def register_builtin_strategies():
    """注册内置场景策略"""
    from derisk.agent.core_v2.se_hooks import (
        SoftwareEngineeringHook,
        SoftwareEngineeringCheckHook,
    )
    
    SceneStrategyRegistry.register_hook(CodeBlockProtectionHook())
    SceneStrategyRegistry.register_hook(FilePathPreservationHook())
    SceneStrategyRegistry.register_hook(CodeStyleInjectionHook())
    SceneStrategyRegistry.register_hook(ProjectContextInjectionHook())
    SceneStrategyRegistry.register_hook(ToolOutputFormatterHook())
    SceneStrategyRegistry.register_hook(ErrorRecoveryHook())
    
    SceneStrategyRegistry.register_hook(SoftwareEngineeringHook(
        injection_level="light",
        config_dir="configs/engineering",
    ))
    SceneStrategyRegistry.register_hook(SoftwareEngineeringCheckHook(
        enabled=True,
        strict_mode=False,
    ))
    
    SceneStrategyRegistry.register_prompt_template("general", GENERAL_SYSTEM_PROMPT)
    SceneStrategyRegistry.register_prompt_template("coding", CODING_SYSTEM_PROMPT)
    
    SceneStrategyRegistry.register_strategy(GENERAL_STRATEGY)
    SceneStrategyRegistry.register_strategy(CODING_STRATEGY)
    
    logger.info("[Built-in Strategies] Registered general and coding strategies with SE rules")


register_builtin_strategies()