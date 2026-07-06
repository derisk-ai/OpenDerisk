// web/src/components/v2/StepPanel.tsx
/** Step面板容器 - 聚合渲染单个step的所有组件 */

import React from 'react';
import { VisComponentState } from '@/utils/v2/types';
import { StepStatusIndicator } from './StepStatusIndicator';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolResultBlock } from './ToolResultBlock';
import { UsageDisplay } from './UsageDisplay';

interface StepPanelProps {
  stepId: string;
  components: VisComponentState[];
}

export const StepPanel: React.FC<StepPanelProps> = ({ stepId, components }) => {
  // 按tag分类组件
  const statusComponent = components.find(c => c.tag === 'step_status');
  const thinkingComponents = components.filter(c => c.tag === 'thinking');
  const toolResultComponents = components.filter(c => c.tag === 'tool_result');
  const usageComponent = components.find(c => c.tag === 'usage_display');

  return (
    <div
      className="step-panel"
      style={{
        border: '1px solid #e0e0e0',
        borderRadius: '12px',
        padding: '16px',
        marginBottom: '16px',
        backgroundColor: '#fff',
      }}
    >
      {/* Step ID header */}
      <div style={{ fontSize: '10px', color: '#999', marginBottom: '12px' }}>
        Step: {stepId}
      </div>

      {/* 状态指示器 */}
      <StepStatusIndicator component={statusComponent} />

      {/* Thinking块 */}
      {thinkingComponents.map(c => (
        <ThinkingBlock key={c.uid} component={c} />
      ))}

      {/* Tool结果块 */}
      {toolResultComponents.map(c => (
        <ToolResultBlock key={c.uid} component={c} />
      ))}

      {/* 用量展示 */}
      <UsageDisplay component={usageComponent} />
    </div>
  );
};
