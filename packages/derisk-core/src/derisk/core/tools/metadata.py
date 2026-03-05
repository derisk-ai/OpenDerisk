"""
Tool Metadata Models - Unified Tool Authorization System

This module defines the core data models for the unified tool system:
- Tool categories and risk levels
- Authorization requirements
- Tool parameters
- Tool metadata with OpenAI spec generation

Version: 2.0
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
import re


class ToolCategory(str, Enum):
    """Tool categories for classification and filtering."""
    FILE_SYSTEM = "file_system"        # File system operations
    SHELL = "shell"                    # Shell command execution
    NETWORK = "network"                # Network requests
    CODE = "code"                      # Code operations
    DATA = "data"                      # Data processing
    AGENT = "agent"                    # Agent collaboration
    INTERACTION = "interaction"        # User interaction
    EXTERNAL = "external"              # External tools
    CUSTOM = "custom"                  # Custom tools


class RiskLevel(str, Enum):
    """Risk levels for authorization decisions."""
    SAFE = "safe"                      # Safe operation - no risk
    LOW = "low"                        # Low risk - minimal impact
    MEDIUM = "medium"                  # Medium risk - requires caution
    HIGH = "high"                      # High risk - requires authorization
    CRITICAL = "critical"              # Critical operation - requires explicit approval


class RiskCategory(str, Enum):
    """Risk categories for fine-grained risk assessment."""
    READ_ONLY = "read_only"                    # Read-only operations
    FILE_WRITE = "file_write"                  # File write operations
    FILE_DELETE = "file_delete"                # File delete operations
    SHELL_EXECUTE = "shell_execute"            # Shell command execution
    NETWORK_OUTBOUND = "network_outbound"      # Outbound network requests
    DATA_MODIFY = "data_modify"                # Data modification
    SYSTEM_CONFIG = "system_config"            # System configuration changes
    PRIVILEGED = "privileged"                  # Privileged operations


class AuthorizationRequirement(BaseModel):
    """
    Authorization requirements for a tool.
    
    Defines when and how authorization should be requested for tool execution.
    """
    # Whether authorization is required
    requires_authorization: bool = True
    
    # Base risk level
    risk_level: RiskLevel = RiskLevel.MEDIUM
    
    # Risk categories for detailed assessment
    risk_categories: List[RiskCategory] = Field(default_factory=list)
    
    # Custom authorization prompt template
    authorization_prompt: Optional[str] = None
    
    # Parameters that contain sensitive data
    sensitive_parameters: List[str] = Field(default_factory=list)
    
    # Function reference for parameter-level risk assessment
    parameter_risk_assessor: Optional[str] = None
    
    # Whitelist rules - skip authorization when matched
    whitelist_rules: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Support session-level authorization grant
    support_session_grant: bool = True
    
    # Grant TTL in seconds, None means permanent
    grant_ttl: Optional[int] = None

    class Config:
        use_enum_values = True


class ToolParameter(BaseModel):
    """
    Tool parameter definition.
    
    Defines the schema and validation rules for a tool parameter.
    """
    # Basic info
    name: str
    type: str                              # string, number, boolean, object, array
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None       # Enumeration values
    
    # Validation constraints
    pattern: Optional[str] = None          # Regex pattern for string validation
    min_value: Optional[float] = None      # Minimum value for numbers
    max_value: Optional[float] = None      # Maximum value for numbers
    min_length: Optional[int] = None       # Minimum length for strings/arrays
    max_length: Optional[int] = None       # Maximum length for strings/arrays
    
    # Sensitive data markers
    sensitive: bool = False
    sensitive_pattern: Optional[str] = None  # Pattern to detect sensitive values

    def validate_value(self, value: Any) -> List[str]:
        """
        Validate a value against this parameter's constraints.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        if value is None:
            if self.required and self.default is None:
                errors.append(f"Required parameter '{self.name}' is missing")
            return errors
        
        # Type validation
        type_validators = {
            "string": lambda v: isinstance(v, str),
            "number": lambda v: isinstance(v, (int, float)),
            "integer": lambda v: isinstance(v, int),
            "boolean": lambda v: isinstance(v, bool),
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
        }
        
        validator = type_validators.get(self.type)
        if validator and not validator(value):
            errors.append(f"Parameter '{self.name}' must be of type {self.type}")
            return errors
        
        # Enum validation
        if self.enum and value not in self.enum:
            errors.append(f"Parameter '{self.name}' must be one of {self.enum}")
        
        # String-specific validation
        if self.type == "string" and isinstance(value, str):
            if self.pattern:
                if not re.match(self.pattern, value):
                    errors.append(f"Parameter '{self.name}' does not match pattern {self.pattern}")
            if self.min_length is not None and len(value) < self.min_length:
                errors.append(f"Parameter '{self.name}' must be at least {self.min_length} characters")
            if self.max_length is not None and len(value) > self.max_length:
                errors.append(f"Parameter '{self.name}' must be at most {self.max_length} characters")
        
        # Number-specific validation
        if self.type in ("number", "integer") and isinstance(value, (int, float)):
            if self.min_value is not None and value < self.min_value:
                errors.append(f"Parameter '{self.name}' must be >= {self.min_value}")
            if self.max_value is not None and value > self.max_value:
                errors.append(f"Parameter '{self.name}' must be <= {self.max_value}")
        
        # Array-specific validation
        if self.type == "array" and isinstance(value, list):
            if self.min_length is not None and len(value) < self.min_length:
                errors.append(f"Parameter '{self.name}' must have at least {self.min_length} items")
            if self.max_length is not None and len(value) > self.max_length:
                errors.append(f"Parameter '{self.name}' must have at most {self.max_length} items")
        
        return errors


