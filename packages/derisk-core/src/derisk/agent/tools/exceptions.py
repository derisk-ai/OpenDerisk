"""
Exceptions - 工具异常定义

定义所有工具相关异常：
- ToolError: 基础异常
- ToolNotFoundError: 工具未找到
- ToolExecutionError: 执行错误
- ToolValidationError: 验证错误
- ToolPermissionError: 权限错误
- ToolTimeoutError: 超时错误
"""

from typing import Optional, Dict, Any


class ToolError(Exception):
    """工具基础异常"""
    
    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.tool_name = tool_name
        self.error_code = error_code
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "tool_name": self.tool_name,
            "error_code": self.error_code,
            "details": self.details
        }


class ToolNotFoundError(ToolError):
    """工具未找到异常"""
    
    def __init__(self, tool_name: str, available_tools: Optional[list] = None):
        super().__init__(
            message=f"Tool '{tool_name}' not found",
            tool_name=tool_name,
            error_code="TOOL_NOT_FOUND",
            details={"available_tools": available_tools or []}
        )


class ToolExecutionError(ToolError):
    """工具执行异常"""
    
    def __init__(
        self,
        message: str,
        tool_name: str,
        error_code: Optional[str] = None,
        stack_trace: Optional[str] = None
    ):
        super().__init__(
            message=message,
            tool_name=tool_name,
            error_code=error_code or "EXECUTION_ERROR",
            details={"stack_trace": stack_trace}
        )


class ToolValidationError(ToolError):
    """工具验证异常"""
    
    def __init__(
        self,
        tool_name: str,
        validation_errors: Dict[str, Any],
        message: Optional[str] = None
    ):
        super().__init__(
            message=message or f"Validation failed for tool '{tool_name}'",
            tool_name=tool_name,
            error_code="VALIDATION_ERROR",
            details={"validation_errors": validation_errors}
        )


class ToolPermissionError(ToolError):
    """工具权限异常"""
    
    def __init__(
        self,
        tool_name: str,
        required_permissions: list,
        user_permissions: list
    ):
        super().__init__(
            message=f"Permission denied for tool '{tool_name}'",
            tool_name=tool_name,
            error_code="PERMISSION_DENIED",
            details={
                "required_permissions": required_permissions,
                "user_permissions": user_permissions,
                "missing_permissions": [p for p in required_permissions if p not in user_permissions]
            }
        )


class ToolTimeoutError(ToolError):
    """工具超时异常"""
    
    def __init__(self, tool_name: str, timeout_seconds: int):
        super().__init__(
            message=f"Tool '{tool_name}' execution timed out after {timeout_seconds} seconds",
            tool_name=tool_name,
            error_code="TIMEOUT",
            details={"timeout_seconds": timeout_seconds}
        )


class ToolConfigurationError(ToolError):
    """工具配置异常"""
    
    def __init__(self, tool_name: str, config_key: str, message: str):
        super().__init__(
            message=message,
            tool_name=tool_name,
            error_code="CONFIG_ERROR",
            details={"config_key": config_key}
        )


class ToolDependencyError(ToolError):
    """工具依赖异常"""
    
    def __init__(self, tool_name: str, missing_dependencies: list):
        super().__init__(
            message=f"Missing dependencies for tool '{tool_name}'",
            tool_name=tool_name,
            error_code="DEPENDENCY_ERROR",
            details={"missing_dependencies": missing_dependencies}
        )