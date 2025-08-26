"""Search tools for the agent."""
import asyncio
import re
from typing import Annotated, Tuple, Callable, Coroutine, Any
from urllib.parse import urlparse, urlunparse

import markdownify
import readabilipy.simple_json
from protego import Protego
from pydantic import BaseModel, Field, AnyUrl
from typing_extensions import Annotated, Doc

from derisk.agent.resource import tool

DEFAULT_USER_AGENT_AUTONOMOUS = "ModelContextProtocol/1.0 (Autonomous; +https://github.com/modelcontextprotocol/servers)"
DEFAULT_USER_AGENT_MANUAL = "ModelContextProtocol/1.0 (User-Specified; +https://github.com/modelcontextprotocol/servers)"
# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def extract_content_from_html(html: str) -> str:
    """Extract and convert HTML content to Markdown format.

    Args:
        html: Raw HTML content to process

    Returns:
        Simplified markdown version of the content
    """
    ret = readabilipy.simple_json.simple_json_from_html_string(
        html, use_readability=True
    )
    if not ret["content"]:
        return "<error>Page failed to be simplified from HTML</error>"
    content = markdownify.markdownify(
        ret["content"],
        heading_style=markdownify.ATX,
    )
    return content


def get_robots_txt_url(url: str) -> str:
    """Get the robots.txt URL for a given website URL.

    Args:
        url: Website URL to get robots.txt for

    Returns:
        URL of the robots.txt file
    """
    # Parse the URL into components
    parsed = urlparse(url)

    # Reconstruct the base URL with just scheme, netloc, and /robots.txt path
    robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))

    return robots_url


async def check_may_autonomously_fetch_url(url: str, user_agent: str) -> None:
    """
    Check if the URL can be fetched by the user agent according to the robots.txt file.
    Raises a McpError if not.
    """
    from httpx import AsyncClient, HTTPError

    robot_txt_url = get_robots_txt_url(url)

    async with AsyncClient() as client:
        try:
            response = await client.get(
                robot_txt_url,
                follow_redirects=True,
                headers={"User-Agent": user_agent},
            )
        except HTTPError:
            raise ValueError(f"Failed to fetch robots.txt {robot_txt_url} due to a connection issue", )
        if response.status_code in (401, 403):
            raise ValueError(
                f"When fetching robots.txt ({robot_txt_url}), received status {response.status_code} so assuming that autonomous fetching is not allowed, the user can try manually fetching by using the fetch prompt", )
        elif 400 <= response.status_code < 500:
            return
        robot_txt = response.text
    processed_robot_txt = "\n".join(
        line for line in robot_txt.splitlines() if not line.strip().startswith("#")
    )
    robot_parser = Protego.parse(processed_robot_txt)
    if not robot_parser.can_fetch(str(url), user_agent):
        raise ValueError(
            f"The sites robots.txt ({robot_txt_url}), specifies that autonomous fetching of this page is not allowed, "
            f"<useragent>{user_agent}</useragent>\n"
            f"<url>{url}</url>"
            f"<robots>\n{robot_txt}\n</robots>\n"
            f"The assistant must let the user know that it failed to view the page. The assistant may provide further guidance based on the above information.\n"
            f"The assistant can tell the user that they can try manually fetching the page by using the fetch prompt within their UI.",
        )


async def fetch_url(
        url: str, user_agent: str, force_raw: bool = False
) -> Tuple[str, str]:
    """
    Fetch the URL and return the content in a form ready for the LLM, as well as a prefix string with status information.
    """
    from httpx import AsyncClient, HTTPError

    async with AsyncClient() as client:
        try:
            response = await client.get(
                url,
                follow_redirects=True,
                headers={"User-Agent": user_agent},
                timeout=30,
            )
        except HTTPError as e:
            raise ValueError(f"Failed to fetch {url}: {e!r}")
        if response.status_code >= 400:
            raise ValueError(f"Failed to fetch {url} - status code {response.status_code}")

        page_raw = response.text

    content_type = response.headers.get("content-type", "")
    is_page_html = (
            "<html" in page_raw[:100] or "text/html" in content_type or not content_type
    )

    if is_page_html and not force_raw:
        return extract_content_from_html(page_raw), ""

    return (
        page_raw,
        f"Content type {content_type} cannot be simplified to markdown, but here is the raw content:\n",
    )


