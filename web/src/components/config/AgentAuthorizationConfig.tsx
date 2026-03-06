/**
 * AgentAuthorizationConfig - Authorization Configuration Panel
 *
 * Provides UI for configuring authorization settings for agents:
 * - Authorization mode selection (strict, moderate, permissive, unrestricted)
 * - LLM judgment policy configuration
 * - Tool whitelist/blacklist management
 * - Permission rule management
 * - Session cache settings
 */

'use client';

import React, { useState, useCallback, useMemo } from 'react';
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
  Modal,
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
  EditOutlined,
  LockOutlined,
  UnlockOutlined,
  SafetyOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  SettingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import type {
  AuthorizationConfig,
  AuthorizationMode,
  LLMJudgmentPolicy,
  PermissionRule,
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

const { Text, Title, Paragraph } = Typography;
const { Option } = Select;
const { Panel } = Collapse;

// ========== Types ==========

export interface AgentAuthorizationConfigProps {
  /** Current configuration */
  value?: AuthorizationConfig;
  /** Callback when configuration changes */
  onChange?: (config: AuthorizationConfig) => void;
  /** Whether the form is disabled */
  disabled?: boolean;
  /** Available tools for whitelist/blacklist selection */
  availableTools?: string[];
  /** Show advanced options */
  showAdvanced?: boolean;
}

// ========== Constants ==========

const MODE_OPTIONS = [
  {
    value: AuthModeEnum.STRICT,
    label: 'Strict',
    description: 'Follow tool definitions strictly. All risk operations require authorization.',
    icon: <LockOutlined />,
    color: 'error',
  },
  {
    value: AuthModeEnum.MODERATE,
    label: 'Moderate',
    description: 'Balance between security and convenience. Medium risk and above require authorization.',
    icon: <SafetyOutlined />,
    color: 'warning',
  },
  {
    value: AuthModeEnum.PERMISSIVE,
    label: 'Permissive',
    description: 'Default allow most operations. Only high risk operations require authorization.',
    icon: <UnlockOutlined />,
    color: 'success',
  },
  {
    value: AuthModeEnum.UNRESTRICTED,
    label: 'Unrestricted',
    description: 'Skip all authorization checks. Use with caution!',
    icon: <WarningOutlined />,
    color: 'default',
  },
];

const LLM_POLICY_OPTIONS = [
  {
    value: LLMPolicyEnum.DISABLED,
    label: 'Disabled',
    description: 'No LLM judgment. Use rule-based authorization only.',
  },
  {
    value: LLMPolicyEnum.CONSERVATIVE,
    label: 'Conservative',
    description: 'LLM tends to request user confirmation when uncertain.',
  },
  {
    value: LLMPolicyEnum.BALANCED,
    label: 'Balanced',
    description: 'LLM makes neutral judgment based on context.',
  },
  {
    value: LLMPolicyEnum.AGGRESSIVE,
    label: 'Aggressive',
    description: 'LLM tends to allow operations when reasonably safe.',
  },
];

const ACTION_OPTIONS = [
  { value: PermActionEnum.ALLOW, label: 'Allow', color: 'success' },
  { value: PermActionEnum.DENY, label: 'Deny', color: 'error' },
  { value: PermActionEnum.ASK, label: 'Ask', color: 'warning' },
];

// ========== Default Config ==========

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

// ========== Sub-Components ==========

/**
 * Tool List Input Component
 */
function ToolListInput({
  value = [],
  onChange,
  availableTools = [],
  placeholder,
  disabled,
}: {
  value?: string[];
  onChange?: (tools: string[]) => void;
  availableTools?: string[];
  placeholder?: string;
  disabled?: boolean;
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
            Add
          </Button>
        </Space.Compact>
      )}
    </div>
  );
}

/**
 * Tool Override Editor Component
 */
function ToolOverrideEditor({
  value = {},
  onChange,
  availableTools = [],
  disabled,
}: {
  value?: Record<string, PermissionAction>;
  onChange?: (overrides: Record<string, PermissionAction>) => void;
  availableTools?: string[];
  disabled?: boolean;
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

  const columns = [
    {
      title: 'Tool',
      dataIndex: 'tool',
      key: 'tool',
    },
    {
      title: 'Action',
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
      title: 'Actions',
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
            placeholder="Select tool"
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
            Add
          </Button>
        </Space.Compact>
      )}
    </div>
  );
}

