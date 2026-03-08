"""
ShellExecTool - 沙箱内 Shell 命令执行工具

在沙箱工作空间中执行受限 Bash 命令
"""

from typing import Dict, Any, Optional, List
import posixpath
import re
import shlex
import logging

from .base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel, ToolEnvironment, ToolSource
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)

# 默认超时时间
_DEFAULT_TIMEOUT: int = 60

# 允许的命令
_ALLOWED_COMMANDS = {
    "cat",
    "ls",
    "pwd",
    "echo",
    "head",
    "tail",
    "wc",
    "which",
    "nl",
    "grep",
    "find",
    "rg",
    "git",
    "sed",
    "pip3",
    "python3",
}

# 禁止的符号
_FORBIDDEN_SYMBOLS = {""}

# find 命令禁止的参数
_FIND_FORBIDDEN_ARGS = {
    "-delete",
    "-exec",
    "-execdir",
    "-fls",
    "-fprint",
    "-fprint0",
    "-fprintf",
    "-ok",
    "-okdir",
}
_FIND_FORBIDDEN_PREFIXES = ("-exec", "-ok")

# ripgrep 禁止的选项
_RG_FORBIDDEN_ARGS = {
    "--search-zip",
    "--pre",
    "--pre-glob",
    "--hostname-bin",
}

# Git 允许的子命令（只读）
_GIT_ALLOWED_SUBCMDS = {"status", "log", "diff", "show", "branch"}
_GIT_FORBIDDEN_ARGS = {
    "-d",
    "-D",
    "-m",
    "-M",
    "--delete",
    "--move",
    "--rename",
    "--force",
    "-f",
}

# 输出限制
_MAX_BYTES = 16 * 1024  # 16KB
_MAX_LINES_DEFAULT = 500
_MAX_LINES_FILE_CHUNK = 500

# ANSI 转义序列正则
_ANSI_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


_PROMPT = """在沙箱工作空间中执行单条 Bash 命令。该工具属于执行层，同一轮回复内仅允许调用一次（一次回复只能使用一次 shell_exec），且不与依赖其结果的其他操作并发调用；若命令会写入状态，请在确认命令成功后，再发起后续读取/写入。

使用指南:
- 【最高优先级】同一轮回复内仅允许调用一次该工具（shell_exec），严禁并发或重复调用。
- 工作目录默认 /home/ubuntu；优先使用绝对路径，所有相对路径均以 /home/ubuntu 为基准。
- 沙箱已配置 sudo 免密，但避免任何交互式确认；对可能需要确认的命令加上 -y/-f 等非交互标志。
- 输出限制：最多 10KB 或 256 行，超出部分会被截断；大量输出请重定向到文件或通过管道进行过滤。
- 可以用 '&&' 串联子命令来减少多次调用并清晰处理错误；适当使用管道 '|' 在命令间传递输出。
- 复杂脚本请先写入文件再执行，禁止直接使用 "python -c"、"bash -c" 执行长代码片段。
- 对长时间运行的服务（如 Web 服务器）必须设置5s超时并且后台运行，避免无意义等待。
- 禁止访问工作空间之外的路径（特别是 ~、.. 或绝对路径越界）。"""


def _strip_ansi_sequences(text: str) -> str:
    """Remove ANSI escape sequences from shell output."""
    if not text:
        return text
    cleaned = _ANSI_PATTERN.sub("", text)
    cleaned = cleaned.replace("\x1b", "")
    cleaned = cleaned.replace("\r", "")
    return cleaned


def _tokenize_command(command: str) -> List[str]:
    """Split the shell command into arguments."""
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"命令解析失败: {exc}") from exc
    if not tokens:
        raise ValueError("command 不能为空")
    return tokens


def _validate_tokens(tokens: List[str], sandbox_work_dir: str) -> None:
    """Ensure the command and its arguments stay within the read-only constraints."""
    binary = tokens[0]
    idx = 1

    while idx < len(tokens):
        token = tokens[idx]
        if token in _FORBIDDEN_SYMBOLS:
            raise PermissionError(
                "命令包含被禁止的符号或重定向，请拆分成单独的只读命令执行"
            )

        if binary == "find":
            if token in _FIND_FORBIDDEN_ARGS or token.startswith(
                _FIND_FORBIDDEN_PREFIXES
            ):
                raise PermissionError(
                    "find 命令禁止使用 -exec/-ok/-delete 等执行或写入参数"
                )

        if binary == "rg":
            if token in _RG_FORBIDDEN_ARGS:
                raise PermissionError(
                    "rg 禁止使用 --search-zip/--pre 等可能执行外部命令或扩大搜索面的参数"
                )

        if binary == "git":
            if idx == 1:
                sub = token
                if sub not in _GIT_ALLOWED_SUBCMDS:
                    allowed_sub = ", ".join(sorted(_GIT_ALLOWED_SUBCMDS))
                    raise PermissionError(f"git 仅允许只读子命令: {allowed_sub}")
            if token in _GIT_FORBIDDEN_ARGS:
                raise PermissionError(
                    "git 命令包含危险选项（删除/重命名/强制），已禁止"
                )

        if token.startswith("-"):
            idx += 1
            continue

        if token.startswith("~"):
            raise PermissionError("禁止访问 home 目录")

        if any(part == ".." for part in token.split("/")):
            raise PermissionError("命令参数尝试跳出工作空间目录，已被禁止")

        if token.startswith("/"):
            combined = token
        else:
            combined = posixpath.join(sandbox_work_dir, token)
        normalized = posixpath.normpath(combined)
        base_norm = posixpath.normpath(sandbox_work_dir.rstrip("/")) or "/"
        prefix = "" if base_norm == "/" else f"{base_norm}/"
        if normalized != base_norm and not normalized.startswith(prefix):
            raise PermissionError("命令参数解析后超出了沙箱工作目录，已被禁止")

        idx += 1

    if binary == "sed":
        if len(tokens) != 4:
            raise PermissionError("仅允许只读 sed：`sed -n {N|M,N}p FILE` 格式")
        if tokens[1] != "-n":
            raise PermissionError("sed 仅允许使用 -n，打印指定行范围")
        expr = tokens[2]
        if not re.fullmatch(r"\d+p|\d+,\d+p", expr):
            raise PermissionError("sed 仅允许 {N|M,N}p 的打印表达式")


