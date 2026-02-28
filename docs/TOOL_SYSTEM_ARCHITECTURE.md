# DeRisk Agent 工具体系架构设计

## 一、架构概览

### 1.1 当前架构分析

#### Core 架构
```
derisk/agent/core/
├── base_agent.py          # Agent基类 (102KB, 核心实现)
├── execution_engine.py    # 执行引擎
├── system_tool_registry.py # 系统工具注册
├── action/                # Action动作体系
│   └── base.py           # Action基类
├── parsers/               # 解析器
├── sandbox_manager.py     # 沙箱管理
└── skill.py              # 技能系统
```

#### CoreV2 架构（模块化重构版）
```
derisk/agent/core_v2/
├── agent_harness.py       # 执行框架（持久化、检查点、熔断）
├── agent_base.py          # 简化的Agent基类
├── agent_info.py          # Agent配置模型
├── permission.py          # 权限系统
├── goal.py                # 目标管理
├── interaction.py         # 交互协议
├── model_provider.py      # 模型供应商
├── model_monitor.py       # 模型监控
├── memory_*.py            # 记忆系统
├── sandbox_docker.py      # Docker沙箱
├── reasoning_strategy.py  # 推理策略
├── observability.py       # 可观测性
├── config_manager.py      # 配置管理
└── tools_v2/              # 新工具体系
    ├── tool_base.py       # 工具基类
    ├── builtin_tools.py   # 内置工具
    └── bash_tool.py       # Bash工具
```

#### 现有工具体系
```
derisk/agent/
├── resource/tool/          # 旧工具体系（Resource模式）
│   ├── base.py            # BaseTool, FunctionTool
│   ├── pack.py            # ToolPack
│   ├── api/               # API工具
│   ├── autogpt/           # AutoGPT工具
│   └── mcp/               # MCP协议工具
├── expand/actions/         # Action动作（16种）
│   ├── tool_action.py     # 工具执行Action
│   ├── agent_action.py    # Agent Action
│   ├── sandbox_action.py  # 沙箱Action
│   ├── rag_action.py      # RAG Action
│   └── ...
└── tools_v2/               # 新工具体系
    ├── tool_base.py       # ToolBase, ToolRegistry
    ├── builtin_tools.py   # ReadTool, WriteTool, EditTool, GlobTool, GrepTool
    └── bash_tool.py       # BashTool
```

### 1.2 架构问题与改进方向

| 问题 | 现状 | 改进方向 |
|------|------|----------|
| 工具体系分散 | resource/tool 和 tools_v2 两套体系 | 统一为单一工具框架 |
| 分类不清晰 | 分类模糊，难以管理 | 明确分类：内置/外部/用户交互等 |
| 扩展性不足 | 硬编码注册，缺乏插件机制 | 插件化发现与加载 |
| 配置分散 | 各工具独立配置 | 统一配置中心 |
| 权限不统一 | 部分工具有权限检查 | 统一权限分级体系 |

---

## 二、工具类型分类体系

### 2.1 工具分类（ToolCategory）

```python
class ToolCategory(str, Enum):
    """工具主分类"""
    
    # === 内置系统工具 ===
    BUILTIN = "builtin"             # 核心内置工具(bash, read, write等)
    
    # === 文件操作 ===
    FILE_SYSTEM = "file_system"     # 文件系统(read, write, edit, glob, grep)
    CODE = "code"                   # 代码操作(parse, lint, format)
    
    # === 系统交互 ===
    SHELL = "shell"                 # Shell执行(bash, python, node)
    SANDBOX = "sandbox"             # 沙箱执行(docker, wasm)
    
    # === 用户交互 ===
    USER_INTERACTION = "user_interaction"  # 用户交互(question, confirm, notify)
    VISUALIZATION = "visualization"        # 可视化(chart, table, markdown)
    
    # === 外部服务 ===
    NETWORK = "network"             # 网络请求(http, fetch, web_search)
    DATABASE = "database"           # 数据库(query, execute)
    API = "api"                     # API调用(openapi, graphql)
    MCP = "mcp"                     # MCP协议工具
    
    # === 知识与推理 ===
    SEARCH = "search"               # 搜索(knowledge, vector, web)
    ANALYSIS = "analysis"           # 分析(data, log, metric)
    REASONING = "reasoning"         # 推理(cot, react, plan)
    
    # === 功能扩展 ===
    UTILITY = "utility"             # 工具函数(calc, datetime, json)
    PLUGIN = "plugin"               # 插件工具(动态加载)
    CUSTOM = "custom"               # 自定义工具
```

