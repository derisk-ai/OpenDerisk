# Derisk 统一工具架构与授权系统 - 开发任务规划

**版本**: v2.0  
**日期**: 2026-03-02  
**目标**: 实现统一工具架构与授权系统的完整功能

---

## 📋 项目概览

### 核心目标
1. ✅ 统一工具系统 - 标准化的工具元数据、注册与执行
2. ✅ 完整权限体系 - 多层次授权控制、智能风险评估
3. ✅ 优雅交互系统 - 统一协议、实时通信
4. ✅ Agent集成框架 - 声明式配置、think-decide-act

### 参考文档
- [架构设计文档 Part1](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md)
- [架构设计文档 Part2](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART2.md)
- [架构设计文档 Part3](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md)

### 开发周期
**总计**: 12周（84天）

---

## 🎯 里程碑规划

| 里程碑 | 周次 | 目标 | 验收标准 |
|--------|------|------|----------|
| **M1: 核心模型** | Week 1-2 | 完成核心数据模型定义 | 所有模型测试通过，文档完整 |
| **M2: 工具系统** | Week 3-4 | 实现工具注册与执行 | 工具可注册、执行、测试覆盖率>80% |
| **M3: 授权系统** | Week 5-6 | 完成授权引擎与风险评估 | 授权决策正确，缓存工作正常 |
| **M4: 交互系统** | Week 7-8 | 实现交互协议与网关 | WebSocket通信正常，交互类型完整 |
| **M5: Agent集成** | Week 9-10 | 完成Agent框架集成 | Agent可运行，授权检查集成 |
| **M6: 前端开发** | Week 11-12 | 完成前端交互组件 | 所有组件可用，E2E测试通过 |

---

## 📝 详细任务清单

---

## 阶段一：核心模型定义（Week 1-2）

### 1.1 工具元数据模型
**优先级**: P0（最高）  
**预估工时**: 3天  
**依赖**: 无

#### 任务描述
创建工具系统的核心数据模型，定义工具元数据标准。

#### 具体步骤

**Step 1: 创建基础枚举类型**
```python
# 文件: derisk/core/tools/metadata.py

任务内容:
1. 定义 ToolCategory 枚举（8个类别）
2. 定义 RiskLevel 枚举（5个等级）
3. 定义 RiskCategory 枚举（8个类别）

验收标准:
- 所有枚举值可正常使用
- 枚举继承自str和Enum
- 每个枚举有清晰的注释
```

**Step 2: 实现授权需求数据模型**
```python
任务内容:
1. 创建 AuthorizationRequirement 类
   - requires_authorization: bool
   - risk_level: RiskLevel
   - risk_categories: List[RiskCategory]
   - authorization_prompt: Optional[str]
   - sensitive_parameters: List[str]
   - whitelist_rules: List[Dict]
   - support_session_grant: bool
   - grant_ttl: Optional[int]

验收标准:
- 使用Pydantic BaseModel
- 所有字段有默认值
- 支持JSON序列化
```

**Step 3: 实现工具参数模型**
```python
任务内容:
1. 创建 ToolParameter 类
   - name, type, description, required
   - default, enum, pattern
   - min_value, max_value, min_length, max_length
   - sensitive, sensitive_pattern

验收标准:
- 支持参数验证
- 支持敏感参数标记
- 支持多种约束类型
```

**Step 4: 实现工具元数据主模型**
```python
任务内容:
1. 创建 ToolMetadata 类（完整版）
   - 基本信息: id, name, version, description, category
   - 作者来源: author, source, package, homepage, repository
   - 参数定义: parameters, return_type, return_description
   - 授权安全: authorization
   - 执行配置: timeout, max_concurrent, retry_count, retry_delay
   - 依赖冲突: dependencies, conflicts
   - 标签示例: tags, examples
   - 元信息: created_at, updated_at, deprecated, deprecation_message
   - 扩展字段: metadata

2. 实现 get_openai_spec() 方法
3. 实现 validate_arguments() 方法

验收标准:
- 与OpenAI Function Calling格式兼容
- 参数验证正确
- 支持JSON序列化/反序列化
```

#### 测试要求
```python
# 文件: tests/unit/test_tool_metadata.py

测试用例:
1. test_create_tool_metadata - 创建工具元数据
2. test_get_openai_spec - 生成OpenAI规范
3. test_validate_arguments_success - 参数验证成功
4. test_validate_arguments_fail - 参数验证失败
5. test_authorization_requirement_defaults - 默认值测试
6. test_sensitive_parameters - 敏感参数测试

覆盖率要求: >85%
```

#### 完成标准
- [ ] 所有枚举类型定义完成
- [ ] AuthorizationRequirement 类实现完成
- [ ] ToolParameter 类实现完成
- [ ] ToolMetadata 类实现完成
- [ ] 单元测试全部通过
- [ ] 代码覆盖率 >85%

---

### 1.2 权限模型定义
**优先级**: P0  
**预估工时**: 3天  
**依赖**: 1.1完成

#### 任务描述
创建权限系统的核心数据模型，定义授权配置和权限规则。

#### 具体步骤

**Step 1: 定义权限动作和模式**
```python
# 文件: derisk/core/authorization/model.py

任务内容:
1. 定义 PermissionAction 枚举 (ALLOW, DENY, ASK)
2. 定义 AuthorizationMode 枚举 (STRICT, MODERATE, PERMISSIVE, UNRESTRICTED)
3. 定义 LLMJudgmentPolicy 枚举 (DISABLED, CONSERVATIVE, BALANCED, AGGRESSIVE)

验收标准:
- 枚举继承自str和Enum
- 值为小写字符串
```

