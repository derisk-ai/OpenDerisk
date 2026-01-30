import gzip
import json
import logging
import struct
from httpcore import (
    ConnectionPool,
    AsyncConnectionPool,
    RemoteProtocolError,
    Response,
)
from enum import Flag, Enum
from typing import Callable, Optional, Dict, Any, Generator, Tuple, Union
from httpcore import URL


logger = logging.getLogger(__name__)
class EnvelopeFlags(Flag):
    compressed = 0b00000001
    end_stream = 0b00000010


class HTTPException(Exception):
    """通用HTTP异常类"""

    def __init__(self, status_code: int, content: bytes, message: str = ""):
        self.status_code = status_code
        self.content = content
        self.message = message or f"HTTP请求失败，状态码: {status_code}"
        super().__init__(self.message)


class GzipCompressor:
    """Gzip压缩处理器"""
    name = "gzip"

    @staticmethod
    def decompress(data: bytes) -> bytes:
        return gzip.decompress(data)

    @staticmethod
    def compress(data: bytes) -> bytes:
        return gzip.compress(data)


class BaseClient:
    """通用HTTP客户端基类"""

    def __init__(
        self,
        *,
        pool: Union[ConnectionPool, AsyncConnectionPool],
        base_url: str,
        compressor: Optional[Any] = None,
        default_headers: Optional[Dict[str, str]] = None,
        timeout: Optional[Dict[str, float]] = None,
        connection_retries: int = 3,
    ):
        self.pool = pool
        self.base_url = base_url
        self.compressor = compressor
        self.default_headers = default_headers or {}
        self.timeout = timeout
        self.connection_retries = connection_retries



    def gen_default_headers(self)->Optional[Dict[str, str]]:
        return self.default_headers

    def _prepare_request(
        self,
        method: str,
        path: str,
        data: Optional[bytes] = None,
        request_timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """准备请求参数"""
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        final_headers = {**self.default_headers, **(headers or {})}

        # 处理数据压缩
        content = data
        if content and self.compressor:
            content = self.compressor.compress(content)
            final_headers["Content-Encoding"] = self.compressor.name

        # 设置超时
        extensions = None
        if self.timeout:
            extensions = {
                "timeout": self.timeout
            }
        if request_timeout is not None:
            if extensions and extensions.get('timeout'):
                extensions['timeout']['read'] = request_timeout

        return {
            "method": method,
            "url": url,
            "content": content,
            "headers": final_headers,
            "extensions": extensions,
            **kwargs
        }

    def _process_response(
        self,
        response: Response,
        decompress: bool = True
    ) -> bytes:
        """处理响应数据"""
        if 200 <= response.status < 300:
            content = response.content

            # 处理内容解压缩
            if decompress and self.compressor and response.headers.get("Content-Encoding") == self.compressor.name:
                content = self.compressor.decompress(content)

            return content
        else:
            raise HTTPException(
                status_code=response.status,
                content=response.content,
                message=f"HTTP请求失败，状态码: {response.status}"
            )


class AsyncClient(BaseClient):
    """异步HTTP客户端"""

    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        base_url: str,
        compressor: Optional[Any] = None,
        default_headers: Optional[Dict[str, str]] = None,
        timeout: Optional[Dict[str, float]] = None,
        connection_retries: int = 3,
    ):
        super().__init__(
            pool=pool,
            base_url=base_url,
            compressor=compressor,
            default_headers=default_headers,
            timeout=timeout,
            connection_retries=connection_retries
        )

    async def request(
        self,
        method: str,
        path: str,
        data: Optional[dict] = None,
        request_timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> bytes:
        """执行HTTP请求并返回响应内容"""
        data_bytes = None
        if data:
            data_bytes = json.dumps(data).encode()
        req_data = self._prepare_request(
            method=method,
            path=path,
            data=data_bytes,
            request_timeout=request_timeout,
            headers=headers,
            **kwargs
        )

        conn = self.pool
        url = req_data["url"]

        for _ in range(self.connection_retries):
            try:
                logger.info(str(req_data))
                response = await conn.request(**req_data)
                return self._process_response(response)
            except RemoteProtocolError:
                # 重建连接
                conn = self.pool.create_connection(URL(url).origin)
                continue
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    content=str(e).encode(),
                    message=f"请求过程中发生错误: {str(e)}"
                ) from e

    async def stream_request(
        self,
        method: str,
        path: str,
        data: Optional[bytes] = None,
        request_timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Generator[bytes, None, None]:
        """流式HTTP请求"""
        req_data = self._prepare_request(
            method=method,
            path=path,
            data=data,
            request_timeout=request_timeout,
            headers=headers,
            **kwargs
        )

        conn = self.pool
        url = req_data["url"]

        for _ in range(self.connection_retries):
            try:
                async with conn.stream(**req_data) as response:
                    # 检查响应状态
                    if not (200 <= response.status < 300):
                        content = await response.aread()
                        raise HTTPException(
                            status_code=response.status,
                            content=content,
                            message=f"HTTP流请求失败，状态码: {response.status}"
                        )

                    # 流式返回数据
                    async for chunk in response.aiter_stream():
                        yield chunk
                    return
            except RemoteProtocolError:
                # 重建连接
                conn = self.pool.create_connection(URL(url).origin)
                continue
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    content=str(e).encode(),
                    message=f"流请求过程中发生错误: {str(e)}"
                ) from e


class SyncClient(BaseClient):
    """同步HTTP客户端"""

    def __init__(
        self,
        *,
        pool: ConnectionPool,
        base_url: str,
        compressor: Optional[Any] = None,
        default_headers: Optional[Dict[str, str]] = None,
        timeout: Optional[Dict[str, float]] = None,
        connection_retries: int = 3,
    ):
        super().__init__(
            pool=pool,
            base_url=base_url,
            compressor=compressor,
            default_headers=default_headers,
            timeout=timeout,
            connection_retries=connection_retries
        )

    def request(
        self,
        method: str,
        path: str,
        data: Optional[bytes] = None,
        request_timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> bytes:
        """执行HTTP请求并返回响应内容"""
        req_data = self._prepare_request(
            method=method,
            path=path,
            data=data,
            request_timeout=request_timeout,
            headers=headers,
            **kwargs
        )

        conn = self.pool
        url = req_data["url"]

        for _ in range(self.connection_retries):
            try:
                response = conn.request(**req_data)
                return self._process_response(response)
            except RemoteProtocolError:
                # 重建连接
                conn = self.pool.create_connection(URL(url).origin)
                continue
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    content=str(e).encode(),
                    message=f"请求过程中发生错误: {str(e)}"
                ) from e

    def stream_request(
        self,
        method: str,
        path: str,
        data: Optional[bytes] = None,
        request_timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Generator[bytes, None, None]:
        """流式HTTP请求"""
        req_data = self._prepare_request(
            method=method,
            path=path,
            data=data,
            request_timeout=request_timeout,
            headers=headers,
            **kwargs
        )

        conn = self.pool
        url = req_data["url"]

        for _ in range(self.connection_retries):
            try:
                with conn.stream(**req_data) as response:
                    # 检查响应状态
                    if not (200 <= response.status < 300):
                        content = response.read()
                        raise HTTPException(
                            status_code=response.status,
                            content=content,
                            message=f"HTTP流请求失败，状态码: {response.status}"
                        )

                    # 流式返回数据
                    for chunk in response.iter_stream():
                        yield chunk
                    return
            except RemoteProtocolError:
                # 重建连接
                conn = self.pool.create_connection(URL(url).origin)
                continue
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    content=str(e).encode(),
                    message=f"流请求过程中发生错误: {str(e)}"
                ) from e
