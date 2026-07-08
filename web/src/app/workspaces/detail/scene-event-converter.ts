import type { AgentStep, AgentStepStatus, AgentStepType } from './agent-types';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { ManusLeftPanelData } from '@/types/manus';

const WORKSPACE_EVENT_TYPES = new Set<string>([
  'task_created',
  'context_loaded',
  'intervention_triggered',
  'artifact_produced',
  'delivery_sent',
  'asset_referenced',
]);

const AGENT_PROGRESS_TAGS = new Set<string>([
  'd-thinking',
  'drsk-thinking',
  'drsk-content',
  'd-tool',
  'drsk-step',
  'nex-step',
  'nex-steps',
  'drsk-steps',
  'd-work',
  'd-agent-plan',
  'd-system-events',
  'manus-right-panel',
]);

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function safeJsonParse<T = unknown>(input: string, fallback?: T): T | undefined {
  try {
    return JSON.parse(input) as T;
  } catch {
    return fallback;
  }
}

function toManusLeftPanelData(json: Record<string, unknown>): ManusLeftPanelData | undefined {
  if (Array.isArray(json.sections) && typeof json.is_working === 'boolean') {
    return json as unknown as ManusLeftPanelData;
  }
  return undefined;
}

function normalizeStatus(input?: string): AgentStepStatus {
  const s = String(input || '').toLowerCase();
  if (s === 'executing' || s === 'running' || s === 'pending_trigger' || s === 'awaiting_human' || s === 'thinking') return 'running';
  if (s === 'failed' || s === 'blocked' || s === 'error') return 'failed';
  if (s === 'complete' || s === 'finished' || s === 'done' || s === 'delivered' || s === 'closed' || s === 'completed' || s === 'success') return 'done';
  return 'pending';
}

function isWorkspaceEvent(obj: Record<string, unknown>): obj is { type: string; payload: Record<string, unknown> } {
  return typeof obj.type === 'string' && WORKSPACE_EVENT_TYPES.has(obj.type) && typeof obj.payload === 'object' && obj.payload !== null;
}

function isV2Event(obj: Record<string, unknown>): obj is { event: string; payload: Record<string, unknown> } {
  return typeof obj.event === 'string' && typeof obj.payload === 'object' && obj.payload !== null;
}

function extractVisBlocks(markdown: string): Array<{ tag: string; json: Record<string, unknown> }> {
  const blocks: Array<{ tag: string; json: Record<string, unknown> }> = [];
  const openRe = /```([\w-]+)/g;
  let match: RegExpExecArray | null;
  while ((match = openRe.exec(markdown)) !== null) {
    const tag = match[1];
    const contentStart = match.index + match[0].length;
    const closeRe = /```/g;
    closeRe.lastIndex = contentStart;
    let closeMatch: RegExpExecArray | null;
    let found = false;
    while ((closeMatch = closeRe.exec(markdown)) !== null) {
      const jsonText = markdown.slice(contentStart, closeMatch.index).trim();
      const parsed = safeJsonParse<Record<string, unknown>>(jsonText);
      if (parsed && typeof parsed === 'object') {
        blocks.push({ tag, json: parsed });
        openRe.lastIndex = closeMatch.index + 3;
        found = true;
        break;
      }
    }
    if (!found) {
      openRe.lastIndex = contentStart;
    }
  }
  return blocks;
}

export function extractAllVisBlocks(markdown: string): Array<{ tag: string; json: Record<string, unknown> }> {
  const blocks = extractVisBlocks(markdown);
  // Recursively extract blocks nested inside markdown fields (e.g. d-agent-plan.markdown)
  for (const block of blocks) {
    const nestedMarkdown = block.json.markdown;
    if (typeof nestedMarkdown === 'string' && nestedMarkdown.includes('```')) {
      blocks.push(...extractAllVisBlocks(nestedMarkdown));
    }
  }
  return blocks;
}

