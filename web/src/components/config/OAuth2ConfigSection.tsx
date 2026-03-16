'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Alert,
  Button,
  Divider,
  Form,
  Input,
  Select,
  Switch,
  Tag,
  Tooltip,
  message,
} from 'antd';
import {
  CheckCircleFilled,
  DeleteOutlined,
  EditOutlined,
  GithubOutlined,
  LockOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SafetyOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { configService, OAuth2ProviderConfig } from '@/services/config';

interface OAuth2ConfigSectionProps {
  onChange?: () => void;
}

const PROVIDER_TYPE_OPTIONS = [
  {
    value: 'github',
    label: (
      <span className="flex items-center gap-2">
        <GithubOutlined /> GitHub
      </span>
    ),
  },
  { value: 'custom', label: <span>自定义 OAuth2</span> },
];

/** Masked display of a secret */
function MaskedValue({ value }: { value?: string }) {
  if (!value) return <span className="text-gray-300 italic text-sm">未填写</span>;
  const head = value.slice(0, 4);
  return (
    <span className="font-mono text-sm text-gray-600">
      {head}{'•'.repeat(Math.min(value.length - 4, 20))}
    </span>
  );
}

/** Single read-only row */
function ReadRow({ label, children }: { label: string; children?: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-1.5">
      <span className="text-xs text-gray-400 w-28 flex-shrink-0 pt-0.5">{label}</span>
      <span className="flex-1 text-sm text-gray-700 break-all">
        {children || <span className="text-gray-300">—</span>}
      </span>
    </div>
  );
}

interface ProviderCardProps {
  /** Form.List index */
  name: number;
  restField: Record<string, any>;
  canRemove: boolean;
  isEditing: boolean;
  onEdit: () => void;
  onDone: () => void;
  onRemove: () => void;
  form: ReturnType<typeof Form.useForm>[0];
}

function ProviderCard({
  name,
  restField,
  canRemove,
  isEditing,
  onEdit,
  onDone,
  onRemove,
  form,
}: ProviderCardProps) {
  // Read current field values for the read-only view
  const providerType: string =
    Form.useWatch(['providers', name, 'provider_type'], form) || 'github';
  const clientId: string = Form.useWatch(['providers', name, 'client_id'], form) || '';
  const clientSecret: string = Form.useWatch(['providers', name, 'client_secret'], form) || '';
  const customId: string = Form.useWatch(['providers', name, 'custom_id'], form) || '';
  const authUrl: string = Form.useWatch(['providers', name, 'authorization_url'], form) || '';
  const tokenUrl: string = Form.useWatch(['providers', name, 'token_url'], form) || '';
  const userinfoUrl: string = Form.useWatch(['providers', name, 'userinfo_url'], form) || '';
  const scope: string = Form.useWatch(['providers', name, 'scope'], form) || '';

  const isGitHub = providerType === 'github';
  const isConfigured = !!clientId && !!clientSecret;

  const handleDone = () => {
    if (!clientId || !clientSecret) {
      message.warning('请先填写 Client ID 和 Client Secret');
      return;
    }
    onDone();
  };

  const cardLabel = isGitHub
    ? 'GitHub OAuth2'
    : `自定义 OAuth2${customId ? ` · ${customId}` : ''}`;

  return (
    <div
      className={`rounded-xl border mb-3 overflow-hidden transition-all duration-200 ${
        isEditing
          ? 'border-blue-300 shadow-sm bg-white'
          : isConfigured
          ? 'border-gray-200 bg-gray-50'
          : 'border-dashed border-orange-300 bg-orange-50/30'
      }`}
    >
      {/* ── Header ── */}
      <div
        className={`flex items-center justify-between px-4 py-2.5 border-b ${
          isEditing
            ? 'bg-blue-50 border-blue-100'
            : isConfigured
            ? 'bg-white border-gray-100'
            : 'bg-orange-50/50 border-orange-100'
        }`}
      >
        <div className="flex items-center gap-2">
          {isGitHub ? (
            <GithubOutlined className="text-gray-700" />
          ) : (
            <SafetyOutlined className="text-blue-500" />
          )}
          <span className="text-sm font-medium text-gray-700">{cardLabel}</span>
          {!isEditing && isConfigured && (
            <Tag color="success" icon={<CheckCircleFilled />} className="text-xs ml-1">
              已配置
            </Tag>
          )}
          {!isEditing && !isConfigured && (
            <Tag color="warning" icon={<WarningOutlined />} className="text-xs ml-1">
              未完成
            </Tag>
          )}
          {isEditing && (
            <Tag color="processing" className="text-xs ml-1">
              编辑中
            </Tag>
          )}
        </div>

        <div className="flex items-center gap-1">
          {!isEditing && (
            <Button
              size="small"
              icon={<EditOutlined />}
              type="text"
              className="text-gray-500 hover:text-blue-500"
              onClick={onEdit}
            >
              编辑
            </Button>
          )}
          {isEditing && (
            <Button
              size="small"
              icon={<LockOutlined />}
              type="text"
              className="text-blue-500"
              onClick={handleDone}
            >
              完成
            </Button>
          )}
          {canRemove && (
            <Button
              size="small"
              icon={<DeleteOutlined />}
              type="text"
              danger
              onClick={onRemove}
            />
          )}
        </div>
      </div>

      {/* ── Body ── */}
      <div className="px-4 py-3">
        {/* Read-only view */}
        {!isEditing && (
          <div className="divide-y divide-gray-100">
            <ReadRow label="提供商类型">
              {isGitHub ? (
                <span className="flex items-center gap-1.5">
                  <GithubOutlined /> GitHub
                </span>
              ) : (
                '自定义 OAuth2'
              )}
            </ReadRow>
            {!isGitHub && customId && <ReadRow label="提供商 ID">{customId}</ReadRow>}
            <ReadRow label="Client ID">
              <span className="font-mono text-sm">{clientId || <span className="text-gray-300 italic">未填写</span>}</span>
            </ReadRow>
            <ReadRow label="Client Secret">
              <MaskedValue value={clientSecret} />
            </ReadRow>
            {!isGitHub && authUrl && <ReadRow label="Authorization URL">{authUrl}</ReadRow>}
            {!isGitHub && tokenUrl && <ReadRow label="Token URL">{tokenUrl}</ReadRow>}
            {!isGitHub && userinfoUrl && <ReadRow label="Userinfo URL">{userinfoUrl}</ReadRow>}
            {!isGitHub && scope && <ReadRow label="Scope">{scope}</ReadRow>}
          </div>
        )}

        {/* Edit form */}
        {isEditing && (
          <>
            <Form.Item
              {...restField}
              name={[name, 'provider_type']}
              label="提供商类型"
              rules={[{ required: true, message: '请选择提供商类型' }]}
              className="mb-3"
            >
              <Select options={PROVIDER_TYPE_OPTIONS} />
            </Form.Item>

            {!isGitHub && (
              <Form.Item
                {...restField}
                name={[name, 'custom_id']}
                label={
                  <span>
                    提供商 ID{' '}
                    <Tooltip title="内部标识，建议英文小写，如 gitlab、okta、keycloak">
                      <QuestionCircleOutlined className="text-gray-400" />
                    </Tooltip>
                  </span>
                }
                rules={[{ required: true, message: '请填写提供商 ID' }]}
                className="mb-3"
              >
                <Input placeholder="gitlab / okta / keycloak" />
              </Form.Item>
            )}

            <Form.Item
              {...restField}
              name={[name, 'client_id']}
              label="Client ID"
              rules={[{ required: true, message: '请填写 Client ID' }]}
              className="mb-3"
            >
              <Input
                placeholder={isGitHub ? 'GitHub OAuth App Client ID' : 'OAuth2 Client ID'}
              />
            </Form.Item>

            <Form.Item
              {...restField}
              name={[name, 'client_secret']}
              label="Client Secret"
              className={isGitHub ? 'mb-0' : 'mb-3'}
            >
              <Input.Password
                placeholder={isGitHub ? 'GitHub OAuth App Client Secret' : 'OAuth2 Client Secret'}
              />
            </Form.Item>

            {!isGitHub && (
              <>
                <Divider orientation="left" className="my-3 text-xs text-gray-400">
                  端点配置
                </Divider>
                <Form.Item
                  {...restField}
                  name={[name, 'authorization_url']}
                  label="Authorization URL"
                  rules={[{ required: true, message: '请填写授权 URL' }]}
                  className="mb-3"
                >
                  <Input placeholder="https://provider.com/oauth/authorize" />
                </Form.Item>
                <Form.Item
                  {...restField}
                  name={[name, 'token_url']}
                  label="Token URL"
                  rules={[{ required: true, message: '请填写 Token URL' }]}
                  className="mb-3"
                >
                  <Input placeholder="https://provider.com/oauth/token" />
                </Form.Item>
                <Form.Item
                  {...restField}
                  name={[name, 'userinfo_url']}
                  label="Userinfo URL"
                  rules={[{ required: true, message: '请填写 Userinfo URL' }]}
                  className="mb-3"
                >
                  <Input placeholder="https://provider.com/api/user" />
                </Form.Item>
                <Form.Item
                  {...restField}
                  name={[name, 'scope']}
                  label="Scope"
                  className="mb-0"
                >
                  <Input placeholder="openid profile email" />
                </Form.Item>
              </>
            )}

            {isGitHub && (
              <Alert
                type="info"
                showIcon
                className="mt-3"
                message={
                  <span className="text-xs">
                    在 GitHub → Settings → Developer settings → OAuth Apps 创建应用，
                    Authorization callback URL 填写：
                    <code className="bg-blue-50 px-1 mx-1 rounded text-xs">
                      http://your-host/api/v1/auth/oauth/callback
                    </code>
                  </span>
                }
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function OAuth2ConfigSection({ onChange }: OAuth2ConfigSectionProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  /** Set of Form.List indices currently in edit mode */
  const [editingSet, setEditingSet] = useState<Set<number>>(new Set());
  const [form] = Form.useForm();
  // Use useWatch instead of Form.Item shouldUpdate to avoid breaking form submission
  const oauthEnabled: boolean = Form.useWatch('enabled', form) ?? false;

  const setEditing = useCallback((idx: number, value: boolean) => {
    setEditingSet((prev) => {
      const next = new Set(prev);
      value ? next.add(idx) : next.delete(idx);
      return next;
    });
  }, []);

  useEffect(() => {
    loadOAuth2Config();
  }, []);

  const loadOAuth2Config = async () => {
    setLoading(true);
    try {
      const data = await configService.getOAuth2Config();
      const providers =
        data.providers?.length
          ? data.providers.map((p) => ({
              provider_type: p.type || 'github',
              custom_id: p.type !== 'github' ? p.id : undefined,
              client_id: p.client_id,
              client_secret: p.client_secret,
              authorization_url: p.authorization_url,
              token_url: p.token_url,
              userinfo_url: p.userinfo_url,
              scope: p.scope,
            }))
          : [{ provider_type: 'github', client_id: '', client_secret: '' }];

      form.setFieldsValue({
        enabled: data.enabled,
        providers,
        admin_users_text: (data.admin_users || []).join(', '),
      });

      // Loaded providers with missing credentials start in edit mode; others lock
      const initialEditing = new Set<number>();
      providers.forEach((p, i) => {
        if (!p.client_id || !p.client_secret) initialEditing.add(i);
      });
      setEditingSet(initialEditing);
    } catch (error: any) {
      message.error('加载 OAuth2 配置失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (values: any) => {
    setSaving(true);
    try {
      const providers: OAuth2ProviderConfig[] = (values.providers || [])
        .map((p: any) => ({
          id: p.provider_type === 'github' ? 'github' : (p.custom_id || 'custom'),
          type: p.provider_type || 'github',
          client_id: p.client_id || '',
          client_secret: p.client_secret || '',
          authorization_url: p.authorization_url,
          token_url: p.token_url,
          userinfo_url: p.userinfo_url,
          scope: p.scope,
        }))
        .filter((p: OAuth2ProviderConfig) => p.client_id);

      const admin_users = (values.admin_users_text || '')
        .split(',')
        .map((s: string) => s.trim())
        .filter(Boolean);

      await configService.updateOAuth2Config({
        enabled: !!values.enabled,
        providers,
        admin_users,
      });
      message.success('OAuth2 配置已保存');
      try { await loadOAuth2Config(); } catch { /* ignore */ }
      onChange?.();
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Form form={form} layout="vertical" onFinish={handleSave} initialValues={{ enabled: false }}>
      {/* 总开关 */}
      <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl border border-gray-200 mb-5">
        <div>
          <div className="font-medium text-gray-800 text-sm">启用 OAuth2 登录</div>
          <div className="text-xs text-gray-500 mt-0.5">
            开启后访问系统需要通过 OAuth2 登录鉴权，对整个平台生效
          </div>
        </div>
        <Form.Item name="enabled" valuePropName="checked" className="mb-0">
          <Switch checkedChildren="已开启" unCheckedChildren="已关闭" loading={loading} />
        </Form.Item>
      </div>

      {oauthEnabled ? (
        <>
          <Form.Item
            name="admin_users_text"
            label={
              <span>
                初始管理员{' '}
                <Tooltip title="填写 OAuth 登录后的用户名（如 GitHub login），首次登录自动获得管理员角色，已登录用户角色不变">
                  <QuestionCircleOutlined className="text-gray-400" />
                </Tooltip>
              </span>
            }
            className="mb-5"
          >
            <Input placeholder="user1, user2, user3（逗号分隔 GitHub 用户名）" />
          </Form.Item>

          <div className="text-sm font-medium text-gray-700 mb-2">登录提供商</div>
          <Form.List name="providers">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <ProviderCard
                    key={key}
                    name={name}
                    restField={restField}
                    canRemove={fields.length > 1}
                    isEditing={editingSet.has(name)}
                    onEdit={() => setEditing(name, true)}
                    onDone={() => setEditing(name, false)}
                    onRemove={() => {
                      remove(name);
                      setEditing(name, false);
                    }}
                    form={form}
                  />
                ))}
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={() => {
                    const newIdx = fields.length;
                    add({ provider_type: 'custom', client_id: '', client_secret: '' });
                    setEditing(newIdx, true);
                  }}
                  block
                  className="mb-5"
                >
                  添加提供商
                </Button>
              </>
            )}
          </Form.List>
        </>
      ) : (
        <div className="text-sm text-gray-400 mb-5">
          关闭时系统无需登录，使用默认匿名用户访问。
        </div>
      )}

      <Button type="primary" htmlType="submit" loading={saving}>
        保存配置
      </Button>
    </Form>
  );
}
