import type { AgentStep, AgentStepStatus, AgentStepType } from './agent-types';

const TYPE_LABELS: Record<string, string> = {
  task_created: 'Task created',
  context_loaded: 'Context loaded',
  tool_call: 'Tool call',
  intervention_triggered: 'Intervention triggered',
  artifact_produced: 'Artifact produced',
  delivery_sent: 'Delivery sent',
  asset_referenced: 'Asset referenced',
  llm: 'LLM',
  planning: 'Planning',
};

function normalizeStatus(input?: string): AgentStepStatus {
  const s = String(input || '').toLowerCase();
  if (s === 'executing' || s === 'running' || s === 'pending_trigger' || s === 'awaiting_human') return 'running';
  if (s === 'failed' || s === 'blocked') return 'failed';
  if (s === 'complete' || s === 'finished' || s === 'done' || s === 'delivered' || s === 'closed') return 'done';
  return 'pending';
}

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function parseAgentSteps(vis: unknown): AgentStep | null {
  if (!vis || typeof vis !== 'object') return null;
  const v = vis as Record<string, any>;
  const payload = v.payload || {};

  if (v.type === 'step_list' && Array.isArray(payload.steps) && payload.steps.length > 0) {
    const step = payload.steps[payload.steps.length - 1];
    return {
      id: makeId(),
      type: 'tool_call',
      title: step.tool_name || step.name || 'Tool call',
      status: normalizeStatus(step.status),
      timestamp: Date.now(),
      payload: step,
    };
  }

  const allowedTypes: AgentStepType[] = [
    'task_created',
    'context_loaded',
    'intervention_triggered',
    'artifact_produced',
    'delivery_sent',
    'asset_referenced',
  ];
  if (allowedTypes.includes(v.type)) {
    return {
      id: makeId(),
      type: v.type,
      title: TYPE_LABELS[v.type] || v.type,
      status: payload.status ? normalizeStatus(payload.status) : 'done',
      timestamp: Date.now(),
      payload,
    };
  }

  return null;
}
