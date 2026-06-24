'use client';

import { apiInterceptors } from '@/client/api';
import { getDerisksList, getModelList } from '@/client/api';
import { getSpace, patchSpace, setEmbedderIdentity } from '@/client/api/knowledge-vault';
import type { SpaceInfo } from '@/types/knowledge-vault';
import { Button, Form, InputNumber, Modal, Select, Spin, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  slug: string;
  onSaved?: (updated: SpaceInfo) => void;
}

interface ModelOption {
  value: string;
  label: string;
}

interface AgentOption {
  value: string;
  label: string;
}

export default function SpaceSettings({ slug, onSaved }: Props) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [space, setSpace] = useState<SpaceInfo | null>(null);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resetModalOpen, setResetModalOpen] = useState(false);
  const [resetModel, setResetModel] = useState<string>('');
  const [resetDim, setResetDim] = useState<number>(1024);

  async function loadOptions() {
    setLoading(true);
    try {
      const [, modelList] = await apiInterceptors(getModelList());
      if (modelList) {
        setModels(
          modelList.map((m: any) => ({
            value: m.model_name || m.name || m.model,
            label: m.model_name || m.name || m.model,
          })),
        );
      }
      const [, agentList] = await apiInterceptors(getDerisksList());
      if (agentList && Array.isArray(agentList)) {
        const items = (agentList as any).data || (agentList as any) || [];
        setAgents(
          items.map((a: any) => ({
            value: a.app_code || a.id || a.name,
            label: a.app_name || a.name || a.app_code,
          })),
        );
      }
    } finally {
      setLoading(false);
    }
  }

  const loadSpace = useCallback(async () => {
    const [, s] = await apiInterceptors(getSpace(slug));
    if (s) setSpace(s);
  }, [slug]);

  useEffect(() => {
    loadOptions();
    loadSpace();
  }, [loadSpace]);

  useEffect(() => {
    if (!space) return;
    form.setFieldsValue({
      default_agent_id: space.default_agent_id || undefined,
      llm_model: space.llm_model || undefined,
      multimodal_model: space.multimodal_model || undefined,
      embedder_model: space.embedder_model || undefined,
    });
  }, [space, form]);

  async function handleSave() {
    if (!space) return;
    try {
      const values = await form.validateFields();
      setSaving(true);
      const [, updated, raw] = await apiInterceptors(
        patchSpace(space.slug, {
          default_agent_id: values.default_agent_id || null,
          llm_model: values.llm_model || null,
          multimodal_model: values.multimodal_model || null,
          embedder_model: values.embedder_model || null,
        }),
      );
      if (raw) {
        message.success('保存成功');
        onSaved?.(updated as SpaceInfo);
        loadSpace();
      }
    } catch (e: any) {
      message.error(`保存失败: ${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleForceResetEmbedder() {
    if (!space) return;
    try {
      const [, , raw] = await apiInterceptors(
        setEmbedderIdentity(space.slug, {
          model_name: resetModel,
          dimension: resetDim,
          force_swap: true,
        }),
      );
      if (raw) {
        message.success('已强制重置 embedder identity（向量库已清空）');
        setResetModalOpen(false);
      }
    } catch (e: any) {
      message.error(`重置失败: ${e?.message || e}`);
    }
  }

  if (!space) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spin />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar">
      <Spin spinning={loading}>
        <div className="max-w-2xl">
          <h2 className="text-lg font-medium mb-1">{t('knowledge_space_settings' as any) || '空间设置'}</h2>
          <p className="text-xs text-gray-400 mb-6">
            {t('knowledge_space_settings_desc' as any) ||
              '配置本空间的默认 Agent、LLM 模型、多模态模型与向量模型。上传文件时会按此处的配置触发 wiki 生成。'}
          </p>

          <Form form={form} layout="vertical">
            <Form.Item
              name="default_agent_id"
              label={t('knowledge_default_agent' as any) || '默认 Agent'}
              tooltip={t('knowledge_default_agent_desc' as any) || '上传文件后用于生成 wiki 的默认 Agent'}
            >
              <Select
                allowClear
                showSearch
                placeholder={t('knowledge_select_agent' as any) || '选择 Agent'}
                options={agents}
                optionFilterProp="label"
              />
            </Form.Item>

            <Form.Item
              name="llm_model"
              label={t('knowledge_llm_model' as any) || 'LLM 模型'}
              tooltip={t('knowledge_llm_model_desc' as any) || '生成 wiki 文档使用的文本 LLM'}
            >
              <Select
                allowClear
                showSearch
                placeholder={t('knowledge_select_llm' as any) || '选择 LLM 模型'}
                options={models}
                optionFilterProp="label"
              />
            </Form.Item>

            <Form.Item
              name="multimodal_model"
              label={t('knowledge_multimodal_model' as any) || '多模态模型'}
              tooltip={t('knowledge_multimodal_model_desc' as any) || '处理图片/音频时使用的多模态模型'}
            >
              <Select
                allowClear
                showSearch
                placeholder={t('knowledge_select_multimodal' as any) || '选择多模态模型'}
                options={models}
                optionFilterProp="label"
              />
            </Form.Item>

            <Form.Item
              name="embedder_model"
              label={t('knowledge_embedder_model' as any) || '向量模型'}
              tooltip={t('knowledge_embedder_model_desc' as any) || '用于对 verbatim/doc 做 embedding 的模型，和 LLM 共用同一套 provider 配置'}
            >
              <Select
                allowClear
                showSearch
                placeholder={t('knowledge_select_embedder' as any) || '选择向量模型'}
                options={models}
                optionFilterProp="label"
              />
            </Form.Item>

            <div className="flex justify-between items-center mt-2">
              <Button onClick={() => setResetModalOpen(true)} danger type="default">
                {t('knowledge_force_reset_embedder' as any) || '强制重置 Embedder'}
              </Button>
              <Button type="primary" loading={saving} onClick={handleSave}>
                {t('common_save' as any) || '保存'}
              </Button>
            </div>
          </Form>
        </div>
      </Spin>

      <Modal
        title={t('knowledge_force_reset_embedder' as any) || '强制重置 Embedder'}
        open={resetModalOpen}
        onCancel={() => setResetModalOpen(false)}
        onOk={handleForceResetEmbedder}
        okText={t('common_confirm' as any) || '确认重置'}
        okButtonProps={{ danger: true }}
        cancelText={t('common_cancel' as any) || '取消'}
      >
        <div className="text-sm text-gray-600 mb-4">
          {t('knowledge_reset_embedder_warning' as any) ||
            '此操作会清空当前空间的向量库并锁定新的 embedder identity。仅当模型维度变化或想切换 embedder 时使用。'}
        </div>
        <div className="space-y-3">
          <div>
            <div className="text-xs text-gray-500 mb-1">模型名</div>
            <Select
              showSearch
              className="w-full"
              placeholder="选择向量模型"
              value={resetModel || undefined}
              onChange={setResetModel}
              options={models}
              optionFilterProp="label"
            />
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">维度</div>
            <InputNumber
              className="w-full"
              min={1}
              max={8192}
              value={resetDim}
              onChange={(v) => setResetDim(v || 1024)}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
