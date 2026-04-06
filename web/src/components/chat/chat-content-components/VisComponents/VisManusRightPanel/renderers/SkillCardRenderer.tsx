'use client';

import React, { FC, useState, useMemo, useCallback } from 'react';
import { Button, Tooltip, Tree, Empty } from 'antd';
import {
  DownloadOutlined,
  PlusOutlined,
  FolderOutlined,
  FileOutlined,
  FileMarkdownOutlined,
  CodeOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons';
import type { ManusExecutionOutput } from '@/types/manus';

interface SkillMeta {
  name: string;
  description?: string;
  files?: SkillFile[];
}

interface SkillFile {
  name: string;
  path: string;
  type?: string;
  content?: string;
}

interface IProps {
  outputs: ManusExecutionOutput[];
  skillName?: string;
  skillDescription?: string;
}

/** File icon by extension */
const getFileIcon = (name: string) => {
  const ext = name.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'md':
      return <FileMarkdownOutlined className="text-blue-500" />;
    case 'py':
    case 'js':
    case 'ts':
    case 'sh':
    case 'json':
    case 'yaml':
    case 'yml':
      return <CodeOutlined className="text-amber-500" />;
    default:
      return <FileOutlined className="text-slate-400" />;
  }
};

/** Language detection by extension */
const getLang = (name: string): string => {
  const ext = name.split('.').pop()?.toLowerCase();
  const map: Record<string, string> = {
    py: 'python',
    js: 'javascript',
    ts: 'typescript',
    sh: 'bash',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    sql: 'sql',
    md: 'markdown',
    html: 'html',
    css: 'css',
  };
  return map[ext || ''] || 'text';
};

/** Compact skill card (collapsed view) */
const CompactView: FC<{
  name: string;
  description?: string;
  fileCount: number;
  onExpand: () => void;
}> = ({ name, description, fileCount, onExpand }) => (
  <div className="rounded-xl border border-slate-200 bg-white p-4 hover:shadow-sm transition-shadow">
    <div className="flex items-start gap-3">
      <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-lg shadow-sm">
        &#9889;
      </div>
      <div className="flex-1 min-w-0">
        <h4 className="text-sm font-semibold text-slate-800">{name}</h4>
        {description && (
          <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">
            {description}
          </p>
        )}
      </div>
      <div className="flex items-center gap-1.5">
        <Tooltip title="下载">
          <Button type="text" size="small" icon={<DownloadOutlined />} />
        </Tooltip>
        <Tooltip title="添加到我的技能">
          <Button type="text" size="small" icon={<PlusOutlined />} />
        </Tooltip>
      </div>
    </div>
    <button
      className="mt-3 text-xs text-blue-500 hover:text-blue-600 flex items-center gap-1"
      onClick={onExpand}
    >
      <FolderOutlined /> {fileCount} 个文件
    </button>
  </div>
);

/** Expanded view with file browser */
const ExpandedView: FC<{
  name: string;
  files: SkillFile[];
  onCollapse: () => void;
}> = ({ name, files, onCollapse }) => {
  const [selectedFile, setSelectedFile] = useState<SkillFile | null>(null);

  const treeData = useMemo(() => {
    return files.map((f, i) => ({
      title: (
        <span className="flex items-center gap-1.5 text-sm">
          {getFileIcon(f.name)}
          {f.name}
        </span>
      ),
      key: f.path || String(i),
      isLeaf: true,
    }));
  }, [files]);

  const handleSelect = useCallback(
    (keys: any[]) => {
      if (keys.length > 0) {
        const file = files.find((f) => (f.path || files.indexOf(f).toString()) === keys[0]);
        setSelectedFile(file || null);
      }
    },
    [files]
  );

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-slate-50 border-b border-slate-200">
        <button onClick={onCollapse} className="text-slate-400 hover:text-slate-600">
          <ArrowLeftOutlined className="text-xs" />
        </button>
        <div className="w-6 h-6 rounded bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs">
          &#9889;
        </div>
        <span className="text-sm font-semibold text-slate-700">{name}</span>
        <div className="ml-auto flex items-center gap-1.5">
          <Button type="text" size="small" icon={<DownloadOutlined />} />
          <Button type="text" size="small" icon={<PlusOutlined />} />
        </div>
      </div>

      {/* File browser */}
      <div className="flex divide-x divide-slate-200" style={{ height: '400px' }}>
        {/* Left sidebar - file tree */}
        <div className="w-[200px] overflow-y-auto p-2 bg-slate-50">
          <Tree
            treeData={treeData}
            onSelect={handleSelect}
            selectedKeys={
              selectedFile
                ? [selectedFile.path || files.indexOf(selectedFile).toString()]
                : []
            }
            showIcon={false}
            className="text-xs"
          />
        </div>

        {/* Right content - file preview */}
        <div className="flex-1 overflow-auto">
          {selectedFile ? (
            <div className="h-full flex flex-col">
              <div className="px-3 py-1.5 bg-slate-100 border-b border-slate-200 text-xs text-slate-500">
                {selectedFile.name}
              </div>
              <pre className="flex-1 p-3 bg-slate-900 text-sm text-slate-100 overflow-auto">
                <code>
                  {selectedFile.content || '// Content loading...'}
                </code>
              </pre>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center">
              <Empty
                description="选择文件预览"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

/** Main skill card renderer */
const SkillCardRenderer: FC<IProps> = ({
  outputs,
  skillName,
  skillDescription,
}) => {
  const [expanded, setExpanded] = useState(false);

  const skillData = useMemo(() => {
    // Try to extract skill metadata from outputs
    const jsonOutput = outputs.find(
      (o) => o.output_type === 'json' || o.output_type === 'code'
    );
    if (jsonOutput) {
      try {
        const parsed =
          typeof jsonOutput.content === 'string'
            ? JSON.parse(jsonOutput.content)
            : jsonOutput.content;
        return {
          name: parsed.name || skillName || 'Skill',
          description: parsed.description || skillDescription,
          files: parsed.files || [],
        } as SkillMeta;
      } catch {
        // fallback
      }
    }
    return {
      name: skillName || 'Skill',
      description: skillDescription,
      files: [],
    } as SkillMeta;
  }, [outputs, skillName, skillDescription]);

  if (expanded && skillData.files.length > 0) {
    return (
      <ExpandedView
        name={skillData.name}
        files={skillData.files}
        onCollapse={() => setExpanded(false)}
      />
    );
  }

  return (
    <CompactView
      name={skillData.name}
      description={skillData.description}
      fileCount={skillData.files.length}
      onExpand={() => setExpanded(true)}
    />
  );
};

export default SkillCardRenderer;
