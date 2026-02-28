"""
软件工程配置加载器 V2 - 优化版
实现分层加载策略，避免上下文空间浪费
"""
import os
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)


class InjectionLevel(Enum):
    LIGHT = "light"       # 轻量级 - 核心摘要，始终注入
    STANDARD = "standard" # 标准级 - 场景规则，编码场景注入
    FULL = "full"         # 完整级 - 按需加载，仅检查时使用


class DevScene(Enum):
    NEW_FEATURE = "new_feature"
    BUG_FIX = "bug_fix"
    REFACTORING = "refactoring"
    CODE_REVIEW = "code_review"
    GENERAL = "general"


@dataclass
class LightConfig:
    """轻量级配置 - 用于系统提示注入"""
    design_principles: str
    architecture: str
    security: str
    checklist: str
    
    def to_prompt(self) -> str:
        return f"{self.design_principles}\n\n{self.architecture}\n\n{self.security}\n\n{self.checklist}"


@dataclass
class SceneRule:
    """场景规则"""
    name: str
    enabled_rules: List[str]
    prompt_suffix: str


@dataclass
class FullConfig:
    """完整配置 - 用于代码检查"""
    design_principles: Dict[str, Any] = field(default_factory=dict)
    architecture_rules: Dict[str, Any] = field(default_factory=dict)
    quality_gates: List[Dict] = field(default_factory=list)
    security_constraints: List[Dict] = field(default_factory=list)
    anti_patterns: List[Dict] = field(default_factory=list)