**Step 2: 实现权限规则模型**
```python
任务内容:
1. 创建 PermissionRule 类
   - id, name, description
   - tool_pattern: str (支持通配符)
   - category_filter: Optional[str]
   - risk_level_filter: Optional[str]
   - parameter_conditions: Dict[str, Any]
   - action: PermissionAction
   - priority: int
   - enabled: bool
   - time_range: Optional[Dict[str, str]]

2. 实现 matches() 方法
   - 检查工具名称匹配
   - 检查类别过滤
   - 检查风险等级过滤
   - 检查参数条件

验收标准:
- 支持通配符匹配
- 支持多种参数条件类型
- 优先级排序正确
```

**Step 3: 实现权限规则集**
```python
任务内容:
1. 创建 PermissionRuleset 类
   - id, name, description
   - rules: List[PermissionRule]
   - default_action: PermissionAction

2. 实现 add_rule() 方法
3. 实现 check() 方法
4. 实现 from_dict() 类方法

验收标准:
- 规则按优先级排序
- check方法返回第一个匹配的规则
- 支持字典快速创建
```

**Step 4: 实现授权配置模型**
```python
任务内容:
1. 创建 AuthorizationConfig 类（完整版）
   - mode: AuthorizationMode
   - ruleset: Optional[PermissionRuleset]
   - llm_policy: LLMJudgmentPolicy
   - llm_prompt: Optional[str]
   - tool_overrides: Dict[str, PermissionAction]
   - whitelist_tools: List[str]
   - blacklist_tools: List[str]
   - session_cache_enabled: bool
   - session_cache_ttl: int
   - authorization_timeout: int
   - user_confirmation_callback: Optional[str]

2. 实现 get_effective_action() 方法
   - 检查黑名单
   - 检查白名单
   - 检查工具覆盖
   - 检查规则集
   - 根据模式返回默认动作

验收标准:
- 优先级正确：黑名单 > 白名单 > 工具覆盖 > 规则集 > 模式
- 不同模式的行为正确
```

#### 测试要求
```python
# 文件: tests/unit/test_authorization_model.py

测试用例:
1. test_permission_rule_matches - 规则匹配测试
2. test_permission_ruleset_check - 规则集检查测试
3. test_authorization_config_priority - 优先级测试
4. test_authorization_modes - 不同模式测试
5. test_from_dict_creation - 字典创建测试

覆盖率要求: >85%
```

#### 完成标准
- [ ] 所有枚举定义完成
- [ ] PermissionRule 类实现完成
- [ ] PermissionRuleset 类实现完成
- [ ] AuthorizationConfig 类实现完成
- [ ] 单元测试全部通过
- [ ] 代码覆盖率 >85%

---

### 1.3 交互协议定义
**优先级**: P0  
**预估工时**: 2天  
**依赖**: 无

#### 任务描述
创建统一的交互协议，定义交互请求和响应的标准格式。

#### 具体步骤

**Step 1: 定义交互类型和状态**
```python
# 文件: derisk/core/interaction/protocol.py

任务内容:
1. 定义 InteractionType 枚举（15种类型）
   - 用户输入类: TEXT_INPUT, FILE_UPLOAD
   - 选择类: SINGLE_SELECT, MULTI_SELECT
   - 确认类: CONFIRMATION, AUTHORIZATION, PLAN_SELECTION
   - 通知类: INFO, WARNING, ERROR, SUCCESS, PROGRESS
   - 任务管理类: TODO_CREATE, TODO_UPDATE

2. 定义 InteractionPriority 枚举
3. 定义 InteractionStatus 枚举

验收标准:
- 覆盖所有交互场景
- 枚举继承自str和Enum
```

**Step 2: 实现交互选项模型**
```python
任务内容:
1. 创建 InteractionOption 类
   - label: str
   - value: str
   - description: Optional[str]
   - icon: Optional[str]
   - disabled: bool
   - default: bool
   - metadata: Dict[str, Any]

验收标准:
- 支持灵活的选项定义
```

**Step 3: 实现交互请求模型**
```python
任务内容:
1. 创建 InteractionRequest 类（完整版）
   - 基本信息: request_id, type, priority
   - 内容: title, message, options
   - 默认值: default_value, default_values
   - 控制: timeout, allow_cancel, allow_skip, allow_defer
   - 会话: session_id, agent_name, step_index, execution_id
   - 授权: authorization_context, allow_session_grant
   - 文件: accepted_file_types, max_file_size, allow_multiple_files
   - 进度: progress_value, progress_message
   - 元数据: metadata, created_at

2. 实现 to_dict() 和 from_dict() 方法

验收标准:
- 支持所有交互类型
- 支持JSON序列化
```

**Step 4: 实现交互响应模型**
```python
任务内容:
1. 创建 InteractionResponse 类
   - 基本信息: request_id, session_id
   - 响应: choice, choices, input_value, file_ids
   - 状态: status
   - 用户消息: user_message, cancel_reason
   - 授权: grant_scope, grant_duration
   - 元数据: metadata, timestamp

2. 实现 is_confirmed 和 is_denied 属性

验收标准:
- 支持多种响应类型
- 属性检查正确
```

**Step 5: 实现便捷构造函数**
```python
任务内容:
1. create_authorization_request() - 创建授权请求
2. create_text_input_request() - 创建文本输入请求
3. create_confirmation_request() - 创建确认请求
4. create_selection_request() - 创建选择请求
5. create_notification() - 创建通知

验收标准:
- 每个函数生成正确的InteractionRequest
- 参数合理，有默认值
```