function tagToType(tag: string): AgentStepType | undefined {
  if (tag === 'd-thinking' || tag === 'drsk-thinking' || tag === 'drsk-content') return 'thinking';
  if (tag === 'd-tool' || tag === 'drsk-step' || tag === 'nex-step') return 'tool_call';
  if (tag === 'nex-steps' || tag === 'drsk-steps') return 'tool_call';
  if (tag === 'd-work' || tag === 'manus-right-panel') return 'status';
  if (tag === 'd-agent-plan') return 'planning';
  if (tag === 'd-system-events') return 'status';
  return undefined;
}

function eventToAgentStep(event: Record<string, unknown>): AgentStep | null {
  const eventId = String(event.event_id || event.id || makeId());
  const status = normalizeStatus(String(event.status || ''));
  const title = String(event.title || event.current_action || event.name || 'Agent event');
  const eventType = String(event.event_type || event.type || '');

  return {
    id: eventId,
    type: inferType({ ...event, tag: eventType }),
    title,
    status,
    timestamp: Date.now(),
    payload: event,
    content: typeof event.description === 'string' ? event.description : undefined,
    streaming: status === 'running',
  };
}

function systemEventsToSteps(json: Record<string, unknown>): AgentStep[] {
  const steps: AgentStep[] = [];

  if (typeof json.current_action === 'string') {
    steps.push({
      id: String(json.uid || makeId()),
      type: 'status',
      title: json.current_action,
      status: json.is_running === true ? 'running' : 'done',
      timestamp: Date.now(),
      payload: json,
      streaming: json.is_running === true,
    });
  }

  if (Array.isArray(json.recent_events)) {
    steps.push(
      ...json.recent_events
        .filter((event): event is Record<string, unknown> => event !== null && typeof event === 'object')
        .map(eventToAgentStep)
        .filter(Boolean) as AgentStep[]
    );
  }

  return steps;
}

function manusPanelToSteps(json: Record<string, unknown>): AgentStep[] {
  const steps: AgentStep[] = [];

  const activeStep = json.active_step;
  if (activeStep && typeof activeStep === 'object') {
    const step = activeStep as Record<string, unknown>;
    const status = normalizeStatus(String(step.status || ''));
    const actionInput = step.action_input;
    let args: Record<string, unknown> | undefined;
    if (typeof actionInput === 'string') {
      args = safeJsonParse<Record<string, unknown>>(actionInput);
    } else if (typeof actionInput === 'object' && actionInput !== null) {
      args = actionInput as Record<string, unknown>;
    }

    steps.push({
      id: String(step.id || makeId()),
      type: step.action || step.type ? 'tool_call' : 'status',
      title: String(step.title || step.action || step.subtitle || 'Agent step'),
      status,
      timestamp: Date.now(),
      payload: step,
      content: typeof step.subtitle === 'string' ? step.subtitle : undefined,
      tool: typeof step.action === 'string' ? step.action : undefined,
      args,
      streaming: status === 'running',
    });
  }

  if (Array.isArray(json.outputs)) {
    json.outputs
      .filter((output): output is Record<string, unknown> => output !== null && typeof output === 'object')
      .forEach((output, index) => {
        const outputId = String(output.id || `output-${index}`);
        steps.push({
          id: outputId,
          type: 'tool_result',
          title: String(output.output_type || 'Output'),
          status: 'done',
          timestamp: Date.now(),
          payload: output,
          result: output.content,
          streaming: false,
        });
      });
  }

  return steps;
}

function visBlockToSteps(tag: string, json: Record<string, unknown>): AgentStep[] {
  if (!AGENT_PROGRESS_TAGS.has(tag)) return [];

  const forcedType = tagToType(tag);

  if (tag === 'd-system-events') {
    return systemEventsToSteps(json);
  }

  if (tag === 'manus-right-panel') {
    return manusPanelToSteps(json);
  }

  if ((tag === 'nex-steps' || tag === 'drsk-steps') && Array.isArray(json.steps)) {
    return json.steps
      .filter((step): step is Record<string, unknown> => step !== null && typeof step === 'object')
      .map((step) => stepToAgentStep(step, forcedType))
      .filter(Boolean) as AgentStep[];
  }

  if (tag === 'd-work' && Array.isArray(json.items)) {
    return json.items
      .filter((item): item is Record<string, unknown> => item !== null && typeof item === 'object')
      .map((item) => itemToAgentStep(item, forcedType))
      .filter(Boolean) as AgentStep[];
  }

  return [stepToAgentStep(json, forcedType)].filter(Boolean) as AgentStep[];
}

