'use client';

import React, { useEffect, useState } from 'react';
import { Card, Table, Tag, Space, Typography, Spin, Alert, Tabs } from 'antd';
import { useTranslation } from 'react-i18next';
import { permissionsService, type Permission, type UserPermissionsResponse } from '@/services/permissions';

const { Text, Title } = Typography;

interface UserPermissionsPanelProps {
  userId: number;
}

interface ScopedPermissionTableItem {
  key: string;
  resource_type: string;
  resource_id: string;
  action: string;
  effect: string;
}

/**
 * User Permissions Panel Component (T2.3)
 *
 * Displays a user's effective permissions including:
 * - Wildcard permissions (resource_id="*")
 * - Scoped permissions (resource_id=specific resource)
 */
export default function UserPermissionsPanel({ userId }: UserPermissionsPanelProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [permissions, setPermissions] = useState<UserPermissionsResponse | null>(null);

  useEffect(() => {
    const loadPermissions = async () => {
      setLoading(true);
      try {
        const data = await permissionsService.getUserPermissions(userId);
        setPermissions(data);
      } catch (error) {
        console.error('Failed to load user permissions:', error);
      } finally {
        setLoading(false);
      }
    };

    if (userId) {
      loadPermissions();
    }
  }, [userId]);

  if (loading) {
    return <Spin size="large" />;
  }

  if (!permissions) {
    return (
      <Alert
        type="warning"
        message={t('permissions_load_user_detail_error')}
        description="Failed to load user permissions"
      />
    );
  }

  // Build table data for wildcard permissions
  const buildWildcardData = (): ScopedPermissionTableItem[] => {
    const items: ScopedPermissionTableItem[] = [];

    Object.entries(permissions.permissions || {}).forEach(([resourceType, permData]) => {
      if (permData.wildcard && permData.wildcard.length > 0) {
        permData.wildcard.forEach((action) => {
          items.push({
            key: `${resourceType}:*:${action}`,
            resource_type: resourceType,
            resource_id: '*',
            action: action,
            effect: 'allow',
          });
        });
      }
    });

    return items;
  };

  // Build table data for scoped permissions
  const buildScopedData = (): ScopedPermissionTableItem[] => {
    const items: ScopedPermissionTableItem[] = [];

    Object.entries(permissions.permissions || {}).forEach(([resourceType, permData]) => {
      if (permData.scoped) {
        Object.entries(permData.scoped).forEach(([resourceId, actions]) => {
          actions.forEach((action) => {
            items.push({
              key: `${resourceType}:${resourceId}:${action}`,
              resource_type: resourceType,
              resource_id: resourceId,
              action: action,
              effect: 'allow',
            });
          });
        });
      }
    });

    return items;
  };

  const wildcardColumns = [
    {
      title: t('permissions_resource_type'),
      dataIndex: 'resource_type',
      key: 'resource_type',
      width: 120,
      render: (type: string) => <Tag>{type}</Tag>,
    },
    {
      title: t('permissions_resource_id'),
      dataIndex: 'resource_id',
      key: 'resource_id',
      width: 150,
      render: () => (
        <Tag color="red">{t('permissions_all_resources')}</Tag>
      ),
    },
    {
      title: t('permissions_action'),
      dataIndex: 'action',
      key: 'action',
      width: 100,
      render: (action: string) => <Tag color="blue">{action}</Tag>,
    },
    {
      title: t('permissions_col_actions'),
      key: 'effect',
      width: 80,
      render: () => <Tag color="green">{t('active')}</Tag>,
    },
  ];

  const scopedColumns = [
    {
      title: t('permissions_resource_type'),
      dataIndex: 'resource_type',
      key: 'resource_type',
      width: 120,
      render: (type: string) => <Tag>{type}</Tag>,
    },
    {
      title: t('permissions_resource_id'),
      dataIndex: 'resource_id',
      key: 'resource_id',
      width: 200,
      render: (id: string) => (
        <Tag color="blue">{id === '*' ? t('permissions_all_resources') : id}</Tag>
      ),
    },
    {
      title: t('permissions_action'),
      dataIndex: 'action',
      key: 'action',
      width: 100,
      render: (action: string) => <Tag color="green">{action}</Tag>,
    },
    {
      title: t('permissions_col_actions'),
      key: 'effect',
      width: 80,
      render: () => <Tag color="green">{t('active')}</Tag>,
    },
  ];

  const wildcardData = buildWildcardData();
  const scopedData = buildScopedData();

  const tabItems = [
    {
      key: 'scoped',
      label: `${t('permissions_scoped')} (${scopedData.length})`,
      children: (
        <Table
          columns={scopedColumns}
          dataSource={scopedData}
          pagination={false}
          size="small"
          scroll={{ x: 600 }}
          locale={{ emptyText: t('permissions_empty') }}
        />
      ),
    },
    {
      key: 'wildcard',
      label: `${t('permissions_wildcard')} (${wildcardData.length})`,
      children: (
        <Table
          columns={wildcardColumns}
          dataSource={wildcardData}
          pagination={false}
          size="small"
          scroll={{ x: 600 }}
          locale={{ emptyText: t('permissions_empty') }}
        />
      ),
    },
  ];

  return (
    <Card
      title={
        <Space>
          <Text strong>{t('permissions_effective_permissions')}</Text>
          <Tag color="purple">{permissions.roles.join(', ') || t('permissions_no_roles')}</Tag>
        </Space>
      }
      size="small"
    >
      <Alert
        type="info"
        showIcon
        className="mb-4"
        message={t('permissions_scoped_permission_hint')}
      />

      <Tabs items={tabItems} size="small" />

      {/* Summary by Resource Type */}
      <div className="mt-4 pt-4 border-t">
        <Text strong className="block mb-2">
          {t('permissions_effective_permissions')} {t('permissions_by_resource')}:
        </Text>
        <Space wrap>
          {Object.entries(permissions.permissions || {}).map(([resourceType, permData]) => {
            const wildcardCount = permData.wildcard?.length || 0;
            const scopedCount = Object.keys(permData.scoped || {}).length;
            const totalCount = wildcardCount + scopedCount;

            if (totalCount === 0) return null;

            return (
              <Tag key={resourceType} color="purple" className="px-3 py-1">
                {resourceType}: {wildcardCount}
                {t('permissions_wildcard_short')} + {scopedCount}
                {t('permissions_scoped_short')}
              </Tag>
            );
          })}
        </Space>
      </div>
    </Card>
  );
}