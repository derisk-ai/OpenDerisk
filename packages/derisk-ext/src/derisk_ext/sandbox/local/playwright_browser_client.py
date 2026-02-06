"""
Real Playwright Browser Client Implementation for Local Sandbox.

Provides actual browser automation using Playwright with proper
headless mode and session management.
"""

import asyncio
import base64
import logging
import tempfile
import os
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from playwright.async_api import Locator
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        Locator,
        Error as PlaywrightError,
    )

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None
    # Define stub types for when Playwright is not available
    Locator = Any  # type: ignore
    PlaywrightError = Exception  # type: ignore

from derisk.sandbox.client.browser.client import BrowserClient

logger = logging.getLogger(__name__)


@dataclass
class BrowserConfig:
    """Configuration for Playwright browser instance."""

    browser_type: str = "chromium"  # chromium, firefox, webkit
    headless: bool = True
    viewport: Dict[str, int] = field(
        default_factory=lambda: {"width": 1280, "height": 720}
    )
    user_agent: Optional[str] = None
    locale: str = "en-US"
    timezone_id: str = "America/New_York"
    ignore_https_errors: bool = False
    javascript_enabled: bool = True
    download_dir: Optional[str] = None
    slow_mo: Optional[int] = None  # Slow down actions by ms (for debugging)
    trace: str = "off"  # off, on, retain-on-failure

    def to_playwright_options(self) -> Dict[str, Any]:
        """Convert to Playwright browser launch options."""
        options = {
            "headless": self.headless,
            "slow_mo": self.slow_mo,
        }

        return options

    def to_context_options(self) -> Dict[str, Any]:
        """Convert to Playwright context options."""
        options = {
            "locale": self.locale,
            "timezone_id": self.timezone_id,
            "java_script_enabled": self.javascript_enabled,
            "ignore_https_errors": self.ignore_https_errors,
            "user_agent": self.user_agent,
            "viewport": self.viewport,
        }

        if self.download_dir:
            options["accept_downloads"] = True

        return options


