'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  Avatar,
  Button,
  Input,
  Modal,
  Popconfirm,
  Space,
  Transfer,
  Switch,
  Select,
  Table,
  Tag,
  Typography,
  message,
  Spin,
} from 'antd';
import {
  DeleteOutlined,
  ReloadOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  permissionsService,
  type UserInfo,
  type UserDetail,
  type Role,
} from '@/services/permissions';
import { usersService, type User } from '@/services/users';
import { authService } from '@/services/auth';
import { userGroupsService, type UserGroupRow, type UserGroupMemberRow } from '@/services/userGroups';
import UserPermissionsPanel from './UserPermissionsPanel';

const { Text } = Typography;

interface UserManagementProps {
  roles?: Role[];
}

interface UnifiedUserRow extends UserInfo {
  oauth_provider?: string;
  legacy_role?: string;
  avatar?: string;
}

export default function UserManagement({ roles: externalRoles }: UserManagementProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [users, setUsers] = useState<UnifiedUserRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [allRoles, setAllRoles] = useState<Role[]>([]);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [groups, setGroups] = useState<UserGroupRow[]>([]);
  const [groupMembersMap, setGroupMembersMap] = useState<Record<number, Set<number>>>({});
  const [groupAssignOpen, setGroupAssignOpen] = useState(false);
  const [groupAssignSaving, setGroupAssignSaving] = useState(false);
  const [groupAssignUser, setGroupAssignUser] = useState<UnifiedUserRow | null>(null);
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([]);

  const loadUsers = useCallback(
    async (opts?: { silent?: boolean }) => {
      const silent = opts?.silent === true;
      if (!silent) setLoading(true);
      try {
        const [oauthData, rbacData] = await Promise.all([
          usersService.listUsers(page, pageSize, keyword),
          permissionsService.listUsers(page, pageSize, keyword),
        ]);
        const rbacMap = new Map<number, UserInfo>(rbacData.items.map((u) => [u.id, u]));
        const merged = oauthData.list.map((user) => {
          const rbacUser = rbacMap.get(user.id);
          return {
            id: user.id,
            name: user.name || rbacUser?.name || '',
            fullname: user.fullname || rbacUser?.fullname || '',
            email: user.email || rbacUser?.email || '',
            is_active: user.is_active ?? rbacUser?.is_active ?? 1,
            roles: rbacUser?.roles || [],
            gmt_create: user.gmt_create,
            oauth_provider: user.oauth_provider || '',
            legacy_role: user.role,
            avatar: user.avatar,
          } satisfies UnifiedUserRow;
        });
        const oauthIds = new Set(oauthData.list.map((u) => u.id));
        rbacData.items.forEach((rbacUser) => {
          if (oauthIds.has(rbacUser.id)) return;
          merged.push({
            id: rbacUser.id,
            name: rbacUser.name || '',
            fullname: rbacUser.fullname || '',
            email: rbacUser.email || '',
            is_active: rbacUser.is_active ?? 1,
            roles: rbacUser.roles || [],
            gmt_create: rbacUser.gmt_create,
            oauth_provider: '',
            legacy_role: 'normal',
            avatar: '',
          });
        });
        setUsers(merged);
        setTotal(Math.max(oauthData.total, merged.length));
      } catch (e: unknown) {
        const err = e as { response?: { status?: number } };
        if (err.response?.status === 403) {
          message.warning(t('permissions_admin_required'));
        } else {
          message.error(t('permissions_load_users_error') + ': ' + (e as Error).message);
        }
      } finally {
        if (!silent) {
          setLoading(false);
        }
      }
    },
    [page, pageSize, keyword, t],
  );

  const loadRoles = useCallback(async () => {
    if (externalRoles) {
      setAllRoles(externalRoles);
      return;
    }
    try {
      const roles = await permissionsService.listRoles();
      setAllRoles(roles);
    } catch (e: unknown) {
      message.error(t('permissions_load_roles_error') + ': ' + (e as Error).message);
    }
  }, [t, externalRoles]);

  const loadGroups = useCallback(async () => {
    try {
      const groupRows = await userGroupsService.listGroups();
      setGroups(groupRows);
      const memberRows = await Promise.all(
        groupRows.map(async (g) => {
          const members = await userGroupsService.listMembers(g.id);
          return [g.id, members] as const;
        }),
      );
      const nextMap: Record<number, Set<number>> = {};
      memberRows.forEach(([groupId, members]) => {
        nextMap[groupId] = new Set(members.map((m: UserGroupMemberRow) => m.user_id));
      });
      setGroupMembersMap(nextMap);
    } catch (e: unknown) {
      const err = e instanceof Error ? e.message : String(e);
      if (err !== 'NOT_MOUNTED') {
        message.error(t('permissions_load_user_groups_error') + ': ' + err);
      }
      setGroups([]);
      setGroupMembersMap({});
    }
  }, [t]);

  useEffect(() => {
    authService.getCurrentUser().then(setCurrentUser).catch(() => setCurrentUser(null));
    loadRoles();
    loadGroups();
  }, [loadRoles, loadGroups]);

  useEffect(() => {
    loadUsers({ silent: false });
  }, [loadUsers]);

  const openUserDetail = async (userId: number) => {
    setDetailLoading(true);
    setDetailOpen(true);
    try {
      const detail = await permissionsService.getUserDetail(userId);
      setSelectedUser(detail);
    } catch (e: unknown) {
      message.error(t('permissions_load_user_detail_error') + ': ' + (e as Error).message);
      setDetailOpen(false);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleToggleAdmin = async (user: UnifiedUserRow) => {
    const isAdmin = user.roles.includes('admin');
    try {
      if (isAdmin) {
        // Remove admin RBAC role
        const adminRole = allRoles.find((r) => r.name === 'admin');
        if (adminRole) {
          await permissionsService.batchRemoveRoles(user.id, [adminRole.id]);
        }
        // Also set legacy role to normal
        await usersService.updateUser(user.id, { role: 'normal' });
        message.success(t('permissions_unset_admin'));
      } else {
        // Assign admin RBAC role
        const adminRole = allRoles.find((r) => r.name === 'admin');
        if (adminRole) {
          await permissionsService.batchAssignRoles(user.id, [adminRole.id]);
        }
        // Also set legacy role to admin (for checker.py bypass compatibility)
        await usersService.updateUser(user.id, { role: 'admin' });
        message.success(t('permissions_set_admin'));
      }
      await loadUsers({ silent: true });
    } catch (e: unknown) {
      message.error(t('permissions_operation_failed') + ': ' + (e as Error).message);
    }
  };

  const handleToggleActive = async (user: UnifiedUserRow, checked: boolean) => {
    const nextActive = checked ? 1 : 0;
    try {
      await usersService.updateUser(user.id, { is_active: nextActive });
      message.success(checked ? t('permissions_user_enabled') : t('permissions_user_disabled'));
      await loadUsers({ silent: true });
    } catch (e: unknown) {
      message.error(t('permissions_operation_failed') + ': ' + (e as Error).message);
    }
  };

  const handleDelete = async (user: UnifiedUserRow) => {
    if (currentUser && currentUser.id === user.id) {
      message.error(t('permissions_cannot_delete_self'));
      return;
    }
    try {
      await usersService.deleteUser(user.id);
      message.success(t('permissions_user_deleted'));
      await loadUsers({ silent: true });
    } catch (e: unknown) {
      message.error(t('permissions_operation_failed') + ': ' + (e as Error).message);
    }
  };

  const getUserGroupIds = useCallback(
    (userId: number) =>
      groups
        .filter((g) => groupMembersMap[g.id]?.has(userId))
        .map((g) => g.id),
    [groups, groupMembersMap],
  );

  const openGroupAssign = (user: UnifiedUserRow) => {
    setGroupAssignUser(user);
    setSelectedGroupIds(getUserGroupIds(user.id));
    setGroupAssignOpen(true);
  };

  const handleSaveGroupAssign = async () => {
    if (!groupAssignUser) return;
    const currentIds = getUserGroupIds(groupAssignUser.id);
    const toAdd = selectedGroupIds.filter((id) => !currentIds.includes(id));
    const toRemove = currentIds.filter((id) => !selectedGroupIds.includes(id));
    if (toAdd.length === 0 && toRemove.length === 0) {
      setGroupAssignOpen(false);
      return;
    }
    setGroupAssignSaving(true);
    try {
      for (const groupId of toAdd) {
        await userGroupsService.addMembers(groupId, [groupAssignUser.id]);
      }
      for (const groupId of toRemove) {
        await userGroupsService.removeMember(groupId, groupAssignUser.id);
      }
      message.success(t('permissions_user_groups_updated'));
      setGroupAssignOpen(false);
      await loadGroups();
    } catch (e: unknown) {
      message.error(t('permissions_operation_failed') + ': ' + (e as Error).message);
    } finally {
      setGroupAssignSaving(false);
    }
  };

  const handlePageChange = (newPage: number, newPageSize: number) => {
    setPage(newPage);
    setPageSize(newPageSize);
  };

  const columns = [
      {
        title: '',
        dataIndex: 'avatar',
        key: 'avatar',
        width: 64,
        render: (_: string | undefined, record: UnifiedUserRow) => (
          <Avatar src={record.avatar || undefined} icon={!record.avatar ? <UserOutlined /> : undefined} />
        ),
      },
      {
        title: t('permissions_col_name'),
        dataIndex: 'name',
        key: 'name',
        width: 140,
      },
      {
        title: t('permissions_col_fullname'),
        dataIndex: 'fullname',
        key: 'fullname',
        width: 140,
      },
      {
        title: t('permissions_col_email'),
        dataIndex: 'email',
        key: 'email',
        width: 220,
        ellipsis: true,
      },
      {
        title: t('permissions_oauth_provider'),
        dataIndex: 'oauth_provider',
        key: 'oauth_provider',
        width: 120,
        render: (provider: string) => (provider ? <Tag>{provider}</Tag> : <Text type="secondary">-</Text>),
      },
      {
        title: t('permissions_col_status'),
        dataIndex: 'is_active',
        key: 'is_active',
        width: 120,
        render: (active: number, record: UnifiedUserRow) => (
          <Switch
            checked={active === 1}
            checkedChildren={t('active')}
            unCheckedChildren={t('inactive')}
            onChange={(checked) => handleToggleActive(record, checked)}
            size="small"
          />
        ),
      },
      {
        title: t('permissions_col_rbac_roles'),
        dataIndex: 'roles',
        key: 'roles',
        width: 260,
        render: (roleNames: string[]) =>
          roleNames.length > 0 ? (
            <Space wrap>
              {roleNames.map((r) => (
                <Tag key={r} color="blue">
                  {r}
                </Tag>
              ))}
            </Space>
          ) : (
            <Text type="secondary">—</Text>
          ),
      },
      {
        title: t('permissions_user_groups'),
        key: 'user_groups',
        width: 220,
        render: (_: unknown, record: UnifiedUserRow) => {
          const names = groups
            .filter((g) => groupMembersMap[g.id]?.has(record.id))
            .map((g) => g.name);
          return names.length > 0 ? (
            <Space wrap>
              {names.map((name) => (
                <Tag key={name} color="cyan">
                  {name}
                </Tag>
              ))}
            </Space>
          ) : (
            <Text type="secondary">—</Text>
          );
        },
      },
      {
        title: t('permissions_col_actions'),
        key: 'actions',
        width: 360,
        render: (_: unknown, record: UnifiedUserRow) => (
          <Space size="small">
            <Button type="link" size="small" onClick={() => openGroupAssign(record)}>
              {t('permissions_add_to_group')}
            </Button>
            <Button type="link" size="small" onClick={() => openUserDetail(record.id)}>
              {t('permissions_add_authorization')}
            </Button>
            <Button type="link" size="small" onClick={() => handleToggleAdmin(record)}>
              {record.roles.includes('admin') ? t('permissions_unset_admin') : t('permissions_set_admin')}
            </Button>
            {currentUser?.role === 'admin' && record.id !== currentUser.id && (
              <Popconfirm
                title={t('permissions_delete_user_confirm')}
                onConfirm={() => handleDelete(record)}
              >
                <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                  {t('delete')}
                </Button>
              </Popconfirm>
            )}
          </Space>
        ),
      },
    ];

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-3">
        <Space>
          <TeamOutlined className="text-xl" />
          <Text strong className="text-lg">
            {t('permissions_user_management')}
          </Text>
        </Space>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => loadUsers({ silent: true })}
          loading={loading}
        >
          {t('refresh')}
        </Button>
      </div>

      <div className="mb-4 flex items-center gap-2">
        <Input.Search
          placeholder={t('permissions_keyword_placeholder')}
          allowClear
          enterButton={t('search')}
          onSearch={(v) => {
            setKeyword(v || '');
            setPage(1);
          }}
          style={{ width: 380 }}
        />
      </div>

      <Table<UnifiedUserRow>
        loading={loading}
        rowKey="id"
        dataSource={users}
        pagination={{
          current: page,
          pageSize: pageSize,
          total: total,
          onChange: handlePageChange,
          showSizeChanger: true,
          showTotal: (total) => t('total_items', { total }),
        }}
        columns={columns}
        scroll={{ x: 1450 }}
      />

      <Modal
        title={
          groupAssignUser
            ? `${t('permissions_add_to_group')} - ${groupAssignUser.name || groupAssignUser.email}`
            : t('permissions_add_to_group')
        }
        open={groupAssignOpen}
        onOk={handleSaveGroupAssign}
        onCancel={() => {
          setGroupAssignOpen(false);
          setGroupAssignUser(null);
          setSelectedGroupIds([]);
        }}
        confirmLoading={groupAssignSaving}
        destroyOnClose
      >
        <Select
          mode="multiple"
          allowClear
          showSearch
          optionFilterProp="label"
          value={selectedGroupIds}
          onChange={(v) => setSelectedGroupIds(v as number[])}
          options={groups.map((g) => ({ value: g.id, label: g.name }))}
          placeholder={t('permissions_select_groups')}
          className="w-full"
        />
      </Modal>

      {/* User Detail Modal */}
      <Modal
        title={selectedUser ? `${t('permissions_user_detail')}: ${selectedUser.name}` : ''}
        open={detailOpen}
        onCancel={() => {
          setDetailOpen(false);
          setSelectedUser(null);
        }}
        footer={null}
        width={700}
        destroyOnClose
      >
        {detailLoading ? (
          <div className="text-center py-8">
            <Spin />
          </div>
        ) : selectedUser ? (
          <div className="space-y-4">
            <UserRolePanel
              user={selectedUser}
              allRoles={allRoles}
              onSuccess={() => {
                loadUsers({ silent: true });
                openUserDetail(selectedUser.id);
              }}
            />
            <UserPermissionsPanel userId={selectedUser.id} />
          </div>
        ) : null}
      </Modal>
    </div>
  );
}

