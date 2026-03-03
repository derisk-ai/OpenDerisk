"""
灰度发布控制器

支持多维度灰度发布
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass, field
import hashlib
import logging

logger = logging.getLogger(__name__)


@dataclass
class GrayReleaseConfig:
    """灰度发布配置"""
    
    enabled: bool = False
    gray_percentage: int = 0
    user_whitelist: list = field(default_factory=list)
    app_whitelist: list = field(default_factory=list)
    conv_whitelist: list = field(default_factory=list)
    user_blacklist: list = field(default_factory=list)
    app_blacklist: list = field(default_factory=list)


class GrayReleaseController:
    """灰度发布控制器"""
    
    def __init__(self, config: GrayReleaseConfig):
        self.config = config
    
    def should_enable_hierarchical_context(
        self,
        user_id: Optional[str] = None,
        app_id: Optional[str] = None,
        conv_id: Optional[str] = None,
    ) -> bool:
        """判断是否启用分层上下文"""
        
        if not self.config.enabled:
            return False
        
        # 1. 检查黑名单
        if user_id and user_id in self.config.user_blacklist:
            logger.debug(f"[GrayRelease] 用户 {user_id} 在黑名单中")
            return False
        if app_id and app_id in self.config.app_blacklist:
            logger.debug(f"[GrayRelease] 应用 {app_id} 在黑名单中")
            return False
        
        # 2. 检查白名单
        if user_id and user_id in self.config.user_whitelist:
            logger.info(f"[GrayRelease] 用户 {user_id} 在白名单中，启用")
            return True
        if app_id and app_id in self.config.app_whitelist:
            logger.info(f"[GrayRelease] 应用 {app_id} 在白名单中，启用")
            return True
        if conv_id and conv_id in self.config.conv_whitelist:
            logger.info(f"[GrayRelease] 会话 {conv_id[:8]} 在白名单中，启用")
            return True
        
        # 3. 流量百分比灰度
        if self.config.gray_percentage > 0:
            hash_key = conv_id or user_id or app_id or "default"
            hash_value = int(hashlib.md5(hash_key.encode()).hexdigest(), 16)
            if (hash_value % 100) < self.config.gray_percentage:
                logger.info(
                    f"[GrayRelease] 哈希灰度启用: {hash_key[:8]} "
                    f"({hash_value % 100} < {self.config.gray_percentage})"
                )
                return True
        
        return False
    
    def update_config(self, new_config: GrayReleaseConfig) -> None:
        """更新配置"""
        self.config = new_config
        logger.info(
            f"[GrayRelease] 配置已更新: "
            f"enabled={new_config.enabled}, "
            f"percentage={new_config.gray_percentage}%"
        )