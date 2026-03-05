# Core V2 工具架构与可视化机制详解

> 最后更新: 2026-03-03
> 状态: 活跃文档

本文档详细说明 Core V2 的工具架构、文件系统集成以及可视化机制。

---

## 一、工具架构总览

### 1.1 工具系统架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Tools V2 架构总览                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                      ToolRegistry (工具注册中心)                    │ │
│  │                                                                     │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │ │
│  │  │ 注册管理     │  │ 查询接口     │  │ OpenAI 格式转换          │  │ │
│  │  │ register()   │  │ get()        │  │ get_openai_tools()       │  │ │
│  │  │ unregister() │  │ list_all()   │  │                          │  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                    │                                     │
│         ┌──────────────────────────┼──────────────────────────┐         │
│         ▼                          ▼                          ▼         │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐   │
│  │ 内置工具    │           │ 交互工具    │           │ 网络工具    │   │
│  │             │           │             │           │             │   │
│  │ • bash      │           │ • question  │           │ • webfetch  │   │
│  │ • read      │           │ • confirm   │           │ • web_search│   │
│  │ • write     │           │ • notify    │           │ • api_call  │   │
│  │ • search    │           │ • progress  │           │ • graphql   │   │
│  │ • list_files│           │ • ask_human │           │             │   │
│  │ • think     │           │ • file_select│          │             │   │
│  └─────────────┘           └─────────────┘           └─────────────┘   │
│                                                                          │
│         ┌──────────────────────────┼──────────────────────────┐         │
│         ▼                          ▼                          ▼         │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐   │
│  │ Action适配器│           │ MCP适配器   │           │ Task工具    │   │
│  │             │           │             │           │             │   │
│  │ V1 Action   │           │ MCP Protocol│           │ 子Agent调用 │   │
│  │ 体系迁移    │           │ 工具集成    │           │             │   │
│  │             │           │             │           │             │   │
│  │ActionTool   │           │MCPTool      │           │TaskTool     │   │
│  │Adapter      │           │Adapter      │           │             │   │
│  └─────────────┘           └─────────────┘           └─────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 目录结构

```
tools_v2/
├── __init__.py            # 模块入口，统一注册接口
├── tool_base.py           # 工具基类和注册系统
├── builtin_tools.py       # 内置工具 (bash, read, write, search)
├── interaction_tools.py   # 用户交互工具
├── network_tools.py       # 网络工具
├── mcp_tools.py           # MCP 协议工具适配器
├── action_tools.py        # Action 体系迁移适配器
├── analysis_tools.py      # 分析可视化工具
└── task_tools.py          # 子 Agent 调用工具
```

---

## 二、工具基础架构

### 2.1 核心数据结构

文件位置: `tools_v2/tool_base.py`

#### ToolMetadata (工具元数据)

```python
@dataclass
class ToolMetadata:
    """工具元数据"""
    name: str                           # 工具名称 (唯一标识)
    description: str                    # 工具描述 (给 LLM 看)
    parameters: Dict[str, Any] = field(default_factory=dict)  # OpenAI 格式参数
    requires_permission: bool = False   # 是否需要用户许可
    dangerous: bool = False             # 是否危险操作
    category: str = "general"           # 类别标签
    version: str = "1.0.0"             # 版本号
    examples: List[Dict] = field(default_factory=list)  # 使用示例
```

#### ToolResult (工具执行结果)

```python
@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool                       # 执行是否成功
    output: str                         # 输出内容
    error: Optional[str] = None         # 错误信息
    metadata: Dict[str, Any] = field(default_factory=dict)  # 附加元数据
```

#### ToolBase (抽象基类)

```python
class ToolBase(ABC):
    """工具抽象基类"""

    def __init__(self):
        self._metadata: Optional[ToolMetadata] = None
        self._define_metadata()

    @property
    def metadata(self) -> ToolMetadata:
        """获取工具元数据"""
        if self._metadata is None:
            raise ValueError("Tool metadata not defined")
        return self._metadata

    @abstractmethod
    def _define_metadata(self) -> ToolMetadata:
        """定义工具元数据 (子类实现)"""
        pass

    def _define_parameters(self) -> Optional[Dict[str, Any]]:
        """定义参数 schema (可选重写)"""
        return None

    def get_openai_spec(self) -> Dict[str, Any]:
        """获取 OpenAI function calling 格式定义"""
        params = self._define_parameters() or self.metadata.parameters
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": params,
            }
        }

    @abstractmethod
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict] = None,
    ) -> ToolResult:
        """执行工具 (子类实现)"""
        pass

    def validate_args(self, args: Dict[str, Any]) -> bool:
        """验证参数 (可选重写)"""
        return True
```

### 2.2 ToolRegistry (工具注册中心)

```python
class ToolRegistry:
    """工具注册中心"""

    def __init__(self):
        self._tools: Dict[str, ToolBase] = {}
        self._categories: Dict[str, Set[str]] = defaultdict(set)

    def register(self, tool: ToolBase) -> "ToolRegistry":
        """注册工具"""
        name = tool.metadata.name
        self._tools[name] = tool
        self._categories[tool.metadata.category].add(name)
        return self

    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            tool = self._tools[name]
            self._categories[tool.metadata.category].discard(name)
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Optional[ToolBase]:
        """获取工具"""
        return self._tools.get(name)

    def list_all(self) -> List[ToolBase]:
        """列出所有工具"""
        return list(self._tools.values())

    def list_by_category(self, category: str) -> List[ToolBase]:
        """按类别列出工具"""
        return [self._tools[name] for name in self._categories.get(category, [])]

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """获取 OpenAI 格式工具列表 (给 LLM API 使用)"""
        return [tool.get_openai_spec() for tool in self._tools.values()]

    async def execute(
        self,
        name: str,
        args: Dict[str, Any],
        context: Optional[Dict] = None,
    ) -> ToolResult:
        """执行工具"""
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool '{name}' not found",
            )

        # 参数验证
        if not tool.validate_args(args):
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid arguments for tool '{name}'",
            )

        return await tool.execute(args, context)

    def register_function(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: Optional[Dict] = None,
        requires_permission: bool = False,
        dangerous: bool = False,
    ) -> "ToolRegistry":
        """通过函数快速注册工具"""
        tool = FunctionTool(
            name=name,
            description=description,
            func=func,
            parameters=parameters or {},
            requires_permission=requires_permission,
            dangerous=dangerous,
        )
        return self.register(tool)
```

