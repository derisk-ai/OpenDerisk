"""
浏览器工具模块

提供浏览器自动化工具：
- browser_navigate: 导航到指定URL
- browser_save_screenshot: 保存截图
- browser_click_element: 点击元素
- browser_input_text: 输入文本
- browser_get_dropdown_options: 获取下拉菜单选项
- browser_select_dropdown_option: 选择下拉菜单选项
- browser_mouse_wheel: 鼠标滚轮
- browser_page_content: 获取页面内容
- browser_mouse_move: 鼠标移动
- browser_hover_element: 鼠标悬停
- browser_save_image: 保存图片
- browser_open_tab: 打开新标签页
"""

from typing import TYPE_CHECKING, Dict, Any, Optional, List
import json
import logging

from pydantic import BaseModel

from .base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel, ToolEnvironment, ToolSource
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

if TYPE_CHECKING:
    from ...registry import ToolRegistry

logger = logging.getLogger(__name__)

# 浏览器工具名称列表
BROWSER_TOOLS: List[str] = [
    "browser_navigate",
    "browser_click_element",
    "browser_input_text",
    "browser_get_dropdown_options",
    "browser_select_dropdown_option",
    "browser_mouse_wheel",
    "browser_page_content",
    "browser_mouse_move",
    "browser_hover_element",
    "browser_save_image",
    "browser_open_tab",
    "browser_save_screenshot",
]


class BrowserResult(BaseModel):
    """浏览器操作结果"""

    type: str = "browser"
    elements: str = ""
    url: str = ""
    title: str = ""
    screenshot: str = ""
    success: bool = True
    error: str = ""
    image_url: str = ""
    analysis: Optional[Dict] = None


class ScreenshotAnalysis(BaseModel):
    """截图分析结果"""

    text: str = ""
    summary: str = ""


async def analyze_image(
    image: str,
    prompt: Optional[str] = None,
    model: str = "aistudio/Qwen3-VL-235B-A22B-Instruct(高保)",
) -> Dict[str, Any]:
    """分析图片"""
    from derisk.model.image_analysis.analyzer import ImageAnalyzer
    from derisk.model import DefaultLLMClient

    llm_client = DefaultLLMClient()
    analyzer = ImageAnalyzer(llm_client=llm_client, model_name=model)

    import base64

    image_bytes = base64.b64decode(image)

    analysis = await analyzer.analyze_screenshot_with_extractor(
        image_data=image_bytes, prompt=prompt, model_name=model
    )

    return {"text": analysis.text, "summary": analysis.summary}


async def _parse_browser_response(
    res,
    operation_name: str,
    input_kwargs: Optional[Dict] = None,
    client=None,
    analyze_screenshot: bool = False,
    analysis_prompt: Optional[str] = None,
) -> BrowserResult:
    """解析浏览器操作响应"""
    try:
        data = (res or {}).get("data") or {}
        state_data_str = data.get("stateData")
        state_data = {}
        if state_data_str:
            try:
                state_data = json.loads(state_data_str)
            except Exception as json_exc:
                logger.warning(
                    f"{operation_name} - Failed to parse stateData: {json_exc}"
                )

        if not data.get("screenshot"):
            logger.error(
                f"{operation_name} - Browser Failed to get screenshot: {res}, input_kwargs: {input_kwargs}"
            )

        result = BrowserResult(
            elements=state_data.get("element_tree", "无"),
            url=data.get("url", ""),
            title=data.get("title", ""),
            screenshot=data.get("screenshot", ""),
            success=True,
        )

        if analyze_screenshot and result.success and result.screenshot:
            try:
                analysis_result = await analyze_image(
                    image=result.screenshot,
                    prompt=analysis_prompt,
                    model="aistudio/Qwen3-VL-235B-A22B-Instruct(高保)",
                )
                result.analysis = analysis_result
                logger.info(
                    f"{operation_name} - Screenshot analysis completed successfully"
                )
            except Exception as analysis_exc:
                logger.warning(
                    f"{operation_name} - Screenshot analysis failed: {analysis_exc}"
                )

        return result

    except Exception as exc:
        logger.error(f"{operation_name} - Failed to parse response: {exc}")
        return BrowserResult(
            success=False,
            error=f"错误: 解析浏览器响应失败: {exc}",
        )


