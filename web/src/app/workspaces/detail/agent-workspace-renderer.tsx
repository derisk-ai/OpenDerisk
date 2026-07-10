'use client';

import { useMemo } from 'react';
import { GPTVis } from '@antv/gpt-vis';
import markdownComponents, { markdownPlugins, preprocessLaTeX } from '@/components/chat/chat-content-components/config';
import type { WorkspaceExecutionStep, WorkspaceView } from './agent-workspace-types';
import type { AgentStep } from './agent-types';

const STATUS_ICON: Record<WorkspaceExecutionStep['status'], string> = {
  running: '⏳',
  done: '✅',
  failed: '❌',
};

function StepCard({ step, onStepClick }: { step: WorkspaceExecutionStep; onStepClick?: (s: WorkspaceExecutionStep) => void }) {
  const markdown = useMemo(() => {
    const parts: string[] = [];
    if (step.action) parts.push(`**工具:** ${step.action}`);
    if (step.action_input) parts.push('```json\n' + JSON.stringify(step.action_input, null, 2) + '\n```');
    if (step.output) parts.push(step.output);
    return parts.join('\n\n');
  }, [step]);

  return (
    <div className="ws-agent-renderer__step" role="button" tabIndex={0}
      onClick={() => onStepClick?.(step)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onStepClick?.(step); } }}>
      <div className="ws-agent-renderer__step-head">
        <span>{STATUS_ICON[step.status]}</span>
        <span className="ws-agent-renderer__step-title">{step.title}</span>
      </div>
      {markdown && (
        // @ts-ignore rehypePlugins type mismatch is pre-existing repo-wide (see chat-detail-content.tsx)
        <GPTVis components={markdownComponents} {...markdownPlugins}>
          {preprocessLaTeX(markdown)}
        </GPTVis>
      )}
      {step.artifact && (
        <div className="ws-agent-renderer__artifact">{step.artifact.file_path}</div>
      )}
    </div>
  );
}

export interface AgentWorkspaceRendererProps {
  view: WorkspaceView;
  onStepClick?: (step: WorkspaceExecutionStep) => void;
}

export function AgentWorkspaceRenderer({ view, onStepClick }: AgentWorkspaceRendererProps) {
  return (
    <div className="ws-agent-renderer">
      {view.planning && (
        <div className="ws-agent-renderer__planning">
          <div className="ws-agent-renderer__goal">{view.planning.goal}</div>
          {view.planning.steps.map(s => (
            <div key={s.id} className="ws-agent-renderer__plan-step">{STATUS_ICON[(s.status as WorkspaceExecutionStep['status'])] ?? '•'} {s.title}</div>
          ))}
        </div>
      )}
      {view.execution.map(step => (
        <StepCard key={step.id} step={step} onStepClick={onStepClick} />
      ))}
      {view.summary && (
        // @ts-ignore rehypePlugins type mismatch is pre-existing repo-wide (see chat-detail-content.tsx)
        <GPTVis components={markdownComponents} {...markdownPlugins}>
          {preprocessLaTeX(view.summary)}
        </GPTVis>
      )}
      {!view.execution.length && !view.summary && (
        <div className="ws-agent-renderer__empty">Agent 就绪,输入指令开始工作</div>
      )}
    </div>
  );
}