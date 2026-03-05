# Derisk 统一工具架构与授权系统 - 文档索引

**版本**: v2.0  
**日期**: 2026-03-02  

---

## 📚 文档结构

本架构设计文档体系包含四个核心部分，建议按顺序阅读：

### [第一部分：核心系统设计](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md)

**主要内容：**
- **执行摘要** - 背景与核心目标
- **架构全景图** - 整体架构与模块关系
- **统一工具系统设计**
  - 工具元数据模型
  - 工具基类与注册
  - 工具装饰器与快速定义
- **统一权限系统设计**
  - 权限模型
  - 授权引擎

**关键代码示例：**
- `ToolMetadata` - 工具元数据标准
- `AuthorizationRequirement` - 授权需求定义
- `AuthorizationEngine` - 授权决策引擎
- `RiskAssessor` - 风险评估器

---

### [第二部分：交互与Agent集成](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART2.md)

**主要内容：**
- **统一交互系统设计**
  - 交互协议
  - 交互网关
- **Agent集成设计**
  - AgentInfo增强
  - 统一Agent基类

**关键代码示例：**
- `InteractionRequest/Response` - 交互协议定义
- `InteractionGateway` - 交互网关实现
- `AgentInfo` - Agent配置模型
- `AgentBase` - Agent基类

---

### [第三部分：实施指南与最佳实践](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md)

**主要内容：**
- **产品使用场景**
  - 代码开发助手
  - 数据分析助手
  - 运维自动化助手
  - 多Agent协作
- **开发实施指南**
  - 目录结构
  - 实施步骤
  - 数据库设计
- **监控与运维**
  - 监控指标
  - 日志规范
  - 审计追踪
- **最佳实践**
- **常见问题FAQ**
- **总结与展望**

**实用工具：**
- 完整的配置示例
- 数据库Schema
- 监控指标定义
- 常见问题解答

---

### [第四部分：开发任务规划](./DEVELOPMENT_TASK_PLAN.md)

**主要内容：**
- **项目概览**
  - 核心目标
  - 参考文档
  - 开发周期
- **里程碑规划**
  - 6个主要里程碑
  - 12周详细计划
- **详细任务清单**
  - 阶段一：核心模型定义
  - 阶段二：工具系统实现
  - 阶段三：授权系统实现
  - 阶段四：交互系统实现
  - 阶段五：Agent集成
  - 阶段六：前端开发
- **质量标准**
- **进度追踪**

**任务清单特点：**
- 每个任务包含优先级和工时估算
- 具体步骤描述和代码示例
- 明确的验收标准
- 测试要求和覆盖率要求

---

### [第五部分：整合与迁移方案](./INTEGRATION_AND_MIGRATION_PLAN.md) ⭐ **重要**

**主要内容：**
- **整合策略概述**
  - 整合原则
  - 整合架构图
  - 迁移路径
- **core架构整合方案**
  - 工具系统集成（ActionToolAdapter）
  - 权限系统集成
  - 自动集成钩子
- **core_v2架构整合方案**
  - 直接集成方案
  - 生产Agent增强
- **历史工具迁移方案**
  - 工具清单
  - 自动化迁移脚本
  - 迁移执行命令
- **自动集成机制**
  - 初始化自动集成
  - 应用启动集成
- **兼容性保证**
  - API兼容层
  - 配置兼容
- **数据迁移方案**
  - 数据库迁移
  - 配置迁移
- **测试验证方案**
  - 兼容性测试
  - 集成测试清单
- **迁移执行计划**

**核心价值：**
- 🔄 **自动集成** - core和core_v2架构自动集成统一系统
- 📦 **无缝迁移** - 历史工具自动迁移到新系统
- 🔙 **向后兼容** - 保证现有API和功能继续可用
- ✅ **测试验证** - 完整的兼容性和集成测试

---

## 🎯 快速导航

### 按角色导航

