import { ins as axios } from '@/client/api';
import type { AxiosError } from 'axios';

const API_BASE = '/api/v1';

export interface Role {
  id: number;
  name: string;
  description: string;
  is_system: number;
  gmt_create?: string | null;
  gmt_modify?: string | null;
}

export interface Permission {
  id: number;
  role_id: number;
  resource_type: string;
  resource_id: string;
  action: string;
  effect: string;
  gmt_create?: string | null;
}

export interface RoleCreateBody {
  name: string;
  description?: string;
}

export interface RoleUpdateBody {
  name?: string;
  description?: string;
}

export interface PermissionAddBody {
  resource_type: string;
  resource_id?: string;
  action: string;
  effect?: string;
}

export interface UserRoleAssignBody {
  role_id: number;
}

export interface GroupRolesRow {
  id: number;
  role_id: number;
  role_name: string;
}

export interface UserRolesRow {
  id: number;
  role_id: number;
  role_name: string;
}

export interface UserInfo {
  id: number;
  name: string;
  fullname: string;
  email: string;
  // 注意：不再使用旧版 role 字段，以 RBAC roles 为准
  is_active: number;
  roles: string[];
  gmt_create?: string | null;
}

export interface ScopedPermission {
  resource_type: string;
  resource_id: string;
  action: string;
  effect: string;
}

export interface PermissionDefinition {
  id: number;
  name: string;
  description: string;
  resource_type: string;
  resource_id: string;
  action: string;
  effect: string;
  is_active: boolean;
  gmt_create?: string | null;
  gmt_modify?: string | null;
}

export interface PermissionDefinitionCreateBody {
  name: string;
  description?: string;
  resource_type: string;
  resource_id?: string;
  action: string;
  effect?: string;
}

export interface PermissionDefinitionUpdateBody {
  name?: string;
  description?: string;
  resource_type?: string;
  resource_id?: string;
  action?: string;
  effect?: string;
  is_active?: boolean;
}

export interface UserPermissionsResponse {
  user_id: number;
  roles: string[];
  permissions: Record<string, {
    wildcard: string[];
    scoped: Record<string, string[]>;
  }>;
}

export interface UserDetail extends UserInfo {
  direct_roles: Role[];
  group_roles: Role[];
  all_roles: string[];
  effective_permissions: Record<string, string[]>;
}

export interface UserListResponse {
  items: UserInfo[];
  total: number;
  page: number;
  page_size: number;
}

function isNotFound(err: unknown): boolean {
  return Boolean(
    err &&
      typeof err === 'object' &&
      'response' in err &&
      (err as AxiosError).response?.status === 404,
  );
}

class PermissionsService {
  // ========== Role Management ==========
  async listRoles(): Promise<Role[]> {
    try {
      const res = await axios.get(`${API_BASE}/permissions/roles`);
      return (res.data?.data ?? []) as Role[];
    } catch (e) {
      if (isNotFound(e)) throw new Error('NOT_MOUNTED');
      throw e;
    }
  }

  async createRole(body: RoleCreateBody): Promise<Role> {
    const res = await axios.post(`${API_BASE}/permissions/roles`, body);
    return res.data.data as Role;
  }

  async getRole(roleId: number): Promise<Role> {
    const res = await axios.get(`${API_BASE}/permissions/roles/${roleId}`);
    return res.data.data as Role;
  }

  async updateRole(roleId: number, body: RoleUpdateBody): Promise<Role> {
    const res = await axios.put(`${API_BASE}/permissions/roles/${roleId}`, body);
    return res.data.data as Role;
  }

  async deleteRole(roleId: number): Promise<void> {
    await axios.delete(`${API_BASE}/permissions/roles/${roleId}`);
  }

  // ========== Role Permission Management ==========
  async listRolePermissions(roleId: number): Promise<Permission[]> {
    const res = await axios.get(`${API_BASE}/permissions/roles/${roleId}/permissions`);
    return (res.data?.data ?? []) as Permission[];
  }

  async addRolePermission(roleId: number, body: PermissionAddBody): Promise<Permission> {
    const res = await axios.post(`${API_BASE}/permissions/roles/${roleId}/permissions`, body);
    return res.data.data as Permission;
  }

  async removeRolePermission(roleId: number, permissionId: number): Promise<void> {
    await axios.delete(`${API_BASE}/permissions/roles/${roleId}/permissions/${permissionId}`);
  }

  // ========== User Role Assignment ==========
  async listUserRoles(userId: number): Promise<UserRolesRow[]> {
    const res = await axios.get(`${API_BASE}/permissions/users/${userId}/roles`);
    return (res.data?.data ?? []) as UserRolesRow[];
  }

  async assignRoleToUser(userId: number, roleId: number): Promise<void> {
    await axios.post(`${API_BASE}/permissions/users/${userId}/roles`, { role_id: roleId });
  }

  async removeUserRole(userId: number, roleId: number): Promise<void> {
    await axios.delete(`${API_BASE}/permissions/users/${userId}/roles/${roleId}`);
  }

  // ========== Group Role Assignment ==========
  async listGroupRoles(groupId: number): Promise<GroupRolesRow[]> {
    const res = await axios.get(`${API_BASE}/permissions/groups/${groupId}/roles`);
    return (res.data?.data ?? []) as GroupRolesRow[];
  }

