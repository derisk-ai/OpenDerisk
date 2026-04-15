'use client';

import React, { FC, useMemo, useState, useEffect, useRef, useCallback } from 'react';
import classNames from 'classnames';
import {
  LoadingOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  GlobalOutlined,
  CaretDownOutlined,
  CaretUpOutlined,
  FileSearchOutlined,
  EditOutlined,
  ConsoleSqlOutlined,
  SearchOutlined,
  CodeOutlined,
  PlayCircleOutlined,
  FileTextOutlined,
  DesktopOutlined,
  FileOutlined,
  ProfileOutlined,
  FolderOpenOutlined,
  DownloadOutlined,
  EyeOutlined,
  FilePdfOutlined,
  PrinterOutlined,
} from '@ant-design/icons';
import { Tooltip, Dropdown, message } from 'antd';
import type { MenuProps } from 'antd';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import { GPTVisLite } from '@antv/gpt-vis';
import { markdownComponents } from '../../config';
import type {
  ManusRightPanelData,
  ManusActiveStepInfo,
  ManusExecutionOutput,
  ManusStepType,
  ManusStepStatus,
  ManusTaskFileItem,
  ManusDeliverableFile,
  ManusStepData,
} from '@/types/manus';
import { ee, EVENTS } from '@/utils/event-emitter';
import {
  OutputRenderer,
  TerminalRenderer,
  CodeExecutionRenderer,
  HtmlTabbedRenderer,
  SkillScriptRenderer,
  SkillCardRenderer,
  SkillReadRenderer,
  SqlQueryRenderer,
} from './renderers';

interface IProps {
   ManusRightPanelData;
}

/* ═══════════════════════════════════════════════════════════════
   Step type helpers
   ═══════════════════════════════════════════════════════════════ */

const getStepTypeIcon = (type: ManusStepType) => {
  const map: Record<string, React.ReactNode> = {
    read: <FileSearchOutlined className="text-emerald-500" />,
    edit: <EditOutlined className="text-amber-500" />,
    write: <EditOutlined className="text-amber-500" />,
    bash: <ConsoleSqlOutlined className="text-purple-500" />,
    grep: <SearchOutlined className="text-cyan-500" />,
    glob: <SearchOutlined className="text-cyan-500" />,
    python: <CodeOutlined className="text-blue-500" />,
    html: <CodeOutlined className="text-orange-500" />,
    task: <PlayCircleOutlined className="text-indigo-500" />,
    skill: <CodeOutlined className="text-violet-500" />,
    sql: <ConsoleSqlOutlined className="text-emerald-600" />,
  };
  return map[type] || <FileTextOutlined className="text-gray-400" />;
};

const getIconBgClass = (type: ManusStepType): string => {
  const map: Record<string, string> = {
    read: 'bg-emerald-50', edit: 'bg-amber-50', write: 'bg-amber-50',
    bash: 'bg-purple-50', grep: 'bg-cyan-50', glob: 'bg-cyan-50',
    python: 'bg-blue-50', html: 'bg-orange-50',
    task: 'bg-indigo-50', skill: 'bg-violet-50', sql: 'bg-emerald-50',
  };
  return map[type] || 'bg-gray-50';
};

/* ═══════════════════════════════════════════════════════════════
   Status badge
   ═══════════════════════════════════════════════════════════════ */

const StatusBadge: FC<{ status: ManusStepStatus; isRunning?: boolean }> = ({ status, isRunning }) => {
  if (isRunning || status === 'running') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 text-[10px] font-medium">
        <LoadingOutlined spin className="text-[10px]" />
        Running
      </span>
    );
  }
  if (status === 'completed') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-600 text-[10px] font-medium">
        <CheckCircleFilled className="text-[10px]" />
        Completed
      </span>
    );
  }
  if (status === 'error') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-50 text-red-500 text-[10px] font-medium">
        <CloseCircleFilled className="text-[10px]" />
        Error
      </span>
    );
  }
  return null;
};

/* ═══════════════════════════════════════════════════════════════
   Step renderer
   ═══════════════════════════════════════════════════════════════ */

function detectCodeLanguageInBash(command?: string): string | null {
  if (!command) return null;
  const cmd = command.toLowerCase();
  if (/(?:^|\s)python[23]?\s/.test(cmd) || /\.py\b/.test(cmd) || /(?:^|\s)pip\s/.test(cmd)) return 'python';
  if (/(?:^|\s)node\s/.test(cmd) || /(?:^|\s)npx?\s/.test(cmd) || /\.(?:js|ts)\b/.test(cmd)) return 'javascript';
  return null;
}

