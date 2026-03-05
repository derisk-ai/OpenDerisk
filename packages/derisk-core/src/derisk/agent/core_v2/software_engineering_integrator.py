"""
软件工程配置集成器
将软件工程最佳实践集成到 CoreV2 Agent 的 Coding 策略模式中
"""
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import logging

from .software_engineering_loader import (
    SoftwareEngineeringConfigLoader,
    SoftwareEngineeringConfig,
    CodeQualityChecker,
    get_software_engineering_config,
    check_code_quality,
)

logger = logging.getLogger(__name__)


class CheckPoint(Enum):
    PRE_WRITE = "pre_write"
    POST_WRITE = "post_write"
    PRE_EDIT = "pre_edit"
    POST_EDIT = "post_edit"
    PRE_COMMIT = "pre_commit"


@dataclass
class EngineeringCheckResult:
    passed: bool
    violations: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
    suggestions: List[Dict[str, Any]]
    metrics: Dict[str, Any]


class SoftwareEngineeringIntegrator:
    """
    软件工程配置集成器
    
    将软件工程黄金法则和最佳实践集成到 Coding 策略模式中
    """

    def __init__(
        self,
        config_dir: Optional[str] = None,
        strict_mode: bool = False,
        auto_suggest: bool = True,
    ):
        self.config_dir = config_dir
        self.strict_mode = strict_mode
        self.auto_suggest = auto_suggest
        self._config: Optional[SoftwareEngineeringConfig] = None
        self._checker: Optional[CodeQualityChecker] = None
        self._hooks: Dict[CheckPoint, List[Callable]] = {
            cp: [] for cp in CheckPoint
        }

    @property
    def config(self) -> SoftwareEngineeringConfig:
        if self._config is None:
            self._config = get_software_engineering_config(self.config_dir)
        return self._config

    @property
    def checker(self) -> CodeQualityChecker:
        if self._checker is None:
            self._checker = CodeQualityChecker(self.config)
        return self._checker

    def register_hook(self, checkpoint: CheckPoint, hook: Callable):
        """注册检查钩子"""
        self._hooks[checkpoint].append(hook)

    def check_code(
        self,
        code: str,
        language: str = "python",
        checkpoint: CheckPoint = CheckPoint.POST_WRITE,
    ) -> EngineeringCheckResult:
        """检查代码质量"""
        base_result = self.checker.check_code(code, language)

        result = EngineeringCheckResult(
            passed=base_result["passed"],
            violations=base_result["violations"],
            warnings=base_result["warnings"],
            suggestions=base_result["suggestions"],
            metrics=base_result["metrics"],
        )

        for hook in self._hooks.get(checkpoint, []):
            try:
                hook_result = hook(code, language)
                if hook_result:
                    result.violations.extend(hook_result.get("violations", []))
                    result.warnings.extend(hook_result.get("warnings", []))
                    result.suggestions.extend(hook_result.get("suggestions", []))
                    if hook_result.get("violations"):
                        result.passed = False
            except Exception as e:
                logger.warning(f"Hook execution failed: {e}")

        if result.violations and self.strict_mode:
            result.passed = False

        return result

    def get_system_prompt_enhancement(self) -> str:
        """获取系统提示增强内容"""
        return self.config.system_prompt_template

    def get_design_principles_prompt(self) -> str:
        """获取设计原则提示"""
        principles = self.config.design_principles
        lines = ["## 核心设计原则", ""]

        for key, principle in principles.items():
            enabled_mark = "" if principle.enabled else " [已禁用]"
            lines.append(f"### {principle.name}{enabled_mark}")
            lines.append(principle.description)
            if principle.check_points:
                lines.append("\n检查要点:")
                for cp in principle.check_points:
                    lines.append(f"- {cp}")
            lines.append("")

        return "\n".join(lines)

    def get_security_constraints_prompt(self) -> str:
        """获取安全约束提示"""
        constraints = self.config.security_constraints
        lines = ["## 安全约束", ""]

        critical = [c for c in constraints if c.severity.value == "critical"]
        high = [c for c in constraints if c.severity.value == "high"]

        if critical:
            lines.append("### 严重约束 (必须遵守)")
            for c in critical:
                lines.append(f"- **{c.name}**: {c.description}")
                if c.action == "reject":
                    lines.append("  - 严格禁止，代码将被拒绝")

        if high:
            lines.append("\n### 高优先级约束")
            for c in high:
                lines.append(f"- **{c.name}**: {c.description}")

        return "\n".join(lines)

    def get_architecture_rules_prompt(self) -> str:
        """获取架构规则提示"""
        rules = self.config.architecture_rules
        lines = ["## 架构规则", ""]

        if "max_function_lines" in rules:
            lines.append(f"- 函数最大行数: {rules['max_function_lines']}")
        if "max_function_params" in rules:
            lines.append(f"- 函数最大参数数: {rules['max_function_params']}")
        if "max_class_lines" in rules:
            lines.append(f"- 类最大行数: {rules['max_class_lines']}")
        if "max_nesting_level" in rules:
            lines.append(f"- 最大嵌套层级: {rules['max_nesting_level']}")

        return "\n".join(lines)

    def get_quality_gates_prompt(self) -> str:
        """获取质量门禁提示"""
        gates = self.config.quality_gates
        if not gates:
            return ""

        lines = ["## 质量门禁", ""]
        for gate in gates:
            action_desc = {
                "block": "阻塞",
                "reject": "拒绝",
                "warn": "警告",
            }.get(gate.action, gate.action)
            lines.append(f"- **{gate.name}**: 阈值 {gate.threshold} ({action_desc})")

        return "\n".join(lines)

    def get_full_prompt_enhancement(self) -> str:
        """获取完整的提示增强内容"""
        sections = [
            "# 软件工程黄金法则",
            "",
            "在编写代码时，你必须遵循以下最佳实践：",
            "",
            self.get_design_principles_prompt(),
            self.get_architecture_rules_prompt(),
            self.get_security_constraints_prompt(),
            self.get_quality_gates_prompt(),
            "",
            "## 代码质量检查清单",
            "",
            "编写代码后，请确保：",
            "- [ ] 代码遵循设计原则",
            "- [ ] 命名清晰准确",
            "- [ ] 无重复代码",
            "- [ ] 有适当的错误处理",
            "- [ ] 有类型注解",
            "- [ ] 有文档说明",
            "- [ ] 没有安全风险",
        ]

        return "\n".join(sections)

    def format_result_for_output(
        self,
        result: EngineeringCheckResult,
        include_suggestions: bool = True,
    ) -> str:
        """格式化检查结果为输出文本"""
        lines = []

        if result.passed:
            lines.append("✅ 代码质量检查通过")
        else:
            lines.append("❌ 代码质量检查未通过")

        if result.violations:
            lines.append("\n### 违规项")
            for v in result.violations:
                lines.append(f"- [{v.get('severity', 'medium')}] {v.get('name', '')}: {v.get('description', '')}")

        if result.warnings:
            lines.append("\n### 警告")
            for w in result.warnings:
                lines.append(f"- [{w.get('severity', 'low')}] {w.get('name', '')}: {w.get('description', '')}")

        if include_suggestions and result.suggestions:
            lines.append("\n### 建议改进")
            for s in result.suggestions:
                lines.append(f"- {s.get('name', '')}: {s.get('description', '')}")

        return "\n".join(lines)

    def suggest_refactoring(self, code: str, language: str = "python") -> List[Dict[str, Any]]:
        """建议重构方案"""
        suggestions = []

        result = self.check_code(code, language)

        for violation in result.violations:
            suggestion = self._generate_refactoring_suggestion(violation, code)
            if suggestion:
                suggestions.append(suggestion)

        for warning in result.warnings:
            suggestion = self._generate_refactoring_suggestion(warning, code)
            if suggestion:
                suggestions.append(suggestion)

        return suggestions

    def _generate_refactoring_suggestion(
        self,
        issue: Dict[str, Any],
        code: str,
    ) -> Optional[Dict[str, Any]]:
        """生成重构建议"""
        issue_name = issue.get("name", "")

        suggestion_map = {
            "函数过长": {
                "suggestion": "考虑将函数拆分为多个较小的函数，每个函数只做一件事",
                "pattern": "提取方法 (Extract Method)",
            },
            "参数过多": {
                "suggestion": "考虑使用参数对象或配置字典来减少参数数量",
                "pattern": "引入参数对象 (Introduce Parameter Object)",
            },
            "禁止硬编码密钥": {
                "suggestion": "使用环境变量或密钥管理服务存储敏感信息",
                "pattern": "使用环境变量 (Environment Variables)",
            },
            "禁止裸异常捕获": {
                "suggestion": "捕获具体的异常类型，避免使用裸except",
                "pattern": "具体异常捕获 (Specific Exception Handling)",
            },
        }

        for key, value in suggestion_map.items():
            if key in issue_name:
                return {
                    "issue": issue,
                    "suggestion": value["suggestion"],
                    "pattern": value["pattern"],
                }

        return None


