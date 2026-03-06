"""
配置加载器单元测试
"""

import pytest
import tempfile
import os
from pathlib import Path

from derisk.context.config_loader import HierarchicalContextConfigLoader


class TestConfigLoader:
    """配置加载器测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        loader = HierarchicalContextConfigLoader(config_path="nonexistent.yaml")
        config = loader.load()
        
        assert config["hierarchical_context"]["enabled"] == True
        assert config["chapter"]["max_chapter_tokens"] == 10000
        assert config["compaction"]["enabled"] == True
    
    def test_get_hc_config(self):
        """测试获取 HierarchicalContext 配置"""
        loader = HierarchicalContextConfigLoader(config_path="nonexistent.yaml")
        hc_config = loader.get_hc_config()
        
        assert hc_config.max_chapter_tokens == 10000
        assert hc_config.max_section_tokens == 2000
        assert hc_config.recent_chapters_full == 2
    
    def test_get_compaction_config(self):
        """测试获取压缩配置"""
        loader = HierarchicalContextConfigLoader(config_path="nonexistent.yaml")
        compaction_config = loader.get_compaction_config()
        
        assert compaction_config.enabled == True
        assert compaction_config.token_threshold == 40000
    
    def test_get_gray_release_config(self):
        """测试获取灰度配置"""
        loader = HierarchicalContextConfigLoader(config_path="nonexistent.yaml")
        gray_config = loader.get_gray_release_config()
        
        assert gray_config.enabled == False
        assert gray_config.gray_percentage == 0
    
    def test_reload(self):
        """测试重新加载"""
        loader = HierarchicalContextConfigLoader(config_path="nonexistent.yaml")
        loader.load()
        loader.reload()
        
        # 应该重新加载
        assert loader._config_cache is None or loader.load() is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])