class SoftwareEngineeringLoaderV2:
    """
    软件工程配置加载器 V2
    
    分层加载策略：
    - Light: 核心摘要 (~500 chars)，始终注入到系统提示
    - Standard: 场景规则 (~1000 chars)，编码场景注入
    - Full: 完整配置，仅代码检查时按需加载
    
    这样避免了将大量配置内容加载到 Agent 上下文空间
    """
    
    SUMMARY_CONFIG_FILE = "se_golden_rules_summary.yaml"
    FULL_CONFIG_FILE = "software_engineering_principles.yaml"
    
    def __init__(self, config_dir: str = "configs/engineering"):
        self.config_dir = Path(config_dir)
        self._summary_cache: Optional[Dict] = None
        self._full_config_cache: Optional[Dict] = None
    
    # ==================== 轻量级配置 (始终可用) ====================
    
    @lru_cache(maxsize=1)
    def get_light_config(self) -> LightConfig:
        """获取轻量级配置 - 核心摘要，约500字符"""
        summary = self._load_summary_config()
        core = summary.get("core_summary", {})
        
        return LightConfig(
            design_principles=core.get("design_principles", self._default_design_principles()),
            architecture=core.get("architecture", self._default_architecture()),
            security=core.get("security", self._default_security()),
            checklist=core.get("checklist", self._default_checklist()),
        )
    
    def get_light_prompt(self) -> str:
        """获取轻量级系统提示 - 始终注入"""
        config = self.get_light_config()
        header = "# 软件工程黄金法则\n\n在编写代码时遵循以下原则：\n\n"
        return header + config.to_prompt()
    
    # ==================== 标准级配置 (场景相关) ====================
    
    def get_standard_prompt(self, scene: DevScene = DevScene.GENERAL) -> str:
        """获取标准级系统提示 - 根据场景注入，约1000字符"""
        light_prompt = self.get_light_prompt()
        scene_rule = self._get_scene_rule(scene)
        
        if scene_rule:
            return f"{light_prompt}\n\n## 当前场景: {scene_rule.name}\n{scene_rule.prompt_suffix}"
        return light_prompt
    
    def _get_scene_rule(self, scene: DevScene) -> Optional[SceneRule]:
        """获取场景规则"""
        summary = self._load_summary_config()
        scene_rules = summary.get("scene_rules", {})
        
        rule_config = scene_rules.get(scene.value, {})
        if not rule_config:
            return None
        
        return SceneRule(
            name=scene.value.replace("_", " ").title(),
            enabled_rules=rule_config.get("enabled_rules", []),
            prompt_suffix=rule_config.get("prompt_suffix", ""),
        )
    
    # ==================== 完整配置 (按需加载) ====================
    
    def get_full_config(self) -> FullConfig:
        """
        获取完整配置 - 仅在代码检查时使用
        不注入到系统提示，避免浪费上下文空间
        """
        if self._full_config_cache is None:
            self._full_config_cache = self._load_full_config()
        
        full = self._full_config_cache
        return FullConfig(
            design_principles=full.get("design_principles", {}),
            architecture_rules=full.get("architecture_patterns", {}),
            quality_gates=self._parse_quality_gates(full),
            security_constraints=self._parse_security_constraints(full),
            anti_patterns=self._parse_anti_patterns(full),
        )
    
    # ==================== 内部加载方法 ====================
    
    def _load_summary_config(self) -> Dict:
        """加载摘要配置"""
        if self._summary_cache is not None:
            return self._summary_cache
        
        config_path = self.config_dir / self.SUMMARY_CONFIG_FILE
        if not config_path.exists():
            logger.warning(f"Summary config not found: {config_path}")
            self._summary_cache = self._default_summary()
            return self._summary_cache
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self._summary_cache = yaml.safe_load(f) or {}
            return self._summary_cache
        except Exception as e:
            logger.error(f"Failed to load summary config: {e}")
            self._summary_cache = self._default_summary()
            return self._summary_cache
    
    def _load_full_config(self) -> Dict:
        """加载完整配置 - 仅在需要时调用"""
        config_path = self.config_dir / self.FULL_CONFIG_FILE
        if not config_path.exists():
            logger.warning(f"Full config not found: {config_path}")
            return {}
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load full config: {e}")
            return {}
    
    def _parse_quality_gates(self, config: Dict) -> List[Dict]:
        """解析质量门禁"""
        gates = []
        qg = config.get("code_quality", {}).get("metrics", {})
        for name, value in qg.items():
            if isinstance(value, dict):
                gates.append({
                    "name": name,
                    "threshold": value.get("threshold", 0),
                    "action": value.get("action", "warn"),
                })
        return gates
    
    def _parse_security_constraints(self, config: Dict) -> List[Dict]:
        """解析安全约束"""
        constraints = []
        for item in config.get("security", {}).get("sensitive_data", {}).get("patterns_to_avoid", []):
            constraints.append({
                "name": "禁止硬编码密钥",
                "pattern": item,
                "severity": "critical",
            })
        return constraints
    
    def _parse_anti_patterns(self, config: Dict) -> List[Dict]:
        """解析反模式"""
        patterns = []
        for key, value in config.get("anti_patterns", {}).get("patterns", {}).items():
            patterns.append({
                "name": value.get("name", key),
                "detection": value.get("detection", {}),
                "severity": value.get("severity", "medium"),
            })
        return patterns
    
    # ==================== 默认配置 ====================
    
    def _default_summary(self) -> Dict:
        """默认摘要配置"""
        return {
            "core_summary": {
                "design_principles": self._default_design_principles(),
                "architecture": self._default_architecture(),
                "security": self._default_security(),
                "checklist": self._default_checklist(),
            }
        }
    
    def _default_design_principles(self) -> str:
        return """## 设计原则
- SRP: 单一职责，一个类只做一件事
- OCP: 开闭原则，扩展开放，修改关闭
- DIP: 依赖倒置，依赖抽象不依赖具体
- KISS: 保持简单，避免过度设计
- DRY: 不重复，提取公共代码"""
    
    def _default_architecture(self) -> str:
        return """## 架构约束
- 函数≤50行，参数≤4个，嵌套≤3层
- 类≤300行，职责单一
- 使用有意义的命名"""
    
    def _default_security(self) -> str:
        return """## 安全约束
- 禁止硬编码密钥密码
- 参数化查询，防止注入
- 验证清理用户输入"""
    
    def _default_checklist(self) -> str:
        return """## 质量检查
- [ ] 遵循设计原则
- [ ] 命名清晰
- [ ] 无重复代码
- [ ] 错误处理完善"""


