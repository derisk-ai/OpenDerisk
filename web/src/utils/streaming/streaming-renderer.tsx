/**
 * Streaming Parameter Renderers
 * 
 * Provides renderers for streaming parameters with real-time updates.
 * Supports code, text, and generic content with typewriter effects.
 */

import React, { useMemo, useEffect, useRef, useState } from 'react';

import type { StreamingRendererProps } from './types';

/**
 * Format bytes to human-readable string
 */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Format speed to human-readable string
 */
function formatSpeed(bytesPerSec: number): string {
  return `${formatBytes(bytesPerSec)}/s`;
}

// ============================================================
// Code Renderer - For code content with syntax awareness
// ============================================================

interface CodeRendererProps extends StreamingRendererProps {
  language?: string;
  showLineNumbers?: boolean;
  maxPreviewLines?: number;
}

/**
 * Code Renderer
 * 
 * Renders code content with streaming effect.
 * Shows line numbers and highlights the streaming cursor.
 */
export const CodeRenderer: React.FC<CodeRendererProps> = ({
  value,
  progress,
  isComplete,
  speed,
  language,
  showLineNumbers = true,
  maxPreviewLines,
}) => {
  const lines = useMemo(() => value.split('\n'), [value]);
  const lineCount = lines.length;
  
  // Apply max preview limit if specified
  const displayLines = useMemo(() => {
    if (maxPreviewLines && lineCount > maxPreviewLines) {
      return lines.slice(-maxPreviewLines);
    }
    return lines;
  }, [lines, maxPreviewLines, lineCount]);
  
  const isTruncated = maxPreviewLines && lineCount > maxPreviewLines;
  
  return (
    <div className="streaming-code-container">
      {/* Header */}
      <div className="streaming-code-header">
        <span className="line-count">
          {lineCount} lines
          {isTruncated && ` (showing last ${maxPreviewLines})`}
        </span>
        {!isComplete && (
          <span className="streaming-indicator">
            Streaming... {Math.round(progress * 100)}%
          </span>
        )}
        {speed !== undefined && speed > 0 && (
          <span className="speed">{formatSpeed(speed)}</span>
        )}
        {language && <span className="language">{language}</span>}
      </div>
      
      {/* Code content */}
      <pre className="streaming-code-content">
        <code>
          {showLineNumbers && (
            <div className="line-numbers">
              {displayLines.map((_, i) => (
                <div key={i} className="line-number">
                  {isTruncated ? lineCount - displayLines.length + i + 1 : i + 1}
                </div>
              ))}
            </div>
          )}
          <div className="code-lines">
            {displayLines.map((line, i) => (
              <div key={i} className="code-line">
                <span className="line-content">{line}</span>
                {i === displayLines.length - 1 && !isComplete && (
                  <span className="streaming-cursor">▊</span>
                )}
              </div>
            ))}
          </div>
        </code>
      </pre>
      
      {/* Progress bar */}
      {!isComplete && (
        <div className="progress-bar">
          <div 
            className="progress-fill" 
            style={{ width: `${progress * 100}%` }}
          />
        </div>
      )}
    </div>
  );
};

// ============================================================
// Text Renderer - For plain text with typewriter effect
// ============================================================

interface TextRendererProps extends StreamingRendererProps {
  typewriterSpeed?: number; // ms per character
  maxPreviewChars?: number;
}

/**
 * Text Renderer
 * 
 * Renders text content with optional typewriter effect.
 */
