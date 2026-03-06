# CoreV2 Agent 架构层次说明

## 架构层次图

```
AgentBase (抽象基类)
    ↓
ProductionAgent (生产级Agent实现)
    ↓
BaseBuiltinAgent (内置Agent基类)
    ↓
├── ReActReasoningAgent (长程推理Agent)
├── FileExplorerAgent (文件探索Agent)
└── CodingAgent (编程开发Agent)
```

## 各层次说明

### 1. AgentBase (抽象基类)
**维度**: Agent的**基础抽象层**

**职责**:
- 定义Agent的核心接口（think/decide/act）
- 提供状态管理机制
- 集成权限系统
- 支持子Agent委派

**何时使用**:
- 需要实现完全自定义的Agent逻辑
- 不需要LLM调用能力
- 需要底层控制

**示例**:
```python
from derisk.agent.core_v2 import AgentBase, AgentInfo

class MyCustomAgent(AgentBase):
    async def think(self, message: str) -> AsyncIterator[str]:
        yield "自定义思考逻辑"
    
    async def act(self, tool_name: str, args: Dict) -> Any:
        return await self.execute_tool(tool_name, args)
```

---

### 2. ProductionAgent (生产级Agent)
**维度**: Agent的**生产可用实现层**

**职责**:
- ✅ LLM调用能力
- ✅ 工具执行能力
- ✅ 记忆管理
- ✅ 目标管理
- ✅ 用户交互（主动提问、授权审批、方案选择）
- ✅ 中断恢复
- ✅ 进度追踪

**何时使用**:
- 需要一个完整的、可立即使用的Agent
- 需要LLM驱动的智能Agent
- 需要与用户交互的能力

**示例1: 直接使用ProductionAgent**
```python
from derisk.agent.core_v2 import ProductionAgent, AgentInfo
from derisk.agent.core_v2.llm_adapter import LLMConfig, LLMFactory

# 创建配置
info = AgentInfo(
    name="my-agent",
    max_steps=20
)

llm_config = LLMConfig(
    model="gpt-4",
    api_key="sk-xxx"
)

llm_adapter = LLMFactory.create(llm_config)

# 创建Agent
agent = ProductionAgent(
    info=info,
    llm_adapter=llm_adapter
)

# 初始化交互
agent.init_interaction(session_id="session-001")

# 执行任务
async for chunk in agent.run("帮我完成数据分析"):
    print(chunk, end="")
```

**示例2: 使用用户交互能力**
```python
# 主动提问
answer = await agent.ask_user(
    question="请提供数据库连接信息",
    title="需要配置",
    timeout=300
)

# 请求授权
authorized = await agent.request_authorization(
    tool_name="bash",
    tool_args={"command": "rm -rf data"},
    reason="需要清理临时数据"
)

# 让用户选择方案
plan_id = await agent.choose_plan(
    plans=[
        {"id": "fast", "name": "快速方案", "cost": "低", "quality": "中"},
        {"id": "quality", "name": "高质量方案", "cost": "高", "quality": "高"},
    ],
    title="请选择执行方案"
)
```

---

### 3. BaseBuiltinAgent (内置Agent基类)
**维度**: Agent的**场景定制基类层**

**职责**:
- 继承ProductionAgent的所有能力
- 提供默认工具集管理
- 支持配置驱动的工具加载
- 支持原生Function Call
- 场景特定的默认行为

**何时使用**:
- 创建特定场景的Agent（如编程、探索、推理）
- 需要预定义的工具集
- 需要场景特定的系统提示词

**示例**:
```python
from derisk.agent.core_v2.builtin_agents import BaseBuiltinAgent
from derisk.agent.core_v2 import AgentInfo
from derisk.agent.core_v2.llm_adapter import LLMConfig, LLMFactory

class MySceneAgent(BaseBuiltinAgent):
    def _get_default_tools(self) -> List[str]:
        """定义场景默认工具"""
        return ["bash", "read", "write", "my_custom_tool"]
    
    def _build_system_prompt(self) -> str:
        """定义场景系统提示词"""
        return "你是一个专业的XX场景Agent..."
    
    async def run(self, message: str, stream: bool = True):
        """实现场景特定的执行逻辑"""
        # 场景特定的处理
        async for chunk in super().run(message, stream):
            yield chunk
```

---