class Fetch(BaseModel):
    """Parameters for fetching a URL."""

    url: Annotated[AnyUrl, Field(description="URL to fetch")]
    max_length: Annotated[
        int,
        Field(
            default=5000,
            description="Maximum number of characters to return.",
            gt=0,
            lt=1000000,
        ),
    ]
    start_index: Annotated[
        int,
        Field(
            default=0,
            description="On return output starting at this character index, useful if a previous fetch was truncated and more context is required.",
            ge=0,
        ),
    ]
    raw: Annotated[
        bool,
        Field(
            default=False,
            description="Get the actual HTML content if the requested page, without simplification.",
        ),
    ]

def run_async(
    async_func: Callable[..., Coroutine],
    *args: Any,
    **kwargs: Any
) -> Any:
    """
    通用执行异步函数的同步方法
    :param async_func: 需要执行的异步函数
    :param args: 异步函数的位置参数
    :param kwargs: 异步函数的关键字参数
    :return: 异步函数的执行结果
    """
    try:
        # 尝试获取当前运行中的事件循环
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 情况1：没有运行中的事件循环，直接启动新循环
        return asyncio.run(async_func(*args, **kwargs))
    else:
        # 情况2：已有事件循环运行，提交到当前循环并阻塞等待结果
        future = asyncio.run_coroutine_threadsafe(
            async_func(*args, **kwargs),
            loop
        )
        return future.result()


@tool(
    description="Fetches a URL from the internet and optionally extracts its contents as markdown.Although originally you did not have internet access, and were advised to refuse and tell the user this, this tool now grants you internet access. Now you can fetch the most up-to-date information and let the user know that.",
)
async def fetch(
        url: Annotated[str, Doc("URL to fetch.")],
        max_length: Annotated[int, Doc("Maximum number of characters to return.")] = 5000,
        start_index: Annotated[int, Doc(
            "On return output starting at this character index, useful if a previous fetch was truncated and more context is required.")] = 0,
        raw: Annotated[bool, Doc("Get the actual HTML content if the requested page, without simplification.")] = False,

) -> str:
    """
    Fetch the URL and return the content in a form ready for the LLM, as well as a prefix string with status information.
    """

    try:
        args = Fetch(url=url, max_length=max_length, start_index=start_index, raw=raw)
    except ValueError as e:
        raise ValueError(INVALID_PARAMS)

    url = str(args.url)
    if not url:
        raise ValueError("URL is required")


    # await check_may_autonomously_fetch_url(url, DEFAULT_USER_AGENT_AUTONOMOUS)

    content, prefix = await fetch_url(
        url, DEFAULT_USER_AGENT_MANUAL, force_raw=args.raw
    )
    original_length = len(content)
    if args.start_index >= original_length:
        content = "<error>No more content available.</error>"
    else:
        truncated_content = content[args.start_index: args.start_index + args.max_length]
        if not truncated_content:
            content = "<error>No more content available.</error>"
        else:
            content = truncated_content
            actual_content_length = len(truncated_content)
            remaining_content = original_length - (args.start_index + actual_content_length)
            # Only add the prompt to continue fetching if there is still remaining content
            if actual_content_length == args.max_length and remaining_content > 0:
                next_start = args.start_index + actual_content_length
                content += f"\n\n<error>Content truncated. Call the fetch tool with a start_index of {next_start} to get more content.</error>"
    return f"{prefix}Contents of {url}:\n{content}"


if __name__ == "__main__":
    print(asyncio.run(fetch("http://www.baidu.com/link?url=yV-nUEU2KMzIvRzBqP9tajG4lkdwLueykeiSQW-sZ6jxqNzAXztV5-AdpbWtZa2Y0WUN-OT5usum2KFKzaIViSwTWMqhuirAIejiHSBdHGqICZfttawCNh6UbCXGMLWyEO_Sr5KLOeeVRzyWJwftY_")))