"""
分析可视化工具模块 - 已迁移到统一工具框架

提供Agent的分析和可视化能力：
- AnalyzeDataTool: 数据分析
- AnalyzeLogTool: 日志分析
- AnalyzeCodeTool: 代码分析
- ShowChartTool: 图表展示
- ShowTableTool: 表格展示
- ShowMarkdownTool: Markdown渲染
- GenerateReportTool: 报告生成
"""

from typing import Any, Dict, List, Optional, Union
import logging
import json
import re

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from ...metadata import ToolMetadata
from ...result import ToolResult
from ...context import ToolContext

logger = logging.getLogger(__name__)


class AnalyzeDataTool(ToolBase):
    """数据分析工具 - 已迁移"""
    
    def __init__(self, analyzer: Optional[Any] = None):
        self._analyzer = analyzer
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_data",
            display_name="Analyze Data",
            description=(
                "Analyze data to extract insights, patterns, and statistics. "
                "Supports various data formats including JSON, CSV, and structured data."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["analysis", "data", "statistics"],
            timeout=60,
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "description": "Data to analyze (JSON object or array)"
                },
                "analysis_type": {
                    "type": "string",
                    "description": "Type of analysis",
                    "enum": ["summary", "statistics", "patterns", "anomalies", "correlation"],
                    "default": "summary"
                },
                "columns": {
                    "type": "array",
                    "description": "Specific columns to analyze",
                    "items": {"type": "string"}
                }
            },
            "required": ["data"]
        }
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        data = args.get("data")
        analysis_type = args.get("analysis_type", "summary")
        columns = args.get("columns", [])
        
        if data is None:
            return ToolResult(
                success=False,
                output="",
                error="数据不能为空",
                tool_name=self.name
            )
        
        try:
            if self._analyzer:
                result = await self._analyzer.analyze(data, analysis_type, columns)
                return ToolResult(
                    success=True,
                    output=str(result),
                    tool_name=self.name,
                    metadata={"analysis_type": analysis_type}
                )
            
            result = self._analyze_data(data, analysis_type, columns)
            
            return ToolResult(
                success=True,
                output=result,
                tool_name=self.name,
                metadata={
                    "analysis_type": analysis_type,
                    "data_type": type(data).__name__
                }
            )
            
        except Exception as e:
            logger.error(f"[AnalyzeDataTool] 分析失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                tool_name=self.name
            )
    
    def _analyze_data(self, data: Any, analysis_type: str, columns: List[str]) -> str:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return f"无法解析数据: {data[:100]}..."
        
        lines = ["## 数据分析结果\n"]
        
        if isinstance(data, dict):
            lines.append("### 基本信息")
            lines.append(f"- 字段数量: {len(data)}")
            lines.append(f"- 字段列表: {', '.join(data.keys())}")
            
            if analysis_type in ["summary", "statistics"]:
                lines.append("\n### 字段详情")
                for key, value in data.items():
                    if columns and key not in columns:
                        continue
                    value_type = type(value).__name__
                    value_repr = str(value)[:100]
                    lines.append(f"- **{key}** ({value_type}): {value_repr}")
        
        elif isinstance(data, list):
            lines.append("### 基本信息")
            lines.append(f"- 数据条数: {len(data)}")
            
            if data and isinstance(data[0], dict):
                keys = set()
                for item in data:
                    if isinstance(item, dict):
                        keys.update(item.keys())
                lines.append(f"- 字段列表: {', '.join(keys)}")
                
                if analysis_type in ["statistics", "summary"]:
                    lines.append("\n### 统计信息")
                    for key in keys:
                        values = [item.get(key) for item in data if isinstance(item, dict) and key in item]
                        numeric_values = [v for v in values if isinstance(v, (int, float))]
                        
                        if numeric_values:
                            lines.append(f"- **{key}**:")
                            lines.append(f"  - 数量: {len(numeric_values)}")
                            lines.append(f"  - 最小值: {min(numeric_values)}")
                            lines.append(f"  - 最大值: {max(numeric_values)}")
                            lines.append(f"  - 平均值: {sum(numeric_values) / len(numeric_values):.2f}")
        else:
            lines.append(f"数据类型: {type(data).__name__}\n值: {str(data)}")
        
        return "\n".join(lines)


