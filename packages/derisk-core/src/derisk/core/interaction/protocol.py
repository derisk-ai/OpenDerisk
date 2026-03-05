"""
Interaction Protocol - Unified Tool Authorization System

This module defines the interaction protocol for user communication:
- Interaction types and statuses
- Request and response models
- Convenience functions for creating interactions

Version: 2.0
"""

from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
import uuid


class InteractionType(str, Enum):
    """Types of user interactions."""
    # User input types
    TEXT_INPUT = "text_input"              # Free text input
    FILE_UPLOAD = "file_upload"            # File upload
    
    # Selection types
    SINGLE_SELECT = "single_select"        # Single option selection
    MULTI_SELECT = "multi_select"          # Multiple option selection
    
    # Confirmation types
    CONFIRMATION = "confirmation"          # Yes/No confirmation
    AUTHORIZATION = "authorization"        # Tool authorization request
    PLAN_SELECTION = "plan_selection"      # Plan/strategy selection
    
    # Notification types
    INFO = "info"                          # Information message
    WARNING = "warning"                    # Warning message
    ERROR = "error"                        # Error message
    SUCCESS = "success"                    # Success message
    PROGRESS = "progress"                  # Progress update
    
    # Task management types
    TODO_CREATE = "todo_create"            # Create todo item
    TODO_UPDATE = "todo_update"            # Update todo item


class InteractionPriority(str, Enum):
    """Priority levels for interactions."""
    LOW = "low"                # Can be deferred
    NORMAL = "normal"          # Normal processing
    HIGH = "high"              # Should be handled promptly
    CRITICAL = "critical"      # Must be handled immediately


class InteractionStatus(str, Enum):
    """Status of an interaction request."""
    PENDING = "pending"        # Waiting for response
    RESPONDED = "responded"    # User has responded
    EXPIRED = "expired"        # Request has expired
    CANCELLED = "cancelled"    # Request was cancelled
    SKIPPED = "skipped"        # User skipped the interaction
    DEFERRED = "deferred"      # User deferred the interaction


class InteractionOption(BaseModel):
    """
    Option for selection-type interactions.
    """
    label: str                             # Display text
    value: str                             # Value returned on selection
    description: Optional[str] = None      # Extended description
    icon: Optional[str] = None             # Icon identifier
    disabled: bool = False                 # Whether option is disabled
    default: bool = False                  # Whether this is the default option
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InteractionRequest(BaseModel):
    """
    Interaction request sent to the user.
    
    Supports various interaction types including confirmations,
    selections, text input, file uploads, and notifications.
    """
    # Basic information
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: InteractionType
    priority: InteractionPriority = InteractionPriority.NORMAL
    
    # Content
    title: Optional[str] = None
    message: str
    options: List[InteractionOption] = Field(default_factory=list)
    
    # Default values
    default_value: Optional[str] = None
    default_values: List[str] = Field(default_factory=list)
    
    # Control flags
    timeout: Optional[int] = None          # Timeout in seconds
    allow_cancel: bool = True              # Allow cancellation
    allow_skip: bool = False               # Allow skipping
    allow_defer: bool = False              # Allow deferring
    
    # Session context
    session_id: Optional[str] = None
    agent_name: Optional[str] = None
    step_index: Optional[int] = None
    execution_id: Optional[str] = None
    
    # Authorization context (for AUTHORIZATION type)
    authorization_context: Optional[Dict[str, Any]] = None
    allow_session_grant: bool = True       # Allow "always allow" option
    
    # File upload settings (for FILE_UPLOAD type)
    accepted_file_types: List[str] = Field(default_factory=list)
    max_file_size: Optional[int] = None    # Max size in bytes
    allow_multiple_files: bool = False
    
    # Progress settings (for PROGRESS type)
    progress_value: Optional[float] = None  # 0.0 to 1.0
    progress_message: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = self.model_dump()
        data['created_at'] = self.created_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InteractionRequest":
        """Create from dictionary."""
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls.model_validate(data)


