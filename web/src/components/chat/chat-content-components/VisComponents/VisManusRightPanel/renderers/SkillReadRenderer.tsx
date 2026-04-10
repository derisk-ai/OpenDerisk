'use client';

import React, { FC, useMemo } from 'react';
import { Tag } from 'antd';
import {
  FileMarkdownOutlined,
  CodeOutlined,
  FolderOutlined,
  FileOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { GPTVisLite } from '@antv/gpt-vis';
import { markdownComponents } from '../../../config';
import type { ManusExecutionOutput } from '@/types/manus';

interface IProps {
  outputs: ManusExecutionOutput[];
  skillName?: string;
}

/** YAML frontmatter fields */
interface SkillFrontmatter {
  name?: string;
  description?: string;
  version?: string;
  author?: string;
  tags?: string[];
  [key: string]: any;
}

/** Content type detection */
type ContentKind = 'markdown' | 'code' | 'directory' | 'text';

/** Parse YAML frontmatter from SKILL.md content.
 *  Supports block scalars (| and >) for multi-line values like description. */
function parseFrontmatter(raw: string): { meta: SkillFrontmatter; body: string } {
  const match = raw.match(/^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$/);
  if (!match) return { meta: {}, body: raw };

  const yamlBlock = match[1];
  const body = match[2];
  const meta: SkillFrontmatter = {};
  const lines = yamlBlock.split('\n');

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    i++;

    if (!trimmed || trimmed.startsWith('#')) continue;
    const colonIdx = trimmed.indexOf(':');
    if (colonIdx < 0) continue;

    const key = trimmed.slice(0, colonIdx).trim();
    let value = trimmed.slice(colonIdx + 1).trim();

    // Strip surrounding quotes
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }

    // Handle inline list: [a, b, c]
    if (value.startsWith('[') && value.endsWith(']')) {
      meta[key] = value
        .slice(1, -1)
        .split(',')
        .map((s) => s.trim().replace(/^['"]|['"]$/g, ''));
    } else if (value === '|' || value === '>') {
      // Block scalar: collect subsequent indented lines
      const blockLines: string[] = [];
      while (i < lines.length) {
        const nextLine = lines[i];
        // Block continues while line is indented (starts with spaces/tabs) or is empty
        if (nextLine.match(/^[ \t]/) || nextLine.trim() === '') {
          blockLines.push(nextLine.replace(/^[ \t]{1,2}/, '')); // strip 1-2 leading spaces
          i++;
        } else {
          break;
        }
      }
      const joined = value === '|'
        ? blockLines.join('\n').trim()
        : blockLines.join(' ').replace(/\s+/g, ' ').trim();
      if (joined) meta[key] = joined;
    } else if (value) {
      meta[key] = value;
    }
  }

  return { meta, body };
}

/** Detect content kind from the body text */
function detectContentKind(body: string, filePath?: string): ContentKind {
  // Directory listing: only match the exact format from _list_local_directory / _render_directory_listing
  // Pattern: "Skill directory: /path" header followed by "  d dirname" / "  - filename (123 bytes)" lines
  if (/^Skill directory:/m.test(body) || /^Directory:/m.test(body)) {
    return 'directory';
  }

  // Code files by extension
  if (filePath) {
    const ext = filePath.split('.').pop()?.toLowerCase();
    if (ext && ['py', 'js', 'ts', 'sh', 'bash', 'json', 'yaml', 'yml', 'sql', 'go', 'java', 'rs', 'rb', 'css', 'html'].includes(ext)) {
      return 'code';
    }
  }

  // Markdown: has headers, lists, links, code fences, etc.
  if (/^#{1,6}\s/m.test(body) || /^\s*[-*]\s/m.test(body) || /\[.*\]\(.*\)/.test(body) || /^```/m.test(body)) {
    return 'markdown';
  }

  return 'text';
}

/** Get language hint from file path */
function getLangFromPath(filePath?: string): string {
  if (!filePath) return 'text';
  const ext = filePath.split('.').pop()?.toLowerCase();
  const map: Record<string, string> = {
    py: 'python', js: 'javascript', ts: 'typescript', sh: 'bash',
    json: 'json', yaml: 'yaml', yml: 'yaml', sql: 'sql',
    go: 'go', java: 'java', rs: 'rust', rb: 'ruby',
    css: 'css', html: 'html', md: 'markdown',
  };
  return map[ext || ''] || 'text';
}

/* ═══════════════════════════════════════════════════════════════
   Sub-components
   ═══════════════════════════════════════════════════════════════ */

/** Frontmatter metadata card */
const MetadataCard: FC<{ meta: SkillFrontmatter }> = ({ meta }) => {
  const displayFields = Object.entries(meta).filter(
    ([k]) => !['name', 'description'].includes(k)
  );

  return (
    <div className="rounded-lg border border-violet-200 bg-gradient-to-r from-violet-50 to-purple-50 p-4 mb-4">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white text-lg shadow-sm flex-shrink-0">
          &#129513;
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-semibold text-slate-800">
            {meta.name || 'Skill'}
          </h4>
          {meta.description && (
            <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
              {meta.description}
            </p>
          )}
        </div>
      </div>

      {displayFields.length > 0 && (
        <div className="mt-3 pt-3 border-t border-violet-200/60 flex flex-wrap gap-x-4 gap-y-1.5">
          {displayFields.map(([key, value]) => (
            <div key={key} className="flex items-center gap-1 text-xs">
              <span className="text-slate-400 font-medium">{key}:</span>
              {Array.isArray(value) ? (
                <span className="flex gap-1">
                  {value.map((v, i) => (
                    <Tag key={i} color="purple" className="text-[10px] leading-tight m-0">
                      {v}
                    </Tag>
                  ))}
                </span>
              ) : (
                <span className="text-slate-600">{String(value)}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

/** Markdown body renderer */
const MarkdownBody: FC<{ content: string }> = ({ content }) => (
  <div className="rounded-lg border border-slate-200 bg-white p-4">
    <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-3">
      <FileMarkdownOutlined />
      <span>Skill Instructions</span>
    </div>
    <div className="whitespace-normal prose-sm prose-slate max-w-none">
      <GPTVisLite components={markdownComponents}>{content}</GPTVisLite>
    </div>
  </div>
);

/** Code body renderer */
const CodeBody: FC<{ content: string; language: string; fileName?: string }> = ({
  content,
  language,
  fileName,
}) => (
  <div className="rounded-lg border border-slate-200 overflow-hidden">
    <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 text-xs text-slate-400">
      <CodeOutlined />
      <span>{fileName || language}</span>
    </div>
    <pre className="p-3 bg-slate-900 text-sm text-slate-100 overflow-x-auto max-h-[600px] overflow-y-auto">
      <code>{content}</code>
    </pre>
  </div>
);

/** Directory listing renderer */
const DirectoryBody: FC<{ content: string }> = ({ content }) => {
  const lines = content.split('\n');

  return (
    <div className="rounded-lg border border-slate-200 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 text-xs text-slate-500 border-b border-slate-200">
        <FolderOutlined />
        <span>Skill Directory</span>
      </div>
      <div className="p-3 bg-white font-mono text-sm space-y-0.5">
        {lines.map((line, i) => {
          const trimmed = line.trimStart();
          const indent = line.length - trimmed.length;
          const isDir = trimmed.startsWith('d ');
          const isFile = trimmed.startsWith('- ');
          const isHeader = !isDir && !isFile && trimmed.includes(':');

          if (!trimmed) return null;

          return (
            <div key={i} className="flex items-center gap-1.5" style={{ paddingLeft: `${indent * 4}px` }}>
              {isDir ? (
                <>
                  <FolderOutlined className="text-amber-500 text-xs flex-shrink-0" />
                  <span className="text-slate-700 font-medium">{trimmed.slice(2)}</span>
                </>
              ) : isFile ? (
                <>
                  <FileOutlined className="text-slate-400 text-xs flex-shrink-0" />
                  <span className="text-slate-600">{trimmed.slice(2)}</span>
                </>
              ) : isHeader ? (
                <span className="text-slate-500 font-medium">{trimmed}</span>
              ) : (
                <span className="text-slate-500">{trimmed}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** Plain text body renderer */
const TextBody: FC<{ content: string }> = ({ content }) => (
  <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
    <pre className="text-sm text-slate-700 whitespace-pre-wrap overflow-x-auto">
      {content}
    </pre>
  </div>
);

/* ═══════════════════════════════════════════════════════════════
   Main renderer
   ═══════════════════════════════════════════════════════════════ */

const SkillReadRenderer: FC<IProps> = ({ outputs, skillName }) => {
  const parsed = useMemo(() => {
    // Combine all text/code/markdown outputs
    const allContent = outputs
      .map((o) => String(o.content || ''))
      .join('\n');

    if (!allContent.trim()) {
      return { meta: {} as SkillFrontmatter, body: '', kind: 'text' as ContentKind };
    }

    const { meta, body } = parseFrontmatter(allContent);

    // Try to get file_path from output metadata
    const filePath = outputs[0]?.content?.file_path;
    const kind = detectContentKind(body, typeof filePath === 'string' ? filePath : undefined);

    return { meta, body, kind, filePath };
  }, [outputs]);

  const { meta, body, kind, filePath } = parsed;

  // Empty state
  if (!body && Object.keys(meta).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-slate-400">
        <InfoCircleOutlined className="text-2xl text-slate-300 mb-2" />
        <div className="text-xs">Skill 内容加载中...</div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* YAML frontmatter metadata card — always show if we have a name */}
      {(Object.keys(meta).length > 0 || skillName) && (
        <MetadataCard meta={{ ...meta, name: meta.name || skillName || 'Skill' }} />
      )}

      {/* Body content - rendered by type */}
      {body.trim() && (
        <>
          {kind === 'markdown' && <MarkdownBody content={body} />}
          {kind === 'code' && (
            <CodeBody
              content={body}
              language={getLangFromPath(typeof filePath === 'string' ? filePath : undefined)}
              fileName={typeof filePath === 'string' ? filePath.split('/').pop() : undefined}
            />
          )}
          {kind === 'directory' && <DirectoryBody content={body} />}
          {kind === 'text' && <TextBody content={body} />}
        </>
      )}
    </div>
  );
};

export default SkillReadRenderer;
