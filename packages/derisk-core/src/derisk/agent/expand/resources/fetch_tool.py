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

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:112.0) Gecko/20100101 Firefox/112.0",
        }
        if "www.baidu.com" in url:
            headers["Cookie"] = """PSTM=1677827588; BAIDUID=A410459655D83837CCD6277C8793D39F:FG=1; BIDUPSID=DA4523422A41D05919A1540DD835F576; BDUSS=Td6UGdPOWJFaWIwTnlqbzRyYndTMW54NVdkQ0IzcmxibVNCa3VJVHl0Nm0wc1ZrSUFBQUFBJCQAAAAAAAAAAAEAAAD-CBYLeWhqdW4xMDI2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKZFnmSmRZ5kL; BDUSS_BFESS=Td6UGdPOWJFaWIwTnlqbzRyYndTMW54NVdkQ0IzcmxibVNCa3VJVHl0Nm0wc1ZrSUFBQUFBJCQAAAAAAAAAAAEAAAD-CBYLeWhqdW4xMDI2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKZFnmSmRZ5kL; MCITY=-75%3A; H_WISE_SIDS=234020_216840_213348_214790_110085_244716_254833_261719_236312_256419_265881_266366_267298_265615_267074_259033_268569_266186_259642_269232_256151_269731_268237_269904_270083_267066_256739_270460_270451_270548_271034_271172_271175_271229_267659_271319_265032_271269_271482_266027_270102_271875_270157_269771_271812_269877_271957_271953_271944_271253_234296_234207_271187_272278_263618_267596_272364_272009_272464_253022_272654_272611_272472_272821_272839_272801_272958_260335_269296_269715_273093_273160_273119_273150_273029_273238_272795_273301_273399_273385_271158_273456_270055_273520_272642_272818_271562_271146_273671_264170_270186_272263_273807_273736_273165_274081_273932_273965_274139_274179_269610_273918_273348_274234_273788_273045_273595_263750_274290_256223_272806_203520_274356_272319_272561; BDORZ=B490B5EBF6F3CD402E515D22BCDA1598; H_WISE_SIDS_BFESS=234020_216840_213348_214790_110085_244716_254833_261719_236312_256419_265881_266366_267298_265615_267074_259033_268569_266186_259642_269232_256151_269731_268237_269904_270083_267066_256739_270460_270451_270548_271034_271172_271175_271229_267659_271319_265032_271269_271482_266027_270102_271875_270157_269771_271812_269877_271957_271953_271944_271253_234296_234207_271187_272278_263618_267596_272364_272009_272464_253022_272654_272611_272472_272821_272839_272801_272958_260335_269296_269715_273093_273160_273119_273150_273029_273238_272795_273301_273399_273385_271158_273456_270055_273520_272642_272818_271562_271146_273671_264170_270186_272263_273807_273736_273165_274081_273932_273965_274139_274179_269610_273918_273348_274234_273788_273045_273595_263750_274290_256223_272806_203520_274356_272319_272561; BA_HECTOR=218ga42521agala504000k0n1ifblgv1p; ZFY=RWcEWIlSWNOokGPSHuKGMqUv7mjMGIhDhNz5vTFDibc:C; BAIDUID_BFESS=A410459655D83837CCD6277C8793D39F:FG=1; BDRCVFR[feWj1Vr5u3D]=I67x6TjHwwYf0; delPer=0; BDRCVFR[S4-dAuiWMmn]=I67x6TjHwwYf0; PSINO=7; H_PS_PSSID=39227_39282_39222_39285_39097_39199_39261_39269_39233_26350_39239_39225; ab_sr=1.0.1_YzUzMzJjOGM3MTk0ZGQ5NTM2N2UyZTMyOGE5OTZkYmIzMzVmZDhiZDM0YjcyNjRkNjdiNzQ0MDk3MmUzMDBmNTE3NjdjZWJhZDYxMDFiZDIxZTVmM2FjMjRkODRkYjlkYTAwYWEwMTM2NGVkNmVjZDViMDQwMTM1ZThmMjViZDQ5OWY1MjJmYzBjMmYyNzlmYmU5NmQxNjFhZWUyODAwYQ==; RT="z=1&dm=baidu.com&si=7ba2d0b3-59a6-4cfa-89d7-2444febb8501&ss=lm60oklu&sl=8&tt=2ti&bcn=https%3A%2F%2Ffclog.baidu.com%2Flog%2Fweirwood%3Ftype%3Dperf&ld=o8o&ul=qno&hd=r01"""
        try:
            response = await client.get(
                url,
                follow_redirects=True,
                headers=headers,
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
    # print(asyncio.run(fetch("http://www.baidu.com/link?url=yV-nUEU2KMzIvRzBqP9tajG4lkdwLueykeiSQW-sZ6jxqNzAXztV5-AdpbWtZa2Y0WUN-OT5usum2KFKzaIViSwTWMqhuirAIejiHSBdHGqICZfttawCNh6UbCXGMLWyEO_Sr5KLOeeVRzyWJwftY_")))
    print(asyncio.run(fetch("http://www.baidu.com/s?wd=%E5%B0%8A%E7%95%8Cs800")))