#### 测试要求
```python
# 文件: tests/unit/test_interaction_protocol.py

测试用例:
1. test_create_interaction_request - 创建请求测试
2. test_interaction_request_serialization - 序列化测试
3. test_interaction_response_properties - 属性测试
4. test_convenience_functions - 便捷函数测试

覆盖率要求: >85%
```

#### 完成标准
- [ ] 所有交互类型定义完成
- [ ] InteractionRequest 类实现完成
- [ ] InteractionResponse 类实现完成
- [ ] 便捷构造函数实现完成
- [ ] 单元测试全部通过
- [ ] 代码覆盖率 >85%

---

### 1.4 Agent配置模型
**优先级**: P0  
**预估工时**: 2天  
**依赖**: 1.2完成

#### 任务描述
创建Agent配置模型，支持声明式Agent定义。

#### 具体步骤

**Step 1: 定义Agent模式和 能力**
```python
# 文件: derisk/core/agent/info.py

任务内容:
1. 定义 AgentMode 枚举 (PRIMARY, SUBAGENT, UTILITY, SUPERVISOR)
2. 定义 AgentCapability 枚举（8种能力）

验收标准:
- 枚举清晰、完整
```

**Step 2: 实现工具选择策略**
```python
任务内容:
1. 创建 ToolSelectionPolicy 类
   - included_categories: List[ToolCategory]
   - excluded_categories: List[ToolCategory]
   - included_tools: List[str]
   - excluded_tools: List[str]
   - preferred_tools: List[str]
   - max_tools: Optional[int]

2. 实现 filter_tools() 方法

验收标准:
- 过滤逻辑正确
- 工具数量限制正确
```

**Step 3: 实现Agent配置主模型**
```python
任务内容:
1. 创建 AgentInfo 类（完整版）
   - 基本信息: name, description, mode, version
   - 隐藏标记: hidden
   - LLM配置: model_id, provider_id, temperature, max_tokens
   - 执行配置: max_steps, timeout
   - 工具配置: tool_policy, tools
   - 授权配置: authorization, permission
   - 能力标签: capabilities
   - 显示配置: color, icon
   - Prompt配置: system_prompt, system_prompt_file, user_prompt_template
   - 上下文配置: context_window_size, memory_enabled, memory_type
   - 多Agent配置: subagents, collaboration_mode
   - 元数据: metadata, tags

2. 实现 get_effective_authorization() 方法
3. 实现 get_openai_tools() 方法

验收标准:
- 支持声明式配置
- 与旧版permission字段兼容
```

**Step 4: 创建预定义Agent模板**
```python
任务内容:
1. 创建 PRIMARY_AGENT_TEMPLATE
2. 创建 PLAN_AGENT_TEMPLATE
3. 创建 SUBAGENT_TEMPLATE
4. 实现 create_agent_from_template() 函数

验收标准:
- 模板配置合理
- 函数可正确创建Agent
```

#### 测试要求
```python
# 文件: tests/unit/test_agent_info.py

测试用例:
1. test_create_agent_info - 创建Agent配置
2. test_tool_selection_policy - 工具过滤测试
3. test_agent_templates - 模板测试
4. test_get_effective_authorization - 授权配置测试

覆盖率要求: >85%
```

#### 完成标准
- [ ] AgentMode 和 AgentCapability 定义完成
- [ ] ToolSelectionPolicy 类实现完成
- [ ] AgentInfo 类实现完成
- [ ] 预定义模板创建完成
- [ ] 单元测试全部通过
- [ ] 代码覆盖率 >85%

---

### 阶段一验收标准
- [ ] 所有核心数据模型定义完成
- [ ] 所有单元测试通过
- [ ] 代码覆盖率 >85%
- [ ] API文档生成完成
- [ ] 设计文档更新完成

---

## 阶段二：工具系统实现（Week 3-4）

### 2.1 工具基类与注册中心
**优先级**: P0  
**预估工时**: 4天  
**依赖**: 阶段一完成

#### 任务描述
实现工具基类和统一的工具注册中心。

#### 具体步骤

**Step 1: 创建工具基类**
```python
# 文件: derisk/core/tools/base.py

任务内容:
1. 创建 ToolBase 抽象类
   - __init__(self, metadata: Optional[ToolMetadata] = None)
   - _metadata 属性
   - metadata 属性（延迟加载）

2. 实现抽象方法
   - _define_metadata() -> ToolMetadata
   - execute(args, context) -> ToolResult

3. 实现实例方法
   - initialize(context) -> bool
   - _do_initialize(context)
   - cleanup()
   - execute_safe(args, context) -> ToolResult
   - execute_stream(args, context) -> AsyncIterator[str]

验收标准:
- 抽象类设计合理
- 安全执行机制正确
- 支持异步和流式
```

**Step 2: 创建工具结果类**
```python
任务内容:
1. 创建 ToolResult 数据类
   - success: bool
   - output: str
   - error: Optional[str]
   - metadata: Dict[str, Any]

验收标准:
- 支持成功和失败两种状态
```

