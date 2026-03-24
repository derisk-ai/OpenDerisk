'use client';

import { useState, useCallback, useMemo, useContext, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useRequest } from 'ahooks';
import {
  Input,
  Spin,
  Tag,
  Tooltip,
  Badge,
  Empty,
  message,
  Switch,
  Collapse,
  Button,
  Space,
  Alert,
  Divider,
  Card,
  Modal,
  Form,
  Select,
  InputNumber,
  Table,
} from 'antd';
import {
  SearchOutlined,
  ReloadOutlined,
  SafetyOutlined,
  ToolOutlined,
  AppstoreOutlined,
  CloudServerOutlined,
  CheckCircleFilled,
  MinusCircleFilled,
  PlusCircleFilled,
  InfoCircleOutlined,
  SettingOutlined,
  LockOutlined,
  ThunderboltOutlined,
  PlusOutlined,
  DeleteOutlined,
} from '@ant-design/icons';

import { AppContext } from '@/contexts';
import {
  getToolGroups,
  updateToolBinding,
  batchUpdateToolBindings,
  clearToolCache,
  type ToolGroup,
  type ToolWithBinding,
  type ToolBindingType,
} from '@/client/api/tools/management';
import { GET, POST, PUT } from '@/client/api';
import { AgentAuthorizationConfig } from '@/components/config/AgentAuthorizationConfig';
import type { AuthorizationConfig } from '@/types/authorization';
import { AuthorizationMode, LLMJudgmentPolicy } from '@/types/authorization';

const { Panel } = Collapse;

// 分组配置
const GROUP_CONFIG: Record<ToolBindingType, { icon: React.ReactNode; color: string }> = {
  builtin_required: {
    icon: <SafetyOutlined />,
    color: '#1677ff',
  },
  builtin_optional: {
    icon: <ToolOutlined />,
    color: '#13c2c2',
  },
  custom: {
    icon: <AppstoreOutlined />,
    color: '#fa8c16',
  },
  external: {
    icon: <CloudServerOutlined />,
    color: '#722ed1',
  },
};

// 风险等级颜色
const RISK_COLORS: Record<string, string> = {
  safe: 'green',
  low: 'green',
  medium: 'orange',
  high: 'red',
  critical: 'red',
};

// 流式配置策略选项
const STRATEGY_OPTIONS = [
  { value: 'adaptive', label: '自适应 (推荐)' },
  { value: 'line_based', label: '按行分片' },
  { value: 'semantic', label: '语义分片' },
  { value: 'fixed_size', label: '固定大小' },
];

const RENDERER_OPTIONS = [
  { value: 'code', label: '代码渲染器' },
  { value: 'text', label: '文本渲染器' },
  { value: 'default', label: '默认渲染器' },
];

// 流式配置类型
interface ParamStreamingConfig {
  param_name: string;
  threshold: number;
  strategy: string;
  chunk_size: number;
  chunk_by_line: boolean;
  renderer: string;
  enabled: boolean;
  description?: string;
}

interface ToolStreamingConfig {
  tool_name: string;
  app_code: string;
  param_configs: ParamStreamingConfig[];
  global_threshold: number;
  global_strategy: string;
  global_renderer: string;
  enabled: boolean;
  priority: number;
}

/**
 * 从 input_schema 中提取参数名列表
 * input_schema 格式:
 * {
 *   "type": "object",
 *   "properties": {
 *     "param1": { "type": "string", "description": "..." },
 *     "param2": { "type": "number", "description": "..." }
 *   },
 *   "required": ["param1"]
 * }
 */
function getParamsFromSchema(inputSchema: { properties?: Record<string, unknown> } | undefined): string[] {
  if (!inputSchema || !inputSchema.properties) {
    return [];
  }
  return Object.keys(inputSchema.properties);
}

