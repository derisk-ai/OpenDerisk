import json
import logging
from dataclasses import Field
from typing import List, Optional, Dict, Any

from pydantic import BaseModel

from derisk.agent.core.sandbox.sandbox_tool_registry import sandbox_tool
from derisk.sandbox.base import SandboxBase

logger = logging.getLogger(__name__)
BROWSER_TOOLS: List[str] =["browser_navigate", "browser_click_element", "browser_input_text", "browser_get_dropdown_options", "browser_select_dropdown_option", "browser_mouse_wheel", "browser_page_content", "browser_mouse_move", "browser_hover_element", "browser_save_image", "browser_open_tab"]
class BrowserResult(BaseModel):
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
    """Complete analysis result of a screenshot"""
    text: str = ""
    summary: str = ""


@sandbox_tool(
    name="browser_navigate",
    description="浏览器导航, 打开指定网址",
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "浏览器打开网址",
            },
            "analyze_screenshot": {
                "type": "boolean",
                "description": "是否对截图进行AI语义分析",
                "default": False,
            },
            "analysis_prompt": {
                "type": "string",
                "description": "自定义图片分析提示词",
                "default": None,
            }
        },
        "required": ["url"],
    },
    owner="chenketing.ckt"
)
async def browser_navigate(
        client: SandboxBase,
        url: str,
        analyze_screenshot: bool = False,
        analysis_prompt: Optional[str] = None,
        **kwargs
) -> BrowserResult:
    """
    浏览器导航, 打开指定网址
    """

    try:
        await client.browser.browser_init()
        res = await client.browser.browser_navigate(url, need_screenshot=True, need_dom_data=True)
        return await _parse_browser_response(
            res,
            "browser_navigate",
            {"url": url},
            client=client,
            analyze_screenshot=analyze_screenshot,
            analysis_prompt=analysis_prompt
        )
        # data = res.get("data")
        # state_data = json.loads(
        #     data.get("stateData")
        # )
        # elements = state_data.get("element_tree")
        # data["domData"] = elements
        # url = data.get("url")
        # screenshot = data.get("screenshot")
        # # screenshot = await browser_screenshot(client, need_screenshot=True)
        # return BrowserResult(
        #     elements=elements,
        #     url=url,
        #     title=data.get("title"),
        #     screenshot=screenshot
        # )
    except Exception as e:
        logger.error(f"Browser Tool browser_navigate Failed! {e}")
        return BrowserResult(
            success=False,
            error=f"错误: 浏览器打开网址失败: {e}"
        )



@sandbox_tool(
    name="browser_save_screenshot",
    description="保存浏览器图片",
    input_schema={
        "type": "object",
        "properties": {
            "need_screenshot": {
                "type": "boolean",
                "description": "是否需要截图",
            },
        },
    },
    owner="chenketing.ckt"
)
async def browser_screenshot(
        client: SandboxBase,
        need_screenshot: bool = True,
        analyze: bool = False,
        analysis_prompt: Optional[str] = None,
        analysis_model: str = "aistudio/Qwen3-VL-235B-A22B-Instruct(高保)",
        **kwargs
) -> BrowserResult:
    """
    浏览器导航, 打开指定网址
    """
    if client is None:
        return BrowserResult(
            success=False,
            error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
        )

    try:
        res = await client.browser.browser_screenshot(
            remove_highlight=True,
            need_screenshot=need_screenshot,
        )
        data = (res or {}).get("data") or {}
        state_data_str = data.get("stateData")
        state_data = {}
        if state_data_str:
            try:
                state_data = json.loads(state_data_str)
            except Exception as json_exc:
                logger.warning(
                    f" Failed to parse screenshot stateData: {json_exc}")

        screenshot_data = data.get("result") or ""

        # Perform AI analysis if requested
        analysis_result = None
        if analyze and screenshot_data:
            try:
                analysis_result = await analyze_image(
                    image=screenshot_data,
                    prompt=analysis_prompt,
                    model=analysis_model
                )
            except Exception as analysis_exc:
                logger.warning(f"Screenshot analysis failed: {analysis_exc}")
                analysis_result = None

        # Create response
        browser_result = BrowserResult(
            elements=state_data.get("element_tree", "无"),
            url=data.get("url") or "",
            title=data.get("title") or "",
            screenshot=screenshot_data,
            success=True,
            analysis_result=analysis_result
        )

        # Attach analysis result if available
        if analysis_result:
            browser_result.__dict__["analysis"] = analysis_result

        return browser_result
    except Exception as exc:
        return BrowserResult(
            success=False,
            error=f"错误: 浏览器截屏失败: {exc}"
        )


