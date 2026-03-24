import { ins as axios } from '@/client/api';

const API_BASE = '/api/v1';

export interface User {
  id: number;
  name: string;
  fullname: string;
  email: string;
  avatar: string;
  oauth_provider: string;
  oauth_id: string;
  role: string;
  is_active: number;
  gmt_create: string | null;
  gmt_modify: string | null;
}

export interface ListUsersResult {
  list: User[];
  total: number;
  page: number;
  page_size: number;
}

class UsersService {
  async listUsers(
    page = 1,
    pageSize = 20,
    keyword = '',
  ): Promise<ListUsersResult> {
    const res = await axios.get(`${API_BASE}/users`, {
      params: { page, page_size: pageSize, keyword },
    });
    return res.data.data as ListUsersResult;
  }

  /** Paginate until all users loaded (API caps page_size at 100). */
  async listAllUsers(keyword = '', maxPages = 50): Promise<User[]> {
    const pageSize = 100;
    const all: User[] = [];
    let page = 1;
    let total = Infinity;
    while (all.length < total && page <= maxPages) {
      const r = await this.listUsers(page, pageSize, keyword);
      all.push(...r.list);
      total = r.total;
      if (r.list.length < pageSize) break;
      page += 1;
    }
    return all;
  }

  async getUser(id: number): Promise<User> {
    const res = await axios.get(`${API_BASE}/users/${id}`);
    return res.data.data as User;
  }

  async updateUser(
    id: number,
    patch: { role?: string; is_active?: number },
  ): Promise<User> {
    const res = await axios.patch(`${API_BASE}/users/${id}`, patch);
    return res.data.data as User;
  }
}

export const usersService = new UsersService();
