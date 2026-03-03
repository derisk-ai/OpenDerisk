"""
灰度控制器单元测试
"""

import pytest
from derisk.context.gray_release_controller import (
    GrayReleaseController,
    GrayReleaseConfig,
)


class TestGrayReleaseController:
    """灰度控制器测试"""
    
    def test_disabled_by_default(self):
        """测试默认禁用"""
        config = GrayReleaseConfig(enabled=False)
        controller = GrayReleaseController(config)
        
        result = controller.should_enable_hierarchical_context(
            user_id="user1",
            app_id="app1",
            conv_id="conv1",
        )
        
        assert result == False
    
    def test_user_whitelist(self):
        """测试用户白名单"""
        config = GrayReleaseConfig(
            enabled=True,
            user_whitelist=["user1", "user2"],
        )
        controller = GrayReleaseController(config)
        
        # 在白名单中
        result = controller.should_enable_hierarchical_context(user_id="user1")
        assert result == True
        
        # 不在白名单中
        result = controller.should_enable_hierarchical_context(user_id="user3")
        assert result == False
    
    def test_app_whitelist(self):
        """测试应用白名单"""
        config = GrayReleaseConfig(
            enabled=True,
            app_whitelist=["app1"],
        )
        controller = GrayReleaseController(config)
        
        result = controller.should_enable_hierarchical_context(app_id="app1")
        assert result == True
        
        result = controller.should_enable_hierarchical_context(app_id="app2")
        assert result == False
    
    def test_user_blacklist(self):
        """测试用户黑名单"""
        config = GrayReleaseConfig(
            enabled=True,
            gray_percentage=100,  # 全量开启
            user_blacklist=["blocked_user"],
        )
        controller = GrayReleaseController(config)
        
        # 在黑名单中
        result = controller.should_enable_hierarchical_context(user_id="blocked_user")
        assert result == False
        
        # 不在黑名单中
        result = controller.should_enable_hierarchical_context(user_id="normal_user")
        assert result == True
    
    def test_gray_percentage(self):
        """测试灰度百分比"""
        config = GrayReleaseConfig(
            enabled=True,
            gray_percentage=50,
        )
        controller = GrayReleaseController(config)
        
        # 同一个会话应该有确定性结果
        result1 = controller.should_enable_hierarchical_context(conv_id="conv1")
        result2 = controller.should_enable_hierarchical_context(conv_id="conv1")
        assert result1 == result2
    
    def test_update_config(self):
        """测试更新配置"""
        config = GrayReleaseConfig(enabled=False)
        controller = GrayReleaseController(config)
        
        assert controller.should_enable_hierarchical_context(user_id="user1") == False
        
        # 更新配置
        new_config = GrayReleaseConfig(
            enabled=True,
            user_whitelist=["user1"],
        )
        controller.update_config(new_config)
        
        assert controller.should_enable_hierarchical_context(user_id="user1") == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])