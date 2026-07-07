'use client';

import { useEffect, useRef } from 'react';
import { CheckCircleOutlined, ExclamationCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import type { AgentStep } from './agent-types';

export interface AgentProcessPanelProps {
  steps: AgentStep[];
  loading?: boolean;
  onStepClick?: (step: AgentStep) => void;
}

const statusIcon = (status: AgentStep['status']) => {
  switch (status) {
    case 'done':
      return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    case 'failed':
      return <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />;
    case 'running':
      return <LoadingOutlined style={{ color: '#1677ff' }} />;
    default:
      return <span className="ws-agent-step-dot" />;
  }
};

export function AgentProcessPanel({ steps, loading, onStepClick }: AgentProcessPanelProps) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [steps.length, loading]);

  return (
    <div className="ws-agent-process-panel">
      <div className="ws-agent-process-header">Agent 工作过程</div>
      {steps.length === 0 && !loading && (
        <div className="ws-agent-process-empty">Agent 就绪，输入指令开始工作</div>
      )}
      <div className="ws-agent-step-list" ref={listRef}>
        {steps.map((step) => (
          <div
            key={step.id}
            className={`ws-agent-step ws-agent-step--${step.status}`}
            onClick={() => onStepClick?.(step)}
            role={onStepClick ? 'button' : undefined}
            tabIndex={onStepClick ? 0 : undefined}
            onKeyDown={(e) => {
              if (onStepClick && (e.key === 'Enter' || e.key === ' ')) {
                e.preventDefault();
                onStepClick(step);
              }
            }}
          >
            <span className="ws-agent-step-icon">{statusIcon(step.status)}</span>
            <span className="ws-agent-step-title">{step.title}</span>
          </div>
        ))}
        {loading && (
          <div className="ws-agent-step ws-agent-step--running">
            <span className="ws-agent-step-icon"><LoadingOutlined style={{ color: '#1677ff' }} /></span>
            <span className="ws-agent-step-title">Agent 思考中...</span>
          </div>
        )}
      </div>
    </div>
  );
}
