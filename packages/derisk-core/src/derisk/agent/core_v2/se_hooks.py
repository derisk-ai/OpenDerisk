"""
软件工程规则注入钩子
自动将软件工程黄金法则注入到 Coding 场景的系统提示中
"""
from typing import Dict, Any, Optional
import logging

from derisk.agent.core_v2.scene_strategy import (
    SceneHook,
    HookContext,
    HookResult,
    HookPriority,
    AgentPhase,
)

logger = logging.getLogger(__name__)


class SoftwareEngineeringHook(SceneHook):
    """
    软件工程规则注入钩子
    
    在系统提示构建时，自动注入软件工程黄金法则的轻量级摘要
    
    使用策略：
    - Light 模式：始终注入核心摘要 (~350字符)
    - Standard 模式：根据场景注入额外规则
    - Full 模式：不注入，仅用于后台检查
    """
    name = "software_engineering_injection"
    priority = HookPriority.HIGH
    phases = [AgentPhase.SYSTEM_PROMPT_BUILD]

    _se_prompt_cache: Optional[str] = None
    _scene_prompts_cache: Dict[str, str] = {}

    def __init__(self, injection_level: str = "light", config_dir: str = "configs/engineering"):
        super().__init__()
        self.injection_level = injection_level
        self.config_dir = config_dir

    async def on_system_prompt_build(self, ctx: HookContext) -> HookResult:
        """系统提示构建时注入软件工程规则"""
        current_prompt = ctx.current_prompt or ""
        scene = ctx.scene or "coding"
        
        se_prompt = self._get_se_prompt(scene)
        
        if se_prompt:
            if "## 设计原则" not in current_prompt and "软件工程黄金法则" not in current_prompt:
                enhanced_prompt = f"{current_prompt}\n\n{se_prompt}"
            else:
                enhanced_prompt = current_prompt
            
            return HookResult(
                proceed=True,
                modified_data={"current_prompt": enhanced_prompt}
            )
        
        return HookResult(proceed=True)

    def _get_se_prompt(self, scene: str) -> str:
        """获取软件工程提示"""
        if self.injection_level == "full":
            return ""
        
        if SoftwareEngineeringHook._se_prompt_cache is None:
            SoftwareEngineeringHook._se_prompt_cache = self._load_light_prompt()
        
        return SoftwareEngineeringHook._se_prompt_cache

    def _load_light_prompt(self) -> str:
        """加载轻量级软件工程提示"""
        try:
            from pathlib import Path
            import yaml
            
            config_path = Path(self.config_dir) / "se_golden_rules_summary.yaml"
            
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                
                core = config.get("core_summary", {})
                parts = []
                
                dp = core.get("design_principles", "")
                if dp:
                    parts.append(dp)
                
                arch = core.get("architecture", "")
                if arch:
                    parts.append(arch)
                
                sec = core.get("security", "")
                if sec:
                    parts.append(sec)
                
                checklist = core.get("checklist", "")
                if checklist:
                    parts.append(checklist)
                
                if parts:
                    return "\n\n".join(parts)
        except Exception as e:
            logger.warning(f"Failed to load SE prompt: {e}")
        
        return self._default_se_prompt()

    def _default_se_prompt(self) -> str:
        """默认软件工程提示"""
        return """# 软件工程黄金法则

## 设计原则
- SRP: 单一职责，一个类只做一件事
- OCP: 开闭原则，扩展开放，修改关闭
- KISS: 保持简单，避免过度设计
- DRY: 不重复，提取公共代码
- YAGNI: 不要过度设计，只实现当前需要

## 架构约束
- 函数≤50行，参数≤4个，嵌套≤3层
- 类≤300行，职责单一
- 使用有意义的命名

## 安全约束
- 禁止硬编码密钥密码
- 参数化查询，防止注入"""