### 2.2 工具来源类型（ToolSource）

```python
class ToolSource(str, Enum):
    """工具来源"""
    
    CORE = "core"           # 核心内置，不可禁用
    SYSTEM = "system"       # 系统预装，可配置启用/禁用
    EXTENSION = "extension" # 扩展插件，动态加载
    USER = "user"           # 用户自定义
    MCP = "mcp"             # MCP协议接入
    API = "api"             # API动态注册
    AGENT = "agent"         # Agent动态创建
```

### 2.3 风险等级（ToolRiskLevel）

```python
class ToolRiskLevel(str, Enum):
    """工具风险等级"""
    
    SAFE = "safe"           # 安全：只读操作，无副作用
    LOW = "low"             # 低风险：读取文件、搜索
    MEDIUM = "medium"       # 中风险：修改文件、写入数据
    HIGH = "high"           # 高风险：执行命令、删除文件
    CRITICAL = "critical"   # 危险：系统操作、网络暴露
```

### 2.4 执行环境（ToolEnvironment）

```python
class ToolEnvironment(str, Enum):
    """工具执行环境"""
    
    LOCAL = "local"         # 本地执行
    DOCKER = "docker"       # Docker容器
    WASM = "wasm"           # WebAssembly沙箱
    REMOTE = "remote"       # 远程执行
    SANDBOX = "sandbox"     # 安全沙箱
```

---

## 三、工具扩展注册管理架构

### 3.1 整体架构图

```
                            ┌─────────────────────────────────────────┐
                            │          ToolRegistry (全局注册表)        │
                            └─────────────────────────────────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │                         │                         │
              ┌─────▼─────┐            ┌─────▼─────┐            ┌─────▼─────┐
              │CoreTools  │            │ExtTools   │            │UserTools  │
              │Manager    │            │Manager    │            │Manager    │
              └───────────┘            └───────────┘            └───────────┘
                    │                         │                         │
    ┌───────────────┼───────────┐   ┌────────┼────────┐   ┌─────────────┼──────────┐
    │               │           │   │        │        │   │             │          │
┌───▼───┐     ┌────▼───┐   ┌───▼───┐ │  ┌────▼───┐  │   │   ┌────▼───┐  │   ┌────▼───┐
│Builtin│     │System  │   │Plugin │ │  │MCP     │  │   │   │User    │  │   │Agent   │
│Tools  │     │Tools   │   │Tools  │ │  │Tools   │  │   │   │Defined │  │   │Dynamic │
└───────┘     └────────┘   └───────┘ │  └────────┘  │   │   └────────┘  │   └────────┘
                                   │               │
                              ┌────▼────┐    ┌────▼────┐
                              │API      │    │Config   │
                              │Registry │    │Loader   │
                              └─────────┘    └─────────┘
```

### 3.2 核心组件设计

#### 3.2.1 ToolRegistry - 全局工具注册表
```python
class ToolRegistry:
    """
    全局工具注册表
    
    职责：
    1. 工具注册/注销
    2. 工具查找与获取
    3. 工具分类管理
    4. 工具生命周期管理
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolBase] = {}
        self._categories: Dict[ToolCategory, Set[str]] = defaultdict(set)
        self._sources: Dict[ToolSource, Set[str]] = defaultdict(set)
        self._metadata_index: Dict[str, ToolMetadata] = {}
    
    # === 注册操作 ===
    def register(self, tool: ToolBase, source: ToolSource = ToolSource.SYSTEM) -> None
    def unregister(self, tool_name: str) -> bool
    def register_batch(self, tools: List[ToolBase], source: ToolSource) -> None
    
    # === 查询操作 ===
    def get(self, tool_name: str) -> Optional[ToolBase]
    def get_by_category(self, category: ToolCategory) -> List[ToolBase]
    def get_by_source(self, source: ToolSource) -> List[ToolBase]
    def get_by_risk_level(self, level: ToolRiskLevel) -> List[ToolBase]
    def search(self, query: str) -> List[ToolBase]
    
    # === 元数据操作 ===
    def get_metadata(self, tool_name: str) -> Optional[ToolMetadata]
    def list_all_metadata(self) -> List[ToolMetadata]
    
    # === LLM适配 ===
    def to_openai_tools(self) -> List[Dict[str, Any]]
    def to_anthropic_tools(self) -> List[Dict[str, Any]]
    def to_mcp_tools(self) -> List[Dict[str, Any]]
```

