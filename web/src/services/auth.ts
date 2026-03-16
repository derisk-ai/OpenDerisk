import axios from 'axios';

const API_BASE = '/api/v1';

export interface OAuthStatus {
  enabled: boolean;
  providers: Array<{ id: string; type: string }>;
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

  async logout(): Promise<void> {
    await axios.post(`${API_BASE}/auth/logout`);
  }

  getOAuthLoginUrl(provider: string): string {
    const base = typeof window !== 'undefined' ? window.location.origin : '';
    return `${base}/api/v1/auth/oauth/login?provider=${encodeURIComponent(provider)}`;
  }
}

export const authService = new AuthService();
