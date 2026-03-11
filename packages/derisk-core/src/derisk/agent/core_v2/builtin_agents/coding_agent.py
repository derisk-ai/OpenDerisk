"""
CodingAgent - 编程开发Agent

特性：
1. 自主探索代码库
2. 智能代码定位
3. 功能开发与重构
4. 代码质量检查
5. 软件工程最佳实践
"""

from typing import AsyncIterator, Dict, Any, Optional, List
import logging
import os

from .base_builtin_agent import BaseBuiltinAgent
from ..agent_info import AgentInfo
from ..llm_adapter import LLMAdapter, LLMConfig, LLMFactory
from ..tools_v2 import ToolRegistry

logger = logging.getLogger(__name__)


CODING_SYSTEM_PROMPT = """你是一个专业的编程Agent，负责代码开发和重构。

## 核心能力

1. **代码探索**：自主探索和理解代码库
2. **智能定位**：快速定位相关代码文件
3. **功能开发**：实现新功能和特性
4. **代码重构**：优化和重构现有代码
5. **质量检查**：检查代码质量，遵循最佳实践

## 开发流程

1. **需求理解**
   - 分析功能需求
   - 理解业务逻辑
   - 确定技术方案

2. **代码探索**
   - 探索项目结构
   - 定位相关代码
   - 理解现有实现

3. **方案设计**
   - 设计实现方案
   - 考虑边界情况
   - 规划测试策略

4. **代码实现**
   - 编写代码
   - 添加注释
   - 处理异常

5. **质量保证**
   - 代码审查
   - 运行测试
   - 性能优化

## 代码规范

{code_style_rules}

当前工作目录: {workspace_path}
请按照软件工程最佳实践进行开发。
"""


