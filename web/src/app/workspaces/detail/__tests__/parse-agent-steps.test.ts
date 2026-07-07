import { parseAgentSteps } from '../parse-agent-steps';

describe('parseAgentSteps', () => {
  test('returns null for non-object payload', () => {
    expect(parseAgentSteps(null)).toBeNull();
    expect(parseAgentSteps('string')).toBeNull();
  });

  test('parses workspace_event into AgentStep', () => {
    const vis = {
      type: 'task_created',
      payload: { task_id: 42, title: 'Refund check' },
    };
    const step = parseAgentSteps(vis);
    expect(step).not.toBeNull();
    expect(step?.type).toBe('task_created');
    expect(step?.title).toBe('Task created');
    expect(step?.status).toBe('done');
    expect(step?.payload?.task_id).toBe(42);
  });

  test('parses step_list item into AgentStep', () => {
    const vis = {
      type: 'step_list',
      payload: {
        steps: [
          { tool_name: 'query_db', status: 'EXECUTING' },
        ],
      },
    };
    const step = parseAgentSteps(vis);
    expect(step?.type).toBe('tool_call');
    expect(step?.title).toBe('query_db');
    expect(step?.status).toBe('running');
  });

  test('returns null for unknown vis type', () => {
    expect(parseAgentSteps({ type: 'unknown', payload: {} })).toBeNull();
  });
});
