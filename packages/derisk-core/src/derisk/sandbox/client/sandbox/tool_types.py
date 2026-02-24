from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


@dataclass
class AvailableTool:
    """
    Describe an available command-line tool.
    """
    name: str
    """Tool’s command / binary name"""

    description: Optional[str] = None
    """Tool’s functionality description"""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ToolSpec:
    """
    Tool specification
    """
    ver: Optional[str] = None
    bin: Optional[str] = None
    alias: Optional[List[str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ToolCategory:
    """
    Categorize available tools by functionality
    """
    category: str
    """Name of tool category"""

    tools: List[AvailableTool] = field(default_factory=list)
    """List of tools under this category"""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
