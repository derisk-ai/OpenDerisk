'use client';

import React, { FC, useMemo } from 'react';
import { Tag } from 'antd';
import { FileTextOutlined, PlayCircleOutlined } from '@ant-design/icons';
import type { ManusExecutionOutput } from '@/types/manus';

interface IProps {
  outputs: ManusExecutionOutput[];
  skillName?: string;
  scriptName?: string;
}

/** Split-pane skill script renderer (45% code | 55% results) */
const SkillScriptRenderer: FC<IProps> = ({
  outputs,
  skillName,
  scriptName,
}) => {
  const codeOutputs = useMemo(
    () => outputs.filter((o) => o.output_type === 'code'),
    [outputs]
  );
  const textOutputs = useMemo(
    () => outputs.filter((o) => o.output_type === 'text'),
    [outputs]
  );
  const imageOutputs = useMemo(
    () => outputs.filter((o) => o.output_type === 'image'),
    [outputs]
  );
  const htmlOutputs = useMemo(
    () => outputs.filter((o) => o.output_type === 'html'),
    [outputs]
  );

  const codeContent = codeOutputs.map((o) => String(o.content || '')).join('\n');

  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden bg-white">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-slate-50 border-b border-slate-200">
        <PlayCircleOutlined className="text-indigo-500" />
        <span className="text-sm font-medium text-slate-700">
          {skillName || 'Skill Script'}
        </span>
        {scriptName && (
          <Tag color="blue" className="text-xs">
            <FileTextOutlined className="mr-1" />
            {scriptName}
          </Tag>
        )}
        {htmlOutputs.length > 0 && (
          <Tag color="green" className="text-xs ml-auto">
            HTML Report
          </Tag>
        )}
      </div>

      {/* Split pane */}
      <div className="flex divide-x divide-slate-200" style={{ minHeight: '300px' }}>
        {/* Left: Code (45%) */}
        <div className="w-[45%] flex flex-col">
          <div className="px-3 py-1.5 bg-slate-100 text-[10px] font-medium text-slate-500 uppercase tracking-wider border-b border-slate-200">
            Script
          </div>
          <pre className="flex-1 p-3 bg-slate-900 text-sm text-slate-100 overflow-auto">
            <code>{codeContent || '// Loading...'}</code>
          </pre>
        </div>

        {/* Right: Results (55%) */}
        <div className="w-[55%] flex flex-col overflow-y-auto">
          <div className="px-3 py-1.5 bg-slate-100 text-[10px] font-medium text-slate-500 uppercase tracking-wider border-b border-slate-200">
            Result
          </div>
          <div className="flex-1 p-3 space-y-3">
            {/* HTML outputs */}
            {htmlOutputs.map((html, i) => (
              <div key={`html-${i}`} className="rounded-lg border border-slate-200 overflow-hidden">
                <iframe
                  srcDoc={String(html.content)}
                  className="w-full border-0"
                  sandbox="allow-scripts allow-same-origin"
                  style={{ height: '300px' }}
                />
              </div>
            ))}

            {/* Text outputs */}
            {textOutputs.map((text, i) => (
              <div
                key={`text-${i}`}
                className="rounded-lg bg-slate-900 p-3 font-mono text-sm text-green-400 whitespace-pre-wrap"
              >
                {String(text.content)}
              </div>
            ))}

            {/* Image outputs */}
            {imageOutputs.map((img, i) => (
              <div key={`img-${i}`} className="flex justify-center">
                <img
                  src={String(img.content)}
                  alt={`result-${i}`}
                  className="max-w-full max-h-[300px] rounded-lg shadow-sm"
                />
              </div>
            ))}

            {/* Empty state */}
            {textOutputs.length === 0 &&
              imageOutputs.length === 0 &&
              htmlOutputs.length === 0 && (
                <div className="flex items-center justify-center h-full text-slate-400 text-sm">
                  等待执行结果...
                </div>
              )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SkillScriptRenderer;
