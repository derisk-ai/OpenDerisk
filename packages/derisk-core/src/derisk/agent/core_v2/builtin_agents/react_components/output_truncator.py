"""
输出截断器 - 截断大型工具输出

参考ReActMasterAgent的Truncation实现
"""

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Optional, Dict, Any

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
    suggestion: Optional[str] = None


class OutputTruncator:
    """
    工具输出截断器

    对于可能返回大量文本的工具输出进行截断，
    避免上下文窗口溢出。
    """

    def __init__(
        self,
        max_lines: int = 2000,
        max_bytes: int = 50000,
        enable_save: bool = True,
    ):
        self.max_lines = max_lines
        self.max_bytes = max_bytes
        self.enable_save = enable_save
        self._output_dir = None

        if enable_save:
            self._output_dir = tempfile.mkdtemp(prefix="agent_output_")
            logger.info(
                f"[Layer1:Truncation] INIT | max_lines={max_lines}, max_bytes={max_bytes}, "
                f"enable_save={enable_save}, output_dir={self._output_dir}"
            )
        else:
            logger.info(
                f"[Layer1:Truncation] INIT | max_lines={max_lines}, max_bytes={max_bytes}, "
                f"enable_save={enable_save}"
            )

    def truncate(
        self,
        content: str,
        tool_name: str = "unknown",
    ) -> TruncationResult:
        """
        截断输出内容

        Args:
            content: 原始内容
            tool_name: 工具名称

        Returns:
            TruncationResult: 截断结果
        """
        logger.info(
            f"[Layer1:Truncation] START | tool={tool_name} | "
            f"limits: max_lines={self.max_lines}, max_bytes={self.max_bytes}"
        )

        if not content:
            logger.info(
                f"[Layer1:Truncation] SKIP | tool={tool_name} | reason=empty_content"
            )
            return TruncationResult(
                content="",
                is_truncated=False,
                original_lines=0,
                truncated_lines=0,
                original_bytes=0,
                truncated_bytes=0,
            )

        lines = content.split("\n")
        original_lines = len(lines)
        original_bytes = len(content.encode("utf-8"))

        logger.debug(
            f"[Layer1:Truncation] ANALYZE | tool={tool_name} | "
            f"original_lines={original_lines}, original_bytes={original_bytes}"
        )

        if original_lines <= self.max_lines and original_bytes <= self.max_bytes:
            logger.info(
                f"[Layer1:Truncation] SKIP | tool={tool_name} | "
                f"reason=within_limits | lines={original_lines}/{self.max_lines}, bytes={original_bytes}/{self.max_bytes}"
            )
            return TruncationResult(
                content=content,
                is_truncated=False,
                original_lines=original_lines,
                truncated_lines=original_lines,
                original_bytes=original_bytes,
                truncated_bytes=original_bytes,
            )

        truncated_lines = lines[: self.max_lines]
        truncated_content = "\n".join(truncated_lines)

        logger.info(
            f"[Layer1:Truncation] TRUNCATE_START | tool={tool_name} | "
            f"trigger=exceeds_limits | lines={original_lines}/{self.max_lines}, bytes={original_bytes}/{self.max_bytes}"
        )

        if len(truncated_content.encode("utf-8")) > self.max_bytes:
            logger.debug(
                f"[Layer1:Truncation] BYTE_TRUNCATE | tool={tool_name} | "
                f"truncated_content_bytes={len(truncated_content.encode('utf-8'))} > max_bytes={self.max_bytes}"
            )
            truncated_bytes = 0
            final_lines = []

            for line in truncated_lines:
                line_bytes = len(line.encode("utf-8")) + 1
                if truncated_bytes + line_bytes > self.max_bytes:
                    break
                final_lines.append(line)
                truncated_bytes += line_bytes

            truncated_content = "\n".join(final_lines)
            truncated_lines_count = len(final_lines)
        else:
            truncated_lines_count = len(truncated_lines)
            truncated_bytes = len(truncated_content.encode("utf-8"))

        temp_file_path = None
        if self.enable_save:
            temp_file_path = self._save_full_output(content, tool_name)
            logger.info(
                f"[Layer1:Truncation] SAVED_FULL | tool={tool_name} | temp_file={temp_file_path}"
            )

        suggestion = self._generate_suggestion(
            original_lines=original_lines,
            original_bytes=original_bytes,
            temp_file_path=temp_file_path,
            tool_name=tool_name,
        )

        compression_ratio = (
            truncated_bytes / original_bytes if original_bytes > 0 else 0
        )
        logger.info(
            f"[Layer1:Truncation] COMPLETE | tool={tool_name} | "
            f"original={original_lines}L/{original_bytes}B -> truncated={truncated_lines_count}L/{truncated_bytes}B | "
            f"compression_ratio={compression_ratio:.1%} | saved={original_bytes - truncated_bytes}B"
        )

        # 组合截断内容和 suggestion（类似 Truncator 的做法）
        final_content = truncated_content + suggestion

        return TruncationResult(
            content=final_content,
            is_truncated=True,
            original_lines=original_lines,
            truncated_lines=truncated_lines_count,
            original_bytes=original_bytes,
            truncated_bytes=truncated_bytes,
            temp_file_path=temp_file_path,
            suggestion=suggestion,
        )

    def _save_full_output(self, content: str, tool_name: str) -> Optional[str]:
        try:
            if not self._output_dir:
                logger.warning(
                    f"[Layer1:Truncation] SAVE_SKIP | tool={tool_name} | reason=no_output_dir"
                )
                return None

            content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
            filename = f"{tool_name}_{content_hash}.txt"
            file_path = os.path.join(self._output_dir, filename)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info(
                f"[Layer1:Truncation] SAVE_SUCCESS | tool={tool_name} | "
                f"file={file_path} | hash={content_hash} | size={len(content)}B"
            )
            return file_path

        except Exception as e:
            logger.error(
                f"[Layer1:Truncation] SAVE_ERROR | tool={tool_name} | error={e}"
            )
            return None

    def _generate_suggestion(
        self,
        original_lines: int,
        original_bytes: int,
        temp_file_path: Optional[str],
        tool_name: str = "unknown",
    ) -> str:
        """生成建议信息，包含 d-attach 组件"""

        # 基础截断提示
        message = f"\n[输出已截断]\n"
        message += f"原始输出: {original_lines}行, {original_bytes}字节\n"

        if temp_file_path:
            message += f"完整输出已保存至: {temp_file_path}\n"
            message += f"\n**使用 read 工具读取完整内容:**\n"
            message += f'{"path": "{temp_file_path}"}\n'
            message += f"\n如需分页读取（内容较大时）:\n"
            message += f'{"path": "{temp_file_path}", "offset": 1, "limit": 500"}\n'

            # 生成 d-attach 组件标签
            dattach_tag = self._generate_dattach_tag(
                file_name=f"{tool_name}_output.txt",
                file_path=temp_file_path,
                file_size=original_bytes,
                tool_name=tool_name,
            )
            message += dattach_tag

        return message

    def _generate_dattach_tag(
        self,
        file_name: str,
        file_path: str,
        file_size: int,
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

            content = json.dumps([attach_data], ensure_ascii=False)
            return f"\n\n```d-attach\n{content}\n```\n"
        except Exception as e:
            logger.warning(f"[OutputTruncator] Failed to generate d-attach tag: {e}")
            return f"\n\n完整输出文件: {file_path}"

    def cleanup(self):
        logger.info(
            f"[Layer1:Truncation] CLEANUP_START | output_dir={self._output_dir}"
        )
        if self._output_dir and os.path.exists(self._output_dir):
            try:
                import shutil

                shutil.rmtree(self._output_dir)
                logger.info(
                    f"[Layer1:Truncation] CLEANUP_SUCCESS | output_dir={self._output_dir}"
                )
            except Exception as e:
                logger.error(
                    f"[Layer1:Truncation] CLEANUP_ERROR | output_dir={self._output_dir} | error={e}"
                )