class BrowserNavigateTool(SandboxToolBase):
    """浏览器导航工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_navigate",
            display_name="Browser Navigate",
            description="浏览器导航, 打开指定网址",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["browser", "navigate", "url"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "浏览器打开网址"},
                "analyze_screenshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否对截图进行AI语义分析",
                },
                "analysis_prompt": {
                    "type": "string",
                    "default": None,
                    "description": "自定义图片分析提示词",
                },
            },
            "required": ["url"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        url = args["url"]
        analyze_screenshot = args.get("analyze_screenshot", False)
        analysis_prompt = args.get("analysis_prompt")

        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法操作浏览器",
                tool_name=self.name,
            )

        try:
            await client.browser.browser_init()
            res = await client.browser.browser_navigate(
                url, need_screenshot=True, need_dom_data=True
            )
            result = await _parse_browser_response(
                res,
                "browser_navigate",
                {"url": url},
                client=client,
                analyze_screenshot=analyze_screenshot,
                analysis_prompt=analysis_prompt,
            )
            return ToolResult.ok(output=result.model_dump(), tool_name=self.name)
        except Exception as e:
            logger.error(f"Browser Tool browser_navigate Failed! {e}")
            return ToolResult.fail(
                error=f"错误: 浏览器打开网址失败: {e}", tool_name=self.name
            )


class BrowserSaveScreenshotTool(SandboxToolBase):
    """浏览器截图工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_save_screenshot",
            display_name="Browser Screenshot",
            description="保存浏览器图片",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["browser", "screenshot", "image"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "need_screenshot": {"type": "boolean", "description": "是否需要截图"},
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        need_screenshot = args.get("need_screenshot", True)

        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法操作浏览器",
                tool_name=self.name,
            )

        try:
            res = await client.browser.browser_screenshot(
                remove_highlight=True, need_screenshot=need_screenshot
            )
            data = (res or {}).get("data") or {}
            state_data_str = data.get("stateData")
            state_data = {}
            if state_data_str:
                try:
                    state_data = json.loads(state_data_str)
                except Exception:
                    pass

            result = BrowserResult(
                elements=state_data.get("element_tree", "无"),
                url=data.get("url") or "",
                title=data.get("title") or "",
                screenshot=data.get("result") or "",
                success=True,
            )
            return ToolResult.ok(output=result.model_dump(), tool_name=self.name)
        except Exception as exc:
            return ToolResult.fail(
                error=f"错误: 浏览器截屏失败: {exc}", tool_name=self.name
            )


class BrowserClickElementTool(SandboxToolBase):
    """浏览器点击元素工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_click_element",
            display_name="Browser Click",
            description="浏览器点击元素",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["browser", "click", "element"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "description": "需要点击元素的索引，返回的dom结构中的，eg:1,2,3 表示第一个元素，必须要>=1",
                },
                "analyze_screenshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否对截图进行AI语义分析",
                },
                "analysis_prompt": {
                    "type": "string",
                    "default": None,
                    "description": "自定义图片分析提示词",
                },
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        index = args["index"]
        analyze_screenshot = args.get("analyze_screenshot", False)
        analysis_prompt = args.get("analysis_prompt")

        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法操作浏览器",
                tool_name=self.name,
            )

        try:
            res = await client.browser.browser_mouse_click(
                index=index, need_screenshot=True
            )
            result = await _parse_browser_response(
                res,
                "click_element",
                {"index": index},
                client=client,
                analyze_screenshot=analyze_screenshot,
                analysis_prompt=analysis_prompt,
            )
            return ToolResult.ok(output=result.model_dump(), tool_name=self.name)
        except Exception as exc:
            logger.error(f"Browser Tool click_element Failed! {exc}")
            return ToolResult.fail(
                error=f"错误: 浏览器点击元素失败: {exc}", tool_name=self.name
            )


class BrowserInputTextTool(SandboxToolBase):
    """浏览器输入文本工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_input_text",
            display_name="Browser Input",
            description="浏览器输入文本",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["browser", "input", "text"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "需要点击元素的索引"},
                "text": {"type": "string", "description": "输入文本"},
                "analyze_screenshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否对截图进行AI语义分析",
                },
                "analysis_prompt": {
                    "type": "string",
                    "default": None,
                    "description": "自定义图片分析提示词",
                },
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        index = args["index"]
        text = args["text"]
        analyze_screenshot = args.get("analyze_screenshot", False)
        analysis_prompt = args.get("analysis_prompt")

        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法操作浏览器",
                tool_name=self.name,
            )

        try:
            res = await client.browser.input_text(
                index=index, text=text, need_screenshot=True
            )
            result = await _parse_browser_response(
                res,
                "input_text",
                {"index": index, "text": text},
                client=client,
                analyze_screenshot=analyze_screenshot,
                analysis_prompt=analysis_prompt,
            )
            return ToolResult.ok(output=result.model_dump(), tool_name=self.name)
        except Exception as exc:
            logger.error(f"Browser Tool input_text Failed! {exc}")
            return ToolResult.fail(
                error=f"错误: 浏览器输入文本失败:{exc}", tool_name=self.name
            )


