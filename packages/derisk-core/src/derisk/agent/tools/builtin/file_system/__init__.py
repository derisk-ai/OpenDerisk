"""文件系统工具"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_file_tools(registry: 'ToolRegistry') -> None:
    """注册文件系统工具"""
    from .read import ReadTool
    from .write import WriteTool
    from .edit import EditTool
    from .glob import GlobTool
    from .grep import GrepTool
    from .list_files import ListFilesTool
    from .search import SearchTool
    
    from ...base import ToolSource
    
    registry.register(ReadTool(), source=ToolSource.CORE)
    registry.register(WriteTool(), source=ToolSource.CORE)
    registry.register(EditTool(), source=ToolSource.CORE)
    registry.register(GlobTool(), source=ToolSource.CORE)
    registry.register(GrepTool(), source=ToolSource.CORE)
    registry.register(ListFilesTool(), source=ToolSource.CORE)
    registry.register(SearchTool(), source=ToolSource.CORE)
