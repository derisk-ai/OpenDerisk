"""Hook endpoint executors: API / CLI / Agent.

The CLI executor speaks the same protocol as Anthropic Claude Code so existing
CC plugin hooks can be reused without modification:

* The hook event JSON is delivered through stdin.
* Exit code 0 with empty stdout → continue.
* Exit code 0 with stdout JSON `{"action":"continue|deny|abort|modify", ...}` → that decision.
* Exit code 2 → deny (stderr is treated as `reason`).
* Other non-zero exits → fall back to `endpoint.default_on_error`.

The API executor follows Claude Code's webhook semantics:

* `2xx` with empty body → continue.
* `2xx` with `{"action":"...", "modified_input":..., "reason":...}` → that decision.
* Non-`2xx` / network errors / timeouts → `endpoint.default_on_error`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

from .schema import (
    BlockingPolicy,
    HookDecision,
    HookEndpointConfig,
    HookEvent,
    HookKind,
)

logger = logging.getLogger(__name__)


class BaseHookExecutor(ABC):
    """Common interface for endpoint executors."""

    @abstractmethod
    async def execute(
        self,
        event: HookEvent,
        endpoint: HookEndpointConfig,
        runtime: Optional[Dict[str, Any]] = None,
    ) -> HookDecision:
        ...


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _parse_decision_payload(payload: Any) -> HookDecision:
    """Parse a JSON payload returned by an API/CLI hook into HookDecision."""
    if not isinstance(payload, dict):
        return HookDecision.cont()
    action = (payload.get("action") or "continue").lower()
    reason = payload.get("reason")
    modified_input = payload.get("modified_input")

    if action == "deny":
        return HookDecision.deny(reason or "denied")
    if action == "abort":
        return HookDecision.abort(reason or "aborted")
    if action == "modify":
        if not isinstance(modified_input, dict):
            modified_input = {}
        return HookDecision.modify(modified_input, reason)
    return HookDecision.cont()


def _on_error(endpoint: HookEndpointConfig, reason: str) -> HookDecision:
    policy = endpoint.default_on_error or BlockingPolicy.CONTINUE
    if policy == BlockingPolicy.DENY:
        return HookDecision.deny(reason)
    if policy == BlockingPolicy.ABORT:
        return HookDecision.abort(reason)
    if policy == BlockingPolicy.MODIFY:
        # MODIFY without modified_input is meaningless — degrade to continue.
        return HookDecision.cont()
    return HookDecision.cont()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class ApiHookExecutor(BaseHookExecutor):
    async def execute(
        self,
        event: HookEvent,
        endpoint: HookEndpointConfig,
        runtime: Optional[Dict[str, Any]] = None,
    ) -> HookDecision:
        if not endpoint.api_url:
            return _on_error(endpoint, "api_url is empty")
        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp not installed — API hook %s skipped", endpoint.api_url)
            return _on_error(endpoint, "aiohttp not installed")

        headers = {"Content-Type": "application/json"}
        headers.update(endpoint.api_headers or {})
        if endpoint.api_auth_token:
            headers["Authorization"] = f"Bearer {endpoint.api_auth_token}"

        payload = event.to_dict()
        timeout = aiohttp.ClientTimeout(total=endpoint.timeout)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    endpoint.api_url, json=payload, headers=headers
                ) as resp:
                    text = await resp.text()
                    if resp.status >= 300:
                        logger.warning(
                            "API hook %s returned %s: %s",
                            endpoint.api_url,
                            resp.status,
                            text[:200],
                        )
                        return _on_error(endpoint, f"http_{resp.status}: {text[:200]}")
                    if not text.strip():
                        return HookDecision.cont()
                    try:
                        body = json.loads(text)
                    except json.JSONDecodeError:
                        return HookDecision.cont()
                    return _parse_decision_payload(body)
        except asyncio.TimeoutError:
            logger.warning("API hook %s timed out", endpoint.api_url)
            return _on_error(endpoint, "timeout")
        except Exception as e:
            logger.warning("API hook %s failed: %s", endpoint.api_url, e)
            return _on_error(endpoint, f"exception: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class CliHookExecutor(BaseHookExecutor):
    """Run an external program and decide based on exit code + stdout."""

    async def execute(
        self,
        event: HookEvent,
        endpoint: HookEndpointConfig,
        runtime: Optional[Dict[str, Any]] = None,
    ) -> HookDecision:
        if not endpoint.cli_command:
            return _on_error(endpoint, "cli_command is empty")

        # Resolve allowlist / sandbox before doing anything destructive.
        try:
            tokens = shlex.split(endpoint.cli_command)
        except ValueError as e:
            return _on_error(endpoint, f"cli_command parse error: {e}")
        if not tokens:
            return _on_error(endpoint, "cli_command empty after parse")
        first = os.path.basename(tokens[0])
        allowlist = endpoint.cli_allowlist or []
        if not endpoint.cli_in_sandbox:
            if not allowlist:
                return _on_error(
                    endpoint, "cli_allowlist is required when cli_in_sandbox is False"
                )
            if first not in allowlist and tokens[0] not in allowlist:
                return _on_error(endpoint, f"command '{first}' not in allowlist")

        runtime = runtime or {}
        sandbox_client = runtime.get("sandbox_client")

        event_json = json.dumps(event.to_dict(), ensure_ascii=False)

        if endpoint.cli_in_sandbox and sandbox_client is not None:
            return await self._run_in_sandbox(
                endpoint, sandbox_client, event_json
            )
        return await self._run_local(endpoint, event_json)

    async def _run_local(
        self, endpoint: HookEndpointConfig, event_json: str
    ) -> HookDecision:
        try:
            proc = await asyncio.create_subprocess_shell(
                endpoint.cli_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=endpoint.cli_cwd or None,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(event_json.encode("utf-8")),
                    timeout=endpoint.timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return _on_error(endpoint, "timeout")
        except Exception as e:
            return _on_error(endpoint, f"spawn error: {e}")

        return self._parse_cli_result(
            endpoint,
            proc.returncode if proc.returncode is not None else -1,
            stdout.decode("utf-8", errors="replace") if stdout else "",
            stderr.decode("utf-8", errors="replace") if stderr else "",
        )

    async def _run_in_sandbox(
        self, endpoint: HookEndpointConfig, sandbox_client: Any, event_json: str
    ) -> HookDecision:
        # The sandbox shell tool typically accepts a string command and returns
        # a result with stdout/stderr/exit_code. Pipe the event JSON via a
        # heredoc-like wrapper so we don't depend on stdin support.
        wrapper = (
            f"cat <<'__DERISK_HOOK_EVENT__' | {endpoint.cli_command}\n"
            f"{event_json}\n__DERISK_HOOK_EVENT__\n"
        )
        try:
            shell_manager = getattr(sandbox_client, "shell_manager", None)
            if shell_manager and hasattr(shell_manager, "execute"):
                fut = shell_manager.execute(
                    command=wrapper,
                    timeout=endpoint.timeout,
                    cwd=endpoint.cli_cwd or None,
                )
                result = await asyncio.wait_for(fut, timeout=endpoint.timeout + 2)
            elif hasattr(sandbox_client, "execute"):
                fut = sandbox_client.execute(
                    command=wrapper,
                    timeout=endpoint.timeout,
                    cwd=endpoint.cli_cwd or None,
                )
                result = await asyncio.wait_for(fut, timeout=endpoint.timeout + 2)
            else:
                return _on_error(endpoint, "sandbox client lacks shell_manager.execute")
        except asyncio.TimeoutError:
            return _on_error(endpoint, "sandbox timeout")
        except Exception as e:
            return _on_error(endpoint, f"sandbox error: {e}")

        # Normalise the result regardless of dict / object shape.
        exit_code = (
            result.get("exit_code")
            if isinstance(result, dict)
            else getattr(result, "exit_code", -1)
        )
        stdout = (
            result.get("stdout")
            if isinstance(result, dict)
            else getattr(result, "stdout", "")
        )
        stderr = (
            result.get("stderr")
            if isinstance(result, dict)
            else getattr(result, "stderr", "")
        )
        return self._parse_cli_result(
            endpoint, int(exit_code or 0), stdout or "", stderr or ""
        )

    @staticmethod
    def _parse_cli_result(
        endpoint: HookEndpointConfig, exit_code: int, stdout: str, stderr: str
    ) -> HookDecision:
        if exit_code == 0:
            stdout = (stdout or "").strip()
            if not stdout:
                return HookDecision.cont()
            try:
                body = json.loads(stdout)
            except json.JSONDecodeError:
                return HookDecision.cont()
            return _parse_decision_payload(body)
        if exit_code == 2:
            # CC convention: 2 means deny / blocking error
            return HookDecision.deny((stderr or "denied").strip())
        return _on_error(endpoint, f"exit_{exit_code}: {(stderr or '').strip()[:200]}")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class AgentHookExecutor(BaseHookExecutor):
    """Dispatch the event to another Agent.

    For now this is fire-and-forget — the agent's reply is captured in logs but
    does not feed back into a HookDecision. To enable blocking semantics, the
    target agent's reply should follow the same JSON schema as API hooks.
    """

    async def execute(
        self,
        event: HookEvent,
        endpoint: HookEndpointConfig,
        runtime: Optional[Dict[str, Any]] = None,
    ) -> HookDecision:
        runtime = runtime or {}
        dispatcher = runtime.get("agent_dispatcher")
        if dispatcher is None:
            logger.debug(
                "AgentHookExecutor: no dispatcher registered; skipping hook %s",
                endpoint.agent_name,
            )
            return HookDecision.cont()
        try:
            reply = await dispatcher(
                agent_name=endpoint.agent_name,
                app_code=endpoint.agent_app_code,
                event=event.to_dict(),
                timeout=endpoint.timeout,
            )
        except Exception as e:
            logger.warning("AgentHook dispatcher failed: %s", e)
            return _on_error(endpoint, f"agent error: {e}")
        if isinstance(reply, dict):
            return _parse_decision_payload(reply)
        return HookDecision.cont()


# ---------------------------------------------------------------------------
# Function (in-process callable)
# ---------------------------------------------------------------------------


class FunctionRegistry:
    """Process-level registry of in-process hook callables.

    Callables are addressed by string name (so HookConfig stays JSON-
    serialisable and can be persisted in team_context.hook_config).

    Registered functions must accept ``(event: dict, runtime: dict)`` and
    return either ``None`` / non-dict (treated as continue) or a dict
    matching the HookDecision payload schema (``{"action": ...}``).
    """

    _registry: Dict[str, Callable[..., Any]] = {}

    @classmethod
    def register(cls, name: str, fn: Callable[..., Any]) -> None:
        cls._registry[name] = fn

    @classmethod
    def unregister(cls, name: str) -> None:
        cls._registry.pop(name, None)

    @classmethod
    def get(cls, name: str) -> Optional[Callable[..., Any]]:
        return cls._registry.get(name)

    @classmethod
    def names(cls) -> list:
        return list(cls._registry.keys())


class FunctionHookExecutor(BaseHookExecutor):
    """Resolve `endpoint.function_name` via FunctionRegistry and call it.

    Used for in-process hooks that don't need an LLM or a real Agent —
    e.g. the memory tier 0/1 fast paths (prefetch, per-turn write).
    Failures fall back to `endpoint.default_on_error` and never propagate
    to the hook executor.
    """

    async def execute(
        self,
        event: HookEvent,
        endpoint: HookEndpointConfig,
        runtime: Optional[Dict[str, Any]] = None,
    ) -> HookDecision:
        name = endpoint.function_name
        if not name:
            logger.warning(
                "FunctionHookExecutor: endpoint has no function_name; skipping"
            )
            return _on_error(endpoint, "missing function_name")
        fn = FunctionRegistry.get(name)
        if fn is None:
            logger.warning(
                "FunctionHookExecutor: function %s not registered; skipping",
                name,
            )
            return _on_error(endpoint, f"function {name} not registered")
        try:
            reply = await fn(event.to_dict(), runtime or {})
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "FunctionHookExecutor: function %s raised: %s", name, e
            )
            return _on_error(endpoint, f"function error: {e}")
        if isinstance(reply, dict):
            return _parse_decision_payload(reply)
        return HookDecision.cont()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ExecutorRegistry:
    """Pick the right executor by HookKind."""

    def __init__(self) -> None:
        self._executors: Dict[HookKind, BaseHookExecutor] = {
            HookKind.API: ApiHookExecutor(),
            HookKind.CLI: CliHookExecutor(),
            HookKind.AGENT: AgentHookExecutor(),
            HookKind.FUNCTION: FunctionHookExecutor(),
        }

    def get(self, kind: HookKind) -> BaseHookExecutor:
        return self._executors[kind]


_DEFAULT_REGISTRY = ExecutorRegistry()


def get_executor(kind: HookKind) -> BaseHookExecutor:
    return _DEFAULT_REGISTRY.get(kind)
