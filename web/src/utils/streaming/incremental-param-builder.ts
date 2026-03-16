/**
 * Incremental Parameter Builder
 * 
 * Builds parameter values incrementally from streaming chunks.
 * Provides real-time state tracking and progress indication.
 */

import {
  StreamingEventType,
  StreamingMessage,
  ToolCallStartMessage,
  ToolCallEndMessage,
  ToolParamStartMessage,
  ToolParamChunkMessage,
  ToolParamEndMessage,
  ParamState,
  ToolCallState,
  BuilderEvent,
  EventListener,
} from './types';

/**
 * Incremental Parameter Builder
 * 
 * Receives streaming messages and builds parameter values incrementally.
 * 
 * Key Features:
 * - Incremental value construction
 * - Progress tracking
 * - Event-based updates
 * - Rollback support
 * 
 * Usage:
 * ```typescript
 * const builder = new IncrementalParamBuilder();
 * 
 * // Subscribe to events
 * builder.subscribe((event) => {
 *   if (event.type === 'param_progress') {
 *     console.log('Progress:', event.state);
 *   }
 * });
 * 
 * // Process messages
 * for (const message of sseMessages) {
 *   builder.processMessage(message);
 * }
 * 
 * // Get final value
 * const value = builder.getParamValue('call_123', 'content');
 * ```
 */
export class IncrementalParamBuilder {
  /** Active tool calls */
  private toolCalls: Map<string, ToolCallState> = new Map();
  
  /** Parameter states */
  private params: Map<string, ParamState> = new Map();
  
  /** Event listeners */
  private listeners: Set<EventListener> = new Set();
  
  /** History for rollback support */
  private history: Map<string, string[]> = new Map();
  
  /** Maximum history entries per parameter */
  private maxHistoryLength = 10;
  
  /**
   * Process a streaming message
   */
  processMessage(message: StreamingMessage): ParamState | ToolCallState | null {
    switch (message.type) {
      case StreamingEventType.TOOL_CALL_START:
        return this.handleToolCallStart(message as ToolCallStartMessage);
      
      case StreamingEventType.TOOL_CALL_END:
        return this.handleToolCallEnd(message as ToolCallEndMessage);
      
      case StreamingEventType.TOOL_PARAM_START:
        return this.handleParamStart(message as ToolParamStartMessage);
      
      case StreamingEventType.TOOL_PARAM_CHUNK:
        return this.handleParamChunk(message as ToolParamChunkMessage);
      
      case StreamingEventType.TOOL_PARAM_END:
        return this.handleParamEnd(message as ToolParamEndMessage);
      
      default:
        return null;
    }
  }
  
  /**
   * Handle tool call start
   */
  private handleToolCallStart(message: ToolCallStartMessage): ToolCallState {
    const state: ToolCallState = {
      callId: message.call_id,
      toolName: message.tool_name,
      params: new Map(),
      status: 'streaming',
      startTime: Date.now(),
    };
    
    this.toolCalls.set(message.call_id, state);
    
    this.emit({
      type: 'tool_start',
      callId: message.call_id,
      toolName: message.tool_name,
      state,
    });
    
    return state;
  }
  
  /**
   * Handle tool call end
   */
  private handleToolCallEnd(message: ToolCallEndMessage): ToolCallState | null {
    const state = this.toolCalls.get(message.call_id);
    
    if (!state) {
      return null;
    }
    
    state.status = 'completed';
    state.endTime = Date.now();
    
    this.emit({
      type: 'tool_complete',
      callId: message.call_id,
      toolName: message.tool_name,
      state,
    });
    
    return state;
  }
  
  /**
   * Handle parameter start
   */
  private handleParamStart(message: ToolParamStartMessage): ParamState {
    const key = this.getParamKey(message.call_id, message.param_name);
    
    const state: ParamState = {
      paramName: message.param_name,
      value: '',
      chunks: [],
      receivedChunks: 0,
      totalChunks: null,
      receivedBytes: 0,
      totalBytes: message.metadata?.estimated_size || null,
      isComplete: false,
      isStreaming: message.streaming,
      renderer: message.metadata?.renderer || 'default',
      startTime: Date.now(),
      lastUpdateTime: Date.now(),
    };
    
    this.params.set(key, state);
    this.history.set(key, []);
    
    // Update tool call state
    const toolCall = this.toolCalls.get(message.call_id);
    if (toolCall) {
      toolCall.params.set(message.param_name, state);
    }
    
    this.emit({
      type: 'param_start',
      callId: message.call_id,
      toolName: message.tool_name,
      paramName: message.param_name,
      state,
    });
    
    return state;
  }
  
  /**
   * Handle parameter chunk
   */
  private handleParamChunk(message: ToolParamChunkMessage): ParamState | null {
    const key = this.getParamKey(message.call_id, message.param_name);
    const state = this.params.get(key);
    
    if (!state) {
      console.warn(`[IncrementalParamBuilder] Param state not found: ${key}`);
      return null;
    }
    
    // Save history for rollback
    const history = this.history.get(key) || [];
    history.push(state.value);
    if (history.length > this.maxHistoryLength) {
      history.shift();
    }
    this.history.set(key, history);
    
    // Update value
    if (message.is_delta) {
      state.value += message.chunk_data;
    } else {
      state.value = message.chunk_data;
    }
    
    state.chunks.push(message.chunk_data);
    state.receivedChunks = (message.chunk_index || state.receivedChunks) + 1;
    state.receivedBytes = message.metadata?.bytes_received || state.value.length;
    state.totalBytes = message.metadata?.bytes_total || state.totalBytes;
    state.lastUpdateTime = Date.now();
    
    this.emit({
      type: 'param_progress',
      callId: message.call_id,
      toolName: message.tool_name,
      paramName: message.param_name,
      state,
      chunk: message.chunk_data,
    });
    
    return state;
  }
  