### 2.3 @tool 装饰器

```python
def tool(
    name: str,
    description: str,
    parameters: Optional[Dict] = None,
    requires_permission: bool = False,
    dangerous: bool = False,
):
    """将函数转换为工具的装饰器"""

    def decorator(func: Callable):
        class DecoratedTool(ToolBase):
            def _define_metadata(self):
                return ToolMetadata(
                    name=name,
                    description=description,
                    parameters=parameters or {},
                    requires_permission=requires_permission,
                    dangerous=dangerous,
                )

            async def execute(self, args: Dict, context: Optional[Dict] = None):
                try:
                    if asyncio.iscoroutinefunction(func):
                        result = await func(**args)
                    else:
                        result = func(**args)
                    return ToolResult(success=True, output=str(result))
                except Exception as e:
                    return ToolResult(success=False, output="", error=str(e))

        return DecoratedTool()

    return decorator


# 使用示例
@tool(
    name="calculate",
    description="执行数学计算",
    parameters={
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "数学表达式"},
        },
        "required": ["expression"],
    },
)
async def calculate(expression: str) -> float:
    """执行数学计算"""
    return eval(expression)  # 注意: 实际使用需要安全检查
```

---

## 三、内置工具详解

文件位置: `tools_v2/builtin_tools.py`

### 3.1 工具列表和权限

| 工具名称 | 类别 | 需许可 | 危险 | 功能描述 |
|---------|------|-------|------|---------|
| `bash` | system | ✅ Yes | ✅ Yes | 执行 shell 命令 |
| `read` | file | ❌ No | ❌ No | 读取文件内容 |
| `write` | file | ✅ Yes | ✅ Yes | 写入/追加文件 |
| `search` | search | ❌ No | ❌ No | 文件内容搜索 (支持正则) |
| `list_files` | file | ❌ No | ❌ No | 列出目录文件 |
| `think` | reasoning | ❌ No | ❌ No | 记录思考过程 |

### 3.2 Bash 工具实现

```python
class BashTool(ToolBase):
    """Shell 命令执行工具"""

    # 禁止的危险命令模式
    FORBIDDEN_PATTERNS = [
        r"rm\s+-rf\s+/",
        r"rm\s+-rf\s+~",
        r"mkfs",
        r"dd\s+if=",
        r">\s*/dev/sd",
        r"chmod\s+777\s+/",
        r":()\s*{\s*:\|:&\s*};:",  # fork bomb
        r"wget\s+.*\s*\|\s*bash",
        r"curl\s+.*\s*\|\s*bash",
    ]

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="bash",
            description="Execute shell commands with safety checks",
            category="system",
            requires_permission=True,
            dangerous=True,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 120)",
                    "default": 120,
                },
            },
            "required": ["command"],
        }

    def _is_safe_command(self, command: str) -> bool:
        """检查命令安全性"""
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, command):
                return False
        return True

    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict] = None,
    ) -> ToolResult:
        command = args.get("command", "")
        timeout = args.get("timeout", 120)

        # 安全检查
        if not self._is_safe_command(command):
            return ToolResult(
                success=False,
                output="",
                error=f"Command blocked: potentially dangerous operation",
            )

        try:
            # 执行命令
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            output = stdout.decode() + stderr.decode()

            return ToolResult(
                success=process.returncode == 0,
                output=output,
                metadata={"return_code": process.returncode},
            )

        except asyncio.TimeoutError:
            process.kill()
            return ToolResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout} seconds",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
```

### 3.3 Read 工具实现

```python
class ReadTool(ToolBase):
    """文件读取工具"""

    MAX_FILE_SIZE = 50 * 1024  # 50KB
    MAX_OUTPUT_LENGTH = 20000  # 字符

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="read",
            description="Read file contents with line range selection",
            category="file",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to read",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line (1-indexed, optional)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line (1-indexed, optional)",
                },
            },
            "required": ["file_path"],
        }

    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict] = None,
    ) -> ToolResult:
        file_path = Path(args["file_path"])
        start_line = args.get("start_line")
        end_line = args.get("end_line")

        # 检查文件是否存在
        if not file_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"File not found: {file_path}",
            )

        # 检查文件大小
        if file_path.stat().st_size > self.MAX_FILE_SIZE:
            return ToolResult(
                success=False,
                output="",
                error=f"File too large (>{self.MAX_FILE_SIZE} bytes). Use search instead.",
            )

        try:
            lines = file_path.read_text().splitlines()

            # 行范围选择
            if start_line is not None:
                lines = lines[start_line - 1:]
            if end_line is not None:
                lines = lines[:end_line - (start_line or 1) + 1]

            # 添加行号
            output_lines = []
            for i, line in enumerate(lines, start=start_line or 1):
                output_lines.append(f"{i:6}\t{line}")

            output = "\n".join(output_lines)

            # 截断检查
            if len(output) > self.MAX_OUTPUT_LENGTH:
                output = output[:self.MAX_OUTPUT_LENGTH] + "\n... [truncated]"

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "file_path": str(file_path),
                    "total_lines": len(lines),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
```

### 3.4 Search 工具实现

```python
class SearchTool(ToolBase):
    """文件内容搜索工具"""

    MAX_RESULTS = 100

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="search",
            description="Search for patterns in files using regex",
            category="search",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: current)",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob pattern for files (default: *)",
                },
                "ignore_case": {
                    "type": "boolean",
                    "description": "Case insensitive search",
                    "default": False,
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict] = None,
    ) -> ToolResult:
        pattern = args["pattern"]
        path = Path(args.get("path", "."))
        file_pattern = args.get("file_pattern", "*")
        ignore_case = args.get("ignore_case", False)

        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid regex: {e}",
            )

        results = []
        for file_path in path.rglob(file_pattern):
            if not file_path.is_file():
                continue
            if file_path.suffix in [".pyc", ".pyo", ".so", ".dylib"]:
                continue

            try:
                for i, line in enumerate(file_path.read_text().splitlines(), 1):
                    if regex.search(line):
                        results.append(f"{file_path}:{i}: {line.strip()}")
                        if len(results) >= self.MAX_RESULTS:
                            break
            except (UnicodeDecodeError, PermissionError):
                continue

            if len(results) >= self.MAX_RESULTS:
                break

        output = "\n".join(results)
        if len(results) >= self.MAX_RESULTS:
            output += f"\n... [truncated at {self.MAX_RESULTS} results]"

        return ToolResult(
            success=True,
            output=output or "No matches found",
            metadata={"result_count": len(results)},
        )
```