class LightweightCodeChecker:
    """
    轻量级代码检查器
    
    使用完整配置进行代码检查，但不加载到系统提示
    """
    
    def __init__(self, loader: SoftwareEngineeringLoaderV2):
        self.loader = loader
        self._full_config: Optional[FullConfig] = None
    
    @property
    def config(self) -> FullConfig:
        """懒加载完整配置"""
        if self._full_config is None:
            self._full_config = self.loader.get_full_config()
        return self._full_config
    
    def quick_check(self, code: str, language: str = "python") -> Dict[str, Any]:
        """
        快速检查 - 使用轻量规则
        
        仅检查最关键的问题：
        - 硬编码密钥
        - 过长函数
        - 参数过多
        """
        import re
        
        issues = []
        
        patterns = [
            (r'password\s*=\s*["\'][^"\']+["\']', "hardcoded_password", "critical"),
            (r'api_key\s*=\s*["\'][^"\']+["\']', "hardcoded_api_key", "critical"),
            (r'secret\s*=\s*["\'][^"\']+["\']', "hardcoded_secret", "critical"),
        ]
        
        for pattern, name, severity in patterns:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append({
                    "name": name,
                    "severity": severity,
                    "message": f"发现{name}，请使用环境变量",
                })
        
        if language == "python":
            lines = code.split("\n")
            func_match = re.finditer(r"def\s+(\w+)\s*\(([^)]*)\)", code)
            for match in func_match:
                func_name = match.group(1)
                params = [p.strip() for p in match.group(2).split(",") if p.strip() and p.strip() != "self"]
                if len(params) > 4:
                    issues.append({
                        "name": "too_many_params",
                        "severity": "medium",
                        "message": f"函数 {func_name} 参数数量({len(params)})超过建议值(4)",
                    })
        
        return {
            "passed": len([i for i in issues if i["severity"] == "critical"]) == 0,
            "issues": issues,
        }
    
    def full_check(self, code: str, language: str = "python") -> Dict[str, Any]:
        """
        完整检查 - 使用完整配置
        
        仅在显式请求时调用
        """
        quick_result = self.quick_check(code, language)
        
        full_issues = []
        
        for pattern in self.config.anti_patterns:
            name = pattern.get("name", "")
            detection = pattern.get("detection", {})
            
            if "max_methods" in detection:
                method_count = self._count_methods(code, language)
                if method_count > detection["max_methods"]:
                    full_issues.append({
                        "name": name,
                        "severity": pattern.get("severity", "medium"),
                        "message": f"方法数量({method_count})超过阈值({detection['max_methods']})",
                    })
        
        return {
            "passed": quick_result["passed"],
            "issues": quick_result["issues"] + full_issues,
        }
    
    def _count_methods(self, code: str, language: str) -> int:
        import re
        if language == "python":
            return len(re.findall(r"^\s*def\s+\w+", code, re.MULTILINE))
        return 0


# ==================== 便捷函数 ====================

_loader_instance: Optional[SoftwareEngineeringLoaderV2] = None

def get_se_loader(config_dir: str = "configs/engineering") -> SoftwareEngineeringLoaderV2:
    """获取配置加载器单例"""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = SoftwareEngineeringLoaderV2(config_dir)
    return _loader_instance


def get_light_se_prompt() -> str:
    """获取轻量级系统提示 - 推荐用于日常编码"""
    return get_se_loader().get_light_prompt()


def get_standard_se_prompt(scene: DevScene = DevScene.GENERAL) -> str:
    """获取标准级系统提示 - 用于特定场景"""
    return get_se_loader().get_standard_prompt(scene)


def quick_code_check(code: str, language: str = "python") -> Dict[str, Any]:
    """快速代码检查 - 使用轻量规则"""
    loader = get_se_loader()
    checker = LightweightCodeChecker(loader)
    return checker.quick_check(code, language)