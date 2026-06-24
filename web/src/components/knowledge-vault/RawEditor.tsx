'use client';

import dynamic from 'next/dynamic';
import { apiInterceptors } from '@/client/api';
import {
  deleteRawFile,
  editRawFile,
  getVerbat,
  readRawFile,
  rebuildVerbatWiki,
} from '@/client/api/knowledge-vault';
import type { VerbatFull } from '@/types/knowledge-vault';
import { DeleteOutlined, EditOutlined, SaveOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Button, Empty, Spin, Tag, Tooltip, message } from 'antd';
import MarkdownIt from 'markdown-it';
import { useCallback, useEffect, useMemo, useState } from 'react';
import 'react-markdown-editor-lite/lib/index.css';
import { useSpace } from './SpaceContext';

const MdEditor = dynamic(() => import('react-markdown-editor-lite'), {
  ssr: false,
});

const mdParser = new MarkdownIt({ html: false, linkify: true, typographer: true });

export default function RawEditor() {
  const { slug, selectedRaw, setSelectedRaw, selectedVerbat, setSelectedVerbat, refresh } = useSpace();
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [verbat, setVerbat] = useState<VerbatFull | null>(selectedVerbat);
  const [rebuilding, setRebuilding] = useState(false);

  const displayPath = useMemo(() => {
    if (!selectedRaw) return '';
    return selectedRaw.replace(/^(raw|wiki)\//, '');
  }, [selectedRaw]);

  const apiPath = useMemo(() => {
    if (!selectedRaw) return '';
    return selectedRaw.replace(/^(raw|wiki)\//, '');
  }, [selectedRaw]);

  const loadVerbat = useCallback(
    async (id: string) => {
      const [, data] = await apiInterceptors(getVerbat(slug, id));
      if (data) {
        setVerbat(data);
        setSelectedVerbat(data);
      }
    },
    [slug, setSelectedVerbat],
  );

  useEffect(() => {
    if (!selectedRaw) {
      setContent('');
      return;
    }
    if (selectedRaw.endsWith('.md')) {
      setLoading(true);
      apiInterceptors(readRawFile(slug, apiPath))
        .then(([, data]) => {
          setContent(data?.content || '');
          setDirty(false);
        })
        .finally(() => setLoading(false));
    } else {
      setContent('');
    }
  }, [slug, selectedRaw, apiPath]);

  useEffect(() => {
    if (selectedVerbat?.id) {
      loadVerbat(selectedVerbat.id);
    } else {
      setVerbat(null);
    }
  }, [selectedVerbat, loadVerbat]);

  async function save() {
    if (!selectedRaw) return;
    setSaving(true);
    try {
      const [, res] = await apiInterceptors(
        editRawFile(slug, apiPath, { content }),
      );
      if (res) {
        message.success('已保存并触发 ingest');
        setDirty(false);
      }
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!selectedRaw) return;
    setDeleting(true);
    try {
      const [, res] = await apiInterceptors(deleteRawFile(slug, apiPath));
      if (res) {
        message.success('已删除');
        setSelectedRaw(null);
        refresh();
      }
    } finally {
      setDeleting(false);
    }
  }

  async function rebuildWiki() {
    if (!verbat?.id) return;
    setRebuilding(true);
    try {
      const [, , raw] = await apiInterceptors(rebuildVerbatWiki(slug, verbat.id));
      if (raw) {
        message.success('已触发 wiki 重建');
      }
    } finally {
      setRebuilding(false);
    }
  }

  if (!selectedRaw && !verbat) {
    return (
      <Empty description="在左侧选择一个 raw 文件或 verbat 查看" className="mt-12" />
    );
  }

  if (verbat && !selectedRaw) {
    return (
      <div className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[16px] font-medium text-gray-800">{verbat.source_file}</span>
          <Tag>{verbat.extract_mode}</Tag>
          {verbat.deprecated && <Tag color="red">deprecated</Tag>}
          <div className="flex-1" />
          <Button
            size="small"
            icon={<ThunderboltOutlined />}
            onClick={rebuildWiki}
            loading={rebuilding}
          >
            重建 wiki
          </Button>
        </div>
        <div className="text-[11px] text-gray-400 mb-2">
          id: <code>{verbat.id}</code>
        </div>
        <pre className="bg-gray-50 p-3 rounded text-xs overflow-auto max-h-[70vh] whitespace-pre-wrap break-words">
          {verbat.content}
        </pre>
      </div>
    );
  }

  return (
    <Spin spinning={loading} className="h-full">
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 bg-white">
          <EditOutlined className="text-violet-500" />
          <span className="text-sm font-medium text-gray-800 truncate" title={selectedRaw || undefined}>
            {displayPath}
          </span>
          {dirty && <Tag color="orange">未保存</Tag>}
          <div className="flex-1" />
          <Button danger size="small" icon={<DeleteOutlined />} onClick={remove} loading={deleting}>
            删除
          </Button>
          {selectedRaw?.endsWith('.md') && (
            <Button
              type="primary"
              size="small"
              icon={<SaveOutlined />}
              onClick={save}
              loading={saving}
              disabled={!dirty}
            >
              保存
            </Button>
          )}
        </div>
        {!selectedRaw?.endsWith('.md') ? (
          <Empty description="非 md 文件，暂不支持编辑" className="mt-12" />
        ) : (
          <>
            <div className="text-[11px] text-gray-400 px-4 py-2 bg-white">
              编辑 raw 原文件，保存后自动重新 ingest
            </div>
            <div className="flex-1 min-h-0 bg-white relative">
              {!loading && content === '' && (
                <div className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none">
                  <Empty description="文件内容为空" imageStyle={{ height: 40 }} />
                </div>
              )}
              <MdEditor
                value={content}
                style={{ height: '100%' }}
                renderHTML={(text) => mdParser.render(text)}
                onChange={({ text }) => {
                  setContent(text);
                  setDirty(true);
                }}
                view={{ menu: true, md: true, html: true }}
              />
            </div>
          </>
        )}
      </div>
    </Spin>
  );
}
