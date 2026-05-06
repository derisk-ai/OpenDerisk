'use client';

import { useCallback, useEffect, useState } from 'react';
import { permissionsService } from '@/services/permissions';
import { getUserId } from '@/utils/storage';
import { message } from 'antd';

export interface UserPermissions {
  roles: string[];
  permissions: Record<string, string[]>;
}

export function useUserPermissions() {
  const [permissions, setPermissions] = useState<UserPermissions | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchPermissions = useCallback(async () => {
    const userId = getUserId();
    if (!userId) {
      setLoading(false);
      return;
    }

    try {
      const data = await permissionsService.getUserEffectivePermissions(Number(userId));
      setPermissions(data);
    } catch (e) {
      // Silent fail - permissions might not be enabled
      console.debug('Failed to fetch user permissions:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPermissions();
  }, [fetchPermissions]);

  const hasPermission = useCallback(
    (resourceType: string, action: string): boolean => {
      if (!permissions) return true; // If permissions not loaded, allow by default
      const actions = permissions.permissions[resourceType] || [];
      return actions.includes('*') || actions.includes(action);
    },
    [permissions]
  );

  const hasResourceRead = useCallback(
    (resourceType: string): boolean => {
      return hasPermission(resourceType, 'read');
    },
    [hasPermission]
  );

  return {
    permissions,
    loading,
    hasPermission,
    hasResourceRead,
    refresh: fetchPermissions,
  };
}
