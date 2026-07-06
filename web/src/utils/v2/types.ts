/** V2 SSE event type definitions - matches Python v2_event_types.py / v2_vis_component.py / step_state.py */

/** V2 event type literal - mirrors Python V2EventType class constants. */
export type V2EventType =
  | 'step_start'
  | 'step_status'
  | 'llm_token'
  | 'tool_call'
  | 'tool_result'
  | 'interaction_request'
  | 'usage_metric'
  | 'sub_agent_start'
  | 'sub_agent_result'
  | 'step_end'
  | 'vis_update'
  | 'error'
  | 'done';

/** V2 SSE event shape - mirrors Python V2Event(dict). */
export interface V2Event {
  event: V2EventType;
  seq: number;
  ts: number;
  payload: Record<string, unknown>;
}

/** VIS operation type - mirrors Python VisOperationType enum values. */
export type VisOperationType = 'incr' | 'replace' | 'delete';

/** VIS component tag - mirrors Python VisComponentTag enum values. */
export type VisComponentTag =
  | 'message'
  | 'thinking'
  | 'tool_result'
  | 'step_status'
  | 'usage_display'
  | 'sub_agent_panel'
  | 'interaction_prompt'
  | 'error_block';

/** Simplified VIS component - mirrors Python SimplifiedVisComponent dataclass. */
export interface SimplifiedVisComponent {
  type: VisOperationType;
  uid: string;
  tag: VisComponentTag;
  content: string;
  meta?: Record<string, unknown>;
}

/** VIS component state (frontend-internal, after parser applies operations). */
export interface VisComponentState {
  uid: string;
  tag: VisComponentTag;
  content: string;
  meta?: Record<string, unknown>;
}

/** Step state - mirrors Python StepState enum values (lowercase). */
export type StepState =
  | 'init'
  | 'thinking'
  | 'acting'
  | 'observing'
  | 'awaiting_user'
  | 'awaiting_tool_permission'
  | 'awaiting_sub_agent'
  | 'done'
  | 'failed';
