import {
  parseSceneEvent,
  reduceSceneSteps,
  SceneEventConverter,
} from '../scene-event-converter';

describe('parseSceneEvent', () => {
  test('returns empty for non-object non-string payloads', () => {
    expect(parseSceneEvent(null)).toEqual({ steps: [] });
    expect(parseSceneEvent(123)).toEqual({ steps: [] });
  });

  test('marks [DONE] as done', () => {
    expect(parseSceneEvent('[DONE]')).toEqual({ steps: [], done: true });
  });

  test('parses workspace event object', () => {
    const result = parseSceneEvent({
      type: 'task_created',
      payload: { task_id: 42, title: 'Refund check' },
    });
    expect(result.workspaceEvent).toEqual({
      type: 'task_created',
      payload: { task_id: 42, title: 'Refund check' },
    });
    expect(result.steps).toEqual([]);
  });

  test('parses V2 step_status event', () => {
    const result = parseSceneEvent({
      event: 'step_status',
      payload: { step_id: 's1', state: 'THINKING' },
    });
    expect(result.steps).toHaveLength(1);
    expect(result.steps[0].type).toBe('status');
    expect(result.steps[0].title).toBe('Agent 思考中...');
    expect(result.steps[0].status).toBe('running');
  });

  test('parses V2 llm_token as thinking content', () => {
    const result = parseSceneEvent({
      event: 'llm_token',
      payload: { token: 'hello' },
    });
    expect(result.steps[0].type).toBe('thinking');
    expect(result.steps[0].content).toBe('hello');
    expect(result.steps[0].streaming).toBe(true);
  });

  test('parses V2 tool_call event', () => {
    const result = parseSceneEvent({
      event: 'tool_call',
      payload: { tool: 'query_db', args: { sql: 'SELECT 1' }, tool_call_id: 'tc1' },
    });
    expect(result.steps[0].type).toBe('tool_call');
    expect(result.steps[0].tool).toBe('query_db');
    expect(result.steps[0].args).toEqual({ sql: 'SELECT 1' });
    expect(result.steps[0].status).toBe('running');
  });

  test('parses V2 tool_result event', () => {
    const result = parseSceneEvent({
      event: 'tool_result',
      payload: { tool_call_id: 'tc1', result: { rows: 1 }, success: true },
    });
    expect(result.steps[0].type).toBe('tool_result');
    expect(result.steps[0].result).toEqual({ rows: 1 });
    expect(result.steps[0].status).toBe('done');
  });

  test('parses V1 step_list object', () => {
    const result = parseSceneEvent({
      type: 'step_list',
      payload: {
        steps: [{ tool_name: 'query_db', status: 'EXECUTING' }],
      },
    });
    expect(result.steps).toHaveLength(1);
    expect(result.steps[0].type).toBe('tool_call');
    expect(result.steps[0].title).toBe('query_db');
    expect(result.steps[0].status).toBe('running');
  });

  test('parses V1 VIS markdown with d-thinking block', () => {
    const markdown = '```d-thinking\n{"uid":"t1","type":"incr","content":"thinking..."}\n```';
    const result = parseSceneEvent(markdown);
    expect(result.steps).toHaveLength(1);
    expect(result.steps[0].type).toBe('thinking');
    expect(result.steps[0].content).toBe('thinking...');
  });

  test('parses V1 VIS markdown with drsk-step block', () => {
    const markdown = '```drsk-step\n{"uid":"s1","tool_name":"query_db","status":"completed","output":"done"}\n```';
    const result = parseSceneEvent(markdown);
    expect(result.steps).toHaveLength(1);
    expect(result.steps[0].type).toBe('tool_call');
    expect(result.steps[0].status).toBe('done');
    expect(result.steps[0].result).toBe('done');
  });

  test('parses V1 VIS markdown with nex-steps block', () => {
    const markdown = '```nex-steps\n{"steps":[{"uid":"s1","tool_name":"search","status":"EXECUTING"}]}\n```';
    const result = parseSceneEvent(markdown);
    expect(result.steps).toHaveLength(1);
    expect(result.steps[0].title).toBe('search');
    expect(result.steps[0].status).toBe('running');
  });

  test('parses V1 VIS markdown with d-work block', () => {
    const markdown = '```d-work\n{"items":[{"uid":"i1","title":"Step 1","status":"running","markdown":"working"}]}\n```';
    const result = parseSceneEvent(markdown);
    expect(result.steps).toHaveLength(1);
    expect(result.steps[0].title).toBe('Step 1');
    expect(result.steps[0].content).toBe('working');
  });

  test('parses stringified JSON object', () => {
    const result = parseSceneEvent('{"event":"step_end","payload":{"step_id":"s1","had_tool_calls":true}}');
    expect(result.steps).toHaveLength(1);
    expect(result.steps[0].type).toBe('status');
    expect(result.steps[0].status).toBe('done');
  });

  test('parses windowed VIS format with planning_window and running_window', () => {
    const runningWindow = '```d-system-events\n{"current_action":"searching docs","recent_events":[{"event_id":"e1","event_type":"llm_thinking","description":"thinking..."}]}\n```\n```manus-right-panel\n{"active_step":{"id":"s1","action":"query_db","action_input":"{\\"sql\\":\\"SELECT 1\\"}","title":"Query DB","status":"executing"},"outputs":[{"id":"o1","output_type":"text","content":"done"}]}\n```';
    const result = parseSceneEvent({
      planning_window: '',
      running_window: runningWindow,
    });
    expect(result.steps.length).toBeGreaterThanOrEqual(2);
    const thinkingStep = result.steps.find((s) => s.type === 'thinking');
    expect(thinkingStep).toBeDefined();
    expect(thinkingStep?.title).toBe('Agent event');

    const toolStep = result.steps.find((s) => s.type === 'tool_call');
    expect(toolStep).toBeDefined();
    expect(toolStep?.tool).toBe('query_db');
    expect(toolStep?.args).toEqual({ sql: 'SELECT 1' });
  });

  test('parses d-agent-plan nested markdown', () => {
    const markdown = '```d-agent-plan\n{"markdown":"```d-thinking\\n{\\"uid\\":\\"t1\\",\\"type\\":\\"incr\\",\\"content\\":\\"planning...\\"}\\n```"}\n```';
    const result = parseSceneEvent(markdown);
    expect(result.steps).toHaveLength(2);
    expect(result.steps[0].type).toBe('planning');
    const thinkingStep = result.steps.find((s) => s.type === 'thinking');
    expect(thinkingStep).toBeDefined();
    expect(thinkingStep?.content).toBe('planning...');
  });

  test('parses real backend windowed VIS chunk', () => {
    const chunk = {
      planning_window:
        '```d-agent-plan\n{"uid":"p1","type":"incr","item_type":"agent","title":"当前空间都有啥","status":"running","markdown":"```drsk-content\\n{\\"uid\\":\\"t1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\\"我来查看\\\"}\\n```"}\n```\n```d-system-events\n{"uid":"se1","type":"incr","is_running":true,"current_action":"Main Agent 思考中...","recent_events":[{"event_id":"e1","event_type":"llm_thinking","title":"Main Agent 思考","status":"running"}]}\n```',
      running_window:
        '```manus-right-panel\n{"uid":"mrp1","type":"all","active_step":{"id":"s1","action":"query_db","action_input":"{\\"sql\\":\\"SELECT 1\\"}","title":"Query DB","status":"executing"},"outputs":[{"id":"o1","output_type":"text","content":"done"}],"is_running":true}\n```',
    };
    const result = parseSceneEvent(chunk);
    const thinkingStep = result.steps.find((s) => s.type === 'thinking' && s.content === '我来查看');
    expect(thinkingStep).toBeDefined();
    expect(thinkingStep?.content).toBe('我来查看');

    const statusStep = result.steps.find((s) => s.title === 'Main Agent 思考中...');
    expect(statusStep).toBeDefined();
    expect(statusStep?.status).toBe('running');

    const toolStep = result.steps.find((s) => s.type === 'tool_call');
    expect(toolStep).toBeDefined();
    expect(toolStep?.tool).toBe('query_db');
    expect(toolStep?.args).toEqual({ sql: 'SELECT 1' });

    const outputStep = result.steps.find((s) => s.type === 'tool_result');
    expect(outputStep).toBeDefined();
    expect(outputStep?.result).toBe('done');
  });
});

