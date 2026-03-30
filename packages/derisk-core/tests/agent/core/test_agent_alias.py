"""Agent Alias Configuration Test"""

import pytest
from derisk.agent.core.agent_alias import (
    AgentAliasConfig,
    AgentNameResolver,
    initialize_default_aliases,
)


def test_alias_registration():
    """测试别名注册"""
    AgentAliasConfig.clear_aliases()

    AgentAliasConfig.register_alias("ReActMasterV2", "BAIZE")
    AgentAliasConfig.register_alias("ReActMaster", "BAIZE")

    assert AgentAliasConfig.is_alias("ReActMasterV2")
    assert AgentAliasConfig.is_alias("ReActMaster")
    assert not AgentAliasConfig.is_alias("BAIZE")


def test_alias_resolution():
    """测试别名解析"""
    AgentAliasConfig.clear_aliases()

    AgentAliasConfig.register_alias("ReActMasterV2", "BAIZE")

    resolved = AgentAliasConfig.resolve_alias("ReActMasterV2")
    assert resolved == "BAIZE"

    resolved = AgentAliasConfig.resolve_alias("BAIZE")
    assert resolved == "BAIZE"

    resolved = AgentAliasConfig.resolve_alias("UnknownAgent")
    assert resolved == "UnknownAgent"


def test_reverse_lookup():
    """测试反向查询"""
    AgentAliasConfig.clear_aliases()

    AgentAliasConfig.register_alias("ReActMasterV2", "BAIZE")
    AgentAliasConfig.register_alias("ReActMaster", "BAIZE")

    aliases = AgentAliasConfig.get_aliases_for("BAIZE")
    assert "ReActMasterV2" in aliases
    assert "ReActMaster" in aliases
    assert len(aliases) == 2


def test_get_all_aliases():
    """测试获取所有别名"""
    AgentAliasConfig.clear_aliases()

    AgentAliasConfig.register_alias("ReActMasterV2", "BAIZE")
    AgentAliasConfig.register_alias("OldAgent", "NewAgent")

    all_aliases = AgentAliasConfig.get_all_aliases()
    assert all_aliases["ReActMasterV2"] == "BAIZE"
    assert all_aliases["OldAgent"] == "NewAgent"


def test_name_resolver():
    """测试名称解析器"""
    AgentAliasConfig.clear_aliases()

    AgentAliasConfig.register_alias("ReActMasterV2", "BAIZE")

    assert AgentNameResolver.resolve_agent_type("ReActMasterV2") == "BAIZE"
    assert AgentNameResolver.resolve_app_code("ReActMasterV2") == "BAIZE"
    assert AgentNameResolver.resolve_gpts_name("ReActMasterV2") == "BAIZE"
    assert AgentNameResolver.resolve_agent_name("ReActMasterV2") == "BAIZE"


def test_default_aliases():
    """测试默认别名初始化"""
    initialize_default_aliases()

    assert AgentAliasConfig.is_alias("ReActMasterV2")
    assert AgentAliasConfig.is_alias("ReActMaster")

    assert AgentAliasConfig.resolve_alias("ReActMasterV2") == "BAIZE"
    assert AgentAliasConfig.resolve_alias("ReActMaster") == "BAIZE"


def test_duplicate_alias_registration():
    """测试重复注册别名"""
    AgentAliasConfig.clear_aliases()

    AgentAliasConfig.register_alias("ReActMasterV2", "BAIZE")
    AgentAliasConfig.register_alias("ReActMasterV2", "BAIZE")

    aliases = AgentAliasConfig.get_aliases_for("BAIZE")
    assert len(aliases) == 1
    assert aliases[0] == "ReActMasterV2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