class AnalyzeLogTool(ToolBase):
    """日志分析工具 - 已迁移"""
    
    def __init__(self, analyzer: Optional[Any] = None):
        self._analyzer = analyzer
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_log",
            display_name="Analyze Log",
            description=(
                "Analyze log files to identify errors, warnings, and patterns. "
                "Supports various log formats."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["analysis", "log", "debug"],
            timeout=60,
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "log_content": {
                    "type": "string",
                    "description": "Log content to analyze"
                },
                "log_type": {
                    "type": "string",
                    "description": "Type of log format",
                    "enum": ["auto", "json", "text", "syslog", "apache", "nginx"],
                    "default": "auto"
                },
                "focus": {
                    "type": "string",
                    "description": "What to focus on",
                    "enum": ["errors", "warnings", "all", "patterns", "timeline"],
                    "default": "all"
                }
            },
            "required": ["log_content"]
        }
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        log_content = args.get("log_content", "")
        log_type = args.get("log_type", "auto")
        focus = args.get("focus", "all")
        
        if not log_content:
            return ToolResult(
                success=False,
                output="",
                error="日志内容不能为空",
                tool_name=self.name
            )
        
        try:
            result = self._analyze_logs(log_content, log_type, focus)
            
            return ToolResult(
                success=True,
                output=result,
                tool_name=self.name,
                metadata={"log_type": log_type, "focus": focus}
            )
            
        except Exception as e:
            logger.error(f"[AnalyzeLogTool] 分析失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                tool_name=self.name
            )
    
    def _analyze_logs(self, content: str, log_type: str, focus: str) -> str:
        lines = content.split("\n")
        
        errors = []
        warnings = []
        
        error_patterns = [r'\bERROR\b', r'\berror\b', r'\bFATAL\b', r'\bfatal\b', r'\bException\b']
        warning_patterns = [r'\bWARNING\b', r'\bwarn\b', r'\bWARN\b']
        
        for line in lines:
            if any(re.search(p, line) for p in error_patterns):
                errors.append(line)
            elif any(re.search(p, line) for p in warning_patterns):
                warnings.append(line)
        
        result = ["## 日志分析结果\n"]
        result.append(f"### 概览")
        result.append(f"- 总行数: {len(lines)}")
        result.append(f"- 错误数: {len(errors)}")
        result.append(f"- 警告数: {len(warnings)}")
        
        if focus in ["errors", "all"] and errors:
            result.append(f"\n### 错误 ({len(errors)} 条)")
            for err in errors[:10]:
                result.append(f"- {err[:200]}")
            if len(errors) > 10:
                result.append(f"... 还有 {len(errors) - 10} 条错误")
        
        if focus in ["warnings", "all"] and warnings:
            result.append(f"\n### 警告 ({len(warnings)} 条)")
            for warn in warnings[:10]:
                result.append(f"- {warn[:200]}")
            if len(warnings) > 10:
                result.append(f"... 还有 {len(warnings) - 10} 条警告")
        
        return "\n".join(result)


