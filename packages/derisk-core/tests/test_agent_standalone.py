"""Standalone tests for refactored Agent system - no external dependencies."""

import asyncio
import fnmatch
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union
import os
import yaml


class AgentMode(str, Enum):
    PRIMARY = "primary"
    SUBAGENT = "subagent"
    ALL = "all"


class PermissionAction(str, Enum):
    ASK = "ask"
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class PermissionRule:
    action: PermissionAction
    pattern: str
    permission: str

    def matches(self, tool_name: str, command: Optional[str] = None) -> bool:
        if self.permission == "*":
            return True
        if fnmatch.fnmatch(tool_name, self.pattern):
            return True
        if command and fnmatch.fnmatch(command, self.pattern):
            return True
        return False


class PermissionRuleset:
    def __init__(self, rules: Optional[List[PermissionRule]] = None):
        self._rules: List[PermissionRule] = rules or []

    def check(self, tool_name: str, command: Optional[str] = None) -> PermissionAction:
        result = PermissionAction.ASK
        for rule in self._rules:
            if rule.matches(tool_name, command):
                result = rule.action
        return result

    def is_allowed(self, tool_name: str, command: Optional[str] = None) -> bool:
        return self.check(tool_name, command) == PermissionAction.ALLOW

    def is_denied(self, tool_name: str, command: Optional[str] = None) -> bool:
        return self.check(tool_name, command) == PermissionAction.DENY

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "PermissionRuleset":
        rules: List[PermissionRule] = []

        def _parse_rules(permission: str, value: Any, prefix: str = ""):
            if isinstance(value, str):
                pattern = f"{prefix}{permission}" if prefix else permission
                rules.append(
                    PermissionRule(
                        action=PermissionAction(value),
                        pattern=pattern,
                        permission=permission,
                    )
                )
            elif isinstance(value, dict):
                for k, v in value.items():
                    new_prefix = f"{prefix}{k}." if prefix else f"{k}."
                    _parse_rules(k, v, new_prefix.rstrip("."))

        for key, value in config.items():
            _parse_rules(key, value)

        return cls(rules)

    @classmethod
    def merge(cls, *rulesets: "PermissionRuleset") -> "PermissionRuleset":
        all_rules: List[PermissionRule] = []
        for ruleset in rulesets:
            if ruleset:
                all_rules.extend(ruleset._rules)
        return cls(all_rules)


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_INPUT = "needs_input"
    TERMINATED = "terminated"


@dataclass
class ExecutionStep:
    step_id: str
    step_type: str
    content: Any
    status: ExecutionStatus = ExecutionStatus.PENDING
    start_time: float = field(default_factory=lambda: __import__("time").time())
    end_time: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def complete(self, result: Any = None):
        self.status = ExecutionStatus.SUCCESS
        self.end_time = __import__("time").time()
        if result is not None:
            self.content = result

    def fail(self, error: str):
        self.status = ExecutionStatus.FAILED
        self.end_time = __import__("time").time()
        self.error = error


@dataclass
class ExecutionResult:
    steps: List[ExecutionStep] = field(default_factory=list)
    final_content: Any = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    total_tokens: int = 0
    total_time_ms: int = 0

    @property
    def success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS

    def add_step(self, step: ExecutionStep) -> ExecutionStep:
        self.steps.append(step)
        return step