#### 3.2.2 ToolBase - 统一工具基类
```python
class ToolBase(ABC):
    """
    统一工具基类
    
    设计原则：
    1. 类型安全 - Pydantic Schema
    2. 元数据丰富 - 分类、风险、权限
    3. 执行统一 - 异步执行、超时控制
    4. 结果标准 - ToolResult格式
    5. 可观测性 - 日志、指标、追踪
    """
    
    # === 核心属性 ===
    metadata: ToolMetadata
    parameters: Dict[str, Any]
    
    # === 抽象方法 ===
    @abstractmethod
    def _define_metadata(self) -> ToolMetadata
    
    @abstractmethod
    def _define_parameters(self) -> Dict[str, Any]
    
    @abstractmethod
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[ToolContext] = None
    ) -> ToolResult
    
    # === 可选生命周期钩子 ===
    async def on_register(self) -> None: ...
    async def on_unregister(self) -> None: ...
    async def pre_execute(self, args: Dict[str, Any]) -> Dict[str, Any]: ...
    async def post_execute(self, result: ToolResult) -> ToolResult: ...
    
    # === 工具方法 ===
    def validate_args(self, args: Dict[str, Any]) -> ValidationResult
    def to_openai_tool(self) -> Dict[str, Any]
    def get_prompt(self, lang: str = "en") -> str
```

#### 3.2.3 ToolMetadata - 工具元数据
```python
class ToolMetadata(BaseModel):
    """工具元数据 - 完整定义"""
    
    # === 基本信息 ===
    name: str                              # 唯一标识
    display_name: str                      # 展示名称
    description: str                       # 详细描述
    version: str = "1.0.0"                # 版本号
    
    # === 分类信息 ===
    category: ToolCategory                 # 工具类别
    subcategory: Optional[str] = None      # 子类别
    source: ToolSource = ToolSource.SYSTEM # 来源
    tags: List[str] = []                   # 标签
    
    # === 风险与权限 ===
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    requires_permission: bool = True       # 是否需要权限
    required_permissions: List[str] = []   # 所需权限列表
    approval_message: Optional[str] = None # 审批提示信息
    
    # === 执行配置 ===
    environment: ToolEnvironment = ToolEnvironment.LOCAL
    timeout: int = 120                     # 默认超时(秒)
    max_retries: int = 0                   # 最大重试次数
    concurrency_limit: int = 1             # 并发限制
    
    # === 输入输出 ===
    input_schema: Dict[str, Any] = {}      # 输入Schema
    output_schema: Dict[str, Any] = {}     # 输出Schema
    examples: List[Dict[str, Any]] = []    # 使用示例
    
    # === 依赖关系 ===
    dependencies: List[str] = []           # 依赖的工具
    conflicts: List[str] = []              # 冲突的工具
    
    # === 文档 ===
    doc_url: Optional[str] = None          # 文档链接
    author: Optional[str] = None           # 作者
    license: Optional[str] = None          # 许可证
```

#### 3.2.4 ToolContext - 执行上下文
```python
class ToolContext(BaseModel):
    """工具执行上下文"""
    
    # === Agent信息 ===
    agent_id: str
    agent_name: str
    conversation_id: str
    message_id: str
    
    # === 用户信息 ===
    user_id: Optional[str] = None
    user_permissions: List[str] = []
    
    # === 执行环境 ===
    working_directory: str = "."
    environment_variables: Dict[str, str] = {}
    sandbox_config: Optional[SandboxConfig] = None
    
    # === 追踪信息 ===
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    
    # === 资源引用 ===
    agent_file_system: Optional[Any] = None
    sandbox_client: Optional[Any] = None
    stream_queue: Optional[asyncio.Queue] = None
    
    # === 配置 ===
    config: Dict[str, Any] = {}
    max_output_bytes: int = 50 * 1024
    max_output_lines: int = 50
```

