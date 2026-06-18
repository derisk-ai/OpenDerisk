"""Claude Code plugin compatibility layer.

A Claude Code plugin ships with a `hooks/hooks.json` file. The format is::

    {
      "hooks": {
        "PreToolUse": [
          {
            "matcher": "Bash|Write",
            "hooks": [
              {"type": "command", "command": "/path/to/checker.sh", "timeout": 10}
            ]
          }
        ],
        "Stop": [...],
        "UserPromptSubmit": [...]
      }
    }

We translate that file into the unified DeRisk schema so the same hooks can run
inside the OpenDerisk runtime untouched. Discovery rules:

* If a path points to a JSON file, load it directly.
* If it points to a directory, look for `hooks/hooks.json` first, then
  `hooks.json`. Also recursively scan `plugins/<name>/` for plugins.
* Each loaded plugin contributes one or more `HookConfig` entries with a
  `kind=cli` endpoint. Sandbox execution defaults to True for safety.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterable, List, Optional

from .schema import (
    CC_EVENT_TO_TRIGGER,
    HookConfig,
    HookEndpointConfig,
    HookKind,
    HookTriggerConfig,
)

logger = logging.getLogger(__name__)


def load_plugin_hooks(paths: Iterable[str], in_sandbox: bool = True) -> List[HookConfig]:
    """Load all CC-style plugin hooks from `paths` and return a flattened list."""
    hooks: List[HookConfig] = []
    for raw_path in paths or []:
        path = os.path.expanduser(raw_path)
        if not os.path.exists(path):
            logger.warning("Hook plugin path not found: %s", path)
            continue
        for manifest in _discover_manifests(path):
            try:
                hooks.extend(_load_manifest(manifest, in_sandbox=in_sandbox))
            except Exception as e:  # noqa: BLE001
                logger.exception("Failed to load CC plugin manifest %s: %s", manifest, e)
    return hooks


def _discover_manifests(path: str) -> List[str]:
    if os.path.isfile(path):
        return [path]
    candidates: List[str] = []
    direct = [
        os.path.join(path, "hooks", "hooks.json"),
        os.path.join(path, "hooks.json"),
    ]
    for c in direct:
        if os.path.exists(c):
            candidates.append(c)
    plugins_dir = os.path.join(path, "plugins")
    if os.path.isdir(plugins_dir):
        for name in os.listdir(plugins_dir):
            sub = os.path.join(plugins_dir, name)
            if not os.path.isdir(sub):
                continue
            for c in (
                os.path.join(sub, "hooks", "hooks.json"),
                os.path.join(sub, "hooks.json"),
            ):
                if os.path.exists(c):
                    candidates.append(c)
    return candidates


def _load_manifest(manifest_path: str, in_sandbox: bool) -> List[HookConfig]:
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    plugin_name = _plugin_name_from_path(manifest_path)
    hooks_section = manifest.get("hooks") or {}
    if not isinstance(hooks_section, dict):
        return []

    out: List[HookConfig] = []
    for cc_event, entries in hooks_section.items():
        trigger = CC_EVENT_TO_TRIGGER.get(cc_event)
        if not trigger:
            logger.debug("Skipping unsupported CC event: %s", cc_event)
            continue
        if not isinstance(entries, list):
            continue
        for idx, group in enumerate(entries):
            matcher = group.get("matcher") if isinstance(group, dict) else None
            globs = _matcher_to_globs(matcher)
            for h_idx, hook_cfg in enumerate(group.get("hooks") or []):
                hc = _convert_hook_cfg(
                    hook_cfg=hook_cfg,
                    trigger=trigger,
                    globs=globs,
                    plugin_name=plugin_name,
                    in_sandbox=in_sandbox,
                    idx=f"{idx}-{h_idx}",
                    cwd=os.path.dirname(manifest_path),
                )
                if hc:
                    out.append(hc)
    return out


def _plugin_name_from_path(manifest_path: str) -> str:
    parent = os.path.basename(os.path.dirname(os.path.dirname(manifest_path)))
    return parent or os.path.basename(os.path.dirname(manifest_path))


def _matcher_to_globs(matcher: Optional[str]) -> List[str]:
    if not matcher:
        return ["*"]
    parts = [p.strip() for p in matcher.split("|") if p.strip()]
    return parts or ["*"]


def _convert_hook_cfg(
    hook_cfg: dict,
    trigger: str,
    globs: List[str],
    plugin_name: str,
    in_sandbox: bool,
    idx: str,
    cwd: str,
) -> Optional[HookConfig]:
    if not isinstance(hook_cfg, dict):
        return None
    h_type = hook_cfg.get("type", "command")
    if h_type != "command":
        logger.debug("Skipping non-command hook type: %s", h_type)
        return None
    command = hook_cfg.get("command")
    if not command:
        return None
    timeout = int(hook_cfg.get("timeout") or 30)
    blocking = bool(hook_cfg.get("blocking", trigger == "pre_tool_use"))
    name = f"cc:{plugin_name}:{trigger}:{idx}"

    endpoint = HookEndpointConfig(
        kind=HookKind.CLI,
        cli_command=command,
        cli_in_sandbox=in_sandbox,
        cli_allowlist=hook_cfg.get("allowlist") or [],
        cli_cwd=hook_cfg.get("cwd") or cwd,
        timeout=timeout,
        blocking=blocking,
    )
    return HookConfig(
        name=name,
        enabled=True,
        trigger=HookTriggerConfig(trigger_type=trigger, tool_name_globs=globs),
        endpoint=endpoint,
        description=f"Imported from Claude Code plugin {plugin_name}",
    )
