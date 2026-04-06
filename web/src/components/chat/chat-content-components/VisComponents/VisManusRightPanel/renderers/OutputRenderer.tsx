'use client';

import React, { FC, useMemo } from 'react';
import { Table, Alert } from 'antd';
import { GPTVisLite } from '@antv/gpt-vis';
import { markdownComponents } from '../../../config';
import type { ManusExecutionOutput, ManusOutputType } from '@/types/manus';

interface IProps {
  outputs: ManusExecutionOutput[];
}

/** Code block with syntax highlighting */
const CodeBlock: FC<{ content: string; language?: string }> = ({
  content,
  language = 'python',
}) => (
  <div className="rounded-lg overflow-hidden border border-slate-200 bg-slate-900">
    <div className="flex items-center justify-between px-3 py-1.5 bg-slate-800 text-xs text-slate-400">
      <span>{language}</span>
    </div>
    <pre className="p-3 text-sm text-slate-100 overflow-x-auto">
      <code>{content}</code>
    </pre>
  </div>
);

/** Check if content contains VIS tag markup */
const containsVisTag = (text: string): boolean => {
  return /```[a-z][\w-]*\s*\n\s*\{/i.test(text);
};

/** Terminal-style text output - renders VIS tags via GPTVisLite if present */
const TextOutput: FC<{ content: string }> = ({ content }) => {
  if (containsVisTag(content)) {
    return (
      <div className="text-sm leading-normal max-w-none">
        <GPTVisLite components={markdownComponents}>{content}</GPTVisLite>
      </div>
    );
  }
  return (
    <div className="rounded-lg bg-slate-900 p-3 font-mono text-sm text-green-400 overflow-x-auto whitespace-pre-wrap">
      {content}
    </div>
  );
};

/** Table renderer */
const TableOutput: FC<{ content: any }> = ({ content }) => {
  const { columns, dataSource } = useMemo(() => {
    if (typeof content === 'string') {
      try {
        const parsed = JSON.parse(content);
        if (Array.isArray(parsed) && parsed.length > 0) {
          const cols = Object.keys(parsed[0]).map((key) => ({
            title: key,
            dataIndex: key,
            key,
            ellipsis: true,
          }));
          return {
            columns: cols,
            dataSource: parsed.map((row: any, i: number) => ({ ...row, key: i })),
          };
        }
      } catch {
        // not JSON table
      }
    }
    return { columns: [], dataSource: [] };
  }, [content]);

  if (columns.length === 0) {
    return <TextOutput content={typeof content === 'string' ? content : JSON.stringify(content, null, 2)} />;
  }

  return (
    <Table
      columns={columns}
      dataSource={dataSource}
      size="small"
      pagination={{ pageSize: 10 }}
      scroll={{ x: true }}
      className="border rounded-lg overflow-hidden"
    />
  );
};

/** JSON renderer */
const JsonOutput: FC<{ content: any }> = ({ content }) => {
  const formatted = useMemo(() => {
    if (typeof content === 'string') {
      try {
        return JSON.stringify(JSON.parse(content), null, 2);
      } catch {
        return content;
      }
    }
    return JSON.stringify(content, null, 2);
  }, [content]);

  return <CodeBlock content={formatted} language="json" />;
};

/** HTML preview in iframe */
const HtmlOutput: FC<{ content: string }> = ({ content }) => (
  <div className="rounded-lg border border-slate-200 overflow-hidden">
    <iframe
      srcDoc={content}
      className="w-full min-h-[300px] border-0"
      sandbox="allow-scripts allow-same-origin"
      style={{ height: '400px' }}
    />
  </div>
);

/** Image display */
const ImageOutput: FC<{ content: string }> = ({ content }) => (
  <div className="flex justify-center p-2">
    <img
      src={content}
      alt="output"
      className="max-w-full max-h-[500px] rounded-lg shadow-sm"
    />
  </div>
);

/** Markdown renderer - compact style without prose spacing */
const MarkdownOutput: FC<{ content: string }> = ({ content }) => (
  <div className="text-sm leading-normal max-w-none [&_h1]:text-lg [&_h1]:font-bold [&_h1]:mt-3 [&_h1]:mb-1.5 [&_h2]:text-base [&_h2]:font-bold [&_h2]:mt-2.5 [&_h2]:mb-1 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1 [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0.5 [&_hr]:my-2">
    <GPTVisLite components={markdownComponents}>{content}</GPTVisLite>
  </div>
);

/** Error display */
const ErrorOutput: FC<{ content: string }> = ({ content }) => (
  <Alert type="error" message="Error" description={content} showIcon />
);

/** Route output to appropriate renderer */
const OutputItem: FC<{ output: ManusExecutionOutput }> = ({ output }) => {
  const { output_type, content } = output;

  if (!content && content !== 0) return null;

  switch (output_type) {
    case 'code':
      return <CodeBlock content={String(content)} />;
    case 'text':
      return <TextOutput content={String(content)} />;
    case 'markdown':
      return <MarkdownOutput content={String(content)} />;
    case 'table':
      return <TableOutput content={content} />;
    case 'json':
      return <JsonOutput content={content} />;
    case 'error':
      return <ErrorOutput content={String(content)} />;
    case 'html':
      return <HtmlOutput content={String(content)} />;
    case 'image':
      return <ImageOutput content={String(content)} />;
    case 'chart':
      return <MarkdownOutput content={String(content)} />;
    case 'thought':
      return (
        <div className="text-xs text-slate-500 bg-slate-50 rounded-lg p-3 italic">
          {String(content)}
        </div>
      );
    default:
      return <TextOutput content={String(content)} />;
  }
};

/** Main output renderer - handles multiple output items */
const OutputRenderer: FC<IProps> = ({ outputs }) => {
  if (!outputs || outputs.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-slate-400 text-sm">
        暂无输出
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {outputs.map((output, index) => (
        <OutputItem key={index} output={output} />
      ))}
    </div>
  );
};

export default OutputRenderer;
