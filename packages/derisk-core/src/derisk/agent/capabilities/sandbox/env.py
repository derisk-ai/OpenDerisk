"""Sandbox env 文本构建(RFC-005 S14)。

从 sandbox_client 静态属性(provider/work_dir/skill_dir)产 env 信息文本。
属轻量属性读取(非 I/O),务实放宽 declare 纯函数约束。
"""

from __future__ import annotations

from typing import Any, Optional


def build_env_text(sandbox_client: Any, work_dir: str) -> str:
    """构建沙箱 env 信息文本。"""
    lines = ["### 环境信息", ""]
    lines.append(f"工作目录: {work_dir}")

    if sandbox_client is not None:
        system_info = get_system_info(sandbox_client)
        if system_info:
            lines.append(f"系统: {system_info}")
        skill_dir = getattr(sandbox_client, "skill_dir", "")
        if skill_dir:
            lines.append(f"技能目录: {skill_dir}")
    lines.append("")
    lines.append(
        "<important>沙箱环境是临时的，会话结束后会被销毁。如需持久化文件，请使用 write_file 工具。</important>"
    )
    return "\n".join(lines)


def get_system_info(sandbox_client: Any) -> str:
    """按 sandbox provider 类型产系统信息(逻辑对齐 _get_sandbox_system_info)。"""
    provider = getattr(sandbox_client, "provider", lambda: "unknown")()
    if provider == "local":
        import platform

        system = platform.system()
        if system == "Darwin":
            return f"macOS ({platform.processor()}), 本地沙箱环境，路径映射到项目目录"
        elif system == "Linux":
            return f"Linux ({platform.processor()}), 本地沙箱环境，路径映射到项目目录"
        elif system == "Windows":
            return "Windows, 本地沙箱环境，路径映射到项目目录"
        return f"{system}, 本地沙箱环境，路径映射到项目目录"
    return "Ubuntu 24.04 linux/amd64（已联网），用户：ubuntu（拥有免密 sudo 权限）"