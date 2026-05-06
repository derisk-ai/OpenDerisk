'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Transfer,
  Typography,
  message,
  Spin,
  Tooltip,
} from 'antd';
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  SafetyOutlined,
  SettingOutlined,
  EyeOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { permissionsService, type Role, type Permission, type ScopedPermission, type PermissionDefinition } from '@/services/permissions';
import ResourceSelector from './ResourceSelector';

const { Text } = Typography;

interface RoleWithPermissions extends Role {
  permissions?: Permission[];
}

interface RoleManagementProps {
  roles?: Role[];
  onRolesChange?: () => void;
}

// Predefined permission policies (T3.4)
interface PredefinedPolicy {
  key: string;
  name: string;
  nameZh: string;
  description: string;
  descriptionZh: string;
  permissions: { resource_type: string; action: string; resource_id: string }[];
  category: 'agent' | 'tool' | 'knowledge' | 'model' | 'system';
}

const predefinedPolicies: PredefinedPolicy[] = [
  // Agent policies
  {
    key: 'agent:readonly',
    name: 'AgentReadOnly',
    nameZh: '智能体只读',
    description: 'Read-only access to agents',
    descriptionZh: '只读访问智能体',
    category: 'agent',
    permissions: [{ resource_type: 'agent', action: 'read', resource_id: '*' }],
  },
  {
    key: 'agent:chat',
    name: 'AgentChatAccess',
    nameZh: '智能体对话',
    description: 'Can view and chat with agents',
    descriptionZh: '可查看智能体并与其对话',
    category: 'agent',
    permissions: [
      { resource_type: 'agent', action: 'read', resource_id: '*' },
      { resource_type: 'agent', action: 'chat', resource_id: '*' },
    ],
  },
  {
    key: 'agent:full',
    name: 'AgentFullAccess',
    nameZh: '智能体完全访问',
    description: 'Full management access to agents',
    descriptionZh: '完全管理智能体',
    category: 'agent',
    permissions: [{ resource_type: 'agent', action: '*', resource_id: '*' }],
  },
  // Tool policies
  {
    key: 'tool:readonly',
    name: 'ToolReadOnly',
    nameZh: '工具只读',
    description: 'Read-only access to tools',
    descriptionZh: '只读访问工具',
    category: 'tool',
    permissions: [{ resource_type: 'tool', action: 'read', resource_id: '*' }],
  },
  {
    key: 'tool:execute',
    name: 'ToolExecuteAccess',
    nameZh: '工具执行',
    description: 'Can view and execute tools',
    descriptionZh: '可查看并执行工具',
    category: 'tool',
    permissions: [
      { resource_type: 'tool', action: 'read', resource_id: '*' },
      { resource_type: 'tool', action: 'execute', resource_id: '*' },
    ],
  },
  {
    key: 'tool:full',
    name: 'ToolFullAccess',
    nameZh: '工具完全访问',
    description: 'Full management access to tools',
    descriptionZh: '完全管理工具',
    category: 'tool',
    permissions: [{ resource_type: 'tool', action: '*', resource_id: '*' }],
  },
  // Knowledge policies
  {
    key: 'knowledge:readonly',
    name: 'KnowledgeReadOnly',
    nameZh: '知识库只读',
    description: 'Read-only access to knowledge bases',
    descriptionZh: '只读访问知识库',
    category: 'knowledge',
    permissions: [{ resource_type: 'knowledge', action: 'read', resource_id: '*' }],
  },
  {
    key: 'knowledge:query',
    name: 'KnowledgeQueryAccess',
    nameZh: '知识库检索',
    description: 'Can view and query knowledge bases',
    descriptionZh: '可查看并检索知识库',
    category: 'knowledge',
    permissions: [
      { resource_type: 'knowledge', action: 'read', resource_id: '*' },
      { resource_type: 'knowledge', action: 'query', resource_id: '*' },
    ],
  },
  {
    key: 'knowledge:full',
    name: 'KnowledgeFullAccess',
    nameZh: '知识库完全访问',
    description: 'Full management access to knowledge bases',
    descriptionZh: '完全管理知识库',
    category: 'knowledge',
    permissions: [{ resource_type: 'knowledge', action: '*', resource_id: '*' }],
  },
  // Model policies
  {
    key: 'model:readonly',
    name: 'ModelReadOnly',
    nameZh: '模型只读',
    description: 'Read-only access to models',
    descriptionZh: '只读访问模型',
    category: 'model',
    permissions: [{ resource_type: 'model', action: 'read', resource_id: '*' }],
  },
  {
    key: 'model:chat',
    name: 'ModelChatAccess',
    nameZh: '模型对话',
    description: 'Can view and chat with models',
    descriptionZh: '可查看模型并与其对话',
    category: 'model',
    permissions: [
      { resource_type: 'model', action: 'read', resource_id: '*' },
      { resource_type: 'model', action: 'chat', resource_id: '*' },
    ],
  },
  {
    key: 'model:full',
    name: 'ModelFullAccess',
    nameZh: '模型完全访问',
    description: 'Full management access to models',
    descriptionZh: '完全管理模型',
    category: 'model',
    permissions: [{ resource_type: 'model', action: '*', resource_id: '*' }],
  },
  // System policies
  {
    key: 'system:readonly',
    name: 'SystemReadOnly',
    nameZh: '系统只读',
    description: 'System-wide read-only access',
    descriptionZh: '全系统只读权限',
    category: 'system',
    permissions: [{ resource_type: '*', action: 'read', resource_id: '*' }],
  },
  {
    key: 'system:operator',
    name: 'SystemOperator',
    nameZh: '系统操作员',
    description: 'Can operate all resources but cannot manage configuration',
    descriptionZh: '可操作所有资源但不可管理配置',
    category: 'system',
    permissions: [
      { resource_type: '*', action: 'read', resource_id: '*' },
      { resource_type: '*', action: 'chat', resource_id: '*' },
      { resource_type: '*', action: 'execute', resource_id: '*' },
      { resource_type: '*', action: 'query', resource_id: '*' },
    ],
  },
  {
    key: 'system:admin',
    name: 'SystemFullAccess',
    nameZh: '系统管理员',
    description: 'Full system administration access',
    descriptionZh: '系统完全管理权限',
    category: 'system',
    permissions: [{ resource_type: '*', action: '*', resource_id: '*' }],
  },
];

