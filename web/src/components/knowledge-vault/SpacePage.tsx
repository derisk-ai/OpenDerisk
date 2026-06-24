'use client';

import { useCallback, useState } from 'react';
import type { VerbatOut } from '@/types/knowledge-vault';
import CenterPane from './CenterPane';
import LeftSidebar from './LeftSidebar';
import RightSidebar from './RightSidebar';
import SpaceLayout from './SpaceLayout';
import { SpaceProvider, useSpace } from './SpaceContext';
import RawCreateModal from './RawCreateModal';
import WikiCreateModal from './WikiCreateModal';
import type { View } from './SpaceContext';

function SpacePageContent({
  slug,
  rawModalOpen,
  setRawModalOpen,
  wikiModalOpen,
  setWikiModalOpen,
}: {
  slug: string;
  rawModalOpen: boolean;
  setRawModalOpen: (v: boolean) => void;
  wikiModalOpen: boolean;
  setWikiModalOpen: (v: boolean) => void;
}) {
  const { setSelectedVerbat, setView, refresh } = useSpace();

  const handleVerbatSelect = useCallback(
    (verbat: VerbatOut) => {
      setSelectedVerbat({
        id: verbat.id,
        source_file: verbat.source_file,
        extract_mode: verbat.extract_mode,
        deprecated: verbat.deprecated,
        content: '',
      } as any);
      setView('raw');
    },
    [setSelectedVerbat, setView],
  );

  return (
    <>
      <SpaceLayout
        left={
          <LeftSidebar
            onCreateDoc={() => setWikiModalOpen(true)}
            onCreateRaw={() => setRawModalOpen(true)}
            onVerbatSelect={handleVerbatSelect}
          />
        }
        center={<CenterPane />}
        right={<RightSidebar />}
      />
      <RawCreateModal
        slug={slug}
        open={rawModalOpen}
        onClose={() => setRawModalOpen(false)}
        onCreated={refresh}
      />
      <WikiCreateModal
        slug={slug}
        open={wikiModalOpen}
        onClose={() => setWikiModalOpen(false)}
        onCreated={refresh}
      />
    </>
  );
}

export default function SpacePage({ slug, initialView }: { slug: string; initialView: View }) {
  const [rawModalOpen, setRawModalOpen] = useState(false);
  const [wikiModalOpen, setWikiModalOpen] = useState(false);

  return (
    <SpaceProvider slug={slug} initialView={initialView}>
      <SpacePageContent
        slug={slug}
        rawModalOpen={rawModalOpen}
        setRawModalOpen={setRawModalOpen}
        wikiModalOpen={wikiModalOpen}
        setWikiModalOpen={setWikiModalOpen}
      />
    </SpaceProvider>
  );
}
