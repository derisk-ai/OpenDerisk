import ssl

import aiohttp
import asyncio
from typing import Any, Dict, Optional, Union
import logging
from ssl import SSLContext

# 配置日志
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class AsyncRestClient:
    def __init__(
        self,
        base_url: str = None,
        max_connections: int = 100,
        timeout: int = 10,
        retries: int = 3,
        ssl_context: Optional[SSLContext] = None,
        default_headers: Optional[Dict[str, str]] = None,
    ):
        """
        异步 REST 客户端

        :param base_url: 基础 API 地址
        :param max_connections: 最大连接数
        :param timeout: 超时时间（秒）
        :param retries: 重试次数
        :param ssl_context: 自定义 SSL 配置
        :param default_headers: 默认请求头
        """
        if not ssl_context:
            # 创建不验证 SSL 的上下文
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        self.base_url = base_url.rstrip("/") if base_url else None
        self.connector = aiohttp.TCPConnector(limit=max_connections, ssl=ssl_context)
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.retries = retries
        self.session = None
        self.default_headers = default_headers or {}
        self.default_headers.setdefault("User-Agent", "AsyncRestClient/1.0")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def start(self):
        """初始化会话"""
        self.session = aiohttp.ClientSession(
            connector=self.connector, timeout=self.timeout, connector_owner=False
        )

    async def close(self):
        """关闭会话"""
        if self.session:
            await self.session.close()

    def _merge_headers(
        self, request_headers: Optional[Dict[str, str]]
    ) -> Dict[str, str]:
        """合并默认头和请求头"""
        merged = self.default_headers.copy()
        if request_headers:
            merged.update(request_headers)
        return merged

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        基础请求方法

        :param method: HTTP 方法 (GET/POST/PUT/DELETE)
        :param endpoint: API 端点
        :return: 响应数据 (自动解析 JSON)
        """
        if self.base_url:
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
        else:
            url = endpoint
        headers = self._merge_headers(kwargs.pop("headers", None))

        for attempt in range(self.retries + 1):
            try:
                logger.info(f"url:{url},headers:{headers},{kwargs}")
                async with self.session.request(
                    method=method, url=url, headers=headers, **kwargs
                ) as response:
                    response.raise_for_status()
                    try:
                        return await response.json()
                    except Exception as e:
                        logger.error(f"Error Response:{await response.text()},{str(e)}")
                        raise

            except Exception as e:
                if attempt >= self.retries:
                    logger.error(
                        f"Request failed after {self.retries} attempts: {str(e)}"
                    )
                    raise
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                await asyncio.sleep(2**attempt)  # 指数退避

    # 便捷方法（增加headers参数）
    async def get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict:
        return await self._request("GET", endpoint, params=params, headers=headers)

    async def post(
        self,
        endpoint: str,
        json: Optional[Union[Dict, str]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict:
        return await self._request("POST", endpoint, json=json, headers=headers)

    async def put(
        self, endpoint: str, data: Dict, headers: Optional[Dict[str, str]] = None
    ) -> Dict:
        return await self._request("PUT", endpoint, json=data, headers=headers)

    async def delete(
        self, endpoint: str, headers: Optional[Dict[str, str]] = None
    ) -> Dict:
        return await self._request("DELETE", endpoint, headers=headers)
