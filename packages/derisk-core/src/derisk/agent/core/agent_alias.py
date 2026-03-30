"""
Agent别名系统（简化版）

别名定义在Agent的ProfileConfig.aliases中，AgentManager自动收集和管理。
"""

from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class AgentAliasManager:
    """
    Agent别名管理器（由AgentManager自动填充）

    别名数据来源：Agent的profile.aliases字段
    无需手动注册，AgentManager会在注册Agent时自动收集。
    """

    _alias_map: Dict[str, str] = {}  # alias -> current_name
    _reverse_map: Dict[str, List[str]] = {}  # current_name -> [aliases]

    @classmethod
    def register_agent_aliases(cls, current_name: str, aliases: List[str]):
        """
        注册Agent的别名（由AgentManager自动调用）

        Args:
            current_name: Agent当前名称
            aliases: 别名列表
        """
        if not aliases:
            return

        for alias in aliases:
            if alias and alias != current_name:
                cls._alias_map[alias] = current_name
                logger.debug(f"[AgentAlias] Registered: {alias} -> {current_name}")

        # 更新反向映射
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
    def resolve_alias(cls, name: str) -> str:
        """
        解析别名，返回当前名称

        Args:
            name: Agent名称（可能是别名）

        Returns:
            str: 解析后的当前名称
        """
        resolved = cls._alias_map.get(name, name)
        if resolved != name:
            logger.debug(f"[AgentAlias] Resolved: {name} -> {resolved}")
        return resolved

    @classmethod
    def get_aliases_for(cls, current_name: str) -> List[str]:
        """获取Agent的所有别名"""
        return cls._reverse_map.get(current_name, [])

    @classmethod
    def is_alias(cls, name: str) -> bool:
        """判断是否为别名"""
        return name in cls._alias_map

    @classmethod
    def get_all_aliases(cls) -> Dict[str, str]:
        """获取所有别名映射"""
        return cls._alias_map.copy()

    @classmethod
    def clear(cls):
        """清空所有别名（用于测试）"""
        cls._alias_map.clear()
        cls._reverse_map.clear()


# 便捷函数
def resolve_agent_name(name: str) -> str:
    """解析Agent名称（便捷函数）"""
    return AgentAliasManager.resolve_alias(name)