class BrowserGetDropdownOptionsTool(SandboxToolBase):
    """浏览器获取下拉菜单选项工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_get_dropdown_options",
            display_name="Browser Get Dropdown",
            description="浏览器获取下拉菜单",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["browser", "dropdown", "options"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "需要点击元素的索引"},
                "analyze_screenshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否对截图进行AI语义分析",
                },
                "analysis_prompt": {
                    "type": "string",
                    "default": None,
                    "description": "自定义图片分析提示词",
                },
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        index = args["index"]
        analyze_screenshot = args.get("analyze_screenshot", False)
        analysis_prompt = args.get("analysis_prompt")

        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法操作浏览器",
                tool_name=self.name,
            )

        try:
            res = await client.browser.get_dropdown_options(
                index=index, need_screenshot=True
            )
            result = await _parse_browser_response(
                res,
                "get_dropdown_options",
                {"index": index},
                client=client,
                analyze_screenshot=analyze_screenshot,
                analysis_prompt=analysis_prompt,
            )
            return ToolResult.ok(output=result.model_dump(), tool_name=self.name)
        except Exception as exc:
            logger.error(f"Browser Tool get_dropdown_options Failed! {exc}")
            return ToolResult.fail(
                error=f"错误: 浏览器获取下拉菜单:{exc}", tool_name=self.name
            )


class BrowserSelectDropdownOptionTool(SandboxToolBase):
    """浏览器选择下拉菜单选项工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_select_dropdown_option",
            display_name="Browser Select Dropdown",
            description="浏览器选择下拉菜单",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["browser", "dropdown", "select"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "需要点击元素的索引"},
                "text": {"type": "string", "description": "选择的下拉菜单的选项文本"},
                "analyze_screenshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否对截图进行AI语义分析",
                },
                "analysis_prompt": {
                    "type": "string",
                    "default": None,
                    "description": "自定义图片分析提示词",
                },
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        index = args["index"]
        text = args["text"]
        analyze_screenshot = args.get("analyze_screenshot", False)
        analysis_prompt = args.get("analysis_prompt")

        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法操作浏览器",
                tool_name=self.name,
            )

        try:
            res = await client.browser.select_dropdown_option(
                index=index, text=text, need_screenshot=True
            )
            result = await _parse_browser_response(
                res,
                "select_dropdown_option",
                {"index": index, "text": text},
                client=client,
                analyze_screenshot=analyze_screenshot,
                analysis_prompt=analysis_prompt,
            )
            return ToolResult.ok(output=result.model_dump(), tool_name=self.name)
        except Exception as exc:
            logger.error(f"Browser Tool select_dropdown_option Failed! {exc}")
            return ToolResult.fail(
                error=f"错误: 浏览器选择下拉菜单:{exc}", tool_name=self.name
            )