// ========== Main Component ==========

export function AgentAuthorizationConfig({
  value,
  onChange,
  disabled = false,
  availableTools = [],
  showAdvanced = true,
}: AgentAuthorizationConfigProps) {
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

  const selectedMode = MODE_OPTIONS.find(m => m.value === config.mode);

  return (
    <div className="agent-authorization-config">
      {/* Preset Buttons */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          <Text strong>Quick Presets:</Text>
          <Button
            size="small"
            type={config.mode === AuthModeEnum.STRICT ? 'primary' : 'default'}
            onClick={() => handlePresetChange('strict')}
            disabled={disabled}
          >
            Strict
          </Button>
          <Button
            size="small"
            type={config.mode === AuthModeEnum.PERMISSIVE ? 'primary' : 'default'}
            onClick={() => handlePresetChange('permissive')}
            disabled={disabled}
          >
            Permissive
          </Button>
          <Button
            size="small"
            type={config.mode === AuthModeEnum.UNRESTRICTED ? 'primary' : 'default'}
            danger
            onClick={() => handlePresetChange('unrestricted')}
            disabled={disabled}
          >
            Unrestricted
          </Button>
        </Space>
      </Card>

      <Form layout="vertical" disabled={disabled}>
        {/* Authorization Mode */}
        <Form.Item
          label={
            <Space>
              <SafetyOutlined />
              <span>Authorization Mode</span>
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

        {/* LLM Judgment Policy */}
        <Form.Item
          label={
            <Space>
              <SettingOutlined />
              <span>LLM Judgment Policy</span>
              <Tooltip title="Configure how LLM assists in authorization decisions">
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

        {/* Custom LLM Prompt */}
        {config.llm_policy !== LLMPolicyEnum.DISABLED && (
          <Form.Item
            label="Custom LLM Prompt (Optional)"
          >
            <Input.TextArea
              value={config.llm_prompt}
              onChange={(e) => handleChange('llm_prompt', e.target.value)}
              placeholder="Enter custom prompt for LLM judgment..."
              rows={3}
            />
          </Form.Item>
        )}

        <Divider />

        {/* Whitelist/Blacklist */}
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              label={
                <Space>
                  <CheckCircleOutlined style={{ color: '#52c41a' }} />
                  <span>Whitelist Tools</span>
                  <Tooltip title="Tools that skip authorization checks">
                    <InfoCircleOutlined />
                  </Tooltip>
                </Space>
              }
            >
              <ToolListInput
                value={config.whitelist_tools}
                onChange={(v) => handleChange('whitelist_tools', v)}
                availableTools={availableTools}
                placeholder="Select tool to whitelist"
                disabled={disabled}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              label={
                <Space>
                  <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                  <span>Blacklist Tools</span>
                  <Tooltip title="Tools that are always denied">
                    <InfoCircleOutlined />
                  </Tooltip>
                </Space>
              }
            >
              <ToolListInput
                value={config.blacklist_tools}
                onChange={(v) => handleChange('blacklist_tools', v)}
                availableTools={availableTools}
                placeholder="Select tool to blacklist"
                disabled={disabled}
              />
            </Form.Item>
          </Col>
        </Row>

        {/* Tool Overrides */}
        {showAdvanced && (
          <Collapse ghost style={{ marginBottom: 16 }}>
            <Panel
              header={
                <Space>
                  <SettingOutlined />
                  <span>Tool-Level Overrides</span>
                </Space>
              }
              key="overrides"
            >
              <ToolOverrideEditor
                value={config.tool_overrides}
                onChange={(v) => handleChange('tool_overrides', v)}
                availableTools={availableTools}
                disabled={disabled}
              />
            </Panel>
          </Collapse>
        )}

        <Divider />

        {/* Session Cache Settings */}
        <Row gutter={16}>
          <Col span={8}>
            <Form.Item
              label={
                <Space>
                  <span>Session Cache</span>
                  <Tooltip title="Cache authorization decisions within a session">
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
            <Form.Item label="Cache TTL (seconds)">
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
            <Form.Item label="Authorization Timeout (seconds)">
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
