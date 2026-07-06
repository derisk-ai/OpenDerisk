// web/src/components/v2/UsageDisplay.tsx
/** Token用量展示 */

import React from 'react';
import { VisComponentState } from '@/utils/v2/types';

interface UsageDisplayProps {
  component?: VisComponentState;
}

export const UsageDisplay: React.FC<UsageDisplayProps> = ({ component }) => {
  if (!component?.meta) {
    return null;
  }

  const total = (component.meta.total as number) || 0;
  const ratio = (component.meta.ratio as number) || 0;

  return (
    <div
      className="usage-display"
      style={{
        padding: '8px 12px',
        backgroundColor: '#fff3e0',
        borderRadius: '8px',
        fontSize: '12px',
        marginBottom: '8px',
      }}
    >
      <span>📊 Token用量: {total} ({(ratio * 100).toFixed(1)}% context window)</span>
    </div>
  );
};
