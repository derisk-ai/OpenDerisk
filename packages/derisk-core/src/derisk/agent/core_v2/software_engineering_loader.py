"""
软件工程配置加载器
用于加载和应用软件工程最佳实践配置到 Coding 策略模式
"""
import os
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class DesignPrinciple:
    name: str
    description: str
    enabled: bool = True
    check_points: List[str] = field(default_factory=list)
    violation_penalty: str = "medium"


@dataclass
class AntiPattern:
    name: str
    description: str
    detection_rules: Dict[str, Any]
    severity: Severity
    suggestion: str = ""


@dataclass
class QualityGate:
    name: str
    threshold: float
    action: str  # warn, block, reject
    description: str = ""


@dataclass
class SecurityConstraint:
    id: str
    name: str
    description: str
    patterns: List[str]
    severity: Severity
    action: str  # reject, warn, suggest


@dataclass
class SoftwareEngineeringConfig:
    design_principles: Dict[str, DesignPrinciple] = field(default_factory=dict)
    architecture_rules: Dict[str, Any] = field(default_factory=dict)
    quality_gates: List[QualityGate] = field(default_factory=list)
    security_constraints: List[SecurityConstraint] = field(default_factory=list)
    anti_patterns: List[AntiPattern] = field(default_factory=list)
    code_style_rules: List[str] = field(default_factory=list)
    system_prompt_template: str = ""


