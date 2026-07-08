'use client';

import { useState } from 'react';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  DownOutlined,
  RightOutlined,
} from '@ant-design/icons';

export interface AgentPlanCardProps {
  title: string;
  agentName?: string;
  status: 'running' | 'done' | 'failed' | 'pending';
  description?: string;
  markdown?: string;
  defaultExpanded?: boolean;
  onClick?: () => void;
}

const statusIcon = (status: AgentPlanCardProps['status']) => {
  switch (status) {
    case 'done':
      return <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 14 }} />;
    case 'failed':
      return <ExclamationCircleOutlined style={{ color: '#ff4d4f', fontSize: 14 }} />;
    case 'running':
      return <LoadingOutlined style={{ color: '#1677ff', fontSize: 14 }} />;
    default:
      return <span className="ws-agent-plan-dot" />;
  }
};

const statusText = (status: AgentPlanCardProps['status']) => {
  switch (status) {
    case 'done':
      return '完成';
    case 'failed':
      return '失败';
    case 'running':
      return '执行中';
    default:
      return '待执行';
  }
};

export function AgentPlanCard({
  title,
  agentName,
  status,
  description,
  markdown,
  defaultExpanded = false,
  onClick,
}: AgentPlanCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const hasContent = Boolean(markdown || description);

  return (
    <div
      className={`ws-agent-plan-card ws-agent-plan-card--${status}`}
      role={onClick || hasContent ? 'button' : undefined}
      tabIndex={onClick || hasContent ? 0 : undefined}
      onClick={() => {
        if (hasContent) setExpanded((v) => !v);
        onClick?.();
      }}
      onKeyDown={(e) => {
        if ((onClick || hasContent) && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          if (hasContent) setExpanded((v) => !v);
          onClick?.();
        }
      }}
    >
      <div className="ws-agent-plan-card__header">
        <span className="ws-agent-plan-card__icon">{statusIcon(status)}</span>
        {agentName && (
          <span className="ws-agent-plan-card__agent">{agentName}</span>
        )}
        <span className="ws-agent-plan-card__title">{title}</span>
        <span className="ws-agent-plan-card__status">{statusText(status)}</span>
        {hasContent && (
          <span className="ws-agent-plan-card__expand">
            {expanded ? <DownOutlined /> : <RightOutlined />}
          </span>
        )}
      </div>
      {description && !expanded && (
        <div className="ws-agent-plan-card__description">{description}</div>
      )}
      {expanded && hasContent && (
        <div className="ws-agent-plan-card__content">
          {markdown ? (
            <pre className="ws-agent-plan-card__markdown">{markdown}</pre>
          ) : (
            <pre className="ws-agent-plan-card__markdown">{description}</pre>
          )}
        </div>
      )}
    </div>
  );
}