**🔧 开发者**
1. [工具元数据模型](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md#31-工具元数据模型)
2. [工具装饰器](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md#33-工具装饰器与快速定义)
3. [Agent基类](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART2.md#62-统一agent基类)
4. [最佳实践](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md#十四最佳实践)

**🏗️ 架构师**
1. [架构全景图](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md#二架构全景图)
2. [权限模型](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md#41-权限模型)
3. [交互协议](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART2.md#51-交互协议)
4. [数据库设计](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md#123-数据库设计)

**📊 运维人员**
1. [监控指标](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md#131-监控指标)
2. [日志规范](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md#132-日志规范)
3. [审计追踪](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md#133-审计追踪)
4. [运维场景](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md#113-场景三运维自动化助手)

**💼 产品经理**
1. [产品使用场景](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md#十一产品使用场景)
2. [实施路线图](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md#122-实施步骤)
3. [常见问题FAQ](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md#十五常见问题faq)

---

## 📝 核心概念速查

### 工具系统

| 概念 | 说明 | 文档位置 |
|------|------|----------|
| `ToolMetadata` | 工具元数据标准 | [第一部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md#31-工具元数据模型) |
| `AuthorizationRequirement` | 工具授权需求 | [第一部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md#31-工具元数据模型) |
| `ToolBase` | 工具基类 | [第一部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md#32-工具基类与注册) |
| `ToolRegistry` | 工具注册中心 | [第一部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md#32-工具基类与注册) |

### 权限系统

| 概念 | 说明 | 文档位置 |
|------|------|----------|
| `AuthorizationMode` | 授权模式 | [第一部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md#41-权限模型) |
| `AuthorizationConfig` | 授权配置 | [第一部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md#41-权限模型) |
| `AuthorizationEngine` | 授权引擎 | [第一部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md#42-授权引擎) |
| `RiskAssessor` | 风险评估器 | [第一部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE.md#42-授权引擎) |

### 交互系统

| 概念 | 说明 | 文档位置 |
|------|------|----------|
| `InteractionRequest` | 交互请求 | [第二部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART2.md#51-交互协议) |
| `InteractionResponse` | 交互响应 | [第二部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART2.md#51-交互协议) |
| `InteractionGateway` | 交互网关 | [第二部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART2.md#52-交互网关) |

### Agent系统

| 概念 | 说明 | 文档位置 |
|------|------|----------|
| `AgentInfo` | Agent配置 | [第二部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART2.md#61-agentinfo增强) |
| `AgentBase` | Agent基类 | [第二部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART2.md#62-统一agent基类) |
| `ToolSelectionPolicy` | 工具选择策略 | [第二部分](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART2.md#61-agentinfo增强) |

---

## 🔍 快速示例

### 定义一个工具

```python
from derisk.core.tools.decorators import tool
from derisk.core.tools.metadata import (
    AuthorizationRequirement,
    RiskLevel,
    RiskCategory,
)

@tool(
    name="read_file",
    description="Read file content",
    authorization=AuthorizationRequirement(
        requires_authorization=False,
        risk_level=RiskLevel.SAFE,
    ),
)
async def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()
```

### 配置Agent授权

```python
from derisk.core.agent.info import AgentInfo
from derisk.core.authorization.model import (
    AuthorizationConfig,
    AuthorizationMode,
    LLMJudgmentPolicy,
)

agent_info = AgentInfo(
    name="dev-assistant",
    description="代码开发助手",
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.STRICT,
        llm_policy=LLMJudgmentPolicy.BALANCED,
        whitelist_tools=["read", "glob", "grep"],
    ),
)
```

### 执行工具

```python
from derisk.core.agent.base import AgentBase

class MyAgent(AgentBase):
    async def run(self, message: str):
        # 执行工具，自动进行授权检查
        result = await self.execute_tool(
            tool_name="read_file",
            arguments={"path": "/src/main.py"},
        )
        return result
```

---

## 📖 相关文档

### 现有架构文档
- [Core Agent架构](./CORE_V2_AGENT_HIERARCHY.md)
- [工具系统架构](./TOOL_SYSTEM_ARCHITECTURE.md)
- [交互使用指南](../packages/derisk-core/src/derisk/agent/INTERACTION_USAGE_GUIDE.md)

### 参考实现
- [core_v2 实现示例](../packages/derisk-core/src/derisk/agent/core_v2/)
- [工具实现示例](../packages/derisk-core/src/derisk/agent/tools_v2/)
- [交互实现示例](../packages/derisk-core/src/derisk/agent/interaction/)

---

## 💬 反馈与贡献

如果您在使用过程中遇到问题或有改进建议，请：

1. 查看 [常见问题FAQ](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md#十五常见问题faq)
2. 参考现有的 [最佳实践](./UNIFIED_TOOL_AUTHORIZATION_ARCHITECTURE_PART3.md#十四最佳实践)
3. 提交 Issue 或 Pull Request

---

**维护团队**: Derisk架构团队  
**最后更新**: 2026-03-02