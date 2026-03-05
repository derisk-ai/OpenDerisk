"""
分析可视化工具集合

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

from .tool_base import ToolBase, ToolMetadata, ToolResult, ToolRegistry

logger = logging.getLogger(__name__)


class AnalyzeDataTool(ToolBase):
    """数据分析工具"""
    
    def __init__(self, analyzer: Optional[Any] = None):
        self._analyzer = analyzer
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_data",
            description=(
                "Analyze data to extract insights, patterns, and statistics. "
                "Supports various data formats including JSON, CSV, and structured data."
            ),
            parameters={
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
            },
            requires_permission=False,
            dangerous=False,
            category="analysis"
        )
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        data = args.get("data")
        analysis_type = args.get("analysis_type", "summary")
        columns = args.get("columns", [])
        
        if data is None:
            return ToolResult(
                success=False,
                output="",
                error="数据不能为空"
            )
        
        try:
            if self._analyzer:
                result = await self._analyzer.analyze(data, analysis_type, columns)
                return ToolResult(
                    success=True,
                    output=str(result),
                    metadata={"analysis_type": analysis_type}
                )
            
            result = self._analyze_data(data, analysis_type, columns)
            
            return ToolResult(
                success=True,
                output=result,
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
                error=str(e)
            )
    
    def _analyze_data(self, data: Any, analysis_type: str, columns: List[str]) -> str:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return f"无法解析数据: {data[:100]}..."
        
        if isinstance(data, dict):
            return self._analyze_dict(data, analysis_type, columns)
        elif isinstance(data, list):
            return self._analyze_list(data, analysis_type, columns)
        else:
            return f"数据类型: {type(data).__name__}\n值: {str(data)}"
    
    def _analyze_dict(self, data: Dict, analysis_type: str, columns: List[str]) -> str:
        lines = ["## 数据分析结果\n"]
        
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
        
        return "\n".join(lines)
    
    def _analyze_list(self, data: List, analysis_type: str, columns: List[str]) -> str:
        lines = ["## 数据分析结果\n"]
        
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
                        lines.append(f"  - 数值数量: {len(numeric_values)}")
                        lines.append(f"  - 最小值: {min(numeric_values)}")
                        lines.append(f"  - 最大值: {max(numeric_values)}")
                        lines.append(f"  - 平均值: {sum(numeric_values) / len(numeric_values):.2f}")
        
        return "\n".join(lines)


class AnalyzeLogTool(ToolBase):
    """日志分析工具"""
    
    def __init__(self, analyzer: Optional[Any] = None):
        self._analyzer = analyzer
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_log",
            description=(
                "Analyze log files to identify errors, warnings, and patterns. "
                "Supports various log formats."
            ),
            parameters={
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
                    },
                    "time_range": {
                        "type": "string",
                        "description": "Time range to analyze (e.g., '1h', '24h', '7d')"
                    }
                },
                "required": ["log_content"]
            },
            requires_permission=False,
            dangerous=False,
            category="analysis"
        )
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        log_content = args.get("log_content", "")
        log_type = args.get("log_type", "auto")
        focus = args.get("focus", "all")
        time_range = args.get("time_range")
        
        if not log_content:
            return ToolResult(
                success=False,
                output="",
                error="日志内容不能为空"
            )
        
        try:
            result = self._analyze_logs(log_content, log_type, focus)
            
            return ToolResult(
                success=True,
                output=result,
                metadata={
                    "log_type": log_type,
                    "focus": focus,
                    "time_range": time_range
                }
            )
            
        except Exception as e:
            logger.error(f"[AnalyzeLogTool] 分析失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
    
    def _analyze_logs(self, content: str, log_type: str, focus: str) -> str:
        lines = content.split("\n")
        
        errors = []
        warnings = []
        info = []
        
        error_patterns = [r'\bERROR\b', r'\berror\b', r'\bFATAL\b', r'\bfatal\b', r'\bException\b']
        warning_patterns = [r'\bWARNING\b', r'\bwarn\b', r'\bWARN\b']
        
        for line in lines:
            if any(re.search(p, line) for p in error_patterns):
                errors.append(line)
            elif any(re.search(p, line) for p in warning_patterns):
                warnings.append(line)
            else:
                info.append(line)
        
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
    """代码分析工具"""
    
    def __init__(self, analyzer: Optional[Any] = None):
        self._analyzer = analyzer
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_code",
            description=(
                "Analyze code for quality, issues, and improvements. "
                "Supports multiple programming languages."
            ),
            parameters={
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
            },
            requires_permission=False,
            dangerous=False,
            category="analysis"
        )
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        code = args.get("code", "")
        language = args.get("language", "auto")
        analysis_type = args.get("analysis_type", "all")
        
        if not code:
            return ToolResult(
                success=False,
                output="",
                error="代码不能为空"
            )
        
        try:
            result = self._analyze_code(code, language, analysis_type)
            
            return ToolResult(
                success=True,
                output=result,
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
                error=str(e)
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
            
            comment_lines = self._count_comments(lines, language)
            result.append(f"- 注释行数: {comment_lines} ({comment_lines/len(lines)*100:.1f}%)")
            
            code_lines = len(lines) - blank_lines - comment_lines
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
        if "def " in code or "import " in code or "class " in code:
            if ":" in code and code.strip().startswith(("def ", "class ", "import ")):
                return "python"
        if "function " in code or "const " in code or "let " in code:
            return "javascript"
        if "package " in code or "func " in code:
            return "go"
        if "#include" in code or "int main" in code:
            return "c"
        if "public class" in code or "private " in code:
            return "java"
        return "unknown"
    
    def _count_comments(self, lines: List[str], language: str) -> int:
        count = 0
        in_block_comment = False
        
        for line in lines:
            stripped = line.strip()
            
            if language == "python":
                if stripped.startswith("#"):
                    count += 1
                if '"""' in stripped or "'''" in stripped:
                    in_block_comment = not in_block_comment
                    count += 1
            else:
                if stripped.startswith("//") or stripped.startswith("#"):
                    count += 1
                if "/*" in stripped:
                    in_block_comment = True
                if "*/" in stripped:
                    in_block_comment = False
                    count += 1
                elif in_block_comment:
                    count += 1
        
        return count


