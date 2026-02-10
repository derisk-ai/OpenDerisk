import React, { useEffect } from 'react';
import { Empty } from 'antd';

interface IProps {
  content?: string;
  error?: unknown;
  componentName?: string;
}

const VisParseError: React.FC<IProps> = ({ content, error, componentName }) => {
  useEffect(() => {
    if (error || content) {
        console.groupCollapsed(`[VisParseError] ${componentName || 'Unknown Component'}`);
        console.error('Error:', error);
        console.log('Original Content:', content);
        console.groupEnd();
    }
  }, [content, error, componentName]);

  return (
    <div style={{ padding: '16px 0', width: '100%', display: 'flex', justifyContent: 'center' }}>
      <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
    </div>
  );
};

export default VisParseError;
