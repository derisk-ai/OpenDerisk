# Derisk Core_v2 统一记忆框架与增强Agent使用指南

## 目录
1. [快速开始](#快速开始)
2. [统一记忆框架](#统一记忆框架)
3. [改进的上下文压缩](#改进的上下文压缩)
4. [增强Agent系统](#增强agent系统)
5. [完整集成示例](#完整集成示例)

---

## 快速开始

### 安装依赖

```bash
# 确保安装了derisk-core
pip install derisk-core

# 可选：安装向量数据库支持
pip install chromadb
pip install openai  # 用于Embedding
```

### 最简使用

```python
from derisk.agent.core_v2 import (
    ClaudeCodeCompatibleMemory,
    EnhancedProductionAgent,
    EnhancedAgentInfo,
)

# 1. 创建记忆系统
memory = await ClaudeCodeCompatibleMemory.from_project(
    project_root="/path/to/project",
)

# 2. 加载CLAUDE.md风格记忆
await memory.load_claude_md_style()

# 3. 创建Agent
agent_info = EnhancedAgentInfo(
    name="my_agent",
    description="A helpful assistant",
    role="assistant",
)

agent = EnhancedProductionAgent(info=agent_info, memory=memory)

# 4. 运行Agent
async for chunk in agent.run("Hello, how can you help?"):
    print(chunk, end="")
```

---

## 统一记忆框架

### 1. 基础使用

```python
from derisk.agent.core_v2 import (
    UnifiedMemoryManager,
    MemoryType,
    MemoryItem,
    SearchOptions,
)
from derisk.storage.vector_store.chroma_store import ChromaStore, ChromaVectorConfig
from derisk.rag.embedding import DefaultEmbeddingFactory

# 创建向量存储
embedding_model = DefaultEmbeddingFactory.openai()
vector_store = ChromaStore(
    ChromaVectorConfig(persist_path="./memory_db"),
    name="my_memory",
    embedding_fn=embedding_model,
)

# 创建统一记忆管理器
memory = UnifiedMemoryManager(
    project_root="/path/to/project",
    vector_store=vector_store,
    embedding_model=embedding_model,
    session_id="session_123",
)

# 初始化
await memory.initialize()

# 写入记忆
memory_id = await memory.write(
    content="用户偏好Python语言，喜欢使用异步编程",
    memory_type=MemoryType.PREFERENCE,
    metadata={"user_id": "user_001"},
)

# 读取记忆
items = await memory.read("Python")

# 向量相似度搜索
similar_items = await memory.search_similar(
    query="编程语言偏好",
    top_k=5,
)
```

### 2. Claude Code 兼容模式

```python
from derisk.agent.core_v2 import ClaudeCodeCompatibleMemory

# 创建Claude Code兼容的记忆系统
memory = await ClaudeCodeCompatibleMemory.from_project(
    project_root="/path/to/project",
    session_id="session_123",
)

# 加载各种CLAUDE.md文件
stats = await memory.load_claude_md_style()
print(f"Loaded: {stats}")
# 示例输出:
# {
#     "user": 1,           # 用户级记忆
#     "project": 2,        # 项目级记忆
#     "local": 1,          # 本地覆盖
# }

# 添加自动记忆（用于子代理）
await memory.auto_memory(
    session_id="session_123",
    content="Learned that user prefers type hints in Python",
    topic="preferences",
)

# 子代理记忆
await memory.update_subagent_memory(
    agent_name="code-reviewer",
    content="Discovered project uses pytest for testing",
    scope="project",
)

# 创建可共享的CLAUDE.md
output_path = await memory.create_claude_md_from_context(
    include_imports=True,
)
```

### 3. 文件系统存储

```python
from derisk.agent.core_v2 import FileBackedStorage, MemoryType

# 创建文件存储
storage = FileBackedStorage(
    project_root="/path/to/project",
    session_id="session_123",
)

# 保存记忆
item = MemoryItem(
    id="mem_001",
    content="Important context about the project",
    memory_type=MemoryType.SHARED,
)
await storage.save(item, sync_to_shared=True)

# 加载共享记忆
shared_items = await storage.load_shared_memory()

# 导出记忆
await storage.export(
    output_path="./exported_memory.md",
    format="markdown",
)

# 确保gitignore配置正确
await storage.ensure_gitignore()
```

### 4. 记忆巩固

```python
# 巩固工作记忆到情景记忆
result = await memory.consolidate(
    source_type=MemoryType.WORKING,
    target_type=MemoryType.EPISODIC,
    criteria={
        "min_importance": 0.5,
        "min_access_count": 2,
        "max_age_hours": 24,
    },
)

print(f"Consolidated: {result.items_consolidated}")
print(f"Tokens saved: {result.tokens_saved}")
```

---

## 改进的上下文压缩

### 1. 基础压缩

```python
from derisk.agent.core_v2 import (
    ImprovedSessionCompaction,
    CompactionConfig,
)

# 创建压缩器
compaction = ImprovedSessionCompaction(
    context_window=128000,
    threshold_ratio=0.80,
    recent_messages_keep=3,
    llm_client=llm_client,
)

# 设置共享记忆加载器
async def load_shared():
    items = await memory.read("")
    return "\n".join([i.content for i in items])

compaction.set_shared_memory_loader(load_shared)

# 执行压缩
result = await compaction.compact(messages)

print(f"Success: {result.success}")
print(f"Tokens saved: {result.tokens_saved}")
print(f"Protected content: {result.protected_content_count}")
```

### 2. 内容保护

```python
from derisk.agent.core_v2 import ContentProtector, ProtectedContent

# 创建内容保护器
protector = ContentProtector()

# 提取受保护内容
protected, _ = protector.extract_protected_content(messages)

# 查看提取的内容
for item in protected:
    print(f"Type: {item.content_type}")
    print(f"Importance: {item.importance}")
    print(f"Content preview: {item.content[:100]}...")

# 格式化输出
formatted = protector.format_protected_content(protected)
```

### 3. 关键信息提取

```python
from derisk.agent.core_v2 import KeyInfoExtractor, KeyInfo

# 创建提取器
extractor = KeyInfoExtractor(llm_client=llm_client)

# 提取关键信息
key_infos = await extractor.extract(messages)

# 查看提取的信息
for info in key_infos:
    print(f"Category: {info.category}")
    print(f"Content: {info.content}")
    print(f"Importance: {info.importance}")

# 格式化输出
formatted = extractor.format_key_infos(key_infos, min_importance=0.5)
```

### 4. 自动压缩管理

```python
from derisk.agent.core_v2 import AutoCompactionManager

# 创建管理器
auto_manager = AutoCompactionManager(
    compaction=compaction,
    memory=memory,
    trigger="adaptive",  # 或 "threshold"
)

# 检查并压缩
result = await auto_manager.check_and_compact(messages)
```

---

## 增强Agent系统

### 1. 基础Agent

```python
from derisk.agent.core_v2 import (
    EnhancedAgentBase,
    EnhancedAgentInfo,
    Decision,
    DecisionType,
    ActionResult,
)

class MyAgent(EnhancedAgentBase):
    async def think(self, message: str, **kwargs):
        """思考阶段"""
        # 调用LLM进行思考
        async for chunk in self.llm_client.astream([...]):
            yield chunk
    
    async def decide(self, context: Dict[str, Any], **kwargs) -> Decision:
        """决策阶段"""
        thinking = context.get("thinking", "")
        
        # 解析思考结果，做出决策
        if "tool" in thinking.lower():
            return Decision(
                type=DecisionType.TOOL_CALL,
                tool_name="read_file",
                tool_args={"path": "example.py"},
            )
        
        return Decision(
            type=DecisionType.RESPONSE,
            content=thinking,
        )
    
    async def act(self, decision: Decision, **kwargs) -> ActionResult:
        """执行阶段"""
        if decision.type == DecisionType.TOOL_CALL:
            tool = self.tools.get(decision.tool_name)
            result = await tool.execute(decision.tool_args)
            return ActionResult(success=True, output=str(result))
        
        return ActionResult(success=True, output=decision.content)

# 使用
agent_info = EnhancedAgentInfo(
    name="my_agent",
    description="Custom agent",
    role="assistant",
    tools=["read_file", "write_file"],
    max_steps=10,
)

agent = MyAgent(info=agent_info, llm_client=llm_client)
```

### 2. 子代理委托

```python
from derisk.agent.core_v2 import EnhancedSubagentManager

# 创建子代理管理器
subagent_manager = EnhancedSubagentManager(memory=memory)

# 注册子代理工厂
async def create_code_reviewer():
    return EnhancedProductionAgent(
        info=EnhancedAgentInfo(
            name="code-reviewer",
            description="Reviews code",
            tools=["read_file", "grep"],
        ),
        memory=memory,
    )

subagent_manager.register_agent_factory("code-reviewer", create_code_reviewer)

# 委托任务
result = await subagent_manager.delegate(
    subagent_name="code-reviewer",
    task="Review the authentication module",
    parent_messages=agent._messages,
    timeout=60,
)

print(result.output)
```

### 3. 团队协作

```python
from derisk.agent.core_v2 import TeamManager, TaskList

# 创建团队管理器
team_manager = TeamManager(memory=memory)

# 生成队友
analyst_agent = EnhancedProductionAgent(...)
await team_manager.spawn_teammate(
    name="analyst",
    role="data_analyst",
    agent=analyst_agent,
)

dev_agent = EnhancedProductionAgent(...)
await team_manager.spawn_teammate(
    name="developer",
    role="developer",
    agent=dev_agent,
)

# 分配任务
task_result = await team_manager.assign_task({
    "description": "Analyze user data",
    "assigned_to": "analyst",
    "dependencies": [],
})

# 队友认领任务
success = await team_manager.claim_task(
    agent_name="analyst",
    task_id=task_result.metadata["task_id"],
)

# 完成任务
await team_manager.complete_task(
    agent_name="analyst",
    task_id=task_result.metadata["task_id"],
    result="Analysis completed...",
)

# 广播消息
await team_manager.broadcast(
    message="Analysis phase complete, development can begin",
    exclude={"analyst"},
)

# 清理团队
await team_manager.cleanup()
```

### 4. 完整配置示例

```python
import asyncio
from derisk.agent.core_v2 import (
    ClaudeCodeCompatibleMemory,
    EnhancedProductionAgent,
    EnhancedAgentInfo,
    EnhancedSubagentManager,
    TeamManager,
    AutoCompactionManager,
    ImprovedSessionCompaction,
)
from derisk.core import LLMClient

async def main():
    # 1. 初始化LLM
    llm_client = LLMClient(...)  # 配置LLM
    
    # 2. 创建记忆系统
    memory = await ClaudeCodeCompatibleMemory.from_project(
        project_root="/path/to/project",
        session_id="session_123",
    )
    await memory.load_claude_md_style()
    
    # 3. 创建主Agent
    main_agent_info = EnhancedAgentInfo(
        name="orchestrator",
        description="Main orchestrator agent",
        role="coordinator",
        tools=["read_file", "write_file", "grep", "bash"],
        subagents=["code-reviewer", "data-analyst"],
        can_spawn_team=True,
        team_role="coordinator",
        max_steps=20,
    )
    
    main_agent = EnhancedProductionAgent(
        info=main_agent_info,
        memory=memory,
        llm_client=llm_client,
    )
    
    # 4. 设置自动压缩
    main_agent.setup_auto_compaction(
        context_window=128000,
        threshold_ratio=0.80,
    )
    
    # 5. 配置子代理
    subagent_manager = EnhancedSubagentManager(memory=memory)
    
    async def create_reviewer():
        return EnhancedProductionAgent(
            info=EnhancedAgentInfo(
                name="code-reviewer",
                description="Code review specialist",
                tools=["read_file", "grep"],
                max_steps=10,
            ),
            memory=memory,
            llm_client=llm_client,
        )
    
    subagent_manager.register_agent_factory("code-reviewer", create_reviewer)
    main_agent.set_subagent_manager(subagent_manager)
    
    # 6. 配置团队
    team_manager = TeamManager(
        coordinator=main_agent,
        memory=memory,
    )
    main_agent.set_team_manager(team_manager)
    
    # 7. 运行
    async for chunk in main_agent.run("Please review the recent code changes"):
        print(chunk, end="")
    
    # 8. 保存记忆
    await memory.archive_session()

asyncio.run(main())
```

---

## 完整集成示例

### 项目结构

```
my_project/
├── .agent_memory/
│   ├── PROJECT_MEMORY.md      # 团队共享记忆 (Git tracked)
│   ├── TEAM_RULES.md          # 团队规则
│   └── sessions/              # 会话记忆
├── .agent_memory.local/       # 本地覆盖 (gitignored)
├── CLAUDE.md                  # 可选：项目指令
└── src/
    └── my_agents/
        ├── __init__.py
        ├── main_agent.py
        └── subagents/
            ├── reviewer.py
            └── analyst.py
```

### CLAUDE.md 示例

```markdown
# Project Memory

## Build Commands
- Build: `npm run build`
- Test: `npm test`
- Lint: `npm run lint`

## Code Style
- Use TypeScript strict mode
- Prefer functional components
- Use async/await over promises

## Important Files
See @docs/api-conventions.md for API design patterns
See @docs/testing-guide.md for testing conventions

## Team Preferences
- Commit messages: conventional commits format
- PR reviews: require 2 approvals
```

### 完整Agent代码

```python
# my_agents/main_agent.py

from derisk.agent.core_v2 import (
    ClaudeCodeCompatibleMemory,
    EnhancedProductionAgent,
    EnhancedAgentInfo,
    EnhancedSubagentManager,
    TeamManager,
    Decision,
    DecisionType,
    ActionResult,
)

class OrchestratorAgent(EnhancedProductionAgent):
    """主协调Agent"""
    
    async def think(self, message: str, **kwargs):
        # 构建上下文
        context = await self._build_context()
        
        # 加载共享记忆
        shared = await self._load_shared_memory()
        
        # 调用LLM思考
        messages = self._build_llm_messages(context, shared, message)
        async for chunk in self.llm_client.astream(messages):
            yield chunk
    
    async def decide(self, context: Dict[str, Any], **kwargs) -> Decision:
        thinking = context.get("thinking", "")
        
        # 智能决策
        if "review" in thinking.lower() or "audit" in thinking.lower():
            return Decision(
                type=DecisionType.SUBAGENT,
                subagent_name="code-reviewer",
                subagent_task=context.get("message", ""),
            )
        
        if "analyze data" in thinking.lower():
            return Decision(
                type=DecisionType.TEAM_TASK,
                team_task={
                    "description": context.get("message", ""),
                    "assigned_to": "analyst",
                },
            )
        
        if any(tool in thinking.lower() for tool in ["read", "write", "grep"]):
            # 解析工具调用
            return self._parse_tool_call(thinking)
        
        return Decision(
            type=DecisionType.RESPONSE,
            content=thinking,
        )
    
    async def act(self, decision: Decision, **kwargs) -> ActionResult:
        return await super().act(decision, **kwargs)


async def create_main_agent(project_root: str, session_id: str):
    """创建主Agent"""
    
    # 记忆系统
    memory = await ClaudeCodeCompatibleMemory.from_project(
        project_root=project_root,
        session_id=session_id,
    )
    await memory.load_claude_md_style()
    
    # Agent配置
    agent_info = EnhancedAgentInfo(
        name="orchestrator",
        description="""Main orchestrator agent that:
- Coordinates subagents for specialized tasks
- Manages team collaboration
- Handles code reviews and data analysis
- Maintains project memory""",
        role="Project Orchestrator",
        tools=["read_file", "write_file", "grep", "glob", "bash"],
        subagents=["code-reviewer", "data-analyst"],
        can_spawn_team=True,
        team_role="coordinator",
        max_steps=20,
        memory_enabled=True,
        memory_scope="project",
    )
    
    # 创建Agent
    agent = OrchestratorAgent(
        info=agent_info,
        memory=memory,
    )
    
    # 设置自动压缩
    agent.setup_auto_compaction(
        context_window=128000,
        threshold_ratio=0.80,
    )
    
    return agent
```

---

## 性能优化建议

### 1. 记忆系统优化

```python
# 批量写入
memories = [
    ("User prefers Python", MemoryType.PREFERENCE),
    ("Project uses pytest", MemoryType.SEMANTIC),
    ("API uses REST", MemoryType.SHARED),
]

for content, mem_type in memories:
    await memory.write(content, mem_type)

# 定期巩固
await memory.consolidate(
    source_type=MemoryType.WORKING,
    target_type=MemoryType.EPISODIC,
)
```

### 2. 压缩策略优化

```python
# 调整压缩阈值
compaction = ImprovedSessionCompaction(
    context_window=128000,
    threshold_ratio=0.75,  # 更早触发压缩
)

# 启用自适应压缩
auto_compaction = AutoCompactionManager(
    compaction=compaction,
    trigger="adaptive",
)
```

### 3. 子代理优化

```python
# 使用后台模式
result = await subagent_manager.delegate(
    subagent_name="reviewer",
    task="Review large codebase",
    background=True,  # 后台执行
)

# 继续主线程工作
# ...

# 恢复获取结果
result = await subagent_manager.resume(result.session_id)
```

---

## 常见问题

### Q: 如何迁移现有Agent？

```python
# 旧代码
from derisk.agent.core import ConversableAgent

# 新代码
from derisk.agent.core_v2 import EnhancedProductionAgent, EnhancedAgentInfo

# 转换配置
old_config = {...}
new_info = EnhancedAgentInfo(
    name=old_config.get("name", "agent"),
    description=old_config.get("description", ""),
    tools=old_config.get("tools", []),
)
```

### Q: 如何与现有SessionCompaction兼容？

```python
from derisk.agent.core_v2 import ImprovedSessionCompaction

# 向后兼容
ImprovedSessionCompaction = ImprovedSessionCompaction  # 别名
```

### Q: 记忆如何跨会话共享？

```python
# 使用shared类型
await memory.write(
    content="Important project context",
    memory_type=MemoryType.SHARED,
    sync_to_file=True,
)

# 自动加载
await memory.load_claude_md_style()
```

---

*文档版本: 1.0*
*最后更新: 2026-03-01*