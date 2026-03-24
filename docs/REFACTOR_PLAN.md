# Agent 系统重构计划

## 一、对比分析总结

### 1. opencode 最佳实践

| 维度 | opencode 设计 | 当前系统问题 | 改进方向 |
|------|--------------|-------------|---------|
| Agent定义 | Zod Schema + 简洁配置 | ABC抽象类过于复杂 | 简化接口，配置化Agent |
| Agent类型 | Primary/Subagent清晰分层 | 层次不清晰 | 规范Agent类型体系 |
| 权限系统 | Permission Ruleset细粒度控制 | 无细粒度权限 | 增加Permission系统 |
| 配置方式 | Markdown/JSON双模式 | 仅代码定义 | 支持配置化定义 |
| 模型选择 | 可独立指定模型 | 配置复杂 | 简化模型配置 |
| 步骤限制 | maxSteps控制迭代 | max_retry_count语义不清 | 重命名并优化 |

### 2. openclaw 最佳实践

| 维度 | openclaw 设计 | 当前系统问题 | 改进方向 |
|------|--------------|-------------|---------|
| 架构 | Gateway + Agent分离 | 混合设计 | 清晰分层 |
| Session | main/分组隔离 | 记忆管理复杂 | 简化Session模型 |
| Skills | 可扩展技能平台 | Action扩展困难 | 增加Skill系统 |
| 可视化 | Canvas实时协作 | Vis协议较重 | 简化可视化 |
| 沙箱 | 多模式Sandbox | 沙箱非核心 | 保留当前设计 |

### 3. 核心改进点

1. **简化Agent接口** - 参考opencode的简洁设计
2. **增加Permission系统** - 细粒度工具权限控制
3. **优化Agent类型** - Primary/Subagent分层
4. **简化Profile配置** - Markdown/JSON双模式支持
5. **优化执行循环** - 减少复杂度，提高可读性
6. **简化Memory系统** - 减少层次，提高效率
7. **增加Skill系统** - 可扩展能力模块

## 二、重构计划

### Phase 1: Agent核心重构

#### 1.1 新增AgentInfo配置模型
- [ ] 创建 `agent_info.py` - Agent配置数据模型
- [ ] 支持 Primary/Subagent 模式
- [ ] 支持 Permission 配置
- [ ] 支持独立模型配置

#### 1.2 重构Agent接口
- [ ] 简化 `agent.py` 抽象方法
- [ ] 保留核心方法: send, receive, generate_reply, thinking, act
- [ ] 移除冗余抽象方法

#### 1.3 新增Permission系统
- [ ] 创建 `permission.py` - 权限规则系统
- [ ] 支持 ask/allow/deny 三种动作
- [ ] 支持工具级别和命令级别权限

### Phase 2: Prompt系统重构

#### 2.1 简化Profile配置
- [ ] 重构 `profile/base.py`
- [ ] 支持 Markdown 前置配置
- [ ] 简化模板变量系统

#### 2.2 优化Prompt模板
- [ ] 减少模板复杂度
- [ ] 支持多语言模板
- [ ] 优化变量注入

### Phase 3: 执行循环优化

#### 3.1 简化generate_reply
- [ ] 减少代码复杂度
- [ ] 提取子方法
- [ ] 优化重试逻辑

#### 3.2 优化thinking方法
- [ ] 简化流式输出逻辑
- [ ] 提取LLM调用

### Phase 4: Memory系统简化

#### 4.1 简化记忆架构
- [ ] 保留核心GptsMemory
- [ ] 优化SessionMemory
- [ ] 减少存储层次

### Phase 5: Tool系统增强

#### 5.1 增加Skill系统
- [ ] 创建 Skill 基类
- [ ] 支持技能注册和发现

#### 5.2 优化工具权限
- [ ] 集成Permission系统
- [ ] 支持工具级别权限控制

### Phase 6: 测试验证

#### 6.1 单元测试
- [ ] Permission系统测试
- [ ] AgentInfo配置测试
- [ ] 执行流程测试

#### 6.2 集成测试
- [ ] 使用现有配置验证
- [ ] 端到端测试

## 三、数据兼容性保证

### 3.1 接口兼容
- 保留所有现有公共接口
- 新增接口使用新前缀
- 废弃接口添加@Deprecated

### 3.2 数据兼容
- AgentMessage格式不变
- GptsMemory格式不变
- 配置文件格式兼容

## 四、风险评估

| 风险 | 影响 | 缓解措施 |
|-----|-----|---------|
| 接口变更破坏兼容性 | 高 | 保留旧接口，添加废弃标记 |
| 执行逻辑变更影响结果 | 中 | 保持核心算法不变 |
| 配置格式变更 | 中 | 向后兼容解析 |

## 五、执行顺序

1. Phase 1.1 - AgentInfo配置模型 (低风险)
2. Phase 1.3 - Permission系统 (独立模块)
3. Phase 2.1 - Profile配置简化 (渐进式)
4. Phase 3.1 - 执行循环优化 (需测试)
5. Phase 4.1 - Memory简化 (需测试)
6. Phase 5 - Tool系统增强 (增量)
7. Phase 6 - 测试验证