def _truncate_text(text: str, line_cap: int, byte_cap: int) -> str:
    """Truncate text by lines then by bytes."""
    if not text:
        return text
    lines = text.splitlines(True)
    if len(lines) > line_cap:
        lines = lines[:line_cap]
        text = "".join(lines)
    else:
        text = "".join(lines)
    b = text.encode("utf-8", errors="replace")
    if len(b) <= byte_cap:
        return text
    truncated = b[:byte_cap]
    try:
        safe = truncated.decode("utf-8", errors="ignore")
    except Exception:
        safe = text[:0]
    return safe


def _is_file_read_command(tokens: List[str]) -> bool:
    """Heuristically decide if command is likely printing file content."""
    binary = tokens[0]
    if binary in {"cat", "nl", "head", "tail", "grep", "rg", "sed"}:
        return True
    return False


def _format_shell_exec_response(
    command: str, exit_code: Optional[int], stdout: str, stderr: str
) -> str:
    """Format shell output for display."""
    code_repr = "unknown" if exit_code is None else str(exit_code)
    if exit_code is None:
        status = "⚠️ 未知"
    elif exit_code == 0:
        status = "✅ 成功"
    else:
        status = "⚠️ 失败"

    lines = [f"命令: {command}", f"结果: {status} (退出码 {code_repr})"]

    if stdout:
        lines.extend(["", "📤 标准输出:", stdout.rstrip("\n")])
    if stderr:
        lines.extend(["", "⚠️ 标准错误:", stderr.rstrip("\n")])

    return "\n".join(lines).rstrip()


class ShellExecTool(SandboxToolBase):
    """沙箱内 Shell 命令执行工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="shell_exec",
            display_name="Shell Exec",
            description=_PROMPT,
            category=ToolCategory.SANDBOX,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=120,
            environment=ToolEnvironment.SANDBOX,
            tags=["shell", "command", "execute", "sandbox"],
            author="tuyang.yhj",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 Bash 命令（单条）。若包含多步操作，请使用 '&&' 串联；避免交互式命令。",
                },
                "timeout": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 10,
                    "description": "超时秒数（正整数）。默认 10；命令若可能长时间运行，请适当上调或后台执行。",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        command = args["command"]
        timeout = args.get("timeout", _DEFAULT_TIMEOUT)

        # 检查沙箱可用性
        client = self._get_sandbox_client(context)
        if client is None:
            return ToolResult.fail(
                error="错误: 当前任务未初始化沙箱环境，无法执行命令",
                tool_name=self.name,
            )

        if timeout <= 0:
            return ToolResult.fail(
                error="timeout 必须为正整数",
                tool_name=self.name,
            )

        try:
            tokens = _tokenize_command(command)
            # _validate_tokens(tokens, client.work_dir)
        except (ValueError, PermissionError) as e:
            return ToolResult.fail(error=str(e), tool_name=self.name)

        try:
            result = await client.shell.exec_command(
                command=command, timeout=float(timeout), work_dir=client.work_dir
            )
        except Exception as exc:
            return ToolResult.ok(
                output=_format_shell_exec_response(
                    command, -1, "", f"命令执行失败: {exc}"
                ),
                tool_name=self.name,
            )

        # 获取输出
        from derisk.sandbox.sandbox_utils import collect_shell_output

        stdout = collect_shell_output(result)
        stdout = _strip_ansi_sequences(stdout)
        line_cap = (
            _MAX_LINES_FILE_CHUNK
            if _is_file_read_command(tokens)
            else _MAX_LINES_DEFAULT
        )
        stdout = _truncate_text(stdout, line_cap, _MAX_BYTES)

        status = getattr(result, "status", None)
        exit_code = getattr(result, "exit_code", None)

        if status != "completed":
            output = _format_shell_exec_response(
                command,
                exit_code if exit_code is not None else -1,
                "",
                stdout or f"命令执行失败，状态: {status}",
            )
            return ToolResult.ok(output=output, tool_name=self.name)

        output = _format_shell_exec_response(
            command, exit_code if exit_code is not None else 0, stdout, ""
        )
        return ToolResult.ok(output=output, tool_name=self.name)
