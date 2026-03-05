# Derisk 统一工具架构与授权系统 - 产品使用场景与实施指南

**版本**: v2.0  
**作者**: 架构团队  
**日期**: 2026-03-02  

---

## 目录

- [十一、产品使用场景](#十一产品使用场景)
- [十二、开发实施指南](#十二开发实施指南)
- [十三、监控与运维](#十三监控与运维)
- [十四、最佳实践](#十四最佳实践)
- [十五、常见问题FAQ](#十五常见问题faq)
- [十六、总结与展望](#十六总结与展望)

---

## 十一、产品使用场景

### 11.1 场景一：代码开发助手

**场景描述**：开发者使用Agent进行代码编写、调试和部署

**授权流程**：

```
┌─────────────┐
│  开发者     │
│  发起请求   │
│"帮我重构这个│
│  函数"      │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│         Agent (STRICT模式)           │
│                                      │
│  1. 分析代码结构                      │
│     - read file.py  ✓ (SAFE, 自动)  │
│     - grep "function"  ✓ (SAFE)     │
│                                      │
│  2. 修改代码                          │
│     - edit file.py  ⚠️ (MEDIUM)     │
│       └─► 弹出授权确认框             │
│                                      │
│  3. 运行测试                          │
│     - bash "pytest"  ⚠️ (HIGH)      │
│       └─► 弹出授权确认框             │
│                                      │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│  完成重构   │
│  返回结果   │
└─────────────┘
```

**配置示例**：

```python
# 开发助手Agent配置
DEV_ASSISTANT_CONFIG = AgentInfo(
    name="dev-assistant",
    description="代码开发助手",
    mode=AgentMode.PRIMARY,
    
    # 授权配置
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.STRICT,
        llm_policy=LLMJudgmentPolicy.BALANCED,
        
        # 白名单：只读操作自动通过
        whitelist_tools=[
            "read", "glob", "grep", "webfetch",
        ],
        
        # 会话缓存：一次授权有效
        session_cache_enabled=True,
        authorization_timeout=300,
    ),
    
    # 工具策略
    tool_policy=ToolSelectionPolicy(
        included_categories=[
            ToolCategory.FILE_SYSTEM,
            ToolCategory.CODE,
            ToolCategory.SHELL,
        ],
        excluded_tools=["delete"],  # 禁止删除
    ),
    
    max_steps=30,
    capabilities=[
        AgentCapability.CODE_GENERATION,
        AgentCapability.FILE_MANIPULATION,
        AgentCapability.SHELL_EXECUTION,
    ],
)
```

**用户交互流程**：

```
1. Agent: "发现需要修改 file.py，请确认授权"
   
   [授权弹窗]
   ┌────────────────────────────────────┐
   │ ⚠️ 工具执行授权                     │
   ├────────────────────────────────────┤
   │ 工具: edit                          │
   │ 文件: /src/utils/helper.py         │
   │ 风险等级: MEDIUM                    │
   │                                    │
   │ 修改内容:                           │
   │ - 重命名函数 process() -> handle() │
   │ - 优化代码结构                      │
   │                                    │
   │ ☑ 在此会话中始终允许                │
   │                                    │
   │        [拒绝]  [允许执行]           │
   └────────────────────────────────────┘

2. 用户点击"允许执行"

3. Agent继续执行，完成重构

4. Agent: "重构完成，是否运行测试验证？"
   
   [确认弹窗]
   ┌────────────────────────────────────┐
   │ 请确认                              │
   ├────────────────────────────────────┤
   │ 重构完成，建议运行测试验证修改。    │
   │                                    │
   │        [跳过]  [运行测试]           │
   └────────────────────────────────────┘
```

### 11.2 场景二：数据分析助手

**场景描述**：业务人员使用Agent进行数据分析和报表生成

**授权流程**：

```python
# 数据分析助手配置
DATA_ANALYST_CONFIG = AgentInfo(
    name="data-analyst",
    description="数据分析助手",
    mode=AgentMode.PRIMARY,
    
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.MODERATE,  # 适度模式
        
        # LLM智能判断
        llm_policy=LLMJudgmentPolicy.CONSERVATIVE,
        
        # 工具级别覆盖
        tool_overrides={
            "database_query": PermissionAction.ASK,
            "export_file": PermissionAction.ASK,
        },
        
        # 白名单
        whitelist_tools=["read", "grep", "analyze"],
        
        # 黑名单：禁止执行shell
        blacklist_tools=["bash", "shell"],
    ),
    
    tool_policy=ToolSelectionPolicy(
        included_categories=[
            ToolCategory.FILE_SYSTEM,
            ToolCategory.DATA,
        ],
        excluded_categories=[ToolCategory.SHELL],
    ),
    
    max_steps=20,
)
```

**交互流程**：

```
用户: "分析上个月的销售数据，生成报表"

Agent思考:
1. 读取销售数据
2. 数据分析处理
3. 生成可视化图表
4. 导出报表

执行:
- read "sales_2026_02.csv"  ✓ 自动通过
- analyze --type=statistics  ✓ 自动通过 (LLM判断安全)
- database_query "SELECT..."  ⚠️ 需要确认 (访问数据库)
  
  [授权弹窗]
  ┌────────────────────────────────────┐
  │ 🔍 数据库查询授权                   │
  ├────────────────────────────────────┤
  │ Agent请求查询数据库                 │
  │                                    │
  │ SQL: SELECT * FROM sales WHERE...  │
  │ 风险: 数据访问                      │
  │                                    │
  │        [拒绝]  [允许查询]           │
  └────────────────────────────────────┘

- export "report.xlsx"  ⚠️ 需要确认 (文件导出)
  
  [授权弹窗]
  ┌────────────────────────────────────┐
  │ 📁 文件导出授权                     │
  ├────────────────────────────────────┤
  │ Agent请求导出报表文件               │
  │                                    │
  │ 文件: /reports/sales_report.xlsx   │
  │ 大小: ~2MB                          │
  │                                    │
  │        [拒绝]  [导出文件]           │
  └────────────────────────────────────┘
```

### 11.3 场景三：运维自动化助手

**场景描述**：运维人员使用Agent进行服务器管理和部署

**配置示例**：

```python
# 运维助手配置
OPS_ASSISTANT_CONFIG = AgentInfo(
    name="ops-assistant",
    description="运维自动化助手",
    mode=AgentMode.PRIMARY,
    
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.STRICT,  # 严格模式
        
        # 无LLM判断，必须人工确认
        llm_policy=LLMJudgmentPolicy.DISABLED,
        
        # 关键操作必须确认
        tool_overrides={
            "bash": PermissionAction.ASK,
            "systemctl": PermissionAction.ASK,
            "docker": PermissionAction.ASK,
        },
        
        # 禁用会话缓存（每次都需要确认）
        session_cache_enabled=False,
        
        # 超时时间较短
        authorization_timeout=60,
    ),
    
    tool_policy=ToolSelectionPolicy(
        included_categories=[
            ToolCategory.SHELL,
            ToolCategory.NETWORK,
        ],
    ),
    
    max_steps=15,
)
```

**交互流程**：

```
用户: "部署新版本到生产环境"

Agent: "检测到生产环境部署操作，这是一个关键操作。"

执行:
- bash "kubectl get pods"  ⚠️ 需要确认
  
  [授权弹窗 - 关键操作]
  ┌────────────────────────────────────┐
  │ ⚠️⚠️⚠️ 高风险操作授权               │
  ├────────────────────────────────────┤
  │ 风险等级: CRITICAL                  │
  │                                    │
  │ 操作: 在生产环境执行Shell命令       │
  │                                    │
  │ 命令: kubectl get pods             │
  │ 环境: production                   │
  │                                    │
  │ ⚠️ 警告：此操作将影响生产环境       │
  │                                    │
  │ 风险因素:                           │
  │ - 生产环境访问                      │
  │ - Shell命令执行                     │
  │                                    │
  │ [查看详细影响]                      │
  │                                    │
  │        [拒绝]  [我已了解，允许执行] │
  └────────────────────────────────────┘

- bash "kubectl set image..."  ⚠️ 需要确认 (每次都需确认)
  
  [授权弹窗]
  ┌────────────────────────────────────┐
  │ ⚠️⚠️⚠️ 高风险操作授权               │
  ├────────────────────────────────────┤
  │ 操作: 更新生产环境镜像              │
  │                                    │
  │ 命令: kubectl set image deployment/│
  │       app=app:v2.0                 │
  │                                    │
  │ 预期影响:                           │
  │ - 滚动更新 deployment/app          │
  │ - 约3分钟完成                       │
  │ - 可能出现短暂服务中断              │
  │                                    │
  │ [查看回滚方案]                      │
  │                                    │
  │        [拒绝]  [我已了解，允许执行] │
  └────────────────────────────────────┘
```

### 11.4 场景四：多Agent协作

**场景描述**：主Agent委派任务给子Agent，子Agent在受限权限下执行

**架构设计**：

```
┌─────────────────────────────────────────────────────────────┐
│                        主Agent (Primary)                    │
│                                                             │
│  Authorization: STRICT                                      │
│  - 完整工具权限                                              │
│  - 可以委派任务给子Agent                                     │
│                                                             │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      │ 任务委派
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
   ┌─────────┐   ┌─────────┐   ┌─────────┐
   │ 子Agent │   │ 子Agent │   │ 子Agent │
   │ (探索)  │   │ (编码)  │   │ (测试)  │
   └─────────┘   └─────────┘   └─────────┘
        │             │             │
        │             │             │
   Authorization:  Authorization:  Authorization:
   PERMISSIVE      STRICT         MODERATE
   
   只读权限:        读写权限:       测试权限:
   - read          - read          - bash (pytest)
   - glob          - write         - read
   - grep          - edit          - glob
```

**代码实现**：

```python
# 主Agent配置
PRIMARY_AGENT = AgentInfo(
    name="primary",
    mode=AgentMode.PRIMARY,
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.STRICT,
    ),
    subagents=["explore", "code", "test"],
    collaboration_mode="parallel",
)

# 探索子Agent
EXPLORE_SUBAGENT = AgentInfo(
    name="explore",
    mode=AgentMode.SUBAGENT,
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.PERMISSIVE,
        whitelist_tools=["read", "glob", "grep", "webfetch"],
        blacklist_tools=["write", "edit", "bash", "delete"],
    ),
    tool_policy=ToolSelectionPolicy(
        included_categories=[ToolCategory.FILE_SYSTEM],
    ),
    max_steps=10,
)

# 编码子Agent
CODE_SUBAGENT = AgentInfo(
    name="code",
    mode=AgentMode.SUBAGENT,
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.STRICT,
        tool_overrides={
            "bash": PermissionAction.ASK,  # Shell需要确认
        },
    ),
    tool_policy=ToolSelectionPolicy(
        included_categories=[ToolCategory.FILE_SYSTEM, ToolCategory.CODE],
    ),
    max_steps=15,
)

# 测试子Agent
TEST_SUBAGENT = AgentInfo(
    name="test",
    mode=AgentMode.SUBAGENT,
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.MODERATE,
        whitelist_tools=["bash", "read", "glob"],
    ),
    tool_policy=ToolSelectionPolicy(
        included_tools=["bash", "read", "glob", "grep"],
    ),
    max_steps=10,
)
```

---

## 十二、开发实施指南

### 12.1 目录结构

```
derisk/
├── core/                          # 核心模块
│   ├── tools/                     # 工具系统
│   │   ├── __init__.py
│   │   ├── base.py               # 工具基类与注册中心
│   │   ├── metadata.py           # 工具元数据模型
│   │   ├── decorators.py         # 工具装饰器
│   │   ├── builtin/              # 内置工具
│   │   │   ├── __init__.py
│   │   │   ├── file_system.py    # 文件系统工具
│   │   │   ├── shell.py          # Shell工具
│   │   │   ├── network.py        # 网络工具
│   │   │   └── code.py           # 代码工具
│   │   └── plugins/              # 插件工具
│   │       └── README.md
│   │
│   ├── authorization/             # 授权系统
│   │   ├── __init__.py
│   │   ├── model.py              # 授权模型
│   │   ├── engine.py             # 授权引擎
│   │   ├── risk_assessor.py      # 风险评估器
│   │   └── cache.py              # 授权缓存
│   │
│   ├── interaction/               # 交互系统
│   │   ├── __init__.py
│   │   ├── protocol.py           # 交互协议
│   │   ├── gateway.py            # 交互网关
│   │   └── handlers/             # 交互处理器
│   │       ├── cli.py
│   │       ├── websocket.py
│   │       └── api.py
│   │
│   ├── agent/                     # Agent系统
│   │   ├── __init__.py
│   │   ├── base.py               # Agent基类
│   │   ├── info.py               # Agent配置
│   │   ├── production.py         # 生产Agent
│   │   ├── builtin/              # 内置Agent
│   │   │   ├── primary.py
│   │   │   ├── plan.py
│   │   │   └── subagent.py
│   │   └── multi_agent/          # 多Agent协作
│   │       ├── orchestrator.py
│   │       ├── router.py
│   │       └── coordinator.py
│   │
│   ├── audit/                     # 审计系统
│   │   ├── __init__.py
│   │   ├── logger.py             # 审计日志
│   │   ├── models.py             # 审计模型
│   │   └── analytics.py          # 审计分析
│   │
│   └── utils/                     # 工具函数
│       ├── __init__.py
│       ├── config.py             # 配置管理
│       └── exceptions.py         # 异常定义
│
├── serve/                         # 服务层
│   ├── api/                       # REST API
│   │   ├── v2/
│   │   │   ├── tools.py
│   │   │   ├── authorization.py
│   │   │   ├── interaction.py
│   │   │   └── agents.py
│   │   └── dependencies.py
│   │
│   ├── websocket/                 # WebSocket
│   │   ├── interaction.py
│   │   └── manager.py
│   │
│   └── middleware/                # 中间件
│       ├── auth.py
│       ├── rate_limit.py
│       └── logging.py
│
├── web/                           # 前端
│   ├── src/
│   │   ├── types/                # 类型定义
│   │   │   ├── tool.ts
│   │   │   ├── authorization.ts
│   │   │   └── interaction.ts
│   │   │
│   │   ├── components/           # 组件
│   │   │   ├── interaction/
│   │   │   │   ├── InteractionManager.tsx
│   │   │   │   ├── AuthorizationDialog.tsx
│   │   │   │   └── InteractionHandler.tsx
│   │   │   │
│   │   │   └── config/
│   │   │       ├── AgentAuthorizationConfig.tsx
│   │   │       └── ToolManagementPanel.tsx
│   │   │
│   │   ├── services/             # 服务
│   │   │   ├── toolService.ts
│   │   │   ├── authService.ts
│   │   │   └── interactionService.ts
│   │   │
│   │   └── hooks/                # Hooks
│   │       ├── useInteraction.ts
│   │       └── useAuthorization.ts
│   │
│   └── public/
│
├── tests/                         # 测试
│   ├── unit/
│   │   ├── test_tools.py
│   │   ├── test_authorization.py
│   │   └── test_interaction.py
│   │
│   ├── integration/
│   │   ├── test_agent_flow.py
│   │   └── test_multi_agent.py
│   │
│   └── e2e/
│       ├── test_authorization_flow.py
│       └── test_interaction_flow.py
│
├── docs/                          # 文档
│   ├── architecture.md
│   ├── api.md
│   ├── tools.md
│   ├── authorization.md
│   └── interaction.md
│
├── examples/                      # 示例
│   ├── custom_tool.py
│   ├── custom_agent.py
│   └── authorization_config.py
│
├── migrations/                    # 数据库迁移
│   └── v1_to_v2/
│
├── scripts/                       # 脚本
│   ├── migrate_tools.py
│   └── generate_docs.py
│
├── pyproject.toml
├── setup.py
└── README.md
```

### 12.2 实施步骤

#### Step 1: 定义核心模型 (Week 1)

```python
# 1. 创建 core/tools/metadata.py
# 定义 ToolMetadata, ToolParameter, AuthorizationRequirement 等

# 2. 创建 core/authorization/model.py
# 定义 AuthorizationConfig, PermissionRule, PermissionRuleset 等

# 3. 创建 core/interaction/protocol.py
# 定义 InteractionRequest, InteractionResponse, InteractionType 等

# 4. 创建 core/agent/info.py
# 定义 AgentInfo, AgentMode, ToolSelectionPolicy 等
```

#### Step 2: 实现工具系统 (Week 2)

```python
# 1. 创建 core/tools/base.py
class ToolBase(ABC):
    def __init__(self, metadata: ToolMetadata):
        self.metadata = metadata
    
    @abstractmethod
    async def execute(self, args: Dict, context: Dict) -> ToolResult:
        pass

class ToolRegistry:
    def register(self, tool: ToolBase):
        pass
    
    async def execute(self, name: str, args: Dict) -> ToolResult:
        pass

# 2. 创建 core/tools/decorators.py
def tool(name: str, description: str, **kwargs):
    def decorator(func):
        # 创建 FunctionTool 类
        # 注册到 ToolRegistry
        return tool_instance
    return decorator

# 3. 实现内置工具
@tool(
    name="read",
    description="Read file content",
    category=ToolCategory.FILE_SYSTEM,
    authorization=AuthorizationRequirement(
        requires_authorization=False,
        risk_level=RiskLevel.SAFE,
    ),
)
async def read_file(path: str, context: Dict) -> str:
    with open(path) as f:
        return f.read()

@tool(
    name="bash",
    description="Execute bash command",
    category=ToolCategory.SHELL,
    authorization=AuthorizationRequirement(
        requires_authorization=True,
        risk_level=RiskLevel.HIGH,
        risk_categories=[RiskCategory.SHELL_EXECUTE],
    ),
)
async def execute_bash(command: str, context: Dict) -> ToolResult:
    # 执行命令
    pass
```

#### Step 3: 实现授权系统 (Week 3)

```python
# 1. 创建 core/authorization/engine.py
class AuthorizationEngine:
    async def check_authorization(
        self,
        ctx: AuthorizationContext,
        config: AuthorizationConfig,
        user_confirmation_handler: Callable,
    ) -> AuthorizationResult:
        # 1. 检查缓存
        # 2. 获取权限动作
        # 3. 风险评估
        # 4. LLM判断（可选）
        # 5. 用户确认（可选）
        pass

# 2. 创建 core/authorization/risk_assessor.py
class RiskAssessor:
    @staticmethod
    def assess(tool_metadata: ToolMetadata, arguments: Dict) -> Dict:
        # 计算风险分数
        # 识别风险因素
        # 生成建议
        pass

# 3. 创建 core/authorization/cache.py
class AuthorizationCache:
    def get(self, key: str) -> Optional[bool]:
        pass
    
    def set(self, key: str, granted: bool):
        pass
```

### 12.3 数据库设计

```sql
-- 工具注册表
CREATE TABLE tools (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    version VARCHAR(32) NOT NULL,
    description TEXT,
    category VARCHAR(32),
    metadata JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent配置表
CREATE TABLE agents (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    mode VARCHAR(32) NOT NULL,
    authorization_config JSONB NOT NULL,
    tool_policy JSONB,
    max_steps INTEGER DEFAULT 20,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 授权日志表
CREATE TABLE authorization_logs (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64),
    agent_name VARCHAR(128),
    tool_name VARCHAR(128),
    arguments JSONB,
    decision VARCHAR(32) NOT NULL,
    risk_score INTEGER,
    risk_factors JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_session_id (session_id),
    INDEX idx_created_at (created_at)
);

-- 授权缓存表
CREATE TABLE authorization_cache (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    tool_name VARCHAR(128) NOT NULL,
    args_hash VARCHAR(64) NOT NULL,
    granted BOOLEAN NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE INDEX idx_session_tool_args (session_id, tool_name, args_hash),
    INDEX idx_expires_at (expires_at)
);
```

---

## 十三、监控与运维

### 13.1 监控指标

```python
# derisk/core/monitoring/metrics.py

from prometheus_client import Counter, Histogram, Gauge

# 授权相关指标
AUTHORIZATION_TOTAL = Counter(
    'authorization_total',
    'Total authorization checks',
    ['agent_name', 'tool_name', 'decision']
)

AUTHORIZATION_DURATION = Histogram(
    'authorization_duration_seconds',
    'Authorization check duration',
    ['agent_name']
)

AUTHORIZATION_CACHE_HITS = Counter(
    'authorization_cache_hits_total',
    'Authorization cache hits',
    ['agent_name']
)

# 工具执行指标
TOOL_EXECUTION_TOTAL = Counter(
    'tool_execution_total',
    'Total tool executions',
    ['tool_name', 'success']
)

TOOL_EXECUTION_DURATION = Histogram(
    'tool_execution_duration_seconds',
    'Tool execution duration',
    ['tool_name']
)

# 交互相关指标
INTERACTION_TOTAL = Counter(
    'interaction_total',
    'Total interactions',
    ['type', 'status']
)

INTERACTION_DURATION = Histogram(
    'interaction_duration_seconds',
    'Interaction duration',
    ['type']
)

PENDING_INTERACTIONS = Gauge(
    'pending_interactions',
    'Number of pending interactions',
    ['session_id']
)
```

### 13.2 日志规范

```python
# derisk/core/monitoring/logging.py

import structlog

def configure_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

# 使用示例
logger = structlog.get_logger()

async def check_authorization(...):
    log = logger.bind(
        session_id=ctx.session_id,
        agent_name=ctx.agent_name,
        tool_name=ctx.tool_name,
    )
    
    log.info("authorization_check_started")
    
    # ... 检查逻辑 ...
    
    log.info(
        "authorization_check_completed",
        decision=result.decision,
        risk_score=risk_assessment["score"],
        duration_ms=(time.time() - start_time) * 1000,
    )
    
    return result
```

### 13.3 审计追踪

```python
# derisk/core/audit/logger.py

from typing import Dict, Any, Optional
from datetime import datetime
import json

class AuditLogger:
    """审计日志记录器"""
    
    def __init__(self, storage_backend: str = "database"):
        self.storage_backend = storage_backend
    
    async def log_authorization(
        self,
        session_id: str,
        user_id: Optional[str],
        agent_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        decision: str,
        risk_assessment: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """记录授权事件"""
        entry = {
            "event_type": "authorization",
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "user_id": user_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "arguments": self._sanitize_arguments(arguments),
            "decision": decision,
            "risk_score": risk_assessment.get("score"),
            "risk_factors": risk_assessment.get("factors"),
            "metadata": metadata,
        }
        
        await self._write(entry)
    
    async def log_tool_execution(
        self,
        session_id: str,
        agent_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Dict[str, Any],
        duration_ms: float,
    ):
        """记录工具执行事件"""
        entry = {
            "event_type": "tool_execution",
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "arguments": self._sanitize_arguments(arguments),
            "success": result.get("success"),
            "output_length": len(result.get("output", "")),
            "error": result.get("error"),
            "duration_ms": duration_ms,
        }
        
        await self._write(entry)
    
    def _sanitize_arguments(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """清理敏感参数"""
        sensitive_keys = ["password", "token", "secret", "key", "credential"]
        sanitized = {}
        
        for key, value in args.items():
            if any(sk in key.lower() for sk in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value
        
        return sanitized
    
    async def _write(self, entry: Dict[str, Any]):
        """写入存储"""
        if self.storage_backend == "database":
            await self._write_to_db(entry)
        elif self.storage_backend == "file":
            await self._write_to_file(entry)
        elif self.storage_backend == "kafka":
            await self._write_to_kafka(entry)
```

---

## 十四、最佳实践

### 14.1 工具开发最佳实践

```python
# ✅ 好的实践：明确声明授权需求

@tool(
    name="database_query",
    description="Execute SQL query on database",
    category=ToolCategory.DATA,
    parameters=[
        ToolParameter(
            name="query",
            type="string",
            description="SQL query to execute",
            required=True,
            sensitive=True,  # 标记为敏感参数
        ),
    ],
    authorization=AuthorizationRequirement(
        requires_authorization=True,
        risk_level=RiskLevel.HIGH,
        risk_categories=[RiskCategory.DATA_MODIFY],
        sensitive_parameters=["query"],
        authorization_prompt="执行数据库查询，可能修改数据",
    ),
)
async def database_query(query: str, context: Dict) -> ToolResult:
    # 执行查询
    pass


# ❌ 不好的实践：没有明确的授权声明

@tool(
    name="database_query",
    description="Execute SQL query",
)
async def database_query(query: str) -> str:
    # 缺少授权配置，默认可能不安全
    pass
```

### 14.2 Agent配置最佳实践

```python
# ✅ 好的实践：根据场景选择合适的授权模式

# 生产环境：严格模式
PRODUCTION_AGENT = AgentInfo(
    name="production-assistant",
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.STRICT,
        llm_policy=LLMJudgmentPolicy.DISABLED,  # 不依赖LLM判断
        session_cache_enabled=False,  # 每次都需要确认
    ),
)

# 开发环境：适度模式
DEV_AGENT = AgentInfo(
    name="dev-assistant",
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.MODERATE,
        llm_policy=LLMJudgmentPolicy.BALANCED,
        session_cache_enabled=True,
    ),
)

# 测试环境：宽松模式
TEST_AGENT = AgentInfo(
    name="test-assistant",
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.PERMISSIVE,
        llm_policy=LLMJudgmentPolicy.AGGRESSIVE,
    ),
)


# ❌ 不好的实践：所有环境使用相同配置

# 不区分环境
AGENT = AgentInfo(
    name="agent",
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.UNRESTRICTED,  # 生产环境也不需要授权？危险！
    ),
)
```

### 14.3 用户交互最佳实践

```python
# ✅ 好的实践：提供清晰的风险信息

async def _handle_user_confirmation(self, request: Dict) -> bool:
    interaction_request = create_authorization_request(
        tool_name=request["tool_name"],
        tool_description=request["tool_description"],
        arguments=request["arguments"],
        risk_assessment=request["risk_assessment"],
        session_id=self.session_id,
        agent_name=self.info.name,
        allow_session_grant=True,
    )
    
    # 添加额外信息帮助用户决策
    interaction_request.metadata["impact_description"] = self._get_impact_description(request)
    interaction_request.metadata["alternative_actions"] = self._get_alternatives(request)
    
    response = await self.interaction.send_and_wait(interaction_request)
    return response.is_confirmed


# ❌ 不好的实践：信息不足，用户难以决策

async def _handle_user_confirmation(self, request: Dict) -> bool:
    # 只问"是否授权"，不给足够信息
    return await self.ask_user("是否授权执行？") == "yes"
```

---

## 十五、常见问题FAQ

### Q1: 如何为新工具设置授权策略？

**A**: 使用`@tool`装饰器时，通过`authorization`参数配置：

```python
@tool(
    name="my_tool",
    description="My custom tool",
    authorization=AuthorizationRequirement(
        requires_authorization=True,
        risk_level=RiskLevel.MEDIUM,
        risk_categories=[RiskCategory.FILE_WRITE],
        support_session_grant=True,
    ),
)
async def my_tool(arg1: str, context: Dict) -> ToolResult:
    pass
```

### Q2: 如何临时禁用某个工具？

**A**: 在Agent配置中将工具加入黑名单：

```python
agent_info.authorization.blacklist_tools.append("dangerous_tool")
```

### Q3: 如何实现"一次授权，会话内有效"？

**A**: 启用会话缓存：

```python
agent_info.authorization.session_cache_enabled = True
agent_info.authorization.session_cache_ttl = 3600  # 1小时有效
```

### Q4: 如何调试授权流程？

**A**: 启用详细日志：

```python
import logging
logging.getLogger("derisk.core.authorization").setLevel(logging.DEBUG)

# 或使用审计日志
from derisk.core.audit import AuditLogger
audit_logger = AuditLogger(storage_backend="file")
```

### Q5: 如何迁移现有的core架构工具？

**A**: 使用适配器模式：

```python
# 旧版core Action
class OldAction(Action):
    async def run(self, **kwargs) -> ActionOutput:
        pass

# 适配为新版Tool
class ActionToolAdapter(ToolBase):
    def __init__(self, action: Action):
        self.action = action
        super().__init__(self._define_metadata())
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=self.action.__class__.__name__,
            description=self.action.__doc__ or "",
            authorization=AuthorizationRequirement(
                requires_authorization=True,
            ),
        )
    
    async def execute(self, args: Dict, context: Dict) -> ToolResult:
        result = await self.action.run(**args)
        return ToolResult(
            success=True,
            output=result.content,
        )
```

---

## 十六、总结与展望

### 16.1 核心成果

本架构设计为Derisk项目带来以下核心价值：

1. **统一的工具架构**
   - 标准化的工具元数据模型
   - 灵活的工具注册与发现机制
   - OpenAI Function Calling兼容

2. **完整的权限体系**
   - 多层次权限控制（工具级、Agent级、用户级）
   - 智能风险评估
   - LLM辅助决策

3. **优雅的交互系统**
   - 统一的交互协议
   - 多种交互类型支持
   - 实时WebSocket通信

4. **生产级保障**
   - 完整的审计追踪
   - 详细的监控指标
   - 灵活的配置管理

### 16.2 技术亮点

- **声明式配置**：通过AgentInfo声明式定义Agent行为
- **插件化架构**：工具可独立开发、注册、管理
- **智能决策**：LLM辅助授权决策，平衡安全与效率
- **多租户支持**：企业级权限隔离

### 16.3 未来演进

1. **短期（1-3个月）**
   - 完善内置工具集
   - 优化前端交互体验
   - 性能优化与压测

2. **中期（3-6个月）**
   - 支持更多LLM提供商
   - 增强多Agent协作能力
   - 可视化配置工具

3. **长期（6-12个月）**
   - 工具市场生态
   - 自定义授权策略DSL
   - 跨平台支持

### 16.4 文档索引

本文档分为三个部分：

1. **第一部分** (`UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md`)
   - 执行摘要
   - 架构全景图
   - 统一工具系统设计
   - 统一权限系统设计

2. **第二部分** (`UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART2.md`)
   - 统一交互系统设计
   - Agent集成设计

3. **第三部分** (本文档)
   - 产品使用场景
   - 开发实施指南
   - 监控与运维
   - 最佳实践
   - 常见问题FAQ

---

**文档版本**: v2.0  
**最后更新**: 2026-03-02  
**维护团队**: Derisk架构团队

---

本架构设计文档为Derisk统一工具架构与授权系统提供了完整的蓝图，涵盖了从核心模型到前后端实现、从开发指南到运维监控的全方位内容。通过这套架构，可以构建一个安全、灵活、易用的AI Agent平台。