import json
import posixpath
import re
import shlex
import textwrap
from typing import Dict, List, Optional, Tuple, Union

from derisk.agent.core.sandbox.sandbox_tool_registry import sandbox_tool
from derisk.agent.core.system_tool_registry import system_tool
from derisk.sandbox.base import SandboxBase
from derisk.sandbox.sandbox_utils import (
    collect_shell_output,
    normalize_sandbox_path,
    detect_path_kind,
)

_VIEW_PROMPT = """
{
  "name": "view",
  "description": "沙箱文件系统交互接口。用于列出目录结构、读取文件内容或渲染图片资源。",
  "instructions": [
    "SKILL.md 加载互斥锁：当访问技能目录路径时，单次交互严格禁止读取超过 1 个 markdown 文件。必须遵循"读取单项技能 -> 执行对应逻辑"的原子化流程，防止领域知识污染。",
    "大文件熔断保护：对于未知大小的业务文件（日志、数据、代码），禁止在无 view_range 限制下全量读取。必须先读取摘要或特定片段。",
    "只读安全边界：此工具仅用于被动获取信息，严禁产生任何副作用（如创建、修改文件）。"
  ],
  "recommended_usage": [
    "侦查先行：优先对目录使用 view 以建立文件树心理模型，而不是盲目猜测文件路径。",
    "切片分析：利用 view_range 模拟 head (如 [1, 50]) 或 tail (如 [1000, -1]) 操作，以最小 Token 消耗定位关键信息。",
    "按需扩容：仅在当前上下文无法支撑决策时，才通过 view 获取新的文件内容。"
  ],
}
"""
_MAX_FILE_CHARS = 16000
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_RANGE_SPLIT_RE = re.compile(r"[\s,\-~:]+")


def _parse_view_range(view_range) -> Optional[Union[Tuple[int, int], str]]:
    """
    Parse view_range with tolerance for common agent mistakes.

    Returns:
        None: if view_range is None or empty
        Tuple[int, int]: parsed (start, end)
        str: error message if parsing fails
    """
    if view_range is None:
        return None

    # Case 1: already a list/tuple like [1, 100] or ["1", "100"]
    if isinstance(view_range, (list, tuple)):
        if len(view_range) == 0:
            return None
        if len(view_range) != 2:
            return "错误: view_range 必须是长度为2的数组 [start_line, end_line]"
        try:
            start = int(view_range[0])
            end = int(view_range[1])
            return (start, end)
        except (ValueError, TypeError):
            return f"错误: view_range 元素必须是整数，收到: {view_range}"

    # Case 2: string like "[1, 100]", "1-100", "1,100", "1:100", "1 100"
    if isinstance(view_range, str):
        view_range = view_range.strip()
        if not view_range:
            return None
        # Try JSON parse first for "[1, 100]" or "[1,100]"
        if view_range.startswith("["):
            try:
                parsed = json.loads(view_range)
                if isinstance(parsed, list) and len(parsed) == 2:
                    return (int(parsed[0]), int(parsed[1]))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        # Fallback: split by common delimiters
        parts = _RANGE_SPLIT_RE.split(view_range)
        parts = [p for p in parts if p]
        if len(parts) != 2:
            return (
                f"错误: 无法解析 view_range 字符串: {view_range}，期望格式如 [1, 100]"
            )
        try:
            start = int(parts[0])
            end = int(parts[1])
            return (start, end)
        except ValueError:
            return f"错误: view_range 元素必须是整数，收到: {view_range}"

    # Case 3: single int (treat as start, read to end)
    if isinstance(view_range, int):
        return (view_range, -1)

    return f"错误: view_range 类型不支持: {type(view_range).__name__}"


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_PROMPT_LINE_RE = re.compile(r"^[\w.-]+@[\w.-]+:[^\n]*\$\s?.*$")


def _format_size(size: int) -> str:
    """格式化文件大小"""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}K"
    else:
        return f"{size / (1024 * 1024):.1f}M"