class SoftwareEngineeringConfigLoader:
    """软件工程配置加载器"""

    DEFAULT_CONFIG_DIR = "configs/engineering"

    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = Path(config_dir or self.DEFAULT_CONFIG_DIR)
        self._principles_cache: Optional[Dict] = None
        self._constraints_cache: Optional[Dict] = None

    def load_all_configs(self) -> SoftwareEngineeringConfig:
        """加载所有软件工程配置"""
        principles = self._load_principles_config()
        constraints = self._load_constraints_config()

        config = SoftwareEngineeringConfig()

        if principles:
            config.design_principles = self._parse_design_principles(principles)
            config.architecture_rules = principles.get("architecture_patterns", {})
            config.anti_patterns = self._parse_anti_patterns(principles)
            config.system_prompt_template = self._build_system_prompt(principles)

        if constraints:
            config.quality_gates = self._parse_quality_gates(constraints)
            config.security_constraints = self._parse_security_constraints(constraints)
            config.code_style_rules = self._extract_code_style_rules(constraints)

        return config

    def _load_principles_config(self) -> Dict[str, Any]:
        """加载设计原则配置"""
        if self._principles_cache is not None:
            return self._principles_cache

        config_path = self.config_dir / "software_engineering_principles.yaml"
        if not config_path.exists():
            logger.warning(f"Software engineering principles config not found: {config_path}")
            return {}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self._principles_cache = yaml.safe_load(f) or {}
            return self._principles_cache
        except Exception as e:
            logger.error(f"Failed to load principles config: {e}")
            return {}

    def _load_constraints_config(self) -> Dict[str, Any]:
        """加载研发约束配置"""
        if self._constraints_cache is not None:
            return self._constraints_cache

        config_path = self.config_dir / "research_development_constraints.yaml"
        if not config_path.exists():
            logger.warning(f"R&D constraints config not found: {config_path}")
            return {}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self._constraints_cache = yaml.safe_load(f) or {}
            return self._constraints_cache
        except Exception as e:
            logger.error(f"Failed to load constraints config: {e}")
            return {}

    def _parse_design_principles(self, config: Dict) -> Dict[str, DesignPrinciple]:
        """解析设计原则"""
        principles = {}
        dp_config = config.get("design_principles", {})

        solid = dp_config.get("solid", {})
        if solid.get("enabled", True):
            for key, value in solid.get("principles", {}).items():
                principles[key] = DesignPrinciple(
                    name=value.get("name", key),
                    description=value.get("description", ""),
                    enabled=value.get("enabled", True),
                    check_points=value.get("check_points", []),
                    violation_penalty=value.get("violation_penalty", "medium"),
                )

        for principle_name in ["kiss", "dry", "yagni"]:
            if dp_config.get(principle_name, {}).get("enabled", True):
                p = dp_config[principle_name]
                principles[principle_name] = DesignPrinciple(
                    name=p.get("name", principle_name.upper()),
                    description=p.get("description", ""),
                    enabled=True,
                )

        return principles

    def _parse_anti_patterns(self, config: Dict) -> List[AntiPattern]:
        """解析反模式"""
        anti_patterns = []
        ap_config = config.get("anti_patterns", {})
        if not ap_config.get("enabled", True):
            return anti_patterns

        for key, value in ap_config.get("patterns", {}).items():
            severity = Severity.MEDIUM
            if isinstance(value.get("severity"), str):
                try:
                    severity = Severity(value["severity"].lower())
                except ValueError:
                    pass

            anti_patterns.append(AntiPattern(
                name=value.get("name", key),
                description=value.get("description", ""),
                detection_rules=value.get("detection", {}),
                severity=severity,
                suggestion=value.get("suggestion", ""),
            ))

        return anti_patterns

    def _parse_quality_gates(self, config: Dict) -> List[QualityGate]:
        """解析质量门禁"""
        gates = []
        qg_config = config.get("quality_gates", {})

        code_quality = qg_config.get("code_quality", {})
        if code_quality.get("enabled", True):
            for metric, value in code_quality.get("metrics", {}).items():
                if isinstance(value, dict):
                    gates.append(QualityGate(
                        name=metric,
                        threshold=value.get("threshold", 0),
                        action=value.get("action", "warn"),
                        description=f"代码质量指标: {metric}",
                    ))

        test_quality = qg_config.get("test_quality", {})
        if test_quality.get("enabled", True):
            coverage = test_quality.get("metrics", {}).get("code_coverage", {})
            if coverage:
                gates.append(QualityGate(
                    name="code_coverage",
                    threshold=coverage.get("line", 80),
                    action=coverage.get("action", "warn"),
                    description="代码覆盖率要求",
                ))

        return gates

    def _parse_security_constraints(self, config: Dict) -> List[SecurityConstraint]:
        """解析安全约束"""
        constraints = []
        cc_config = config.get("code_constraints", {})
        forbidden = cc_config.get("forbidden", [])

        for item in forbidden:
            severity = Severity.MEDIUM
            if isinstance(item.get("severity"), str):
                try:
                    severity = Severity(item["severity"].lower())
                except ValueError:
                    pass

            constraints.append(SecurityConstraint(
                id=item.get("id", ""),
                name=item.get("name", ""),
                description=item.get("description", ""),
                patterns=item.get("patterns", []),
                severity=severity,
                action=item.get("action", "warn"),
            ))

        return constraints

    def _extract_code_style_rules(self, config: Dict) -> List[str]:
        """提取代码风格规则"""
        rules = []
        naming = config.get("code_quality", {}).get("naming", {})

        if naming.get("enabled", True):
            for category, value in naming.get("rules", {}).items():
                pattern = value.get("pattern", "")
                if pattern:
                    rules.append(f"{category}: {pattern}")

        return rules

    def _build_system_prompt(self, config: Dict) -> str:
        """构建系统提示模板"""
        injection = config.get("injection", {})
        if not injection.get("system_prompt", {}).get("enabled", True):
            return ""

        template = injection.get("system_prompt", {}).get("template", "")
        if template:
            design_principles = self._format_design_principles_for_prompt(config)
            architecture = self._format_architecture_for_prompt(config)
            quality = self._format_quality_for_prompt(config)
            security = self._format_security_for_prompt(config)

            template = template.replace("{design_principles}", design_principles)
            template = template.replace("{architecture_guidelines}", architecture)
            template = template.replace("{quality_standards}", quality)
            template = template.replace("{security_constraints}", security)

        return template

    def _format_design_principles_for_prompt(self, config: Dict) -> str:
        """格式化设计原则为提示文本"""
        lines = []
        dp = config.get("design_principles", {})

        solid = dp.get("solid", {})
        if solid.get("enabled", True):
            lines.append("### SOLID原则")
            for key, value in solid.get("principles", {}).items():
                lines.append(f"- **{value.get('name', key)}**: {value.get('description', '').split(chr(10))[0]}")

        for p in ["kiss", "dry", "yagni"]:
            if dp.get(p, {}).get("enabled", True):
                p_config = dp[p]
                lines.append(f"- **{p_config.get('name', p.upper())}**: {p_config.get('description', '').split(chr(10))[0]}")

        return "\n".join(lines)

    def _format_architecture_for_prompt(self, config: Dict) -> str:
        """格式化架构规则为提示文本"""
        lines = []
        arch = config.get("architecture_patterns", {})

        if arch.get("layered_architecture", {}).get("enabled", True):
            lines.append("### 分层架构")
            layers = arch["layered_architecture"].get("layers", {})
            for layer_name, layer_config in layers.items():
                lines.append(f"- **{layer_config.get('description', layer_name)}**")

        return "\n".join(lines)

    def _format_quality_for_prompt(self, config: Dict) -> str:
        """格式化质量标准为提示文本"""
        lines = []
        quality = config.get("code_quality", {})

        naming = quality.get("naming", {})
        if naming.get("enabled", True):
            lines.append("### 命名规范")
            for category, value in naming.get("rules", {}).items():
                lines.append(f"- {category}: {value.get('pattern', '')}")

        func_design = quality.get("function_design", {})
        if func_design.get("enabled", True):
            lines.append("### 函数设计")
            rules = func_design.get("rules", {})
            lines.append(f"- 最大行数: {rules.get('max_lines', 20)}")
            lines.append(f"- 最大参数数: {rules.get('max_parameters', 4)}")
            lines.append(f"- 最大嵌套层级: {rules.get('max_nesting_level', 3)}")

        return "\n".join(lines)

    def _format_security_for_prompt(self, config: Dict) -> str:
        """格式化安全约束为提示文本"""
        lines = []
        security = config.get("security", {})

        sensitive = security.get("sensitive_data", {})
        if sensitive.get("enabled", True):
            lines.append("### 敏感数据处理")
            rules = sensitive.get("rules", {})
            if rules.get("no_hardcoded_secrets"):
                lines.append("- 禁止硬编码密钥、密码")
            if rules.get("encrypt_at_rest"):
                lines.append("- 静态数据加密")

        input_val = security.get("input_validation", {})
        if input_val.get("enabled", True):
            lines.append("### 输入验证")
            rules = input_val.get("rules", {})
            if rules.get("validate_at_boundary"):
                lines.append("- 在系统边界验证所有输入")
            if rules.get("sanitize_user_input"):
                lines.append("- 清理用户输入")

        return "\n".join(lines)