### 4. 内置Agent (ReActReasoningAgent/FileExplorerAgent/CodingAgent)
**维度**: Agent的**具体场景实现层**

**特点**:
- ✅ 开箱即用
- ✅ 场景优化
- ✅ 特殊能力（末日循环检测、主动探索等）

**何时使用**:
- 直接使用预定义的Agent
- 无需自己实现

**示例**:
```python
from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent

# 方式1: 使用create方法
agent = ReActReasoningAgent.create(
    name="my-react-agent",
    model="gpt-4",
    api_key="sk-xxx",
    max_steps=30
)

# 方式2: 从配置文件创建
from derisk.agent.core_v2.builtin_agents import create_agent_from_config
agent = create_agent_from_config("configs/agents/react_reasoning_agent.yaml")

# 方式3: 使用工厂创建
from derisk.agent.core_v2.builtin_agents import create_agent
agent = create_agent(
    agent_type="react_reasoning",
    name="my-agent"
)

# 执行任务
async for chunk in agent.run("帮我完成长程推理任务"):
    print(chunk, end="")
```

---

## 使用建议

### 场景1: 快速使用（推荐）
```python
# 直接使用内置Agent
from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent

agent = ReActReasoningAgent.create(name="my-agent")
async for chunk in agent.run("任务"):
    print(chunk)
```

### 场景2: 需要完全自定义
```python
# 继承AgentBase
class MyAgent(AgentBase):
    async def think(self, message: str):
        yield "自定义思考"
    
    async def act(self, tool_name: str, args: Dict):
        return await self.execute_tool(tool_name, args)
```

### 场景3: 需要生产级能力但想定制
```python
# 继承ProductionAgent
class MyProductionAgent(ProductionAgent):
    async def run(self, message: str, stream: bool = True):
        # 定制执行逻辑
        async for chunk in super().run(message, stream):
            # 后处理
            yield chunk
```

### 场景4: 创建新的场景Agent
```python
# 继承BaseBuiltinAgent
class MySceneAgent(BaseBuiltinAgent):
    def _get_default_tools(self):
        return ["tool1", "tool2"]
    
    def _build_system_prompt(self):
        return "场景提示词"
```

---

## ProductionAgent 核心能力

### 1. LLM调用
```python
# 自动处理LLM调用
response = await self.llm.generate(messages=[...])
```

### 2. 工具执行
```python
# 执行工具
result = await self.execute_tool("bash", {"command": "ls -la"})

# 检查权限
permission = self.check_permission("bash", {"command": "rm -rf"})
```

### 3. 用户交互
```python
# 主动提问
answer = await agent.ask_user("问题")

# 请求授权
authorized = await agent.request_authorization("bash", args)

# 选择方案
plan_id = await agent.choose_plan([...])

# 确认操作
confirmed = await agent.confirm("确认删除？")

# 多选
selected = await agent.select("选择工具", options=[...])
```

### 4. 目标管理
```python
# 设置目标
agent.goals.set_goal("完成数据分析")

# 检查目标
status = agent.goals.check_status()
```

### 5. 进度追踪
```python
# 广播进度
agent.progress.broadcast("正在处理...")
```

---

## 完整示例

```python
import asyncio
from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent

async def main():
    # 创建Agent
    agent = ReActReasoningAgent.create(
        name="my-react-agent",
        model="gpt-4",
        api_key="sk-xxx",
        max_steps=30,
        enable_doom_loop_detection=True
    )
    
    # 初始化交互
    agent.init_interaction(session_id="session-001")
    
    # 执行任务（可交互）
    async for chunk in agent.run("帮我分析当前项目的代码质量"):
        print(chunk, end="", flush=True)
    
    # 获取统计信息
    stats = agent.get_statistics()
    print(f"\n\n统计: {stats}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 总结

| Agent层级 | 维度 | 使用场景 | 推荐度 |
|---------|------|---------|--------|
| AgentBase | 抽象基类 | 完全自定义Agent | ⭐⭐ |
| ProductionAgent | 生产实现 | 需要完整能力 | ⭐⭐⭐ |
| BaseBuiltinAgent | 场景基类 | 创建场景Agent | ⭐⭐⭐⭐ |
| 内置Agent | 具体实现 | 直接使用 | ⭐⭐⭐⭐⭐ |

**推荐**: 优先使用内置Agent，其次继承BaseBuiltinAgent创建场景Agent。