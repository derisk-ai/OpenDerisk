"""
Watchdog Management - 沙箱看门狗管理

提供沙箱生命周期的自动管理功能：
- 监控沙箱剩余时间
- 自动延长沙箱存活时间
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_CHECK_INTERVAL = 60  # 检查间隔（秒）
DEFAULT_EXTEND_THRESHOLD = 300  # 延长阈值（秒），剩余时间少于此值时延长
DEFAULT_EXTEND_MINUTES = 10  # 默认延长时间（分钟）


@dataclass
class WatchdogStatus:
    """看门狗状态"""

    remaining_time_ms: int  # 剩余时间（毫秒）
    user_id: Optional[str] = None
    pod_name: Optional[str] = None
    create_time: Optional[str] = None

    @property
    def remaining_time_seconds(self) -> float:
        """剩余时间（秒）"""
        return self.remaining_time_ms / 1000

    @property
    def remaining_time_minutes(self) -> float:
        """剩余时间（分钟）"""
        return self.remaining_time_ms / 1000 / 60


class WatchdogError(Exception):
    """看门狗操作错误"""

    pass


class WatchdogClient:
    """
    看门狗客户端

    用于调用 xic 沙箱的看门狗 API：
    - feedWatchdog: 延长容器存活时间
    - getWatchdogRemainingTime: 获取剩余时间
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        api_key: Optional[str] = None,
    ):
        """
        初始化看门狗客户端

        Args:
            base_url: API 基础 URL（如 http://api.example.com）
            timeout: 请求超时时间（秒）
            api_key: API 密钥（可选）
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key

        # HTTP 客户端配置
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers=headers,
        )

    async def close(self) -> None:
        """关闭客户端"""
        await self._client.aclose()

    async def get_remaining_time(self, instance_id: str) -> WatchdogStatus:
        """
        获取沙箱剩余时间

        Args:
            instance_id: 云实例 ID

        Returns:
            WatchdogStatus: 看门狗状态

        Raises:
            WatchdogError: 获取失败时抛出
        """
        url = "/api/v1/computer-tools/watchdogRemainingTime"
        params = {"instanceId": instance_id}

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            return WatchdogStatus(
                remaining_time_ms=data.get("RemainingTime", 0),
                user_id=data.get("UserId"),
                pod_name=data.get("podName"),
                create_time=data.get("createTime"),
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                f"[WatchdogClient] get_remaining_time failed: {e.response.status_code} - {e.response.text}"
            )
            raise WatchdogError(f"获取剩余时间失败: HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"[WatchdogClient] get_remaining_time request error: {e}")
            raise WatchdogError(f"请求失败: {str(e)}")
        except Exception as e:
            logger.error(f"[WatchdogClient] get_remaining_time error: {e}")
            raise WatchdogError(f"获取剩余时间失败: {str(e)}")

    async def feed_watchdog(
        self,
        instance_id: str,
        instance_timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        延长沙箱存活时间

        Args:
            instance_id: 云实例 ID
            instance_timeout: 实例有效时间（分钟），不传则使用申请时设置的时间

        Returns:
            Dict: API 响应

        Raises:
            WatchdogError: 延长失败时抛出
        """
        url = "/api/v1/computer-tools/feedWatchdog"
        payload: Dict[str, Any] = {"instanceId": instance_id}

        if instance_timeout is not None:
            payload["instanceTimeout"] = instance_timeout

        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()

            data = response.json()
            logger.info(
                f"[WatchdogClient] feed_watchdog success: instance_id={instance_id}, "
                f"timeout={instance_timeout or 'default'} minutes"
            )
            return data

        except httpx.HTTPStatusError as e:
            logger.error(
                f"[WatchdogClient] feed_watchdog failed: {e.response.status_code} - {e.response.text}"
            )
            raise WatchdogError(f"延长存活时间失败: HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"[WatchdogClient] feed_watchdog request error: {e}")
            raise WatchdogError(f"请求失败: {str(e)}")
        except Exception as e:
            logger.error(f"[WatchdogClient] feed_watchdog error: {e}")
            raise WatchdogError(f"延长存活时间失败: {str(e)}")


class WatchdogManager:
    """
    看门狗管理器

    自动管理沙箱生命周期：
    - 定期检查沙箱剩余时间
    - 当剩余时间不足时自动延长
    """

    def __init__(
        self,
        client: WatchdogClient,
        check_interval: int = DEFAULT_CHECK_INTERVAL,
        extend_threshold: int = DEFAULT_EXTEND_THRESHOLD,
        extend_minutes: int = DEFAULT_EXTEND_MINUTES,
    ):
        """
        初始化看门狗管理器

        Args:
            client: 看门狗客户端
            check_interval: 检查间隔（秒）
            extend_threshold: 延长阈值（秒），剩余时间少于此值时延长
            extend_minutes: 延长时间（分钟）
        """
        self.client = client
        self.check_interval = check_interval
        self.extend_threshold = extend_threshold
        self.extend_minutes = extend_minutes

        # 监控任务
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

        # 注册的沙箱实例
        self._instances: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        instance_id: str,
        on_expire: Optional[Callable] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        注册沙箱实例进行监控

        Args:
            instance_id: 云实例 ID
            on_expire: 过期回调函数（可选）
            metadata: 元数据（可选）
        """
        self._instances[instance_id] = {
            "registered_at": datetime.now(),
            "on_expire": on_expire,
            "metadata": metadata or {},
            "last_check": None,
            "last_extend": None,
            "extend_count": 0,
        }
        logger.info(f"[WatchdogManager] Registered instance: {instance_id}")

    def unregister(self, instance_id: str) -> None:
        """
        取消注册沙箱实例

        Args:
            instance_id: 云实例 ID
        """
        self._instances.pop(instance_id, None)
        logger.info(f"[WatchdogManager] Unregistered instance: {instance_id}")

    async def start(self) -> None:
        """启动看门狗监控"""
        if self._running:
            logger.warning("[WatchdogManager] Already running")
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("[WatchdogManager] Started")

    async def stop(self) -> None:
        """停止看门狗监控"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        logger.info("[WatchdogManager] Stopped")

    async def _monitor_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                await self._check_all_instances()
            except Exception as e:
                logger.error(f"[WatchdogManager] Monitor loop error: {e}")

            await asyncio.sleep(self.check_interval)

    async def _check_all_instances(self) -> None:
        """检查所有注册的实例"""
        for instance_id in list(self._instances.keys()):
            try:
                await self._check_instance(instance_id)
            except WatchdogError as e:
                logger.warning(
                    f"[WatchdogManager] Failed to check instance {instance_id}: {e}"
                )
            except Exception as e:
                logger.error(
                    f"[WatchdogManager] Unexpected error for instance {instance_id}: {e}"
                )

    async def _check_instance(self, instance_id: str) -> None:
        """
        检查单个实例

        Args:
            instance_id: 云实例 ID
        """
        instance_info = self._instances.get(instance_id)
        if not instance_info:
            return

        # 获取剩余时间
        status = await self.client.get_remaining_time(instance_id)
        instance_info["last_check"] = datetime.now()

        remaining_seconds = status.remaining_time_seconds
        logger.debug(
            f"[WatchdogManager] Instance {instance_id} remaining time: "
            f"{remaining_seconds:.1f}s ({remaining_seconds / 60:.1f}m)"
        )

        # 检查是否需要延长
        if remaining_seconds <= self.extend_threshold:
            logger.info(
                f"[WatchdogManager] Instance {instance_id} remaining time "
                f"{remaining_seconds:.1f}s <= threshold {self.extend_threshold}s, "
                f"extending by {self.extend_minutes} minutes"
            )

            # 延长存活时间
            await self.client.feed_watchdog(
                instance_id=instance_id,
                instance_timeout=self.extend_minutes,
            )

            instance_info["last_extend"] = datetime.now()
            instance_info["extend_count"] += 1

            logger.info(
                f"[WatchdogManager] Instance {instance_id} extended successfully "
                f"(total extends: {instance_info['extend_count']})"
            )

    async def check_now(self, instance_id: Optional[str] = None) -> Dict[str, Any]:
        """
        立即检查指定实例或所有实例

        Args:
            instance_id: 云实例 ID，为 None 时检查所有实例

        Returns:
            Dict: 检查结果
        """
        if instance_id:
            await self._check_instance(instance_id)
            status = await self.client.get_remaining_time(instance_id)
            return {
                instance_id: {
                    "remaining_time_seconds": status.remaining_time_seconds,
                    "remaining_time_minutes": status.remaining_time_minutes,
                }
            }
        else:
            await self._check_all_instances()
            return {
                iid: {
                    "remaining_time_seconds": (
                        await self.client.get_remaining_time(iid)
                    ).remaining_time_seconds,
                    "extend_count": info.get("extend_count", 0),
                }
                for iid, info in self._instances.items()
            }

    def get_status(self) -> Dict[str, Any]:
        """
        获取看门狗管理器状态

        Returns:
            Dict: 状态信息
        """
        return {
            "running": self._running,
            "check_interval": self.check_interval,
            "extend_threshold": self.extend_threshold,
            "extend_minutes": self.extend_minutes,
            "registered_instances": list(self._instances.keys()),
            "instance_details": {
                iid: {
                    "registered_at": info["registered_at"].isoformat(),
                    "last_check": (
                        info["last_check"].isoformat() if info["last_check"] else None
                    ),
                    "last_extend": (
                        info["last_extend"].isoformat() if info["last_extend"] else None
                    ),
                    "extend_count": info["extend_count"],
                }
                for iid, info in self._instances.items()
            },
        }


# 全局看门狗管理器实例（延迟初始化）
_global_watchdog_manager: Optional[WatchdogManager] = None


def get_watchdog_manager() -> Optional[WatchdogManager]:
    """获取全局看门狗管理器"""
    return _global_watchdog_manager


async def initialize_watchdog_manager(
    base_url: str,
    api_key: Optional[str] = None,
    check_interval: int = DEFAULT_CHECK_INTERVAL,
    extend_threshold: int = DEFAULT_EXTEND_THRESHOLD,
    extend_minutes: int = DEFAULT_EXTEND_MINUTES,
    auto_start: bool = True,
) -> WatchdogManager:
    """
    初始化全局看门狗管理器

    Args:
        base_url: API 基础 URL
        api_key: API 密钥（可选）
        check_interval: 检查间隔（秒）
        extend_threshold: 延长阈值（秒）
        extend_minutes: 延长时间（分钟）
        auto_start: 是否自动启动

    Returns:
        WatchdogManager: 看门狗管理器实例
    """
    global _global_watchdog_manager

    client = WatchdogClient(base_url=base_url, api_key=api_key)
    manager = WatchdogManager(
        client=client,
        check_interval=check_interval,
        extend_threshold=extend_threshold,
        extend_minutes=extend_minutes,
    )

    _global_watchdog_manager = manager

    if auto_start:
        await manager.start()

    logger.info("[WatchdogManager] Global instance initialized")
    return manager


async def shutdown_watchdog_manager() -> None:
    """关闭全局看门狗管理器"""
    global _global_watchdog_manager

    if _global_watchdog_manager:
        await _global_watchdog_manager.stop()
        await _global_watchdog_manager.client.close()
        _global_watchdog_manager = None
        logger.info("[WatchdogManager] Global instance shut down")