class ShowChartTool(ToolBase):
    """图表展示工具"""
    
    def __init__(self, chart_renderer: Optional[Any] = None):
        self._chart_renderer = chart_renderer
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="show_chart",
            description=(
                "Display data as a chart (bar, line, pie, etc.). "
                "Use this tool to visualize data for better understanding."
            ),
            parameters={
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
                    },
                    "x_label": {
                        "type": "string",
                        "description": "X-axis label"
                    },
                    "y_label": {
                        "type": "string",
                        "description": "Y-axis label"
                    },
                    "options": {
                        "type": "object",
                        "description": "Additional chart options"
                    }
                },
                "required": ["data"]
            },
            requires_permission=False,
            dangerous=False,
            category="visualization"
        )
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        data = args.get("data")
        chart_type = args.get("chart_type", "bar")
        title = args.get("title", "图表")
        x_label = args.get("x_label", "")
        y_label = args.get("y_label", "")
        options = args.get("options", {})
        
        if data is None:
            return ToolResult(
                success=False,
                output="",
                error="数据不能为空"
            )
        
        try:
            if self._chart_renderer:
                result = await self._chart_renderer.render(
                    data=data,
                    chart_type=chart_type,
                    title=title,
                    x_label=x_label,
                    y_label=y_label,
                    options=options
                )
                return ToolResult(
                    success=True,
                    output=str(result),
                    metadata={"chart_type": chart_type}
                )
            
            chart_spec = self._create_chart_spec(data, chart_type, title, x_label, y_label, options)
            
            return ToolResult(
                success=True,
                output=f"[Chart: {chart_type}]\n{json.dumps(chart_spec, indent=2, ensure_ascii=False)}",
                metadata={
                    "chart_type": chart_type,
                    "chart_spec": chart_spec,
                    "visualization_type": "chart"
                }
            )
            
        except Exception as e:
            logger.error(f"[ShowChartTool] 创建图表失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
    
    def _create_chart_spec(
        self, 
        data: Any, 
        chart_type: str,
        title: str,
        x_label: str,
        y_label: str,
        options: Dict
    ) -> Dict[str, Any]:
        return {
            "type": chart_type,
            "title": {"text": title},
            "data": data,
            "xAxis": {"title": {"text": x_label}} if x_label else {},
            "yAxis": {"title": {"text": y_label}} if y_label else {},
            "options": options
        }


class ShowTableTool(ToolBase):
    """表格展示工具"""
    
    def __init__(self, table_renderer: Optional[Any] = None):
        self._table_renderer = table_renderer
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="show_table",
            description=(
                "Display data as a formatted table. "
                "Use this tool to present structured data clearly."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "description": "Table data (array of rows or objects)",
                        "items": {}
                    },
                    "headers": {
                        "type": "array",
                        "description": "Column headers",
                        "items": {"type": "string"}
                    },
                    "title": {
                        "type": "string",
                        "description": "Table title"
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format",
                        "enum": ["markdown", "html", "json"],
                        "default": "markdown"
                    }
                },
                "required": ["data"]
            },
            requires_permission=False,
            dangerous=False,
            category="visualization"
        )
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        data = args.get("data", [])
        headers = args.get("headers", [])
        title = args.get("title", "表格")
        format_type = args.get("format", "markdown")
        
        if not data:
            return ToolResult(
                success=False,
                output="",
                error="数据不能为空"
            )
        
        try:
            if self._table_renderer:
                result = await self._table_renderer.render(data, headers, title, format_type)
                return ToolResult(
                    success=True,
                    output=str(result),
                    metadata={"format": format_type}
                )
            
            if not headers and data and isinstance(data[0], dict):
                headers = list(data[0].keys())
            
            table_str = self._format_table(data, headers, title, format_type)
            
            return ToolResult(
                success=True,
                output=table_str,
                metadata={
                    "format": format_type,
                    "rows": len(data),
                    "columns": len(headers)
                }
            )
            
        except Exception as e:
            logger.error(f"[ShowTableTool] 创建表格失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
    
    def _format_table(
        self, 
        data: List, 
        headers: List[str], 
        title: str,
        format_type: str
    ) -> str:
        if format_type == "markdown":
            return self._format_markdown_table(data, headers, title)
        elif format_type == "html":
            return self._format_html_table(data, headers, title)
        else:
            return json.dumps({"title": title, "headers": headers, "data": data}, ensure_ascii=False, indent=2)
    
    def _format_markdown_table(self, data: List, headers: List[str], title: str) -> str:
        lines = [f"### {title}\n"]
        
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        
        for row in data[:20]:
            if isinstance(row, dict):
                values = [str(row.get(h, "")) for h in headers]
            else:
                values = [str(v) for v in (row if isinstance(row, list) else [row])]
            lines.append("| " + " | ".join(values) + " |")
        
        if len(data) > 20:
            lines.append(f"\n*... 共 {len(data)} 行数据*")
        
        return "\n".join(lines)
    
    def _format_html_table(self, data: List, headers: List[str], title: str) -> str:
        lines = [f"<h3>{title}</h3>", "<table border='1'>"]
        
        lines.append("<tr>")
        for h in headers:
            lines.append(f"<th>{h}</th>")
        lines.append("</tr>")
        
        for row in data[:20]:
            lines.append("<tr>")
            if isinstance(row, dict):
                for h in headers:
                    lines.append(f"<td>{row.get(h, '')}</td>")
            else:
                for v in (row if isinstance(row, list) else [row]):
                    lines.append(f"<td>{v}</td>")
            lines.append("</tr>")
        
        lines.append("</table>")
        
        return "\n".join(lines)


class ShowMarkdownTool(ToolBase):
    """Markdown渲染工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="show_markdown",
            description=(
                "Render Markdown content. "
                "Use this tool to display formatted documentation or reports."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Markdown content to render"
                    },
                    "render_html": {
                        "type": "boolean",
                        "description": "Whether to render as HTML",
                        "default": False
                    }
                },
                "required": ["content"]
            },
            requires_permission=False,
            dangerous=False,
            category="visualization"
        )
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        content = args.get("content", "")
        render_html = args.get("render_html", False)
        
        if not content:
            return ToolResult(
                success=False,
                output="",
                error="Markdown内容不能为空"
            )
        
        if render_html:
            try:
                import markdown
                html_content = markdown.markdown(content)
                return ToolResult(
                    success=True,
                    output=html_content,
                    metadata={"format": "html"}
                )
            except ImportError:
                pass
        
        return ToolResult(
            success=True,
            output=f"[Markdown]\n{content}",
            metadata={
                "format": "markdown",
                "length": len(content)
            }
        )


class GenerateReportTool(ToolBase):
    """报告生成工具"""
    
    def __init__(self, report_generator: Optional[Any] = None):
        self._report_generator = report_generator
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="generate_report",
            description=(
                "Generate a structured report from data. "
                "Use this tool to create formal documentation or analysis reports."
            ),
            parameters={
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
                                "content": {"type": "string"},
                                "data": {}
                            }
                        }
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format",
                        "enum": ["markdown", "html", "json"],
                        "default": "markdown"
                    },
                    "include_summary": {
                        "type": "boolean",
                        "description": "Include executive summary",
                        "default": True
                    }
                },
                "required": ["title"]
            },
            requires_permission=False,
            dangerous=False,
            category="visualization"
        )
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        title = args.get("title", "报告")
        sections = args.get("sections", [])
        format_type = args.get("format", "markdown")
        include_summary = args.get("include_summary", True)
        
        try:
            if self._report_generator:
                result = await self._report_generator.generate(
                    title=title,
                    sections=sections,
                    format=format_type
                )
                return ToolResult(
                    success=True,
                    output=result,
                    metadata={"format": format_type}
                )
            
            report = self._generate_report(title, sections, format_type, include_summary)
            
            return ToolResult(
                success=True,
                output=report,
                metadata={
                    "format": format_type,
                    "sections": len(sections)
                }
            )
            
        except Exception as e:
            logger.error(f"[GenerateReportTool] 生成报告失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
    
    def _generate_report(
        self, 
        title: str, 
        sections: List[Dict], 
        format_type: str,
        include_summary: bool
    ) -> str:
        lines = []
        
        lines.append(f"# {title}")
        lines.append("")
        
        if include_summary and sections:
            lines.append("## 概要")
            lines.append(f"本报告包含 {len(sections)} 个部分。")
            lines.append("")
        
        for i, section in enumerate(sections, 1):
            heading = section.get("heading", f"第{i}部分")
            content = section.get("content", "")
            data = section.get("data")
            
            lines.append(f"## {heading}")
            lines.append("")
            
            if content:
                lines.append(content)
                lines.append("")
            
            if data:
                lines.append("```json")
                lines.append(json.dumps(data, indent=2, ensure_ascii=False))
                lines.append("```")
                lines.append("")
        
        return "\n".join(lines)


def register_analysis_tools(registry: ToolRegistry) -> ToolRegistry:
    """注册所有分析可视化工具"""
    registry.register(AnalyzeDataTool())
    registry.register(AnalyzeLogTool())
    registry.register(AnalyzeCodeTool())
    registry.register(ShowChartTool())
    registry.register(ShowTableTool())
    registry.register(ShowMarkdownTool())
    registry.register(GenerateReportTool())
    
    logger.info(f"[Tools] 已注册分析可视化工具")
    
    return registry