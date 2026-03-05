"""
Code Tools - Unified Tool Authorization System

This module implements code analysis operations:
- analyze: Analyze code structure and metrics

Version: 2.0
"""

import ast
import re
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, field

from ..decorators import tool
from ..base import ToolResult
from ..metadata import (
    ToolParameter,
    ToolCategory,
    AuthorizationRequirement,
    RiskLevel,
    RiskCategory,
)


@dataclass
class CodeMetrics:
    """Code analysis metrics."""
    lines_total: int = 0
    lines_code: int = 0
    lines_comment: int = 0
    lines_blank: int = 0
    functions: int = 0
    classes: int = 0
    imports: int = 0
    complexity: int = 0  # Cyclomatic complexity estimate
    issues: List[str] = field(default_factory=list)


class PythonAnalyzer(ast.NodeVisitor):
    """AST-based Python code analyzer."""
    
    def __init__(self):
        self.functions = 0
        self.classes = 0
        self.imports = 0
        self.complexity = 0
        self.issues: List[str] = []
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.functions += 1
        # Estimate complexity from branches
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler)):
                self.complexity += 1
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.functions += 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler)):
                self.complexity += 1
        self.generic_visit(node)
    
    def visit_ClassDef(self, node: ast.ClassDef):
        self.classes += 1
        self.generic_visit(node)
    
    def visit_Import(self, node: ast.Import):
        self.imports += len(node.names)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        self.imports += len(node.names) if node.names else 1
        self.generic_visit(node)


def analyze_python_code(content: str) -> CodeMetrics:
    """Analyze Python code and return metrics."""
    metrics = CodeMetrics()
    
    lines = content.split("\n")
    metrics.lines_total = len(lines)
    
    in_multiline_string = False
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            metrics.lines_blank += 1
        elif stripped.startswith("#"):
            metrics.lines_comment += 1
        elif stripped.startswith('"""') or stripped.startswith("'''"):
            # Toggle multiline string state
            quote = stripped[:3]
            if stripped.count(quote) == 1:
                in_multiline_string = not in_multiline_string
            metrics.lines_comment += 1
        elif in_multiline_string:
            metrics.lines_comment += 1
            if '"""' in stripped or "'''" in stripped:
                in_multiline_string = False
        else:
            metrics.lines_code += 1
    
    # Parse AST for detailed analysis
    try:
        tree = ast.parse(content)
        analyzer = PythonAnalyzer()
        analyzer.visit(tree)
        
        metrics.functions = analyzer.functions
        metrics.classes = analyzer.classes
        metrics.imports = analyzer.imports
        metrics.complexity = analyzer.complexity
        metrics.issues = analyzer.issues
        
    except SyntaxError as e:
        metrics.issues.append(f"Syntax error: {e}")
    
    return metrics


def analyze_generic_code(content: str) -> CodeMetrics:
    """Analyze generic code (non-Python) with basic metrics."""
    metrics = CodeMetrics()
    
    lines = content.split("\n")
    metrics.lines_total = len(lines)
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            metrics.lines_blank += 1
        elif stripped.startswith("//") or stripped.startswith("#"):
            metrics.lines_comment += 1
        elif stripped.startswith("/*") or stripped.startswith("*"):
            metrics.lines_comment += 1
        else:
            metrics.lines_code += 1
    
    # Count function-like patterns
    metrics.functions = len(re.findall(
        r"\b(function|def|fn|func|async\s+function)\s+\w+",
        content,
        re.IGNORECASE
    ))
    
    # Count class-like patterns
    metrics.classes = len(re.findall(
        r"\b(class|struct|interface|type)\s+\w+",
        content,
        re.IGNORECASE
    ))
    
    # Count import-like patterns
    metrics.imports = len(re.findall(
        r"^\s*(import|from|require|use|include)\s+",
        content,
        re.MULTILINE | re.IGNORECASE
    ))
    
    # Estimate complexity from control flow
    metrics.complexity = len(re.findall(
        r"\b(if|for|while|switch|case|try|catch|except)\b",
        content,
        re.IGNORECASE
    ))
    
    return metrics


@tool(
    name="analyze",
    description="Analyze code structure and metrics. Returns line counts, function/class counts, and complexity estimates.",
    category=ToolCategory.CODE,
    parameters=[
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the file to analyze",
            required=False,
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Code content to analyze (alternative to file_path)",
            required=False,
        ),
        ToolParameter(
            name="language",
            type="string",
            description="Programming language (auto-detected if file_path provided)",
            required=False,
            enum=["python", "javascript", "typescript", "java", "go", "rust", "cpp", "generic"],
        ),
    ],
    authorization=AuthorizationRequirement(
        requires_authorization=False,
        risk_level=RiskLevel.SAFE,
        risk_categories=[RiskCategory.READ_ONLY],
    ),
    tags=["code", "analysis", "metrics", "complexity"],
)
async def analyze_code(
    file_path: Optional[str] = None,
    content: Optional[str] = None,
    language: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Analyze code structure and return metrics."""
    
    # Get content
    if file_path:
        path = Path(file_path)
        if not path.exists():
            return ToolResult.error_result(f"File not found: {file_path}")
        
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return ToolResult.error_result(f"Error reading file: {str(e)}")
        
        # Auto-detect language from extension
        if not language:
            ext = path.suffix.lower()
            language_map = {
                ".py": "python",
                ".pyw": "python",
                ".js": "javascript",
                ".mjs": "javascript",
                ".cjs": "javascript",
                ".ts": "typescript",
                ".tsx": "typescript",
                ".java": "java",
                ".go": "go",
                ".rs": "rust",
                ".cpp": "cpp",
                ".cc": "cpp",
                ".cxx": "cpp",
                ".c": "cpp",
                ".h": "cpp",
                ".hpp": "cpp",
            }
            language = language_map.get(ext, "generic")
    
    if not content:
        return ToolResult.error_result(
            "Either file_path or content must be provided"
        )
    
    # Analyze based on language
    if language == "python":
        metrics = analyze_python_code(content)
    else:
        metrics = analyze_generic_code(content)
    
    # Format output
    output_lines = [
        f"Code Analysis Results",
        f"=====================",
        f"",
        f"Lines:",
        f"  Total:    {metrics.lines_total}",
        f"  Code:     {metrics.lines_code}",
        f"  Comments: {metrics.lines_comment}",
        f"  Blank:    {metrics.lines_blank}",
        f"",
        f"Structure:",
        f"  Functions: {metrics.functions}",
        f"  Classes:   {metrics.classes}",
        f"  Imports:   {metrics.imports}",
        f"",
        f"Complexity: {metrics.complexity} (cyclomatic estimate)",
    ]
    
    if metrics.issues:
        output_lines.extend([
            f"",
            f"Issues:",
        ])
        for issue in metrics.issues:
            output_lines.append(f"  - {issue}")
    
    output = "\n".join(output_lines)
    
    return ToolResult.success_result(
        output,
        metrics={
            "lines_total": metrics.lines_total,
            "lines_code": metrics.lines_code,
            "lines_comment": metrics.lines_comment,
            "lines_blank": metrics.lines_blank,
            "functions": metrics.functions,
            "classes": metrics.classes,
            "imports": metrics.imports,
            "complexity": metrics.complexity,
            "issues": metrics.issues,
        },
        language=language,
        file_path=file_path,
    )


# Export all tools for registration
__all__ = [
    "analyze_code",
    "analyze_python_code",
    "analyze_generic_code",
    "CodeMetrics",
    "PythonAnalyzer",
]