function itemToAgentStep(item: Record<string, unknown>, forcedType?: AgentStepType): AgentStep | null {
  const status = normalizeStatus(String(item.status || item.item_status || ''));
  const title = String(item.title || item.tool_name || item.name || item.item_type || 'Agent step');
  const id = String(item.uid || item.path_uid || makeId());
  return {
    id,
    type: forcedType || inferType(item),
    title,
    status,
    timestamp: Date.now(),
    payload: item,
    content: typeof item.markdown === 'string' ? item.markdown : undefined,
    tool: typeof item.tool_name === 'string' ? item.tool_name : typeof item.name === 'string' ? item.name : undefined,
    streaming: status === 'running' && item.dynamic === true,
  };
}

function stepToAgentStep(step: Record<string, unknown>, forcedType?: AgentStepType): AgentStep | null {
  const status = normalizeStatus(String(step.status || step.state || ''));
  const title = String(
    step.tool_name || step.name || step.tool || step.title || step.tag || 'Agent step'
  );
  const id = String(step.uid || step.step_id || step.tool_call_id || step.event_id || makeId());
  const type = forcedType || inferType(step);

  return {
    id,
    type,
    title,
    status,
    timestamp: Date.now(),
    payload: step,
    content: typeof step.content === 'string'
      ? step.content
      : typeof step.markdown === 'string'
        ? step.markdown
          : typeof step.description === 'string'
            ? step.description
            : undefined,
    tool: typeof step.tool === 'string'
      ? step.tool
      : typeof step.tool_name === 'string'
        ? step.tool_name
          : typeof step.name === 'string'
            ? step.name
            : undefined,
    args: step.args && typeof step.args === 'object' ? (step.args as Record<string, unknown>) : undefined,
    result: step.result ?? step.output ?? undefined,
    error: typeof step.error === 'string' ? step.error : undefined,
    streaming: status === 'running' && (step.dynamic === true || step.type === 'incr'),
  };
}

function inferType(step: Record<string, unknown>): AgentStepType {
  if (step.tag === 'thinking' || step.type === 'thinking' || step.event_type === 'llm_thinking') return 'thinking';
  if (step.tag === 'tool_call' || step.tool_call_id || step.tool || step.tool_name || step.action) return 'tool_call';
  if (step.tag === 'tool_result' || step.output_type) return 'tool_result';
  if (step.tag === 'step_status' || step.state) return 'status';
  if (step.tag === 'plan' || step.type === 'plan' || step.item_type === 'agent') return 'planning';
  return 'unknown';
}