@sandbox_tool(
    name="browser_click_element",
    description="浏览器点击元素",
    input_schema={
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "需要点击元素的索引，返回的dom结构中的，eg:1,2,3 表示第一个元素，必须要>=1",
            },
            "analyze_screenshot": {
                "type": "boolean",
                "description": "是否对截图进行AI语义分析",
                "default": False,
            },
            "analysis_prompt": {
                "type": "string",
                "description": "自定义图片分析提示词",
                "default": None,
            }
        },
    },
    owner="chenketing.ckt"
)
async def click_element(
        client: SandboxBase,
        index: int,
        analyze_screenshot: bool = False,
        analysis_prompt: Optional[str] = None,
        **kwargs
) -> BrowserResult:
    """
    浏览器点击元素
    """
    if client is None:
        return BrowserResult(
            success=False,
            error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
        )

    try:
        res = await client.browser.browser_mouse_click(
            index=index,
            need_screenshot=True,
        )
        return await _parse_browser_response(
            res,
            "click_element",
            {"index": index},
            client=client,
            analyze_screenshot=analyze_screenshot,
            analysis_prompt=analysis_prompt
        )
        # data = res.get("data")
        # state_data = json.loads(
        #     data.get("stateData")
        # )
        # screenshot = data.get("screenshot")
        # # screenshot = await browser_screenshot(client, need_screenshot=True)
        # elements = state_data.get("element_tree")
        # return BrowserResult(
        #     elements=elements,
        #     url=data.get("url"),
        #     title=data.get("title"),
        #     screenshot=screenshot,
        #
        # )
    except Exception as exc:
        logger.error(f"Browser Tool click_element Failed! {exc}")
        return BrowserResult(
            success=False,
            error=f"错误: 浏览器点击元素失败: {exc}"
        )