class CodingStrategyEnhancer:
    """
    Coding 策略增强器
    
    为 Coding 策略模式提供软件工程最佳实践支持
    """

    def __init__(self, config_dir: Optional[str] = None):
        self.integrator = SoftwareEngineeringIntegrator(config_dir)

    def enhance_system_prompt(self, base_prompt: str) -> str:
        """增强系统提示"""
        enhancement = self.integrator.get_full_prompt_enhancement()
        if base_prompt:
            return f"{base_prompt}\n\n{enhancement}"
        return enhancement

    def should_check_code(
        self,
        action: str,
        file_path: str,
    ) -> bool:
        """判断是否需要检查代码"""
        code_extensions = {
            ".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c",
            ".jsx", ".tsx", ".vue", ".rb", ".php", ".swift", ".kt",
        }

        ext = None
        if "." in file_path:
            ext = "." + file_path.rsplit(".", 1)[-1]

        if ext not in code_extensions:
            return False

        return action in ["write", "edit"]

    def get_language_from_extension(self, file_path: str) -> str:
        """从文件扩展名获取语言"""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
        }

        ext = None
        if "." in file_path:
            ext = "." + file_path.rsplit(".", 1)[-1]

        return ext_map.get(ext, "text")


def create_coding_strategy_enhancer(
    config_dir: Optional[str] = None,
) -> CodingStrategyEnhancer:
    """创建 Coding 策略增强器的便捷函数"""
    return CodingStrategyEnhancer(config_dir)


def integrate_with_agent(agent: Any, config_dir: Optional[str] = None) -> Any:
    """将软件工程检查集成到 Agent"""
    enhancer = CodingStrategyEnhancer(config_dir)

    original_think = getattr(agent, "think", None)
    original_act = getattr(agent, "act", None)

    if original_think:
        async def enhanced_think(*args, **kwargs):
            return await original_think(*args, **kwargs)
        agent.think = enhanced_think

    if original_act:
        async def enhanced_act(*args, **kwargs):
            result = await original_act(*args, **kwargs)

            if hasattr(result, "content") and isinstance(result.content, str):
                file_path = kwargs.get("file_path", "")
                action = kwargs.get("action", "")

                if enhancer.should_check_code(action, file_path):
                    language = enhancer.get_language_from_extension(file_path)
                    check_result = enhancer.integrator.check_code(
                        result.content,
                        language,
                    )
                    if not check_result.passed:
                        logger.warning(
                            f"Code quality check failed for {file_path}: "
                            f"{len(check_result.violations)} violations"
                        )

            return result
        agent.act = enhanced_act

    return agent