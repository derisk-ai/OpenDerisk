'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { PlusOutlined, TeamOutlined, UserAddOutlined } from '@ant-design/icons';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import {
  userGroupsService,
  type UserGroupRow,
  type UserGroupMemberRow,
} from '@/services/userGroups';
import { usersService, type User } from '@/services/users';

const { Text } = Typography;

type Props = {
  /** From plugin catalog: switch is on in derisk.json */
  catalogEnabled: boolean;
};

export default function UserGroupsPluginPanel({ catalogEnabled }: Props) {
  const { t } = useTranslation();
  /** Full-table Spin blocks clicks (same List/Table issue as plugin market). */
  const [tableBlocking, setTableBlocking] = useState(() => catalogEnabled);
  const [refreshing, setRefreshing] = useState(false);
  const [groups, setGroups] = useState<UserGroupRow[]>([]);
  const [apiState, setApiState] = useState<'idle' | 'ok' | 'not_mounted' | 'error'>('idle');
  const [createOpen, setCreateOpen] = useState(false);
  const [membersOpen, setMembersOpen] = useState(false);
  const [activeGroup, setActiveGroup] = useState<UserGroupRow | null>(null);
  const [members, setMembers] = useState<UserGroupMemberRow[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [userOptions, setUserOptions] = useState<User[]>([]);
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);
  const [manualUserId, setManualUserId] = useState<number | null>(null);
  const [allUsersCache, setAllUsersCache] = useState<User[]>([]);
  const [memberCache, setMemberCache] = useState<Record<number, UserGroupMemberRow[]>>({});
  const [membersPrefetching, setMembersPrefetching] = useState(false);
  const [createForm] = Form.useForm();

  const loadGroups = useCallback(async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent === true;
    if (silent) {
      setRefreshing(true);
    } else {
      setTableBlocking(true);
    }
    setApiState('idle');
    try {
      const [data, users] = await Promise.all([
        userGroupsService.listGroups(),
        usersService.listAllUsers('').catch(() => [] as User[]),
      ]);
      setAllUsersCache(users);
      setGroups(data);
      setApiState('ok');

      if (data.length > 0) {
        setMembersPrefetching(true);
        try {
          const pairs = await Promise.all(
            data.map(async (g) => {
              try {
                const ms = await userGroupsService.listMembers(g.id);
                return [g.id, ms] as const;
              } catch {
                return [g.id, []] as const;
              }
            }),
          );
          setMemberCache(Object.fromEntries(pairs));
        } catch {
          setMemberCache({});
        } finally {
          setMembersPrefetching(false);
        }
      } else {
        setMemberCache({});
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg === 'NOT_MOUNTED') {
        setApiState('not_mounted');
        setGroups([]);
        setMemberCache({});
      } else {
        setApiState('error');
        setGroups([]);
        setMemberCache({});
        message.error(t('plugin_user_groups_load_error') + ': ' + msg);
      }
    } finally {
      if (silent) {
        setRefreshing(false);
      } else {
        setTableBlocking(false);
      }
    }
  }, [t]);

  useEffect(() => {
    if (!catalogEnabled) {
      setGroups([]);
      setApiState('idle');
      setTableBlocking(false);
      return;
    }
    loadGroups({ silent: false });
  }, [catalogEnabled, loadGroups]);

  const openMembers = async (g: UserGroupRow) => {
    setActiveGroup(g);
    setMembersOpen(true);
    setSelectedUserIds([]);
    if (allUsersCache.length > 0) {
      setUserOptions(allUsersCache);
    }
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
      if (list.length === 0) {
        message.warning(t('plugin_user_groups_user_list_empty'));
      }
    } catch (e: unknown) {
      setUserOptions([]);
      const detail = axios.isAxiosError(e)
        ? (typeof e.response?.data === 'object' &&
            e.response?.data !== null &&
            'detail' in e.response.data
            ? String((e.response.data as { detail: unknown }).detail)
            : e.message)
        : e instanceof Error
          ? e.message
          : String(e);
      message.error(t('plugin_user_groups_user_list_load_failed') + ': ' + detail);
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

  const handleCreate = async () => {
    try {
      const v = await createForm.validateFields();
      await userGroupsService.createGroup(v.name, v.description);
      message.success(t('plugin_user_groups_created'));
      setCreateOpen(false);
      createForm.resetFields();
      await loadGroups({ silent: true });
    } catch (e: unknown) {
      if ((e as { errorFields?: unknown })?.errorFields) return;
      message.error(String(e));
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await userGroupsService.deleteGroup(id);
      message.success(t('plugin_user_groups_deleted'));
      await loadGroups({ silent: true });
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
      setMemberCache((prev) => ({ ...prev, [activeGroup.id]: next }));
      await loadGroups({ silent: true });
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
      setMemberCache((prev) => ({ ...prev, [activeGroup.id]: next }));
      await loadGroups({ silent: true });
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
      setMemberCache((prev) => ({ ...prev, [activeGroup.id]: next }));
      await loadGroups({ silent: true });
    } catch (e: unknown) {
      message.error(String(e));
    }
  };

  if (!catalogEnabled) {
    return (
      <Alert
        type="warning"
        showIcon
        className="mt-3"
        message={t('plugin_user_groups_disabled_hint')}
      />
    );
  }

  if (apiState === 'not_mounted') {
    return (
      <Alert
        type="error"
        showIcon
        className="mt-3"
        message={t('plugin_user_groups_not_mounted_title')}
        description={t('plugin_user_groups_not_mounted_desc')}
      />
    );
  }

  return (
    <div className="mt-4 pt-4 border-t border-gray-100 dark:border-neutral-800">
      <div className="flex items-center justify-between mb-3">
        <Space>
          <TeamOutlined />
          <Text strong>{t('plugin_user_groups_admin_title')}</Text>
        </Space>
        <Space>
          <Button
            size="small"
            onClick={() => loadGroups({ silent: true })}
            loading={refreshing}
          >
            {t('plugin_user_groups_refresh')}
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => setCreateOpen(true)}
          >
            {t('plugin_user_groups_new_group')}
          </Button>
        </Space>
      </div>
      <Text type="secondary" className="block mb-2 text-xs">
        {t('plugin_user_groups_admin_hint')}
      </Text>
      <Table<UserGroupRow>
        size="small"
        loading={tableBlocking}
        rowKey="id"
        pagination={false}
        dataSource={groups}
        scroll={{ x: 900 }}
        columns={[
          { title: t('plugin_user_groups_col_name'), dataIndex: 'name', key: 'name', width: 140 },
          {
            title: t('plugin_user_groups_col_desc'),
            dataIndex: 'description',
            key: 'description',
            ellipsis: true,
            width: 160,
          },
          {
            title: t('plugin_user_groups_col_members'),
            dataIndex: 'member_count',
            key: 'member_count',
            width: 72,
            align: 'center' as const,
          },
          {
            title: t('plugin_user_groups_col_member_list'),
            key: 'member_list',
            render: (_, row) => {
              if (membersPrefetching && memberCache[row.id] === undefined) {
                return <Spin size="small" />;
              }
              const list = memberCache[row.id];
              if (!list || list.length === 0) {
                return <Text type="secondary">—</Text>;
              }
              return (
                <div className="max-h-[7.5rem] overflow-y-auto pr-1">
                  <Space wrap size={[4, 4]}>
                    {list.map((m) => (
                      <Tag key={m.id} className="m-0">
                        {getUserLabel(m.user_id)}
                        <span className="ml-1 opacity-60">#{m.user_id}</span>
                      </Tag>
                    ))}
                  </Space>
                </div>
              );
            },
          },
          {
            title: t('plugin_user_groups_col_actions'),
            key: 'actions',
            width: 168,
            fixed: 'right' as const,
            render: (_, row) => (
              <Space>
                <Button type="link" size="small" onClick={() => openMembers(row)}>
                  {t('plugin_user_groups_manage_members')}
                </Button>
                <Popconfirm
                  title={t('plugin_user_groups_delete_confirm')}
                  onConfirm={() => handleDelete(row.id)}
                >
                  <Button type="link" size="small" danger>
                    {t('plugin_user_groups_delete')}
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={t('plugin_user_groups_new_group')}
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => {
          setCreateOpen(false);
          createForm.resetFields();
        }}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical">
          <Form.Item
            name="name"
            label={t('plugin_user_groups_col_name')}
            rules={[{ required: true, message: t('plugin_user_groups_name_required') }]}
          >
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="description" label={t('plugin_user_groups_col_desc')}>
            <Input.TextArea rows={3} maxLength={2000} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={
          activeGroup
            ? `${t('plugin_user_groups_members')} — ${activeGroup.name}`
            : t('plugin_user_groups_members')
        }
        open={membersOpen}
        onCancel={() => {
          setMembersOpen(false);
          setActiveGroup(null);
          setManualUserId(null);
        }}
        footer={null}
        width={640}
        destroyOnClose
      >
        <div className="mb-3 space-y-3">
          <Space wrap className="w-full">
            <Select
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('plugin_user_groups_select_users')}
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
              {t('plugin_user_groups_add_to_group')}
            </Button>
          </Space>
          <Space wrap align="center">
            <Text type="secondary" className="text-xs">
              {t('plugin_user_groups_add_by_id_hint')}
            </Text>
            <InputNumber
              min={1}
              precision={0}
              placeholder={t('plugin_user_groups_add_by_id_placeholder')}
              value={manualUserId ?? undefined}
              onChange={(v) => setManualUserId(typeof v === 'number' ? v : null)}
              style={{ width: 140 }}
            />
            <Button onClick={handleAddMemberById}>{t('plugin_user_groups_add_by_id')}</Button>
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
              title: 'user_id',
              dataIndex: 'user_id',
              width: 100,
            },
            {
              title: t('plugin_user_groups_col_user'),
              key: 'label',
              render: (_, r) => getUserLabel(r.user_id),
            },
            {
              title: t('plugin_user_groups_col_actions'),
              key: 'rm',
              width: 100,
              render: (_, r) => (
                <Popconfirm
                  title={t('plugin_user_groups_remove_member_confirm')}
                  onConfirm={() => handleRemoveMember(r.user_id)}
                >
                  <Button type="link" size="small" danger>
                    {t('plugin_user_groups_remove')}
                  </Button>
                </Popconfirm>
              ),
            },
          ]}
        />
      </Modal>
    </div>
  );
}