**Step 3: 实现工具注册中心**
```python
任务内容:
1. 创建 ToolRegistry 单例类
   - _tools: Dict[str, ToolBase]
   - _categories: Dict[str, List[str]]
   - _tags: Dict[str, List[str]]

2. 实现注册方法
   - register(tool: ToolBase) -> ToolRegistry
   - unregister(name: str) -> bool

3. 实现查询方法
   - get(name: str) -> Optional[ToolBase]
   - list_all() -> List[ToolBase]
   - list_names() -> List[str]
   - list_by_category(category: str) -> List[ToolBase]
   - list_by_tag(tag: str) -> List[ToolBase]

4. 实现执行方法
   - get_openai_tools(filter_func) -> List[Dict]
   - execute(name, args, context) -> ToolResult

验收标准:
- 单例模式正确
- 索引机制高效
- 支持OpenAI格式
```

**Step 4: 实现全局注册函数**
```python
任务内容:
1. 创建全局 tool_registry 实例
2. 创建 register_tool() 装饰器

验收标准:
- 全局访问正常
```

#### 测试要求
```python
# 文件: tests/unit/test_tool_base.py

测试用例:
1. test_tool_base_initialization - 初始化测试
2. test_tool_registry_singleton - 单例测试
3. test_tool_registration - 注册测试
4. test_tool_execution - 执行测试
5. test_openai_spec_generation - OpenAI规范生成测试

覆盖率要求: >80%
```

#### 完成标准
- [ ] ToolBase 抽象类实现完成
- [ ] ToolResult 类实现完成
- [ ] ToolRegistry 单例实现完成
- [ ] 全局注册函数实现完成
- [ ] 单元测试全部通过

---

### 2.2 工具装饰器
**优先级**: P0  
**预估工时**: 2天  
**依赖**: 2.1完成

#### 任务描述
实现工具装饰器，支持快速定义工具。

#### 具体步骤

**Step 1: 实现主装饰器**
```python
# 文件: derisk/core/tools/decorators.py

任务内容:
1. 实现 tool() 装饰器
   - 支持所有ToolMetadata字段
   - 自动创建FunctionTool类
   - 自动注册到registry

验收标准:
- 装饰器语法正确
- 自动注册成功
```

**Step 2: 实现快速定义装饰器**
```python
任务内容:
1. 实现 shell_tool() 装饰器
2. 实现 file_read_tool() 装饰器
3. 实现 file_write_tool() 装饰器

验收标准:
- 默认授权配置合理
```

#### 测试要求
```python
测试用例:
1. test_tool_decorator - 装饰器测试
2. test_quick_decorators - 快速定义测试
```

#### 完成标准
- [ ] tool() 装饰器实现完成
- [ ] 快速定义装饰器实现完成
- [ ] 测试全部通过

---

### 2.3 内置工具实现
**优先级**: P0  
**预估工时**: 4天  
**依赖**: 2.2完成

#### 任务描述
实现一组内置工具，覆盖文件系统、Shell、网络、代码等类别。

#### 具体步骤

**Step 1: 实现文件系统工具**
```python
# 文件: derisk/core/tools/builtin/file_system.py

任务内容:
1. read - 读取文件
   - 风险: SAFE
   - 无需授权

2. write - 写入文件
   - 风险: MEDIUM
   - 需要授权

3. edit - 编辑文件
   - 风险: MEDIUM
   - 需要授权

4. glob - 文件搜索
   - 风险: SAFE
   - 无需授权

5. grep - 内容搜索
   - 风险: SAFE
   - 无需授权

验收标准:
- 所有工具可正常执行
- 授权配置正确
```

**Step 2: 实现Shell工具**
```python
# 文件: derisk/core/tools/builtin/shell.py

任务内容:
1. bash - 执行Shell命令
   - 风险: HIGH
   - 需要: requires_authorization, risk_categories=[SHELL_EXECUTE]
   - 支持危险命令检测

验收标准:
- 命令执行正确
- 危险命令检测有效
```

**Step 3: 实现网络工具**
```python
# 文件: derisk/core/tools/builtin/network.py

任务内容:
1. webfetch - 获取网页内容
   - 风险: LOW
   - 需要授权

2. websearch - 网络搜索
   - 风险: LOW
   - 需要授权

验收标准:
- 网络请求正确
```

**Step 4: 实现代码工具**
```python
# 文件: derisk/core/tools/builtin/code.py

任务内容:
1. analyze - 代码分析
   - 风险: SAFE
   - 无需授权

验收标准:
- 代码分析功能正确
```

**Step 5: 创建工具注册函数**
```python
# 文件: derisk/core/tools/builtin/__init__.py

任务内容:
1. 实现 register_builtin_tools(registry: ToolRegistry)
   - 注册所有内置工具

验收标准:
- 所有工具正确注册
```

#### 测试要求
```python
# 文件: tests/unit/test_builtin_tools.py

测试用例:
1. test_file_system_tools - 文件系统工具测试
2. test_shell_tool - Shell工具测试
3. test_network_tools - 网络工具测试
4. test_tool_registration - 工具注册测试

覆盖率要求: >75%
```

#### 完成标准
- [ ] 文件系统工具实现完成
- [ ] Shell工具实现完成
- [ ] 网络工具实现完成
- [ ] 代码工具实现完成
- [ ] 工具注册函数实现完成
- [ ] 所有工具测试通过

---

### 阶段二验收标准
- [ ] 工具基类实现完成
- [ ] 工具注册中心实现完成
- [ ] 内置工具集实现完成（至少10个工具）
- [ ] 所有工具测试通过
- [ ] 可以通过OpenAI格式调用工具
- [ ] 测试覆盖率 >80%

---

## 阶段三：授权系统实现（Week 5-6）

### 3.1 授权引擎核心
**优先级**: P0  
**预估工时**: 5天  
**依赖**: 阶段一、二完成

