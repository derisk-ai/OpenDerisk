'use client';

import React, { useContext, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  App,
  AutoComplete,
  Badge,
  Button,
  Card,
  Collapse,
  Empty,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  ApiOutlined,
  CodeOutlined,
  DeleteOutlined,
  FunctionOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SaveOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { AppContext } from '@/contexts';
import { apiInterceptors } from '@/client/api';
import { getAgentList, getHookFunctions } from '@/client/api/app';
import {
  BlockingPolicy,
  DEFAULT_TEAM_HOOK_CONFIG,
  HookConfigItem,
  HookEndpointConfig,
  HookKind,
  HookTriggerType,
  TeamHookConfig,
} from '@/types/app';

const { Text } = Typography;
const { Panel } = Collapse;

const TRIGGER_OPTIONS: { value: HookTriggerType; label: string; description: string }[] = [
  { value: 'pre_tool_use', label: 'pre_tool_use', description: '工具执行前（可阻断/改写参数）' },
  { value: 'post_tool_use', label: 'post_tool_use', description: '工具执行后（异步）' },
  { value: 'conversation_start', label: 'conversation_start', description: '对话开始' },
  { value: 'conversation_complete', label: 'conversation_complete', description: '对话完成' },
  { value: 'turn_complete', label: 'turn_complete', description: '每轮对话结束（记忆写入/反思）' },
  { value: 'state_change', label: 'state_change', description: '会话状态变化' },
  { value: 'user_prompt_submit', label: 'user_prompt_submit', description: '用户提交输入' },
  { value: 'error_occurred', label: 'error_occurred', description: '出现错误' },
];

const KIND_OPTIONS: { value: HookKind; label: string; icon: React.ReactNode }[] = [
  { value: 'api', label: 'API (HTTP POST)', icon: <ApiOutlined /> },
  { value: 'cli', label: 'CLI (沙箱内执行)', icon: <CodeOutlined /> },
  { value: 'agent', label: 'Agent (派发 Agent 处理)', icon: <RobotOutlined /> },
  { value: 'function', label: 'Function (进程内调用)', icon: <FunctionOutlined /> },
];

const BLOCKING_POLICY_OPTIONS: { value: BlockingPolicy; label: string }[] = [
  { value: 'continue', label: 'continue（放行）' },
  { value: 'deny', label: 'deny（软阻断）' },
  { value: 'abort', label: 'abort（终止对话）' },
  { value: 'modify', label: 'modify（改参数）' },
];

const buildEmptyHook = (): HookConfigItem => ({
  name: `hook_${Date.now().toString(36)}`,
  enabled: true,
  description: '',
  priority: 100,
  trigger: {
    trigger_type: 'pre_tool_use',
    tool_name_globs: ['*'],
  },
  endpoint: {
    kind: 'api',
    api_url: '',
    api_headers: {},
    timeout: 30,
    blocking: true,
    default_on_error: 'continue',
    cli_in_sandbox: true,
    cli_allowlist: [],
  },
});

export default function TabHooks() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const { message, modal } = App.useApp();

  const [config, setConfig] = useState<TeamHookConfig>(DEFAULT_TEAM_HOOK_CONFIG);
  const [hasChanges, setHasChanges] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeKey, setActiveKey] = useState<string[]>([]);
  // Registered agents for the agent-name dropdown (kind=agent endpoint).
  const [agentOptions, setAgentOptions] = useState<
    { value: string; label: string; desc?: string }[]
  >([
    { value: 'MemoryReflectAgent', label: 'MemoryReflectAgent', desc: '记忆 tier 2：每 N 轮反思' },
    { value: 'MemoryCurateAgent', label: 'MemoryCurateAgent', desc: '记忆 tier 3：会话归档' },
  ]);

  // Registered in-process functions for the function-name dropdown
  // (kind=function endpoint). Memory tier 0/1 fast paths live here.
  const [functionOptions, setFunctionOptions] = useState<
    { value: string; label: string; desc?: string }[]
  >([
    { value: 'memory_prefetch', label: 'memory_prefetch', desc: '记忆 tier 0：预取（确定性）' },
    { value: 'memory_write_turn', label: 'memory_write_turn', desc: '记忆 tier 1：每轮写入（确定性）' },
  ]);

  useEffect(() => {
    let cancelled = false;
    apiInterceptors(getAgentList())
      .then(([err, res]) => {
        if (cancelled || err || !res?.agents) return;
        const fetched = res.agents
          .filter(
            a => !agentOptions.some(existing => existing.value === a.name),
          )
          .map(a => ({
            value: a.name,
            label: a.name,
            desc: a.description,
          }));
        if (fetched.length) setAgentOptions(prev => [...prev, ...fetched]);
      })
      .catch(() => {
        // Silent — agent list is a convenience; the AutoComplete still
        // accepts manual input as a fallback.
      });
    apiInterceptors(getHookFunctions())
      .then(([err, res]) => {
        if (cancelled || err || !res?.functions) return;
        const fetched = res.functions
          .filter(
            f => !functionOptions.some(existing => existing.value === f.name),
          )
          .map(f => ({ value: f.name, label: f.name }));
        if (fetched.length) setFunctionOptions(prev => [...prev, ...fetched]);
      })
      .catch(() => {
        // Silent — function list is a convenience.
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load from team_context.hook_config
  useEffect(() => {
    const tc = (appInfo?.team_context || {}) as Record<string, any>;
    if (tc.hook_config) {
      const merged: TeamHookConfig = {
        enabled: !!tc.hook_config.enabled,
        hooks: Array.isArray(tc.hook_config.hooks) ? tc.hook_config.hooks : [],
        plugin_paths: Array.isArray(tc.hook_config.plugin_paths)
          ? tc.hook_config.plugin_paths
          : [],
      };
      setConfig(merged);
    } else {
      setConfig(DEFAULT_TEAM_HOOK_CONFIG);
    }
    setHasChanges(false);
  }, [appInfo?.app_code, appInfo?.team_context]);

  const hookCount = config.hooks.length;
  const enabledCount = useMemo(
    () => config.hooks.filter(h => h.enabled).length,
    [config],
  );

  const updateConfig = (next: TeamHookConfig) => {
    setConfig(next);
    setHasChanges(true);
  };

  const handleAdd = () => {
    const next = buildEmptyHook();
    updateConfig({ ...config, hooks: [...config.hooks, next] });
    setActiveKey([...activeKey, next.name]);
  };

  const handleRemove = (name: string) => {
    modal.confirm({
      title: t('hooks_remove_title', '删除 Hook'),
      content: t('hooks_remove_content', '确认删除该 Hook 配置？'),
      onOk: () => {
        updateConfig({
          ...config,
          hooks: config.hooks.filter(h => h.name !== name),
        });
      },
    });
  };

  const updateHook = (idx: number, patch: Partial<HookConfigItem>) => {
    const next = config.hooks.map((h, i) => (i === idx ? { ...h, ...patch } : h));
    updateConfig({ ...config, hooks: next });
  };

  const updateEndpoint = (idx: number, patch: Partial<HookEndpointConfig>) => {
    const next = config.hooks.map((h, i) =>
      i === idx ? { ...h, endpoint: { ...h.endpoint, ...patch } } : h,
    );
    updateConfig({ ...config, hooks: next });
  };

  const updateTrigger = (
    idx: number,
    patch: Partial<HookConfigItem['trigger']>,
  ) => {
    const next = config.hooks.map((h, i) =>
      i === idx ? { ...h, trigger: { ...h.trigger, ...patch } } : h,
    );
    updateConfig({ ...config, hooks: next });
  };

  const handleReset = () => {
    modal.confirm({
      title: t('hooks_reset_title', '重置 Hook 配置'),
      content: t('hooks_reset_content', '将清空所有 Hook 设置，确认继续？'),
      onOk: () => updateConfig(DEFAULT_TEAM_HOOK_CONFIG),
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const teamContext = { ...(appInfo?.team_context || {}), hook_config: config };
      await fetchUpdateApp({ ...appInfo, team_context: teamContext });
      setHasChanges(false);
      message.success(t('hooks_save_success', 'Hook 配置已保存'));
    } catch (e) {
      message.error(t('hooks_save_failed', 'Hook 配置保存失败'));
    } finally {
      setSaving(false);
    }
  };

  const renderEndpointFields = (hook: HookConfigItem, idx: number) => {
    const ep = hook.endpoint;
    if (ep.kind === 'api') {
      return (
        <div className="space-y-3">
          <div>
            <Text className="text-xs text-gray-500">API URL</Text>
            <Input
              placeholder="https://hooks.example.com/derisk"
              value={ep.api_url}
              onChange={e => updateEndpoint(idx, { api_url: e.target.value })}
            />
          </div>
          <div>
            <Text className="text-xs text-gray-500">Bearer Token (Authorization)</Text>
            <Input.Password
              placeholder="可选"
              value={ep.api_auth_token}
              onChange={e => updateEndpoint(idx, { api_auth_token: e.target.value })}
            />
          </div>
        </div>
      );
    }
    if (ep.kind === 'cli') {
      return (
        <div className="space-y-3">
          <Alert
            type="warning"
            showIcon
            message={t(
              'hooks_cli_safety',
              'CLI 命令默认在沙箱中执行；如必须在宿主机执行，请关闭沙箱并显式配置 allowlist',
            )}
          />
          <div>
            <Text className="text-xs text-gray-500">CLI 命令模板（事件 JSON 由 stdin 传入）</Text>
            <Input
              placeholder="/path/to/checker.sh --strict"
              value={ep.cli_command}
              onChange={e => updateEndpoint(idx, { cli_command: e.target.value })}
            />
          </div>
          <div className="flex items-center gap-3">
            <Switch
              checked={ep.cli_in_sandbox !== false}
              onChange={v => updateEndpoint(idx, { cli_in_sandbox: v })}
            />
            <Text className="text-xs text-gray-500">沙箱内执行</Text>
          </div>
          <div>
            <Text className="text-xs text-gray-500">命令允许名单（首 token，逗号分隔）</Text>
            <Input
              placeholder="checker.sh,/usr/bin/python3"
              value={(ep.cli_allowlist || []).join(',')}
              onChange={e =>
                updateEndpoint(idx, {
                  cli_allowlist: e.target.value
                    .split(',')
                    .map(s => s.trim())
                    .filter(Boolean),
                })
              }
            />
          </div>
          <div>
            <Text className="text-xs text-gray-500">工作目录 cwd（可选）</Text>
            <Input
              placeholder="/workspace 或留空"
              value={ep.cli_cwd}
              onChange={e => updateEndpoint(idx, { cli_cwd: e.target.value })}
            />
          </div>
        </div>
      );
    }
    if (ep.kind === 'function') {
      return (
        <div className="space-y-3">
          <Alert
            type="info"
            showIcon
            message={t(
              'hooks_function_hint',
              '进程内 Python callable，由 FunctionRegistry 按 name 解析；不走 LLM、不走 AgentManager。适合每轮触发的轻量任务（如记忆 tier 0/1）',
            )}
          />
          <div>
            <Text className="text-xs text-gray-500">Function name</Text>
            <AutoComplete
              className="w-full"
              value={ep.function_name}
              onChange={v => updateEndpoint(idx, { function_name: v })}
              placeholder="从下拉列表选择，或手动输入 function name"
              options={functionOptions.map(o => ({
                value: o.value,
                label: (
                  <span>
                    <Text strong>{o.label}</Text>
                    {o.desc && (
                      <Text type="secondary" className="ml-2 text-xs">
                        {o.desc}
                      </Text>
                    )}
                  </span>
                ),
              }))}
              filterOption={(input, option) =>
                (option?.value as string)
                  ?.toLowerCase()
                  .includes(input.toLowerCase())
              }
            />
          </div>
        </div>
      );
    }
    return (
      <div className="space-y-3">
        <div>
          <Text className="text-xs text-gray-500">目标 Agent name</Text>
          <AutoComplete
            className="w-full"
            value={ep.agent_name}
            onChange={v => updateEndpoint(idx, { agent_name: v })}
            placeholder="从下拉列表选择，或手动输入 agent name"
            options={agentOptions.map(o => ({
              value: o.value,
              label: (
                <span>
                  <Text strong>{o.label}</Text>
                  {o.desc && (
                    <Text type="secondary" className="ml-2 text-xs">
                      {o.desc}
                    </Text>
                  )}
                </span>
              ),
            }))}
            filterOption={(input, option) =>
              (option?.value as string)
                ?.toLowerCase()
                .includes(input.toLowerCase())
            }
          />
        </div>
        <div>
          <Text className="text-xs text-gray-500">Agent app_code（可选）</Text>
          <Input
            placeholder="如果该 hook 实现为子应用"
            value={ep.agent_app_code}
            onChange={e => updateEndpoint(idx, { agent_app_code: e.target.value })}
          />
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full w-full bg-gradient-to-br from-gray-50/50 to-amber-50/20">
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200/60 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="flex items-center gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 shadow-lg shadow-amber-500/20">
            <ThunderboltOutlined className="text-white text-lg" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900 tracking-tight">
              {t('hooks_title', '统一 Hook 系统')}
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {t(
                'hooks_subtitle',
                'API / CLI / Agent / Function 四种落点；支持工具调用前后阻断、参数改写，兼容 Claude Code plugin',
              )}
            </p>
          </div>
          {hasChanges && (
            <Tag color="orange" className="ml-2">
              <WarningOutlined className="mr-1" />
              {t('hooks_unsaved', '未保存')}
            </Tag>
          )}
        </div>
        <Space>
          <Tooltip title={t('hooks_reset', '重置')}>
            <Button icon={<ReloadOutlined />} onClick={handleReset} />
          </Tooltip>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            disabled={!hasChanges}
            onClick={handleSave}
            className="bg-gradient-to-r from-amber-500 to-orange-600 border-0"
          >
            {t('save', '保存')}
          </Button>
        </Space>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-5xl mx-auto space-y-4">
          <Card className="shadow-sm">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-semibold text-gray-800">
                  {t('hooks_master_switch', 'Hook 总开关')}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {t(
                    'hooks_master_desc',
                    '关闭后所有 Hook 都不会触发，已配置的 Hook 仍会保留',
                  )}
                </div>
              </div>
              <Switch
                checked={config.enabled}
                onChange={v => updateConfig({ ...config, enabled: v })}
              />
            </div>
            <div className="mt-4 flex items-center gap-3 text-xs text-gray-500">
              <Badge status={config.enabled ? 'success' : 'default'} />
              {t('hooks_summary', '已配置 Hook：')}
              <Tag color="blue">{hookCount}</Tag>
              <span>·</span>
              {t('hooks_summary_enabled', '启用：')}
              <Tag color="green">{enabledCount}</Tag>
            </div>
          </Card>

          <Card
            title={
              <div className="flex items-center justify-between">
                <span>{t('hooks_list_title', 'Hook 列表')}</span>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd} size="small">
                  {t('hooks_add', '新增 Hook')}
                </Button>
              </div>
            }
            className="shadow-sm"
          >
            {config.hooks.length === 0 ? (
              <Empty description={t('hooks_empty', '尚未配置任何 Hook')} />
            ) : (
              <Collapse
                activeKey={activeKey}
                onChange={k => setActiveKey(Array.isArray(k) ? k : [k])}
                ghost
              >
                {config.hooks.map((hook, idx) => {
                  const ep = hook.endpoint;
                  return (
                    <Panel
                      key={hook.name}
                      header={
                        <div className="flex items-center gap-2">
                          <Switch
                            size="small"
                            checked={hook.enabled}
                            onChange={v => updateHook(idx, { enabled: v })}
                            onClick={(_, ev) => ev.stopPropagation()}
                          />
                          <Tag color={
                            ep.kind === 'cli' ? 'volcano'
                            : ep.kind === 'api' ? 'blue'
                            : ep.kind === 'function' ? 'green'
                            : 'purple'
                          }>
                            {ep.kind.toUpperCase()}
                          </Tag>
                          <Tag color="default">{hook.trigger.trigger_type}</Tag>
                          {ep.blocking && <Tag color="red">blocking</Tag>}
                          <Text strong>{hook.name}</Text>
                          {hook.description && (
                            <Text type="secondary" className="text-xs">
                              {hook.description}
                            </Text>
                          )}
                        </div>
                      }
                      extra={
                        <Button
                          type="text"
                          danger
                          icon={<DeleteOutlined />}
                          size="small"
                          onClick={ev => {
                            ev.stopPropagation();
                            handleRemove(hook.name);
                          }}
                        />
                      }
                    >
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Text className="text-xs text-gray-500">{t('hooks_field_name', '名称')}</Text>
                          <Input
                            value={hook.name}
                            onChange={e => updateHook(idx, { name: e.target.value })}
                          />
                        </div>
                        <div>
                          <Text className="text-xs text-gray-500">
                            {t('hooks_field_priority', '优先级（小的先执行）')}
                          </Text>
                          <InputNumber
                            min={0}
                            max={9999}
                            value={hook.priority}
                            onChange={v => updateHook(idx, { priority: v ?? 100 })}
                            className="w-full"
                          />
                        </div>
                        <div className="col-span-2">
                          <Text className="text-xs text-gray-500">
                            {t('hooks_field_description', '描述')}
                          </Text>
                          <Input
                            value={hook.description}
                            onChange={e => updateHook(idx, { description: e.target.value })}
                          />
                        </div>

                        <div>
                          <Text className="text-xs text-gray-500">
                            {t('hooks_field_trigger', '触发点')}
                          </Text>
                          <Select
                            className="w-full"
                            value={hook.trigger.trigger_type}
                            onChange={v => updateTrigger(idx, { trigger_type: v })}
                            options={TRIGGER_OPTIONS.map(o => ({
                              value: o.value,
                              label: (
                                <span>
                                  <Text strong>{o.label}</Text>
                                  <Text type="secondary" className="ml-2 text-xs">
                                    {o.description}
                                  </Text>
                                </span>
                              ),
                            }))}
                          />
                        </div>
                        {hook.trigger.trigger_type === 'turn_complete' && (
                          <div>
                            <Text className="text-xs text-gray-500">
                              每 N 轮触发（留空或 1 = 每轮）
                            </Text>
                            <InputNumber
                              min={1}
                              max={1000}
                              className="w-full"
                              placeholder="留空 = 每轮；10 = 每 10 轮"
                              value={hook.trigger.every_n_turns ?? undefined}
                              onChange={v =>
                                updateTrigger(idx, {
                                  every_n_turns: v == null ? null : v,
                                })
                              }
                            />
                          </div>
                        )}
                        <div>
                          <Text className="text-xs text-gray-500">
                            {t('hooks_field_tool_globs', '工具名匹配（fnmatch；多个逗号分隔）')}
                          </Text>
                          <Input
                            placeholder="* 或 Bash,Write,mcp__*"
                            value={(hook.trigger.tool_name_globs || []).join(',')}
                            onChange={e =>
                              updateTrigger(idx, {
                                tool_name_globs: e.target.value
                                  .split(',')
                                  .map(s => s.trim())
                                  .filter(Boolean),
                              })
                            }
                          />
                        </div>

                        <div>
                          <Text className="text-xs text-gray-500">
                            {t('hooks_field_kind', '落点类型')}
                          </Text>
                          <Select
                            className="w-full"
                            value={ep.kind}
                            onChange={v => updateEndpoint(idx, { kind: v })}
                            options={KIND_OPTIONS.map(o => ({
                              value: o.value,
                              label: (
                                <span>
                                  {o.icon}
                                  <span className="ml-2">{o.label}</span>
                                </span>
                              ),
                            }))}
                          />
                        </div>
                        <div>
                          <Text className="text-xs text-gray-500">
                            {t('hooks_field_timeout', '超时（秒）')}
                          </Text>
                          <InputNumber
                            min={1}
                            max={600}
                            className="w-full"
                            value={ep.timeout}
                            onChange={v => updateEndpoint(idx, { timeout: v ?? 30 })}
                          />
                        </div>

                        <div>
                          <Text className="text-xs text-gray-500">
                            {t('hooks_field_blocking', '是否同步阻断（仅 pre_* 有效）')}
                          </Text>
                          <Switch
                            checked={!!ep.blocking}
                            onChange={v => updateEndpoint(idx, { blocking: v })}
                          />
                        </div>
                        <div>
                          <Text className="text-xs text-gray-500">
                            {t('hooks_field_default_on_error', '错误兜底策略')}
                          </Text>
                          <Select
                            className="w-full"
                            value={ep.default_on_error || 'continue'}
                            onChange={v => updateEndpoint(idx, { default_on_error: v })}
                            options={BLOCKING_POLICY_OPTIONS}
                          />
                        </div>
                      </div>

                      <div className="mt-4 p-3 rounded-lg bg-gray-50 border border-gray-100">
                        <Text className="text-xs text-gray-500 block mb-2">
                          {t('hooks_endpoint_section', '落点详细配置')}
                        </Text>
                        {renderEndpointFields(hook, idx)}
                      </div>
                    </Panel>
                  );
                })}
              </Collapse>
            )}
          </Card>

          <Card
            title={t('hooks_plugin_title', 'Claude Code 插件路径（可选）')}
            className="shadow-sm"
          >
            <Alert
              type="info"
              showIcon
              className="mb-3"
              message={t(
                'hooks_plugin_desc',
                '指定一个或多个目录或 hooks.json 路径，自动导入 Claude Code 风格的 plugin hooks。',
              )}
            />
            <Input.TextArea
              rows={3}
              placeholder={'/path/to/.claude/plugins\n/another/plugin/hooks.json'}
              value={(config.plugin_paths || []).join('\n')}
              onChange={e =>
                updateConfig({
                  ...config,
                  plugin_paths: e.target.value
                    .split('\n')
                    .map(s => s.trim())
                    .filter(Boolean),
                })
              }
            />
          </Card>
        </div>
      </div>
    </div>
  );
}
