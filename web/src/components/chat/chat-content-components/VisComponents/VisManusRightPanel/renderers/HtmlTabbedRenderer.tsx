'use client';

import React, { FC, useState, useMemo } from 'react';
import { Tabs } from 'antd';
import type { ManusExecutionOutput } from '@/types/manus';

interface IProps {
  outputs: ManusExecutionOutput[];
  title?: string;
}

/** Tabbed HTML preview + source code renderer */
const HtmlTabbedRenderer: FC<IProps> = ({ outputs, title }) => {
  const htmlContent = useMemo(() => {
    const htmlOutput = outputs.find((o) => o.output_type === 'html');
    return htmlOutput ? String(htmlOutput.content || '') : '';
  }, [outputs]);

  const codeContent = useMemo(() => {
    const codeOutput = outputs.find((o) => o.output_type === 'code');
    return codeOutput ? String(codeOutput.content || '') : htmlContent;
  }, [outputs, htmlContent]);

  if (!htmlContent && !codeContent) {
    return (
      <div className="flex items-center justify-center h-32 text-slate-400 text-sm">
        暂无 HTML 内容
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden bg-white">
      {title && (
        <div className="px-4 py-2 bg-slate-50 border-b border-slate-200 text-sm font-medium text-slate-700">
          {title}
        </div>
      )}
      <Tabs
        size="small"
        defaultActiveKey="preview"
        className="px-2"
        items={[
          {
            key: 'preview',
            label: '预览',
            children: (
              <div className="border border-slate-200 rounded-lg overflow-hidden mb-3">
                <iframe
                  srcDoc={htmlContent || codeContent}
                  className="w-full border-0"
                  sandbox="allow-scripts allow-same-origin"
                  style={{ height: '450px' }}
                />
              </div>
            ),
          },
          {
            key: 'source',
            label: '源码',
            children: (
              <div className="rounded-lg overflow-hidden border border-slate-200 mb-3">
                <pre className="p-3 bg-slate-900 text-sm text-slate-100 overflow-auto max-h-[450px]">
                  <code>{codeContent || htmlContent}</code>
                </pre>
              </div>
            ),
          },
        ]}
      />
    </div>
  );
};

export default HtmlTabbedRenderer;
