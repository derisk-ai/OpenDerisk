/** V2 constants - mirrors Python v2_event_types.py module-level constants. */

import type { VisComponentTag, V2EventType } from './types';

/** Event type constants (SCREAMING_SNAKE → literal). */
export const EVENT_TYPES = {
  STEP_START: 'step_start',
  STEP_STATUS: 'step_status',
  LLM_TOKEN: 'llm_token',
  TOOL_CALL: 'tool_call',
  TOOL_RESULT: 'tool_result',
  INTERACTION_REQUEST: 'interaction_request',
  USAGE_METRIC: 'usage_metric',
  SUB_AGENT_START: 'sub_agent_start',
  SUB_AGENT_RESULT: 'sub_agent_result',
  STEP_END: 'step_end',
  VIS_UPDATE: 'vis_update',
  ERROR: 'error',
  DONE: 'done',
} as const satisfies Record<string, V2EventType>;

/** Component tag constants. */
export const COMPONENT_TAGS = {
  MESSAGE: 'message',
  THINKING: 'thinking',
  TOOL_RESULT: 'tool_result',
  STEP_STATUS: 'step_status',
  USAGE_DISPLAY: 'usage_display',
  SUB_AGENT_PANEL: 'sub_agent_panel',
  INTERACTION_PROMPT: 'interaction_prompt',
  ERROR_BLOCK: 'error_block',
} as const satisfies Record<string, VisComponentTag>;

/** UID segment separator (format: {step_id}-{component_type}-{index}). */
export const UID_SEPARATOR = '-';

/** Default max steps per conversation turn. */
export const DEFAULT_MAX_STEPS = 20;