#### 3.2.5 ToolResult - 统一执行结果
```python
class ToolResult(BaseModel):
    """工具执行结果"""
    
    # === 结果状态 ===
    success: bool
    output: Any                            # 输出内容
    error: Optional[str] = None            # 错误信息
    
    # === 元数据 ===
    tool_name: str
    execution_time_ms: int = 0
    tokens_used: int = 0
    
    # === 扩展信息 ===
    metadata: Dict[str, Any] = {}
    artifacts: List[Artifact] = []         # 产出物（文件、链接等）
    visualizations: List[Visualization] = []  # 可视化数据
    
    # === 流式支持 ===
    is_stream: bool = False
    stream_complete: bool = True
    
    # === 追踪 ===
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
```

### 3.3 工具管理器

#### 3.3.1 CoreToolsManager - 内置工具管理
```python
class CoreToolsManager:
    """
    内置工具管理器
    
    职责：
    1. 加载核心工具
    2. 管理工具生命周期
    3. 提供工具访问接口
    """
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self._core_tools: Dict[str, ToolBase] = {}
    
    def load_core_tools(self) -> None:
        """加载所有核心工具"""
        # 文件系统工具
        self._register_file_tools()
        # Shell工具
        self._register_shell_tools()
        # 搜索工具
        self._register_search_tools()
        # 用户交互工具
        self._register_interaction_tools()
        # 工具函数
        self._register_utility_tools()
    
    def get_tool(self, name: str) -> Optional[ToolBase]:
        return self._core_tools.get(name)
```

#### 3.3.2 ExtensionToolsManager - 扩展工具管理
```python
class ExtensionToolsManager:
    """
    扩展工具管理器
    
    职责：
    1. 插件发现与加载
    2. MCP工具接入
    3. API工具注册
    4. 用户自定义工具管理
    """
    
    def __init__(self, registry: ToolRegistry, config: ToolConfig):
        self.registry = registry
        self.config = config
        self._plugins: Dict[str, PluginInfo] = {}
        self._mcp_clients: Dict[str, MCPClient] = {}
    
    # === 插件管理 ===
    async def discover_plugins(self, plugin_dir: str) -> List[PluginInfo]
    async def load_plugin(self, plugin_path: str) -> bool
    async def unload_plugin(self, plugin_name: str) -> bool
    async def reload_plugin(self, plugin_name: str) -> bool
    
    # === MCP工具 ===
    async def connect_mcp_server(self, config: MCPConfig) -> bool
    async def load_mcp_tools(self, server_name: str) -> List[ToolBase]
    async def disconnect_mcp_server(self, server_name: str) -> bool
    
    # === API工具 ===
    async def register_from_openapi(self, spec_url: str) -> List[ToolBase]
    async def register_from_graphql(self, endpoint: str) -> List[ToolBase]
    
    # === 用户工具 ===
    async def register_user_tool(self, tool_def: UserToolDefinition) -> ToolBase
    async def update_user_tool(self, tool_name: str, tool_def: UserToolDefinition) -> bool
    async def delete_user_tool(self, tool_name: str) -> bool
```

---

## 四、工具配置开发体系

### 4.1 配置系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     ToolConfiguration                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐        │
│  │ GlobalConfig  │  │ AgentConfig   │  │ UserConfig    │        │
│  │ (全局配置)    │  │ (Agent级)     │  │ (用户级)      │        │
│  └───────────────┘  └───────────────┘  └───────────────┘        │
│         │                  │                  │                  │
│         └──────────────┬───┴──────────────────┘                  │
│                        │                                          │
│                        ▼                                          │
│              ┌─────────────────┐                                  │
│              │ ConfigMerger    │                                  │
│              │ (配置合并)      │                                  │
│              └─────────────────┘                                  │
│                        │                                          │
│         ┌──────────────┼──────────────┐                          │
│         │              │              │                          │
│    ┌────▼────┐    ┌────▼────┐   ┌────▼────┐                     │
│    │Tool     │    │Execution│   │Permission│                     │
│    │Settings │    │Settings │   │Settings  │                     │
│    └─────────┘    └─────────┘   └──────────┘                     │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 配置模型