---

## 四、用户交互工具

文件位置: `tools_v2/interaction_tools.py`

### 4.1 工具列表

| 工具名称 | 功能 | 特殊特性 |
|---------|------|---------|
| `question` | 多选项提问 | 支持单选/多选、交互管理器集成 |
| `confirm` | 确认操作 | 超时控制、默认值 |
| `notify` | 通知消息 | 等级分级 (info/warning/error/success) |
| `progress` | 进度更新 | 进度条渲染、阶段标记 |
| `ask_human` | 请求人工协助 | 紧急度分级 |
| `file_select` | 文件选择 | 文件类型过滤、多选支持 |

### 4.2 Question Tool 实现

```python
class QuestionTool(ToolBase):
    """多选项提问工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="question",
            description="Ask user questions with multiple choice options",
            category="interaction",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "header": {"type": "string", "maxLength": 30},
                            "options": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                },
                            },
                            "multiple": {"type": "boolean", "default": False},
                        },
                        "required": ["question", "header", "options"],
                    },
                },
            },
            "required": ["questions"],
        }

    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict] = None,
    ) -> ToolResult:
        questions = args["questions"]

        # 获取交互管理器 (从 context)
        interaction_manager = context.get("interaction_manager") if context else None

        if interaction_manager:
            # 通过交互管理器发送问题
            answers = await interaction_manager.ask_questions(questions)
        else:
            # 简单控制台输入
            answers = []
            for q in questions:
                print(f"\n{q['question']}")
                for i, opt in enumerate(q['options']):
                    print(f"  {i + 1}. {opt['label']} - {opt['description']}")

                if q.get('multiple'):
                    selection = input("Enter choices (comma-separated): ")
                    selected = [q['options'][int(s.strip()) - 1]['label']
                               for s in selection.split(',')]
                else:
                    selection = input("Enter choice: ")
                    selected = q['options'][int(selection) - 1]['label']

                answers.append({"question": q['header'], "answer": selected})

        return ToolResult(
            success=True,
            output=json.dumps(answers),
            metadata={"answers": answers},
        )
```

### 4.3 Progress Tool 实现

```python
class ProgressTool(ToolBase):
    """进度更新工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="progress",
            description="Update task progress with visual progress bar",
            category="interaction",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "progress": {
                    "type": "number",
                    "description": "Progress percentage (0-100)",
                    "minimum": 0,
                    "maximum": 100,
                },
                "message": {
                    "type": "string",
                    "description": "Status message",
                },
                "stage": {
                    "type": "string",
                    "description": "Current stage name",
                },
            },
            "required": ["progress"],
        }

    def _render_progress_bar(self, percentage: float, width: int = 20) -> str:
        """渲染进度条"""
        filled = int(percentage / 100 * width)
        bar = '█' * filled + '░' * (width - filled)
        return f"[{bar}] {percentage:.0f}%"

    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict] = None,
    ) -> ToolResult:
        progress = args["progress"]
        message = args.get("message", "")
        stage = args.get("stage", "")

        # 渲染进度条
        progress_bar = self._render_progress_bar(progress)

        # 构建输出
        output_parts = [progress_bar]
        if stage:
            output_parts.append(f"Stage: {stage}")
        if message:
            output_parts.append(message)

        output = "\n".join(output_parts)

        # 通知前端 (通过 progress_broadcaster)
        progress_broadcaster = context.get("progress_broadcaster") if context else None
        if progress_broadcaster:
            await progress_broadcaster.broadcast({
                "type": "progress",
                "progress": progress,
                "message": message,
                "stage": stage,
            })

        return ToolResult(
            success=True,
            output=output,
            metadata={"progress": progress, "stage": stage},
        )
```

---

## 五、Action 迁移适配器

文件位置: `tools_v2/action_tools.py`

### 5.1 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                  Action → Tool 适配架构                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  V1 Action 体系                         V2 Tool 体系             │
│  ┌──────────────────┐                  ┌──────────────────┐     │
│  │ Action 基类       │                  │ ToolBase         │     │
│  │ - init_action()  │                  │ - _define_meta() │     │
│  │ - before_run()   │   适配转换       │ - execute()      │     │
│  │ - run()          │ ───────────────▶ │                  │     │
│  │ - _render        │                  │                  │     │
│  └──────────────────┘                  └──────────────────┘     │
│                                                                  │
│  具体实现:                                                       │
│  ┌──────────────────┐                  ┌──────────────────┐     │
│  │ ToolAction       │                  │ ActionToolAdapter│     │
│  │ CodeAction       │ ───────────────▶ │                  │     │
│  │ KnowledgeAction  │                  │ 包装 Action 实例 │     │
│  │ RagAction        │                  │ 提供统一接口     │     │
│  └──────────────────┘                  └──────────────────┘     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 ActionToolAdapter 实现

```python
class ActionToolAdapter(ToolBase):
    """Action 到 Tool 的适配器"""

    def __init__(
        self,
        action: Any,
        action_name: Optional[str] = None,
        resource: Optional[Any] = None,
    ):
        self._action = action
        self._action_name = action_name or action.__class__.__name__
        self._resource = resource
        self._render_protocol = getattr(action, "_render", None)
        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=f"action_{self._action_name.lower()}",
            description=self._extract_description(),
            parameters=self._extract_action_parameters(),
            category="action",
        )

    def _extract_description(self) -> str:
        """从 Action 提取描述"""
        # 尝试多种来源
        if hasattr(self._action, '__doc__') and self._action.__doc__:
            return self._action.__doc__.strip()
        if hasattr(self._action, 'description'):
            return self._action.description
        return f"Action: {self._action_name}"

    def _extract_action_parameters(self) -> Dict[str, Any]:
        """从 Action 的 ai_out_schema_json 提取参数"""
        if hasattr(self._action, 'ai_out_schema_json'):
            return self._action.ai_out_schema_json
        if hasattr(self._action, 'out_model_type'):
            # 从 Pydantic model 提取 schema
            model = self._action.out_model_type
            if hasattr(model, 'model_json_schema'):
                return model.model_json_schema()
        return {"type": "object", "properties": {}}

    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict] = None,
    ) -> ToolResult:
        """执行 Action"""
        try:
            # 1. 初始化 Action
            if hasattr(self._action, 'init_action'):
                self._action.init_action(context or {})

            # 2. 初始化资源
            if self._resource and hasattr(self._action, 'init_resource'):
                self._action.init_resource(self._resource)

            # 3. 运行前准备
            if hasattr(self._action, 'before_run'):
                self._action.before_run()

            # 4. 执行 Action
            if asyncio.iscoroutinefunction(self._action.run):
                result = await self._action.run(**args)
            else:
                result = self._action.run(**args)

            # 5. 格式化输出
            output = self._format_result(result)

            return ToolResult(
                success=True,
                output=output,
                metadata={"action_name": self._action_name},
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Action execution failed: {e}",
            )

    def _format_result(self, result: Any) -> str:
        """格式化 Action 结果"""
        # 优先使用 view 属性
        if hasattr(result, 'view') and result.view:
            return str(result.view)

        # 其次使用 content 属性
        if hasattr(result, 'content'):
            return str(result.content)

        # 最后尝试 to_dict
        if hasattr(result, 'to_dict'):
            return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

        return str(result)
```

