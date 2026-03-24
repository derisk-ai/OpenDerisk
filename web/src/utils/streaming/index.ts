/**
 * Streaming Function Call Module
 * 
 * Provides real-time parameter streaming for LLM function calls.
 * 
 * Key Features:
 * - Incremental parameter parsing
 * - Real-time rendering with typewriter effect
 * - Progress tracking
 * - Multiple renderers (code, text, generic)
 * 
 * @example
 * ```tsx
 * import { 
 *   useStreamingFunctionCall,
 *   StreamingParamRenderer,
 *   IncrementalParamBuilder,
 * } from '@/utils/streaming';
 * 
 * function MyComponent() {
 *   const { handleMessage, streamingParams, isStreaming } = useStreamingFunctionCall();
 *   
 *   // Handle SSE messages
 *   useEffect(() => {
 *     // Connect to SSE and call handleMessage
 *   }, []);
 *   
 *   return (
 *     <div>
 *       {Array.from(streamingParams.entries()).map(([key, state]) => (
 *         <StreamingParamRenderer
 *           key={key}
 *           callId={state.callId}
 *           paramName={state.paramName}
 *           builder={builder}
 *         />
 *       ))}
 *     </div>
 *   );
 * }
 * ```
 */

// Types
export {
  StreamingEventType,
  BaseStreamingMessage,
  ToolCallStartMessage,
  ToolCallEndMessage,
  ToolParamStartMessage,
  ToolParamChunkMessage,
  ToolParamEndMessage,
  ToolParamErrorMessage,
  StreamingMessage,
  ParamState,
  ToolCallState,
  BuilderEventType,
  BuilderEvent,
  EventListener,
  StreamingRendererProps,
  ChunkStrategy,
  StreamingConfig,
  DEFAULT_STREAMING_CONFIG,
} from './types';

// Incremental Builder
export {
  IncrementalParamBuilder,
  getDefaultBuilder,
  setDefaultBuilder,
} from './incremental-param-builder';

// Renderers
export {
  CodeRenderer,
  TextRenderer,
  GenericRenderer,
  StreamingParamRenderer,
  RendererRegistry,
  rendererRegistry,
  type IRenderer,
} from './streaming-renderer';

// Hooks
export {
  useStreamingFunctionCall,
  useStreamingParam,
  type UseStreamingFunctionCallOptions,
  type UseStreamingFunctionCallReturn,
} from './use-streaming-function-call';

// Re-export commonly used types
export type { 
  StreamingRendererProps as StreamingProps 
} from './types';