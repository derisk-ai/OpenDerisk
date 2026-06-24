'use client';

import { useEffect, useState } from 'react';
import { Alert, Button, Input, Spin, Typography, message } from 'antd';
import { apiInterceptors } from '@/client/api';
import { readSchemaMd, writeSchemaMd } from '@/client/api/knowledge-vault';

const { Title, Paragraph } = Typography;

export default function SchemaEditor({ slug }: { slug: string }) {
  const [content, setContent] = useState('');
  const [original, setOriginal] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [, data] = await apiInterceptors(readSchemaMd(slug));
      const md = data?.schema_md || '';
      setContent(md);
      setOriginal(md);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [slug]);

  async function save() {
    setSaving(true);
    try {
      const [, res] = await apiInterceptors(writeSchemaMd(slug, content));
      if (res !== null) {
        message.success('schema.md 已保存');
        setOriginal(content);
      }
    } finally {
      setSaving(false);
    }
  }

  const dirty = content !== original;

  return (
    <Spin spinning={loading}>
      <div className="max-w-4xl">
        <Title level={4}>schema.md</Title>
        <Paragraph type="secondary" className="!text-sm">
          空间配置文件：Page Types (type→dir 路由) / Relation Types (predicate 验证) /
          Ingest Workflow / Lint Rules。保存后立即影响后续 doc_create / edge_add。
        </Paragraph>
        <Alert
          type="info"
          showIcon
          className="mb-3"
          message="修改 schema.md 不会自动迁移已有文档。删除 type/predicate 只影响新建，不影响已有数据。"
        />
        <Input.TextArea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={24}
          className="font-mono text-xs"
          spellCheck={false}
        />
        <div className="mt-3 flex items-center gap-3">
          <Button type="primary" loading={saving} onClick={save} disabled={!dirty}>
            保存
          </Button>
          {dirty && <span className="text-orange-500 text-sm">未保存</span>}
          <Button onClick={load} disabled={!dirty} className="ml-auto">
            撤销
          </Button>
        </div>
      </div>
    </Spin>
  );
}