describe('reduceSceneSteps', () => {
  test('appends new steps', () => {
    const first = reduceSceneSteps([], {
      event: 'tool_call',
      payload: { tool_call_id: 'tc1', tool: 'search' },
    });
    expect(first.steps).toHaveLength(1);
    const second = reduceSceneSteps(first.steps, {
      event: 'tool_result',
      payload: { tool_call_id: 'tc1', result: 'ok', success: true },
    });
    expect(second.steps).toHaveLength(1);
    expect(second.steps[0].type).toBe('tool_result');
    expect(second.steps[0].status).toBe('done');
  });

  test('merges streaming thinking tokens', () => {
    const s1 = reduceSceneSteps([], {
      event: 'llm_token',
      payload: { token: '我' },
    });
    const s2 = reduceSceneSteps(s1.steps, {
      event: 'llm_token',
      payload: { token: '来' },
    });
    expect(s2.steps).toHaveLength(1);
    expect(s2.steps[0].content).toBe('我来');
  });

  test('updates status by step id', () => {
    const s1 = reduceSceneSteps([], {
      event: 'step_start',
      payload: { step_id: 's1' },
    });
    const s2 = reduceSceneSteps(s1.steps, {
      event: 'step_end',
      payload: { step_id: 's1', had_tool_calls: false },
    });
    expect(s2.steps).toHaveLength(1);
    expect(s2.steps[0].status).toBe('done');
  });
});

describe('SceneEventConverter', () => {
  test('consumes messages and keeps state', () => {
    const converter = new SceneEventConverter();
    converter.consume({ event: 'tool_call', payload: { tool_call_id: 'tc1', tool: 'search' } });
    converter.consume({ event: 'tool_result', payload: { tool_call_id: 'tc1', result: 'ok', success: true } });
    expect(converter.getSteps()).toHaveLength(1);
    expect(converter.getSteps()[0].status).toBe('done');
  });

  test('clear resets state', () => {
    const converter = new SceneEventConverter();
    converter.consume({ event: 'step_start', payload: { step_id: 's1' } });
    converter.clear();
    expect(converter.getSteps()).toEqual([]);
  });

  test('finalize marks running steps as done', () => {
    const converter = new SceneEventConverter();
    converter.consume({ event: 'tool_call', payload: { tool_call_id: 'tc1', tool: 'search' } });
    expect(converter.getSteps()[0].status).toBe('running');
    converter.finalize();
    expect(converter.getSteps()[0].status).toBe('done');
    expect(converter.getSteps()[0].streaming).toBe(false);
  });
});