#### 4.2.1 全局工具配置
```python
class GlobalToolConfig(BaseModel):
    """全局工具配置"""
    
    # === 启用配置 ===
    enabled_categories: List[ToolCategory] = list(ToolCategory)
    disabled_tools: List[str] = []
    
    # === 默认配置 ===
    default_timeout: int = 120
    default_environment: ToolEnvironment = ToolEnvironment.LOCAL
    default_risk_approval: Dict[ToolRiskLevel, bool] = {
        ToolRiskLevel.SAFE: False,
        ToolRiskLevel.LOW: False,
        ToolRiskLevel.MEDIUM: True,
        ToolRiskLevel.HIGH: True,
        ToolRiskLevel.CRITICAL: True,
    }
    
    # === 执行配置 ===
    max_concurrent_tools: int = 5
    max_output_size: int = 100 * 1024
    enable_caching: bool = True
    cache_ttl: int = 3600
    
    # === 沙箱配置 ===
    sandbox_enabled: bool = False
    docker_image: str = "python:3.11"
    memory_limit: str = "512m"
    
    # === 日志配置 ===
    log_level: str = "INFO"
    log_tool_calls: bool = True
    log_arguments: bool = True  # 敏感参数脱敏
```

#### 4.2.2 Agent级别配置
```python
class AgentToolConfig(BaseModel):
    """Agent级工具配置"""
    
    agent_id: str
    agent_name: str
    
    # === 可用工具 ===
    available_tools: List[str] = []         # 空则全部可用
    excluded_tools: List[str] = []          # 排除的工具
    
    # === 工具参数覆盖 ===
    tool_overrides: Dict[str, Dict[str, Any]] = {}
    
    # === 执行策略 ===
    execution_mode: str = "sequential"      # sequential | parallel
    max_retries: int = 0
    retry_delay: float = 1.0
    
    # === 权限配置 ===
    auto_approve_safe: bool = True
    auto_approve_low_risk: bool = False
    require_approval_high_risk: bool = True
```

### 4.3 工具开发规范

#### 4.3.1 工具定义模板
```python
from derisk.agent.tools_v2 import (
    ToolBase, ToolMetadata, ToolResult, ToolContext,
    ToolCategory, ToolRiskLevel, ToolSource, ToolEnvironment,
    tool, register_tool
)

# === 方式一：类定义（推荐复杂工具） ===
class MyCustomTool(ToolBase):
    """自定义工具示例"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="my_custom_tool",
            display_name="我的自定义工具",
            description="执行特定功能",
            category=ToolCategory.UTILITY,
            subcategory="data",
            source=ToolSource.USER,
            risk_level=ToolRiskLevel.LOW,
            tags=["custom", "data"],
            examples=[
                {
                    "input": {"param1": "value1"},
                    "output": "result",
                    "description": "示例用法"
                }
            ]
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "参数1说明"
                },
                "param2": {
                    "type": "integer",
                    "default": 10,
                    "description": "参数2说明"
                }
            },
            "required": ["param1"]
        }
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        # 1. 参数提取与验证
        param1 = args["param1"]
        param2 = args.get("param2", 10)
        
        # 2. 执行前钩子
        args = await self.pre_execute(args)
        
        try:
            # 3. 核心逻辑
            result = await self._do_work(param1, param2)
            
            # 4. 返回结果
            return ToolResult(
                success=True,
                output=result,
                tool_name=self.metadata.name,
                metadata={"param1": param1}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                tool_name=self.metadata.name
            )
    
    async def _do_work(self, param1: str, param2: int) -> str:
        # 实际工作逻辑
        return f"processed: {param1} with {param2}"


# === 方式二：装饰器定义（简单工具） ===
@tool(
    name="simple_tool",
    description="简单工具",
    category=ToolCategory.UTILITY,
    risk_level=ToolRiskLevel.SAFE
)
async def simple_tool(input_text: str) -> str:
    """简单工具示例"""
    return f"processed: {input_text}"


# === 方式三：配置定义（声明式） ===
tool_config = {
    "name": "config_tool",
    "description": "配置化工具",
    "category": "utility",
    "parameters": {
        "type": "object",
        "properties": {
            "input": {"type": "string"}
        }
    },
    "handler": "module.handler_function"  # 指向处理函数
}
```

