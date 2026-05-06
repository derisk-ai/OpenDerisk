'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  SafetyOutlined,
  CopyOutlined,
  AppstoreOutlined,
  AimOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ins as axios } from '@/client/api';
import { permissionsService, type Role, type Permission, type PermissionDefinition } from '@/services/permissions';

const { Text } = Typography;

const RESOURCE_PICKER_TYPES = ['agent', 'tool', 'knowledge', 'model'] as const;

interface CustomPolicy {
  id?: number;
  name: string;
  description: string;
  resource_type: string;
  resource_id: string;
  action: string;
  effect: string;
  role_id?: number;
  role_name?: string;
  gmt_create?: string | null;
  source: 'role_permission' | 'permission_definition';
}

interface PresetTemplateDef {
  name: string;
  labelKey: string;
  descKey: string;
  resource_type: string;
  resource_id: string;
  action: string;
  effect: string;
}

const PRESET_TEMPLATE_DEFS: PresetTemplateDef[] = [
  {
    name: 'agent_readonly',
    labelKey: 'permissions_tpl_agent_readonly',
    descKey: 'permissions_tpl_agent_readonly_desc',
    resource_type: 'agent',
    resource_id: '*',
    action: 'read',
    effect: 'allow',
  },
  {
    name: 'agent_chat',
    labelKey: 'permissions_tpl_agent_chat',
    descKey: 'permissions_tpl_agent_chat_desc',
    resource_type: 'agent',
    resource_id: '*',
    action: 'chat',
    effect: 'allow',
  },
  {
    name: 'tool_execute',
    labelKey: 'permissions_tpl_tool_execute',
    descKey: 'permissions_tpl_tool_execute_desc',
    resource_type: 'tool',
    resource_id: '*',
    action: 'execute',
    effect: 'allow',
  },
  {
    name: 'knowledge_query',
    labelKey: 'permissions_tpl_knowledge_query',
    descKey: 'permissions_tpl_knowledge_query_desc',
    resource_type: 'knowledge',
    resource_id: '*',
    action: 'query',
    effect: 'allow',
  },
  {
    name: 'model_chat',
    labelKey: 'permissions_tpl_model_chat',
    descKey: 'permissions_tpl_model_chat_desc',
    resource_type: 'model',
    resource_id: '*',
    action: 'chat',
    effect: 'allow',
  },
  {
    name: 'system_readonly',
    labelKey: 'permissions_tpl_system_readonly',
    descKey: 'permissions_tpl_system_readonly_desc',
    resource_type: 'system',
    resource_id: '*',
    action: 'read',
    effect: 'allow',
  },
];

async function loadOptionsForResourceType(
  resourceType: string,
): Promise<{ value: string; label: string }[]> {
  let resources: Array<{ name?: string; displayName?: string; id?: string | number }> = [];
  try {
    switch (resourceType) {
      case 'agent': {
        const res = await axios.get('/api/v1/config/agents');
        resources = res.data?.data?.list || res.data?.data || [];
        break;
      }
      case 'tool': {
        const res = await axios.get('/api/v1/tools/list');
        resources = res.data?.data?.list || res.data?.data || [];
        break;
      }
      case 'knowledge': {
        const res = await axios.get('/api/v1/knowledge/space/list');
        resources = res.data?.data?.list || res.data?.data || [];
        break;
      }
      case 'model': {
        const res = await axios.get('/api/v1/serve/model/models');
        resources = res.data?.data?.list || res.data?.data || [];
        break;
      }
      default:
        return [];
    }
  } catch {
    return [];
  }

  return resources
    .map((item) => {
      const label =
        item.displayName != null && item.displayName !== ''
          ? String(item.displayName)
          : item.name != null && item.name !== ''
            ? String(item.name)
            : String(item.id ?? '');
      const value = item.name != null && item.name !== '' ? String(item.name) : String(item.id ?? '');
      return { value, label: label || value };
    })
    .filter((o) => o.value);
}

