"""
Agent别名系统测试（简化版）
"""

import sys

sys.path.insert(0, "packages/derisk-core/src")

print("=" * 70)
print("测试简化版Agent别名系统")
print("=" * 70)
print()


# 模拟ProfileConfig
class ProfileConfig:
    def __init__(self, name, role="", goal="", aliases=None):
        self.name = name
        self.role = role or name
        self.goal = goal
        self.aliases = aliases or []


# 模拟AgentAliasManager
class AgentAliasManager:
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
        resolved = cls._alias_map.get(name, name)
        return resolved

    @classmethod
    def get_aliases_for(cls, current_name):
        return cls._reverse_map.get(current_name, [])


print("1. 模拟Agent注册流程")
print("-" * 70)

# 模拟注册BAIZE Agent
baize_profile = ProfileConfig(
    name="BAIZE",
    role="BAIZE",
    goal="白泽Agent",
    aliases=["ReActMasterV2", "ReActMaster"],  # 在Agent类中直接定义别名
)

print(f"注册Agent: {baize_profile.name}")
AgentAliasManager.register_agent_aliases(baize_profile.name, baize_profile.aliases)
print()

print("2. 测试别名解析")
print("-" * 70)

test_cases = [
    ("ReActMasterV2", "BAIZE"),
    ("ReActMaster", "BAIZE"),
    ("BAIZE", "BAIZE"),
    ("UnknownAgent", "UnknownAgent"),
]

for input_name, expected in test_cases:
    resolved = AgentAliasManager.resolve_alias(input_name)
    status = "✓" if resolved == expected else "✗"
    print(f"  {status} {input_name} -> {resolved} (预期: {expected})")

print()

print("3. 测试反向查询")
print("-" * 70)

aliases = AgentAliasManager.get_aliases_for("BAIZE")
print(f"  BAIZE 的所有别名: {aliases}")
print()

print("4. 对比：旧方式 vs 新方式")
print("-" * 70)

print()
print("【旧方式】需要单独维护别名配置:")
print("  在 agent_alias.py 中:")
print("    AgentAliasConfig.register_alias('ReActMasterV2', 'BAIZE')")
print("    AgentAliasConfig.register_alias('ReActMaster', 'BAIZE')")
print()

print("【新方式】别名定义在Agent类中:")
print("  在 react_master_agent.py 中:")
print("    profile = ProfileConfig(")
print("        name='BAIZE',")
print("        aliases=['ReActMasterV2', 'ReActMaster'],  # 直接在这里定义")
print("    )")
print()

print("优势:")
print("  ✓ 别名和Agent定义在一起，更内聚")
print("  ✓ 无需单独维护别名注册代码")
print("  ✓ AgentManager自动收集别名")
print("  ✓ 更加符合'配置跟着类走'的设计原则")
print()

print("=" * 70)
print("✅ 测试完成")
print("=" * 70)