class CodeQualityChecker:
    """代码质量检查器"""

    def __init__(self, config: SoftwareEngineeringConfig):
        self.config = config

    def check_code(self, code: str, language: str = "python") -> Dict[str, Any]:
        """检查代码质量"""
        results = {
            "passed": True,
            "violations": [],
            "warnings": [],
            "suggestions": [],
            "metrics": self._calculate_metrics(code),
        }

        self._check_security_constraints(code, results)
        self._check_anti_patterns(code, results, language)
        self._check_architecture_rules(code, results, language)

        return results

    def _calculate_metrics(self, code: str) -> Dict[str, Any]:
        """计算代码指标"""
        lines = code.split("\n")
        non_empty_lines = [l for l in lines if l.strip() and not l.strip().startswith("#")]

        return {
            "total_lines": len(lines),
            "code_lines": len(non_empty_lines),
            "blank_lines": len(lines) - len(non_empty_lines) - sum(1 for l in lines if l.strip().startswith("#")),
        }

    def _check_security_constraints(self, code: str, results: Dict):
        """检查安全约束"""
        for constraint in self.config.security_constraints:
            for pattern in constraint.patterns:
                try:
                    if re.search(pattern, code, re.IGNORECASE):
                        violation = {
                            "id": constraint.id,
                            "name": constraint.name,
                            "description": constraint.description,
                            "severity": constraint.severity.value,
                            "action": constraint.action,
                        }
                        if constraint.action == "reject":
                            results["violations"].append(violation)
                            results["passed"] = False
                        elif constraint.action == "warn":
                            results["warnings"].append(violation)
                        else:
                            results["suggestions"].append(violation)
                except re.error:
                    pass

    def _check_anti_patterns(self, code: str, results: Dict, language: str):
        """检查反模式"""
        for ap in self.config.anti_patterns:
            detection = ap.detection_rules

            if "max_methods" in detection:
                method_count = self._count_methods(code, language)
                if method_count > detection["max_methods"]:
                    results["warnings"].append({
                        "name": ap.name,
                        "description": f"方法数量 ({method_count}) 超过阈值 ({detection['max_methods']})",
                        "severity": ap.severity.value,
                    })

            if "max_cyclomatic_complexity" in detection:
                complexity = self._estimate_complexity(code, language)
                if complexity > detection["max_cyclomatic_complexity"]:
                    results["warnings"].append({
                        "name": ap.name,
                        "description": f"圈复杂度 ({complexity}) 超过阈值 ({detection['max_cyclomatic_complexity']})",
                        "severity": ap.severity.value,
                    })

    def _check_architecture_rules(self, code: str, results: Dict, language: str):
        """检查架构规则"""
        arch_rules = self.config.architecture_rules
        if not arch_rules:
            return

        func_max_lines = arch_rules.get("max_function_lines", 50)
        func_lines = self._find_long_functions(code, language, func_max_lines)
        for func_name, line_count in func_lines:
            results["warnings"].append({
                "name": "函数过长",
                "description": f"函数 '{func_name}' 行数 ({line_count}) 超过阈值 ({func_max_lines})",
                "severity": "medium",
            })

        max_params = arch_rules.get("max_function_params", 4)
        param_violations = self._find_functions_with_many_params(code, language, max_params)
        for func_name, param_count in param_violations:
            results["suggestions"].append({
                "name": "参数过多",
                "description": f"函数 '{func_name}' 参数数量 ({param_count}) 超过建议值 ({max_params})",
                "severity": "low",
            })

    def _count_methods(self, code: str, language: str) -> int:
        """计算方法数量"""
        if language == "python":
            return len(re.findall(r"^\s*def\s+\w+", code, re.MULTILINE))
        elif language in ["javascript", "typescript"]:
            return len(re.findall(r"^\s*(async\s+)?[\w$]+\s*\([^)]*\)\s*\{", code, re.MULTILINE))
        return 0

    def _estimate_complexity(self, code: str, language: str) -> int:
        """估算圈复杂度"""
        complexity = 1
        keywords = ["if", "elif", "else", "for", "while", "and", "or", "try", "except", "with"]
        for kw in keywords:
            complexity += len(re.findall(rf"\b{kw}\b", code))
        return complexity

    def _find_long_functions(self, code: str, language: str, max_lines: int) -> List[Tuple[str, int]]:
        """查找过长的函数"""
        violations = []
        if language == "python":
            lines = code.split("\n")
            current_func = None
            func_start = 0
            indent_level = 0

            for i, line in enumerate(lines):
                match = re.match(r"^(\s*)def\s+(\w+)", line)
                if match:
                    if current_func:
                        func_lines = i - func_start
                        if func_lines > max_lines:
                            violations.append((current_func, func_lines))
                    current_func = match.group(2)
                    func_start = i
                    indent_level = len(match.group(1))

        return violations

    def _find_functions_with_many_params(self, code: str, language: str, max_params: int) -> List[Tuple[str, int]]:
        """查找参数过多的函数"""
        violations = []
        if language == "python":
            for match in re.finditer(r"def\s+(\w+)\s*\(([^)]*)\)", code):
                func_name = match.group(1)
                params = [p.strip() for p in match.group(2).split(",") if p.strip() and p.strip() != "self"]
                if len(params) > max_params:
                    violations.append((func_name, len(params)))

        return violations


def get_software_engineering_config(config_dir: Optional[str] = None) -> SoftwareEngineeringConfig:
    """获取软件工程配置的便捷函数"""
    loader = SoftwareEngineeringConfigLoader(config_dir)
    return loader.load_all_configs()


def check_code_quality(code: str, language: str = "python") -> Dict[str, Any]:
    """检查代码质量的便捷函数"""
    config = get_software_engineering_config()
    checker = CodeQualityChecker(config)
    return checker.check_code(code, language)