'use client';

import { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { Input, Popover, Spin } from 'antd';
import { ArrowUpOutlined, CloseOutlined, DownOutlined, FileOutlined, LoadingOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import classNames from 'classnames';
import { useRequest } from 'ahooks';
import { apiInterceptors, getModelList, postChatModeParamsFileLoad } from '@/client/api';
import ModelIcon from '@/components/icons/model-icon';
import { transformFileUrl } from '@/utils';
import type { IModelData } from '@/types/model';
import type { AgentWorkspaceInputHandle, PlaybookCommand } from './agent-workspace-types';

/** 选了剧本时必须输入任务目标;没选剧本按原逻辑(有文本或有资源即可)。 */
export function canSendSceneTask(
  text: string,
  hasResources: boolean,
  playbookCommand: { playbook_id: number; playbook_name: string } | null,
): boolean {
  const trimmed = text.trim();
  if (playbookCommand) return trimmed.length > 0;
  return trimmed.length > 0 || hasResources;
}

interface ResourceItem {
  type: string;
  image_url?: { url: string; preview_url?: string; file_name?: string };
  file_url?: { url: string; preview_url?: string; file_name?: string };
  audio_url?: { url: string; preview_url?: string; file_name?: string };
  video_url?: { url: string; preview_url?: string; file_name?: string };
}

interface UploadingFile { id: string; file: File; status: 'uploading' | 'success' | 'error'; error?: string }

interface AgentWorkspaceInputProps {
  convUid?: string;
  onSend: (payload: { text: string; resources?: ResourceItem[]; model?: string; playbookCommand?: PlaybookCommand }) => void;
  loading?: boolean;
  disabled?: boolean;
  lastInput?: { text: string } | null;
  onRetry?: () => void;
  playbooks?: { playbook_id: number; playbook_name: string }[];
}

export const AgentWorkspaceInput = forwardRef<AgentWorkspaceInputHandle, AgentWorkspaceInputProps>(
  function AgentWorkspaceInput({ convUid, onSend, loading, disabled, lastInput, onRetry, playbooks }, ref) {
    const [text, setText] = useState('');
    const [resources, setResources] = useState<ResourceItem[]>([]);
    const [uploading, setUploading] = useState<UploadingFile[]>([]);
    const [modelList, setModelList] = useState<IModelData[]>([]);
    const [selectedModel, setSelectedModel] = useState<string>('');
    const [showPlaybook, setShowPlaybook] = useState(false);
    const [playbookCommand, setPlaybookCommand] = useState<PlaybookCommand | null>(null);
    const [isFocus, setIsFocus] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useImperativeHandle(ref, () => ({ focus: () => textareaRef.current?.focus() }));

    useRequest(async () => {
      const [, data] = await apiInterceptors(getModelList());
      return data || [];
    }, {
      onSuccess: (models: IModelData[]) => {
        const llm = models.filter(m => m.worker_type === 'llm');
        setModelList(llm);
        if (llm.length) setSelectedModel(llm[0].model_name);
      },
    });

    const normalizeUploadRes = (res: any): { fileUrl: string; previewUrl: string } => {
      let previewUrl = '', fileUrl = '';
      if (res?.preview_url) { previewUrl = res.preview_url; fileUrl = res.file_path || previewUrl; }
      else if (res?.file_path) { fileUrl = res.file_path; previewUrl = transformFileUrl(fileUrl); }
      else if (res?.url || res?.file_url) { fileUrl = res.url || res.file_url; previewUrl = fileUrl; }
      else if (res?.path) { fileUrl = res.path; previewUrl = transformFileUrl(fileUrl); }
      else if (typeof res === 'string') { fileUrl = res; previewUrl = res; }
      else if (Array.isArray(res)) { const f = res[0]; previewUrl = f?.preview_url || ''; fileUrl = f?.file_path || f?.preview_url || previewUrl; if (!previewUrl && fileUrl) previewUrl = transformFileUrl(fileUrl); }
      return { fileUrl, previewUrl };
    };

    const buildResourceItem = (file: File, fileUrl: string, previewUrl: string): ResourceItem => {
      const common = { url: fileUrl, preview_url: previewUrl || fileUrl, file_name: file.name };
      if (file.type.startsWith('image/')) return { type: 'image_url', image_url: common };
      if (file.type.startsWith('audio/')) return { type: 'audio_url', audio_url: common };
      if (file.type.startsWith('video/')) return { type: 'video_url', video_url: common };
      return { type: 'file_url', file_url: common };
    };

    // File-type accent theme (mirrors home UnifiedChatInput chip theming).
    const getFileTheme = (name: string) => {
      const lower = name.toLowerCase();
      if (/\.(png|jpe?g|gif|bmp|webp)$/.test(lower)) return { bg: 'bg-purple-50 dark:bg-purple-900/30', border: 'border-purple-200 dark:border-purple-700', icon: 'text-purple-500' };
      if (/\.pdf$/.test(lower)) return { bg: 'bg-red-50 dark:bg-red-900/30', border: 'border-red-200 dark:border-red-700', icon: 'text-red-500' };
      if (/\.(doc|docx)$/.test(lower)) return { bg: 'bg-blue-50 dark:bg-blue-900/30', border: 'border-blue-200 dark:border-blue-700', icon: 'text-blue-500' };
      if (/\.(xlsx?|csv)$/.test(lower)) return { bg: 'bg-green-50 dark:bg-green-900/30', border: 'border-green-200 dark:border-green-700', icon: 'text-green-500' };
      if (/\.(ppt|pptx)$/.test(lower)) return { bg: 'bg-orange-50 dark:bg-orange-900/30', border: 'border-orange-200 dark:border-orange-700', icon: 'text-orange-500' };
      if (/\.(mp4|mov|avi|mkv)$/.test(lower)) return { bg: 'bg-pink-50 dark:bg-pink-900/30', border: 'border-pink-200 dark:border-pink-700', icon: 'text-pink-500' };
      if (/\.(mp3|wav|ogg|aac)$/.test(lower)) return { bg: 'bg-yellow-50 dark:bg-yellow-900/30', border: 'border-yellow-200 dark:border-yellow-700', icon: 'text-yellow-500' };
      return { bg: 'bg-gray-50 dark:bg-gray-800', border: 'border-gray-200 dark:border-gray-700', icon: 'text-gray-400' };
    };

    const resourceName = (r: ResourceItem) =>
      r.image_url?.file_name || r.file_url?.file_name || r.audio_url?.file_name || r.video_url?.file_name || '';
    const resourcePreview = (r: ResourceItem) =>
      r.image_url?.preview_url || r.file_url?.preview_url || r.audio_url?.preview_url || r.video_url?.preview_url || '';
    const isImageResource = (r: ResourceItem) => !!r.image_url;

    const hasContent = text.trim().length > 0 || resources.length > 0 || playbookCommand !== null;
    const popoverOverlay = '[&_.ant-popover-inner]:!p-0 [&_.ant-popover-inner]:!rounded-xl [&_.ant-popover-inner]:!shadow-xl';

    const handleFileUpload = async (file: File) => {
      if (!convUid) return;
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
      setUploading(prev => [...prev, { id, file, status: 'uploading' }]);
      const formData = new FormData();
      formData.append('doc_files', file);
      const [err, res] = await apiInterceptors(
        postChatModeParamsFileLoad({ convUid, chatMode: 'chat_normal', data: formData, model: selectedModel, config: { timeout: 1000 * 60 * 60 } }),
      );
      setUploading(prev => prev.filter(u => u.id !== id));
      if (err) {
        setUploading(prev => [...prev, { id, file, status: 'error', error: String(err) }]);
        return;
      }
      const { fileUrl, previewUrl } = normalizeUploadRes(res);
      setResources(prev => [...prev, buildResourceItem(file, fileUrl, previewUrl)]);
    };

    const handleDrop = async (e: React.DragEvent) => {
      e.preventDefault();
      for (const f of Array.from(e.dataTransfer.files)) await handleFileUpload(f);
    };

    const canSend = canSendSceneTask(text, resources.length > 0, playbookCommand);

    const handleSend = () => {
      if (!canSend) return;
      const trimmed = text.trim();
      onSend({
        text: trimmed,
        resources: resources.length ? resources : undefined,
        model: selectedModel || undefined,
        playbookCommand: playbookCommand ?? undefined,
      });
      setText('');
      setResources([]);
      setPlaybookCommand(null);
      setShowPlaybook(false);
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
    };

    const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const v = e.target.value;
      setText(v);
      // 只有输入框"最开始"的 / 才有命令效果：文本中间的 / 不触发。
      // 已选了剧本 chip 后不再触发（单选，要换剧本先移除 chip）。
      const isSlashCommand = v.startsWith('/') && !playbookCommand;
      setShowPlaybook(isSlashCommand && (playbooks?.length ?? 0) > 0);
    };

    const pickPlaybook = (pb: { playbook_id: number; playbook_name: string }) => {
      setPlaybookCommand({ playbook_id: pb.playbook_id, playbook_name: pb.playbook_name });
      // 清掉触发用的 "/"（用户在开头打的那个），话题由用户随后输入。
      setText(text.replace(/^\/\s*/, ''));
      setShowPlaybook(false);
      textareaRef.current?.focus();
    };

    // `/` at the very start of text pops the playbook list; the text the user
    // types after picking a chip is the task topic (sent as `text`). Show all
    // playbooks while the picker is open (no name filter).
    const visiblePlaybooks = (playbooks ?? []);

    const playbookPopover = (
      <div className="w-72 max-h-72 overflow-y-auto py-1">
        {visiblePlaybooks.length === 0 && (
          <div className="px-3 py-2 text-xs text-gray-400">暂无剧本</div>
        )}
        {visiblePlaybooks.map(pb => (
          <div
            key={pb.playbook_id}
            className="flex items-center gap-2 px-3 py-2 cursor-pointer rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors group"
            onClick={() => pickPlaybook(pb)}
            role="button"
          >
            <PlusOutlined className="text-xs text-gray-400 group-hover:text-indigo-500" />
            <span className="text-sm text-gray-700 dark:text-gray-300 group-hover:text-indigo-600">{pb.playbook_name}</span>
          </div>
        ))}
      </div>
    );

    return (
      <div className="w-full relative">
        <div
          className={classNames(
            'w-full bg-white dark:bg-[#232734] rounded-2xl shadow-sm border transition-all duration-300',
            isFocus
              ? 'border-indigo-500/50 shadow-lg ring-4 ring-indigo-500/5'
              : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
          )}
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
        >
          {/* SECTION 1 — attached file chips (only when files present) */}
          {(uploading.length > 0 || resources.length > 0) && (
            <div className="px-4 pt-3 pb-2">
              {(uploading.length + resources.length) > 1 && (
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    已上传文件 ({uploading.length + resources.length})
                  </span>
                  <button
                    className="text-xs text-gray-500 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 px-2 py-0.5 rounded transition-colors"
                    onClick={() => { setResources([]); setUploading([]); }}
                  >
                    全部清除
                  </button>
                </div>
              )}
              <div className="flex flex-wrap gap-3">
                {/* uploading cards */}
                {uploading.map(u => {
                  const theme = getFileTheme(u.file.name);
                  const isImg = u.file.type.startsWith('image/');
                  return (
                    <div key={u.id} className="relative">
                      <div className={`w-[60px] h-[60px] rounded-lg border-2 overflow-hidden bg-white dark:bg-gray-800 shadow-sm ${u.status === 'error' ? 'border-red-300' : theme.border}`}>
                        {isImg
                          ? <img src={URL.createObjectURL(u.file)} className="w-full h-full object-cover" />
                          : <div className={`w-full h-full flex items-center justify-center ${theme.bg}`}>
                              <FileOutlined className={`${theme.icon} text-xl`} />
                            </div>}
                        {u.status === 'uploading' && (
                          <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                            <LoadingOutlined className="text-white text-lg" spin />
                          </div>
                        )}
                        {u.status === 'error' && (
                          <div className="absolute inset-0 bg-red-500/80 flex flex-col items-center justify-center gap-0.5">
                            <CloseOutlined className="text-white text-xs" />
                            <span className="text-white text-[10px]">失败</span>
                          </div>
                        )}
                      </div>
                      <div className="mt-1 max-w-[60px]">
                        <p className={`text-xs truncate ${u.status === 'error' ? 'text-red-500' : 'text-gray-600 dark:text-gray-400'}`}>{u.file.name}</p>
                      </div>
                    </div>
                  );
                })}
                {/* uploaded chips */}
                {resources.map((r, i) => {
                  const name = resourceName(r);
                  const theme = getFileTheme(name);
                  const preview = resourcePreview(r);
                  const isImg = isImageResource(r);
                  return (
                    <div key={`${name}-${i}`} className="relative group">
                      <div className={`w-[60px] h-[60px] rounded-lg border-2 overflow-hidden bg-white dark:bg-gray-800 shadow-sm hover:shadow-md transition-all duration-200 ${theme.border}`}>
                        {isImg && preview
                          ? <img src={preview} className="w-full h-full object-cover" />
                          : <div className={`w-full h-full flex items-center justify-center ${theme.bg}`}>
                              <FileOutlined className={`${theme.icon} text-xl`} />
                            </div>}
                      </div>
                      <div className="mt-1 max-w-[60px]">
                        <p className="text-xs text-gray-600 dark:text-gray-400 truncate">{name}</p>
                      </div>
                      <button
                        className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-200 shadow hover:bg-red-50 hover:border-red-300 hover:text-red-500"
                        onClick={() => setResources(prev => prev.filter((_, j) => j !== i))}
                      >
                        <CloseOutlined className="text-[10px]" />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* SECTION 1.5 — selected playbook command chip (single, removable) */}
          {playbookCommand && (
            <div className="px-4 pt-3 pb-1 flex items-center gap-2 flex-wrap">
              <span className="inline-flex items-center gap-1 bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-200 dark:border-indigo-700 text-indigo-600 dark:text-indigo-300 rounded-md px-2 py-1 text-sm">
                <span className="text-xs text-indigo-400">/</span>
                <span className="font-medium">{playbookCommand.playbook_name}</span>
                <button
                  className="ml-0.5 text-indigo-400 hover:text-red-500 transition-colors"
                  onClick={() => setPlaybookCommand(null)}
                  title="移除剧本"
                >
                  <CloseOutlined className="text-[11px]" />
                </button>
              </span>
            </div>
          )}

          {/* SECTION 2 — textarea (borderless, card is the only border) */}
          <Popover
            open={showPlaybook}
            content={playbookPopover}
            placement="topLeft"
            trigger={[]}
            overlayClassName={popoverOverlay}
          >
            <div className="p-4">
              <Input.TextArea
                ref={textareaRef}
                value={text}
                onChange={handleChange}
                onFocus={() => setIsFocus(true)}
                onBlur={() => setIsFocus(false)}
                onKeyDown={handleKeyDown}
                placeholder="输入指令给 Agent…(输入 / 选择剧本)"
                className="!text-base !bg-transparent !border-0 !resize-none placeholder:!text-gray-400 !text-gray-800 dark:!text-gray-200 !shadow-none !p-0 !min-h-[60px]"
                autoSize={{ minRows: 2, maxRows: 8 }}
                disabled={disabled || loading}
              />
            </div>
          </Popover>

          {/* SECTION 3 — footer toolbar: left tools / right send */}
          <div className="flex items-center justify-between gap-2 px-3 pb-3 min-w-0">
            <div className="flex items-center gap-2 min-w-0 flex-shrink overflow-visible">
              {/* + file attach button */}
              <button
                className="h-8 w-8 rounded-full flex items-center justify-center border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:text-indigo-500 hover:border-indigo-300 dark:hover:border-indigo-600 transition-all hover:bg-indigo-50 dark:hover:bg-indigo-900/20 flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
                onClick={() => fileInputRef.current?.click()}
                disabled={!convUid || disabled || loading}
                title="上传文件"
              >
                <PlusOutlined className="text-sm" />
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                style={{ display: 'none' }}
                onChange={(e) => { for (const f of Array.from(e.target.files || [])) handleFileUpload(f); e.target.value = ''; }}
              />

              {/* retry (only when retryable) */}
              {lastInput && onRetry && !loading && (
                <button
                  className="h-8 w-8 rounded-full flex items-center justify-center border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:text-indigo-500 hover:border-indigo-300 transition-all hover:bg-indigo-50 dark:hover:bg-indigo-900/20 flex-shrink-0 disabled:opacity-40"
                  onClick={onRetry}
                  disabled={disabled}
                  title="重试"
                >
                  <ReloadOutlined className="text-sm" />
                </button>
              )}

              {/* model selector pill */}
              <Popover
                content={(
                  <div className="w-56 max-h-60 overflow-y-auto py-1">
                    {modelList.length === 0 && <div className="px-3 py-2 text-xs text-gray-400">暂无可用模型</div>}
                    {modelList.map(m => (
                      <div
                        key={m.model_name}
                        className={classNames(
                          'flex items-center gap-2 px-3 py-2 cursor-pointer rounded-lg transition-colors group',
                          selectedModel === m.model_name
                            ? 'bg-indigo-50 dark:bg-indigo-900/20'
                            : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                        )}
                        onClick={() => setSelectedModel(m.model_name)}
                      >
                        <ModelIcon model={m.model_name} width={16} height={16} />
                        <span className={classNames(
                          'text-sm truncate',
                          selectedModel === m.model_name ? 'text-indigo-600' : 'text-gray-700 dark:text-gray-300 group-hover:text-indigo-600'
                        )}>{m.model_name}</span>
                      </div>
                    ))}
                  </div>
                )}
                trigger="click"
                overlayClassName={popoverOverlay}
              >
                <div className="flex items-center gap-1.5 bg-gray-50 dark:bg-gray-800 px-2 py-1 rounded-full border border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 transition-all group flex-shrink-0">
                  <ModelIcon model={selectedModel} width={14} height={14} />
                  <span className="text-xs text-gray-700 dark:text-gray-300 max-w-[80px] truncate group-hover:text-indigo-500 transition-colors">
                    {selectedModel || '选择模型'}
                  </span>
                  <DownOutlined className="text-[10px] text-gray-400 group-hover:text-indigo-500 transition-colors" />
                </div>
              </Popover>
            </div>

            <div className="flex items-center gap-1.5 flex-shrink-0">
              {playbookCommand && !text.trim() && (
                <div className="text-[11px] text-amber-600 px-1 pb-1">
                  选了剧本要写本次任务目标 — 剧本只指定资源/能力,目标由你定。
                </div>
              )}
              <button
                className={classNames(
                  'w-9 h-9 flex items-center justify-center transition-all !border-0 flex-shrink-0 rounded-full',
                  hasContent
                    ? 'bg-gradient-to-r from-indigo-500 to-indigo-600 hover:from-indigo-600 hover:to-indigo-700 shadow-md hover:shadow-lg text-white'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                )}
                onClick={handleSend}
                disabled={!hasContent || disabled || loading || !canSend}
                title="发送"
              >
                {loading
                  ? <Spin indicator={<LoadingOutlined className="text-white text-base" spin />} />
                  : <ArrowUpOutlined className="text-base" />}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  },
);