function v2EventToSteps(event: string, payload: Record<string, unknown>): AgentStep[] {
  switch (event) {
    case 'step_start': {
      const stepId = String(payload.step_id || makeId());
      return [
        {
          id: stepId,
          type: 'status',
          title: '开始思考',
          status: 'running',
          timestamp: payload.ts ? Number(payload.ts) : Date.now(),
          payload,
          streaming: true,
        },
      ];
    }
    case 'step_status': {
      const state = String(payload.state || '').toLowerCase();
      const isRunning = state === 'thinking' || state === 'running' || state === 'executing';
      return [
        {
          id: String(payload.step_id || makeId()),
          type: 'status',
          title: state === 'thinking' ? 'Agent 思考中...' : `状态: ${payload.state}`,
          status: isRunning ? 'running' : normalizeStatus(state),
          timestamp: payload.ts ? Number(payload.ts) : Date.now(),
          payload,
          streaming: isRunning,
        },
      ];
    }
    case 'llm_token': {
      return [
        {
          id: `llm-${payload.step_id || 'current'}`,
          type: 'thinking',
          title: '思考',
          status: 'running',
          timestamp: Date.now(),
          payload,
          content: String(payload.token || ''),
          streaming: true,
        },
      ];
    }
    case 'tool_call': {
      return [
        {
          id: String(payload.tool_call_id || makeId()),
          type: 'tool_call',
          title: `调用: ${payload.tool || 'tool'}`,
          status: 'running',
          timestamp: Date.now(),
          payload,
          tool: String(payload.tool || ''),
          args: payload.args && typeof payload.args === 'object' ? (payload.args as Record<string, unknown>) : undefined,
          streaming: true,
        },
      ];
    }
    case 'tool_result': {
      return [
        {
          id: String(payload.tool_call_id || makeId()),
          type: 'tool_result',
          title: '工具结果',
          status: payload.success === false ? 'failed' : 'done',
          timestamp: Date.now(),
          payload,
          result: payload.result,
          streaming: false,
        },
      ];
    }
    case 'vis_update': {
      const tag = String(payload.tag || '');
      if (AGENT_PROGRESS_TAGS.has(tag) || tag === 'thinking' || tag === 'tool_result' || tag === 'step_status') {
        return visBlockToSteps(tag === 'thinking' ? 'd-thinking' : tag === 'tool_result' ? 'd-tool' : tag, payload);
      }
      return [];
    }
    case 'step_end': {
      return [
        {
          id: String(payload.step_id || makeId()),
          type: 'status',
          title: payload.had_tool_calls ? '步骤完成（含工具调用）' : '步骤完成',
          status: 'done',
          timestamp: Date.now(),
          payload,
          streaming: false,
        },
      ];
    }
    default:
      return [];
  }
}

function parseWindowedVis(obj: Record<string, unknown>): { steps: AgentStep[]; leftPanelData?: ManusLeftPanelData } {
  const steps: AgentStep[] = [];
  let leftPanelData: ManusLeftPanelData | undefined;

  for (const windowKey of ['planning_window', 'running_window']) {
    const windowValue = obj[windowKey];
    if (typeof windowValue !== 'string') continue;

    const blocks = extractAllVisBlocks(windowValue);
    for (const block of blocks) {
      if (block.tag === 'manus-left-panel') {
        const parsed = toManusLeftPanelData(block.json);
        if (parsed) leftPanelData = parsed;
        continue;
      }
      steps.push(...visBlockToSteps(block.tag, block.json));
    }
  }

  return { steps, leftPanelData };
}

function objectToSteps(obj: Record<string, unknown>): { steps: AgentStep[]; workspaceEvent?: WorkspaceEvent; leftPanelData?: ManusLeftPanelData } {
  if (isWorkspaceEvent(obj)) {
    return {
      steps: [],
      workspaceEvent: { type: obj.type as WorkspaceEvent['type'], payload: obj.payload },
    };
  }

  if (isV2Event(obj)) {
    return { steps: v2EventToSteps(obj.event, obj.payload) };
  }

  // Windowed VIS format: {"planning_window": "...", "running_window": "..."}
  if (typeof obj.planning_window === 'string' || typeof obj.running_window === 'string') {
    return parseWindowedVis(obj);
  }

  if (typeof obj.type === 'string') {
    if (WORKSPACE_EVENT_TYPES.has(obj.type)) {
      return {
        steps: [],
        workspaceEvent: { type: obj.type as WorkspaceEvent['type'], payload: (obj.payload as Record<string, unknown>) || {} },
      };
    }
    if (obj.type === 'step_list' && Array.isArray((obj.payload as Record<string, unknown>)?.steps)) {
      const payload = obj.payload as Record<string, unknown>;
      return {
        steps: (payload.steps as unknown[])
          .filter((step): step is Record<string, unknown> => step !== null && typeof step === 'object')
          .map((step) => stepToAgentStep(step))
          .filter(Boolean) as AgentStep[],
      };
    }
    // Plain VIS object (e.g. { type: 'd-thinking', ... })
    return { steps: visBlockToSteps(obj.type, obj) };
  }

  return { steps: [] };
}

