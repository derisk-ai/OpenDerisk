/**
 * Core_v2 Agent 前端类型定义
 */

// ========== Agent 相关 ==========

export type AgentMode = 'primary' | 'planner' | 'worker';

export interface V2AgentInfo {
  name: string;
  mode: AgentMode;
  description?: string;
  max_steps: number;
  timeout: number;
  permission: Record<string, string>;
  color?: string;
}

// ========== Session 相关 ==========

export type RuntimeState = 'idle' | 'running' | 'paused' | 'error' | 'terminated';

export interface V2Session {
  session_id: string;
  conv_id: string;
  user_id?: string;
  agent_name: string;
  created_at: string;
  last_active: string;
  state: RuntimeState;
  message_count: number;
}

export interface CreateSessionParams {
  user_id?: string;
  agent_name: string;
}

// ========== 消息相关 ==========

export type ChunkType = 'response' | 'thinking' | 'tool_call' | 'error' | 'warning';

export interface V2StreamChunk {
  type: ChunkType;
  content: string;
  metadata: Record<string, any>;
  is_final: boolean;
}

export interface ChatParams {
  message: string;
  session_id?: string;
  agent_name?: string;
}

// ========== Canvas Block 相关 ==========

export type BlockType = 
  | 'thinking' 
  | 'tool_call' 
  | 'message' 
  | 'task' 
  | 'plan' 
  | 'error' 
  | 'code' 
  | 'chart';

export interface CanvasBlock {
  block_id: string;
  block_type: BlockType;
  content: any;
  title?: string;
  metadata: Record<string, any>;
}

// ========== Progress 相关 ==========

export type ProgressType = 
  | 'thinking' 
  | 'tool_execution' 
  | 'subagent' 
  | 'error' 
  | 'success' 
  | 'warning' 
  | 'info';

export interface ProgressEvent {
  type: ProgressType;
  session_id: string;
  message: string;
  details: Record<string, any>;
  percent?: number;
  timestamp: string;
}

// ========== 状态相关 ==========

export interface V2RuntimeStatus {
  state: RuntimeState;
  total_sessions: number;
  running_sessions: number;
  registered_agents: string[];
  config: {
    max_concurrent_sessions: number;
    session_timeout: number;
    enable_streaming: boolean;
  };
}

// ========== 应用集成相关 ==========

export interface V2AgentTemplate {
  id: string;
  name: string;
  description: string;
  mode: AgentMode;
  tools: string[];
  permission: Record<string, string>;
  icon?: string;
  category: string;
}

export interface V2AppConfig {
  app_code: string;
  app_name: string;
  agent_mode: AgentMode;
  tools: string[];
  permission: Record<string, string>;
  max_steps: number;
  enable_canvas: boolean;
  enable_progress: boolean;
}
