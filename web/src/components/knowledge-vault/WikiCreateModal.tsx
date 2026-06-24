'use client';

import { apiInterceptors } from '@/client/api';
import { createDoc } from '@/client/api/knowledge-vault';
import { Input, Modal, message } from 'antd';
import { useState } from 'react';

const DEFAULT_NEW_BODY = `---\ntype: concept\ntitle: \ncreated: 2026-06-23\nupdated: 2026-06-23\n---

#

`;

export default function WikiCreateModal({
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
  const [body, setBody] = useState(DEFAULT_NEW_BODY);
  const [loading, setLoading] = useState(false);

  async function submit() {
    if (!path.trim()) {
      message.warning('请填写路径');
      return;
    }
    setLoading(true);
    try {
      const [, res] = await apiInterceptors(createDoc(slug, path.trim(), body));
      if (res !== null) {
        message.success('已创建');
        onClose();
        setPath('');
        setBody(DEFAULT_NEW_BODY);
        onCreated?.();
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      title="新建 Wiki 文档"
      open={open}
      onCancel={onClose}
      onOk={submit}
      okText="创建"
      width={800}
      confirmLoading={loading}
    >
      <div className="mb-2">
        <label className="text-xs text-gray-500">路径 (相对 wiki/, 如 concepts/attention.md)</label>
        <Input value={path} onChange={(e) => setPath(e.target.value)} placeholder="concepts/attention.md" />
      </div>
      <div className="text-xs text-gray-500 mb-1">内容 (含 frontmatter)</div>
      <Input.TextArea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={14}
        className="font-mono"
      />
    </Modal>
  );
}
