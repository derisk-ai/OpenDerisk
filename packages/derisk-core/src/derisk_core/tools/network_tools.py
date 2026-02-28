import asyncio
import json
import re
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
from .base import ToolBase, ToolMetadata, ToolResult, ToolCategory, ToolRisk

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


class WebFetchTool(ToolBase):
    """网络请求工具 - 获取网页内容"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="webfetch",
            description="获取网页内容，支持多种格式输出",
            category=ToolCategory.NETWORK,
            risk=ToolRisk.LOW,
            requires_permission=False,
            examples=[
                "webfetch('https://example.com')",
                "webfetch('https://api.example.com/data', format='json')"
            ]
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要获取的URL"
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "markdown", "json", "html"],
                    "default": "markdown",
                    "description": "输出格式"
                },
                "timeout": {
                    "type": "integer",
                    "default": 30,
                    "description": "超时时间(秒)"
                },
                "headers": {
                    "type": "object",
                    "description": "请求头"
                }
            },
            "required": ["url"]
        }
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        url = args["url"]
        format_type = args.get("format", "markdown")
        timeout = args.get("timeout", 30)
        headers = args.get("headers", {})
        
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ToolResult(success=False, error=f"无效的URL: {url}")
        
        try:
            if not HAS_AIOHTTP:
                return ToolResult(success=False, error="需要安装 aiohttp: pip install aiohttp")
            
            default_headers = {
                "User-Agent": "Mozilla/5.0 (compatible; OpenDeRisk/1.0)",
                "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            }
            default_headers.update(headers)
            
            timeout_config = aiohttp.ClientTimeout(total=timeout)
            
            async with aiohttp.ClientSession(timeout=timeout_config) as session:
                async with session.get(url, headers=default_headers) as response:
                    if response.status >= 400:
                        return ToolResult(
                            success=False, 
                            error=f"HTTP错误: {response.status} {response.reason}"
                        )
                    
                    content_type = response.headers.get("Content-Type", "")
                    raw_content = await response.text()
                    
                    if format_type == "json" or "application/json" in content_type:
                        try:
                            data = json.loads(raw_content)
                            return ToolResult(
                                success=True,
                                output=json.dumps(data, indent=2, ensure_ascii=False),
                                metadata={"content_type": content_type}
                            )
                        except json.JSONDecodeError:
                            pass
                    
                    if format_type == "html":
                        return ToolResult(
                            success=True,
                            output=raw_content,
                            metadata={"content_type": content_type}
                        )
                    
                    if format_type == "markdown":
                        markdown = self._html_to_markdown(raw_content)
                        return ToolResult(
                            success=True,
                            output=markdown,
                            metadata={"content_type": content_type, "original_length": len(raw_content)}
                        )
                    
                    text = self._extract_text(raw_content)
                    return ToolResult(
                        success=True,
                        output=text,
                        metadata={"content_type": content_type}
                    )
                    
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"请求超时({timeout}秒)")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    def _html_to_markdown(self, html: str) -> str:
        """简单的HTML转Markdown"""
        text = html
        
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        
        text = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<h4[^>]*>(.*?)</h4>', r'\n#### \1\n', text, flags=re.IGNORECASE)
        
        text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', text, flags=re.IGNORECASE)
        text = re.sub(r'<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*/?>', r'![\2](\1)', text, flags=re.IGNORECASE)
        
        text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', text, flags=re.IGNORECASE)
        text = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', text, flags=re.IGNORECASE)
        text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', text, flags=re.IGNORECASE)
        text = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', text, flags=re.IGNORECASE)
        text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.IGNORECASE)
        
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', text, flags=re.IGNORECASE)
        
        text = re.sub(r'<[^>]+>', '', text)
        
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        
        return text.strip()
    
    def _extract_text(self, html: str) -> str:
        """提取纯文本"""
        text = html
        
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
        
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        
        return text.strip()


class WebSearchTool(ToolBase):
    """网络搜索工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="websearch",
            description="在网络上搜索信息",
            category=ToolCategory.NETWORK,
            risk=ToolRisk.LOW,
            requires_permission=False
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询"
                },
                "num_results": {
                    "type": "integer",
                    "default": 5,
                    "description": "返回结果数量"
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        query = args["query"]
        num_results = args.get("num_results", 5)
        
        if not HAS_AIOHTTP:
            return ToolResult(success=False, error="需要安装 aiohttp")
        
        search_url = f"https://duckduckgo.com/html/?q={query}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; OpenDeRisk/1.0)"
                }) as response:
                    html = await response.text()
            
            results = self._parse_search_results(html, num_results)
            
            if not results:
                return ToolResult(
                    success=True,
                    output="未找到相关结果",
                    metadata={"query": query}
                )
            
            output = "\n\n".join([
                f"**{r['title']}**\n{r['url']}\n{r['snippet']}"
                for r in results
            ])
            
            return ToolResult(
                success=True,
                output=output,
                metadata={"query": query, "count": len(results)}
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    def _parse_search_results(self, html: str, max_results: int) -> List[Dict]:
        """解析搜索结果"""
        results = []
        
        result_pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        snippet_pattern = r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>'
        
        links = re.findall(result_pattern, html, re.DOTALL)
        snippets = re.findall(snippet_pattern, html, re.DOTALL)
        
        for i, (url, title) in enumerate(links[:max_results]):
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            
            clean_url = url
            if url.startswith('//'):
                clean_url = 'https:' + url
            
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            
            results.append({
                "title": clean_title,
                "url": clean_url,
                "snippet": snippet
            })
        
        return results