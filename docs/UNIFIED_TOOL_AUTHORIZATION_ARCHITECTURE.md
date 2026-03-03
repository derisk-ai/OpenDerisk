# Derisk 统一工具架构与授权系统 - 架构设计文档

**版本**: v2.0  
**作者**: 架构团队  
**日期**: 2026-03-02  

---

## 目录

- [一、执行摘要](#一执行摘要)
- [二、架构全景图](#二架构全景图)
- [三、统一工具系统设计](#三统一工具系统设计)
- [四、统一权限系统设计](#四统一权限系统设计)
- [五、统一交互系统设计](#五统一交互系统设计)
- [六、Agent集成设计](#六agent集成设计)
- [七、前端集成设计](#七前端集成设计)
- [八、后端API设计](#八后端api设计)
- [九、实施路线图](#九实施路线图)
- [十、总结](#十总结)

---

## 一、执行摘要

### 1.1 背景

当前Derisk项目存在两套架构（core和core_v2），工具执行和权限管理机制分散不统一。为支撑企业级应用需求，需要设计一套**统一的、可扩展的、安全的**工具架构与授权系统。

### 1.2 核心目标

| 目标 | 描述 |
|------|------|
| **统一性** | 一套API、一套协议、一套权限模型，覆盖core和core_v2 |
| **可扩展** | 支持插件化工具、自定义授权策略、多租户场景 |
| **安全性** | 细粒度权限控制、审计日志、风险评估 |
| **易用性** | 声明式配置、开箱即用的默认策略、友好的前端交互 |
| **高性能** | 授权缓存、异步处理、批量优化 |

### 1.3 关键成果

- 统一工具元数据模型
- 分层权限控制体系
- 智能授权决策引擎
- 前后端一体化交互协议
- 完整的审计追踪机制

---

## 二、架构全景图

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           前端层 (Frontend)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ 工具管理面板  │  │ 授权配置面板  │  │ 交互确认弹窗  │  │ 审计日志面板  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ WebSocket / HTTP API
┌────────────────────────────┴────────────────────────────────────────────┐
│                          网关层 (Gateway API)                            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  /api/v2/tools/*        - 工具注册与管理                          │  │
│  │  /api/v2/authorization/*- 授权配置与检查                          │  │
│  │  /api/v2/interaction/*  - 交互请求与响应                          │  │
│  │  /ws/interaction/{sid}  - 实时交互WebSocket                       │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
┌────────────────────────────┴────────────────────────────────────────────┐
│                         核心层 (Core System)                              │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    统一工具系统 (Tools)                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │   │
│  │  │ToolRegistry │  │ ToolExecutor│  │ ToolValidator│              │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                   统一权限系统 (Authorization)                        │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │   │
│  │  │PermissionModel│  │AuthzEngine  │  │AuditLogger  │           │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                  统一交互系统 (Interaction)                     │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │   │
│  │  │InteractionGW │  │SessionManager│  │CacheManager │           │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────┴────────────────────────────────────────────┐
│                        基础设施层 (Infrastructure)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  Redis   │  │ PostgreSQL│  │  Kafka   │  │ S3/MinIO │  │Prometheus│  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心模块关系

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Agent Runtime                               │
│                                                                      │
│  ┌──────────────┐         ┌──────────────────────────────────────┐ │
│  │   Agent      │         │         Tool Execution Flow          │ │
│  │              │         │                                      │ │
│  │  - AgentInfo │────────▶│  1. Tool Selection                   │ │
│  │  - AuthzMode │         │  2. Authorization Check ────────┐    │ │
│  │  - Tools     │         │  3. Execution                   │    │ │
│  │              │         │  4. Result Processing           │    │ │
│  └──────────────┘         └──────────────────────────────────│────┘ │
│                                                           │       │
│                                                           ▼       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Authorization Engine                       │  │
│  │                                                                │  │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │  │
│  │  │Tool Metadata│───▶│Policy Engine│───▶│  Decision   │      │  │
│  │  └─────────────┘    └─────────────┘    └─────────────┘      │  │
│  │         │                  │                   │             │  │
│  │         │                  ▼                   ▼             │  │
│  │         │         ┌─────────────┐      ┌─────────────┐      │  │
│  │         │         │Risk Assessor│      │Interaction  │      │  │
│  │         │         └─────────────┘      └─────────────┘      │  │
│  │         │                                     │              │  │
│  │         └─────────────────────────────────────┘              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 三、统一工具系统设计

### 3.1 工具元数据模型

```python
# derisk/core/tools/metadata.py

from typing import Dict, Any, List, Optional, Callable
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class ToolCategory(str, Enum):
    """工具类别"""
    FILE_SYSTEM = "file_system"        # 文件系统操作
    SHELL = "shell"                    # Shell命令执行
    NETWORK = "network"                # 网络请求
    CODE = "code"                      # 代码操作
    DATA = "data"                      # 数据处理
    AGENT = "agent"                    # Agent协作
    INTERACTION = "interaction"        # 用户交互
    EXTERNAL = "external"              # 外部工具
    CUSTOM = "custom"                  # 自定义工具


class RiskLevel(str, Enum):
    """风险等级"""
    SAFE = "safe"                      # 安全操作
    LOW = "low"                        # 低风险
    MEDIUM = "medium"                  # 中风险
    HIGH = "high"                      # 高风险
    CRITICAL = "critical"              # 关键操作


class RiskCategory(str, Enum):
    """风险类别"""
    READ_ONLY = "read_only"                    # 只读操作
    FILE_WRITE = "file_write"                  # 文件写入
    FILE_DELETE = "file_delete"                # 文件删除
    SHELL_EXECUTE = "shell_execute"            # Shell执行
    NETWORK_OUTBOUND = "network_outbound"      # 出站网络请求
    DATA_MODIFY = "data_modify"                # 数据修改
    SYSTEM_CONFIG = "system_config"            # 系统配置
    PRIVILEGED = "privileged"                  # 特权操作


class AuthorizationRequirement(BaseModel):
    """授权要求"""
    requires_authorization: bool = True
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk_categories: List[RiskCategory] = Field(default_factory=list)
    
    # 授权提示模板
    authorization_prompt: Optional[str] = None
    
    # 敏感参数定义
    sensitive_parameters: List[str] = Field(default_factory=list)
    
    # 参数级别风险评估函数
    parameter_risk_assessor: Optional[str] = None  # 函数引用名
    
    # 白名单规则（匹配规则时跳过授权）
    whitelist_rules: List[Dict[str, Any]] = Field(default_factory=list)
    
    # 会话级授权支持
    support_session_grant: bool = True
    
    # 授权有效期（秒），None表示永久
    grant_ttl: Optional[int] = None


class ToolParameter(BaseModel):
    """工具参数定义"""
    name: str
    type: str                              # string, number, boolean, object, array
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None       # 枚举值
    
    # 参数验证
    pattern: Optional[str] = None          # 正则模式
    min_value: Optional[float] = None      # 最小值
    max_value: Optional[float] = None      # 最大值
    min_length: Optional[int] = None       # 最小长度
    max_length: Optional[int] = None       # 最大长度
    
    # 敏感标记
    sensitive: bool = False
    sensitive_pattern: Optional[str] = None  # 敏感值模式


class ToolMetadata(BaseModel):
    """工具元数据 - 统一标准"""
    
    # ========== 基本信息 ==========
    id: str                                          # 工具唯一标识
    name: str                                        # 工具名称
    version: str = "1.0.0"                          # 版本号
    description: str                                 # 描述
    category: ToolCategory = ToolCategory.CUSTOM    # 类别
    
    # ========== 作者与来源 ==========
    author: Optional[str] = None
    source: str = "builtin"                         # builtin/plugin/custom/mcp
    package: Optional[str] = None                   # 所属包
    homepage: Optional[str] = None
    repository: Optional[str] = None
    
    # ========== 参数定义 ==========
    parameters: List[ToolParameter] = Field(default_factory=list)
    return_type: str = "string"
    return_description: Optional[str] = None
    
    # ========== 授权与安全 ==========
    authorization: AuthorizationRequirement = Field(
        default_factory=AuthorizationRequirement
    )
    
    # ========== 执行配置 ==========
    timeout: int = 60                               # 默认超时（秒）
    max_concurrent: int = 1                         # 最大并发数
    retry_count: int = 0                           # 重试次数
    retry_delay: float = 1.0                       # 重试延迟
    
    # ========== 依赖与冲突 ==========
    dependencies: List[str] = Field(default_factory=list)      # 依赖工具
    conflicts: List[str] = Field(default_factory=list)         # 冲突工具
    
    # ========== 标签与示例 ==========
    tags: List[str] = Field(default_factory=list)
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    
    # ========== 元信息 ==========
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    deprecated: bool = False
    deprecation_message: Optional[str] = None
    
    # ========== 扩展字段 ==========
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
    
    def get_openai_spec(self) -> Dict[str, Any]:
        """生成OpenAI Function Calling规范"""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            }
        }
    
    def validate_arguments(self, arguments: Dict[str, Any]) -> List[str]:
        """验证参数，返回错误列表"""
        errors = []
        
        for param in self.parameters:
            value = arguments.get(param.name)
            
            # 检查必填
            if param.required and value is None:
                errors.append(f"缺少必填参数: {param.name}")
                continue
            
            if value is None:
                continue
            
            # 类型检查
            # ... 省略详细类型检查逻辑
            
            # 约束检查
            if param.enum and value not in param.enum:
                errors.append(f"参数 {param.name} 的值必须在 {param.enum} 中")
            
            if param.min_value is not None and value < param.min_value:
                errors.append(f"参数 {param.name} 不能小于 {param.min_value}")
            
            if param.max_value is not None and value > param.max_value:
                errors.append(f"参数 {param.name} 不能大于 {param.max_value}")
        
        return errors
```

### 3.2 工具基类与注册

```python
# derisk/core/tools/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncIterator
import asyncio
import logging

from .metadata import ToolMetadata, ToolResult

logger = logging.getLogger(__name__)


class ToolBase(ABC):
    """
    工具基类 - 统一接口
    
    所有工具必须继承此类并实现execute方法
    """
    
    def __init__(self, metadata: Optional[ToolMetadata] = None):
        self._metadata = metadata or self._define_metadata()
        self._initialized = False
    
    @property
    def metadata(self) -> ToolMetadata:
        """获取工具元数据"""
        return self._metadata
    
    @abstractmethod
    def _define_metadata(self) -> ToolMetadata:
        """
        定义工具元数据（子类必须实现）
        
        示例:
            return ToolMetadata(
                id="bash",
                name="bash",
                description="Execute bash commands",
                category=ToolCategory.SHELL,
                parameters=[
                    ToolParameter(
                        name="command",
                        type="string",
                        description="The bash command to execute",
                        required=True,
                    ),
                ],
                authorization=AuthorizationRequirement(
                    requires_authorization=True,
                    risk_level=RiskLevel.HIGH,
                    risk_categories=[RiskCategory.SHELL_EXECUTE],
                ),
            )
        """
        pass
    
    async def initialize(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        初始化工具（可选实现）
        
        Args:
            context: 初始化上下文
            
        Returns:
            bool: 是否初始化成功
        """
        if self._initialized:
            return True
        
        try:
            await self._do_initialize(context)
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"[{self.metadata.name}] 初始化失败: {e}")
            return False
    
    async def _do_initialize(self, context: Optional[Dict[str, Any]] = None):
        """实际初始化逻辑（子类可覆盖）"""
        pass
    
    async def cleanup(self):
        """清理资源（可选实现）"""
        pass
    
    @abstractmethod
    async def execute(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        执行工具（子类必须实现）
        
        Args:
            arguments: 工具参数
            context: 执行上下文，包含:
                - session_id: 会话ID
                - agent_name: Agent名称
                - user_id: 用户ID
                - workspace: 工作目录
                - env: 环境变量
                - timeout: 超时时间
                
        Returns:
            ToolResult: 执行结果
        """
        pass
    
    async def execute_safe(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        安全执行（带参数验证、超时控制、异常捕获）
        """
        # 参数验证
        errors = self.metadata.validate_arguments(arguments)
        if errors:
            return ToolResult(
                success=False,
                output="",
                error="参数验证失败: " + "; ".join(errors),
            )
        
        # 确保初始化
        if not self._initialized:
            await self.initialize(context)
        
        # 执行超时控制
        timeout = context.get("timeout", self.metadata.timeout) if context else self.metadata.timeout
        
        try:
            if timeout:
                result = await asyncio.wait_for(
                    self.execute(arguments, context),
                    timeout=timeout
                )
            else:
                result = await self.execute(arguments, context)
            
            return result
            
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"工具执行超时（{timeout}秒）",
            )
        except Exception as e:
            logger.exception(f"[{self.metadata.name}] 执行异常")
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
    
    async def execute_stream(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """
        流式执行（可选实现）
        
        用于长时间运行的任务，实时返回进度
        """
        result = await self.execute_safe(arguments, context)
        yield result.output


class ToolRegistry:
    """
    工具注册中心 - 单例模式
    
    管理所有工具的注册、发现、执行
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: Dict[str, ToolBase] = {}
            cls._instance._categories: Dict[str, List[str]] = {}
            cls._instance._tags: Dict[str, List[str]] = {}
        return cls._instance
    
    def register(self, tool: ToolBase) -> "ToolRegistry":
        """注册工具"""
        name = tool.metadata.name
        
        if name in self._tools:
            logger.warning(f"[ToolRegistry] 工具 {name} 已存在，将被覆盖")
        
        self._tools[name] = tool
        
        # 索引类别
        category = tool.metadata.category
        if category not in self._categories:
            self._categories[category] = []
        self._categories[category].append(name)
        
        # 索引标签
        for tag in tool.metadata.tags:
            if tag not in self._tags:
                self._tags[tag] = []
            self._tags[tag].append(name)
        
        logger.info(f"[ToolRegistry] 注册工具: {name} (category={category})")
        return self
    
    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            tool = self._tools.pop(name)
            
            # 清理索引
            category = tool.metadata.category
            if category in self._categories:
                self._categories[category].remove(name)
            
            for tag in tool.metadata.tags:
                if tag in self._tags:
                    self._tags[tag].remove(name)
            
            return True
        return False
    
    def get(self, name: str) -> Optional[ToolBase]:
        """获取工具"""
        return self._tools.get(name)
    
    def list_all(self) -> List[ToolBase]:
        """列出所有工具"""
        return list(self._tools.values())
    
    def list_names(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())
    
    def list_by_category(self, category: str) -> List[ToolBase]:
        """按类别列出工具"""
        names = self._categories.get(category, [])
        return [self._tools[name] for name in names if name in self._tools]
    
    def list_by_tag(self, tag: str) -> List[ToolBase]:
        """按标签列出工具"""
        names = self._tags.get(tag, [])
        return [self._tools[name] for name in names if name in self._tools]
    
    def get_openai_tools(self, filter_func=None) -> List[Dict[str, Any]]:
        """获取OpenAI格式工具列表"""
        tools = []
        for tool in self._tools.values():
            if filter_func and not filter_func(tool):
                continue
            tools.append(tool.metadata.get_openai_spec())
        return tools
    
    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """执行工具"""
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"工具不存在: {name}",
            )
        
        return await tool.execute_safe(arguments, context)


# 全局工具注册中心
tool_registry = ToolRegistry()


def register_tool(tool: ToolBase) -> ToolBase:
    """装饰器：注册工具"""
    tool_registry.register(tool)
    return tool
```

### 3.3 工具装饰器与快速定义

```python
# derisk/core/tools/decorators.py

from typing import Callable, Optional, Dict, Any, List
from functools import wraps
import asyncio

from .base import ToolBase, ToolResult, tool_registry
from .metadata import (
    ToolMetadata,
    ToolParameter,
    ToolCategory,
    AuthorizationRequirement,
    RiskLevel,
    RiskCategory,
)


def tool(
    name: str,
    description: str,
    category: ToolCategory = ToolCategory.CUSTOM,
    parameters: Optional[List[ToolParameter]] = None,
    *,
    authorization: Optional[AuthorizationRequirement] = None,
    timeout: int = 60,
    tags: Optional[List[str]] = None,
    examples: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    工具装饰器 - 快速定义工具
    
    示例:
        @tool(
            name="read_file",
            description="Read file content",
            category=ToolCategory.FILE_SYSTEM,
            parameters=[
                ToolParameter(name="path", type="string", description="File path"),
            ],
            authorization=AuthorizationRequirement(
                requires_authorization=False,
                risk_level=RiskLevel.SAFE,
            ),
        )
        async def read_file(path: str, context: dict) -> str:
            with open(path) as f:
                return f.read()
    """
    def decorator(func: Callable):
        # 定义元数据
        tool_metadata = ToolMetadata(
            id=name,
            name=name,
            description=description,
            category=category,
            parameters=parameters or [],
            authorization=authorization or AuthorizationRequirement(),
            timeout=timeout,
            tags=tags or [],
            examples=examples or [],
            metadata=metadata or {},
        )
        
        # 创建工具类
        class FunctionTool(ToolBase):
            def _define_metadata(self) -> ToolMetadata:
                return tool_metadata
            
            async def execute(
                self,
                arguments: Dict[str, Any],
                context: Optional[Dict[str, Any]] = None,
            ) -> ToolResult:
                try:
                    # 合并参数
                    kwargs = {**arguments}
                    if context:
                        kwargs["context"] = context
                    
                    # 执行函数
                    if asyncio.iscoroutinefunction(func):
                        result = await func(**kwargs)
                    else:
                        result = func(**kwargs)
                    
                    # 包装结果
                    if isinstance(result, ToolResult):
                        return result
                    
                    return ToolResult(
                        success=True,
                        output=str(result) if result is not None else "",
                    )
                    
                except Exception as e:
                    return ToolResult(
                        success=False,
                        output="",
                        error=str(e),
                    )
        
        # 注册工具
        tool_instance = FunctionTool(tool_metadata)
        tool_registry.register(tool_instance)
        
        # 保留原函数
        tool_instance._func = func
        
        return tool_instance
    
    return decorator


def shell_tool(
    name: str,
    description: str,
    dangerous: bool = False,
    **kwargs,
):
    """Shell工具快速定义"""
    from .metadata import AuthorizationRequirement, RiskLevel, RiskCategory
    
    auth = AuthorizationRequirement(
        requires_authorization=True,
        risk_level=RiskLevel.HIGH if dangerous else RiskLevel.MEDIUM,
        risk_categories=[RiskCategory.SHELL_EXECUTE],
    )
    
    return tool(
        name=name,
        description=description,
        category=ToolCategory.SHELL,
        authorization=auth,
        **kwargs,
    )


def file_read_tool(
    name: str,
    description: str,
    **kwargs,
):
    """文件读取工具快速定义"""
    auth = AuthorizationRequirement(
        requires_authorization=False,
        risk_level=RiskLevel.SAFE,
        risk_categories=[RiskCategory.READ_ONLY],
    )
    
    return tool(
        name=name,
        description=description,
        category=ToolCategory.FILE_SYSTEM,
        authorization=auth,
        **kwargs,
    )


def file_write_tool(
    name: str,
    description: str,
    dangerous: bool = False,
    **kwargs,
):
    """文件写入工具快速定义"""
    auth = AuthorizationRequirement(
        requires_authorization=True,
        risk_level=RiskLevel.HIGH if dangerous else RiskLevel.MEDIUM,
        risk_categories=[RiskCategory.FILE_WRITE],
    )
    
    return tool(
        name=name,
        description=description,
        category=ToolCategory.FILE_SYSTEM,
        authorization=auth,
        **kwargs,
    )
```

---

## 四、统一权限系统设计

### 4.1 权限模型

```python
# derisk/core/authorization/model.py

from typing import Dict, Any, List, Optional, Set
from pydantic import BaseModel, Field
from enum import Enum
import fnmatch
import hashlib
import json


class PermissionAction(str, Enum):
    """权限动作"""
    ALLOW = "allow"         # 允许执行
    DENY = "deny"           # 拒绝执行
    ASK = "ask"             # 询问用户


class AuthorizationMode(str, Enum):
    """授权模式"""
    STRICT = "strict"               # 严格模式：按工具定义执行
    MODERATE = "moderate"           # 适度模式：可覆盖工具定义
    PERMISSIVE = "permissive"       # 宽松模式：默认允许
    UNRESTRICTED = "unrestricted"   # 无限制模式：跳过所有检查


class LLMJudgmentPolicy(str, Enum):
    """LLM判断策略"""
    DISABLED = "disabled"           # 禁用LLM判断
    CONSERVATIVE = "conservative"   # 保守：倾向于询问
    BALANCED = "balanced"           # 平衡：中性判断
    AGGRESSIVE = "aggressive"       # 激进：倾向于允许


class PermissionRule(BaseModel):
    """权限规则"""
    id: str
    name: str
    description: Optional[str] = None
    
    # 匹配条件
    tool_pattern: str = "*"                 # 工具名称模式（支持通配符）
    category_filter: Optional[str] = None   # 类别过滤
    risk_level_filter: Optional[str] = None # 风险等级过滤
    parameter_conditions: Dict[str, Any] = Field(default_factory=dict)  # 参数条件
    
    # 动作
    action: PermissionAction = PermissionAction.ASK
    
    # 优先级（数字越小优先级越高）
    priority: int = 100
    
    # 生效条件
    enabled: bool = True
    time_range: Optional[Dict[str, str]] = None  # {"start": "09:00", "end": "18:00"}
    
    def matches(
        self,
        tool_name: str,
        tool_metadata: Any,
        arguments: Dict[str, Any],
    ) -> bool:
        """检查是否匹配"""
        if not self.enabled:
            return False
        
        # 工具名称匹配
        if not fnmatch.fnmatch(tool_name, self.tool_pattern):
            return False
        
        # 类别过滤
        if self.category_filter:
            if tool_metadata.category != self.category_filter:
                return False
        
        # 风险等级过滤
        if self.risk_level_filter:
            if tool_metadata.authorization.risk_level != self.risk_level_filter:
                return False
        
        # 参数条件
        for param_name, condition in self.parameter_conditions.items():
            if param_name not in arguments:
                return False
            
            # 支持多种条件类型
            if isinstance(condition, dict):
                # 范围条件
                if "min" in condition and arguments[param_name] < condition["min"]:
                    return False
                if "max" in condition and arguments[param_name] > condition["max"]:
                    return False
                # 模式匹配
                if "pattern" in condition:
                    if not fnmatch.fnmatch(str(arguments[param_name]), condition["pattern"]):
                        return False
            elif isinstance(condition, list):
                # 枚举值
                if arguments[param_name] not in condition:
                    return False
            else:
                # 精确匹配
                if arguments[param_name] != condition:
                    return False
        
        return True


class PermissionRuleset(BaseModel):
    """权限规则集"""
    id: str
    name: str
    description: Optional[str] = None
    
    # 规则列表（按优先级排序）
    rules: List[PermissionRule] = Field(default_factory=list)
    
    # 默认动作
    default_action: PermissionAction = PermissionAction.ASK
    
    def add_rule(self, rule: PermissionRule):
        """添加规则"""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority)
    
    def check(
        self,
        tool_name: str,
        tool_metadata: Any,
        arguments: Dict[str, Any],
    ) -> PermissionAction:
        """检查权限"""
        for rule in self.rules:
            if rule.matches(tool_name, tool_metadata, arguments):
                return rule.action
        
        return self.default_action
    
    @classmethod
    def from_dict(cls, config: Dict[str, str], **kwargs) -> "PermissionRuleset":
        """从字典创建"""
        rules = []
        priority = 10
        
        for pattern, action_str in config.items():
            action = PermissionAction(action_str)
            rules.append(PermissionRule(
                id=f"rule_{priority}",
                name=f"Rule for {pattern}",
                tool_pattern=pattern,
                action=action,
                priority=priority,
            ))
            priority += 10
        
        return cls(rules=rules, **kwargs)


class AuthorizationConfig(BaseModel):
    """授权配置"""
    
    # 授权模式
    mode: AuthorizationMode = AuthorizationMode.STRICT
    
    # 权限规则集
    ruleset: Optional[PermissionRuleset] = None
    
    # LLM判断策略
    llm_policy: LLMJudgmentPolicy = LLMJudgmentPolicy.DISABLED
    llm_prompt: Optional[str] = None
    
    # 工具级别覆盖
    tool_overrides: Dict[str, PermissionAction] = Field(default_factory=dict)
    
    # 白名单工具（跳过授权）
    whitelist_tools: List[str] = Field(default_factory=list)
    
    # 黑名单工具（禁止执行）
    blacklist_tools: List[str] = Field(default_factory=list)
    
    # 会话级授权缓存
    session_cache_enabled: bool = True
    session_cache_ttl: int = 3600  # 秒
    
    # 授权超时
    authorization_timeout: int = 300  # 秒
    
    # 用户确认回调
    user_confirmation_callback: Optional[str] = None
    
    def get_effective_action(
        self,
        tool_name: str,
        tool_metadata: Any,
        arguments: Dict[str, Any],
    ) -> PermissionAction:
        """获取生效的权限动作"""
        
        # 1. 检查黑名单
        if tool_name in self.blacklist_tools:
            return PermissionAction.DENY
        
        # 2. 检查白名单
        if tool_name in self.whitelist_tools:
            return PermissionAction.ALLOW
        
        # 3. 检查工具覆盖
        if tool_name in self.tool_overrides:
            return self.tool_overrides[tool_name]
        
        # 4. 检查规则集
        if self.ruleset:
            action = self.ruleset.check(tool_name, tool_metadata, arguments)
            if action != self.default_action:
                return action
        
        # 5. 根据模式返回默认动作
        if self.mode == AuthorizationMode.UNRESTRICTED:
            return PermissionAction.ALLOW
        elif self.mode == AuthorizationMode.PERMISSIVE:
            # 宽松模式：根据工具风险等级决定
            if tool_metadata.authorization.risk_level in ["safe", "low"]:
                return PermissionAction.ALLOW
            return PermissionAction.ASK
        else:
            # 严格/适度模式：使用工具定义或默认ASK
            if self.mode == AuthorizationMode.STRICT:
                # 严格模式：使用工具定义
                if not tool_metadata.authorization.requires_authorization:
                    return PermissionAction.ALLOW
            return PermissionAction.ASK
```

### 4.2 授权引擎

```python
# derisk/core/authorization/engine.py

from typing import Dict, Any, Optional, Callable, Awaitable
from enum import Enum
import asyncio
import logging
import time
from datetime import datetime

from .model import (
    AuthorizationConfig,
    PermissionAction,
    AuthorizationMode,
    LLMJudgmentPolicy,
)
from ..tools.metadata import ToolMetadata, RiskLevel

logger = logging.getLogger(__name__)


class AuthorizationDecision(str, Enum):
    """授权决策"""
    GRANTED = "granted"             # 授权通过
    DENIED = "denied"               # 授权拒绝
    NEED_CONFIRMATION = "need_confirmation"  # 需要用户确认
    NEED_LLM_JUDGMENT = "need_llm_judgment"  # 需要LLM判断
    CACHED = "cached"               # 使用缓存


class AuthorizationContext(BaseModel):
    """授权上下文"""
    session_id: str
    user_id: Optional[str] = None
    agent_name: str
    tool_name: str
    tool_metadata: ToolMetadata
    arguments: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)


class AuthorizationResult(BaseModel):
    """授权结果"""
    decision: AuthorizationDecision
    action: PermissionAction
    reason: str
    cached: bool = False
    cache_key: Optional[str] = None
    user_message: Optional[str] = None
    risk_assessment: Optional[Dict[str, Any]] = None
    llm_judgment: Optional[Dict[str, Any]] = None


class AuthorizationCache:
    """授权缓存"""
    
    def __init__(self, ttl: int = 3600):
        self._cache: Dict[str, tuple] = {}  # key -> (granted, timestamp)
        self._ttl = ttl
    
    def get(self, key: str) -> Optional[bool]:
        """获取缓存"""
        if key in self._cache:
            granted, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return granted
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, granted: bool):
        """设置缓存"""
        self._cache[key] = (granted, time.time())
    
    def clear(self, session_id: Optional[str] = None):
        """清空缓存"""
        if session_id:
            # 清空指定会话的缓存
            keys_to_remove = [
                k for k in self._cache 
                if k.startswith(f"{session_id}:")
            ]
            for k in keys_to_remove:
                del self._cache[k]
        else:
            self._cache.clear()
    
    def _build_cache_key(self, ctx: AuthorizationContext) -> str:
        """构建缓存键"""
        import hashlib
        import json
        
        args_hash = hashlib.md5(
            json.dumps(ctx.arguments, sort_keys=True).encode()
        ).hexdigest()[:8]
        
        return f"{ctx.session_id}:{ctx.tool_name}:{args_hash}"


class RiskAssessor:
    """风险评估器"""
    
    @staticmethod
    def assess(
        tool_metadata: ToolMetadata,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """评估风险"""
        auth_req = tool_metadata.authorization
        
        risk_score = 0
        risk_factors = []
        
        # 基础风险等级
        level_scores = {
            RiskLevel.SAFE: 0,
            RiskLevel.LOW: 10,
            RiskLevel.MEDIUM: 30,
            RiskLevel.HIGH: 60,
            RiskLevel.CRITICAL: 90,
        }
        risk_score += level_scores.get(auth_req.risk_level, 30)
        
        # 风险类别
        high_risk_categories = {
            "shell_execute": 20,
            "file_delete": 25,
            "privileged": 30,
        }
        
        for category in auth_req.risk_categories:
            if category in high_risk_categories:
                risk_score += high_risk_categories[category]
                risk_factors.append(f"高风险类别: {category}")
        
        # 敏感参数检查
        for param_name in auth_req.sensitive_parameters:
            if param_name in arguments:
                risk_score += 10
                risk_factors.append(f"敏感参数: {param_name}")
        
        # 特定工具的风险评估
        if tool_metadata.name == "bash":
            command = arguments.get("command", "")
            # 危险命令检测
            dangerous_patterns = ["rm -rf", "sudo", "chmod 777", "> /dev/"]
            for pattern in dangerous_patterns:
                if pattern in command:
                    risk_score += 20
                    risk_factors.append(f"危险命令模式: {pattern}")
        
        elif tool_metadata.name == "write":
            path = arguments.get("file_path", arguments.get("path", ""))
            # 系统文件检查
            if any(p in path for p in ["/etc/", "/usr/bin", "~/.ssh"]):
                risk_score += 25
                risk_factors.append(f"系统路径: {path}")
        
        # 归一化风险分数
        risk_score = min(100, risk_score)
        
        return {
            "score": risk_score,
            "level": RiskAssessor._score_to_level(risk_score),
            "factors": risk_factors,
            "recommendation": RiskAssessor._get_recommendation(risk_score),
        }
    
    @staticmethod
    def _score_to_level(score: int) -> str:
        """分数转等级"""
        if score < 20:
            return "low"
        elif score < 50:
            return "medium"
        elif score < 80:
            return "high"
        else:
            return "critical"
    
    @staticmethod
    def _get_recommendation(score: int) -> str:
        """获取建议"""
        if score < 20:
            return "建议直接允许执行"
        elif score < 50:
            return "建议根据用户偏好决定是否询问"
        elif score < 80:
            return "建议询问用户确认"
        else:
            return "建议拒绝或需要管理员审批"


class AuthorizationEngine:
    """
    授权引擎 - 核心授权决策组件
    
    职责:
    1. 统一授权决策
    2. 风险评估
    3. LLM判断
    4. 缓存管理
    5. 审计日志
    """
    
    def __init__(
        self,
        llm_adapter: Optional[Any] = None,
        cache_ttl: int = 3600,
        audit_logger: Optional[Any] = None,
    ):
        self.llm_adapter = llm_adapter
        self.cache = AuthorizationCache(cache_ttl)
        self.risk_assessor = RiskAssessor()
        self.audit_logger = audit_logger
        
        # 统计
        self._stats = {
            "total_checks": 0,
            "granted": 0,
            "denied": 0,
            "cached_hits": 0,
            "user_confirmations": 0,
            "llm_judgments": 0,
        }
    
    async def check_authorization(
        self,
        ctx: AuthorizationContext,
        config: AuthorizationConfig,
        user_confirmation_handler: Optional[Callable[[Dict[str, Any]], Awaitable[bool]]] = None,
    ) -> AuthorizationResult:
        """
        检查授权 - 主入口
        
        流程:
        1. 检查缓存
        2. 获取权限动作
        3. 风险评估
        4. LLM判断（可选）
        5. 用户确认（可选）
        6. 记录审计日志
        """
        self._stats["total_checks"] += 1
        
        # 1. 检查缓存
        if config.session_cache_enabled:
            cache_key = self.cache._build_cache_key(ctx)
            cached = self.cache.get(cache_key)
            
            if cached is not None:
                self._stats["cached_hits"] += 1
                return AuthorizationResult(
                    decision=AuthorizationDecision.CACHED,
                    action=PermissionAction.ALLOW if cached else PermissionAction.DENY,
                    reason="使用会话缓存授权",
                    cached=True,
                    cache_key=cache_key,
                )
        
        # 2. 获取权限动作
        action = config.get_effective_action(
            ctx.tool_name,
            ctx.tool_metadata,
            ctx.arguments,
        )
        
        # 3. 风险评估
        risk_assessment = self.risk_assessor.assess(
            ctx.tool_metadata,
            ctx.arguments,
        )
        
        # 4. 根据动作决策
        if action == PermissionAction.ALLOW:
            return await self._handle_allow(ctx, config, risk_assessment, cache_key)
        
        elif action == PermissionAction.DENY:
            return await self._handle_deny(ctx, config, risk_assessment)
        
        elif action == PermissionAction.ASK:
            # 检查LLM判断策略
            if config.llm_policy != LLMJudgmentPolicy.DISABLED and self.llm_adapter:
                llm_result = await self._llm_judgment(ctx, config, risk_assessment)
                if llm_result:
                    return llm_result
            
            # 需要用户确认
            return await self._handle_user_confirmation(
                ctx, config, risk_assessment, user_confirmation_handler, cache_key
            )
        
        # 默认拒绝
        return AuthorizationResult(
            decision=AuthorizationDecision.DENIED,
            action=PermissionAction.DENY,
            reason="未知权限动作",
            risk_assessment=risk_assessment,
        )
    
    async def _handle_allow(
        self,
        ctx: AuthorizationContext,
        config: AuthorizationConfig,
        risk_assessment: Dict[str, Any],
        cache_key: Optional[str] = None,
    ) -> AuthorizationResult:
        """处理允许"""
        self._stats["granted"] += 1
        
        # 缓存
        if config.session_cache_enabled and cache_key:
            self.cache.set(cache_key, True)
        
        # 审计
        await self._log_authorization(ctx, "granted", risk_assessment)
        
        return AuthorizationResult(
            decision=AuthorizationDecision.GRANTED,
            action=PermissionAction.ALLOW,
            reason="权限规则允许",
            cached=False,
            risk_assessment=risk_assessment,
        )
    
    async def _handle_deny(
        self,
        ctx: AuthorizationContext,
        config: AuthorizationConfig,
        risk_assessment: Dict[str, Any],
    ) -> AuthorizationResult:
        """处理拒绝"""
        self._stats["denied"] += 1
        
        # 审计
        await self._log_authorization(ctx, "denied", risk_assessment)
        
        user_message = f"工具 '{ctx.tool_name}' 执行被拒绝。\n原因: {risk_assessment.get('factors', ['权限策略限制'])}"
        
        return AuthorizationResult(
            decision=AuthorizationDecision.DENIED,
            action=PermissionAction.DENY,
            reason="权限规则拒绝",
            risk_assessment=risk_assessment,
            user_message=user_message,
        )
    
    async def _handle_user_confirmation(
        self,
        ctx: AuthorizationContext,
        config: AuthorizationConfig,
        risk_assessment: Dict[str, Any],
        handler: Optional[Callable],
        cache_key: Optional[str] = None,
    ) -> AuthorizationResult:
        """处理用户确认"""
        self._stats["user_confirmations"] += 1
        
        if not handler:
            # 没有用户确认处理器，默认拒绝
            return AuthorizationResult(
                decision=AuthorizationDecision.DENIED,
                action=PermissionAction.DENY,
                reason="需要用户确认但未提供处理程序",
                risk_assessment=risk_assessment,
            )
        
        # 构建确认请求
        confirmation_request = {
            "tool_name": ctx.tool_name,
            "tool_description": ctx.tool_metadata.description,
            "arguments": ctx.arguments,
            "risk_assessment": risk_assessment,
            "session_id": ctx.session_id,
            "timeout": config.authorization_timeout,
            "allow_session_grant": ctx.tool_metadata.authorization.support_session_grant,
        }
        
        # 调用用户确认
        try:
            confirmed = await asyncio.wait_for(
                handler(confirmation_request),
                timeout=config.authorization_timeout,
            )
            
            if confirmed:
                self._stats["granted"] += 1
                
                # 缓存
                if config.session_cache_enabled and cache_key:
                    self.cache.set(cache_key, True)
                
                # 审计
                await self._log_authorization(ctx, "user_confirmed", risk_assessment)
                
                return AuthorizationResult(
                    decision=AuthorizationDecision.GRANTED,
                    action=PermissionAction.ALLOW,
                    reason="用户已确认授权",
                    risk_assessment=risk_assessment,
                )
            else:
                self._stats["denied"] += 1
                
                # 审计
                await self._log_authorization(ctx, "user_denied", risk_assessment)
                
                return AuthorizationResult(
                    decision=AuthorizationDecision.DENIED,
                    action=PermissionAction.DENY,
                    reason="用户拒绝授权",
                    risk_assessment=risk_assessment,
                    user_message="您拒绝了该工具的执行",
                )
                
        except asyncio.TimeoutError:
            self._stats["denied"] += 1
            
            return AuthorizationResult(
                decision=AuthorizationDecision.DENIED,
                action=PermissionAction.DENY,
                reason="用户确认超时",
                risk_assessment=risk_assessment,
                user_message="授权确认超时，操作已取消",
            )
    
    async def _llm_judgment(
        self,
        ctx: AuthorizationContext,
        config: AuthorizationConfig,
        risk_assessment: Dict[str, Any],
    ) -> Optional[AuthorizationResult]:
        """LLM判断"""
        self._stats["llm_judgments"] += 1
        
        if not self.llm_adapter:
            return None
        
        try:
            # 构建prompt
            prompt = config.llm_prompt or self._default_llm_prompt()
            
            request_content = f"""请判断以下工具执行是否需要用户确认：

工具名称: {ctx.tool_name}
工具描述: {ctx.tool_metadata.description}
参数: {ctx.arguments}
风险等级: {ctx.tool_metadata.authorization.risk_level.value}
风险类别: {[c.value for c in ctx.tool_metadata.authorization.risk_categories]}
风险评估: {risk_assessment}

请返回JSON格式：
{{"need_confirmation": true/false, "reason": "判断理由"}}
"""
            
            # 调用LLM
            response = await self.llm_adapter.generate(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": request_content},
                ]
            )
            
            # 解析结果
            import json
            result = json.loads(response.content)
            need_confirmation = result.get("need_confirmation", True)
            
            # 根据策略调整
            if config.llm_policy == LLMJudgmentPolicy.CONSERVATIVE:
                # 保守策略：倾向于询问
                need_confirmation = need_confirmation or risk_assessment["score"] > 20
            elif config.llm_policy == LLMJudgmentPolicy.AGGRESSIVE:
                # 激进策略：倾向于允许
                need_confirmation = need_confirmation and risk_assessment["score"] > 60
            
            llm_judgment = {
                "need_confirmation": need_confirmation,
                "reason": result.get("reason"),
                "policy": config.llm_policy.value,
            }
            
            if not need_confirmation:
                self._stats["granted"] += 1
                
                return AuthorizationResult(
                    decision=AuthorizationDecision.GRANTED,
                    action=PermissionAction.ALLOW,
                    reason="LLM判断无需用户确认",
                    risk_assessment=risk_assessment,
                    llm_judgment=llm_judgment,
                )
            
            return None
            
        except Exception as e:
            logger.error(f"[AuthorizationEngine] LLM判断失败: {e}")
            return None
    
    def _default_llm_prompt(self) -> str:
        """默认LLM判断prompt"""
        return """你是一个安全助手，负责判断工具执行是否需要用户确认。

判断标准：
1. 工具的风险等级和类别
2. 执行参数的敏感程度
3. 可能的影响范围
4. 是否涉及数据修改或删除

返回JSON格式：
{
  "need_confirmation": true/false,
  "reason": "判断理由"
}
"""
    
    async def _log_authorization(
        self,
        ctx: AuthorizationContext,
        result: str,
        risk_assessment: Dict[str, Any],
    ):
        """记录审计日志"""
        if not self.audit_logger:
            return
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": ctx.session_id,
            "user_id": ctx.user_id,
            "agent_name": ctx.agent_name,
            "tool_name": ctx.tool_name,
            "arguments": ctx.arguments,
            "result": result,
            "risk_score": risk_assessment.get("score"),
            "risk_factors": risk_assessment.get("factors"),
        }
        
        await self.audit_logger.log(log_entry)
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()
    
    def clear_cache(self, session_id: Optional[str] = None):
        """清空缓存"""
        self.cache.clear(session_id)


# 全局授权引擎
_authorization_engine: Optional[AuthorizationEngine] = None


def get_authorization_engine() -> AuthorizationEngine:
    """获取全局授权引擎"""
    global _authorization_engine
    if _authorization_engine is None:
        _authorization_engine = AuthorizationEngine()
    return _authorization_engine


def set_authorization_engine(engine: AuthorizationEngine):
    """设置全局授权引擎"""
    global _authorization_engine
    _authorization_engine = engine
```

---

*文档继续，请查看第二部分...*