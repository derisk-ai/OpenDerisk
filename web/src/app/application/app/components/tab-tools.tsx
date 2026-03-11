'use client';

import { useState, useCallback, useMemo, useContext } from 'react';
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

export default function TabToolsManagement() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const [searchValue, setSearchValue] = useState('');
  const [togglingTools, setTogglingTools] = useState<Set<string>>(new Set());
  const [expandedGroups, setExpandedGroups] = useState<string[]>([]);

  const appCode = appInfo?.app_code;
  const agentName = useMemo(() => {
    const firstAgent = appInfo?.details?.[0];
    return firstAgent?.agent_name || 'default';
  }, [appInfo]);

  // 获取工具分组列表
  const { data: toolGroupsData, loading, refresh } = useRequest(
    async () => {
      if (!appCode) return null;
      const res = await getToolGroups({
        app_id: appCode,
        agent_name: agentName,
        lang: t('language') || 'zh',
      });
      if (res.data?.success) {
        setExpandedGroups(res.data.data.map((g) => g.group_id));
        return res.data.data;
      }
      return null;
    },
    {
      refreshDeps: [appCode, agentName, t],
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
    </div>
  );
}

// 单个工具项组件
interface ToolItemProps {
  tool: ToolWithBinding;
  groupType: ToolBindingType;
  isToggling: boolean;
  onToggle: () => void;
  t: (key: string) => string;
}

function ToolItem({ tool, groupType, isToggling, onToggle, t }: ToolItemProps) {
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