const StepRenderer: FC<{
  activeStep: ManusActiveStepInfo;
  outputs: ManusExecutionOutput[];
}> = ({ activeStep, outputs }) => {
  const { type, action, action_input, status } = activeStep;

  const command = useMemo(() => {
    if (!action_input) return undefined;
    if (typeof action_input === 'string') {
      try {
        const parsed = JSON.parse(action_input);
        return parsed.command || parsed.cmd;
      } catch {
        return action_input;
      }
    }
    return action_input?.command || action_input?.cmd;
  }, [action_input]);

  const codeLanguage = useMemo(
    () => (type === 'bash' ? detectCodeLanguageInBash(command) : null),
    [type, command]
  );

  switch (type) {
    case 'bash':
      if (codeLanguage) return <CodeExecutionRenderer outputs={outputs} language={codeLanguage} />;
      return <TerminalRenderer command={command} outputs={outputs} status={status} title={`Terminal - ${activeStep.title}`} />;
    case 'python':
      return <CodeExecutionRenderer outputs={outputs} language="python" />;
    case 'sql':
      return <SqlQueryRenderer outputs={outputs} />;
    case 'html':
      return <HtmlTabbedRenderer outputs={outputs} title={activeStep.title} />;
    case 'skill':
      if (action === 'skill_read') return <SkillReadRenderer outputs={outputs} skillName={activeStep.title} />;
      if (action === 'skill_exec' || action === 'execute_skill_script_file') return <SkillScriptRenderer outputs={outputs} skillName={activeStep.title} />;
      if (action === 'skill_list' || action === 'get_skill_resource' || action === 'load_skill') return <SkillCardRenderer outputs={outputs} skillName={activeStep.title} />;
      return <SkillReadRenderer outputs={outputs} skillName={activeStep.title} />;
    default:
      return <OutputRenderer outputs={outputs} />;
  }
};

/* ═══════════════════════════════════════════════════════════════
   Tab button — underline style (matching DB-GPT original)
   ═══════════════════════════════════════════════════════════════ */

const TabItem: FC<{
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}> = ({ active, onClick, icon, label }) => (
  <button
    onClick={onClick}
    className={classNames(
      'relative flex items-center gap-1.5 px-4 py-2.5 text-[13px] font-medium transition-colors whitespace-nowrap',
      active
        ? 'text-gray-900'
        : 'text-gray-400 hover:text-gray-600'
    )}
  >
    <span className="text-xs">{icon}</span>
    <span>{label}</span>
    {/* Active underline indicator */}
    {active && (
      <span className="absolute bottom-0 left-2 right-2 h-[2px] bg-gray-900 rounded-full" />
    )}
  </button>
);

/* ═══════════════════════════════════════════════════════════════
   Summary view
   ═══════════════════════════════════════════════════════════════ */

const SummaryView: FC<{ content: string }> = ({ content }) => (
  <div className="py-2 px-3">
    <div className="whitespace-normal">
      <GPTVisLite components={markdownComponents}>{content}</GPTVisLite>
    </div>
  </div>
);

/* ═══════════════════════════════════════════════════════════════
   File helpers
   ═══════════════════════════════════════════════════════════════ */

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
};

const getFileIcon = (fileName: string): string => {
  const ext = fileName.split('.').pop()?.toLowerCase() || '';
  const map: Record<string, string> = {
    html: '🌐', htm: '🌐', md: '📝', pdf: '📕',
    png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', svg: '🖼️', webp: '🖼️',
    py: '🐍', js: '📜', ts: '📜', java: '☕', go: '🔵', rs: '🦀',
    sql: '🗄️', csv: '📊', xlsx: '📊', xls: '📊',
    json: '📋', yaml: '📋', yml: '📋', xml: '📋',
    txt: '📄', log: '📄', zip: '📦', tar: '📦', gz: '📦',
  };
  return map[ext] || '📄';
};

const getFileTypeColor = (fileType: string): string => {
  const map: Record<string, string> = {
    deliverable: 'bg-blue-50 text-blue-600',
    conclusion: 'bg-green-50 text-green-600',
    tool_output: 'bg-purple-50 text-purple-600',
    write_file: 'bg-amber-50 text-amber-600',
  };
  return map[fileType] || 'bg-gray-50 text-gray-500';
};

/* ═══════════════════════════════════════════════════════════════
   TaskFilesView
   ═══════════════════════════════════════════════════════════════ */

/** Resolve a usable URL for a task file, handling derisk-fs:// URIs and object_path fallback */
const resolveTaskFilePreviewUrl = (file: ManusTaskFileItem): string | null => {
  // 1. Try direct preview_url
  const raw = file.preview_url || file.oss_url;
  if (raw) {
    if (raw.startsWith('derisk-fs://')) {
      const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || '';
      return `${apiBaseUrl}/api/v2/serve/file/files/preview?uri=${encodeURIComponent(raw)}`;
    }
    if (raw.startsWith('http')) return raw;
  }
  // 2. Try object_path → API endpoint (same as VisDAttach)
  if (file.object_path) {
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || '';
    return `${apiBaseUrl}/api/oss/getFileByFileName?fileName=${encodeURIComponent(file.object_path)}`;
  }
  return null;
};

