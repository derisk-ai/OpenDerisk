"""
FileExplorerAgent - 文件探索Agent

特性：
1. 主动探索机制
2. 项目结构分析
3. 代码库深度理解
4. 自动生成项目文档
"""

from typing import AsyncIterator, Dict, Any, Optional, List
import logging
import os

from .base_builtin_agent import BaseBuiltinAgent
from ..agent_info import AgentInfo
from ..llm_adapter import LLMAdapter, LLMConfig, LLMFactory
from ..tools_v2 import ToolRegistry

logger = logging.getLogger(__name__)


FILE_EXPLORER_SYSTEM_PROMPT = """你是一个专业的文件探索Agent，负责探索和分析项目结构。

## 核心能力

1. **项目探索**：主动探索项目目录结构
2. **文件分析**：读取和分析关键文件内容
3. **结构理解**：识别项目类型和架构模式
4. **文档生成**：生成项目结构文档

## 探索策略

1. **广度优先探索**
   - 先了解整体目录结构
   - 识别关键配置文件
   - 分析项目类型

2. **深度优先分析**
   - 深入关键目录
   - 理解代码组织
   - 分析依赖关系

## 工作流程

1. 探索项目根目录
2. 识别项目类型（Python/Node.js/Java等）
3. 查找关键文件（README、配置文件、入口文件）
4. 分析项目结构
5. 生成项目文档

当前项目路径: {project_path}
请主动探索并分析项目结构。
"""


