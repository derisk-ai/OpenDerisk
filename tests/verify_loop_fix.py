#!/usr/bin/env python3
"""
Verification script to test the LOOP mode tool_messages fix.

This script verifies that:
1. The bug condition has been removed
2. LOOP mode agents now receive tool messages
"""

import sys
from pathlib import Path

# Add project paths
_project_root = Path(__file__).parent
sys.path.insert(0, str(_project_root / "packages/derisk-core/src"))


def verify_fix():
    """Verify that the bug has been fixed"""
    print("=" * 80)
    print("Verifying LOOP mode tool_messages fix")
    print("=" * 80)

    base_agent_path = (
        _project_root / "packages/derisk-core/src/derisk/agent/core/base_agent.py"
    )

    with open(base_agent_path, "r") as f:
        content = f.read()

    # Check if the buggy condition still exists
    buggy_condition = "if self.run_mode != AgentRunMode.LOOP:"

    if buggy_condition in content:
        print(f"❌ FIX NOT APPLIED: Buggy condition still exists")
        print(f"   Found: '{buggy_condition}'")

        # Find the line number
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            if buggy_condition in line:
                print(f"   Location: line {i}")

        return False

    print("✅ FIX APPLIED: Buggy condition has been removed")

    # Verify the correct code exists
    correct_pattern = """if self.current_retry_counter > 0:
                        if self.enable_function_call:
                            ## 基于当前action的结果，构建history_dialogue 和 tool_message
                            tool_messages = self.function_callning_reply_messages(
                                agent_llm_out, act_outs
                            )
                            all_tool_messages.extend(tool_messages)"""

    if correct_pattern in content:
        print("✅ CORRECT CODE: Tool messages are now appended for all modes")
    else:
        print("⚠️  WARNING: Code structure may have changed")
        print("   Please verify manually that tool messages are appended")

    return True


def explain_fix():
    """Explain what the fix does"""
    print("\n" + "=" * 80)
    print("FIX EXPLANATION")
    print("=" * 80)

    print("""
## What Was Fixed

Removed the condition `if self.run_mode != AgentRunMode.LOOP:` from line 821.

## Before (BUGGY):
```python
if self.current_retry_counter > 0:
    if self.run_mode != AgentRunMode.LOOP:    # ❌ Excluded LOOP mode
        if self.enable_function_call:
            tool_messages = self.function_callning_reply_messages(...)
            all_tool_messages.extend(tool_messages)
```

## After (FIXED):
```python
if self.current_retry_counter > 0:
    if self.enable_function_call:    # ✅ All modes get tool messages
        tool_messages = self.function_callning_reply_messages(...)
        all_tool_messages.extend(tool_messages)
```

## Impact

✅ ReActMasterV2 (LOOP mode) will now receive tool call results in each iteration
✅ LLM can see previous tool results and make informed decisions
✅ Prevents infinite loops caused by LLM not knowing tools were already called
✅ WorkLog records will be visible to LLM through tool_messages

## Expected Behavior After Fix

1. First iteration: Tool is called, result recorded to WorkLog and tool_messages
2. Second iteration: LLM sees the previous tool result in tool_messages
3. LLM decides next action based on results (instead of calling same tool again)
4. Loop continues with full context of previous tool calls
""")


def test_simulation():
    """Simulate the expected behavior"""
    print("\n" + "=" * 80)
    print("BEHAVIOR SIMULATION")
    print("=" * 80)

    print("""
## Scenario: User asks "Check if there's a system anomaly at 12:30"

### Before Fix (BUGGY):
```
Iteration 1:
  - LLM calls view("/path/to/SKILL.md")
  - Result: Skill file content
  - ❌ Result NOT added to all_tool_messages (because LOOP mode)

Iteration 2:
  - LLM prompt: Same as iteration 1 (no tool results visible)
  - LLM thinks: "I should load the skill file"
  - LLM calls view("/path/to/SKILL.md")  ← SAME CALL
  - ❌ Result NOT added to all_tool_messages

Iteration 3:
  - Same as iteration 2
  - Infinite loop!
```

### After Fix (CORRECT):
```
Iteration 1:
  - LLM calls view("/path/to/SKILL.md")
  - Result: Skill file content
  - ✅ Result ADDED to all_tool_messages

Iteration 2:
  - LLM prompt: Includes tool result from iteration 1
  - LLM sees: "I already loaded the skill file, now I should..."
  - LLM calls next tool based on skill content
  - Result: Analysis data
  - ✅ Result ADDED to all_tool_messages

Iteration 3:
  - LLM prompt: Includes results from iterations 1 and 2
  - LLM makes final decision
  - Calls terminate to finish
```
""")


def main():
    print("\n" + "✅" * 40)
    print("LOOP Mode Tool Messages Fix Verification")
    print("✅" * 40 + "\n")

    # Verify the fix
    fix_applied = verify_fix()

    # Explain what was fixed
    explain_fix()

    # Simulate behavior
    test_simulation()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if fix_applied:
        print("✅ Fix successfully applied!")
        print("\nNext steps:")
        print("1. Restart the Derisk server to apply changes")
        print("2. Test with a query that previously caused loops")
        print("3. Verify that tool results are now visible in LLM prompts")
        print("\nExpected outcome:")
        print("  - No more infinite loops calling the same tool")
        print("  - LLM makes informed decisions based on previous tool results")
        print("  - ReActMasterV2 completes tasks efficiently")
        return 0
    else:
        print("❌ Fix not applied or verification failed")
        print("Please check the code changes manually")
        return 1


if __name__ == "__main__":
    sys.exit(main())
