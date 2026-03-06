"""
配置加载器

支持从 YAML 文件加载配置
"""

from typing import Optional, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class HierarchicalContextConfigLoader:
    """分层上下文配置加载器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config/hierarchical_context_config.yaml"
        self._config_cache: Optional[Dict[str, Any]] = None
    
    def load(self) -> Dict[str, Any]:
        """加载配置"""
        if self._config_cache:
            return self._config_cache
        
        config_file = Path(self.config_path)
        if not config_file.exists():
            logger.warning(f"配置文件不存在: {self.config_path}, 使用默认配置")
            return self._get_default_config()
        
        try:
            import yaml
            with open(config_file, 'r', encoding='utf-8') as f:
                self._config_cache = yaml.safe_load(f)
            return self._config_cache
        except Exception as e:
            logger.warning(f"加载配置失败: {e}, 使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "hierarchical_context": {"enabled": True},
            "chapter": {
                "max_chapter_tokens": 10000,
                "max_section_tokens": 2000,
                "recent_chapters_full": 2,
                "middle_chapters_index": 3,
                "early_chapters_summary": 5,
            },
            "compaction": {
                "enabled": True,
                "strategy": "llm_summary",
                "trigger": {
                    "token_threshold": 40000,
                },
            },
            "worklog_conversion": {
                "enabled": True,
            },
            "gray_release": {
                "enabled": False,
                "gray_percentage": 0,
            },
        }
    
    def get_hc_config(self):
        """获取 HierarchicalContext 配置"""
        from derisk.agent.shared.hierarchical_context import HierarchicalContextConfig
        
        config = self.load()
        chapter_config = config.get("chapter", {})
        
        return HierarchicalContextConfig(
            max_chapter_tokens=chapter_config.get("max_chapter_tokens", 10000),
            max_section_tokens=chapter_config.get("max_section_tokens", 2000),
            recent_chapters_full=chapter_config.get("recent_chapters_full", 2),
            middle_chapters_index=chapter_config.get("middle_chapters_index", 3),
            early_chapters_summary=chapter_config.get("early_chapters_summary", 5),
        )
    
    def get_compaction_config(self):
        """获取压缩配置"""
        from derisk.agent.shared.hierarchical_context import (
            HierarchicalCompactionConfig,
            CompactionStrategy,
        )
        
        config = self.load()
        compaction_config = config.get("compaction", {})
        
        strategy_map = {
            "llm_summary": CompactionStrategy.LLM_SUMMARY,
            "rule_based": CompactionStrategy.RULE_BASED,
            "hybrid": CompactionStrategy.HYBRID,
        }
        
        strategy_str = compaction_config.get("strategy", "llm_summary")
        strategy = strategy_map.get(strategy_str, CompactionStrategy.LLM_SUMMARY)
        
        return HierarchicalCompactionConfig(
            enabled=compaction_config.get("enabled", True),
            strategy=strategy,
            token_threshold=compaction_config.get("trigger", {}).get("token_threshold", 40000),
        )
    
    def get_gray_release_config(self):
        """获取灰度配置"""
        from .gray_release_controller import GrayReleaseConfig
        
        config = self.load()
        gray_config = config.get("gray_release", {})
        
        return GrayReleaseConfig(
            enabled=gray_config.get("enabled", False),
            gray_percentage=gray_config.get("gray_percentage", 0),
            user_whitelist=gray_config.get("user_whitelist", []),
            app_whitelist=gray_config.get("app_whitelist", []),
            conv_whitelist=gray_config.get("conv_whitelist", []),
            user_blacklist=gray_config.get("user_blacklist", []),
            app_blacklist=gray_config.get("app_blacklist", []),
        )
    
    def reload(self) -> None:
        """重新加载配置"""
        self._config_cache = None
        self.load()
        logger.info("[ConfigLoader] 配置已重新加载")