#### 任务描述
实现核心授权引擎，包含授权决策、缓存、审计等功能。

#### 具体步骤

**Step 1: 实现授权上下文和结果**
```python
# 文件: derisk/core/authorization/engine.py

任务内容:
1. 创建 AuthorizationDecision 枚举
   - GRANTED, DENIED, NEED_CONFIRMATION, NEED_LLM_JUDGMENT, CACHED

2. 创建 AuthorizationContext 类
   - session_id, user_id, agent_name
   - tool_name, tool_metadata, arguments
   - timestamp

3. 创建 AuthorizationResult 类
   - decision, action, reason
   - cached, cache_key
   - user_message, risk_assessment, llm_judgment

验收标准:
- 数据结构完整
```

**Step 2: 实现授权缓存**
```python
# 文件: derisk/core/authorization/cache.py

任务内容:
1. 创建 AuthorizationCache 类
   - _cache: Dict[str, tuple]
   - _ttl: int

2. 实现 get(key) 方法
3. 实现 set(key, granted) 方法
4. 实现 clear(session_id) 方法
5. 实现 _build_cache_key(ctx) 方法

验收标准:
- 缓存机制正确
- TTL过期正确
```

**Step 3: 实现风险评估器**
```python
# 文件: derisk/core/authorization/risk_assessor.py

任务内容:
1. 创建 RiskAssessor 类
2. 实现 assess() 静态方法
   - 计算风险分数（0-100）
   - 识别风险因素
   - 生成建议
   - 特定工具的风险检测

3. 实现 _score_to_level() 方法
4. 实现 _get_recommendation() 方法

验收标准:
- 风险评估准确
- 特定工具检测有效
```

**Step 4: 实现授权引擎**
```python
# 文件: derisk/core/authorization/engine.py

任务内容:
1. 创建 AuthorizationEngine 类
   - llm_adapter: Optional[Any]
   - cache: AuthorizationCache
   - risk_assessor: RiskAssessor
   - audit_logger: Optional[Any]
   - _stats: Dict[str, int]

2. 实现 check_authorization() 主方法
   - 检查缓存
   - 获取权限动作
   - 风险评估
   - LLM判断（可选）
   - 用户确认（可选）
   - 记录审计日志

3. 实现 _handle_allow() 方法
4. 实现 _handle_deny() 方法
5. 实现 _handle_user_confirmation() 方法
6. 实现 _llm_judgment() 方法
7. 实现 _log_authorization() 方法

验收标准:
- 授权决策正确
- 所有分支覆盖
```

**Step 5: 实现全局函数**
```python
任务内容:
1. 创建全局 _authorization_engine 实例
2. 实现 get_authorization_engine() 函数
3. 实现 set_authorization_engine() 函数

验收标准:
- 全局访问正常
```

#### 测试要求
```python
# 文件: tests/unit/test_authorization_engine.py

测试用例:
1. test_authorization_cache - 缓存测试
2. test_risk_assessment - 风险评估测试
3. test_authorization_decision - 授权决策测试
4. test_llm_judgment - LLM判断测试
5. test_user_confirmation - 用户确认测试
6. test_audit_logging - 审计日志测试

覆盖率要求: >80%
```

#### 完成标准
- [ ] AuthorizationEngine 类实现完成
- [ ] AuthorizationCache 类实现完成
- [ ] RiskAssessor 类实现完成
- [ ] 授权流程测试通过
- [ ] 代码覆盖率 >80%

---

### 3.2 授权集成与测试
**优先级**: P0  
**预估工时**: 2天  
**依赖**: 3.1完成

#### 任务描述
完成授权系统的集成测试和性能优化。

#### 具体步骤

**Step 1: 集成测试**
```python
# 文件: tests/integration/test_authorization_integration.py

测试场景:
1. 工具执行授权流程
2. 会话缓存功能
3. LLM判断集成
4. 多Agent授权隔离

验收标准:
- 所有场景测试通过
```

**Step 2: 性能测试**
```python
测试内容:
1. 授权决策延迟 < 50ms（不含用户确认）
2. 缓存命中率 > 80%
3. 并发授权处理能力

验收标准:
- 性能达标
```

**Step 3: 安全测试**
```python
测试内容:
1. 权限绕过测试
2. 注入攻击测试
3. 敏感参数泄露测试

验收标准:
- 无安全漏洞
```

#### 完成标准
- [ ] 集成测试全部通过
- [ ] 性能测试达标
- [ ] 安全测试通过

---

### 阶段三验收标准
- [ ] 授权引擎实现完成
- [ ] 风险评估器实现完成
- [ ] 缓存机制正常工作
- [ ] LLM判断集成完成
- [ ] 审计日志记录正常
- [ ] 所有测试通过
- [ ] 性能达标

---

## 阶段四：交互系统实现（Week 7-8）

### 4.1 交互网关
**优先级**: P0  
**预估工时**: 4天  
**依赖**: 阶段一完成

#### 任务描述
实现统一的交互网关，支持WebSocket实时通信。

#### 具体步骤

**Step 1: 实现连接管理器**
```python
# 文件: derisk/core/interaction/gateway.py

任务内容:
1. 创建 ConnectionManager 抽象类
   - has_connection(session_id) -> bool
   - send(session_id, message) -> bool
   - broadcast(message) -> int

2. 创建 MemoryConnectionManager 类
   - add_connection(session_id)
   - remove_connection(session_id)

验收标准:
- 连接管理正确
```

