"""
简单的Agent别名系统验证脚本（无外部依赖）
"""


# 模拟AgentAliasConfig和AgentNameResolver
class AgentAliasConfig:
    _alias_map = {}
    _reverse_map = {}

    @classmethod
    def register_alias(cls, old_name, current_name):
        cls._alias_map[old_name] = current_name

        if current_name not in cls._reverse_map:
            cls._reverse_map[current_name] = []
        if old_name not in cls._reverse_map[current_name]:
            cls._reverse_map[current_name].append(old_name)

    @classmethod
    def resolve_alias(cls, name):
        return cls._alias_map.get(name, name)

    @classmethod
    def get_aliases_for(cls, current_name):
        return cls._reverse_map.get(current_name, [])

    @classmethod
    def is_alias(cls, name):
        return name in cls._alias_map

    @classmethod
    def get_all_aliases(cls):
        return cls._alias_map.copy()


# 初始化默认别名
AgentAliasConfig.register_alias("ReActMasterV2", "BAIZE")
AgentAliasConfig.register_alias("ReActMaster", "BAIZE")


print("=" * 60)
print("Agent别名系统验证测试")
print("=" * 60)
print()

print("1. 测试别名解析:")
print("-" * 60)
print(f"   ReActMasterV2 -> {AgentAliasConfig.resolve_alias('ReActMasterV2')}")
print(f"   ReActMaster -> {AgentAliasConfig.resolve_alias('ReActMaster')}")
print(f"   BAIZE -> {AgentAliasConfig.resolve_alias('BAIZE')}")
print(f"   UnknownAgent -> {AgentAliasConfig.resolve_alias('UnknownAgent')}")
print()

print("2. 测试反向查询:")
print("-" * 60)
aliases = AgentAliasConfig.get_aliases_for("BAIZE")
print(f"   BAIZE 的所有别名: {aliases}")
print()

print("3. 测试别名判断:")
print("-" * 60)
print(f"   ReActMasterV2 是别名吗? {AgentAliasConfig.is_alias('ReActMasterV2')}")
print(f"   BAIZE 是别名吗? {AgentAliasConfig.is_alias('BAIZE')}")
print()

print("4. 所有别名映射:")
print("-" * 60)
for old, new in AgentAliasConfig.get_all_aliases().items():
    print(f"   {old} -> {new}")
print()

print("5. 测试场景模拟:")
print("-" * 60)

# 模拟从JSON配置读取agent类型
config_agent_type = "ReActMasterV2"
resolved_type = AgentAliasConfig.resolve_alias(config_agent_type)
print(f"   配置文件中的agent类型: {config_agent_type}")
print(f"   解析后的类型: {resolved_type}")
print()

# 模拟从历史数据读取gpts_name
historical_gpts_name = "ReActMasterV2"
resolved_name = AgentAliasConfig.resolve_alias(historical_gpts_name)
print(f"   历史数据中的gpts_name: {historical_gpts_name}")
print(f"   解析后的名称: {resolved_name}")
print()

print("=" * 60)
print("✅ Agent别名系统验证完成")
print("=" * 60)
print()
print("说明:")
print("- 历史数据中的 'ReActMasterV2' 会自动解析为 'BAIZE'")
print("- 历史数据中的 'ReActMaster' 会自动解析为 'BAIZE'")
print("- 如果名称不是别名，则原样返回")
print("- 别名系统确保历史数据与新Agent名称的兼容性")
print()
