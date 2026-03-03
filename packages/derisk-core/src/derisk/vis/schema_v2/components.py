"""
VIS Protocol V2 - Component Schema Definitions

Defines schemas for all built-in VIS components.
"""

from .core import (
    VisComponentSchema,
    VisPropertyDefinition,
    VisPropertyType,
    VisSlotDefinition,
    VisEventDefinition,
    IncrementalStrategy,
    get_schema_registry,
)


def register_all_schemas() -> None:
    """Register all built-in component schemas."""
    registry = get_schema_registry()
    
    _register_thinking_schema(registry)
    _register_message_schema(registry)
    _register_text_schema(registry)
    _register_tool_schema(registry)
    _register_plan_schema(registry)
    _register_chart_schema(registry)
    _register_code_schema(registry)
    _register_confirm_schema(registry)
    _register_select_schema(registry)
    _register_dashboard_schema(registry)
    _register_attach_schema(registry)
    _register_todo_schema(registry)


def _register_thinking_schema(registry) -> None:
    """Register vis-thinking component schema."""
    schema = VisComponentSchema(
        tag="vis-thinking",
        version="1.0.0",
        description="Displays the agent's thinking/reasoning process",
        category="reasoning",
        properties={
            "uid": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Unique identifier for this component",
                required=True,
            ),
            "type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Update type: 'incr' for incremental, 'all' for full",
                required=True,
                enum_values=["incr", "all"],
                default="incr",
            ),
            "dynamic": VisPropertyDefinition(
                type=VisPropertyType.BOOLEAN,
                description="Whether this is a dynamic/streaming update",
                default=False,
            ),
            "markdown": VisPropertyDefinition(
                type=VisPropertyType.INCREMENTAL_STRING,
                description="The thinking content in markdown format",
                incremental=IncrementalStrategy.APPEND,
            ),
            "think_link": VisPropertyDefinition(
                type=VisPropertyType.URI,
                description="Link to detailed thinking view",
            ),
        },
        slots={
            "details": VisSlotDefinition(
                name="details",
                description="Detailed thinking breakdown",
                type="single",
            ),
        },
        events={
            "expand": VisEventDefinition(
                name="expand",
                description="Fired when user expands thinking details",
                action="emit",
            ),
        },
        examples=[
            {
                "uid": "think-001",
                "type": "incr",
                "markdown": "Analyzing user request...",
            }
        ],
    )
    registry.register(schema)


def _register_message_schema(registry) -> None:
    """Register vis-message/drsk-msg component schema."""
    schema = VisComponentSchema(
        tag="drsk-msg",
        version="1.0.0",
        description="A complete message from an agent",
        category="message",
        properties={
            "uid": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Unique message identifier",
                required=True,
            ),
            "type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Update type",
                required=True,
                enum_values=["incr", "all"],
            ),
            "dynamic": VisPropertyDefinition(
                type=VisPropertyType.BOOLEAN,
                description="Whether this is a streaming message",
                default=False,
            ),
            "markdown": VisPropertyDefinition(
                type=VisPropertyType.INCREMENTAL_STRING,
                description="Message content in markdown",
                incremental=IncrementalStrategy.APPEND,
            ),
            "role": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Role of the message sender",
            ),
            "name": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Display name of the sender",
            ),
            "avatar": VisPropertyDefinition(
                type=VisPropertyType.URI,
                description="Avatar URL for the sender",
            ),
            "model": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Model name used for generation",
            ),
            "start_time": VisPropertyDefinition(
                type=VisPropertyType.TIMESTAMP,
                description="Message creation timestamp",
            ),
            "task_id": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Associated task ID",
            ),
        },
        slots={
            "content": VisSlotDefinition(
                name="content",
                description="Main message content",
                type="single",
                required=True,
            ),
            "actions": VisSlotDefinition(
                name="actions",
                description="Action buttons",
                type="list",
            ),
        },
        events={
            "copy": VisEventDefinition(
                name="copy",
                description="Copy message content",
                action="emit",
            ),
            "retry": VisEventDefinition(
                name="retry",
                description="Retry message generation",
                action="emit",
            ),
        },
    )
    registry.register(schema)