class BrowserMouseWheelTool(SandboxToolBase):
    """浏览器鼠标滚轮工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_mouse_wheel",
            display_name="Browser Mouse Wheel",
            description="浏览器鼠标滚动",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["browser", "mouse", "scroll"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "y": {
                    "type": "integer",
                    "description": "浏览器页面滚动的值，大于0为向下滚动，小于0为向上滚动",
                },
                "analyze_screenshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否对截图进行AI语义分析",
                },
                "analysis_prompt": {
                    "type": "string",
                    "default": None,
                    "description": "自定义图片分析提示词",
                },
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        y = args["y"]
        analyze_screenshot = args.get("analyze_screenshot", False)
        analysis_prompt = args.get("analysis_prompt")

        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法操作浏览器",
                tool_name=self.name,
            )

        try:
            res = await client.browser.browser_mouse_wheel(y=y, need_screenshot=True)
            result = await _parse_browser_response(
                res,
                "browser_mouse_wheel",
                {"y": y},
                client=client,
                analyze_screenshot=analyze_screenshot,
                analysis_prompt=analysis_prompt,
            )
            return ToolResult.ok(output=result.model_dump(), tool_name=self.name)
        except Exception as exc:
            logger.error(f"Browser Tool browser_mouse_wheel Failed! {exc}")
            return ToolResult.fail(
                error=f"错误: 浏览器鼠标滚动失败:{exc}", tool_name=self.name
            )


class BrowserPageContentTool(SandboxToolBase):
    """浏览器获取页面内容工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_page_content",
            display_name="Browser Page Content",
            description="查看当前页面, 获取页面内容",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["browser", "page", "content"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "need_screenshot": {"type": "boolean", "description": "是否需要截图"},
                "analyze_screenshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否对截图进行AI语义分析",
                },
                "analysis_prompt": {
                    "type": "string",
                    "default": None,
                    "description": "自定义图片分析提示词",
                },
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        need_screenshot = args.get("need_screenshot", True)
        analyze_screenshot = args.get("analyze_screenshot", False)
        analysis_prompt = args.get("analysis_prompt")

        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法操作浏览器",
                tool_name=self.name,
            )

        try:
            res = await client.browser.page_content(need_screenshot=True)
            result = await _parse_browser_response(
                res,
                "page_content",
                {"need_screenshot": need_screenshot},
                client=client,
                analyze_screenshot=analyze_screenshot,
                analysis_prompt=analysis_prompt,
            )
            return ToolResult.ok(output=result.model_dump(), tool_name=self.name)
        except Exception as exc:
            logger.error(f"Browser Tool page_content Failed! {exc}")
            return ToolResult.fail(
                error=f"错误: 查看当前页面:{exc}", tool_name=self.name
            )


class BrowserMouseMoveTool(SandboxToolBase):
    """浏览器鼠标移动工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_mouse_move",
            display_name="Browser Mouse Move",
            description="浏览器鼠标移动",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["browser", "mouse", "move"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "需要点击元素的索引"},
                "analyze_screenshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否对截图进行AI语义分析",
                },
                "analysis_prompt": {
                    "type": "string",
                    "default": None,
                    "description": "自定义图片分析提示词",
                },
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        index = args["index"]
        analyze_screenshot = args.get("analyze_screenshot", False)
        analysis_prompt = args.get("analysis_prompt")

        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法操作浏览器",
                tool_name=self.name,
            )

        try:
            res = await client.browser.browser_mouse_move(
                index=index, need_screenshot=True
            )
            result = await _parse_browser_response(
                res,
                "browser_mouse_move",
                {"index": index},
                client=client,
                analyze_screenshot=analyze_screenshot,
                analysis_prompt=analysis_prompt,
            )
            return ToolResult.ok(output=result.model_dump(), tool_name=self.name)
        except Exception as exc:
            logger.error(f"Browser Tool browser_mouse_move Failed! {exc}")
            return ToolResult.fail(
                error=f"错误: 浏览器鼠标移动:{exc}", tool_name=self.name
            )


class BrowserHoverElementTool(SandboxToolBase):
    """浏览器鼠标悬停元素工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_hover_element",
            display_name="Browser Hover",
            description="浏览器鼠标悬停元素",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["browser", "hover", "element"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "需要点击元素的索引"},
                "xpath": {"type": "string", "description": "需要点击元素的xpath"},
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        index = args.get("index")
        xpath = args.get("xpath")

        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法操作浏览器",
                tool_name=self.name,
            )

        try:
            res = await client.browser.browser_hover_element(
                index=index, xpath=xpath, need_screenshot=True
            )
            result = await _parse_browser_response(res, "browser_hover_element")
            return ToolResult.ok(output=result.model_dump(), tool_name=self.name)
        except Exception as exc:
            logger.error(f"Browser Tool browser_hover_element Failed! {exc}")
            return ToolResult.fail(
                error=f"错误: 浏览器鼠标悬停元素失败:{exc}", tool_name=self.name
            )


