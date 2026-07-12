import { statusToTab, statusLabel } from '../scene-task-rail';

describe('statusToTab', () => {
  it('maps running variants to running tab', () => {
    expect(statusToTab('running')).toBe('running');
    expect(statusToTab('draft')).toBe('running');
    expect(statusToTab('pending_trigger')).toBe('running');
    expect(statusToTab('blocked')).toBe('running');
  });
  it('maps awaiting_human to awaiting tab', () => {
    expect(statusToTab('awaiting_human')).toBe('awaiting');
  });
  it('maps delivered/closed to done tab', () => {
    expect(statusToTab('delivered')).toBe('done');
    expect(statusToTab('closed')).toBe('done');
  });
  it('maps failed to failed tab', () => {
    expect(statusToTab('failed')).toBe('failed');
  });
  it('falls back to all', () => {
    expect(statusToTab('whatever')).toBe('all');
    expect(statusToTab(undefined)).toBe('all');
  });
});

describe('statusLabel', () => {
  it('returns 人话文案', () => {
    expect(statusLabel('running')).toBe('运行中');
    expect(statusLabel('awaiting_human')).toBe('待你介入');
    expect(statusLabel('delivered')).toBe('已交付');
    expect(statusLabel('failed')).toBe('失败');
  });
});