class ToolMetadata(BaseModel):
    """
    Tool Metadata - Unified Standard.
    
    Complete metadata definition for a tool, including:
    - Basic information (id, name, version, description)
    - Author and source information
    - Parameter definitions
    - Authorization and security settings
    - Execution configuration
    - Dependencies and conflicts
    - Tags and examples
    """
    
    # ========== Basic Information ==========
    id: str                                          # Unique tool identifier
    name: str                                        # Tool name
    version: str = "1.0.0"                          # Version number
    description: str                                 # Description
    category: ToolCategory = ToolCategory.CUSTOM    # Category
    
    # ========== Author and Source ==========
    author: Optional[str] = None
    source: str = "builtin"                         # builtin/plugin/custom/mcp
    package: Optional[str] = None                   # Package name
    homepage: Optional[str] = None
    repository: Optional[str] = None
    
    # ========== Parameter Definitions ==========
    parameters: List[ToolParameter] = Field(default_factory=list)
    return_type: str = "string"
    return_description: Optional[str] = None
    
    # ========== Authorization and Security ==========
    authorization: AuthorizationRequirement = Field(
        default_factory=AuthorizationRequirement
    )
    
    # ========== Execution Configuration ==========
    timeout: int = 60                               # Default timeout in seconds
    max_concurrent: int = 1                         # Maximum concurrent executions
    retry_count: int = 0                            # Retry count on failure
    retry_delay: float = 1.0                        # Retry delay in seconds
    
    # ========== Dependencies and Conflicts ==========
    dependencies: List[str] = Field(default_factory=list)      # Required tools
    conflicts: List[str] = Field(default_factory=list)         # Conflicting tools
    
    # ========== Tags and Examples ==========
    tags: List[str] = Field(default_factory=list)
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    
    # ========== Meta Information ==========
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    deprecated: bool = False
    deprecation_message: Optional[str] = None
    
    # ========== Extension Fields ==========
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
    
    def get_openai_spec(self) -> Dict[str, Any]:
        """
        Generate OpenAI Function Calling specification.
        
        Returns:
            Dict conforming to OpenAI's function calling format
        """
        properties = {}
        required = []
        
        for param in self.parameters:
            prop: Dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            
            # Add enum if present
            if param.enum:
                prop["enum"] = param.enum
            
            # Add default if present
            if param.default is not None:
                prop["default"] = param.default
            
            # Add constraints for documentation
            if param.min_value is not None:
                prop["minimum"] = param.min_value
            if param.max_value is not None:
                prop["maximum"] = param.max_value
            if param.min_length is not None:
                prop["minLength"] = param.min_length
            if param.max_length is not None:
                prop["maxLength"] = param.max_length
            if param.pattern:
                prop["pattern"] = param.pattern
            
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            }
        }
    
    def validate_arguments(self, arguments: Dict[str, Any]) -> List[str]:
        """
        Validate arguments against parameter definitions.
        
        Args:
            arguments: Dictionary of argument name to value
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Check each defined parameter
        for param in self.parameters:
            value = arguments.get(param.name)
            
            # Use default if not provided
            if value is None and param.default is not None:
                continue
            
            # Validate the value
            param_errors = param.validate_value(value)
            errors.extend(param_errors)
        
        # Check for unknown parameters (warning only, not error)
        known_params = {p.name for p in self.parameters}
        for arg_name in arguments:
            if arg_name not in known_params:
                # This is just informational, not an error
                pass
        
        return errors
    
    def get_sensitive_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract sensitive arguments based on parameter definitions.
        
        Returns:
            Dictionary of sensitive parameter names and their values
        """
        sensitive = {}
        
        # From authorization requirements
        for param_name in self.authorization.sensitive_parameters:
            if param_name in arguments:
                sensitive[param_name] = arguments[param_name]
        
        # From parameter definitions
        for param in self.parameters:
            if param.sensitive and param.name in arguments:
                sensitive[param.name] = arguments[param.name]
            elif param.sensitive_pattern and param.name in arguments:
                value = str(arguments[param.name])
                if re.search(param.sensitive_pattern, value):
                    sensitive[param.name] = arguments[param.name]
        
        return sensitive
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolMetadata":
        """Create from dictionary."""
        return cls.model_validate(data)
