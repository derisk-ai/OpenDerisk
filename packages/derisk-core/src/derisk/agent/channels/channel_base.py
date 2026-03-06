"""
Channel - 统一消息接口抽象

参考OpenClaw的多渠道架构设计
支持CLI、Web等多渠道消息推送和接收
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)


class ChannelType(str, Enum):
    """Channel类型"""

    CLI = "cli"  # 命令行
    WEB = "web"  # Web界面
    API = "api"  # API接口
    WEBSOCKET = "websocket"  # WebSocket
    TELEGRAM = "telegram"  # Telegram
    SLACK = "slack"  # Slack
    DISCORD = "discord"  # Discord


class ChannelConfig(BaseModel):
    """Channel配置"""

    name: str  # Channel名称
    type: ChannelType  # Channel类型
    enabled: bool = True  # 是否启用
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 元数据

    class Config:
        use_enum_values = True


class ChannelMessage(BaseModel):
    """Channel消息"""

    channel_type: ChannelType  # Channel类型
    session_id: str  # Session ID
    content: str  # 消息内容
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 元数据

    class Config:
        use_enum_values = True


class ChannelBase(ABC):
    """
    Channel抽象基类 - 参考OpenClaw Channel设计

    设计原则:
    1. 统一接口 - 所有Channel实现相同接口
    2. 异步优先 - 全异步消息处理
    3. 可扩展 - 容易添加新Channel类型

    示例:
        class MyChannel(ChannelBase):
            async def connect(self):
                # 连接逻辑
                pass

            async def send(self, message: str):
                # 发送逻辑
                pass
    """

    def __init__(self, config: ChannelConfig):
        self.config = config
        self._connected = False
        self._message_queue = asyncio.Queue()

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected

    @abstractmethod
    async def connect(self):
        """
        连接到Channel

        初始化Channel连接所需的资源
        """
        pass

    @abstractmethod
    async def disconnect(self):
        """
        断开Channel连接

        清理Channel连接的资源
        """
        pass

    @abstractmethod
    async def send(self, message: str, context: Optional[Dict[str, Any]] = None):
        """
        发送消息到Channel

        Args:
            message: 消息内容
            context: 上下文信息
        """
        pass

    @abstractmethod
    async def receive(self) -> AsyncIterator[ChannelMessage]:
        """
        从Channel接收消息

        Yields:
            ChannelMessage: 接收到的消息
        """
        pass

    async def typing_indicator(self, is_typing: bool):
        """
        显示打字指示器

        Args:
            is_typing: 是否正在输入
        """
        # 默认实现: 不做任何操作
        pass

    async def _enqueue_message(self, message: ChannelMessage):
        """将消息加入队列"""
        await self._message_queue.put(message)


class CLIChannel(ChannelBase):
    """
    CLI Channel - 命令行交互

    示例:
        config = ChannelConfig(name="cli", type=ChannelType.CLI)
        channel = CLIChannel(config)

        await channel.connect()
        await channel.send("你好！")

        async for message in channel.receive():
            print(f"收到: {message.content}")
    """

    async def connect(self):
        """连接CLI"""
        self._connected = True
        logger.info(f"[CLIChannel] 已连接")

    async def disconnect(self):
        """断开CLI"""
        self._connected = False
        logger.info(f"[CLIChannel] 已断开")

    async def send(self, message: str, context: Optional[Dict[str, Any]] = None):
        """
        发送消息到CLI

        Args:
            message: 消息内容
            context: 上下文信息
        """
        if not self._connected:
            return

        # 打印到标准输出
        print(f"\n[Agent]: {message}\n")

    async def receive(self) -> AsyncIterator[ChannelMessage]:
        """
        从CLI接收消息

        Yields:
            ChannelMessage: 用户输入的消息
        """
        if not self._connected:
            return

        while self._connected:
            try:
                # 异步读取用户输入
                user_input = await self._async_input()

                if user_input:
                    yield ChannelMessage(
                        channel_type=ChannelType.CLI,
                        session_id="cli-session",
                        content=user_input,
                    )
            except Exception as e:
                logger.error(f"[CLIChannel] 接收消息失败: {e}")
                break

    async def _async_input(self) -> str:
        """异步读取用户输入"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input, "[You]: ")

    async def typing_indicator(self, is_typing: bool):
        """显示打字指示器"""
        if is_typing:
            print("...", end="", flush=True)