# @sandbox_tool(
#     name="scroll_up",
#     description="浏览器向上滚动",
#     input_schema={
#         "type": "object",
#         "properties": {
#             "need_screenshot": {
#                 "type": "boolean",
#                 "description": "是否需要截图",
#             },
#         },
#     },
#     owner="chenketing.ckt"
# )
# async def scroll_up(
#         client: SandboxBase,
#         need_screenshot: bool
# ) -> BrowserResult:
#     """
#     浏览器导航, 打开指定网址
#     """
#     if client is None:
#         return BrowserResult(
#             success=False,
#             error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
#         )
#
#     try:
#         logger.info(f"need_screenshot,{need_screenshot}")
#         res = await client.browser.scroll_up(
#             need_screenshot=True,
#         )
#         data = res.get("data")
#         state_data = json.loads(
#             data.get("stateData")
#         )
#         screenshot = await browser_screenshot(client, need_screenshot=True)
#         elements = state_data.get("element_tree")
#         return BrowserResult(
#             elements=elements,
#             url=data.get("url"),
#             title=data.get("title"),
#             screenshot=screenshot,
#
#         )
#     except Exception as exc:
#         return BrowserResult(
#             success=False,
#             error=f"错误: 浏览器向上滚动失败:{exc}"
#         )
#
# @sandbox_tool(
#     name="scroll_down",
#     description="浏览器向下滚动",
#     input_schema={
#         "type": "object",
#         "properties": {
#             "need_screenshot": {
#                 "type": "boolean",
#                 "description": "是否需要截图",
#             },
#         },
#     },
#     owner="chenketing.ckt"
# )
#
# async def scroll_down(
#         client: SandboxBase,
#         need_screenshot: bool
# ) -> BrowserResult:
#     """
#     浏览器导航, 打开指定网址
#     """
#     if client is None:
#         return BrowserResult(
#             success=False,
#             error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
#         )
#
#     try:
#         logger.info(f"need_screenshot,{need_screenshot}")
#         res = await client.browser.scroll_down(
#             need_screenshot=True,
#         )
#         data = res.get("data")
#         state_data = json.loads(
#             data.get("stateData")
#         )
#         screenshot = await browser_screenshot(client, need_screenshot=True)
#         elements = state_data.get("element_tree")
#         return BrowserResult(
#             elements=elements,
#             url=data.get("url"),
#             title=data.get("title"),
#             screenshot=screenshot,
#
#         )
#     except Exception as exc:
#         return BrowserResult(
#             success=False,
#             error=f"错误: 浏览器向下滚动失败:{exc}"
#         )
#
#
# @sandbox_tool(
#     name="scroll_to_text",
#     description="浏览器滚动到指定文本处",
#     input_schema={
#         "type": "object",
#         "properties": {
#             "text": {
#                 "type": "string",
#                 "description": "需要滚动到文本",
#             }
#         },
#     },
#     owner="chenketing.ckt"
# )
#
# async def scroll_to_text(
#         client: SandboxBase,
#         text: str
# ) -> BrowserResult:
#     """
#     浏览器导航, 打开指定网址
#     """
#     if client is None:
#         return BrowserResult(
#             success=False,
#             error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
#         )
#
#     try:
#         logger.info(f"scroll_to_text,{text}")
#         res = await client.browser.scroll_to_text(
#             text=text,
#             need_screenshot=True,
#         )
#         data = res.get("data")
#         state_data = json.loads(
#             data.get("stateData")
#         )
#         screenshot = await browser_screenshot(client, need_screenshot=True)
#         elements = state_data.get("element_tree")
#         return BrowserResult(
#             elements=elements,
#             url=data.get("url"),
#             title=data.get("title"),
#             screenshot=screenshot,
#
#         )
#     except Exception as exc:
#         return (BrowserResult(
#             success=False,
#             error=f"错误: 浏览器向下滚动失败:{exc}"
#         )
#     )

@sandbox_tool(
    name="browser_input_text",
    description="浏览器输入文本",
    input_schema={
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "需要点击元素的索引，返回的dom结构中的，eg:0,1,2",
            },
            "text": {
                "type": "string",
                "description": "输入文本",
            },
            "analyze_screenshot": {
                "type": "boolean",
                "description": "是否对截图进行AI语义分析",
                "default": False,
            },
            "analysis_prompt": {
                "type": "string",
                "description": "自定义图片分析提示词",
                "default": None,
            }
        },
    },
    owner="chenketing.ckt"
)

async def input_text(
        client: SandboxBase,
        index: int,
        text: str,
        analyze_screenshot: bool = False,
        analysis_prompt: Optional[str] = None,
        **kwargs
) -> BrowserResult:
    """
    浏览器输入文本
    """
    if client is None:
        return BrowserResult(
            success=False,
            error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
        )

    try:
        logger.info(f"input_text,{text}")
        res = await client.browser.input_text(
            index=index,
            text=text,
            need_screenshot=True,
        )
        return await _parse_browser_response(
            res,
            "input_text",
            {"index": index, "text": text},
            client=client,
            analyze_screenshot=analyze_screenshot,
            analysis_prompt=analysis_prompt
        )
        # data = res.get("data")
        # state_data = json.loads(
        #     data.get("stateData")
        # )
        # screenshot = data.get("screenshot")
        # # screenshot = await browser_screenshot(client, need_screenshot=True)
        # elements = state_data.get("element_tree")
        # return BrowserResult(
        #     elements=elements,
        #     url=data.get("url"),
        #     title=data.get("title"),
        #     screenshot=screenshot,
        #
        # )
    except Exception as exc:
        logger.error(f"Browser Tool input_text Failed! {exc}")
        return BrowserResult(
            success=False,
            error=f"错误: 浏览器输入文本失败:{exc}"
        )


