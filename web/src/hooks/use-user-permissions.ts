'use client';

import { useCallback, useEffect, useState } from 'react';
import { permissionsService, isNotFound } from '@/services/permissions';
import { getUserId } from '@/utils/storage';
import { authService } from '@/services/auth';
import { message } from 'antd';

export interface UserPermissions {
  roles: string[];
  permissions: Record<string, string[]>;
}

export function useUserPermissions() {
  const [permissions, setPermissions] = useState<UserPermissions | null>(null);
  const [loading, setLoading] = useState(true);
  const [oauthEnabled, setOauthEnabled] = useState<boolean | null>(null);

  // First check OAuth status
  useEffect(() => {
    authService.getOAuthStatus().then((s) => setOauthEnabled(s.enabled));
  }, []);

  const fetchPermissions = useCallback(async () => {
    // Skip if OAuth is not enabled (no real login)
    if (oauthEnabled === false) {
      setLoading(false);
      return;
    }

    // Wait for OAuth status check
    if (oauthEnabled === null) {
      return;
    }

    const userId = getUserId();
    if (!userId) {
      setLoading(false);
      return;
    }

    try {
      const data = await permissionsService.getUserEffectivePermissions(Number(userId));
      setPermissions(data);
    } catch (e) {
      // Silent fail - permissions API might not be available
      if (isNotFound(e)) {
        // Permissions plugin not enabled, treat as no restrictions
        console.debug('Permissions API not available (plugin not enabled)');
      } else {
        console.debug('Failed to fetch user permissions:', e);
      }
    } finally {
      setLoading(false);
    }
  }, [oauthEnabled]);

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
