# CoreV2 内置Agent集成完成清单

## ✅ 已完成的修改

### 1. **Agent模板注册**（unified_context.py）
- ✅ 在 `V2AgentTemplate` 枚举中新增三种Agent
  - `REACT_REASONING = "react_reasoning"`
  - `FILE_EXPLORER = "file_explorer"`
  - `CODING = "coding"`

- ✅ 在 `V2_AGENT_TEMPLATES` 字典中添加详细配置
  - ReAct推理Agent（推荐）
  - 文件探索Agent
  - 编程开发Agent

### 2. **Agent工厂注册**（core_v2_adapter.py）
- ✅ 修改 `create_from_template` 函数
  - 支持 `react_reasoning` → 创建 `ReActReasoningAgent`
  - 支持 `file_explorer` → 创建 `FileExplorerAgent`
  - 支持 `coding` → 创建 `CodingAgent`

- ✅ 注册新增Agent模板到运行时工厂
  - 在工厂注册列表中添加三种新Agent

### 3. **Agent实现代码**（builtin_agents/）
- ✅ ReActReasoningAgent - 完整实现
- ✅ FileExplorerAgent - 完整实现
- ✅ CodingAgent - 完整实现
- ✅ Agent工厂和配置加载器

## 🎯 前端显示验证

### 应用配置页面应该能看到：

1. **Agent版本选择**
   - V1（传统Core架构）
   - V2（Core_v2架构）← 选择这个

2. **V2 Agent模板列表**（应该显示9个模板）
   - 简单对话Agent
   - 规划执行Agent
   - 代码助手
   - 数据分析师
   - 研究助手
   - 写作助手
   - **ReAct推理Agent（推荐）** ← 新增
   - **文件探索Agent** ← 新增
   - **编程开发Agent** ← 新增

### 检查步骤：

```bash
# 1. 重启服务
pkill -f "derisk"
python derisk_server.py

# 2. 访问API确认模板列表
curl http://localhost:5005/api/agent/list?version=v2

# 3. 检查返回结果是否包含新增的三种Agent
```

## 🔍 如果前端仍然看不到

### 可能的原因和解决方案：

#### 1. **缓存问题**
```bash
# 清理浏览器缓存或强制刷新
Ctrl+Shift+R (Windows/Linux)
Cmd+Shift+R (Mac)

# 清理Python缓存
find . -type d -name __pycache__ -exec rm -rf {} +
```

#### 2. **服务未重启**
```bash
# 完全重启服务
pkill -9 -f derisk
python derisk_server.py
```

#### 3. **导入错误**
```python
# 测试导入是否正常
python -c "
from derisk.agent.core_v2.builtin_agents import (
    ReActReasoningAgent,
    FileExplorerAgent, 
    CodingAgent
)
print('导入成功')
"
```

#### 4. **数据库缓存**
```bash
# 如果使用了数据库缓存，可能需要清理
# 或者等待缓存过期
```

## 📊 验证API响应

### 正确的API响应格式：

```json
[
  {
    "name": "simple_chat",
    "display_name": "简单对话Agent",
    "description": "适用于基础对话场景，无工具调用能力",
    "mode": "primary",
    "tools": []
  },
  ...
  {
    "name": "react_reasoning",
    "display_name": "ReAct推理Agent（推荐）",
    "description": "长程任务推理Agent，支持末日循环检测、上下文压缩...",
    "mode": "primary",
    "tools": ["bash", "read", "write", "grep", "glob", "think"],
    "capabilities": [...],
    "recommended": true
  },
  {
    "name": "file_explorer",
    "display_name": "文件探索Agent",
    "description": "主动探索项目结构...",
    "mode": "primary",
    "tools": ["glob", "grep", "read", "bash", "think"],
    "capabilities": [...]
  },
  {
    "name": "coding",
    "display_name": "编程开发Agent",
    "description": "自主代码开发Agent...",
    "mode": "primary",
    "tools": ["read", "write", "bash", "grep", "glob", "think"],
    "capabilities": [...]
  }
]
```

## 🚀 使用方法

### 方式1：直接创建（代码方式）

```python
from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent

agent = ReActReasoningAgent.create(
    name="my-agent",
    model="gpt-4"
)

async for chunk in agent.run("帮我分析项目"):
    print(chunk, end="")
```

### 方式2：应用配置（前端方式）

1. 进入应用配置页面
2. 选择Agent版本：V2
3. 选择Agent模板：ReAct推理Agent（推荐）
4. 保存配置
5. 开始对话

### 方式3：配置文件（YAML）

```yaml
agent_version: "v2"
team_mode: "single_agent"
agent_name: "react_reasoning"
```

## ⚠️ 注意事项

1. **API Key必需**
   - 所有Agent需要OpenAI API Key
   - 设置环境变量：`export OPENAI_API_KEY="sk-xxx"`

2. **模型要求**
   - 推荐使用 GPT-4 或 Claude-3
   - GPT-3.5 可能无法充分发挥Agent能力

3. **权限配置**
   - 确保Agent有文件系统访问权限
   - 确保Agent有网络访问权限（如果需要）

## 📝 文件清单

### 新增文件：
```
derisk/agent/core_v2/builtin_agents/
├── __init__.py
├── base_builtin_agent.py
├── react_reasoning_agent.py
├── file_explorer_agent.py
├── coding_agent.py
├── agent_factory.py
└── react_components/
    ├── __init__.py
    ├── doom_loop_detector.py
    ├── output_truncator.py
    ├── context_compactor.py
    └── history_pruner.py
```

### 修改文件：
```
derisk/agent/core/plan/unified_context.py
derisk-serve/src/derisk_serve/agent/core_v2_adapter.py
```

### 配置文件：
```
configs/agents/
├── react_reasoning_agent.yaml
├── file_explorer_agent.yaml
└── coding_agent.yaml
```

### 文档文件：
```
docs/CORE_V2_AGENTS_USAGE.md
tests/test_builtin_agents.py
CORE_V2_AGENT_IMPLEMENTATION_PLAN.md
```

## 🐛 问题排查

如果前端仍然看不到新增Agent，请按以下顺序检查：

1. **检查日志**
   ```bash
   tail -f logs/derisk.log | grep -i agent
   ```

2. **验证导入**
   ```python
   from derisk.agent.core.plan.unified_context import V2_AGENT_TEMPLATES
   print(V2_AGENT_TEMPLATES.keys())
   ```

3. **检查API**
   ```bash
   curl http://localhost:5005/api/agent/list?version=v2 | jq
   ```

4. **重启所有服务**
   ```bash
   # 停止所有服务
   pkill -9 -f derisk
   
   # 清理缓存
   find . -type d -name __pycache__ -exec rm -rf {} +
   
   # 重启
   python derisk_server.py
   ```

## ✅ 集成完成确认

如果以上步骤都正常，你应该能看到：

- [ ] 前端应用配置页面显示9种V2 Agent模板
- [ ] 包含"ReAct推理Agent（推荐）"
- [ ] 包含"文件探索Agent"
- [ ] 包含"编程开发Agent"
- [ ] 选择后能正常保存配置
- [ ] 对话时能正常调用Agent

---

如有任何问题，请检查日志或联系开发团队。