**Step 2: 实现状态存储**
```python
任务内容:
1. 创建 StateStore 抽象类
   - get(key) -> Optional[Dict]
   - set(key, value, ttl) -> bool
   - delete(key) -> bool
   - exists(key) -> bool

2. 创建 MemoryStateStore 类

验收标准:
- 存储功能正确
```

**Step 3: 实现交互网关**
```python
任务内容:
1. 创建 InteractionGateway 类
   - connection_manager: ConnectionManager
   - state_store: StateStore
   - _pending_requests: Dict[str, asyncio.Future]
   - _session_requests: Dict[str, List[str]]
   - _stats: Dict[str, int]

2. 实现 send() 方法
3. 实现 send_and_wait() 方法
4. 实现 deliver_response() 方法
5. 实现 get_pending_requests() 方法
6. 实现 cancel_request() 方法

验收标准:
- 请求分发正确
- 响应投递正确
```

**Step 4: 实现全局函数**
```python
任务内容:
1. 创建全局 _gateway_instance
2. 实现 get_interaction_gateway() 函数
3. 实现 set_interaction_gateway() 函数

验收标准:
- 全局访问正常
```

#### 测试要求
```python
# 文件: tests/unit/test_interaction_gateway.py

测试用例:
1. test_send_request - 发送请求测试
2. test_send_and_wait - 等待响应测试
3. test_deliver_response - 投递响应测试
4. test_cancel_request - 取消请求测试

覆盖率要求: >80%
```

#### 完成标准
- [ ] ConnectionManager 实现完成
- [ ] StateStore 实现完成
- [ ] InteractionGateway 实现完成
- [ ] 测试全部通过

---

### 4.2 WebSocket服务端
**优先级**: P0  
**预估工时**: 3天  
**依赖**: 4.1完成

#### 任务描述
实现WebSocket服务端，支持实时交互通信。

#### 具体步骤

**Step 1: 实现WebSocket管理器**
```python
# 文件: derisk_serve/websocket/manager.py

任务内容:
1. 创建 WebSocketManager 类
   - 管理WebSocket连接
   - 实现连接池
   - 实现心跳机制

验收标准:
- 连接管理正确
```

**Step 2: 实现WebSocket端点**
```python
# 文件: derisk_serve/websocket/interaction.py

任务内容:
1. 创建 WebSocket 端点 /ws/interaction/{session_id}
2. 处理连接建立
3. 处理消息接收
4. 处理连接断开

验收标准:
- WebSocket连接正常
```

**Step 3: 实现消息处理器**
```python
任务内容:
1. 处理 interaction_response 类型消息
2. 处理 ping 类型消息
3. 处理其他类型消息

验收标准:
- 消息处理正确
```

#### 测试要求
```python
# 文件: tests/integration/test_websocket.py

测试用例:
1. test_websocket_connection - 连接测试
2. test_websocket_message_exchange - 消息交换测试
3. test_websocket_disconnect - 断开测试

覆盖率要求: >75%
```

#### 完成标准
- [ ] WebSocket管理器实现完成
- [ ] WebSocket端点实现完成
- [ ] 消息处理器实现完成
- [ ] 测试全部通过

---

### 4.3 REST API
**优先级**: P1  
**预估工时**: 2天  
**依赖**: 4.2完成

#### 任务描述
实现交互相关的REST API。

#### 具体步骤

**Step 1: 实现响应提交API**
```python
# 文件: derisk_serve/api/v2/interaction.py

任务内容:
1. POST /api/v2/interaction/respond
   - 提交交互响应

验收标准:
- API可正常调用
```

**Step 2: 实现待处理请求API**
```python
任务内容:
1. GET /api/v2/interaction/pending/{session_id}
   - 获取待处理请求列表

验收标准:
- API可正常调用
```

#### 完成标准
- [ ] 所有API实现完成
- [ ] API文档生成完成

---

### 阶段四验收标准
- [ ] 交互网关实现完成
- [ ] WebSocket服务实现完成
- [ ] REST API实现完成
- [ ] 所有交互类型支持
- [ ] 测试全部通过

---

## 阶段五：Agent集成（Week 9-10）

### 5.1 Agent基类实现
**优先级**: P0  
**预估工时**: 5天  
**依赖**: 阶段三、四完成

#### 任务描述
实现统一的Agent基类，集成工具执行和授权检查。

#### 具体步骤

**Step 1: 创建Agent状态**
```python
# 文件: derisk/core/agent/base.py

任务内容:
1. 定义 AgentState 枚举
   - IDLE, RUNNING, WAITING, COMPLETED, FAILED

验收标准:
- 状态定义完整
```

**Step 2: 实现AgentBase类**
```python
任务内容:
1. 创建 AgentBase 抽象类
   - info: AgentInfo
   - tools: ToolRegistry
   - auth_engine: AuthorizationEngine
   - interaction: InteractionGateway
   - _state: AgentState
   - _session_id: Optional[str]
   - _current_step: int

2. 实现抽象方法
   - think(message, **kwargs) -> AsyncIterator[str]
   - decide(message, **kwargs) -> Dict[str, Any]
   - act(action, **kwargs) -> Any

验收标准:
- 抽象类设计合理
```

**Step 3: 实现工具执行方法**
```python
任务内容:
1. 实现 execute_tool() 方法
   - 获取工具
   - 授权检查
   - 执行工具
   - 返回结果

2. 实现 _check_authorization() 方法
3. 实现 _handle_user_confirmation() 方法

验收标准:
- 工具执行流程正确
- 授权检查集成
```