class WebChannel(ChannelBase):
    """
    Web Channel - Web界面交互

    通过WebSocket与Web前端通信

    示例:
        config = ChannelConfig(
            name="web",
            type=ChannelType.WEB,
            metadata={"websocket_url": "ws://localhost:8765"}
        )
        channel = WebChannel(config)

        await channel.connect()
        await channel.send("你好！")
    """

    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self.websocket = None

    async def connect(self):
        """连接WebSocket"""
        try:
            import websockets

            ws_url = self.config.metadata.get("websocket_url", "ws://localhost:8765")
            self.websocket = await websockets.connect(ws_url)
            self._connected = True
            logger.info(f"[WebChannel] 已连接到 {ws_url}")

        except Exception as e:
            logger.error(f"[WebChannel] 连接失败: {e}")
            self._connected = False

    async def disconnect(self):
        """断开WebSocket"""
        if self.websocket:
            await self.websocket.close()
        self._connected = False
        logger.info(f"[WebChannel] 已断开")

    async def send(self, message: str, context: Optional[Dict[str, Any]] = None):
        """
        发送消息到Web

        Args:
            message: 消息内容
            context: 上下文信息
        """
        if not self._connected or not self.websocket:
            return

        try:
            import json

            data = {"type": "message", "content": message, "context": context or {}}

            await self.websocket.send(json.dumps(data))
            logger.debug(f"[WebChannel] 发送消息: {message[:50]}...")

        except Exception as e:
            logger.error(f"[WebChannel] 发送失败: {e}")

    async def receive(self) -> AsyncIterator[ChannelMessage]:
        """
        从Web接收消息

        Yields:
            ChannelMessage: 接收到的消息
        """
        if not self._connected or not self.websocket:
            return

        try:
            import json

            async for data in self.websocket:
                try:
                    message_data = json.loads(data)

                    yield ChannelMessage(
                        channel_type=ChannelType.WEB,
                        session_id=message_data.get("session_id", "web-session"),
                        content=message_data.get("content", ""),
                        metadata=message_data.get("metadata", {}),
                    )

                except Exception as e:
                    logger.error(f"[WebChannel] 解析消息失败: {e}")

        except Exception as e:
            logger.error(f"[WebChannel] 接收消息失败: {e}")

    async def typing_indicator(self, is_typing: bool):
        """发送打字指示器状态"""
        if not self._connected or not self.websocket:
            return

        try:
            import json

            data = {"type": "typing_indicator", "is_typing": is_typing}

            await self.websocket.send(json.dumps(data))

        except Exception as e:
            logger.error(f"[WebChannel] 发送打字指示器失败: {e}")


class APIChannel(ChannelBase):
    """
    API Channel - REST API交互

    通过HTTP API进行消息交互
    """

    async def connect(self):
        """连接API"""
        self._connected = True
        logger.info(f"[APIChannel] 已连接")

    async def disconnect(self):
        """断开API"""
        self._connected = False
        logger.info(f"[APIChannel] 已断开")

    async def send(self, message: str, context: Optional[Dict[str, Any]] = None):
        """发送消息（API模式下通常不主动发送）"""
        pass

    async def receive(self) -> AsyncIterator[ChannelMessage]:
        """API模式下通常通过enqueue_message从外部接收"""
        while self._connected:
            try:
                message = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
                yield message
            except asyncio.TimeoutError:
                continue

    def enqueue_api_message(
        self, session_id: str, content: str, metadata: Optional[Dict] = None
    ):
        """
        从API接收消息（外部调用）

        Args:
            session_id: Session ID
            content: 消息内容
            metadata: 元数据
        """
        message = ChannelMessage(
            channel_type=ChannelType.API,
            session_id=session_id,
            content=content,
            metadata=metadata or {},
        )
        asyncio.create_task(self._enqueue_message(message))


class ChannelManager:
    """
    Channel管理器 - 管理多个Channel实例

    示例:
        manager = ChannelManager()

        # 注册Channel
        manager.register("cli", CLIChannel(cli_config))
        manager.register("web", WebChannel(web_config))

        # 获取Channel
        channel = manager.get("cli")

        # 广播消息到所有Channel
        await manager.broadcast("大家好！")
    """

    def __init__(self):
        self._channels: Dict[str, ChannelBase] = {}

    def register(self, name: str, channel: ChannelBase):
        """
        注册Channel

        Args:
            name: Channel名称
            channel: Channel实例
        """
        self._channels[name] = channel
        logger.info(f"[ChannelManager] 注册Channel: {name} ({channel.config.type})")

    def unregister(self, name: str):
        """
        注销Channel

        Args:
            name: Channel名称
        """
        if name in self._channels:
            del self._channels[name]
            logger.info(f"[ChannelManager] 注销Channel: {name}")

    def get(self, name: str) -> Optional[ChannelBase]:
        """
        获取Channel

        Args:
            name: Channel名称

        Returns:
            Optional[ChannelBase]: Channel实例
        """
        return self._channels.get(name)

    def list_channels(self) -> Dict[str, ChannelConfig]:
        """列出所有Channel"""
        return {name: channel.config for name, channel in self._channels.items()}

    async def connect_all(self):
        """连接所有Channel"""
        for name, channel in self._channels.items():
            try:
                await channel.connect()
            except Exception as e:
                logger.error(f"[ChannelManager] 连接Channel {name} 失败: {e}")

    async def disconnect_all(self):
        """断开所有Channel"""
        for name, channel in self._channels.items():
            try:
                await channel.disconnect()
            except Exception as e:
                logger.error(f"[ChannelManager] 断开Channel {name} 失败: {e}")

    async def broadcast(self, message: str, context: Optional[Dict[str, Any]] = None):
        """
        广播消息到所有Channel

        Args:
            message: 消息内容
            context: 上下文信息
        """
        for name, channel in self._channels.items():
            try:
                if channel.is_connected:
                    await channel.send(message, context)
            except Exception as e:
                logger.error(f"[ChannelManager] 广播到Channel {name} 失败: {e}")

    async def send_to(
        self, channel_name: str, message: str, context: Optional[Dict[str, Any]] = None
    ):
        """
        发送消息到指定Channel

        Args:
            channel_name: Channel名称
            message: 消息内容
            context: 上下文信息
        """
        channel = self.get(channel_name)
        if channel and channel.is_connected:
            await channel.send(message, context)
        else:
            logger.warning(f"[ChannelManager] Channel {channel_name} 不存在或未连接")


# 全局Channel管理器
_channel_manager: Optional[ChannelManager] = None


def get_channel_manager() -> ChannelManager:
    """获取全局Channel管理器"""
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager()
    return _channel_manager


def init_channel_manager() -> ChannelManager:
    """初始化全局Channel管理器"""
    global _channel_manager
    _channel_manager = ChannelManager()
    return _channel_manager