const resolveTaskFileDownloadUrl = (file: ManusTaskFileItem): string | null => {
  const raw = file.download_url || file.oss_url;
  if (raw) {
    if (raw.startsWith('derisk-fs://')) {
      const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || '';
      return `${apiBaseUrl}/api/v2/serve/file/files/preview?uri=${encodeURIComponent(raw)}&download=true`;
    }
    if (raw.startsWith('http')) return raw;
  }
  if (file.object_path) {
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || '';
    return `${apiBaseUrl}/api/oss/getFileByFileName?fileName=${encodeURIComponent(file.object_path)}`;
  }
  return null;
};

const handleTaskFilePreview = async (file: ManusTaskFileItem) => {
  const url = resolveTaskFilePreviewUrl(file);
  if (!url) return;
  try {
    // Fetch and open as blob to force inline display (avoid server Content-Disposition: attachment)
    const resp = await fetch(url);
    const blob = await resp.blob();
    const mimeType = file.mime_type || (file.file_name?.endsWith('.txt') ? 'text/plain' : blob.type) || 'text/plain';
    const inlineBlob = new Blob([blob], { type: mimeType });
    const blobUrl = URL.createObjectURL(inlineBlob);
    window.open(blobUrl, '_blank', 'noopener,noreferrer');
  } catch {
    // Fallback: open URL directly
    window.open(url, '_blank', 'noopener,noreferrer');
  }
};

const handleTaskFileDownload = (file: ManusTaskFileItem) => {
  const url = resolveTaskFileDownloadUrl(file);
  if (!url) return;
  const a = document.createElement('a');
  a.href = url;
  a.download = file.file_name || 'download';
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
};