**Step 4: 实现用户交互方法**
```python
任务内容:
1. 实现 ask_user() 方法
2. 实现 confirm() 方法
3. 实现 select() 方法
4. 实现 notify() 方法

验收标准:
- 所有交互方法可用
```

**Step 5: 实现运行循环**
```python
任务内容:
1. 实现 run() 方法
   - 思考 -> 决策 -> 行动 循环
   - 步数限制
   - 状态管理

验收标准:
- 运行循环正确
```

#### 测试要求
```python
# 文件: tests/unit/test_agent_base.py

测试用例:
1. test_agent_initialization - 初始化测试
2. test_tool_execution - 工具执行测试
3. test_authorization_check - 授权检查测试
4. test_user_interaction - 用户交互测试
5. test_run_loop - 运行循环测试

覆盖率要求: >80%
```

#### 完成标准
- [ ] AgentBase 类实现完成
- [ ] 工具执行集成完成
- [ ] 授权检查集成完成
- [ ] 用户交互集成完成
- [ ] 运行循环实现完成
- [ ] 测试全部通过

---

### 5.2 内置Agent实现
**优先级**: P1  
**预估工时**: 3天  
**依赖**: 5.1完成

#### 任务描述
实现几个内置的Agent实现，展示框架能力。

#### 具体步骤

**Step 1: 实现生产Agent**
```python
# 文件: derisk/core/agent/production.py

任务内容:
1. 创建 ProductionAgent 类
   - 继承 AgentBase
   - 实现 think()、decide()、act() 方法
   - 集成LLM调用
   - 集成工具选择

验收标准:
- Agent可正常运行
```

**Step 2: 实现规划Agent**
```python
# 文件: derisk/core/agent/builtin/plan.py

任务内容:
1. 创建 PlanAgent 类
   - 只读工具权限
   - 分析和探索能力

验收标准:
- 只读权限生效
```

**Step 3: 实现子Agent示例**
```python
任务内容:
1. 创建 ExploreSubagent 类
2. 创建 CodeSubagent 类

验收标准:
- 子Agent权限受限
```

#### 测试要求
```python
# 文件: tests/integration/test_builtin_agents.py

测试用例:
1. test_production_agent - 生产Agent测试
2. test_plan_agent - 规划Agent测试
3. test_subagent_permissions - 子Agent权限测试

覆盖率要求: >75%
```

#### 完成标准
- [ ] ProductionAgent 实现完成
- [ ] PlanAgent 实现完成
- [ ] 子Agent示例实现完成
- [ ] 测试全部通过

---

### 阶段五验收标准
- [ ] AgentBase 基类实现完成
- [ ] 授权检查完全集成
- [ ] 工具执行正常
- [ ] 用户交互正常
- [ ] 内置Agent实现完成
- [ ] 所有测试通过

---

## 阶段六：前端开发（Week 11-12）

### 6.1 类型定义与API服务
**优先级**: P0  
**预估工时**: 2天  
**依赖**: 阶段四完成

#### 任务描述
创建前端的类型定义和API服务层。

#### 具体步骤

**Step 1: 创建类型定义**
```typescript
// 文件: web/src/types/tool.ts

任务内容:
1. 定义 ToolCategory, RiskLevel, RiskCategory 枚举
2. 定义 ToolParameter, AuthorizationRequirement 接口
3. 定义 ToolMetadata 接口

验收标准:
- 类型定义完整
```

**Step 2: 创建授权类型**
```typescript
// 文件: web/src/types/authorization.ts

任务内容:
1. 定义 PermissionAction, AuthorizationMode 枚举
2. 定义 PermissionRule, AuthorizationConfig 接口

验收标准:
- 类型定义完整
```

**Step 3: 创建交互类型**
```typescript
// 文件: web/src/types/interaction.ts

任务内容:
1. 定义 InteractionType, InteractionStatus 枚举
2. 定义 InteractionRequest, InteractionResponse 接口

验收标准:
- 类型定义完整
```

**Step 4: 创建API服务**
```typescript
// 文件: web/src/services/interactionService.ts

任务内容:
1. 实现 submitResponse() 函数
2. 实现 getPendingRequests() 函数
3. 实现 WebSocket连接管理

验收标准:
- API服务可用
```

#### 完成标准
- [x] 所有类型定义完成
- [x] API服务实现完成

---

### 6.2 交互组件
**优先级**: P0  
**预估工时**: 4天  
**依赖**: 6.1完成

#### 任务描述
实现前端交互组件，支持各种交互类型。

#### 具体步骤

**Step 1: 实现交互管理器**
```typescript
// 文件: web/src/components/interaction/InteractionManager.tsx

任务内容:
1. 创建 InteractionProvider 组件
2. 实现 WebSocket连接
3. 实现响应提交
4. 实现状态管理

验收标准:
- 交互管理正常
```

**Step 2: 实现授权弹窗**
```typescript
// 文件: web/src/components/interaction/AuthorizationDialog.tsx

任务内容:
1. 显示工具信息
2. 显示风险评估
3. 显示参数详情
4. 支持会话级授权选项

验收标准:
- 弹窗显示正确
```

**Step 3: 实现交互处理器**
```typescript
// 文件: web/src/components/interaction/InteractionHandler.tsx

任务内容:
1. 处理TEXT_INPUT类型
2. 处理SINGLE_SELECT类型
3. 处理MULTI_SELECT类型
4. 处理CONFIRMATION类型
5. 处理FILE_UPLOAD类型

验收标准:
- 所有类型处理正确
```

