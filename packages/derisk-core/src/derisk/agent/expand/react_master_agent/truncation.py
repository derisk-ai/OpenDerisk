"""
工具输出截断模块 (Truncate.output)

对于可能返回大量文本的工具 (如 read, grep, bash)，其输出在返回给 LLM 之前
会经过 Truncate.output 函数的处理。

文件管理使用 AgentFileSystem 实现统一接入。
"""

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING, Tuple, Union
import asyncio

from derisk.agent.core.memory.gpts.file_base import FileType

if TYPE_CHECKING:
    try:
        from derisk.agent.expand.pdca_agent.agent_file_system import AgentFileSystem
    except ImportError:
        AgentFileSystem = None

logger = logging.getLogger(__name__)


@dataclass
class TruncationResult:
    """截断结果"""

    content: str
    is_truncated: bool
    original_lines: int
    truncated_lines: int
    original_bytes: int
    truncated_bytes: int
    temp_file_path: Optional[str] = None
    file_key: Optional[str] = None  # 使用文件 key 而非路径
    suggestion: Optional[str] = None


class TruncationConfig:
    """截断配置"""

    DEFAULT_MAX_LINES = 500
    DEFAULT_MAX_BYTES = 5 * 1024

    TRUNCATION_SUGGESTION_TEMPLATE = """
[输出已截断]
原始输出包含 {original_lines} 行 ({original_bytes} 字节)，已超过限制。
完整输出已保存至: {file_path}

**使用 read 工具读取完整内容：**
{{"path": "{file_path}"}}

如需分页读取（内容较大时）：
{{"path": "{file_path}", "offset": 1, "limit": 500}}
{{"path": "{file_path}", "offset": 501, "limit": 500}}
"""

    TRUNCATION_SUGGESTION_TEMPLATE_NO_AFS = """
[输出已截断]
原始输出包含 {original_lines} 行 ({original_bytes} 字节)，已超过限制。
完整输出已保存至: {file_path}
"""

    @staticmethod
    def generate_dattach_tag(
        file_name: str,
        file_path: str,
        file_size: int,
        file_key: Optional[str] = None,
        tool_name: str = "unknown",
    ) -> str:
        """生成 d-attach 组件标签"""
        try:
            attach_data = {
                "file_name": file_name,
                "file_size": file_size,
                "file_type": "truncated_output",
                "oss_url": file_path,
                "preview_url": file_path,
                "download_url": file_path,
                "mime_type": "text/plain",
                "description": f"工具 {tool_name} 的完整输出（已截断）",
            }

            if file_key:
                attach_data["file_id"] = file_key

            content = json.dumps([attach_data], ensure_ascii=False)
            return f"\n\n```d-attach\n{content}\n```\n"
        except Exception as e:
            logger.warning(f"Failed to generate d-attach tag: {e}")
            return f"\n\n完整输出文件: {file_path}"