@sandbox_tool(
    name="browser_get_dropdown_options",
    description="浏览器获取下拉菜单",
    input_schema={
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "需要点击元素的索引，返回的dom结构中的，eg:0,1,2",
            },
            "analyze_screenshot": {
                "type": "boolean",
                "description": "是否对截图进行AI语义分析",
                "default": False,
            },
            "analysis_prompt": {
                "type": "string",
                "description": "自定义图片分析提示词",
                "default": None,
            }
        },
    },
    owner="chenketing.ckt"
)

async def get_dropdown_options(
        client: SandboxBase,
        index: int,
        analyze_screenshot: bool = False,
        analysis_prompt: Optional[str] = None,
        **kwargs
) -> BrowserResult:
    """
    浏览器选择下拉菜单
    """
    if client is None:
        return BrowserResult(
            success=False,
            error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
        )

    try:
        logger.info(f"get_dropdown_options,{index}")
        res = await client.browser.get_dropdown_options(
            index=index,
            need_screenshot=True,
        )
        return await _parse_browser_response(
            res,
            "get_dropdown_options",
            {"index": index},
            client=client,
            analyze_screenshot=analyze_screenshot,
            analysis_prompt=analysis_prompt
        )
        # data = res.get("data")
        # state_data = json.loads(
        #     data.get("stateData")
        # )
        # screenshot = data.get("screenshot")
        # # screenshot = await browser_screenshot(client, need_screenshot=True)
        # elements = state_data.get("element_tree")
        # return BrowserResult(
        #     elements=elements,
        #     url=data.get("url"),
        #     title=data.get("title"),
        #     screenshot=screenshot,
        #
        # )
    except Exception as exc:
        logger.error(f"Browser Tool get_dropdown_options Failed! {exc}")
        return (BrowserResult(
            success=False,
            error=f"错误: 浏览器获取下拉菜单:{exc}"
        )
    )


@sandbox_tool(
    name="browser_select_dropdown_option",
    description="浏览器选择下拉菜单",
    input_schema={
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "需要点击元素的索引，返回的dom结构中的，eg:0,1,2",
            },
            "text": {
                "type": "string",
                "description": "选择的下拉菜单的选项文本",
            },
            "analyze_screenshot": {
                "type": "boolean",
                "description": "是否对截图进行AI语义分析",
                "default": False,
            },
            "analysis_prompt": {
                "type": "string",
                "description": "自定义图片分析提示词",
                "default": None,
            }
        },
    },
    owner="chenketing.ckt"
)

async def select_dropdown_option(
        client: SandboxBase,
        index: int,
        text: str,
        analyze_screenshot: bool = False,
        analysis_prompt: Optional[str] = None,
        **kwargs
) -> BrowserResult:
    """
    浏览器选择下拉菜单
    """
    if client is None:
        return BrowserResult(
            success=False,
            error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
        )

    try:
        logger.info(f"select_dropdown_option, {index}")
        res = await client.browser.select_dropdown_option(
            index=index,
            text=text,
            need_screenshot=True,
        )
        return await _parse_browser_response(
            res,
            "select_dropdown_option",
            {"index": index, "text": text},
            client=client,
            analyze_screenshot=analyze_screenshot,
            analysis_prompt=analysis_prompt
        )
        # data = res.get("data")
        # state_data = json.loads(
        #     data.get("stateData")
        # )
        # screenshot = data.get("screenshot")
        # # screenshot = await browser_screenshot(client, need_screenshot=True)
        # elements = state_data.get("element_tree")
        # return BrowserResult(
        #     elements=elements,
        #     url=data.get("url"),
        #     title=data.get("title"),
        #     screenshot=screenshot,
        #
        # )
    except Exception as exc:
        logger.error(f"Browser Tool select_dropdown_option Failed! {exc}")
        return (BrowserResult(
            success=False,
            error=f"错误: 浏览器选择下拉菜单:{exc}"
        )
    )


