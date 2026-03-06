/**
 * Part渲染器 - React组件
 * 
 * 负责将Part数据渲染为UI组件
 */

import React, { useEffect, useState, useRef } from 'react';
import type { Part, VisPart, TextPart, CodePart, ToolUsePart, ThinkingPart, PlanPart } from './types';
import { PartType, PartStatus } from './types';

// ═══════════════════════════════════════════════════════════════
// 基础Part渲染器
// ═══════════════════════════════════════════════════════════════

interface PartRendererProps {
  part: Part;
  onAction?: (action: string, data: any) => void;
}

export const PartRenderer: React.FC<PartRendererProps> = ({ part, onAction }) => {
  switch (part.type) {
    case PartType.TEXT:
      return <TextPartRenderer part={part as TextPart} />;
    case PartType.CODE:
      return <CodePartRenderer part={part as CodePart} />;
    case PartType.TOOL_USE:
      return <ToolUsePartRenderer part={part as ToolUsePart} />;
    case PartType.THINKING:
      return <ThinkingPartRenderer part={part as ThinkingPart} />;
    case PartType.PLAN:
      return <PlanPartRenderer part={part as PlanPart} />;
    default:
      return <DefaultPartRenderer part={part} />;
  }
};

// ═══════════════════════════════════════════════════════════════
// 具体Part渲染器
// ═══════════════════════════════════════════════════════════════

// 文本Part渲染器
const TextPartRenderer: React.FC<{ part: TextPart }> = ({ part }) => {
  const [isStreaming, setIsStreaming] = useState(part.status === PartStatus.STREAMING);
  const contentRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    if (part.status === PartStatus.STREAMING) {
      setIsStreaming(true);
      // 自动滚动到底部
      if (contentRef.current) {
        contentRef.current.scrollTop = contentRef.current.scrollHeight;
      }
    } else {
      setIsStreaming(false);
    }
  }, [part.status, part.content]);
  
  return (
    <div className="part-text" ref={contentRef}>
      <div className={`part-content ${isStreaming ? 'streaming' : ''}`}>
        {part.format === 'markdown' ? (
          <MarkdownContent content={part.content} />
        ) : (
          <pre>{part.content}</pre>
        )}
        {isStreaming && <span className="cursor">▊</span>}
      </div>
    </div>
  );
};

// 代码Part渲染器
const CodePartRenderer: React.FC<{ part: CodePart }> = ({ part }) => {
  const [copied, setCopied] = useState(false);
  
  const handleCopy = async () => {
    await navigator.clipboard.writeText(part.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  
  return (
    <div className="part-code">
      <div className="code-header">
        <span className="language">{part.language || 'code'}</span>
        {part.filename && <span className="filename">{part.filename}</span>}
        <button className="copy-btn" onClick={handleCopy}>
          {copied ? '✓ Copied' : 'Copy'}
        </button>
      </div>
      <pre className="code-content">
        <code className={`language-${part.language}`}>
          {part.content}
        </code>
      </pre>
    </div>
  );
};

// 工具使用Part渲染器
const ToolUsePartRenderer: React.FC<{ part: ToolUsePart }> = ({ part }) => {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <div className={`part-tool ${part.status}`}>
      <div className="tool-header" onClick={() => setExpanded(!expanded)}>
        <span className="tool-icon">🔧</span>
        <span className="tool-name">{part.tool_name}</span>
        <span className="tool-status">
          {part.status === PartStatus.STREAMING && '⏳ Running...'}
          {part.status === PartStatus.COMPLETED && '✓ Done'}
          {part.status === PartStatus.ERROR && '✗ Failed'}
        </span>
        {part.execution_time && (
          <span className="tool-time">{part.execution_time.toFixed(2)}s</span>
        )}
      </div>
      
      {expanded && (
        <div className="tool-details">
          {part.tool_args && (
            <div className="tool-args">
              <strong>Arguments:</strong>
              <pre>{JSON.stringify(part.tool_args, null, 2)}</pre>
            </div>
          )}
          {part.tool_result && (
            <div className="tool-result">
              <strong>Result:</strong>
              <pre>{part.tool_result}</pre>
            </div>
          )}
          {part.tool_error && (
            <div className="tool-error">
              <strong>Error:</strong>
              <pre className="error">{part.tool_error}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// 思考Part渲染器
const ThinkingPartRenderer: React.FC<{ part: ThinkingPart }> = ({ part }) => {
  const [expanded, setExpanded] = useState(part.expand ?? false);
  
  return (
    <div className="part-thinking">
      <div className="thinking-header" onClick={() => setExpanded(!expanded)}>
        <span className="thinking-icon">💭</span>
        <span className="thinking-label">Thinking</span>
        <span className={`expand-icon ${expanded ? 'expanded' : ''}`}>▼</span>
      </div>
      
      {expanded && (
        <div className="thinking-content">
          <MarkdownContent content={part.content} />
          {part.think_link && (
            <a href={part.think_link} className="think-link" target="_blank">
              View Details →
            </a>
          )}
        </div>
      )}
    </div>
  );
};

// 计划Part渲染器
const PlanPartRenderer: React.FC<{ part: PlanPart }> = ({ part }) => {
  return (
    <div className="part-plan">
      {part.title && <h3 className="plan-title">{part.title}</h3>}
      <div className="plan-items">
        {part.items?.map((item, index) => (
          <div 
            key={index} 
            className={`plan-item ${item.status} ${index === part.current_index ? 'current' : ''}`}
          >
            <span className="item-status">
              {item.status === 'completed' && '✓'}
              {item.status === 'working' && '⏳'}
              {item.status === 'pending' && '○'}
              {item.status === 'failed' && '✗'}
            </span>
            <span className="item-task">{item.task}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// 默认Part渲染器
const DefaultPartRenderer: React.FC<{ part: VisPart }> = ({ part }) => {
  return (
    <div className="part-default">
      <pre>{JSON.stringify(part, null, 2)}</pre>
    </div>
  );
};

// Markdown内容渲染器(简化版)
const MarkdownContent: React.FC<{ content: string }> = ({ content }) => {
  // 实际项目中应该使用markdown库如react-markdown
  return <div className="markdown-content">{content}</div>;
};

export default PartRenderer;