"""
Agent别名系统使用说明

功能概述：
-----------
Agent别名系统用于处理Agent重命名后的历史数据兼容性问题。
当Agent名称从"ReActMasterV2"改为"BAIZE"后，历史数据和配置文件中
仍使用旧名称，别名系统确保这些旧名称能够正确匹配到新Agent。

核心组件：
-----------
1. AgentAliasConfig - 别名配置管理类
   - register_alias(old_name, current_name): 注册别名
   - resolve_alias(name): 解析别名，返回当前名称
   - get_aliases_for(current_name): 获取所有别名
   - is_alias(name): 判断是否为别名

2. AgentNameResolver - 名称解析器（便捷工具类）
   - resolve_agent_type(agent_type): 解析Agent类型
   - resolve_app_code(app_code): 解析应用代码
   - resolve_gpts_name(gpts_name): 解析gpts_name
   - resolve_agent_name(agent_name): 解析Agent名称

3. AgentManager - Agent管理器（已集成别名解析）
   - get_by_name(name): 支持别名解析
   - get_agent(name): 支持别名解析
   - get_describe_by_name(name): 支持别名解析

默认别名映射：
--------------
系统启动时自动初始化以下别名：
- ReActMasterV2 -> BAIZE
- ReActMaster -> BAIZE

使用示例：
-----------

1. 注册新别名：
   ```python
   from derisk.agent.core.agent_alias import AgentAliasConfig
   
   AgentAliasConfig.register_alias("OldAgentName", "NewAgentName")
   ```

2. 解析别名：
   ```python
   from derisk.agent.core.agent_alias import AgentAliasConfig
   
   # 直接使用
   resolved_name = AgentAliasConfig.resolve_alias("ReActMasterV2")
   print(resolved_name)  # 输出: BAIZE
   
   # 或使用便捷工具
   from derisk.agent.core.agent_alias import AgentNameResolver
   
   resolved_name = AgentNameResolver.resolve_agent_type("ReActMasterV2")
   print(resolved_name)  # 输出: BAIZE
   ```

3. 反向查询别名：
   ```python
   from derisk.agent.core.agent_alias import AgentAliasConfig
   
   aliases = AgentAliasConfig.get_aliases_for("BAIZE")
   print(aliases)  # 输出: ['ReActMasterV2', 'ReActMaster']
   ```

4. 在Agent管理器中使用：
   ```python
   from derisk.agent.core.agent_manage import get_agent_manager
   
   agent_manager = get_agent_manager()
   
   # 自动支持别名解析
   agent_cls = agent_manager.get_by_name("ReActMasterV2")  # 会返回BAIZE Agent类
   agent_instance = agent_manager.get_agent("ReActMasterV2")  # 会返回BAIZE Agent实例
   ```

5. 在配置文件中使用：
   历史配置文件中的旧名称会自动解析：
   ```json
   {
     "agent": "ReActMasterV2",  // 自动解析为 BAIZE
     "team_context": {
       "teamleader": "ReActMasterV2"  // 自动解析为 BAIZE
     }
   }
   ```

集成点：
-----------
别名系统已集成到以下关键位置：
1. AgentManager - Agent类检索
2. AgentChat - Agent实例构建
3. AgentInfo - Agent配置管理
4. 历史数据匹配 - gpts_name、app_code解析

日志追踪：
-----------
别名解析会记录日志，方便排查：
- [AgentAlias] Resolved alias: OldName -> NewName
- [AgentManager] Resolved alias: OldName -> NewName
- [AgentChat] Resolved agent alias: OldName -> NewName

扩展别名：
-----------
如需添加更多别名，有两种方式：

方式1: 在代码中直接注册（推荐）
```python
from derisk.agent.core.agent_alias import AgentAliasConfig

AgentAliasConfig.register_alias("OldName", "NewName")
```

方式2: 修改agent_alias.py的initialize_default_aliases函数
```python
def initialize_default_aliases():
    AgentAliasConfig.register_alias("ReActMasterV2", "BAIZE")
    AgentAliasConfig.register_alias("ReActMaster", "BAIZE")
    # 添加新的别名映射
    AgentAliasConfig.register_alias("OldPDCAAgent", "NewPDCAAgent")
```

注意事项：
-----------
1. 别名注册应在系统启动早期完成
2. 别名映射是全局的，建议集中管理
3. 解析失败时返回原名称，不影响正常流程
4. 支持多对一映射（多个旧名称指向同一个新名称）
5. 不支持一对多映射（一个旧名称指向多个新名称）

测试验证：
-----------
运行测试验证别名系统：
```bash
cd packages/derisk-core
python -m pytest tests/test_agent_alias.py -v
```

或者手动测试：
```python
from derisk.agent.core.agent_alias import AgentAliasConfig

# 测试别名解析
print(AgentAliasConfig.resolve_alias("ReActMasterV2"))  # 应返回 "BAIZE"
print(AgentAliasConfig.resolve_alias("BAIZE"))  # 应返回 "BAIZE"
print(AgentAliasConfig.resolve_alias("UnknownAgent"))  # 应返回 "UnknownAgent"

# 测试反向查询
print(AgentAliasConfig.get_aliases_for("BAIZE"))  # 应返回 ['ReActMasterV2', 'ReActMaster']
```

常见问题：
-----------

Q: 如果同时存在旧Agent和新Agent怎么办？
A: 别名系统只处理名称解析，不会创建Agent实例。如果旧Agent类仍存在，
   可以选择不注册别名，或者注册别名指向新Agent。

Q: 别名会影响Agent的实际名称吗？
A: 不会。别名只在匹配阶段使用，Agent的实际profile.name保持不变。

Q: 如何查看当前所有的别名？
A: 使用 AgentAliasConfig.get_all_aliases() 查看所有别名映射。

Q: 别名可以动态修改吗？
A: 可以，但建议在系统启动时确定，避免运行时修改导致不一致。
```