'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Tabs, Alert } from 'antd';
import { useTranslation } from 'react-i18next';
import { TeamOutlined, UserOutlined, SafetyCertificateOutlined, KeyOutlined } from '@ant-design/icons';
import RoleManagement from '@/components/permissions/RoleManagement';
import UserManagement from '@/components/permissions/UserManagement';
import CustomPermissions from '@/components/permissions/CustomPermissions';
import GroupManagement from '@/components/permissions/GroupManagement';
import { permissionsService, type Role } from '@/services/permissions';

type IdentityTabKey = 'users' | 'groups' | 'roles';
type PermissionTabKey = 'policies';

export default function PermissionsPage() {
  const { t } = useTranslation();
  const [activeMainTab, setActiveMainTab] = useState<'identity' | 'permission'>('identity');
  const [activeIdentityTab, setActiveIdentityTab] = useState<IdentityTabKey>('users');
  const [activePermissionTab, setActivePermissionTab] = useState<PermissionTabKey>('policies');
  const [roles, setRoles] = useState<Role[]>([]);

  const loadRoles = useCallback(async () => {
    try {
      const rolesData = await permissionsService.listRoles();
      setRoles(rolesData);
    } catch (e) {
      console.error('Failed to load roles:', e);
    }
  }, []);

  useEffect(() => {
    loadRoles();
  }, [loadRoles]);

  // 身份管理子 Tab
  const identityItems = [
    {
      key: 'users',
      label: (
        <span>
          <UserOutlined /> {t('permissions_col_user') || '用户'}
        </span>
      ),
      children: <UserManagement roles={roles} />,
    },
    {
      key: 'groups',
      label: (
        <span>
          <TeamOutlined /> {t('permissions_user_groups') || '用户组'}
        </span>
      ),
      children: <GroupManagement roles={roles} />,
    },
    {
      key: 'roles',
      label: (
        <span>
          <SafetyCertificateOutlined /> {t('permissions_role_management') || '角色'}
        </span>
      ),
      children: <RoleManagement roles={roles} onRolesChange={loadRoles} />,
    },
  ];

  // 权限管理子 Tab
  const permissionItems = [
    {
      key: 'policies',
      label: (
        <span>
          <KeyOutlined /> {t('permissions_policies') || '策略'}
        </span>
      ),
      children: <CustomPermissions roles={roles} />,
    },
  ];

  // 主 Tab
  const mainItems = [
    {
      key: 'identity',
      label: t('permissions_identity_management') || '身份管理',
      children: (
        <Tabs
          activeKey={activeIdentityTab}
          onChange={(key) => setActiveIdentityTab(key as IdentityTabKey)}
          items={identityItems}
        />
      ),
    },
    {
      key: 'permission',
      label: t('permissions_permission_management') || '权限管理',
      children: (
        <Tabs
          activeKey={activePermissionTab}
          onChange={(key) => setActivePermissionTab(key as PermissionTabKey)}
          items={permissionItems}
        />
      ),
    },
  ];

  return (
    <div className="p-6 h-full overflow-auto">
      <Alert
        type="info"
        showIcon
        className="mb-4"
        message={t('permissions_title')}
        description={t('permissions_page_hint') || '基于角色的访问控制：在此统一管理身份与权限。身份管理用于管理用户、用户组和角色；权限管理用于管理策略。'}
      />
      <Tabs
        activeKey={activeMainTab}
        onChange={(key) => setActiveMainTab(key as 'identity' | 'permission')}
        items={mainItems}
      />
    </div>
  );
}