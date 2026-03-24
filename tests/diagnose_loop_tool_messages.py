#!/usr/bin/env python3
"""
Diagnostic script to verify ReActMasterV2 loop tool_messages bug.

Issue: In AgentRunMode.LOOP mode, tool call results are NOT appended to all_tool_messages,
causing LLM to repeatedly call the same tool because it doesn't see previous results.

Root Cause: Line 821 in base_agent.py has condition `self.run_mode != AgentRunMode.LOOP`
which skips appending tool_messages for LOOP mode agents.

Expected Behavior: Tool call results should be appended to all_tool_messages for ALL modes.
"""

import sys
from pathlib import Path

# Add project paths
_project_root = Path(__file__).parent
sys.path.insert(0, str(_project_root / "packages/derisk-core/src"))


def check_base_agent_code():
    """Check if the bug exists in base_agent.py"""
    print("=" * 80)
    print("Checking base_agent.py for LOOP mode tool_messages bug")
    print("=" * 80)

    base_agent_path = (
        _project_root / "packages/derisk-core/src/derisk/agent/core/base_agent.py"
    )

    if not base_agent_path.exists():
        print(f"❌ File not found: {base_agent_path}")
        return False

    with open(base_agent_path, "r") as f:
        lines = f.readlines()

    # Find the problematic code section (around line 820-827)
    print("\n📍 Checking lines 820-827 for the bug condition:\n")

    bug_found = False
    for i in range(819, min(828, len(lines))):
        line = lines[i]
        line_num = i + 1
        print(f"  {line_num:4d}: {line.rstrip()}")

        # Check for the bug condition
        if "if self.run_mode != AgentRunMode.LOOP:" in line:
            bug_found = True
            print(
                "\n  ⚠️  BUG FOUND: This condition prevents LOOP mode agents from getting tool_messages!"
            )

    print("\n" + "-" * 80)

    if bug_found:
        print("❌ BUG CONFIRMED: LOOP mode agents will NOT receive tool call results")
        print("\n🔧 Impact:")
        print("  - ReActMasterV2 (LOOP mode) will repeatedly call the same tool")
        print("  - LLM doesn't see previous tool results in next iteration")
        print("  - WorkLog records tools but doesn't inject them to LLM prompt")
        print("\n💡 Fix: Remove the 'self.run_mode != AgentRunMode.LOOP' condition")
        print("       OR handle LOOP mode specially to inject tool messages")
    else:
        print("✅ No bug found in this section (may have been fixed)")

    return bug_found


def explain_the_bug():
    """Explain the bug in detail"""
    print("\n" + "=" * 80)
    print("DETAILED BUG EXPLANATION")
    print("=" * 80)

    print("""
## Problem

ReActMasterV2 uses AgentRunMode.LOOP mode to execute multiple iterations.
In each iteration, it should:
  1. Call a tool
  2. Get result
  3. Pass result to LLM in next iteration
  4. LLM decides next action based on results

## What Actually Happens

In base_agent.py generate_reply() method (line 820-827):

    if self.current_retry_counter > 0:
        if self.run_mode != AgentRunMode.LOOP:    # ⚠️ PROBLEM: This excludes LOOP mode!
            if self.enable_function_call:
                tool_messages = self.function_callning_reply_messages(agent_llm_out, act_outs)
                all_tool_messages.extend(tool_messages)  # ❌ NOT executed for LOOP mode

Result:
- For LOOP mode agents, tool_messages are NEVER appended to all_tool_messages
- LLM sees the SAME context in each iteration (no tool results)
- LLM calls the same tool again → infinite loop

## Why WorkLog Doesn't Help

WorkLog injection happens only ONCE at the start (line 798-804):

    if self.enable_function_call and self.current_retry_counter == 0:
        worklog_messages = await self._get_worklog_tool_messages()
        all_tool_messages.extend(worklog_messages)

The condition `self.current_retry_counter == 0` means WorkLog is only fetched once.
In subsequent LOOP iterations, WorkLog is NOT re-fetched.

## Solution

Remove the `self.run_mode != AgentRunMode.LOOP` condition to allow LOOP mode agents
to receive tool call results in each iteration:

    if self.current_retry_counter > 0:
        if self.enable_function_call:
            tool_messages = self.function_callning_reply_messages(agent_llm_out, act_outs)
            all_tool_messages.extend(tool_messages)
""")


def suggest_fix():
    """Suggest the fix"""
    print("\n" + "=" * 80)
    print("SUGGESTED FIX")
    print("=" * 80)

    print("""
## File: packages/derisk-core/src/derisk/agent/core/base_agent.py

## Location: Line 820-827

## Current Code (BUGGY):
```python
if self.current_retry_counter > 0:
    if self.run_mode != AgentRunMode.LOOP:    # ❌ Remove this condition
        if self.enable_function_call:
            tool_messages = self.function_callning_reply_messages(agent_llm_out, act_outs)
            all_tool_messages.extend(tool_messages)
```

## Fixed Code:
```python
if self.current_retry_counter > 0:
    if self.enable_function_call:
        tool_messages = self.function_callning_reply_messages(agent_llm_out, act_outs)
        all_tool_messages.extend(tool_messages)
```

## Why This Works:
- Removes the LOOP mode exclusion
- All agents (including ReActMasterV2) will now receive tool call results
- LLM can see previous tool results and make informed decisions
- Prevents infinite loops caused by LLM not knowing tools were already called
""")


def main():
    print("\n" + "🔍" * 40)
    print("ReActMasterV2 LOOP Mode Tool Messages Bug Diagnostic")
    print("🔍" * 40 + "\n")

    # Check for the bug
    bug_exists = check_base_agent_code()

    # Explain the bug
    explain_the_bug()

    # Suggest fix
    suggest_fix()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if bug_exists:
        print("❌ Bug confirmed in base_agent.py line 821")
        print("✅ Fix: Remove 'self.run_mode != AgentRunMode.LOOP' condition")
        print(
            "\nThis will resolve the issue where ReActMasterV2 repeatedly calls tools"
        )
        print("without seeing previous results, causing infinite loops.")
        return 1
    else:
        print("✅ Bug may have been fixed or code has changed")
        print("Please verify manually that LOOP mode agents receive tool messages")
        return 0


if __name__ == "__main__":
    sys.exit(main())