// Helper to get category color
const getCategoryColor = (category: string): string => {
  const colors: Record<string, string> = {
    agent: 'blue',
    tool: 'green',
    knowledge: 'orange',
    model: 'purple',
    system: 'red',
  };
  return colors[category] || 'default';
};

// Helper to get category label
const getCategoryLabel = (category: string, t: (key: string) => string): string => {
  const labels: Record<string, string> = {
    agent: t('permissions_resource_agent'),
    tool: t('permissions_resource_tool'),
    knowledge: t('permissions_resource_knowledge'),
    model: t('permissions_resource_model'),
    system: t('permissions_resource_all'),
  };
  return labels[category] || category;
};

// Helper to get action options by resource type
const getActionOptions = (resourceType: string, t: (key: string) => string) => {
  const actionMap: Record<string, { value: string; label: string }[]> = {
    agent: [
      { value: 'read', label: t('permissions_action_read') },
      { value: 'chat', label: t('permissions_action_chat') },
      { value: 'write', label: t('permissions_action_write') },
      { value: 'admin', label: t('permissions_action_admin') },
    ],
    tool: [
      { value: 'read', label: t('permissions_action_read') },
      { value: 'execute', label: t('permissions_action_execute') },
      { value: 'manage', label: t('permissions_action_manage') },
      { value: 'admin', label: t('permissions_action_admin') },
    ],
    knowledge: [
      { value: 'read', label: t('permissions_action_read') },
      { value: 'query', label: t('permissions_action_query') },
      { value: 'write', label: t('permissions_action_write') },
      { value: 'admin', label: t('permissions_action_admin') },
    ],
    model: [
      { value: 'read', label: t('permissions_action_read') },
      { value: 'chat', label: t('permissions_action_chat') },
      { value: 'manage', label: t('permissions_action_manage') },
      { value: 'admin', label: t('permissions_action_admin') },
    ],
  };
  return actionMap[resourceType] || actionMap.agent;
};

