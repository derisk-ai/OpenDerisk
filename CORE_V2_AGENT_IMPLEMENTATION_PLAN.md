# CoreV2 Agent实现方案

## 当前状态分析

### ✅ 已具备的完整基础设施

1. **Agent框架核心** (`agent_base.py`)
   - AgentBase基类：think/decide/act三阶段循环
   - 状态管理、权限系统、子Agent委派
   - 消息历史、执行统计

2. **生产级Agent** (`production_agent.py`)
   - ProductionAgent：具备LLM调用、工具执行
   - AgentBuilder：链式构建模式
   - 增强交互能力（ask_user、request_authorization、choose_plan）

3. **完整的工具系统** (`tools_v2/`)
   - 内置工具：BashTool, ReadTool, WriteTool, SearchTool, ListFilesTool
   - 交互工具：QuestionTool, ConfirmTool, NotifyTool, AskHumanTool
   - 网络工具：WebFetchTool, WebSearchTool
   - 分析工具：AnalyzeDataTool, AnalyzeCodeTool, GenerateReportTool
   - TaskTool：子Agent委派工具

4. **场景策略系统** (`scene_strategies_builtin.py`)
   - GENERAL_STRATEGY：通用场景
   - CODING_STRATEGY：编码场景
   - SystemPrompt模板、钩子机制
   - 代码块保护、文件路径保留、错误恢复

5. **高级特性支持**
   - 上下文压缩（memory_compaction.py）
   - 向量检索（memory_vector.py）
   - 目标管理（goal.py）
   - 检查点恢复（agent_harness.py）
   - Docker沙箱（sandbox_docker.py）

### ❌ 缺失的关键组件

1. **没有内置的默认Agent实例**
   - 场景策略只是配置，缺少具体Agent实现
   - 用户无法直接使用开箱即用的Agent

2. **没有ReAct推理Agent**
   - Core架构的ReActMasterAgent能力未迁移
   - 缺少末日循环检测、上下文压缩、历史修剪

3. **没有专用场景Agent**
   - 缺少FileExplorerAgent（主动探索）
   - 缺少CodingAgent（自主编程）

4. **缺少主动探索机制**
   - 没有自动调用glob/grep/read探索项目
   - 没有项目结构分析和理解能力

---

## 实现方案

### 方案选择

根据你的需求，采用以下方案：

1. ✅ **独立Agent类** - 创建三个专用Agent类
2. ✅ **完整迁移** - 从Core完整迁移ReActMasterAgent特性
3. ✅ **自主探索** - 支持主动探索能力（参考OpenCode）
4. ✅ **默认+配置** - 硬编码内置工具集 + 配置文件扩展

---

## 实现架构

### 1. ReActReasoningAgent（长程任务推理）

**文件位置**：`core_v2/builtin_agents/react_reasoning_agent.py`

**核心特性**（完整迁移自ReActMasterAgent）：
```python
class ReActReasoningAgent(AgentBase):
    """
    ReAct推理Agent - 长程任务解决
    
    特性：
    1. 末日循环检测（DoomLoopDetector）
    2. 上下文压缩（SessionCompaction）
    3. 工具输出截断（Truncation）
    4. 历史修剪（HistoryPruning）
    5. 原生Function Call支持
    6. 阶段管理（PhaseManager）
    7. 自动报告生成
    """
    
    # 核心组件
    enable_doom_loop_detection: bool = True
    enable_session_compaction: bool = True
    enable_output_truncation: bool = True
    enable_history_pruning: bool = True
    enable_phase_management: bool = True
    
    # Function Call模式
    function_calling: bool = True
    
    # 工具选择策略
    tool_choice_strategy: str = "auto"  # auto/required/none
```

**实现要点**：
- 从`core/expand/react_master_agent/`迁移核心组件
- 适配CoreV2的AgentBase接口
- 集成CoreV2的工具系统和权限系统
- 保持原有的末日循环检测、上下文压缩等高级特性

