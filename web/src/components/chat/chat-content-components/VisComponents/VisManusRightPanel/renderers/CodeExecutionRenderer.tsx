'use client';

import React, { FC, useMemo, useState } from 'react';
import { Tabs } from 'antd';
import type { ManusExecutionOutput } from '@/types/manus';

interface IProps {
  outputs: ManusExecutionOutput[];
  language?: string;
}

/** Notebook-style Python code execution renderer */
const CodeExecutionRenderer: FC<IProps> = ({ outputs, language = 'python' }) => {
  const codeOutputs = useMemo(
    () => outputs.filter((o) => o.output_type === 'code'),
    [outputs]
  );
  const resultOutputs = useMemo(
    () => outputs.filter((o) => o.output_type !== 'code' && o.output_type !== 'thought'),
    [outputs]
  );
  const imageOutputs = useMemo(
    () => outputs.filter((o) => o.output_type === 'image' || o.output_type === 'chart'),
    [outputs]
  );

  const hasImages = imageOutputs.length > 0;

  const codeContent = codeOutputs.map((o) => String(o.content || '')).join('\n');
  const resultContent = resultOutputs
    .map((o) => String(o.content || ''))
    .join('\n');

  if (hasImages) {
    return (
      <Tabs
        size="small"
        defaultActiveKey="chart"
        items={[
          {
            key: 'chart',
            label: '图表',
            children: (
              <div className="p-3 space-y-3">
                {imageOutputs.map((img, i) => (
                  <div key={i} className="flex justify-center">
                    <img
                      src={String(img.content)}
                      alt={`chart-${i}`}
                      className="max-w-full max-h-[400px] rounded-lg shadow-sm"
                    />
                  </div>
                ))}
              </div>
            ),
          },
          {
            key: 'code',
            label: '代码',
            children: (
              <div className="space-y-0">
                <CodeResultCard
                  code={codeContent}
                  result={resultContent}
                  language={language}
                />
              </div>
            ),
          },
        ]}
      />
    );
  }

  return (
    <CodeResultCard
      code={codeContent}
      result={resultContent}
      language={language}
    />
  );
};

/** Code + result card */
const CodeResultCard: FC<{
  code: string;
  result: string;
  language: string;
}> = ({ code, result, language }) => (
  <div className="rounded-xl border border-slate-200 overflow-hidden bg-white">
    {/* Code section */}
    {code && (
      <div className="relative">
        <div className="sticky top-0 z-10 bg-slate-100 px-3 py-1 text-[10px] font-medium text-slate-500 uppercase tracking-wider border-b border-slate-200">
          {language}
        </div>
        <pre className="p-3 bg-slate-900 text-sm text-slate-100 overflow-x-auto">
          <code>{code.replace(/^```\w*\n?|```$/g, '')}</code>
        </pre>
      </div>
    )}

    {/* Result section */}
    {result && (
      <div className="relative border-t border-slate-200">
        <div className="sticky top-0 z-10 bg-emerald-50 px-3 py-1 text-[10px] font-medium text-emerald-600 uppercase tracking-wider border-b border-emerald-100">
          执行结果
        </div>
        <div className="p-3 bg-white text-sm text-slate-700 font-mono whitespace-pre-wrap overflow-x-auto">
          {result}
        </div>
      </div>
    )}
  </div>
);

export default CodeExecutionRenderer;