  async assignRoleToGroup(groupId: number, roleId: number): Promise<void> {
    await axios.post(`${API_BASE}/permissions/groups/${groupId}/roles`, { role_id: roleId });
  }

  async removeGroupRole(groupId: number, roleId: number): Promise<void> {
    await axios.delete(`${API_BASE}/permissions/groups/${groupId}/roles/${roleId}`);
  }

  // ========== User Management ==========
  async listUsers(
    page: number = 1,
    pageSize: number = 20,
    keyword: string = '',
  ): Promise<UserListResponse> {
    const res = await axios.get(`${API_BASE}/permissions/users`, {
      params: { page, page_size: pageSize, keyword },
    });
    return res.data.data as UserListResponse;
  }

  async getUserDetail(userId: number): Promise<UserDetail> {
    const res = await axios.get(`${API_BASE}/permissions/users/${userId}`);
    return res.data.data as UserDetail;
  }

  async getUserEffectivePermissions(
    userId: number,
  ): Promise<{ roles: string[]; permissions: Record<string, string[]> }> {
    const res = await axios.get(
      `${API_BASE}/permissions/users/${userId}/effective-permissions`,
    );
    return res.data.data as { roles: string[]; permissions: Record<string, string[]> };
  }

  async batchAssignRoles(userId: number, roleIds: number[]): Promise<{
    assigned: number[];
    errors: string[];
  }> {
    const res = await axios.post(`${API_BASE}/permissions/users/${userId}/roles/batch`, {
      role_ids: roleIds,
    });
    return res.data.data as { assigned: number[]; errors: string[] };
  }

  async batchRemoveRoles(userId: number, roleIds: number[]): Promise<{
    removed: number[];
  }> {
    const res = await axios.post(
      `${API_BASE}/permissions/users/${userId}/roles/batch-remove`,
      { role_ids: roleIds },
    );
    return res.data.data as { removed: number[] };
  }

  // ========== Scoped Resource Permissions ==========
  async listScopedPermissions(params?: {
    role_id?: number;
    resource_type?: string;
    resource_id?: string;
  }): Promise<Permission[]> {
    const res = await axios.get(`${API_BASE}/permissions/scoped/list`, { params });
    return (res.data?.data ?? []) as Permission[];
  }

  async grantScopedPermission(params: {
    role_id: number;
    resource_type: string;
    resource_id: string;
    action: string;
    effect?: string;
  }): Promise<Permission> {
    const res = await axios.post(`${API_BASE}/permissions/scoped`, params);
    return res.data.data as Permission;
  }

  async revokeScopedPermission(params: {
    role_id: number;
    resource_type: string;
    resource_id: string;
    action: string;
  }): Promise<void> {
    await axios.delete(`${API_BASE}/permissions/scoped`, { params });
  }

  async getUserPermissions(userId: number): Promise<UserPermissionsResponse> {
    const res = await axios.get(`${API_BASE}/permissions/users/${userId}/permissions`);
    return res.data.data as UserPermissionsResponse;
  }

  // ========== Permission Definitions ==========
  async listPermissionDefinitions(params?: {
    resource_type?: string;
    action?: string;
    is_active?: boolean;
  }): Promise<PermissionDefinition[]> {
    const res = await axios.get(`${API_BASE}/permissions/definitions`, { params });
    return (res.data?.data ?? []) as PermissionDefinition[];
  }

  async createPermissionDefinition(
    body: PermissionDefinitionCreateBody,
  ): Promise<PermissionDefinition> {
    const res = await axios.post(`${API_BASE}/permissions/definitions`, body);
    return res.data.data as PermissionDefinition;
  }

  async getPermissionDefinition(id: number): Promise<PermissionDefinition> {
    const res = await axios.get(`${API_BASE}/permissions/definitions/${id}`);
    return res.data.data as PermissionDefinition;
  }

  async updatePermissionDefinition(
    id: number,
    body: PermissionDefinitionUpdateBody,
  ): Promise<PermissionDefinition> {
    const res = await axios.put(`${API_BASE}/permissions/definitions/${id}`, body);
    return res.data.data as PermissionDefinition;
  }

  async deletePermissionDefinition(id: number): Promise<void> {
    await axios.delete(`${API_BASE}/permissions/definitions/${id}`);
  }

  async getRolePermissionDefs(roleId: number): Promise<PermissionDefinition[]> {
    const res = await axios.get(`${API_BASE}/permissions/roles/${roleId}/permission-defs`);
    return (res.data?.data ?? []) as PermissionDefinition[];
  }

  async addPermissionDefToRole(
    roleId: number,
    permissionDefId: number,
  ): Promise<{ id: number; role_id: number; permission_def_id: number }> {
    const res = await axios.post(`${API_BASE}/permissions/roles/${roleId}/permission-defs`, {
      permission_def_id: permissionDefId,
    });
    return res.data.data as { id: number; role_id: number; permission_def_id: number };
  }

  async removePermissionDefFromRole(
    roleId: number,
    permissionDefId: number,
  ): Promise<void> {
    await axios.delete(
      `${API_BASE}/permissions/roles/${roleId}/permission-defs/${permissionDefId}`,
    );
  }
}

export const permissionsService = new PermissionsService();
export { isNotFound };