// User Role Panel Component
interface UserRolePanelProps {
  user: UserDetail;
  allRoles: Role[];
  onSuccess: () => void;
}

function UserRolePanel({ user, allRoles, onSuccess }: UserRolePanelProps) {
  const { t } = useTranslation();
  const [targetKeys, setTargetKeys] = useState<React.Key[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    // 初始化已选中的角色（Transfer 需要字符串 key）
    const currentRoleIds = user.direct_roles.map((r) => String(r.id));
    setTargetKeys(currentRoleIds);
  }, [user.direct_roles]);

  const handleSave = async () => {
    const currentRoleIds = user.direct_roles.map((r) => r.id);
    const newRoleIds = targetKeys.map((k) => Number(k));

    // 计算需要添加和移除的角色
    const toAdd = newRoleIds.filter((id) => !currentRoleIds.includes(id));
    const toRemove = currentRoleIds.filter((id) => !newRoleIds.includes(id));

    // 如果没有变化，直接返回
    if (toAdd.length === 0 && toRemove.length === 0) {
      message.info(t('permissions_no_changes'));
      return;
    }

    setSaving(true);
    try {
      if (toAdd.length > 0) {
        await permissionsService.batchAssignRoles(user.id, toAdd);
      }
      if (toRemove.length > 0) {
        await permissionsService.batchRemoveRoles(user.id, toRemove);
      }
      message.success(t('permissions_roles_updated'));
      onSuccess();
    } catch (e: unknown) {
      message.error(t('permissions_roles_update_error') + ': ' + (e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  // 构建 Transfer 的数据源
  // 注意：不禁用系统角色，管理员应该能够分配所有角色
  const mockData = allRoles.map((role) => ({
    key: String(role.id),
    title: role.name,
    description: role.description || '',
  }));

  return (
    <div>
      <div className="mb-4">
        <Text type="secondary">{t('permissions_assign_roles_hint')}</Text>
      </div>

      <Transfer
        dataSource={mockData}
        targetKeys={targetKeys}
        onChange={setTargetKeys}
        titles={[t('permissions_available_roles'), t('permissions_assigned_roles')]}
        render={(item) => `${item.title} (${item.description || '无描述'})`}
        listStyle={{ width: 280, height: 300 }}
        operations={[t('assign'), t('remove')]}
      />

      <div className="mt-4 flex justify-end">
        <Space>
          <Button onClick={() => setTargetKeys(user.direct_roles.map((r) => String(r.id)))}>
            {t('reset')}
          </Button>
          <Button type="primary" onClick={handleSave} loading={saving}>
            {t('save')}
          </Button>
        </Space>
      </div>

      {/* Current roles display */}
      <div className="mt-6">
        <Text strong>{t('permissions_current_roles')}:</Text>
        <div className="mt-2">
          {user.direct_roles.length > 0 ? (
            <Space wrap>
              {user.direct_roles.map((r) => (
                <Tag key={r.id} color="blue">
                  {r.name}
                  {r.is_system === 1 && ` (${t('system_role')})`}
                </Tag>
              ))}
            </Space>
          ) : (
            <Text type="secondary">{t('permissions_no_roles')}</Text>
          )}
        </div>
      </div>

      {/* Group roles display */}
      {user.group_roles.length > 0 && (
        <div className="mt-4">
          <Text type="secondary">{t('permissions_inherited_roles')}:</Text>
          <div className="mt-2">
            <Space wrap>
              {user.group_roles.map((r) => (
                <Tag key={r.id} color="green">
                  {r.name} ({t('from_group')})
                </Tag>
              ))}
            </Space>
          </div>
        </div>
      )}

      {/* Effective permissions display */}
      <div className="mt-4">
        <Text type="secondary">{t('permissions_effective_permissions')}:</Text>
        <div className="mt-2">
          {Object.keys(user.effective_permissions).length > 0 ? (
            <Space direction="vertical" align="start">
              {Object.entries(user.effective_permissions).map(([resource, actions]) => (
                <Tag key={resource} color="purple">
                  {resource}: {actions.join(', ')}
                </Tag>
              ))}
            </Space>
          ) : (
            <Text type="secondary">{t('permissions_no_permissions')}</Text>
          )}
        </div>
      </div>
    </div>
  );
}