'use client';

import { apiInterceptors } from '@/client/api';
import { createSpace, deleteSpace, listSpaces } from '@/client/api/knowledge-vault';
import type { SpaceInfo } from '@/types/knowledge-vault';
import {
  DeleteOutlined,
  PlusOutlined,
  RightOutlined,
  SettingOutlined,
  ReloadOutlined,
  SearchOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { Button, Input, Modal, Popconfirm, Select, Spin, message } from 'antd';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import VaultSeal from '@/components/knowledge-vault/VaultSeal';
import '../mcp/index.css';

export default function KnowledgeVaultHomePage() {
  const [spaces, setSpaces] = useState<SpaceInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [newSlug, setNewSlug] = useState('');
  const [newBackend, setNewBackend] = useState<'local' | 'distributed'>('local');
  const [query, setQuery] = useState('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');

  const loadSpaces = useCallback(async () => {
    setLoading(true);
    try {
      const [, data] = await apiInterceptors(listSpaces());
      setSpaces(data || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSpaces();
  }, [loadSpaces]);

  async function handleCreate() {
    const slug = newSlug.trim();
    if (!slug || /[^a-zA-Z0-9_-]/.test(slug)) {
      message.warning('slug 只允许字母、数字、下划线、短横线');
      return;
    }
    const [, res] = await apiInterceptors(createSpace({ slug, backend: newBackend }));
    if (res) {
      message.success(`已创建空间 ${slug}`);
      setModalOpen(false);
      setNewSlug('');
      setNewBackend('local');
      await loadSpaces();
    }
  }

  async function handleDelete(slug: string) {
    const [, res] = await apiInterceptors(deleteSpace(slug));
    if (res?.ok) {
      message.success(`已删除空间 ${slug}`);
      await loadSpaces();
    }
  }

  const filteredSpaces = useMemo(() => {
    if (!query.trim()) return spaces;
    const q = query.toLowerCase();
    return spaces.filter(
      (s) =>
        s.slug.toLowerCase().includes(q) ||
        (s.root && s.root.toLowerCase().includes(q)),
    );
  }, [query, spaces]);

  const stats = useMemo(() => {
    const total = spaces.length;
    const local = spaces.filter((s) => s.backend === 'local').length;
    const distributed = spaces.filter((s) => s.backend === 'distributed').length;
    return { total, local, distributed };
  }, [spaces]);

  return (
    <Spin spinning={loading}>
      <div className="mcp-page-root">
        <div className="mcp-page-bg" />

        <div className="mcp-page-content">
          {/* Header */}
          <div className="mcp-header">
            <div className="mcp-header-left">
              <div className="mcp-header-icon">
                <VaultSeal className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="mcp-title">知识库</h1>
                <p className="mcp-subtitle">
                  每个空间是一个独立的归档单元：上传原始文件，生成 wiki，构建图谱，统一检索。
                </p>
              </div>
            </div>
            <div className="mcp-header-actions">
              <Button
                className="mcp-btn-refresh"
                icon={<ReloadOutlined />}
                onClick={loadSpaces}
              />
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setModalOpen(true)}
                className="!rounded-md"
              >
                新建空间
              </Button>
            </div>
          </div>

          {/* Stats bar */}
          <div className="mcp-stats-bar">
            <div className="mcp-stats-group">
              <div className="mcp-stat">
                <span className="mcp-stat-value">{stats.total}</span>
                <span className="mcp-stat-label">总空间</span>
              </div>
              <div className="mcp-stat-divider" />
              <div className="mcp-stat">
                <span className="mcp-stat-value mcp-stat-online">{stats.local}</span>
                <span className="mcp-stat-label">Local</span>
              </div>
              <div className="mcp-stat-divider" />
              <div className="mcp-stat">
                <span className="mcp-stat-value mcp-stat-offline">{stats.distributed}</span>
                <span className="mcp-stat-label">Distributed</span>
              </div>
            </div>

            <div className="mcp-toolbar">
              <div className="mcp-search-wrapper">
                <SearchOutlined className="mcp-search-icon" />
                <input
                  className="mcp-search-input"
                  placeholder="搜索空间或路径..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <div className="mcp-view-toggle">
                <button
                  className={`mcp-view-btn ${viewMode === 'grid' ? 'active' : ''}`}
                  onClick={() => setViewMode('grid')}
                >
                  <AppstoreOutlined />
                </button>
                <button
                  className={`mcp-view-btn ${viewMode === 'list' ? 'active' : ''}`}
                  onClick={() => setViewMode('list')}
                >
                  <UnorderedListOutlined />
                </button>
              </div>
            </div>
          </div>

          {/* Cards */}
          {filteredSpaces.length ? (
            <div className={viewMode === 'grid' ? 'mcp-grid' : 'mcp-list-view'}>
              {filteredSpaces.map((s) => (
                <article
                  key={s.slug}
                  className={`mcp-card ${viewMode === 'list' ? 'mcp-card--list' : ''}`}
                >
                  <div className="mcp-card-header">
                    <div className="mcp-card-identity">
                      <div className="mcp-card-avatar">
                        <VaultSeal className="w-5 h-5 text-[var(--mcp-accent)]" />
                      </div>
                      <div className="mcp-card-meta">
                        <h3 className="mcp-card-name">{s.slug}</h3>
                        <div className="mcp-card-badges">
                          <span className="mcp-badge mcp-badge--type">
                            {s.backend || 'local'}
                          </span>
                          {(s.slug || '').startsWith('memory-') && (
                            <span className="mcp-badge mcp-badge--offline">记忆</span>
                          )}
                          {s.llm_model && (
                            <span className="mcp-badge mcp-badge--offline">{s.llm_model}</span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="mcp-card-actions">
                      <Link href={`/knowledge-vault/space/?slug=${s.slug}&view=settings`}>
                        <button
                          className="w-7 h-7 inline-flex items-center justify-center rounded text-[var(--mcp-text-tertiary)] hover:text-[var(--mcp-accent)] hover:bg-[var(--mcp-accent-light)] transition-colors"
                          title="设置"
                        >
                          <SettingOutlined className="text-xs" />
                        </button>
                      </Link>
                      <Popconfirm
                        title={`删除空间 ${s.slug}`}
                        description="删除后无法恢复，确认删除？"
                        onConfirm={() => handleDelete(s.slug)}
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                      >
                        <button
                          className="w-7 h-7 inline-flex items-center justify-center rounded text-[var(--mcp-text-tertiary)] hover:text-[var(--mcp-danger)] hover:bg-red-50 transition-colors"
                          title="删除"
                        >
                          <DeleteOutlined className="text-xs" />
                        </button>
                      </Popconfirm>
                    </div>
                  </div>

                  <p className="mcp-card-desc">
                    {s.root || '—'}
                    {s.embedder_model ? ` · ${s.embedder_model}` : ''}
                  </p>

                  <div className="mcp-card-footer">
                    <div className="mcp-card-footer-left">
                      <Link
                        href={`/knowledge-vault/space/?slug=${s.slug}&view=raw`}
                        className="inline-flex items-center gap-1 text-[13px] font-medium text-[var(--mcp-accent)] hover:gap-1.5 transition-all"
                      >
                        进入 <RightOutlined className="text-[10px]" />
                      </Link>
                    </div>
                    <span className="mcp-card-version">
                      {s.backend || 'local'}
                    </span>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            !loading && (
              <div className="mcp-empty">
                <div className="mcp-empty-icon">
                  <VaultSeal className="w-8 h-8 text-[var(--mcp-accent)]" />
                </div>
                <h3 className="mcp-empty-title">还没有知识空间</h3>
                <p className="mcp-empty-desc">创建第一个空间，开始归档你的资料。{query && '试试清空搜索条件。'}</p>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => setModalOpen(true)}
                  className="!mt-5 !rounded-md"
                >
                  新建空间
                </Button>
              </div>
            )
          )}
        </div>
      </div>

      <Modal
        title="新建知识空间"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleCreate}
        okText="创建"
        className="mcp-modal"
      >
        <div className="mcp-modal-section-title">slug · 英文短名</div>
        <Input
          value={newSlug}
          onChange={(e) => setNewSlug(e.target.value)}
          placeholder="my-research"
          onPressEnter={handleCreate}
          className="font-mono"
        />
        <div className="mcp-modal-section-title">backend</div>
        <Select
          value={newBackend}
          onChange={(v) => setNewBackend(v)}
          className="w-full"
          options={[
            { value: 'local', label: 'local (FS + SQLite + LanceDB)' },
            { value: 'distributed', label: 'distributed (S3 + SQL + pgvector/milvus/chroma/lance)' },
          ]}
        />
        <div className="text-xs text-[var(--mcp-text-tertiary)] mt-2">
          distributed 后端需要在配置文件中启用 [knowledge.distributed] enabled=true
        </div>
      </Modal>
    </Spin>
  );
}