def _format_text_content(
    content: str, view_range: Optional[Tuple[int, int]] = None
) -> str:
    """格式化文本内容，处理范围与长度限制。"""
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)

    if view_range:
        start_line, end_line = view_range
        start_idx = max(0, start_line - 1)
        end_idx = total_lines if end_line == -1 else min(total_lines, end_line)
        if start_idx >= total_lines:
            return f"[错误: 起始行 {start_line} 超出文件范围 (总行数: {total_lines})]"
        lines = lines[start_idx:end_idx]

    content_joined = "".join(lines)

    if len(content_joined) > _MAX_FILE_CHARS:
        return (
            f"[文件内容过长: {len(content_joined)} 字符，超出限制 {_MAX_FILE_CHARS} 字符，共 {total_lines} 行]\n"
            f"建议：\n"
            f"  1. 使用 view_range 参数分段读取，如 [1, 200] 或 [500, -1]\n"
            f"  2. 使用 grep 工具搜索关键信息"
        )

    return content_joined


def _clean_terminal_output(result) -> str:
    """提取并净化终端输出，去除 ANSI 控制符与提示行。"""
    raw = collect_shell_output(result)
    if not raw:
        return ""
    text = raw.replace("\r", "")
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = text.replace("\x1b", "")
    lines = []
    for line in text.splitlines():
        if not line:
            continue
        if _PROMPT_LINE_RE.match(line.strip()):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _extract_first_json_object(text: str) -> Optional[dict]:
    """从清理后的终端输出中提取首个完整 JSON 对象。"""
    if not text:
        return None
    decoder = json.JSONDecoder()
    idx = 0
    length = len(text)
    while idx < length:
        ch = text[idx]
        if ch != "{":
            idx += 1
            continue
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        return obj
    return None


async def _render_directory_listing(client, abs_path: str) -> str:
    script = textwrap.dedent(
        """
        import json
        import os
        import sys

        base = sys.argv[1]
        max_depth = 2

        def allowed(name: str) -> bool:
            return not name.startswith('.') and name != 'node_modules'

        def dir_size(path: str) -> int:
            total = 0
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if allowed(d)]
                for fname in files:
                    if fname.startswith('.'):
                        continue
                    try:
                        total += os.path.getsize(os.path.join(root, fname))
                    except OSError:
                        pass
            return total

        entries = []

        def walk(path: str, depth: int, rel: str) -> None:
            try:
                names = sorted(os.listdir(path))
            except OSError as exc:
                entries.append({"path": rel or path, "error": str(exc)})
                return

            for name in names:
                if not allowed(name):
                    continue
                full = os.path.join(path, name)
                rel_path = f"{rel}/{name}" if rel else name
                if os.path.isdir(full):
                    size = dir_size(full)
                    entries.append({"path": rel_path, "is_dir": True, "size": size})
                    if depth + 1 < max_depth:
                        walk(full, depth + 1, rel_path)
                else:
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = -1
                    entries.append({"path": rel_path, "is_dir": False, "size": size})

        walk(base, 0, "")
        root_size = dir_size(base)
        print(json.dumps({"entries": entries, "root_size": root_size}, ensure_ascii=False))
        """
    ).strip()

    command = f"python3 - <<'PY' {shlex.quote(abs_path)}\n{script}\nPY"
    result = await client.shell.exec_command(
        command=command, work_dir=client.work_dir, timeout=60.0
    )
    if getattr(result, "status", None) != "completed":
        return f"[错误: 目录读取失败，状态: {getattr(result, 'status', None)}]"

    cleaned = _clean_terminal_output(result)
    data = _extract_first_json_object(cleaned)
    if data is None:
        return f"[错误: 目录读取失败，返回值无法解析]\n{cleaned}"

    entries = data.get("entries", [])
    root_size = data.get("root_size", 0)
    lines = [
        f"Here are the files and directories up to 2 levels deep in {abs_path}, excluding hidden items and node_modules:",
        f"{_format_size(root_size):>8}    {abs_path}",
    ]

    for entry in entries:
        if "error" in entry:
            lines.append(f"{'[denied]':>8}    {entry['path']}: {entry['error']}")
            continue
        size = entry.get("size", -1)
        size_str = _format_size(size) if isinstance(size, int) and size >= 0 else "???"
        rel_path = entry.get("path", "")
        if not rel_path:
            full_path = abs_path
        else:
            base_prefix = abs_path if abs_path == "/" else abs_path.rstrip("/")
            full_path = posixpath.join(base_prefix, rel_path)
        lines.append(f"{size_str:>8}    {full_path}")

    return "\n".join(lines)