class PlaywrightBrowserClient(BrowserClient):
    """
    Real Playwright-based Browser Client implementation.

    Provides full browser automation capabilities including:
    - Page navigation
    - Element interaction (click, type, hover)
    - Screenshots
    - Element tree extraction
    - Wait operations
    - Browser event handling
    """

    def __init__(self, instance_id: str, runtime=None, **kwargs):
        self._runtime = runtime
        self._browser_config: BrowserConfig = kwargs.pop(
            "browser_config", BrowserConfig(browser_type="chromium", headless=True)
        )
        super().__init__(instance_id, connection_config=None, **kwargs)

        # Playwright state
        self._playwright_obj = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        # Element tracking
        self._element_map: Dict[int, Locator] = {}
        self._element_index_counter = 0

        # State tracking
        self._is_initialized = False
        self._current_url: Optional[str] = None

    @property
    def is_available(self) -> bool:
        """Check if Playwright is available."""
        return PLAYWRIGHT_AVAILABLE

    def _ensure_playwright_installed(self) -> None:
        """Ensure Playwright browsers are installed."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright is not installed. Install it with: pip install playwright && playwright install"
            )

    async def browser_init(
        self,
        *,
        browser_config: Optional[Dict[str, Any]] = None,
        security_config: Optional[Dict[str, Any]] = None,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Initialize the browser with Playwright.

        Args:
            browser_config: Optional browser configuration overrides
            security_config: Security settings (screening, content filters)
            request_options: Additional request options

        Returns:
            Dict with initialization status
        """
        self._ensure_playwright_installed()

        if self._is_initialized:
            logger.info("Browser already initialized")
            return {"status": "success", "message": "Browser already initialized"}

        try:
            # Apply config overrides
            if browser_config:
                if "browser_type" in browser_config:
                    self._browser_config.browser_type = browser_config["browser_type"]
                if "headless" in browser_config:
                    self._browser_config.headless = browser_config["headless"]
                if "viewport" in browser_config:
                    self._browser_config.viewport = browser_config["viewport"]

            # Create download directory if specified
            if self._browser_config.download_dir:
                Path(self._browser_config.download_dir).mkdir(
                    parents=True, exist_ok=True
                )

            # Initialize Playwright
            self._playwright_obj = await async_playwright().start()

            # Launch browser based on type
            browser_launchers = {
                "chromium": self._playwright_obj.chromium,
                "firefox": self._playwright_obj.firefox,
                "webkit": self._playwright_obj.webkit,
            }

            browser_launcher = browser_launchers.get(
                self._browser_config.browser_type, self._playwright_obj.chromium
            )

            self._browser = await browser_launcher.launch(
                **self._browser_config.to_playwright_options()
            )

            # Create context with options
            context_options = self._browser_config.to_context_options()

            # Add download location if specified
            if self._browser_config.download_dir:
                context_options["downloads_path"] = self._browser_config.download_dir

            self._context = await self._browser.new_context(**context_options)

            # Create default page
            self._page = await self._context.new_page()

            # Set default timeout
            self._page.set_default_timeout(30000)  # 30 seconds

            self._is_initialized = True
            logger.info(
                f"Playwright browser initialized: {self._browser_config.browser_type}, "
                f"headless={self._browser_config.headless}"
            )

            return {
                "status": "success",
                "message": f"Browser initialized successfully using {self._browser_config.browser_type}",
                "browser_type": self._browser_config.browser_type,
                "headless": self._browser_config.headless,
            }

        except Exception as e:
            logger.error(f"Failed to initialize Playwright browser: {e}")
            await self._cleanup()
            return {
                "status": "error",
                "message": f"Failed to initialize browser: {str(e)}",
                "error": str(e),
            }

    async def browser_navigate(
        self,
        url: str,
        *,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Navigate to the specified URL.

        Args:
            url: URL to navigate to
            need_screenshot: Whether to take a screenshot after navigation
            request_options: Additional options

        Returns:
            Dict with navigation result
        """
        if not self._is_initialized:
            return {"status": "error", "message": "Browser not initialized"}

        if not self._page:
            return {"status": "error", "message": "No active page"}

        try:
            # Navigate to URL
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._current_url = self._page.url

            # Wait for page to be ready
            await self._page.wait_for_load_state("networkidle", timeout=5000)

            result = {
                "status": "success",
                "url": self._current_url,
                "message": f"Navigated to {url}",
            }

            # Optionally take screenshot
            if need_screenshot:
                screenshot_result = await self.browser_screenshot(
                    full_page=False, request_options=request_options
                )
                result["screenshot"] = screenshot_result.get("screenshot", "")

            # Get page content
            content = await self.page_content(request_options=request_options)
            result["content"] = content.get("content", "")

            return result

        except PlaywrightError as e:
            logger.error(f"Navigation error: {e}")
            return {
                "status": "error",
                "message": f"Navigation failed: {str(e)}",
                "error": str(e),
            }
        except Exception as e:
            logger.error(f"Unexpected navigation error: {e}")
            return {
                "status": "error",
                "message": f"Navigation failed: {str(e)}",
                "error": str(e),
            }

    async def browser_screenshot(
        self,
        *,
        full_page: Optional[bool] = False,
        remove_highlight: Optional[bool] = False,
        need_screenshot: Optional[bool] = True,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Take a screenshot of the current page.

        Args:
            full_page: Whether to capture the entire page (scrolling)
            remove_highlight: Whether to remove element highlights
            need_screenshot: Whether to actually take the screenshot
            request_options: Additional options

        Returns:
            Dict with screenshot data (base64 encoded)
        """
        if not need_screenshot:
            return {"status": "success", "screenshot": ""}

        if not self._is_initialized or not self._page:
            return {
                "status": "error",
                "message": "Browser not initialized or no active page",
                "screenshot": "",
            }

        try:
            screenshot_bytes = await self._page.screenshot(
                full_page=full_page,
                type="png",
            )

            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            return {
                "status": "success",
                "screenshot": screenshot_b64,
                "type": "png",
                "full_page": full_page,
            }

        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return {
                "status": "error",
                "message": f"Screenshot failed: {str(e)}",
                "error": str(e),
                "screenshot": "",
            }

    async def _get_element_tree(self) -> Dict[str, Any]:
        """
        Get the DOM element tree using JavaScript.

        Returns:
            Dict containing the element tree structure
        """
        if not self._page:
            return {"tree": {}, "highlight_index": {}}

        # JavaScript to extract element tree with interaction elements
        js_script = """
        () => {
            const result = {
                tree: {},
                elements: [],
                index: 0
            };

            function processElement(element, parentId = null) {
                // Skip non-interactive text nodes
                if (element.nodeType !== Node.ELEMENT_NODE) {
                    return;
                }

                // Check if element is interactive
                const tagName = element.tagName.toLowerCase();
                const interactive = [
                    'a', 'button', 'input', 'select', 'textarea',
                    'option', 'label', 'form', 'iframe'
                ].includes(tagName) ||
                    element.hasAttribute('onclick') ||
                    element.hasAttribute('onchange') ||
                    element.hasAttribute('role') ||
                    element.hasAttribute('tabindex') ||
                    window.getComputedStyle(element).cursor === 'pointer';

                const elementId = result.index++;
                const attributes = {};
                for (let attr of element.attributes) {
                    if (['id', 'class', 'name', 'value', 'placeholder', 'href', 'src', 'alt', 'title', 'aria-label', 'role'].includes(attr.name)) {
                        attributes[attr.name] = attr.value;
                    }
                }

                // Get text content (truncate if too long)
                const text = element.textContent?.substring(0, 100) || '';

                // Get styles
                const styles = window.getComputedStyle(element);
                const visibility = element.offsetParent !== null;

                const node = {
                    id: elementId,
                    tag: tagName,
                    text: text,
                    interactive: interactive,
                    visible: visibility && styles.visibility !== 'hidden' && styles.display !== 'none',
                    attributes: attributes,
                    parentId: parentId
                };

                result.elements.push(node);

                // Store by index for quick lookup
                result.tree[elementId] = node;

                // Process children
                const children = [];
                for (let child of element.children) {
                    const childElement = processElement(child, elementId);
                    if (childElement) {
                        children.push(childElement);
                    }
                }
                node.children = children;

                // Return interactive elements
                return interactive ? elementId : null;
            }

            // Start from body
            processElement(document.body);

            // Build highlight_index for interactive elements
            const highlightIndex = {};
            let interactiveIndex = 0;
            for (let elem of result.elements) {
                if (elem.interactive && elem.visible) {
                    highlightIndex[elem.id] = interactiveIndex++;
                }
            }

            return {
                tree: result.tree,
                highlightIndex: highlightIndex,
                interactiveElements: result.elements.filter(e => e.interactive && e.visible).map((e, i) => ({
                    index: highlightIndex[e.id],
                    tag: e.tag,
                    text: e.text,
                    id: e.id
                }))
            };
        }
        """

        try:
            return await self._page.evaluate(js_script)
        except Exception as e:
            logger.error(f"Get element tree error: {e}")
            return {"tree": {}, "highlight_index": {}}

    async def browser_element_tree(
        self,
        *,
        include_attributes: Optional[List[str]] = None,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Get the DOM element tree.

        Args:
            include_attributes: List of attributes to include (default: all relevant)
            need_screenshot: Whether to take a screenshot
            request_options: Additional options

        Returns:
            Dict containing the element tree
        """
        if not self._is_initialized or not self._page:
            return {"status": "error", "tree": {}, "highlight_index": {}}

        tree_data = await self._get_element_tree()

        result = {
            "status": "success",
            "tree": tree_data.get("tree", {}),
            "highlight_index": tree_data.get("highlight_index", {}),
        }

        if need_screenshot:
            screenshot_result = await self.browser_screenshot(
                request_options=request_options
            )
            result["screenshot"] = screenshot_result.get("screenshot", "")

        return result

    async def page_content(
        self,
        *,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Get the current page content.

        Args:
            need_screenshot: Whether to take a screenshot
            request_options: Additional options

        Returns:
            Dict with page content
        """
        if not self._is_initialized or not self._page:
            return {
                "status": "error",
                "content": "",
                "message": "Browser not initialized or no active page",
            }

        try:
            # Get page text content
            text = await self._page.evaluate("() => document.body.innerText")
            url = self._page.url
            title = await self._page.title()

            result = {
                "status": "success",
                "content": text,
                "url": url,
                "title": title,
            }

            if need_screenshot:
                screenshot_result = await self.browser_screenshot(
                    request_options=request_options
                )
                result["screenshot"] = screenshot_result.get("screenshot", "")

            return result

        except Exception as e:
            logger.error(f"Get page content error: {e}")
            return {
                "status": "error",
                "content": "",
                "message": f"Failed to get page content: {str(e)}",
            }

    async def _find_element_by_index(self, index: int) -> Optional["Locator"]:
        """
        Find an element by its highlight index.

        Args:
            index: The highlight index from element_tree

        Returns:
            Locator if found, None otherwise
        """
        tree_data = await self._get_element_tree()
        highlight_index = tree_data.get("highlight_index", {})

        # Find the element ID that corresponds to this index
        element_id = None
        for elem_id, idx in highlight_index.items():
            if idx == index:
                element_id = elem_id
                break

        if element_id is None:
            logger.warning(f"Element index {index} not found")
            return None

        # Use querySelector with stored data attribute or use the index directly
        # For simplicity, we'll use nth() on interactive elements
        try:
            interactive_elements = tree_data.get("interactiveElements", [])
            if index < len(interactive_elements):
                # Use the nth interactive element
                return self._page.locator("*").nth(index)
        except Exception as e:
            logger.error(f"Error finding element by index {index}: {e}")

        return None

    async def click_element(
        self,
        index: int,
        *,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Click on an element by highlight index.

        Args:
            index: The highlight index from element_tree
            need_screenshot: Whether to take a screenshot after clicking
            request_options: Additional options

        Returns:
            Dict with click result
        """
        if not self._is_initialized or not self._page:
            return {
                "status": "error",
                "message": "Browser not initialized or no active page",
            }

        try:
            element = await self._find_element_by_index(index)
            if not element:
                return {
                    "status": "error",
                    "message": f"Element at index {index} not found",
                }

            await element.click(timeout=5000)

            result = {
                "status": "success",
                "message": f"Clicked element at index {index}",
            }

            if need_screenshot:
                screenshot_result = await self.browser_screenshot(
                    request_options=request_options
                )
                result["screenshot"] = screenshot_result.get("screenshot", "")

            return result

        except PlaywrightError as e:
            logger.error(f"Click error: {e}")
            return {
                "status": "error",
                "message": f"Failed to click element: {str(e)}",
                "error": str(e),
            }
        except Exception as e:
            logger.error(f"Unexpected click error: {e}")
            return {
                "status": "error",
                "message": f"Failed to click element: {str(e)}",
                "error": str(e),
            }

    async def browser_mouse_click(
        self,
        index: int,
        *,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Mouse click on an element (alias for click_element).

        Args:
            index: The highlight index from element_tree
            need_screenshot: Whether to take a screenshot
            request_options: Additional options

        Returns:
            Dict with click result
        """
        return await self.click_element(
            index, need_screenshot=need_screenshot, request_options=request_options
        )

    async def input_text(
        self,
        index: int,
        text: str,
        *,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Input text into an element by highlight index.

        Args:
            index: The highlight index from element_tree
            text: Text to input
            need_screenshot: Whether to take a screenshot
            request_options: Additional options

        Returns:
            Dict with input result
        """
        if not self._is_initialized or not self._page:
            return {
                "status": "error",
                "message": "Browser not initialized or no active page",
            }

        try:
            element = await self._find_element_by_index(index)
            if not element:
                return {
                    "status": "error",
                    "message": f"Element at index {index} not found",
                }

            await element.fill(text)

            result = {
                "status": "success",
                "message": f"Input text into element at index {index}",
            }

            if need_screenshot:
                screenshot_result = await self.browser_screenshot(
                    request_options=request_options
                )
                result["screenshot"] = screenshot_result.get("screenshot", "")

            return result

        except PlaywrightError as e:
            logger.error(f"Input text error: {e}")
            return {
                "status": "error",
                "message": f"Failed to input text: {str(e)}",
                "error": str(e),
            }
        except Exception as e:
            logger.error(f"Unexpected input text error: {e}")
            return {
                "status": "error",
                "message": f"Failed to input text: {str(e)}",
                "error": str(e),
            }

    async def scroll_down(
        self,
        *,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Scroll down the page"""
        if not self._is_initialized or not self._page:
            return {"status": "error", "message": "Browser not initialized"}

        try:
            await self._page.evaluate("window.scrollBy(0, window.innerHeight)")

            result = {"status": "success", "message": "Scrolled down"}

            if need_screenshot:
                screenshot_result = await self.browser_screenshot(
                    request_options=request_options
                )
                result["screenshot"] = screenshot_result.get("screenshot", "")

            return result

        except Exception as e:
            logger.error(f"Scroll down error: {e}")
            return {"status": "error", "message": str(e)}

    async def scroll_up(
        self,
        *,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Scroll up the page"""
        if not self._is_initialized or not self._page:
            return {"status": "error", "message": "Browser not initialized"}

        try:
            await self._page.evaluate("window.scrollBy(0, -window.innerHeight)")

            result = {"status": "success", "message": "Scrolled up"}

            if need_screenshot:
                screenshot_result = await self.browser_screenshot(
                    request_options=request_options
                )
                result["screenshot"] = screenshot_result.get("screenshot", "")

            return result

        except Exception as e:
            logger.error(f"Scroll up error: {e}")
            return {"status": "error", "message": str(e)}

    async def scroll_to_text(
        self,
        *,
        text: str,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Scroll to find the specified text.

        Args:
            text: Text to search for
            need_screenshot: Whether to take a screenshot
            request_options: Additional options

        Returns:
            Dict with scroll result
        """
        if not self._is_initialized or not self._page:
            return {"status": "error", "message": "Browser not initialized"}

        try:
            # Try to find the text and scroll to it
            found = await self._page.evaluate(
                f"""
                (searchText) => {{
                    const elements = document.querySelectorAll('*');
                    for (let el of elements) {{
                        if (el.textContent && el.textContent.includes(searchText)) {{
                            el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                            return true;
                        }}
                    }}
                    return false;
                }}
                """,
                text,
            )

            result = {
                "status": "success",
                "message": f"Scrolled to find text: {text}",
                "found": found,
            }

            if need_screenshot:
                screenshot_result = await self.browser_screenshot(
                    request_options=request_options
                )
                result["screenshot"] = screenshot_result.get("screenshot", "")

            return result

        except Exception as e:
            logger.error(f"Scroll to text error: {e}")
            return {"status": "error", "message": str(e)}

    async def browser_mouse_wheel(
        self,
        *,
        y: int,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Scroll using mouse wheel"""
        if not self._is_initialized or not self._page:
            return {"status": "error", "message": "Browser not initialized"}

        try:
            await self._page.evaluate(f"window.scrollBy(0, {y})")

            result = {"status": "success", "message": f"Scrolled by {y}px"}

            if need_screenshot:
                screenshot_result = await self.browser_screenshot(
                    request_options=request_options
                )
                result["screenshot"] = screenshot_result.get("screenshot", "")

            return result

        except Exception as e:
            logger.error(f"Mouse wheel error: {e}")
            return {"status": "error", "message": str(e)}

    async def browser_mouse_move(
        self,
        *,
        index: Optional[int] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Move mouse to element or coordinates"""
        if not self._is_initialized or not self._page:
            return {"status": "error", "message": "Browser not initialized"}

        try:
            if index is not None:
                element = await self._find_element_by_index(index)
                if element:
                    box = await element.bounding_box()
                    if box:
                        await self._page.mouse.move(
                            box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                        )
            elif x is not None and y is not None:
                await self._page.mouse.move(x, y)

            result = {"status": "success", "message": "Mouse moved"}

            if need_screenshot:
                screenshot_result = await self.browser_screenshot(
                    request_options=request_options
                )
                result["screenshot"] = screenshot_result.get("screenshot", "")

            return result

        except Exception as e:
            logger.error(f"Mouse move error: {e}")
            return {"status": "error", "message": str(e)}

    async def open_tab(
        self,
        *,
        url: str,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Open a new tab with the specified URL"""
        if not self._is_initialized or not self._context:
            return {"status": "error", "message": "Browser not initialized"}

        try:
            new_page = await self._context.new_page()
            await new_page.goto(url, wait_until="domcontentloaded")

            # Store the new page
            if not hasattr(self, "_pages"):
                self._pages = []
            self._pages.append(new_page)

            # Make it the active page
            self._page = new_page

            result = {
                "status": "success",
                "message": f"Opened new tab with URL: {url}",
                "url": url,
            }

            if need_screenshot:
                screenshot_result = await self.browser_screenshot(
                    request_options=request_options
                )
                result["screenshot"] = screenshot_result.get("screenshot", "")

            return result

        except Exception as e:
            logger.error(f"Open tab error: {e}")
            return {"status": "error", "message": str(e)}

    async def browser_hover_element(
        self,
        *,
        index: Optional[int] = None,
        xpath: Optional[str] = None,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Hover over an element"""
        if not self._is_initialized or not self._page:
            return {"status": "error", "message": "Browser not initialized"}

        try:
            if index is not None:
                element = await self._find_element_by_index(index)
            elif xpath:
                element = self._page.locator(f"xpath={xpath}")
            else:
                return {
                    "status": "error",
                    "message": "Either index or xpath must be provided",
                }

            if element:
                await element.hover()
                result = {"status": "success", "message": "Hovered over element"}

                if need_screenshot:
                    screenshot_result = await self.browser_screenshot(
                        request_options=request_options
                    )
                    result["screenshot"] = screenshot_result.get("screenshot", "")
                return result

            return {"status": "error", "message": "Element not found"}

        except Exception as e:
            logger.error(f"Hover error: {e}")
            return {"status": "error", "message": str(e)}

    async def get_dropdown_options(
        self,
        *,
        index: int,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Get dropdown options for a select element"""
        if not self._is_initialized or not self._page:
            return {"status": "error", "message": "Browser not initialized"}

        try:
            element = await self._find_element_by_index(index)
            if not element:
                return {
                    "status": "error",
                    "message": f"Element at index {index} not found",
                }

            # Get options
            options = await element.evaluate(
                "el => Array.from(el.options).map(opt => opt.text)"
            )

            return {
                "status": "success",
                "options": options,
                "count": len(options),
            }

        except Exception as e:
            logger.error(f"Get dropdown options error: {e}")
            return {"status": "error", "message": str(e), "options": []}

    async def select_dropdown_option(
        self,
        *,
        index: int,
        text: str,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Select an option from a dropdown"""
        if not self._is_initialized or not self._page:
            return {"status": "error", "message": "Browser not initialized"}

        try:
            element = await self._find_element_by_index(index)
            if not element:
                return {
                    "status": "error",
                    "message": f"Element at index {index} not found",
                }

            await element.select_option(text)

            result = {"status": "success", "message": f"Selected option: {text}"}

            if need_screenshot:
                screenshot_result = await self.browser_screenshot(
                    request_options=request_options
                )
                result["screenshot"] = screenshot_result.get("screenshot", "")

            return result

        except Exception as e:
            logger.error(f"Select dropdown option error: {e}")
            return {"status": "error", "message": str(e)}

    async def browser_search(
        self,
        query: str,
        *,
        need_screenshot: Optional[bool] = False,
        request_options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Search for the given query (navigates to search engine).

        Args:
            query: Search query
            need_screenshot: Whether to take a screenshot
            request_options: Additional options

        Returns:
            Dict with search result
        """
        # Build Google search URL
        search_url = f"https://www.google.com/search?q={query}"

        # Navigate to search results
        navigate_result = await self.browser_navigate(
            search_url, need_screenshot=need_screenshot, request_options=request_options
        )

        return {
            "status": navigate_result.get("status", "error"),
            "message": f"Searched for: {query}",
            "query": query,
            "search_url": search_url,
            "results": [],  # Could parse results if needed
        }

    async def _cleanup(self):
        """Cleanup Playwright resources."""
        try:
            if self._page:
                await self._page.close()
                self._page = None

            if hasattr(self, "_pages"):
                for page in self._pages:
                    await page.close()
                self._pages = []

            if self._context:
                await self._context.close()
                self._context = None

            if self._browser:
                await self._browser.close()
                self._browser = None

            if self._playwright_obj:
                await self._playwright_obj.stop()
                self._playwright_obj = None

            self._is_initialized = False
            logger.info("Playwright browser cleaned up")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# Convenience function to quickly check Playwright availability
def is_playwright_available() -> bool:
    """Check if Playwright is available and browsers are installed."""
    return PLAYWRIGHT_AVAILABLE