def _register_text_schema(registry) -> None:
    """Register vis-text/drsk-content component schema."""
    schema = VisComponentSchema(
        tag="drsk-content",
        version="1.0.0",
        description="Text content with incremental update support",
        category="content",
        properties={
            "uid": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Unique content identifier",
                required=True,
            ),
            "type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Update type",
                required=True,
                enum_values=["incr", "all"],
            ),
            "dynamic": VisPropertyDefinition(
                type=VisPropertyType.BOOLEAN,
                description="Streaming content flag",
                default=False,
            ),
            "markdown": VisPropertyDefinition(
                type=VisPropertyType.INCREMENTAL_STRING,
                description="Text content in markdown",
                incremental=IncrementalStrategy.APPEND,
            ),
        },
    )
    registry.register(schema)


def _register_tool_schema(registry) -> None:
    """Register vis-tool/drsk-step component schema."""
    schema = VisComponentSchema(
        tag="vis-tool",
        version="1.0.0",
        description="Tool execution display",
        category="action",
        properties={
            "uid": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Unique tool execution identifier",
                required=True,
            ),
            "type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Update type",
                enum_values=["incr", "all"],
                default="all",
            ),
            "name": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Tool name",
                required=True,
            ),
            "args": VisPropertyDefinition(
                type=VisPropertyType.OBJECT,
                description="Tool arguments",
            ),
            "status": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Execution status",
                enum_values=["pending", "running", "completed", "failed"],
                default="pending",
            ),
            "output": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Tool output/result",
            ),
            "error": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Error message if failed",
            ),
            "start_time": VisPropertyDefinition(
                type=VisPropertyType.TIMESTAMP,
                description="Execution start time",
            ),
            "end_time": VisPropertyDefinition(
                type=VisPropertyType.TIMESTAMP,
                description="Execution end time",
            ),
            "progress": VisPropertyDefinition(
                type=VisPropertyType.INTEGER,
                description="Execution progress percentage (0-100)",
                minimum=0,
                maximum=100,
            ),
        },
        slots={
            "details": VisSlotDefinition(
                name="details",
                description="Detailed execution logs",
                type="single",
            ),
        },
        events={
            "cancel": VisEventDefinition(
                name="cancel",
                description="Cancel tool execution",
                action="emit",
            ),
            "retry": VisEventDefinition(
                name="retry",
                description="Retry failed execution",
                action="emit",
            ),
        },
    )
    registry.register(schema)


def _register_plan_schema(registry) -> None:
    """Register vis-plans/drsk-plan component schema."""
    schema = VisComponentSchema(
        tag="drsk-plan",
        version="1.0.0",
        description="Task plan visualization",
        category="planning",
        properties={
            "uid": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Unique plan identifier",
                required=True,
            ),
            "type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Update type",
                enum_values=["incr", "all"],
                default="all",
            ),
            "round_title": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Plan round title",
            ),
            "round_description": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Plan round description",
            ),
            "tasks": VisPropertyDefinition(
                type=VisPropertyType.ARRAY,
                description="List of tasks in the plan",
                items=VisPropertyDefinition(
                    type=VisPropertyType.OBJECT,
                    properties={
                        "task_id": VisPropertyDefinition(
                            type=VisPropertyType.STRING,
                            description="Task ID",
                        ),
                        "task_uid": VisPropertyDefinition(
                            type=VisPropertyType.STRING,
                            description="Task UID",
                        ),
                        "task_name": VisPropertyDefinition(
                            type=VisPropertyType.STRING,
                            description="Task name",
                        ),
                        "task_content": VisPropertyDefinition(
                            type=VisPropertyType.STRING,
                            description="Task description",
                        ),
                        "agent_name": VisPropertyDefinition(
                            type=VisPropertyType.STRING,
                            description="Assigned agent name",
                        ),
                        "status": VisPropertyDefinition(
                            type=VisPropertyType.ENUM,
                            description="Task status",
                            enum_values=["pending", "running", "completed", "failed"],
                        ),
                    },
                ),
            ),
        },
        events={
            "task_click": VisEventDefinition(
                name="task_click",
                description="Task item clicked",
                action="emit",
                payload_schema={"task_id": "string"},
            ),
        },
    )
    registry.register(schema)


