"""
输出截断器 - 截断大型工具输出

参考ReActMasterAgent的Truncation实现
"""

import hashlib
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
        """
        初始化截断器
        
        Args:
            max_lines: 最大行数限制
            max_bytes: 最大字节数限制
            enable_save: 是否保存完整输出到临时文件
        """
        self.max_lines = max_lines
        self.max_bytes = max_bytes
        self.enable_save = enable_save
        self._output_dir = None
        
        if enable_save:
            self._output_dir = tempfile.mkdtemp(prefix="agent_output_")
            logger.info(f"[Truncator] 输出目录: {self._output_dir}")
    
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
        if not content:
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
        
        if original_lines <= self.max_lines and original_bytes <= self.max_bytes:
            return TruncationResult(
                content=content,
                is_truncated=False,
                original_lines=original_lines,
                truncated_lines=original_lines,
                original_bytes=original_bytes,
                truncated_bytes=original_bytes,
            )
        
        truncated_lines = lines[:self.max_lines]
        truncated_content = "\n".join(truncated_lines)
        
        if len(truncated_content.encode("utf-8")) > self.max_bytes:
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
        
        suggestion = self._generate_suggestion(
            original_lines=original_lines,
            original_bytes=original_bytes,
            temp_file_path=temp_file_path,
        )
        
        logger.info(
            f"[Truncator] 截断输出: {original_lines}行 -> {truncated_lines_count}行, "
            f"{original_bytes}字节 -> {truncated_bytes}字节"
        )
        
        return TruncationResult(
            content=truncated_content,
            is_truncated=True,
            original_lines=original_lines,
            truncated_lines=truncated_lines_count,
            original_bytes=original_bytes,
            truncated_bytes=truncated_bytes,
            temp_file_path=temp_file_path,
            suggestion=suggestion,
        )
    
    def _save_full_output(self, content: str, tool_name: str) -> Optional[str]:
        """保存完整输出到临时文件"""
        try:
            if not self._output_dir:
                return None
            
            content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
            filename = f"{tool_name}_{content_hash}.txt"
            file_path = os.path.join(self._output_dir, filename)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            logger.info(f"[Truncator] 保存完整输出: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"[Truncator] 保存失败: {e}")
            return None
    
    def _generate_suggestion(
        self,
        original_lines: int,
        original_bytes: int,
        temp_file_path: Optional[str],
    ) -> str:
        """生成建议信息"""
        message = f"\n[输出已截断]\n"
        message += f"原始输出: {original_lines}行, {original_bytes}字节\n"
        
        if temp_file_path:
            message += f"完整输出已保存: {temp_file_path}\n"
        
        return message
    
    def cleanup(self):
        """清理临时文件"""
        if self._output_dir and os.path.exists(self._output_dir):
            try:
                import shutil
                shutil.rmtree(self._output_dir)
                logger.info(f"[Truncator] 清理输出目录: {self._output_dir}")
            except Exception as e:
                logger.error(f"[Truncator] 清理失败: {e}")