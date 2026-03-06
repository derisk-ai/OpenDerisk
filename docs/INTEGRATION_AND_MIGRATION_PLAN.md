# Derisk 统一工具架构与授权系统 - 整合与迁移方案

**版本**: v2.0  
**日期**: 2026-03-02  
**目标**: 将统一工具架构与授权系统无缝整合到现有core和core_v2架构，并完成历史工具迁移

---

## 📋 目录

- [一、整合策略概述](#一整合策略概述)
- [二、core架构整合方案](#二core架构整合方案)
- [三、core_v2架构整合方案](#三core_v2架构整合方案)
- [四、历史工具迁移方案](#四历史工具迁移方案)
- [五、自动集成机制](#五自动集成机制)
- [六、兼容性保证](#六兼容性保证)
- [七、数据迁移方案](#七数据迁移方案)
- [八、测试验证方案](#八测试验证方案)

---

## 一、整合策略概述

### 1.1 整合原则

| 原则 | 说明 |
|------|------|
| **无缝集成** | 新系统作为增强层，不破坏现有功能 |
| **渐进式迁移** | 支持新旧系统共存，逐步迁移 |
| **向后兼容** | 现有API和配置继续可用 |
| **透明升级** | 用户无需修改代码即可获得新功能 |

### 1.2 整合架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                     统一工具与授权系统 (新)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │
│  │ToolRegistry │  │AuthzEngine  │  │InteractionGW│                │
│  └─────────────┘  └─────────────┘  └─────────────┘                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  core架构     │  │  core_v2架构  │  │  新应用       │
│               │  │               │  │               │
│ 适配层        │  │ 直接集成      │  │ 原生使用      │
│ ↓             │  │ ↓             │  │ ↓             │
│ Conversable   │  │ Production    │  │ AgentBase     │
│ Agent         │  │ Agent         │  │               │
│               │  │               │  │               │
│ ✅ 保留原有   │  │ ✅ 统一权限   │  │ ✅ 新功能     │
│ ✅ 增强授权   │  │ ✅ 统一交互   │  │ ✅ 新API      │
└───────────────┘  └───────────────┘  └───────────────┘
```

### 1.3 迁移路径

```
阶段1: 基础设施层整合 (Week 1-2)
├── 统一工具注册中心
├── 统一授权引擎
└── 统一交互网关

阶段2: core架构适配 (Week 3-4)
├── 工具系统适配
├── 权限系统集成
└── 兼容层实现

阶段3: core_v2架构增强 (Week 5-6)
├── 直接集成统一系统
├── 替换现有实现
└── 功能增强

阶段4: 历史工具迁移 (Week 7-8)
├── 工具改造
├── 自动化迁移
└── 测试验证

阶段5: 全面测试与上线 (Week 9-10)
├── 集成测试
├── 性能测试
└── 灰度发布
```

---

## 二、core架构整合方案

### 2.1 工具系统集成

#### 2.1.1 创建适配层

```python
# 文件: derisk/agent/core/tool_adapter.py

"""
core架构工具适配器
将旧版Action系统适配到统一工具系统
"""

from typing import Dict, Any, Optional, List
import logging

from derisk.core.tools.base import ToolBase, ToolRegistry, ToolResult
from derisk.core.tools.metadata import (
    ToolMetadata,
    ToolParameter,
    AuthorizationRequirement,
    RiskLevel,
    RiskCategory,
)
from derisk.agent.core.action.base import Action, ActionOutput

logger = logging.getLogger(__name__)


class ActionToolAdapter(ToolBase):
    """
    将旧版Action适配为新版Tool
    
    示例:
        # 旧版Action
        class ReadFileAction(Action):
            async def run(self, **kwargs) -> ActionOutput:
                pass
        
        # 适配为新版Tool
        read_tool = ActionToolAdapter(ReadFileAction())
        tool_registry.register(read_tool)
    """
    
    def __init__(self, action: Action, metadata_override: Optional[Dict] = None):
        """
        初始化适配器
        
        Args:
            action: 旧版Action实例
            metadata_override: 元数据覆盖配置
        """
        self.action = action
        self.metadata_override = metadata_override or {}
        super().__init__(self._define_metadata())
    
    def _define_metadata(self) -> ToolMetadata:
        """定义工具元数据（从Action推断）"""
        # 从Action类推断元数据
        action_name = self.action.__class__.__name__
        
        # 尝试从Action获取风险信息
        risk_level = RiskLevel.MEDIUM
        risk_categories = []
        requires_auth = True
        
        # 检查Action是否有风险标记
        if hasattr(self.action, '_risk_level'):
            risk_level = getattr(self.action, '_risk_level')
        
        if hasattr(self.action, '_risk_categories'):
            risk_categories = getattr(self.action, '_risk_categories')
        
        if hasattr(self.action, '_requires_authorization'):
            requires_auth = getattr(self.action, '_requires_authorization')
        
        # 检查是否是只读操作
        if hasattr(self.action, '_read_only') and getattr(self.action, '_read_only'):
            risk_level = RiskLevel.SAFE
            requires_auth = False
            risk_categories = [RiskCategory.READ_ONLY]
        
        # 应用覆盖配置
        metadata_dict = {
            "id": action_name.replace('Action', '').lower(),
            "name": action_name.replace('Action', '').lower(),
            "description": self.action.__doc__ or f"Action: {action_name}",
            "category": self._infer_category(),
            "authorization": AuthorizationRequirement(
                requires_authorization=requires_auth,
                risk_level=risk_level,
                risk_categories=risk_categories,
            ),
            **self.metadata_override
        }
        
        return ToolMetadata(**metadata_dict)
    
    def _infer_category(self) -> str:
        """从Action类名推断类别"""
        action_name = self.action.__class__.__name__.lower()
        
        if 'file' in action_name or 'read' in action_name or 'write' in action_name:
            return "file_system"
        elif 'bash' in action_name or 'shell' in action_name:
            return "shell"
        elif 'web' in action_name or 'http' in action_name:
            return "network"
        elif 'code' in action_name:
            return "code"
        elif 'agent' in action_name:
            return "agent"
        else:
            return "custom"
    
    async def execute(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """执行工具（调用Action）"""
        try:
            # 调用旧版Action
            result: ActionOutput = await self.action.run(**arguments)
            
            # 转换结果
            return ToolResult(
                success=result.is_success if hasattr(result, 'is_success') else True,
                output=result.content or "",
                error=result.error if hasattr(result, 'error') else None,
                metadata={
                    "action_type": self.action.__class__.__name__,
                }
            )
        except Exception as e:
            logger.exception(f"[ActionToolAdapter] Action执行失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )


class CoreToolIntegration:
    """
    core架构工具集成管理器
    
    自动将所有旧版Action适配并注册到统一工具注册中心
    """
    
    def __init__(self, tool_registry: Optional[ToolRegistry] = None):
        self.registry = tool_registry or ToolRegistry()
        self._action_map: Dict[str, Action] = {}
    
    def register_action(
        self,
        action: Action,
        metadata_override: Optional[Dict] = None,
    ) -> str:
        """
        注册Action到统一工具系统
        
        Args:
            action: Action实例
            metadata_override: 元数据覆盖
            
        Returns:
            str: 工具名称
        """
        adapter = ActionToolAdapter(action, metadata_override)
        self.registry.register(adapter)
        self._action_map[adapter.metadata.name] = action
        
        logger.info(f"[CoreToolIntegration] 已注册Action: {adapter.metadata.name}")
        return adapter.metadata.name
    
    def register_all_actions(
        self,
        actions: Dict[str, Action],
        metadata_overrides: Optional[Dict[str, Dict]] = None,
    ):
        """
        批量注册Actions
        
        Args:
            actions: Action字典 {name: Action}
            metadata_overrides: 元数据覆盖字典
        """
        metadata_overrides = metadata_overrides or {}
        
        for name, action in actions.items():
            override = metadata_overrides.get(name)
            self.register_action(action, override)
    
    def get_tool_for_action(self, action_name: str) -> Optional[Action]:
        """获取Action对应的工具"""
        return self._action_map.get(action_name)


# 全局实例
core_tool_integration = CoreToolIntegration()


def get_core_tool_integration() -> CoreToolIntegration:
    """获取core架构工具集成实例"""
    return core_tool_integration
```

#### 2.1.2 集成到ConversableAgent

```python
# 文件: derisk/agent/core/base_agent.py (修改)

"""
修改ConversableAgent以集成统一工具系统
"""

from derisk.core.tools.base import ToolRegistry
from derisk.core.authorization.engine import AuthorizationEngine, get_authorization_engine
from derisk.core.interaction.gateway import InteractionGateway, get_interaction_gateway
from .tool_adapter import get_core_tool_integration


class ConversableAgent(Role, Agent):
    """可对话Agent - 增强版（集成统一工具系统）"""
    
    def __init__(self, **kwargs):
        # ========== 原有初始化逻辑 ==========
        Role.__init__(self, **kwargs)
        Agent.__init__(self)
        self.register_variables()
        
        # ========== 新增：统一工具系统集成 ==========
        self._unified_tool_registry: Optional[ToolRegistry] = None
        self._unified_auth_engine: Optional[AuthorizationEngine] = None
        self._unified_interaction: Optional[InteractionGateway] = None
        
        # 自动集成
        self._auto_integrate_unified_system()
    
    def _auto_integrate_unified_system(self):
        """自动集成统一工具系统"""
        # 1. 初始化统一组件
        self._unified_tool_registry = ToolRegistry()
        self._unified_auth_engine = get_authorization_engine()
        self._unified_interaction = get_interaction_gateway()
        
        # 2. 适配现有Action到统一工具系统
        core_integration = get_core_tool_integration()
        
        # 注册系统工具
        if hasattr(self, 'available_system_tools'):
            core_integration.register_all_actions(
                self.available_system_tools,
                self._get_action_metadata_overrides()
            )
        
        # 3. 创建权限规则集
        from derisk.core.authorization.model import AuthorizationConfig
        self._effective_auth_config = self._build_auth_config()
    
    def _get_action_metadata_overrides(self) -> Dict[str, Dict]:
        """获取Action元数据覆盖配置"""
        overrides = {}
        
        # 根据Action特性配置风险等级
        action_risk_config = {
            "read": {"risk_level": "safe", "requires_auth": False},
            "write": {"risk_level": "medium", "requires_auth": True},
            "edit": {"risk_level": "medium", "requires_auth": True},
            "bash": {"risk_level": "high", "requires_auth": True},
            "delete": {"risk_level": "high", "requires_auth": True},
        }
        
        for action_name, config in action_risk_config.items():
            if action_name in self.available_system_tools:
                overrides[action_name] = {
                    "authorization": config
                }
        
        return overrides
    
    def _build_auth_config(self) -> 'AuthorizationConfig':
        """构建授权配置"""
        from derisk.core.authorization.model import (
            AuthorizationConfig,
            AuthorizationMode,
            PermissionRuleset,
        )
        
        # 从agent_info转换
        if self.agent_info and self.agent_info.permission_ruleset:
            return AuthorizationConfig(
                mode=AuthorizationMode.STRICT,
                ruleset=self.agent_info.permission_ruleset,
            )
        
        # 从permission_ruleset转换
        if self.permission_ruleset:
            return AuthorizationConfig(
                mode=AuthorizationMode.STRICT,
                ruleset=self.permission_ruleset,
            )
        
        # 默认配置
        return AuthorizationConfig(
            mode=AuthorizationMode.MODERATE,
        )
    
    # ========== 新增：统一工具执行方法 ==========
    
    async def execute_tool_unified(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> 'ToolResult':
        """
        使用统一工具系统执行工具
        
        这是新的推荐方法，包含完整的授权检查
        """
        from derisk.core.authorization.engine import AuthorizationContext
        
        # 1. 获取工具
        tool = self._unified_tool_registry.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"工具不存在: {tool_name}"
            )
        
        # 2. 构建授权上下文
        auth_ctx = AuthorizationContext(
            session_id=self.agent_context.conv_id if self.agent_context else "default",
            agent_name=self.name,
            tool_name=tool_name,
            tool_metadata=tool.metadata,
            arguments=arguments,
        )
        
        # 3. 授权检查
        auth_result = await self._unified_auth_engine.check_authorization(
            ctx=auth_ctx,
            config=self._effective_auth_config,
            user_confirmation_handler=self._handle_user_confirmation_unified,
        )
        
        # 4. 根据授权结果执行
        if auth_result.decision in ["granted", "cached"]:
            # 执行工具
            return await tool.execute_safe(arguments, context)
        else:
            # 拒绝执行
            return ToolResult(
                success=False,
                output="",
                error=auth_result.user_message or "授权被拒绝"
            )
    
    async def _handle_user_confirmation_unified(
        self,
        request: Dict[str, Any],
    ) -> bool:
        """处理用户确认（统一交互系统）"""
        from derisk.core.interaction.protocol import create_authorization_request
        
        # 创建交互请求
        interaction_request = create_authorization_request(
            tool_name=request["tool_name"],
            tool_description=request["tool_description"],
            arguments=request["arguments"],
            risk_assessment=request["risk_assessment"],
            session_id=self.agent_context.conv_id if self.agent_context else "default",
            agent_name=self.name,
        )
        
        # 发送并等待响应
        response = await self._unified_interaction.send_and_wait(interaction_request)
        
        return response.is_confirmed
    
    # ========== 兼容性方法：保留原有接口 ==========
    
    async def execute_action(
        self,
        action_name: str,
        **kwargs,
    ) -> 'ActionOutput':
        """
        执行Action（兼容性接口）
        
        内部会路由到统一工具系统
        """
        # 尝试使用统一工具系统
        if self._unified_tool_registry and self._unified_tool_registry.get(action_name):
            result = await self.execute_tool_unified(
                tool_name=action_name,
                arguments=kwargs,
            )
            
            # 转换结果为ActionOutput
            action_output = ActionOutput(
                content=result.output,
                is_success=result.success,
            )
            if result.error:
                action_output.error = result.error
            
            return action_output
        
        # 回退到原有逻辑
        return await self._execute_action_legacy(action_name, **kwargs)
    
    async def _execute_action_legacy(self, action_name: str, **kwargs) -> 'ActionOutput':
        """原有Action执行逻辑（兼容性）"""
        # 原有的Action执行代码
        pass
```

### 2.2 权限系统集成

#### 2.2.1 权限配置转换

```python
# 文件: derisk/agent/core/permission_adapter.py

"""
权限配置适配器
将旧版权限配置转换为新版AuthorizationConfig
"""

from typing import Dict, Any, Optional
from derisk.core.authorization.model import (
    AuthorizationConfig,
    AuthorizationMode,
    PermissionRuleset,
    PermissionRule,
    PermissionAction,
)
from derisk.agent.core.agent_info import PermissionRuleset as OldPermissionRuleset


class PermissionConfigAdapter:
    """权限配置适配器"""
    
    @staticmethod
    def convert_from_old_ruleset(
        old_ruleset: OldPermissionRuleset,
    ) -> AuthorizationConfig:
        """从旧版PermissionRuleset转换"""
        return AuthorizationConfig(
            mode=AuthorizationMode.STRICT,
            ruleset=old_ruleset,
        )
    
    @staticmethod
    def convert_from_dict(
        config: Dict[str, str],
    ) -> AuthorizationConfig:
        """从字典配置转换"""
        ruleset = PermissionRuleset.from_dict(config)
        return AuthorizationConfig(
            mode=AuthorizationMode.STRICT,
            ruleset=ruleset,
        )
    
    @staticmethod
    def convert_from_app_config(
        app_config: Any,
    ) -> AuthorizationConfig:
        """从GptsApp配置转换"""
        rules = []
        
        # 从app配置中提取权限规则
        if hasattr(app_config, 'tool_permission'):
            for tool, action in app_config.tool_permission.items():
                rules.append(PermissionRule(
                    id=f"rule_{tool}",
                    name=f"Rule for {tool}",
                    tool_pattern=tool,
                    action=PermissionAction(action),
                    priority=10,
                ))
        
        ruleset = PermissionRuleset(rules=rules)
        
        return AuthorizationConfig(
            mode=AuthorizationMode.STRICT,
            ruleset=ruleset,
        )


def convert_permission_config(
    config: Any,
) -> AuthorizationConfig:
    """
    自动转换权限配置
    
    支持多种输入格式：
    - 旧版PermissionRuleset
    - Dict[str, str]
    - GptsApp配置
    """
    if isinstance(config, AuthorizationConfig):
        return config
    
    if isinstance(config, OldPermissionRuleset):
        return PermissionConfigAdapter.convert_from_old_ruleset(config)
    
    if isinstance(config, dict):
        return PermissionConfigAdapter.convert_from_dict(config)
    
    if hasattr(config, 'tool_permission'):
        return PermissionConfigAdapter.convert_from_app_config(config)
    
    # 默认配置
    return AuthorizationConfig()
```

### 2.3 自动集成钩子

```python
# 文件: derisk/agent/core/integration_hooks.py

"""
自动集成钩子
在Agent初始化时自动集成统一系统
"""

from typing import Any, Callable, Optional
import logging

logger = logging.getLogger(__name__)


class AutoIntegrationHooks:
    """自动集成钩子管理器"""
    
    _hooks: Dict[str, Callable] = {}
    
    @classmethod
    def register(cls, name: str, hook: Callable):
        """注册钩子"""
        cls._hooks[name] = hook
        logger.info(f"[AutoIntegration] 注册钩子: {name}")
    
    @classmethod
    def execute(cls, name: str, *args, **kwargs) -> Any:
        """执行钩子"""
        hook = cls._hooks.get(name)
        if hook:
            return hook(*args, **kwargs)
        return None


def auto_integrate_tools(agent: Any):
    """自动集成工具的钩子"""
    from .tool_adapter import get_core_tool_integration
    
    integration = get_core_tool_integration()
    
    # 自动注册系统工具
    if hasattr(agent, 'available_system_tools'):
        integration.register_all_actions(
            agent.available_system_tools
        )
    
    logger.info(f"[AutoIntegration] 已为Agent {agent.name} 集成工具")


def auto_integrate_authorization(agent: Any):
    """自动集成授权的钩子"""
    from .permission_adapter import convert_permission_config
    
    # 转换权限配置
    if hasattr(agent, 'permission_ruleset'):
        agent._effective_auth_config = convert_permission_config(
            agent.permission_ruleset
        )
    elif hasattr(agent, 'agent_info') and agent.agent_info:
        agent._effective_auth_config = convert_permission_config(
            agent.agent_info.permission_ruleset
        )
    
    logger.info(f"[AutoIntegration] 已为Agent {agent.name} 集成授权")


def auto_integrate_interaction(agent: Any):
    """自动集成交互的钩子"""
    from derisk.core.interaction.gateway import get_interaction_gateway
    
    agent._unified_interaction = get_interaction_gateway()
    
    logger.info(f"[AutoIntegration] 已为Agent {agent.name} 集成交互")


# 注册所有钩子
AutoIntegrationHooks.register("tools", auto_integrate_tools)
AutoIntegrationHooks.register("authorization", auto_integrate_authorization)
AutoIntegrationHooks.register("interaction", auto_integrate_interaction)
```

---

## 三、core_v2架构整合方案

### 3.1 直接集成方案

core_v2架构相对较新，可以直接集成统一系统：

```python
# 文件: derisk/agent/core_v2/integration/unified_integration.py

"""
core_v2架构统一系统集成
直接替换现有实现
"""

from typing import Optional
from derisk.core.tools.base import ToolRegistry
from derisk.core.authorization.engine import AuthorizationEngine
from derisk.core.interaction.gateway import InteractionGateway
from derisk.agent.core_v2.agent_base import AgentBase
from derisk.agent.core_v2.agent_info import AgentInfo


class UnifiedIntegration:
    """统一系统集成器"""
    
    def __init__(self):
        self.tool_registry = ToolRegistry()
        self.auth_engine = AuthorizationEngine()
        self.interaction_gateway = InteractionGateway()
    
    def integrate_to_agent(self, agent: AgentBase):
        """
        将统一系统集成到Agent
        
        Args:
            agent: Agent实例
        """
        # 替换工具注册中心
        agent.tools = self.tool_registry
        
        # 设置授权引擎
        agent.auth_engine = self.auth_engine
        
        # 设置交互网关
        agent.interaction = self.interaction_gateway
    
    def register_tools_from_config(
        self,
        tool_configs: Dict[str, Any],
    ):
        """从配置注册工具"""
        for tool_name, config in tool_configs.items():
            # 创建工具实例
            tool = self._create_tool_from_config(tool_name, config)
            self.tool_registry.register(tool)
    
    def _create_tool_from_config(
        self,
        tool_name: str,
        config: Dict[str, Any],
    ) -> 'ToolBase':
        """从配置创建工具"""
        from derisk.core.tools.decorators import tool
        
        @tool(
            name=tool_name,
            description=config.get('description', ''),
            category=config.get('category', 'custom'),
            authorization=config.get('authorization'),
        )
        async def configured_tool(**kwargs):
            # 执行工具逻辑
            pass
        
        return configured_tool


# 全局集成实例
unified_integration = UnifiedIntegration()


def get_unified_integration() -> UnifiedIntegration:
    """获取统一集成实例"""
    return unified_integration
```

### 3.2 生产Agent增强

```python
# 文件: derisk/agent/core_v2/production_agent.py (增强版)

"""
增强版ProductionAgent
完全集成统一工具与授权系统
"""

from derisk.core.tools.base import ToolRegistry
from derisk.core.authorization.engine import AuthorizationEngine, get_authorization_engine
from derisk.core.interaction.gateway import InteractionGateway, get_interaction_gateway
from .agent_base import AgentBase
from .agent_info import AgentInfo


class ProductionAgent(AgentBase):
    """生产可用Agent - 完全集成版"""
    
    def __init__(
        self,
        info: AgentInfo,
        llm_adapter: Optional[Any] = None,
        tool_registry: Optional[ToolRegistry] = None,
        auth_engine: Optional[AuthorizationEngine] = None,
        interaction_gateway: Optional[InteractionGateway] = None,
    ):
        super().__init__(info)
        
        # LLM适配器
        self.llm = llm_adapter
        
        # 统一工具系统（必须）
        self.tools = tool_registry or ToolRegistry()
        
        # 统一授权系统（必须）
        self.auth_engine = auth_engine or get_authorization_engine()
        
        # 统一交互系统（必须）
        self.interaction = interaction_gateway or get_interaction_gateway()
        
        # 自动注册内置工具
        if len(self.tools.list_all()) == 0:
            self._register_builtin_tools()
    
    def _register_builtin_tools(self):
        """注册内置工具"""
        from derisk.core.tools.builtin import register_builtin_tools
        register_builtin_tools(self.tools)
    
    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> 'ToolResult':
        """执行工具 - 完整授权流程"""
        from derisk.core.authorization.engine import AuthorizationContext
        from derisk.core.tools.base import ToolResult
        
        # 1. 获取工具
        tool = self.tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"工具不存在: {tool_name}"
            )
        
        # 2. 授权检查（使用info中的授权配置）
        auth_ctx = AuthorizationContext(
            session_id=self._session_id or "default",
            agent_name=self.info.name,
            tool_name=tool_name,
            tool_metadata=tool.metadata,
            arguments=arguments,
        )
        
        auth_result = await self.auth_engine.check_authorization(
            ctx=auth_ctx,
            config=self.info.authorization,
            user_confirmation_handler=self._handle_user_confirmation,
        )
        
        # 3. 执行或拒绝
        if auth_result.decision in ["granted", "cached"]:
            return await tool.execute_safe(arguments, context)
        else:
            return ToolResult(
                success=False,
                output="",
                error=auth_result.user_message or "授权被拒绝"
            )
    
    async def _handle_user_confirmation(
        self,
        request: Dict[str, Any],
    ) -> bool:
        """处理用户确认"""
        from derisk.core.interaction.protocol import create_authorization_request
        
        interaction_request = create_authorization_request(
            tool_name=request["tool_name"],
            tool_description=request["tool_description"],
            arguments=request["arguments"],
            risk_assessment=request["risk_assessment"],
            session_id=self._session_id,
            agent_name=self.info.name,
        )
        
        response = await self.interaction.send_and_wait(interaction_request)
        return response.is_confirmed
```

---

## 四、历史工具迁移方案

### 4.1 现有系统工具清单

基于代码分析，需要迁移的工具类别：

| 类别 | 工具数量 | 迁移优先级 | 说明 |
|------|---------|-----------|------|
| 文件系统工具 | 5个 | P0 | read, write, edit, glob, grep |
| Shell工具 | 1个 | P0 | bash |
| 网络工具 | 3个 | P1 | webfetch, websearch |
| 代码工具 | 2个 | P1 | analyze |
| Agent工具 | 5个 | P2 | call_agent,等 |
| 审计工具 | 3个 | P2 | log等 |

### 4.2 工具迁移脚本

```python
# 文件: scripts/migrate_tools.py

"""
历史工具迁移脚本
自动将所有历史工具迁移到统一工具系统
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ToolMigration:
    """工具迁移处理器"""
    
    # 工具风险配置
    TOOL_RISK_CONFIG = {
        # 文件系统
        "read": {
            "risk_level": "safe",
            "requires_auth": False,
            "categories": ["read_only"],
        },
        "write": {
            "risk_level": "medium",
            "requires_auth": True,
            "categories": ["file_write"],
        },
        "edit": {
            "risk_level": "medium",
            "requires_auth": True,
            "categories": ["file_write"],
        },
        "glob": {
            "risk_level": "safe",
            "requires_auth": False,
            "categories": ["read_only"],
        },
        "grep": {
            "risk_level": "safe",
            "requires_auth": False,
            "categories": ["read_only"],
        },
        # Shell
        "bash": {
            "risk_level": "high",
            "requires_auth": True,
            "categories": ["shell_execute"],
        },
        # 网络
        "webfetch": {
            "risk_level": "low",
            "requires_auth": True,
            "categories": ["network_outbound"],
        },
        "websearch": {
            "risk_level": "low",
            "requires_auth": True,
            "categories": ["network_outbound"],
        },
        # Agent
        "call_agent": {
            "risk_level": "medium",
            "requires_auth": True,
            "categories": ["agent"],
        },
    }
    
    def __init__(self, source_dir: str, target_dir: str):
        self.source_dir = Path(source_dir)
        self.target_dir = Path(target_dir)
        self.migrated_count = 0
        self.failed_count = 0
    
    def migrate_all(self):
        """迁移所有工具"""
        logger.info("开始迁移工具...")
        
        # 查找所有Action文件
        action_files = self._find_action_files()
        
        for action_file in action_files:
            try:
                self._migrate_action_file(action_file)
                self.migrated_count += 1
            except Exception as e:
                logger.error(f"迁移失败: {action_file}, 错误: {e}")
                self.failed_count += 1
        
        logger.info(f"迁移完成: 成功 {self.migrated_count}, 失败 {self.failed_count}")
    
    def _find_action_files(self) -> List[Path]:
        """查找所有Action文件"""
        action_files = []
        
        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                if file.endswith('.py') and 'action' in file.lower():
                    action_files.append(Path(root) / file)
        
        return action_files
    
    def _migrate_action_file(self, action_file: Path):
        """迁移单个Action文件"""
        logger.info(f"迁移文件: {action_file}")
        
        # 读取源文件
        with open(action_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取Action类
        actions = self._extract_actions(content)
        
        for action_name, action_info in actions.items():
            # 生成新工具代码
            new_tool_code = self._generate_tool_code(action_name, action_info)
            
            # 写入目标文件
            target_file = self.target_dir / f"{action_name}.py"
            with open(target_file, 'w', encoding='utf-8') as f:
                f.write(new_tool_code)
            
            logger.info(f"已生成工具: {action_name}")
    
    def _extract_actions(self, content: str) -> Dict[str, Any]:
        """从文件中提取Action定义"""
        actions = {}
        
        # 简单的正则提取（实际可能需要更复杂的解析）
        pattern = r'class\s+(\w+Action)\s*\([^)]*Action[^)]*\):'
        matches = re.findall(pattern, content)
        
        for match in matches:
            action_name = match.replace('Action', '').lower()
            
            # 提取docstring
            docstring_pattern = rf'class\s+{match}.*?"""(.*?)"""'
            docstring_match = re.search(docstring_pattern, content, re.DOTALL)
            description = docstring_match.group(1).strip() if docstring_match else ""
            
            actions[action_name] = {
                "class_name": match,
                "description": description,
            }
        
        return actions
    
    def _generate_tool_code(
        self,
        action_name: str,
        action_info: Dict[str, Any],
    ) -> str:
        """生成新工具代码"""
        risk_config = self.TOOL_RISK_CONFIG.get(action_name, {
            "risk_level": "medium",
            "requires_auth": True,
            "categories": [],
        })
        
        template = '''"""
{name.upper()} Tool - 迁移自 {class_name}
"""

from typing import Dict, Any, Optional
from derisk.core.tools.decorators import tool
from derisk.core.tools.metadata import (
    AuthorizationRequirement,
    RiskLevel,
    RiskCategory,
)


@tool(
    name="{name}",
    description="""{description}""",
    category="tool_category",
    authorization=AuthorizationRequirement(
        requires_authorization={requires_auth},
        risk_level=RiskLevel.{risk_level},
        risk_categories={risk_categories},
    ),
)
async def {name}_tool(
    {parameters}
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    {description}
    
    Args:
        {param_docs}
        context: 执行上下文
        
    Returns:
        str: 执行结果
    """
    # TODO: 从原Action迁移实现逻辑
    # 原: {class_name}
    
    result = ""
    return result
'''
        
        # 填充模板
        code = template.format(
            name=action_name,
            class_name=action_info['class_name'],
            description=action_info['description'],
            requires_auth=risk_config['requires_auth'],
            risk_level=risk_config['risk_level'].upper(),
            risk_categories=f"[RiskCategory.{c.upper()} for c in {risk_config['categories']}]",
            parameters="# 添加参数",
            param_docs="# 参数说明",
        )
        
        return code


def main():
    """主函数"""
    source_dir = "derisk/agent/core/sandbox/tools"
    target_dir = "derisk/core/tools/builtin"
    
    migration = ToolMigration(source_dir, target_dir)
    migration.migrate_all()


if __name__ == "__main__":
    main()
```

### 4.3 自动化迁移命令

```bash
# scripts/run_migration.sh

#!/bin/bash

echo "==================================="
echo "  Derisk 工具迁移脚本"
echo "==================================="

# 1. 备份现有工具
echo "1. 备份现有工具..."
tar -czf backup_tools_$(date +%Y%m%d_%H%M%S).tar.gz \
    packages/derisk-core/src/derisk/agent/core/sandbox/tools/

# 2. 运行迁移脚本
echo "2. 运行迁移脚本..."
python scripts/migrate_tools.py

# 3. 运行测试
echo "3. 运行测试..."
pytest tests/unit/test_builtin_tools.py -v

# 4. 生成迁移报告
echo "4. 生成迁移报告..."
python scripts/generate_migration_report.py

echo "==================================="
echo "  迁移完成"
echo "==================================="
```

---

## 五、自动集成机制

### 5.1 初始化自动集成

```python
# 文件: derisk/core/auto_integration.py

"""
自动集成机制
在系统启动时自动集成所有组件
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AutoIntegrationManager:
    """自动集成管理器"""
    
    _instance: Optional['AutoIntegrationManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._integrated_components = []
    
    def auto_integrate_all(self):
        """自动集成所有组件"""
        logger.info("[AutoIntegration] 开始自动集成...")
        
        # 1. 集成工具系统
        self._integrate_tools()
        
        # 2. 集成授权系统
        self._integrate_authorization()
        
        # 3. 集成交互系统
        self._integrate_interaction()
        
        # 4. 集成到core架构
        self._integrate_to_core()
        
        # 5. 集成到core_v2架构
        self._integrate_to_core_v2()
        
        logger.info(f"[AutoIntegration] 集成完成: {self._integrated_components}")
    
    def _integrate_tools(self):
        """集成工具系统"""
        from derisk.core.tools.builtin import register_builtin_tools
        from derisk.core.tools.base import ToolRegistry
        
        registry = ToolRegistry()
        register_builtin_tools(registry)
        
        self._integrated_components.append("tools")
        logger.info("[AutoIntegration] 工具系统集成完成")
    
    def _integrate_authorization(self):
        """集成授权系统"""
        from derisk.core.authorization.engine import get_authorization_engine
        
        engine = get_authorization_engine()
        
        self._integrated_components.append("authorization")
        logger.info("[AutoIntegration] 授权系统集成完成")
    
    def _integrate_interaction(self):
        """集成交互系统"""
        from derisk.core.interaction.gateway import get_interaction_gateway
        
        gateway = get_interaction_gateway()
        
        self._integrated_components.append("interaction")
        logger.info("[AutoIntegration] 交互系统集成完成")
    
    def _integrate_to_core(self):
        """集成到core架构"""
        try:
            from derisk.agent.core.tool_adapter import get_core_tool_integration
            from derisk.agent.core.integration_hooks import AutoIntegrationHooks
            
            # 执行集成钩子
            for hook_name in ["tools", "authorization", "interaction"]:
                AutoIntegrationHooks.execute(hook_name, None)
            
            self._integrated_components.append("core_integration")
            logger.info("[AutoIntegration] core架构集成完成")
        except Exception as e:
            logger.warning(f"[AutoIntegration] core架构集成跳过: {e}")
    
    def _integrate_to_core_v2(self):
        """集成到core_v2架构"""
        try:
            from derisk.agent.core_v2.integration.unified_integration import get_unified_integration
            
            integration = get_unified_integration()
            
            self._integrated_components.append("core_v2_integration")
            logger.info("[AutoIntegration] core_v2架构集成完成")
        except Exception as e:
            logger.warning(f"[AutoIntegration] core_v2架构集成跳过: {e}")


# 全局实例
auto_integration_manager = AutoIntegrationManager()


def init_auto_integration():
    """初始化自动集成（在应用启动时调用）"""
    auto_integration_manager.auto_integrate_all()
```

### 5.2 应用启动集成

```python
# 文件: derisk/app.py (或 derisk_serve/app.py)

"""
应用启动入口
初始化自动集成
"""

from derisk.core.auto_integration import init_auto_integration


def create_app():
    """创建应用"""
    # 初始化自动集成（最优先）
    init_auto_integration()
    
    # 创建应用
    # ... 原有应用创建逻辑
    
    return app


if __name__ == "__main__":
    app = create_app()
    app.run()
```

---

## 六、兼容性保证

### 6.1 API兼容层

```python
# 文件: derisk/core/compatibility_layer.py

"""
兼容层
保证API向后兼容
"""

from typing import Dict, Any, Optional, Callable
import warnings
import logging

logger = logging.getLogger(__name__)


class CompatibilityLayer:
    """兼容层管理器"""
    
    @staticmethod
    def wrap_tool_for_action(tool_executor: Callable) -> Callable:
        """
        将工具执行器包装为Action兼容接口
        
        Args:
            tool_executor: 新版工具执行器
            
        Returns:
            Callable: Action兼容的执行器
        """
        async def action_executor(**kwargs) -> 'ActionOutput':
            from derisk.agent.core.action.base import ActionOutput
            
            # 调用新版工具
            result = await tool_executor(**kwargs)
            
            # 转换结果
            return ActionOutput(
                content=result.output,
                is_success=result.success,
                error=result.error if hasattr(result, 'error') else None,
            )
        
        return action_executor
    
    @staticmethod
    def wrap_auth_config_for_agent(
        auth_config: Any,
    ) -> 'AuthorizationConfig':
        """
        将各种权限配置转换为AuthorizationConfig
        
        支持格式：
        - PermissionRuleset (旧版)
        - Dict[str, str]
        - AuthorizationConfig (新版)
        """
        from derisk.core.authorization.model import AuthorizationConfig
        from derisk.agent.core.permission_adapter import convert_permission_config
        
        if isinstance(auth_config, AuthorizationConfig):
            return auth_config
        
        warnings.warn(
            "使用旧版权限配置格式，建议迁移到AuthorizationConfig",
            DeprecationWarning
        )
        
        return convert_permission_config(auth_config)


# 兼容性装饰器
def deprecated_api(replacement: str):
    """
    API弃用装饰器
    
    Args:
        replacement: 替代API
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            warnings.warn(
                f"{func.__name__} 已弃用，请使用 {replacement}",
                DeprecationWarning,
                stacklevel=2
            )
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

### 6.2 配置兼容

```python
# 文件: derisk/core/config_adapter.py

"""
配置兼容适配器
支持新旧配置格式
"""

from typing import Dict, Any
from derisk.core.authorization.model import AuthorizationConfig
from derisk.core.agent.info import AgentInfo


class ConfigAdapter:
    """配置适配器"""
    
    @staticmethod
    def load_agent_config(config: Dict[str, Any]) -> AgentInfo:
        """
        加载Agent配置（支持新旧格式）
        
        新格式:
        {
            "name": "agent",
            "authorization": {
                "mode": "strict",
                "whitelist_tools": ["read"],
            }
        }
        
        旧格式:
        {
            "name": "agent",
            "permission": {
                "read": "allow",
                "write": "ask",
            }
        }
        """
        # 检查是否使用新格式
        if "authorization" in config:
            authorization = AuthorizationConfig(**config["authorization"])
        elif "permission" in config:
            # 转换旧格式
            from derisk.agent.core.permission_adapter import convert_permission_config
            authorization = convert_permission_config(config["permission"])
        else:
            authorization = AuthorizationConfig()
        
        # 构建AgentInfo
        return AgentInfo(
            name=config.get("name", "agent"),
            description=config.get("description"),
            authorization=authorization,
            **{k: v for k, v in config.items() 
               if k not in ["name", "description", "authorization", "permission"]}
        )
```

---

## 七、数据迁移方案

### 7.1 数据库迁移

```python
# 文件: migrations/v1_to_v2/migrate_tools.py

"""
数据库迁移工具
将旧版工具数据迁移到新表结构
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ToolDataMigration:
    """工具数据迁移"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def migrate_tool_definitions(self):
        """迁移工具定义"""
        # 查询旧版工具定义
        old_tools = await self._query_old_tools()
        
        # 转换并插入新表
        for old_tool in old_tools:
            new_tool = self._convert_tool_definition(old_tool)
            await self._insert_new_tool(new_tool)
        
        await self.session.commit()
    
    async def migrate_permission_configs(self):
        """迁移权限配置"""
        # 查询旧版权限配置
        old_configs = await self._query_old_permissions()
        
        # 转换并插入新表
        for old_config in old_configs:
            new_config = self._convert_permission_config(old_config)
            await self._insert_new_permission(new_config)
        
        await self.session.commit()
    
    async def _query_old_tools(self) -> List[Dict]:
        """查询旧版工具"""
        result = await self.session.execute(
            text("SELECT * FROM old_tools_table")
        )
        return [dict(row) for row in result]
    
    async def _query_old_permissions(self) -> List[Dict]:
        """查询旧版权限配置"""
        result = await self.session.execute(
            text("SELECT * FROM old_permissions_table")
        )
        return [dict(row) for row in result]
    
    def _convert_tool_definition(self, old_tool: Dict) -> Dict:
        """转换工具定义"""
        return {
            "id": old_tool["tool_id"],
            "name": old_tool["tool_name"],
            "version": "1.0.0",
            "description": old_tool.get("description", ""),
            "category": old_tool.get("category", "custom"),
            "metadata": {
                "authorization": {
                    "requires_authorization": old_tool.get("ask_user", True),
                    "risk_level": self._infer_risk_level(old_tool),
                }
            },
            "created_at": old_tool.get("created_at", datetime.now()),
        }
    
    def _infer_risk_level(self, old_tool: Dict) -> str:
        """推断风险等级"""
        # 根据工具特性推断
        if old_tool.get("read_only"):
            return "safe"
        elif old_tool.get("dangerous"):
            return "high"
        else:
            return "medium"


async def run_migration():
    """运行迁移"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    engine = create_async_engine("postgresql+asyncpg://...")
    async_session = sessionmaker(engine, class_=AsyncSession)
    
    async with async_session() as session:
        migration = ToolDataMigration(session)
        
        print("开始迁移工具定义...")
        await migration.migrate_tool_definitions()
        
        print("开始迁移权限配置...")
        await migration.migrate_permission_configs()
        
        print("迁移完成")


if __name__ == "__main__":
    asyncio.run(run_migration())
```

---

## 八、测试验证方案

### 8.1 兼容性测试

```python
# 文件: tests/compatibility/test_integration.py

"""
整合与兼容性测试
验证新旧系统集成正确性
"""

import pytest
from derisk.core.tools.base import ToolRegistry
from derisk.core.authorization.engine import AuthorizationEngine
from derisk.agent.core.tool_adapter import ActionToolAdapter
from derisk.agent.core.action.base import Action, ActionOutput


class TestCoreIntegration:
    """core架构集成测试"""
    
    def test_action_adapter(self):
        """测试Action适配器"""
        # 创建旧版Action
        class TestAction(Action):
            async def run(self, **kwargs) -> ActionOutput:
                return ActionOutput(content="test result", is_success=True)
        
        # 创建适配器
        adapter = ActionToolAdapter(TestAction())
        
        # 验证元数据
        assert adapter.metadata.name == "test"
        assert adapter.metadata.authorization is not None
    
    @pytest.mark.asyncio
    async def test_tool_execution(self):
        """测试工具执行"""
        # 创建Action和适配器
        class TestAction(Action):
            async def run(self, **kwargs) -> ActionOutput:
                return ActionOutput(content="result", is_success=True)
        
        adapter = ActionToolAdapter(TestAction())
        
        # 注册到Registry
        registry = ToolRegistry()
        registry.register(adapter)
        
        # 执行
        result = await registry.execute("test", {})
        
        assert result.success
        assert result.output == "result"


class TestCoreV2Integration:
    """core_v2架构集成测试"""
    
    def test_agent_with_unified_tools(self):
        """测试Agent使用统一工具"""
        from derisk.agent.core_v2.production_agent import ProductionAgent
        from derisk.agent.core_v2.agent_info import AgentInfo
        
        info = AgentInfo(name="test")
        agent = ProductionAgent(info)
        
        assert agent.tools is not None
        assert agent.auth_engine is not None
        assert agent.interaction is not None


class TestBackwardCompatibility:
    """向后兼容性测试"""
    
    def test_old_permission_format(self):
        """测试旧版权限格式兼容"""
        from derisk.core.authorization.model import AuthorizationConfig
        from derisk.agent.core.permission_adapter import convert_permission_config
        
        # 旧格式
        old_config = {
            "read": "allow",
            "write": "ask",
            "bash": "deny",
        }
        
        # 转换
        new_config = convert_permission_config(old_config)
        
        # 验证
        assert isinstance(new_config, AuthorizationConfig)
        assert new_config.ruleset is not None
```

### 8.2 集成测试清单

```markdown
# 测试清单

## core架构测试
- [ ] Action适配器正确工作
- [ ] 工具注册到统一Registry
- [ ] 授权检查集成
- [ ] 交互系统集成
- [ ] 旧API调用兼容

## core_v2架构测试
- [ ] 统一工具系统集成
- [ ] 统一授权系统集成
- [ ] 统一交互系统集成
- [ ] Agent执行流程正确

## 工具迁移测试
- [ ] 所有内置工具迁移完成
- [ ] 工具元数据正确
- [ ] 授权配置正确
- [ ] 功能测试通过

## 兼容性测试
- [ ] 旧版配置加载
- [ ] 旧版API调用
- [ ] 数据迁移
- [ ] 性能无明显下降
```

---

## 九、迁移执行计划

### 9.1 迁移步骤

```
第1步: 准备工作 (Day 1-2)
├── 备份现有代码和数据
├── 创建迁移分支
└── 准备测试环境

第2步: 基础设施层 (Day 3-7)
├── 部署统一工具系统
├── 部署统一授权系统
├── 部署统一交互系统
└── 测试基础功能

第3步: core架构适配 (Day 8-14)
├── 创建适配层
├── 集成到ConversableAgent
├── 测试兼容性
└── 性能测试

第4步: core_v2架构增强 (Day 15-21)
├── 直接集成统一系统
├── 替换现有实现
├── 功能测试
└── 性能测试

第5步: 工具迁移 (Day 22-35)
├── 批量迁移工具
├── 修复问题
├── 测试验证
└── 文档更新

第6步: 集成测试 (Day 36-42)
├── 端到端测试
├── 兼容性测试
├── 性能测试
└── 安全测试

第7步: 灰度发布 (Day 43-56)
├── 内部测试
├── 小规模用户测试
├── 全量发布
└── 监控观察
```

### 9.2 回滚方案

```bash
#!/bin/bash
# scripts/rollback.sh

echo "开始回滚..."

# 1. 恢复代码
git checkout backup_branch

# 2. 恢复数据
psql -U postgres -d derisk < backup_$(date +%Y%m%d).sql

# 3. 重启服务
systemctl restart derisk-server

echo "回滚完成"
```

---

## 十、总结

### 关键成果

1. **core架构** - 通过适配层无缝集成，保留所有原有功能
2. **core_v2架构** - 直接集成统一系统，功能增强
3. **历史工具** - 自动化迁移脚本，批量转换
4. **向后兼容** - API兼容层，配置迁移
5. **自动集成** - 系统启动时自动完成集成

### 后续工作

1. 完善自动化测试
2. 性能优化
3. 文档完善
4. 用户培训

---

**文档版本**: v2.0  
**最后更新**: 2026-03-02  
**维护团队**: Derisk架构团队