"""
调试Agent别名注册流程
"""

print("=" * 70)
print("调试Agent别名注册")
print("=" * 70)


# 模拟简化版的ProfileConfig
class SimpleProfileConfig:
    def __init__(self, name, aliases=None):
        self.name = name
        self.aliases = aliases or []


# 模拟AgentAliasManager
class DebugAgentAliasManager:
    _alias_map = {}
    _reverse_map = {}

    @classmethod
    def register_agent_aliases(cls, current_name, aliases):
        print(f"  [DEBUG] 尝试注册别名: current_name={current_name}, aliases={aliases}")
        if not aliases:
            print(f"  [DEBUG] aliases为空，跳过注册")
            return

        for alias in aliases:
            if alias and alias != current_name:
                cls._alias_map[alias] = current_name
                print(f"  [DEBUG] ✓ 成功注册: {alias} -> {current_name}")

        if current_name not in cls._reverse_map:
            cls._reverse_map[current_name] = []

        for alias in aliases:
            if (
                alias
                and alias != current_name
                and alias not in cls._reverse_map[current_name]
            ):
                cls._reverse_map[current_name].append(alias)


# 模拟Agent类
class MockBAIZEAgent:
    def __init__(self):
        self.role = "BAIZE"
        # 关键：这里模拟ProfileConfig
        self.profile = SimpleProfileConfig(
            name="BAIZE", aliases=["ReActMasterV2", "ReActMaster"]
        )

    def __class__(self):
        return type("BAIZE", (), {})


print("\n1. 模拟register_agent流程:")
print("-" * 70)

agent_cls = MockBAIZEAgent
print(f"注册Agent类: {agent_cls.__name__}")

# 模拟AgentManager.register_agent的逻辑
inst = agent_cls()
profile = inst.role
print(f"  profile名称: {profile}")

# 关键步骤：检查是否有profile.aliases
if hasattr(inst, "profile"):
    print(f"  ✓ 有profile属性")
    if hasattr(inst.profile, "aliases"):
        aliases = inst.profile.aliases
        print(f"  ✓ profile.aliases存在: {aliases}")
        DebugAgentAliasManager.register_agent_aliases(profile, aliases)
    else:
        print(f"  ✗ profile.aliases不存在")
else:
    print(f"  ✗ 没有profile属性")

print("\n2. 检查别名注册结果:")
print("-" * 70)
print(f"所有别名映射: {DebugAgentAliasManager.get_all_aliases()}")
print(f"ReActMasterV2解析: {DebugAgentAliasManager.resolve_alias('ReActMasterV2')}")

print("\n" + "=" * 70)

# 现在检查真实的ProfileConfig定义
print("\n3. 检查真实ProfileConfig定义:")
print("-" * 70)

try:
    import sys

    sys.path.insert(0, "/Users/tuyang/GitHub/OpenDerisk/packages/derisk-core/src")

    # 只导入ProfileConfig，不导入整个agent模块
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "profile_base",
        "/Users/tuyang/GitHub/OpenDerisk/packages/derisk-core/src/derisk/agent/core/profile/base.py",
    )
    profile_module = importlib.util.module_from_spec(spec)

    # 先导入必要的依赖
    print("尝试导入ProfileConfig...")
    from derisk._private.pydantic import BaseModel, Field

    print("  ✓ pydantic导入成功")

    # 手动定义简化版ProfileConfig
    class TestProfileConfig(BaseModel):
        name: str = Field(default="TestAgent")
        aliases: list = Field(default_factory=list)

    test_profile = TestProfileConfig(
        name="BAIZE", aliases=["ReActMasterV2", "ReActMaster"]
    )
    print(f"  ✓ ProfileConfig创建成功")
    print(f"  - name: {test_profile.name}")
    print(f"  - aliases: {test_profile.aliases}")

except Exception as e:
    print(f"  ✗ 导入失败: {e}")

print("\n" + "=" * 70)
