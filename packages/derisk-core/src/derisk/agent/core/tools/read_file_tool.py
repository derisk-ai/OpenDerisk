"""
读取文件工具 - 用于读取 AgentFileSystem 中保存的文件内容
"""
import json
import logging
from typing import Annotated, Any, Dict, List, Optional

from derisk.agent.core.system_tool_registry import system_tool

logger = logging.getLogger(__name__)


@system_tool(
    name="read_file",
    description="读取 AgentFileSystem 中保存的文件内容。用于读取之前执行结果中被归档的大文件。",
    concurrency="parallel",
)
def read_file(
    file_key: Annotated[str, "文件 key，在截断提示中显示，如 'view_abc123_1234567890'"],
    offset: Annotated[int, "起始行号（从 1 开始）"] = 1,
    limit: Annotated[int, "读取行数，-1 表示读取到文件末尾"] = 500,
    agent_file_system: Optional[Any] = None,
) -> str:
    """
    读取 AgentFileSystem 中保存的文件内容

    Args:
        file_key: 文件 key
        offset: 起始行号（从 1 开始）
        limit: 读取行数
        agent_file_system: AgentFileSystem 实例（由系统注入）

    Returns:
        文件内容或错误信息
    """
    if not agent_file_system:
        return "错误: AgentFileSystem 未初始化"

    try:
        import asyncio

        async def _read_async():
            content = await agent_file_system.read_file(file_key)
            if content is None:
                return f"错误: 文件不存在: {file_key}"

            lines = content.split('\n')
            total_lines = len(lines)

            # 处理 offset
            start_idx = max(0, offset - 1)  # 转换为 0-based 索引

            # 处理 limit
            if limit == -1:
                end_idx = total_lines
            else:
                end_idx = min(start_idx + limit, total_lines)

            selected_lines = lines[start_idx:end_idx]
            result = '\n'.join(selected_lines)

            # 添加行号和统计信息
            header = f"[文件: {file_key}]\n[显示第 {offset}-{end_idx} 行，共 {total_lines} 行]\n\n"
            return header + result

        # 检查是否在异步上下文中
        try:
            loop = asyncio.get_running_loop()
            # 在异步上下文中，创建一个 Task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _read_async())
                return future.result()
        except RuntimeError:
            # 没有运行的事件循环
            return asyncio.run(_read_async())

    except Exception as e:
        logger.exception(f"Failed to read file: {e}")
        return f"错误: 读取文件失败: {str(e)}"