const TaskFilesView: FC<{ files: ManusTaskFileItem[] }> = ({ files }) => {
  if (!files || files.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-gray-400">
        <FolderOpenOutlined className="text-2xl text-gray-300 mb-2" />
        <div className="text-xs">暂无任务文件</div>
      </div>
    );
  }

  return (
    <div className="p-5">
      <div className="text-xs text-gray-400 mb-3">
        共 {files.length} 个文件，总大小 {formatFileSize(files.reduce((sum, f) => sum + f.file_size, 0))}
      </div>
      <div className="space-y-1.5">
        {files.map((file) => {
          const previewUrl = resolveTaskFilePreviewUrl(file);
          const downloadUrl = resolveTaskFileDownloadUrl(file);
          return (
            <div
              key={file.file_id}
              className="flex items-center gap-3 px-3.5 py-2.5 rounded-lg hover:bg-gray-50 transition-colors group"
            >
              <span className="text-base flex-shrink-0">{getFileIcon(file.file_name)}</span>
              <div className="flex-1 min-w-0">
                <div className="text-[13px] font-medium text-gray-700 truncate">{file.file_name}</div>
                <div className="flex items-center gap-2 mt-0.5">
                  {file.file_size > 0 && (
                    <span className="text-[11px] text-gray-400">{formatFileSize(file.file_size)}</span>
                  )}
                  {file.file_type && (
                    <span className={classNames('text-[10px] px-1.5 py-px rounded font-medium', getFileTypeColor(file.file_type))}>
                      {file.file_type}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                {previewUrl && (
                  <Tooltip title="预览">
                    <button
                      onClick={() => handleTaskFilePreview(file)}
                      className="w-7 h-7 rounded flex items-center justify-center text-gray-400 hover:text-blue-500 hover:bg-blue-50 transition-colors"
                    >
                      <EyeOutlined className="text-xs" />
                    </button>
                  </Tooltip>
                )}
                {downloadUrl && (
                  <Tooltip title="下载">
                    <button
                      onClick={() => handleTaskFileDownload(file)}
                      className="w-7 h-7 rounded flex items-center justify-center text-gray-400 hover:text-blue-500 hover:bg-blue-50 transition-colors"
                    >
                      <DownloadOutlined className="text-xs" />
                    </button>
                  </Tooltip>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════
   DeliverableContentView
   ═══════════════════════════════════════════════════════════════ */

/** Resolve the best usable URL for a deliverable file.
 *  For derisk-fs:// URIs, use the preview API (returns inline Content-Disposition).
 *  For regular HTTPS URLs, use directly. */
const resolveFileUrl = (file: ManusDeliverableFile): string | null => {
  const raw = file.content_url || file.download_url;
  if (!raw) return null;
  // derisk-fs:// URIs → use preview API endpoint for inline rendering
  if (raw.startsWith('derisk-fs://')) {
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || '';
    return `${apiBaseUrl}/api/v2/serve/file/files/preview?uri=${encodeURIComponent(raw)}`;
  }
  return raw;
};

/** Deliverable content view — fetches remote content and renders inline */
const DeliverableContentView: FC<{ file: ManusDeliverableFile }> = ({ file }) => {
  const { render_type, content, file_name, download_url } = file;
  const resolvedUrl = useMemo(() => resolveFileUrl(file), [file]);

  // DEBUG: trace deliverable file data reaching the component
  useEffect(() => {
    console.log('[DeliverableContentView] file:', JSON.stringify(file, null, 2));
    console.log('[DeliverableContentView] resolvedUrl:', resolvedUrl);
    console.log('[DeliverableContentView] render_type:', render_type, 'content_url:', file.content_url, 'download_url:', file.download_url);
  }, [file, resolvedUrl]);
  const [fetchedContent, setFetchedContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // For types that need text content (markdown, code, text), fetch from URL
  const needsFetch = ['markdown', 'code', 'text'].includes(render_type) && !content && resolvedUrl;

  useEffect(() => {
    if (!needsFetch) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(resolvedUrl!)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((text) => { if (!cancelled) setFetchedContent(text); })
      .catch((err) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [needsFetch, resolvedUrl]);

  const displayContent = content || fetchedContent || '';

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-400">
        <LoadingOutlined spin className="mr-2" />
        <span className="text-sm">加载文件内容...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-gray-400 text-sm">
        <div className="mb-2">加载失败: {error}</div>
        {resolvedUrl && (
          <a href={resolvedUrl} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline text-xs">
            在新窗口打开
          </a>
        )}
      </div>
    );
  }

  switch (render_type) {
    case 'iframe':
      return (
        <iframe
          src={resolvedUrl || undefined}
          srcDoc={!resolvedUrl && content ? content : undefined}
          className="w-full border-0"
          style={{ height: 'calc(100vh - 140px)', minHeight: '500px' }}
          sandbox="allow-scripts allow-same-origin"
        />
      );
    case 'markdown':
      return (
        <div className="py-2 px-3">
          <div className="whitespace-normal">
            <GPTVisLite components={markdownComponents}>{displayContent}</GPTVisLite>
          </div>
        </div>
      );
    case 'code':
      return (
        <div className="p-5">
          <div className="rounded-lg overflow-hidden border border-slate-200 bg-slate-900">
            <div className="flex items-center px-3 py-1.5 bg-slate-800 text-xs text-slate-400">
              <span>{file_name}</span>
            </div>
            <pre className="p-3 text-sm text-slate-100 overflow-x-auto max-h-[600px] overflow-y-auto">
              <code>{displayContent}</code>
            </pre>
          </div>
        </div>
      );
    case 'image':
      return (
        <div className="flex items-center justify-center p-6">
          <img src={resolvedUrl || content || ''} alt={file_name} className="max-w-full max-h-[600px] rounded-lg shadow-sm" />
        </div>
      );
    case 'pdf':
      return (
        <div className="h-full flex flex-col">
          <iframe src={resolvedUrl || ''} className="flex-1 w-full border-0" style={{ minHeight: '500px' }} />
        </div>
      );
    case 'text':
      return (
        <div className="p-5">
          <pre className="rounded-lg bg-gray-50 p-4 text-sm text-gray-700 overflow-x-auto max-h-[600px] overflow-y-auto whitespace-pre-wrap">
            {displayContent}
          </pre>
        </div>
      );
    default:
      return (
        <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
          {(resolvedUrl || download_url) ? (
            <a href={resolvedUrl || download_url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
              下载文件: {file_name}
            </a>
          ) : (
            <span>不支持预览此文件类型</span>
          )}
        </div>
      );
  }
};

/* ═══════════════════════════════════════════════════════════════
   Markdown to HTML helper for PDF export
   ═══════════════════════════════════════════════════════════════ */

/** Generate styled HTML document from markdown content for PDF export.
 *  Uses GitHub-flavored markdown styling for consistent PDF output. */
const renderMarkdownToHtml = (markdownContent: string, fileName?: string): string => {
  // Standard GitHub markdown CSS styles for PDF export
  const markdownStyles = `
    /* GitHub Markdown Styles for PDF */
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
      font-size: 16px;
      line-height: 1.6;
      color: #24292f;
      background: #ffffff;
      padding: 40px;
      max-width: 960px;
      margin: 0 auto;
    }
    h1 { font-size: 32px; font-weight: 600; margin: 24px 0 16px; padding-bottom: 8px; border-bottom: 1px solid #d0d7de; line-height: 1.25; }
    h2 { font-size: 24px; font-weight: 600; margin: 24px 0 16px; padding-bottom: 8px; border-bottom: 1px solid #d0d7de; line-height: 1.25; }
    h3 { font-size: 20px; font-weight: 600; margin: 24px 0 16px; line-height: 1.25; }
    h4 { font-size: 16px; font-weight: 600; margin: 24px 0 16px; line-height: 1.25; }
    h5 { font-size: 14px; font-weight: 600; margin: 24px 0 16px; line-height: 1.25; }
    h6 { font-size: 12px; font-weight: 600; margin: 24px 0 16px; line-height: 1.25; color: #57606a; }
    p { margin: 0 0 16px; }
    a { color: #0969da; text-decoration: none; }
    a:hover { text-decoration: underline; }
    strong { font-weight: 600; }
    em { font-style: italic; }
    code {
      font-family: ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace;
      font-size: 13.6px;
      padding: 2px 6px;
      background: rgba(175, 184, 193, 0.2);
      border-radius: 6px;
    }
    pre {
      font-family: ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace;
      font-size: 13.6px;
      padding: 16px;
      overflow-x: auto;
      background: #f6f8fa;
      border-radius: 6px;
      margin: 0 0 16px;
      line-height: 1.45;
    }
    pre code {
      background: transparent;
      padding: 0;
      font-size: inherit;
    }
    blockquote {
      margin: 0 0 16px;
      padding: 0 16px;
      border-left: 4px solid #d0d7de;
      color: #57606a;
    }
    blockquote p { margin: 0; }
    ul, ol { margin: 0 0 16px; padding-left: 32px; }
    li { margin: 4px 0; }
    li + li { margin-top: 4px; }
    table {
      border-collapse: collapse;
      margin: 0 0 16px;
      width: 100%;
      overflow: auto;
    }
    table th, table td {
      padding: 6px 13px;
      border: 1px solid #d0d7de;
    }
    table th { font-weight: 600; background: #f6f8fa; }
    table tr { background: #ffffff; }
    table tr:nth-child(2n) { background: #f6f8fa; }
    hr { height: 2px; padding: 0; margin: 24px 0; background-color: #d0d7de; border: 0; }
    img { max-width: 100%; box-sizing: content-box; background-color: #fff; }
    .task-list-item { list-style-type: none; }
    .task-list-item input { margin: 0 8px 0 -20px; vertical-align: middle; }
    /* Syntax highlighting (light theme for PDF) */
    .hljs-comment, .hljs-quote { color: #6e7781; }
    .hljs-keyword, .hljs-selector-tag { color: #cf222e; }
    .hljs-string, .hljs-attr { color: #0a3069; }
    .hljs-number, .hljs-literal { color: #0550ae; }
    .hljs-function, .hljs-title { color: #8250df; }
    .hljs-variable, .hljs-template-variable { color: #24292f; }
    .hljs-type, .hljs-class { color: #953800; }
    /* Print/PDF optimizations */
    @media print {
      body { padding: 20px; }
      pre { white-space: pre-wrap; word-wrap: break-word; }
      h1, h2, h3, h4, h5, h6 { page-break-after: avoid; }
      table, figure, img, pre { page-break-inside: avoid; }
      a { color: #24292f !important; }
    }
  `;

  // Simple markdown-to-HTML conversion (basic patterns)
  let html = markdownContent;

  // Escape HTML entities first
  html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // Code blocks (fenced with ```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const langClass = lang ? ` class="language-${lang}"` : '';
    return `<pre><code${langClass}>${code.trim()}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Headers
  html = html.replace(/^###### (.+)$/gm, '<h6>$1</h6>');
  html = html.replace(/^##### (.+)$/gm, '<h5>$1</h5>');
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Bold and italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/___(.+?)___/g, '<strong><em>$1</em></strong>');
  html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');
  html = html.replace(/_(.+?)_/g, '<em>$1</em>');

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

  // Images
  html = html.replace(/!\[([^\]]+)\]\(([^)]+)\)/g, '<img src="$2" alt="$1">');

  // Blockquotes
  html = html.replace(/^> (.+)$/gm, '<blockquote><p>$1</p></blockquote>');

  // Horizontal rule
  html = html.replace(/^---$/gm, '<hr>');
  html = html.replace(/^\*\*\*$/gm, '<hr>');

  // Unordered lists (collect consecutive list items)
  html = html.replace(/^(?:[-*] .+\n?)+/gm, (match) => {
    const items = match.trim().split('\n').map(line => `<li>${line.replace(/^[-*] /, '')}</li>`).join('\n');
    return `<ul>\n${items}\n</ul>`;
  });

  // Ordered lists (collect consecutive list items)
  html = html.replace(/^(?:\d+\. .+\n?)+/gm, (match) => {
    const items = match.trim().split('\n').map(line => `<li>${line.replace(/^\d+\. /, '')}</li>`).join('\n');
    return `<ol>\n${items}\n</ol>`;
  });

  // Paragraphs (wrap remaining non-tagged blocks)
  html = html.split('\n\n').map(block => {
    const trimmed = block.trim();
    if (trimmed && !/^<[hpuoblirtc]/.test(trimmed)) {
      return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
    }
    return block;
  }).join('\n');

  const title = fileName ? fileName.replace(/\.[^.]+$/, '') : 'Markdown Document';
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${title}</title>
  <style>${markdownStyles}</style>
</head>
<body>
${html}
</body>
</html>`;
};

/* ═══════════════════════════════════════════════════════════════
   Main component
   ═══════════════════════════════════════════════════════════════ */

type ActiveTab = 'execution' | 'task_files' | 'summary' | `deliverable_${string}`;

const VisManusRightPanel: FC<IProps> = ({ data }) => {
  const {
    active_step,
    outputs = [],
    is_running,
    summary_content,
    panel_view,
    task_files = [],
    deliverable_files = [],
    steps_map,
  } = data;

  const [activeTab, setActiveTab] = useState<ActiveTab>('execution');
  const [inputCollapsed, setInputCollapsed] = useState(false);
  const [exporting, setExporting] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  // Track user-selected step via CLICK_FOLDER event
  const [selectedStep, setSelectedStep] = useState<ManusStepData | null>(null);

  const hasSummary = !!summary_content;
  const hasTaskFiles = task_files.length > 0;
  const hasDeliverables = deliverable_files.length > 0;

  // Whether to show PDF export (only on summary / deliverable tabs)
  const showPdfExport = activeTab === 'summary' || (typeof activeTab === 'string' && activeTab.startsWith('deliverable_'));

  // When backend active_step changes (new step), clear user selection to follow live
  const activeStepIdRef = useRef(active_step?.id);
  useEffect(() => {
    if (active_step?.id && active_step.id !== activeStepIdRef.current) {
      activeStepIdRef.current = active_step.id;
      // Backend moved to a new step — resume live following
      if (selectedStep) {
        setSelectedStep(null);
      }
    }
  }, [active_step?.id]);

  // Listen for CLICK_FOLDER events to switch displayed step
  // Use a ref to avoid re-registering the handler on every steps_map change
  const stepsMapRef = useRef(steps_map);
  stepsMapRef.current = steps_map;

  useEffect(() => {
    const handler = (payload: { uid?: string }) => {
      const currentMap = stepsMapRef.current;
      if (!payload?.uid || !currentMap) return;
      const stepData = currentMap[payload.uid];
      if (stepData) {
        setSelectedStep(stepData);
        setActiveTab('execution');
        setInputCollapsed(false);
      }
    };
    ee.on(EVENTS.CLICK_FOLDER, handler);
    return () => {
      ee.off(EVENTS.CLICK_FOLDER, handler);
    };
  }, []); // stable — no dependency on steps_map

  // Listen for SWITCH_TAB events from left panel links
  useEffect(() => {
    const handler = (payload: { tab?: string }) => {
      if (payload?.tab) {
        setActiveTab(payload.tab as ActiveTab);
        setSelectedStep(null);
      }
    };
    ee.on(EVENTS.SWITCH_TAB, handler);
    return () => { ee.off(EVENTS.SWITCH_TAB, handler); };
  }, []);

  // Determine which step to display: user-selected or backend-active
  const displayStep = selectedStep?.active_step ?? active_step;
  const displayOutputs = selectedStep?.outputs ?? outputs;

  // Auto-switch to deliverable or summary tab when task completes
  useEffect(() => {
    if (panel_view === 'deliverable' && hasDeliverables) {
      setActiveTab(`deliverable_${deliverable_files[0].file_id}`);
    } else if (panel_view === 'summary' && hasSummary) {
      setActiveTab('summary');
    }
  }, [panel_view, hasSummary, hasDeliverables, deliverable_files]);

  const matchedDeliverable = useMemo(() => {
    if (typeof activeTab === 'string' && activeTab.startsWith('deliverable_')) {
      const fileId = activeTab.replace('deliverable_', '');
      return deliverable_files.find((f) => f.file_id === fileId);
    }
    return undefined;
  }, [activeTab, deliverable_files]);

  /* ── PDF export handlers ── */
  const handleExportPDF = useCallback(async () => {
    // For deliverable files, fetch content and generate PDF from it
    if (matchedDeliverable) {
      const url = resolveFileUrl(matchedDeliverable);
      const renderType = matchedDeliverable.render_type;
      if (url) {
        setExporting(true);
        try {
          const resp = await fetch(url);
          const rawContent = await resp.text();

          // Determine how to render content based on render_type
          let htmlContent: string;
          if (renderType === 'markdown') {
            // Convert markdown to styled HTML for PDF
            htmlContent = renderMarkdownToHtml(rawContent, matchedDeliverable.file_name);
          } else if (renderType === 'code' || renderType === 'text') {
            // Wrap code/text in a styled HTML document
            htmlContent = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 14px; padding: 40px; background: #fff; color: #24292f; white-space: pre-wrap; word-wrap: break-word; }
    @media print { body { padding: 20px; } }
  </style>
</head>
<body>${rawContent}</body>
</html>`;
          } else {
            // Default: treat as HTML (iframe type or unknown)
            htmlContent = rawContent;
          }

          // Open content in hidden iframe for html2canvas capture
          const tempIframe = document.createElement('iframe');
          tempIframe.style.cssText = 'position:fixed;left:-9999px;width:1200px;height:auto;border:none;';
          document.body.appendChild(tempIframe);
          tempIframe.contentDocument?.open();
          tempIframe.contentDocument?.write(htmlContent);
          tempIframe.contentDocument?.close();
          await new Promise(resolve => setTimeout(resolve, 2000)); // Wait for content to render
          const body = tempIframe.contentDocument?.body;
          if (body) {
            const canvas = await html2canvas(body, { useCORS: true, scale: 2, backgroundColor: '#ffffff', width: 1200 });
            const imgData = canvas.toDataURL('image/png');
            const pdf = new jsPDF('p', 'mm', 'a4');
            const imgWidth = pdf.internal.pageSize.getWidth() - 20;
            const pageHeight = pdf.internal.pageSize.getHeight() - 20;
            const imgHeight = (canvas.height * imgWidth) / canvas.width;
            const totalPages = Math.ceil(imgHeight / pageHeight);
            for (let i = 0; i < totalPages; i++) {
              if (i > 0) pdf.addPage();
              pdf.addImage(imgData, 'PNG', 10, -pageHeight * i + 10, imgWidth, imgHeight);
            }
            // Generate PDF filename based on original file
            const pdfFileName = matchedDeliverable.file_name?.replace(/\.(md|markdown|txt|html?|py|js|ts)$/i, '.pdf') || 'report.pdf';
            pdf.save(pdfFileName);
            message.success('PDF 导出成功');
          }
          document.body.removeChild(tempIframe);
        } catch (error) {
          console.error('PDF export error:', error);
          message.error('PDF 导出失败');
        } finally {
          setExporting(false);
        }
        return;
      }
    }
    // Fallback: capture current tab content directly
    const container = contentRef.current;
    if (!container) return;
    setExporting(true);
    try {
      const canvas = await html2canvas(container, { useCORS: true, scale: 2, backgroundColor: '#ffffff' });
      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF('p', 'mm', 'a4');
      const imgWidth = pdf.internal.pageSize.getWidth() - 20;
      const pageHeight = pdf.internal.pageSize.getHeight() - 20;
      const imgHeight = (canvas.height * imgWidth) / canvas.width;
      const totalPages = Math.ceil(imgHeight / pageHeight);
      for (let i = 0; i < totalPages; i++) {
        if (i > 0) pdf.addPage();
        pdf.addImage(imgData, 'PNG', 10, -pageHeight * i + 10, imgWidth, imgHeight);
      }
      pdf.save('report.pdf');
      message.success('PDF 导出成功');
    } catch (error) {
      console.error('PDF export error:', error);
      message.error('PDF 导出失败');
    } finally {
      setExporting(false);
    }
  }, [matchedDeliverable]);

  const handlePrint = useCallback(async () => {
    // For deliverable files, use a temp full-height iframe for accurate printing
    if (matchedDeliverable) {
      const url = resolveFileUrl(matchedDeliverable);
      const renderType = matchedDeliverable.render_type;
      if (url) {
        try {
          const resp = await fetch(url);
          const rawContent = await resp.text();

          // Determine how to render content based on render_type
          let htmlContent: string;
          if (renderType === 'markdown') {
            htmlContent = renderMarkdownToHtml(rawContent, matchedDeliverable.file_name);
          } else if (renderType === 'code' || renderType === 'text') {
            htmlContent = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 14px; padding: 40px; background: #fff; color: #24292f; white-space: pre-wrap; word-wrap: break-word; }
  </style>
</head>
<body>${rawContent}</body>
</html>`;
          } else {
            htmlContent = rawContent;
          }

          // Create hidden full-height iframe with the complete HTML content
          const tempIframe = document.createElement('iframe');
          tempIframe.style.cssText = 'position:fixed;left:-9999px;width:1200px;height:auto;border:none;';
          document.body.appendChild(tempIframe);
          const iframeDoc = tempIframe.contentDocument;
          if (iframeDoc) {
            iframeDoc.open();
            iframeDoc.write(htmlContent);
            iframeDoc.close();
            // Inject additional print styles
            const printStyle = iframeDoc.createElement('style');
            printStyle.textContent = `
              @media print {
                html, body { height: auto !important; overflow: visible !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
                * { max-height: none !important; }
                h1, h2, h3, h4, h5, h6 { page-break-after: avoid; }
                table, figure, img, pre { page-break-inside: avoid; }
              }
            `;
            iframeDoc.head.appendChild(printStyle);
          }
          // Wait for content to render
          await new Promise(resolve => setTimeout(resolve, 2000));
          tempIframe.contentWindow?.print();
          // Cleanup after print dialog closes
          setTimeout(() => {
            try { document.body.removeChild(tempIframe); } catch {}
          }, 1000);
          return;
        } catch (e) {
          console.error('Print via temp iframe failed:', e);
          // Fall through to fallback
        }
      }
    }

    // Fallback: print current container content
    const container = contentRef.current;
    if (!container) return;

    const printId = 'manus-print-area';
    container.setAttribute('id', printId);
    const style = document.createElement('style');
    style.setAttribute('data-print-helper', 'true');
    style.textContent = `
      @media print {
        body * { visibility: hidden !important; }
        #${printId}, #${printId} * {
          visibility: visible !important;
          overflow: visible !important;
          max-height: none !important;
          height: auto !important;
        }
        #${printId} {
          position: absolute;
          left: 0;
          top: 0;
          width: 100%;
          height: auto !important;
          overflow: visible !important;
        }
        html, body {
          height: auto !important;
          overflow: visible !important;
        }
      }
    `;
    document.head.appendChild(style);
    window.print();
    document.head.removeChild(style);
    container.removeAttribute('id');
  }, [matchedDeliverable]);

  const pdfMenuItems: MenuProps['items'] = useMemo(() => [
    { key: 'export', icon: <DownloadOutlined />, label: '导出文件', onClick: handleExportPDF },
    { key: 'print', icon: <PrinterOutlined />, label: '打印', onClick: handlePrint },
  ], [handleExportPDF, handlePrint]);

  // No data at all — minimal placeholder, parent container already shows the workspace empty state
  if (!displayStep && !hasSummary && !hasTaskFiles && !hasDeliverables) {
    return null;
  }

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 56px)' }}>
      {/* ── Tab bar (underline style, matching DB-GPT original) ── */}
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-1">
        <div className="flex items-center overflow-x-auto">
          {/* 1. 执行步骤 */}
          <TabItem
            active={activeTab === 'execution'}
            onClick={() => { setActiveTab('execution'); setSelectedStep(null); }}
            icon={<DesktopOutlined />}
            label="执行步骤"
          />
          {/* 2. 任务文件 */}
          {hasTaskFiles && (
            <TabItem
              active={activeTab === 'task_files'}
              onClick={() => setActiveTab('task_files')}
              icon={<FolderOpenOutlined />}
              label={`任务文件 ${task_files.length}`}
            />
          )}
          {/* 3. 摘要 */}
          {hasSummary && (
            <TabItem
              active={activeTab === 'summary'}
              onClick={() => setActiveTab('summary')}
              icon={<ProfileOutlined />}
              label="摘要"
            />
          )}
          {/* 4. Dynamic deliverable file tabs */}
          {deliverable_files.map((file) => (
            <TabItem
              key={file.file_id}
              active={activeTab === `deliverable_${file.file_id}`}
              onClick={() => setActiveTab(`deliverable_${file.file_id}`)}
              icon={<FileOutlined />}
              label={file.file_name}
            />
          ))}
        </div>

        {/* PDF export — only on summary / deliverable tabs */}
        {showPdfExport && (
          <div className="flex items-center pr-3 flex-shrink-0">
            <Dropdown menu={{ items: pdfMenuItems }} placement="bottomRight">
              <button
                className={classNames(
                  'flex items-center gap-1 px-2.5 py-1 rounded text-xs transition-colors',
                  exporting
                    ? 'text-blue-500 cursor-wait'
                    : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
                )}
                disabled={exporting}
              >
                <FilePdfOutlined className="text-[11px]" />
                <span>{exporting ? '导出中...' : '导出 PDF'}</span>
              </button>
            </Dropdown>
          </div>
        )}
      </div>

      {/* ── Tab content ── */}
      <div className="flex-1 overflow-y-auto bg-white" ref={contentRef}>
        {activeTab === 'task_files' && hasTaskFiles ? (
          <TaskFilesView files={task_files} />
        ) : activeTab === 'summary' && hasSummary ? (
          <SummaryView content={summary_content!} />
        ) : matchedDeliverable ? (
          <DeliverableContentView file={matchedDeliverable} />
        ) : (
          /* Execution tab */
          displayStep ? (
            <div className="flex flex-col h-full">
              {/* Compact step info bar */}
              <div
                className="flex items-center justify-between px-4 py-2 border-b border-gray-100 cursor-pointer select-none hover:bg-gray-50/50 transition-colors flex-shrink-0"
                onClick={() => setInputCollapsed(prev => !prev)}
              >
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  <div className={classNames('w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 text-xs', getIconBgClass(displayStep.type))}>
                    {getStepTypeIcon(displayStep.type)}
                  </div>
                  <div className="text-[13px] font-medium text-gray-700 truncate">
                    {displayStep.title}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <StatusBadge status={displayStep.status} isRunning={!selectedStep && is_running} />
                  <span className="text-gray-300 text-[10px]">
                    {inputCollapsed ? <CaretDownOutlined /> : <CaretUpOutlined />}
                  </span>
                </div>
              </div>

              {/* Step content — fills remaining area */}
              {!inputCollapsed && (
                <div className="flex-1 min-h-0 overflow-auto p-3">
                  <StepRenderer activeStep={displayStep} outputs={displayOutputs} />
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-48">
              <LoadingOutlined spin className="text-xl text-gray-300 mb-2" />
              <div className="text-xs text-gray-300">加载中...</div>
            </div>
          )
        )}
      </div>
    </div>
  );
};

export default VisManusRightPanel;
