'use client';

import { apiInterceptors } from '@/client/api';
import { createSpace, listSpaces } from '@/client/api/knowledge-vault';
import type { SpaceInfo } from '@/types/knowledge-vault';
import { PlusOutlined, SettingOutlined } from '@ant-design/icons';
import { Button, Card, Empty, Input, Modal, Select, Spin, Typography, message } from 'antd';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

const { Title, Paragraph } = Typography;

export default function KnowledgeVaultHomePage() {
  const [spaces, setSpaces] = useState<SpaceInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [newSlug, setNewSlug] = useState('');
  const [newBackend, setNewBackend] = useState<'local' | 'distributed'>('local');

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

  return (
    <div className="p-6 h-full overflow-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Title level={3} className="!mb-1">
            Knowledge Vault
          </Title>
          <Paragraph className="!text-gray-500">管理你的知识空间</Paragraph>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          新建空间
        </Button>
      </div>

      <Spin spinning={loading}>
        {spaces.length === 0 ? (
          <Empty description="还没有空间，点击右上角新建" className="mt-12" />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {spaces.map((s) => (
              <Card
                key={s.slug}
                title={
                  <Link
                    href={`/knowledge-vault/space/?slug=${s.slug}&view=raw`}
                    className="text-violet-600 hover:text-violet-700"
                  >
                    {s.slug}
                  </Link>
                }
                extra={<span className="text-xs text-gray-400">{s.backend}</span>}
                className="hover:shadow-md transition-shadow"
              >
                <div className="text-sm text-gray-500 space-y-1">
                  <div className="truncate">{s.root || 'local'}</div>
                  {s.llm_model && <div>LLM: {s.llm_model}</div>}
                  {s.embedder_model && <div>Embedder: {s.embedder_model}</div>}
                </div>
                <div className="mt-4 flex gap-2">
                  <Link href={`/knowledge-vault/space/?slug=${s.slug}&view=raw`} passHref>
                    <Button type="primary" size="small">
                      进入
                    </Button>
                  </Link>
                  <Link href={`/knowledge-vault/space/?slug=${s.slug}&view=settings`} passHref>
                    <Button size="small" icon={<SettingOutlined />}>
                      设置
                    </Button>
                  </Link>
                </div>
              </Card>
            ))}
          </div>
        )}
      </Spin>

      <Modal
        title="新建知识空间"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleCreate}
        okText="创建"
      >
        <div className="text-sm text-gray-500 mb-2">slug (英文短名, 如 my-research)</div>
        <Input
          value={newSlug}
          onChange={(e) => setNewSlug(e.target.value)}
          placeholder="my-research"
          onPressEnter={handleCreate}
        />
        <div className="text-sm text-gray-500 mb-2 mt-4">后端 (backend)</div>
        <Select
          value={newBackend}
          onChange={(v) => setNewBackend(v)}
          className="w-full"
          options={[
            { value: 'local', label: 'local (FS + SQLite + LanceDB)' },
            { value: 'distributed', label: 'distributed (S3 + SQL + pgvector/milvus/chroma/lance)' },
          ]}
        />
        <div className="text-xs text-gray-400 mt-1">
          distributed 后端需要在配置文件中启用 [knowledge.distributed] enabled=true
        </div>
      </Modal>
    </div>
  );
}