class CodingAgent(BaseBuiltinAgent):
    """
    编程Agent - 自主代码开发

    特性：
    1. 自主探索代码库
    2. 智能代码定位
    3. 功能开发与重构
    4. 代码质量检查
    5. 软件工程最佳实践
    """

    def __init__(
        self,
        info: AgentInfo,
        llm_adapter: LLMAdapter,
        tool_registry: Optional[ToolRegistry] = None,
        workspace_path: Optional[str] = None,
        enable_auto_exploration: bool = True,
        enable_code_quality_check: bool = True,
        code_style_rules: Optional[List[str]] = None,
        **kwargs,
    ):
        super().__init__(info, llm_adapter, tool_registry, **kwargs)

        self.workspace_path = workspace_path or os.getcwd()
        self.enable_auto_exploration = enable_auto_exploration
        self.enable_code_quality_check = enable_code_quality_check

        self.code_style_rules = code_style_rules or [
            "Use consistent indentation (4 spaces for Python)",
            "Follow PEP 8 for Python code",
            "Use meaningful variable and function names",
            "Add docstrings for public functions",
            "Keep functions under 50 lines",
            "Avoid deep nesting",
        ]

        self._explored_files = set()
        self._project_context = {}

        logger.info(
            f"[CodingAgent] 初始化完成: "
            f"workspace={self.workspace_path}, "
            f"auto_explore={enable_auto_exploration}, "
            f"quality_check={enable_code_quality_check}"
        )

    def _get_default_tools(self) -> List[str]:
        """获取默认工具列表"""
        return ["read", "write", "bash", "grep", "glob", "think"]

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        code_style = "\n".join(f"- {rule}" for rule in self.code_style_rules)

        return CODING_SYSTEM_PROMPT.format(
            code_style_rules=code_style, workspace_path=self.workspace_path
        )

    async def explore_codebase(
        self, task_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        探索代码库

        Args:
            task_context: 任务上下文

        Returns:
            Dict: 代码库信息
        """
        logger.info(f"[CodingAgent] 开始探索代码库: {self.workspace_path}")

        codebase_info = {
            "workspace_path": self.workspace_path,
            "project_type": None,
            "key_files": [],
            "dependencies": [],
            "structure": None,
        }

        try:
            project_type = await self._detect_project_type()
            codebase_info["project_type"] = project_type

            key_files = await self._find_relevant_files(task_context)
            codebase_info["key_files"] = key_files

            if project_type == "Python":
                dependencies = await self._analyze_python_dependencies()
                codebase_info["dependencies"] = dependencies

            structure = await self._analyze_project_structure()
            codebase_info["structure"] = structure

            self._project_context = codebase_info

            logger.info(
                f"[CodingAgent] 探索完成: {project_type}, {len(key_files)} 个关键文件"
            )

        except Exception as e:
            logger.error(f"[CodingAgent] 探索失败: {e}")
            codebase_info["error"] = str(e)

        return codebase_info

    async def _detect_project_type(self) -> str:
        """检测项目类型"""
        type_indicators = {
            "Python": ["setup.py", "pyproject.toml", "requirements.txt"],
            "Node.js": ["package.json"],
            "Java": ["pom.xml", "build.gradle"],
        }

        for project_type, indicators in type_indicators.items():
            for indicator in indicators:
                if os.path.exists(os.path.join(self.workspace_path, indicator)):
                    return project_type

        return "Unknown"

    async def _find_relevant_files(
        self, task_context: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """查找相关文件"""
        key_patterns = {
            "Python": ["*.py", "requirements.txt", "setup.py"],
            "Node.js": ["*.js", "package.json"],
        }

        project_type = await self._detect_project_type()
        patterns = key_patterns.get(project_type, ["*"])

        relevant_files = []

        for pattern in patterns[:3]:
            result = await self.execute_tool(
                "glob", {"pattern": pattern, "path": self.workspace_path}
            )

            if result.get("success"):
                files = result.get("output", "").strip().split("\n")
                for file_path in files[:10]:
                    if file_path and file_path not in self._explored_files:
                        relevant_files.append({"path": file_path, "type": pattern})
                        self._explored_files.add(file_path)

        return relevant_files

    async def _analyze_python_dependencies(self) -> List[str]:
        """分析Python依赖"""
        requirements_path = os.path.join(self.workspace_path, "requirements.txt")

        if os.path.exists(requirements_path):
            result = await self.execute_tool("read", {"file_path": requirements_path})

            if result.get("success"):
                content = result.get("output", "")
                dependencies = [
                    line.strip().split("==")[0]
                    for line in content.split("\n")
                    if line.strip() and not line.startswith("#")
                ]
                return dependencies

        return []

    async def _analyze_project_structure(self) -> Dict[str, Any]:
        """分析项目结构"""
        result = await self.execute_tool(
            "bash",
            {"command": f"find {self.workspace_path} -type f -name '*.py' | head -20"},
        )

        if result.get("success"):
            files = result.get("output", "").strip().split("\n")
            return {"python_files": len(files), "sample_files": files[:10]}

        return {}

    async def locate_code(
        self, keyword: str, file_pattern: str = "*.py"
    ) -> List[Dict[str, Any]]:
        """
        定位代码

        Args:
            keyword: 关键词
            file_pattern: 文件模式

        Returns:
            List: 匹配的代码位置
        """
        logger.info(f"[CodingAgent] 定位代码: {keyword}")

        result = await self.execute_tool(
            "grep",
            {"pattern": keyword, "path": self.workspace_path, "include": file_pattern},
        )

        if result.get("success"):
            output = result.get("output", "")
            matches = []

            for line in output.split("\n")[:20]:
                if ":" in line:
                    parts = line.split(":", 2)
                    if len(parts) >= 2:
                        matches.append(
                            {
                                "file": parts[0],
                                "line": parts[1],
                                "content": parts[2] if len(parts) > 2 else "",
                            }
                        )

            return matches

        return []

    async def check_code_quality(self, file_path: str) -> Dict[str, Any]:
        """
        检查代码质量

        Args:
            file_path: 文件路径

        Returns:
            Dict: 质量检查结果
        """
        if not self.enable_code_quality_check:
            return {"enabled": False}

        logger.info(f"[CodingAgent] 检查代码质量: {file_path}")

        result = await self.execute_tool("read", {"file_path": file_path})

        if not result.get("success"):
            return {"error": "无法读取文件"}

        content = result.get("output", "")

        quality_report = {
            "file_path": file_path,
            "lines": len(content.split("\n")),
            "size": len(content),
            "issues": [],
        }

        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            if len(line) > 100:
                quality_report["issues"].append(
                    {
                        "line": i,
                        "type": "long_line",
                        "message": f"行长度超过100字符: {len(line)}",
                    }
                )

            if "\t" in line:
                quality_report["issues"].append(
                    {
                        "line": i,
                        "type": "tab_indent",
                        "message": "使用Tab缩进，建议使用空格",
                    }
                )

        return quality_report

    async def run(self, message: str, stream: bool = True) -> AsyncIterator[str]:
        """主执行循环"""

        if self.enable_auto_exploration and not self._project_context:
            codebase_info = await self.explore_codebase(message)

            summary = f"""
[代码库探索结果]

项目类型: {codebase_info.get("project_type", "Unknown")}
工作目录: {codebase_info.get("workspace_path", "N/A")}
关键文件: {len(codebase_info.get("key_files", []))} 个
依赖数量: {len(codebase_info.get("dependencies", []))} 个
"""
            yield summary

        async for chunk in super().run(message, stream):
            yield chunk

    @classmethod
    def create(
        cls,
        name: str = "coding-agent",
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        max_steps: int = 30,
        workspace_path: Optional[str] = None,
        enable_auto_exploration: bool = True,
        enable_code_quality_check: bool = True,
        sandbox_manager: Optional[Any] = None,
        enable_doom_loop_detection: bool = True,
        doom_loop_threshold: int = 3,
        enable_output_truncation: bool = True,
        max_output_lines: int = 2000,
        max_output_bytes: int = 50000,
        **kwargs,
    ) -> "CodingAgent":
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
            workspace_path=workspace_path,
            enable_auto_exploration=enable_auto_exploration,
            enable_code_quality_check=enable_code_quality_check,
            sandbox_manager=sandbox_manager,
            enable_doom_loop_detection=enable_doom_loop_detection,
            doom_loop_threshold=doom_loop_threshold,
            enable_output_truncation=enable_output_truncation,
            max_output_lines=max_output_lines,
            max_output_bytes=max_output_bytes,
            **kwargs,
        )
