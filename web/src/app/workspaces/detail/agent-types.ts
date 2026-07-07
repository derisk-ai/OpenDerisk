export type AgentStepType =
  | 'task_created'
  | 'context_loaded'
  | 'tool_call'
  | 'intervention_triggered'
  | 'artifact_produced'
  | 'delivery_sent'
  | 'asset_referenced'
  | 'llm'
  | 'planning'
  | 'unknown';

export type AgentStepStatus = 'running' | 'done' | 'failed' | 'pending';

export interface AgentStep {
  id: string;
  type: AgentStepType;
  title: string;
  status: AgentStepStatus;
  timestamp: number;
  payload?: Record<string, any>;
}

export type DetailContext =
  | 'dashboard'
  | 'task-detail'
  | 'file-preview'
  | 'tool-result'
  | 'entity-card';