def _register_chart_schema(registry) -> None:
    """Register vis-chart component schema."""
    schema = VisComponentSchema(
        tag="vis-chart",
        version="1.0.0",
        description="Data visualization chart",
        category="visualization",
        properties={
            "uid": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Unique chart identifier",
                required=True,
            ),
            "type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Update type",
                enum_values=["incr", "all"],
                default="all",
            ),
            "chart_type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Chart type",
                enum_values=["line", "bar", "pie", "scatter", "area"],
                required=True,
            ),
            "data": VisPropertyDefinition(
                type=VisPropertyType.OBJECT,
                description="Chart data configuration",
                required=True,
            ),
            "config": VisPropertyDefinition(
                type=VisPropertyType.OBJECT,
                description="Chart display configuration",
            ),
            "title": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Chart title",
            ),
        },
        events={
            "point_click": VisEventDefinition(
                name="point_click",
                description="Chart point clicked",
                action="emit",
            ),
        },
    )
    registry.register(schema)


def _register_code_schema(registry) -> None:
    """Register vis-code component schema."""
    schema = VisComponentSchema(
        tag="vis-code",
        version="1.0.0",
        description="Code display with syntax highlighting",
        category="content",
        properties={
            "uid": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Unique code block identifier",
                required=True,
            ),
            "type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Update type",
                enum_values=["incr", "all"],
                default="all",
            ),
            "language": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Programming language",
                default="python",
            ),
            "code": VisPropertyDefinition(
                type=VisPropertyType.INCREMENTAL_STRING,
                description="Code content",
                incremental=IncrementalStrategy.APPEND,
            ),
            "filename": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Source file name",
            ),
            "executable": VisPropertyDefinition(
                type=VisPropertyType.BOOLEAN,
                description="Whether code can be executed",
                default=False,
            ),
        },
        events={
            "run": VisEventDefinition(
                name="run",
                description="Execute the code",
                action="emit",
            ),
            "copy": VisEventDefinition(
                name="copy",
                description="Copy code to clipboard",
                action="emit",
            ),
        },
    )
    registry.register(schema)


def _register_confirm_schema(registry) -> None:
    """Register vis-confirm component schema."""
    schema = VisComponentSchema(
        tag="vis-confirm",
        version="1.0.0",
        description="User confirmation dialog",
        category="interaction",
        properties={
            "uid": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Unique confirm identifier",
                required=True,
            ),
            "type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Update type",
                enum_values=["incr", "all"],
                default="all",
            ),
            "markdown": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Confirmation message",
                required=True,
            ),
            "disabled": VisPropertyDefinition(
                type=VisPropertyType.BOOLEAN,
                description="Whether buttons are disabled",
                default=False,
            ),
            "extra": VisPropertyDefinition(
                type=VisPropertyType.OBJECT,
                description="Extra data to pass on confirmation",
            ),
        },
        events={
            "confirm": VisEventDefinition(
                name="confirm",
                description="User confirmed action",
                action="emit",
            ),
            "cancel": VisEventDefinition(
                name="cancel",
                description="User cancelled action",
                action="emit",
            ),
        },
    )
    registry.register(schema)


def _register_select_schema(registry) -> None:
    """Register vis-select component schema."""
    schema = VisComponentSchema(
        tag="vis-select",
        version="1.0.0",
        description="User selection options",
        category="interaction",
        properties={
            "uid": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Unique select identifier",
                required=True,
            ),
            "type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Update type",
                enum_values=["incr", "all"],
                default="all",
            ),
            "options": VisPropertyDefinition(
                type=VisPropertyType.ARRAY,
                description="Selection options",
                required=True,
                items=VisPropertyDefinition(
                    type=VisPropertyType.OBJECT,
                    properties={
                        "markdown": VisPropertyDefinition(
                            type=VisPropertyType.STRING,
                            description="Option display text",
                        ),
                        "confirm_message": VisPropertyDefinition(
                            type=VisPropertyType.STRING,
                            description="Message to send when selected",
                        ),
                        "extra": VisPropertyDefinition(
                            type=VisPropertyType.OBJECT,
                            description="Extra data for this option",
                        ),
                    },
                ),
            ),
        },
        events={
            "select": VisEventDefinition(
                name="select",
                description="Option selected",
                action="emit",
                payload_schema={"option_index": "integer"},
            ),
        },
    )
    registry.register(schema)