function stringToSteps(input: string): { steps: AgentStep[]; workspaceEvent?: WorkspaceEvent; leftPanelData?: ManusLeftPanelData } {
  if (input === '[DONE]') return { steps: [] };

  const trimmed = input.trim();
  if (!trimmed) return { steps: [] };

  // Try parsing as JSON first (windowed VIS or event object)
  const parsed = safeJsonParse<Record<string, unknown>>(trimmed);
  if (parsed && typeof parsed === 'object') {
    return objectToSteps(parsed);
  }

  // Otherwise treat as VIS markdown and extract code blocks
  const blocks = extractAllVisBlocks(trimmed);
  const steps: AgentStep[] = [];
  let leftPanelData: ManusLeftPanelData | undefined;
  for (const block of blocks) {
    if (block.tag === 'manus-left-panel') {
      const parsed = toManusLeftPanelData(block.json);
      if (parsed) leftPanelData = parsed;
      continue;
    }
    steps.push(...visBlockToSteps(block.tag, block.json));
  }
  return { steps, leftPanelData };
}

export interface SceneEventResult {
  steps: AgentStep[];
  workspaceEvent?: WorkspaceEvent;
  leftPanelData?: ManusLeftPanelData;
  done?: boolean;
}

export function parseSceneEvent(message: unknown): SceneEventResult {
  if (typeof message === 'string') {
    if (message === '[DONE]') return { steps: [], done: true };
    return stringToSteps(message);
  }

  if (message && typeof message === 'object') {
    return objectToSteps(message as Record<string, unknown>);
  }

  return { steps: [] };
}

function mergeStep(existing: AgentStep, update: AgentStep): AgentStep {
  const next: AgentStep = { ...existing };

  if (update.status && update.status !== 'pending') {
    next.status = update.status;
  }

  if (update.title && update.title !== existing.title && update.title !== 'Agent step') {
    next.title = update.title;
  }

  if (update.type && update.type !== 'unknown') {
    next.type = update.type;
  }

  if (update.content) {
    if (existing.content && update.streaming) {
      next.content = existing.content + update.content;
    } else {
      next.content = update.content;
    }
  }

  if (update.tool) next.tool = update.tool;
  if (update.args) next.args = update.args;
  if (update.result !== undefined) next.result = update.result;
  if (update.error) next.error = update.error;
  if (update.streaming !== undefined) next.streaming = update.streaming;

  next.timestamp = update.timestamp;
  next.payload = { ...existing.payload, ...update.payload };

  return next;
}

export function reduceSceneSteps(prevSteps: AgentStep[], message: unknown): { steps: AgentStep[]; workspaceEvent?: WorkspaceEvent; leftPanelData?: ManusLeftPanelData; done?: boolean } {
  const { steps: incoming, workspaceEvent, leftPanelData, done } = parseSceneEvent(message);
  if (!incoming.length && !workspaceEvent && !leftPanelData && !done) {
    return { steps: prevSteps };
  }

  const stepMap = new Map<string, AgentStep>();
  for (const step of prevSteps) {
    stepMap.set(step.id, step);
  }

  for (const step of incoming) {
    const existing = stepMap.get(step.id);
    if (existing) {
      stepMap.set(step.id, mergeStep(existing, step));
    } else {
      stepMap.set(step.id, step);
    }
  }

  return {
    steps: Array.from(stepMap.values()),
    workspaceEvent,
    leftPanelData,
    done,
  };
}

export class SceneEventConverter {
  private steps: AgentStep[] = [];
  private leftPanelData?: ManusLeftPanelData;

  consume(message: unknown): SceneEventResult {
    const result = reduceSceneSteps(this.steps, message);
    this.steps = result.steps;
    if (result.leftPanelData) {
      this.leftPanelData = result.leftPanelData;
    }
    return { ...result, steps: this.steps, leftPanelData: this.leftPanelData };
  }

  finalize(): AgentStep[] {
    this.steps = this.steps.map((step) =>
      step.status === 'running' || step.streaming
        ? { ...step, status: 'done' as const, streaming: false }
        : step
    );
    return this.steps;
  }

  getSteps(): AgentStep[] {
    return this.steps;
  }

  getLeftPanelData(): ManusLeftPanelData | undefined {
    return this.leftPanelData;
  }

  clear(): void {
    this.steps = [];
    this.leftPanelData = undefined;
  }
}
