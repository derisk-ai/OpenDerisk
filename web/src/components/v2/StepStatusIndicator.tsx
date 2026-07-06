// web/src/components/v2/StepStatusIndicator.tsx
/** Step状态指示器 */

import React from 'react';
import { VisComponentState } from '@/utils/v2/types';

interface StepStatusIndicatorProps {
  component?: VisComponentState;
}

const STEP_STATE_LABELS: Record<string, string> = {
  INIT: '初始化',
  THINKING: '思考中',
  ACTING: '执行工具',
  OBSERVING: '观察结果',
  AWAITING_USER: '等待用户',
  AWAITING_TOOL_PERMISSION: '等待授权',
  AWAITING_SUB_AGENT: '等待子Agent',
  DONE: '完成',
  FAILED: '失败',
};

const STEP_STATE_COLORS: Record<string, string> = {
  INIT: 'gray',
  THINKING: 'blue',
  ACTING: 'orange',
  OBSERVING: 'green',
  AWAITING_USER: 'yellow',
  AWAITING_TOOL_PERMISSION: 'yellow',
  AWAITING_SUB_AGENT: 'purple',
  DONE: 'green',
  FAILED: 'red',
};

export const StepStatusIndicator: React.FC<StepStatusIndicatorProps> = ({ component }) => {
  if (!component) {
    return null;
  }

  const state = (component.meta?.state as string) || 'INIT';
  const label = STEP_STATE_LABELS[state] || state;
  const color = STEP_STATE_COLORS[state] || 'gray';

  return (
    <div className="step-status-indicator" style={{ marginBottom: '8px' }}>
      <span
        className="status-badge"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          padding: '4px 12px',
          borderRadius: '12px',
          backgroundColor: color,
          color: 'white',
          fontSize: '12px',
          fontWeight: '500',
        }}
      >
        {label}
      </span>
    </div>
  );
};
