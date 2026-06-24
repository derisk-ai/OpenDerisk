'use client';

import { lazy, Suspense, useCallback } from 'react';
import { useSpace } from './SpaceContext';

const RawEditor = lazy(() => import('./RawEditor'));
const WikiEditor = lazy(() => import('./WikiEditor'));
const GraphCanvas = lazy(() => import('./GraphCanvas'));
const SchemaEditor = lazy(() => import('./SchemaEditor'));
const LintView = lazy(() => import('./LintView'));
const SpaceSettings = lazy(() => import('./SpaceSettings'));

export default function CenterPane() {
  const { view, slug, openDoc } = useSpace();

  const components: Record<typeof view, React.ReactNode> = {
    raw: <RawEditor />,
    wiki: <WikiEditor />,
    graph: <GraphCanvas />,
    schema: <SchemaEditor slug={slug} />,
    lint: <LintView slug={slug} onOpenDoc={openDoc} />,
    settings: <SpaceSettings slug={slug} />,
  };

  return (
    <div className="h-full overflow-hidden bg-white flex flex-col">
      <Suspense fallback={<div className="p-4">Loading...</div>}>{components[view]}</Suspense>
    </div>
  );
}
