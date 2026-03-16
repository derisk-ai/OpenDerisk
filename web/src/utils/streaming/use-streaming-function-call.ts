/**
 * useStreamingFunctionCall Hook
 * 
 * React hook for handling streaming function call parameters.
 * Provides state management and real-time updates for streaming tools.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { IncrementalParamBuilder } from './incremental-param-builder';
import {
  StreamingMessage,
  StreamingEventType,
  ParamState,
  ToolCallState,
  DEFAULT_STREAMING_CONFIG,
  StreamingConfig,
} from './types';

/**
 * Hook options
 */
export interface UseStreamingFunctionCallOptions {
  /** Streaming configuration */
  config?: Partial<StreamingConfig>;
  
  /** Callback when tool call starts */
  onToolStart?: (callId: string, toolName: string) => void;
  
  /** Callback when parameter chunk is received */
  onParamChunk?: (callId: string, paramName: string, chunk: string) => void;
  
  /** Callback when tool call ends */
  onToolEnd?: (callId: string, toolName: string, params: Record<string, unknown>) => void;
  
  /** Callback on error */
  onError?: (error: string) => void;
}

/**
 * Hook return type
 */
export interface UseStreamingFunctionCallReturn {
  /** Active tool calls */
  toolCalls: Map<string, ToolCallState>;
  
  /** Streaming parameters state */
  streamingParams: Map<string, ParamState>;
  
  /** Incremental builder instance */
  builder: IncrementalParamBuilder;
  
  /** Handle incoming SSE message */
  handleMessage: (message: StreamingMessage) => void;
  
  /** Get progress for a parameter */
  getProgress: (callId: string, paramName: string) => number;
  
  /** Get current value for a parameter */
  getParamValue: (callId: string, paramName: string) => string | undefined;
  
  /** Get streaming speed */
  getSpeed: (callId: string, paramName: string) => number;
  
  /** Check if streaming is active */
  isStreaming: boolean;
  
  /** Clear all state */
  clear: (callId?: string) => void;
  
  /** Current streaming stats */
  stats: {
    activeToolCalls: number;
    totalParams: number;
    streamingParams: number;
    completedParams: number;
  };
}