@sandbox_tool(
    name="browser_mouse_wheel",
    description="浏览器鼠标滚动",
    input_schema={
        "type": "object",
        "properties": {
            "y": {
                "type": "integer",
                "description": "浏览器页面滚动的值，大于0为向下滚动，小于0为向上滚动,eg:100(向下滚动100px)， -100(向上滚动100px)",
            },
            "analyze_screenshot": {
                "type": "boolean",
                "description": "是否对截图进行AI语义分析",
                "default": False,
            },
            "analysis_prompt": {
                "type": "string",
                "description": "自定义图片分析提示词",
                "default": None,
            }
        },
    },
    owner="chenketing.ckt"
)

async def browser_mouse_wheel(
        client: SandboxBase,
        y: int,
        analyze_screenshot: bool = False,
        analysis_prompt: Optional[str] = None,
        **kwargs
) -> BrowserResult:
    """
    浏览器鼠标滚动
    """
    if client is None:
        return BrowserResult(
            success=False,
            error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
        )

    try:
        logger.info(f"browser_mouse_wheel y, {y}, analyze_screenshot: {analyze_screenshot}")
        res = await client.browser.browser_mouse_wheel(
            y=y,
            need_screenshot=True,
        )

        # 使用统一的响应解析方法，包含截图分析功能
        result = await _parse_browser_response(
            res,
            "browser_mouse_wheel",
            {"y": y},
            client=client,
            analyze_screenshot=analyze_screenshot,
            analysis_prompt=analysis_prompt
        )

        return result
    except Exception as exc:
        logger.error(f"Browser Tool browser_mouse_wheel Failed! {exc}")
        return (BrowserResult(
            success=False,
            error=f"错误: 浏览器鼠标滚动失败:{exc}"
        )
    )

@sandbox_tool(
    name="browser_page_content",
    description="查看当前页面, 获取页面内容",
    input_schema={
        "type": "object",
        "properties": {
            "need_screenshot": {
                "type": "bool",
                "description": "是否需要截图",
            },
            "analyze_screenshot": {
                "type": "boolean",
                "description": "是否对截图进行AI语义分析",
                "default": False,
            },
            "analysis_prompt": {
                "type": "string",
                "description": "自定义图片分析提示词",
                "default": None,
            }
        },
    },
    owner="chenketing.ckt"
)

async def page_content(
        client: SandboxBase,
        need_screenshot: bool,
        analyze_screenshot: bool = False,
        analysis_prompt: Optional[str] = None,
        **kwargs
) -> BrowserResult:
    """
    查看当前页面
    """
    if client is None:
        return BrowserResult(
            success=False,
            error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
        )

    try:
        logger.info(f"browser_current_state need_screenshot, {need_screenshot}")
        res = await client.browser.page_content(
            need_screenshot=True,
        )
        return await _parse_browser_response(
            res,
            "page_content",
            {"need_screenshot": need_screenshot},
            client=client,
            analyze_screenshot=analyze_screenshot,
            analysis_prompt=analysis_prompt
        )
        # data = res.get("data")
        # state_data = json.loads(
        #     data.get("stateData")
        # )
        # screenshot = data.get("screenshot")
        # # screenshot = await browser_screenshot(client, need_screenshot=True)
        # elements = state_data.get("element_tree")
        # return BrowserResult(
        #     elements=elements,
        #     url=data.get("url"),
        #     title=data.get("title"),
        #     screenshot=screenshot,
        #
        # )
    except Exception as exc:
        logger.error(f"Browser Tool page_content Failed! {exc}")
        return (BrowserResult(
            success=False,
            error=f"错误: 查看当前页面:{exc}"
        )
    )