class FileExplorerAgent(BaseBuiltinAgent):
    """
    文件探索Agent - 主动探索项目结构

    特性：
    1. 主动探索机制（参考OpenCode）
    2. 项目结构分析
    3. 代码库深度理解
    4. 自动生成项目文档
    """

    def __init__(
        self,
        info: AgentInfo,
        llm_adapter: LLMAdapter,
        tool_registry: Optional[ToolRegistry] = None,
        project_path: Optional[str] = None,
        enable_auto_exploration: bool = True,
        max_exploration_depth: int = 5,
        **kwargs,
    ):
        super().__init__(info, llm_adapter, tool_registry, **kwargs)

        self.project_path = project_path or os.getcwd()
        self.enable_auto_exploration = enable_auto_exploration
        self.max_exploration_depth = max_exploration_depth

        self._explored_files = set()
        self._project_structure = {}

        logger.info(
            f"[FileExplorerAgent] 初始化完成: "
            f"project={self.project_path}, "
            f"auto_explore={enable_auto_exploration}"
        )

    def _get_default_tools(self) -> List[str]:
        """获取默认工具列表"""
        return ["glob", "grep", "read", "bash", "think"]

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return FILE_EXPLORER_SYSTEM_PROMPT.format(project_path=self.project_path)

    async def explore_project(self) -> Dict[str, Any]:
        """
        主动探索项目结构

        Returns:
            Dict: 项目结构信息
        """
        logger.info(f"[FileExplorerAgent] 开始探索项目: {self.project_path}")

        structure = {
            "project_path": self.project_path,
            "project_type": None,
            "key_files": [],
            "directories": [],
            "summary": None,
        }

        try:
            result = await self.execute_tool(
                "bash", {"command": f"ls -la {self.project_path}"}
            )

            if result.get("success"):
                structure["root_files"] = result.get("output", "")

            glob_result = await self.execute_tool(
                "glob", {"pattern": "*", "path": self.project_path}
            )

            if glob_result.get("success"):
                structure["directories"] = self._parse_glob_result(
                    glob_result.get("output", "")
                )

            structure["project_type"] = await self._detect_project_type()

            structure["key_files"] = await self._find_key_files(
                structure["project_type"]
            )

            structure["summary"] = await self._generate_project_summary(structure)

            self._project_structure = structure

            logger.info(f"[FileExplorerAgent] 探索完成: {structure['project_type']}")

        except Exception as e:
            logger.error(f"[FileExplorerAgent] 探索失败: {e}")
            structure["error"] = str(e)

        return structure

    async def _detect_project_type(self) -> str:
        """检测项目类型"""
        type_indicators = {
            "Python": ["setup.py", "pyproject.toml", "requirements.txt", "Pipfile"],
            "Node.js": ["package.json", "yarn.lock", "package-lock.json"],
            "Java": ["pom.xml", "build.gradle", "gradlew"],
            "Go": ["go.mod", "go.sum"],
            "Rust": ["Cargo.toml", "Cargo.lock"],
        }

        for project_type, indicators in type_indicators.items():
            for indicator in indicators:
                indicator_path = os.path.join(self.project_path, indicator)
                if os.path.exists(indicator_path):
                    return project_type

        return "Unknown"

    async def _find_key_files(self, project_type: str) -> List[Dict[str, str]]:
        """查找关键文件"""
        key_file_patterns = {
            "Python": ["*.py", "requirements.txt", "setup.py", "README.md"],
            "Node.js": ["*.js", "package.json", "README.md"],
            "Java": ["*.java", "pom.xml", "README.md"],
        }

        patterns = key_file_patterns.get(project_type, ["README.md"])
        key_files = []

        for pattern in patterns[:3]:
            result = await self.execute_tool(
                "glob", {"pattern": pattern, "path": self.project_path}
            )

            if result.get("success"):
                files = result.get("output", "").strip().split("\n")
                for file_path in files[:5]:
                    if file_path:
                        key_files.append({"path": file_path, "type": pattern})

        return key_files

    async def _generate_project_summary(self, structure: Dict) -> str:
        """生成项目摘要"""
        summary_parts = [
            f"项目路径: {structure['project_path']}",
            f"项目类型: {structure['project_type']}",
            f"关键文件数量: {len(structure['key_files'])}",
        ]

        return "\n".join(summary_parts)

    def _parse_glob_result(self, output: str) -> List[str]:
        """解析glob结果"""
        lines = output.strip().split("\n")
        return [line for line in lines if line and not line.startswith("#")]

    async def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """分析单个文件"""
        result = await self.execute_tool("read", {"file_path": file_path})

        if result.get("success"):
            content = result.get("output", "")

            analysis = {
                "file_path": file_path,
                "size": len(content),
                "lines": len(content.split("\n")),
                "preview": content[:500] if content else None,
            }

            return analysis

        return {"error": result.get("error", "读取失败")}

    async def run(self, message: str, stream: bool = True) -> AsyncIterator[str]:
        """主执行循环"""

        if self.enable_auto_exploration and not self._project_structure:
            structure = await self.explore_project()

            summary = f"""
[项目探索结果]

项目类型: {structure.get("project_type", "Unknown")}
项目路径: {structure.get("project_path", "N/A")}
关键文件: {len(structure.get("key_files", []))} 个

{structure.get("summary", "")}
"""
            yield summary

        async for chunk in super().run(message, stream):
            yield chunk

    @classmethod
    def create(
        cls,
        name: str = "file-explorer-agent",
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        max_steps: int = 20,
        project_path: Optional[str] = None,
        enable_auto_exploration: bool = True,
        sandbox_manager: Optional[Any] = None,
        enable_doom_loop_detection: bool = True,
        doom_loop_threshold: int = 3,
        enable_output_truncation: bool = True,
        max_output_lines: int = 2000,
        max_output_bytes: int = 50000,
        **kwargs,
    ) -> "FileExplorerAgent":
        """便捷创建方法 - 支持 runtime_config 参数"""
        import os
        from derisk.agent.util.llm.model_config_cache import ModelConfigCache

        if not api_key:
            if ModelConfigCache.has_model(model):
                model_config = ModelConfigCache.get_config(model)
                if model_config:
                    api_key = api_key or model_config.get("api_key")

        api_key = api_key or os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("需要提供OpenAI API Key")

        info = AgentInfo(name=name, max_steps=max_steps, **kwargs)

        llm_config = LLMConfig(model=model, api_key=api_key)

        llm_adapter = LLMFactory.create(llm_config)

        return cls(
            info=info,
            llm_adapter=llm_adapter,
            project_path=project_path,
            enable_auto_exploration=enable_auto_exploration,
            sandbox_manager=sandbox_manager,
            enable_doom_loop_detection=enable_doom_loop_detection,
            doom_loop_threshold=doom_loop_threshold,
            enable_output_truncation=enable_output_truncation,
            max_output_lines=max_output_lines,
            max_output_bytes=max_output_bytes,
            **kwargs,
        )