/**
 * useStreamingFunctionCall Hook
 * 
 * Manages streaming function call state and provides utilities
 * for real-time parameter rendering.
 * 
 * Usage:
 * ```tsx
 * function MyComponent() {
 *   const {
 *     toolCalls,
 *     streamingParams,
 *     handleMessage,
 *     getProgress,
 *     isStreaming,
 *   } = useStreamingFunctionCall({
 *     onParamChunk: (callId, paramName, chunk) => {
 *       console.log('Received chunk:', chunk);
 *     },
 *   });
 *   
 *   // Handle SSE messages
 *   useEffect(() => {
 *     const eventSource = new EventSource('/api/stream');
 *     eventSource.onmessage = (event) => {
 *       const message = JSON.parse(event.data);
 *       handleMessage(message);
 *     };
 *     return () => eventSource.close();
 *   }, [handleMessage]);
 *   
 *   return (
 *     <div>
 *       {isStreaming && <Spinner />}
 *       {/* Render streaming params */}
 *     </div>
 *   );
 * }
 * ```
 */
export function useStreamingFunctionCall(
  options: UseStreamingFunctionCallOptions = {}
): UseStreamingFunctionCallReturn {
  const {
    onToolStart,
    onParamChunk,
    onToolEnd,
    onError,
  } = options;
  
  // Builder instance
  const builderRef = useRef<IncrementalParamBuilder>(
    new IncrementalParamBuilder()
  );
  
  // State
  const [toolCalls, setToolCalls] = useState<Map<string, ToolCallState>>(new Map());
  const [streamingParams, setStreamingParams] = useState<Map<string, ParamState>>(new Map());
  const [stats, setStats] = useState({
    activeToolCalls: 0,
    totalParams: 0,
    streamingParams: 0,
    completedParams: 0,
  });
  
  // Update stats when state changes
  const updateStats = useCallback(() => {
    const newStats = builderRef.current.getStats();
    setStats(newStats);
  }, []);
  
  // Handle incoming message
  const handleMessage = useCallback((message: StreamingMessage) => {
    const builder = builderRef.current;
    
    // Process message
    const result = builder.processMessage(message);
    
    // Update state based on message type
    switch (message.type) {
      case StreamingEventType.TOOL_CALL_START:
        setToolCalls(new Map(builder.getActiveToolCalls()));
        if (onToolStart) {
          onToolStart(message.call_id, message.tool_name);
        }
        break;
      
      case StreamingEventType.TOOL_CALL_END:
        setToolCalls(new Map(builder.getActiveToolCalls()));
        if (onToolEnd) {
          onToolEnd(message.call_id, message.tool_name, message.params);
        }
        break;
      
      case StreamingEventType.TOOL_PARAM_START:
      case StreamingEventType.TOOL_PARAM_CHUNK:
      case StreamingEventType.TOOL_PARAM_END:
        // Update streaming params
        if (message.param_name) {
          const state = builder.getParamState(message.call_id, message.param_name);
          if (state) {
            setStreamingParams(prev => {
              const next = new Map(prev);
              next.set(`${message.call_id}:${message.param_name}`, state);
              return next;
            });
          }
        }
        
        if (message.type === StreamingEventType.TOOL_PARAM_CHUNK && onParamChunk) {
          onParamChunk(message.call_id, message.param_name!, message.chunk_data);
        }
        break;
      
      case StreamingEventType.TOOL_PARAM_ERROR:
        if (onError) {
          onError(message.error);
        }
        break;
    }
    
    updateStats();
  }, [onToolStart, onParamChunk, onToolEnd, onError, updateStats]);
  
  // Get progress
  const getProgress = useCallback((callId: string, paramName: string): number => {
    return builderRef.current.getProgress(callId, paramName);
  }, []);
  
  // Get param value
  const getParamValue = useCallback((callId: string, paramName: string): string | undefined => {
    return builderRef.current.getParamValue(callId, paramName);
  }, []);
  
  // Get speed
  const getSpeed = useCallback((callId: string, paramName: string): number => {
    return builderRef.current.getSpeed(callId, paramName);
  }, []);
  
  // Check if streaming
  const isStreaming = stats.streamingParams > 0;
  
  // Clear state
  const clear = useCallback((callId?: string) => {
    builderRef.current.clear(callId);
    setToolCalls(new Map(builderRef.current.getActiveToolCalls()));
    setStreamingParams(new Map());
    updateStats();
  }, [updateStats]);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      builderRef.current.clear();
    };
  }, []);
  
  return {
    toolCalls,
    streamingParams,
    builder: builderRef.current,
    handleMessage,
    getProgress,
    getParamValue,
    getSpeed,
    isStreaming,
    clear,
    stats,
  };
}

/**
 * useStreamingParam Hook
 * 
 * Simplified hook for tracking a single streaming parameter.
 * 
 * Usage:
 * ```tsx
 * function CodePreview({ callId, paramName }) {
 *   const { value, progress, isComplete } = useStreamingParam(callId, paramName);
 *   
 *   return (
 *     <div>
 *       <pre>{value}</pre>
 *       {!isComplete && <ProgressBar value={progress} />}
 *     </div>
 *   );
 * }
 * ```
 */
export function useStreamingParam(
  callId: string,
  paramName: string,
  builder?: IncrementalParamBuilder
): {
  value: string;
  progress: number;
  isComplete: boolean;
  speed: number;
  state: ParamState | null;
} {
  const builderRef = useRef<IncrementalParamBuilder>(
    builder || new IncrementalParamBuilder()
  );
  
  const [state, setState] = useState<ParamState | null>(null);
  
  useEffect(() => {
    const unsubscribe = builderRef.current.subscribe((event) => {
      if (event.callId === callId && event.paramName === paramName) {
        const newState = builderRef.current.getParamState(callId, paramName);
        setState(newState);
      }
    });
    
    // Get initial state
    const initialState = builderRef.current.getParamState(callId, paramName);
    if (initialState) {
      setState(initialState);
    }
    
    return unsubscribe;
  }, [callId, paramName]);
  
  return {
    value: state?.value || '',
    progress: state ? builderRef.current.getProgress(callId, paramName) : 0,
    isComplete: state?.isComplete || false,
    speed: state ? builderRef.current.getSpeed(callId, paramName) : 0,
    state,
  };
}

export default useStreamingFunctionCall;