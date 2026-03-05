"""
Network Tools - Unified Tool Authorization System

This module implements network operations:
- webfetch: Fetch content from a URL
- websearch: Web search (placeholder)

Version: 2.0
"""

import asyncio
import re
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
import ssl
import json

from ..decorators import network_tool
from ..base import ToolResult
from ..metadata import (
    ToolParameter,
    ToolCategory,
    AuthorizationRequirement,
    RiskLevel,
    RiskCategory,
)


# Try to import aiohttp, but provide fallback
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


# URL patterns that might be sensitive
SENSITIVE_URL_PATTERNS = [
    r"localhost",
    r"127\.0\.0\.1",
    r"0\.0\.0\.0",
    r"192\.168\.",
    r"10\.\d+\.",
    r"172\.(1[6-9]|2[0-9]|3[01])\.",
    r"\.local$",
    r"\.internal$",
    r"metadata\.google",  # Cloud metadata services
    r"169\.254\.169\.254",  # AWS metadata
]


def is_sensitive_url(url: str) -> bool:
    """Check if URL might be accessing sensitive internal resources."""
    for pattern in SENSITIVE_URL_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False


@network_tool(
    name="webfetch",
    description="Fetch content from a URL. Returns the response body as text or JSON.",
    dangerous=False,
    parameters=[
        ToolParameter(
            name="url",
            type="string",
            description="The URL to fetch (must be http:// or https://)",
            required=True,
            pattern=r"^https?://",
        ),
        ToolParameter(
            name="method",
            type="string",
            description="HTTP method to use",
            required=False,
            default="GET",
            enum=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"],
        ),
        ToolParameter(
            name="headers",
            type="object",
            description="HTTP headers to send",
            required=False,
        ),
        ToolParameter(
            name="body",
            type="string",
            description="Request body (for POST/PUT)",
            required=False,
        ),
        ToolParameter(
            name="format",
            type="string",
            description="Response format: 'text', 'json', or 'markdown'",
            required=False,
            default="text",
            enum=["text", "json", "markdown"],
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Request timeout in seconds",
            required=False,
            default=30,
            min_value=1,
            max_value=120,
        ),
        ToolParameter(
            name="max_length",
            type="integer",
            description="Maximum response length in bytes",
            required=False,
            default=100000,
            max_value=10000000,
        ),
    ],
    tags=["network", "http", "fetch", "web"],
    timeout=120,
)
async def webfetch(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[str] = None,
    format: str = "text",
    timeout: int = 30,
    max_length: int = 100000,
    context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Fetch content from a URL."""
    
    # Validate URL
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult.error_result(
                f"Invalid URL scheme: {parsed.scheme}. Only http:// and https:// are allowed."
            )
    except Exception as e:
        return ToolResult.error_result(f"Invalid URL: {str(e)}")
    
    # Check for sensitive URLs
    if is_sensitive_url(url):
        return ToolResult.error_result(
            f"Access to internal/sensitive URLs is not allowed: {url}",
            sensitive=True,
        )
    
    # Check if aiohttp is available
    if not AIOHTTP_AVAILABLE:
        return ToolResult.error_result(
            "aiohttp is not installed. Install with: pip install aiohttp"
        )
    
    try:
        # Create SSL context
        ssl_context = ssl.create_default_context()
        
        # Prepare headers
        request_headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DeRiskTool/2.0)",
        }
        if headers:
            request_headers.update(headers)
        
        # Make request
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=client_timeout,
        ) as session:
            async with session.request(
                method=method.upper(),
                url=url,
                headers=request_headers,
                data=body if body else None,
            ) as response:
                # Get response info
                status = response.status
                content_type = response.headers.get("Content-Type", "")
                
                # Read content with limit
                content = await response.content.read(max_length)
                
                # Check if content was truncated
                truncated = False
                try:
                    remaining = await response.content.read(1)
                    if remaining:
                        truncated = True
                except:
                    pass
                
                # Decode content
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        text = content.decode("latin-1")
                    except:
                        text = content.decode("utf-8", errors="replace")
                
                # Format response
                if format == "json":
                    try:
                        data = json.loads(text)
                        text = json.dumps(data, indent=2)
                    except json.JSONDecodeError:
                        # Return as-is if not valid JSON
                        pass
                elif format == "markdown":
                    # Basic HTML to markdown conversion (simplified)
                    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r"<[^>]+>", "", text)
                    text = re.sub(r"\s+", " ", text)
                    text = text.strip()
                
                # Build output
                if truncated:
                    text += f"\n\n... (content truncated at {max_length} bytes)"
                
                if status >= 400:
                    return ToolResult.error_result(
                        f"HTTP {status}: {text[:500]}",
                        status_code=status,
                        content_type=content_type,
                    )
                
                return ToolResult.success_result(
                    text,
                    status_code=status,
                    content_type=content_type,
                    truncated=truncated,
                )
                
    except asyncio.TimeoutError:
        return ToolResult.error_result(f"Request timed out after {timeout} seconds")
    except aiohttp.ClientError as e:
        return ToolResult.error_result(f"HTTP client error: {str(e)}")
    except Exception as e:
        return ToolResult.error_result(f"Error fetching URL: {str(e)}")


@network_tool(
    name="websearch",
    description="Search the web for information. Returns search results.",
    dangerous=False,
    parameters=[
        ToolParameter(
            name="query",
            type="string",
            description="The search query",
            required=True,
            min_length=1,
            max_length=500,
        ),
        ToolParameter(
            name="num_results",
            type="integer",
            description="Number of results to return",
            required=False,
            default=10,
            min_value=1,
            max_value=50,
        ),
    ],
    tags=["network", "search", "web"],
    timeout=60,
)
async def websearch(
    query: str,
    num_results: int = 10,
    context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """
    Search the web for information.
    
    Note: This is a placeholder implementation.
    In production, integrate with a search API (Google, Bing, etc.)
    """
    return ToolResult.error_result(
        "Web search is not configured. Please configure a search API provider.",
        query=query,
        placeholder=True,
    )


# Export all tools for registration
__all__ = [
    "webfetch",
    "websearch",
    "is_sensitive_url",
    "SENSITIVE_URL_PATTERNS",
]
