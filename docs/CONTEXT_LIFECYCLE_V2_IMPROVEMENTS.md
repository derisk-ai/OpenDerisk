# Context Lifecycle Management V2 - 改进版设计

## 基于 OpenCode 最佳实践的改进

### OpenCode 的关键模式

1. **Auto Compact** - 当上下文接近限制时自动压缩
2. **单一会话** - 每次只处理一个主要任务
3. **简单触发** - 明确的压缩触发条件

### 改进设计

## 问题1解决：加载新Skill自动压缩旧Skill

```
┌─────────────────────────────────────────────────────────────────┐
│                    V2 工作流程                                   │
│                                                                 │
│  Step 1: Load Skill A                                          │
│  ┌─────────────────────────────────────────┐                   │
│  │ Skill A (完整内容)                       │                   │
│  │ Token: 10000                            │                   │
│  └─────────────────────────────────────────┘                   │
│                                                                 │
│  Step 2: Load Skill B (自动触发压缩)                            │
│  ┌─────────────────────────────────────────┐                   │
│  │ Skill A (摘要) ← 自动压缩                │                   │
│  │ Token: 500                              │                   │
│  ├─────────────────────────────────────────┤                   │
│  │ Skill B (完整内容) ← 当前活跃            │                   │
│  │ Token: 8000                             │                   │
│  └─────────────────────────────────────────┘                   │
│                                                                 │
│  Step 3: Load Skill C (再次触发压缩)                            │
│  ┌─────────────────────────────────────────┐                   │
│  │ Skill A (摘要)                          │                   │
│  │ Skill B (摘要) ← 自动压缩                │                   │
│  │ Skill C (完整内容) ← 当前活跃            │                   │
│  └─────────────────────────────────────────┘                   │
│                                                                 │
│  关键：不需要判断"任务完成"，加载新Skill = 退出旧Skill           │
└─────────────────────────────────────────────────────────────────┘
```

## 问题2解决：参考 OpenCode 最佳实践

### OpenCode 的上下文管理

```go
// OpenCode 的 auto-compact 机制
type Config struct {
    AutoCompact bool `json:"autoCompact"` // 默认 true
}

// 当 token 使用超过 95% 时自动压缩
if tokenUsage > 0.95 * maxTokens {
    summarize(session)
    createNewSession(summary)
}
```

### 我们的设计借鉴

```python
# 简化的上下文规则（参考OpenCode）
class SimpleContextManager:
    def __init__(self, token_budget=100000, auto_compact_threshold=0.9):
        self._auto_compact_threshold = auto_compact_threshold
        self._active_skill = None  # 只允许一个活跃Skill
        self._compacted_skills = []  # 已压缩的Skills
    
    def load_skill(self, name, content):
        # 关键改进：加载新Skill时自动压缩旧的
        if self._active_skill:
            self._compact_skill(self._active_skill)
        
        self._active_skill = ContentSlot(name, content)
```

## V2 与 V1 对比

| 特性 | V1 (完整版) | V2 (简化版) |
|-----|------------|------------|
| 任务完成判断 | 多种检测方式 | **无需判断** |
| Skill切换 | 手动/自动检测 | **自动压缩** |
| Token管理 | 复杂预算系统 | **简单阈值** |
| 上下文组装 | 多类型支持 | **专注于Skill/Tool** |
| 集成复杂度 | 高 | **低** |

## V2 快速使用

```python
from derisk.agent.core.context_lifecycle import AgentContextIntegration

# 1. 创建集成实例
integration = AgentContextIntegration(
    token_budget=50000,  # 50k token预算
    auto_compact_threshold=0.9,  # 90%时自动压缩
)

# 2. 初始化
await integration.initialize(
    session_id="coding_session",
    system_prompt="You are a helpful coding assistant.",
)

# 3. 加载第一个Skill
result = await integration.prepare_skill(
    skill_name="code_analysis",
    skill_content="# Code Analysis Skill\n\nAnalyze code...",
    required_tools=["read", "grep"],
)
# result = {"skill_name": "code_analysis", "previous_skill": None}

# 4. 构建消息（注入上下文）
messages = integration.build_messages(
    user_message="分析认证模块的代码",
)
# messages 包含：system prompt + 完整skill内容 + 工具定义 + 用户消息

# 5. 模型处理后，加载下一个Skill
# 关键：此时自动压缩上一个Skill
result = await integration.prepare_skill(
    skill_name="code_fix",
    skill_content="# Code Fix Skill\n\nFix identified issues...",
    required_tools=["edit", "write"],
)
# result = {"skill_name": "code_fix", "previous_skill": "code_analysis"}
# "code_analysis" 已自动压缩为摘要形式

# 6. 查看Token使用
pressure = integration.check_context_pressure()
print(f"Context pressure: {pressure:.1%}")
```

## 上下文消息结构

