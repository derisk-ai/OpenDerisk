'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import SpacePage from '@/components/knowledge-vault/SpacePage';
import type { View } from '@/components/knowledge-vault/SpaceContext';

const VALID_VIEWS: View[] = ['raw', 'wiki', 'graph', 'schema', 'lint', 'settings'];

export default function KnowledgeVaultSpaceRoutePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const slug = searchParams.get('slug') || '';
  const viewParam = searchParams.get('view');
  const initialView: View =
    viewParam && VALID_VIEWS.includes(viewParam as View)
      ? (viewParam as View)
      : 'raw';

  useEffect(() => {
    if (!slug) {
      router.replace('/knowledge-vault');
    }
  }, [slug, router]);

  if (!slug) {
    return null;
  }

  return <SpacePage slug={slug} initialView={initialView} />;
}