class AnalyzeCodeTool(ToolBase):
    """代码分析工具 - 已迁移"""
    
    def __init__(self, analyzer: Optional[Any] = None):
        self._analyzer = analyzer
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_code",
            display_name="Analyze Code",
            description=(
                "Analyze code for quality, issues, and improvements. "
                "Supports multiple programming languages."
            ),
            category=ToolCategory.CODE,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["analysis", "code", "quality"],
            timeout=60,
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Code to analyze"
                },
                "language": {
                    "type": "string",
                    "description": "Programming language",
                    "default": "auto"
                },
                "analysis_type": {
                    "type": "string",
                    "description": "Type of analysis",
                    "enum": ["quality", "security", "complexity", "all"],
                    "default": "all"
                }
            },
            "required": ["code"]
        }
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        code = args.get("code", "")
        language = args.get("language", "auto")
        analysis_type = args.get("analysis_type", "all")
        
        if not code:
            return ToolResult(
                success=False,
                output="",
                error="代码不能为空",
                tool_name=self.name
            )
        
        try:
            result = self._analyze_code(code, language, analysis_type)
            
            return ToolResult(
                success=True,
                output=result,
                tool_name=self.name,
                metadata={
                    "language": language,
                    "analysis_type": analysis_type,
                    "lines": len(code.split("\n"))
                }
            )
            
        except Exception as e:
            logger.error(f"[AnalyzeCodeTool] 分析失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                tool_name=self.name
            )
    
    def _analyze_code(self, code: str, language: str, analysis_type: str) -> str:
        lines = code.split("\n")
        
        result = ["## 代码分析结果\n"]
        
        result.append("### 基本信息")
        result.append(f"- 总行数: {len(lines)}")
        result.append(f"- 字符数: {len(code)}")
        
        if language == "auto":
            language = self._detect_language(code)
        result.append(f"- 检测语言: {language}")
        
        if analysis_type in ["quality", "all"]:
            result.append("\n### 代码质量")
            
            blank_lines = sum(1 for line in lines if not line.strip())
            result.append(f"- 空白行数: {blank_lines} ({blank_lines/len(lines)*100:.1f}%)")
            
            code_lines = len(lines) - blank_lines
            result.append(f"- 代码行数: {code_lines}")
        
        if analysis_type in ["complexity", "all"]:
            result.append("\n### 复杂度分析")
            
            max_line_length = max(len(line) for line in lines) if lines else 0
            result.append(f"- 最大行长: {max_line_length}")
            
            indent_levels = set()
            for line in lines:
                indent = len(line) - len(line.lstrip())
                indent_levels.add(indent // 4)
            result.append(f"- 缩进层级: {max(indent_levels) if indent_levels else 0}")
        
        return "\n".join(result)
    
    def _detect_language(self, code: str) -> str:
        if "def " in code or "import " in code:
            return "python"
        if "function " in code or "const " in code:
            return "javascript"
        if "package " in code or "func " in code:
            return "go"
        return "unknown"


class ShowChartTool(ToolBase):
    """图表展示工具 - 已迁移"""
    
    def __init__(self, chart_renderer: Optional[Any] = None):
        self._chart_renderer = chart_renderer
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="show_chart",
            display_name="Show Chart",
            description=(
                "Display data as a chart (bar, line, pie, etc.). "
                "Use this tool to visualize data for better understanding."
            ),
            category=ToolCategory.VISUALIZATION,
            risk_level=ToolRiskLevel.SAFE,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["visualization", "chart", "graph"],
            timeout=30,
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "description": "Data for the chart"
                },
                "chart_type": {
                    "type": "string",
                    "description": "Type of chart",
                    "enum": ["bar", "line", "pie", "scatter", "area", "radar"],
                    "default": "bar"
                },
                "title": {
                    "type": "string",
                    "description": "Chart title"
                }
            },
            "required": ["data"]
        }
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        data = args.get("data", {})
        chart_type = args.get("chart_type", "bar")
        title = args.get("title", "Chart")
        
        result = f"📊 **{title}** ({chart_type} chart)\n\n"
        result += f"```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```"
        
        return ToolResult(
            success=True,
            output=result,
            tool_name=self.name,
            metadata={"chart_type": chart_type, "title": title}
        )