async def _read_text_content(client, abs_path: str) -> str:
    try:
        file_info = await client.file.read(abs_path)
    except Exception as exc:
        return f"[错误: 读取文件失败 - {exc}]"
    content = getattr(file_info, "content", None)
    if content is None:
        return "[错误: 文件内容为空或无法解析]"
    return content


async def _read_image_base64(client, abs_path: str) -> Dict[str, Union[str, int]]:
    script = textwrap.dedent(
        """
        import base64
        import json
        import os
        import sys

        path = sys.argv[1]
        try:
            with open(path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')
            size = os.path.getsize(path)
            print(json.dumps({'data': data, 'size': size}, ensure_ascii=False))
        except Exception as exc:
            print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        """
    ).strip()

    command = f"python3 - <<'PY' {shlex.quote(abs_path)}\n{script}\nPY"
    result = await client.shell.exec_command(
        command=command, work_dir=client.work_dir, timeout=60.0
    )
    if getattr(result, "status", None) != "completed":
        return {
            "type": "error",
            "message": f"读取图片失败: {getattr(result, 'status', None)}",
        }

    cleaned = _clean_terminal_output(result)
    data = _extract_first_json_object(cleaned)
    if data is None:
        return {
            "type": "error",
            "message": f"读取图片失败: 返回内容无法解析\n{cleaned}",
        }

    if "error" in data:
        return {"type": "error", "message": f"读取图片失败: {data['error']}"}

    return {
        "type": "image",
        "data": data.get("data", ""),
        "size": data.get("size", 0),
    }


@sandbox_tool(
    name="view",
    description=_VIEW_PROMPT,
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目标绝对路径。支持目录（显示列表）或文件（显示内容）。",
            },
            "view_range": {
                "anyOf": [
                    {
                        "maxItems": 2,
                        "minItems": 2,
                        "prefixItems": [{"type": "integer"}, {"type": "integer"}],
                        "type": "array",
                    },
                    {"type": "null"},
                ],
                "default": None,
                "description": "行号范围 [start, end]（从1开始）。\\n- 强制场景：读取 >100 行的代码或日志时必填。\\n- 特殊值：使用 -1 代表文件末尾（例如 [50, -1] 读取从第50行到最后）。",
            },
        },
        "required": ["path"],
    },
    owner="tuyang.yhj",
)
async def execute_view(
    client: SandboxBase, path: str, view_range: Optional[List[int]] = None
) -> str:
    """
    查看文件或目录内容。

    Args:
        path: 文件或目录的绝对路径
        view_range: 可选的行范围 [start_line, end_line]，仅用于文本文件

    Returns:
        文件或目录内容的文本表示
    """
    if client is None:
        return "错误: 当前任务未初始化沙箱环境，无法查看文件"

    try:
        sandbox_path = normalize_sandbox_path(client, path)
    except ValueError as exc:
        return f"错误: {exc}"

    path_kind = await detect_path_kind(client, sandbox_path)
    if path_kind == "none":
        return f"错误: 路径不存在: {sandbox_path}"

    if path_kind == "dir":
        return await _render_directory_listing(client, sandbox_path)

    suffix = posixpath.splitext(sandbox_path)[1].lower()
    if suffix in _IMAGE_EXTENSIONS:
        img_result = await _read_image_base64(client, sandbox_path)
        if img_result.get("type") == "error":
            return str(img_result.get("message", "读取图片失败"))
        img_size = img_result.get("size", 0)
        size_mb = float(img_size) / (1024 * 1024) if isinstance(img_size, int) else 0.0
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(suffix, "image/jpeg")
        header = [
            f"Image file: {sandbox_path}",
            f"Type: {mime_type}",
            f"Size: {size_mb:.2f}MB",
            "Base64 data:",
            img_result.get("data", ""),
        ]
        return "\n".join(header)

    range_tuple = _parse_view_range(view_range)
    if isinstance(range_tuple, str):
        return range_tuple

    content = await _read_text_content(client, sandbox_path)
    if content.startswith("[错误:"):
        return content
    return _format_text_content(content, range_tuple)
