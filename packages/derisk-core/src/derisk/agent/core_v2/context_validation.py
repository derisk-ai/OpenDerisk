"""
ContextValidation - 上下文验证系统

实现完整的上下文验证机制：
- 完整性验证：检查上下文是否完整
- 一致性验证：检查上下文是否自洽
- 约束验证：检查上下文是否符合约束
- 状态验证：检查状态转换是否合法
"""

from typing import Dict, Any, List, Optional, Callable, Tuple
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field as dataclass_field
import re
import json
import logging

logger = logging.getLogger(__name__)


class ValidationLevel(str, Enum):
    """验证级别"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationCategory(str, Enum):
    """验证类别"""
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    CONSTRAINT = "constraint"
    STATE = "state"
    SECURITY = "security"
    PERFORMANCE = "performance"


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    category: ValidationCategory
    level: ValidationLevel
    message: str
    field: Optional[str] = None
    value: Optional[Any] = None
    suggestion: Optional[str] = None
    timestamp: datetime = dataclass_field(default_factory=datetime.now)


class ContextValidator:
    """
    上下文验证器
    
    验证上下文的完整性、一致性、约束条件
    
    示例:
        validator = ContextValidator()
        
        # 添加规则
        validator.add_required_field("session_id")
        validator.add_constraint("max_steps", lambda x: x > 0 and x < 1000)
        
        # 验证
        results = validator.validate(context)
        if results.is_valid:
            print("验证通过")
    """
    
    def __init__(self):
        self._required_fields: Dict[str, ValidationCategory] = {}
        self._field_constraints: Dict[str, List[Callable[[Any], Tuple[bool, str]]]] = {}
        self._cross_field_validators: List[Callable[[Dict], List[ValidationResult]]] = []
        self._state_transitions: Dict[str, List[str]] = {}
        self._security_rules: List[Callable[[Dict], List[ValidationResult]]] = []
        
        self._setup_default_rules()
    
    def _setup_default_rules(self):
        """设置默认验证规则"""
        self.add_required_field("session_id", ValidationCategory.COMPLETENESS)
        self.add_required_field("conversation_id", ValidationCategory.COMPLETENESS)
        
        self.add_constraint("current_step", lambda x: (
            isinstance(x, int) and x >= 0,
            "current_step must be a non-negative integer"
        ), ValidationCategory.CONSISTENCY)
        
        self.add_constraint("max_steps", lambda x: (
            isinstance(x, int) and 0 < x <= 10000,
            "max_steps must be between 1 and 10000"
        ), ValidationCategory.CONSTRAINT)
        
        self.add_state_transition("idle", ["thinking", "acting", "terminated"])
        self.add_state_transition("thinking", ["acting", "waiting_input", "error", "terminated"])
        self.add_state_transition("acting", ["thinking", "waiting_input", "error", "terminated"])
        self.add_state_transition("waiting_input", ["thinking", "terminated"])
        self.add_state_transition("error", ["thinking", "terminated"])
        
        self.add_security_rule(self._check_sensitive_data)
    
    def add_required_field(self, field: str, category: ValidationCategory = ValidationCategory.COMPLETENESS):
        """添加必填字段"""
        self._required_fields[field] = category
    
    def add_constraint(
        self,
        field: str,
        validator: Callable[[Any], Tuple[bool, str]],
        category: ValidationCategory = ValidationCategory.CONSTRAINT
    ):
        """添加字段约束"""
        if field not in self._field_constraints:
            self._field_constraints[field] = []
        self._field_constraints[field].append((validator, category))
    
    def add_cross_field_validator(self, validator: Callable[[Dict], List[ValidationResult]]):
        """添加跨字段验证器"""
        self._cross_field_validators.append(validator)
    
    def add_state_transition(self, from_state: str, to_states: List[str]):
        """添加状态转换规则"""
        self._state_transitions[from_state] = to_states
    
    def add_security_rule(self, rule: Callable[[Dict], List[ValidationResult]]):
        """添加安全规则"""
        self._security_rules.append(rule)
    
    def validate(self, context: Dict[str, Any]) -> List[ValidationResult]:
        """执行完整验证"""
        results = []
        
        results.extend(self._validate_completeness(context))
        
        results.extend(self._validate_consistency(context))
        
        results.extend(self._validate_constraints(context))
        
        results.extend(self._validate_state(context))
        
        results.extend(self._validate_security(context))
        
        for validator in self._cross_field_validators:
            results.extend(validator(context))
        
        return results
    
    def _validate_completeness(self, context: Dict[str, Any]) -> List[ValidationResult]:
        """验证完整性"""
        results = []
        
        for field, category in self._required_fields.items():
            if field not in context or context[field] is None:
                results.append(ValidationResult(
                    is_valid=False,
                    category=category,
                    level=ValidationLevel.ERROR,
                    message=f"Required field '{field}' is missing",
                    field=field,
                    suggestion=f"Please provide a value for '{field}'"
                ))
        
        return results
    
    def _validate_consistency(self, context: Dict[str, Any]) -> List[ValidationResult]:
        """验证一致性"""
        results = []
        
        if "created_at" in context and "updated_at" in context:
            try:
                created = self._parse_datetime(context["created_at"])
                updated = self._parse_datetime(context["updated_at"])
                
                if created and updated and updated < created:
                    results.append(ValidationResult(
                        is_valid=False,
                        category=ValidationCategory.CONSISTENCY,
                        level=ValidationLevel.ERROR,
                        message="updated_at cannot be before created_at",
                        field="updated_at"
                    ))
            except Exception:
                pass
        
        if "current_step" in context and "max_steps" in context:
            if context["current_step"] > context["max_steps"]:
                results.append(ValidationResult(
                    is_valid=False,
                    category=ValidationCategory.CONSISTENCY,
                    level=ValidationLevel.WARNING,
                    message="current_step exceeds max_steps",
                    field="current_step"
                ))
        
        return results
    
    def _validate_constraints(self, context: Dict[str, Any]) -> List[ValidationResult]:
        """验证约束条件"""
        results = []
        
        for field, validators in self._field_constraints.items():
            if field not in context:
                continue
            
            value = context[field]
            
            for validator, category in validators:
                try:
                    is_valid, message = validator(value)
                    if not is_valid:
                        results.append(ValidationResult(
                            is_valid=False,
                            category=category,
                            level=ValidationLevel.ERROR,
                            message=message,
                            field=field,
                            value=str(value)[:100]
                        ))
                except Exception as e:
                    results.append(ValidationResult(
                        is_valid=False,
                        category=category,
                        level=ValidationLevel.ERROR,
                        message=f"Validation error: {str(e)}",
                        field=field
                    ))
        
        return results
    
    def _validate_state(self, context: Dict[str, Any]) -> List[ValidationResult]:
        """验证状态转换"""
        results = []
        
        if "state" not in context or "previous_state" not in context:
            return results
        
        from_state = context["previous_state"]
        to_state = context["state"]
        
        if from_state in self._state_transitions:
            allowed_transitions = self._state_transitions[from_state]
            if to_state not in allowed_transitions:
                results.append(ValidationResult(
                    is_valid=False,
                    category=ValidationCategory.STATE,
                    level=ValidationLevel.ERROR,
                    message=f"Invalid state transition: {from_state} -> {to_state}",
                    field="state",
                    suggestion=f"Allowed transitions from '{from_state}': {allowed_transitions}"
                ))
        
        return results
    
    def _validate_security(self, context: Dict[str, Any]) -> List[ValidationResult]:
        """验证安全规则"""
        results = []
        
        for rule in self._security_rules:
            try:
                results.extend(rule(context))
            except Exception as e:
                logger.error(f"[ContextValidator] Security rule error: {e}")
        
        return results
    
    def _check_sensitive_data(self, context: Dict[str, Any]) -> List[ValidationResult]:
        """检查敏感数据"""
        results = []
        
        sensitive_patterns = [
            (r'sk-[a-zA-Z0-9]{20,}', 'API Key'),
            (r'eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+', 'JWT Token'),
            (r'-----BEGIN.*PRIVATE KEY-----', 'Private Key'),
            (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', 'Email'),
            (r'\b\d{16,19}\b', 'Credit Card Number'),
        ]
        
        context_str = json.dumps(context, default=str)
        
        for pattern, data_type in sensitive_patterns:
            matches = re.findall(pattern, context_str)
            if matches:
                results.append(ValidationResult(
                    is_valid=False,
                    category=ValidationCategory.SECURITY,
                    level=ValidationLevel.WARNING,
                    message=f"Potential {data_type} found in context",
                    suggestion=f"Consider masking or encrypting {data_type}"
                ))
        
        return results
    
    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """解析日期时间"""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except Exception:
                pass
        return None
    
    def is_valid(self, context: Dict[str, Any]) -> bool:
        """检查上下文是否有效"""
        results = self.validate(context)
        return all(r.is_valid for r in results)
    
    def get_errors(self, context: Dict[str, Any]) -> List[ValidationResult]:
        """获取错误结果"""
        results = self.validate(context)
        return [r for r in results if not r.is_valid and r.level == ValidationLevel.ERROR]
    
    def get_warnings(self, context: Dict[str, Any]) -> List[ValidationResult]:
        """获取警告结果"""
        results = self.validate(context)
        return [r for r in results if r.level == ValidationLevel.WARNING]


class LayeredContextValidator:
    """
    分层上下文验证器
    
    验证ExecutionContext的每一层
    
    示例:
        validator = LayeredContextValidator()
        
        from derisk.agent.core_v2.agent_harness import ExecutionContext
        context = ExecutionContext(...)
        
        results = validator.validate_layers(context)
    """
    
    def __init__(self):
        self.base_validator = ContextValidator()
        
        self._layer_validators: Dict[str, List[Callable]] = {
            "system_layer": [],
            "task_layer": [],
            "tool_layer": [],
            "memory_layer": [],
            "temporary_layer": [],
        }
        
        self._setup_layer_rules()
    
    def _setup_layer_rules(self):
        """设置层级规则"""
        self.add_layer_validator("system_layer", self._validate_system_layer)
        self.add_layer_validator("task_layer", self._validate_task_layer)
        self.add_layer_validator("tool_layer", self._validate_tool_layer)
        self.add_layer_validator("memory_layer", self._validate_memory_layer)
    
    def add_layer_validator(self, layer: str, validator: Callable):
        """添加层级验证器"""
        if layer in self._layer_validators:
            self._layer_validators[layer].append(validator)
    
    def validate_layers(self, context) -> List[ValidationResult]:
        """验证所有层"""
        results = []
        
        for layer_name, validators in self._layer_validators.items():
            layer_data = getattr(context, layer_name, {})
            
            if not isinstance(layer_data, dict):
                results.append(ValidationResult(
                    is_valid=False,
                    category=ValidationCategory.CONSISTENCY,
                    level=ValidationLevel.ERROR,
                    message=f"Layer '{layer_name}' must be a dictionary",
                    field=layer_name
                ))
                continue
            
            for validator in validators:
                try:
                    layer_results = validator(layer_data)
                    if layer_results:
                        results.extend(layer_results)
                except Exception as e:
                    results.append(ValidationResult(
                        is_valid=False,
                        category=ValidationCategory.CONSISTENCY,
                        level=ValidationLevel.ERROR,
                        message=f"Layer validation error: {str(e)}",
                        field=layer_name
                    ))
        
        return results
    
    def _validate_system_layer(self, layer: Dict[str, Any]) -> List[ValidationResult]:
        """验证系统层"""
        results = []
        
        if "agent_version" in layer:
            version = layer["agent_version"]
            if not re.match(r'^\d+\.\d+(\.\d+)?$', str(version)):
                results.append(ValidationResult(
                    is_valid=False,
                    category=ValidationCategory.CONSISTENCY,
                    level=ValidationLevel.WARNING,
                    message="agent_version should follow semantic versioning (e.g., '1.0.0')",
                    field="system_layer.agent_version"
                ))
        
        return results
    
    def _validate_task_layer(self, layer: Dict[str, Any]) -> List[ValidationResult]:
        """验证任务层"""
        results = []
        
        if "goals" in layer:
            goals = layer["goals"]
            if not isinstance(goals, list):
                results.append(ValidationResult(
                    is_valid=False,
                    category=ValidationCategory.CONSISTENCY,
                    level=ValidationLevel.ERROR,
                    message="goals must be a list",
                    field="task_layer.goals"
                ))
        
        if "priority" in layer:
            priority = layer["priority"]
            if priority not in ["critical", "high", "medium", "low"]:
                results.append(ValidationResult(
                    is_valid=False,
                    category=ValidationCategory.CONSTRAINT,
                    level=ValidationLevel.WARNING,
                    message="priority should be one of: critical, high, medium, low",
                    field="task_layer.priority"
                ))
        
        return results
    
    def _validate_tool_layer(self, layer: Dict[str, Any]) -> List[ValidationResult]:
        """验证工具层"""
        results = []
        
        if "tools" in layer:
            tools = layer["tools"]
            if not isinstance(tools, (list, dict)):
                results.append(ValidationResult(
                    is_valid=False,
                    category=ValidationCategory.CONSISTENCY,
                    level=ValidationLevel.ERROR,
                    message="tools must be a list or dict",
                    field="tool_layer.tools"
                ))
        
        return results
    
    def _validate_memory_layer(self, layer: Dict[str, Any]) -> List[ValidationResult]:
        """验证记忆层"""
        results = []
        
        if "messages" in layer:
            messages = layer["messages"]
            if not isinstance(messages, list):
                results.append(ValidationResult(
                    is_valid=False,
                    category=ValidationCategory.CONSISTENCY,
                    level=ValidationLevel.ERROR,
                    message="messages must be a list",
                    field="memory_layer.messages"
                ))
            elif len(messages) > 1000:
                results.append(ValidationResult(
                    is_valid=False,
                    category=ValidationCategory.PERFORMANCE,
                    level=ValidationLevel.WARNING,
                    message=f"Too many messages ({len(messages)}), consider compression",
                    field="memory_layer.messages",
                    suggestion="Use StateCompressor to reduce message count"
                ))
        
        return results


class ContextValidationManager:
    """
    上下文验证管理器
    
    统一管理所有验证规则和执行验证
    
    示例:
        manager = ContextValidationManager()
        
        # 验证并修复
        context = {...}
        results, fixed_context = manager.validate_and_fix(context)
    """
    
    def __init__(self):
        self.validator = ContextValidator()
        self.layered_validator = LayeredContextValidator()
        
        self._auto_fix_rules: Dict[str, Callable] = {}
        
        self._setup_auto_fix_rules()
    
    def _setup_auto_fix_rules(self):
        """设置自动修复规则"""
        self.add_auto_fix_rule("current_step", self._fix_current_step)
        self.add_auto_fix_rule("max_steps", self._fix_max_steps)
    
    def add_auto_fix_rule(self, field: str, fixer: Callable):
        """添加自动修复规则"""
        self._auto_fix_rules[field] = fixer
    
    def validate(self, context: Dict[str, Any]) -> List[ValidationResult]:
        """执行完整验证"""
        results = []
        results.extend(self.validator.validate(context))
        
        if hasattr(context, 'to_dict'):
            results.extend(self.layered_validator.validate_layers(context))
        
        return results
    
    def validate_and_fix(self, context: Dict[str, Any]) -> Tuple[List[ValidationResult], Dict[str, Any]]:
        """验证并自动修复"""
        results = self.validate(context)
        fixed_context = context.copy() if isinstance(context, dict) else context
        
        errors = [r for r in results if not r.is_valid]
        
        for error in errors:
            if error.field and error.field in self._auto_fix_rules:
                try:
                    fixed_value = self._auto_fix_rules[error.field](
                        fixed_context.get(error.field)
                    )
                    if isinstance(fixed_context, dict):
                        fixed_context[error.field] = fixed_value
                except Exception as e:
                    logger.error(f"[ContextValidationManager] Auto-fix failed: {e}")
        
        new_results = self.validate(fixed_context)
        
        return new_results, fixed_context
    
    def _fix_current_step(self, value: Any) -> int:
        """修复current_step"""
        if not isinstance(value, int) or value < 0:
            return 0
        return value
    
    def _fix_max_steps(self, value: Any) -> int:
        """修复max_steps"""
        if not isinstance(value, int) or value <= 0:
            return 100
        if value > 10000:
            return 10000
        return value
    
    def get_validation_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """获取验证摘要"""
        results = self.validate(context)
        
        return {
            "is_valid": all(r.is_valid for r in results),
            "total_checks": len(results),
            "errors": len([r for r in results if r.level == ValidationLevel.ERROR]),
            "warnings": len([r for r in results if r.level == ValidationLevel.WARNING]),
            "passed": len([r for r in results if r.is_valid]),
            "categories": {
                cat.value: len([r for r in results if r.category == cat])
                for cat in ValidationCategory
            }
        }


context_validator = ContextValidator()
layered_context_validator = LayeredContextValidator()
context_validation_manager = ContextValidationManager()