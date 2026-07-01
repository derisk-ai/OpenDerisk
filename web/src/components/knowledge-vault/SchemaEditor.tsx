'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Spin, Typography, message } from 'antd';
import { apiInterceptors } from '@/client/api';
import { readSchemaMd, writeSchemaMd } from '@/client/api/knowledge-vault';

const { Title, Paragraph } = Typography;

export default function SchemaEditor({ slug }: { slug: string }) {
  const [content, setContent] = useState('');
  const [original, setOriginal] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [, data] = await apiInterceptors(readSchemaMd(slug));
      const md = data?.schema_md || '';
      setContent(md);
      setOriginal(md);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    load();
  }, [load]);

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

  function cancel() {
    setContent(original);
  }

  const dirty = content !== original;

  return (
    <Spin spinning={loading} wrapperClassName="h-full">
      <div className="flex flex-col h-full max-w-full">
        <div className="flex-shrink-0 px-4 py-3 border-b border-gray-100 bg-white">
          <Title level={4} className="!mb-1">schema.md</Title>
          <Paragraph type="secondary" className="!text-sm !mb-0">
            空间配置文件：Page Types (type→dir 路由) / Relation Types (predicate 验证) /
            Ingest Workflow / Lint Rules。保存后立即影响后续 doc_create / edge_add。
          </Paragraph>
        </div>
        <div className="flex-shrink-0 px-4 pt-3">
          <Alert
            type="info"
            showIcon
            className="mb-3"
            message="修改 schema.md 不会自动迁移已有文档。删除 type/predicate 只影响新建，不影响已有数据。"
          />
        </div>
        <div className="flex-1 min-h-0 px-4 pb-3">
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full h-full resize-none rounded-lg border border-gray-200 p-3 font-mono text-xs leading-relaxed focus:border-[#0C75FC] focus:ring-1 focus:ring-[#0C75FC] focus:outline-none"
            spellCheck={false}
          />
        </div>
        <div className="flex-shrink-0 px-4 py-3 border-t border-gray-100 bg-white flex items-center gap-3">
          <Button type="primary" loading={saving} onClick={save} disabled={!dirty}>
            保存
          </Button>
          <Button onClick={cancel} disabled={!dirty}>
            撤销
          </Button>
          {dirty && <span className="text-orange-500 text-sm">未保存</span>}
        </div>
      </div>
    </Spin>
  );
}