#### 4.3.2 工具注册方式

```python
from derisk.agent.tools_v2 import tool_registry, ToolSource

# === 注册实例 ===
tool_registry.register(MyCustomTool(), source=ToolSource.USER)

# === 注册装饰器工具 ===
tool_registry.register(simple_tool._tool, source=ToolSource.USER)

# === 批量注册 ===
tools = [Tool1(), Tool2(), Tool3()]
tool_registry.register_batch(tools, source=ToolSource.EXTENSION)

# === 从配置注册 ===
tool_registry.register_from_config(tool_config)

# === 从模块自动发现 ===
tool_registry.discover_and_register("my_tools_package")
```

### 4.4 插件系统设计

#### 4.4.1 插件结构
```
my_plugin/
├── plugin.yaml          # 插件配置
├── __init__.py          # 插件入口
├── tools/               # 工具定义
│   ├── __init__.py
│   ├── tool1.py
│   └── tool2.py
├── schemas/             # 参数Schema
│   └── tool1_schema.json
├── tests/               # 测试
│   └── test_tools.py
└── docs/                # 文档
    └── README.md
```

#### 4.4.2 插件配置 (plugin.yaml)
```yaml
name: my_plugin
version: 1.0.0
description: 我的自定义插件
author: Your Name
license: MIT

# 兼容性
min_derisk_version: "0.1.0"
max_derisk_version: "1.0.0"

# 依赖
dependencies:
  - requests>=2.28.0
  - numpy>=1.20.0

# 工具配置
tools:
  - name: tool1
    module: tools.tool1
    enabled: true
  - name: tool2
    module: tools.tool2
    enabled: true
    config:
      timeout: 60

# 默认配置
default_config:
  api_key: ""
  base_url: "https://api.example.com"

# 权限声明
permissions:
  - network_access
  - file_read
```

#### 4.4.3 插件加载器
```python
class PluginLoader:
    """插件加载器"""
    
    async def load_plugin(self, plugin_path: str) -> LoadedPlugin:
        """加载插件"""
        # 1. 解析配置
        config = self._parse_plugin_config(plugin_path)
        
        # 2. 检查兼容性
        self._check_compatibility(config)
        
        # 3. 安装依赖
        await self._install_dependencies(config.dependencies)
        
        # 4. 加载工具
        tools = await self._load_tools(config.tools)
        
        # 5. 注册工具
        for tool in tools:
            self.registry.register(tool, source=ToolSource.EXTENSION)
        
        return LoadedPlugin(config=config, tools=tools)
```

---

## 五、内置工具覆盖清单

### 5.1 参考 OpenCode 工具体系

| 工具名 | 类别 | 风险等级 | 功能 |
|--------|------|----------|------|
| bash | SHELL | HIGH | 执行Shell命令 |
| read | FILE_SYSTEM | LOW | 读取文件 |
| write | FILE_SYSTEM | MEDIUM | 写入文件 |
| edit | FILE_SYSTEM | MEDIUM | 编辑文件 |
| glob | FILE_SYSTEM | LOW | 文件模式匹配 |
| grep | SEARCH | LOW | 内容搜索 |
| question | USER_INTERACTION | SAFE | 用户提问 |
| task | UTILITY | SAFE | 任务管理 |
| skill | UTILITY | LOW | 技能调用 |
| webfetch | NETWORK | MEDIUM | 网页获取 |
| gemini_quota | UTILITY | SAFE | 配额查询 |

### 5.2 参考 OpenClaw 工具体系

