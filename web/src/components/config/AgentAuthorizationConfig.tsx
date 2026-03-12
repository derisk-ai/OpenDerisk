'use client';

import React, { useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card,
  Form,
  Select,
  Switch,
  Input,
  InputNumber,
  Button,
  Space,
  Tag,
  Table,
  Tooltip,
  Typography,
  Divider,
  Alert,
  Collapse,
  Row,
  Col,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  LockOutlined,
  UnlockOutlined,
  SafetyOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  SettingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import type {
  AuthorizationConfig,
  AuthorizationMode,
  LLMJudgmentPolicy,
  PermissionAction,
} from '@/types/authorization';
import {
  AuthorizationMode as AuthModeEnum,
  LLMJudgmentPolicy as LLMPolicyEnum,
  PermissionAction as PermActionEnum,
  STRICT_CONFIG,
  PERMISSIVE_CONFIG,
  UNRESTRICTED_CONFIG,
} from '@/types/authorization';

const { Text } = Typography;
const { Option } = Select;
const { Panel } = Collapse;

export interface AgentAuthorizationConfigProps {
  value?: AuthorizationConfig;
  onChange?: (config: AuthorizationConfig) => void;
  disabled?: boolean;
  availableTools?: string[];
  showAdvanced?: boolean;
}

const DEFAULT_CONFIG: AuthorizationConfig = {
  mode: AuthModeEnum.STRICT,
  llm_policy: LLMPolicyEnum.DISABLED,
  tool_overrides: {},
  whitelist_tools: [],
  blacklist_tools: [],
  session_cache_enabled: true,
  session_cache_ttl: 3600,
  authorization_timeout: 300,
};

function ToolListInput({
  value = [],
  onChange,
  availableTools = [],
  placeholder,
  disabled,
  t,
}: {
  value?: string[];
  onChange?: (tools: string[]) => void;
  availableTools?: string[];
  placeholder?: string;
  disabled?: boolean;
  t: (key: string, fallback?: string) => string;
}) {
  const [inputValue, setInputValue] = useState('');

  const handleAdd = useCallback(() => {
    if (inputValue && !value.includes(inputValue)) {
      onChange?.([...value, inputValue]);
      setInputValue('');
    }
  }, [inputValue, value, onChange]);

  const handleRemove = useCallback((tool: string) => {
    onChange?.(value.filter(t => t !== tool));
  }, [value, onChange]);

  return (
    <div>
      <Space wrap style={{ marginBottom: 8 }}>
        {value.map(tool => (
          <Tag
            key={tool}
            closable={!disabled}
            onClose={() => handleRemove(tool)}
          >
            {tool}
          </Tag>
        ))}
      </Space>
      {!disabled && (
        <Space.Compact style={{ width: '100%' }}>
          <Select
            style={{ width: '100%' }}
            placeholder={placeholder}
            value={inputValue || undefined}
            onChange={setInputValue}
            showSearch
            allowClear
          >
            {availableTools
              .filter(t => !value.includes(t))
              .map(tool => (
                <Option key={tool} value={tool}>{tool}</Option>
              ))}
          </Select>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            {t('auth_add', '添加')}
          </Button>
        </Space.Compact>
      )}
    </div>
  );
}

function ToolOverrideEditor({
  value = {},
  onChange,
  availableTools = [],
  disabled,
  t,
}: {
  value?: Record<string, PermissionAction>;
  onChange?: (overrides: Record<string, PermissionAction>) => void;
  availableTools?: string[];
  disabled?: boolean;
  t: (key: string, fallback?: string) => string;
}) {
  const [newTool, setNewTool] = useState('');
  const [newAction, setNewAction] = useState<PermissionAction>(PermActionEnum.ASK);

  const entries = useMemo(() => Object.entries(value), [value]);

  const handleAdd = useCallback(() => {
    if (newTool && !value[newTool]) {
      onChange?.({ ...value, [newTool]: newAction });
      setNewTool('');
    }
  }, [newTool, newAction, value, onChange]);

  const handleRemove = useCallback((tool: string) => {
    const newValue = { ...value };
    delete newValue[tool];
    onChange?.(newValue);
  }, [value, onChange]);

  const handleChange = useCallback((tool: string, action: PermissionAction) => {
    onChange?.({ ...value, [tool]: action });
  }, [value, onChange]);

  const ACTION_OPTIONS = [
    { value: PermActionEnum.ALLOW, label: t('auth_action_allow', '允许'), color: 'success' },
    { value: PermActionEnum.DENY, label: t('auth_action_deny', '拒绝'), color: 'error' },
    { value: PermActionEnum.ASK, label: t('auth_action_ask', '询问'), color: 'warning' },
  ];

  const columns = [
    {
      title: t('auth_tool', '工具'),
      dataIndex: 'tool',
      key: 'tool',
    },
    {
      title: t('auth_action', '动作'),
      dataIndex: 'action',
      key: 'action',
      render: (action: PermissionAction, record: { tool: string }) => (
        <Select
          value={action}
          onChange={(v) => handleChange(record.tool, v)}
          disabled={disabled}
          style={{ width: 100 }}
        >
          {ACTION_OPTIONS.map(opt => (
            <Option key={opt.value} value={opt.value}>
              <Tag color={opt.color}>{opt.label}</Tag>
            </Option>
          ))}
        </Select>
      ),
    },
    {
      title: t('Operation', '操作'),
      key: 'actions',
      width: 80,
      render: (_: any, record: { tool: string }) => (
        <Button
          type="text"
          danger
          icon={<DeleteOutlined />}
          onClick={() => handleRemove(record.tool)}
          disabled={disabled}
        />
      ),
    },
  ];

  const dataSource = entries.map(([tool, action]) => ({
    key: tool,
    tool,
    action,
  }));

  return (
    <div>
      <Table
        columns={columns}
        dataSource={dataSource}
        pagination={false}
        size="small"
        style={{ marginBottom: 16 }}
      />
      {!disabled && (
        <Space.Compact style={{ width: '100%' }}>
          <Select
            style={{ flex: 1 }}
            placeholder={t('auth_select_tool', '选择工具')}
            value={newTool || undefined}
            onChange={setNewTool}
            showSearch
            allowClear
          >
            {availableTools
              .filter(t => !value[t])
              .map(tool => (
                <Option key={tool} value={tool}>{tool}</Option>
              ))}
          </Select>
          <Select
            style={{ width: 120 }}
            value={newAction}
            onChange={setNewAction}
          >
            {ACTION_OPTIONS.map(opt => (
              <Option key={opt.value} value={opt.value}>{opt.label}</Option>
            ))}
          </Select>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            {t('auth_add', '添加')}
          </Button>
        </Space.Compact>
      )}
    </div>
  );
}

export function AgentAuthorizationConfig({
  value,
  onChange,
  disabled = false,
  availableTools = [],
  showAdvanced = true,
}: AgentAuthorizationConfigProps) {
  const { t } = useTranslation();
  const config = value ?? DEFAULT_CONFIG;

  const handleChange = useCallback((field: keyof AuthorizationConfig, fieldValue: any) => {
    onChange?.({
      ...config,
      [field]: fieldValue,
    });
  }, [config, onChange]);

  const handlePresetChange = useCallback((preset: 'strict' | 'permissive' | 'unrestricted') => {
    switch (preset) {
      case 'strict':
        onChange?.(STRICT_CONFIG);
        break;
      case 'permissive':
        onChange?.(PERMISSIVE_CONFIG);
        break;
      case 'unrestricted':
        onChange?.(UNRESTRICTED_CONFIG);
        break;
    }
  }, [onChange]);

  const MODE_OPTIONS = [
    {
      value: AuthModeEnum.STRICT,
      label: t('auth_mode_strict', '严格'),
      description: t('auth_mode_strict_desc', '严格遵循工具定义，所有风险操作都需要授权'),
      icon: <LockOutlined />,
      color: 'error',
    },
    {
      value: AuthModeEnum.MODERATE,
      label: t('auth_mode_moderate', '适度'),
      description: t('auth_mode_moderate_desc', '安全与便利平衡，中风险及以上需要授权'),
      icon: <SafetyOutlined />,
      color: 'warning',
    },
    {
      value: AuthModeEnum.PERMISSIVE,
      label: t('auth_mode_permissive', '宽松'),
      description: t('auth_mode_permissive_desc', '默认允许大多数操作，仅高风险需要授权'),
      icon: <UnlockOutlined />,
      color: 'success',
    },
    {
      value: AuthModeEnum.UNRESTRICTED,
      label: t('auth_mode_unrestricted', '无限制'),
      description: t('auth_mode_unrestricted_desc', '跳过所有授权检查，请谨慎使用！'),
      icon: <WarningOutlined />,
      color: 'default',
    },
  ];

  const LLM_POLICY_OPTIONS = [
    {
      value: LLMPolicyEnum.DISABLED,
      label: t('auth_llm_disabled', '禁用'),
      description: t('auth_llm_disabled_desc', '不使用LLM判断，仅基于规则授权'),
    },
    {
      value: LLMPolicyEnum.CONSERVATIVE,
      label: t('auth_llm_conservative', '保守'),
      description: t('auth_llm_conservative_desc', 'LLM不确定时倾向于请求用户确认'),
    },
    {
      value: LLMPolicyEnum.BALANCED,
      label: t('auth_llm_balanced', '平衡'),
      description: t('auth_llm_balanced_desc', 'LLM根据上下文做出中性判断'),
    },
    {
      value: LLMPolicyEnum.AGGRESSIVE,
      label: t('auth_llm_aggressive', '激进'),
      description: t('auth_llm_aggressive_desc', 'LLM在合理安全时倾向于允许操作'),
    },
  ];

  const selectedMode = MODE_OPTIONS.find(m => m.value === config.mode);

  return (
    <div className="agent-authorization-config">
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          <Text strong>{t('auth_quick_presets', '快速预设')}:</Text>
          <Button
            size="small"
            type={config.mode === AuthModeEnum.STRICT ? 'primary' : 'default'}
            onClick={() => handlePresetChange('strict')}
            disabled={disabled}
          >
            {t('auth_mode_strict', '严格')}
          </Button>
          <Button
            size="small"
            type={config.mode === AuthModeEnum.PERMISSIVE ? 'primary' : 'default'}
            onClick={() => handlePresetChange('permissive')}
            disabled={disabled}
          >
            {t('auth_mode_permissive', '宽松')}
          </Button>
          <Button
            size="small"
            type={config.mode === AuthModeEnum.UNRESTRICTED ? 'primary' : 'default'}
            danger
            onClick={() => handlePresetChange('unrestricted')}
            disabled={disabled}
          >
            {t('auth_mode_unrestricted', '无限制')}
          </Button>
        </Space>
      </Card>

      <Form layout="vertical" disabled={disabled}>
        <Form.Item
          label={
            <Space>
              <SafetyOutlined />
              <span>{t('auth_authorization_mode', '授权模式')}</span>
            </Space>
          }
        >
          <Select
            value={config.mode}
            onChange={(v) => handleChange('mode', v)}
            style={{ width: '100%' }}
          >
            {MODE_OPTIONS.map(opt => (
              <Option key={opt.value} value={opt.value}>
                <Space>
                  {opt.icon}
                  <span>{opt.label}</span>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    - {opt.description}
                  </Text>
                </Space>
              </Option>
            ))}
          </Select>
          {selectedMode && (
            <Alert
              type={
                selectedMode.value === AuthModeEnum.UNRESTRICTED ? 'warning' :
                selectedMode.value === AuthModeEnum.STRICT ? 'info' : 'success'
              }
              message={selectedMode.description}
              showIcon
              style={{ marginTop: 8 }}
            />
          )}
        </Form.Item>

        <Form.Item
          label={
            <Space>
              <SettingOutlined />
              <span>{t('auth_llm_policy', 'LLM判断策略')}</span>
              <Tooltip title={t('auth_llm_policy_tip', '配置LLM如何辅助授权决策')}>
                <InfoCircleOutlined />
              </Tooltip>
            </Space>
          }
        >
          <Select
            value={config.llm_policy}
            onChange={(v) => handleChange('llm_policy', v)}
            style={{ width: '100%' }}
          >
            {LLM_POLICY_OPTIONS.map(opt => (
              <Option key={opt.value} value={opt.value}>
                <Space>
                  <span>{opt.label}</span>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    - {opt.description}
                  </Text>
                </Space>
              </Option>
            ))}
          </Select>
        </Form.Item>

        {config.llm_policy !== LLMPolicyEnum.DISABLED && (
          <Form.Item
            label={t('auth_custom_llm_prompt', '自定义LLM提示词（可选）')}
          >
            <Input.TextArea
              value={config.llm_prompt}
              onChange={(e) => handleChange('llm_prompt', e.target.value)}
              placeholder={t('auth_custom_llm_prompt_placeholder', '输入自定义的LLM判断提示词...')}
              rows={3}
            />
          </Form.Item>
        )}

        <Divider />

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              label={
                <Space>
                  <CheckCircleOutlined style={{ color: '#52c41a' }} />
                  <span>{t('auth_whitelist_tools', '白名单工具')}</span>
                  <Tooltip title={t('auth_whitelist_tip', '跳过授权检查的工具')}>
                    <InfoCircleOutlined />
                  </Tooltip>
                </Space>
              }
            >
              <ToolListInput
                value={config.whitelist_tools}
                onChange={(v) => handleChange('whitelist_tools', v)}
                availableTools={availableTools}
                placeholder={t('auth_select_whitelist', '选择白名单工具')}
                disabled={disabled}
                t={t}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              label={
                <Space>
                  <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                  <span>{t('auth_blacklist_tools', '黑名单工具')}</span>
                  <Tooltip title={t('auth_blacklist_tip', '始终拒绝的工具')}>
                    <InfoCircleOutlined />
                  </Tooltip>
                </Space>
              }
            >
              <ToolListInput
                value={config.blacklist_tools}
                onChange={(v) => handleChange('blacklist_tools', v)}
                availableTools={availableTools}
                placeholder={t('auth_select_blacklist', '选择黑名单工具')}
                disabled={disabled}
                t={t}
              />
            </Form.Item>
          </Col>
        </Row>

        {showAdvanced && (
          <Collapse ghost style={{ marginBottom: 16 }}>
            <Panel
              header={
                <Space>
                  <SettingOutlined />
                  <span>{t('auth_tool_overrides', '工具级别覆盖')}</span>
                </Space>
              }
              key="overrides"
            >
              <ToolOverrideEditor
                value={config.tool_overrides}
                onChange={(v) => handleChange('tool_overrides', v)}
                availableTools={availableTools}
                disabled={disabled}
                t={t}
              />
            </Panel>
          </Collapse>
        )}

        <Divider />

        <Row gutter={16}>
          <Col span={8}>
            <Form.Item
              label={
                <Space>
                  <span>{t('auth_session_cache', '会话缓存')}</span>
                  <Tooltip title={t('auth_session_cache_tip', '在会话内缓存授权决策')}>
                    <InfoCircleOutlined />
                  </Tooltip>
                </Space>
              }
            >
              <Switch
                checked={config.session_cache_enabled}
                onChange={(v) => handleChange('session_cache_enabled', v)}
              />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label={t('auth_cache_ttl', '缓存TTL (秒)')}>
              <InputNumber
                value={config.session_cache_ttl}
                onChange={(v) => handleChange('session_cache_ttl', v ?? 3600)}
                min={0}
                max={86400}
                style={{ width: '100%' }}
                disabled={!config.session_cache_enabled}
              />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label={t('auth_timeout', '授权超时 (秒)')}>
              <InputNumber
                value={config.authorization_timeout}
                onChange={(v) => handleChange('authorization_timeout', v ?? 300)}
                min={10}
                max={3600}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </div>
  );
}

export default AgentAuthorizationConfig;