#### 测试要求
- 组件渲染正确
- 交互响应正确
- E2E测试通过

#### 完成标准
- [x] InteractionProvider 组件完成
- [x] AuthorizationDialog 组件完成
- [x] InteractionHandler 组件完成
- [x] 所有交互类型支持
- [x] VisAuthorizationCard VIS组件完成 (d-authorization)

---

### 6.3 配置面板
**优先级**: P1  
**预估工时**: 2天  
**依赖**: 6.2完成

#### 任务描述
实现Agent授权配置面板。

#### 具体步骤

**Step 1: 实现授权配置面板**
```typescript
// 文件: web/src/components/config/AgentAuthorizationConfig.tsx

任务内容:
1. 授权模式选择
2. LLM策略配置
3. 白名单/黑名单配置
4. 高级选项配置

验收标准:
- 配置面板可用
```

**Step 2: 实现工具管理面板**
```typescript
// 文件: web/src/components/config/ToolManagementPanel.tsx

任务内容:
1. 工具列表展示
2. 工具详情查看
3. 工具授权配置

验收标准:
- 管理面板可用
```

#### 完成标准
- [x] 授权配置面板完成
- [x] 工具管理面板完成
- [x] 配置面板集成到设置页面

---

### 6.4 E2E测试
**优先级**: P1  
**预估工时**: 2天  
**依赖**: 6.3完成

#### 任务描述
实现端到端测试，验证整个系统的功能。

#### 具体步骤

**Step 1: 授权流程测试**
```python
# 文件: tests/e2e/test_authorization_flow.py

测试场景:
1. 工具执行授权流程
2. 会话缓存功能
3. 风险评估显示
4. 用户确认流程

验收标准:
- 所有场景通过
```

**Step 2: 交互流程测试**
```python
测试场景:
1. 文本输入交互
2. 选择交互
3. 确认交互
4. 文件上传交互

验收标准:
- 所有场景通过
```

**Step 3: Agent运行测试**
```python
测试场景:
1. Agent执行工具
2. 授权检查
3. 用户交互
4. 结果返回

验收标准:
- 所有场景通过
```

#### 完成标准
- [x] 所有E2E测试通过
- [x] 测试覆盖率 >70%

---

### 阶段六验收标准
- [x] 所有前端组件实现完成
- [x] WebSocket通信正常
- [x] 所有交互类型支持
- [x] 配置面板可用
- [x] E2E测试全部通过

---

## 📊 质量标准

### 代码质量
- **测试覆盖率**: 单元测试 >80%，集成测试 >75%，E2E测试 >70%
- **代码规范**: 遵循PEP8（Python）和ESLint（TypeScript）
- **文档覆盖**: 所有公共API有文档字符串
- **类型检查**: Python使用type hints，TypeScript严格模式

### 性能标准
- **授权决策延迟**: < 50ms（不含用户确认）
- **工具执行延迟**: < 1s（简单工具）
- **WebSocket延迟**: < 100ms
- **前端渲染**: < 100ms首次渲染

### 安全标准
- **权限检查**: 所有敏感操作必须检查权限
- **输入验证**: 所有用户输入必须验证
- **敏感信息**: 不记录敏感信息（密码、token等）
- **审计日志**: 记录所有关键操作

---

## 📈 进度追踪

### 周进度检查清单

**Week 2 检查点:**
- [ ] 所有核心模型测试通过
- [ ] API文档生成
- [ ] 设计文档更新

**Week 4 检查点:**
- [ ] 工具系统基本可用
- [ ] 内置工具测试通过
- [ ] OpenAI格式兼容

**Week 6 检查点:**
- [ ] 授权引擎可用
- [ ] 风险评估准确
- [ ] 缓存机制正常

**Week 8 检查点:**
- [ ] WebSocket通信正常
- [ ] 所有交互类型支持
- [ ] REST API可用

**Week 10 检查点:**
- [ ] Agent框架可用
- [ ] 授权检查集成
- [ ] 内置Agent实现

**Week 12 检查点:**
- [ ] 前端组件完成
- [ ] E2E测试通过
- [ ] 文档完整

---

## 🎯 交付清单

### 代码交付物
- [ ] `derisk/core/tools/` - 工具系统完整实现
- [ ] `derisk/core/authorization/` - 授权系统完整实现
- [ ] `derisk/core/interaction/` - 交互系统完整实现
- [ ] `derisk/core/agent/` - Agent框架完整实现
- [ ] `derisk_serve/api/v2/` - 所有API实现
- [ ] `web/src/components/` - 所有前端组件

### 文档交付物
- [ ] 架构设计文档（3部分）
- [ ] API文档
- [ ] 开发指南
- [ ] 最佳实践文档
- [ ] 迁移指南

### 测试交付物
- [ ] 单元测试套件（覆盖率 >80%）
- [ ] 集成测试套件（覆盖率 >75%）
- [ ] E2E测试套件（覆盖率 >70%）
- [ ] 性能测试报告
- [ ] 安全测试报告

---

## 🚀 开始实施

Agent现在可以根据此文档开始实施开发：

1. **从阶段一开始** - 完成核心模型定义
2. **按顺序执行** - 遵循依赖关系
3. **每步验收** - 确保质量标准
4. **持续测试** - 保持测试覆盖率
5. **文档同步** - 更新设计和API文档

**下一步**: 开始执行阶段一任务 1.1 - 工具元数据模型

---

**文档版本**: v2.0  
**最后更新**: 2026-03-02  
**维护团队**: Derisk开发团队