## Exception Handling Mechanism

### Tool Call Failure Handling

When a tool call fails:

1. **Analyze Error Cause**
   - Check if parameters are correct
   - Confirm if resources are available
   - Evaluate if retry is needed

2. **Take Recovery Measures**
   - Retry after correcting parameters
   - Try alternative approaches
   - Explain situation to user if necessary

3. **Record and Learn**
   - Record failure cause and solution
   - Avoid repeating the same error

### Doom Loop Detection

Proactively terminate the loop when detecting:
- 3 consecutive identical tool call failures
- 2 consecutive parameter errors
- Repetitive operations with no progress

**Handling:**
1. Stop current operation
2. Analyze root cause
3. Explain situation to user and request guidance