@sandbox_tool(
    name="browser_mouse_move",
    description="浏览器鼠标移动",
    input_schema={
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "需要点击元素的索引，返回的dom结构中的，eg:0,1,2",
            },
            "analyze_screenshot": {
                "type": "boolean",
                "description": "是否对截图进行AI语义分析",
                "default": False,
            },
            "analysis_prompt": {
                "type": "string",
                "description": "自定义图片分析提示词",
                "default": None,
            }
        },
    },
    owner="chenketing.ckt"
)

async def browser_mouse_move(
        client: SandboxBase,
        index: int,
        analyze_screenshot: bool = False,
        analysis_prompt: Optional[str] = None,
        **kwargs
) -> BrowserResult:
    """
    浏览器鼠标移动
    """
    if client is None:
        return BrowserResult(
            success=False,
            error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
        )

    try:
        logger.info(f"browser_mouse_move index, {index}")
        res = await client.browser.browser_mouse_move(
            index=index,
            need_screenshot=True,
        )
        return await _parse_browser_response(
            res,
            "browser_mouse_move",
            {"index": index},
            client=client,
            analyze_screenshot=analyze_screenshot,
            analysis_prompt=analysis_prompt
        )
        # data = res.get("data")
        # state_data = json.loads(
        #     data.get("stateData")
        # )
        # screenshot = data.get("screenshot")
        # # screenshot = await browser_screenshot(client, need_screenshot=True)
        # elements = state_data.get("element_tree")
        # return BrowserResult(
        #     elements=elements,
        #     url=data.get("url"),
        #     title=data.get("title"),
        #     screenshot=screenshot,
        #
        # )
    except Exception as exc:
        logger.error(f"Browser Tool browser_mouse_move Failed! {exc}")
        return (BrowserResult(
            success=False,
            error=f"错误: 浏览器鼠标移动:{exc}"
        )
    )


@sandbox_tool(
    name="browser_hover_element",
    description="浏览器鼠标悬停元素",
    input_schema={
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "需要点击元素的索引，返回的dom结构中的，eg:0,1,2",
            },
            "xpath": {
                "type": "string",
                "description": "需要点击元素的xpath",
            },
        },
    },
    owner="chenketing.ckt"
)
async def browser_hover_element(
        client: SandboxBase,
        index: Optional[int] = None,
        xpath: Optional[str] = None,
        **kwargs
) -> BrowserResult:
    """
    浏览器鼠标悬停元素
    """
    if client is None:
        return BrowserResult(
            success=False,
            error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
        )

    try:
        logger.info(f"browser_hover_element index, {index} xpath, {xpath}")
        res = await client.browser.browser_hover_element(
            index=index,
            xpath=xpath,
            need_screenshot=True,
        )
        return _parse_browser_response(res, "browser_hover_element")
    except Exception as exc:
        logger.error(f"Browser Tool browser_hover_element Failed! {exc}")
        return BrowserResult(
            success=False,
            error=f"错误: 浏览器鼠标悬停元素失败:{exc}"
        )
@sandbox_tool(
    name="browser_save_image",
    description="保存浏览器图片",
    input_schema={
        "type": "object",
        "properties": {
            "image_url": {
                "type": "str",
                "description": "图片链接",
            },
            "title": {
                "type": "str",
                "description": "图片标题",
            },
            "summary": {
                "type": "str",
                "description": "图片的上下文摘要(100字以内)",
            },
        },
    },
    owner="chenketing.ckt"
)
async def browser_save_image(
        client: SandboxBase,
        title: str,
        image_url: str,
        summary: str,
        **kwargs
) -> BrowserResult:
    """
    浏览器导航, 打开指定网址
    """

    try:
        logger.info(f"browser_save_image image_url, {image_url}")
        res = await browser_screenshot(client, need_screenshot=True)
        return BrowserResult(
            success=True,
            image_url=image_url,
            screenshot=res.screenshot if res.success else "",
            url=res.url if res.success else "",
            title=title or f"保存浏览器图片",
            elements=summary,
        )
    except Exception as exc:
        return BrowserResult(
            success=False,
            error=f"错误: 浏览器截屏失败: {exc}"
        )


