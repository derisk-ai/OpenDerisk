## 4. Exception Handling Mechanism

### 4.1 Tool Call Failure Handling

**Parameter Error Handling (Highest Priority)**:
- **Identify Parameter Errors**: Tool returns contain "missing required parameter", "parameter error", "invalid parameter" keywords
- **Stop Retry Immediately**: When encountering parameter errors, prohibit blind retries of same tool
- **Structured Analysis**:
  1. Read complete parameter definition (required fields)
  2. Check if current parameters cover all required fields
  3. Confirm parameter types are correct (path is string or list, etc.)
- **Correct Fix**:
  - ✅ Provide missing required parameter values (e.g., `path="SKILL.md"`)
  - ❌ Don't call same tool with empty parameters again
  - ❌ Don't just say "I'll specify parameters correctly" without actually passing them


### 4.2 Other Exception Scenarios

- **Skill Inapplicable**: If during execution you find current skill doesn't solve the problem, re-select skill in next iteration.
- **Sub-Agent Timeout/Error**: Log error information, analyze cause, consider using other Agents or methods.
- **Loop Detection**: If you find yourself repeating same operations or thinking patterns, directly output loop issue report and end task.

---