  /**
   * Handle parameter end
   */
  private handleParamEnd(message: ToolParamEndMessage): ParamState | null {
    const key = this.getParamKey(message.call_id, message.param_name);
    const state = this.params.get(key);
    
    if (!state) {
      return null;
    }
    
    state.isComplete = true;
    state.lastUpdateTime = Date.now();
    
    this.emit({
      type: 'param_complete',
      callId: message.call_id,
      toolName: message.tool_name,
      paramName: message.param_name,
      state,
    });
    
    return state;
  }
  
  /**
   * Get parameter key for storage
   */
  private getParamKey(callId: string, paramName: string): string {
    return `${callId}:${paramName}`;
  }
  
  /**
   * Get parameter state
   */
  getParamState(callId: string, paramName: string): ParamState | undefined {
    return this.params.get(this.getParamKey(callId, paramName));
  }
  
  /**
   * Get parameter value (may be incomplete)
   */
  getParamValue(callId: string, paramName: string): string | undefined {
    const state = this.getParamState(callId, paramName);
    return state?.value;
  }
  
  /**
   * Get tool call state
   */
  getToolCallState(callId: string): ToolCallState | undefined {
    return this.toolCalls.get(callId);
  }
  
  /**
   * Get progress percentage (0-1)
   */
  getProgress(callId: string, paramName: string): number {
    const state = this.getParamState(callId, paramName);
    
    if (!state) {
      return 0;
    }
    
    if (state.isComplete) {
      return 1;
    }
    
    if (state.totalBytes) {
      return state.receivedBytes / state.totalBytes;
    }
    
    if (state.totalChunks) {
      return state.receivedChunks / state.totalChunks;
    }
    
    // Can't determine progress
    return 0;
  }
  
  /**
   * Get streaming speed in bytes/second
   */
  getSpeed(callId: string, paramName: string): number {
    const state = this.getParamState(callId, paramName);
    
    if (!state || state.receivedBytes === 0) {
      return 0;
    }
    
    const elapsed = (Date.now() - state.startTime) / 1000;
    
    if (elapsed === 0) {
      return 0;
    }
    
    return state.receivedBytes / elapsed;
  }
  
  /**
   * Rollback to a previous chunk state
   */
  rollback(callId: string, paramName: string, chunkIndex: number): boolean {
    const key = this.getParamKey(callId, paramName);
    const state = this.params.get(key);
    const history = this.history.get(key);
    
    if (!state || !history || chunkIndex >= history.length) {
      return false;
    }
    
    state.value = history[chunkIndex];
    state.chunks = state.chunks.slice(0, chunkIndex + 1);
    state.receivedChunks = chunkIndex + 1;
    
    return true;
  }
  
  /**
   * Subscribe to events
   */
  subscribe(listener: EventListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  
  /**
   * Emit an event to all listeners
   */
  private emit(event: BuilderEvent): void {
    for (const listener of this.listeners) {
      try {
        listener(event);
      } catch (error) {
        console.error('[IncrementalParamBuilder] Listener error:', error);
      }
    }
  }
  
  /**
   * Clear state for a specific call or all
   */
  clear(callId?: string): void {
    if (callId) {
      // Clear specific call
      this.toolCalls.delete(callId);
      
      // Clear related params
      for (const key of this.params.keys()) {
        if (key.startsWith(callId)) {
          this.params.delete(key);
          this.history.delete(key);
        }
      }
    } else {
      // Clear all
      this.toolCalls.clear();
      this.params.clear();
      this.history.clear();
    }
  }
  
  /**
   * Get all active tool calls
   */
  getActiveToolCalls(): Map<string, ToolCallState> {
    return new Map(this.toolCalls);
  }
  
  /**
   * Get all parameters for a tool call
   */
  getParamsForCall(callId: string): Map<string, ParamState> {
    const result = new Map<string, ParamState>();
    
    for (const [key, state] of this.params) {
      if (key.startsWith(callId)) {
        result.set(state.paramName, state);
      }
    }
    
    return result;
  }
  
  /**
   * Check if a parameter is currently streaming
   */
  isStreaming(callId: string, paramName: string): boolean {
    const state = this.getParamState(callId, paramName);
    return state?.isStreaming && !state.isComplete;
  }
  
  /**
   * Get statistics about the builder
   */
  getStats(): {
    activeToolCalls: number;
    totalParams: number;
    streamingParams: number;
    completedParams: number;
  } {
    let streaming = 0;
    let completed = 0;
    
    for (const state of this.params.values()) {
      if (state.isComplete) {
        completed++;
      } else if (state.isStreaming) {
        streaming++;
      }
    }
    
    return {
      activeToolCalls: this.toolCalls.size,
      totalParams: this.params.size,
      streamingParams: streaming,
      completedParams: completed,
    };
  }
}

/**
 * Create a singleton instance for convenience
 */
let _defaultBuilder: IncrementalParamBuilder | null = null;

export function getDefaultBuilder(): IncrementalParamBuilder {
  if (!_defaultBuilder) {
    _defaultBuilder = new IncrementalParamBuilder();
  }
  return _defaultBuilder;
}

export function setDefaultBuilder(builder: IncrementalParamBuilder): void {
  _defaultBuilder = builder;
}