| 工具名 | 类别 | 风险等级 | 功能 |
|--------|------|----------|------|
| execute_code | CODE | HIGH | 代码执行 |
| execute_bash | SHELL | HIGH | Bash执行 |
| think | REASONING | SAFE | 思考推理 |
| finish | UTILITY | SAFE | 任务完成 |
| delegate_work | AGENT | MEDIUM | 任务委派 |
| ask_human | USER_INTERACTION | SAFE | 人工协助 |
| list_directory | FILE_SYSTEM | LOW | 列出目录 |
| create_file | FILE_SYSTEM | MEDIUM | 创建文件 |
| open_file | FILE_SYSTEM | LOW | 打开文件 |
| search_files | SEARCH | LOW | 搜索文件 |
| web_search | NETWORK | MEDIUM | 网络搜索 |
| analyze | ANALYSIS | LOW | 数据分析 |
| image_gen | UTILITY | MEDIUM | 图像生成 |

### 5.3 完整内置工具清单

#### 5.3.1 文件系统工具
```python
FILE_SYSTEM_TOOLS = [
    # 基础操作
    "read",           # 读取文件
    "write",          # 写入文件
    "edit",           # 编辑文件（替换）
    "append",         # 追加内容
    "delete",         # 删除文件
    "copy",           # 复制文件
    "move",           # 移动文件
    
    # 目录操作
    "list_dir",       # 列出目录
    "create_dir",     # 创建目录
    "delete_dir",     # 删除目录
    
    # 搜索
    "glob",           # 文件模式匹配
    "grep",           # 内容搜索
    "find",           # 文件查找
    
    # 信息
    "file_info",      # 文件信息
    "file_diff",      # 文件对比
]
```

#### 5.3.2 Shell与代码执行工具
```python
EXECUTION_TOOLS = [
    # Shell执行
    "bash",           # Bash命令
    "python",         # Python代码
    "node",           # Node.js代码
    "shell",          # 通用Shell
    
    # 沙箱执行
    "docker_exec",    # Docker容器执行
    "wasm_exec",      # WebAssembly执行
    
    # 代码工具
    "code_lint",      # 代码检查
    "code_format",    # 代码格式化
    "code_test",      # 运行测试
]
```

#### 5.3.3 用户交互工具
```python
INTERACTION_TOOLS = [
    # 问答
    "question",       # 提问用户（选项）
    "ask",            # 开放式提问
    "confirm",        # 确认操作
    
    # 通知
    "notify",         # 通知消息
    "progress",       # 进度更新
    
    # 文件选择
    "file_upload",    # 文件上传
    "file_select",    # 文件选择
]
```

#### 5.3.4 搜索与知识工具
```python
SEARCH_TOOLS = [
    # 文件搜索
    "search_code",    # 代码搜索
    "search_file",    # 文件搜索
    "search_symbol",  # 符号搜索
    
    # 知识检索
    "search_knowledge",  # 知识库搜索
    "search_web",     # 网络搜索
    "search_vector",  # 向量搜索
    
    # 信息获取
    "web_fetch",      # 网页获取
    "api_call",       # API调用
]
```

#### 5.3.5 分析与可视化工具
```python
ANALYSIS_TOOLS = [
    # 数据分析
    "analyze_data",   # 数据分析
    "analyze_log",    # 日志分析
    "analyze_code",   # 代码分析
    
    # 可视化
    "show_chart",     # 图表展示
    "show_table",     # 表格展示
    "show_markdown",  # Markdown渲染
    
    # 报告
    "generate_report",  # 生成报告
]
```

#### 5.3.6 工具函数
```python
UTILITY_TOOLS = [
    # 计算
    "calculate",      # 数学计算
    "datetime",       # 日期时间
    "json_tool",      # JSON处理
    "text_process",   # 文本处理
    
    # 任务管理
    "task_create",    # 创建任务
    "task_list",      # 列出任务
    "task_complete",  # 完成任务
    
    # 存储
    "store_get",      # 获取存储
    "store_set",      # 设置存储
]
```

---

## 六、迁移与整合计划

### 6.1 迁移策略

