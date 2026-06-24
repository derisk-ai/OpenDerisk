'use client';

import dynamic from 'next/dynamic';
import { apiInterceptors } from '@/client/api';
import { editDoc, getVerbat, readDoc, rebuildVerbatWiki } from '@/client/api/knowledge-vault';
import type { DocRead, VerbatFull } from '@/types/knowledge-vault';
import { FileTextOutlined, SaveOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Button, Drawer, Empty, Spin, Tag, Tooltip, Typography, message } from 'antd';
import MarkdownIt from 'markdown-it';
import { useCallback, useEffect, useState } from 'react';
import 'react-markdown-editor-lite/lib/index.css';
import { useSpace } from './SpaceContext';

const MdEditor = dynamic(() => import('react-markdown-editor-lite'), {
  ssr: false,
});

const { Title } = Typography;
const mdParser = new MarkdownIt({ html: false, linkify: true, typographer: true });

export default function WikiEditor() {
  const { slug, selectedDoc, refresh } = useSpace();
  const [doc, setDoc] = useState<DocRead | null>(null);
  const [draft, setDraft] = useState('');
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [verbat, setVerbat] = useState<VerbatFull | null>(null);
  const [verbatOpen, setVerbatOpen] = useState(false);
  const [verbatLoading, setVerbatLoading] = useState(false);

  const load = useCallback(async () => {
    if (!selectedDoc) return;
    setLoading(true);
    try {
      const [, data] = await apiInterceptors(readDoc(slug, selectedDoc));
      if (data) {
        setDoc(data);
        const fm = data.frontmatter || {};
        const fmLines = Object.entries(fm).map(([k, v]) => {
          const value =
            Array.isArray(v) || (typeof v === 'object' && v !== null)
              ? JSON.stringify(v)
              : String(v);
          return `${k}: ${value}`;
        });
        setDraft(`---\n${fmLines.join('\n')}\n---\n\n${data.content}`);
        setDirty(false);
      }
    } finally {
      setLoading(false);
    }
  }, [slug, selectedDoc]);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    if (!selectedDoc) return;
    setSaving(true);
    try {
      const [, res] = await apiInterceptors(editDoc(slug, selectedDoc, draft));
      if (res !== null) {
        message.success('已保存');
        setDirty(false);
        load();
        refresh();
      }
    } finally {
      setSaving(false);
    }
  }

  const sourceVerbatId = doc?.frontmatter
    ? Object.entries(doc.frontmatter).find(([k]) => k.toLowerCase() === 'source_verbat')?.[1] as
        | string
        | undefined
    : undefined;

  async function openSourceVerbat() {
    if (!sourceVerbatId) return;
    setVerbatLoading(true);
    setVerbatOpen(true);
    try {
      const [, data] = await apiInterceptors(getVerbat(slug, sourceVerbatId));
      setVerbat(data || null);
    } finally {
      setVerbatLoading(false);
    }
  }

  async function regenerateWiki() {
    if (!sourceVerbatId) {
      message.warning('当前文档未关联 source_verbat，无法重建');
      return;
    }
    setRegenerating(true);
    try {
      const [, , raw] = await apiInterceptors(rebuildVerbatWiki(slug, sourceVerbatId));
      if (raw) {
        message.success('已触发 wiki 重建');
      }
    } finally {
      setRegenerating(false);
    }
  }

  if (!selectedDoc) {
    return <Empty description="选择左侧文档查看 / 编辑" className="mt-12" />;
  }

  return (
    <Spin spinning={loading} className="h-full">
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 bg-white">
          <FileTextOutlined className="text-violet-500" />
          <Title level={5} className="!mb-0 text-sm truncate" title={selectedDoc}>
            {doc?.title || selectedDoc}
          </Title>
          {doc?.type && <Tag color="blue">{doc.type}</Tag>}
          {dirty && <Tag color="orange">未保存</Tag>}
          <span className="flex-1" />
          {sourceVerbatId && (
            <Tooltip title={`查看源 verbatim: ${sourceVerbatId}`}>
              <Button size="small" onClick={openSourceVerbat} loading={verbatLoading}>
                查看原文
              </Button>
            </Tooltip>
          )}
          <Button
            size="small"
            icon={<ThunderboltOutlined />}
            onClick={regenerateWiki}
            loading={regenerating}
            disabled={!sourceVerbatId}
          >
            AI 重新生成
          </Button>
          <Button type="primary" icon={<SaveOutlined />} onClick={save} disabled={!dirty}>
            保存
          </Button>
        </div>
        <div className="text-xs text-gray-400 px-4 py-2 bg-white truncate" title={selectedDoc}>
          {selectedDoc}
        </div>
        <div className="flex-1 min-h-0 bg-white relative">
          {!loading && draft === '' && (
            <div className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none">
              <Empty description="文档内容为空" imageStyle={{ height: 40 }} />
            </div>
          )}
          <MdEditor
            value={draft}
            style={{ height: '100%' }}
            renderHTML={(text) => mdParser.render(text)}
            onChange={({ text }) => {
              setDraft(text);
              setDirty(true);
            }}
            view={{ menu: true, md: true, html: true }}
          />
        </div>
      </div>
      <Drawer
        title="源 Verbatim"
        open={verbatOpen}
        onClose={() => setVerbatOpen(false)}
        width={520}
      >
        {verbat ? (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="font-medium truncate">{verbat.source_file}</span>
              <Tag>{verbat.extract_mode}</Tag>
            </div>
            <pre className="bg-gray-50 p-3 rounded text-xs overflow-auto max-h-[70vh] whitespace-pre-wrap break-words">
              {verbat.content}
            </pre>
          </div>
        ) : (
          <Empty description="未找到 verbatim" />
        )}
      </Drawer>
    </Spin>
  );
}
