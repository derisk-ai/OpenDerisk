"""
网络工具集合

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

from .tool_base import ToolBase, ToolMetadata, ToolResult

logger = logging.getLogger(__name__)


class WebFetchTool(ToolBase):
    """获取网页内容工具"""
    
    def __init__(self, http_client: Optional[Any] = None, timeout: int = 30):
        self._http_client = http_client
        self._timeout = timeout
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="webfetch",
            description=(
                "Fetch content from a specified URL. "
                "Takes a URL and optional format as input. "
                "Fetches the URL content, converts to requested format (markdown by default). "
                "Returns the content in the specified format. "
                "Use this tool when you need to retrieve and analyze web content."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch content from"
                    },
                    "format": {
                        "type": "string",
                        "description": "Format to return content in",
                        "enum": ["markdown", "text", "html", "json"],
                        "default": "markdown"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (max 120)",
                        "default": 30
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers",
                        "additionalProperties": {"type": "string"}
                    }
                },
                "required": ["url"]
            },
            requires_permission=True,
            dangerous=False,
            category="network"
        )
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        url = args.get("url", "")
        format_type = args.get("format", "markdown")
        timeout = min(args.get("timeout", self._timeout), 120)
        headers = args.get("headers", {})
        
        if not url:
            return ToolResult(
                success=False,
                output="",
                error="URL不能为空"
            )
        
        try:
            parsed = urlparse(url)
            if not parsed.scheme:
                url = "https://" + url
            elif parsed.scheme not in ["http", "https"]:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"不支持的协议: {parsed.scheme}"
                )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"无效的URL: {e}"
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
                metadata={
                    "url": url,
                    "format": format_type,
                    "content_length": len(output)
                }
            )
            
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"请求超时 ({timeout}秒)"
            )
        except Exception as e:
            logger.error(f"[WebFetchTool] 请求失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
    
    async def _fetch_with_client(
        self, 
        url: str, 
        headers: Dict[str, str], 
        timeout: int
    ) -> str:
        if hasattr(self._http_client, "get"):
            response = await self._http_client.get(url, headers=headers, timeout=timeout)
            return await response.text()
        raise ValueError("HTTP client not properly configured")
    
    async def _fetch_with_aiohttp(
        self, 
        url: str, 
        headers: Dict[str, str], 
        timeout: int
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
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status >= 400:
                        raise ValueError(f"HTTP错误: {response.status}")
                    return await response.text()
        except ImportError:
            return await self._fetch_with_httpx(url, headers, timeout)
    
    async def _fetch_with_httpx(
        self, 
        url: str, 
        headers: Dict[str, str], 
        timeout: int
    ) -> str:
        try:
            import httpx
            
            default_headers = {
                "User-Agent": "Mozilla/5.0 (compatible; DeRiskAgent/1.0)",
            }
            default_headers.update(headers)
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, 
                    headers=default_headers, 
                    timeout=timeout
                )
                response.raise_for_status()
                return response.text
        except ImportError:
            raise ImportError("需要安装 aiohttp 或 httpx: pip install aiohttp 或 pip install httpx")
    
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
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
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
    """网络搜索工具"""
    
    def __init__(
        self, 
        search_engine: Optional[Any] = None,
        api_key: Optional[str] = None,
        search_engine_id: Optional[str] = None
    ):
        self._search_engine = search_engine
        self._api_key = api_key
        self._search_engine_id = search_engine_id
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="web_search",
            description=(
                "Search the web for information. "
                "Returns search results with titles, URLs, and snippets. "
                "Use this tool when you need to find information on the internet."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 10,
                        "maximum": 20
                    },
                    "lang": {
                        "type": "string",
                        "description": "Language for search results",
                        "default": "en"
                    }
                },
                "required": ["query"]
            },
            requires_permission=True,
            dangerous=False,
            category="network"
        )
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        query = args.get("query", "")
        num_results = min(args.get("num_results", 10), 20)
        lang = args.get("lang", "en")
        
        if not query:
            return ToolResult(
                success=False,
                output="",
                error="搜索查询不能为空"
            )
        
        try:
            if self._search_engine:
                results = await self._search_with_engine(query, num_results)
            elif self._api_key and self._search_engine_id:
                results = await self._search_with_google(query, num_results, lang)
            else:
                results = await self._search_with_duckduckgo(query, num_results)
            
            output = self._format_results(results)
            
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "query": query,
                    "num_results": len(results),
                    "results": results
                }
            )
            
        except Exception as e:
            logger.error(f"[WebSearchTool] 搜索失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
    
    async def _search_with_engine(
        self, 
        query: str, 
        num_results: int
    ) -> List[Dict[str, str]]:
        if hasattr(self._search_engine, "search"):
            return await self._search_engine.search(query, num_results=num_results)
        raise ValueError("Search engine not properly configured")
    
    async def _search_with_google(
        self, 
        query: str, 
        num_results: int,
        lang: str
    ) -> List[Dict[str, str]]:
        try:
            import aiohttp
            
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": self._api_key,
                "cx": self._search_engine_id,
                "q": query,
                "num": num_results,
                "hl": lang
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    data = await response.json()
            
            results = []
            for item in data.get("items", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", "")
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Google搜索失败: {e}")
            return []
    
    async def _search_with_duckduckgo(
        self, 
        query: str, 
        num_results: int
    ) -> List[Dict[str, str]]:
        try:
            from duckduckgo_search import DDGS
            
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=num_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")
                    })
            
            return results
            
        except ImportError:
            return await self._search_with_aiohttp_fallback(query, num_results)
        except Exception as e:
            logger.error(f"DuckDuckGo搜索失败: {e}")
            return await self._search_with_aiohttp_fallback(query, num_results)
    
    async def _search_with_aiohttp_fallback(
        self, 
        query: str, 
        num_results: int
    ) -> List[Dict[str, str]]:
        results = []
        
        return [
            {
                "title": f"搜索结果占位 - 需要配置搜索API",
                "url": "https://example.com",
                "snippet": f"查询: {query}。请配置Google API或安装duckduckgo-search: pip install duckduckgo-search"
            }
        ]
    
    def _format_results(self, results: List[Dict[str, str]]) -> str:
        if not results:
            return "未找到相关结果"
        
        output_lines = []
        for i, r in enumerate(results, 1):
            output_lines.append(f"## [{i}] {r.get('title', '无标题')}")
            output_lines.append(f"URL: {r.get('url', '')}")
            output_lines.append(f"摘要: {r.get('snippet', '')}")
            output_lines.append("")
        
        return "\n".join(output_lines)


class APICallTool(ToolBase):
    """API调用工具"""
    
    def __init__(self, http_client: Optional[Any] = None, default_timeout: int = 30):
        self._http_client = http_client
        self._default_timeout = default_timeout
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="api_call",
            description=(
                "Make HTTP API calls. Supports GET, POST, PUT, DELETE methods. "
                "Use this tool to interact with external APIs and services."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "API endpoint URL"
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method",
                        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                        "default": "GET"
                    },
                    "headers": {
                        "type": "object",
                        "description": "Request headers",
                        "additionalProperties": {"type": "string"}
                    },
                    "body": {
                        "type": "object",
                        "description": "Request body (for POST/PUT/PATCH)"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds",
                        "default": 30
                    },
                    "auth_token": {
                        "type": "string",
                        "description": "Bearer token for authentication"
                    }
                },
                "required": ["url"]
            },
            requires_permission=True,
            dangerous=True,
            category="network"
        )
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        url = args.get("url", "")
        method = args.get("method", "GET").upper()
        headers = args.get("headers", {})
        body = args.get("body")
        timeout = args.get("timeout", self._default_timeout)
        auth_token = args.get("auth_token")
        
        if not url:
            return ToolResult(
                success=False,
                output="",
                error="URL不能为空"
            )
        
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        
        if body and method in ["POST", "PUT", "PATCH"]:
            headers.setdefault("Content-Type", "application/json")
        
        try:
            response_data = await self._make_request(
                url=url,
                method=method,
                headers=headers,
                body=body,
                timeout=timeout
            )
            
            output = self._format_response(response_data)
            
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "url": url,
                    "method": method,
                    "status": response_data.get("status", 200)
                }
            )
            
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"请求超时 ({timeout}秒)"
            )
        except Exception as e:
            logger.error(f"[APICallTool] 请求失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
    
    async def _make_request(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[Dict[str, Any]],
        timeout: int
    ) -> Dict[str, Any]:
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                kwargs = {
                    "headers": headers,
                    "timeout": aiohttp.ClientTimeout(total=timeout)
                }
                if body:
                    kwargs["json"] = body
                
                async with session.request(method, url, **kwargs) as response:
                    try:
                        data = await response.json()
                    except:
                        data = await response.text()
                    
                    return {
                        "status": response.status,
                        "headers": dict(response.headers),
                        "data": data
                    }
                    
        except ImportError:
            try:
                import httpx
                
                async with httpx.AsyncClient() as client:
                    kwargs = {
                        "headers": headers,
                        "timeout": timeout
                    }
                    if body:
                        kwargs["json"] = body
                    
                    response = await client.request(method, url, **kwargs)
                    
                    try:
                        data = response.json()
                    except:
                        data = response.text
                    
                    return {
                        "status": response.status_code,
                        "headers": dict(response.headers),
                        "data": data
                    }
            except ImportError:
                raise ImportError("需要安装 aiohttp 或 httpx")
    
    def _format_response(self, response_data: Dict[str, Any]) -> str:
        status = response_data.get("status", 200)
        data = response_data.get("data", {})
        
        if isinstance(data, dict) or isinstance(data, list):
            formatted_data = json.dumps(data, indent=2, ensure_ascii=False)
        else:
            formatted_data = str(data)
        
        return f"Status: {status}\n\n{formatted_data}"


class GraphQLTool(ToolBase):
    """GraphQL查询工具"""
    
    def __init__(self, endpoint: Optional[str] = None, http_client: Optional[Any] = None):
        self._endpoint = endpoint
        self._http_client = http_client
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="graphql",
            description=(
                "Execute GraphQL queries. "
                "Use this tool to interact with GraphQL APIs."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "endpoint": {
                        "type": "string",
                        "description": "GraphQL endpoint URL (optional if configured)"
                    },
                    "query": {
                        "type": "string",
                        "description": "GraphQL query or mutation"
                    },
                    "variables": {
                        "type": "object",
                        "description": "Query variables"
                    },
                    "operation_name": {
                        "type": "string",
                        "description": "Operation name"
                    }
                },
                "required": ["query"]
            },
            requires_permission=True,
            dangerous=False,
            category="network"
        )
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        endpoint = args.get("endpoint") or self._endpoint
        query = args.get("query", "")
        variables = args.get("variables", {})
        operation_name = args.get("operation_name")
        
        if not endpoint:
            return ToolResult(
                success=False,
                output="",
                error="GraphQL endpoint未配置"
            )
        
        if not query:
            return ToolResult(
                success=False,
                output="",
                error="查询不能为空"
            )
        
        payload = {
            "query": query,
            "variables": variables
        }
        if operation_name:
            payload["operationName"] = operation_name
        
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    result = await response.json()
            
            output = json.dumps(result, indent=2, ensure_ascii=False)
            
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "endpoint": endpoint,
                    "has_errors": "errors" in result
                }
            )
            
        except Exception as e:
            logger.error(f"[GraphQLTool] 查询失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


def register_network_tools(
    registry: Any,
    http_client: Optional[Any] = None,
    search_config: Optional[Dict[str, str]] = None
) -> Any:
    """注册所有网络工具"""
    registry.register(WebFetchTool(http_client=http_client))
    
    search_tool = WebSearchTool(
        api_key=search_config.get("google_api_key") if search_config else None,
        search_engine_id=search_config.get("google_search_engine_id") if search_config else None
    )
    registry.register(search_tool)
    
    registry.register(APICallTool(http_client=http_client))
    registry.register(GraphQLTool(http_client=http_client))
    
    logger.info(f"[Tools] 已注册网络工具")
    
    return registry