export const TextRenderer: React.FC<TextRendererProps> = ({
  value,
  progress,
  isComplete,
  speed,
  typewriterSpeed = 0, // 0 = instant, no typewriter
  maxPreviewChars,
}) => {
  const [displayedChars, setDisplayedChars] = useState(0);
  const totalChars = value.length;
  
  // Typewriter effect
  useEffect(() => {
    if (typewriterSpeed === 0 || isComplete) {
      setDisplayedChars(totalChars);
      return;
    }
    
    if (displayedChars >= totalChars) {
      return;
    }
    
    const timer = setTimeout(() => {
      setDisplayedChars(prev => Math.min(prev + 1, totalChars));
    }, typewriterSpeed);
    
    return () => clearTimeout(timer);
  }, [typewriterSpeed, isComplete, displayedChars, totalChars]);
  
  const displayText = useMemo(() => {
    const text = typewriterSpeed > 0 
      ? value.slice(0, displayedChars)
      : value;
    
    if (maxPreviewChars && text.length > maxPreviewChars) {
      return '...' + text.slice(-maxPreviewChars);
    }
    return text;
  }, [value, displayedChars, typewriterSpeed, maxPreviewChars]);
  
  return (
    <div className="streaming-text-container">
      {/* Header */}
      <div className="streaming-text-header">
        <span className="char-count">{totalChars} chars</span>
        {!isComplete && (
          <span className="streaming-indicator">
            {Math.round(progress * 100)}%
          </span>
        )}
        {speed !== undefined && speed > 0 && (
          <span className="speed">{formatSpeed(speed)}</span>
        )}
      </div>
      
      {/* Text content */}
      <div className="streaming-text-content">
        <pre>{displayText}</pre>
        {!isComplete && (
          <span className="streaming-cursor">▊</span>
        )}
      </div>
      
      {/* Progress bar */}
      {!isComplete && (
        <div className="progress-bar">
          <div 
            className="progress-fill" 
            style={{ width: `${progress * 100}%` }}
          />
        </div>
      )}
    </div>
  );
};

// ============================================================
// Generic Renderer - Fallback for any content type
// ============================================================

/**
 * Generic Renderer
 * 
 * Fallback renderer that shows basic information and progress.
 */
export const GenericRenderer: React.FC<StreamingRendererProps> = ({
  value,
  progress,
  isComplete,
  receivedBytes,
  totalBytes,
  speed,
  toolName,
  paramName,
}) => {
  return (
    <div className="streaming-generic-container">
      {/* Header */}
      <div className="streaming-generic-header">
        {toolName && <span className="tool-name">{toolName}</span>}
        {paramName && <span className="param-name">.{paramName}</span>}
        <span className="size">
          {formatBytes(receivedBytes)}
          {totalBytes && ` / ${formatBytes(totalBytes)}`}
        </span>
      </div>
      
      {/* Progress bar */}
      <div className="progress-bar-container">
        <div className="progress-bar">
          <div 
            className="progress-fill" 
            style={{ width: `${progress * 100}%` }}
          />
        </div>
        <span className="progress-text">
          {Math.round(progress * 100)}%
        </span>
      </div>
      
      {/* Speed indicator */}
      {speed !== undefined && speed > 0 && (
        <div className="speed-indicator">
          {formatSpeed(speed)}
        </div>
      )}
      
      {/* Preview */}
      <div className="streaming-preview">
        <pre>{value.slice(-200)}</pre>
        {!isComplete && (
          <div className="loading-indicator">Loading more...</div>
        )}
      </div>
    </div>
  );
};

// ============================================================
// Renderer Registry
// ============================================================

/**
 * Renderer interface
 */
export interface IRenderer {
  name: string;
  render: (props: StreamingRendererProps) => React.ReactElement;
  supports: (props: StreamingRendererProps) => boolean;
}

/**
 * Default renderers
 */
const defaultRenderers: IRenderer[] = [
  {
    name: 'code',
    supports: ({ renderer, value }) => {
      if (renderer === 'code') return true;
      
      // Auto-detect code
      const codeIndicators = [
        'def ', 'class ', 'function ', 'import ',
        'const ', 'let ', '=> {', '() =>',
      ];
      return codeIndicators.some(ind => value.includes(ind));
    },
    render: (props) => <CodeRenderer {...props} />,
  },
  {
    name: 'text',
    supports: ({ renderer }) => renderer === 'text' || renderer === 'default',
    render: (props) => <TextRenderer {...props} />,
  },
];

