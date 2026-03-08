"""
Sandbox 浏览器工具兼容层

旧版浏览器工具已迁移到统一工具框架。
此文件仅为向后兼容，新代码请使用:

    from derisk.agent.tools.builtin.sandbox import (
        BrowserNavigateTool,
        BrowserClickElementTool,
        ...
    )
"""

# 向后兼容：从统一框架导入
from derisk.agent.tools.builtin.sandbox.browser import (
    BROWSER_TOOLS,
    BrowserResult,
    ScreenshotAnalysis,
    BrowserNavigateTool,
    BrowserSaveScreenshotTool,
    BrowserClickElementTool,
    BrowserInputTextTool,
    BrowserGetDropdownOptionsTool,
    BrowserSelectDropdownOptionTool,
    BrowserMouseWheelTool,
    BrowserPageContentTool,
    BrowserMouseMoveTool,
    BrowserHoverElementTool,
    BrowserSaveImageTool,
    BrowserOpenTabTool,
    analyze_image,
)

__all__ = [
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
    "analyze_image",
]
