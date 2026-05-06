import { ins as axios } from '@/client/api';
import type { User } from '@/services/users';

const API_BASE = '/api/v1';

export interface OAuthProvider {
  id: string;
  type: string;
}

export interface OAuthStatus {
  enabled: boolean;
  providers: OAuthProvider[];
}

export interface LocalLoginRequest {
  username: string;
  password: string;
}

export interface LocalRegisterRequest {
  username: string;
  password: string;
  email?: string;
  fullname?: string;
}

export interface AuthUser {
  id: number;
  name: string;
  fullname: string;
  email?: string;
  avatar?: string;
  oauth_provider?: string;
  oauth_id?: string;
}

export interface MeResponse {
  user: AuthUser;
  user_channel: string;
  user_no: string;
  nick_name: string;
  avatar_url?: string;
  email?: string;
  role?: string;
}

class AuthService {
  async getOAuthStatus(): Promise<OAuthStatus> {
    try {
      const response = await axios.get(`${API_BASE}/auth/oauth/status`);
      return response.data;
    } catch {
      return { enabled: false, providers: [] };
    }
  }

  async getMe(): Promise<MeResponse> {
    const response = await axios.get(`${API_BASE}/auth/me`);
    return response.data;
  }

  /** Maps /auth/me to the users table shape (for user admin UI). */
  async getCurrentUser(): Promise<User | null> {
    try {
      const me = await this.getMe();
      const u = me.user;
      if (u == null || typeof u.id !== 'number') {
        return null;
      }
      const extra = u as AuthUser & {
        is_active?: number;
        gmt_create?: string | null;
        gmt_modify?: string | null;
      };
      return {
        id: u.id,
        name: u.name ?? '',
        fullname: u.fullname ?? '',
        email: u.email ?? '',
        avatar: u.avatar ?? me.avatar_url ?? '',
        oauth_provider: u.oauth_provider ?? '',
        oauth_id: u.oauth_id ?? '',
        role: me.role ?? 'normal',
        is_active: typeof extra.is_active === 'number' ? extra.is_active : 1,
        gmt_create: extra.gmt_create ?? null,
        gmt_modify: extra.gmt_modify ?? null,
      };
    } catch {
      return null;
    }
  }

  async logout(): Promise<void> {
    await axios.post(`${API_BASE}/auth/logout`);
  }

  getOAuthLoginUrl(provider: string): string {
    const base = typeof window !== 'undefined' ? window.location.origin : '';
    return `${base}/api/v1/auth/oauth/login?provider=${encodeURIComponent(provider)}`;
  }

  async localLogin(data: LocalLoginRequest): Promise<MeResponse> {
    const payload = { ...data, password: btoa(data.password) };
    const response = await axios.post(`${API_BASE}/auth/local/login`, payload);
    return response.data;
  }

  async localRegister(data: LocalRegisterRequest): Promise<MeResponse> {
    const payload = { ...data, password: btoa(data.password) };
    const response = await axios.post(`${API_BASE}/auth/local/register`, payload);
    return response.data;
  }
}

export const authService = new AuthService();
