import { V2SimplifiedVisParser } from '../V2SimplifiedVisParser';
import { V2Event, SimplifiedVisComponent } from '../types';

describe('V2SimplifiedVisParser', () => {
  let parser: V2SimplifiedVisParser;

  beforeEach(() => {
    parser = new V2SimplifiedVisParser();
  });

  test('should handle vis_update incr event', () => {
    const event: V2Event = {
      event: 'vis_update',
      seq: 1,
      ts: 123456,
      payload: {
        type: 'incr',
        uid: 's1-thinking-0',
        tag: 'thinking',
        content: '你好',
      } as SimplifiedVisComponent,
    };

    parser.handleEvent(event);
    const components = parser.getComponents();

    expect(components.has('s1-thinking-0')).toBe(true);
    expect(components.get('s1-thinking-0')?.content).toBe('你好');
  });

  test('should accumulate content for incr events', () => {
    parser.handleEvent({
      event: 'vis_update',
      seq: 1,
      ts: 123456,
      payload: { type: 'incr', uid: 's1-thinking-0', tag: 'thinking', content: '你' },
    });
    parser.handleEvent({
      event: 'vis_update',
      seq: 2,
      ts: 123457,
      payload: { type: 'incr', uid: 's1-thinking-0', tag: 'thinking', content: '好' },
    });

    expect(parser.getComponents().get('s1-thinking-0')?.content).toBe('你好');
  });

  test('should replace content for replace events', () => {
    parser.handleEvent({
      event: 'vis_update',
      seq: 1,
      ts: 123456,
      payload: { type: 'replace', uid: 's1-step_status-0', tag: 'step_status', content: '', meta: { state: 'THINKING' } },
    });
    parser.handleEvent({
      event: 'vis_update',
      seq: 2,
      ts: 123457,
      payload: { type: 'replace', uid: 's1-step_status-0', tag: 'step_status', content: '', meta: { state: 'DONE' } },
    });

    expect(parser.getComponents().get('s1-step_status-0')?.meta?.state).toBe('DONE');
  });

  test('should delete component for delete events', () => {
    parser.handleEvent({
      event: 'vis_update',
      seq: 1,
      ts: 123456,
      payload: { type: 'incr', uid: 's1-temp-0', tag: 'message', content: 'temp' },
    });
    parser.handleEvent({
      event: 'vis_update',
      seq: 2,
      ts: 123457,
      payload: { type: 'delete', uid: 's1-temp-0', tag: 'message', content: '' },
    });

    expect(parser.getComponents().has('s1-temp-0')).toBe(false);
  });

  test('should group components by step', () => {
    parser.handleEvent({
      event: 'vis_update',
      seq: 1,
      ts: 123456,
      payload: { type: 'incr', uid: 's1-thinking-0', tag: 'thinking', content: '分析' },
    });
    parser.handleEvent({
      event: 'vis_update',
      seq: 2,
      ts: 123457,
      payload: { type: 'incr', uid: 's1-tool-echo-0', tag: 'tool_result', content: '结果' },
    });
    parser.handleEvent({
      event: 'vis_update',
      seq: 3,
      ts: 123458,
      payload: { type: 'incr', uid: 's2-thinking-0', tag: 'thinking', content: '继续' },
    });

    const groups = parser.groupByStep();
    expect(groups.get('s1')?.length).toBe(2);
    expect(groups.get('s2')?.length).toBe(1);
  });
});
