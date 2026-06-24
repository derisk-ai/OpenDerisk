'use client';

import { Tabs } from 'antd';
import { BookOutlined, FileOutlined } from '@ant-design/icons';
import type { VerbatOut } from '@/types/knowledge-vault';
import KnowledgeTreePanel from './KnowledgeTreePanel';
import FilesTreePanel from './FilesTreePanel';
import { useSpace } from './SpaceContext';

export default function LeftSidebar({
  onCreateDoc,
  onCreateRaw,
  onVerbatSelect,
}: {
  onCreateDoc: () => void;
  onCreateRaw: () => void;
  onVerbatSelect: (verbat: VerbatOut) => void;
}) {
  const { leftTab, setLeftTab } = useSpace();

  return (
    <Tabs
      activeKey={leftTab}
      size="small"
      onChange={(k) => setLeftTab(k as 'knowledge' | 'files')}
      className="h-full flex flex-col kv-tabs"
      items={[
        {
          key: 'knowledge',
          label: (
            <span className="flex items-center gap-1 px-2">
              <BookOutlined className="text-sm" />
              Knowledge
            </span>
          ),
          children: <KnowledgeTreePanel onCreate={onCreateDoc} />,
        },
        {
          key: 'files',
          label: (
            <span className="flex items-center gap-1 px-2">
              <FileOutlined className="text-sm" />
              Files
            </span>
          ),
          children: <FilesTreePanel onCreate={onCreateRaw} onVerbatSelect={onVerbatSelect} />,
        },
      ]}
    />
  );
}