/**
 * Renderer Registry
 * 
 * Manages available renderers and selects the appropriate one.
 */
export class RendererRegistry {
  private renderers: IRenderer[] = [...defaultRenderers];
  
  /**
   * Register a new renderer
   */
  register(renderer: IRenderer): void {
    this.renderers.push(renderer);
  }
  
  /**
   * Find a renderer for the given props
   */
  findRenderer(props: StreamingRendererProps): IRenderer {
    for (const renderer of this.renderers) {
      if (renderer.supports(props)) {
        return renderer;
      }
    }
    
    // Fallback to generic
    return {
      name: 'generic',
      supports: () => true,
      render: (p) => <GenericRenderer {...p} />,
    };
  }
  
  /**
   * Render using the appropriate renderer
   */
  render(props: StreamingRendererProps): React.ReactElement {
    const renderer = this.findRenderer(props);
    return renderer.render(props);
  }
}

/**
 * Global renderer registry instance
 */
export const rendererRegistry = new RendererRegistry();

// ============================================================
// Main Streaming Param Renderer Component
// ============================================================

interface StreamingParamRendererProps {
  callId: string;
  paramName: string;
  builder: ReturnType<typeof import('./incremental-param-builder').IncrementalParamBuilder>;
  customRenderer?: IRenderer;
  className?: string;
}

/**
 * Streaming Parameter Renderer
 * 
 * Main component for rendering streaming parameters.
 * Automatically selects the appropriate renderer based on content.
 */
export const StreamingParamRenderer: React.FC<StreamingParamRendererProps> = ({
  callId,
  paramName,
  builder,
  customRenderer,
  className,
}) => {
  const [state, setState] = useState<{
    value: string;
    progress: number;
    isComplete: boolean;
    receivedBytes: number;
    totalBytes: number | null;
    renderer: string;
  } | null>(null);
  
  const startTimeRef = useRef(Date.now());
  
  // Subscribe to builder events
  useEffect(() => {
    const unsubscribe = builder.subscribe((event) => {
      if (event.paramName === paramName && event.callId === callId) {
        if (event.type === 'param_start' || 
            event.type === 'param_progress' || 
            event.type === 'param_complete') {
          
          const paramState = builder.getParamState(callId, paramName);
          if (paramState) {
            setState({
              value: paramState.value,
              progress: builder.getProgress(callId, paramName),
              isComplete: paramState.isComplete,
              receivedBytes: paramState.receivedBytes,
              totalBytes: paramState.totalBytes,
              renderer: paramState.renderer,
            });
          }
        }
      }
    });
    
    return unsubscribe;
  }, [builder, paramName, callId]);
  
  // Calculate speed
  const speed = useMemo(() => {
    if (!state || state.receivedBytes === 0) return undefined;
    const elapsed = (Date.now() - startTimeRef.current) / 1000;
    return state.receivedBytes / elapsed;
  }, [state?.receivedBytes]);
  
  if (!state) {
    return (
      <div className={`streaming-waiting ${className || ''}`}>
        Waiting for parameter stream...
      </div>
    );
  }
  
  const props: StreamingRendererProps = {
    value: state.value,
    progress: state.progress,
    isComplete: state.isComplete,
    receivedBytes: state.receivedBytes,
    totalBytes: state.totalBytes,
    speed,
    renderer: state.renderer,
    paramName,
  };
  
  // Use custom renderer or registry
  if (customRenderer) {
    return (
      <div className={`streaming-param-container ${className || ''}`}>
        {customRenderer.render(props)}
      </div>
    );
  }
  
  return (
    <div className={`streaming-param-container ${className || ''}`}>
      {rendererRegistry.render(props)}
    </div>
  );
};

export default StreamingParamRenderer;