// web/src/components/v2/ToolResultBlock.tsx
/** 工具执行结果块 */

import React from 'react';
import { VisComponentState } from '@/utils/v2/types';

interface ToolResultBlockProps {
  component: VisComponentState;
}

export const ToolResultBlock: React.FC<ToolResultBlockProps> = ({ component }) => {
  const toolName = (component.meta?.tool as string) || 'unknown';
  const success = component.meta?.success !== false;

  return (
    <div
      className="tool-result-block"
      style={{
        padding: '12px',
        backgroundColor: success ? '#e8f5e9' : '#ffebee',
        borderRadius: '8px',
        marginBottom: '8px',
      }}
    >
      <div className="tool-header" style={{ display: 'flex', alignItems: 'center', marginBottom: '8px' }}>
        <span style={{ fontSize: '14px', fontWeight: '500' }}>
          {success ? '✅' : '❌'} 工具: {toolName}
        </span>
      </div>
      <div className="tool-content" style={{ fontFamily: 'monospace', fontSize: '13px' }}>
        {component.content}
      </div>
    </div>
  );
};
