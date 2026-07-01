'use client';

import { markdown } from '@codemirror/lang-markdown';
import { createTheme } from '@uiw/codemirror-themes';
import CodeMirror from '@uiw/react-codemirror';
import { EditOutlined, EyeOutlined, SplitCellsOutlined } from '@ant-design/icons';
import { Button, Tooltip } from 'antd';
import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import styles from './MarkdownEditor.module.css';
import rehypeRaw from 'rehype-raw';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';

interface MarkdownEditorProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  placeholder?: string;
}

type Mode = 'edit' | 'preview' | 'split';

const lightTheme = createTheme({
  theme: 'light',
  settings: {
    background: '#ffffff',
    backgroundImage: '',
    foreground: '#1f2937',
    caret: '#7c3aed',
    selection: '#ddd6fe',
    selectionMatch: '#ddd6fe',
    gutterBackground: '#ffffff',
    gutterForeground: '#9ca3af',
    gutterBorder: '#e5e7eb',
    lineHighlight: '#f9fafb',
    fontSize: '14px',
  },
  styles: [],
});

export default function MarkdownEditor({
  value,
  onChange,
  readOnly,
  placeholder,
}: MarkdownEditorProps) {
  const [mode, setMode] = useState<Mode>('split');

  const showEdit = mode === 'edit' || mode === 'split';
  const showPreview = mode === 'preview' || mode === 'split';

  const preview = useMemo(
    () => (
      <div className={`p-4 text-sm text-gray-800 ${styles.markdownPreview}`}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkBreaks]}
          rehypePlugins={[rehypeRaw, rehypeHighlight]}
        >
          {value || ''}
        </ReactMarkdown>
      </div>
    ),
    [value],
  );

  return (
    <div className="h-full flex flex-col bg-white">
      <div className="flex items-center justify-end gap-1 px-3 py-2 border-b border-gray-100">
        <Tooltip title="编辑">
          <Button
            type={mode === 'edit' ? 'primary' : 'text'}
            size="small"
            icon={<EditOutlined />}
            onClick={() => setMode('edit')}
          />
        </Tooltip>
        <Tooltip title="预览">
          <Button
            type={mode === 'preview' ? 'primary' : 'text'}
            size="small"
            icon={<EyeOutlined />}
            onClick={() => setMode('preview')}
          />
        </Tooltip>
        <Tooltip title="分屏">
          <Button
            type={mode === 'split' ? 'primary' : 'text'}
            size="small"
            icon={<SplitCellsOutlined />}
            onClick={() => setMode('split')}
          />
        </Tooltip>
      </div>
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {showEdit && (
          <div
            className={`h-full ${mode === 'split' ? 'w-1/2 border-r border-gray-100' : 'w-full'}`}
          >
            <CodeMirror
              value={value}
              onChange={onChange}
              readOnly={readOnly}
              placeholder={placeholder}
              extensions={[markdown()]}
              theme={lightTheme}
              height="100%"
              className="h-full text-sm"
              basicSetup={{
                lineNumbers: true,
                highlightActiveLineGutter: true,
                foldGutter: false,
                autocompletion: false,
                indentOnInput: true,
                highlightActiveLine: true,
                highlightSelectionMatches: false,
              }}
            />
          </div>
        )}
        {showPreview && (
          <div
            className={`h-full ${mode === 'split' ? 'w-1/2' : 'w-full'} overflow-auto bg-white`}
          >
            {preview}
          </div>
        )}
      </div>
    </div>
  );
}