class Truncator:
    """工具输出截断器"""

    def __init__(
        self,
        max_lines: int = TruncationConfig.DEFAULT_MAX_LINES,
        max_bytes: int = TruncationConfig.DEFAULT_MAX_BYTES,
        agent_file_system: Optional["AgentFileSystem"] = None,
        use_legacy_mode: bool = False,
    ):
        """
        初始化截断器

        Args:
            max_lines: 最大行数限制
            max_bytes: 最大字节数限制
            agent_file_system: AgentFileSystem 实例，用于统一文件管理
            use_legacy_mode: 是否使用传统模式（不使用 AFS）
        """
        self.max_lines = max_lines
        self.max_bytes = max_bytes
        self.agent_file_system = agent_file_system
        self.use_legacy_mode = use_legacy_mode

        # 传统模式下的输出目录
        self.legacy_output_dir = os.path.expanduser("~/.opencode/tool-output")
        if self.use_legacy_mode:
            self._ensure_output_dir()

        # 用于生成文件 key 的计数器
        self._file_count = 0

    def _ensure_output_dir(self):
        """确保传统模式下的输出目录存在"""
        os.makedirs(self.legacy_output_dir, exist_ok=True)

    def _generate_file_key(self, tool_name: str, content: str) -> str:
        """生成唯一的文件 key"""
        self._file_count += 1
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
        clean_tool_name = (
            tool_name.replace("/", "_").replace("\\", "_").replace(" ", "_")
        )
        return f"tool_output_{clean_tool_name}_{content_hash}_{self._file_count}"

    def _generate_temp_file_path(self, content: str, tool_name: str) -> str:
        """传统模式：生成临时文件路径"""
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
        filename = f"{tool_name}_{content_hash}_{self._file_count}.txt"
        return os.path.join(self.legacy_output_dir, filename)

    async def _save_via_agent_file_system(
        self, content: str, tool_name: str
    ) -> Tuple[str, str, Optional[str]]:
        """
        使用 AgentFileSystem 保存文件（异步版本）

        Returns:
            Tuple[file_key, local_path, sandbox_path]: 文件 key、本地路径和 sandbox 路径
        """
        if self.agent_file_system is None or self.use_legacy_mode:
            raise RuntimeError("AgentFileSystem not available or in legacy mode")

        file_key = self._generate_file_key(tool_name, content)

        logger.info(
            f"[AFS] Saving truncated output: key={file_key}, "
            f"afs_id={id(self.agent_file_system)}, "
            f"conv_id={getattr(self.agent_file_system, 'conv_id', 'N/A')}"
        )

        # 使用 AgentFileSystem 异步保存文件
        file_metadata = await self.agent_file_system.save_file(
            file_key=file_key,
            data=content,
            file_type=FileType.TRUNCATED_OUTPUT,
            extension="txt",
            tool_name=tool_name,
        )

        # 构建 sandbox 路径（如果有 sandbox）
        sandbox_path = None
        sandbox = getattr(self.agent_file_system, "sandbox", None)
        if sandbox:
            goal_id = getattr(self.agent_file_system, "goal_id", "default")
            work_dir = getattr(sandbox, "work_dir", "/home/ubuntu")
            safe_key = self.agent_file_system._sanitize_filename(file_key)
            if "." not in safe_key:
                safe_key = f"{safe_key}.txt"
            sandbox_path = f"{work_dir}/{goal_id}/{safe_key}"

        logger.info(
            f"[AFS] Saved truncated output via AgentFileSystem: "
            f"key={file_key}, path={file_metadata.local_path}, sandbox_path={sandbox_path}"
        )

        return file_key, file_metadata.local_path, sandbox_path

    def _save_via_agent_file_system_sync(
        self, content: str, tool_name: str
    ) -> Tuple[str, str, Optional[str]]:
        """
        使用 AgentFileSystem 保存文件（同步版本）

        Returns:
            Tuple[file_key, local_path, sandbox_path]: 文件 key、本地路径和 sandbox 路径
        """
        import concurrent.futures

        async def _save():
            return await self._save_via_agent_file_system(content, tool_name)

        try:
            loop = asyncio.get_running_loop()
            # 已经在异步上下文中，使用 run_in_executor 在新线程中运行
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _save())
                return future.result()
        except RuntimeError:
            # 没有运行的事件循环，直接创建新的
            return asyncio.run(_save())

    def _save_to_legacy_temp_file(self, content: str, tool_name: str) -> str:
        """传统模式：将完整内容保存到临时文件"""
        file_path = self._generate_temp_file_path(content, tool_name)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return file_path
        except Exception as e:
            logger.error(f"Failed to save truncated output to temp file: {e}")
            # 使用系统临时目录作为备选
            fd, temp_path = tempfile.mkstemp(suffix=".txt", prefix=f"{tool_name}_")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                return temp_path
            except Exception as e2:
                logger.error(f"Failed to save to fallback temp file: {e2}")
                os.close(fd)
                return ""

    async def truncate_async(
        self,
        content: str,
        tool_name: str = "unknown",
        max_lines: Optional[int] = None,
        max_bytes: Optional[int] = None,
    ) -> TruncationResult:
        """
        异步截断工具输出（推荐在异步上下文中使用）

        Args:
            content: 原始输出内容
            tool_name: 工具名称，用于生成文件名
            max_lines: 最大行数限制，默认使用配置值
            max_bytes: 最大字节数限制，默认使用配置值

        Returns:
            TruncationResult: 截断结果
        """
        if not content:
            return TruncationResult(
                content="",
                is_truncated=False,
                original_lines=0,
                truncated_lines=0,
                original_bytes=0,
                truncated_bytes=0,
            )

        max_lines = max_lines or self.max_lines
        max_bytes = max_bytes or self.max_bytes

        original_bytes = len(content.encode("utf-8"))
        lines = content.split("\n")
        original_lines = len(lines)

        # 检查是否需要截断
        need_truncate = original_lines > max_lines or original_bytes > max_bytes

        if not need_truncate:
            return TruncationResult(
                content=content,
                is_truncated=False,
                original_lines=original_lines,
                truncated_lines=original_lines,
                original_bytes=original_bytes,
                truncated_bytes=original_bytes,
            )

        # 执行截断
        logger.info(
            f"Truncating output for {tool_name}: "
            f"{original_lines} lines, {original_bytes} bytes -> "
            f"max {max_lines} lines, {max_bytes} bytes"
        )

        # 先按字节截断
        truncated_content = content
        if original_bytes > max_bytes:
            # 保留前 max_bytes 字节，但要确保不切断多字节字符
            truncated_bytes = content.encode("utf-8")[:max_bytes]
            truncated_content = truncated_bytes.decode("utf-8", errors="ignore")

        # 再按行截断
        truncated_lines = truncated_content.split("\n")
        if len(truncated_lines) > max_lines:
            truncated_lines = truncated_lines[:max_lines]
            truncated_content = "\n".join(truncated_lines)

        truncated_lines_count = len(truncated_lines)
        truncated_bytes_count = len(truncated_content.encode("utf-8"))

        # 保存完整内容到文件（使用 AgentFileSystem 或传统模式）
        file_key = None
        temp_file_path = None

        try:
            if self.agent_file_system and not self.use_legacy_mode:
                (
                    file_key,
                    temp_file_path,
                    sandbox_path,
                ) = await self._save_via_agent_file_system(content, tool_name)
                file_path = sandbox_path or temp_file_path
                suggestion = TruncationConfig.TRUNCATION_SUGGESTION_TEMPLATE.format(
                    original_lines=original_lines,
                    original_bytes=original_bytes,
                    file_path=file_path,
                )
                dattach_tag = TruncationConfig.generate_dattach_tag(
                    file_name=f"{tool_name}_output.txt",
                    file_path=temp_file_path or "",
                    file_size=original_bytes,
                    file_key=file_key,
                    tool_name=tool_name,
                )
            else:
                temp_file_path = self._save_to_legacy_temp_file(content, tool_name)
                suggestion = (
                    TruncationConfig.TRUNCATION_SUGGESTION_TEMPLATE_NO_AFS.format(
                        original_lines=original_lines,
                        original_bytes=original_bytes,
                        file_path=temp_file_path or "unknown",
                    )
                )
                dattach_tag = TruncationConfig.generate_dattach_tag(
                    file_name=f"{tool_name}_output.txt",
                    file_path=temp_file_path or "",
                    file_size=original_bytes,
                    tool_name=tool_name,
                )
        except Exception as e:
            logger.error(f"[Layer1-Truncation] ERROR saving '{tool_name}': {e}")
            suggestion = f"""
[输出已截断]
原始输出包含 {original_lines} 行 ({original_bytes} 字节)，已超过限制。
完整输出因保存失败而未持久化。

建议处理方式:
1. 重新执行工具操作
2. 检查文件系统状态
"""
            dattach_tag = ""

        final_content = truncated_content + suggestion + dattach_tag

        return TruncationResult(
            content=final_content,
            is_truncated=True,
            original_lines=original_lines,
            truncated_lines=truncated_lines_count,
            original_bytes=original_bytes,
            truncated_bytes=truncated_bytes_count,
            temp_file_path=temp_file_path,
            file_key=file_key,
            suggestion=suggestion,
        )

    def truncate(
        self,
        content: str,
        tool_name: str = "unknown",
        max_lines: Optional[int] = None,
        max_bytes: Optional[int] = None,
    ) -> TruncationResult:
        """
        截断工具输出（同步版本，不推荐在异步上下文中使用）

        注意：在异步上下文中，请使用 truncate_async() 方法以避免潜在的问题。

        Args:
            content: 原始输出内容
            tool_name: 工具名称，用于生成文件名
            max_lines: 最大行数限制，默认使用配置值
            max_bytes: 最大字节数限制，默认使用配置值

        Returns:
            TruncationResult: 截断结果
        """
        if not content:
            return TruncationResult(
                content="",
                is_truncated=False,
                original_lines=0,
                truncated_lines=0,
                original_bytes=0,
                truncated_bytes=0,
            )

        max_lines = max_lines or self.max_lines
        max_bytes = max_bytes or self.max_bytes

        original_bytes = len(content.encode("utf-8"))
        lines = content.split("\n")
        original_lines = len(lines)

        # 检查是否需要截断
        need_truncate = original_lines > max_lines or original_bytes > max_bytes

        if not need_truncate:
            return TruncationResult(
                content=content,
                is_truncated=False,
                original_lines=original_lines,
                truncated_lines=original_lines,
                original_bytes=original_bytes,
                truncated_bytes=original_bytes,
            )

        # 执行截断
        logger.info(
            f"Truncating output for {tool_name}: "
            f"{original_lines} lines, {original_bytes} bytes -> "
            f"max {max_lines} lines, {max_bytes} bytes"
        )

        # 先按字节截断
        truncated_content = content
        if original_bytes > max_bytes:
            # 保留前 max_bytes 字节，但要确保不切断多字节字符
            truncated_bytes = content.encode("utf-8")[:max_bytes]
            truncated_content = truncated_bytes.decode("utf-8", errors="ignore")

        # 再按行截断
        truncated_lines = truncated_content.split("\n")
        if len(truncated_lines) > max_lines:
            truncated_lines = truncated_lines[:max_lines]
            truncated_content = "\n".join(truncated_lines)

        truncated_lines_count = len(truncated_lines)
        truncated_bytes_count = len(truncated_content.encode("utf-8"))

        # 保存完整内容到文件（使用 AgentFileSystem 或传统模式）
        file_key = None
        temp_file_path = None

        try:
            if self.agent_file_system and not self.use_legacy_mode:
                file_key, temp_file_path, sandbox_path = (
                    self._save_via_agent_file_system_sync(content, tool_name)
                )
                file_path = sandbox_path or temp_file_path
                suggestion = TruncationConfig.TRUNCATION_SUGGESTION_TEMPLATE.format(
                    original_lines=original_lines,
                    original_bytes=original_bytes,
                    file_path=file_path,
                )
                dattach_tag = TruncationConfig.generate_dattach_tag(
                    file_name=f"{tool_name}_output.txt",
                    file_path=temp_file_path or "",
                    file_size=original_bytes,
                    file_key=file_key,
                    tool_name=tool_name,
                )
            else:
                temp_file_path = self._save_to_legacy_temp_file(content, tool_name)
                suggestion = (
                    TruncationConfig.TRUNCATION_SUGGESTION_TEMPLATE_NO_AFS.format(
                        original_lines=original_lines,
                        original_bytes=original_bytes,
                        file_path=temp_file_path or "unknown",
                    )
                )
                dattach_tag = TruncationConfig.generate_dattach_tag(
                    file_name=f"{tool_name}_output.txt",
                    file_path=temp_file_path or "",
                    file_size=original_bytes,
                    tool_name=tool_name,
                )
        except Exception as e:
            logger.error(f"Failed to save truncated output: {e}")
            suggestion = f"""
[输出已截断]
原始输出包含 {original_lines} 行 ({original_bytes} 字节)，已超过限制。
完整输出因保存失败而未持久化。

建议处理方式:
1. 重新执行工具操作
2. 检查文件系统状态
"""
            dattach_tag = ""

        final_content = truncated_content + suggestion + dattach_tag

        return TruncationResult(
            content=final_content,
            is_truncated=True,
            original_lines=original_lines,
            truncated_lines=truncated_lines_count,
            original_bytes=original_bytes,
            truncated_bytes=truncated_bytes_count,
            temp_file_path=temp_file_path,
            file_key=file_key,
            suggestion=suggestion,
        )

    def truncate_sync(
        self,
        content: str,
        tool_name: str = "unknown",
        max_lines: Optional[int] = None,
        max_bytes: Optional[int] = None,
    ) -> TruncationResult:
        """同步版本的截断方法"""
        return self.truncate(content, tool_name, max_lines, max_bytes)

    async def read_truncated_content_async(self, file_key: str) -> Optional[str]:
        """
        读取被截断的完整内容（异步版本）

        Args:
            file_key: 文件 key

        Returns:
            Optional[str]: 文件内容，如果读取失败返回 None
        """
        if self.agent_file_system and not self.use_legacy_mode:
            # 使用 AgentFileSystem 异步读取
            return await self.agent_file_system.read_file(file_key)
        else:
            # 传统模式：从文件路径读取
            import re

            try:
                pattern = re.compile(rf"{file_key}_\d+\.txt")
                for filename in os.listdir(self.legacy_output_dir):
                    if pattern.match(filename):
                        file_path = os.path.join(self.legacy_output_dir, filename)
                        with open(file_path, "r", encoding="utf-8") as f:
                            return f.read()
            except Exception as e:
                logger.error(f"Failed to read truncated content: {e}")
            return None

    def read_truncated_content(self, file_key: str) -> Optional[str]:
        """
        读取被截断的完整内容（同步版本）

        Args:
            file_key: 文件 key

        Returns:
            Optional[str]: 文件内容，如果读取失败返回 None
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果在异步环境中，使用run_coroutine_threadsafe
                future = asyncio.run_coroutine_threadsafe(
                    self.read_truncated_content_async(file_key), loop
                )
                return future.result(timeout=30)
            else:
                return loop.run_until_complete(
                    self.read_truncated_content_async(file_key)
                )
        except RuntimeError:
            # 没有事件循环，创建一个新的
            return asyncio.run(self.read_truncated_content_async(file_key))


class ToolOutputWrapper:
    """工具输出包装器，自动截断大输出"""

    def __init__(self, truncator: Optional[Truncator] = None):
        self.truncator = truncator or Truncator()

    def wrap_output(
        self,
        content: str,
        tool_name: str,
        **kwargs,
    ) -> str:
        """
        包装工具输出，自动截断

        Args:
            content: 原始输出内容
            tool_name: 工具名称
            **kwargs: 额外的截断参数

        Returns:
            str: 处理后的输出内容
        """
        result = self.truncator.truncate(content, tool_name, **kwargs)

        if result.is_truncated:
            logger.info(
                f"Output truncated for {tool_name}: "
                f"{result.original_lines}->{result.truncated_lines} lines, "
                f"{result.original_bytes}->{result.truncated_bytes} bytes"
            )

        return result.content


# 全局截断器实例（传统模式）
default_truncator = Truncator()


def truncate_output(
    content: str,
    tool_name: str = "unknown",
    max_lines: Optional[int] = None,
    max_bytes: Optional[int] = None,
) -> TruncationResult:
    """
    截断工具输出的便捷函数

    Args:
        content: 原始输出内容
        tool_name: 工具名称
        max_lines: 最大行数限制
        max_bytes: 最大字节数限制

    Returns:
        TruncationResult: 截断结果
    """
    return default_truncator.truncate(content, tool_name, max_lines, max_bytes)


async def create_truncator_with_fs(
    conv_id: str,
    session_id: Optional[str] = None,
    max_lines: int = TruncationConfig.DEFAULT_MAX_LINES,
    max_bytes: int = TruncationConfig.DEFAULT_MAX_BYTES,
    gpts_memory=None,
    oss_client=None,
) -> Truncator:
    """
    创建使用 AgentFileSystem 的截断器（异步版本）

    Args:
        conv_id: 会话 ID
        session_id: 会话会话ID
        max_lines: 最大行数
        max_bytes: 最大字节数
        gpts_memory: GPTS内存管理器
        oss_client: OSS客户端

    Returns:
        Truncator: 配置了 AgentFileSystem 的截断器
    """
    try:
        from derisk.agent.expand.pdca_agent.agent_file_system import AgentFileSystem

        afs = AgentFileSystem(
            conv_id=conv_id,
            session_id=session_id or conv_id,
            gpts_memory=gpts_memory,
            oss_client=oss_client,
        )

        # 同步工作区
        await afs.sync_workspace()

        return Truncator(
            max_lines=max_lines,
            max_bytes=max_bytes,
            agent_file_system=afs,
        )
    except ImportError as e:
        logger.warning(
            f"AgentFileSystem not available, falling back to legacy mode: {e}"
        )
        return Truncator(max_lines=max_lines, max_bytes=max_bytes)


def create_truncator_with_fs_sync(
    conv_id: str,
    session_id: Optional[str] = None,
    max_lines: int = TruncationConfig.DEFAULT_MAX_LINES,
    max_bytes: int = TruncationConfig.DEFAULT_MAX_BYTES,
    gpts_memory=None,
    oss_client=None,
) -> Truncator:
    """
    创建使用 AgentFileSystem 的截断器（同步版本）

    Args:
        conv_id: 会话 ID
        session_id: 会话会话ID
        max_lines: 最大行数
        max_bytes: 最大字节数
        gpts_memory: GPTS内存管理器
        oss_client: OSS客户端

    Returns:
        Truncator: 配置了 AgentFileSystem 的截断器
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果在异步环境中，创建一个task
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    create_truncator_with_fs(
                        conv_id=conv_id,
                        session_id=session_id,
                        max_lines=max_lines,
                        max_bytes=max_bytes,
                        gpts_memory=gpts_memory,
                        oss_client=oss_client,
                    ),
                )
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(
                create_truncator_with_fs(
                    conv_id=conv_id,
                    session_id=session_id,
                    max_lines=max_lines,
                    max_bytes=max_bytes,
                    gpts_memory=gpts_memory,
                    oss_client=oss_client,
                )
            )
    except RuntimeError:
        # 没有事件循环，创建一个新的
        return asyncio.run(
            create_truncator_with_fs(
                conv_id=conv_id,
                session_id=session_id,
                max_lines=max_lines,
                max_bytes=max_bytes,
                gpts_memory=gpts_memory,
                oss_client=oss_client,
            )
        )