### 5.3 ActionTypeMapper (资源类型映射)

```python
class ActionTypeMapper:
    """资源类型到 Action 类的映射"""

    def __init__(self):
        self._mappings: Dict[str, Type] = {}
        self._instances: Dict[str, Any] = {}

    def register(self, resource_type: str, action_class: Type) -> None:
        """注册资源类型到 Action 类的映射"""
        self._mappings[resource_type] = action_class

    def get_action_class(self, resource_type: str) -> Optional[Type]:
        """获取 Action 类"""
        return self._mappings.get(resource_type)

    def create_tool(
        self,
        resource_type: str,
        resource: Optional[Any] = None,
    ) -> Optional[ActionToolAdapter]:
        """创建工具实例"""
        action_class = self._mappings.get(resource_type)
        if not action_class:
            return None

        # 获取或创建 Action 实例
        if resource_type in self._instances:
            action = self._instances[resource_type]
        else:
            action = action_class()
            self._instances[resource_type] = action

        return ActionToolAdapter(action, resource_type, resource)

    def list_actions(self) -> List[str]:
        """列出所有注册的 Action"""
        return list(self._mappings.keys())


# 默认映射
default_action_mapper = ActionTypeMapper()
default_action_mapper.register("tool", ToolAction)
default_action_mapper.register("sandbox", SandboxAction)
default_action_mapper.register("knowledge", KnowledgeAction)
default_action_mapper.register("code", CodeAction)
default_action_mapper.register("rag", RagAction)
default_action_mapper.register("chart", ChartAction)
```

---

## 六、MCP 协议工具适配器

文件位置: `tools_v2/mcp_tools.py`

### 6.1 MCP 协议简介

MCP (Model Context Protocol) 是一个标准化的工具协议，允许外部工具服务器与 AI Agent 集成。

### 6.2 MCPToolAdapter 实现

```python
class MCPToolAdapter(ToolBase):
    """MCP 协议工具适配器"""

    def __init__(
        self,
        mcp_tool: Any,
        server_name: str,
        mcp_client: Optional[Any] = None,
    ):
        self._mcp_tool = mcp_tool
        self._server_name = server_name
        self._mcp_client = mcp_client

        self._tool_name = getattr(mcp_tool, "name", str(mcp_tool))
        self._tool_description = getattr(mcp_tool, "description", "")
        self._input_schema = getattr(mcp_tool, "inputSchema", {})

        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=f"mcp_{self._server_name}_{self._tool_name}",
            description=self._tool_description,
            parameters=self._input_schema,
            category="mcp",
        )

    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict] = None,
    ) -> ToolResult:
        """执行 MCP 工具"""
        try:
            if self._mcp_client:
                # 通过客户端调用
                result = await self._mcp_client.call_tool(
                    server_name=self._server_name,
                    tool_name=self._tool_name,
                    arguments=args,
                )
            elif hasattr(self._mcp_tool, 'execute'):
                # 直接执行
                result = await self._mcp_tool.execute(args)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error="No execution method available",
                )

            # 解析结果
            if hasattr(result, 'content'):
                output = result.content
            else:
                output = str(result)

            return ToolResult(
                success=True,
                output=output,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"MCP tool execution failed: {e}",
            )
```

### 6.3 MCP 连接管理器

```python
class MCPConnectionManager:
    """MCP 连接管理器 - 支持多种传输协议"""

    def __init__(self):
        self._connections: Dict[str, Any] = {}
        self._tools: Dict[str, List[MCPToolAdapter]] = defaultdict(list)

    async def connect(
        self,
        server_name: str,
        config: Dict[str, Any],
    ) -> bool:
        """连接 MCP 服务器"""
        transport = config.get("transport", "stdio")

        try:
            if transport == "stdio":
                # 使用 MCPToolsKit (标准输入输出)
                client = await self._connect_stdio(config)
            elif transport == "sse":
                # Server-Sent Events
                client = await self._connect_sse(config)
            elif transport == "websocket":
                # WebSocket
                client = await self._connect_websocket(config)
            else:
                raise ValueError(f"Unknown transport: {transport}")

            self._connections[server_name] = client

            # 发现并注册工具
            tools = await client.list_tools()
            for tool in tools:
                adapter = MCPToolAdapter(tool, server_name, client)
                self._tools[server_name].append(adapter)

            return True

        except Exception as e:
            print(f"Failed to connect MCP server {server_name}: {e}")
            return False

    async def _connect_stdio(self, config: Dict) -> Any:
        """连接 STDIO 传输"""
        # 使用 MCPToolsKit 或类似库
        from mcp import MCPToolsKit
        return MCPToolsKit(command=config["command"])

    async def _connect_sse(self, config: Dict) -> Any:
        """连接 SSE 传输"""
        import aiohttp
        session = aiohttp.ClientSession()
        # 实现 SSE 连接逻辑
        return session

    async def _connect_websocket(self, config: Dict) -> Any:
        """连接 WebSocket 传输"""
        import websockets
        ws = await websockets.connect(config["url"])
        return ws

    def get_tools(self, server_name: Optional[str] = None) -> List[MCPToolAdapter]:
        """获取 MCP 工具列表"""
        if server_name:
            return self._tools.get(server_name, [])
        return [t for tools in self._tools.values() for t in tools]


# 全局 MCP 连接管理器
mcp_connection_manager = MCPConnectionManager()
```

---

## 七、子 Agent 调用工具

文件位置: `tools_v2/task_tools.py`

### 7.1 TaskTool 设计

参考 OpenCode 的 Task 工具设计，支持委派任务给子 Agent。