export default function TabToolsManagement() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');
  const [togglingTools, setTogglingTools] = useState<Set<string>>(new Set());
  const [expandedGroups, setExpandedGroups] = useState<string[]>([]);
  
  // 流式配置相关状态
  const [streamingModalVisible, setStreamingModalVisible] = useState(false);
  const [currentStreamingTool, setCurrentStreamingTool] = useState<ToolWithBinding | null>(null);
  const [streamingConfigs, setStreamingConfigs] = useState<Record<string, ToolStreamingConfig>>({});
  const [currentStreamingConfig, setCurrentStreamingConfig] = useState<ToolStreamingConfig | null>(null);

  const appCode = appInfo?.app_code;
  const agentName = useMemo(() => {
    const firstAgent = appInfo?.details?.[0];
    return firstAgent?.agent_name || 'default';
  }, [appInfo]);

  const sandboxEnabled = useMemo(() => {
    const teamContext = appInfo?.team_context;
    if (!teamContext) return false;
    const context = typeof teamContext === 'string' ? JSON.parse(teamContext) : teamContext;
    return context?.use_sandbox ?? false;
  }, [appInfo?.team_context]);

  // 获取工具分组列表
  const { data: toolGroupsData, loading, refresh } = useRequest(
    async () => {
      if (!appCode) return null;
      const res = await getToolGroups({
        app_id: appCode,
        agent_name: agentName,
        lang: t('language') || 'zh',
        sandbox_enabled: sandboxEnabled,
      });
      if (res.data?.success) {
        setExpandedGroups(res.data.data.map((g) => g.group_id));
        return res.data.data;
      }
      return null;
    },
    {
      refreshDeps: [appCode, agentName, t, sandboxEnabled],
      ready: !!appCode,
    }
  );

  // 可用工具列表
  const availableTools = useMemo(() => {
    if (!toolGroupsData) return [];
    const toolNames = new Set<string>();
    toolGroupsData.forEach((group) => {
      group.tools.forEach((tool) => {
        toolNames.add(tool.name);
      });
    });
    return Array.from(toolNames);
  }, [toolGroupsData]);

  // 过滤工具
  const filteredGroups = useMemo(() => {
    if (!toolGroupsData) return [];
    if (!searchValue) return toolGroupsData;

    const lower = searchValue.toLowerCase();
    return toolGroupsData
      .map((group) => ({
        ...group,
        tools: group.tools.filter(
          (tool) =>
            tool.name.toLowerCase().includes(lower) ||
            tool.display_name.toLowerCase().includes(lower) ||
            tool.description.toLowerCase().includes(lower) ||
            tool.tags.some((tag) => tag.toLowerCase().includes(lower))
        ),
      }))
      .filter((group) => group.tools.length > 0);
  }, [toolGroupsData, searchValue]);

  // 处理工具绑定/解绑
  const handleToggleBinding = useCallback(
    async (tool: ToolWithBinding, groupType: ToolBindingType) => {
      const toolId = tool.tool_id;
      const newBindingState = !tool.is_bound;

      if (togglingTools.has(toolId)) return;
      setTogglingTools((prev) => new Set(prev).add(toolId));

      try {
        const res = await updateToolBinding({
          app_id: appCode!,
          agent_name: agentName,
          tool_id: toolId,
          is_bound: newBindingState,
        });

        if (res.success) {
          message.success(
            newBindingState
              ? t('builder_tool_bound_success') || '工具绑定成功'
              : t('builder_tool_unbound_success') || '工具解绑成功'
          );
          refresh();
        } else {
          message.error(res.message || t('builder_tool_toggle_error') || '操作失败');
        }
      } catch (error) {
        message.error(t('builder_tool_toggle_error') || '操作失败');
      } finally {
        setTogglingTools((prev) => {
          const next = new Set(prev);
          next.delete(toolId);
          return next;
        });
      }
    },
    [appCode, agentName, togglingTools, refresh, t]
  );

  // 批量绑定/解绑分组内所有工具
  const handleBatchToggle = useCallback(
    async (group: ToolGroup, bindAll: boolean) => {
      const bindings = group.tools.map((tool) => ({
        tool_id: tool.tool_id,
        is_bound: bindAll,
      }));

      try {
        const res = await batchUpdateToolBindings({
          app_id: appCode!,
          agent_name: agentName,
          bindings,
        });

        if (res.success) {
          message.success(
            bindAll
              ? t('builder_batch_bound_success') || '批量绑定成功'
              : t('builder_batch_unbound_success') || '批量解绑成功'
          );
          refresh();
        } else {
          message.error(res.message || t('builder_batch_toggle_error') || '批量操作失败');
        }
      } catch (error) {
        message.error(t('builder_batch_toggle_error') || '批量操作失败');
      }
    },
    [appCode, agentName, refresh, t]
  );

  // 获取统计信息
  const stats = useMemo(() => {
    if (!toolGroupsData) return { total: 0, bound: 0, defaultBound: 0 };
    let total = 0;
    let bound = 0;
    let defaultBound = 0;
    toolGroupsData.forEach((group) => {
      total += group.tools.length;
      group.tools.forEach((tool) => {
        if (tool.is_bound) bound++;
        if (tool.is_default && tool.is_bound) defaultBound++;
      });
    });
    return { total, bound, defaultBound };
  }, [toolGroupsData]);

  // 切换分组展开状态
  const handleCollapseChange = useCallback((keys: string | string[]) => {
    setExpandedGroups(Array.isArray(keys) ? keys : [keys]);
  }, []);

  // 加载流式配置
  const loadStreamingConfigs = useCallback(async () => {
    if (!appCode) return;
    try {
      const response = await GET<null, { app_code: string; configs: ToolStreamingConfig[]; total: number }>(
        `/api/v1/streaming-config/apps/${appCode}`
      );
      const data = response.data;
      if (data?.configs && Array.isArray(data.configs)) {
        const configMap: Record<string, ToolStreamingConfig> = {};
        data.configs.forEach((cfg: ToolStreamingConfig) => {
          configMap[cfg.tool_name] = cfg;
        });
        setStreamingConfigs(configMap);
        console.log('[ToolStreaming] Loaded configs:', Object.keys(configMap));
      }
    } catch (error) {
      console.error('Failed to load streaming configs:', error);
      message.warning(t('streaming_load_failed') || '加载流式配置失败');
    }
  }, [appCode, t]);

  useEffect(() => {
    loadStreamingConfigs();
  }, [loadStreamingConfigs]);

  // 打开流式配置弹窗
  const openStreamingModal = useCallback((tool: ToolWithBinding) => {
    console.log('[ToolStreaming] Opening modal for tool:', tool.name, 'input_schema:', tool.input_schema);
    setCurrentStreamingTool(tool);
    const existingConfig = streamingConfigs[tool.name];
    if (existingConfig) {
      setCurrentStreamingConfig(existingConfig);
    } else {
      setCurrentStreamingConfig({
        tool_name: tool.name,
        app_code: appCode || '',
        param_configs: [],
        global_threshold: 256,
        global_strategy: 'adaptive',
        global_renderer: 'default',
        enabled: true,
        priority: 0,
      });
    }
    setStreamingModalVisible(true);
  }, [streamingConfigs, appCode]);

  // 保存流式配置
  const saveStreamingConfig = useCallback(async (config: ToolStreamingConfig) => {
    console.log('[ToolStreaming] saveStreamingConfig called with config:', config);
    console.log('[ToolStreaming] appCode:', appCode, 'currentStreamingTool:', currentStreamingTool?.name);
    
    if (!appCode) {
      console.error('[ToolStreaming] No appCode');
      message.error(t('builder_no_app_selected') || '未选择应用');
      return;
    }
    if (!currentStreamingTool) {
      console.error('[ToolStreaming] No currentStreamingTool');
      message.error(t('streaming_no_tool_selected') || '未选择工具');
      return;
    }
    
    const invalidParams = config.param_configs.filter(p => !p.param_name);
    if (invalidParams.length > 0) {
      console.error('[ToolStreaming] Invalid params:', invalidParams);
      message.error(t('streaming_param_name_required') || '请填写所有参数名称');
      return;
    }
    
    try {
      const url = `/api/v1/streaming-config/apps/${appCode}/tools/${currentStreamingTool.name}`;
      console.log('[ToolStreaming] Sending PUT to:', url, 'with data:', JSON.stringify(config, null, 2));
      
      const response = await PUT<ToolStreamingConfig, { success: boolean; config: ToolStreamingConfig }>(
        url,
        config
      );
      console.log('[ToolStreaming] Save response:', response);
      if (response.data?.success) {
        message.success(t('streaming_save_success') || '配置已保存');
        setStreamingConfigs(prev => ({ ...prev, [currentStreamingTool.name]: config }));
        setStreamingModalVisible(false);
      } else {
        const errorMsg = (response.data as any)?.error || t('streaming_save_failed') || '保存失败';
        console.error('[ToolStreaming] Save failed:', errorMsg);
        message.error(errorMsg);
      }
    } catch (error) {
      console.error('[ToolStreaming] Failed to save streaming config:', error);
      message.error(t('streaming_save_failed') || '保存失败');
    }
  }, [appCode, currentStreamingTool, t]);

  if (!appCode) {
    return (
      <div className="flex items-center justify-center h-64">
        <Alert
          message={t('builder_no_app_selected') || '未选择应用'}
          description={t('builder_please_select_app') || '请先选择或创建一个应用'}
          type="info"
          showIcon
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-white">
      {/* 头部工具栏 */}
      <div className="px-5 py-4 border-b border-gray-100">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800">
            {t('builder_tool_management') || '工具管理'}
          </h3>
          <Space>
            <Tooltip title={t('builder_refresh') || '刷新'}>
              <Button
                icon={<ReloadOutlined />}
                onClick={refresh}
                loading={loading}
                size="small"
              />
            </Tooltip>
          </Space>
        </div>

        {/* 搜索框 */}
        <Input
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder={t('builder_search_tools_placeholder') || '搜索工具...'}
          value={searchValue}
          onChange={(e) => setSearchValue(e.target.value)}
          allowClear
          className="rounded-lg"
        />

        {/* 统计信息 */}
        <div className="flex items-center gap-4 mt-3 text-sm text-gray-500">
          <span>
            {t('builder_tools_total') || '共'} <b className="text-gray-700">{stats.total}</b>{' '}
            {t('builder_tools_count') || '个工具'}
          </span>
          <Divider type="vertical" />
          <span>
            {t('builder_tools_bound') || '已绑定'} <b className="text-green-600">{stats.bound}</b>{' '}
            {t('builder_tools_count') || '个'}
          </span>
          <Divider type="vertical" />
          <span>
            {t('builder_tools_default_bound') || '默认绑定'} <b className="text-blue-600">{stats.defaultBound}</b>{' '}
            {t('builder_tools_count') || '个'}
          </span>
        </div>
      </div>

      {/* 工具分组列表 */}
      <div className="flex-1 overflow-y-auto p-4">
        <Spin spinning={loading}>
          {filteredGroups.length > 0 ? (
            <Collapse
              activeKey={expandedGroups}
              onChange={handleCollapseChange}
              bordered={false}
              expandIconPosition="end"
              className="tool-groups-collapse"
            >
              {filteredGroups.map((group) => (
                <Panel
                  key={group.group_id}
                  header={
                    <div className="flex items-center justify-between pr-4">
                      <div className="flex items-center gap-3">
                        <div
                          className="w-8 h-8 rounded-lg flex items-center justify-center text-white"
                          style={{
                            backgroundColor: GROUP_CONFIG[group.group_type].color,
                          }}
                        >
                          {GROUP_CONFIG[group.group_type].icon}
                        </div>
                        <div>
                          <div className="font-medium text-gray-800">{group.group_name}</div>
                          <div className="text-xs text-gray-400">{group.description}</div>
                        </div>
                        <Badge
                          count={group.count}
                          style={{
                            backgroundColor: GROUP_CONFIG[group.group_type].color,
                          }}
                        />
                      </div>
                      {/* 批量操作按钮 */}
                      <Space onClick={(e) => e.stopPropagation()}>
                        <span className="text-xs text-gray-400">
                          {group.tools.filter((t) => t.is_bound).length}/{group.count}{' '}
                          {t('builder_tools_bound') || '已绑定'}
                        </span>
                        {group.group_type !== 'builtin_required' && (
                          <>
                            <Button
                              size="small"
                              icon={<PlusCircleFilled />}
                              onClick={() => handleBatchToggle(group, true)}
                            >
                              {t('builder_bind_all') || '全部绑定'}
                            </Button>
                            <Button
                              size="small"
                              icon={<MinusCircleFilled />}
                              onClick={() => handleBatchToggle(group, false)}
                            >
                              {t('builder_unbind_all') || '全部解绑'}
                            </Button>
                          </>
                        )}
                      </Space>
                    </div>
                  }
                  className="mb-3 bg-gray-50 rounded-lg overflow-hidden"
                >
                  {/* 分组提示 */}
                  {group.group_type === 'builtin_required' && (
                    <Alert
                      message={t('builder_builtin_required_tip') || '默认绑定工具'}
                      description={
                        t('builder_builtin_required_desc') ||
                        '这些工具是 Agent 默认绑定的核心工具，您可以反向解除绑定，但可能会影响 Agent 的基础功能。'
                      }
                      type="info"
                      showIcon
                      icon={<InfoCircleOutlined />}
                      className="mb-3"
                    />
                  )}

                  {/* 工具列表 */}
                  <div className="space-y-2">
                    {group.tools.map((tool) => (
                      <ToolItem
                        key={tool.tool_id}
                        tool={tool}
                        groupType={group.group_type}
                        isToggling={togglingTools.has(tool.tool_id)}
                        onToggle={() => handleToggleBinding(tool, group.group_type)}
                        onOpenStreamingConfig={() => openStreamingModal(tool)}
                        hasStreamingConfig={!!streamingConfigs[tool.name]}
                        t={t}
                      />
                    ))}
                  </div>
                </Panel>
              ))}
            </Collapse>
          ) : (
            !loading && (
              <Empty
                description={t('builder_no_tools') || '没有找到匹配的工具'}
                className="py-12"
              />
            )
          )}
        </Spin>
      </div>

      {/* 授权配置区域 */}
      <div className="border-t border-gray-100 bg-gray-50/50">
        <Collapse ghost>
          <Panel
            header={
              <div className="flex items-center gap-2">
                <LockOutlined className="text-blue-500" />
                <span className="font-medium text-gray-700">
                  {t('builder_authorization_config') || '授权配置'}
                </span>
                <Tooltip title={t('builder_authorization_config_tip') || '配置工具的授权策略和权限管理'}>
                  <InfoCircleOutlined className="text-gray-400 text-sm" />
                </Tooltip>
              </div>
            }
            key="authorization"
            className="bg-transparent"
          >
            <div className="bg-white rounded-lg border border-gray-100 p-4">
              <AgentAuthorizationConfig
                value={appInfo?.authorization_config as AuthorizationConfig}
                onChange={(config) => {
                  const updatedApp = {
                    ...appInfo,
                    authorization_config: config,
                  };
                  if (typeof fetchUpdateApp === 'function') {
                    fetchUpdateApp(updatedApp);
                  }
                }}
                availableTools={availableTools}
                showAdvanced={true}
              />
            </div>
          </Panel>
        </Collapse>
      </div>

      {/* 流式配置弹窗 */}
      <Modal
        title={
          <div className="flex items-center gap-2">
            <ThunderboltOutlined className="text-yellow-500" />
            <span>{t('streaming_config_title') || '流式参数配置'} - {currentStreamingTool?.display_name || currentStreamingTool?.name}</span>
          </div>
        }
        open={streamingModalVisible}
        onCancel={() => setStreamingModalVisible(false)}
        width={800}
        footer={[
          <Button key="cancel" onClick={() => setStreamingModalVisible(false)}>
            {t('cancel') || '取消'}
          </Button>,
          <Button
            key="save"
            type="primary"
            onClick={() => {
              if (currentStreamingConfig) {
                saveStreamingConfig(currentStreamingConfig);
              } else {
                message.error(t('streaming_config_not_found') || '配置不存在，请重试');
              }
            }}
          >
            {t('save') || '保存'}
          </Button>,
        ]}
      >
        {currentStreamingConfig && (
          <div>
            <Alert
              message={t('streaming_config_info') || '配置工具参数的流式传输行为'}
              description={t('streaming_config_desc') || '当参数值超过阈值时，将以流式方式传输到前端，实现实时预览效果'}
              type="info"
              showIcon
              className="mb-4"
            />

            <Form layout="vertical">
              <Card size="small" title={t('streaming_global_settings') || '全局设置'} className="mb-4">
                <div className="grid grid-cols-2 gap-4">
                  <Form.Item label={t('streaming_enabled') || '启用流式传输'} className="mb-2">
                    <Switch
                      checked={currentStreamingConfig.enabled}
                      onChange={(checked) =>
                        setCurrentStreamingConfig({ ...currentStreamingConfig, enabled: checked })
                      }
                    />
                  </Form.Item>

                  <Form.Item label={t('streaming_global_threshold') || '全局阈值 (字符)'} className="mb-2">
                    <InputNumber
                      min={0}
                      max={100000}
                      value={currentStreamingConfig.global_threshold}
                      onChange={(value) =>
                        setCurrentStreamingConfig({
                          ...currentStreamingConfig,
                          global_threshold: value || 256,
                        })
                      }
                      style={{ width: '100%' }}
                    />
                  </Form.Item>

                  <Form.Item label={t('streaming_global_strategy') || '分片策略'} className="mb-2">
                    <Select
                      value={currentStreamingConfig.global_strategy}
                      onChange={(value) =>
                        setCurrentStreamingConfig({ ...currentStreamingConfig, global_strategy: value })
                      }
                      options={STRATEGY_OPTIONS}
                    />
                  </Form.Item>

                  <Form.Item label={t('streaming_global_renderer') || '渲染器'} className="mb-2">
                    <Select
                      value={currentStreamingConfig.global_renderer}
                      onChange={(value) =>
                        setCurrentStreamingConfig({ ...currentStreamingConfig, global_renderer: value })
                      }
                      options={RENDERER_OPTIONS}
                    />
                  </Form.Item>
                </div>
              </Card>

              <Card 
                size="small" 
                title={t('streaming_param_configs') || '参数配置'}
                extra={
                  <Button 
                    type="link" 
                    size="small"
                    icon={<PlusOutlined />}
                    onClick={() => {
                      const newParam: ParamStreamingConfig = {
                        param_name: '',
                        threshold: 256,
                        strategy: 'adaptive',
                        chunk_size: 100,
                        chunk_by_line: true,
                        renderer: 'default',
                        enabled: true,
                      };
                      setCurrentStreamingConfig({
                        ...currentStreamingConfig,
                        param_configs: [...currentStreamingConfig.param_configs, newParam],
                      });
                    }}
                  >
                    {t('streaming_add_param') || '添加参数'}
                  </Button>
                }
              >
                {currentStreamingConfig.param_configs.length > 0 ? (
                  <Table
                    size="small"
                    dataSource={currentStreamingConfig.param_configs}
                    rowKey="param_name"
                    pagination={false}
                    columns={[
                      {
                        title: t('streaming_param_name') || '参数名',
                        dataIndex: 'param_name',
                        key: 'param_name',
                        width: 140,
                        render: (value, record, index) => {
                          const availableParams = getParamsFromSchema(currentStreamingTool?.input_schema);
                          console.log('[ToolStreaming] currentStreamingTool:', currentStreamingTool?.name, 'input_schema:', currentStreamingTool?.input_schema, 'availableParams:', availableParams);
                          const existingParams = currentStreamingConfig.param_configs
                            .map((p, i) => i !== index ? p.param_name : null)
                            .filter(Boolean);
                          const selectableParams = availableParams.filter(p => !existingParams.includes(p));
                          
                          if (availableParams.length > 0) {
                            return (
                              <Select
                                value={value}
                                size="small"
                                style={{ width: '100%' }}
                                placeholder={t('streaming_select_param') || '选择参数'}
                                onChange={(v) => {
                                  const newConfigs = [...currentStreamingConfig.param_configs];
                                  newConfigs[index] = { ...record, param_name: v };
                                  setCurrentStreamingConfig({ ...currentStreamingConfig, param_configs: newConfigs });
                                }}
                              >
                                {selectableParams.map((param) => (
                                  <Select.Option key={param} value={param}>
                                    {param}
                                  </Select.Option>
                                ))}
                              </Select>
                            );
                          }
                          
                          return (
                            <Input
                              value={value}
                              size="small"
                              onChange={(e) => {
                                const newConfigs = [...currentStreamingConfig.param_configs];
                                newConfigs[index] = { ...record, param_name: e.target.value };
                                setCurrentStreamingConfig({ ...currentStreamingConfig, param_configs: newConfigs });
                              }}
                              placeholder="content / code / command"
                            />
                          );
                        },
                      },
                      {
                        title: t('streaming_threshold') || '阈值',
                        dataIndex: 'threshold',
                        key: 'threshold',
                        width: 100,
                        render: (value, record, index) => (
                          <InputNumber
                            min={0}
                            max={100000}
                            value={value}
                            onChange={(v) => {
                              const newConfigs = [...currentStreamingConfig.param_configs];
                              newConfigs[index] = { ...record, threshold: v || 256 };
                              setCurrentStreamingConfig({ ...currentStreamingConfig, param_configs: newConfigs });
                            }}
                            size="small"
                          />
                        ),
                      },
                      {
                        title: t('streaming_strategy') || '策略',
                        dataIndex: 'strategy',
                        key: 'strategy',
                        width: 120,
                        render: (value, record, index) => (
                          <Select
                            value={value}
                            size="small"
                            onChange={(v) => {
                              const newConfigs = [...currentStreamingConfig.param_configs];
                              newConfigs[index] = { ...record, strategy: v };
                              setCurrentStreamingConfig({ ...currentStreamingConfig, param_configs: newConfigs });
                            }}
                            options={STRATEGY_OPTIONS}
                          />
                        ),
                      },
                      {
                        title: t('streaming_renderer') || '渲染器',
                        dataIndex: 'renderer',
                        key: 'renderer',
                        width: 120,
                        render: (value, record, index) => (
                          <Select
                            value={value}
                            size="small"
                            onChange={(v) => {
                              const newConfigs = [...currentStreamingConfig.param_configs];
                              newConfigs[index] = { ...record, renderer: v };
                              setCurrentStreamingConfig({ ...currentStreamingConfig, param_configs: newConfigs });
                            }}
                            options={RENDERER_OPTIONS}
                          />
                        ),
                      },
                      {
                        title: t('streaming_enabled') || '启用',
                        dataIndex: 'enabled',
                        key: 'enabled',
                        width: 60,
                        render: (value, record, index) => (
                          <Switch
                            size="small"
                            checked={value}
                            onChange={(checked) => {
                              const newConfigs = [...currentStreamingConfig.param_configs];
                              newConfigs[index] = { ...record, enabled: checked };
                              setCurrentStreamingConfig({ ...currentStreamingConfig, param_configs: newConfigs });
                            }}
                          />
                        ),
                      },
                      {
                        title: '',
                        key: 'action',
                        width: 40,
                        render: (_, record, index) => (
                          <Button
                            type="text"
                            danger
                            size="small"
                            icon={<DeleteOutlined />}
                            onClick={() => {
                              const newConfigs = currentStreamingConfig.param_configs.filter((_, i) => i !== index);
                              setCurrentStreamingConfig({ ...currentStreamingConfig, param_configs: newConfigs });
                            }}
                          />
                        ),
                      },
                    ]}
                  />
                ) : (
                  <Empty description={t('streaming_no_params') || '暂无参数配置，使用全局设置'} image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Form>
          </div>
        )}
      </Modal>
    </div>
  );
}

// 单个工具项组件
interface ToolItemProps {
  tool: ToolWithBinding;
  groupType: ToolBindingType;
  isToggling: boolean;
  onToggle: () => void;
  onOpenStreamingConfig: () => void;
  hasStreamingConfig: boolean;
  t: (key: string) => string;
}

function ToolItem({ tool, groupType, isToggling, onToggle, onOpenStreamingConfig, hasStreamingConfig, t }: ToolItemProps) {
  const isBuiltinRequired = groupType === 'builtin_required';
  const isBound = tool.is_bound;
  const isDefault = tool.is_default;
  const canUnbind = tool.can_unbind;

  // 状态标签
  const statusTag = useMemo(() => {
    if (isDefault && isBound) {
      return (
        <Tag color="blue" className="text-xs">
          {t('tool_status_default') || '默认'}
        </Tag>
      );
    }
    if (isBound) {
      return (
        <Tag color="green" className="text-xs">
          {t('tool_status_bound') || '已绑定'}
        </Tag>
      );
    }
    return (
      <Tag className="text-xs">
        {t('tool_status_unbound') || '未绑定'}
      </Tag>
    );
  }, [isDefault, isBound, t]);

  return (
    <div
      className={`group flex items-center justify-between p-3 rounded-lg border transition-all ${
        isBound
          ? 'bg-blue-50/50 border-blue-100 hover:bg-blue-50'
          : 'bg-white border-gray-100 hover:border-gray-200'
      } ${isToggling ? 'opacity-50 pointer-events-none' : ''}`}
    >
      <div className="flex items-center gap-3 flex-1 min-w-0">
        {/* 绑定状态图标 */}
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
            isBound ? 'bg-blue-100 text-blue-500' : 'bg-gray-100 text-gray-400'
          }`}
        >
          {isBound ? <CheckCircleFilled /> : <ToolOutlined />}
        </div>

        {/* 工具信息 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-gray-800">{tool.display_name || tool.name}</span>
            {statusTag}
            {tool.risk_level === 'high' || tool.risk_level === 'critical' ? (
              <Tooltip title={t('builder_tool_high_risk') || '高风险工具'}>
                <Tag color="red" className="text-xs">
                  {tool.risk_level.toUpperCase()}
                </Tag>
              </Tooltip>
            ) : null}
            {tool.requires_permission && (
              <Tooltip title={t('builder_tool_requires_permission') || '需要权限'}>
                <Tag color="orange" className="text-xs">
                  {t('tool_permission_required') || '需权限'}
                </Tag>
              </Tooltip>
            )}
          </div>
          <div className="text-xs text-gray-500 mt-1 truncate">{tool.description}</div>
          {tool.tags.length > 0 && (
            <div className="flex gap-1 mt-2">
              {tool.tags.slice(0, 3).map((tag) => (
                <Tag key={tag} className="text-xs" size="small">
                  {tag}
                </Tag>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 绑定/解绑开关 */}
      <div className="flex items-center gap-3 ml-4 flex-shrink-0">
        {/* 流式配置按钮 - 只在已绑定时显示 */}
        {isBound && (
          <Tooltip title={hasStreamingConfig ? (t('streaming_edit_config') || '编辑流式配置') : (t('streaming_add_tool') || '添加流式配置')}>
            <Button
              type={hasStreamingConfig ? 'primary' : 'default'}
              size="small"
              icon={<ThunderboltOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                onOpenStreamingConfig();
              }}
              className={hasStreamingConfig ? 'bg-yellow-500 border-yellow-500 hover:bg-yellow-600' : ''}
            />
          </Tooltip>
        )}
        <span className="text-xs text-gray-400">
          {isBound
            ? t('tool_action_unbind') || '点击解绑'
            : t('tool_action_bind') || '点击绑定'}
        </span>
        <Switch
          checked={isBound}
          onChange={onToggle}
          loading={isToggling}
          disabled={isBuiltinRequired && isDefault && !canUnbind}
        />
      </div>
    </div>
  );
}