export default function RoleManagement({ roles: externalRoles, onRolesChange }: RoleManagementProps) {
  const { t, i18n } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [roles, setRoles] = useState<RoleWithPermissions[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [selectedRole, setSelectedRole] = useState<RoleWithPermissions | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const isSystemRole = (role: RoleWithPermissions | null | undefined) =>
    (role?.is_system ?? 0) === 1;

  const loadRoles = useCallback(async () => {
    setLoading(true);
    try {
      const rolesData = await permissionsService.listRoles();
      // Load permissions for each role
      const rolesWithPerms = await Promise.all(
        rolesData.map(async (role) => {
          try {
            const perms = await permissionsService.listRolePermissions(role.id);
            return { ...role, permissions: perms };
          } catch {
            return { ...role, permissions: [] };
          }
        })
      );
      setRoles(rolesWithPerms);
    } catch (e: unknown) {
      message.error(t('permissions_load_error') + ': ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [t]);

  // Load roles with permissions when external roles change
  const loadRolesWithPermissions = useCallback(async () => {
    setLoading(true);
    try {
      const rolesData = await permissionsService.listRoles();
      const rolesWithPerms = await Promise.all(
        rolesData.map(async (role) => {
          try {
            const perms = await permissionsService.listRolePermissions(role.id);
            return { ...role, permissions: perms };
          } catch {
            return { ...role, permissions: [] };
          }
        })
      );
      setRoles(rolesWithPerms);
    } catch (e: unknown) {
      message.error(t('permissions_load_error') + ': ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (externalRoles && externalRoles.length > 0) {
      // Use external roles and load their permissions
      loadRolesWithPermissions();
    } else if (!externalRoles) {
      // No external roles, load internally
      loadRoles();
    }
  }, [externalRoles, loadRoles, loadRolesWithPermissions]);

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      await permissionsService.createRole({
        name: values.name,
        description: values.description,
      });
      message.success(t('permissions_role_created'));
      setCreateOpen(false);
      createForm.resetFields();
      await loadRoles();
      onRolesChange?.();
    } catch (e: unknown) {
      if ((e as { errorFields?: unknown })?.errorFields) return;
      message.error(t('permissions_create_error') + ': ' + (e as Error).message);
    }
  };

  const handleEdit = async () => {
    if (!selectedRole) return;
    if (isSystemRole(selectedRole)) {
      message.warning(
        t('permissions_system_role_readonly') || '系统角色为只读，不允许配置或修改'
      );
      return;
    }
    try {
      const values = await editForm.validateFields();
      await permissionsService.updateRole(selectedRole.id, {
        name: values.name,
        description: values.description,
      });
      message.success(t('permissions_role_updated'));
      setEditOpen(false);
      editForm.resetFields();
      await loadRoles();
      onRolesChange?.();
    } catch (e: unknown) {
      if ((e as { errorFields?: unknown })?.errorFields) return;
      message.error(t('permissions_update_error') + ': ' + (e as Error).message);
    }
  };

  const handleDelete = async (roleId: number, isSystem: number) => {
    if (isSystem === 1) {
      message.warning(t('permissions_system_role_cannot_delete'));
      return;
    }
    try {
      await permissionsService.deleteRole(roleId);
      message.success(t('permissions_role_deleted'));
      await loadRoles();
      onRolesChange?.();
    } catch (e: unknown) {
      message.error(t('permissions_delete_error') + ': ' + (e as Error).message);
    }
  };

  const openEdit = (role: RoleWithPermissions) => {
    if (isSystemRole(role)) {
      message.warning(
        t('permissions_system_role_readonly') || '系统角色为只读，不允许配置或修改'
      );
      return;
    }
    setSelectedRole(role);
    editForm.setFieldsValue({
      name: role.name,
      description: role.description,
    });
    setEditOpen(true);
  };

  // Apply preset role template
  const applyPreset = (preset: 'viewer' | 'operator' | 'editor' | 'admin') => {
    const presets = {
      viewer: {
        name: 'viewer',
        description: '只读访问所有资源',
      },
      operator: {
        name: 'operator',
        description: '可操作所有资源但不可管理配置',
      },
      editor: {
        name: 'editor',
        description: '可读、写、执行所有资源',
      },
      admin: {
        name: 'admin',
        description: '完全管理权限',
      },
    };
    const p = presets[preset];
    createForm.setFieldsValue({
      name: p.name,
      description: p.description,
    });
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <Space>
          <SafetyOutlined className="text-xl" />
          <Text strong className="text-lg">
            {t('permissions_role_management')}
          </Text>
        </Space>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setCreateOpen(true)}
        >
          {t('permissions_create_role')}
        </Button>
      </div>

      <Alert
        type="info"
        showIcon
        className="mb-4"
        message={t('permissions_role_management_hint')}
      />

      <Table<RoleWithPermissions>
        loading={loading}
        rowKey="id"
        dataSource={roles}
        columns={[
          {
            title: t('permissions_col_name'),
            dataIndex: 'name',
            key: 'name',
            width: 260,
            onCell: () => ({
              style: {
                wordBreak: 'normal',
                overflowWrap: 'normal',
              },
            }),
            render: (name: string, record: RoleWithPermissions) => (
              <Space align="center" wrap={false}>
                <Text strong style={{ whiteSpace: 'nowrap' }}>
                  {name}
                </Text>
                {record.is_system === 1 && (
                  <Tag color="blue" style={{ flexShrink: 0, marginInlineEnd: 0 }}>
                    {t('permissions_system_role')}
                  </Tag>
                )}
              </Space>
            ),
          },
          {
            title: t('permissions_col_description'),
            dataIndex: 'description',
            key: 'description',
            ellipsis: true,
          },
          {
            title: t('permissions_col_permissions'),
            key: 'permissions',
            width: 200,
            render: (_: unknown, record: RoleWithPermissions) => (
              <Text type="secondary">
                {record.permissions?.length ?? 0} {t('permissions_count')}
              </Text>
            ),
          },
          {
            title: t('permissions_col_actions'),
            key: 'actions',
            width: 200,
            render: (_: unknown, record: RoleWithPermissions) => {
              if (isSystemRole(record)) {
                return (
                  <Space>
                    <Button
                      type="link"
                      size="small"
                      icon={<EyeOutlined />}
                      onClick={() => setSelectedRole(record)}
                    >
                      {t('view_details')}
                    </Button>
                    <Text type="secondary">
                      {t('permissions_system_role_readonly') || '系统角色为只读，不允许配置或修改'}
                    </Text>
                  </Space>
                );
              }
              return (
                <Space>
                  <Button
                    type="link"
                    size="small"
                    icon={<SettingOutlined />}
                    onClick={() => setSelectedRole(record)}
                  >
                    {t('permissions_manage')}
                  </Button>
                  <Button
                    type="link"
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => openEdit(record)}
                  >
                    {t('edit')}
                  </Button>
                  <Popconfirm
                    title={t('permissions_delete_confirm')}
                    onConfirm={() => handleDelete(record.id, record.is_system)}
                  >
                    <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                      {t('delete')}
                    </Button>
                  </Popconfirm>
                </Space>
              );
            },
          },
        ]}
      />

      {/* Permission Management Panel */}
      {selectedRole && (
        <PermissionPanel
          role={selectedRole}
          readonly={isSystemRole(selectedRole)}
          onClose={() => setSelectedRole(null)}
          onPermissionsChange={() => {
            loadRoles();
            onRolesChange?.();
          }}
        />
      )}

      {/* Create Role Modal */}
      <Modal
        title={t('permissions_create_role')}
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
            name="name"
            label={t('permissions_col_name')}
            rules={[{ required: true, message: t('permissions_name_required') }]}
          >
            <Input maxLength={64} placeholder={t('permissions_name_placeholder')} />
          </Form.Item>
          <Form.Item name="description" label={t('permissions_col_description')}>
            <Input.TextArea rows={3} maxLength={500} />
          </Form.Item>
          <Form.Item label={t('permissions_preset_desc')}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t('permissions_preset_desc')}
              </Text>
              <Space wrap>
                <Button onClick={() => applyPreset('viewer')}>
                  {t('permissions_preset_viewer')}
                </Button>
                <Button onClick={() => applyPreset('operator')}>
                  {t('permissions_preset_operator')}
                </Button>
                <Button onClick={() => applyPreset('editor')}>
                  {t('permissions_preset_editor')}
                </Button>
                <Button onClick={() => applyPreset('admin')}>
                  {t('permissions_preset_admin')}
                </Button>
              </Space>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Role Modal */}
      <Modal
        title={t('permissions_edit_role')}
        open={editOpen}
        onOk={handleEdit}
        onCancel={() => {
          setEditOpen(false);
          editForm.resetFields();
        }}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="name"
            label={t('permissions_col_name')}
            rules={[{ required: true, message: t('permissions_name_required') }]}
          >
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="description" label={t('permissions_col_description')}>
            <Input.TextArea rows={3} maxLength={500} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// Permission Panel Component with Transfer UI
interface PermissionPanelProps {
  role: RoleWithPermissions;
  onClose: () => void;
  onPermissionsChange: () => void;
  readonly?: boolean;
}

interface TransferItem {
  key: string;
  title: string;
  description: string;
  policy: PredefinedPolicy;
}

// Scoped Permission Form State
interface ScopedPermissionForm {
  resource_type: string;
  resource_id: string[];
  action: string;
  effect: string;
}

function PermissionPanel({
  role,
  onClose,
  onPermissionsChange,
  readonly = false,
}: PermissionPanelProps) {
  const { t, i18n } = useTranslation();
  const [permissions, setPermissions] = useState<Permission[]>(role.permissions ?? []);
  const [loading, setLoading] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [selectedPolicy, setSelectedPolicy] = useState<PredefinedPolicy | null>(null);

  // Scoped permissions state (T2.2)
  const [scopedForm, setScopedForm] = useState<ScopedPermissionForm>({
    resource_type: 'agent',
    resource_id: [],
    action: 'read',
    effect: 'allow',
  });
  const [scopedPermissions, setScopedPermissions] = useState<Permission[]>([]);
  const [loadingScoped, setLoadingScoped] = useState(false);

  // Permission definitions state
  const [permissionDefinitions, setPermissionDefinitions] = useState<PermissionDefinition[]>([]);
  const [rolePermissionDefs, setRolePermissionDefs] = useState<PermissionDefinition[]>([]);
  const [loadingDefs, setLoadingDefs] = useState(false);
  const [selectedDefIds, setSelectedDefIds] = useState<number[]>([]);

  // Sync local state when role.permissions changes
  useEffect(() => {
    setPermissions(role.permissions ?? []);
  }, [role.permissions]);

  // Load scoped permissions for this role
  useEffect(() => {
    const loadScopedPermissions = async () => {
      setLoadingScoped(true);
      try {
        const scopedPerms = await permissionsService.listScopedPermissions({ role_id: role.id });
        setScopedPermissions(scopedPerms);
      } catch (error) {
        console.error('Failed to load scoped permissions:', error);
      } finally {
        setLoadingScoped(false);
      }
    };

    if (role.id) {
      loadScopedPermissions();
    }
  }, [role.id]);

  // Load permission definitions for this role
  useEffect(() => {
    const loadPermissionDefinitions = async () => {
      setLoadingDefs(true);
      try {
        const allDefs = await permissionsService.listPermissionDefinitions({});
        setPermissionDefinitions(allDefs);

        // Load permission definitions assigned to this role
        const roleDefs = await permissionsService.getRolePermissionDefs(role.id);
        setRolePermissionDefs(roleDefs);
        setSelectedDefIds(roleDefs.map((d) => d.id));
      } catch (error) {
        console.error('Failed to load permission definitions:', error);
      } finally {
        setLoadingDefs(false);
      }
    };

    if (role.id) {
      loadPermissionDefinitions();
    }
  }, [role.id]);

  // Build transfer data source from predefined policies
  const transferDataSource: TransferItem[] = predefinedPolicies.map((policy) => ({
    key: policy.key,
    title: i18n.language === 'zh' ? policy.nameZh : policy.name,
    description: i18n.language === 'zh' ? policy.descriptionZh : policy.description,
    policy,
  }));

  // Get currently selected policy keys based on role's permissions
  const getSelectedKeys = (): string[] => {
    const selected: string[] = [];

    for (const policy of predefinedPolicies) {
      // Check if all permissions in this policy are granted
      const allGranted = policy.permissions.every((pp) =>
        permissions.some(
          (rp) =>
            rp.resource_type === pp.resource_type &&
            rp.action === pp.action &&
            (rp.resource_id === pp.resource_id || rp.resource_id === '*' || pp.resource_id === '*')
        )
      );
      if (allGranted) {
        selected.push(policy.key);
      }
    }

    return selected;
  };

  const [targetKeys, setTargetKeys] = useState<string[]>(getSelectedKeys());

  // Update target keys when permissions change
  useEffect(() => {
    setTargetKeys(getSelectedKeys());
  }, [permissions]);

  const handleTransferChange = async (newTargetKeys: string[]) => {
    if (readonly) {
      message.warning(
        t('permissions_system_role_readonly') || '系统角色为只读，不允许配置或修改'
      );
      return;
    }
    const currentKeys = getSelectedKeys();
    const added = newTargetKeys.filter((k) => !currentKeys.includes(k));
    const removed = currentKeys.filter((k) => !newTargetKeys.includes(k));

    setLoading(true);
    try {
      // Add new permissions
      for (const key of added) {
        const policy = predefinedPolicies.find((p) => p.key === key);
        if (policy) {
          for (const perm of policy.permissions) {
            await permissionsService.addRolePermission(role.id, {
              resource_type: perm.resource_type,
              resource_id: perm.resource_id,
              action: perm.action,
            });
          }
        }
      }

      // Remove permissions (find matching permissions and remove them)
      for (const key of removed) {
        const policy = predefinedPolicies.find((p) => p.key === key);
        if (policy) {
          for (const perm of policy.permissions) {
            const matchingPerm = permissions.find(
              (p) =>
                p.resource_type === perm.resource_type &&
                p.action === perm.action &&
                (p.resource_id === perm.resource_id || p.resource_id === '*' || perm.resource_id === '*')
            );
            if (matchingPerm) {
              await permissionsService.removeRolePermission(role.id, matchingPerm.id);
            }
          }
        }
      }

      message.success(t('permissions_role_updated'));
      await onPermissionsChange();
    } catch (e: unknown) {
      message.error(t('permissions_update_error') + ': ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleShowDetail = (policy: PredefinedPolicy) => {
    setSelectedPolicy(policy);
    setDetailModalOpen(true);
  };

  // Handle scoped permission add
  const handleAddScopedPermission = async () => {
    if (readonly) {
      message.warning(
        t('permissions_system_role_readonly') || '系统角色为只读，不允许配置或修改'
      );
      return;
    }
    if (!scopedForm.resource_id || scopedForm.resource_id.length === 0) {
      message.warning(t('permissions_select_resource'));
      return;
    }

    setLoading(true);
    try {
      const addedPermissions: Permission[] = [];

      for (const resourceId of scopedForm.resource_id) {
        try {
          const perm = await permissionsService.grantScopedPermission({
            role_id: role.id,
            resource_type: scopedForm.resource_type,
            resource_id: resourceId,
            action: scopedForm.action,
            effect: scopedForm.effect,
          });
          addedPermissions.push(perm);
        } catch (error) {
          // Skip if already exists
          console.warn(`Failed to add scoped permission for ${resourceId}:`, error);
        }
      }

      if (addedPermissions.length > 0) {
        setScopedPermissions((prev) => [...prev, ...addedPermissions]);
        message.success(t('permissions_permission_added'));
        await onPermissionsChange();

        // Reset form
        setScopedForm({
          resource_type: scopedForm.resource_type,
          resource_id: [],
          action: 'read',
          effect: 'allow',
        });
      }
    } catch (e: unknown) {
      message.error(t('permissions_add_permission_error') + ': ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  // Handle scoped permission remove
  const handleRemoveScopedPermission = async (permissionId: number) => {
    if (readonly) {
      message.warning(
        t('permissions_system_role_readonly') || '系统角色为只读，不允许配置或修改'
      );
      return;
    }
    try {
      await permissionsService.removeRolePermission(role.id, permissionId);
      setScopedPermissions((prev) => prev.filter((p) => p.id !== permissionId));
      message.success(t('permissions_permission_removed'));
      await onPermissionsChange();
    } catch (e: unknown) {
      message.error(t('permissions_remove_permission_error') + ': ' + (e as Error).message);
    }
  };

  // Custom render for transfer items
  const renderTransferItem = (item: TransferItem) => {
    return (
      <div className="flex items-center justify-between w-full">
        <div className="flex flex-col">
          <Space>
            <Tag color={getCategoryColor(item.policy.category)} size="small">
              {getCategoryLabel(item.policy.category, t)}
            </Tag>
            <span className="font-medium">{item.title}</span>
          </Space>
          <span className="text-xs text-gray-500 mt-1">{item.description}</span>
        </div>
        <Tooltip title={t('view_details')}>
          <Button
            type="text"
            size="small"
            icon={<EyeOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              handleShowDetail(item.policy);
            }}
          />
        </Tooltip>
      </div>
    );
  };

  return (
    <>
      <Drawer
        title={`${t('permissions_manage')}: ${role.name}`}
        open
        onClose={onClose}
        placement="right"
        width={920}
        destroyOnClose
        extra={<Button onClick={onClose}>{t('close')}</Button>}
      >
        <Spin spinning={loading}>
          {readonly && (
            <Alert
              type="warning"
              showIcon
              className="mb-4"
              message={t('permissions_system_role_readonly') || '系统角色为只读，不允许配置或修改'}
            />
          )}
          <Alert
            type="info"
            showIcon
            icon={<InfoCircleOutlined />}
            className="mb-4"
            message={t('permissions_preset_desc')}
            description={
              <div className="mt-2">
                <Text type="secondary">
                  {t('permissions_assign_roles_hint') || '使用穿梭框分配权限策略：'}
                </Text>
              </div>
            }
          />

          <Transfer
            dataSource={transferDataSource}
            targetKeys={targetKeys}
            onChange={handleTransferChange}
            disabled={readonly}
            titles={[t('permissions_available_roles'), t('permissions_assigned_roles')]}
            render={(item) => renderTransferItem(item as TransferItem)}
            listStyle={{ width: 360, height: 400 }}
            operations={[t('add'), t('delete')]}
            showSearch
            filterOption={(inputValue, item) => {
              const transferItem = item as TransferItem;
              return (
                transferItem.title.toLowerCase().includes(inputValue.toLowerCase()) ||
                transferItem.description.toLowerCase().includes(inputValue.toLowerCase()) ||
                transferItem.policy.name.toLowerCase().includes(inputValue.toLowerCase())
              );
            }}
          />

          {/* Scoped Resource Permissions Section (T2.2) */}
          <div className="mt-6 border-t pt-4">
            <Text strong className="block mb-3">
              {t('permissions_scoped')} ({t('permissions_specific_resources')})
            </Text>

          {/* Add Scoped Permission Form */}
          {!readonly && (
            <Card size="small" className="mb-4" title={t('permissions_add_scoped_permission')}>
              <div className="space-y-3">
                {/* Resource Type Selector */}
                <div>
                  <Text className="block mb-1">{t('permissions_resource_type')}:</Text>
                  <Select
                    value={scopedForm.resource_type}
                    onChange={(value) =>
                      setScopedForm({ ...scopedForm, resource_type: value, resource_id: [] })
                    }
                    options={[
                      { value: 'agent', label: t('permissions_resource_agent') },
                      { value: 'tool', label: t('permissions_resource_tool') },
                      { value: 'knowledge', label: t('permissions_resource_knowledge') },
                      { value: 'model', label: t('permissions_resource_model') },
                    ]}
                    className="w-full"
                  />
                </div>

                {/* Resource Selector */}
                <ResourceSelector
                  resourceType={scopedForm.resource_type}
                  selectedResourceIds={scopedForm.resource_id}
                  onChange={(ids) => setScopedForm({ ...scopedForm, resource_id: ids })}
                  allowWildcard={false}
                />

                {/* Action Selector */}
                <div>
                  <Text className="block mb-1">{t('permissions_action')}:</Text>
                  <Select
                    value={scopedForm.action}
                    onChange={(value) => setScopedForm({ ...scopedForm, action: value })}
                    options={getActionOptions(scopedForm.resource_type, t)}
                    className="w-full"
                  />
                </div>

                <Button
                  type="primary"
                  onClick={handleAddScopedPermission}
                  loading={loading}
                  disabled={!scopedForm.resource_id || scopedForm.resource_id.length === 0}
                >
                  {t('add')}
                </Button>
              </div>
            </Card>
          )}

          {/* Scoped Permissions List */}
          <Text className="block mb-2">
            {t('permissions_scoped')}: {scopedPermissions.length} {t('permissions_count')}
          </Text>
          {loadingScoped ? (
            <Spin size="small" />
          ) : scopedPermissions.length > 0 ? (
            <Table
              size="small"
              pagination={false}
              dataSource={scopedPermissions}
              columns={[
                {
                  title: t('permissions_resource_type'),
                  dataIndex: 'resource_type',
                  key: 'resource_type',
                  width: 100,
                  render: (type: string) => <Tag>{type}</Tag>,
                },
                {
                  title: t('permissions_resource_id'),
                  dataIndex: 'resource_id',
                  key: 'resource_id',
                  width: 150,
                  render: (id: string) => (
                    <Tag color={id === '*' ? 'red' : 'blue'}>
                      {id === '*' ? t('permissions_all_resources') : id}
                    </Tag>
                  ),
                },
                {
                  title: t('permissions_action'),
                  dataIndex: 'action',
                  key: 'action',
                  width: 80,
                  render: (action: string) => <Tag color="green">{action}</Tag>,
                },
                {
                  title: t('permissions_col_actions'),
                  key: 'actions',
                  width: 80,
                  render: (_: unknown, record: Permission) =>
                    readonly ? null : (
                      <Button
                        type="link"
                        size="small"
                        danger
                        onClick={() => handleRemoveScopedPermission(record.id)}
                      >
                        {t('delete')}
                      </Button>
                    ),
                },
              ]}
            />
          ) : (
            <Text type="secondary">{t('permissions_empty')}</Text>
          )}
          </div>

          {/* Permission Definitions Section */}
          <div className="mt-6 border-t pt-4">
            <Text strong className="block mb-3">
              {t('permissions_from_definition_library') || '从权限库选择'}
            </Text>

          <Alert
            type="info"
            showIcon
            className="mb-3"
            message={t('permissions_definition_library_hint') || '从已创建的权限定义库中选择权限分配给当前角色'}
            description={
              <Text type="secondary">
                {t('permissions_definition_library_desc') || '权限定义允许您创建可复用的权限模板'}
              </Text>
            }
          />

          {loadingDefs ? (
            <Spin size="small" />
          ) : permissionDefinitions.length > 0 ? (
            <div className="max-h-64 overflow-y-auto border rounded p-2">
              <Checkbox.Group
                value={selectedDefIds}
                onChange={(values) => setSelectedDefIds(values as number[])}
                disabled={readonly}
                className="w-full"
              >
                <Space direction="vertical" className="w-full">
                  {permissionDefinitions.map((def) => (
                    <Checkbox key={def.id} value={def.id} className="w-full">
                      <Space>
                        <Tag color="blue">{def.resource_type}</Tag>
                        <Text>{def.name}</Text>
                        <Text type="secondary">- {def.description || def.action}</Text>
                      </Space>
                    </Checkbox>
                  ))}
                </Space>
              </Checkbox.Group>
            </div>
          ) : (
            <Text type="secondary">
              {t('permissions_no_definitions') || '暂无权限定义，请先在"权限定义"标签页创建'}
            </Text>
          )}

          {!readonly && selectedDefIds.length > 0 && (
            <Button
              type="primary"
              className="mt-3"
              onClick={async () => {
                setLoading(true);
                try {
                  // Add new permission definitions
                  const currentIds = rolePermissionDefs.map((d) => d.id);
                  const toAdd = selectedDefIds.filter((id) => !currentIds.includes(id));

                  for (const defId of toAdd) {
                    await permissionsService.addPermissionDefToRole(role.id, defId);
                  }

                  // Remove deselected permission definitions
                  const toRemove = currentIds.filter((id) => !selectedDefIds.includes(id));
                  for (const defId of toRemove) {
                    await permissionsService.removePermissionDefFromRole(role.id, defId);
                  }

                  message.success(t('permissions_definition_assigned'));
                  await onPermissionsChange();

                  // Reload role permission definitions
                  const roleDefs = await permissionsService.getRolePermissionDefs(role.id);
                  setRolePermissionDefs(roleDefs);
                } catch (e: unknown) {
                  message.error(t('permissions_assign_error') + ': ' + (e as Error).message);
                } finally {
                  setLoading(false);
                }
              }}
              loading={loading}
            >
              {t('permissions_save_definition_selection') || '保存权限选择'}
            </Button>
          )}
          </div>

          {/* Current Permissions Summary */}
          <div className="mt-6">
            <Text strong>{t('permissions_effective_permissions')}:</Text>
            <div className="mt-2">
              {permissions.length > 0 ? (
                <Space direction="vertical" align="start" className="w-full">
                  {Object.entries(
                    permissions.reduce((acc, perm) => {
                      if (!acc[perm.resource_type]) {
                        acc[perm.resource_type] = [];
                      }
                      acc[perm.resource_type].push(perm.action);
                      return acc;
                    }, {} as Record<string, string[]>)
                  ).map(([resourceType, actions]) => (
                    <Tag key={resourceType} color="purple" className="px-3 py-1">
                      {resourceType}: {actions.join(', ')}
                    </Tag>
                  ))}
                </Space>
              ) : (
                <Text type="secondary">{t('permissions_no_permissions')}</Text>
              )}
            </div>
          </div>
        </Spin>
      </Drawer>

      {/* Policy Detail Modal (T3.5) */}
      <Modal
        title={selectedPolicy ? (i18n.language === 'zh' ? selectedPolicy.nameZh : selectedPolicy.name) : ''}
        open={detailModalOpen}
        onCancel={() => {
          setDetailModalOpen(false);
          setSelectedPolicy(null);
        }}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>
            {t('close')}
          </Button>,
        ]}
        width={600}
      >
        {selectedPolicy && (
          <div>
            <Descriptions bordered column={1} size="small" className="mb-4">
              <Descriptions.Item label={t('permissions_col_name')}>
                {i18n.language === 'zh' ? selectedPolicy.nameZh : selectedPolicy.name}
              </Descriptions.Item>
              <Descriptions.Item label={t('permissions_col_description')}>
                {i18n.language === 'zh' ? selectedPolicy.descriptionZh : selectedPolicy.description}
              </Descriptions.Item>
              <Descriptions.Item label={t('permissions_resource_type')}>
                <Tag color={getCategoryColor(selectedPolicy.category)}>
                  {getCategoryLabel(selectedPolicy.category, t)}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('permissions_col_permissions')}>
                {selectedPolicy.permissions.length} {t('permissions_count')}
              </Descriptions.Item>
            </Descriptions>

            <Text strong className="block mb-2">
              {t('permissions_col_permissions')}:
            </Text>
            <Table
              size="small"
              pagination={false}
              dataSource={selectedPolicy.permissions}
              columns={[
                {
                  title: t('permissions_resource_type'),
                  dataIndex: 'resource_type',
                  key: 'resource_type',
                  render: (type: string) => <Tag>{type}</Tag>,
                },
                {
                  title: t('permissions_action'),
                  dataIndex: 'action',
                  key: 'action',
                  render: (action: string) => (
                    <Tag color={action === '*' ? 'red' : 'blue'}>{action}</Tag>
                  ),
                },
                {
                  title: t('permissions_resource_id'),
                  dataIndex: 'resource_id',
                  key: 'resource_id',
                  render: (id: string) => (id === '*' ? t('permissions_resource_all') : id),
                },
              ]}
            />
          </div>
        )}
      </Modal>
    </>
  );
}
