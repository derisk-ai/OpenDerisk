# ReActMasterV2 循环执行工具 Bug 修复报告

## 问题概述

ReActMasterV2 Agent 在执行过程中出现循环调用同一个工具的问题，导致任务无法正常完成。

### 现象

用户询问"今天12点30是否有系统异常"时，Agent 反复执行同一个工具调用：

```
view {"path": "/Users/tuyang/GitHub/OpenDerisk/pilot/data/skill/open_rca_diagnosis/SKILL.md"}
```

这个工具被调用了 3 次以上，形成无限循环。

## 根本原因

### 问题定位

在 `packages/derisk-core/src/derisk/agent/core/base_agent.py` 的 `generate_reply` 方法中（line 820-827），存在一个条件判断错误：

```python
if self.current_retry_counter > 0:
    if self.run_mode != AgentRunMode.LOOP:  # ❌ 问题所在
        if self.enable_function_call:
            tool_messages = self.function_callning_reply_messages(
                agent_llm_out, act_outs
            )
            all_tool_messages.extend(tool_messages)
```

### 问题分析

1. **ReActMasterV2 的运行模式**：
   - ReActMasterV2 使用 `AgentRunMode.LOOP` 模式
   - 这意味着它会循环执行多个迭代，直到任务完成

2. **Bug 的影响**：
   - 条件 `self.run_mode != AgentRunMode.LOOP` 导致 LOOP 模式的 Agent **不会**将工具调用结果追加到 `all_tool_messages`
   - 结果：LLM 在每次迭代时都看不到之前的工具调用结果
   - LLM 认为还没有调用过工具，于是再次调用同一个工具
   - 形成无限循环

3. **为什么 WorkLog 没起作用**：
   - WorkLog 确实记录了工具调用（通过 `_record_action_to_work_log`）
   - 但 WorkLog 的注入只在循环开始前执行一次（条件 `self.current_retry_counter == 0`）
   - 在 LOOP 模式的后续迭代中，WorkLog 不会被重新获取
   - 即使 WorkLog 记录了工具调用，它也不会被转换为 tool_messages 传给 LLM

## 修复方案

### 代码修改

移除 `self.run_mode != AgentRunMode.LOOP` 条件，让所有模式的 Agent 都能接收工具调用结果：

**修改前（BUGGY）**：
```python
if self.current_retry_counter > 0:
    if self.run_mode != AgentRunMode.LOOP:  # ❌ 移除这个条件
        if self.enable_function_call:
            tool_messages = self.function_callning_reply_messages(
                agent_llm_out, act_outs
            )
            all_tool_messages.extend(tool_messages)
```

**修改后（FIXED）**：
```python
if self.current_retry_counter > 0:
    if self.enable_function_call:  # ✅ 所有模式都执行
        tool_messages = self.function_callning_reply_messages(
            agent_llm_out, act_outs
        )
        all_tool_messages.extend(tool_messages)
```

### 修复文件

- **文件路径**：`packages/derisk-core/src/derisk/agent/core/base_agent.py`
- **修改行**：Line 821
- **修改类型**：移除条件判断

## 修复效果

### 修复前的行为

```
Iteration 1:
  - LLM 调用 view("/path/to/SKILL.md")
  - 结果：技能文件内容
  - ❌ 结果未添加到 all_tool_messages（因为是 LOOP 模式）

Iteration 2:
  - LLM prompt：与 iteration 1 相同（没有工具结果可见）
  - LLM 认为："我应该加载技能文件"
  - LLM 再次调用 view("/path/to/SKILL.md")  ← 相同调用
  - ❌ 结果未添加到 all_tool_messages

Iteration 3:
  - 与 iteration 2 相同
  - 无限循环！
```

### 修复后的行为

```
Iteration 1:
  - LLM 调用 view("/path/to/SKILL.md")
  - 结果：技能文件内容
  - ✅ 结果添加到 all_tool_messages

Iteration 2:
  - LLM prompt：包含 iteration 1 的工具结果
  - LLM 看到："我已经加载了技能文件，现在应该..."
  - LLM 根据技能内容调用下一个工具
  - 结果：分析数据
  - ✅ 结果添加到 all_tool_messages

Iteration 3:
  - LLM prompt：包含 iterations 1 和 2 的结果
  - LLM 做出最终决策
  - 调用 terminate 完成任务
```

## 验证

### 诊断脚本

创建了两个诊断脚本：

1. **`diagnose_loop_tool_messages.py`**：检测 bug 是否存在
2. **`verify_loop_fix.py`**：验证修复是否成功

### 验证结果

```bash
$ python3 verify_loop_fix.py

✅ FIX APPLIED: Buggy condition has been removed
✅ CORRECT CODE: Tool messages are now appended for all modes
```

## 影响范围

### 受影响的 Agent

- **ReActMasterV2**：主要受影响的 Agent
- **所有使用 AgentRunMode.LOOP 模式的 Agent**

### 受益的功能

- ✅ 工具调用结果现在能正确传递给 LLM
- ✅ LLM 能基于历史结果做出明智决策
- ✅ 防止因 LLM 不知道工具已调用而导致的无限循环
- ✅ WorkLog 记录现在能通过 tool_messages 对 LLM 可见

## 后续步骤

1. **重启服务器**：应用代码修改
2. **测试验证**：
   - 使用之前导致循环的查询进行测试
   - 验证工具结果现在在 LLM prompt 中可见
   - 确认任务能正常完成

3. **监控**：
   - 观察 ReActMasterV2 的执行日志
   - 确认不再出现重复工具调用
   - 验证任务完成效率提升

## 总结

这个 bug 是一个典型的"上下文丢失"问题：

- **症状**：Agent 循环调用同一个工具
- **根因**：LOOP 模式的 Agent 在迭代间丢失了工具调用结果
- **修复**：移除错误的条件判断，让所有模式都能接收工具结果
- **效果**：Agent 现在能基于历史结果做出正确决策，避免无限循环

修复后，ReActMasterV2 将能够：
- 正确执行多步骤任务
- 基于前序工具结果做决策
- 高效完成任务，不再陷入循环

---

**修复日期**：2026-03-09  
**修复文件**：`packages/derisk-core/src/derisk/agent/core/base_agent.py`  
**修复行数**：Line 821  
**修复类型**：移除条件判断 `self.run_mode != AgentRunMode.LOOP`