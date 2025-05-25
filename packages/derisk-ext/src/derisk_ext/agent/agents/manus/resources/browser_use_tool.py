import asyncio
import json
from typing import Optional

try:
    from browser_use import Browser as BrowserUseBrowser
    from browser_use import BrowserConfig
    from browser_use.browser.context import BrowserContext
    from browser_use.dom.service import DomService
except ImportError:
    raise Exception("""
        Import browser_use error, you can install use `pip install browser_use` to fix this.
    """)

from pydantic import Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from derisk.agent.resource.tool.base import tool

from .base import ToolResult

_BROWSER_DESCRIPTION = """ 
Interact with a web browser to perform various actions such as navigation, element interaction,
content extraction, and tab management. Supported actions include:
- 'navigate': Go to a specific URL
- 'click': Click an element by index
- 'input_text': Input text into an element
- 'screenshot': Capture a screenshot
- 'get_html': Get page HTML content
- 'execute_js': Execute JavaScript code
- 'scroll': Scroll the page
- 'switch_tab': Switch to a specific tab
- 'new_tab': Open a new tab
- 'close_tab': Close the current tab
- 'refresh': Refresh the current page
"""


@tool(description=_BROWSER_DESCRIPTION)
async def browser_use(
    action: str,
    url: Optional[str] = None,
    index: Optional[int] = None,
    text: Optional[str] = None,
    script: Optional[str] = None,
    scroll_amount: Optional[int] = None,
    tab_id: Optional[int] = None,
    **kwargs,
) -> ToolResult:
    """Execute a specific action using a web browser.

    Args:
        action (str): The browser action to perform.
        url (Optional[str], optional): URL for navigation or new tab
        index (Optional[int], optional): Element index for 'click' action. Defaults to None.
        text (Optional[str], optional): Text for input action.
        script (Optional[str], optional): script for JavaScript action.
        scroll_amount (Optional[int], optional): Pixels to scroll for 'scroll' action.
        tab_id (Optional[int], optional): Tab ID for 'switch_tab' action.
        **kwargs: Additional arguments for the browser action.
    Returns:
        ToolResult: ToolResult with the action's output or error
    """

    lock: asyncio.Lock = Field(default_factory=asyncio.Lock)
    browser: Optional[BrowserUseBrowser] = Field(default=None, exclude=True)
    context: Optional[BrowserContext] = Field(default=None, exclude=True)
    dom_service: Optional[DomService] = Field(default=None, exclude=True)

    if not hasattr(browser_use, "_state"):
        browser_use._state = {
            "lock": lock,
            "browser": browser,
            "context": context,
            "dom_service": dom_service,
        }

    @field_validator("parameters", mode="before")
    def validate_parameters(cls, v: dict, info: ValidationInfo) -> dict:
        if not v:
            raise ValueError("Parameters connot be empty.")
        return v

    async def _ensure_browser_initialized(self) -> BrowserContext:
        """Ensure browser and context are initialized."""
        if browser is None:
            browserr = BrowserUseBrowser(BrowserConfig(headless=False))

        if context is None:
            context = await browser.new_context()
            dom_service = DomService(await context.get_current_page())
        return context

    async with browser_use._state["lock"]:
        try:
            context = await _ensure_browser_initialized()
            if action == "navigate":
                if not url:
                    return ToolResult("URL is required for navigation.")
                await context.navigate_to(url)
                return ToolResult(output=f"Navigated to {url}.")

            elif action == "click":
                if index is None:
                    return ToolResult("Index is required for click action.")
                element = await context.get_dom_element_by_index(index)
                if not element:
                    return ToolResult(error=f"Element not found at index {index}.")
                download_path = await context._click_element_node(element)
                output = f"Clicked on element at index {index}."
                if download_path:
                    output += f" Downloaded file to {download_path}."
                return ToolResult(output=output)

            elif action == "input_text":
                if index is None or not text:
                    return ToolResult(
                        error="Index and text are required for input_text action."
                    )

                if not element:
                    return ToolResult(error=f"Element not found at index {index}.")

                await context._input_text_element_node(element, text)
                return ToolResult(
                    output=f"Input text '{text}' into element at index {index}."
                )

            elif action == "screenshot":
                screenshot = await context.take_screenshot(full_page=True)
                return ToolResult(
                    output=f"Screenshot captured (base64 lenghth: {len(screenshot)}).",
                    system=screenshot,
                )

            elif action == "get_html":
                html = await context.get_page_html()
                truncated = html[:2000] + "..." if len(html) > 2000 else html
                return ToolResult(output=truncated)

            elif action == "execute_js":
                if not script:
                    return ToolResult(
                        error="Script is required for 'execute_js' action"
                    )
                result = await context.execute_javascript(script)
                return ToolResult(output=str(result))

            elif action == "scroll":
                if scroll_amount is None:
                    return ToolResult(
                        error="Scroll amount is required for 'scroll' action"
                    )
                await context.execute_javascript(
                    f"window.scrollBy(0, {scroll_amount});"
                )
                direction = "down" if scroll_amount > 0 else "up"
                return ToolResult(
                    output=f"Scrolled {direction} by {abs(scroll_amount)} pixels"
                )

            elif action == "switch_tab":
                if tab_id is None:
                    return ToolResult(
                        error="Tab ID is required for 'switch_tab' action"
                    )
                await context.switch_to_tab(tab_id)
                return ToolResult(output=f"Switched to tab {tab_id}")

            elif action == "new_tab":
                if not url:
                    return ToolResult(error="URL is required for 'new_tab' action")
                await context.create_new_tab(url)
                return ToolResult(output=f"Opened new tab with URL {url}")

            elif action == "close_tab":
                await context.close_current_tab()
                return ToolResult(output="Closed current tab")

            elif action == "refresh":
                await context.refresh_page()
                return ToolResult(output="Refreshed the page")

            else:
                return ToolResult(error=f"Unsupported action: {action}")
        except Exception as e:
            return ToolResult(error=f"Browser action '{action}' failed: {str(e)}")

    async def _get_current_state() -> ToolResult:
        """Get the current state of the browser."""
        try:
            context = await _ensure_browser_initialized()
            state = await context.get_state()
            state_info = {
                "url": state.url,
                "title": state.title,
                "tabs": [tab.model_dump() for tab in state.tabs],
                "interactive_elements": state.element_tree.clickable_elements_to_string(),
            }
            return ToolResult(output=json.dumps(state_info))
        except Exception as e:
            return ToolResult(error=f"Failed to get browser state: {str(e)}")

    async def _cleanup() -> None:
        """Clean up the browser."""

        async with browser_use._state["lock"]:
            if browser_use._state["context"]:
                await browser_use._state["context"].close()
                browser_use._state["context"] = None
                browser_use._state["dom_service"] = None
            if browser_use._state["browser"]:
                await browser_use._state["browser"].close()
                browser_use._state["browser"] = None
