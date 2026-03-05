'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Tabs } from 'antd';

interface MDEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  height?: number;
}

/**
 * Markdown 编辑器组件
 * 支持实时预览
 */
export const MDEditor: React.FC<MDEditorProps> = ({
  value,
  onChange,
  placeholder = '请输入 Markdown 内容',
  height = 400,
}) => {
  return (
    <div style={{ border: '1px solid #d9d9d9', borderRadius: 4 }}>
      <Tabs defaultActiveKey="edit">
        <Tabs.TabPane tab="编辑" key="edit">
          <textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            style={{
              width: '100%',
              height: height,
              padding: 12,
              border: 'none',
              outline: 'none',
              resize: 'vertical',
              fontFamily: 'monospace',
              fontSize: 14,
            }}
          />
        </Tabs.TabPane>
        <Tabs.TabPane tab="预览" key="preview">
          <div
            style={{
              padding: 12,
              height: height,
              overflow: 'auto',
            }}
            className="markdown-body"
          >
            <ReactMarkdown>
              {value || '*暂无内容*'}
            </ReactMarkdown>
          </div>
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
};

export default MDEditor;