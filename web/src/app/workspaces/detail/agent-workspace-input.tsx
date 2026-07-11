'use client';

import { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { Button, Input, Popover, Select } from 'antd';
import { SendOutlined, ReloadOutlined, PaperClipOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { apiInterceptors, getModelList, postChatModeParamsFileLoad } from '@/client/api';
import { transformFileUrl } from '@/utils';
import type { IModelData } from '@/types/model';
import type { AgentWorkspaceInputHandle, PlaybookCommand } from './agent-workspace-types';

/** 选了剧本时必须输入任务目标;没选剧本按原逻辑(有文本或有资源即可)。 */
export function canSendSceneTask(
  text: string,
  hasResources: boolean,
  playbookCommand: PlaybookCommand | null,
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
      if (!playbookCommand) {
        setShowPlaybook(v.endsWith('/') && (playbooks?.length ?? 0) > 0);
      }
    };

    const pickPlaybook = (pb: { playbook_id: number; playbook_name: string }) => {
      setPlaybookCommand({ playbook_id: pb.playbook_id, playbook_name: pb.playbook_name });
      setShowPlaybook(false);
      // 清掉触发用的 "/"(用户在开头打的那个),话题由用户随后输入。
      setText((t) => t.replace(/^\/\s*/, ''));
      textareaRef.current?.focus();
    };

    // `/` at end of text pops the playbook list; the text before `/` is the
    // task topic (sent as `text`), not a playbook-name filter. Show all
    // playbooks while the picker is open.
    const visiblePlaybooks = (playbooks ?? []);

    const playbookPopover = (
      <div className="ws-agent-input__playbook-list">
        {visiblePlaybooks.map(pb => (
          <div key={pb.playbook_id} className="ws-agent-input__playbook-item" onClick={() => pickPlaybook(pb)} role="button">
            {pb.playbook_name}
          </div>
        ))}
      </div>
    );

    return (
      <div className="ws-agent-input" onDrop={handleDrop} onDragOver={(e) => e.preventDefault()}>
        {uploading.map(u => (
          <div key={u.id} className="ws-agent-input__uploading">{u.file.name} {u.status === 'error' ? '失败' : '上传中'}</div>
        ))}
        {resources.map((r, i) => (
          <div key={i} className="ws-agent-input__resource">
            <span>{r.image_url?.file_name || r.file_url?.file_name || r.audio_url?.file_name || r.video_url?.file_name}</span>
            <Button size="small" type="text" onClick={() => setResources(prev => prev.filter((_, j) => j !== i))}>×</Button>
          </div>
        ))}
        <Popover open={showPlaybook} content={playbookPopover} placement="topLeft">
          <Input.TextArea
            ref={textareaRef}
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder="输入指令给 Agent…(输入 / 选择剧本)"
            autoSize={{ minRows: 1, maxRows: 6 }}
            disabled={disabled || loading}
          />
        </Popover>
        <div className="ws-agent-input__actions">
          <Select
            size="small"
            style={{ minWidth: 140 }}
            value={selectedModel}
            onChange={setSelectedModel}
            disabled={disabled || loading}
            options={modelList.map(m => ({ label: m.model_name, value: m.model_name }))}
            placeholder="模型选择"
          />
          <Button icon={<PaperClipOutlined />} disabled={!convUid || disabled} onClick={() => fileInputRef.current?.click()} />
          <input ref={fileInputRef} type="file" multiple style={{ display: 'none' }} onChange={(e) => { for (const f of Array.from(e.target.files || [])) handleFileUpload(f); e.target.value = ''; }} />
          {lastInput && onRetry && !loading && <Button icon={<ReloadOutlined />} onClick={onRetry} disabled={disabled} title="重试" />}
          {playbookCommand && !text.trim() && (
            <span className="text-xs text-amber-600 mr-2">选了剧本要写任务目标 — 剧本只指定资源/能力,目标由你定。</span>
          )}
          <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading} disabled={!canSend || disabled || loading} />
        </div>
      </div>
    );
  },
);