**工具集**：
- 默认加载：bash, read, write, grep, glob, think
- 可选工具：web_search, web_fetch, question, confirm
- 自定义工具：通过配置加载

---

### 2. FileExplorerAgent（文件探索）

**文件位置**：`core_v2/builtin_agents/file_explorer_agent.py`

**核心特性**：
```python
class FileExplorerAgent(AgentBase):
    """
    文件探索Agent - 主动探索项目结构
    
    特性：
    1. 主动探索机制（参考OpenCode）
    2. 项目结构分析
    3. 代码库深度理解
    4. 自动生成项目文档
    5. 依赖关系分析
    """
    
    # 探索配置
    enable_auto_exploration: bool = True
    max_exploration_depth: int = 5
    exploration_strategy: str = "breadth_first"  # breadth_first/depth_first
    
    # 分析能力
    enable_code_analysis: bool = True
    enable_dependency_analysis: bool = True
    enable_structure_summary: bool = True
```

**主动探索机制**：
```python
async def _auto_explore_project(self, project_path: str):
    """自动探索项目结构"""
    
    # 1. 探索目录结构
    files = await self.execute_tool("glob", {
        "pattern": "**/*",
        "path": project_path
    })
    
    # 2. 分析项目类型
    project_type = await self._detect_project_type(files)
    
    # 3. 探索关键文件
    key_files = await self._find_key_files(project_type)
    
    # 4. 分析代码结构
    structure = await self._analyze_structure(key_files)
    
    # 5. 生成项目摘要
    summary = await self._generate_summary(structure)
    
    return summary
```

**工具集**：
- 核心工具：glob, grep, read, bash
- 分析工具：analyze_code, analyze_log
- 报告工具：generate_report, show_markdown

---

### 3. CodingAgent（编程开发）

**文件位置**：`core_v2/builtin_agents/coding_agent.py`

**核心特性**：
```python
class CodingAgent(AgentBase):
    """
    编程Agent - 自主代码开发
    
    特性：
    1. 自主探索代码库
    2. 智能代码定位
    3. 功能开发与重构
    4. 代码质量检查
    5. 测试生成与执行
    """
    
    # 开发配置
    enable_auto_exploration: bool = True
    enable_code_quality_check: bool = True
    enable_test_generation: bool = False
    
    # 软件工程最佳实践（集成现有SE系统）
    enable_se_best_practices: bool = True
    se_injection_level: str = "standard"  # light/standard/full
    
    # 代码风格
    code_style_rules: List[str] = [
        "Use consistent indentation (4 spaces for Python)",
        "Follow PEP 8 for Python code",
        "Use meaningful variable and function names",
    ]
```

**自主开发流程**：
```python
async def _develop_feature(self, feature_request: str):
    """自主开发功能"""
    
    # 1. 理解需求
    requirements = await self._analyze_requirements(feature_request)
    
    # 2. 探索代码库
    if self.enable_auto_exploration:
        codebase_context = await self._explore_codebase(requirements)
    
    # 3. 定位相关代码
    relevant_files = await self._locate_relevant_code(requirements, codebase_context)
    
    # 4. 设计方案
    design = await self._design_solution(requirements, relevant_files)
    
    # 5. 实现代码
    implementation = await self._implement_code(design)
    
    # 6. 质量检查
    if self.enable_code_quality_check:
        quality_report = await self._check_code_quality(implementation)
    
    # 7. 测试验证
    if self.enable_test_generation:
        test_results = await self._run_tests(implementation)
    
    return implementation
```

**工具集**：
- 开发工具：read, write, edit, bash, grep, glob
- 质量工具：analyze_code, bash（执行测试）
- 辅助工具：question, confirm

---

### 4. FunctionCall原生支持

**实现位置**：在各个Agent的decide方法中

