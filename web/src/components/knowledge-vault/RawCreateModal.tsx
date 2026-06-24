'use client';

import { apiInterceptors } from '@/client/api';
import { createRawFile } from '@/client/api/knowledge-vault';
import { Input, Modal, message } from 'antd';
import { useState } from 'react';

export default function RawCreateModal({
  slug,
  open,
  onClose,
  onCreated,
}: {
  slug: string;
  open: boolean;
  onClose: () => void;
  onCreated?: () => void;
}) {
  const [path, setPath] = useState('');
  const [content, setContent] = useState('# \n\n');
  const [loading, setLoading] = useState(false);

  async function submit() {
    const p = path.trim();
    if (!p) {
      message.warning('请填写路径');
      return;
    }
    if (!p.endsWith('.md')) {
      message.warning('仅支持 .md 文件');
      return;
    }
    const normalized =
      p.startsWith('sources/') || p.startsWith('convos/') || p.startsWith('clips/')
        ? p
        : `sources/${p}`;
    setLoading(true);
    try {
      const [, res] = await apiInterceptors(
        createRawFile(slug, { path: normalized, content }),
      );
      if (res) {
        message.success('已创建并触发 ingest');
        onClose();
        setPath('');
        setContent('# \n\n');
        onCreated?.();
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      title="新建 Raw md 文件"
      open={open}
      onCancel={onClose}
      onOk={submit}
      okText="创建"
      width={800}
      confirmLoading={loading}
    >
      <div className="mb-2">
        <label className="text-xs text-gray-500">路径 (相对 raw/, 如 sources/notes.md)</label>
        <Input value={path} onChange={(e) => setPath(e.target.value)} placeholder="sources/notes.md" />
      </div>
      <div className="text-xs text-gray-500 mb-1">内容</div>
      <Input.TextArea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={14}
        className="font-mono"
      />
    </Modal>
  );
}
