'use client';

import React, { useContext, useState, useEffect, useCallback } from 'react';
import { AppContext } from '@/contexts';
import {
  Button, Tabs, Empty, Tooltip, App, Modal, InputNumber, Switch, Collapse, Divider,
  Typography, Badge, Card, Space, Alert
} from 'antd';
import { 
  SettingOutlined, ThunderboltOutlined, ReloadOutlined, SaveOutlined,
  SyncOutlined, WarningOutlined, CheckCircleOutlined, InfoCircleOutlined,
  ControlOutlined, CompressOutlined, RetweetOutlined, SafetyOutlined
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { debounce } from 'lodash';
import {
  AgentRuntimeConfig,
  DEFAULT_AGENT_RUNTIME_CONFIG,
  DoomLoopConfig,
  AgentLoopConfig,
  WorkLogCompressionConfig,
} from '@/types/app';

const { Text, Title } = Typography;
const { Panel } = Collapse;

export default function TabRuntime() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const { message } = App.useApp();
  
  const [config, setConfig] = useState<AgentRuntimeConfig>(DEFAULT_AGENT_RUNTIME_CONFIG);
  const [hasChanges, setHasChanges] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeCollapse, setActiveCollapse] = useState<string[]>(['doom_loop', 'loop']);

  useEffect(() => {
    if (appInfo?.runtime_config) {
      setConfig({
        doom_loop: { ...DEFAULT_AGENT_RUNTIME_CONFIG.doom_loop, ...appInfo.runtime_config.doom_loop },
        loop: { ...DEFAULT_AGENT_RUNTIME_CONFIG.loop, ...appInfo.runtime_config.loop },
        work_log_compression: {
          ...DEFAULT_AGENT_RUNTIME_CONFIG.work_log_compression,
          ...appInfo.runtime_config.work_log_compression,
          truncation: { ...DEFAULT_AGENT_RUNTIME_CONFIG.work_log_compression.truncation, ...appInfo.runtime_config.work_log_compression?.truncation },
          pruning: { ...DEFAULT_AGENT_RUNTIME_CONFIG.work_log_compression.pruning, ...appInfo.runtime_config.work_log_compression?.pruning },
          compaction: { ...DEFAULT_AGENT_RUNTIME_CONFIG.work_log_compression.compaction, ...appInfo.runtime_config.work_log_compression?.compaction },
          layer4: { ...DEFAULT_AGENT_RUNTIME_CONFIG.work_log_compression.layer4, ...appInfo.runtime_config.work_log_compression?.layer4 },
          content_protection: { ...DEFAULT_AGENT_RUNTIME_CONFIG.work_log_compression.content_protection, ...appInfo.runtime_config.work_log_compression?.content_protection },
        },
      });
    }
  }, [appInfo?.runtime_config]);

  const updateConfig = useCallback(debounce((newConfig: AgentRuntimeConfig) => {
    setConfig(newConfig);
    setHasChanges(true);
  }, 300), []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetchUpdateApp({ ...appInfo, runtime_config: config });
      setHasChanges(false);
      message.success(t('runtime_save_success', '配置保存成功'));
    } catch (error) {
      message.error(t('runtime_save_failed', '配置保存失败'));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    Modal.confirm({
      title: t('runtime_reset_title', '重置配置'),
      content: t('runtime_reset_content', '确定要重置为默认配置吗？'),
      okText: t('confirm', '确认'),
      cancelText: t('cancel', '取消'),
      onOk: () => {
        setConfig(DEFAULT_AGENT_RUNTIME_CONFIG);
        setHasChanges(true);
      },
    });
  };

  const updateDoomLoop = (key: keyof DoomLoopConfig, value: boolean | number) => {
    updateConfig({
      ...config,
      doom_loop: { ...config.doom_loop, [key]: value },
    });
  };

  const updateLoop = (key: keyof AgentLoopConfig, value: boolean | number) => {
    updateConfig({
      ...config,
      loop: { ...config.loop, [key]: value },
    });
  };

  const updateWorkLogCompression = <K extends keyof WorkLogCompressionConfig>(
    key: K,
    value: WorkLogCompressionConfig[K]
  ) => {
    updateConfig({
      ...config,
      work_log_compression: { ...config.work_log_compression, [key]: value },
    });
  };

  const renderDoomLoopConfig = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between py-2 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <SafetyOutlined className="text-blue-500" />
          <span className="font-medium">{t('runtime_doom_loop_enabled', '启用检测')}</span>
        </div>
        <Switch
          checked={config.doom_loop.enabled}
          onChange={(v) => updateDoomLoop('enabled', v)}
        />
      </div>
      
      <div className="flex items-center justify-between py-2 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <span className="text-gray-600">{t('runtime_doom_loop_threshold', '触发阈值')}</span>
          <Tooltip title={t('runtime_doom_loop_threshold_tip', '连续相同调用次数达到此值时触发检测')}>
            <InfoCircleOutlined className="text-gray-400 text-sm" />
          </Tooltip>
        </div>
        <InputNumber
          min={2}
          max={10}
          value={config.doom_loop.threshold}
          onChange={(v) => updateDoomLoop('threshold', v ?? 3)}
          disabled={!config.doom_loop.enabled}
          className="w-24"
        />
      </div>

      <div className="flex items-center justify-between py-2 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <span className="text-gray-600">{t('runtime_doom_loop_max_history', '最大历史记录')}</span>
        </div>
        <InputNumber
          min={10}
          max={500}
          value={config.doom_loop.max_history_size}
          onChange={(v) => updateDoomLoop('max_history_size', v ?? 100)}
          disabled={!config.doom_loop.enabled}
          className="w-24"
        />
      </div>

      <div className="flex items-center justify-between py-2">
        <div className="flex items-center gap-2">
          <span className="text-gray-600">{t('runtime_doom_loop_expiry', '记录过期时间(秒)')}</span>
        </div>
        <InputNumber
          min={60}
          max={3600}
          value={config.doom_loop.expiry_seconds}
          onChange={(v) => updateDoomLoop('expiry_seconds', v ?? 300)}
          disabled={!config.doom_loop.enabled}
          className="w-24"
        />
      </div>
    </div>
  );

  const renderLoopConfig = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between py-2 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <RetweetOutlined className="text-purple-500" />
          <span className="font-medium">{t('runtime_loop_max_iterations', '最大迭代次数')}</span>
        </div>
        <InputNumber
          min={10}
          max={1000}
          value={config.loop.max_iterations}
          onChange={(v) => updateLoop('max_iterations', v ?? 300)}
          className="w-24"
        />
      </div>

      <div className="flex items-center justify-between py-2 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <span className="text-gray-600">{t('runtime_loop_enable_retry', '启用重试')}</span>
        </div>
        <Switch
          checked={config.loop.enable_retry}
          onChange={(v) => updateLoop('enable_retry', v)}
        />
      </div>

      <div className="flex items-center justify-between py-2 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <span className="text-gray-600">{t('runtime_loop_max_retries', '最大重试次数')}</span>
        </div>
        <InputNumber
          min={1}
          max={10}
          value={config.loop.max_retries}
          onChange={(v) => updateLoop('max_retries', v ?? 3)}
          disabled={!config.loop.enable_retry}
          className="w-24"
        />
      </div>

      <div className="flex items-center justify-between py-2">
        <div className="flex items-center gap-2">
          <span className="text-gray-600">{t('runtime_loop_timeout', '每轮超时(秒)')}</span>
        </div>
        <InputNumber
          min={30}
          max={600}
          value={config.loop.iteration_timeout}
          onChange={(v) => updateLoop('iteration_timeout', v ?? 300)}
          className="w-24"
        />
      </div>
    </div>
  );

  const renderCompressionConfig = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between py-2 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <CompressOutlined className="text-green-500" />
          <span className="font-medium">{t('runtime_compression_enabled', '启用压缩')}</span>
        </div>
        <Switch
          checked={config.work_log_compression.enabled}
          onChange={(v) => updateWorkLogCompression('enabled', v)}
        />
      </div>

      <Collapse
        activeKey={activeCollapse.includes('compression') ? ['1', '2', '3', '4'] : []}
        onChange={() => {
          if (activeCollapse.includes('compression')) {
            setActiveCollapse(activeCollapse.filter(k => k !== 'compression'));
          } else {
            setActiveCollapse([...activeCollapse, 'compression']);
          }
        }}
        ghost
        disabled={!config.work_log_compression.enabled}
      >
        <Panel 
          header={
            <div className="flex items-center gap-2">
              <Badge status="processing" />
              <span>{t('runtime_layer1_truncation', 'Layer 1: 截断配置')}</span>
            </div>
          } 
          key="1"
        >
          <div className="space-y-3 pl-4">
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 text-sm">{t('runtime_max_output_lines', '最大输出行数')}</span>
              <InputNumber
                min={100}
                max={10000}
                value={config.work_log_compression.truncation.max_output_lines}
                onChange={(v) => updateWorkLogCompression('truncation', { ...config.work_log_compression.truncation, max_output_lines: v ?? 2000 })}
                disabled={!config.work_log_compression.enabled}
                className="w-20"
                size="small"
              />
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 text-sm">{t('runtime_max_output_bytes', '最大输出字节(KB)')}</span>
              <InputNumber
                min={10}
                max={500}
                value={Math.round(config.work_log_compression.truncation.max_output_bytes / 1024)}
                onChange={(v) => updateWorkLogCompression('truncation', { ...config.work_log_compression.truncation, max_output_bytes: (v ?? 50) * 1024 })}
                disabled={!config.work_log_compression.enabled}
                className="w-20"
                size="small"
              />
            </div>
          </div>
        </Panel>

        <Panel 
          header={
            <div className="flex items-center gap-2">
              <Badge status="warning" />
              <span>{t('runtime_layer2_pruning', 'Layer 2: 剪枝配置')}</span>
            </div>
          } 
          key="2"
        >
          <div className="space-y-3 pl-4">
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 text-sm">{t('runtime_adaptive_pruning', '自适应剪枝')}</span>
              <Switch
                checked={config.work_log_compression.pruning.enable_adaptive_pruning}
                onChange={(v) => updateWorkLogCompression('pruning', { ...config.work_log_compression.pruning, enable_adaptive_pruning: v })}
                disabled={!config.work_log_compression.enabled}
                size="small"
              />
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 text-sm">{t('runtime_prune_protect_tokens', '保护Token数(K)')}</span>
              <InputNumber
                min={1}
                max={50}
                value={Math.round(config.work_log_compression.pruning.prune_protect_tokens / 1000)}
                onChange={(v) => updateWorkLogCompression('pruning', { ...config.work_log_compression.pruning, prune_protect_tokens: (v ?? 10) * 1000 })}
                disabled={!config.work_log_compression.enabled}
                className="w-20"
                size="small"
              />
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 text-sm">{t('runtime_min_messages_keep', '最少保留消息数')}</span>
              <InputNumber
                min={5}
                max={100}
                value={config.work_log_compression.pruning.min_messages_keep}
                onChange={(v) => updateWorkLogCompression('pruning', { ...config.work_log_compression.pruning, min_messages_keep: v ?? 20 })}
                disabled={!config.work_log_compression.enabled}
                className="w-20"
                size="small"
              />
            </div>
          </div>
        </Panel>

        <Panel 
          header={
            <div className="flex items-center gap-2">
              <Badge status="success" />
              <span>{t('runtime_layer3_compaction', 'Layer 3: 压缩配置')}</span>
            </div>
          } 
          key="3"
        >
          <div className="space-y-3 pl-4">
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 text-sm">{t('runtime_context_window', '上下文窗口(K tokens)')}</span>
              <InputNumber
                min={4}
                max={512}
                value={Math.round(config.work_log_compression.compaction.context_window / 1000)}
                onChange={(v) => updateWorkLogCompression('compaction', { ...config.work_log_compression.compaction, context_window: (v ?? 128) * 1000 })}
                disabled={!config.work_log_compression.enabled}
                className="w-20"
                size="small"
              />
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 text-sm">{t('runtime_compaction_threshold', '压缩阈值比例')}</span>
              <InputNumber
                min={0.5}
                max={0.95}
                step={0.05}
                value={config.work_log_compression.compaction.compaction_threshold_ratio}
                onChange={(v) => updateWorkLogCompression('compaction', { ...config.work_log_compression.compaction, compaction_threshold_ratio: v ?? 0.8 })}
                disabled={!config.work_log_compression.enabled}
                className="w-20"
                size="small"
              />
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 text-sm">{t('runtime_recent_messages_keep', '保留最近消息数')}</span>
              <InputNumber
                min={2}
                max={20}
                value={config.work_log_compression.compaction.recent_messages_keep}
                onChange={(v) => updateWorkLogCompression('compaction', { ...config.work_log_compression.compaction, recent_messages_keep: v ?? 5 })}
                disabled={!config.work_log_compression.enabled}
                className="w-20"
                size="small"
              />
            </div>
          </div>
        </Panel>

        <Panel 
          header={
            <div className="flex items-center gap-2">
              <Badge status="default" />
              <span>{t('runtime_layer4_history', 'Layer 4: 多轮历史配置')}</span>
            </div>
          } 
          key="4"
        >
          <div className="space-y-3 pl-4">
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 text-sm">{t('runtime_layer4_enabled', '启用Layer 4压缩')}</span>
              <Switch
                checked={config.work_log_compression.layer4.enable_layer4_compression}
                onChange={(v) => updateWorkLogCompression('layer4', { ...config.work_log_compression.layer4, enable_layer4_compression: v })}
                disabled={!config.work_log_compression.enabled}
                size="small"
              />
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 text-sm">{t('runtime_max_rounds_before_compression', '压缩前保留轮数')}</span>
              <InputNumber
                min={1}
                max={10}
                value={config.work_log_compression.layer4.max_rounds_before_compression}
                onChange={(v) => updateWorkLogCompression('layer4', { ...config.work_log_compression.layer4, max_rounds_before_compression: v ?? 3 })}
                disabled={!config.work_log_compression.enabled || !config.work_log_compression.layer4.enable_layer4_compression}
                className="w-20"
                size="small"
              />
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 text-sm">{t('runtime_max_total_rounds', '最大保留总轮数')}</span>
              <InputNumber
                min={5}
                max={50}
                value={config.work_log_compression.layer4.max_total_rounds}
                onChange={(v) => updateWorkLogCompression('layer4', { ...config.work_log_compression.layer4, max_total_rounds: v ?? 10 })}
                disabled={!config.work_log_compression.enabled || !config.work_log_compression.layer4.enable_layer4_compression}
                className="w-20"
                size="small"
              />
            </div>
          </div>
        </Panel>
      </Collapse>

      <Divider orientation="left" plain className="text-sm text-gray-500">
        {t('runtime_content_protection', '内容保护')}
      </Divider>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex items-center justify-between py-2">
          <span className="text-gray-600 text-sm">{t('runtime_code_protection', '代码块保护')}</span>
          <Switch
            checked={config.work_log_compression.content_protection.code_block_protection}
            onChange={(v) => updateWorkLogCompression('content_protection', { ...config.work_log_compression.content_protection, code_block_protection: v })}
            disabled={!config.work_log_compression.enabled}
            size="small"
          />
        </div>
        <div className="flex items-center justify-between py-2">
          <span className="text-gray-600 text-sm">{t('runtime_thinking_protection', '思维链保护')}</span>
          <Switch
            checked={config.work_log_compression.content_protection.thinking_chain_protection}
            onChange={(v) => updateWorkLogCompression('content_protection', { ...config.work_log_compression.content_protection, thinking_chain_protection: v })}
            disabled={!config.work_log_compression.enabled}
            size="small"
          />
        </div>
        <div className="flex items-center justify-between py-2">
          <span className="text-gray-600 text-sm">{t('runtime_filepath_protection', '文件路径保护')}</span>
          <Switch
            checked={config.work_log_compression.content_protection.file_path_protection}
            onChange={(v) => updateWorkLogCompression('content_protection', { ...config.work_log_compression.content_protection, file_path_protection: v })}
            disabled={!config.work_log_compression.enabled}
            size="small"
          />
        </div>
        <div className="flex items-center justify-between py-2">
          <span className="text-gray-600 text-sm">{t('runtime_max_protected_blocks', '最大保护块数')}</span>
          <InputNumber
            min={1}
            max={30}
            value={config.work_log_compression.content_protection.max_protected_blocks}
            onChange={(v) => updateWorkLogCompression('content_protection', { ...config.work_log_compression.content_protection, max_protected_blocks: v ?? 10 })}
            disabled={!config.work_log_compression.enabled}
            className="w-16"
            size="small"
          />
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full w-full bg-gradient-to-br from-gray-50/50 to-blue-50/20">
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200/60 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="flex items-center gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-indigo-600 shadow-lg shadow-purple-500/20">
            <ControlOutlined className="text-white text-lg" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900 tracking-tight">
              {t('runtime_config_title', '运行时配置')}
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {t('runtime_config_desc', '配置Agent执行过程中的参数和行为')}
            </p>
          </div>
          {hasChanges && (
            <Tag color="orange" className="ml-2">
              <WarningOutlined className="mr-1" />
              {t('runtime_unsaved', '未保存')}
            </Tag>
          )}
        </div>
        <div className="flex items-center gap-3">
          <Tooltip title={t('runtime_reset_default', '重置为默认')}>
            <Button 
              icon={<ReloadOutlined />} 
              onClick={handleReset}
              className="hover:bg-gray-100 transition-colors"
            />
          </Tooltip>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            disabled={!hasChanges}
            onClick={handleSave}
            className="bg-gradient-to-r from-green-500 to-emerald-600 border-0 shadow-lg shadow-green-500/25"
          >
            {t('save', '保存')}
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto space-y-4">
          <Alert
            message={t('runtime_config_note', '配置说明')}
            description={t('runtime_config_note_desc', '这些配置将在Agent运行时生效，影响执行循环、上下文压缩和错误恢复行为。修改后请保存。')}
            type="info"
            showIcon
            className="mb-4"
          />

          <Card 
            title={
              <div className="flex items-center gap-2">
                <SafetyOutlined className="text-blue-500" />
                <span>{t('runtime_doom_loop_section', 'Doom Loop 检测')}</span>
                <Badge 
                  status={config.doom_loop.enabled ? 'success' : 'default'} 
                  text={config.doom_loop.enabled ? t('enabled', '已启用') : t('disabled', '已禁用')}
                />
              </div>
            }
            className="shadow-sm"
          >
            {renderDoomLoopConfig()}
          </Card>

          <Card 
            title={
              <div className="flex items-center gap-2">
                <RetweetOutlined className="text-purple-500" />
                <span>{t('runtime_loop_section', '执行循环配置')}</span>
              </div>
            }
            className="shadow-sm"
          >
            {renderLoopConfig()}
          </Card>

          <Card 
            title={
              <div className="flex items-center gap-2">
                <CompressOutlined className="text-green-500" />
                <span>{t('runtime_compression_section', 'Work Log 压缩')}</span>
                <Badge 
                  status={config.work_log_compression.enabled ? 'success' : 'default'} 
                  text={config.work_log_compression.enabled ? t('enabled', '已启用') : t('disabled', '已禁用')}
                />
              </div>
            }
            className="shadow-sm"
          >
            {renderCompressionConfig()}
          </Card>
        </div>
      </div>
    </div>
  );
}

import { Tag } from 'antd';