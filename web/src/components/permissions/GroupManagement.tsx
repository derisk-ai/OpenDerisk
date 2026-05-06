'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  Divider,
  Drawer,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tabs,
  Typography,
  message,
  Alert,
} from 'antd';
import { PlusOutlined, ReloadOutlined, TeamOutlined, UserAddOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  userGroupsService,
  type UserGroupRow,
  type UserGroupMemberRow,
} from '@/services/userGroups';
import { usersService, type User } from '@/services/users';
import { permissionsService, type Role } from '@/services/permissions';

const { Text } = Typography;

interface GroupManagementProps {
  roles: Role[];
}

export default function GroupManagement({ roles }: GroupManagementProps) {
  const { t } = useTranslation();
  const [groups, setGroups] = useState<UserGroupRow[]>([]);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [panelTab, setPanelTab] = useState<'members' | 'roles'>('members');
  const [activeGroup, setActiveGroup] = useState<UserGroupRow | null>(null);
  const [members, setMembers] = useState<UserGroupMemberRow[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [userOptions, setUserOptions] = useState<User[]>([]);
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);
  const [manualUserId, setManualUserId] = useState<number | null>(null);
  const [allUsersCache, setAllUsersCache] = useState<User[]>([]);
  const [groupRoles, setGroupRoles] = useState<Role[]>([]);
  const [selectedRoleIds, setSelectedRoleIds] = useState<number[]>([]);
  const [rolesSaving, setRolesSaving] = useState(false);
  const [groupRoleNamesMap, setGroupRoleNamesMap] = useState<Record<number, string[]>>({});
  const [createForm] = Form.useForm();

  const loadGroups = useCallback(async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent === true;
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      // Load groups first, handle NOT_MOUNTED separately
      let data: UserGroupRow[] = [];
      try {
        data = await userGroupsService.listGroups();
      } catch (e) {
        const errMsg = e instanceof Error ? e.message : String(e);
        if (errMsg === 'NOT_MOUNTED') {
          // Feature not enabled, show empty state
          data = [];
        } else {
          throw e;
        }
      }

      // Load users
      let users: User[] = [];
      try {
        users = await usersService.listAllUsers('');
      } catch {
        users = [];
      }

      const roleAssignments = await Promise.all(
        data.map(async (g) => {
          try {
            const assignments = await permissionsService.listGroupRoles(g.id);
            return [g.id, assignments.map((row) => row.role_name)] as const;
          } catch {
            return [g.id, []] as const;
          }
        }),
      );

      const roleMap: Record<number, string[]> = {};
      roleAssignments.forEach(([groupId, roleNames]) => {
        roleMap[groupId] = roleNames;
      });

      setAllUsersCache(users);
      setGroups(data);
      setGroupRoleNamesMap(roleMap);
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : String(e);
      if (errMsg !== 'NOT_MOUNTED') {
        message.error(String(e));
      }
    } finally {
      if (silent) {
        setRefreshing(false);
      } else {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  const openMembers = async (g: UserGroupRow) => {
    setActiveGroup(g);
    setPanelOpen(true);
    setPanelTab('members');
    setSelectedUserIds([]);
    setMembersLoading(true);
    try {
      const m = await userGroupsService.listMembers(g.id);
      setMembers(m);
    } catch (e: unknown) {
      message.error(String(e));
      setMembers([]);
    } finally {
      setMembersLoading(false);
    }
    try {
      const list = await usersService.listAllUsers('');
      setUserOptions(list);
    } catch {
      setUserOptions([]);
    }
  };

  const openRoles = async (g: UserGroupRow) => {
    setActiveGroup(g);
    setPanelOpen(true);
    setPanelTab('roles');
    try {
      const assignments = await permissionsService.listGroupRoles(g.id);
      const assignedRoleIds = assignments.map((item) => item.role_id);
      const assignedRoles = roles.filter((r) => assignedRoleIds.includes(r.id));
      setGroupRoles(assignedRoles);
      setSelectedRoleIds(assignedRoleIds);
    } catch {
      setGroupRoles([]);
      setSelectedRoleIds([]);
      message.error(t('permissions_load_roles_error') || '加载角色失败');
    }
  };

  const userLabelById = useMemo(() => {
    const m = new Map<number, string>();
    allUsersCache.forEach((u) => {
      m.set(u.id, u.name || u.email || u.fullname || `#${u.id}`);
    });
    userOptions.forEach((u) => {
      m.set(u.id, u.name || u.email || u.fullname || `#${u.id}`);
    });
    return m;
  }, [allUsersCache, userOptions]);

  const getUserLabel = useCallback(
    (userId: number) => userLabelById.get(userId) ?? `#${userId}`,
    [userLabelById],
  );

  const filteredGroups = useMemo(() => {
    const term = keyword.trim().toLowerCase();
    if (!term) return groups;
    return groups.filter((g) => {
      const name = (g.name || '').toLowerCase();
      const desc = (g.description || '').toLowerCase();
      return name.includes(term) || desc.includes(term);
    });
  }, [groups, keyword]);

  const handleCreate = async () => {
    try {
      const v = await createForm.validateFields();
      await userGroupsService.createGroup(v.name, v.description);
      message.success(t('plugin_user_groups_created'));
      setCreateOpen(false);
      createForm.resetFields();
      await loadGroups();
    } catch (e: unknown) {
      if ((e as { errorFields?: unknown })?.errorFields) return;
      message.error(String(e));
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await userGroupsService.deleteGroup(id);
      message.success(t('plugin_user_groups_deleted'));
      await loadGroups();
    } catch (e: unknown) {
      message.error(String(e));
    }
  };

  const handleAddMembers = async () => {
    if (!activeGroup || selectedUserIds.length === 0) return;
    try {
      const n = await userGroupsService.addMembers(activeGroup.id, selectedUserIds);
      message.success(t('plugin_user_groups_members_added', { count: n }));
      setSelectedUserIds([]);
      const next = await userGroupsService.listMembers(activeGroup.id);
      setMembers(next);
      await loadGroups();
    } catch (e: unknown) {
      message.error(String(e));
    }
  };

  const handleAddMemberById = async () => {
    if (!activeGroup || manualUserId == null || manualUserId < 1) {
      message.warning(t('plugin_user_groups_invalid_user_id'));
      return;
    }
    const uid = Math.floor(manualUserId);
    try {
      const n = await userGroupsService.addMembers(activeGroup.id, [uid]);
      if (n === 0) {
        message.info(t('plugin_user_groups_already_member'));
      } else {
        message.success(t('plugin_user_groups_members_added', { count: n }));
      }
      setManualUserId(null);
      const next = await userGroupsService.listMembers(activeGroup.id);
      setMembers(next);
      await loadGroups();
    } catch (e: unknown) {
      message.error(String(e));
    }
  };

  const handleRemoveMember = async (userId: number) => {
    if (!activeGroup) return;
    try {
      await userGroupsService.removeMember(activeGroup.id, userId);
      message.success(t('plugin_user_groups_member_removed'));
      const next = await userGroupsService.listMembers(activeGroup.id);
      setMembers(next);
      await loadGroups();
    } catch (e: unknown) {
      message.error(String(e));
    }
  };

  const handleAssignRoles = async () => {
    if (!activeGroup) return;
    const currentRoleIds = groupRoles.map((r) => r.id);
    const toAdd = selectedRoleIds.filter((id) => !currentRoleIds.includes(id));
    const toRemove = currentRoleIds.filter((id) => !selectedRoleIds.includes(id));

    if (toAdd.length === 0 && toRemove.length === 0) {
      setPanelOpen(false);
      return;
    }

    setRolesSaving(true);
    try {
      for (const roleId of toAdd) {
        await permissionsService.assignRoleToGroup(activeGroup.id, roleId);
      }
      for (const roleId of toRemove) {
        await permissionsService.removeGroupRole(activeGroup.id, roleId);
      }
      message.success(t('permissions_roles_updated'));
      setPanelOpen(false);
      await loadGroups({ silent: true });
    } catch (e: unknown) {
      message.error(String(e));
    } finally {
      setRolesSaving(false);
    }
  };

  const handleClosePanel = () => {
    setPanelOpen(false);
    setActiveGroup(null);
    setManualUserId(null);
  };

  const currentRoleNames = activeGroup ? groupRoleNamesMap[activeGroup.id] || [] : [];
  const currentMemberCount = activeGroup
    ? panelTab === 'members'
      ? members.length
      : (activeGroup.member_count ?? 0)
    : 0;

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-3">
        <Space>
          <TeamOutlined className="text-xl" />
          <Text strong className="text-lg">
            {t('permissions_user_groups') || '用户组管理'}
          </Text>
        </Space>
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => loadGroups({ silent: true })}
            loading={refreshing}
          >
            {t('refresh')}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            {t('plugin_user_groups_new_group')}
          </Button>
        </Space>
      </div>

      <Alert
        type="info"
        showIcon
        className="mb-4"
        message={t('permissions_user_groups') || '用户组'}
        description={t('permissions_user_groups_hint') || '用户组用于批量管理用户权限。将角色分配给用户组后，该组内的所有用户将继承这些角色。'}
      />

      <div className="mb-4 flex items-center justify-between gap-3">
        <Input.Search
          allowClear
          placeholder={t('permissions_keyword_placeholder') || '请输入关键词搜索'}
          onSearch={(v) => setKeyword(v || '')}
          onChange={(e) => setKeyword(e.target.value || '')}
          value={keyword}
          style={{ width: 380 }}
        />
        <Text type="secondary">
          {(t('total_items', { total: filteredGroups.length }) as string) || `共 ${filteredGroups.length} 条`}
        </Text>
      </div>

      <Table<UserGroupRow>
        loading={loading}
        rowKey="id"
        pagination={false}
        dataSource={filteredGroups}
        columns={[
          {
            title: t('plugin_user_groups_col_name') || '组名称',
            dataIndex: 'name',
            key: 'name',
            width: 240,
            render: (name: string, row) => (
              <div className="flex flex-col">
                <Text strong>{name}</Text>
                <Text type="secondary" className="text-xs">
                  {row.description || '-'}
                </Text>
              </div>
            ),
          },
          {
            title: t('plugin_user_groups_col_desc') || '描述',
            dataIndex: 'description',
            key: 'description',
            ellipsis: true,
          },
          {
            title: t('plugin_user_groups_col_members') || '成员数',
            dataIndex: 'member_count',
            key: 'member_count',
            width: 100,
            render: (count) => <Tag color="blue">{count ?? 0}</Tag>,
          },
          {
            title: t('permissions_col_rbac_roles') || 'RBAC 角色',
            key: 'rbac_roles',
            width: 260,
            render: (_: unknown, row) => {
              const roleNames = groupRoleNamesMap[row.id] || [];
              return roleNames.length > 0 ? (
                <Space wrap>
                  {roleNames.map((name) => (
                    <Tag key={name} color="purple">
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
            title: t('permissions_col_actions') || '操作',
            key: 'actions',
            width: 320,
            render: (_, row) => (
              <Space>
                <Button type="link" size="small" onClick={() => openMembers(row)} className="px-0">
                  {t('permissions_manage_members') || '管理成员'}
                </Button>
                <Divider type="vertical" className="mx-0" />
                <Button type="link" size="small" onClick={() => openRoles(row)} className="px-0">
                  {t('permissions_add_authorization') || '新增授权'}
                </Button>
                <Divider type="vertical" className="mx-0" />
                <Popconfirm
                  title={t('plugin_user_groups_delete_confirm')}
                  onConfirm={() => handleDelete(row.id)}
                >
                  <Button type="link" size="small" danger className="px-0">
                    {t('delete') || '删除用户组'}
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      {/* Create Group Modal */}
      <Modal
        title={t('plugin_user_groups_new_group')}
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
            label={t('plugin_user_groups_col_name') || '组名称'}
            rules={[{ required: true, message: t('plugin_user_groups_name_required') }]}
          >
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="description" label={t('plugin_user_groups_col_desc') || '描述'}>
            <Input.TextArea rows={3} maxLength={2000} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={
          activeGroup
            ? `${activeGroup.name} - ${t('permissions_user_groups') || '用户组'}`
            : t('permissions_user_groups') || '用户组'
        }
        placement="right"
        width={820}
        open={panelOpen}
        onClose={handleClosePanel}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={handleClosePanel}>{t('cancel') || '取消'}</Button>
            {panelTab === 'roles' && (
              <Button type="primary" onClick={handleAssignRoles} loading={rolesSaving}>
                {t('save') || '保存'}
              </Button>
            )}
          </div>
        }
        destroyOnClose
      >
        {activeGroup && (
          <Card size="small" className="mb-4">
            <div className="flex flex-wrap items-center gap-4">
              <Text type="secondary">
                {t('plugin_user_groups_col_members') || '成员数'}: <Text strong>{currentMemberCount}</Text>
              </Text>
              <Text type="secondary">
                {t('permissions_col_rbac_roles') || 'RBAC 角色'}: <Text strong>{currentRoleNames.length}</Text>
              </Text>
              {currentRoleNames.length > 0 && (
                <Space size={[4, 4]} wrap>
                  {currentRoleNames.slice(0, 6).map((name) => (
                    <Tag key={name} color="purple">
                      {name}
                    </Tag>
                  ))}
                  {currentRoleNames.length > 6 && (
                    <Tag>+{currentRoleNames.length - 6}</Tag>
                  )}
                </Space>
              )}
            </div>
          </Card>
        )}

        <Tabs
          activeKey={panelTab}
          onChange={(key) => setPanelTab(key as 'members' | 'roles')}
          items={[
            {
              key: 'members',
              label: t('permissions_manage_members') || '管理成员',
              children: (
                <>
                  <div className="mb-3 space-y-3">
                    <Space wrap className="w-full">
                      <Select
                        mode="multiple"
                        allowClear
                        showSearch
                        optionFilterProp="label"
                        placeholder={t('plugin_user_groups_select_users') || '选择用户'}
                        className="min-w-[240px]"
                        style={{ minWidth: 280 }}
                        value={selectedUserIds}
                        onChange={(v) => setSelectedUserIds(v as number[])}
                        options={userOptions.map((u) => ({
                          value: u.id,
                          label: `${u.name || u.email || u.id} (#${u.id})`,
                        }))}
                      />
                      <Button
                        type="primary"
                        icon={<UserAddOutlined />}
                        onClick={handleAddMembers}
                        disabled={selectedUserIds.length === 0}
                      >
                        {t('permissions_add_members') || '添加成员'}
                      </Button>
                    </Space>
                    <Space wrap align="center">
                      <Text type="secondary" className="text-xs">
                        {t('permissions_add_by_id_hint') || '或输入用户 ID:'}
                      </Text>
                      <Input
                        type="number"
                        min={1}
                        placeholder={t('permissions_user_id') || '用户 ID'}
                        value={manualUserId ?? undefined}
                        onChange={(e) => setManualUserId(e.target.value ? parseInt(e.target.value) : null)}
                        style={{ width: 100 }}
                      />
                      <Button onClick={handleAddMemberById}>{t('add') || '添加'}</Button>
                    </Space>
                  </div>
                  <Table<UserGroupMemberRow>
                    size="small"
                    loading={membersLoading}
                    rowKey="id"
                    pagination={false}
                    dataSource={members}
                    columns={[
                      {
                        title: 'ID',
                        dataIndex: 'user_id',
                        width: 80,
                      },
                      {
                        title: t('permissions_col_user') || '用户',
                        key: 'label',
                        render: (_, r) => getUserLabel(r.user_id),
                      },
                      {
                        title: t('permissions_col_actions') || '操作',
                        key: 'rm',
                        width: 80,
                        render: (_, r) => (
                          <Popconfirm
                            title={t('permissions_remove_member_confirm')}
                            onConfirm={() => handleRemoveMember(r.user_id)}
                          >
                            <Button type="link" size="small" danger>
                              {t('delete') || '删除'}
                            </Button>
                          </Popconfirm>
                        ),
                      },
                    ]}
                  />
                </>
              ),
            },
            {
              key: 'roles',
              label: t('permissions_add_authorization') || '新增授权',
              children: (
                <>
                  <Alert
                    type="info"
                    showIcon
                    className="mb-3"
                    message={
                      t('permissions_group_roles_hint') || '为用户组分配角色后，该组内所有用户将继承这些角色。'
                    }
                  />
                  <Form layout="vertical">
                    <Form.Item label={t('permissions_available_roles') || '可用角色'}>
                      <Select
                        mode="multiple"
                        allowClear
                        value={selectedRoleIds}
                        onChange={(v) => setSelectedRoleIds(v as number[])}
                        placeholder={t('permissions_select_roles') || '选择角色'}
                        options={roles.map((r) => ({
                          value: r.id,
                          label: r.name,
                        }))}
                      />
                    </Form.Item>
                  </Form>
                </>
              ),
            },
          ]}
        />
      </Drawer>
    </div>
  );
}