class BrowserSaveImageTool(SandboxToolBase):
    """浏览器保存图片工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_save_image",
            display_name="Browser Save Image",
            description="保存浏览器图片",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["browser", "image", "save"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "图片链接"},
                "title": {"type": "string", "description": "图片标题"},
                "summary": {
                    "type": "string",
                    "description": "图片的上下文摘要(100字以内)",
                },
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        image_url = args.get("image_url", "")
        title = args.get("title", "")
        summary = args.get("summary", "")

        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法操作浏览器",
                tool_name=self.name,
            )

        try:
            res = await client.browser.browser_screenshot(
                remove_highlight=True, need_screenshot=True
            )
            data = (res or {}).get("data") or {}
            result = BrowserResult(
                success=True,
                image_url=image_url,
                screenshot=data.get("result") or "",
                url=data.get("url") or "",
                title=title or "保存浏览器图片",
                elements=summary,
            )
            return ToolResult.ok(output=result.model_dump(), tool_name=self.name)
        except Exception as exc:
            return ToolResult.fail(
                error=f"错误: 浏览器截屏失败: {exc}", tool_name=self.name
            )


class BrowserOpenTabTool(SandboxToolBase):
    """浏览器打开新标签页工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_open_tab",
            display_name="Browser Open Tab",
            description="浏览器打开新页签",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            environment=ToolEnvironment.SANDBOX,
            tags=["browser", "tab", "open"],
            author="chenketing.ckt",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "打开新标签URL"},
                "analyze_screenshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否对截图进行AI语义分析",
                },
                "analysis_prompt": {
                    "type": "string",
                    "default": None,
                    "description": "自定义图片分析提示词",
                },
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        url = args["url"]
        analyze_screenshot = args.get("analyze_screenshot", False)
        analysis_prompt = args.get("analysis_prompt")

        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法操作浏览器",
                tool_name=self.name,
            )

        try:
            res = await client.browser.open_tab(url=url, need_screenshot=True)
            result = await _parse_browser_response(
                res,
                "browser_open_tab",
                {"url": url},
                client=client,
                analyze_screenshot=analyze_screenshot,
                analysis_prompt=analysis_prompt,
            )
            return ToolResult.ok(output=result.model_dump(), tool_name=self.name)
        except Exception as exc:
            logger.error(f"Browser Tool browser_open_tab Failed! {exc}")
            return ToolResult.fail(
                error=f"错误: 浏览器打开新页签:{exc}", tool_name=self.name
            )


def register_browser_tools(registry: "ToolRegistry") -> None:
    """注册所有浏览器工具"""
    registry.register(BrowserNavigateTool())
    registry.register(BrowserSaveScreenshotTool())
    registry.register(BrowserClickElementTool())
    registry.register(BrowserInputTextTool())
    registry.register(BrowserGetDropdownOptionsTool())
    registry.register(BrowserSelectDropdownOptionTool())
    registry.register(BrowserMouseWheelTool())
    registry.register(BrowserPageContentTool())
    registry.register(BrowserMouseMoveTool())
    registry.register(BrowserHoverElementTool())
    registry.register(BrowserSaveImageTool())
    registry.register(BrowserOpenTabTool())


__all__ = [
    "register_browser_tools",
    "BROWSER_TOOLS",
    "BrowserResult",
    "ScreenshotAnalysis",
    "BrowserNavigateTool",
    "BrowserSaveScreenshotTool",
    "BrowserClickElementTool",
    "BrowserInputTextTool",
    "BrowserGetDropdownOptionsTool",
    "BrowserSelectDropdownOptionTool",
    "BrowserMouseWheelTool",
    "BrowserPageContentTool",
    "BrowserMouseMoveTool",
    "BrowserHoverElementTool",
    "BrowserSaveImageTool",
    "BrowserOpenTabTool",
]