#### 第一阶段：统一接口层
```python
# 创建统一接口，兼容现有实现
class UnifiedToolInterface:
    """统一工具接口，提供向后兼容"""
    
    @staticmethod
    def from_resource_tool(old_tool: 'BaseTool') -> ToolBase:
        """从旧资源工具转换"""
        pass
    
    @staticmethod
    def from_action(action: 'Action') -> ToolBase:
        """从Action转换"""
        pass
```

#### 第二阶段：逐步迁移
1. 新工具使用新框架
2. 旧工具添加适配层
3. 核心工具优先迁移
4. 扩展工具按需迁移

#### 第三阶段：清理
1. 移除废弃代码
2. 统一导入路径
3. 更新文档

### 6.2 兼容性保证

```python
# 向后兼容层
class LegacyToolAdapter(ToolBase):
    """旧工具适配器"""
    
    def __init__(self, legacy_tool: 'BaseTool'):
        self.legacy_tool = legacy_tool
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=self.legacy_tool.name,
            description=self.legacy_tool.description,
            # ... 转换其他字段
        )
    
    async def execute(self, args: Dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult:
        if self.legacy_tool.is_async:
            output = await self.legacy_tool.async_execute(**args)
        else:
            output = self.legacy_tool.execute(**args)
        
        return ToolResult(success=True, output=output, tool_name=self.legacy_tool.name)
```

### 6.3 推荐目录结构

```
derisk/agent/tools/
├── __init__.py              # 统一入口
├── base.py                  # 基类定义
├── registry.py              # 注册表
├── context.py               # 执行上下文
├── result.py                # 结果定义
├── metadata.py              # 元数据定义
├── config.py                # 配置模型
│
├── builtin/                 # 内置工具
│   ├── __init__.py
│   ├── file_system/         # 文件系统工具
│   │   ├── __init__.py
│   │   ├── read.py
│   │   ├── write.py
│   │   ├── edit.py
│   │   ├── glob.py
│   │   └── grep.py
│   ├── shell/               # Shell工具
│   │   ├── __init__.py
│   │   ├── bash.py
│   │   ├── python.py
│   │   └── docker.py
│   ├── interaction/         # 交互工具
│   │   ├── __init__.py
│   │   ├── question.py
│   │   ├── confirm.py
│   │   └── notify.py
│   ├── search/              # 搜索工具
│   │   ├── __init__.py
│   │   ├── web_search.py
│   │   └── code_search.py
│   ├── analysis/            # 分析工具
│   │   └── ...
│   └── utility/             # 工具函数
│       └── ...
│
├── extension/               # 扩展管理
│   ├── __init__.py
│   ├── plugin_loader.py     # 插件加载器
│   ├── mcp_manager.py       # MCP管理
│   └── api_registry.py      # API注册
│
├── adapters/                # 兼容适配器
│   ├── __init__.py
│   ├── resource_adapter.py  # 旧资源工具适配
│   └── action_adapter.py    # Action适配
│
└── utils/                   # 工具函数
    ├── __init__.py
    ├── schema_utils.py      # Schema工具
    ├── validation.py        # 验证工具
    └── formatting.py        # 格式化工具
```

---

## 七、实现路线图

### 7.1 Phase 1: 核心框架（1-2周）
- [ ] 统一ToolBase基类
- [ ] ToolRegistry注册表
- [ ] ToolMetadata元数据
- [ ] ToolContext上下文
- [ ] ToolResult结果

### 7.2 Phase 2: 内置工具迁移（2-3周）
- [ ] 文件系统工具迁移
- [ ] Shell工具迁移
- [ ] 搜索工具迁移
- [ ] 交互工具实现
- [ ] 工具函数实现

### 7.3 Phase 3: 扩展系统（2周）
- [ ] 插件加载器
- [ ] MCP管理器
- [ ] API注册器
- [ ] 配置系统

### 7.4 Phase 4: 兼容与测试（1周）
- [ ] 适配器实现
- [ ] 集成测试
- [ ] 文档编写
- [ ] 性能优化

---

## 八、附录

### A. 完整代码示例

参见：`/packages/derisk-core/src/derisk/agent/tools/` 目录

### B. 配置示例

参见：`/config/tools.yaml`

### C. 插件开发指南

参见：`/docs/PLUGIN_DEVELOPMENT.md`