```python
# build_messages() 返回的消息结构
messages = [
    # System消息（包含系统提示和已完成的Skills摘要）
    {
        "role": "system",
        "content": """
You are a helpful coding assistant.

# Completed Tasks
<skill-result name="code_analysis">
<summary>分析了3个文件，发现5个问题</summary>
<key-results>
  <result>SQL注入风险 in auth.py</result>
  <result>缺少错误处理 in api.py</result>
</key-results>
</skill-result>
"""
    },
    
    # 当前活跃Skill（完整内容）
    {
        "role": "system",
        "content": """
# Current Task Instructions

# Code Fix Skill

Fix identified issues...
"""
    },
    
    # 工具定义
    {
        "role": "system",
        "content": """
# Available Tools

{"name": "edit", "description": "Edit file..."}
{"name": "write", "description": "Write file..."}
"""
    },
    
    # 用户消息
    {
        "role": "user",
        "content": "请修复发现的问题"
    }
]
```

## 与 Agent 架构集成

### Core 架构集成

```python
# 在 AgentExecutor 中使用
class AgentExecutor:
    def __init__(self, agent, context_integration=None):
        self.agent = agent
        self._context = context_integration or AgentContextIntegration()
    
    async def run(self, message, skill_name=None, skill_content=None):
        # 如果指定了Skill，加载它
        if skill_name and skill_content:
            await self._context.prepare_skill(
                skill_name=skill_name,
                skill_content=skill_content,
            )
        
        # 构建消息
        messages = self._context.build_messages(message)
        
        # 调用LLM...
        response = await self.agent.think(messages)
        
        return response
```

### CoreV2 架构集成

```python
# 在 AgentHarness 中使用
class AgentHarness:
    def __init__(self, agent, context_integration=None):
        self.agent = agent
        self._context = context_integration or AgentContextIntegration()
    
    async def execute_with_skill(
        self,
        task: str,
        skill_sequence: List[Dict[str, str]],
    ):
        """按顺序执行Skills"""
        results = []
        
        for skill in skill_sequence:
            # 加载Skill（自动压缩前一个）
            await self._context.prepare_skill(
                skill_name=skill["name"],
                skill_content=skill["content"],
                required_tools=skill.get("tools", []),
            )
            
            # 执行任务
            messages = self._context.build_messages(task)
            response = await self._run_with_messages(messages)
            
            results.append({
                "skill": skill["name"],
                "response": response,
            })
        
        return results
```

## 完整工作流示例

```python
async def complete_workflow_example():
    """完整的开发工作流"""
    
    integration = AgentContextIntegration(token_budget=50000)
    await integration.initialize(
        session_id="dev_workflow",
        system_prompt="You are a senior developer.",
    )
    
    # 定义Skill序列
    skills = [
        {
            "name": "requirement_analysis",
            "content": "# Requirement Analysis\n\nUnderstand requirements...",
            "tools": ["read", "grep"],
        },
        {
            "name": "architecture_design",
            "content": "# Architecture Design\n\nDesign system architecture...",
            "tools": ["read", "write"],
        },
        {
            "name": "code_implementation",
            "content": "# Code Implementation\n\nImplement the designed system...",
            "tools": ["read", "write", "edit", "bash"],
        },
        {
            "name": "testing",
            "content": "# Testing\n\nWrite and run tests...",
            "tools": ["bash", "read"],
        },
    ]
    
    task = "实现用户认证系统"
    
    for i, skill in enumerate(skills):
        print(f"\n=== Step {i+1}: {skill['name']} ===")
        
        # 加载Skill（自动压缩前一个）
        result = await integration.prepare_skill(
            skill_name=skill["name"],
            skill_content=skill["content"],
            required_tools=skill["tools"],
        )
        
        if result.get("previous_skill"):
            print(f"Previous skill compacted: {result['previous_skill']}")
        
        # 构建消息
        messages = integration.build_messages(task)
        
        # 模拟LLM调用
        # response = await llm.chat(messages)
        print(f"Messages built: {len(messages)} parts")
        
        # 记录工具使用
        for tool in skill["tools"]:
            integration.record_tool_call(tool)
        
        # 检查上下文压力
        pressure = integration.check_context_pressure()
        print(f"Context pressure: {pressure:.1%}")
    
    # 最终报告
    report = integration.get_report()
    print(f"\n=== Final Report ===")
    print(f"Total skills processed: {len(skills)}")
    print(f"Final token usage: {report['manager_stats']['token_usage']['ratio']:.1%}")
```

## 总结

### V2 核心改进

1. **移除不可靠的判断**
   - 不需要检测"任务完成"
   - 加载新Skill = 自动压缩旧Skill

2. **简化触发机制**
   - 参考 OpenCode 的 auto-compact
   - Token超过阈值自动压缩

3. **明确的上下文结构**
   - System prompt + 已完成Skills摘要
   - 当前活跃Skill完整内容
   - 工具定义
   - 用户消息

### 推荐使用

- **简单场景**：使用 `AgentContextIntegration` (V2)
- **复杂场景**：使用完整版 V1 组件