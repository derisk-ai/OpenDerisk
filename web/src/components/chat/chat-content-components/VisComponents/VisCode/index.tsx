import React, { useState } from 'react';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { CodePreview } from '../../code-preview';
import { codeComponents, markdownPlugins } from '../../config';

function formatMarkdownVal(val: string) {
  return val
    ?.replace(/<table(\w*=[^>]+)>/gi, '<table $1>')
    .replace(/<tr(\w*=[^>]+)>/gi, '<tr $1>');
}

function preprocessLaTeX(content: unknown): string {
  if (typeof content !== 'string') return String(content ?? '');
  const codeBlocks: string[] = [];
  let rtnContent = content.replace(
    /(```[\s\S]*?```|`[^`\n]+`)/g,
    (match: string) => {
      codeBlocks.push(match);
      return `<<CODE_BLOCK_${codeBlocks.length - 1}>>`;
    },
  );
  rtnContent = rtnContent
    .replace(/\\\\\[/g, '$$')
    .replace(/\\\\\]/g, '$$')
    .replace(/\\\\\(/g, '$')
    .replace(/\\\\\)/g, '$')
    .replace(/\\\[/g, '$$')
    .replace(/\\\]/g, '$$')
    .replace(/\\\(/g, '$')
    .replace(/\\\)/g, '$')
    .replace(/([^\n])\$\$/g, '$1\n\n$$')
    .replace(/\$\$([^\n])/g, '$$\n\n$1')
    .replace(/\$(?=\d)/g, '\\$');
  rtnContent = rtnContent.replace(
    /<<CODE_BLOCK_(\d+)>>/g,
    (_: string, index: string) => codeBlocks[parseInt(index, 10)] ?? '',
  );
  return rtnContent;
}

interface Props {
  code?: string[][];
  exit_success?: boolean;
  language?: string;
  log?: string;
}

export function VisCode({
  code,
  exit_success,
  language,
  log,
}: Props) {
  const [show, setShow] = useState(0);

  return (
    <div className="bg-[#EAEAEB] rounded overflow-hidden border border-theme-primary dark:bg-theme-dark text-sm">
      <div>
        <div className="flex">
          {code?.map((item, index) => (
            <div
              key={index}
              className={`px-4 py-2 text-[#121417] dark:text-white cursor-pointer ${
                index === show ? 'bg-white dark:bg-theme-dark-container' : ''
              }`}
              onClick={() => setShow(index)}
            >
              CODE {index + 1}: {item?.[0]}
            </div>
          ))}
        </div>
        {code?.length ? (
          <CodePreview
            language={language || code?.[show]?.[0] || 'text'}
            code={code?.[show]?.[1] || ''}
            light={oneLight}
          />
        ) : null}
      </div>
      <div>
        <div className="flex">
          <div className="bg-white dark:bg-theme-dark-container px-4 py-2 text-[#121417] dark:text-white">
            Terminal
            {exit_success ? (
              <CheckOutlined className="text-green-600" />
            ) : (
              <CloseOutlined className="text-red-600" />
            )}
          </div>
        </div>
        <div className="p-4 max-h-72 overflow-y-auto whitespace-normal bg-white dark:dark:bg-theme-dark">
          {/* @ts-ignore */}
          <GPTVis components={codeComponents} {...markdownPlugins}>
            {(() => {
              try {
                return JSON.parse(
                  preprocessLaTeX(formatMarkdownVal(log || '-')),
                );
              } catch {
                return log || '-';
              }
            })()}
          </GPTVis>
        </div>
      </div>
    </div>
  );
}

export default VisCode;