**支持模式**：
```python
async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
    """决策阶段 - 支持原生Function Call"""
    
    # 1. 构建工具定义
    tools = self._build_tool_definitions()
    
    # 2. 调用LLM（支持Function Call）
    response = await self.llm.generate(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ],
        tools=tools,
        tool_choice=self.tool_choice_strategy
    )
    
    # 3. 处理响应
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        return {
            "type": "tool_call",
            "tool_name": tool_call["function"]["name"],
            "tool_args": json.loads(tool_call["function"]["arguments"])
        }
    
    # 4. 直接响应
    return {
        "type": "response",
        "content": response.content
    }
```

**工具定义格式**（OpenAI Function Calling）：
```python
{
    "type": "function",
    "function": {
        "name": "bash",
        "description": "执行Shell命令",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令"
                }
            },
            "required": ["command"]
        }
    }
}
```

---

### 5. 工具加载机制

**默认工具集**（硬编码）：
```python
DEFAULT_TOOLS = {
    "reasoning": ["bash", "read", "write", "grep", "glob", "think"],
    "exploration": ["glob", "grep", "read", "bash", "analyze_code"],
    "coding": ["read", "write", "edit", "bash", "grep", "glob"]
}
```

**配置扩展**（YAML配置文件）：
```yaml
# configs/agents/reasoning_agent.yaml
agent:
  name: "reasoning-agent"
  type: "react_reasoning"
  
tools:
  default:
    - bash
    - read
    - write
    - grep
    - glob
    - think
  
  custom:
    - name: "custom_tool"
      type: "python"
      module: "my_tools.custom"
      function: "custom_tool"
      parameters:
        param1: "value1"
```

**工具注册流程**：
```python
def register_tools_from_config(config_path: str, registry: ToolRegistry):
    """从配置文件注册工具"""
    
    # 1. 加载配置
    config = load_yaml(config_path)
    
    # 2. 注册默认工具
    for tool_name in config["tools"]["default"]:
        registry.register(get_builtin_tool(tool_name))
    
    # 3. 注册自定义工具
    for custom_tool in config["tools"]["custom"]:
        tool = create_custom_tool(custom_tool)
        registry.register(tool)
    
    return registry
```

---

## 文件结构

```
derisk/agent/core_v2/
├── builtin_agents/
│   ├── __init__.py
│   ├── base_builtin_agent.py          # 内置Agent基类
│   ├── react_reasoning_agent.py       # ReAct推理Agent
│   ├── file_explorer_agent.py         # 文件探索Agent
│   ├── coding_agent.py                # 编程Agent
│   └── agent_factory.py               # Agent工厂
│
├── tools_v2/
│   ├── exploration_tools.py           # 探索工具集
│   └── development_tools.py           # 开发工具集
│
└── integration/
    └── agent_loader.py                # Agent加载器

configs/
└── agents/
    ├── reasoning_agent.yaml
    ├── explorer_agent.yaml
    └── coding_agent.yaml
```

---

## 使用示例

### 1. 创建并使用ReActReasoningAgent

```python
from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent

# 创建Agent
agent = ReActReasoningAgent.create(
    name="my-reasoning-agent",
    model="gpt-4",
    api_key="sk-xxx",
    max_steps=30,
    enable_doom_loop_detection=True
)

# 初始化交互
agent.init_interaction(session_id="session-001")

# 执行长程任务
async for chunk in agent.run("帮我完成数据分析项目，从数据清洗到生成报告"):
    print(chunk, end="")
```

### 2. 创建并使用FileExplorerAgent

```python
from derisk.agent.core_v2.builtin_agents import FileExplorerAgent

# 创建Agent
agent = FileExplorerAgent.create(
    name="explorer",
    project_path="/path/to/project"
)

# 探索项目
async for chunk in agent.run("分析这个项目的架构和代码组织"):
    print(chunk, end="")
```

### 3. 创建并使用CodingAgent

```python
from derisk.agent.core_v2.builtin_agents import CodingAgent

# 创建Agent
agent = CodingAgent.create(
    name="coder",
    workspace_path="/path/to/workspace"
)

# 开发功能
async for chunk in agent.run("为用户管理模块添加批量导入功能"):
    print(chunk, end="")
```

