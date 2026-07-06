// web/src/components/v2/ThinkingBlock.tsx
/** Thinking内容块 */

import React from 'react';
import { VisComponentState } from '@/utils/v2/types';

interface ThinkingBlockProps {
  component: VisComponentState;
}

export const ThinkingBlock: React.FC<ThinkingBlockProps> = ({ component }) => {
  return (
    <div
      className="thinking-block"
      style={{
        padding: '12px',
        backgroundColor: '#f5f5f5',
        borderRadius: '8px',
        marginBottom: '8px',
        fontFamily: 'monospace',
      }}
    >
      <div className="thinking-label" style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>
        💭 思考过程
      </div>
      <div className="thinking-content">
        {component.content}
      </div>
    </div>
  );
};
