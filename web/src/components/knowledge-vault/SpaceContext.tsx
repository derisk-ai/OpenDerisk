'use client';

import type { VerbatFull } from '@/types/knowledge-vault';
import { createContext, useCallback, useContext, useMemo, useState } from 'react';

export type View = 'raw' | 'wiki' | 'graph' | 'schema' | 'lint' | 'settings';
export type LeftTab = 'knowledge' | 'files';

interface SpaceContextValue {
  slug: string;
  view: View;
  setView: (view: View) => void;
  leftTab: LeftTab;
  setLeftTab: (tab: LeftTab) => void;
  selectedRaw: string | null;
  setSelectedRaw: (path: string | null) => void;
  selectedDoc: string | null;
  setSelectedDoc: (path: string | null) => void;
  selectedVerbat: VerbatFull | null;
  setSelectedVerbat: (v: VerbatFull | null) => void;
  refreshKey: number;
  refresh: () => void;
  openDoc: (path: string) => void;
  openRawFile: (path: string) => void;
}

const SpaceContext = createContext<SpaceContextValue | null>(null);

export function useSpace() {
  const ctx = useContext(SpaceContext);
  if (!ctx) {
    throw new Error('useSpace must be used within a SpaceProvider');
  }
  return ctx;
}

export function SpaceProvider({
  slug,
  initialView = 'raw',
  children,
}: {
  slug: string;
  initialView?: View;
  children: React.ReactNode;
}) {
  const [view, setViewState] = useState<View>(initialView);
  const [leftTab, setLeftTab] = useState<LeftTab>('knowledge');
  const [selectedRaw, setSelectedRaw] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [selectedVerbat, setSelectedVerbat] = useState<VerbatFull | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  const setView = useCallback(
    (v: View) => {
      setViewState(v);
      try {
        const url = new URL(window.location.href);
        url.searchParams.set('view', v);
        window.history.replaceState({}, '', url.toString());
      } catch {
        // ignore
      }
    },
    [setViewState],
  );

  const openDoc = useCallback(
    (path: string) => {
      setSelectedDoc(path);
      setView('wiki');
    },
    [setView],
  );

  const openRawFile = useCallback(
    (path: string) => {
      setSelectedRaw(path);
      setSelectedVerbat(null);
      setView('raw');
    },
    [setView],
  );

  const value = useMemo(
    () => ({
      slug,
      view,
      setView,
      leftTab,
      setLeftTab,
      selectedRaw,
      setSelectedRaw,
      selectedDoc,
      setSelectedDoc,
      selectedVerbat,
      setSelectedVerbat,
      refreshKey,
      refresh,
      openDoc,
      openRawFile,
    }),
    [
      slug,
      view,
      setView,
      leftTab,
      selectedRaw,
      selectedDoc,
      selectedVerbat,
      refreshKey,
      refresh,
      openDoc,
      openRawFile,
    ],
  );

  return <SpaceContext.Provider value={value}>{children}</SpaceContext.Provider>;
}

export default SpaceContext;
