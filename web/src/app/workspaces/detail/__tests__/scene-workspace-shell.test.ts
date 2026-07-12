import { hasActiveTask } from '../scene-workspace-shell';

describe('hasActiveTask', () => {
  it('returns true when any task is running/awaiting/draft/etc', () => {
    expect(hasActiveTask([{ status: 'running' }])).toBe(true);
    expect(hasActiveTask([{ status: 'awaiting_human' }])).toBe(true);
    expect(hasActiveTask([{ status: 'draft' }])).toBe(true);
    expect(hasActiveTask([{ status: 'delivered' }, { status: 'running' }])).toBe(true);
  });
  it('returns false when all tasks are terminal', () => {
    expect(hasActiveTask([{ status: 'delivered' }])).toBe(false);
    expect(hasActiveTask([{ status: 'closed' }, { status: 'failed' }])).toBe(false);
  });
  it('returns false on empty', () => {
    expect(hasActiveTask([])).toBe(false);
    expect(hasActiveTask(null as any)).toBe(false);
  });
});