```python
class TaskTool(ToolBase):
    """子 Agent 调用工具"""

    # 超时配置 (根据彻底程度)
    TIMEOUTS = {
        "quick": 60,       # 1 分钟
        "medium": 180,     # 3 分钟
        "thorough": 600,   # 10 分钟
    }

    # 预定义的子 Agent 类型
    SUBAGENT_TYPES = {
        "general": "通用 Agent，适合大多数任务",
        "explore": "代码探索 Agent，快速搜索和分析代码库",
        "code-reviewer": "代码审查 Agent，专注于代码质量和最佳实践",
    }

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="task",
            description="Delegate a task to a specialized sub-agent",
            category="task",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subagent": {
                    "type": "string",
                    "enum": list(self.SUBAGENT_TYPES.keys()),
                    "description": "Type of sub-agent to use",
                },
                "prompt": {
                    "type": "string",
                    "description": "Task description for the sub-agent",
                },
                "thoroughness": {
                    "type": "string",
                    "enum": ["quick", "medium", "thorough"],
                    "default": "medium",
                    "description": "How thorough the sub-agent should be",
                },
                "context": {
                    "type": "object",
                    "description": "Additional context to pass to sub-agent",
                },
            },
            "required": ["subagent", "prompt"],
        }

    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict] = None,
    ) -> ToolResult:
        subagent_type = args["subagent"]
        prompt = args["prompt"]
        thoroughness = args.get("thoroughness", "medium")
        extra_context = args.get("context", {})

        # 获取 SubagentManager
        subagent_manager = context.get("subagent_manager") if context else None
        if not subagent_manager:
            return ToolResult(
                success=False,
                output="",
                error="SubagentManager not available",
            )

        # 获取超时
        timeout = self.TIMEOUTS.get(thoroughness, 180)

        try:
            # 委派任务
            result = await asyncio.wait_for(
                subagent_manager.delegate(
                    subagent_name=subagent_type,
                    task=prompt,
                    parent_session_id=context.get("session_id", ""),
                    context=extra_context,
                ),
                timeout=timeout,
            )

            return ToolResult(
                success=result.success,
                output=result.output,
                metadata={
                    "subagent": subagent_type,
                    "thoroughness": thoroughness,
                },
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"Sub-agent task timed out after {timeout} seconds",
            )
```

---

## 八、工具注册流程

文件位置: `tools_v2/__init__.py`

```python
def register_all_tools(
    registry: ToolRegistry = None,
    interaction_manager: Any = None,
    progress_broadcaster: Any = None,
    http_client: Any = None,
    search_config: Dict = None,
) -> ToolRegistry:
    """注册所有工具"""

    if registry is None:
        registry = ToolRegistry()

    # 1. 注册内置工具
    register_builtin_tools(registry)

    # 2. 注册交互工具
    register_interaction_tools(
        registry,
        interaction_manager,
        progress_broadcaster,
    )

    # 3. 注册网络工具
    register_network_tools(registry, http_client, search_config)

    # 4. 注册分析工具
    register_analysis_tools(registry)

    # 5. 注册 Action 适配器
    for action_name in default_action_mapper.list_actions():
        adapter = default_action_mapper.create_tool(action_name)
        if adapter:
            registry.register(adapter)

    return registry


def register_builtin_tools(registry: ToolRegistry) -> None:
    """注册内置工具"""
    registry.register(BashTool())
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(SearchTool())
    registry.register(ListFilesTool())
    registry.register(ThinkTool())


def register_interaction_tools(
    registry: ToolRegistry,
    interaction_manager: Any = None,
    progress_broadcaster: Any = None,
) -> None:
    """注册交互工具"""
    registry.register(QuestionTool())
    registry.register(ConfirmTool())
    registry.register(NotifyTool())
    registry.register(ProgressTool())
    registry.register(AskHumanTool())
    registry.register(FileSelectTool())
```

---

## 九、可视化机制

### 9.1 VIS 协议架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        VIS 可视化架构                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                     前端 (vis_window3 组件)                         │ │
│  │                                                                     │ │
│  │  ┌──────────────────────┐    ┌──────────────────────────────────┐  │ │
│  │  │   Planning Window    │    │       Running Window             │  │ │
│  │  │   (左侧: 步骤列表)    │    │       (右侧: 详细内容)           │  │ │
│  │  │                      │    │                                  │  │ │
│  │  │  步骤 1: 分析需求     │    │  当前步骤详情                    │  │ │
│  │  │  步骤 2: 设计方案     │    │  思考过程...                     │  │ │
│  │  │  步骤 3: 实现       │    │  输出内容...                     │  │ │
│  │  │  ...               │    │  产物列表...                     │  │ │
│  │  └──────────────────────┘    └──────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                    ▲                                     │
│                                    │ WebSocket/SSE                       │
│                                    │                                     │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                     后端转换层                                      │ │
│  │                                                                     │ │
│  │  ┌────────────────┐    ┌──────────────────┐    ┌────────────────┐  │ │
│  │  │ CoreV2Vis     │    │ CoreV2VisWindow3 │    │ VIS 标签生成   │  │ │
│  │  │ Adapter       │───▶│ Converter        │───▶│                │  │ │
│  │  │                │    │                  │    │ drsk-plan      │  │ │
│  │  │ 步骤收集       │    │ 数据转换         │    │ drsk-thinking  │  │ │
│  │  │ 产物收集       │    │                  │    │ drsk-content   │  │ │
│  │  │ 状态管理       │    │                  │    │ nex-work-space │  │ │
│  │  └────────────────┘    └──────────────────┘    └────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                    ▲                                     │
│                                    │                                     │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                     Core V2 Agent 执行层                           │ │
│  │                                                                     │ │
│  │  Agent.run() → think() → decide() → act()                         │ │
│  │                                                                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.2 VIS 协议数据结构

文件位置: `vis_protocol.py`

#### 核心枚举

```python
class StepStatus(str, Enum):
    """步骤状态"""
    PENDING = "pending"      # 等待中
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 已失败


class ArtifactType(str, Enum):
    """产物类型"""
    TOOL_OUTPUT = "tool_output"  # 工具输出
    LLM_OUTPUT = "llm_output"    # LLM 输出
    FILE = "file"                # 文件
    IMAGE = "image"              # 图片
    CODE = "code"                # 代码
    REPORT = "report"            # 报告
```

#### Planning Window 数据

