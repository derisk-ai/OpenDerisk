'use client';

import { useCallback, useState } from 'react';
import { apiInterceptors } from '@/client/api';
import { searchSpace } from '@/client/api/knowledge-vault';
import type { DocHit } from '@/types/knowledge-vault';
import { Empty, Input, Select, Spin, Tag } from 'antd';
import { useSpace } from './SpaceContext';

export default function SearchPanel() {
  const { slug, openDoc } = useSpace();
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<'documents' | 'semantic' | 'hybrid' | 'references'>('hybrid');
  const [hits, setHits] = useState<DocHit[]>([]);
  const [searching, setSearching] = useState(false);

  const runSearch = useCallback(async () => {
    const q = query.trim();
    if (!q) {
      setHits([]);
      return;
    }
    setSearching(true);
    try {
      const [, res] = await apiInterceptors(searchSpace(slug, { query: q, mode, limit: 20 }));
      setHits(res?.hits || []);
    } finally {
      setSearching(false);
    }
  }, [slug, query, mode]);

  return (
    <div className="flex flex-col h-full p-4">
      <div className="text-sm font-medium text-gray-700 mb-2">Deep Research</div>
      <Input.Search
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onSearch={runSearch}
        placeholder="搜索 wiki（语义/关键词）"
        loading={searching}
        enterButton
        size="small"
        className="mb-2"
      />
      <Select
        size="small"
        value={mode}
        onChange={(v) => setMode(v)}
        options={[
          { value: 'hybrid', label: 'hybrid (推荐)' },
          { value: 'semantic', label: 'semantic' },
          { value: 'documents', label: 'documents' },
          { value: 'references', label: 'references' },
        ]}
        className="mb-3"
      />
      <Spin spinning={searching} className="flex-1 overflow-auto">
        {hits.length === 0 ? (
          <Empty description="输入关键词开始搜索" imageStyle={{ height: 40 }} />
        ) : (
          <div className="flex flex-col gap-1">
            {hits.map((h) => (
              <button
                key={h.document_id}
                onClick={() => openDoc(h.path)}
                className="text-left px-2 py-1.5 rounded hover:bg-gray-50 border border-transparent hover:border-gray-200"
              >
                <div className="text-xs font-medium truncate">{h.title || h.path}</div>
                {h.snippet && <div className="text-xs text-gray-500 line-clamp-2">{h.snippet}</div>}
                <div className="text-[10px] text-gray-400">
                  {h.path} · score {h.score.toFixed(3)}
                </div>
              </button>
            ))}
          </div>
        )}
      </Spin>
    </div>
  );
}