class ExecutionHooks:
    def __init__(self):
        self._hooks: Dict[str, List[Callable]] = {
            "before_thinking": [],
            "after_thinking": [],
            "before_action": [],
            "after_action": [],
            "before_step": [],
            "after_step": [],
            "on_error": [],
            "on_complete": [],
        }

    def on(self, event: str, handler: Callable) -> "ExecutionHooks":
        if event in self._hooks:
            self._hooks[event].append(handler)
        return self

    async def emit(self, event: str, *args, **kwargs) -> None:
        for handler in self._hooks.get(event, []):
            try:
                result = handler(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass


class ExecutionEngine:
    def __init__(
        self,
        max_steps: int = 10,
        timeout_seconds: Optional[float] = None,
        hooks: Optional[ExecutionHooks] = None,
    ):
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds
        self.hooks = hooks or ExecutionHooks()

    async def execute(
        self,
        initial_input: Any,
        think_func: Callable[[Any], Any],
        act_func: Callable[[Any], Any],
        verify_func: Optional[Callable[[Any], Tuple[bool, Optional[str]]]] = None,
        should_terminate: Optional[Callable[[Any], bool]] = None,
    ) -> ExecutionResult:
        result = ExecutionResult()
        current_input = initial_input
        step_count = 0
        start_time = __import__("time").time()

        try:
            await self.hooks.emit("before_step", step_count, current_input)

            while step_count < self.max_steps:
                step_id = __import__("uuid").uuid4().hex[:8]

                thinking_step = ExecutionStep(
                    step_id=step_id,
                    step_type="thinking",
                    content=None,
                )
                result.add_step(thinking_step)

                await self.hooks.emit("before_thinking", step_count, current_input)

                thinking_result = await think_func(current_input)
                thinking_step.complete(thinking_result)

                await self.hooks.emit("after_thinking", step_count, thinking_result)

                action_step = ExecutionStep(
                    step_id=f"{step_id}_action",
                    step_type="action",
                    content=None,
                )
                result.add_step(action_step)

                await self.hooks.emit("before_action", step_count, thinking_result)

                action_result = await act_func(thinking_result)
                action_step.complete(action_result)

                await self.hooks.emit("after_action", step_count, action_result)

                if verify_func:
                    passed, reason = await verify_func(action_result)
                    if not passed:
                        current_input = action_result
                        step_count += 1
                        continue

                if should_terminate and should_terminate(action_result):
                    result.status = ExecutionStatus.TERMINATED
                    result.final_content = action_result
                    break

                step_count += 1
                await self.hooks.emit("after_step", step_count, action_result)

                result.final_content = action_result
                result.status = ExecutionStatus.SUCCESS

            if step_count >= self.max_steps:
                result.status = ExecutionStatus.FAILED

        except Exception as e:
            result.status = ExecutionStatus.FAILED
            await self.hooks.emit("on_error", e)
            raise

        finally:
            result.total_time_ms = int((__import__("time").time() - start_time) * 1000)
            await self.hooks.emit("on_complete", result)

        return result


def run_tests():
    """Run all tests."""
    import time

    print("=" * 60)
    print("Agent Refactor Tests")
    print("=" * 60)

    passed = 0
    failed = 0

    # Test 1: Permission Rule Creation
    print("\n[Test 1] Permission Rule Creation...")
    try:
        rule = PermissionRule(
            action=PermissionAction.ALLOW, pattern="read", permission="read"
        )
        assert rule.action == PermissionAction.ALLOW
        assert rule.pattern == "read"
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        failed += 1

    # Test 2: Permission Ruleset from Config
    print("\n[Test 2] Permission Ruleset from Config...")
    try:
        config = {
            "*": "ask",
            "read": "allow",
            "write": "deny",
        }
        ruleset = PermissionRuleset.from_config(config)

        assert ruleset.check("read") == PermissionAction.ALLOW, (
            f"Expected ALLOW for read, got {ruleset.check('read')}"
        )
        assert ruleset.check("write") == PermissionAction.DENY, (
            f"Expected DENY for write, got {ruleset.check('write')}"
        )
        assert ruleset.check("edit") == PermissionAction.ASK, (
            f"Expected ASK for edit, got {ruleset.check('edit')}"
        )
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        failed += 1

    # Test 3: Permission Ruleset Merge
    print("\n[Test 3] Permission Ruleset Merge...")
    try:
        ruleset1 = PermissionRuleset.from_config(
            {
                "*": "deny",
                "read": "allow",
            }
        )
        ruleset2 = PermissionRuleset.from_config(
            {
                "write": "ask",
            }
        )

        merged = PermissionRuleset.merge(ruleset1, ruleset2)
        assert merged.check("read") == PermissionAction.ALLOW
        assert merged.check("write") == PermissionAction.ASK
        assert merged.check("edit") == PermissionAction.DENY
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        failed += 1

    # Test 4: Execution Step
    print("\n[Test 4] Execution Step...")
    try:
        step = ExecutionStep(step_id="test-1", step_type="thinking", content=None)

        assert step.status == ExecutionStatus.PENDING

        step.complete("result")
        assert step.status == ExecutionStatus.SUCCESS
        assert step.content == "result"
        assert step.end_time is not None
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        failed += 1

    # Test 5: Execution Engine Simple
    print("\n[Test 5] Execution Engine Simple...")

    async def test_engine_simple():
        engine = ExecutionEngine(max_steps=2)

        think_calls = 0
        act_calls = 0

        async def think_func(x):
            nonlocal think_calls
            think_calls += 1
            return f"thought_{think_calls}"

        async def act_func(x):
            nonlocal act_calls
            act_calls += 1
            return f"action_{act_calls}"

        async def verify_func(x):
            return (True, None)

        result = await engine.execute(
            initial_input="test_input",
            think_func=think_func,
            act_func=act_func,
            verify_func=verify_func,
        )

        assert result.status == ExecutionStatus.SUCCESS
        assert think_calls == 1
        assert act_calls == 1
        return True

    try:
        asyncio.run(test_engine_simple())
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        failed += 1

    # Test 6: Execution Engine with Retry
    print("\n[Test 6] Execution Engine with Retry...")

    async def test_engine_retry():
        engine = ExecutionEngine(max_steps=5)

        call_count = 0

        async def think_func(x):
            return "thinking"

        async def act_func(x):
            nonlocal call_count
            call_count += 1
            return f"action_{call_count}"

        async def verify_func(x):
            nonlocal call_count
            return (call_count >= 3, "not done") if call_count < 3 else (True, None)

        result = await engine.execute(
            initial_input="test_input",
            think_func=think_func,
            act_func=act_func,
            verify_func=verify_func,
        )

        assert result.status == ExecutionStatus.SUCCESS
        assert call_count == 3
        return True

    try:
        asyncio.run(test_engine_retry())
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        failed += 1

    # Test 7: Execution Hooks
    print("\n[Test 7] Execution Hooks...")

    async def test_hooks():
        hooks = ExecutionHooks()
        events = []

        hooks.on("before_thinking", lambda *a, **k: events.append("before_thinking"))
        hooks.on("after_thinking", lambda *a, **k: events.append("after_thinking"))

        engine = ExecutionEngine(max_steps=1, hooks=hooks)

        await engine.execute(
            initial_input="test",
            think_func=lambda x: "thought",
            act_func=lambda x: "action",
        )

        assert "before_thinking" in events
        assert "after_thinking" in events
        return True

    try:
        asyncio.run(test_hooks())
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        failed += 1

    # Test 8: Permission is_allowed/is_denied
    print("\n[Test 8] Permission is_allowed/is_denied...")
    try:
        ruleset = PermissionRuleset.from_config({"read": "allow", "write": "deny"})
        assert ruleset.is_allowed("read")
        assert not ruleset.is_allowed("write")
        assert ruleset.is_denied("write")
        assert not ruleset.is_denied("read")
        print("  ✓ PASSED")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
