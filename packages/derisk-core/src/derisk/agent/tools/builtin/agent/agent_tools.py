"""
BrowserTool - 浏览器自动化工具
参考 OpenClaw 的浏览器工具设计
"""

from typing import Dict, Any, Optional
import logging

from .base import ToolBase, ToolCategory, ToolRiskLevel, ToolEnvironment
from .metadata import ToolMetadata
from .context import ToolContext
from .result import ToolResult

logger = logging.getLogger(__name__)


class BrowserTool(ToolBase):
    """
    浏览器自动化工具
    
    支持操作：
    - 浏览器初始化
    - 页面导航
    - 截图
    - 元素点击
    - 文本输入
    - 元素树获取
    - 滚动
    """
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser",
            display_name="Browser Automation",
            description="Control a web browser to navigate pages, click elements, input text, and take screenshots",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            environment=ToolEnvironment.SANDBOX,
            timeout=60,
            tags=["browser", "automation", "playwright", "web"],
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "init", "navigate", "screenshot", "click", "input",
                        "element_tree", "scroll_down", "scroll_up", "scroll_to_text",
                        "open_tab", "hover", "search", "content", "dropdown_options", "select_dropdown"
                    ],
                    "description": "Browser action to perform"
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to"
                },
                "index": {
                    "type": "integer",
                    "description": "Element index from element_tree"
                },
                "text": {
                    "type": "string",
                    "description": "Text to input or search"
                },
                "need_screenshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to take a screenshot"
                },
                "full_page": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to capture full page"
                },
                "browser_config": {
                    "type": "object",
                    "description": "Browser configuration"
                }
            },
            "required": ["action"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        action = args.get("action")
        
        try:
            browser_client = await self._get_browser_client(context)
            
            if not browser_client:
                return ToolResult.fail(
                    error="Browser client not available",
                    tool_name=self.name
                )
            
            result = await self._execute_action(browser_client, action, args)
            
            return ToolResult.ok(
                output=result,
                tool_name=self.name,
                metadata={"action": action}
            )
            
        except Exception as e:
            logger.error(f"[BrowserTool] 执行失败: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)
    
    async def _get_browser_client(self, context: Optional[ToolContext] = None):
        if context:
            client = context.get_resource("browser_client")
            if client:
                return client
            
            sandbox_client = context.get_resource("sandbox_client")
            if sandbox_client and hasattr(sandbox_client, "browser"):
                return sandbox_client.browser
        
        try:
            from derisk_ext.sandbox.local.playwright_browser_client import PlaywrightBrowserClient
            return PlaywrightBrowserClient("default")
        except ImportError:
            logger.warning("Playwright browser not available")
            return None
    
    async def _execute_action(self, client, action: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if action == "init":
            return await client.browser_init(
                browser_config=args.get("browser_config")
            )
        elif action == "navigate":
            return await client.browser_navigate(
                url=args["url"],
                need_screenshot=args.get("need_screenshot", False)
            )
        elif action == "screenshot":
            return await client.browser_screenshot(
                full_page=args.get("full_page", False)
            )
        elif action == "click":
            return await client.click_element(
                index=args["index"],
                need_screenshot=args.get("need_screenshot", False)
            )
        elif action == "input":
            return await client.input_text(
                index=args["index"],
                text=args["text"],
                need_screenshot=args.get("need_screenshot", False)
            )
        elif action == "element_tree":
            return await client.browser_element_tree(
                need_screenshot=args.get("need_screenshot", False)
            )
        elif action == "scroll_down":
            return await client.scroll_down(
                need_screenshot=args.get("need_screenshot", False)
            )
        elif action == "scroll_up":
            return await client.scroll_up(
                need_screenshot=args.get("need_screenshot", False)
            )
        elif action == "scroll_to_text":
            return await client.scroll_to_text(
                text=args["text"],
                need_screenshot=args.get("need_screenshot", False)
            )
        elif action == "content":
            return await client.page_content(
                need_screenshot=args.get("need_screenshot", False)
            )
        elif action == "search":
            return await client.browser_search(
                query=args["text"],
                need_screenshot=args.get("need_screenshot", False)
            )
        else:
            return {"status": "error", "message": f"Unknown action: {action}"}


class SandboxTool(ToolBase):
    """
    沙箱执行工具
    
    提供隔离环境中的代码执行能力
    """
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="sandbox",
            display_name="Sandbox Execution",
            description="Execute code in an isolated sandbox environment",
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.HIGH,
            requires_permission=True,
            environment=ToolEnvironment.SANDBOX,
            timeout=300,
            tags=["sandbox", "docker", "isolation", "execute"],
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Code to execute"
                },
                "language": {
                    "type": "string",
                    "enum": ["python", "javascript", "shell"],
                    "default": "python",
                    "description": "Programming language"
                },
                "timeout": {
                    "type": "integer",
                    "default": 120,
                    "description": "Execution timeout in seconds"
                }
            },
            "required": ["code"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        code = args.get("code")
        language = args.get("language", "python")
        timeout = args.get("timeout", 120)
        
        try:
            sandbox_client = await self._get_sandbox_client(context)
            
            if not sandbox_client:
                return ToolResult.fail(
                    error="Sandbox client not available",
                    tool_name=self.name
                )
            
            result = await sandbox_client.execute_code(
                code=code,
                language=language,
                timeout=timeout
            )
            
            return ToolResult.ok(
                output=result.get("output", ""),
                tool_name=self.name,
                metadata={
                    "language": language,
                    "exit_code": result.get("exit_code"),
                    "execution_time": result.get("execution_time")
                }
            )
            
        except Exception as e:
            logger.error(f"[SandboxTool] 执行失败: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)
    
    async def _get_sandbox_client(self, context: Optional[ToolContext] = None):
        if context:
            client = context.get_resource("sandbox_client")
            if client:
                return client
        
        try:
            from derisk_ext.sandbox.local.runtime import LocalSandboxRuntime
            return LocalSandboxRuntime()
        except ImportError:
            logger.warning("Local sandbox runtime not available")
            return None


class TerminateTool(ToolBase):
    """
    终止对话工具
    
    用于结束当前对话
    """
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="terminate",
            display_name="End Conversation",
            description="End the current conversation with a final message",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.SAFE,
            requires_permission=False,
            tags=["conversation", "end", "finish"],
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Final message to the user"
                }
            },
            "required": ["message"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        message = args.get("message", "Task completed")
        
        return ToolResult.ok(
            output=f"[TERMINATE] {message}",
            tool_name=self.name,
            metadata={"terminate": True, "message": message}
        )


class KnowledgeTool(ToolBase):
    """
    知识检索工具
    
    用于从知识库中检索相关信息
    """
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="knowledge_search",
            display_name="Knowledge Search",
            description="Search for information in the knowledge base",
            category=ToolCategory.SEARCH,
            risk_level=ToolRiskLevel.SAFE,
            requires_permission=False,
            tags=["knowledge", "search", "rag"],
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "knowledge_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Knowledge base IDs to search"
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "Number of results to return"
                }
            },
            "required": ["query"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        query = args.get("query")
        knowledge_ids = args.get("knowledge_ids", [])
        top_k = args.get("top_k", 5)
        
        try:
            if context:
                knowledge_client = context.get_resource("knowledge_client")
                if knowledge_client:
                    results = await knowledge_client.search(
                        query=query,
                        knowledge_ids=knowledge_ids,
                        top_k=top_k
                    )
                    return ToolResult.ok(
                        output=results,
                        tool_name=self.name
                    )
            
            return ToolResult.fail(
                error="Knowledge client not available",
                tool_name=self.name
            )
            
        except Exception as e:
            logger.error(f"[KnowledgeTool] 搜索失败: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)


class KanbanTool(ToolBase):
    """
    看板管理工具
    
    用于任务和项目管理
    """
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kanban",
            display_name="Kanban Board",
            description="Manage tasks on a kanban board",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            tags=["kanban", "task", "project", "management"],
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "update", "delete", "move", "list"],
                    "description": "Kanban action"
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID"
                },
                "title": {
                    "type": "string",
                    "description": "Task title"
                },
                "description": {
                    "type": "string",
                    "description": "Task description"
                },
                "status": {
                    "type": "string",
                    "enum": ["todo", "in_progress", "done"],
                    "description": "Task status"
                },
                "column": {
                    "type": "string",
                    "description": "Target column"
                }
            },
            "required": ["action"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        action = args.get("action")
        
        return ToolResult.ok(
            output=f"Kanban action '{action}' executed",
            tool_name=self.name,
            metadata=args
        )


class TodoTool(ToolBase):
    """
    TODO任务管理工具
    """
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="todo",
            display_name="TODO Manager",
            description="Manage TODO tasks",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.SAFE,
            requires_permission=False,
            tags=["todo", "task", "plan"],
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "complete", "delete", "list"],
                    "description": "TODO action"
                },
                "content": {
                    "type": "string",
                    "description": "Task content"
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID"
                }
            },
            "required": ["action"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        action = args.get("action")
        
        return ToolResult.ok(
            output=f"TODO action '{action}' executed",
            tool_name=self.name,
            metadata=args
        )


# 注册所有Agent工具
def register_agent_tools(registry):
    """注册Agent相关工具"""
    from .base import ToolSource
    
    registry.register(BrowserTool(), source=ToolSource.CORE)
    registry.register(SandboxTool(), source=ToolSource.CORE)
    registry.register(TerminateTool(), source=ToolSource.CORE)
    registry.register(KnowledgeTool(), source=ToolSource.CORE)
    registry.register(KanbanTool(), source=ToolSource.CORE)
    registry.register(TodoTool(), source=ToolSource.CORE)