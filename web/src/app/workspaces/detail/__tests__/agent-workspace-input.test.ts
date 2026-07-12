import { canSendSceneTask } from '../agent-workspace-input';

const pb = { playbook_id: 1, playbook_name: '容量巡检' };

describe('canSendSceneTask', () => {
  it('allows send with text and no playbook', () => {
    expect(canSendSceneTask('hello', false, null)).toBe(true);
  });
  it('allows send with resources only and no playbook', () => {
    expect(canSendSceneTask('', true, null)).toBe(true);
  });
  it('blocks send with empty text and no resources and no playbook', () => {
    expect(canSendSceneTask('   ', false, null)).toBe(false);
  });
  it('blocks send when playbook chosen but text empty', () => {
    expect(canSendSceneTask('', false, pb)).toBe(false);
    expect(canSendSceneTask('   ', true, pb)).toBe(false);
  });
  it('allows send when playbook chosen and text present', () => {
    expect(canSendSceneTask('生成本周巡检', false, pb)).toBe(true);
  });
});