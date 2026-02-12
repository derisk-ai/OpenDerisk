"""Execute guard-railed shell commands inside the sandbox workspace."""
import logging
import posixpath
import re
import shlex
from typing import List, Optional

from derisk.agent.core.sandbox.sandbox_tool_registry import sandbox_tool
from derisk.agent.core.system_tool_registry import system_tool
from derisk.sandbox.base import SandboxBase
from derisk.sandbox.sandbox_utils import collect_shell_output



logger = logging.getLogger(__name__)

_PROMPT = """
{
  "name": "shell_exec",
  "description": "在沙箱工作空间中执行单条 Bash 命令。该工具属于执行层，同一轮回复内仅允许调用一次（一次回复只能使用一次 shell_exec），且不与依赖其结果的其他操作并发调用；若命令会写入状态，请在确认命令成功后，再发起后续读取/写入。",
  "usage_guidelines": [
    "【最高优先级】同一轮回复内仅允许调用一次该工具（shell_exec），严禁并发或重复调用。",
    "工作目录默认 /home/ubuntu；优先使用绝对路径，所有相对路径均以 /home/ubuntu 为基准。",
    "沙箱已配置 sudo 免密，但避免任何交互式确认；对可能需要确认的命令加上 -y/-f 等非交互标志。",
    "输出限制：最多 10KB 或 256 行，超出部分会被截断；大量输出请重定向到文件或通过管道进行过滤。",
    "可以用 '&&' 串联子命令来减少多次调用并清晰处理错误；适当使用管道 '|' 在命令间传递输出。",
    "复杂脚本请先写入文件再执行，禁止直接使用 \"python -c\"、\"bash -c\" 执行长代码片段。",
    "对长时间运行的服务（如 Web 服务器）必须设置5s超时并且后台运行，避免无意义等待。",
    "禁止访问工作空间之外的路径（特别是 ~、.. 或绝对路径越界）。"
  ],
}
"""

_DEFAULT_TIMEOUT: int = 60
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
_FORBIDDEN_SYMBOLS = {""}
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

# ripgrep forbidden options
_RG_FORBIDDEN_ARGS = {
    "--search-zip",
    "--pre",
    "--pre-glob",
    "--hostname-bin",  # 按需禁用（即使不是标准参数，作为保护项）
}

# Git safe subcommands (read-only)
_GIT_ALLOWED_SUBCMDS = {"status", "log", "diff", "show", "branch"}
_GIT_FORBIDDEN_ARGS = {"-d", "-D", "-m", "-M", "--delete", "--move", "--rename", "--force", "-f"}

_MAX_BYTES = 16 * 1024  # 10KB
_MAX_LINES_DEFAULT = 500
_MAX_LINES_FILE_CHUNK = 500
_ANSI_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _format_shell_exec_response(command: str, exit_code: Optional[int], stdout: str, stderr: str) -> str:
    """将命令输出包装为更易理解的文本描述，便于前端展示。"""
    code_repr = "unknown" if exit_code is None else str(exit_code)
    if exit_code is None:
        status = "⚠️ 未知"
    elif exit_code == 0:
        status = "✅ 成功"
    else:
        status = "⚠️ 失败"

    lines = [
        f"命令: {command}",
        f"结果: {status} (退出码 {code_repr})"
    ]

    if stdout:
        lines.extend(["", "📤 标准输出:", stdout.rstrip("\n")])
    if stderr:
        lines.extend(["", "⚠️ 标准错误:", stderr.rstrip("\n")])

    return "\n".join(lines).rstrip()


def _strip_ansi_sequences(text: str) -> str:
    """Remove ANSI escape sequences (e.g. colored prompts) from shell output."""
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
    # if binary not in _ALLOWED_COMMANDS:
    #     allowed = ", ".join(sorted(_ALLOWED_COMMANDS))
    #     raise PermissionError(
    #         f"命令 `{binary}` 不受支持，仅允许执行文件浏览相关命令: {allowed}"
    #     )

    idx = 1
    while idx < len(tokens):
        token = tokens[idx]
        if token in _FORBIDDEN_SYMBOLS:
            raise PermissionError("命令包含被禁止的符号或重定向，请拆分成单独的只读命令执行")

        if binary == "find":
            if token in _FIND_FORBIDDEN_ARGS or token.startswith(_FIND_FORBIDDEN_PREFIXES):
                raise PermissionError("find 命令禁止使用 -exec/-ok/-delete 等执行或写入参数")

        if binary == "rg":
            if token in _RG_FORBIDDEN_ARGS:
                raise PermissionError("rg 禁止使用 --search-zip/--pre 等可能执行外部命令或扩大搜索面的参数")

        if binary == "git":
            # 仅允许固定只读子命令
            if idx == 1:
                sub = token
                if sub not in _GIT_ALLOWED_SUBCMDS:
                    allowed_sub = ", ".join(sorted(_GIT_ALLOWED_SUBCMDS))
                    raise PermissionError(f"git 仅允许只读子命令: {allowed_sub}")
            # 全程禁止危险参数
            if token in _GIT_FORBIDDEN_ARGS:
                raise PermissionError("git 命令包含危险选项（删除/重命名/强制），已禁止")

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
        # 仅允许：sed -n {N|M,N}p FILE
        if len(tokens) not in (4,):
            raise PermissionError("仅允许只读 sed：`sed -n {N|M,N}p FILE` 格式")
        if tokens[1] != "-n":
            raise PermissionError("sed 仅允许使用 -n，打印指定行范围")
        expr = tokens[2]
        # 支持 10p 或 5,20p 两种
        import re as _re
        if not _re.fullmatch(r"\d+p|\d+,\d+p", expr):
            raise PermissionError("sed 仅允许 {N|M,N}p 的打印表达式")
        # 第 4 个参数必须是文件路径（已在上面路径校验）


