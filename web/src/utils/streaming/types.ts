/**
 * Streaming Function Call Types
 * 
 * Type definitions for streaming tool parameters during LLM function calls.
 */

/**
 * Message types for streaming function call events
 */
export enum StreamingEventType {
  // Tool call lifecycle
  TOOL_CALL_START = 'tool_call_start',
  TOOL_CALL_END = 'tool_call_end',
  
  // Parameter lifecycle
  TOOL_PARAM_START = 'tool_param_start',
  TOOL_PARAM_CHUNK = 'tool_param_chunk',
  TOOL_PARAM_END = 'tool_param_end',
  
  // Error
  TOOL_PARAM_ERROR = 'tool_param_error',
}

/**
 * Base message interface
 */
export interface BaseStreamingMessage {
  type: StreamingEventType;
  call_id: string;
  tool_name: string;
  timestamp?: number;
}

/**
 * Tool call start message
 */
export interface ToolCallStartMessage extends BaseStreamingMessage {
  type: StreamingEventType.TOOL_CALL_START;
}

/**
 * Tool call end message
 */
export interface ToolCallEndMessage extends BaseStreamingMessage {
  type: StreamingEventType.TOOL_CALL_END;
  params: Record<string, unknown>;
}

/**
 * Parameter start message
 */
export interface ToolParamStartMessage extends BaseStreamingMessage {
  type: StreamingEventType.TOOL_PARAM_START;
  param_name: string;
  streaming: boolean;
  metadata?: {
    estimated_size?: number;
    renderer?: string;
  };
}

/**
 * Parameter chunk message
 */
export interface ToolParamChunkMessage extends BaseStreamingMessage {
  type: StreamingEventType.TOOL_PARAM_CHUNK;
  param_name: string;
  chunk_data: string;
  is_delta: boolean;
  chunk_index?: number;
  metadata?: {
    bytes_received?: number;
    bytes_total?: number;
    is_final_chunk?: boolean;
  };
}

/**
 * Parameter end message
 */
export interface ToolParamEndMessage extends BaseStreamingMessage {
  type: StreamingEventType.TOOL_PARAM_END;
  param_name: string;
  length: number;
}

/**
 * Parameter error message
 */
export interface ToolParamErrorMessage extends BaseStreamingMessage {
  type: StreamingEventType.TOOL_PARAM_ERROR;
  param_name?: string;
  error: string;
}

/**
 * Union type for all streaming messages
 */
export type StreamingMessage =
  | ToolCallStartMessage
  | ToolCallEndMessage
  | ToolParamStartMessage
  | ToolParamChunkMessage
  | ToolParamEndMessage
  | ToolParamErrorMessage;

/**
 * Parameter state during streaming
 */
export interface ParamState {
  /** Parameter name */
  paramName: string;
  
  /** Current accumulated value */
  value: string;
  
  /** Individual chunks received */
  chunks: string[];
  
  /** Number of chunks received */
  receivedChunks: number;
  
  /** Total chunks expected (may be null if unknown) */
  totalChunks: number | null;
  
  /** Bytes received */
  receivedBytes: number;
  
  /** Total bytes expected (may be null if unknown) */
  totalBytes: number | null;
  
  /** Whether streaming is complete */
  isComplete: boolean;
  
  /** Whether this parameter should be rendered with streaming effect */
  isStreaming: boolean;
  
  /** Renderer hint */
  renderer: string;
  
  /** Timestamp when streaming started */
  startTime: number;
  
  /** Timestamp of last update */
  lastUpdateTime: number;
}

/**
 * Tool call state during streaming
 */
export interface ToolCallState {
  /** Call ID */
  callId: string;
  
  /** Tool name */
  toolName: string;
  
  /** Parameters being streamed */
  params: Map<string, ParamState>;
  
  /** Overall status */
  status: 'pending' | 'streaming' | 'completed' | 'error';
  
  /** Timestamp when call started */
  startTime: number;
  
  /** Timestamp when call ended */
  endTime?: number;
  
  /** Error message if failed */
  error?: string;
}

/**
 * Builder event types
 */
export type BuilderEventType = 
  | 'tool_start'
  | 'tool_progress'
  | 'tool_complete'
  | 'tool_error'
  | 'param_start'
  | 'param_progress'
  | 'param_complete'
  | 'param_error';

/**
 * Builder event
 */
export interface BuilderEvent {
  type: BuilderEventType;
  callId?: string;
  toolName?: string;
  paramName?: string;
  state?: ParamState | ToolCallState;
  chunk?: string;
  error?: string;
}

/**
 * Event listener type
 */
export type EventListener = (event: BuilderEvent) => void;

/**
 * Renderer props for streaming parameters
 */
export interface StreamingRendererProps {
  /** Parameter value (may be incomplete) */
  value: string;
  
  /** Progress percentage (0-1) */
  progress: number;
  
  /** Whether streaming is complete */
  isComplete: boolean;
  
  /** Bytes received */
  receivedBytes: number;
  
  /** Total bytes (may be null) */
  totalBytes: number | null;
  
  /** Streaming speed in bytes/second */
  speed?: number;
  
  /** Renderer hint from backend */
  renderer?: string;
  
  /** Tool name */
  toolName?: string;
  
  /** Parameter name */
  paramName?: string;
}

/**
 * Chunk strategy enum (mirrors backend)
 */
export enum ChunkStrategy {
  FIXED_SIZE = 'fixed_size',
  LINE_BASED = 'line_based',
  SEMANTIC = 'semantic',
  ADAPTIVE = 'adaptive',
}

/**
 * Streaming configuration
 */
export interface StreamingConfig {
  /** Character threshold for streaming */
  streamingThreshold: number;
  
  /** Default chunk strategy */
  defaultChunkStrategy: ChunkStrategy;
  
  /** Chunk size in characters */
  chunkSize: number;
  
  /** Prefer line boundaries for chunks */
  chunkByLine: boolean;
  
  /** Maximum buffer size in bytes */
  maxBufferSize: number;
  
  /** Enable virtual scrolling for large content */
  enableVirtualScroll: boolean;
  
  /** Line threshold for virtual scrolling */
  virtualScrollThreshold: number;
}

/**
 * Default streaming configuration
 */
export const DEFAULT_STREAMING_CONFIG: StreamingConfig = {
  streamingThreshold: 256,
  defaultChunkStrategy: ChunkStrategy.ADAPTIVE,
  chunkSize: 100,
  chunkByLine: true,
  maxBufferSize: 10 * 1024 * 1024, // 10MB
  enableVirtualScroll: true,
  virtualScrollThreshold: 1000, // 1000 lines
};