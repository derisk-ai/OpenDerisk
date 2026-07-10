import type { WorkspaceExecutionStep, WorkspaceView } from './agent-workspace-types';

const VALID_TYPES = ['tool_call', 'thinking', 'artifact', 'delivery'];
const VALID_STATUS = ['running', 'done', 'failed'];

function normalizeStep(raw: unknown): WorkspaceExecutionStep | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.id !== 'string' || typeof r.title !== 'string') return null;
  const type = VALID_TYPES.includes(r.type as string) ? (r.type as WorkspaceExecutionStep['type']) : 'tool_call';
  const status = VALID_STATUS.includes(r.status as string) ? (r.status as WorkspaceExecutionStep['status']) : 'running';
  return {
    id: r.id,
    type,
    title: r.title,
    status,
    action: typeof r.action === 'string' ? r.action : null,
    action_input: r.action_input && typeof r.action_input === 'object' ? (r.action_input as Record<string, unknown>) : null,
    output: typeof r.output === 'string' ? r.output : null,
    artifact: r.artifact && typeof r.artifact === 'object' ? (r.artifact as WorkspaceExecutionStep['artifact']) : null,
    vis: r.vis ?? null,
  };
}

export function parseWorkspaceView(chunk: unknown, prev: WorkspaceView | null): WorkspaceView {
  if (!chunk || typeof chunk !== 'object') return prev ?? { planning: null, execution: [], summary: null };
  const c = chunk as Record<string, unknown>;
  if (!Array.isArray(c.execution)) return prev ?? { planning: null, execution: [], summary: null };

  const prevById = new Map((prev?.execution ?? []).map(e => [e.id, e]));
  const execution: WorkspaceExecutionStep[] = [];
  for (const raw of c.execution) {
    const step = normalizeStep(raw);
    if (!step) continue;
    const existing = prevById.get(step.id);
    execution.push(existing ? { ...existing, ...step } : step);
    prevById.delete(step.id);
  }
  // 保留 prev 中未被本 chunk 覆盖的旧步骤(已完成的)
  for (const leftover of prevById.values()) {
    execution.push(leftover);
  }

  const planning = c.planning && typeof c.planning === 'object'
    ? (c.planning as WorkspaceView['planning'])
    : (prev?.planning ?? null);
  const summary = typeof c.summary === 'string' ? c.summary : (prev?.summary ?? null);

  return { planning, execution, summary };
}