```python
@dataclass
class PlanningStep:
    """规划步骤"""
    step_id: str
    title: str
    status: StepStatus = StepStatus.PENDING
    result_summary: Optional[str] = None
    agent_name: Optional[str] = None
    agent_role: Optional[str] = None
    layer_count: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@dataclass
class PlanningWindow:
    """规划窗口"""
    steps: List[PlanningStep]
    current_step_id: Optional[str] = None
```

#### Running Window 数据

```python
@dataclass
class RunningArtifact:
    """运行产物"""
    artifact_id: str
    type: ArtifactType
    content: str
    title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CurrentStep:
    """当前步骤"""
    step_id: str
    title: str
    status: str


@dataclass
class RunningWindow:
    """运行窗口"""
    current_step: Optional[CurrentStep] = None
    thinking: Optional[str] = None       # 思考过程
    content: Optional[str] = None        # 主要内容
    artifacts: List[RunningArtifact] = field(default_factory=list)
```

### 9.3 VIS 标签格式

#### drsk-plan (规划步骤)

```markdown
```drsk-plan
{
    "uid": "step_001",
    "type": "all",           // "all" 全量替换, "incr" 增量追加
    "item_type": "task",
    "task_type": "tool",
    "title": "分析代码库结构",
    "status": "completed",
    "markdown": "嵌套的其他VIS标签内容..."
}
```
```

#### drsk-thinking (思考内容)

```markdown
```drsk-thinking
{
    "uid": "msg_123_thinking",
    "type": "incr",          // 增量更新
    "dynamic": false,
    "markdown": "我正在分析代码结构...",
    "expand": true           // 是否展开显示
}
```
```

#### drsk-content (普通内容)

```markdown
```drsk-content
{
    "uid": "msg_123_content",
    "type": "incr",
    "dynamic": false,
    "markdown": "分析结果如下..."
}
```
```

#### nex-work-space (运行窗口容器)

```markdown
```nex-work-space
{
    "uid": "session_abc",
    "type": "incr",
    "items": [
        {"tag": "drsk-thinking", "data": {...}},
        {"tag": "drsk-content", "data": {...}}
    ]
}
```
```

### 9.4 CoreV2VisWindow3Converter 实现

文件位置: `core_v2/vis_converter.py`

```python
class CoreV2VisWindow3Converter:
    """Core V2 VIS 窗口转换器

    特点:
    1. 不依赖 ConversableAgent
    2. 直接从 stream_msg dict 生成 vis_window3 格式
    3. 轻量级，不进行 VIS 标签文件扫描
    4. 支持增量传输协议
    """

    def convert_stream_message(
        self,
        stream_msg: Dict[str, Any],
        is_first_chunk: bool = False,
    ) -> str:
        """转换流式消息为 VIS 格式"""
        message_id = stream_msg.get("message_id", str(uuid.uuid4()))

        output_parts = []

        # 1. 构建 Planning Window
        planning_vis = self._build_planning_from_stream(stream_msg, is_first_chunk)
        if planning_vis:
            output_parts.append(planning_vis)

        # 2. 构建 Running Window
        running_vis = self._build_running_from_stream(stream_msg)
        if running_vis:
            output_parts.append(running_vis)

        return "\n\n".join(output_parts)

    def _build_planning_from_stream(
        self,
        stream_msg: Dict[str, Any],
        is_first_chunk: bool,
    ) -> Optional[str]:
        """构建规划窗口 VIS"""
        message_id = stream_msg.get("message_id")

        # 处理思考内容
        thinking = stream_msg.get("thinking")
        if thinking:
            thinking_vis = self._vis_tag("drsk-thinking", {
                "uid": f"{message_id}_thinking",
                "type": "incr",
                "dynamic": False,
                "markdown": thinking,
                "expand": True,
            })
            return self._wrap_as_plan_item(thinking_vis, message_id, is_first_chunk)

        # 处理普通内容
        content = stream_msg.get("content")
        if content and not thinking:
            content_vis = self._vis_tag("drsk-content", {
                "uid": f"{message_id}_step_thought",
                "type": "incr",
                "dynamic": False,
                "markdown": content,
            })
            return self._wrap_as_plan_item(content_vis, message_id, is_first_chunk)

        return None

    def _build_running_from_stream(
        self,
        stream_msg: Dict[str, Any],
    ) -> Optional[str]:
        """构建运行窗口 VIS"""
        message_id = stream_msg.get("message_id")
        conv_uid = stream_msg.get("conv_uid")

        work_items = []

        # 添加思考
        thinking = stream_msg.get("thinking")
        if thinking:
            work_items.append({
                "tag": "drsk-thinking",
                "data": {
                    "uid": f"{message_id}_run_thinking",
                    "type": "incr",
                    "markdown": thinking,
                    "expand": True,
                }
            })

        # 添加内容
        content = stream_msg.get("content")
        if content:
            work_items.append({
                "tag": "drsk-content",
                "data": {
                    "uid": f"{message_id}_run_content",
                    "type": "incr",
                    "markdown": content,
                }
            })

        if not work_items:
            return None

        return self._vis_tag("nex-work-space", {
            "uid": conv_uid or message_id,
            "type": "incr",
            "items": work_items,
        })

    def _vis_tag(self, tag_name: str, data: dict) -> str:
        """生成 VIS 标签字符串"""
        content = json.dumps(data, ensure_ascii=False)
        return f"```{tag_name}\n{content}\n```"

    def _wrap_as_plan_item(
        self,
        inner_vis: str,
        message_id: str,
        is_first_chunk: bool,
    ) -> str:
        """包装为 Plan Item"""
        return self._vis_tag("drsk-plan", {
            "uid": f"goal_{message_id}",
            "type": "all" if is_first_chunk else "incr",
            "markdown": inner_vis,
        })
```

### 9.5 CoreV2VisAdapter 实现

文件位置: `core_v2/vis_adapter.py`

