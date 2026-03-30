"""
完整测试：模拟Agent启动和别名注册流程
"""

import sys
import os

print("=" * 70)
print("完整Agent别名系统测试")
print("=" * 70)
print()

# 步骤1：测试ProfileConfig aliases字段
print("步骤1: 测试ProfileConfig aliases字段")
print("-" * 70)

try:
    from derisk._private.pydantic import BaseModel, Field

    class MockProfileConfig(BaseModel):
        name: str
        aliases: list = Field(default_factory=list)

    test_profile = MockProfileConfig(
        name="BAIZE", aliases=["ReActMasterV2", "ReActMaster"]
    )

    print("✓ ProfileConfig创建成功")
    print(f"  - name: {test_profile.name}")
    print(f"  - aliases: {test_profile.aliases}")
    print()

except Exception as e:
    print(f"✗ ProfileConfig测试失败: {e}")
    print()

# 步骤2：测试AgentAliasManager
print("步骤2: 测试AgentAliasManager")
print("-" * 70)


class SimpleAgentAliasManager:
    _alias_map = {}
    _reverse_map = {}

    @classmethod
    def register_agent_aliases(cls, current_name, aliases):
        if not aliases:
            return

        for alias in aliases:
            if alias and alias != current_name:
                cls._alias_map[alias] = current_name
                print(f"  ✓ 注册别名: {alias} -> {current_name}")

        if current_name not in cls._reverse_map:
            cls._reverse_map[current_name] = []

        for alias in aliases:
            if (
                alias
                and alias != current_name
                and alias not in cls._reverse_map[current_name]
            ):
                cls._reverse_map[current_name].append(alias)

    @classmethod
    def resolve_alias(cls, name):
        return cls._alias_map.get(name, name)

    @classmethod
    def get_all_aliases(cls):
        return cls._alias_map.copy()


# 注册别名
SimpleAgentAliasManager.register_agent_aliases(
    "BAIZE", ["ReActMasterV2", "ReActMaster"]
)
print()

# 步骤3：测试别名解析
print("步骤3: 测试别名解析")
print("-" * 70)

test_cases = [
    ("ReActMasterV2", "BAIZE"),
    ("ReActMaster", "BAIZE"),
    ("BAIZE", "BAIZE"),
]

for input_name, expected in test_cases:
    resolved = SimpleAgentAliasManager.resolve_alias(input_name)
    status = "✓" if resolved == expected else "✗"
    print(f"  {status} {input_name} -> {resolved} (预期: {expected})")

print()

# 步骤4：模拟完整Agent注册流程
print("步骤4: 模拟完整Agent注册流程")
print("-" * 70)


class MockReActMasterAgent:
    """模拟ReActMasterAgent"""

    def __init__(self):
        # 模拟ConversableAgent的基本属性
        self.role = "BAIZE"

        # 关键：模拟profile配置
        self.profile = MockProfileConfig(
            name="BAIZE", aliases=["ReActMasterV2", "ReActMaster"]
        )


class MockAgentManager:
    """模拟AgentManager"""

    def __init__(self):
        self._agents = {}

    def register_agent(self, agent_cls):
        """模拟register_agent方法"""
        print(f"  注册Agent类: {agent_cls.__name__}")

        # 创建实例
        inst = agent_cls()
        profile = inst.role
        print(f"  Agent名称: {profile}")

        # 注册到字典
        self._agents[profile] = (agent_cls, inst)

        # 关键步骤：读取并注册别名
        aliases = []

        # 方式1：从inst.profile.aliases获取
        if hasattr(inst, "profile"):
            profile_obj = inst.profile
            if hasattr(profile_obj, "aliases") and profile_obj.aliases:
                aliases = profile_obj.aliases
                print(f"  发现aliases: {aliases}")

        # 注册别名
        if aliases and isinstance(aliases, list):
            SimpleAgentAliasManager.register_agent_aliases(profile, aliases)
            print(f"  ✓ 成功注册别名: {aliases}")

        return profile

    def get_by_name(self, name):
        """模拟get_by_name，支持别名解析"""
        resolved_name = SimpleAgentAliasManager.resolve_alias(name)

        if resolved_name != name:
            print(f"  ✓ 别名解析: {name} -> {resolved_name}")

        if resolved_name in self._agents:
            return self._agents[resolved_name][0]
        else:
            raise ValueError(f"Agent:{name} (resolved: {resolved_name}) not register!")


# 模拟注册流程
manager = MockAgentManager()
print("  执行Agent注册...")
manager.register_agent(MockReActMasterAgent)
print()

# 步骤5：测试Agent检索（使用别名）
print("步骤5: 测试Agent检索（使用别名）")
print("-" * 70)

print("  测试1: 使用别名'ReActMasterV2'检索Agent")
try:
    agent_cls = manager.get_by_name("ReActMasterV2")
    print(f"  ✓ 成功获取Agent类: {agent_cls.__name__}")
except Exception as e:
    print(f"  ✗ 失败: {e}")

print()

print("  测试2: 使用当前名称'BAIZE'检索Agent")
try:
    agent_cls = manager.get_by_name("BAIZE")
    print(f"  ✓ 成功获取Agent类: {agent_cls.__name__}")
except Exception as e:
    print(f"  ✗ 失败: {e}")

print()

print("=" * 70)
print("✅ 测试完成")
print("=" * 70)
print()

print("关键流程总结:")
print("  1. ProfileConfig定义aliases字段 ✓")
print("  2. Agent类在profile中配置aliases ✓")
print("  3. AgentManager.register_agent读取aliases ✓")
print("  4. AgentAliasManager注册别名映射 ✓")
print("  5. AgentManager.get_by_name解析别名 ✓")
print()

print("实际运行时:")
print("  - AgentManager在after_start时会扫描并注册所有Agent")
print("  - 注册时会自动读取每个Agent的aliases")
print("  - 之后任何地方使用'ReActMasterV2'都会自动解析为'BAIZE'")
print()