class SoftwareEngineeringCheckHook(SceneHook):
    """
    软件工程检查钩子
    
    在代码写入/编辑后，进行代码质量检查
    注意：这是后台检查，不注入到系统提示
    """
    name = "software_engineering_check"
    priority = HookPriority.LOW
    phases = [AgentPhase.POST_TOOL_CALL]

    def __init__(self, enabled: bool = True, strict_mode: bool = False):
        super().__init__()
        self.enabled = enabled
        self.strict_mode = strict_mode
        self._checker = None

    async def on_post_tool_call(self, ctx: HookContext) -> HookResult:
        """工具调用后检查代码质量"""
        if not self.enabled:
            return HookResult(proceed=True)
        
        tool_name = ctx.tool_name or ""
        
        if tool_name not in ["write", "edit"]:
            return HookResult(proceed=True)
        
        tool_result = ctx.tool_result or {}
        file_path = tool_result.get("file_path", "")
        content = tool_result.get("content", "")
        
        if not content:
            return HookResult(proceed=True)
        
        language = self._detect_language(file_path)
        
        if not language:
            return HookResult(proceed=True)
        
        check_result = self._quick_check(content, language)
        
        if not check_result["passed"] and self.strict_mode:
            return HookResult(
                proceed=False,
                message=f"代码质量检查未通过: {check_result['issues']}"
            )
        
        if check_result["issues"]:
            logger.info(f"[SE Check] Found {len(check_result['issues'])} issues in {file_path}")
        
        return HookResult(
            proceed=True,
            modified_data={"se_check_result": check_result}
        )

    def _detect_language(self, file_path: str) -> Optional[str]:
        """检测文件语言"""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
        }
        
        if "." in file_path:
            ext = "." + file_path.rsplit(".", 1)[-1]
            return ext_map.get(ext)
        return None

    def _quick_check(self, code: str, language: str) -> Dict[str, Any]:
        """快速检查代码质量"""
        import re
        
        issues = []
        
        patterns = [
            (r'password\s*=\s*["\'][^"\']+["\']', "hardcoded_password", "critical"),
            (r'api_key\s*=\s*["\'][^"\']+["\']', "hardcoded_api_key", "critical"),
            (r'secret\s*=\s*["\'][^"\']+["\']', "hardcoded_secret", "critical"),
            (r'token\s*=\s*["\'][^"\']+["\']', "hardcoded_token", "critical"),
        ]
        
        for pattern, name, severity in patterns:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append({
                    "name": name,
                    "severity": severity,
                    "message": f"发现{name}，请使用环境变量",
                })
        
        if language == "python":
            func_matches = list(re.finditer(r"def\s+(\w+)\s*\(([^)]*)\)", code))
            for match in func_matches:
                func_name = match.group(1)
                params_str = match.group(2)
                params = [p.strip() for p in params_str.split(",") if p.strip() and p.strip() != "self"]
                if len(params) > 4:
                    issues.append({
                        "name": "too_many_params",
                        "severity": "medium",
                        "message": f"函数 {func_name} 参数数量({len(params)})超过建议值(4)",
                    })
        
        critical_issues = [i for i in issues if i["severity"] == "critical"]
        
        return {
            "passed": len(critical_issues) == 0,
            "issues": issues,
        }


def create_se_hooks(
    injection_level: str = "light",
    enable_check: bool = True,
    strict_mode: bool = False,
    config_dir: str = "configs/engineering",
) -> list:
    """
    创建软件工程相关钩子
    
    Args:
        injection_level: 注入级别 (light/standard/full)
        enable_check: 是否启用代码检查
        strict_mode: 严格模式（检查不通过时阻止操作）
        config_dir: 配置目录
    
    Returns:
        钩子列表
    """
    hooks = []
    
    hooks.append(SoftwareEngineeringHook(
        injection_level=injection_level,
        config_dir=config_dir,
    ))
    
    if enable_check:
        hooks.append(SoftwareEngineeringCheckHook(
            enabled=True,
            strict_mode=strict_mode,
        ))
    
    return hooks