'use client';

import React, { FC, useMemo } from 'react';
import { CopyOutlined } from '@ant-design/icons';
import { Tooltip, message } from 'antd';
import { GPTVisLite } from '@antv/gpt-vis';
import { markdownComponents } from '../../../config';
import type { ManusExecutionOutput, ManusStepStatus } from '@/types/manus';

interface IProps {
  command?: string;
  outputs: ManusExecutionOutput[];
  status: ManusStepStatus;
  title?: string;
}

/** Check if content contains VIS tag markup (```tag-name\n{...}\n```) */
const containsVisTag = (text: string): boolean => {
  return /```[a-z][\w-]*\s*\n\s*\{/i.test(text);
};

/** macOS-style terminal emulator */
const TerminalRenderer: FC<IProps> = ({
  command,
  outputs,
  status,
  title = 'Terminal',
}) => {
  const outputText = useMemo(() => {
    return outputs
      .filter((o) => o.output_type === 'text' || o.output_type === 'error')
      .map((o) => String(o.content || ''))
      .join('\n');
  }, [outputs]);

  const errorText = useMemo(() => {
    return outputs
      .filter((o) => o.output_type === 'error')
      .map((o) => String(o.content || ''))
      .join('\n');
  }, [outputs]);

  /** Whether output contains VIS tags that need GPTVis rendering */
  const hasVisContent = useMemo(() => containsVisTag(outputText), [outputText]);

  const handleCopy = () => {
    const text = [command ? `$ ${command}` : '', outputText].filter(Boolean).join('\n');
    navigator.clipboard.writeText(text);
    message.success('已复制');
  };

  const isRunning = status === 'running';
  const isError = status === 'error';

  return (
    <div className="h-full flex flex-col rounded-lg overflow-hidden border border-slate-700/60 bg-[#1e1e1e] shadow-sm">
      {/* macOS-style header */}
      <div className="flex items-center justify-between px-4 py-2 bg-[#2d2d2d] border-b border-slate-700/60 flex-shrink-0">
        <div className="flex items-center gap-2">
          {/* Traffic light dots */}
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
            <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
            <div className="w-3 h-3 rounded-full bg-[#28c840]" />
          </div>
          <span className="ml-3 text-xs text-slate-400 font-medium">{title}</span>
        </div>
        <div className="flex items-center gap-2">
          {/* Status badge */}
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
              isRunning
                ? 'bg-blue-500/20 text-blue-400'
                : isError
                  ? 'bg-red-500/20 text-red-400'
                  : 'bg-emerald-500/20 text-emerald-400'
            }`}
          >
            {isRunning ? '执行中' : isError ? '失败' : '完成'}
          </span>
          <Tooltip title="复制">
            <button
              onClick={handleCopy}
              className="text-slate-500 hover:text-slate-300 transition-colors"
            >
              <CopyOutlined className="text-xs" />
            </button>
          </Tooltip>
        </div>
      </div>

      {/* Terminal content */}
      <div className="flex-1 p-4 font-mono text-sm overflow-x-auto overflow-y-auto min-h-0">
        {/* Command line */}
        {command && (
          <div className="flex items-start gap-0">
            <span className="text-emerald-400 select-none">
              derisk@sandbox:~$
            </span>
            <span className="text-white ml-2">{command}</span>
          </div>
        )}

        {/* Output - use GPTVis if content contains VIS tags */}
        {outputText && !errorText && (
          hasVisContent ? (
            <div className="mt-2">
              <GPTVisLite components={markdownComponents}>{outputText}</GPTVisLite>
            </div>
          ) : (
            <div className="mt-2 text-slate-200 whitespace-pre-wrap leading-relaxed">
              {outputText}
            </div>
          )
        )}

        {/* Error output */}
        {errorText && (
          <div className="mt-2 text-red-400 whitespace-pre-wrap leading-relaxed">
            {errorText}
          </div>
        )}

        {/* Blinking cursor when running */}
        {isRunning && (
          <div className="flex items-center mt-1">
            <span className="text-emerald-400 select-none">
              derisk@sandbox:~$
            </span>
            <span className="ml-2 w-2 h-4 bg-emerald-400 animate-pulse" />
          </div>
        )}
      </div>
    </div>
  );
};

export default TerminalRenderer;