class InteractionResponse(BaseModel):
    """
    User response to an interaction request.
    """
    # Reference
    request_id: str
    session_id: Optional[str] = None
    
    # Response content
    choice: Optional[str] = None           # Single selection
    choices: List[str] = Field(default_factory=list)  # Multiple selections
    input_value: Optional[str] = None      # Text input value
    file_ids: List[str] = Field(default_factory=list)  # Uploaded file IDs
    
    # Status
    status: InteractionStatus = InteractionStatus.RESPONDED
    
    # User message (optional explanation)
    user_message: Optional[str] = None
    cancel_reason: Optional[str] = None
    
    # Authorization grant scope
    grant_scope: Optional[str] = None      # "once", "session", "always"
    grant_duration: Optional[int] = None   # Duration in seconds
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True
    
    @property
    def is_confirmed(self) -> bool:
        """Check if this is a positive confirmation."""
        if self.status != InteractionStatus.RESPONDED:
            return False
        if self.choice:
            return self.choice.lower() in ("yes", "confirm", "allow", "approve", "true")
        return False
    
    @property
    def is_denied(self) -> bool:
        """Check if this is a negative confirmation."""
        if self.status == InteractionStatus.CANCELLED:
            return True
        if self.choice:
            return self.choice.lower() in ("no", "deny", "reject", "cancel", "false")
        return False
    
    @property
    def is_session_grant(self) -> bool:
        """Check if user granted session-level permission."""
        return self.grant_scope == "session"
    
    @property
    def is_always_grant(self) -> bool:
        """Check if user granted permanent permission."""
        return self.grant_scope == "always"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = self.model_dump()
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InteractionResponse":
        """Create from dictionary."""
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls.model_validate(data)


# ============ Convenience Functions ============

def create_authorization_request(
    tool_name: str,
    tool_description: str,
    arguments: Dict[str, Any],
    risk_level: str = "medium",
    risk_factors: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    allow_session_grant: bool = True,
    timeout: Optional[int] = None,
) -> InteractionRequest:
    """
    Create an authorization request for tool execution.
    
    Args:
        tool_name: Name of the tool
        tool_description: Description of the tool
        arguments: Tool arguments
        risk_level: Risk level (safe, low, medium, high, critical)
        risk_factors: List of risk factors
        session_id: Session ID
        agent_name: Agent name
        allow_session_grant: Allow session-level grant
        timeout: Request timeout in seconds
        
    Returns:
        InteractionRequest for authorization
    """
    # Format arguments for display
    args_display = "\n".join(f"  - {k}: {v}" for k, v in arguments.items())
    
    message = f"""Tool: **{tool_name}**

{tool_description}

**Arguments:**
{args_display}

**Risk Level:** {risk_level.upper()}"""
    
    if risk_factors:
        message += f"\n\n**Risk Factors:**\n" + "\n".join(f"  - {f}" for f in risk_factors)
    
    message += "\n\nDo you want to allow this operation?"
    
    options = [
        InteractionOption(
            label="Allow",
            value="allow",
            description="Allow this operation once",
            default=True,
        ),
        InteractionOption(
            label="Deny",
            value="deny",
            description="Deny this operation",
        ),
    ]
    
    if allow_session_grant:
        options.insert(1, InteractionOption(
            label="Allow for Session",
            value="allow_session",
            description="Allow this tool for the entire session",
        ))
    
    return InteractionRequest(
        type=InteractionType.AUTHORIZATION,
        priority=InteractionPriority.HIGH,
        title=f"Authorization Required: {tool_name}",
        message=message,
        options=options,
        session_id=session_id,
        agent_name=agent_name,
        allow_session_grant=allow_session_grant,
        timeout=timeout,
        authorization_context={
            "tool_name": tool_name,
            "arguments": arguments,
            "risk_level": risk_level,
            "risk_factors": risk_factors or [],
        },
    )


def create_text_input_request(
    message: str,
    title: Optional[str] = None,
    default_value: Optional[str] = None,
    placeholder: Optional[str] = None,
    session_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    required: bool = True,
    timeout: Optional[int] = None,
) -> InteractionRequest:
    """
    Create a text input request.
    
    Args:
        message: Prompt message
        title: Dialog title
        default_value: Default input value
        placeholder: Input placeholder text
        session_id: Session ID
        agent_name: Agent name
        required: Whether input is required
        timeout: Request timeout in seconds
        
    Returns:
        InteractionRequest for text input
    """
    return InteractionRequest(
        type=InteractionType.TEXT_INPUT,
        title=title or "Input Required",
        message=message,
        default_value=default_value,
        session_id=session_id,
        agent_name=agent_name,
        allow_skip=not required,
        timeout=timeout,
        metadata={"placeholder": placeholder} if placeholder else {},
    )