```python
class CoreV2VisAdapter:
    """Core V2 VIS 适配器

    管理执行过程中的状态和产物，转换为 VIS 格式
    """

    def __init__(self, agent_name: str = "primary"):
        self.agent_name = agent_name
        self.steps: Dict[str, VisStep] = {}
        self.step_order: List[str] = []
        self.current_step_id: Optional[str] = None
        self.artifacts: List[VisArtifact] = []
        self.thinking_content: Optional[str] = None
        self.content: Optional[str] = None

    def add_step(
        self,
        step_id: str,
        title: str,
        status: str = "pending",
    ) -> None:
        """添加步骤"""
        step = VisStep(
            step_id=step_id,
            title=title,
            status=_map_status(status),
            start_time=datetime.now() if status == "running" else None,
        )
        self.steps[step_id] = step
        self.step_order.append(step_id)

        if status == "running":
            self.current_step_id = step_id

    def update_step(
        self,
        step_id: str,
        status: str,
        result_summary: Optional[str] = None,
    ) -> None:
        """更新步骤状态"""
        if step_id not in self.steps:
            return

        step = self.steps[step_id]
        step.status = _map_status(status)

        if status in ["completed", "failed"]:
            step.end_time = datetime.now()
            if result_summary:
                step.result_summary = result_summary

    def add_artifact(
        self,
        artifact_type: str,
        title: str,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        """添加产物"""
        artifact_id = str(uuid.uuid4())
        artifact = VisArtifact(
            artifact_id=artifact_id,
            type=artifact_type,
            title=title,
            content=content,
            metadata=metadata or {},
        )
        self.artifacts.append(artifact)
        return artifact_id

    def set_thinking(self, content: str) -> None:
        """设置思考内容"""
        self.thinking_content = content

    def set_content(self, content: str) -> None:
        """设置主要内容"""
        self.content = content

    async def generate_vis_output(self) -> str:
        """生成 VIS 输出"""
        # 转换步骤为 GptsMessage 格式
        messages = self._steps_to_gpts_messages()

        # 使用转换器生成 VIS
        converter = DeriskIncrVisWindow3Converter()
        vis_output = await converter.visualization(
            messages=messages,
            senders_map={},
            main_agent_name=self.agent_name,
            is_first_chunk=True,
            is_first_push=True,
        )

        return vis_output

    def _steps_to_gpts_messages(self) -> List:
        """转换步骤为 GptsMessage 列表"""
        messages = []
        for step_id in self.step_order:
            step = self.steps[step_id]

            # 创建 ActionReportType
            action_report = ActionReportType(
                action_id=step.step_id,
                action="step",
                action_name=step.title,
                thoughts="",
                view="",
                content=step.result_summary or "",
                state=step.status,
                start_time=step.start_time,
                end_time=step.end_time,
            )

            # 创建 GptsMessage
            msg = GptsMessage(
                message_id=step_id,
                role="assistant",
                content="",
                action_report=[action_report],
            )
            messages.append(msg)

        return messages
```

### 9.6 前后端交互流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        前后端 VIS 交互流程                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  前端                           后端                                     │
│  ┌─────────────────┐          ┌─────────────────────────────────────┐   │
│  │ vis_window3     │          │ V2AgentRuntime                      │   │
│  │ 组件            │          │                                     │   │
│  └────────┬────────┘          │  execute() {                        │   │
│           │                    │    agent.run() {                    │   │
│           │                    │      think() {                      │   │
│           │                    │        // 生成思考内容              │   │
│           │                    │        adapter.set_thinking(...)   │   │
│           │                    │      }                              │   │
│           │                    │      decide()                       │   │
│           │                    │      act() {                        │   │
│           │                    │        // 执行工具                  │   │
│           │                    │        adapter.add_step(...)       │   │
│           │                    │        adapter.update_step(...)    │   │
│           │                    │      }                              │   │
│           │                    │    }                                │   │
│           │                    │                                     │   │
│           │                    │    // 流式输出                      │   │
│           │                    │    for chunk in stream:            │   │
│           │◀── SSE/WebSocket ──│      vis = converter.convert()     │   │
│           │   VIS 标签         │      yield vis                      │   │
│           │                    │  }                                  │   │
│  ┌────────┴────────┐          └─────────────────────────────────────┘   │
│  │ 解析 VIS 标签  │                                                       │
│  │ 更新 UI 状态   │                                                       │
│  │                │                                                       │
│  │ type=incr:     │                                                       │
│  │   追加到现有   │                                                       │
│  │ type=all:      │                                                       │
│  │   替换全部     │                                                       │
│  └────────────────┘                                                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 十、文件系统集成

### 10.1 文件系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       文件系统集成架构                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                  ProjectMemoryManager                               │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐      │ │
│  │  │ 记忆层管理   │  │ @import 解析│  │ 上下文构建           │      │ │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘      │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                    │                                     │
│                                    ▼                                     │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                  AgentFileSystemMemoryExtension                     │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐      │ │
│  │  │内存-文件同步│  │ 工件导出     │  │ 提示词文件管理       │      │ │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘      │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                    │                                     │
│         ┌──────────────────────────┼──────────────────────────┐         │
│         ▼                          ▼                          ▼         │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐   │
│  │Claude 兼容层│           │ 自动记忆钩子│           │ 记忆文件同步│   │
│  │             │           │             │           │             │   │
│  │CLAUDE.md    │           │ HookRegistry│           │MemoryFileSync│   │
│  │解析/转换    │           │ AutoMemory  │           │             │   │
│  │             │           │ Hook        │           │             │   │
│  └─────────────┘           └─────────────┘           └─────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 10.2 CLAUDE.md 兼容层

文件位置: `filesystem/claude_compatible.py`

```python
class ClaudeMdParser:
    """CLAUDE.md 文件解析器"""

    @staticmethod
    def parse(content: str) -> ClaudeMdDocument:
        """解析 CLAUDE.md 内容"""
        # 1. 提取 YAML Front Matter
        front_matter = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                front_matter = yaml.safe_load(parts[1])
                content = parts[2]

        # 2. 提取 @import 导入
        imports = []
        import_pattern = r'@import\s+(@?[\w./-]+)'
        for match in re.finditer(import_pattern, content):
            imports.append(match.group(1))

        # 3. 提取章节结构
        sections = ClaudeMdParser._extract_sections(content)

        return ClaudeMdDocument(
            front_matter=front_matter,
            content=content.strip(),
            imports=imports,
            sections=sections,
        )

    @staticmethod
    def _extract_sections(content: str) -> List[Section]:
        """提取章节结构"""
        sections = []
        current_section = None

        for line in content.split('\n'):
            if line.startswith('# '):
                if current_section:
                    sections.append(current_section)
                current_section = Section(
                    title=line[2:].strip(),
                    level=1,
                    content="",
                )
            elif line.startswith('## '):
                if current_section:
                    sections.append(current_section)
                current_section = Section(
                    title=line[3:].strip(),
                    level=2,
                    content="",
                )
            elif current_section:
                current_section.content += line + '\n'

        if current_section:
            sections.append(current_section)

        return sections


class ClaudeCompatibleAdapter:
    """Claude Code 兼容适配器"""

    CLAUDE_MD_FILES = ["CLAUDE.md", "claude.md", ".claude.md", "CLAUDE"]

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.parser = ClaudeMdParser()

    async def detect_claude_md(self) -> Optional[Path]:
        """检测 CLAUDE.md 文件"""
        for filename in self.CLAUDE_MD_FILES:
            path = self.project_root / filename
            if path.exists():
                return path
        return None

    async def convert_to_derisk(self, overwrite: bool = False) -> bool:
        """将 CLAUDE.md 转换为 Derisk 格式"""
        claude_md = await self.detect_claude_md()
        if not claude_md:
            return False

        # 解析内容
        doc = self.parser.parse(claude_md.read_text())

        # 转换为 Derisk 格式
        derisk_content = self.parser.to_derisk_format(doc)

        # 写入 .derisk/MEMORY.md
        derisk_path = self.project_root / ".derisk" / "MEMORY.md"
        derisk_path.parent.mkdir(parents=True, exist_ok=True)

        if overwrite or not derisk_path.exists():
            derisk_path.write_text(derisk_content)
            return True

        return False
```

