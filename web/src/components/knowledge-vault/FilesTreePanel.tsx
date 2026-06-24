'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiInterceptors } from '@/client/api';
import {
  getRawTree,
  listIngestJobs,
  listVerbats,
  uploadFile,
} from '@/client/api/knowledge-vault';
import type { IngestJob, TreeNode, VerbatOut } from '@/types/knowledge-vault';
import {
  FileAddOutlined,
  InboxOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Button, Empty, List, Spin, Tag, Tooltip, Upload, message as antMessage, message } from 'antd';
import TreeView from './TreeView';
import { useSpace } from './SpaceContext';

const { Dragger } = Upload;

const STATUS_LABEL: Record<string, string> = {
  pending: '排队中',
  extracting: '抽取中',
  embedding: '向量化',
  generating_wiki: '生成 wiki',
  done: '完成',
  failed: '失败',
};

const STATUS_COLOR: Record<string, string> = {
  pending: 'default',
  extracting: 'processing',
  embedding: 'processing',
  generating_wiki: 'processing',
  done: 'success',
  failed: 'error',
};

export default function FilesTreePanel({
  onCreate,
  onVerbatSelect,
}: {
  onCreate: () => void;
  onVerbatSelect: (verbat: VerbatOut) => void;
}) {
  const { slug, selectedRaw, openRawFile, refreshKey, refresh } = useSpace();
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [verbats, setVerbats] = useState<VerbatOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<IngestJob[]>([]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [, t] = await apiInterceptors(getRawTree(slug));
      const [, v] = await apiInterceptors(listVerbats(slug, 200, 0));
      setTree(t || []);
      setVerbats(v?.items || []);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  const pollJobs = useCallback(async () => {
    const [, data] = await apiInterceptors(listIngestJobs(slug, 30));
    setJobs(data?.items || []);
    const hasPending = (data?.items || []).some(
      (j) => j.status !== 'done' && j.status !== 'failed',
    );
    if (hasPending) {
      setTimeout(pollJobs, 2000);
    }
  }, [slug]);

  useEffect(() => {
    loadAll();
    pollJobs();
  }, [loadAll, pollJobs, refreshKey]);

  async function handleUpload(file: File) {
    const hide = antMessage.loading(`上传中: ${file.name}`, 0);
    try {
      const [, , raw] = await apiInterceptors(uploadFile({ slug, file }));
      if (raw) {
        hide();
        message.success(`${file.name} 已上传，wiki 生成中…`);
        pollJobs();
        refresh();
      } else {
        hide();
      }
    } catch (e: any) {
      hide();
      message.error(`上传失败: ${e?.message || e}`);
    }
    return false;
  }

  return (
    <Spin spinning={loading} className="h-full">
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-100 bg-white">
          <span className="font-medium text-gray-800">Raw Files</span>
          <div className="flex items-center gap-1">
            <Tooltip title="刷新">
              <button
                onClick={loadAll}
                className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-gray-100 text-gray-400"
              >
                <ReloadOutlined className={`text-xs ${loading ? 'animate-spin' : ''}`} />
              </button>
            </Tooltip>
            <Tooltip title="新建 md 原文件">
              <Button size="small" type="primary" icon={<FileAddOutlined />} onClick={onCreate} />
            </Tooltip>
          </div>
        </div>
        <div className="p-3 flex flex-col gap-2 overflow-hidden flex-1 bg-white">
          <Dragger
            multiple
            showUploadList={false}
            beforeUpload={(file) => {
              handleUpload(file);
              return false;
            }}
            className="!bg-violet-50/30 !border-violet-200 !rounded-lg !py-2"
          >
            <p className="ant-upload-drag-icon !mb-0.5">
              <InboxOutlined className="text-violet-400 text-xl" />
            </p>
            <p className="ant-upload-text text-xs text-gray-600">拖拽或点击上传</p>
            <p className="ant-upload-hint text-[10px] text-gray-400">pdf / docx / pptx / txt / md / 图片 / 音频</p>
          </Dragger>

          {jobs.some((j) => j.status !== 'done' && j.status !== 'failed') && (
            <div className="text-xs text-violet-700 bg-violet-50 px-2 py-1 rounded">
              {jobs.filter((j) => j.status !== 'done' && j.status !== 'failed').length} 个 ingest 任务进行中
            </div>
          )}

          <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
            <div className="text-[12px] font-medium text-gray-700 mb-1">Raw 文件树</div>
            {tree.length ? (
              <TreeView
                nodes={tree}
                onSelect={openRawFile}
                selectedKey={selectedRaw || undefined}
                height="auto"
                className="flex-1 min-h-0"
              />
            ) : (
              <Empty description="raw/ 为空" imageStyle={{ height: 40 }} />
            )}
          </div>

          <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
            <div className="text-[12px] font-medium text-gray-700 mb-1">Verbat 列表 ({verbats.length})</div>
            <div className="flex-1 min-h-0 overflow-auto custom-scrollbar">
              <List
                size="small"
                dataSource={verbats}
                renderItem={(v) => (
                  <List.Item
                    className="cursor-pointer hover:bg-gray-50 !px-2"
                    onClick={() => onVerbatSelect(v)}
                  >
                    <div className="w-full">
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium truncate flex-1 text-[12px]">{v.source_file}</span>
                        <Tag color={STATUS_COLOR[v.extract_mode]} className="!text-[10px] !px-1 !py-0 !m-0">
                          {v.extract_mode}
                        </Tag>
                        {v.deprecated && (
                          <Tag color="red" className="!text-[10px] !px-1 !py-0 !m-0">
                            dep
                          </Tag>
                        )}
                      </div>
                      <div className="text-[10px] text-gray-400 truncate mt-0.5">{v.content_preview}</div>
                    </div>
                  </List.Item>
                )}
              />
            </div>
          </div>
        </div>
      </div>
    </Spin>
  );
}
