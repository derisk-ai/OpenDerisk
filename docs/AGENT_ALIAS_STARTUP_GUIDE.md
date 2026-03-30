# Agent别名系统 - 启动验证指南

## ✅ 实现完成

所有核心组件已正确实现：

1. ✅ **ProfileConfig.aliases字段** - 已添加
2. ✅ **ReActMasterAgent配置** - 已配置aliases
3. ✅ **AgentManager集成** - 自动读取并注册别名
4. ✅ **AgentChat集成** - 使用resolve_agent_name()

## 🚀 启动验证步骤

### 1. 重启应用

```bash
# 停止应用
# 启动应用
```

### 2. 观察启动日志

查找以下关键日志：

```
[INFO] register_agent:<class 'derisk.agent.expand.react_master_agent.react_master_agent.ReActMasterAgent'>
[INFO] [AgentManager] Auto-registered aliases for BAIZE: ['ReActMasterV2', 'ReActMaster']
```

**日志位置**: 通常是 `logs/derisk.log` 或控制台输出

### 3. 验证别名注册

使用调试命令检查别名是否注册成功：

```python
# 进入Python环境
python

# 导入并检查
from derisk.agent.core.agent_alias import AgentAliasManager
print(AgentAliasManager.get_all_aliases())
# 预期输出: {'ReActMasterV2': 'BAIZE', 'ReActMaster': 'BAIZE'}
```

### 4. 测试历史配置

**测试场景**: 使用包含`"agent": "ReActMasterV2"`的JSON配置

**预期结果**:
- ✅ Agent成功加载
- ✅ 日志显示: `[AgentManager.get_by_name] Resolved alias: ReActMasterV2 -> BAIZE`
- ✅ 无错误信息

## 📋 验证清单

- [ ] 应用成功启动
- [ ] 启动日志显示别名注册
- [ ] 使用历史配置测试成功
- [ ] Agent功能正常运行

## 🔍 故障排查

### 问题: 别名未注册

**症状**: 日志中没有 `[AgentManager] Auto-registered aliases`

**可能原因**:
1. ProfileConfig.aliases字段未正确添加
2. ReActMasterAgent未配置aliases
3. AgentManager.register_agent逻辑错误

**检查方法**:
```bash
# 检查ProfileConfig
grep -n "aliases:" packages/derisk-core/src/derisk/agent/core/profile/base.py

# 检查ReActMasterAgent
grep -n "aliases=" packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py

# 检查AgentManager
grep -n "Auto-registered aliases" packages/derisk-core/src/derisk/agent/core/agent_manage.py
```

### 问题: 别名解析失败

**症状**: 错误 `Agent:ReActMasterV2 (resolved: ReActMasterV2) not register!`

**可能原因**:
1. 别名未成功注册
2. AgentAliasManager未正确导入

**调试方法**:
```python
# 在agent_manage.py的get_by_name方法中添加调试日志
logger.info(f"[DEBUG] All aliases: {AgentAliasManager.get_all_aliases()}")
logger.info(f"[DEBUG] Resolving: {name} -> {resolved_name}")
```

### 问题: Agent未找到

**症状**: 即使解析成功，仍报错Agent未注册

**可能原因**:
1. Agent类本身未注册
2. Agent扫描路径问题

**检查方法**:
```python
# 检查已注册的Agent
from derisk.agent.core.agent_manage import get_agent_manager
manager = get_agent_manager()
print("已注册Agent:", manager.all_agents())
```

## 📝 日志示例

### 正常启动日志

```
2024-01-15 10:00:00 [INFO] register_agent:<class 'derisk.agent.expand.react_master_agent.react_master_agent.ReActMasterAgent'>
2024-01-15 10:00:00 [INFO] [AgentManager] Auto-registered aliases for BAIZE: ['ReActMasterV2', 'ReActMaster']
2024-01-15 10:00:00 [INFO] register_agent:<class 'derisk.agent.expand.other_agent.OtherAgent'>
...
```

### 正常使用日志

```
2024-01-15 10:05:00 [INFO] [AgentChat] Resolved agent alias: ReActMasterV2 -> BAIZE
2024-01-15 10:05:00 [INFO] [AgentManager.get_by_name] Resolved alias: ReActMasterV2 -> BAIZE
```

## 🎯 成功标志

当你看到以下情况，说明别名系统工作正常：

1. ✅ 启动日志显示别名注册
2. ✅ 使用ReActMasterV2能成功加载Agent
3. ✅ 无"Agent not register"错误
4. ✅ Agent功能正常运行

## 📚 相关文档

- `docs/AGENT_ALIAS_SYSTEM.md` - 使用说明
- `docs/AGENT_ALIAS_REFACTOR.md` - 重构说明
- `docs/AGENT_ALIAS_FIX_SUMMARY.md` - 问题排查总结

## 🆘 需要帮助?

如果问题仍未解决，请检查：

1. 所有修改的文件是否保存
2. 应用是否完全重启（不是热重载）
3. Python环境是否正确
4. 依赖包是否完整

或提供以下信息以获得帮助：
- 完整的错误日志
- 启动日志（前100行）
- `AgentAliasManager.get_all_aliases()` 的输出
- `get_agent_manager().all_agents()` 的输出