@sandbox_tool(
    name="browser_open_tab",
    description="浏览器打开新页签",
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "str",
                "description": "打开新标签URL",
            },
            "analyze_screenshot": {
                "type": "boolean",
                "description": "是否对截图进行AI语义分析",
                "default": False,
            },
            "analysis_prompt": {
                "type": "string",
                "description": "自定义图片分析提示词",
                "default": None,
            }
        },
    },
    owner="chenketing.ckt"
)

async def browser_open_tab(
        client: SandboxBase,
        url: str,
        analyze_screenshot: bool = False,
        analysis_prompt: Optional[str] = None,
        **kwargs
) -> BrowserResult:
    """
    浏览器打开新页签
    """
    if client is None:
        return BrowserResult(
            success=False,
            error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
        )

    try:
        logger.info(f"browser_open_tab url, {url}")
        res = await client.browser.open_tab(
            url=url,
            need_screenshot=True,
        )
        return await _parse_browser_response(
            res,
            "browser_open_tab",
            {"url": url},
            client=client,
            analyze_screenshot=analyze_screenshot,
            analysis_prompt=analysis_prompt
        )
        # data = res.get("data")
        # state_data = json.loads(
        #     data.get("stateData")
        # )
        # screenshot = data.get("screenshot")
        # # screenshot = await browser_screenshot(client, need_screenshot=True)
        # elements = state_data.get("element_tree")
        # return BrowserResult(
        #     elements=elements,
        #     url=data.get("url"),
        #     title=data.get("title"),
        #     screenshot=screenshot,
        #
        # )
    except Exception as exc:
        logger.error(f"Browser Tool browser_open_tab Failed! {exc}")
        return (BrowserResult(
            success=False,
            error=f"错误: 浏览器打开新页签:{exc}"
        )
    )

# @sandbox_tool(
#     name="browser_chart_peak",
#     description="浏览器鼠标移动到当前折线图最高点",
#     input_schema={
#         "type": "object",
#         "properties": {
#             "screenshot": {
#                 "type": "bool",
#                 "description": "是否截图",
#             },
#         },
#     },
#     owner="chenketing.ckt"
# )
# async def browser_chart_peak(
#         client: SandboxBase,
#         **kwargs
# ) -> BrowserResult:
#     """
#     浏览器鼠标移动到折线图最高点
#     """
#     if client is None:
#         return BrowserResult(
#             success=False,
#             error=f"错误: 当前任务未初始化沙箱环境，无法操作浏览器"
#         )
#
#     try:
#         logger.info(f"browser_chart_peak")
#         res = await client.browser.page_content(
#             need_screenshot=True,
#         )
#         data = (res or {}).get("data") or {}
#         if data.get("result"):
#             peak = dom_utils.get_chart_peak_xpath(data.get("result"))
#             logger.info(f"browser_chart_peak peak, {peak}")
#             if peak:
#                 res = await client.browser.browser_hover_element(
#                    xpath=peak[2],
#                     need_screenshot=True,
#                 )
#                 return _parse_browser_response(res, "browser_hover_element")
#         # data = res.get("data")
#         # state_data = json.loads(
#         #     data.get("stateData")
#         # )
#         # screenshot = data.get("screenshot")
#         # # screenshot = await browser_screenshot(client, need_screenshot=True)
#         # elements = state_data.get("element_tree")
#         # return BrowserResult(
#         #     elements=elements,
#         #     url=data.get("url"),
#         #     title=data.get("title"),
#         #     screenshot=screenshot,
#         #
#         # )
#     except Exception as exc:
#         logger.error(f"Browser Tool browser_mouse_move Failed! {exc}")
#         return (BrowserResult(
#             success=False,
#             error=f"错误: 浏览器鼠标移动:{exc}"
#         )
#     )