### 4. 从配置加载

```python
from derisk.agent.core_v2.builtin_agents import create_agent_from_config

# 从配置文件创建
agent = create_agent_from_config("configs/agents/coding_agent.yaml")

# 使用Agent
async for chunk in agent.run("实现用户登录功能"):
    print(chunk, end="")
```

---

## 实现优先级

### Phase 1：核心Agent实现（优先级：高）
1. ✅ ReActReasoningAgent - 完整迁移ReActMasterAgent
2. ✅ 工具系统集成和FunctionCall支持
3. ✅ 权限系统和交互能力集成

### Phase 2：专用Agent（优先级：中）
1. ✅ FileExplorerAgent - 文件探索Agent
2. ✅ CodingAgent - 编程Agent
3. ✅ 主动探索机制实现

### Phase 3：配置系统（优先级：中）
1. ✅ 工具配置加载器
2. ✅ Agent配置管理
3. ✅ 场景配置扩展

### Phase 4：优化和测试（优先级：低）
1. ✅ 性能优化
2. ✅ 单元测试
3. ✅ 集成测试
4. ✅ 文档完善

---

## 关键技术点

### 1. ReAct循环实现

```python
async def run(self, message: str, stream: bool = True) -> AsyncIterator[str]:
    """主执行循环 - ReAct范式"""
    
    while self._current_step < self.info.max_steps:
        # Think: 思考当前状态
        async for chunk in self.think(message):
            yield chunk
        
        # Decide: 决定下一步动作
        decision = await self.decide(message)
        
        # Act: 执行动作
        if decision["type"] == "tool_call":
            result = await self.execute_tool(
                decision["tool_name"],
                decision["tool_args"]
            )
            message = self._format_tool_result(result)
            
        elif decision["type"] == "response":
            yield decision["content"]
            break
```

### 2. 末日循环检测

```python
class DoomLoopDetector:
    """末日循环检测器"""
    
    def check(self, tool_calls: List[Dict]) -> DoomLoopCheckResult:
        """检测工具调用模式"""
        
        # 检测重复模式
        pattern = self._extract_pattern(tool_calls)
        if self._is_repeating(pattern):
            return DoomLoopCheckResult(
                detected=True,
                pattern=pattern,
                suggestion="请求用户确认"
            )
        
        return DoomLoopCheckResult(detected=False)
```

### 3. 上下文压缩

```python
class SessionCompaction:
    """会话上下文压缩"""
    
    async def compact(self, messages: List[Dict]) -> CompactionResult:
        """压缩上下文"""
        
        # 1. 检测是否需要压缩
        if not self._needs_compaction(messages):
            return CompactionResult(compact_needed=False)
        
        # 2. 提取关键信息
        key_info = await self._extract_key_info(messages)
        
        # 3. 生成摘要
        summary = await self._generate_summary(key_info)
        
        # 4. 构建新的上下文
        new_messages = self._build_compacted_messages(summary, key_info)
        
        return CompactionResult(
            compact_needed=True,
            new_messages=new_messages,
            tokens_saved=...,
        )
```

---

## 预期成果

1. **开箱即用的Agent**：三种场景Agent可直接使用
2. **完整ReAct能力**：长程任务推理和解决
3. **主动探索能力**：自主探索和理解代码库
4. **灵活配置**：支持自定义工具和参数
5. **生产可用**：具备权限、监控、恢复能力

---

## 下一步行动

建议按以下顺序实现：

1. **实现ReActReasoningAgent**（最核心）
   - 迁移ReActMasterAgent的核心组件
   - 适配CoreV2接口
   - 测试基本功能

2. **实现工具加载机制**
   - 默认工具注册
   - 配置加载器
   - 自定义工具支持

3. **实现FileExplorerAgent**
   - 主动探索机制
   - 项目分析能力

4. **实现CodingAgent**
   - 自主开发能力
   - 代码质量检查

5. **完善文档和测试**
   - 使用文档
   - API文档
   - 单元测试
   - 集成测试