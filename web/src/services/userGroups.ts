import { ins as axios } from '@/client/api';
import type { AxiosError } from 'axios';

const API_BASE = '/api/v1';

export interface UserGroupRow {
  id: number;
  name: string;
  description: string;
  member_count?: number;
  gmt_create?: string | null;
  gmt_modify?: string | null;
}

export interface UserGroupMemberRow {
  id: number;
  group_id: number;
  user_id: number;
  gmt_create?: string | null;
}

function isNotFound(err: unknown): boolean {
  return Boolean(
    err &&
      typeof err === 'object' &&
      'response' in err &&
      (err as AxiosError).response?.status === 404,
  );
}

class UserGroupsService {
  async listGroups(): Promise<UserGroupRow[]> {
    try {
      const res = await axios.get(`${API_BASE}/user-groups/groups`);
      return (res.data?.data ?? []) as UserGroupRow[];
    } catch (e) {
      if (isNotFound(e)) throw new Error('NOT_MOUNTED');
      throw e;
    }
  }

  async createGroup(name: string, description?: string): Promise<UserGroupRow> {
    const res = await axios.post(`${API_BASE}/user-groups/groups`, {
      name,
      description: description || undefined,
    });
    return res.data.data as UserGroupRow;
  }

  async deleteGroup(groupId: number): Promise<void> {
    await axios.delete(`${API_BASE}/user-groups/groups/${groupId}`);
  }

  async listMembers(groupId: number): Promise<UserGroupMemberRow[]> {
    const res = await axios.get(`${API_BASE}/user-groups/groups/${groupId}/members`);
    return (res.data?.data ?? []) as UserGroupMemberRow[];
  }

  async addMembers(groupId: number, userIds: number[]): Promise<number> {
    const res = await axios.post(`${API_BASE}/user-groups/groups/${groupId}/members`, {
      user_ids: userIds,
    });
    return (res.data?.data?.added ?? 0) as number;
  }

  async removeMember(groupId: number, memberUserId: number): Promise<void> {
    await axios.delete(
      `${API_BASE}/user-groups/groups/${groupId}/members/${memberUserId}`,
    );
  }
}

export const userGroupsService = new UserGroupsService();
export { isNotFound };
