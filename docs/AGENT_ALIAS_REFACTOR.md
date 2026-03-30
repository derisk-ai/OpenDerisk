# Agent别名系统重构总结

## 重构动机

原方案需要单独维护 `AgentAliasConfig` 类和手动注册别名，配置分散，维护麻烦。

新方案将别名直接定义在 Agent 类中，AgentManager 自动收集，更加简洁优雅。

## 核心改动

### 1. ProfileConfig 添加 aliases 字段

**文件**: `packages/derisk-core/src/derisk/agent/core/profile/base.py`

```python
class ProfileConfig(BaseModel):
    name: str = Field(default="ConversableAgent")
    role: str = Field(default="ConvUser")
    # ... 其他字段 ...
    
    # 新增：别名配置
    aliases: List[str] = Field(
        default_factory=list, 
        description="Agent别名列表，用于历史数据兼容。例如：['ReActMasterV2', 'ReActMaster']"
    )
```

### 2. Agent 类中直接定义别名

**文件**: `packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py`

```python
class ReActMasterAgent(ConversableAgent):
    profile: ProfileConfig = Field(
        default_factory=lambda: ProfileConfig(
            name="BAIZE",
            role="BAIZE",
            goal="白泽Agent...",
            # 直接在这里定义别名
            aliases=["ReActMasterV2", "ReActMaster"],
        )
    )
```

### 3. AgentManager 自动收集别名

**文件**: `packages/derisk-core/src/derisk/agent/core/agent_manage.py`

```python
def register_agent(self, cls: Type[ConversableAgent], ignore_duplicate: bool = False) -> str:
    """Register an agent."""
    inst = cls()
    profile = inst.role
    # ... 注册逻辑 ...
    self._agents[profile] = (cls, inst)
    
    # 自动注册Agent别名（从profile.aliases获取）
    if hasattr(inst, 'profile') and hasattr(inst.profile, 'aliases'):
        aliases = inst.profile.aliases
        if aliases:
            AgentAliasManager.register_agent_aliases(profile, aliases)
            logger.info(f"[AgentManager] Auto-registered aliases for {profile}: {aliases}")
    
    return profile
```

### 4. 简化 agent_alias.py

只保留核心的别名管理逻辑，无需手动初始化：

```python
class AgentAliasManager:
    """Agent别名管理器（由AgentManager自动填充）"""
    
    _alias_map: Dict[str, str] = {}  # alias -> current_name
    _reverse_map: Dict[str, List[str]] = {}  # current_name -> [aliases]
    
    @classmethod
    def register_agent_aliases(cls, current_name: str, aliases: List[str]):
        """注册Agent的别名（由AgentManager自动调用）"""
        # ... 实现 ...
    
    @classmethod
    def resolve_alias(cls, name: str) -> str:
        """解析别名"""
        return cls._alias_map.get(name, name)

# 便捷函数
def resolve_agent_name(name: str) -> str:
    return AgentAliasManager.resolve_alias(name)
```

## 使用对比

### 旧方式（已废弃）

```python
# 需要单独维护别名配置文件
# 在 agent_alias.py 中：
def initialize_default_aliases():
    AgentAliasConfig.register_alias("ReActMasterV2", "BAIZE")
    AgentAliasConfig.register_alias("ReActMaster", "BAIZE")
```

### 新方式（推荐）

```python
# 直接在Agent类中定义
class ReActMasterAgent(ConversableAgent):
    profile: ProfileConfig = Field(
        default_factory=lambda: ProfileConfig(
            name="BAIZE",
            aliases=["ReActMasterV2", "ReActMaster"],  # 别名跟着Agent走
        )
    )
```

## 优势对比

| 特性 | 旧方案 | 新方案 |
|------|--------|--------|
| 配置位置 | 单独的 agent_alias.py | Agent 类内部 |
| 维护成本 | 需要手动同步 | 自动同步 |
| 代码内聚性 | 低（分散） | 高（集中） |
| 注册方式 | 手动调用 | 自动收集 |
| 可读性 | 需要查看多个文件 | 一目了然 |

## 迁移指南

如果需要为其他 Agent 添加别名：

```python
class YourAgent(ConversableAgent):
    profile: ProfileConfig = Field(
        default_factory=lambda: ProfileConfig(
            name="YourAgent",
            aliases=["OldName1", "OldName2"],  # 添加历史别名
        )
    )
```

就这么简单！AgentManager 会自动处理其余的事情。

## 测试验证

```bash
python test_simplified_alias.py
```

输出：
```
✓ ReActMasterV2 -> BAIZE
✓ ReActMaster -> BAIZE
✓ BAIZE -> BAIZE (非别名)
✓ UnknownAgent -> UnknownAgent (未知Agent)
```

## 总结

重构后的别名系统：
- ✅ 配置跟着 Agent 类走，更加内聚
- ✅ 无需手动维护别名注册代码
- ✅ AgentManager 自动收集别名
- ✅ 代码更简洁，维护更方便
- ✅ 符合"配置即代码"的设计原则

感谢你的建议，这是一个很好的改进！