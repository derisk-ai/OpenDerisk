'use client';

import type { VerbatOut } from '@/types/knowledge-vault';
import GraphNavPanel from './GraphNavPanel';
import KnowledgeTreePanel from './KnowledgeTreePanel';
import FilesTreePanel from './FilesTreePanel';
import { useSpace } from './SpaceContext';

interface LeftSidebarProps {
  onCreateDoc: () => void;
  onCreateRaw: () => void;
  onVerbatSelect: (verbat: VerbatOut) => void;
}

export default function LeftSidebar({
  onCreateDoc,
  onCreateRaw,
  onVerbatSelect,
}: LeftSidebarProps) {
  const { view } = useSpace();

  switch (view) {
    case 'raw':
      return <FilesTreePanel onCreate={onCreateRaw} onVerbatSelect={onVerbatSelect} />;
    case 'wiki':
      return <KnowledgeTreePanel onCreate={onCreateDoc} />;
    case 'graph':
      return <GraphNavPanel />;
    case 'schema':
    case 'lint':
    case 'settings':
    default:
      return null;
  }
}