def _register_dashboard_schema(registry) -> None:
    """Register vis-dashboard component schema."""
    schema = VisComponentSchema(
        tag="vis-dashboard",
        version="1.0.0",
        description="Dashboard layout for multiple widgets",
        category="layout",
        properties={
            "uid": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Unique dashboard identifier",
                required=True,
            ),
            "type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Update type",
                enum_values=["incr", "all"],
                default="all",
            ),
            "layout": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Dashboard layout type",
                enum_values=["grid", "flex", "custom"],
                default="grid",
            ),
            "columns": VisPropertyDefinition(
                type=VisPropertyType.INTEGER,
                description="Number of columns in grid layout",
                minimum=1,
                maximum=12,
                default=2,
            ),
        },
        slots={
            "widgets": VisSlotDefinition(
                name="widgets",
                description="Dashboard widgets",
                type="list",
            ),
        },
    )
    registry.register(schema)


def _register_attach_schema(registry) -> None:
    """Register d-attach component schema."""
    schema = VisComponentSchema(
        tag="d-attach",
        version="1.0.0",
        description="File attachment display",
        category="content",
        properties={
            "uid": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Unique attachment identifier",
                required=True,
            ),
            "type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Update type",
                enum_values=["incr", "all"],
                default="all",
            ),
            "file_id": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="File unique identifier",
                required=True,
            ),
            "file_name": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="File name",
                required=True,
            ),
            "file_type": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="File MIME type",
                required=True,
            ),
            "file_size": VisPropertyDefinition(
                type=VisPropertyType.INTEGER,
                description="File size in bytes",
                minimum=0,
            ),
            "oss_url": VisPropertyDefinition(
                type=VisPropertyType.URI,
                description="OSS download URL",
            ),
            "preview_url": VisPropertyDefinition(
                type=VisPropertyType.URI,
                description="Preview URL",
            ),
            "download_url": VisPropertyDefinition(
                type=VisPropertyType.URI,
                description="Download URL",
            ),
        },
        events={
            "download": VisEventDefinition(
                name="download",
                description="Download file",
                action="emit",
            ),
            "preview": VisEventDefinition(
                name="preview",
                description="Preview file",
                action="emit",
            ),
        },
    )
    registry.register(schema)


def _register_todo_schema(registry) -> None:
    """Register vis-todo component schema."""
    schema = VisComponentSchema(
        tag="vis-todo",
        version="1.0.0",
        description="Todo list display",
        category="planning",
        properties={
            "uid": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Unique todo list identifier",
                required=True,
            ),
            "type": VisPropertyDefinition(
                type=VisPropertyType.ENUM,
                description="Update type",
                enum_values=["incr", "all"],
                default="all",
            ),
            "mission": VisPropertyDefinition(
                type=VisPropertyType.STRING,
                description="Mission/task description",
            ),
            "items": VisPropertyDefinition(
                type=VisPropertyType.ARRAY,
                description="Todo items",
                items=VisPropertyDefinition(
                    type=VisPropertyType.OBJECT,
                    properties={
                        "id": VisPropertyDefinition(
                            type=VisPropertyType.STRING,
                            description="Item ID",
                        ),
                        "title": VisPropertyDefinition(
                            type=VisPropertyType.STRING,
                            description="Item title",
                        ),
                        "status": VisPropertyDefinition(
                            type=VisPropertyType.ENUM,
                            description="Item status",
                            enum_values=["pending", "working", "completed", "failed"],
                        ),
                        "index": VisPropertyDefinition(
                            type=VisPropertyType.INTEGER,
                            description="Item order index",
                        ),
                    },
                ),
            ),
            "current_index": VisPropertyDefinition(
                type=VisPropertyType.INTEGER,
                description="Currently active item index",
                minimum=0,
            ),
        },
        events={
            "item_click": VisEventDefinition(
                name="item_click",
                description="Todo item clicked",
                action="emit",
            ),
        },
    )
    registry.register(schema)