def create_confirmation_request(
    message: str,
    title: Optional[str] = None,
    confirm_label: str = "Yes",
    cancel_label: str = "No",
    default_confirm: bool = False,
    session_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    timeout: Optional[int] = None,
) -> InteractionRequest:
    """
    Create a yes/no confirmation request.
    
    Args:
        message: Confirmation message
        title: Dialog title
        confirm_label: Label for confirm button
        cancel_label: Label for cancel button
        default_confirm: Whether confirm is the default
        session_id: Session ID
        agent_name: Agent name
        timeout: Request timeout in seconds
        
    Returns:
        InteractionRequest for confirmation
    """
    return InteractionRequest(
        type=InteractionType.CONFIRMATION,
        title=title or "Confirmation Required",
        message=message,
        options=[
            InteractionOption(
                label=confirm_label,
                value="yes",
                default=default_confirm,
            ),
            InteractionOption(
                label=cancel_label,
                value="no",
                default=not default_confirm,
            ),
        ],
        session_id=session_id,
        agent_name=agent_name,
        timeout=timeout,
    )


def create_selection_request(
    message: str,
    options: List[Union[str, Dict[str, Any], InteractionOption]],
    title: Optional[str] = None,
    multiple: bool = False,
    default_value: Optional[str] = None,
    default_values: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    timeout: Optional[int] = None,
) -> InteractionRequest:
    """
    Create a selection request.
    
    Args:
        message: Selection prompt
        options: List of options (strings, dicts, or InteractionOption)
        title: Dialog title
        multiple: Allow multiple selections
        default_value: Default selection (single)
        default_values: Default selections (multiple)
        session_id: Session ID
        agent_name: Agent name
        timeout: Request timeout in seconds
        
    Returns:
        InteractionRequest for selection
    """
    parsed_options = []
    for opt in options:
        if isinstance(opt, str):
            parsed_options.append(InteractionOption(
                label=opt,
                value=opt,
            ))
        elif isinstance(opt, dict):
            parsed_options.append(InteractionOption(**opt))
        elif isinstance(opt, InteractionOption):
            parsed_options.append(opt)
    
    return InteractionRequest(
        type=InteractionType.MULTI_SELECT if multiple else InteractionType.SINGLE_SELECT,
        title=title or "Selection Required",
        message=message,
        options=parsed_options,
        default_value=default_value,
        default_values=default_values or [],
        session_id=session_id,
        agent_name=agent_name,
        timeout=timeout,
    )


def create_notification(
    message: str,
    type: InteractionType = InteractionType.INFO,
    title: Optional[str] = None,
    session_id: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> InteractionRequest:
    """
    Create a notification (no response required).
    
    Args:
        message: Notification message
        type: Notification type (INFO, WARNING, ERROR, SUCCESS)
        title: Notification title
        session_id: Session ID
        agent_name: Agent name
        
    Returns:
        InteractionRequest for notification
    """
    if type not in (InteractionType.INFO, InteractionType.WARNING, 
                    InteractionType.ERROR, InteractionType.SUCCESS):
        type = InteractionType.INFO
    
    return InteractionRequest(
        type=type,
        title=title,
        message=message,
        session_id=session_id,
        agent_name=agent_name,
        allow_cancel=False,
        timeout=0,  # No response needed
    )


def create_progress_update(
    message: str,
    progress: float,
    title: Optional[str] = None,
    session_id: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> InteractionRequest:
    """
    Create a progress update notification.
    
    Args:
        message: Progress message
        progress: Progress value (0.0 to 1.0)
        title: Progress title
        session_id: Session ID
        agent_name: Agent name
        
    Returns:
        InteractionRequest for progress update
    """
    return InteractionRequest(
        type=InteractionType.PROGRESS,
        title=title or "Progress",
        message=message,
        progress_value=max(0.0, min(1.0, progress)),
        progress_message=message,
        session_id=session_id,
        agent_name=agent_name,
        allow_cancel=False,
        timeout=0,  # No response needed
    )