def generate_markdown_image(base64_string, title="图片展示", description="图片描述",
                            width=200):
    """
    生成包含 base64 图片的 Markdown 字符串

    Args:
        base64_string: base64 编码的图片字符串
        title: 标题
        description: 图片描述
        width: 图片宽度

    Returns:
        拼接好的 Markdown 字符串
    """
    markdown_content = f"""## {title}
    ![{title}](data:image/png;base64,{base64_string})"""
    return markdown_content


async def _parse_browser_response(
        res,
        operation_name: str,
        input_kwargs: Optional[Dict] = dict,
        client: Optional[SandboxBase] = None,
        analyze_screenshot: bool = False,
        analysis_prompt: Optional[str] = None,
) -> BrowserResult:
    """
    解析浏览器操作响应，统一处理数据提取和错误

    Args:
        res: 浏览器操作返回的响应
        operation_name: 操作名称，用于日志记录
        input_kwargs: 输入参数，用于日志记录
        client: 沙箱客户端，用于截图分析
        analyze_screenshot: 是否分析截图
        analysis_prompt: 截图分析提示词

    Returns:
        BrowserResult: 包含解析后的数据或错误信息，可能包含截图分析结果
    """
    try:
        data = (res or {}).get("data") or {}
        state_data_str = data.get("stateData")
        state_data = {}
        if state_data_str:
            try:
                state_data = json.loads(state_data_str)
            except Exception as json_exc:
                logger.warning(
                    f"{operation_name} - Failed to parse stateData: {json_exc}")
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

        # 如果需要分析截图，进行AI分析
        if analyze_screenshot and result.success and result.screenshot:
            try:
                analysis_result = await analyze_image(
                    image=result.screenshot,
                    prompt=analysis_prompt,
                    model="aistudio/Qwen3-VL-235B-A22B-Instruct(高保)"
                )
                result.analysis = analysis_result
                logger.info(f"{operation_name} - Screenshot analysis completed successfully, result: {analysis_result}")
            except Exception as analysis_exc:
                logger.warning(f"{operation_name} - Screenshot analysis failed: {analysis_exc}")
                result.analysis_error = str(analysis_exc)

        return result

    except Exception as exc:
        logger.error(f"{operation_name} - Failed to parse response: {exc}")
        return BrowserResult(
            success=False,
            error=f"错误: 解析浏览器响应失败: {exc}",
        )



async def analyze_image(
        image: str,
        prompt: Optional[str] = None,
        model: str = "aistudio/Qwen3-VL-235B-A22B-Instruct(高保)"
) -> Dict[str, Any]:
    """
    Analyze an image using multimodal AI models following the parse_image_content pattern.

    Args:
        image: Base64 encoded image data
        prompt: Optional custom analysis prompt
        model: VLM model to use for analysis (aistudio/Qwen2.5-VL-7B-Instruct format)

    Returns:
        Dictionary containing analysis results with fields:
        - text_content: OCR text found in the image
        - description: Visual description of the screenshot
        - ui_elements: List of UI elements with positions
        - summary: Summary of the page content
        - language: Detected language
        - confidence: Analysis confidence score
    """
    from derisk.model.image_analysis.analyzer import ImageAnalyzer
    from derisk.model import DefaultLLMClient

    # Initialize analyzer with LLMClient following parse_image_content pattern
    llm_client = DefaultLLMClient()
    analyzer = ImageAnalyzer(
        llm_client=llm_client,
        model_name=model
    )

    # Decode base64 image
    import base64
    image_bytes = base64.b64decode(image)

    # Analyze the screenshot using ImageExtractor pattern
    analysis = await analyzer.analyze_screenshot_with_extractor(
        image_data=image_bytes,
        prompt=prompt,
        model_name=model
    )

    # Return results as dictionary
    return {
        "text": analysis.text,
        "summary": analysis.summary
    }