### 10.3 自动记忆钩子系统

文件位置: `filesystem/auto_memory_hook.py`

```python
class AutoMemoryHook(SceneHook):
    """自动记忆写入钩子"""

    name = "auto_memory"
    phases = [AgentPhase.AFTER_ACT, AgentPhase.COMPLETE]
    priority = HookPriority.LOW

    # 值得记忆的模式
    MEMORY_PATTERNS = [
        r'(?:decided|determined|concluded)\s+(?:to|that)',
        r'(?:important|key|critical|essential)\s+(?:point|finding|insight)',
        r'(?:solution|fix|resolution)\s+(?:for|to)',
        r'(?:lesson|learned|takeaway)',
        r'(?:remember|note|keep in mind)',
    ]

    def __init__(
        self,
        project_memory: "ProjectMemoryManager",
        threshold: int = 10,
    ):
        self.project_memory = project_memory
        self.threshold = threshold
        self.interaction_count = 0

    async def execute(self, ctx: HookContext) -> HookResult:
        """执行钩子"""
        self.interaction_count += 1

        # 检查是否达到阈值
        if self.interaction_count < self.threshold:
            return HookResult(should_continue=True)

        # 提取值得记忆的内容
        memory_content = self._extract_memory_content(ctx)

        if memory_content:
            # 写入自动记忆
            await self.project_memory.write_auto_memory(
                content=memory_content,
                metadata={
                    "phase": ctx.phase.value,
                    "interaction_count": self.interaction_count,
                },
            )

            # 重置计数
            self.interaction_count = 0

            return HookResult(
                should_continue=True,
                should_write_memory=True,
                memory_content=memory_content,
            )

        return HookResult(should_continue=True)

    def _extract_memory_content(self, ctx: HookContext) -> Optional[str]:
        """提取记忆内容"""
        # 从上下文获取最近的输出
        recent_content = ""
        if ctx.tool_result:
            recent_content = str(ctx.tool_result)

        # 匹配记忆模式
        for pattern in self.MULTI_PATTERNS:
            matches = re.findall(pattern, recent_content, re.IGNORECASE)
            if matches:
                return f"Auto-detected: {matches[0]}"

        return None


class ImportantDecisionHook(SceneHook):
    """重要决策记录钩子"""

    name = "important_decision"
    phases = [AgentPhase.AFTER_DECIDE, AgentPhase.AFTER_ACT]
    priority = HookPriority.HIGH

    DECISION_KEYWORDS = [
        "decided", "chose", "selected", "resolved",
        "决定", "选择", "采用",
    ]

    def __init__(
        self,
        project_memory: "ProjectMemoryManager",
        confidence_threshold: float = 0.7,
    ):
        self.project_memory = project_memory
        self.confidence_threshold = confidence_threshold

    async def execute(self, ctx: HookContext) -> HookResult:
        """执行钩子"""
        content = ""

        if ctx.decision:
            content = str(ctx.decision)
        elif ctx.tool_result:
            content = str(ctx.tool_result)

        # 检测决策关键词
        confidence = self._calculate_confidence(content)

        if confidence >= self.confidence_threshold:
            # 记录决策
            decision_record = self._format_decision(ctx, content, confidence)

            await self.project_memory.write_auto_memory(
                content=decision_record,
                metadata={
                    "type": "decision",
                    "confidence": confidence,
                },
            )

            return HookResult(
                should_continue=True,
                should_write_memory=True,
                memory_content=decision_record,
            )

        return HookResult(should_continue=True)

    def _calculate_confidence(self, content: str) -> float:
        """计算决策置信度"""
        count = 0
        for keyword in self.DECISION_KEYWORDS:
            if keyword in content.lower():
                count += 1
        return min(count / 3, 1.0)  # 每个关键词贡献 1/3 置信度
```

---

## 十一、关键文件索引

| 文件 | 功能 | 关键类/函数 |
|------|------|------------|
| `tools_v2/tool_base.py` | 工具基础架构 | `ToolBase`, `ToolRegistry`, `ToolResult` |
| `tools_v2/builtin_tools.py` | 内置工具 | `BashTool`, `ReadTool`, `WriteTool`, `SearchTool` |
| `tools_v2/interaction_tools.py` | 交互工具 | `QuestionTool`, `ProgressTool`, `ConfirmTool` |
| `tools_v2/action_tools.py` | Action 适配 | `ActionToolAdapter`, `ActionTypeMapper` |
| `tools_v2/mcp_tools.py` | MCP 适配 | `MCPToolAdapter`, `MCPConnectionManager` |
| `tools_v2/task_tools.py` | 子 Agent 调用 | `TaskTool` |
| `core_v2/vis_converter.py` | VIS 转换 | `CoreV2VisWindow3Converter` |
| `core_v2/vis_adapter.py` | VIS 适配 | `CoreV2VisAdapter` |
| `filesystem/claude_compatible.py` | CLAUDE.md 兼容 | `ClaudeMdParser`, `ClaudeCompatibleAdapter` |
| `filesystem/auto_memory_hook.py` | 自动记忆钩子 | `AutoMemoryHook`, `ImportantDecisionHook` |
| `filesystem/integration.py` | 文件系统集成 | `AgentFileSystemMemoryExtension`, `MemoryFileSync` |