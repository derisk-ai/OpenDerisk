/**
 * 统一消息渲染器
 * 
 * 自动适配V1/V2消息格式的统一渲染组件
 */

import React from 'react';
import { UnifiedMessage } from '@/services/unified/unified-session-service';

/**
 * 消息渲染器属性
 */
interface UnifiedMessageRendererProps {
  message: UnifiedMessage;
  agentVersion?: 'v1' | 'v2';
  className?: string;
}

/**
 * 消息类型
 */
type MessageType = 'thinking' | 'tool_call' | 'response' | 'error' | 'code' | 'chart';

/**
 * 统一消息渲染器
 */
export function UnifiedMessageRenderer({ 
  message,
  agentVersion = 'v2',
  className = ''
}: UnifiedMessageRendererProps) {
  const messageType = _detectMessageType(message, agentVersion);
  
  return (
    <div className={`unified-message-container ${agentVersion} ${messageType} ${className}`}>
      {_renderContent(message, messageType)}
    </div>
  );
}

/**
 * 检测消息类型
 */
function _detectMessageType(message: UnifiedMessage, agentVersion: 'v1' | 'v2' = 'v2'): MessageType {
  const metadata = message.metadata || {};
  
  if (metadata.type === 'thinking') {
    return 'thinking';
  }
  
  if (metadata.type === 'tool_call' || metadata.toolName) {
    return 'tool_call';
  }
  
  if (metadata.type === 'error') {
    return 'error';
  }
  
  if (message.content.startsWith('```')) {
    if (message.content.includes('```vis-chart')) {
      return 'chart';
    }
    return 'code';
  }
  
  if (agentVersion === 'v1') {
    if (message.content.startsWith('[THINKING]')) {
      return 'thinking';
    }
    if (message.content.startsWith('[TOOL:')) {
      return 'tool_call';
    }
    if (message.content.startsWith('[ERROR]')) {
      return 'error';
    }
  }
  
  return 'response';
}

/**
 * 渲染消息内容
 */
function _renderContent(message: UnifiedMessage, type: MessageType): React.ReactNode {
  switch (type) {
    case 'thinking':
      return <ThinkingBlock content={_extractContent(message, type)} />;
    
    case 'tool_call':
      return (
        <ToolExecutionBlock 
          toolName={message.metadata?.toolName || _extractToolName(message.content)}
          content={_extractContent(message, type)}
        />
      );
    
    case 'error':
      return <ErrorBlock content={_extractContent(message, type)} />;
    
    case 'code':
      return <CodeBlock content={message.content} />;
    
    case 'chart':
      return <ChartBlock content={message.content} />;
    
    default:
      return <ResponseBlock content={message.content} />;
  }
}

/**
 * 提取内容
 */
function _extractContent(message: UnifiedMessage, type: MessageType): string {
  let content = message.content;
  
  if (type === 'thinking') {
    content = content.replace('[THINKING]', '').replace('[/THINKING]', '');
  } else if (type === 'tool_call') {
    const match = content.match(/\[TOOL:([^\]]+)\]([\s\S]*)\[\/TOOL\]/);
    if (match) {
      content = match[2].trim();
    }
  } else if (type === 'error') {
    content = content.replace('[ERROR]', '').replace('[/ERROR]', '');
  }
  
  return content.trim();
}

/**
 * 提取工具名称
 */
function _extractToolName(content: string): string {
  const match = content.match(/\[TOOL:([^\]]+)\]/);
  return match ? match[1] : 'unknown';
}

/**
 * 思考块组件
 */
function ThinkingBlock({ content }: { content: string }) {
  return (
    <div className="thinking-block bg-gray-50 dark:bg-gray-800 p-3 rounded-lg my-2">
      <div className="thinking-header flex items-center text-sm text-gray-500 dark:text-gray-400 mb-2">
        <span className="thinking-icon mr-2">🤔</span>
        <span>Thinking...</span>
      </div>
      <div className="thinking-content text-sm italic text-gray-600 dark:text-gray-300">
        {content}
      </div>
    </div>
  );
}

/**
 * 工具执行块组件
 */
function ToolExecutionBlock({ toolName, content }: { toolName: string; content: string }) {
  return (
    <div className="tool-block bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg my-2">
      <div className="tool-header flex items-center text-sm text-blue-600 dark:text-blue-400 mb-2">
        <span className="tool-icon mr-2">🔧</span>
        <span>Tool: {toolName}</span>
      </div>
      <div className="tool-content text-sm text-gray-700 dark:text-gray-300">
        <pre className="whitespace-pre-wrap">{content}</pre>
      </div>
    </div>
  );
}

/**
 * 错误块组件
 */
function ErrorBlock({ content }: { content: string }) {
  return (
    <div className="error-block bg-red-50 dark:bg-red-900/20 p-3 rounded-lg my-2">
      <div className="error-header flex items-center text-sm text-red-600 dark:text-red-400 mb-2">
        <span className="error-icon mr-2">❌</span>
        <span>Error</span>
      </div>
      <div className="error-content text-sm text-red-700 dark:text-red-300">
        {content}
      </div>
    </div>
  );
}

/**
 * 响应块组件
 */
function ResponseBlock({ content }: { content: string }) {
  return (
    <div className="response-block text-gray-800 dark:text-gray-200">
      <div className="response-content whitespace-pre-wrap">
        {content}
      </div>
    </div>
  );
}

/**
 * 代码块组件
 */
function CodeBlock({ content }: { content: string }) {
  const language = _extractLanguage(content);
  const code = _extractCode(content);
  
  return (
    <div className="code-block my-2">
      <div className="code-header bg-gray-100 dark:bg-gray-700 px-3 py-1 rounded-t-lg text-xs text-gray-500 dark:text-gray-400">
        {language}
      </div>
      <pre className="code-content bg-gray-50 dark:bg-gray-800 p-3 rounded-b-lg overflow-x-auto text-sm">
        <code className={`language-${language}`}>{code}</code>
      </pre>
    </div>
  );
}

/**
 * 图表块组件
 */
function ChartBlock({ content }: { content: string }) {
  try {
    const chartData = _extractChartData(content);
    return (
      <div className="chart-block my-2 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <div className="chart-preview text-sm text-gray-500 dark:text-gray-400">
          📊 Chart: {chartData.type || 'unknown'}
        </div>
      </div>
    );
  } catch (error) {
    return <ResponseBlock content={content} />;
  }
}

/**
 * 提取代码语言
 */
function _extractLanguage(content: string): string {
  const match = content.match(/```(\w+)/);
  return match ? match[1] : 'text';
}

/**
 * 提取代码内容
 */
function _extractCode(content: string): string {
  const match = content.match(/```(\w+)?\n([\s\S]*)```/);
  return match ? match[2].trim() : content;
}

/**
 * 提取图表数据
 */
function _extractChartData(content: string): any {
  const match = content.match(/```vis-chart\n([\s\S]*)```/);
  if (match) {
    return JSON.parse(match[1]);
  }
  return null;
}

export default UnifiedMessageRenderer;