def _truncate_text(text: str, line_cap: int, byte_cap: int) -> str:
    """Truncate text by lines then by bytes. Guarantees not exceeding caps."""
    if not text:
        return text
    lines = text.splitlines(True)  # keepends
    if len(lines) > line_cap:
        lines = lines[:line_cap]
        text = "".join(lines)
    else:
        text = "".join(lines)
    # bytes cap
    b = text.encode("utf-8", errors="replace")
    if len(b) <= byte_cap:
        return text
    # truncate by bytes safely on utf-8 boundary
    truncated = b[:byte_cap]
    try:
        safe = truncated.decode("utf-8", errors="ignore")
    except Exception:
        safe = text[:0]
    return safe


def _is_file_read_command(tokens: List[str]) -> bool:
    """Heuristically decide if command is likely printing file content."""
    binary = tokens[0]
    if binary in {"cat", "nl", "head", "tail", "grep", "rg"}:
        return True
    if binary == "sed":
        return True
    return False


@sandbox_tool(
    name="shell_exec",
    description=_PROMPT,
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 Bash 命令（单条）。若包含多步操作，请使用 '&&' 串联；避免交互式命令，注意：每次命令执行前会自动执行 `cd {your workdir}`, 因此在必要时请使用绝对路径以确保文件操作的正确性。"
            },
            "timeout": {
                "type": "integer",
                "minimum": 1,
                "default": 10,
                "description": "超时秒数（正整数）。默认 10；命令若可能长时间运行，请适当上调或后台执行。"
            }
        },
        "required": ["command"]
    },
    owner="tuyang.yhj"
)
async def execute_workspace_exec(client: SandboxBase, command: str, timeout: int = _DEFAULT_TIMEOUT, ) -> str:
    """
    在技能工作空间内执行受限只读 shell 命令，用于浏览目录、阅读技能说明与检索文本。

    返回经过整理的文本描述，包含命令、返回码以及标准输出/错误。
    """
    if timeout <= 0:
        raise ValueError("timeout 必须为正整数")

    if client is None:
        return _format_shell_exec_response(
            command,
            -1,
            "",
            "错误: 当前任务未初始化沙箱环境，无法执行命令"
        )

    tokens = _tokenize_command(command)
    # _validate_tokens(tokens, client.work_dir)

    try:
        result = await client.shell.exec_command(
            command=command,
            timeout=float(timeout),
            work_dir=client.work_dir
        )
    except Exception as exc:
        return _format_shell_exec_response(command, -1, "", f"命令执行失败: {exc}")

    stdout = collect_shell_output(result)
    stdout = _strip_ansi_sequences(stdout)
    line_cap = _MAX_LINES_FILE_CHUNK if _is_file_read_command(tokens) else _MAX_LINES_DEFAULT
    stdout = _truncate_text(stdout, line_cap, _MAX_BYTES)

    status = getattr(result, "status", None)
    exit_code = getattr(result, "exit_code", None)
    ## 暂时关闭这个逻辑.
    #
    # if status == "completed":
    #     # 同步上传文件到 OSS
    #     try:
    #         logger.info("[shell_exec] 命令成功，开始同步沙箱产物")
    #         await sync_shell_artifacts(client)
    #         logger.info("[shell_exec] ✅ 沙箱产物同步完成")
    #     except Exception as sync_exc:  # noqa: BLE001
    #         logger.warning(
    #             "[shell_exec] ⚠️  同步沙箱产物失败: %s",
    #             sync_exc,
    #             exc_info=True
    #         )

    if status != "completed":
        return _format_shell_exec_response(
            command,
            exit_code if exit_code is not None else -1,
            "",
            stdout or f"命令执行失败，状态: {status}"
        )

    return _format_shell_exec_response(
        command,
        exit_code if exit_code is not None else 0,
        stdout,
        ""
    )


