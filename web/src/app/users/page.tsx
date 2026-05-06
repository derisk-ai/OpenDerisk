'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Avatar, Badge, Button, Input, Modal, Space, Switch, Table, Tag, message } from 'antd';
import { DeleteOutlined, SearchOutlined, UserOutlined } from '@ant-design/icons';
import { usersService, User } from '@/services/users';
import { authService } from '@/services/auth';
import { useRouter } from 'next/navigation';

const { Search } = Input;

export default function UsersPage() {
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(false);
  const [oauthEnabled, setOauthEnabled] = useState<boolean | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const checkedRef = useRef(false);

  useEffect(() => {
    if (checkedRef.current) return;
    checkedRef.current = true;
    authService.getOAuthStatus().then((status) => {
      setOauthEnabled(status.enabled);
      if (!status.enabled) {
        router.replace('/');
      }
    });
    // Get current user info
    authService.getCurrentUser().then((user) => {
      setCurrentUser(user);
    }).catch(() => {
      // Ignore error
    });
  }, [router]);

  useEffect(() => {
    if (oauthEnabled) fetchUsers();
  }, [oauthEnabled, page, keyword]);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const result = await usersService.listUsers(page, pageSize, keyword);
      setUsers(result.list);
      setTotal(result.total);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '加载用户列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleRole = async (user: User) => {
    const newRole = user.role === 'admin' ? 'normal' : 'admin';
    try {
      const updated = await usersService.updateUser(user.id, { role: newRole });
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
      message.success(`已${newRole === 'admin' ? '设为' : '取消'}管理员`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败');
    }
  };

  const handleToggleActive = async (user: User, checked: boolean) => {
    const newActive = checked ? 1 : 0;
    try {
      const updated = await usersService.updateUser(user.id, { is_active: newActive });
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
      message.success(checked ? '用户已启用' : '用户已禁用');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败');
    }
  };

  const handleDelete = async (user: User) => {
    // Prevent self-deletion
    if (currentUser && currentUser.id === user.id) {
      message.error('不能删除自己的账号');
      return;
    }

    Modal.confirm({
      title: '确认删除用户',
      content: `确定要删除用户 "${user.name || user.fullname || user.email || user.id}" 吗？此操作将禁用该用户账号。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await usersService.deleteUser(user.id);
          message.success('用户已删除');
          fetchUsers(); // Refresh list
        } catch (e: any) {
          message.error(e?.response?.data?.detail || '删除失败');
        }
      },
    });
  };

  const columns = [
    {
      title: '头像',
      dataIndex: 'avatar',
      key: 'avatar',
      width: 64,
      render: (_: any, record: User) => (
        <Avatar
          src={record.avatar || undefined}
          icon={!record.avatar ? <UserOutlined /> : undefined}
          size={36}
          className="bg-gradient-to-tr from-[#31afff] to-[#1677ff]"
        />
      ),
    },
    {
      title: '用户名',
      dataIndex: 'name',
      key: 'name',
      render: (v: string) => v || '-',
    },
    {
      title: '全名',
      dataIndex: 'fullname',
      key: 'fullname',
      render: (v: string) => v || '-',
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      render: (v: string) => v || '-',
    },
    {
      title: 'OAuth 提供商',
      dataIndex: 'oauth_provider',
      key: 'oauth_provider',
      render: (v: string) => v ? <Tag>{v}</Tag> : '-',
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (v: string) => (
        <Tag color={v === 'admin' ? 'gold' : 'default'}>
          {v === 'admin' ? '管理员' : '普通用户'}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (v: number, record: User) => (
        <Switch
          checked={v === 1}
          checkedChildren="启用"
          unCheckedChildren="禁用"
          onChange={(checked) => handleToggleActive(record, checked)}
          size="small"
        />
      ),
    },
    {
      title: '注册时间',
      dataIndex: 'gmt_create',
      key: 'gmt_create',
      render: (v: string | null) =>
        v ? new Date(v).toLocaleDateString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: User) => (
        <Space>
          <Button
            size="small"
            type={record.role === 'admin' ? 'default' : 'primary'}
            onClick={() => handleToggleRole(record)}
          >
            {record.role === 'admin' ? '取消管理员' : '设为管理员'}
          </Button>
          {/* Show delete button only for admin users, hide for self */}
          {currentUser?.role === 'admin' && currentUser?.id !== record.id && (
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record)}
            >
              删除
            </Button>
          )}
        </Space>
      ),
    },
  ];

  if (oauthEnabled === null) {
    return null;
  }

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-white mb-1">用户管理</h1>
        <p className="text-sm text-gray-500">管理通过 OAuth2 登录的用户，设置角色与状态。</p>
      </div>

      <div className="mb-4">
        <Search
          placeholder="搜索用户名 / 邮箱"
          allowClear
          style={{ width: 300 }}
          onSearch={(v) => {
            setKeyword(v);
            setPage(1);
          }}
          prefix={<SearchOutlined className="text-gray-400" />}
        />
      </div>

      <Table<User>
        rowKey="id"
        columns={columns}
        dataSource={users}
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          onChange: (p) => setPage(p),
          showTotal: (t) => `共 ${t} 条`,
        }}
        scroll={{ x: 900 }}
        className="bg-white dark:bg-[#1a1a1a] rounded-xl shadow-sm"
      />
    </div>
  );
}