class ShowTableTool(ToolBase):
    """表格展示工具 - 已迁移"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="show_table",
            display_name="Show Table",
            description=(
                "Display data as a formatted table. "
                "Use this tool to present structured data in a readable format."
            ),
            category=ToolCategory.VISUALIZATION,
            risk_level=ToolRiskLevel.SAFE,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["visualization", "table", "data"],
            timeout=30,
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "data": {
                    "type": "array",
                    "description": "Table data (array of objects)",
                    "items": {"type": "object"}
                },
                "columns": {
                    "type": "array",
                    "description": "Column names to display",
                    "items": {"type": "string"}
                },
                "title": {
                    "type": "string",
                    "description": "Table title"
                }
            },
            "required": ["data"]
        }
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        data = args.get("data", [])
        columns = args.get("columns", [])
        title = args.get("title", "Table")
        
        if not data:
            return ToolResult(
                success=True,
                output=f"📋 **{title}**\n\n(空表格)",
                tool_name=self.name
            )
        
        if not columns and data:
            columns = list(data[0].keys()) if isinstance(data[0], dict) else []
        
        result = f"📋 **{title}**\n\n"
        result += "| " + " | ".join(columns) + " |\n"
        result += "| " + " | ".join(["---"] * len(columns)) + " |\n"
        
        for row in data[:20]:
            if isinstance(row, dict):
                values = [str(row.get(col, ""))[:50] for col in columns]
            else:
                values = [str(row)[:50]]
            result += "| " + " | ".join(values) + " |\n"
        
        if len(data) > 20:
            result += f"\n*... 还有 {len(data) - 20} 行数据*"
        
        return ToolResult(
            success=True,
            output=result,
            tool_name=self.name,
            metadata={"rows": len(data), "columns": len(columns)}
        )


class ShowMarkdownTool(ToolBase):
    """Markdown渲染工具 - 已迁移"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="show_markdown",
            display_name="Show Markdown",
            description="Render and display Markdown content.",
            category=ToolCategory.VISUALIZATION,
            risk_level=ToolRiskLevel.SAFE,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["visualization", "markdown", "document"],
            timeout=10,
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Markdown content to render"
                }
            },
            "required": ["content"]
        }
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        content = args.get("content", "")
        
        return ToolResult(
            success=True,
            output=content,
            tool_name=self.name,
            metadata={"format": "markdown"}
        )


class GenerateReportTool(ToolBase):
    """报告生成工具 - 已迁移"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="generate_report",
            display_name="Generate Report",
            description=(
                "Generate a formatted report from analysis results. "
                "Supports various report formats and templates."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["analysis", "report", "document"],
            timeout=60,
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Report title"
                },
                "sections": {
                    "type": "array",
                    "description": "Report sections",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "content": {"type": "string"}
                        }
                    }
                },
                "format": {
                    "type": "string",
                    "description": "Output format",
                    "enum": ["markdown", "html", "text"],
                    "default": "markdown"
                }
            },
            "required": ["title"]
        }
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        title = args.get("title", "Report")
        sections = args.get("sections", [])
        format_type = args.get("format", "markdown")
        
        result = f"# {title}\n\n"
        
        for section in sections:
            heading = section.get("heading", "")
            content = section.get("content", "")
            
            if heading:
                result += f"## {heading}\n\n"
            if content:
                result += f"{content}\n\n"
        
        return ToolResult(
            success=True,
            output=result,
            tool_name=self.name,
            metadata={"format": format_type, "sections": len(sections)}
        )


def register_analysis_tools(registry) -> None:
    """注册分析工具"""
    from ...registry import ToolRegistry
    
    registry.register(AnalyzeDataTool())
    registry.register(AnalyzeLogTool())
    registry.register(AnalyzeCodeTool())
    registry.register(ShowChartTool())
    registry.register(ShowTableTool())
    registry.register(ShowMarkdownTool())
    registry.register(GenerateReportTool())
    
    logger.info("[AnalysisTools] 已注册 7 个分析工具到统一框架")