function isPresetScope(resourceId: string | undefined): boolean {
  return resourceId === undefined || resourceId === '' || resourceId === '*';
}

function findMatchingPreset(
  resourceType: string,
  action: string,
  resourceId: string,
): PresetTemplateDef | undefined {
  if (!isPresetScope(resourceId)) return undefined;
  return PRESET_TEMPLATE_DEFS.find(
    (p) => p.resource_type === resourceType && p.action === action && p.resource_id === '*',
  );
}

interface CustomPermissionsProps {
  roles?: Role[];
}

export default function CustomPermissions({ roles: externalRoles }: CustomPermissionsProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [policies, setPolicies] = useState<CustomPolicy[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [createKind, setCreateKind] = useState<'role_permission' | 'permission_definition'>('role_permission');
  const [selectedPolicy, setSelectedPolicy] = useState<CustomPolicy | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [selectedResourceType, setSelectedResourceType] = useState<string>('agent');
  const [search, setSearch] = useState('');
  const [resourceIdOptions, setResourceIdOptions] = useState<{ value: string; label: string }[]>([]);
  const [resourceIdsLoading, setResourceIdsLoading] = useState(false);

  const resourceTypeOptions = useMemo(
    () => [
      { value: 'agent', label: t('permissions_resource_agent') },
      { value: 'tool', label: t('permissions_resource_tool') },
      { value: 'knowledge', label: t('permissions_resource_knowledge') },
      { value: 'model', label: t('permissions_resource_model') },
      { value: 'system', label: t('permissions_resource_system') },
      { value: '*', label: t('permissions_resource_wildcard') },
    ],
    [t],
  );

  const actionOptionsMap = useMemo(
    () => ({
      agent: [
        { value: 'read', label: t('permissions_action_read') },
        { value: 'chat', label: t('permissions_action_chat') },
        { value: 'write', label: t('permissions_action_write') },
        { value: 'admin', label: t('permissions_action_admin') },
        { value: '*', label: t('permissions_action_all') },
      ],
      tool: [
        { value: 'read', label: t('permissions_action_read') },
        { value: 'execute', label: t('permissions_action_execute') },
        { value: 'manage', label: t('permissions_action_manage') },
        { value: 'admin', label: t('permissions_action_admin') },
        { value: '*', label: t('permissions_action_all') },
      ],
      knowledge: [
        { value: 'read', label: t('permissions_action_read') },
        { value: 'query', label: t('permissions_action_query') },
        { value: 'write', label: t('permissions_action_write') },
        { value: 'admin', label: t('permissions_action_admin') },
        { value: '*', label: t('permissions_action_all') },
      ],
      model: [
        { value: 'read', label: t('permissions_action_read') },
        { value: 'chat', label: t('permissions_action_chat') },
        { value: 'manage', label: t('permissions_action_manage') },
        { value: 'admin', label: t('permissions_action_admin') },
        { value: '*', label: t('permissions_action_all') },
      ],
      system: [
        { value: 'read', label: t('permissions_action_read') },
        { value: 'write', label: t('permissions_action_write') },
        { value: 'admin', label: t('permissions_action_admin') },
        { value: '*', label: t('permissions_action_all') },
      ],
      '*': [
        { value: 'read', label: t('permissions_action_read') },
        { value: 'write', label: t('permissions_action_write') },
        { value: 'admin', label: t('permissions_action_admin') },
        { value: '*', label: t('permissions_action_all') },
      ],
    }),
    [t],
  );

  const loadRoles = useCallback(async () => {
    if (externalRoles) {
      setRoles(externalRoles);
      return;
    }
    try {
      const rolesData = await permissionsService.listRoles();
      setRoles(rolesData);
    } catch (e: unknown) {
      message.error(t('permissions_load_roles_error') + ': ' + (e as Error).message);
    }
  }, [t, externalRoles]);

  const policyFromPermission = useCallback(
    (p: Permission, roleList: Role[]): CustomPolicy => {
      const role = roleList.find((r) => r.id === p.role_id);
      const preset = findMatchingPreset(p.resource_type, p.action, p.resource_id);
      const name = preset
        ? t(preset.labelKey)
        : `${p.resource_type}_${p.action}_${isPresetScope(p.resource_id) ? 'all' : p.resource_id}`;
      const description = preset
        ? t(preset.descKey)
        : `${p.resource_type} / ${p.resource_id} / ${p.action}`;
      return {
        id: p.id,
        name,
        description,
        resource_type: p.resource_type,
        resource_id: p.resource_id,
        action: p.action,
        effect: p.effect,
        role_id: p.role_id,
        role_name: role?.name,
        gmt_create: p.gmt_create,
        source: 'role_permission',
      };
    },
    [t],
  );

  const policyFromDefinition = useCallback(
    (def: PermissionDefinition): CustomPolicy => {
      const preset = findMatchingPreset(def.resource_type, def.action, def.resource_id);
      const name = def.name || (preset
        ? t(preset.labelKey)
        : `${def.resource_type}_${def.action}_${isPresetScope(def.resource_id) ? 'all' : def.resource_id}`);
      const description = def.description || (preset
        ? t(preset.descKey)
        : `${def.resource_type} / ${def.resource_id} / ${def.action}`);
      return {
        id: def.id,
        name,
        description,
        resource_type: def.resource_type,
        resource_id: def.resource_id,
        action: def.action,
        effect: def.effect,
        role_id: undefined,
        role_name: undefined,
        gmt_create: def.gmt_create,
        source: 'permission_definition',
      };
    },
    [t],
  );

  const loadPolicies = useCallback(async () => {
    if (roles.length === 0) return;
    setLoading(true);
    try {
      // Load both scoped permissions and permission definitions
      const [perms, defs] = await Promise.all([
        permissionsService.listScopedPermissions({}),
        permissionsService.listPermissionDefinitions({}),
      ]);
      const permRows = perms.map((p) => policyFromPermission(p, roles));
      const defRows = defs.map((d) => policyFromDefinition(d));
      setPolicies([...permRows, ...defRows]);
    } catch (e: unknown) {
      message.error(t('permissions_load_error') + ': ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [t, roles, policyFromPermission, policyFromDefinition]);

  useEffect(() => {
    loadRoles();
  }, [loadRoles, externalRoles]);

  useEffect(() => {
    if (roles.length > 0) {
      loadPolicies();
    }
  }, [loadPolicies, roles]);

  useEffect(() => {
    if (!createOpen && !editOpen) return;
    const rt = selectedResourceType;
    if (!RESOURCE_PICKER_TYPES.includes(rt as (typeof RESOURCE_PICKER_TYPES)[number])) {
      setResourceIdOptions([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setResourceIdsLoading(true);
      const opts = await loadOptionsForResourceType(rt);
      if (!cancelled) {
        setResourceIdOptions(opts);
      }
      if (!cancelled) {
        setResourceIdsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedResourceType, createOpen, editOpen]);

  const presetPolicies = useMemo(
    () => policies.filter((p) => isPresetScope(p.resource_id)),
    [policies],
  );
  const customPolicies = useMemo(
    () => policies.filter((p) => !isPresetScope(p.resource_id)),
    [policies],
  );

  const filterPoliciesBySearch = useCallback(
    (list: CustomPolicy[]) => {
      const q = search.trim().toLowerCase();
      if (!q) return list;
      return list.filter((p) => {
        const typeLabel = resourceTypeOptions.find((o) => o.value === p.resource_type)?.label ?? '';
        const actions =
          actionOptionsMap[p.resource_type as keyof typeof actionOptionsMap] || actionOptionsMap['*'];
        const actionLabel = actions.find((a) => a.value === p.action)?.label ?? '';
        const blob = [
          p.name,
          p.description,
          p.resource_type,
          p.resource_id,
          p.action,
          p.role_name ?? '',
          typeLabel,
          actionLabel,
        ]
          .join(' ')
          .toLowerCase();
        return blob.includes(q);
      });
    },
    [search, resourceTypeOptions, actionOptionsMap],
  );

  const filteredPreset = useMemo(
    () => filterPoliciesBySearch(presetPolicies),
    [presetPolicies, filterPoliciesBySearch],
  );
  const filteredCustom = useMemo(
    () => filterPoliciesBySearch(customPolicies),
    [customPolicies, filterPoliciesBySearch],
  );

  function getResourceTypeLabel(type: string) {
    const option = resourceTypeOptions.find((o) => o.value === type);
    return option?.label || type;
  }

  function getActionLabel(resourceType: string, action: string) {
    const actions = actionOptionsMap[resourceType as keyof typeof actionOptionsMap] || actionOptionsMap['*'];
    const option = actions.find((a) => a.value === action);
    return option?.label || action;
  }

  const openCreateCustom = (kind: 'role_permission' | 'permission_definition' = 'role_permission') => {
    setCreateKind(kind);
    setSelectedResourceType('agent');
    createForm.resetFields();
    createForm.setFieldsValue({
      kind,
      resource_type: 'agent',
      resource_id: kind === 'role_permission' ? undefined : '*',
      effect: 'allow',
    });
    setCreateOpen(true);
  };

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      const kind = values.kind as 'role_permission' | 'permission_definition';
      const rid = String(values.resource_id ?? '').trim() || '*';

      if (kind === 'permission_definition') {
        const definitionName = String(values.name ?? '').trim();
        if (!definitionName) {
          message.warning(t('permissions_name_required'));
          return;
        }
        await permissionsService.createPermissionDefinition({
          name: definitionName,
          description: values.description,
          resource_type: values.resource_type,
          resource_id: rid,
          action: values.action,
          effect: values.effect || 'allow',
        });
        message.success(t('permissions_definition_created'));
      } else if (values.role_id) {
        await permissionsService.grantScopedPermission({
          role_id: values.role_id,
          resource_type: values.resource_type,
          resource_id: rid,
          action: values.action,
          effect: values.effect || 'allow',
        });
        message.success(t('permissions_permission_added'));
      } else {
        message.warning(t('permissions_role_pick_required'));
        return;
      }
      setCreateOpen(false);
      createForm.resetFields();
      await loadPolicies();
    } catch (e: unknown) {
      if ((e as { errorFields?: unknown })?.errorFields) return;
      message.error(t('permissions_add_permission_error') + ': ' + (e as Error).message);
    }
  };

  const handleEdit = async () => {
    if (!selectedPolicy) return;
    try {
      const values = await editForm.validateFields();
      const rid = String(values.resource_id ?? '').trim() || '*';
      if (selectedPolicy.source === 'permission_definition') {
        if (!selectedPolicy.id) return;
        await permissionsService.updatePermissionDefinition(selectedPolicy.id, {
          name: String(values.name ?? '').trim(),
          description: values.description,
          resource_type: values.resource_type,
          resource_id: rid,
          action: values.action,
          effect: values.effect || 'allow',
        });
      } else {
        if (selectedPolicy.id && selectedPolicy.role_id) {
          await permissionsService.removeRolePermission(selectedPolicy.role_id, selectedPolicy.id);
        }
        await permissionsService.grantScopedPermission({
          role_id: values.role_id,
          resource_type: values.resource_type,
          resource_id: rid,
          action: values.action,
          effect: values.effect || 'allow',
        });
      }
      message.success(t('permissions_role_updated'));
      setEditOpen(false);
      editForm.resetFields();
      await loadPolicies();
    } catch (e: unknown) {
      if ((e as { errorFields?: unknown })?.errorFields) return;
      message.error(t('permissions_update_error') + ': ' + (e as Error).message);
    }
  };

  const handleDelete = async (policy: CustomPolicy) => {
    if (!policy.id) return;
    try {
      if (policy.source === 'permission_definition') {
        await permissionsService.deletePermissionDefinition(policy.id);
        message.success(t('permissions_definition_deleted'));
      } else if (policy.role_id) {
        await permissionsService.removeRolePermission(policy.role_id, policy.id);
        message.success(t('permissions_permission_removed'));
      }
      await loadPolicies();
    } catch (e: unknown) {
      message.error(t('permissions_remove_permission_error') + ': ' + (e as Error).message);
    }
  };

  const openEdit = (policy: CustomPolicy) => {
    setSelectedPolicy(policy);
    setSelectedResourceType(policy.resource_type);
    editForm.setFieldsValue({
      kind: policy.source,
      name: policy.source === 'permission_definition' ? policy.name : undefined,
      description: policy.source === 'permission_definition' ? policy.description : undefined,
      resource_type: policy.resource_type,
      resource_id: policy.resource_id,
      action: policy.action,
      effect: policy.effect,
      role_id: policy.role_id,
    });
    setEditOpen(true);
  };

  const applyTemplate = (template: PresetTemplateDef) => {
    setCreateKind('role_permission');
    setSelectedResourceType(template.resource_type);
    createForm.setFieldsValue({
      kind: 'role_permission',
      resource_type: template.resource_type,
      resource_id: '*',
      action: template.action,
      effect: template.effect,
    });
    setCreateOpen(true);
  };

  const editKind = selectedPolicy?.source ?? 'role_permission';

  const tableColumns = [
    {
      title: t('permissions_col_policy_name'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (name: string) => <Text strong>{name}</Text>,
    },
    {
      title: t('permissions_col_policy_desc'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: t('permissions_resource_type'),
      dataIndex: 'resource_type',
      key: 'resource_type',
      width: 100,
      render: (type: string) => <Tag color="blue">{getResourceTypeLabel(type)}</Tag>,
    },
    {
      title: t('permissions_resource_id'),
      dataIndex: 'resource_id',
      key: 'resource_id',
      width: 120,
      render: (id: string) => (
        <Tag color={isPresetScope(id) ? 'red' : 'green'}>
          {isPresetScope(id) ? t('permissions_all_resources_tag') : id}
        </Tag>
      ),
    },
    {
      title: t('permissions_action'),
      dataIndex: 'action',
      key: 'action',
      width: 100,
      render: (action: string, record: CustomPolicy) => (
        <Tag color="purple">{getActionLabel(record.resource_type, action)}</Tag>
      ),
    },
    {
      title: t('permissions_effect'),
      dataIndex: 'effect',
      key: 'effect',
      width: 80,
      render: (effect: string) => (
        <Tag color={effect === 'allow' ? 'green' : 'red'}>
          {effect === 'allow' ? t('permissions_effect_allow') : t('permissions_effect_deny')}
        </Tag>
      ),
    },
    {
      title: t('permissions_col_linked_role'),
      dataIndex: 'role_name',
      key: 'role_name',
      width: 120,
      render: (name: string) =>
        name ? <Tag color="orange">{name}</Tag> : <Text type="secondary">-</Text>,
    },
    {
      title: t('permissions_source') || '来源',
      dataIndex: 'source',
      key: 'source',
      width: 100,
      render: (source: string) =>
        source === 'permission_definition' ? (
          <Tag color="green">{t('permissions_definition_library') || '权限模板'}</Tag>
        ) : (
          <Tag color="blue">{t('permissions_direct_permission') || '直接权限'}</Tag>
        ),
    },
    {
      title: t('permissions_col_actions'),
      key: 'actions',
      width: 120,
      render: (_: unknown, record: CustomPolicy) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            {t('edit')}
          </Button>
          <Popconfirm title={t('permissions_remove_permission_confirm')} onConfirm={() => handleDelete(record)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              {t('delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const resourceIdFormItem = () => {
    const usePicker = RESOURCE_PICKER_TYPES.includes(
      selectedResourceType as (typeof RESOURCE_PICKER_TYPES)[number],
    );
    if (usePicker) {
      return (
        <Form.Item
          name="resource_id"
          label={t('permissions_resource_id')}
          rules={[{ required: true, message: t('permissions_resource_id_required') }]}
          extra={t('permissions_resource_pick_placeholder')}
        >
          <Select
            showSearch
            allowClear
            loading={resourceIdsLoading}
            placeholder={t('permissions_resource_pick_placeholder')}
            options={[
              { value: '*', label: t('permissions_all_resources_tag') },
              ...resourceIdOptions,
            ]}
            optionFilterProp="label"
          />
        </Form.Item>
      );
    }
    return (
      <Form.Item
        name="resource_id"
        label={t('permissions_resource_id')}
        rules={[{ required: true, message: t('permissions_resource_id_required') }]}
        extra={t('permissions_resource_id_manual_hint')}
      >
        <Input placeholder={t('permissions_resource_id_placeholder')} />
      </Form.Item>
    );
  };

  return (
    <div className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <Space>
          <SafetyOutlined className="text-xl" />
          <Text strong className="text-lg">
            {t('permissions_custom_policy')}
          </Text>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openCreateCustom('role_permission')}>
          {t('permissions_create_custom')}
        </Button>
      </div>

      <Alert
        type="info"
        showIcon
        className="mb-4"
        message={t('permissions_custom_policy_hint')}
        description={
          <Text type="secondary">
            {t('permissions_section_preset_scope_hint')} {t('permissions_section_resource_scoped_hint')}
          </Text>
        }
      />

      <Input.Search
        allowClear
        className="mb-4 max-w-md"
        placeholder={t('permissions_search_policies_placeholder')}
        onSearch={setSearch}
        onChange={(e) => setSearch(e.target.value)}
      />

      <Card
        size="small"
        className="mb-4"
        title={
          <Space>
            <AppstoreOutlined />
            <span>{t('permissions_section_preset_scope')}</span>
            <Tag>{filteredPreset.length}</Tag>
          </Space>
        }
      >
        <Text type="secondary" className="block mb-3">
          {t('permissions_section_preset_scope_hint')}
        </Text>
        <div className="mb-4">
          <Text strong className="mr-2">
            {t('permissions_quick_templates')}:
          </Text>
          <Space wrap>
            {PRESET_TEMPLATE_DEFS.map((template) => (
              <Button
                key={template.name}
                size="small"
                icon={<CopyOutlined />}
                onClick={() => applyTemplate(template)}
              >
                {t(template.labelKey)}
              </Button>
            ))}
          </Space>
        </div>
        <Table<CustomPolicy>
          loading={loading}
          rowKey={(r) => `preset-${r.id}-${r.role_id}`}
          dataSource={filteredPreset}
          columns={tableColumns}
          pagination={{ pageSize: 8, showSizeChanger: false }}
        />
      </Card>

      <Card
        size="small"
        className="mb-4"
        title={
          <Space>
            <AimOutlined />
            <span>{t('permissions_section_resource_scoped')}</span>
            <Tag color="green">{filteredCustom.length}</Tag>
          </Space>
        }
      >
        <Text type="secondary" className="block mb-3">
          {t('permissions_section_resource_scoped_hint')}
        </Text>
        <Table<CustomPolicy>
          loading={loading}
          rowKey={(r) => `custom-${r.id}-${r.role_id}`}
          dataSource={filteredCustom}
          columns={tableColumns}
          pagination={{ pageSize: 8, showSizeChanger: false }}
        />
      </Card>

      <Modal
        title={t('permissions_create_custom')}
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => {
          setCreateOpen(false);
          createForm.resetFields();
        }}
        destroyOnClose
        width={600}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item
            name="kind"
            label={t('permissions_custom_target')}
            initialValue={createKind}
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: 'role_permission', label: t('permissions_target_direct') },
                { value: 'permission_definition', label: t('permissions_target_definition') },
              ]}
              onChange={(value: 'role_permission' | 'permission_definition') => {
                setCreateKind(value);
                createForm.setFieldsValue({
                  name: undefined,
                  description: undefined,
                  role_id: undefined,
                  resource_id: value === 'permission_definition' ? '*' : undefined,
                });
              }}
            />
          </Form.Item>
          {createKind === 'permission_definition' && (
            <>
              <Form.Item
                name="name"
                label={t('permissions_definition_name')}
                rules={[{ required: true, message: t('permissions_name_required') }]}
              >
                <Input placeholder={t('permissions_definition_name_placeholder')} />
              </Form.Item>
              <Form.Item name="description" label={t('permissions_col_description')}>
                <Input.TextArea rows={3} placeholder={t('permissions_definition_desc_placeholder')} />
              </Form.Item>
            </>
          )}
          {createKind === 'role_permission' && (
            <Form.Item
              name="role_id"
              label={t('permissions_assign_to_role')}
              rules={[{ required: true, message: t('permissions_role_pick_required') }]}
            >
              <Select
                placeholder={t('permissions_pick_role_placeholder')}
                options={roles.map((r) => ({ value: r.id, label: r.name }))}
              />
            </Form.Item>
          )}
          <Form.Item
            name="resource_type"
            label={t('permissions_resource_type')}
            rules={[{ required: true, message: t('permissions_select_resource') }]}
          >
            <Select
              options={resourceTypeOptions}
              onChange={(value) => {
                setSelectedResourceType(value);
                createForm.setFieldsValue({ resource_id: undefined, action: undefined });
              }}
            />
          </Form.Item>
          {resourceIdFormItem()}
          <Form.Item
            name="action"
            label={t('permissions_action')}
            rules={[{ required: true, message: t('permissions_action_required') }]}
          >
            <Select options={actionOptionsMap[selectedResourceType as keyof typeof actionOptionsMap] || actionOptionsMap['*']} />
          </Form.Item>
          <Form.Item name="effect" label={t('permissions_effect')} initialValue="allow">
            <Select
              options={[
                { value: 'allow', label: t('permissions_effect_allow') },
                { value: 'deny', label: t('permissions_effect_deny') },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('permissions_edit_role')}
        open={editOpen}
        onOk={handleEdit}
        onCancel={() => {
          setEditOpen(false);
          editForm.resetFields();
        }}
        destroyOnClose
        width={600}
      >
        <Form form={editForm} layout="vertical">
          {editKind === 'permission_definition' ? (
            <>
              <Form.Item
                name="name"
                label={t('permissions_definition_name')}
                rules={[{ required: true, message: t('permissions_name_required') }]}
              >
                <Input placeholder={t('permissions_definition_name_placeholder')} />
              </Form.Item>
              <Form.Item name="description" label={t('permissions_col_description')}>
                <Input.TextArea rows={3} placeholder={t('permissions_definition_desc_placeholder')} />
              </Form.Item>
            </>
          ) : (
            <Form.Item
              name="role_id"
              label={t('permissions_assign_to_role')}
              rules={[{ required: true, message: t('permissions_role_pick_required') }]}
            >
              <Select
                placeholder={t('permissions_pick_role_placeholder')}
                options={roles.map((r) => ({ value: r.id, label: r.name }))}
              />
            </Form.Item>
          )}
          <Form.Item
            name="resource_type"
            label={t('permissions_resource_type')}
            rules={[{ required: true, message: t('permissions_select_resource') }]}
          >
            <Select
              options={resourceTypeOptions}
              onChange={(value) => {
                setSelectedResourceType(value);
                editForm.setFieldsValue({ resource_id: undefined, action: undefined });
              }}
            />
          </Form.Item>
          {resourceIdFormItem()}
          <Form.Item
            name="action"
            label={t('permissions_action')}
            rules={[{ required: true, message: t('permissions_action_required') }]}
          >
            <Select options={actionOptionsMap[selectedResourceType as keyof typeof actionOptionsMap] || actionOptionsMap['*']} />
          </Form.Item>
          <Form.Item name="effect" label={t('permissions_effect')}>
            <Select
              options={[
                { value: 'allow', label: t('permissions_effect_allow') },
                { value: 'deny', label: t('permissions_effect_deny') },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
