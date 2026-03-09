"""
网络工具模块 - 已迁移到统一工具框架

提供Agent的网络访问能力：
- WebFetchTool: 获取网页内容
- WebSearchTool: 网络搜索
- APICallTool: API调用
"""

from typing import Any, Dict, List, Optional
import logging
import asyncio
import json
import re
from urllib.parse import urlparse

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from ...metadata import ToolMetadata
from ...result import ToolResult
from ...context import ToolContext

logger = logging.getLogger(__name__)


class WebFetchTool(ToolBase):
    """获取网页内容工具 - 已迁移"""

    def __init__(self, http_client: Optional[Any] = None, timeout: int = 30):
        self._http_client = http_client
        self._timeout = timeout
        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="webfetch",
            display_name="Web Fetch",
            description=(
                "Fetch content from a specified URL. "
                "Takes a URL and optional format as input. "
                "Fetches the URL content, converts to requested format (markdown by default). "
                "Returns the content in the specified format. "
                "Use this tool when you need to retrieve and analyze web content."
            ),
            category=ToolCategory.NETWORK,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=True,
            tags=["network", "web", "fetch", "http"],
            timeout=30,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch content from",
                },
                "format": {
                    "type": "string",
                    "description": "Format to return content in",
                    "enum": ["markdown", "text", "html", "json"],
                    "default": "markdown",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (max 120)",
                    "default": 30,
                    "maximum": 120,
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["url"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        url = args.get("url", "")
        format_type = args.get("format", "markdown")
        timeout = min(args.get("timeout", self._timeout), 120)
        headers = args.get("headers", {})

        if not url:
            return ToolResult(
                success=False, output="", error="URL不能为空", tool_name=self.name
            )

        try:
            parsed = urlparse(url)
            if not parsed.scheme:
                url = "https://" + url
            elif parsed.scheme not in ["http", "https"]:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"不支持的协议: {parsed.scheme}",
                    tool_name=self.name,
                )
        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"无效的URL: {e}", tool_name=self.name
            )

        try:
            if self._http_client:
                content = await self._fetch_with_client(url, headers, timeout)
            else:
                content = await self._fetch_with_aiohttp(url, headers, timeout)

            output = self._format_content(content, format_type)

            return ToolResult(
                success=True,
                output=output,
                tool_name=self.name,
                metadata={
                    "url": url,
                    "format": format_type,
                    "content_length": len(output),
                },
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"请求超时 ({timeout}秒)",
                tool_name=self.name,
            )
        except Exception as e:
            logger.error(f"[WebFetchTool] 请求失败: {e}")
            return ToolResult(
                success=False, output="", error=str(e), tool_name=self.name
            )

    async def _fetch_with_client(
        self, url: str, headers: Dict[str, str], timeout: int
    ) -> str:
        if hasattr(self._http_client, "get"):
            response = await self._http_client.get(
                url, headers=headers, timeout=timeout
            )
            return await response.text()
        raise ValueError("HTTP client not properly configured")

    async def _fetch_with_aiohttp(
        self, url: str, headers: Dict[str, str], timeout: int
    ) -> str:
        try:
            import aiohttp

            default_headers = {
                "User-Agent": "Mozilla/5.0 (compatible; DeRiskAgent/1.0)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            default_headers.update(headers)

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=default_headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status >= 400:
                        raise ValueError(f"HTTP错误: {response.status}")
                    return await response.text()
        except ImportError:
            return await self._fetch_with_httpx(url, headers, timeout)

    async def _fetch_with_httpx(
        self, url: str, headers: Dict[str, str], timeout: int
    ) -> str:
        try:
            import httpx

            default_headers = {
                "User-Agent": "Mozilla/5.0 (compatible; DeRiskAgent/1.0)",
            }
            default_headers.update(headers)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=default_headers, timeout=timeout
                )
                response.raise_for_status()
                return response.text
        except ImportError:
            raise ImportError(
                "需要安装 aiohttp 或 httpx: pip install aiohttp 或 pip install httpx"
            )

    def _format_content(self, content: str, format_type: str) -> str:
        if format_type == "html":
            return content
        elif format_type == "text":
            return self._html_to_text(content)
        elif format_type == "json":
            return self._extract_json(content)
        else:
            return self._html_to_markdown(content)

    def _html_to_text(self, html: str) -> str:
        text = re.sub(
            r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(
            r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _html_to_markdown(self, html: str) -> str:
        text = self._html_to_text(html)

        lines = text.split("\n")
        result = []
        for line in lines:
            line = line.strip()
            if line:
                result.append(line)

        return "\n\n".join(result)

    def _extract_json(self, content: str) -> str:
        json_pattern = r'<(?:script[^>]*type=["\']application/json["\'][^>]*|pre)[^>]*>(.*?)</(?:script|pre)>'
        matches = re.findall(json_pattern, content, re.DOTALL | re.IGNORECASE)

        json_objects = []
        for match in matches:
            try:
                data = json.loads(match.strip())
                json_objects.append(data)
            except json.JSONDecodeError:
                continue

        if json_objects:
            return json.dumps(json_objects, indent=2, ensure_ascii=False)

        return "未找到JSON内容"


class WebSearchTool(ToolBase):
    """网络搜索工具 - 已迁移"""

    def __init__(
        self,
        search_engine: Optional[Any] = None,
        api_key: Optional[str] = None,
        search_engine_id: Optional[str] = None,
    ):
        self._search_engine = search_engine
        self._api_key = api_key
        self._search_engine_id = search_engine_id
        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="websearch",
            display_name="Web Search",
            description=(
                "Search the web for information. "
                "Returns search results with titles, URLs, and snippets. "
                "Use this tool when you need to find information on the internet."
            ),
            category=ToolCategory.NETWORK,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=True,
            tags=["network", "search", "web", "google"],
            timeout=30,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 10,
                    "maximum": 20,
                },
                "lang": {
                    "type": "string",
                    "description": "Language for search results",
                    "default": "en",
                },
            },
            "required": ["query"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        query = args.get("query", "")
        num_results = min(args.get("num_results", 10), 20)
        lang = args.get("lang", "en")

        if not query:
            return ToolResult(
                success=False, output="", error="搜索查询不能为空", tool_name=self.name
            )

        try:
            if self._search_engine:
                results = await self._search_with_engine(query, num_results, lang)
            else:
                results = await self._search_with_serp(query, num_results, lang)

            if not results:
                return ToolResult(
                    success=True,
                    output="未找到搜索结果",
                    tool_name=self.name,
                    metadata={"query": query, "count": 0},
                )

            output_lines = [f"搜索: {query}\n"]
            for i, result in enumerate(results, 1):
                output_lines.append(f"\n{i}. {result.get('title', '无标题')}")
                output_lines.append(f"   URL: {result.get('url', 'N/A')}")
                output_lines.append(f"   {result.get('snippet', '无摘要')}")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                tool_name=self.name,
                metadata={"query": query, "count": len(results), "results": results},
            )

        except Exception as e:
            logger.error(f"[WebSearchTool] 搜索失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=f"搜索失败: {str(e)}",
                tool_name=self.name,
            )

    async def _search_with_engine(self, query: str, num: int, lang: str) -> List[Dict]:
        """使用配置的搜索引擎"""
        if hasattr(self._search_engine, "search"):
            return await self._search_engine.search(query, num_results=num, lang=lang)
        return []

    async def _search_with_serp(self, query: str, num: int, lang: str) -> List[Dict]:
        """使用 SerpAPI 或类似服务"""
        try:
            import aiohttp

            api_key = self._api_key
            if not api_key:
                return self._mock_search_results(query, num)

            url = "https://serpapi.com/search"
            params = {
                "q": query,
                "api_key": api_key,
                "engine": "google",
                "num": num,
                "hl": lang,
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    data = await response.json()

                    results = []
                    for item in data.get("organic_results", [])[:num]:
                        results.append(
                            {
                                "title": item.get("title"),
                                "url": item.get("link"),
                                "snippet": item.get("snippet", ""),
                            }
                        )
                    return results
        except ImportError:
            return self._mock_search_results(query, num)
        except Exception as e:
            logger.warning(f"搜索API调用失败，使用模拟结果: {e}")
            return self._mock_search_results(query, num)

    def _mock_search_results(self, query: str, num: int) -> List[Dict]:
        """模拟搜索结果（用于测试）"""
        return [
            {
                "title": f"搜索结果 {i + 1} for: {query}",
                "url": f"https://example.com/result/{i + 1}",
                "snippet": f"这是关于 '{query}' 的模拟搜索结果 {i + 1}。请配置搜索API以获取真实结果。",
            }
            for i in range(min(num, 3))
        ]


def register_network_tools(
    registry: "ToolRegistry", http_client: Optional[Any] = None
) -> None:
    """注册网络工具"""
    from ...registry import ToolRegistry

    registry.register(WebFetchTool(http_client=http_client))
    registry.register(WebSearchTool())
    logger.info("[NetworkTools] 已注册网络工具: webfetch, websearch")
