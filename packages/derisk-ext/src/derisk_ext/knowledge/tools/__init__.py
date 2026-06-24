"""Built-in knowledge tools (RFC 004).

Tools operate on a KnowledgeSpaceResource mounted onto an Agent. They
look up the VaultFS instance via the registered vault factory and
execute L0/L1/L2/Space/Admin operations.

These same handlers are exposed via the MCP server (RFC 004 §5) so
external tools like Claude Code can drive the space identically.
"""

from derisk_ext.knowledge.tools.base import KnowledgeToolBase
from derisk_ext.knowledge.tools.l0 import (
    VerbatAddTool,
    VerbatSearchTool,
    VerbatGetTool,
    VerbatListTool,
)
from derisk_ext.knowledge.tools.l1 import (
    DocCreateTool,
    DocReadTool,
    DocEditTool,
    DocSearchTool,
    DocListTool,
    DocAppendLogTool,
)
from derisk_ext.knowledge.tools.l2 import (
    EdgeAddTool,
    EdgeInvalidateTool,
    GraphQueryTool,
    GraphTraverseTool,
    GraphBacklinksTool,
)
from derisk_ext.knowledge.tools.space import (
    SchemaReadTool,
    SchemaWriteTool,
    LintRunTool,
)
from derisk_ext.knowledge.tools.admin import (
    ReindexTool,
    SetEmbedderIdentityTool,
)

ALL_KNOWLEDGE_TOOLS = [
    VerbatAddTool,
    VerbatSearchTool,
    VerbatGetTool,
    VerbatListTool,
    DocCreateTool,
    DocReadTool,
    DocEditTool,
    DocSearchTool,
    DocListTool,
    DocAppendLogTool,
    EdgeAddTool,
    EdgeInvalidateTool,
    GraphQueryTool,
    GraphTraverseTool,
    GraphBacklinksTool,
    SchemaReadTool,
    SchemaWriteTool,
    LintRunTool,
    ReindexTool,
    SetEmbedderIdentityTool,
]


def register_knowledge_tools(registry) -> None:
    """Register all built-in knowledge tools with a ToolRegistry."""
    for tool_cls in ALL_KNOWLEDGE_TOOLS:
        registry.register_tool(tool_cls())


__all__ = [
    "KnowledgeToolBase",
    "ALL_KNOWLEDGE_TOOLS",
    "register_knowledge_tools",
    # L0
    "VerbatAddTool",
    "VerbatSearchTool",
    "VerbatGetTool",
    "VerbatListTool",
    # L1
    "DocCreateTool",
    "DocReadTool",
    "DocEditTool",
    "DocSearchTool",
    "DocListTool",
    "DocAppendLogTool",
    # L2
    "EdgeAddTool",
    "EdgeInvalidateTool",
    "GraphQueryTool",
    "GraphTraverseTool",
    "GraphBacklinksTool",
    # Space
    "SchemaReadTool",
    "SchemaWriteTool",
    "LintRunTool",
    # Admin
    "ReindexTool",
    "SetEmbedderIdentityTool",
]
